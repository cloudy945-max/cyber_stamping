"""测试颜色校正：墨水区域 HSV 色相从蓝紫色 → 红色。

思路：
1. 对 alpha > 32 的像素视为墨水
2. 转 HSV，只改 H/S，保留 V（亮度纹理）
3. H 映射：90 (蓝紫) → 0-15 (红)
4. S 提高：让红色更鲜艳
5. 转回 BGR 输出
"""
import sys, types
from pathlib import Path
import cv2
import numpy as np
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

src = Path(r'test_output/module_test/8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

# ====== 定位印章 ======
b_ch, g_ch, r_ch = cv2.split(img)
r_minus_g = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(0, 255).astype(np.uint8)

_, r_binary = cv2.threshold(r_minus_g, 10, 255, cv2.THRESH_BINARY)
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
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
    stamp_cx, stamp_cy = w // 2, int(h * 0.55)
    stamp_r = int(min(w, h) * 0.17)

print(f"印章: ({stamp_cx}, {stamp_cy}), r={stamp_r}")

Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - stamp_cx)**2 + (Y - stamp_cy)**2)
inside_circle = dist <= stamp_r

# ====== rembg ======
print("rembg...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
rembg_alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full((h, w), 255, dtype=np.uint8)

# ====== 分层 alpha（和正式代码一致）======
rg = r_minus_g.astype(np.int16)
final_alpha = np.zeros((h, w), dtype=np.uint8)

strong_ink = (rg > 15) & inside_circle
final_alpha[strong_ink] = np.maximum(rembg_alpha[strong_ink], 200)

medium_ink = (rg > 8) & (rg <= 15) & inside_circle & (rembg_alpha > 100)
final_alpha[medium_ink] = np.maximum(rembg_alpha[medium_ink], 150)

light_ink = (rg > 3) & (rg <= 8) & inside_circle & (rembg_alpha > 150)
final_alpha[light_ink] = np.maximum(rembg_alpha[light_ink], 100)

rembg_foreground = (rg <= 3) & inside_circle & (rembg_alpha > 200)
final_alpha[rembg_foreground] = rembg_alpha[rembg_foreground]

paper_zone = (dist < stamp_r * 0.70) & inside_circle
paper_suspect = paper_zone & (rg <= 5) & (final_alpha > 0)
final_alpha[paper_suspect] = 0

final_alpha[~inside_circle] = 0
final_alpha = cv2.morphologyEx(final_alpha, cv2.MORPH_CLOSE, k3, iterations=2)
final_alpha = cv2.morphologyEx(final_alpha, cv2.MORPH_OPEN, k3, iterations=1)
final_alpha[~inside_circle] = 0

# ====== 颜色校正（关键新增步骤）======
# 墨水像素：按 alpha 渐变校正（alpha 越高，校正越强）
# alpha < 16：完全不校正（保持原图颜色）
# alpha > 128：完全校正
# 中间区域：线性过渡

corrected_bgr = img.copy()
ink_mask_strong = final_alpha >= 128  # 确定墨水像素，强校正
ink_mask_medium = (final_alpha >= 32) & (final_alpha < 128)  # 中等墨水，半校正
ink_mask_any = final_alpha >= 32  # 至少有墨水的像素

if ink_mask_any.sum() > 0:
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 对强墨水像素，做 HSV 映射
    for mask_strong_factor, pixels_mask in [(1.0, ink_mask_strong), (0.5, ink_mask_medium)]:
        count = pixels_mask.sum()
        if count == 0:
            continue
        
        pix_hsv = img_hsv[pixels_mask].astype(np.float32)
        
        # H 映射：蓝紫(H~90-110) → 红(H~172)
        h_orig = pix_hsv[:, 0]
        h_target_mean = 172.0
        h_new = h_target_mean + (h_orig - 97.5) * 0.3 * mask_strong_factor
        # 如果是中等强度，减少偏移
        if mask_strong_factor < 1.0:
            # 中等：一半用新颜色，一半用旧颜色
            h_new = (h_orig * (1 - mask_strong_factor) + h_new * mask_strong_factor)
        h_new = np.clip(h_new, 0, 179)
        
        # S 增强
        s_orig = pix_hsv[:, 1]
        s_new = np.clip(s_orig * (1 + mask_strong_factor * 0.8) + mask_strong_factor * 40, 60, 255)
        if mask_strong_factor < 1.0:
            s_new = s_orig * (1 - mask_strong_factor) + s_new * mask_strong_factor
        
        # V 保持
        v_new = pix_hsv[:, 2]
        
        pix_new = np.zeros_like(pix_hsv)
        pix_new[:, 0] = h_new
        pix_new[:, 1] = s_new
        pix_new[:, 2] = v_new
        
        pix_new_uint8 = np.clip(pix_new, 0, 255).astype(np.uint8)
        pix_bgr = cv2.cvtColor(pix_new_uint8.reshape(-1, 1, 3), cv2.COLOR_HSV2BGR).reshape(-1, 3)
        corrected_bgr[pixels_mask] = pix_bgr
    
    # 统计（对强墨水）
    cor_hsv = cv2.cvtColor(corrected_bgr, cv2.COLOR_BGR2HSV)
    if ink_mask_strong.sum() > 0:
        cor_ink = cor_hsv[ink_mask_strong]
        print(f"\n墨水强校正后 HSV 统计:")
        print(f"  H: mean={cor_ink[:,0].mean():.1f}")
        print(f"  S: mean={cor_ink[:,1].mean():.1f}")
        print(f"  V: mean={cor_ink[:,2].mean():.1f}")

# ====== 输出 RGBA PNG ======
rgba = np.dstack([corrected_bgr, final_alpha])
cv2.imwrite("test_output/FINAL_color_corrected.png", rgba)
print(f"\n输出: test_output/FINAL_color_corrected.png")

# 同时保存"不校正颜色"的版本做对比
rgba_orig = np.dstack([img, final_alpha])
cv2.imwrite("test_output/FINAL_orig_color.png", rgba_orig)
print(f"对比（原始颜色）: test_output/FINAL_orig_color.png")
