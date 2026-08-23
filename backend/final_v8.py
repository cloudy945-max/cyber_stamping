"""最终方案 VIII：Canny 边框检测 + R-G 低阈值墨水提取。

1. Canny 边缘检测找印章边框（圆形边界）
2. R-G 低阈值（5）二值化提取墨水
3. 合并两者
4. 圆形约束 + 形态学清理
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

# ====== 步骤 1：Canny 边缘检测找边框 ======
# 在圆形内做 Canny
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
canny = cv2.Canny(gray, 30, 100)  # 低阈值捕获更多边缘
canny[~inside_circle] = 0

# 膨胀边缘
k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
edge_dilated = cv2.dilate(canny, k5, iterations=2)
edge_filled = cv2.morphologyEx(edge_dilated, cv2.MORPH_CLOSE, k5, iterations=5)

# ====== 步骤 2：R-G 低阈值墨水 ======
rg_in_circle = np.where(inside_circle, r_minus_g, 0)
_, ink_low = cv2.threshold(rg_in_circle, 5, 255, cv2.THRESH_BINARY)
ink_low_closed = cv2.morphologyEx(ink_low, cv2.MORPH_CLOSE, k5, iterations=3)
ink_low_clean = cv2.morphologyEx(ink_low_closed, cv2.MORPH_OPEN, k3, iterations=1)

# ====== 步骤 3：合并两种墨水检测 ======
# Canny 边缘（补全边框）+ R-G 低阈值（墨水主体）
combined_ink = cv2.bitwise_or(edge_filled, ink_low_clean)
ink_mask = combined_ink > 0

# 限制在圆形内
ink_mask = ink_mask & inside_circle

print(f"墨水区域占圆形: {ink_mask.sum()/inside_circle.sum()*100:.1f}%")

# ====== 步骤 4：rembg alpha ======
print("rembg 全图处理...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
rembg_alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full((h, w), 255, dtype=np.uint8)

# ====== 步骤 5：在墨水区域内计算软 alpha ======
rg_enhanced = np.clip(r_minus_g.astype(np.float32) * 3, 0, 255).astype(np.uint8)
soft_alpha = np.maximum(rembg_alpha.astype(np.uint16), rg_enhanced.astype(np.uint16))
soft_alpha = np.clip(soft_alpha, 0, 255).astype(np.uint8)

final_alpha = np.zeros((h, w), dtype=np.uint8)
final_alpha[ink_mask] = soft_alpha[ink_mask]

# 边框区域强制高 alpha
ring_zone = (dist >= stamp_r*0.88) & (dist <= stamp_r*0.98)
edge_pixels = ink_mask & ring_zone
final_alpha[edge_pixels] = np.maximum(final_alpha[edge_pixels], 220)

# 圆形外强制 0
final_alpha[~inside_circle] = 0

# ====== 验证 ======
print("\n===== 测试验证 =====")

t1 = final_alpha[~inside_circle].max()
print(f"T1 (圆外=0): {'✅' if t1 == 0 else '❌'} max={t1}")

ring_mask = (dist >= stamp_r*0.90) & (dist <= stamp_r*0.98)
ring_alpha = final_alpha[ring_mask]
t2 = (ring_alpha > 200).sum() / ring_alpha.size * 100 if ring_alpha.size > 0 else 0
print(f"T2 (边框>200): {'✅' if t2 >= 70 else '❌'} {t2:.1f}%")

text_mask = (dist >= stamp_r*0.65) & (dist <= stamp_r*0.85)
text_alpha = final_alpha[text_mask]
t3 = text_alpha.mean() if text_alpha.size > 0 else 0
print(f"T3 (文字均值>80): {'✅' if t3 >= 80 else '❌'} mean={t3:.1f}")

inner_mask = dist <= stamp_r*0.50
inner_alpha = final_alpha[inner_mask]
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
            if final_alpha[py,px] > 32: c += 1
    rate = c/t*100 if t else 0
    p = rate >= 95
    all_pass = all_pass and p
    print(f"  {ang:3d}°: {rate:.0f}% {'✅' if p else '❌'}")
print(f"  T5: {'✅' if all_pass else '❌'}")

rgba = np.dstack([img, final_alpha])
cv2.imwrite("test_output/FINAL_v8.png", rgba)
print(f"\n输出: test_output/FINAL_v8.png")

# 保存墨水掩码预览
ink_preview = np.zeros((h, w), dtype=np.uint8)
ink_preview[ink_mask] = 255
cv2.imwrite("test_output/ink_mask_v8.png", ink_preview)
