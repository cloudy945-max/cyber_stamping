"""内联整个 segment_stamp 的逻辑，确保用最新代码"""
import logging
import sys
import types
from pathlib import Path
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO)

BBox = Tuple[int, int, int, int]

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

src_path = Path(r'test_output/module_test/8181.jpg')
dst_path = Path(r'test_output/INLINE_segmented.png')

img_bgr = cv2.imread(str(src_path))
H, W = img_bgr.shape[:2]
roi = img_bgr.copy()
bx0, by0 = 0, 0
roi_h, roi_w = H, W

# ====== 圆形定位 ======
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
b_ch, g_ch, r_ch = cv2.split(roi)
r_minus_g = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(0, 255).astype(np.uint8)

_, r_binary = cv2.threshold(r_minus_g, 10, 255, cv2.THRESH_BINARY)
r_dilated = cv2.dilate(r_binary, k3, iterations=3)
contours, _ = cv2.findContours(r_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
contours = sorted(contours, key=cv2.contourArea, reverse=True)

stamp_cx, stamp_cy, stamp_r = None, None, None
for cnt in contours[:20]:
    area = cv2.contourArea(cnt)
    if area < 50000: continue
    x, y, cw, ch = cv2.boundingRect(cnt)
    aspect = cw / ch if ch > 0 else 0
    if 0.7 < aspect < 1.4:
        stamp_cx = x + cw // 2
        stamp_cy = y + ch // 2
        stamp_r = max(cw, ch) // 2
        break

if stamp_cx is None:
    stamp_cx, stamp_cy = roi_w // 2, roi_h // 2
    stamp_r = int(min(roi_w, roi_h) * 0.48)

Y_roi, X_roi = np.ogrid[:roi_h, :roi_w]
dist_roi = np.sqrt((X_roi - stamp_cx) ** 2 + (Y_roi - stamp_cy) ** 2)
inside_circle_roi = dist_roi <= stamp_r

# ====== rembg ======
print("rembg ROI...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
if arr.shape[2] == 4:
    rembg_alpha_roi = arr[:, :, 3]
else:
    rembg_alpha_roi = np.full((roi_h, roi_w), 255, dtype=np.uint8)

# ====== 分层 alpha ======
rg = r_minus_g.astype(np.int16)
final_alpha_roi = np.zeros((roi_h, roi_w), dtype=np.uint8)

strong_ink = (rg > 15) & inside_circle_roi
final_alpha_roi[strong_ink] = np.maximum(rembg_alpha_roi[strong_ink], 200)

medium_ink = (rg > 8) & (rg <= 15) & inside_circle_roi & (rembg_alpha_roi > 100)
final_alpha_roi[medium_ink] = np.maximum(rembg_alpha_roi[medium_ink], 150)

light_ink = (rg > 3) & (rg <= 8) & inside_circle_roi & (rembg_alpha_roi > 150)
final_alpha_roi[light_ink] = np.maximum(rembg_alpha_roi[light_ink], 100)

rembg_foreground = (rg <= 3) & inside_circle_roi & (rembg_alpha_roi > 200)
final_alpha_roi[rembg_foreground] = rembg_alpha_roi[rembg_foreground]

paper_zone = (dist_roi < stamp_r * 0.70) & inside_circle_roi
paper_suspect = paper_zone & (rg <= 5) & (final_alpha_roi > 0)
final_alpha_roi[paper_suspect] = 0

final_alpha_roi[~inside_circle_roi] = 0
final_alpha_roi = cv2.morphologyEx(final_alpha_roi, cv2.MORPH_CLOSE, k3, iterations=2)
final_alpha_roi = cv2.morphologyEx(final_alpha_roi, cv2.MORPH_OPEN, k3, iterations=1)
final_alpha_roi[~inside_circle_roi] = 0

full_alpha = np.zeros((H, W), dtype=np.uint8)
full_alpha[by0:by0 + roi_h, bx0:bx0 + roi_w] = final_alpha_roi

# ====== 颜色校正（关键步骤）======
output_bgr = img_bgr.copy()
ink_mask_full = full_alpha >= 32
strong_mask_full = full_alpha >= 128
print(f"墨水 alpha>=32: {ink_mask_full.sum()}, alpha>=128: {strong_mask_full.sum()}")

if ink_mask_full.sum() > 0 and strong_mask_full.sum() > 0:
    full_hsv = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2HSV)
    ink_pix = full_hsv[ink_mask_full].astype(np.float32)
    print(f"  校正前墨水 H 均值: {ink_pix[:, 0].mean():.1f}, S: {ink_pix[:, 1].mean():.1f}")

    h_target = 172.0
    h_new = np.full(ink_pix.shape[0], h_target, dtype=np.float32)

    strong_s_mean = full_hsv[strong_mask_full][:, 1].astype(np.float32).mean()
    s_orig = ink_pix[:, 1]
    s_target_base = 130.0
    s_new = s_target_base + (s_orig - strong_s_mean) * 1.5
    s_new = np.clip(s_new, 60, 255)
    v_new = ink_pix[:, 2]

    new_pix = np.zeros_like(ink_pix)
    new_pix[:, 0] = h_new
    new_pix[:, 1] = s_new
    new_pix[:, 2] = v_new

    new_pix_u8 = np.clip(new_pix, 0, 255).astype(np.uint8)
    print(f"  设置 H={h_target}, S mean={s_new.mean():.1f}, V mean={v_new.mean():.1f}")

    new_bgr = cv2.cvtColor(new_pix_u8.reshape(-1, 1, 3), cv2.COLOR_HSV2BGR).reshape(-1, 3)
    print(f"  转换后 BGR: B={new_bgr[:,0].mean():.1f}, G={new_bgr[:,1].mean():.1f}, R={new_bgr[:,2].mean():.1f}")

    output_bgr[ink_mask_full] = new_bgr

    low_alpha = full_alpha < 16
    output_bgr[low_alpha] = [0, 0, 0]

# 写回验证
final_hsv = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2HSV)
final_ink = final_hsv[ink_mask_full]
print(f"\n最终墨水像素写入后: H={final_ink[:,0].mean():.1f}, S={final_ink[:,1].mean():.1f}, V={final_ink[:,2].mean():.1f}")

# 保存
rgba = np.dstack([output_bgr, full_alpha])
dst_path.parent.mkdir(parents=True, exist_ok=True)
Image.fromarray(rgba, "RGBA").save(dst_path, "PNG")
print(f"\n保存: {dst_path}")

# 再读一次验证
check = cv2.imread(str(dst_path), cv2.IMREAD_UNCHANGED)
check_hsv = cv2.cvtColor(check[:,:,0:3], cv2.COLOR_BGR2HSV)
strong = check[:,:,3] >= 128
print(f"读取文件后墨水像素: H={check_hsv[strong][:,0].mean():.1f}, S={check_hsv[strong][:,1].mean():.1f}, V={check_hsv[strong][:,2].mean():.1f}")
