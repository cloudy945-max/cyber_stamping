"""
stamp_extractor.edge_processing
===============================
可选的极其轻微后处理。默认不启用。
本模块存在是为了将来扩展（例如邮票齿孔边界剔除）预留位置，避免以后改 processor 主流程。
当前实际的轻噪声抑制在 alpha_mask.py 里。
"""
from __future__ import annotations

import cv2
import numpy as np
from .config import ExtractorConfig


def remove_far_tiny_specs(alpha_u8: np.ndarray, cfg: ExtractorConfig) -> np.ndarray:
    """
    一个额外的保守清理：
    把距离强墨水(alpha>=200) 非常远、自身又很淡(alpha<96)的孤立像素清零。
    默认并不会被调用（processor.py 默认关掉它）。原因：它可能删淡墨水细线。
    """
    strong = (alpha_u8 >= 200).astype(np.uint8) * 255
    if strong.sum() < 64:
        return alpha_u8
    dist = cv2.distanceTransform(255 - strong, cv2.DIST_L1, 3)
    weak = (alpha_u8 > 0) & (alpha_u8 < 96) & (dist > 60.0)
    out = alpha_u8.copy()
    out[weak] = 0
    return out
