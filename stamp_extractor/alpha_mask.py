"""
stamp_extractor.alpha_mask
==========================
把 InkScore → 连续 Alpha 0..255。
原则 5：必须是连续的，不能二值化。
原则 6：禁止 MORPH_CLOSE / FillHoles / 大尺度修复。
"""
from __future__ import annotations

import cv2
import numpy as np

from .config import ExtractorConfig


def smoothstep01(x: np.ndarray, e0: float, e1: float) -> np.ndarray:
    """经典 smoothstep。x<=e0 → 0，x>=e1 → 1，中间 Hermite 平滑。"""
    if e1 <= e0:
        # 退化情况：硬阈值
        return np.where(x < e1, np.float32(0.0), np.float32(1.0))
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def score_to_alpha(score: np.ndarray, cfg: ExtractorConfig) -> np.ndarray:
    """
    InkScore (越大越像墨) → alpha (float32, 0..255)。
    注意：score 的值越大越像墨；smoothstep(score, lo, hi) 直接就是 alpha_01。
    """
    # 防御性：去掉可能的 NaN/inf（来自上游极端情况），把它们视作 0 → 透明
    s = np.nan_to_num(score, nan=0.0, posinf=1e4, neginf=0.0).astype(np.float32)
    alpha_01 = smoothstep01(s, cfg.ink_low, cfg.ink_high)
    # alpha_strength 增强（只抬升中间区域，顶端用 clamp）
    alpha_01 = np.clip(alpha_01 * cfg.alpha_strength, 0.0, 1.0)
    out_u8 = np.floor(alpha_01 * cfg.alpha_clamp_max + 0.5)
    return np.clip(out_u8, 0, 255).astype(np.uint8)


def very_light_denoise(alpha_u8: np.ndarray, cfg: ExtractorConfig) -> np.ndarray:
    """
    极其轻的噪声抑制：
      - 可选：中值滤波，核=0或3。
      - 可选：删除极小连通域（默认关闭=0）。
    严格遵循原则 6：不做任何 closing / filling / 大范围膨胀腐蚀。
    """
    out = alpha_u8.copy()
    # 1. 中值（默认 0，不启用）
    if cfg.noise_median_ksize >= 3 and (cfg.noise_median_ksize & 1) == 1:
        out = cv2.medianBlur(out, cfg.noise_median_ksize)

    # 2. 极小连通域剔除（默认 noise_min_area=0 关闭）
    if cfg.noise_min_area and cfg.noise_min_area >= 1:
        # 只处理"真实前景"的部分：alpha > 32 算作连通
        bin_fg = (out >= 32).astype(np.uint8) * 255
        num, labels, stats, _ = cv2.connectedComponentsWithStats(bin_fg, connectivity=8)
        if num > 1:
            killed = np.zeros(out.shape, dtype=bool)
            for i in range(1, num):
                if stats[i, cv2.CC_STAT_AREA] < cfg.noise_min_area:
                    killed[labels == i] = True
            out = out.copy()
            out[killed] = 0
    return out
