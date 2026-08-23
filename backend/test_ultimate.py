"""终极方案：粗蒙版（全覆盖）+ 精细阈值（去噪）"""
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
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))

# ========== 步骤1：构建粗蒙版（全覆盖，可能含背景） ==========
print("=== Step 1: 粗蒙版构建 ===")

session = new_session('u2netp')
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]
_, rembg_binary = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)

b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
enhanced_r = clahe.apply(r_u8)
r_binary = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 5)

# OR + 大膨胀 + 填充 = 全覆盖蒙版
coarse_raw = cv2.bitwise_or(rembg_binary, r_binary)
coarse_raw = cv2.bitwise_and(coarse_raw, circle_m)
save_diag("S1_coarse_raw", coarse_raw)

# 膨胀 6 次 + 填充
coarse_dilated = cv2.dilate(coarse_raw, k3, iterations=6)
coarse_filled = ndimage.binary_fill_holes(coarse_dilated > 0).astype(np.uint8) * 255
# 再膨胀 2 次确保覆盖外圈
coarse_mask = cv2.dilate(coarse_filled, k3, iterations=2)
save_diag("S1_coarse_mask_final", coarse_mask)

# ========== 步骤2：在粗蒙版内用精细阈值提取线条 ==========
print("\n=== Step 2: 精细阈值提取 ===")

gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced_gray = clahe.apply(gray)

# 在粗蒙版范围内：灰度自适应阈值（多参数测试）
for bs in [11, 21, 31, 51]:
    for c in [2, 3, 5, 8]:
        if bs % 2 == 0: bs += 1
        fine = cv2.adaptiveThreshold(enhanced_gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY_INV, bs, c)
        # 限制在粗蒙版内
        fine_masked = cv2.bitwise_and(fine, coarse_mask)
        # 开运算去噪 + 小连通块去噪
        fine_clean = cv2.morphologyEx(fine_masked, cv2.MORPH_OPEN, k2)
        labeled, num = ndimage.label(fine_clean > 0)
        if num > 0:
            sizes = ndimage.sum(fine_clean > 0, labeled, range(1, num + 1))
            min_sz = 30
            keep = np.zeros_like(fine_clean > 0, dtype=bool)
            for i in range(1, num + 1):
                if sizes[i-1] >= min_sz:
                    keep = keep | (labeled == i)
            fine_clean = keep.astype(np.uint8) * 255
        rates = capture_rate(fine_clean, 32)
        avg = np.mean(list(rates.values()))
        fg = cv2.countNonZero(fine_clean)/(roi_w*roi_h)*100
        if 15 <= fg <= 35 and avg >= 60:
            print(f"  ✓ bs={bs} c={c} sz=30: fg={fg:.1f}% avg={avg:.0f}%")
            save_diag(f"fine_bs{bs}_c{c}", fine_clean)
        elif fg <= 10:
            pass
        else:
            print(f"  ✗ bs={bs} c={c} sz=30: fg={fg:.1f}% avg={avg:.0f}%")

# ========== 步骤3：同时也用 R-G 精细提取（左半边 rembg 强，右半边 R-G 强） ==========
print("\n=== Step 3: R-G 精细 + 灰度精细 OR ===")
# 取 Step2 中最好的一个参数组合（假设 fg 15-35 avg>=60 存在）
# 先选一个最平衡的
best_gray = None
best_avg = 0
for bs in [21, 31, 51]:
    for c in [2, 3]:
        if bs % 2 == 0: bs += 1
        fine = cv2.adaptiveThreshold(enhanced_gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, bs, c)
        fine_masked = cv2.bitwise_and(fine, coarse_mask)
        fine_clean = cv2.morphologyEx(fine_masked, cv2.MORPH_OPEN, k2)
        labeled, num = ndimage.label(fine_clean > 0)
        if num > 0:
            sizes = ndimage.sum(fine_clean > 0, labeled, range(1, num + 1))
            keep = np.zeros_like(fine_clean > 0, dtype=bool)
            for i in range(1, num + 1):
                if sizes[i-1] >= 30:
                    keep = keep | (labeled == i)
            fine_clean = keep.astype(np.uint8) * 255
        rates = capture_rate(fine_clean, 32)
        avg = np.mean(list(rates.values()))
        fg = cv2.countNonZero(fine_clean)/(roi_w*roi_h)*100
        if 10 <= fg <= 40 and avg > best_avg:
            best_avg = avg
            best_gray = fine_clean.copy()

if best_gray is not None:
    save_diag("BEST_GRAY", best_gray)

# R-G 精细：bs=21 c=5 + 粗蒙版限制 + 严格去噪
r_fine = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 5)
r_fine_masked = cv2.bitwise_and(r_fine, coarse_mask)
r_fine_clean = cv2.morphologyEx(r_fine_masked, cv2.MORPH_OPEN, k3, iterations=2)
labeled, num = ndimage.label(r_fine_clean > 0)
if num > 0:
    sizes = ndimage.sum(r_fine_clean > 0, labeled, range(1, num + 1))
    keep = np.zeros_like(r_fine_clean > 0, dtype=bool)
    for i in range(1, num + 1):
        if sizes[i-1] >= 100:
            keep = keep | (labeled == i)
    r_fine_clean = keep.astype(np.uint8) * 255
save_diag("R_FINE_STRICT", r_fine_clean)

# rembg 精细：alpha > 64 + 连通块去噪
rembg_fine = rembg_binary.copy()
labeled, num = ndimage.label(rembg_fine > 0)
if num > 0:
    sizes = ndimage.sum(rembg_fine > 0, labeled, range(1, num + 1))
    keep = np.zeros_like(rembg_fine > 0, dtype=bool)
    for i in range(1, num + 1):
        if sizes[i-1] >= 30:
            keep = keep | (labeled == i)
    rembg_fine = keep.astype(np.uint8) * 255
save_diag("REMBG_FINE", rembg_fine)

# 三通道精细 OR
combined_fine = cv2.bitwise_or(cv2.bitwise_or(best_gray if best_gray is not None else np.zeros_like(r_fine_clean), r_fine_clean), rembg_fine)
combined_fine = cv2.bitwise_and(combined_fine, coarse_mask)
save_diag("FINAL_COMBINED_FINE", combined_fine)
