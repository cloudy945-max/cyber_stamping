"""软 alpha：基于颜色距离的连续透明度（不做二值化）"""
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
    fg = cv2.countNonZero(mask > 32)/(roi_w*roi_h)*100
    print(f"  [{name}] fg(>32)={fg:.1f}% avg(cap>32)={avg:.0f}%")
    cv2.imwrite(str(Path(f'test_output/diag_{name}.png')), mask)
    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y0:y0+roi_h, x0:x0+roi_w] = mask
    rgba = np.dstack([img, full_mask])
    cv2.imwrite(str(Path(f'test_output/diag_{name}_rgba.png')), rgba)

# 先构建粗蒙版
center_x, center_y = roi_w // 2, roi_h // 2
circle_r = int(min(roi_w, roi_h) * 0.48)
circle_m = np.zeros((roi_h, roi_w), dtype=np.uint8)
cv2.circle(circle_m, (center_x, center_y), circle_r, 255, -1)

k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
session = new_session('u2netp')
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]
_, rembg_binary = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)

b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced_r = clahe.apply(r_u8)
r_binary = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 5)

coarse_raw = cv2.bitwise_or(rembg_binary, r_binary)
coarse_raw = cv2.bitwise_and(coarse_raw, circle_m)
coarse_dilated = cv2.dilate(coarse_raw, k3, iterations=6)
coarse_filled = ndimage.binary_fill_holes(coarse_dilated > 0).astype(np.uint8) * 255
coarse_mask = cv2.dilate(coarse_filled, k3, iterations=2)
print(f"粗蒙版覆盖: {cv2.countNonZero(coarse_mask>0)/(roi_w*roi_h)*100:.1f}%")

# ====== 软 Alpha 算法 ======
print("\n=== 软 Alpha ===")

# 在粗蒙版内部，对于每个像素计算颜色"印章度"
# 方法1：离白色的距离
roi_float = roi_bgr.astype(np.float32)
# 距离纯白 (255,255,255) 的欧氏距离
dist_white = np.sqrt(np.sum((255.0 - roi_float) ** 2, axis=2))
# 归一化到 0-255
dist_white_norm = np.clip(dist_white / 80.0 * 255.0, 0, 255).astype(np.uint8)
alpha_white = cv2.bitwise_and(dist_white_norm, coarse_mask)
save_diag("A_dist_white", alpha_white)

# 方法2：红色特征 R - max(G,B)
r_max_gb = cv2.subtract(r_ch.astype(np.int16), cv2.max(g_ch, b_ch).astype(np.int16))
r_max_gb_norm = np.clip(r_max_gb.astype(np.int32) * 8, 0, 255).astype(np.uint8)
alpha_red = cv2.bitwise_and(r_max_gb_norm, coarse_mask)
save_diag("B_red_feature", alpha_red)

# 方法3：离"纯白纸颜色"（由粗蒙版边缘取样）的距离
# 取粗蒙版外一圈作为背景色样本
bg_sample_mask = cv2.subtract(circle_m, cv2.erode(circle_m, k3, iterations=3))
bg_pixels = roi_bgr[bg_sample_mask > 0]
if len(bg_pixels) > 100:
    bg_color = bg_pixels.mean(axis=0)
    print(f"  背景采样色 BGR: {bg_color}")
    dist_bg = np.sqrt(np.sum((roi_float - bg_color.reshape(1,1,3)) ** 2, axis=2))
    dist_bg_norm = np.clip(dist_bg / 60.0 * 255.0, 0, 255).astype(np.uint8)
    alpha_bg = cv2.bitwise_and(dist_bg_norm, coarse_mask)
    save_diag("C_dist_bgcolor", alpha_bg)

# 方法4：距离背景色 + 红色特征 加权
print("\n=== 加权组合 ===")
# soft combination
def soft_combine(a, b, weight_a=0.5):
    return np.clip(a.astype(np.int32) * weight_a + b.astype(np.int32) * (1 - weight_a), 0, 255).astype(np.uint8)

if len(bg_pixels) > 100:
    alpha_wb = soft_combine(alpha_bg, alpha_red, 0.5)
    save_diag("D_distbg_red_0.5", alpha_wb)
    alpha_wb2 = soft_combine(alpha_bg, alpha_red, 0.7)
    save_diag("E_distbg_red_0.7", alpha_wb2)

# 方法5：粗蒙版内 + 自适应阈值线条的"信心度"（灰度 CLAHE 值反向）
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced = clahe.apply(gray)
# 越暗的地方，alpha 越高（暗=印章线条）
alpha_dark = np.clip((255 - enhanced.astype(np.int32)) * 2, 0, 255).astype(np.uint8)
alpha_dark = cv2.bitwise_and(alpha_dark, coarse_mask)
save_diag("F_darkness", alpha_dark)

# 方法6：dist_bgcolor + darkness
if len(bg_pixels) > 100:
    alpha_all = soft_combine(alpha_bg, alpha_dark, 0.5)
    save_diag("G_distbg_dark_0.5", alpha_all)
    alpha_all2 = soft_combine(alpha_all, alpha_red, 0.7)
    save_diag("H_distbg_dark_red", alpha_all2)

# 7. 同时输出粗蒙版 + rembg 原始 alpha（软版本）
rembg_soft = cv2.bitwise_and(rembg_alpha, coarse_mask)
save_diag("I_rembg_soft", rembg_soft)

# 8. rembg soft + dist_bg 组合
if len(bg_pixels) > 100:
    final_soft = soft_combine(rembg_soft, alpha_bg, 0.4)
    save_diag("J_rembg40_distbg60", final_soft)

    final_soft2 = soft_combine(final_soft, alpha_red, 0.7)
    save_diag("K_ultimate_soft", final_soft2)
