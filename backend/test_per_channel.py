"""每个通道先严格去噪 再 OR 组合"""
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

center_x, center_y = roi_w // 2, roi_h // 2
circle_r = int(min(roi_w, roi_h) * 0.48)
circle_m = np.zeros((roi_h, roi_w), dtype=np.uint8)
cv2.circle(circle_m, (center_x, center_y), circle_r, 255, -1)

# 1. 获取三个通道的 raw 结果
print("=== 每个通道 raw + 去噪对比 ===")
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

def clean_mask(binary, min_sz=50, open_k=k3, open_iter=1):
    """统一去噪流程：开运算 + 连通块过滤"""
    # 开运算
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_k, iterations=open_iter)
    # 连通块去噪
    labeled, num = ndimage.label(cleaned > 0)
    if num == 0:
        return cleaned
    sizes = ndimage.sum(cleaned > 0, labeled, range(1, num + 1))
    keep = np.zeros_like(cleaned > 0, dtype=bool)
    for i in range(1, num + 1):
        if sizes[i-1] >= min_sz:
            keep = keep | (labeled == i)
    return keep.astype(np.uint8) * 255

# --- R-G 增强 ---
print("\n--- R-G 通道 ---")
b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
enhanced_r = clahe.apply(r_u8)
for bs in [21, 31]:
    for c in [5, 8, 10]:
        if bs % 2 == 0: bs += 1
        binary = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, bs, c)
        masked = cv2.bitwise_and(binary, circle_m)
        # 去噪：k3 open 1次 + min_sz 200
        cleaned = clean_mask(masked, min_sz=200, open_k=k3, open_iter=1)
        rates = capture_rate(cleaned, 32)
        avg = np.mean(list(rates.values()))
        fg = cv2.countNonZero(cleaned)/(roi_w*roi_h)*100
        print(f"  bs={bs} c={c} min_sz=200: fg={fg:.1f}% avg={avg:.0f}%")
        if fg < 40 and avg > 50:
            save_diag(f"rg_bs{bs}_c{c}_sz200", cleaned)

# --- 灰度 ---
print("\n--- 灰度通道 ---")
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced_gray = clahe.apply(gray)
for bs in [31, 51, 71]:
    for c in [3, 5, 8]:
        if bs % 2 == 0: bs += 1
        binary = cv2.adaptiveThreshold(enhanced_gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, bs, c)
        masked = cv2.bitwise_and(binary, circle_m)
        cleaned = clean_mask(masked, min_sz=200, open_k=k3, open_iter=1)
        rates = capture_rate(cleaned, 32)
        avg = np.mean(list(rates.values()))
        fg = cv2.countNonZero(cleaned)/(roi_w*roi_h)*100
        print(f"  bs={bs} c={c} min_sz=200: fg={fg:.1f}% avg={avg:.0f}%")
        if fg < 40 and avg > 50:
            save_diag(f"gray_bs{bs}_c{c}_sz200", cleaned)

# --- rembg ---
print("\n--- rembg ---")
session = new_session('u2netp')
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]
    _, rembg_binary = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)
    rembg_circle = cv2.bitwise_and(rembg_binary, circle_m)
    save_diag("rembg_raw", rembg_circle)
