"""最终版：rembg(左) + R-G增强(右) + 圆形蒙版"""
import os, sys, types
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage
from PIL import Image

# pymatting stub
if "pymatting.alpha.estimate_alpha_cf" not in sys.modules:
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
        if "." in name: mod.__path__ = []
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

from rembg import new_session, remove

src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]
cx_img, cy_img = w//2, int(h*0.55)
r_roi = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx_img-r_roi), max(0,cy_img-r_roi), min(w,cx_img+r_roi), min(h,cy_img+r_roi)
roi_bgr = img[y0:y1, x0:x1]
roi_h, roi_w = roi_bgr.shape[:2]
roi_path = Path('test_output/rembg_roi.jpg')
cv2.imwrite(str(roi_path), roi_bgr)

def capture_rate(alpha, threshold=32):
    center_x, center_y = roi_w // 2, roi_h // 2
    rates = {}
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        angle = np.radians(angle_deg)
        captured = 0
        total = 0
        for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
            px_x = int(center_x + dist * np.cos(angle))
            px_y = int(center_y + dist * np.sin(angle))
            if 0 <= px_x < roi_w and 0 <= px_y < roi_h:
                total += 1
                if alpha[px_y, px_x] > threshold:
                    captured += 1
        rates[angle_deg] = captured / total * 100 if total > 0 else 0
    return rates

def save_diag(name, mask):
    rates = capture_rate(mask, 32)
    avg = np.mean(list(rates.values()))
    fg = cv2.countNonZero(mask)/(roi_w*roi_h)*100
    print(f"  [{name}] fg={fg:.1f}% avg={avg:.0f}% | {[f'{k}={v:.0f}%' for k,v in rates.items()]}")
    cv2.imwrite(str(Path(f'test_output/diag_{name}.png')), mask)
    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y0:y0+roi_h, x0:x0+roi_w] = mask
    rgba = np.dstack([img, full_mask])
    cv2.imwrite(str(Path(f'test_output/diag_{name}_rgba.png')), rgba)

# 1. 圆形蒙版（bbox 中心）
center_x, center_y = roi_w // 2, roi_h // 2
circle_r = int(min(roi_w, roi_h) * 0.48)
circle_m = np.zeros((roi_h, roi_w), dtype=np.uint8)
cv2.circle(circle_m, (center_x, center_y), circle_r, 255, -1)
print(f"Circle mask: r={circle_r} from center ({center_x},{center_y})")

# 2. rembg 蒙版
print("\n[1] rembg mask")
session = new_session('u2netp')
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]
_, rembg_binary = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)
rembg_circle = cv2.bitwise_and(rembg_binary, circle_m)
save_diag("rembg", rembg_circle)

# 3. R-G 增强 + 自适应阈值（bs=21, c=5）
print("\n[2] R-G enhanced mask")
b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced_r = clahe.apply(r_u8)
r_binary = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 5)
r_circle = cv2.bitwise_and(r_binary, circle_m)
save_diag("r_g_enhanced", r_circle)

# 4. 灰度 + 自适应阈值
print("\n[3] Gray enhanced mask")
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced_gray = clahe.apply(gray)
g_binary = cv2.adaptiveThreshold(enhanced_gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 3)
g_circle = cv2.bitwise_and(g_binary, circle_m)
save_diag("gray_enhanced", g_circle)

# 5. OR 组合所有三个蒙版
print("\n[4] Combined (rembg OR R-G OR gray)")
combined = cv2.bitwise_or(cv2.bitwise_or(rembg_circle, r_circle), g_circle)
# 去噪
k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, k2)
# 连通块去噪
labeled, num = ndimage.label(cleaned > 0)
if num > 0:
    sizes = ndimage.sum(cleaned > 0, labeled, range(1, num + 1))
    min_sz = 20
    keep = np.zeros_like(cleaned > 0, dtype=bool)
    for i in range(1, num + 1):
        if sizes[i-1] >= min_sz:
            keep = keep | (labeled == i)
    final = keep.astype(np.uint8) * 255
    save_diag("COMBINED_3", final)

# 6. 方向加权：左半边用 rembg 多一点，右半边用 R-G 多一点
print("\n[5] Direction weighted combine")
# 左半边 mask (x < center)
left_m = (np.tile(np.arange(roi_w), (roi_h, 1)) < center_x).astype(np.uint8) * 255
right_m = 255 - left_m
# 用权重过渡（渐变而不是硬分割）
grad_x = np.tile(np.linspace(0, 1, roi_w), (roi_h, 1)).astype(np.float32)
# 左半边 (60% rembg, 40% R-G) -> 右半边 (40% rembg, 60% R-G)
# 简化：两个 OR 之后再加权 OR
weighted = cv2.bitwise_or(
    cv2.bitwise_or(rembg_circle, cv2.bitwise_and(r_circle, right_m)),
    cv2.bitwise_or(r_circle, cv2.bitwise_and(rembg_circle, left_m))
)
weighted = cv2.bitwise_or(weighted, g_circle)
# 去噪
cleaned2 = cv2.morphologyEx(weighted, cv2.MORPH_OPEN, k2)
labeled2, num2 = ndimage.label(cleaned2 > 0)
if num2 > 0:
    sizes2 = ndimage.sum(cleaned2 > 0, labeled2, range(1, num2 + 1))
    min_sz = 20
    keep2 = np.zeros_like(cleaned2 > 0, dtype=bool)
    for i in range(1, num2 + 1):
        if sizes2[i-1] >= min_sz:
            keep2 = keep2 | (labeled2 == i)
    final2 = keep2.astype(np.uint8) * 255
    save_diag("FINAL_WEIGHTED", final2)

# 7. 纯 OR (rembg | R-G | gray) - 不做方向加权 做最终对比
print("\n[6] Simple OR 3 masks (same as #4 but output image for visual check)")
save_diag("SIMPLE_OR_3", final)
