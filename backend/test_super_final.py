"""激进去噪 + 方向选择组合"""
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

k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

# ====== 获取原始通道 ======
session = new_session('u2netp')
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]

b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced_r = clahe.apply(r_u8)
r_binary = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 5)

# ====== 方案1：激进开运算是去噪 ======
print("=== 方案1：激进开运算 ===")
# R-G 多次开运算
for open_iter in [1, 2, 3, 4]:
    r_clean = cv2.morphologyEx(r_binary, cv2.MORPH_OPEN, k3, iterations=open_iter)
    r_clean = cv2.bitwise_and(r_clean, circle_m)
    save_diag(f"R_open_k3x{open_iter}", r_clean)

print()
# rembg 多次开运算
_, rembg_binary = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)
for open_iter in [1, 2, 3]:
    rmbg_clean = cv2.morphologyEx(rembg_binary, cv2.MORPH_OPEN, k3, iterations=open_iter)
    rmbg_clean = cv2.bitwise_and(rmbg_clean, circle_m)
    save_diag(f"Rembg_open_k3x{open_iter}", rmbg_clean)

# ====== 方案2：连通块 更高 min_sz ======
print("\n=== 方案2：连通块 高 min_sz ===")
labeled, num = ndimage.label(r_binary > 0)
sizes = ndimage.sum(r_binary > 0, labeled, range(1, num + 1))
for min_sz in [100, 200, 500, 1000, 2000]:
    keep = np.zeros_like(r_binary > 0, dtype=bool)
    for i in range(1, num + 1):
        if sizes[i-1] >= min_sz:
            keep = keep | (labeled == i)
    clean = keep.astype(np.uint8) * 255
    clean = cv2.bitwise_and(clean, circle_m)
    save_diag(f"R_cc_{min_sz}", clean)

print()
labeled2, num2 = ndimage.label(rembg_binary > 0)
sizes2 = ndimage.sum(rembg_binary > 0, labeled2, range(1, num2 + 1))
for min_sz in [100, 200, 500, 1000, 2000]:
    keep = np.zeros_like(rembg_binary > 0, dtype=bool)
    for i in range(1, num2 + 1):
        if sizes2[i-1] >= min_sz:
            keep = keep | (labeled2 == i)
    clean = keep.astype(np.uint8) * 255
    clean = cv2.bitwise_and(clean, circle_m)
    save_diag(f"Rembg_cc_{min_sz}", clean)

# ====== 方案3：最小连通块尺寸 + 方向组合 ======
print("\n=== 方案3：最优去噪参数组合 + 方向加权 ===")
# 选 R-G 中 fg 20-30% 的 cc 参数 做 RIGHT
# 选 rembg 中 fg 20-30% 的 cc 参数 做 LEFT

# 左半边：x < center
left_mask = (np.tile(np.arange(roi_w), (roi_h, 1)) < center_x).astype(np.uint8) * 255
right_mask = 255 - left_mask

# 用多种组合测试
results = []
for r_cc in [200, 500, 1000, 2000, 5000]:
    keep_r = np.zeros_like(r_binary > 0, dtype=bool)
    for i in range(1, num + 1):
        if sizes[i-1] >= r_cc:
            keep_r = keep_r | (labeled == i)
    r_clean = keep_r.astype(np.uint8) * 255
    r_clean = cv2.bitwise_and(r_clean, circle_m)

    for rembg_cc in [200, 500, 1000, 2000, 5000]:
        keep_rm = np.zeros_like(rembg_binary > 0, dtype=bool)
        for i in range(1, num2 + 1):
            if sizes2[i-1] >= rembg_cc:
                keep_rm = keep_rm | (labeled2 == i)
        rembg_clean = keep_rm.astype(np.uint8) * 255
        rembg_clean = cv2.bitwise_and(rembg_clean, circle_m)

        # 方向组合
        left_part = cv2.bitwise_and(rembg_clean, left_mask)
        right_part = cv2.bitwise_and(r_clean, right_mask)
        combined = cv2.bitwise_or(left_part, right_part)
        # 中间 20% 像素区域 OR
        mid_left = int(roi_w * 0.4)
        mid_right = int(roi_w * 0.6)
        mid_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
        mid_mask[:, mid_left:mid_right] = 255
        mid_combined = cv2.bitwise_or(r_clean, rembg_clean)
        mid_combined = cv2.bitwise_and(mid_combined, mid_mask)
        combined = cv2.bitwise_or(combined, mid_combined)

        rates = capture_rate(combined, 32)
        avg = np.mean(list(rates.values()))
        fg = cv2.countNonZero(combined)/(roi_w*roi_h)*100
        results.append((fg, avg, r_cc, rembg_cc, combined, rates))

# 排序找最优 fg 20-35% 且 avg 最大
results.sort(key=lambda x: -x[1])
print("  Top results (fg 15-40%):")
count = 0
for fg, avg, r_cc, rembg_cc, combined, rates in results:
    if 15 <= fg <= 40:
        count += 1
        print(f"    #{count}: fg={fg:.1f}% avg={avg:.0f}% (r_cc={r_cc} rembg_cc={rembg_cc})")
        print(f"       rates: {[f'{k}={v:.0f}%' for k,v in rates.items()]}")
        if count <= 5:
            save_diag(f"BEST_combo_{count}_fg{fg:.0f}_avg{avg:.0f}", combined)
    if count >= 8:
        break

# 如果结果很少，放宽到 45%
if count < 3:
    print("\n  (放宽到 15-45%):")
    count2 = 0
    for fg, avg, r_cc, rembg_cc, combined, rates in results:
        if 15 <= fg <= 45 and avg > 60:
            count2 += 1
            print(f"    #{count2}: fg={fg:.1f}% avg={avg:.0f}% (r_cc={r_cc} rembg_cc={rembg_cc})")
            if count2 <= 5:
                save_diag(f"BEST2_combo_{count2}_fg{fg:.0f}_avg{avg:.0f}", combined)
        if count2 >= 8:
            break
