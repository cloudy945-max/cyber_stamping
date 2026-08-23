"""方案：R-G 分段映射 + 圆形约束 + 形态学清理。

分段映射：
  R-G > 50  → alpha = 255 (强墨水)
  20 < R-G ≤ 50 → alpha 线性映射 100-255
  10 < R-G ≤ 20 → alpha 线性映射 20-100
  R-G ≤ 10 → alpha = 0 (纸张背景)
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

# ====== 步骤 2：圆形约束 ======
Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - stamp_cx)**2 + (Y - stamp_cy)**2)
inside_circle = dist <= stamp_r

# ====== 步骤 3：分段映射 ======
def segment_map(rg, thr_low, thr_mid, thr_high):
    """R-G 值映射到 alpha。"""
    alpha = np.zeros_like(rg, dtype=np.float32)
    rgf = rg.astype(np.float32)
    
    # 低于低阈值 → 0
    alpha[rgf <= thr_low] = 0
    # 低→中 线性映射
    mask_low_mid = (rgf > thr_low) & (rgf <= thr_mid)
    if mask_low_mid.sum() > 0:
        alpha[mask_low_mid] = (rgf[mask_low_mid] - thr_low) / (thr_mid - thr_low) * 100
    # 中→高 线性映射
    mask_mid_high = (rgf > thr_mid) & (rgf <= thr_high)
    if mask_mid_high.sum() > 0:
        alpha[mask_mid_high] = 100 + (rgf[mask_mid_high] - thr_mid) / (thr_high - thr_mid) * 155
    # 高于高阈值 → 255
    alpha[rgf > thr_high] = 255
    
    return np.clip(alpha, 0, 255).astype(np.uint8)

# 尝试不同阈值组合
best_result = None
best_score = -1

for thr_low in [5, 8, 10, 12, 15]:
    for thr_mid in [15, 20, 25, 30, 40]:
        for thr_high in [40, 50, 60, 80]:
            if thr_low >= thr_mid or thr_mid >= thr_high:
                continue
            
            alpha_full = segment_map(r_minus_g, thr_low, thr_mid, thr_high)
            alpha_full[~inside_circle] = 0
            
            # 形态学清理
            alpha_closed = cv2.morphologyEx(alpha_full, cv2.MORPH_CLOSE, k3, iterations=2)
            alpha_clean = cv2.morphologyEx(alpha_closed, cv2.MORPH_OPEN, k3, iterations=1)
            alpha_clean[~inside_circle] = 0
            
            # 评分
            # T5: 8 方向边框捕获率
            ring_inner = stamp_r * 0.90
            ring_outer = stamp_r * 0.98
            ring_mask = (dist >= ring_inner) & (dist <= ring_outer)
            
            total_cap = 0
            for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
                a = np.radians(ang)
                c = 0; t = 0
                for d in range(int(stamp_r * 0.88), int(stamp_r * 0.98), 2):
                    px = int(stamp_cx + d * np.cos(a))
                    py = int(stamp_cy + d * np.sin(a))
                    if 0 <= px < w and 0 <= py < h:
                        t += 1
                        if alpha_clean[py, px] > 64: c += 1
                total_cap += (c / t * 100 if t else 0)
            avg_cap = total_cap / 8
            
            # T4: 内部空白透明度
            inner_mask = dist <= stamp_r * 0.50
            inner_alpha = alpha_clean[inner_mask]
            transparency = (inner_alpha < 30).sum() / inner_alpha.size * 100 if inner_alpha.size > 0 else 0
            
            # T2: 边框强度
            ring_alpha = alpha_clean[ring_mask]
            ring_strength = (ring_alpha > 200).sum() / ring_alpha.size * 100 if ring_alpha.size > 0 else 0
            
            # 综合评分
            score = avg_cap * 2 + transparency + ring_strength * 0.5
            
            if score > best_score:
                best_score = score
                best_result = (thr_low, thr_mid, thr_high, avg_cap, transparency, ring_strength, alpha_clean.copy())

print(f"\n最佳参数: thr_low={best_result[0]}, thr_mid={best_result[1]}, thr_high={best_result[2]}")
print(f"  avg_cap8={best_result[3]:.0f}%, transparency={best_result[4]:.1f}%, ring_strength={best_result[5]:.1f}%")

# ====== 步骤 4：保存最佳结果 ======
best_alpha = best_result[6]
rgba = np.dstack([img, best_alpha])
cv2.imwrite("test_output/FINAL_stamp_v2.png", rgba)

# ====== 步骤 5：完整验证 ======
full_alpha = best_alpha
print("\n===== 完整测试验证 =====")

# T1
t1_max = full_alpha[~inside_circle].max()
print(f"T1 (圆外=0): {'✅' if t1_max == 0 else '❌'} max={t1_max}")

# T2
ring_mask = (dist >= stamp_r*0.90) & (dist <= stamp_r*0.98)
ring_alpha = full_alpha[ring_mask]
t2 = (ring_alpha > 200).sum() / ring_alpha.size * 100 if ring_alpha.size > 0 else 0
print(f"T2 (边框>200): {'✅' if t2 >= 70 else '❌'} {t2:.1f}%")

# T3
text_mask = (dist >= stamp_r*0.65) & (dist <= stamp_r*0.85)
text_alpha = full_alpha[text_mask]
t3 = text_alpha.mean() if text_alpha.size > 0 else 0
print(f"T3 (文字均值>80): {'✅' if t3 >= 80 else '❌'} mean={t3:.1f}")

# T4
inner_mask = dist <= stamp_r*0.50
inner_alpha = full_alpha[inner_mask]
t4 = (inner_alpha < 30).sum() / inner_alpha.size * 100 if inner_alpha.size > 0 else 0
print(f"T4 (内部<30): {'✅' if t4 >= 80 else '❌'} {t4:.1f}%")

# T5
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
            if full_alpha[py,px] > 64: c += 1
    rate = c/t*100 if t else 0
    p = rate >= 95
    all_pass = all_pass and p
    print(f"  {ang:3d}°: {rate:.0f}% {'✅' if p else '❌'}")
print(f"  T5 总计: {'✅' if all_pass else '❌'}")

print(f"\n输出: test_output/FINAL_stamp_v2.png")
