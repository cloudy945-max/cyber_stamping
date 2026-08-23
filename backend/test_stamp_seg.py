"""印章颜色分割测试：HSV 红色阈值 + 形态学 + 最大连通块。

独立测试脚本，不修改现有 backend/app/services 代码。
验证能否从 8181 照片中自动分割出红色印章。

运行：python test_stamp_seg.py
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

# 输入输出
SRC = Path(r"d:\projects\cyber_stamping\backend\test_output\8181_original.jpg")
OUT_DIR = Path(r"d:\projects\cyber_stamping\backend\test_output\seg")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def segment_red_stamp(img_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """从 BGR 图像中分割红色印章。

    返回 (mask, cleaned_mask)：mask 是原始红色阈值，cleaned_mask 是形态学+连通块处理后的。
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # 红色在 HSV 中横跨 0°，需要两段阈值
    # H: 0-180 (OpenCV), 红色 = [0,10] ∪ [170,180]
    # S: 0-255, 印章红饱和度高 > 70
    # V: 0-255, 排除过暗 > 50
    lower1 = np.array([0, 70, 50])
    upper1 = np.array([10, 255, 255])
    lower2 = np.array([170, 70, 50])
    upper2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)

    # 形态学：闭运算填洞 + 开运算去噪
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel_open)

    return mask, cleaned


def extract_largest_blob(mask: np.ndarray) -> tuple[np.ndarray, dict]:
    """取最大连通块，返回 (blob_mask, info)。"""
    binary = mask > 0
    labeled, num = ndimage.label(binary)
    if num == 0:
        return np.zeros_like(mask), {"found": False}

    sizes = ndimage.sum(binary, labeled, range(1, num + 1))
    largest = np.argmax(sizes) + 1

    blob = (labeled == largest).astype(np.uint8) * 255

    slices = ndimage.find_objects(labeled == largest)[0]
    y0, y1 = slices[0].start, slices[0].stop
    x0, x1 = slices[1].start, slices[1].stop

    H, W = mask.shape
    info = {
        "found": True,
        "area": int(sizes[largest - 1]),
        "bbox": (x0, y0, x1, y1),
        "size": (x1 - x0, y1 - y0),
        "ratio_w": (x1 - x0) / W,
        "ratio_h": (y1 - y0) / H,
        "image_size": (W, H),
    }
    return blob, info


def make_rgba(img_bgr: np.ndarray, alpha_mask: np.ndarray) -> Image.Image:
    """用 alpha_mask 作为 alpha 通道生成 RGBA PIL Image。"""
    rgba = np.dstack([img_bgr, alpha_mask])
    return Image.fromarray(rgba, "RGBA")


# ===== 主流程 =====
print("=" * 60)
print("印章颜色分割测试 (8181)")
print("=" * 60)

img_bgr = cv2.imread(str(SRC))
H, W = img_bgr.shape[:2]
print(f"原图尺寸: {W} x {H}")

mask, cleaned = segment_red_stamp(img_bgr)
blob, info = extract_largest_blob(cleaned)

# 统计
total = H * W
mask_pixels = (mask > 0).sum()
cleaned_pixels = (cleaned > 0).sum()
print(f"\n红色阈值像素: {mask_pixels} ({mask_pixels/total*100:.2f}%)")
print(f"形态学后像素: {cleaned_pixels} ({cleaned_pixels/total*100:.2f}%)")

if info["found"]:
    print(f"\n最大连通块:")
    print(f"  面积: {info['area']} 像素 ({info['area']/total*100:.2f}%)")
    print(f"  边界框: x=[{info['bbox'][0]},{info['bbox'][2]}], y=[{info['bbox'][1]},{info['bbox'][3]}]")
    print(f"  尺寸: {info['size'][0]} x {info['size'][1]}")
    print(f"  占图比例: 宽{info['ratio_w']*100:.1f}% 高{info['ratio_h']*100:.1f}%")
else:
    print("未找到红色区域")

# 保存各阶段结果
cv2.imwrite(str(OUT_DIR / "01_red_mask.png"), mask)
cv2.imwrite(str(OUT_DIR / "02_cleaned.png"), cleaned)
cv2.imwrite(str(OUT_DIR / "03_largest_blob.png"), blob)

# 生成 RGBA 贴纸
rgba = make_rgba(img_bgr, blob)
# 裁剪到印章边界框（加 padding）
pad = 30
x0, y0, x1, y1 = info["bbox"]
crop = rgba.crop(
    (max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad))
)
crop.save(str(OUT_DIR / "04_stamp_sticker.png"))

# 叠加可视化（红色 mask 半透明叠在原图上）
overlay = img_bgr.copy()
overlay[blob > 0] = [0, 0, 255]  # 纯红高亮
blended = cv2.addWeighted(img_bgr, 0.5, overlay, 0.5, 0)
cv2.rectangle(blended, (x0, y0), (x1, y1), (0, 255, 0), 3)
cv2.imwrite(str(OUT_DIR / "05_overlay.png"), blended)

print(f"\n结果已保存到: {OUT_DIR}")
print("  01_red_mask.png      - 原始红色阈值")
print("  02_cleaned.png       - 形态学处理后")
print("  03_largest_blob.png  - 最大连通块")
print("  04_stamp_sticker.png - 印章贴纸 (RGBA, 裁剪)")
print("  05_overlay.png       - 原图叠加可视化")
