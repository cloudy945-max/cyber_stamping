# -*- coding: utf-8 -*-
"""
stamp_extractor.checkpoint_v2_params
====================================

v2 参数快照 / 回滚参考。
创建时间：2026-08-29（继 v1 之后）

背景：
  在 v1 版 outline 外围清零的基础上，跑 img1~3（3 张 jfif 聊天截图）发现：
  - locate_stamp_subregion_bbox 定位出的方形工作图，最外圈带有 80px 厚的纯黑 letterbox
    （聊天截图常见的「卡片黑边框」），RGB=[0,0,0]，距离纸色估计 L=47 极远，
    InkScore 直接把它判为「最浓墨水」→ alpha=255，占工作图面积 ≈33.4%。
  - 结果：closing(r=32, 2 iters) 把 letterbox 和邮票内墨水连成一片，
    最大 RETR_EXTERNAL contour 包成一个实心矩形，凸包/原轮廓都覆盖整图，
    region_ratio=1.0 → 四角的纸（圆形邮票在方形里的外侧）完全无法删除。

  于是 v2 引入 3 层互补修复，并重新跑了 img1~3 的 default / preserve_light / conservative
  三档预设，输出 PNG 四角与外围边缘的 Alpha 现在 90~99% 为 0，符合需求。

回滚方式：
  - 如果 v2 把真实深黑印章/黑色墨水误删，把下面的 artifact_pure_black_drop 改回 False
    或 CLI 加 `--no-drop-pure-black`。
  - 如果凸包把非凸/异形邮票（蝴蝶/人形等）外形放得太大，提高 hull_area/raw_area 的
    阈值 1.20 → 1.3~1.5，或在调用点直接 `use_hull = False`。
  - 如果圆形邮票四角仍有纸残留，增大 outline_close_bridge_px 或减小
    outline_seed_alpha_thr 或 outline_ignore_border_px。
"""

from copy import deepcopy

#  ============================================================
#  v2 三套预设（建议以此为默认基线）
#  ============================================================
V2_PRESETS = {
    # —— 默认：兼顾淡墨保留与干净度（用户日常首选）
    "default": {
        # Alpha 核心阈值
        "ink_low":                          2.5,
        "ink_high":                         12.0,
        "alpha_strength":                   1.10,

        # 纸张估计
        "paper_percentile_lo":              65.0,
        "paper_percentile_hi":              97.0,
        "paper_max_chroma":                 10.0,
        "local_bg_sigma_ratio":             0.05,
        "local_bg_enabled":                 True,
        "local_bg_gain":                    0.70,

        # 外围清零 A：聊天背景（纯白）
        "drop_outer_stamp_region":          True,
        "chat_bg_L_min":                    96.0,
        "chat_bg_chroma_max":               4.0,
        "stamp_region_close_px":            3,
        "stamp_region_border_px":           4,

        # 外围清零 B：墨水分布 → 外轮廓凸包
        "drop_outside_stamp_outline":       True,
        "outline_close_bridge_px":          32,       # 环形缺口桥接半径
        "outline_outer_border_px":          10,       # 多边形外扩安全边（齿孔）
        "outline_seed_alpha_thr":           60,       # 种子最小墨水 Alpha
        "outline_ignore_border_px":         0,        # 0=自适应：close_bridge + 8

        # ===== v2 新增 =====
        # 近纯黑 artifact（letterbox / 黑边）硬清零
        # 原则：纸上真实墨水绝不可能 RGB 三通道全 ≤15。阈值调大可多删，
        # 调小可防止误伤某些深黑色铜版画/铅笔画式的邮票。
        "artifact_pure_black_drop":         True,
        "artifact_pure_black_max_rgb":      15,

        # 噪声抑制（默认几乎关）
        "noise_min_area":                   0,
        "median_filter_kernel":             0,
        "local_contrast_strength":          0.30,
    },

    # —— 保守：更干净，会删一点淡墨（适合印刷特别精良/墨迹很浓的场景）
    "conservative": {
        **{  # 先抄 default 全量，再覆盖差异
        },
        "ink_low":                          3.5,
        "ink_high":                         14.0,
        "alpha_strength":                   1.0,
        "noise_min_area":                   2,
        "local_contrast_strength":          0.15,
        "artifact_pure_black_drop":         True,
        "artifact_pure_black_max_rgb":      15,
    },

    # —— 保淡墨：宁可多留一点纸噪，也不删淡印/淡墨（用户最推荐的质量模式）
    "preserve_light": {
        "ink_low":                          1.5,
        "ink_high":                         9.0,
        "alpha_strength":                   1.2,
        "drop_outer_stamp_region":          True,
        "chat_bg_L_min":                    96.0,
        "chat_bg_chroma_max":               4.0,
        "drop_outside_stamp_outline":       True,
        "outline_close_bridge_px":          32,
        "outline_outer_border_px":          10,
        "outline_seed_alpha_thr":           60,
        "outline_ignore_border_px":         0,
        "artifact_pure_black_drop":         True,
        "artifact_pure_black_max_rgb":      15,
        "noise_min_area":                   0,
        "median_filter_kernel":             0,
        "local_contrast_strength":          0.40,
    },
}


#  ============================================================
#  v2 处理流程（严格按顺序，任何一步都不可调换 InkScore→Alpha 顺序）
#  ============================================================
V2_PIPELINE_STEPS = [
    "0. locate_stamp_subregion_bbox(rgb_uint8)  →  sub_bbox（去掉大片聊天白背景）",
    "1. working_rgb = rgb_uint8[y0:y1, x0:x2]   (crop to subregion)",
    "2. lab_orig  = rgb_uint8_to_lab_float(working_rgb)   # L∈[0,100], a,b∈[-128,127]",
    "3. lab_norm  = apply_local_luminance_correction(lab_orig, cfg)  # 仅 L 通道，补偿光照不均",
    "4. paper     = estimate_paper_from_lab_float(lab_norm, cfg)     # 与像素在同一归一化空间！",
    "5. fused     = fused_ink_score(lab_norm, paper, cfg)            # ΔE 距离 × 色饱和度 boost × 暗色 boost × 局部对比度 boost",
    "6. alpha     = score_to_alpha(fused['score'], cfg)              # smoothstep(ink_low, ink_high) → alpha_strength 次幂，[0,255]",
    "6. very_light_denoise(alpha, cfg)                                # 极小连通域剔除+可选中值滤波（默认几乎关）",
    "6a. ★ artifact_pure_black_drop:  R≤15 AND G≤15 AND B≤15  → alpha=0   # 纯黑 letterbox/黑边清掉",
    "6b1. region_mask_wk  = compute_stamp_paper_region_mask(lab_full, cfg)   # A. 聊天背景白外区",
    "6b2. outline_mask    = compute_stamp_outer_shape_mask_from_alpha(alpha, ignore_border=auto, close=32, seed_thr=60)",
    "         └─ 最大 contour → convexHull（默认），hull/contour 面积比 >1.20 回退原 contour",
    "6b3. final_keep = region_mask_wk & outline_mask   (AND，若某侧 skipped 则忽略)",
    "6b4. alpha = where(final_keep, alpha, 0)          # 仅删外部，不填实内部空白",
    "7. auto_crop  （按 Alpha>12 的 bbox，外扩 auto_crop_border=2）→ 裁掉四周大片纯透明带",
    "8. RGBA 输出：rgb 原样拷贝，alpha 直接写入（RGB 绝不作任何修复/增强）— 遵守原则 6",
    "9. 调试输出（debug dir）：00_original / 01_lab_L / 02_paper_samples / 03_distance / 03b_ink_score",
    "                          04_alpha / 05_final.png(棋盘格合成) / 05b_checker_RGBA.png / 06_outer_region_mask / stats.json",
]


#  ============================================================
#  v2 → img1~3 实测关键指标（default preset，作为回归对比基准）
#  ============================================================
V2_IMG123_BENCHMARK_default = {
    # MsgID=4205134340272875963  深色圆形邮票（淡墨为主，大量内部空白）
    "img875963": {
        "shape_out":                [1006, 1006],     # 从 1202² 缩（letterbox+外围透明被裁）
        "opaque_pct":               10.83,
        "nontransparent_pct":       47.85,
        "mean_alpha":               36.83,
        "pure_black_px":            482_644,          # 1202² 的 33.4%（正好 80px 黑边面积）
        "outline_region_ratio":     0.7199,            # ≈ π/4，圆形邮票的完美值（π/4≈0.7854 - 少量外扩）
        "use_convex_hull":          True,
        "hull_area/raw_contour":    1.027,             # 几乎圆形，凸包几乎未放
    },
    # MsgID=5824586483576075266  红色圆形邮票（浓墨为主）
    "img075266": {
        "shape_out":                [1006, 1006],
        "opaque_pct":               47.92,
        "nontransparent_pct":       80.76,
        "mean_alpha":               144.2,
        "pure_black_px":            "≈ 同 img875963",
        "outline_region_ratio":     "≈ 0.72（圆形）",
    },
    # MsgID=9190721770453415767  青绿色横向邮票（部分黑边在左）
    "img415767": {
        "shape_out":                [904, 1006],      # 从 904x1058（右侧裁 52 透明带）
        "opaque_pct":               59.17,
        "nontransparent_pct":       84.24,
        "mean_alpha":               176.2,
        "edge_left_0-3_A_mean":     2.2,               # 纯黑左边已清零
        "edge_left_0-3_A==0_pct":   87.5,
    },
}


#  ============================================================
#  回滚 / 超控建议
#  ============================================================
ROLLBACK_TIPS = {
    # 典型故障 → 操作
    "真实深黑色印章被误删（比如整版墨蓝/纯黑墨迹的邮票四周缺边）":
        "CLI 加 `--no-drop-pure-black` 或 `--pure-black-rgb 5`（阈值变小更保守）",

    "四角仍残留方形工作图白纸（圆形邮票外侧没清零）":
        "把 `--outline-close` 从 32 调到 40~48，或 `--outline-seed-thr` 从 60 降到 45",

    "反把邮票最外圈齿孔/齿牙误切（alpha 边缘整圈锯齿变少）":
        "把 `--outline-border` 从 10 调到 16~24",

    "非凸/异形邮票（如蝴蝶形/心形）被凸包放大过多，边缘大片纸透明不掉":
        "修改 utils.compute_stamp_outer_shape_mask_from_alpha 的阈值 1.20 → 0（永远不用凸包），或 CLI 暂时把 --outline-close 减小",

    "subregion 裁切边附近有少量杂点，closing 把 outline 撑到整图":
        "增大 `--outline-ignore-border` 到 60~80（默认自适应 close+8，仅对 32 半径给了 40）",
}


def apply_preset(name: str, cfg):
    """把 V2_PRESETS[name] 中的 k-v 写回 ExtractorConfig 实例。"""
    p = V2_PRESETS.get(name)
    if p is None:
        raise KeyError(f"unknown v2 preset: {name}，可选 {list(V2_PRESETS)}")
    for k, v in p.items():
        if not hasattr(cfg, k):
            continue  # 兼容未来新增字段缺失
        setattr(cfg, k, v)
    return cfg


if __name__ == "__main__":
    # Quick self-print
    import json
    for name, preset in V2_PRESETS.items():
        print(f"\n===== V2_PRESET: {name} =====")
        for k, v in preset.items():
            print(f"  {k:35s} = {v}")
    print("\nPipeline (strict order):")
    for s in V2_PIPELINE_STEPS:
        print("  -", s)
    print("\nBenchmark (default preset on img1~3):")
    for k, v in V2_IMG123_BENCHMARK_default.items():
        print(f"  {k}:", json.dumps(v, ensure_ascii=False))
