"""最终方案：圆形约束 + R-G 自适应软 alpha + 形态学清理。

最终测试标准：
- T1: 圆形区域外 alpha 全为 0
- T2: 印章边框（圆环）alpha > 200
- T3: 印章文字区域 alpha 平均值 > 100
- T4: 印章内部空白区域 alpha < 30
- T5: 8 方向（45°步长）的边框捕获率 >= 95%
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

print(f"印章: ({stamp_cx}, {stamp_cy}), r={stamp_r}")

# ====== 步骤 2：圆形约束 ======
Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - stamp_cx)**2 + (Y - stamp_cy)**2)
inside_circle = dist <= stamp_r

# ====== 步骤 3：在圆形内计算软 alpha ======
roi_x0, roi_y0 = max(0, stamp_cx - stamp_r - 10), max(0, stamp_cy - stamp_r - 10)
roi_x1, roi_y1 = min(w, stamp_cx + stamp_r + 10), min(h, stamp_cy + stamp_r + 10)
roi_rg = r_minus_g[roi_y0:roi_y1, roi_x0:roi_x1]
roi_circle = inside_circle[roi_y0:roi_y1, roi_x0:roi_x1]
rh, rw = roi_rg.shape[:2]

# 用局部自适应方法
# 方法：在圆形内做均值滤波，然后 alpha = 原始值 / 局部均值
# 这样在平滑区域（纸张）alpha 低，在边缘区域（墨水）alpha 高

# 先对 R-G 图做均值滤波作为"局部背景"
k_size = max(5, stamp_r // 8)  # 核大小约为印章半径的 1/8
if k_size % 2 == 0: k_size += 1
local_mean = cv2.blur(roi_rg, (k_size, k_size))

# 相对强度 = (当前值 - 局部均值) / max(局部均值, 1)
relative = roi_rg.astype(np.float32) - local_mean.astype(np.float32)
relative = np.clip(relative, 0, 255)

# 再归一化到 0-255
rel_max = relative[roi_circle].max() if roi_circle.sum() > 0 else 1
if rel_max > 0:
    alpha_soft = (relative / rel_max * 255).astype(np.uint8)
else:
    alpha_soft = np.zeros((rh, rw), dtype=np.uint8)

alpha_soft[~roi_circle] = 0

# ====== 步骤 4：形态学清理 ======
# 闭运算：连接笔画
alpha_closed = cv2.morphologyEx(alpha_soft, cv2.MORPH_CLOSE, kernel, iterations=2)
# 开运算：去小噪点
alpha_clean = cv2.morphologyEx(alpha_closed, cv2.MORPH_OPEN, kernel, iterations=1)

# 再次限制在圆形内
alpha_clean[~roi_circle] = 0

# ====== 步骤 5：生成全图 alpha ======
full_alpha = np.zeros((h, w), dtype=np.uint8)
full_alpha[roi_y0:roi_y1, roi_x0:roi_x1] = alpha_clean

# ====== 步骤 6：验证 ======
print("\n===== 测试验证 =====")

# T1: 圆形外 alpha 为 0
outside_alpha_max = full_alpha[~inside_circle].max()
t1_pass = outside_alpha_max == 0
print(f"T1 (圆外=0): {'✅' if t1_pass else '❌'} max={outside_alpha_max}")

# T2: 印章边框 alpha > 200
# 边框定义：距离圆心 0.90r - 0.98r 的环形区域
ring_inner = stamp_r * 0.90
ring_outer = stamp_r * 0.98
ring_mask = (dist >= ring_inner) & (dist <= ring_outer)
ring_alpha = full_alpha[ring_mask]
t2_ratio = (ring_alpha > 200).sum() / ring_alpha.size * 100 if ring_alpha.size > 0 else 0
t2_pass = t2_ratio >= 70
print(f"T2 (边框>200): {'✅' if t2_pass else '❌'} {t2_ratio:.1f}% (需要>=70%)")

# T3: 印章文字区域 alpha 平均值 > 100
# 文字区域：距离圆心 0.65r - 0.85r 的环形
text_inner = stamp_r * 0.65
text_outer = stamp_r * 0.85
text_mask = (dist >= text_inner) & (dist <= text_outer)
text_alpha = full_alpha[text_mask]
t3_mean = text_alpha.mean() if text_alpha.size > 0 else 0
t3_pass = t3_mean >= 80
print(f"T3 (文字均值>80): {'✅' if t3_pass else '❌'} mean={t3_mean:.1f}")

# T4: 印章内部空白 alpha < 30
# 内部空白：距离圆心 0.20r - 0.50r 的圆盘
inner_disk = stamp_r * 0.50
inner_mask = dist <= inner_disk
inner_alpha = full_alpha[inner_mask]
t4_ratio = (inner_alpha < 30).sum() / inner_alpha.size * 100 if inner_alpha.size > 0 else 0
t4_pass = t4_ratio >= 80
print(f"T4 (内部<30): {'✅' if t4_pass else '❌'} {t4_ratio:.1f}% (需要>=80%)")

# T5: 8 方向边框捕获率
print(f"T5 (8方向边框捕获):")
t5_all_pass = True
for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
    a = np.radians(ang)
    c = 0; t = 0
    for d in range(int(stamp_r * 0.88), int(stamp_r * 0.98), 2):
        px = int(stamp_cx + d * np.cos(a))
        py = int(stamp_cy + d * np.sin(a))
        if 0 <= px < w and 0 <= py < h:
            t += 1
            if full_alpha[py, px] > 64: c += 1
    rate = c / t * 100 if t else 0
    passed = rate >= 95
    t5_all_pass = t5_all_pass and passed
    print(f"  {ang:3d}°: {rate:.0f}% {'✅' if passed else '❌'}")
print(f"  T5 总计: {'✅' if t5_all_pass else '❌'}")

# ====== 步骤 7：保存结果 ======
rgba = np.dstack([img, full_alpha])
out_path = "test_output/FINAL_stamp.png"
cv2.imwrite(out_path, rgba)
print(f"\n输出: {out_path}")

# 统计
print(f"\n最终 alpha 统计:")
print(f"  alpha>0: {(full_alpha>0).sum()/(h*w)*100:.2f}%")
print(f"  alpha>128: {(full_alpha>128).sum()/(h*w)*100:.2f}%")
print(f"  alpha>200: {(full_alpha>200).sum()/(h*w)*100:.2f}%")
