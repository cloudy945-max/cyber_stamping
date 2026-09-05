#!/usr/bin/env python
"""
stamp_extractor.app
====================
CLI 入口。独立小工具。

示例：
    # 单张
    python stamp_extractor/app.py --input input/IMG_8181.HEIC --output output/

    # 批量（默认递归）
    python stamp_extractor/app.py --input input/ --output output/ --debug debug/

    # 用更保守的参数（对印刷颗粒少的干净图片）
    python stamp_extractor/app.py -i input/ -o output/ --preset conservative

    # 用「保留淡墨优先」参数
    python stamp_extractor/app.py -i input/ -o output/ --preset preserve_light

    # 自定义参数覆盖
    python stamp_extractor/app.py -i input/ -o output/ --ink-low 1.8 --ink-high 9 --alpha-strength 1.2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许 `python stamp_extractor/app.py` 直接运行（把父级加入 sys.path）
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stamp_extractor.config import ExtractorConfig  # noqa: E402
from stamp_extractor.batch_processor import process_batch  # noqa: E402
from stamp_extractor.utils import list_images  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stamp_extractor",
        description=("高保真印章墨迹 Alpha 提取工具。只改 Alpha，不改 RGB。 "
                     "纸张内外的纸色区域一律变透明；原始墨迹的颗粒/磨损/淡墨全部保留。"),
    )
    p.add_argument("-i", "--input", required=True, type=Path, help="输入文件或目录")
    p.add_argument("-o", "--output", required=True, type=Path, help="输出目录（会自动创建）")
    p.add_argument("-d", "--debug", type=Path, default=None, help="Debug 图目录（默认 output 同级的 debug/）")
    p.add_argument("--preset", choices=["default", "conservative", "preserve_light"], default="default",
                   help="参数预设；默认 default，保守（更干净）选 conservative，保留淡墨选 preserve_light")
    p.add_argument("--no-debug", action="store_true", help="关闭 Debug 图保存")
    p.add_argument("--no-recursive", action="store_true", help="目录模式下不递归子目录")
    p.add_argument("--no-auto-crop", action="store_true", help="关闭自动裁切（保留原图尺寸）")

    # 核心阈值（直接覆盖预设）
    g = p.add_argument_group("核心阈值")
    g.add_argument("--ink-low", type=float, default=None, help="Alpha 平滑起点（越低保留越淡）")
    g.add_argument("--ink-high", type=float, default=None, help="Alpha 平滑终点")
    g.add_argument("--alpha-strength", type=float, default=None, help="Alpha 增益（建议 1.0~1.3）")
    g.add_argument("--light-ink", action="store_true",
                   help="快捷把 ink-low 调低，等价于 --preset preserve_light 的阈值部分")

    g2 = p.add_argument_group("颜色距离与背景")
    g2.add_argument("--weight-L", type=float, default=None)
    g2.add_argument("--weight-a", type=float, default=None)
    g2.add_argument("--weight-b", type=float, default=None)
    g2.add_argument("--sat-boost", type=float, default=None, help="饱和度加分 0..1")
    g2.add_argument("--dark-boost", type=float, default=None, help="暗色加分 0..1")
    g2.add_argument("--local-bg-gain", type=float, default=None,
                    help="局部亮度归一化强度 0..1（0 关，1 完全补偿）")
    g2.add_argument("--local-bg-off", action="store_true", help="关闭局部亮度归一化")

    g3 = p.add_argument_group("局部对比度 & 噪声")
    g3.add_argument("--lc-off", action="store_true", help="关闭局部对比度加分")
    g3.add_argument("--lc-strength", type=float, default=None, help="局部对比度加分强度（默认 0.3）")
    g3.add_argument("--noise-min-area", type=int, default=None, help="最小连通域（像素，默认 0=关）")
    g3.add_argument("--noise-median", type=int, default=None, help="中值滤波核 0 或 3（默认 0=关）")

    g4 = p.add_argument_group("其他")
    g4.add_argument("--desat-paper", action="store_true",
                    help="【实验】启用纸张染色去除（默认关闭，默认输出纯原 RGB）")
    g4.add_argument("--crop-thr", type=int, default=None, help="自动裁边 Alpha 阈值（默认 12）")

    g5 = p.add_argument_group("邮票外围区域清零（聊天截图/jfif 必开；img1~3 的默认行为）",
                              "分两阶段，阶段 B 是主力，也会处理方形图里圆形邮票的四角纸张。\n"
                              "阶段只删除 mask 外部的像素；邮票内部空白仍按 InkScore 正常透明化，绝不填实内部。")
    g5.add_argument("--drop-outer-region", dest="drop_outer_region", action="store_true",
                    default=None, help="阶段A:开启删除大片纯白聊天背景（默认开）")
    g5.add_argument("--no-drop-outer-region", dest="drop_outer_region", action="store_false",
                    help="阶段A:关闭；仅当你的输入已经是紧密裁剪好的照片时使用")
    g5.add_argument("--chat-bg-L-min", type=float, default=None,
                    help="阶段A阈值：聊天背景纯白的 L 下限（默认 96.0，越大越严格只认纯白）")
    g5.add_argument("--chat-bg-chroma-max", type=float, default=None,
                    help="阶段A阈值：聊天背景的 chroma 上限（默认 4.0，越小越严格认无色）")
    g5.add_argument("--stamp-region-close", type=int, default=None,
                    help="阶段A齿孔闭合半径（默认 3px；仅作用 region mask，不作用于 ink Alpha）")
    g5.add_argument("--stamp-region-border", type=int, default=None,
                    help="阶段A外扩安全边（默认 4px）")

    g5.add_argument("--drop-outline", dest="drop_outline", action="store_true",
                    default=None, help="阶段B:开启 按墨水分布推导邮票外轮廓多边形并删除多边形外部（默认开）——这是主力")
    g5.add_argument("--no-drop-outline", dest="drop_outline", action="store_false",
                    help="阶段B:关闭（不推荐）")
    g5.add_argument("--outline-close", type=int, default=None,
                    help="阶段B 桥接外轮廓缺口 closing 半径（默认 32）。越大越能跨越大缺口；但异形邮票别开太大。")
    g5.add_argument("--outline-border", type=int, default=None,
                    help="阶段B polygon 外扩安全边（默认 10），防止把最外圈齿孔/齿牙误删。")
    g5.add_argument("--outline-seed-thr", type=int, default=None,
                    help="阶段B 种子最小 Alpha（默认 60）；调高能更狠地排除纸纹理。")
    g5.add_argument("--outline-ignore-border", type=int, default=None,
                    help="阶段B 忽略工作图最外圈 N 像素的种子（默认 0=自适应 close+8；建议 subregion 裁切场景给 40 左右）。")
    g5.add_argument("--outline-chroma-min", type=float, default=None,
                    help="阶段B 种子最小 chroma（默认 8）；灰色背景 alpha 高但饱和度低，设此值可排除。黑色/灰色墨水印章建议设 0。")

    g6 = p.add_argument_group("Artifact 近纯黑 letterbox / 黑边硬清零")
    g6.add_argument("--no-drop-pure-black", dest="drop_pb", action="store_false",
                    default=None, help="关闭：不把近纯黑像素视为聊天截图 artifact（默认开启）")
    g6.add_argument("--pure-black-rgb", type=int, default=None,
                    help="判定 artifact 的 RGB 全通道上限（默认 15）；例如写 20 则 R,G,B 全都 <= 20 判为 artifact")

    return p


def apply_args_to_cfg(cfg: ExtractorConfig, args: argparse.Namespace) -> ExtractorConfig:
    if args.ink_low is not None: cfg.ink_low = args.ink_low
    if args.ink_high is not None: cfg.ink_high = args.ink_high
    if args.alpha_strength is not None: cfg.alpha_strength = args.alpha_strength
    if args.light_ink:
        cfg.ink_low = min(cfg.ink_low, 1.6)
        cfg.ink_high = min(cfg.ink_high, 9.0)
        cfg.alpha_strength = max(cfg.alpha_strength, 1.15)

    if args.weight_L is not None: cfg.weight_L = args.weight_L
    if args.weight_a is not None: cfg.weight_a = args.weight_a
    if args.weight_b is not None: cfg.weight_b = args.weight_b
    if args.sat_boost is not None: cfg.saturation_boost = args.sat_boost
    if args.dark_boost is not None: cfg.darkness_boost = args.dark_boost
    if args.local_bg_gain is not None: cfg.local_bg_gain = args.local_bg_gain
    if args.local_bg_off: cfg.local_bg_enabled = False

    if args.lc_off: cfg.local_contrast_enabled = False
    if args.lc_strength is not None: cfg.local_contrast_strength = args.lc_strength
    if args.noise_min_area is not None: cfg.noise_min_area = args.noise_min_area
    if args.noise_median is not None: cfg.noise_median_ksize = args.noise_median

    if args.desat_paper: cfg.desaturate_paper_tint = True
    if args.crop_thr is not None: cfg.auto_crop_alpha_threshold = args.crop_thr
    if args.no_auto_crop: cfg.auto_crop = False
    if args.no_debug: cfg.save_debug_images = False

    # 邮票外围清零开关（默认 True；若用户显式传 --no-drop-outer-region 则为 False）
    if args.drop_outer_region is not None:
        cfg.drop_outer_stamp_region = args.drop_outer_region
    if args.chat_bg_L_min is not None: cfg.chat_bg_L_min = args.chat_bg_L_min
    if args.chat_bg_chroma_max is not None: cfg.chat_bg_chroma_max = args.chat_bg_chroma_max
    if args.stamp_region_close is not None: cfg.stamp_region_close_px = args.stamp_region_close
    if args.stamp_region_border is not None: cfg.stamp_region_border_px = args.stamp_region_border
    if args.drop_outline is not None:
        cfg.drop_outside_stamp_outline = args.drop_outline
    if args.outline_close is not None: cfg.outline_close_bridge_px = args.outline_close
    if args.outline_border is not None: cfg.outline_outer_border_px = args.outline_border
    if args.outline_seed_thr is not None: cfg.outline_seed_alpha_thr = args.outline_seed_thr
    if args.outline_ignore_border is not None: cfg.outline_ignore_border_px = args.outline_ignore_border
    if args.outline_chroma_min is not None: cfg.outline_seed_chroma_min = args.outline_chroma_min
    if args.drop_pb is not None:      cfg.artifact_pure_black_drop = bool(args.drop_pb)
    if args.pure_black_rgb is not None: cfg.artifact_pure_black_max_rgb = int(args.pure_black_rgb)
    return cfg


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # 预设
    if args.preset == "default":
        cfg = ExtractorConfig.defaults()
    elif args.preset == "conservative":
        cfg = ExtractorConfig.conservative()
    elif args.preset == "preserve_light":
        cfg = ExtractorConfig.preserve_light_ink()
    else:
        cfg = ExtractorConfig.defaults()

    apply_args_to_cfg(cfg, args)

    inp: Path = args.input
    out: Path = args.output
    out.mkdir(parents=True, exist_ok=True)

    debug_dir: Path | None = args.debug
    if debug_dir is None and cfg.save_debug_images:
        debug_dir = out.parent / "debug" if out.name != "output" else out.parent / "debug"
        # 如果 output 就是项目的 output 目录，debug 用并列的 debug
        if debug_dir == Path("debug"):
            debug_dir = _HERE / "debug"
    if cfg.save_debug_images and debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)

    # 收集输入
    if inp.is_dir():
        inputs = list_images(inp, recursive=not args.no_recursive)
        if not inputs:
            print(f"[!] 在目录 {inp} 下未找到支持的图片。", file=sys.stderr)
            return 2
    elif inp.is_file():
        inputs = [inp]
    else:
        print(f"[!] 输入不存在: {inp}", file=sys.stderr)
        return 2

    print(f"[INFO] 待处理 {len(inputs)} 张，preset={args.preset}")
    print(f"[INFO]   ink_low={cfg.ink_low}  ink_high={cfg.ink_high}  alpha_strength={cfg.alpha_strength}")
    print(f"[INFO]   local_bg={'ON(gain=%.2f)'%cfg.local_bg_gain if cfg.local_bg_enabled else 'OFF'}  "
          f"local_contrast={'ON(strength=%.2f)'%cfg.local_contrast_strength if cfg.local_contrast_enabled else 'OFF'}")
    print(f"[INFO]   noise_min_area={cfg.noise_min_area}  noise_median={cfg.noise_median_ksize}  "
          f"desat_paper_tint={cfg.desaturate_paper_tint}")

    process_batch(inputs, output_dir=out, debug_dir=debug_dir, cfg=cfg, verbose=True)
    print(f"\n✅ 全部完成。输出：{out}")
    if debug_dir is not None and cfg.save_debug_images:
        print(f"   Debug：{debug_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
