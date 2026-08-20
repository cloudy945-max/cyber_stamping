"""印章增强：提升色彩鲜艳度与锐度，让印章更突出。

DESIGN 原方案用 OpenCV 做「灰度化 + CLAHE + 自适应阈值二值化」，针对扫描件场景。
但实际印章打卡照片通常是彩色照片（印泥红章 + 桌面背景），二值化会丢失色彩信息，
因此改用 Pillow ImageEnhance 做轻量增强：
  - 饱和度 +30%（让红色印泥更鲜艳）
  - 对比度 +15%（拉开印章与背景）
  - 锐度 +30%（边缘更清晰，利于 rembg 抠图）

避免引入 OpenCV 重型依赖（Windows 下安装麻烦），Pillow 跨平台无坑。
"""
from pathlib import Path

from PIL import Image, ImageEnhance


# 增强系数（>1 增强，<1 减弱，=1 不变）
SATURATION_FACTOR = 1.30   # 饱和度
CONTRAST_FACTOR = 1.15      # 对比度
SHARPNESS_FACTOR = 1.30     # 锐度


def enhance_image(src_path: Path, dst_path: Path) -> Path:
    """读取原图 → 增强 → 保存为 PNG（无损，保留透明通道能力）。

    Args:
        src_path: 原图绝对路径
        dst_path: 增强后保存路径（建议 .png）

    Returns:
        dst_path（成功时） / src_path（失败时降级用原图）
    """
    try:
        with Image.open(src_path) as img:
            # 转 RGB 统一处理（避免 RGBA/调色板模式引发异常）
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            # 顺序：先增强对比（影响整体明暗），再饱和度（影响色彩），最后锐度（边缘）
            img = ImageEnhance.Contrast(img).enhance(CONTRAST_FACTOR)
            img = ImageEnhance.Color(img).enhance(SATURATION_FACTOR)
            img = ImageEnhance.Sharpness(img).enhance(SHARPNESS_FACTOR)

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(dst_path, "PNG")
            return dst_path
    except Exception:
        # 增强失败时降级用原图，不阻断后续管线
        return src_path
