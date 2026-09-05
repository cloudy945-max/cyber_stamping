"""
stamp_extractor.processor
=========================
主处理流程（原则 9 推荐架构）：
    Input → Load → Lab → 纸色建模 → 局部亮度校正 → InkScore融合 → Alpha → 轻去噪 → Crop → RGBA/调试输出
所有 debug 图和结果都在这里统一写出。
"""
from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from .config import ExtractorConfig
from .utils import (
    load_rgb_uint8,
    save_png_rgba,
    save_grayscale,
    save_debug_rgb,
    alpha_bbox,
    crop_bbox,
    rgb_uint8_to_lab_float,
    lab_float_to_rgb_uint8,
    locate_stamp_subregion_bbox,
    compute_stamp_paper_region_mask,
    compute_stamp_outer_shape_mask_from_alpha,
)
from .background import (
    PaperModel,
    estimate_paper_from_lab_float,
    apply_local_luminance_correction,
)
from .color_analysis import fused_ink_score
from .alpha_mask import score_to_alpha, very_light_denoise


@dataclass
class ExtractResult:
    rgba: np.ndarray              # (H,W,4) uint8 最终透明印章（可能已 auto_crop）
    alpha: np.ndarray             # (H,W) uint8 最终 Alpha（与 rgba 等大，即已裁剪）
    alpha_fullres: np.ndarray     # 未裁剪的原始分辨率 Alpha（用于外部进一步处理）
    bbox: Optional[tuple]
    paper: PaperModel
    stats: Dict[str, Any]
    debug_dir: Optional[Path] = None


class StampExtractor:
    """高保真墨迹 Alpha 提取器。RGB 保持原始值。"""

    def __init__(self, cfg: Optional[ExtractorConfig] = None):
        self.cfg = cfg or ExtractorConfig.defaults()

    # --------- 单图主入口 ---------
    def extract_file(
        self,
        input_path: Path,
        output_png: Path,
        debug_dir: Optional[Path] = None,
    ) -> ExtractResult:
        rgb0 = load_rgb_uint8(Path(input_path))
        return self.extract_array(
            rgb0,
            output_png=output_png,
            debug_dir=debug_dir,
            source_name=Path(input_path).name,
        )

    def extract_array(
        self,
        rgb_uint8: np.ndarray,
        output_png: Optional[Path],
        debug_dir: Optional[Path] = None,
        source_name: str = "source",
    ) -> ExtractResult:
        cfg = self.cfg
        assert rgb_uint8.dtype == np.uint8 and rgb_uint8.ndim == 3 and rgb_uint8.shape[2] == 3

        # ============================================================
        # 0-. 邮票外围区域强制清零：FULL-RES 原图先做一次
        #
        # 关键：region mask 必须基于整张聊天截图做（边框像素包含纯白聊天背景），
        # 如果先 subregion 再做，四周白边已经被裁掉，检测会失效（漏删齿孔外杂边）。
        # ============================================================
        region_mask_full: Optional[np.ndarray]
        outer_region_meta: Dict[str, Any]
        if cfg.drop_outer_stamp_region:
            lab_full = rgb_uint8_to_lab_float(rgb_uint8)
            region_mask_full, outer_region_meta = compute_stamp_paper_region_mask(lab_full, cfg)
            del lab_full
        else:
            region_mask_full = None
            outer_region_meta = {"skipped": True, "reason": "disabled"}

        # ============================================================
        # 0. 定位印章子区域（应对：截图/聊天框/非章背景）
        #    若无明显非章区域则 sub_bbox=None，使用全图。
        # ============================================================
        sub_bbox = locate_stamp_subregion_bbox(rgb_uint8)
        if sub_bbox is not None:
            x0, y0, x1, y1 = sub_bbox
            working_rgb = rgb_uint8[y0:y1, x0:x1]
            # 同步裁剪 region mask
            if region_mask_full is not None:
                region_mask_wk = region_mask_full[y0:y1, x0:x1]
            else:
                region_mask_wk = None
        else:
            working_rgb = rgb_uint8
            region_mask_wk = region_mask_full
        H, W, _ = working_rgb.shape

        # ============================================================
        # 1. RGB → Lab  float32（真正的感知 Lab：L∈[0,100], a,b∈[-128,127]）
        # ============================================================
        lab_orig = rgb_uint8_to_lab_float(working_rgb)

        # ============================================================
        # 2. 局部亮度归一化（仅 L 通道，光照不均补偿）
        #    纸色估计必须在「相同空间」进行，不能拿未经归一化的纸色对比归一化后的像素。
        # ============================================================
        lab_norm, local_L_map = apply_local_luminance_correction(lab_orig, cfg)

        # ============================================================
        # 3. 全局纸张建模（从归一化后的 Lab 估计，保证一致空间）
        # ============================================================
        paper = estimate_paper_from_lab_float(lab_norm, cfg)

        # ============================================================
        # 4. 融合 InkScore
        # ============================================================
        fused = fused_ink_score(lab_norm, paper, cfg)
        score = fused["score"]
        distance_map = fused["distance_map"]

        # 预计算 chroma map（Lab 空间饱和度），供 outline 种子过滤使用
        chroma_map = np.sqrt(lab_norm[:, :, 1] ** 2 + lab_norm[:, :, 2] ** 2).astype(np.float32)

        # ============================================================
        # 5. 连续 Alpha 映射（非二值）
        # ============================================================
        alpha_fullres = score_to_alpha(score, cfg)

        # ============================================================
        # 6. 极轻去噪（默认几乎关闭）
        # ============================================================
        alpha_fullres = very_light_denoise(alpha_fullres, cfg)

        # ============================================================
        # 6a. 近纯黑 letterbox / 黑边 artifact 硬清零
        #     —— 典型 jfif 聊天截图：方形裁切图最外圈一大圈纯黑 RGB(0,0,0)，
        #        InkScore 把它当最浓墨水给 alpha=255。真实纸质印章/邮票墨水绝
        #        不可能是"所有通道都<15"的死黑。直接清零。
        # ============================================================
        artifact_meta: Dict[str, Any] = {"enabled": False}
        if cfg.artifact_pure_black_drop and cfg.artifact_pure_black_max_rgb >= 0:
            artifact_meta["enabled"] = True
            # near-pure-black: R <= thr AND G <= thr AND B <= thr
            thr = int(cfg.artifact_pure_black_max_rgb)
            m_r = working_rgb[..., 0] <= thr
            m_g = working_rgb[..., 1] <= thr
            m_b = working_rgb[..., 2] <= thr
            mask_pb = (m_r & m_g & m_b)
            n_pb = int(mask_pb.sum())
            artifact_meta["n_pure_black_px"] = n_pb
            artifact_meta["pure_black_ratio"] = float(n_pb / max(1, alpha_fullres.size))
            if n_pb > 0:
                alpha_fullres = np.where(mask_pb, np.uint8(0), alpha_fullres)

        # ============================================================
        # 6b. 两种「外围区域强制清零」策略：
        #
        #   方案 A（region_mask_wk）：从全图原始 Lab 出发，定位「非聊天背景最大连通域」= 邮票纸
        #        本体。适合删除四周大片聊天白背景 / 截图杂边。
        #   方案 B（outline_mask）：  从已经算好的 Alpha 墨水分布出发，闭合外轮廓并填充，得到
        #        「邮票的外形多边形」。适合删除：方形工作图的 4 个角纸（圆形邮票在方形里）。
        #
        # 最终：取两张 mask 的交集（AND），交集外 alpha 强制清零。
        #
        # 原则保证：所有形态学操作/填洞都只作用于 region/outline 临时 mask，
        #           永远不把 mask 内的像素"强制变成不透明"。内部空白透明化仍由 InkScore 独立进行。
        # ============================================================
        outline_mask: Optional[np.ndarray] = None
        outline_meta: Dict[str, Any] = {"skipped": True, "reason": "disabled"}
        if cfg.drop_outside_stamp_outline:
            # 自适应：如果 outline_ignore_border_px=0，并且工作图是 subregion 裁出来的，
            # 自动忽略"裁切边附近 close 半径"的种子，防 closing 撑满整图。
            if cfg.outline_ignore_border_px == 0:
                auto_border = cfg.outline_close_bridge_px + 8
            else:
                auto_border = cfg.outline_ignore_border_px
            outline_mask, outline_meta = compute_stamp_outer_shape_mask_from_alpha(
                alpha_fullres,
                close_bridge_px=cfg.outline_close_bridge_px,
                outer_border_px=cfg.outline_outer_border_px,
                seed_alpha_thr=cfg.outline_seed_alpha_thr,
                ignore_border_px=auto_border,
                chroma_map=chroma_map,
                seed_chroma_min=cfg.outline_seed_chroma_min,
            )

        applied_any_drop = False
        final_keep_mask: Optional[np.ndarray] = None
        # 组装：先 AND 所有启用的 keep-mask
        keep_masks = []
        if region_mask_wk is not None and not outer_region_meta.get("skipped", False):
            keep_masks.append(region_mask_wk)
        if outline_mask is not None and not outline_meta.get("skipped", False):
            keep_masks.append(outline_mask)
        if keep_masks:
            final_keep_mask = keep_masks[0]
            for m in keep_masks[1:]:
                final_keep_mask = final_keep_mask & m
            alpha_fullres = np.where(final_keep_mask, alpha_fullres, np.uint8(0))
            applied_any_drop = True
        # 合并统计
        outer_region_meta["outline"] = outline_meta
        outer_region_meta["applied_drop"] = applied_any_drop
        if final_keep_mask is not None:
            outer_region_meta["keep_ratio_after_drop"] = float(final_keep_mask.mean())
        outer_region_meta["pure_black_artifact"] = artifact_meta
        # 传递给 debug（画合成 keep mask 的外轮廓）
        debug_region_mask: Optional[np.ndarray] = final_keep_mask if applied_any_drop else (
            region_mask_wk if (region_mask_wk is not None and not outer_region_meta.get("skipped", False)) else (
                outline_mask if (outline_mask is not None and not outline_meta.get("skipped", False)) else None
            )
        )

        # ============================================================
        # 7. BBox 裁剪（按真实墨迹，不是按纸边或邮票边）
        # ============================================================
        bbox = None
        if cfg.auto_crop:
            bbox = alpha_bbox(
                alpha_fullres,
                threshold=cfg.auto_crop_alpha_threshold,
                border=cfg.auto_crop_border,
            )

        rgb_out = working_rgb
        alpha_out = alpha_fullres
        if bbox is not None:
            rgb_out = crop_bbox(working_rgb, bbox)
            alpha_out = crop_bbox(alpha_fullres, bbox)

        # ============================================================
        # 8. 构建 RGBA：RGB 原样保留，只替换 Alpha（原则 1、8）
        # ============================================================
        # 可选的实验模式：去除纸张染色（默认关闭）
        if cfg.desaturate_paper_tint:
            # 原理：在 Lab 中，把「与纸色 a,b 接近且 Alpha 低」的像素的 a,b 向纸色轻微拉回
            # 仅影响接近纸张但仍残留透明的像素，不动强墨迹。用户显式开启才执行。
            rgba_rgb = self._soft_desaturate_paper_tint(rgb_out, alpha_out, paper)
        else:
            rgba_rgb = rgb_out

        rgba = np.dstack([rgba_rgb, alpha_out]).astype(np.uint8)

        # ============================================================
        # 9. 保存输出
        # ============================================================
        if output_png is not None:
            output_png = Path(output_png)
            save_png_rgba(output_png, rgba)

        # ============================================================
        # 10. Debug 图（原则 17）
        # ============================================================
        if cfg.save_debug_images and debug_dir is not None:
            debug_dir = Path(debug_dir)
            self._save_debug(
                debug_dir,
                source_name=source_name,
                original=working_rgb,
                paper=paper,
                local_L_map=local_L_map,
                distance_map=distance_map,
                score=score,
                alpha_fullres=alpha_fullres,
                alpha_out=alpha_out,
                rgba=rgba,
                bbox=bbox,
                region_mask=debug_region_mask,
            )

        stats = dict(
            shape=[int(rgba.shape[1]), int(rgba.shape[0])],
            sub_bbox_in_original=list(sub_bbox) if sub_bbox is not None else None,
            n_paper_samples=int(paper.n_samples),
            paper_lab_mean=[float(x) for x in paper.lab_mean.tolist()],
            mean_alpha=float(alpha_out.mean()),
            nontransparent_pct=float((alpha_out > 0).mean() * 100.0),
            opaque_pct=float((alpha_out >= 220).mean() * 100.0),
            outer_region=outer_region_meta,
        )

        return ExtractResult(
            rgba=rgba,
            alpha=alpha_out,
            alpha_fullres=alpha_fullres,
            bbox=bbox,
            paper=paper,
            stats=stats,
            debug_dir=debug_dir,
        )

    # --------- 子工具 ---------
    @staticmethod
    def _soft_desaturate_paper_tint(
        rgb_out: np.ndarray,
        alpha_out: np.ndarray,
        paper: PaperModel,
    ) -> np.ndarray:
        """可选实验模式。Alpha 越低 → 越按纸色 a,b 漂白 RGB（轻微）。"""
        lab_small = rgb_uint8_to_lab_float(rgb_out)
        # 计算每个像素 RGB 中的 "纸染色残留"：低 alpha 的像素更可能带纸色染色
        t = 1.0 - (alpha_out.astype(np.float32) / 255.0)  # 0..1，越高越接近纸
        t = t * t  # 更保守，主要动透明边缘
        # 只在 a,b 上向纸色靠拢
        mix_a = lab_small[:, :, 1] * (1 - t) + paper.lab_mean[1] * t
        mix_b = lab_small[:, :, 2] * (1 - t) + paper.lab_mean[2] * t
        lab_small[:, :, 1] = mix_a
        lab_small[:, :, 2] = mix_b
        return lab_float_to_rgb_uint8(lab_small)

    @staticmethod
    def _save_debug(
        debug_dir: Path,
        source_name: str,
        original: np.ndarray,
        paper: PaperModel,
        local_L_map: np.ndarray,
        distance_map: np.ndarray,
        score: np.ndarray,
        alpha_fullres: np.ndarray,
        alpha_out: np.ndarray,
        rgba: np.ndarray,
        bbox: Optional[tuple],
        region_mask: Optional[np.ndarray] = None,
    ) -> None:
        # 文件名使用稳定前缀
        def p(tag: str, ext: str = "png") -> Path:
            base = Path(source_name).stem
            return debug_dir / f"{base}_{tag}.{ext}"

        save_debug_rgb(p("01_original", "jpg"), original)

        # 02: 纸张采样可视化：在原图上高亮选中的纸像素
        overlay = original.copy()
        if paper.mask.dtype != bool:
            mask = paper.mask.astype(bool)
        else:
            mask = paper.mask
        overlay[mask] = np.clip(overlay[mask].astype(np.int16) + np.array([40, 0, 0], dtype=np.int16), 0, 255).astype(np.uint8)
        # 如果计算了 bbox，也叠一个 bbox 框到 debug 图
        if bbox is not None:
            x0, y0, x1, y1 = bbox
            cv2.rectangle(overlay, (x0, y0), (x1 - 1, y1 - 1), (0, 180, 0), 2)
        # 再叠纸色说明：左上角一个小方块显示估计的纸色
        lab_block = np.zeros((1, 1, 3), dtype=np.float32)
        lab_block[0, 0, :] = paper.lab_mean  # float Lab (L∈[0,100], a,b∈[-128,127])
        paper_rgb = lab_float_to_rgb_uint8(lab_block)[0, 0].tolist()
        cv2.rectangle(overlay, (10, 10), (70, 70), tuple(int(x) for x in paper_rgb), -1)
        cv2.putText(overlay, f"N={paper.n_samples}", (16, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        save_debug_rgb(p("02_background_estimation", "jpg"), overlay)

        # 局部亮度估计（作为背景估计的一部分附到 02b）
        local_L_norm = (local_L_map - local_L_map.min()) / max(1e-6, local_L_map.max() - local_L_map.min())
        save_grayscale(p("02b_local_luminance"), local_L_norm.astype(np.float32))

        # 03: 颜色距离图（归一化后再乘，便于观察淡墨区）
        dmax = float(np.percentile(distance_map, 99.0))
        dist_show = np.clip(distance_map / max(dmax, 1e-3), 0.0, 1.0)
        save_grayscale(p("03_color_distance"), dist_show.astype(np.float32))

        # 03b: 融合后的 InkScore（显示实际喂给 Alpha 的最终量）
        smax = float(np.percentile(score, 99.0))
        score_show = np.clip(score / max(smax, 1e-3), 0.0, 1.0)
        save_grayscale(p("03b_ink_score"), score_show.astype(np.float32))

        # 04: 最终 Alpha（灰度） — 两种：原始整图 & 裁剪后
        save_grayscale(p("04_alpha_mask_full"), alpha_fullres)
        save_grayscale(p("04_alpha_mask_cropped"), alpha_out)

        # 05: 最终 RGBA（转成棋盘格预览更好观察）
        save_png_rgba(p("05_final"), rgba)
        # 附：05b 棋盘格预览版（方便肉眼看透明）
        preview = _render_checker_preview(rgba, cell=12)
        save_debug_rgb(p("05b_preview_checker", "jpg"), preview)

        # 06: 外围邮票纸区域识别（把 region 轮廓叠加到原图）
        #     便于检查外围清零有没有误删掉邮票齿孔最外的齿牙
        if region_mask is not None:
            m = region_mask.astype(np.uint8) * 255
            contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            reg_overlay = original.copy()
            # region外 → 暗化（视觉上像删掉的预览）
            not_reg = ~region_mask
            reg_overlay[not_reg] = (reg_overlay[not_reg].astype(np.float32) * 0.20).astype(np.uint8)
            cv2.drawContours(reg_overlay, contours, -1, (0, 255, 255), 2)
            save_debug_rgb(p("06_outer_region_mask", "jpg"), reg_overlay)


def _render_checker_preview(rgba: np.ndarray, cell: int = 12) -> np.ndarray:
    """把 RGBA 叠在经典灰/白棋盘格上，方便检查透明。"""
    H, W, _ = rgba.shape
    y, x = np.mgrid[:H, :W]
    checker = (((y // cell) + (x // cell)) % 2 == 0).astype(np.uint8) * 30 + 215  # 215/245
    bg = np.dstack([checker, checker, checker])
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    out = rgb * a + bg.astype(np.float32) * (1 - a)
    return np.clip(out, 0, 255).astype(np.uint8)
