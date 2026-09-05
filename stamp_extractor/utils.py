"""
stamp_extractor.utils
=====================
IO / 通用小工具。支持 .heic（通过 pillow_heif，若未装则给出清晰报错）。
原则：输入/输出尽量保留原始分辨率，不做缩放。
"""
from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple

from .config import ExtractorConfig
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    _HEIC_OK = True
except Exception:  # pragma: no cover
    _HEIC_OK = False


HEIC_EXTS = {".heic"}
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".jfif", ".heic"}


def require_heic_ok(path: Path) -> None:
    if path.suffix.lower() in HEIC_EXTS and not _HEIC_OK:
        raise RuntimeError(
            f"需要读取 HEIC 文件但未安装 pillow_heif。请执行：pip install pillow-heif  "
            f"(当前文件: {path.name})"
        )


def load_rgb_uint8(path: Path) -> np.ndarray:
    """读取任何支持的图片，返回 (H, W, 3) uint8 RGB。"""
    path = Path(path)
    require_heic_ok(path)
    with Image.open(path) as im:
        if im.mode not in ("RGB", "RGBA", "L"):
            im = im.convert("RGB")
        rgb = np.array(im.convert("RGB"), dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"输入图像格式异常: {path.name} shape={rgb.shape}")
    return rgb


def rgb_uint8_to_lab_float(rgb_uint8: np.ndarray) -> np.ndarray:
    """
    OpenCV COLOR_RGB2LAB(uint8) → 真正感知的 Lab float32:
        L ∈ [0, 100]
        a ∈ [-128, 127]  (绿↔红)
        b ∈ [-128, 127]  (蓝↔黄)
    后面全链路的「纸色建模 / 颜色距离 / chroma / 亮度校正」都基于这个编码。
    """
    lab_u8 = cv2.cvtColor(rgb_uint8, cv2.COLOR_RGB2LAB)
    lab = lab_u8.astype(np.float32)
    L = lab[:, :, 0] * (100.0 / 255.0)
    a = lab[:, :, 1] - 128.0
    b = lab[:, :, 2] - 128.0
    return np.dstack([L, a, b])


def lab_float_to_rgb_uint8(lab_f32: np.ndarray) -> np.ndarray:
    """反变换（调试/重着色用，默认流程不会用到）。"""
    L = np.clip(lab_f32[:, :, 0] * (255.0 / 100.0), 0, 255)
    a = np.clip(lab_f32[:, :, 1] + 128.0, 0, 255)
    b = np.clip(lab_f32[:, :, 2] + 128.0, 0, 255)
    lab_u8 = np.dstack([L, a, b]).astype(np.uint8)
    return cv2.cvtColor(lab_u8, cv2.COLOR_LAB2RGB)


def save_png_rgba(path: Path, rgba: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", optimize=False)


def save_grayscale(path: Path, gray01: np.ndarray) -> None:
    """保存 0..1 float 或 0..255 uint8 为灰度 PNG/JPG。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if gray01.dtype != np.uint8:
        g = np.clip(gray01, 0.0, 1.0)
        g = (g * 255.0 + 0.5).astype(np.uint8)
    else:
        g = gray01
    Image.fromarray(g, mode="L").save(path)


def save_debug_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0.0, 1.0)
        rgb = (rgb * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(rgb, mode="RGB").save(path)


def list_images(folder: Path, recursive: bool = True) -> list[Path]:
    it = folder.rglob("*") if recursive else folder.iterdir()
    out = []
    for p in sorted(it):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            out.append(p)
    return out


def alpha_bbox(
    alpha: np.ndarray, threshold: int = 8, border: int = 2
) -> Optional[Tuple[int, int, int, int]]:
    """返回 (x0, y0, x1, y1) 的真实墨迹 bbox；全透明返回 None。"""
    mask = alpha >= threshold
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    h, w = alpha.shape
    x0 = max(0, int(xs.min()) - border)
    y0 = max(0, int(ys.min()) - border)
    x1 = min(w, int(xs.max()) + 1 + border)
    y1 = min(h, int(ys.max()) + 1 + border)
    return x0, y0, x1, y1


def crop_bbox(img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    if img.ndim == 2:
        return img[y0:y1, x0:x1]
    return img[y0:y1, x0:x1, :]


def short_stem(p: Path) -> str:
    """MsgID / 长文件名安全截断。"""
    s = p.stem
    if "MsgID=" in s:
        # 微信 _cgi 文件：MsgID=xxxxx& 之间的数字
        start = s.find("MsgID=") + 6
        end = s.find("&", start)
        if end == -1:
            end = len(s)
        return "img" + s[start:end][-6:]
    # heic 转出来的 8181
    if s.upper().endswith("8181") or s.endswith("8181"):
        return "8181"
    return s[:80]


def locate_stamp_subregion_bbox(
    rgb_uint8: np.ndarray,
    min_rel_area: float = 0.004,
    pad_rel: float = 0.10,
    color_diff_thr: int = 10,
    paper_L_thr_pct: float = 65.0,
) -> Optional[Tuple[int, int, int, int]]:
    """
    从整张图里定位「章+纸」的大致子区域（纯 OpenCV 传统启发，无 AI）。
    适用场景：输入是带 UI / 聊天截图 / 深色网页包裹的邮票截图，整张图大部分像素不属纸张。
    思路：
        a) 高饱和像素（墨迹/彩色物体）：max(RGB)-min(RGB) ≥ color_diff_thr → 彩色
        b) 亮度足够高的像素（纸）：max(RGB) >= 某阈值（与纸百分位挂钩）
        c) 对彩色像素做连通域分析，取所有「面积足够大 + 宽高比 0.2~5.0」的连通域并集作为印章候选
        d) 外扩 10%（或至少 40px）作为包含周围纸边的 bbox，返回 (x0,y0,x1,y1)
    如果图本身已经是章+纸（没有无关像素），返回 None（不裁剪）。
    """
    H, W, _ = rgb_uint8.shape
    rgb = rgb_uint8.astype(np.int16)
    R = rgb[:, :, 0]; G = rgb[:, :, 1]; B = rgb[:, :, 2]
    max_c = np.maximum(np.maximum(R, G), B)
    min_c = np.minimum(np.minimum(R, G), B)
    color_diff = (max_c - min_c).astype(np.uint8)
    # 彩色像素（印章墨迹一定是彩色的）
    color_mask = color_diff >= color_diff_thr

    num, labels, stats, _ = cv2.connectedComponentsWithStats(
        color_mask.astype(np.uint8) * 255, connectivity=8
    )
    min_abs = int(max(H, W) ** 2 * min_rel_area)
    all_x0, all_y0 = W, H
    all_x1, all_y1 = 0, 0
    hit = False
    if num > 1:
        for i in range(1, num):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < max(500, min_abs // 4):
                continue
            x = int(stats[i, cv2.CC_STAT_LEFT])
            y = int(stats[i, cv2.CC_STAT_TOP])
            w = int(stats[i, cv2.CC_STAT_WIDTH])
            h = int(stats[i, cv2.CC_STAT_HEIGHT])
            if w == 0 or h == 0:
                continue
            aspect = w / h
            if not (0.2 <= aspect <= 5.0):
                continue
            hit = True
            all_x0 = min(all_x0, x)
            all_y0 = min(all_y0, y)
            all_x1 = max(all_x1, x + w)
            all_y1 = max(all_y1, y + h)
    if not hit:
        return None

    bw, bh = all_x1 - all_x0, all_y1 - all_y0
    pad = int(max(bw, bh) * pad_rel)
    pad = max(pad, 40)
    x0 = max(0, all_x0 - pad)
    y0 = max(0, all_y0 - pad)
    x1 = min(W, all_x1 + pad)
    y1 = min(H, all_y1 + pad)

    # 如果候选区域占原图 >= 95%，认为没必要裁剪（本来就是印章图），返回 None
    rel = (x1 - x0) * (y1 - y0) / (H * W)
    if rel > 0.95:
        return None
    return x0, y0, x1, y1


def compute_stamp_paper_region_mask(
    lab_orig: np.ndarray,
    cfg: ExtractorConfig,
) -> Tuple[np.ndarray, dict]:
    """
    从工作图的原始 Lab float 中，定位「最大的非聊天背景连通域」
    = 邮票纸张本体（含齿孔、墨迹、内部空白纸）的外轮廓 polygon mask。

    只用于：强制把聊天截图白色背景（最外围）alpha=0 删除。
    绝不用于：把 region 内部填实（内部纸张空白仍由 InkScore 负责透明化，
    严格遵守原则 3 / 测试 A：不把邮票外框误当印章实体边界）。

    Parameters
    ----------
    lab_orig : H x W x 3 float32 real-perceptual Lab
    cfg : ExtractorConfig

    Returns
    -------
    region_mask : H x W bool   (True = inside the stamp-paper region)
    meta        : dict with stats (area ratio, whether chat-bg was detected, etc.)
    """
    H, W, _ = lab_orig.shape
    L = lab_orig[..., 0]
    a = lab_orig[..., 1]
    b = lab_orig[..., 2]
    chroma = np.sqrt(a * a + b * b)

    # 1. 聊天背景像素 = 极亮 + 几乎无色
    chat_bg = (L >= cfg.chat_bg_L_min) & (chroma <= cfg.chat_bg_chroma_max)

    # 2. 判断这张图是否真的是「聊天截图」：
    #    关键特征：图像四周的"边框像素"有相当比例是纯白聊天背景。
    #    （因为 subregion 预裁剪会保留四周少量白边，这里我们用"边框像素"判据更稳；
    #      之前用整图 90% 阈值会把"四周都是聊天背景但占比很小"的情况漏掉。）
    border = max(2, int(0.015 * max(H, W)))
    perimeter_mask = np.zeros((H, W), dtype=bool)
    perimeter_mask[:border, :] = True
    perimeter_mask[-border:, :] = True
    perimeter_mask[:, :border] = True
    perimeter_mask[:, -border:] = True
    perimeter_total = max(1, int(perimeter_mask.sum()))
    perimeter_chat_ratio = float((chat_bg & perimeter_mask).sum() / perimeter_total)
    overall_chat_ratio = float(chat_bg.mean())

    # 判定阈值：若「边框 ≥ 35% 聊天白」 或 「整图 ≥ 8% 聊天白」→ 认为存在需要清的外围。
    has_chat_border = (perimeter_chat_ratio >= 0.35) or (overall_chat_ratio >= 0.08)
    if not has_chat_border:
        meta = {
            "candidate_ratio": float((~chat_bg).mean()),
            "chat_bg_ratio": overall_chat_ratio,
            "perimeter_chat_ratio": perimeter_chat_ratio,
            "skipped": True,
            "reason": "no-chat-border-detected",
        }
        return np.ones((H, W), dtype=bool), meta

    # 3. 非聊天背景 = 邮票纸张主体（包括纸、印墨、齿孔齿牙）
    candidate = (~chat_bg)

    candidate_ratio = float(candidate.mean())
    # 4. 找最大连通域
    num, labels, stats, _ = cv2.connectedComponentsWithStats(
        candidate.astype(np.uint8) * 255, connectivity=8
    )
    if num <= 1:
        # 全图都是聊天背景（极端情况）
        return np.zeros((H, W), dtype=bool), {
            "candidate_ratio": candidate_ratio,
            "chat_bg_ratio": float(chat_bg.mean()),
            "skipped": True,
            "reason": "all-chat-bg",
        }
    areas = stats[1:, cv2.CC_STAT_AREA]
    max_i = 1 + int(np.argmax(areas))
    main_label = max_i

    region_mask = (labels == main_label)

    # 4. 非常轻微的 closing（仅作用于 region，不作用于 ink alpha！）
    #    目的：把邮票齿牙通过齿孔缺口连成完整外轮廓。
    r = max(0, int(cfg.stamp_region_close_px))
    if r >= 1:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        region_mask = cv2.morphologyEx(
            region_mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, k, iterations=1
        ) > 127

    # 5. 外扩 border，防止最外一圈齿牙被误删
    b = max(0, int(cfg.stamp_region_border_px))
    if b >= 1:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * b + 1, 2 * b + 1))
        region_mask = cv2.dilate(region_mask.astype(np.uint8) * 255, k, iterations=1) > 127

    meta = {
        "candidate_ratio": candidate_ratio,
        "chat_bg_ratio": overall_chat_ratio,
        "perimeter_chat_ratio": perimeter_chat_ratio,
        "skipped": False,
        "main_area_px": int(stats[main_label, cv2.CC_STAT_AREA]),
        "region_ratio": float(region_mask.mean()),
        "close_r": r,
        "border": b,
    }
    return region_mask, meta


def compute_stamp_outer_shape_mask_from_alpha(
    alpha_fullres: np.ndarray,
    close_bridge_px: int = 32,
    outer_border_px: int = 10,
    min_ink_area_px: int = 4096,
    seed_alpha_thr: int = 50,          # 只有 >= 该 Alpha 的像素才算"墨水位置"（排除纸纹理弱半透明）
    ignore_border_px: int = 0,         # 忽略工作图最外圈 N 像素里的 seed（防 subregion 切边残留杂点把轮廓撑到整图）
    chroma_map: Optional[np.ndarray] = None,   # Lab 空间每像素 chroma = sqrt(a²+b²)，用于排除灰色背景
    seed_chroma_min: float = 0.0,      # 种子最小 chroma；>0 时灰色背景（低饱和度高 alpha）被排除
) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    """
    从「已经算好的 Alpha」反推邮票外轮廓 —— 把「墨水肯定分布的区域」闭合成一个
    大填充多边形（允许内部空白透明，只删除 polygon 外面的任何东西）。

    专门用来删除：img1~3 这种"方形工作图里有一个圆形/异形邮票"的 4 个角纸张像素
    （即邮票齿孔「外面」的纸/背景残留，不管它是聊天白还是普通纸，一律删掉）。

    原则保证：
      * 只把 polygon 外像素 → Alpha 强制 0，不把 polygon 内任何像素改为不透明。
      * 内部纸空白仍由 InkScore 独立透明化（符合原则 3、测试 A/B）。
      * 所有形态学操作只作用于临时 mask，绝不写入输出 Alpha。

    Parameters
    ----------
    alpha_fullres : H x W uint8
    close_bridge_px : 闭合计数器（把外圈环形墨水连成一体）。推荐 24~48。
    outer_border_px  : 闭合后外扩像素（包含最外圈齿孔）。推荐 8~16。
    min_ink_area_px  : 墨水像素总面积过少时（说明不是邮票图），直接放弃。
    seed_alpha_thr   : 用作"墨水种子"的最小 Alpha（默认 50，排除纸纹理的弱半透明）。
    ignore_border_px : 忽略工作图最外圈 N 像素的种子（默认 0；subregion 切图时建议 3~6，
                       防止裁切边界附近的 1px 杂点被 closing 把轮廓"撑"到整图）。
    """
    H, W = alpha_fullres.shape[:2]
    meta: Dict[str, Any] = {
        "close_bridge_px": close_bridge_px,
        "outer_border_px": outer_border_px,
        "seed_alpha_thr": seed_alpha_thr,
        "ignore_border_px": ignore_border_px,
        "seed_chroma_min": seed_chroma_min,
    }

    # 1. 墨水种子：必须是足够强的 alpha，排除纸张纹理产生的 alpha=2/5/10 杂点
    ink_seed = (alpha_fullres >= seed_alpha_thr)

    # 1b. 色彩过滤：如果提供了 chroma_map 且 seed_chroma_min > 0，
    #     排除"高 alpha 但低饱和度"的灰色背景像素（它们不是彩色墨水）。
    #     典型场景：img415767 灰色聊天背景 L 远低于纸色估计 → InkScore 误判为墨水 → alpha 高但 chroma≈0。
    if chroma_map is not None and seed_chroma_min > 0:
        chroma_mask = (chroma_map >= seed_chroma_min)
        n_before = int(ink_seed.sum())
        ink_seed = ink_seed & chroma_mask
        meta["ink_seed_before_chroma_filter"] = n_before
        meta["ink_seed_after_chroma_filter"] = int(ink_seed.sum())

    # 2. 可选：忽略工作图边界的种子（防 subregion 裁切边的杂点撑满整图）
    ib = max(0, int(ignore_border_px))
    if ib > 0:
        ink_seed[:ib, :] = False
        ink_seed[-ib:, :] = False
        ink_seed[:, :ib] = False
        ink_seed[:, -ib:] = False

    ink_pixels = int(ink_seed.sum())
    meta["ink_seed_px"] = ink_pixels
    if ink_pixels < min_ink_area_px:
        meta["skipped"] = True
        meta["reason"] = f"ink-seed-too-small ({ink_pixels}<{min_ink_area_px})"
        return None, meta

    ink_u8 = ink_seed.astype(np.uint8) * 255

    # 3. 超大 closing：把环形印章（例如圆章外环）沿缺口桥接闭合为一个「实心 filled blob」
    #    椭圆核更稳（对圆形/方形/异形都OK），iterations 2 稍微增强桥接
    r = max(1, int(close_bridge_px))
    k_bridge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    closed = cv2.morphologyEx(ink_u8, cv2.MORPH_CLOSE, k_bridge, iterations=2)

    # 3. 找最大外部轮廓 (RETR_EXTERNAL)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        meta["skipped"] = True
        meta["reason"] = "no-contour-after-close"
        return None, meta
    # 取面积最大的轮廓
    max_area = -1.0
    best_contour = contours[0]
    for c in contours:
        a = cv2.contourArea(c)
        if a > max_area:
            max_area = a
            best_contour = c
    meta["largest_contour_area"] = float(max_area)
    meta["num_contours_found"] = int(len(contours))
    if max_area < min_ink_area_px:
        meta["skipped"] = True
        meta["reason"] = f"contour-too-small ({max_area}<{min_ink_area_px})"
        return None, meta

    # 4. 关键稳健性改进：取最大轮廓的 CONVEX HULL（凸包）作为邮票外形多边形。
    #    ——圆形/方形/矩形/椭圆形/异形邮票（整体凸的形状）都可以完美地用凸包表示外轮廓；
    #    ——那些"墨水 closing 后不小心连到方形工作图 4 角"造成的方形外轮廓，会因为凸包
    #      把工作图 4 个角的凸顶点剔除（如果真正的邮票墨水不延伸到那里，凸包不会触及）。
    #    ——完美解决"方形工作图里有圆形邮票"的四角纸漏删。
    #
    # 例外：如果邮票本身明显是非凸的（例如蝴蝶/人形），凸包会略微扩大边界（通常可接受），
    #       但我们提供回退逻辑：当凸包相比原轮廓膨胀超过一定倍数时，放弃凸包改用原轮廓。
    raw_area = float(cv2.contourArea(best_contour))
    hull = cv2.convexHull(best_contour)
    hull_area = float(cv2.contourArea(hull))
    use_hull = True
    if raw_area > 0 and hull_area / raw_area > 1.20:  # 凸包膨胀>20%视为明显非凸，回退原轮廓
        use_hull = False
    final_poly = hull if use_hull else best_contour
    meta["use_convex_hull"] = use_hull
    meta["hull_area"] = hull_area
    meta["raw_contour_area"] = raw_area

    filled_u8 = np.zeros((H, W), dtype=np.uint8)
    cv2.drawContours(filled_u8, [final_poly], 0, 255, thickness=cv2.FILLED)

    # 5. 轻微外扩 border（把最外圈齿孔包含进去）
    b = max(0, int(outer_border_px))
    if b >= 1:
        k_border = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * b + 1, 2 * b + 1))
        filled_u8 = cv2.dilate(filled_u8, k_border, iterations=1)
    region_mask_bool = filled_u8 > 127

    meta["skipped"] = False
    meta["region_ratio"] = float(region_mask_bool.mean())
    return region_mask_bool, meta



