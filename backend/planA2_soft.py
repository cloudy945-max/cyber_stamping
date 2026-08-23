"""方案 A-2：圆形约束 + R-G 软 alpha（不是二值化）。

关键改进：不用二值化，直接用 R-G 通道的值作为 alpha，
这样印章墨迹部分 alpha 高，纸张空白部分 alpha 低。
"""
import cv2
import numpy as np
from pathlib import Path
from scipy import ndimage

src = Path(r'test_output/module_test/8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

# ====== 步骤 1：定位印章 ======
b_ch, g_ch, r_ch = cv2.split(img)
r_minus_g = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(0, 255).astype(np.uint8)

# 找轮廓
_, r_binary = cv2.threshold(r_minus_g, 10, 255, cv2.THRESH_BINARY)
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
r_dilated = cv2.dilate(r_binary, kernel, iterations=3)
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

print(f"印章定位: ({stamp_cx}, {stamp_cy}), r={stamp_r}")

# ====== 步骤 2：圆形区域内用 R-G 软 alpha ======
# 圆形蒙版
Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - stamp_cx)**2 + (Y - stamp_cy)**2)
inside_circle = dist <= stamp_r
outside_circle = dist > stamp_r

# 在圆形区域内：
# 印章墨水特征：R-G > 某个阈值
# 但直接用 R-G 值作为 alpha（软 alpha）
# 需要归一化：R-G 值越大 → alpha 越高

# 提取圆形内的 R-G 值
rg_inside = r_minus_g.copy()
rg_inside[~inside_circle] = 0

# 归一化：把 R-G 值映射到 alpha
# 圆形内 R-G 的范围
print(f"\n圆形内 R-G 统计:")
rg_valid = rg_inside[inside_circle]
print(f"  min={rg_valid.min()}, max={rg_valid.max()}, mean={rg_valid.mean():.1f}")
print(f"  R-G > 5: {(rg_valid > 5).sum()} ({(rg_valid > 5).sum()/len(rg_valid)*100:.1f}%)")
print(f"  R-G > 10: {(rg_valid > 10).sum()} ({(rg_valid > 10).sum()/len(rg_valid)*100:.1f}%)")
print(f"  R-G > 20: {(rg_valid > 20).sum()} ({(rg_valid > 20).sum()/len(rg_valid)*100:.1f}%)")
print(f"  R-G > 50: {(rg_valid > 50).sum()} ({(rg_valid > 50).sum()/len(rg_valid)*100:.1f}%)")

# 方案 1：直接用 R-G * 倍数作为 alpha（带圆形约束）
# 但圆形内还有海报背景文字等干扰
alpha_rg = np.clip(r_minus_g.astype(np.float32) * 3, 0, 255).astype(np.uint8)
alpha_rg[outside_circle] = 0

# 方案 2：在圆形内做自适应阈值的软 alpha
# 用 CLAHE + 局部统计
roi_x0, roi_y0 = max(0, stamp_cx - stamp_r), max(0, stamp_cy - stamp_r)
roi_x1, roi_y1 = min(w, stamp_cx + stamp_r), min(h, stamp_cy + stamp_r)

roi_rg = r_minus_g[roi_y0:roi_y1, roi_x0:roi_x1]
roi_circle = inside_circle[roi_y0:roi_y1, roi_x0:roi_x1]

# CLAHE 增强
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced_rg = clahe.apply(roi_rg)

# 在 ROI 内做：高于局部均值 + C 的为高 alpha
# 使用简单方法：归一化
roi_rg_float = roi_rg.astype(np.float32)
# 在圆形内的最小值作为基准
min_in_circle = roi_rg[roi_circle].min() if roi_circle.sum() > 0 else 0
max_in_circle = roi_rg[roi_circle].max() if roi_circle.sum() > 0 else 255
print(f"\n圆形内 R-G 范围: {min_in_circle} - {max_in_circle}")

# 归一化到 0-255
if max_in_circle > min_in_circle:
    alpha_normalized = np.clip((roi_rg_float - min_in_circle) / (max_in_circle - min_in_circle) * 255, 0, 255).astype(np.uint8)
else:
    alpha_normalized = np.zeros_like(roi_rg)

# 限制在圆形内
alpha_normalized[~roi_circle] = 0

# 方案 3：在圆形内，只有 "R > G + 阈值" 的像素才保留
# 并且 alpha 强度 = (R-G - threshold) * multiplier
threshold = 8  # R-G 差值阈值
alpha_strict = np.zeros_like(roi_rg)
mask_above = roi_rg > threshold
alpha_strict[mask_above] = np.clip((roi_rg[mask_above] - threshold) * 4, 0, 255).astype(np.uint8)
alpha_strict[~roi_circle] = 0

# ====== 步骤 3：比较三种方案 ======
def save_result(name, alpha, bgr_img):
    full_alpha = np.zeros((h, w), dtype=np.uint8)
    full_alpha[roi_y0:roi_y1, roi_x0:roi_x1] = alpha
    rgba = np.dstack([bgr_img, full_alpha])
    path = f"test_output/A2_{name}.png"
    cv2.imwrite(path, rgba)
    # 统计
    print(f"\n  {name}:")
    for th in [32, 64, 128, 200]:
        a_roi = full_alpha[roi_y0:roi_y1, roi_x0:roi_x1]
        c = (a_roi[roi_circle] > th).sum()
        t = roi_circle.sum()
        print(f"    alpha>{th}: {c}/{t} ({c/t*100:.1f}%)")
    return full_alpha

print("\n===== 三种方案对比 =====")

# 方案 1
save_result("rg_times3", alpha_rg[roi_y0:roi_y1, roi_x0:roi_x1], img)

# 方案 2
save_result("normalized", alpha_normalized, img)

# 方案 3
save_result("strict_t8_x4", alpha_strict, img)

# 额外：方案 3 + 形态学清理
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
alpha_strict_clean = cv2.morphologyEx(alpha_strict, cv2.MORPH_CLOSE, k3, iterations=2)
alpha_strict_clean = cv2.morphologyEx(alpha_strict_clean, cv2.MORPH_OPEN, k3, iterations=1)
save_result("strict_t8_x4_clean", alpha_strict_clean, img)

# 方案 3 + 更低阈值
for thr in [3, 5, 10, 15]:
    a = np.zeros_like(roi_rg)
    m = roi_rg > thr
    a[m] = np.clip((roi_rg[m] - thr) * 4, 0, 255).astype(np.uint8)
    a[~roi_circle] = 0
    save_result(f"strict_t{thr}_x4", a, img)

# 查看方案 3 t=5 的效果
best_path = "test_output/A2_strict_t5_x4.png"
print(f"\n最佳方案预览: {best_path}")
