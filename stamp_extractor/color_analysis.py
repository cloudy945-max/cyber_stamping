"""
stamp_extractor.color_analysis
==============================
Lab 距离、饱和度加权、局部对比度。
不使用单一简单阈值，多个指标融合 InkScore。
"""
from __future__ import annotations

import cv2
import numpy as np

from .config import ExtractorConfig
from .background import PaperModel


def compute_weighted_lab_distance(
    lab_norm: np.ndarray, paper: PaperModel, cfg: ExtractorConfig
) -> np.ndarray:
    """
    按权重加权计算每个像素到纸色的距离。
    d = sqrt( w_L * dL^2 + w_a * da^2 + w_b * db^2 )
    注意：
    - dL 只取「纸比像素亮」的部分（max(paper.L - px.L, 0)），
      防止局部过曝 / 反光区域（比纸还亮）被当作墨水。
    - da, db 取绝对值平方，因为墨水可能偏任何方向。
    返回 (H, W) float32 距离图（近似 ΔE 单位）。
    """
    Lp, ap, bp = paper.lab_mean.tolist()
    dL = np.clip(Lp - lab_norm[:, :, 0], 0.0, None)
    da = lab_norm[:, :, 1] - ap
    db = lab_norm[:, :, 2] - bp

    d2 = (cfg.weight_L * (dL * dL)
          + cfg.weight_a * (da * da)
          + cfg.weight_b * (db * db))
    return np.sqrt(np.maximum(d2, 0.0)).astype(np.float32)


def chroma_relative_boost(lab_norm: np.ndarray, paper: PaperModel) -> np.ndarray:
    """
    饱和度加分项：
        chroma_px = sqrt(a² + b²)
        若明显高于纸 chroma，则 boost 大于 1。
    返回乘法增益，范围 [1, ~3]。
    """
    Lp, ap, bp = paper.lab_mean.tolist()
    paper_c = float(np.sqrt(ap * ap + bp * bp)) + 1e-3
    px_c = np.sqrt(lab_norm[:, :, 1] ** 2 + lab_norm[:, :, 2] ** 2)
    rel = (px_c / paper_c).astype(np.float32)
    # rel 在 1 附近 → 1；rel 大 → 上升但有上限
    return 1.0 + np.tanh(np.maximum(rel - 1.0, 0.0)).astype(np.float32)


def darkness_relative_boost(lab_norm: np.ndarray, paper: PaperModel) -> np.ndarray:
    """
    专门照顾低饱和的黑/深灰墨迹。
    比纸色暗的程度越大，加成越大。返回 [1, ~2.5]。
    """
    Lp = paper.lab_mean[0]
    delta_L = np.clip(Lp - lab_norm[:, :, 0], 0.0, None)
    # delta_L 在 0~20 区间慢慢升，超过 30 后趋于饱和
    return (1.0 + 1.5 * (1.0 - np.exp(-delta_L / 15.0))).astype(np.float32)


def local_contrast_score(
    distance_map: np.ndarray, cfg: ExtractorConfig
) -> np.ndarray:
    """
    基于距离图本身的局部残差：
        residual = dist - blur(dist)
    residual > 0 的像素，是「比局部周围更像墨水」的点，通常是线条/文字/颗粒；
    残差越大（局部对比度越高），加分越多。
    返回一个范围 ~[0.8, 1.5] 的乘法增益图。
    """
    if not cfg.local_contrast_enabled:
        return np.ones_like(distance_map, dtype=np.float32)
    k = cfg.local_contrast_ksize
    if k < 3 or (k & 1) == 0:
        k = k | 1
        k = max(3, k)
    blurred = cv2.GaussianBlur(distance_map, (k, k), sigmaX=0)
    residual = distance_map - blurred
    # 正数残差 → 提升；负数残差 → 轻度打压（但不要打到 0，保守点）
    gain = 1.0 + np.clip(residual / 4.0, -0.3, cfg.local_contrast_strength)
    return gain.astype(np.float32)


def fused_ink_score(
    lab_norm: np.ndarray,
    paper: PaperModel,
    cfg: ExtractorConfig,
) -> dict:
    """
    融合多指标得到连续 InkScore（= ΔE 风格，越大越像墨）。
    返回 dict，含：
        distance_map / chroma_gain / darkness_gain / contrast_gain / score
    """
    dist = compute_weighted_lab_distance(lab_norm, paper, cfg)

    # 乘法增益
    c_gain = chroma_relative_boost(lab_norm, paper)
    d_gain = darkness_relative_boost(lab_norm, paper)
    lc_gain = local_contrast_score(dist, cfg)

    # 最终分数
    chroma_mult = 1.0 + cfg.saturation_boost * (c_gain - 1.0)
    dark_mult = 1.0 + cfg.darkness_boost * (d_gain - 1.0)
    score = dist * chroma_mult * dark_mult * lc_gain

    return dict(
        distance_map=dist,
        chroma_gain=c_gain,
        darkness_gain=d_gain,
        contrast_gain=lc_gain,
        score=score.astype(np.float32),
    )
