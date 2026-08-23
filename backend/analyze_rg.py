"""统计纸张和墨水的 R-G 值分布，确定区分阈值"""
import cv2
import numpy as np
from pathlib import Path

src = Path(r'test_output/module_test/8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

b_ch, g_ch, r_ch = cv2.split(img)
r_minus_g = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(0, 255).astype(np.uint8)

# 定位印章
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

Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - stamp_cx)**2 + (Y - stamp_cy)**2)
inside_circle = dist <= stamp_r

# 印章内部（排除边框和文字区域）：中心区域
inner_ring = (dist <= stamp_r * 0.30)
# 印章外部（远离印章的纸张）：右上角区域
paper_region = (X > stamp_cx + stamp_r * 1.5) & (Y < stamp_cy - stamp_r * 0.5)

print(f"印章内部中心区域像素数: {inner_ring.sum()}")
print(f"印章外部纸张区域像素数: {paper_region.sum()}")

# 统计
rg_inner = r_minus_g[inner_ring]
rg_paper = r_minus_g[paper_region]

print(f"\n印章内部 R-G:")
print(f"  min={rg_inner.min()}, max={rg_inner.max()}")
print(f"  mean={rg_inner.mean():.1f}, median={np.median(rg_inner):.1f}")
print(f"  std={rg_inner.std():.1f}")

print(f"\n外部纸张 R-G:")
print(f"  min={rg_paper.min()}, max={rg_paper.max()}")
print(f"  mean={rg_paper.mean():.1f}, median={np.median(rg_paper):.1f}")
print(f"  std={rg_paper.std():.1f}")

# 直方图
print(f"\nR-G 直方图 (0-100):")
hist, _ = np.histogram(r_minus_g[inside_circle], bins=50, range=(0, 100))
for i, count in enumerate(hist):
    bar = '#' * (count // 500)
    print(f"  {i*2:3d}-{(i+1)*2:3d}: {count:7d} {bar}")

# 分析：纸张 vs 墨水的 R-G 分布
# 在圆形内，低 R-G 值（0-10）应该是纸张
# 高 R-G 值（>15）应该是墨水
print(f"\n圆形内 R-G 分布:")
for th in [3, 5, 8, 10, 12, 15, 20, 30, 50]:
    below = (r_minus_g[inside_circle] <= th).sum()
    above = (r_minus_g[inside_circle] > th).sum()
    print(f"  <= {th:2d}: {below:7d} ({below/inside_circle.sum()*100:5.1f}%)")
    print(f"  >  {th:2d}: {above:7d} ({above/inside_circle.sum()*100:5.1f}%)")
