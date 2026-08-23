"""最终组合 + 严格去噪"""
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
    print(f"  [{name}] fg={fg:.1f}% avg={avg:.0f}%")
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

# 2. 获取三个蒙版
session = new_session('u2netp')
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]
_, rembg_binary = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)
rembg_circle = cv2.bitwise_and(rembg_binary, circle_m)

b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced_r = clahe.apply(r_u8)
r_binary = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 5)
r_circle = cv2.bitwise_and(r_binary, circle_m)

gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced_gray = clahe.apply(gray)
g_binary = cv2.adaptiveThreshold(enhanced_gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 3)
g_circle = cv2.bitwise_and(g_binary, circle_m)

combined = cv2.bitwise_or(cv2.bitwise_or(rembg_circle, r_circle), g_circle)
print(f"Combined raw: fg={cv2.countNonZero(combined)/(roi_w*roi_h)*100:.1f}%")

# 3. 严格去噪方案对比
k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

# A: 大核开运算 (3x3, 2次)
print("\n去噪对比:")
A = cv2.morphologyEx(combined, cv2.MORPH_OPEN, k3, iterations=2)
save_diag("A_open3x2", A)

# B: 3x3 开运算 + 大连通块 (min_sz=100)
B_raw = cv2.morphologyEx(combined, cv2.MORPH_OPEN, k3)
labeled_b, num_b = ndimage.label(B_raw > 0)
if num_b > 0:
    sizes_b = ndimage.sum(B_raw > 0, labeled_b, range(1, num_b + 1))
    min_b = 100
    keep_b = np.zeros_like(B_raw > 0, dtype=bool)
    for i in range(1, num_b + 1):
        if sizes_b[i-1] >= min_b:
            keep_b = keep_b | (labeled_b == i)
    B = keep_b.astype(np.uint8) * 255
save_diag("B_open3+cc100", B)

# C: rembg 主体作为核心锚点，只保留和 rembg 连通的前景
# 膨胀 rembg 作为种子
rembg_seed = cv2.dilate(rembg_circle, k3, iterations=3)
# 和 combined 做交集得到包含种子的部分
seeded = cv2.bitwise_and(combined, rembg_seed)
# 对 combined 做连通块分析，保留和 seeded 相交的组件
labeled_c, num_c = ndimage.label(combined > 0)
seeded_labels = set(labeled_c[seeded > 0].flatten())
keep_c = np.zeros_like(combined > 0, dtype=bool)
for lbl in seeded_labels:
    if lbl > 0:
        keep_c = keep_c | (labeled_c == lbl)
C = keep_c.astype(np.uint8) * 255
save_diag("C_seeded_by_rembg", C)

# D: 圆形环形蒙版 (只保留内圈到外圈的环形区域，去除中心大面积白噪)
inner_r = int(circle_r * 0.15)
ring_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
cv2.circle(ring_mask, (center_x, center_y), circle_r, 255, -1)
cv2.circle(ring_mask, (center_x, center_y), inner_r, 0, -1)
D_ring = cv2.bitwise_and(combined, ring_mask)
D_ring = cv2.morphologyEx(D_ring, cv2.MORPH_OPEN, k3)
save_diag("D_ring_mask", D_ring)

# E: 环形 + 连通块 min_sz=50
labeled_e, num_e = ndimage.label(D_ring > 0)
if num_e > 0:
    sizes_e = ndimage.sum(D_ring > 0, labeled_e, range(1, num_e + 1))
    min_e = 50
    keep_e = np.zeros_like(D_ring > 0, dtype=bool)
    for i in range(1, num_e + 1):
        if sizes_e[i-1] >= min_e:
            keep_e = keep_e | (labeled_e == i)
    E = keep_e.astype(np.uint8) * 255
save_diag("E_ring+cc50", E)

# F: 用 rembg 主体膨胀做蒙版 (rembg → 大膨胀 → 与 combined 交集)
rembg_expanded = cv2.dilate(rembg_circle, k3, iterations=8)
# 填充孔洞
rembg_filled = ndimage.binary_fill_holes(rembg_expanded > 0).astype(np.uint8) * 255
F_masked = cv2.bitwise_and(combined, rembg_filled)
F_masked = cv2.morphologyEx(F_masked, cv2.MORPH_OPEN, k2)
save_diag("F_rembg_expanded_mask", F_masked)
