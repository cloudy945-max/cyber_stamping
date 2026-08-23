"""调试：检查边框处像素的 alpha 值"""
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

# ====== 圆形约束 ======
Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - stamp_cx)**2 + (Y - stamp_cy)**2)
inside_circle = dist <= stamp_r

# ====== R-G 二值化 ======
rg_in_circle = np.where(inside_circle, r_minus_g, 0)
_, ink_binary = cv2.threshold(rg_in_circle, 12, 255, cv2.THRESH_BINARY)
k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
ink_closed = cv2.morphologyEx(ink_binary, cv2.MORPH_CLOSE, k5, iterations=3)
ink_clean = cv2.morphologyEx(ink_closed, cv2.MORPH_OPEN, k3, iterations=1)
ink_mask = ink_clean > 0

# ====== rembg ======
print("rembg...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
rembg_alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full((h, w), 255, dtype=np.uint8)

# ====== 调试：在边框区域取样本 ======
ring_mask = (dist >= stamp_r*0.90) & (dist <= stamp_r*0.98)
border_mask = ink_mask & ring_mask

print(f"\n边框墨水像素数: {border_mask.sum()}")
print(f"边框总像素数: {ring_mask.sum()}")
print(f"墨水覆盖率: {border_mask.sum()/ring_mask.sum()*100:.1f}%")

# 采样边框处的像素
if border_mask.sum() > 0:
    border_rg = r_minus_g[border_mask]
    border_rembg = rembg_alpha[border_mask]
    print(f"\n边框墨水像素 R-G 值: min={border_rg.min()}, max={border_rg.max()}, mean={border_rg.mean():.1f}")
    print(f"边框墨水像素 rembg alpha: min={border_rembg.min()}, max={border_rembg.max()}, mean={border_rembg.mean():.1f}")

# 在 8 方向检查
print(f"\n8 方向边框检查 (沿 0.88r-0.98r 扫描):")
for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
    a = np.radians(ang)
    rg_vals = []
    ink_present = 0
    total = 0
    for d in range(int(stamp_r*0.88), int(stamp_r*0.98), 2):
        px = int(stamp_cx + d*np.cos(a))
        py = int(stamp_cy + d*np.sin(a))
        if 0<=px<w and 0<=py<h:
            total += 1
            if ink_mask[py, px]:
                ink_present += 1
                rg_vals.append(r_minus_g[py, px])
    rg_str = f"R-G: min={min(rg_vals)},max={max(rg_vals)},mean={np.mean(rg_vals):.1f}" if rg_vals else "无墨水"
    print(f"  {ang:3d}°: 墨水覆盖 {ink_present}/{total} ({ink_present/total*100:.0f}%) {rg_str}")
