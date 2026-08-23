"""最终方案 XI：rembg + R-G 分层 alpha，保留原始颜色。

改进：
1. 只用 R-G 通道计算 alpha（不修改颜色）
2. 输出颜色 = 原图颜色（保持红/蓝紫原色）
3. 分层 R-G 阈值确定 alpha
4. 圆形外透明
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

# ====== rembg 全图处理 ======
print("rembg 全图处理...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
rembg_alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full((h, w), 255, dtype=np.uint8)

# ====== 分层 alpha ======
rg = r_minus_g.astype(np.int16)
final_alpha = np.zeros((h, w), dtype=np.uint8)

# 策略：
# 1. R-G > 8 AND inside_circle → 墨水（至少 alpha = 200）
# 2. R-G > 3 AND rembg_alpha > 128 AND inside_circle → 墨水
# 3. 其他 → alpha = 0

# 第一档：强墨水（R-G > 15）
strong_ink = (rg > 15) & inside_circle
final_alpha[strong_ink] = np.maximum(rembg_alpha[strong_ink], 200)

# 第二档：中等墨水（8 < R-G <= 15，且 rembg 认为是前景）
medium_ink = (rg > 8) & (rg <= 15) & inside_circle & (rembg_alpha > 100)
final_alpha[medium_ink] = np.maximum(rembg_alpha[medium_ink], 150)

# 第三档：淡色墨水（3 < R-G <= 8，且 rembg 认为是前景）
light_ink = (rg > 3) & (rg <= 8) & inside_circle & (rembg_alpha > 150)
final_alpha[light_ink] = np.maximum(rembg_alpha[light_ink], 100)

# 第四档：rembg 确定前景（R-G <= 3 但 rembg alpha 高）
# 这可能是印章内部的深色图案
rembg_foreground = (rg <= 3) & inside_circle & (rembg_alpha > 200)
final_alpha[rembg_foreground] = rembg_alpha[rembg_foreground]

# ====== 纸张抑制：去除圆形内的纸张空白 ======
# 原则：印章中心区域（dist < 0.7r）如果 R-G 值低，说明是纸张
# 边框和文字区域（0.7r-1.0r）即使 R-G 低也保留
paper_zone = (dist < stamp_r * 0.70) & inside_circle
paper_suspect = paper_zone & (rg <= 5) & (final_alpha > 0)
final_alpha[paper_suspect] = 0

# ====== 形态学清理 ======
final_alpha = cv2.morphologyEx(final_alpha, cv2.MORPH_CLOSE, k3, iterations=2)
final_alpha = cv2.morphologyEx(final_alpha, cv2.MORPH_OPEN, k3, iterations=1)
final_alpha[~inside_circle] = 0

# ====== 输出：保留原始颜色 ======
# 颜色来自原图，alpha 来自计算结果
rgba = np.dstack([img, final_alpha])

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

cv2.imwrite("test_output/FINAL_v11.png", rgba)
print(f"\n输出: test_output/FINAL_v11.png")

# 统计
print(f"\n圆内 alpha 分布:")
ia = final_alpha[inside_circle]
print(f"  alpha=0: {(ia==0).sum()}/{ia.size} ({(ia==0).sum()/ia.size*100:.1f}%)")
print(f"  alpha<32: {(ia<32).sum()}/{ia.size} ({(ia<32).sum()/ia.size*100:.1f}%)")
print(f"  alpha>=128: {(ia>=128).sum()}/{ia.size} ({(ia>=128).sum()/ia.size*100:.1f}%)")
