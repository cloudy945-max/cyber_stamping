"""印章分割最终版：R-G 墨水分层 alpha + 颜色校正。

算法流程：
1. 确定处理区域（bbox 或全图）
2. R-G 通道分层决策（仅保留墨水，非墨水区域透明）：
   - R-G > 15: 强墨水，alpha = 255
   - 8 < R-G <= 15: 中等墨水，alpha = 200
   - 3 < R-G <= 8 且 rembg_alpha > 100: 淡色墨水，alpha = 120
   - R-G <= 3: 非墨水（纸张空白），alpha = 0
3. 形态学清理
4. 颜色校正（HSV H→172 红色，S 增强）
5. 输出 RGBA PNG
"""
import logging
import sys
import types
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

BBox = Tuple[int, int, int, int]


def _stub_pymatting() -> None:
    if "pymatting.alpha.estimate_alpha_cf" in sys.modules:
        return
    stubs = {
        "pymatting": types.ModuleType("pymatting"),
        "pymatting.alpha": types.ModuleType("pymatting.alpha"),
        "pymatting.alpha.estimate_alpha_cf": types.ModuleType("pymatting.alpha.estimate_alpha_cf"),
        "pymatting.foreground": types.ModuleType("pymatting.foreground"),
        "pymatting.foreground.estimate_foreground_ml": types.ModuleType("pymatting.foreground.estimate_foreground_ml"),
        "pymatting.util": types.ModuleType("pymatting.util"),
        "pymatting.util.util": types.ModuleType("pymatting.util.util"),
    }
    for name, mod in stubs.items():
        if "." in name:
            mod.__path__ = []
    stubs["pymatting.alpha.estimate_alpha_cf"].estimate_alpha_cf = lambda *a, **kw: None
    stubs["pymatting.foreground.estimate_foreground_ml"].estimate_foreground_ml = lambda *a, **kw: None
    stubs["pymatting.util.util"].stack_images = lambda *a, **kw: None
    stubs["pymatting"].alpha = stubs["pymatting.alpha"]
    stubs["pymatting"].foreground = stubs["pymatting.foreground"]
    stubs["pymatting"].util = stubs["pymatting.util"]
    stubs["pymatting.alpha"].estimate_alpha_cf = stubs["pymatting.alpha.estimate_alpha_cf"]
    stubs["pymatting.foreground"].estimate_foreground_ml = stubs["pymatting.foreground.estimate_foreground_ml"]
    stubs["pymatting.util"].util = stubs["pymatting.util.util"]
    for name, mod in stubs.items():
        sys.modules.setdefault(name, mod)


def _get_rembg_session():
    try:
        from .background_removal import _get_session as _bg_get_session
        _stub_pymatting()
        return _bg_get_session()
    except Exception as e:
        logger.warning("stamp_segment: rembg session unavailable: %s", e)
        return None


def segment_stamp(
    src_path: Path,
    dst_path: Path,
    bbox: Optional[BBox] = None,
    color: str = "auto",
) -> Optional[Path]:
    try:
        img_bgr = cv2.imread(str(src_path))
        if img_bgr is None:
            logger.warning("stamp_segment: cannot read %s", src_path)
            return None
        H, W = img_bgr.shape[:2]

        # ===== 1. 确定处理区域 =====
        if bbox is not None:
            bx0, by0, bx1, by1 = bbox
            bx0 = max(0, min(bx0, W))
            bx1 = max(0, min(bx1, W))
            by0 = max(0, min(by0, H))
            by1 = max(0, min(by1, H))
            if bx1 - bx0 < 10 or by1 - by0 < 10:
                logger.warning("stamp_segment: bbox too small %s", bbox)
                return None
            roi = img_bgr[by0:by1, bx0:bx1].copy()
            roi_h, roi_w = roi.shape[:2]
        else:
            roi = img_bgr.copy()
            bx0, by0 = 0, 0
            roi_h, roi_w = H, W

        k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # ===== 2. 圆形定位（在 ROI 内找印章圆心）=====
        b_ch, g_ch, r_ch = cv2.split(roi)
        r_minus_g = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(0, 255).astype(np.uint8)

        _, r_binary = cv2.threshold(r_minus_g, 10, 255, cv2.THRESH_BINARY)
        r_dilated = cv2.dilate(r_binary, k3, iterations=3)
        contours, _ = cv2.findContours(r_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        stamp_cx, stamp_cy, stamp_r = None, None, None
        for cnt in contours[:20]:
            area = cv2.contourArea(cnt)
            if area < 50000:
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            aspect = cw / ch if ch > 0 else 0
            if 0.7 < aspect < 1.4:
                stamp_cx = x + cw // 2
                stamp_cy = y + ch // 2
                stamp_r = max(cw, ch) // 2
                break

        if stamp_cx is None:
            stamp_cx, stamp_cy = roi_w // 2, roi_h // 2
            stamp_r = int(min(roi_w, roi_h) * 0.48)

        logger.info("stamp_segment: stamp at (%d,%d) r=%d in ROI %dx%d",
                     stamp_cx, stamp_cy, stamp_r, roi_w, roi_h)

        # ===== 3. rembg 处理（在 ROI 上）=====
        rembg_alpha_roi = np.zeros((roi_h, roi_w), dtype=np.uint8)
        session = _get_rembg_session()
        if session is not None:
            try:
                from rembg import remove
                pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
                result = remove(pil_img, session=session)
                arr = np.array(result)
                if arr.shape[2] == 4:
                    rembg_alpha_roi = arr[:, :, 3]
                else:
                    rembg_alpha_roi = np.full((roi_h, roi_w), 255, dtype=np.uint8)
            except Exception as e:
                logger.warning("stamp_segment: rembg step failed: %s", e)

        # ===== 4. 构建印章区域 mask（智能边界约束）=====
        # 策略：圆形检测 + 大搜索区域 + 低阈值连通域 + 扩张
        rg = r_minus_g.astype(np.int16)

        # 4a. 基于已检测的圆形创建搜索区域 mask，扩大到 1.35 倍半径覆盖外圈边缘
        search_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
        if stamp_cx is not None:
            Y, X = np.mgrid[0:roi_h, 0:roi_w]
            dist = np.sqrt((X - stamp_cx) ** 2 + (Y - stamp_cy) ** 2)
            search_r = int(stamp_r * 1.35)  # 扩大搜索范围，覆盖外圈文字和星星边缘
            search_mask[dist <= search_r] = 255
        else:
            search_mask[:] = 255  # 无圆形检测时全图搜索

        # 4b. 在搜索区域内找最大连通域，用更低阈值 (3) 捕获淡色边缘
        _, ink_binary = cv2.threshold(r_minus_g, 3, 255, cv2.THRESH_BINARY)
        ink_binary = cv2.morphologyEx(ink_binary, cv2.MORPH_CLOSE, k3, iterations=3)
        # 限制在搜索区域内
        ink_binary_in_search = cv2.bitwise_and(ink_binary, search_mask)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            ink_binary_in_search, connectivity=8
        )
        seal_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
        if num_labels > 1:
            areas = stats[1:, cv2.CC_STAT_AREA]
            largest_label = np.argmax(areas) + 1
            seal_mask = (labels == largest_label).astype(np.uint8) * 255
            # 扩张 + 开运算：先扩大覆盖外圈边缘淡色，再用开运算去掉孤立毛刺
            k5d = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            k3o = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            seal_mask = cv2.dilate(seal_mask, k5d, iterations=2)
            seal_mask = cv2.morphologyEx(seal_mask, cv2.MORPH_OPEN, k3o, iterations=1)

        # ===== 5. R-G 分层 alpha（仅保留 seal_mask 内的墨水）=====
        final_alpha_roi = np.zeros((roi_h, roi_w), dtype=np.uint8)

        # 强墨水（R-G > 15）：文字、图案、外圈边框
        strong_ink = (rg > 15) & (seal_mask > 0)
        final_alpha_roi[strong_ink] = 255

        # 中等墨水（8 < R-G <= 15）
        medium_ink = (rg > 8) & (rg <= 15) & (seal_mask > 0)
        final_alpha_roi[medium_ink] = 200

        # 淡色墨水（3 < R-G <= 8）：只在 seal_mask 内，不需要 rembg，
        # 后续靠 RG 扩张连通过滤来剔除孤立毛刺
        light_ink = (rg > 3) & (rg <= 8) & (seal_mask > 0)
        final_alpha_roi[light_ink] = 120

        # ===== 6. 形态学清理 + 孤立淡色墨水过滤 =====
        final_alpha_roi = cv2.morphologyEx(final_alpha_roi, cv2.MORPH_CLOSE, k3, iterations=2)
        final_alpha_roi = cv2.morphologyEx(final_alpha_roi, cv2.MORPH_OPEN, k3, iterations=1)

        # 再次限制在 seal_mask 内
        final_alpha_roi[seal_mask == 0] = 0

        # 6a. 主连通域（alpha>=64，8 连通），先剔除独立毛刺斑块
        _, alpha_bin_main = cv2.threshold(final_alpha_roi, 63, 255, cv2.THRESH_BINARY)
        num_cc_main, cc_main, stats_main, _ = cv2.connectedComponentsWithStats(
            alpha_bin_main, connectivity=8
        )
        if num_cc_main > 1:
            areas_main = stats_main[1:, cv2.CC_STAT_AREA]
            largest_main = np.argmax(areas_main) + 1
            max_area = areas_main[largest_main - 1]
            keep_main = np.zeros_like(cc_main, dtype=bool)
            for lidx in range(1, num_cc_main):
                a = stats_main[lidx, cv2.CC_STAT_AREA]
                if a >= max_area * 0.5:
                    keep_main |= cc_main == lidx
            not_keep = ~keep_main & (final_alpha_roi >= 64)
            final_alpha_roi[not_keep] = 0

        # 6b. 淡色墨水（64 <= alpha < 200）必须在距离强墨水（>=200）30px 以内
        # 外圈淡墨水约 84% 在 20px 内、84.3% 在 30px 内；印章外毛刺 99.9% > 20px
        # 距离阈值取 30px，保留更完整的边缘淡色
        strong_mask = (final_alpha_roi >= 200).astype(np.uint8) * 255
        if strong_mask.sum() > 0:
            # 用距离变换快速计算每个像素到强墨水的距离
            distance_map = cv2.distanceTransform(255 - strong_mask, cv2.DIST_L1, 3)
            light_ink_mask = (final_alpha_roi >= 64) & (final_alpha_roi < 200)
            too_far = light_ink_mask & (distance_map > 30.0)
            final_alpha_roi[too_far] = 0

        # ===== 9. 还原到全图 =====
        full_alpha = np.zeros((H, W), dtype=np.uint8)
        full_alpha[by0:by0 + roi_h, bx0:bx0 + roi_w] = final_alpha_roi

        if bbox is not None:
            bbox_mask = np.zeros((H, W), dtype=np.uint8)
            bbox_mask[by0:by1, bx0:bx1] = 255
            full_alpha = cv2.bitwise_and(full_alpha, bbox_mask)

        # ===== 10. 颜色校正（蓝紫墨水 → 红色墨水）=====
        # 所有墨水像素（alpha >= 64）都做颜色校正，确保颜色一致
        # alpha < 64 强制透明
        output_bgr = img_bgr.copy()

        # 全档：墨水 alpha >= 64 → 做颜色校正
        ink_mask = full_alpha >= 64
        # 透明：alpha < 64 → 完全透明
        transparent_mask = full_alpha < 64

        # 强制透明低 alpha
        full_alpha[transparent_mask] = 0
        output_bgr[transparent_mask] = [0, 0, 0]

        if ink_mask.sum() > 0:
            try:
                full_hsv = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2HSV)
                ink_pix = full_hsv[ink_mask].astype(np.float32)

                # H：统一目标红色 Hue（OpenCV范围 0-179，红色在 160-179）
                h_target = 172.0
                h_new = np.full(ink_pix.shape[0], h_target, dtype=np.float32)

                # S：增强，使红色鲜艳
                s_orig = ink_pix[:, 1]
                s_target_base = 130.0
                s_new = s_target_base + (s_orig - s_orig.mean()) * 1.5
                s_new = np.clip(s_new, 60, 255)

                v_new = ink_pix[:, 2]

                new_pix = np.zeros_like(ink_pix)
                new_pix[:, 0] = h_new
                new_pix[:, 1] = s_new
                new_pix[:, 2] = v_new

                new_pix_u8 = np.clip(new_pix, 0, 255).astype(np.uint8)
                new_bgr = cv2.cvtColor(new_pix_u8.reshape(-1, 1, 3), cv2.COLOR_HSV2BGR).reshape(-1, 3)
                output_bgr[ink_mask] = new_bgr

                # 淡色墨水（alpha 64-199）调淡：降低 alpha 和饱和度
                # 使纸张染色区域视觉上变得极淡，不影响强墨水文字/图案
                light_mask = (full_alpha >= 64) & (full_alpha < 200)
                if light_mask.sum() > 0:
                    # alpha 降低 60
                    full_alpha[light_mask] = np.clip(
                        full_alpha[light_mask].astype(np.int16) - 60, 0, 255
                    ).astype(np.uint8)
                    # 饱和度降为 40%，红色变淡粉
                    light_hsv = full_hsv[light_mask].astype(np.float32)
                    light_hsv[:, 1] = np.clip(light_hsv[:, 1] * 0.4, 0, 255)
                    light_u8 = np.clip(light_hsv, 0, 255).astype(np.uint8)
                    light_bgr = cv2.cvtColor(
                        light_u8.reshape(-1, 1, 3), cv2.COLOR_HSV2BGR
                    ).reshape(-1, 3)
                    output_bgr[light_mask] = light_bgr
            except Exception as ce:
                logger.warning("stamp_segment: color correction step skipped: %s", ce)
                output_bgr = img_bgr

        # ===== 11. 有效性检查 =====
        fg_pixels = int((full_alpha > 10).sum())
        if fg_pixels == 0:
            logger.info("stamp_segment: empty foreground")
            return None

        fg_ratio = fg_pixels / (H * W) * 100
        if fg_ratio > 85:
            logger.warning("stamp_segment: foreground too large (%.1f%%)", fg_ratio)
            return None

        # ===== 12. 裁剪到印章实际边界 =====
        # 找到非透明像素的 bounding box，去掉大量透明边距
        fg_coords = cv2.findNonZero((full_alpha > 10).astype(np.uint8))
        if fg_coords is not None:
            x, y, w, h = cv2.boundingRect(fg_coords)
            pad_x = int(w * 0.10)
            pad_y = int(h * 0.10)
            x0 = max(0, x - pad_x)
            y0 = max(0, y - pad_y)
            x1 = min(W, x + w + pad_x)
            y1 = min(H, y + h + pad_y)
            full_alpha = full_alpha[y0:y1, x0:x1]
            output_bgr = output_bgr[y0:y1, x0:x1]
            H, W = full_alpha.shape[:2]

        # ===== 13. 输出 RGBA PNG =====
        output_rgb = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2RGB)
        rgba = np.dstack([output_rgb, full_alpha])
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba, "RGBA").save(dst_path, "PNG")
        strong = int((full_alpha > 200).sum()) / (H * W) * 100
        logger.info(
            "stamp_segment ok: %s -> %s (fg>10=%.1f%%, fg>200=%.1f%%, bbox=%s)",
            src_path.name, dst_path.name, fg_ratio, strong, bbox,
        )
        return dst_path
    except Exception as e:
        logger.warning("stamp_segment failed for %s: %s", src_path, e)
        import traceback
        traceback.print_exc()
        return None
