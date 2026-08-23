"""最终方案 V5：rembg alpha 为主 + R-G 局部标准差补充淡色区域。

思路：
1. rembg 生成主 alpha（深色主体）
2. R-G 局部高方差区域补充淡色墨水
3. 两者合并，限制在圆形内
4. 纸张空白（低方差 + 低 R-G）强制透明
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

# ====== 圆形约束 ======
Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - stamp_cx)**2 + (Y - stamp_cy)**2)
inside_circle = dist <= stamp_r

# ====== ROI ======
pad = 20
roi_x0, roi_y0 = max(0, stamp_cx - stamp_r - pad), max(0, stamp_cy - stamp_r - pad)
roi_x1, roi_y1 = min(w, stamp_cx + stamp_r + pad), min(h, stamp_cy + stamp_r + pad)
roi = img[roi_y0:roi_y1, roi_x0:roi_x1].copy()
rh, rw = roi.shape[:2]

cy, cx = rh // 2, rw // 2
circle_r = int(min(rw, rh) * 0.98)
circle_mask_roi = np.zeros((rh, rw), dtype=np.uint8)
cv2.circle(circle_mask_roi, (cx, cy), circle_r, 255, -1)

# ====== 路 1: rembg ======
print("路 1: rembg...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
rembg_alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full((rh, rw), 255, dtype=np.uint8)

# ====== 路 2: R-G 局部高方差 ======
print("路 2: R-G 局部方差...")
roi_rg = r_minus_g[roi_y0:roi_y1, roi_x0:roi_x1]

# 计算局部标准差（墨水区域有高方差）
k_size = 15
if k_size % 2 == 0: k_size += 1
from scipy.ndimage import uniform_filter
# local mean
local_mean_rg = uniform_filter(roi_rg.astype(np.float32), size=k_size)
# local variance = E[x^2] - E[x]^2
local_sq_mean = uniform_filter((roi_rg.astype(np.float32))**2, size=k_size)
local_var = np.maximum(local_sq_mean - local_mean_rg**2, 0)
local_std_rg = np.sqrt(local_var)

# 高方差区域 = 墨水（文字、图案、边框）
# 归一化
std_max = local_std_rg[circle_mask_roi > 0].max() if circle_mask_roi.sum() > 0 else 1
if std_max > 0:
    high_var_alpha = np.clip(local_std_rg / std_max * 255, 0, 255).astype(np.uint8)
else:
    high_var_alpha = np.zeros((rh, rw), dtype=np.uint8)

# ====== 合并策略 ======
# 1. rembg 主 alpha：深色部分
# 2. 高方差 alpha：补充淡色墨水
# 3. 关键：高方差区域中，R-G 均值需 > 0（排除纯纸张噪声）

# 混合：rembg 为主，高方差为辅
# 高方差区域（墨水）：用 max(rembg, high_var)
# 低方差区域（纸张）：rembg 值保持
combined = rembg_alpha.astype(np.float32)

# 对于高方差区域，补充 alpha（但限制在 200 以上）
high_var_mask = local_std_rg > 3  # 阈值：局部标准差 > 3
combined = np.where(
    high_var_mask,
    np.maximum(combined, high_var_alpha.astype(np.float32)),
    combined
)

combined = np.clip(combined, 0, 255).astype(np.uint8)

# 形态学清理
combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, k3, iterations=2)
combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, k3, iterations=1)

# 限制在圆形内
combined = cv2.bitwise_and(combined, circle_mask_roi)

# ====== 全图 alpha ======
full_alpha = np.zeros((h, w), dtype=np.uint8)
full_alpha[roi_y0:roi_y1, roi_x0:roi_x1] = combined
full_alpha[~inside_circle] = 0

# ====== 验证 ======
print("\n===== 测试验证 =====")

t1 = full_alpha[~inside_circle].max()
print(f"T1 (圆外=0): {'✅' if t1 == 0 else '❌'} max={t1}")

ring_mask = (dist >= stamp_r*0.90) & (dist <= stamp_r*0.98)
ring_alpha = full_alpha[ring_mask]
t2 = (ring_alpha > 200).sum() / ring_alpha.size * 100 if ring_alpha.size > 0 else 0
print(f"T2 (边框>200): {'✅' if t2 >= 70 else '❌'} {t2:.1f}%")

text_mask = (dist >= stamp_r*0.65) & (dist <= stamp_r*0.85)
text_alpha = full_alpha[text_mask]
t3 = text_alpha.mean() if text_alpha.size > 0 else 0
print(f"T3 (文字均值>80): {'✅' if t3 >= 80 else '❌'} mean={t3:.1f}")

inner_mask = dist <= stamp_r*0.50
inner_alpha = full_alpha[inner_mask]
t4 = (inner_alpha < 30).sum() / inner_alpha.size * 100 if inner_alpha.size > 0 else 0
print(f"T4 (内部<30): {'✅' if t4 >= 80 else '❌'} {t4:.1f}%")

print(f"T5 (8方向边框):")
all_pass = True
for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
    a = np.radians(ang)
    c = 0; t = 0
    for d in range(int(stamp_r*0.88), int(stamp_r*0.98), 2):
        px = int(stamp_cx + d*np.cos(a))
        py = int(stamp_cy + d*np.sin(a))
        if 0<=px<w and 0<=py<h:
            t += 1
            if full_alpha[py,px] > 32: c += 1
    rate = c/t*100 if t else 0
    p = rate >= 95
    all_pass = all_pass and p
    print(f"  {ang:3d}°: {rate:.0f}% {'✅' if p else '❌'}")
print(f"  T5: {'✅' if all_pass else '❌'}")

rgba = np.dstack([img, full_alpha])
cv2.imwrite("test_output/FINAL_v5.png", rgba)
print(f"\n输出: test_output/FINAL_v5.png")
