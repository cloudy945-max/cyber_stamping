"""测试：颜色校正后清理 alpha 低的区域颜色，避免透明区显示污染"""
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

# ====== 分层 alpha ======
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

# ====== 颜色校正 ======
# 先把输出颜色 = 原图拷贝
corrected_bgr = img.copy()
ink_mask = final_alpha >= 32

if ink_mask.sum() > 0:
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    pix_hsv = img_hsv[ink_mask].astype(np.float32)

    # H 映射：蓝紫 → 红（H 目标均值 172），保留相对差异
    h_orig = pix_hsv[:, 0]
    h_mean_orig = h_orig.mean()
    h_new = 172.0 + (h_orig - h_mean_orig) * 0.3
    h_new = np.clip(h_new, 0, 179)

    # S 增强：提高饱和度（红色更鲜艳）
    s_orig = pix_hsv[:, 1]
    s_new = np.clip(s_orig * 1.8 + 40, 60, 255)

    # V 保持
    v_new = pix_hsv[:, 2]

    pix_new = np.zeros_like(pix_hsv)
    pix_new[:, 0] = h_new
    pix_new[:, 1] = s_new
    pix_new[:, 2] = v_new

    pix_new_uint8 = np.clip(pix_new, 0, 255).astype(np.uint8)
    pix_bgr = cv2.cvtColor(pix_new_uint8.reshape(-1, 1, 3), cv2.COLOR_HSV2BGR).reshape(-1, 3)
    corrected_bgr[ink_mask] = pix_bgr

# ====== 关键：清理 alpha < 16 的区域颜色（避免透明区污染）======
# 策略：
# - alpha = 0 的像素：颜色设为黑色（0,0,0），这样无论预览器如何，都不会透出
# - 0 < alpha < 16 的像素：颜色 = 墨水校正后颜色 × alpha + 黑色 × (1-alpha)，但实际上
#   这些像素本身就很透明，保持原样或按 alpha 混合到黑色都可以
# 简单做法：alpha < 16 的像素颜色全部设为黑色

low_alpha_mask = final_alpha < 16
corrected_bgr[low_alpha_mask] = [0, 0, 0]

# ====== 输出 ======
rgba = np.dstack([corrected_bgr, final_alpha])
cv2.imwrite("test_output/FINAL_v2_color_ok.png", rgba)

# 统计墨水颜色
cor_hsv = cv2.cvtColor(corrected_bgr, cv2.COLOR_BGR2HSV)
strong = final_alpha >= 128
if strong.sum() > 0:
    h, s, v = cor_hsv[strong][:, 0].mean(), cor_hsv[strong][:, 1].mean(), cor_hsv[strong][:, 2].mean()
    print(f"墨水强像素 HSV: H={h:.0f} (红), S={s:.0f} (饱和), V={v:.0f} (亮)")

print(f"输出: test_output/FINAL_v2_color_ok.png")
