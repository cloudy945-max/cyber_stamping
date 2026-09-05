"""
stamp_extractor.background
==========================
全局纸张颜色估计 + 局部亮度背景建模（应对光照不均）。
符合原则 4「多点采样」与原则 11「局部背景估计」。
"""
from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Tuple

from .config import ExtractorConfig
from .utils import rgb_uint8_to_lab_float


@dataclass
class PaperModel:
    """全局纸张在 Lab 空间的代表颜色。"""
    lab_mean: np.ndarray  # (3,) float32: [L, a, b]
    lab_std: np.ndarray   # (3,) float32
    mask: np.ndarray      # (H, W) bool：用于计算纸张的采样像素掩膜
    n_samples: int


def _percentile_axis0(arr: np.ndarray, p: float) -> np.ndarray:
    """对 (N, 3) 数组按列求百分位。"""
    return np.percentile(arr, p, axis=0)


def estimate_global_paper_lab(
    rgb_uint8: np.ndarray, cfg: ExtractorConfig
) -> PaperModel:
    """从 uint8 RGB 估计纸色。"""
    lab = rgb_uint8_to_lab_float(rgb_uint8)  # L∈[0,100], a,b∈[-128,127]
    return estimate_paper_from_lab_float(lab, cfg)


def estimate_paper_from_lab_float(
    lab: np.ndarray, cfg: ExtractorConfig
) -> PaperModel:
    """直接从 float32 Lab (H,W,3) 估计纸色。"""
    H, W, _ = lab.shape
    total = H * W
    L = lab[:, :, 0]
    a = lab[:, :, 1]
    b = lab[:, :, 2]
    chroma = np.sqrt(a * a + b * b)

    # Step 1: 基于全局 L 百分位选出「高亮区域」（纸是亮的）
    L_flat = L.reshape(-1)
    lo = float(np.percentile(L_flat, cfg.paper_percentile_lo))
    hi = float(np.percentile(L_flat, cfg.paper_percentile_hi))

    bright = (L >= lo) & (L <= hi)
    low_chroma = chroma <= cfg.paper_max_chroma
    candidate_mask = bright & low_chroma

    MIN_RATIO = 0.005  # 纸像素至少应占 0.5% 图像，否则认为算法太严
    if not candidate_mask.any() or candidate_mask.mean() < MIN_RATIO:
        # 极端情况：放宽 chroma 阈值
        relaxed_c = max(15.0, cfg.paper_max_chroma * 1.5)
        bright_only = (L >= lo - 8)
        candidate_mask = bright_only & (chroma <= relaxed_c)

    # Step 2: 稳健均值 + 迭代剔除离群（最多 2 轮，且每轮保留 >= 前一轮 60%，防止塌缩）
    mask = candidate_mask
    prev_count = int(mask.sum())
    for _it in range(2):
        if prev_count < max(256, int(total * MIN_RATIO)):
            break
        pts = lab[mask].reshape(-1, 3)
        med = np.median(pts, axis=0)
        mad = np.median(np.abs(pts - med), axis=0) + 1e-3
        # 剔除 > 5 MAD 的离群（更宽松，5 而不是 4）
        dev = np.abs(lab - med)
        keep = np.all(dev <= 5.0 * mad + 1.5, axis=2)
        new_mask = mask & keep
        new_count = int(new_mask.sum())
        # 防止塌缩：如果剔除超过 40% 就不迭代了
        if new_count < prev_count * 0.60 or new_count < 128:
            break
        mask = new_mask
        prev_count = new_count

    pts = lab[mask].reshape(-1, 3)
    if len(pts) < 32:
        # 实在样本太少：直接用候选集（第一轮未剔之前的集合）
        pts = lab[candidate_mask].reshape(-1, 3)
        mask = candidate_mask

    if len(pts) < 32:
        # 最后兜底：根据 L 分位构造 paper 色（只看最亮的 20% 像素）
        L_top_val = float(np.percentile(L_flat, 80))
        fallback_mask = L >= L_top_val
        pts = lab[fallback_mask].reshape(-1, 3)
        mask = fallback_mask

    pts = np.asarray(pts, dtype=np.float32)
    if len(pts) < 2:
        # 极端情况：整个图都是纯色，手动给一个白纸色（float Lab）
        mean = np.array([95.0, 0.0, 3.0], dtype=np.float32)
        std = np.array([2.0, 1.0, 1.0], dtype=np.float32)
        return PaperModel(lab_mean=mean, lab_std=std, mask=np.ones((H, W), dtype=bool), n_samples=1)

    mean = np.mean(pts, axis=0).astype(np.float32)
    std = np.std(pts, axis=0).astype(np.float32)
    # 下限防止除零及异常窄分布（实际照片纸色分布不会窄于这个）
    std = np.maximum(std, np.float32([0.8, 0.4, 0.4]))
    return PaperModel(lab_mean=mean, lab_std=std, mask=mask, n_samples=len(pts))


def estimate_local_luminance(
    lab_L: np.ndarray, cfg: ExtractorConfig
) -> np.ndarray:
    """
    低频局部亮度估计，用于应对纸张阴影（原则 11）。
    核大小随图大小自适应。
    返回 (H, W) float32 的局部亮度估计。
    """
    H, W = lab_L.shape
    sigma_px = float(max(3, int(cfg.local_bg_sigma_ratio * max(H, W))))
    # 保证奇数
    k = int(sigma_px) | 1
    ksize = (max(3, k), max(3, k))
    # 使用 cv2.GaussianBlur 的 sigma 自动由 ksize 推导的做法稳妥
    return cv2.GaussianBlur(lab_L, ksize, sigmaX=sigma_px, sigmaY=sigma_px).astype(np.float32)


def apply_local_luminance_correction(
    lab: np.ndarray, cfg: ExtractorConfig
) -> Tuple[np.ndarray, np.ndarray]:
    """
    仅对 L 通道做局部亮度归一化：
        L' = (L / local_L)^g * ref_L
    其中 ref_L = 全局纸色 L 估计的附近常数（取局部亮度的均值）。
    返回 (lab_norm, local_L_map)；如果关闭则返回 (原 lab, ones)。
    """
    if not cfg.local_bg_enabled:
        ones = np.ones(lab.shape[:2], dtype=np.float32)
        return lab, ones
    L = lab[:, :, 0]
    local_L = estimate_local_luminance(L, cfg)
    safe_local = np.maximum(local_L, 1.0)  # L 范围 0..100，但别除 0
    ref_L = float(np.mean(local_L))
    ratio = (L / safe_local).astype(np.float32)
    # g=0.7 避免过度校正（淡墨也可能是局部变暗）
    ratio_g = np.power(ratio, cfg.local_bg_gain)
    new_L = np.clip(ratio_g * ref_L, 0.0, 100.0).astype(np.float32)
    out = lab.copy()
    out[:, :, 0] = new_L
    return out, local_L
