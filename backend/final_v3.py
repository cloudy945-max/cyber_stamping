"""最终方案 V3：线条骨架 + 膨胀 + R-G 软 alpha。

1. 高阈值 R-G 找印章"骨架"（边框、文字、图案的线条）
2. 形态学膨胀让骨架变粗
3. 骨架区域内用 R-G 值做软 alpha
4. 非骨架区域 alpha = 0
5. 圆形外 alpha = 0
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

# ====== 步骤 3：提取印章骨架 ======
# 圆形内 ROI
roi_x0, roi_y0 = max(0, stamp_cx - stamp_r - 10), max(0, stamp_cy - stamp_r - 10)
roi_x1, roi_y1 = min(w, stamp_cx + stamp_r + 10), min(h, stamp_cy + stamp_r + 10)
roi_rg = r_minus_g[roi_y0:roi_y1, roi_x0:roi_x1]
roi_circle = inside_circle[roi_y0:roi_y1, roi_x0:roi_x1]
rh, rw = roi_rg.shape[:2]

# 3a. 用中等阈值找"骨架"（印章的边框、文字、图案的线条）
# 阈值要合适：不能太高（丢细线条），不能太低（引入噪点）
# 扫描不同阈值
best_alpha = None
best_score = -1
best_params = None

for skeleton_thr in [8, 10, 12, 15, 20]:
    for dilate_iter in [1, 2, 3]:
        for open_iter in [0, 1]:
            for alpha_mult in [2, 3, 4, 5]:
                # 高阈值二值化：找到印章骨架
                _, skeleton = cv2.threshold(roi_rg, skeleton_thr, 255, cv2.THRESH_BINARY)
                skeleton = cv2.bitwise_and(skeleton, roi_circle)
                
                # 形态学：膨胀让骨架变粗
                skel_dilated = cv2.dilate(skeleton, k3, iterations=dilate_iter)
                skel_dilated = cv2.bitwise_and(skel_dilated, roi_circle)
                
                # 可选：开运算去小噪点
                if open_iter > 0:
                    skel_clean = cv2.morphologyEx(skel_dilated, cv2.MORPH_OPEN, k3, iterations=open_iter)
                else:
                    skel_clean = skel_dilated
                skel_clean = cv2.bitwise_and(skel_clean, roi_circle)
                
                # 骨架区域内用 R-G 值做软 alpha
                alpha_roi = np.zeros((rh, rw), dtype=np.uint8)
                in_skeleton = skel_clean > 0
                alpha_roi[in_skeleton] = np.clip(roi_rg[in_skeleton].astype(np.float32) * alpha_mult, 0, 255).astype(np.uint8)
                alpha_roi[~roi_circle] = 0
                
                # 评分
                # T5: 8 方向边框捕获
                ring_mask = ((dist[roi_y0:roi_y1, roi_x0:roi_x1] >= stamp_r*0.88) & 
                           (dist[roi_y0:roi_y1, roi_x0:roi_x1] <= stamp_r*0.98))
                total_cap = 0
                for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
                    a = np.radians(ang)
                    c = 0; t = 0
                    for d in range(int(stamp_r*0.88), int(stamp_r*0.98), 2):
                        px = int(stamp_cx + d*np.cos(a)) - roi_x0
                        py = int(stamp_cy + d*np.sin(a)) - roi_y0
                        if 0 <= px < rw and 0 <= py < rh:
                            t += 1
                            if alpha_roi[py, px] > 32: c += 1
                    total_cap += (c / t * 100 if t else 0)
                avg_cap = total_cap / 8
                
                # T4: 内部空白透明度
                inner_mask = dist[roi_y0:roi_y1, roi_x0:roi_x1] <= stamp_r*0.50
                inner_alpha = alpha_roi[inner_mask]
                transparency = (inner_alpha < 30).sum() / inner_alpha.size * 100 if inner_alpha.size > 0 else 0
                
                # 边框强度
                ring_alpha = alpha_roi[ring_mask]
                ring_strength = (ring_alpha > 200).sum() / ring_alpha.size * 100 if ring_alpha.size > 0 else 0
                
                # 综合评分
                score = avg_cap * 3 + transparency * 0.5 + ring_strength
                
                if score > best_score:
                    best_score = score
                    best_alpha = alpha_roi.copy()
                    best_params = (skeleton_thr, dilate_iter, open_iter, alpha_mult, avg_cap, transparency, ring_strength)

skel_thr, dil_it, op_it, a_mult, cap8, trans, ring_s = best_params
print(f"最佳: skel_thr={skel_thr}, dil={dil_it}, open={op_it}, mult={a_mult}")
print(f"  cap8={cap8:.0f}%, trans={trans:.1f}%, ring_strength={ring_s:.1f}%")

# ====== 步骤 4：生成全图 alpha ======
full_alpha = np.zeros((h, w), dtype=np.uint8)
full_alpha[roi_y0:roi_y1, roi_x0:roi_x1] = best_alpha

# ====== 步骤 5：完整验证 ======
print("\n===== 测试验证 =====")

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
            if full_alpha[py,px] > 32: c += 1
    rate = c/t*100 if t else 0
    p = rate >= 95
    all_pass = all_pass and p
    print(f"  {ang:3d}°: {rate:.0f}% {'✅' if p else '❌'}")
print(f"  T5: {'✅' if all_pass else '❌'}")

# 保存
rgba = np.dstack([img, full_alpha])
cv2.imwrite("test_output/FINAL_stamp_v3.png", rgba)
print(f"\n输出: test_output/FINAL_stamp_v3.png")
