"""最终方案 VII：先找墨水区域（R-G 二值化 + 形态学），再在墨水区域内做软 alpha。

关键：
1. 先用 R-G 二值化确定"哪些像素属于印章墨水"
2. 墨水区域内：用 rembg alpha 和 R-G 值计算软 alpha
3. 非墨水区域：alpha = 0
4. 圆形外：alpha = 0
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

# ====== 步骤 1：R-G 二值化找墨水 ======
# 在圆形内，用 R-G 阈值找墨水区域
rg_in_circle = np.where(inside_circle, r_minus_g, 0)

# 高阈值：只保留强墨水（R-G > 15）
_, ink_binary = cv2.threshold(rg_in_circle, 12, 255, cv2.THRESH_BINARY)

# 形态学处理
# 闭运算：连接断裂的笔画
k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
ink_closed = cv2.morphologyEx(ink_binary, cv2.MORPH_CLOSE, k5, iterations=3)
# 开运算：去除小噪点
ink_clean = cv2.morphologyEx(ink_closed, cv2.MORPH_OPEN, k3, iterations=1)

# 墨水掩码
ink_mask = ink_clean > 0
print(f"墨水区域占圆形: {ink_mask.sum()/inside_circle.sum()*100:.1f}%")

# ====== 步骤 2：rembg alpha ======
print("rembg 全图处理...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
rembg_alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full((h, w), 255, dtype=np.uint8)

# ====== 步骤 3：在墨水区域内计算软 alpha ======
# 墨水区域的 alpha = max(rembg_alpha, R-G 增强值)
# 但边框区域（圆形边缘）强制高 alpha

rg_enhanced = np.clip(r_minus_g.astype(np.float32) * 3, 0, 255).astype(np.uint8)
soft_alpha = np.maximum(rembg_alpha.astype(np.uint16), rg_enhanced.astype(np.uint16))
soft_alpha = np.clip(soft_alpha, 0, 255).astype(np.uint8)

# 边框区域：距圆心 0.88-0.98r 的环形
ring_zone = (dist >= stamp_r*0.88) & (dist <= stamp_r*0.98)

# 只保留墨水区域的 alpha
final_alpha = np.zeros((h, w), dtype=np.uint8)
final_alpha[ink_mask] = soft_alpha[ink_mask]

# 边框区域内的墨水像素：alpha 至少为 220
edge_pixels = ink_mask & ring_zone & (final_alpha < 220)
final_alpha[edge_pixels] = 220

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
cv2.imwrite("test_output/FINAL_v7.png", rgba)
print(f"\n输出: test_output/FINAL_v7.png")

# 额外：保存墨水掩码预览
ink_preview = np.zeros((h, w), dtype=np.uint8)
ink_preview[ink_mask] = 255
cv2.imwrite("test_output/ink_mask_v7.png", ink_preview)
