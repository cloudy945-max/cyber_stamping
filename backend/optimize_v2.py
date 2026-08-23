"""缩小搜索范围：3 种通道 + rembg alpha 混合。"""
import os, sys, types
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage
from PIL import Image

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

outer_ring = cv2.subtract(circle_m, cv2.erode(circle_m, k3, iterations=5))
bg_pixels = roi_bgr[outer_ring > 0]
bg_color = bg_pixels.mean(axis=0) if len(bg_pixels) >= 100 else np.array([230,230,230])

roi_f = roi_bgr.astype(np.float32)
dist_bg = np.sqrt(np.sum((roi_f - bg_color.reshape(1,1,3)) ** 2, axis=2))
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced_gray = clahe.apply(gray)
alpha_dark_raw = (255 - enhanced_gray.astype(np.int32)).astype(np.float32)
alpha_red_raw = cv2.subtract(r_ch.astype(np.int16), cv2.max(g_ch, b_ch).astype(np.int16)).astype(np.float32)

def capture_rate(alpha, th=32):
    rates = {}
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        angle = np.radians(angle_deg)
        c = 0; t = 0
        for dist in range(int(roi_w*0.1), int(roi_w*0.48), 3):
            px = int(center_x + dist*np.cos(angle))
            py = int(center_y + dist*np.sin(angle))
            if 0 <= px < roi_w and 0 <= py < roi_h:
                t += 1
                if alpha[py,px] > th: c += 1
        rates[angle_deg] = c/t*100 if t else 0
    return rates, np.mean(list(rates.values()))

def save(name, alpha_u8):
    rates, avg = capture_rate(alpha_u8, 64)
    fg32 = (alpha_u8>32).sum()/(roi_w*roi_h)*100
    fg64 = (alpha_u8>64).sum()/(roi_w*roi_h)*100
    fg128 = (alpha_u8>128).sum()/(roi_w*roi_h)*100
    fg200 = (alpha_u8>200).sum()/(roi_w*roi_h)*100
    print(f"  {name}: fg32={fg32:.1f}% fg64={fg64:.1f}% fg128={fg128:.1f}% fg200={fg200:.1f}% | cap_avg={avg:.0f}%")
    print(f"      8d: {[f'{k}={v:.0f}%' for k,v in rates.items()]}")
    full = np.zeros((h,w), dtype=np.uint8)
    full[y0:y0+roi_h, x0:x0+roi_w] = alpha_u8
    rgba = np.dstack([img, full])
    cv2.imwrite(str(Path(f'test_output/v2_{name}.png')), rgba)

# rembg alpha 和 R-G 融合的关键思想：
# - rembg alpha 在右半边(0-135°)很弱(0-33%)
# - R-G 增强 binarize 后背景太多
# 正确方案：rembg alpha 提供"基础信心"，R-G 通道对 rembg 信心低的区域做增强
print("=== Base channels ===")
save("A_rembg_alpha_raw", rembg_alpha)
save("B_distbg_s40", np.clip(dist_bg / 40 * 255, 0, 255).astype(np.uint8))
save("C_dark_x2", np.clip(alpha_dark_raw * 2, 0, 255).astype(np.uint8))
save("D_red_x6", np.clip(alpha_red_raw * 6, 0, 255).astype(np.uint8))

# 策略：rembg 原始 alpha 或 dist_bg/dark 做 MAX(soft 选择)
print("\n=== Strategy: MAX blend = 最强通道 ===")
# MAX 比加权求和更能保留边界
def MAX(channels):
    return np.max(np.stack(channels), axis=0)

rembg_f = rembg_alpha.astype(np.float32)
db30 = np.clip(dist_bg / 30 * 255, 0, 255)
db40 = np.clip(dist_bg / 40 * 255, 0, 255)
db50 = np.clip(dist_bg / 50 * 255, 0, 255)
dk2 = np.clip(alpha_dark_raw * 2, 0, 255)
dk3 = np.clip(alpha_dark_raw * 3, 0, 255)
rd6 = np.clip(alpha_red_raw * 6, 0, 255)
rd8 = np.clip(alpha_red_raw * 8, 0, 255)

combos = [
    ("E_max_rembg_db40_dk2", MAX([rembg_f, db40, dk2])),
    ("F_max_rembg_db40_dk3", MAX([rembg_f, db40, dk3])),
    ("G_max_rembg_db30_dk2_rd6", MAX([rembg_f, db30, dk2, rd6])),
    ("H_max_rembg_db40_dk2_rd6", MAX([rembg_f, db40, dk2, rd6])),
    ("I_max_rembg_db50_dk3_rd8", MAX([rembg_f, db50, dk3, rd8])),
    ("J_rembg_add_db30x0.5_dk2x0.5",
        rembg_f + 0.5*db30 + 0.5*dk2),
]

for name, f_ in combos:
    # Sigmoid 锐化
    f = np.clip(f_, 0, 255) / 255.0
    for sharp in [6, 10]:
        for mid in [0.30, 0.40, 0.50]:
            sharpened = 1.0 / (1.0 + np.exp(-sharp * (f - mid)))
            u8 = (sharpened * 255).clip(0, 255).astype(np.uint8)
            u8 = cv2.bitwise_and(u8, coarse_mask)
            r, avg64 = capture_rate(u8, 64)
            if avg64 >= 90:
                save(f"{name}_sh{sharp}_m{mid:.2f}", u8)
