"""方案 A：HoughCircle 找圆心 + R-G 通道提取印章 + 圆形约束。

核心思路：
1. 在全图上用 HoughCircle 找到印章圆心和半径
2. 圆形区域内：用 R-G 通道自适应阈值提取印章墨水
3. 圆形区域外：alpha = 0
4. 输出只包含圆形印章
"""
import cv2
import numpy as np
from pathlib import Path

src = Path(r'test_output/module_test/8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

# ====== 步骤 1：定位印章（HoughCircle）======
# 转灰度 + 模糊
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)

# 用 R-G 增强后找圆形
b_ch, g_ch, r_ch = cv2.split(img)
r_minus_g = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(0, 255).astype(np.uint8)
# 二值化：R > G 的区域（印章特征）
_, r_binary = cv2.threshold(r_minus_g, 10, 255, cv2.THRESH_BINARY)
# 膨胀连接笔画
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
r_dilated = cv2.dilate(r_binary, kernel, iterations=3)

cv2.imwrite("test_output/A_r_minus_g.jpg", r_minus_g)
cv2.imwrite("test_output/A_r_binary.jpg", r_binary)
cv2.imwrite("test_output/A_r_dilated.jpg", r_dilated)

# 在 R-G 二值图上找轮廓，取最大的圆形轮廓
contours, _ = cv2.findContours(r_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
print(f"找到 {len(contours)} 个轮廓")

# 按面积排序
contours = sorted(contours, key=cv2.contourArea, reverse=True)
for i, cnt in enumerate(contours[:10]):
    area = cv2.contourArea(cnt)
    x, y, cw, ch = cv2.boundingRect(cnt)
    aspect = cw / ch if ch > 0 else 0
    print(f"  #{i}: area={area:.0f} bbox={cw}x{ch} aspect={aspect:.2f} center=({x+cw//2},{y+ch//2})")

# 找圆形：检查宽高比接近 1 的大轮廓
stamp_cx, stamp_cy, stamp_r = None, None, None
for cnt in contours[:20]:
    area = cv2.contourArea(cnt)
    if area < 50000: continue  # 太小的不是印章
    x, y, cw, ch = cv2.boundingRect(cnt)
    aspect = cw / ch if ch > 0 else 0
    if 0.7 < aspect < 1.4:  # 接近正方形/圆形
        stamp_cx = x + cw // 2
        stamp_cy = y + ch // 2
        stamp_r = max(cw, ch) // 2
        print(f"选中等轮廓: area={area:.0f} center=({stamp_cx},{stamp_cy}) r≈{stamp_r}")
        break

# 如果上面没找到，回退到手动估计
if stamp_cx is None:
    # 根据之前的分析，印章中心大约在 (w//2, h*0.55)
    stamp_cx = w // 2
    stamp_cy = int(h * 0.55)
    stamp_r = int(min(w, h) * 0.17)
    print(f"回退估计: center=({stamp_cx},{stamp_cy}) r={stamp_r}")

print(f"\n印章定位: 圆心({stamp_cx}, {stamp_cy}), 半径≈{stamp_r}")

# 画出来验证
debug = img.copy()
cv2.circle(debug, (stamp_cx, stamp_cy), stamp_r, (0, 255, 0), 5)
cv2.circle(debug, (stamp_cx, stamp_cy), 10, (0, 0, 255), -1)
cv2.imwrite("test_output/A_stamp_location.jpg", debug)

# ====== 步骤 2：在圆形区域内提取印章 ======
# 圆形蒙版
circle_mask = np.zeros((h, w), dtype=np.uint8)
cv2.circle(circle_mask, (stamp_cx, stamp_cy), stamp_r, 255, -1)

# 在圆形区域内，用 R-G 通道 + 自适应阈值提取印章
roi_x0 = max(0, stamp_cx - stamp_r - 20)
roi_y0 = max(0, stamp_cy - stamp_r - 20)
roi_x1 = min(w, stamp_cx + stamp_r + 20)
roi_y1 = min(h, stamp_cy + stamp_r + 20)

roi = img[roi_y0:roi_y1, roi_x0:roi_x1]
roi_circle = circle_mask[roi_y0:roi_y1, roi_x0:roi_x1]
rh, rw = roi.shape[:2]

# 对 ROI 做 R-G 增强
b_r, g_r, r_r = cv2.split(roi)
rg = (r_r.astype(np.int16) - g_r.astype(np.int16)).clip(-128, 127)
rg_u8 = (rg.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)

# CLAHE 增强对比度
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(rg_u8)

# 自适应阈值
binary = cv2.adaptiveThreshold(
    enhanced, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
    cv2.THRESH_BINARY, 21, 5
)

# 限制在圆形区域内
binary_masked = cv2.bitwise_and(binary, roi_circle)

cv2.imwrite("test_output/A_roi_binary.jpg", binary_masked)

# ====== 步骤 3：干净化处理 ======
# 形态学操作：去小噪点 + 填充孔洞
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

# 开运算去噪
cleaned = cv2.morphologyEx(binary_masked, cv2.MORPH_OPEN, k3, iterations=1)
# 闭运算填充
cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, k3, iterations=2)

# 孔洞填充
from scipy import ndimage
filled = ndimage.binary_fill_holes(cleaned > 0).astype(np.uint8) * 255
filled = cv2.bitwise_and(filled, roi_circle)

cv2.imwrite("test_output/A_roi_cleaned.jpg", cleaned)
cv2.imwrite("test_output/A_roi_filled.jpg", filled)

# ====== 步骤 4：生成最终 alpha ======
# 放回全图
full_alpha = np.zeros((h, w), dtype=np.uint8)
full_alpha[roi_y0:roi_y1, roi_x0:roi_x1] = filled

# ====== 步骤 5：生成 RGBA 输出 ======
rgba = np.dstack([img, full_alpha])
cv2.imwrite("test_output/A_final_result.png", rgba)

# 统计
print(f"\n最终 alpha 统计:")
print(f"  总像素: {h*w}")
print(f"  alpha>0: {(full_alpha>0).sum()} ({(full_alpha>0).sum()/(h*w)*100:.2f}%)")
print(f"  alpha>128: {(full_alpha>128).sum()} ({(full_alpha>128).sum()/(h*w)*100:.2f}%)")
print(f"  alpha>200: {(full_alpha>200).sum()} ({(full_alpha>200).sum()/(h*w)*100:.2f}%)")

# 检查 8 方向（只看圆形内）
print(f"\n8方向捕获率（圆形区域内）:")
for th in [32, 64, 128]:
    rates = {}
    for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
        a = np.radians(ang)
        c = 0; t = 0
        for d in range(int(stamp_r*0.2), int(stamp_r*0.95), 3):
            px = int(stamp_cx + d*np.cos(a))
            py = int(stamp_cy + d*np.sin(a))
            if 0<=px<w and 0<=py<h:
                t += 1
                if full_alpha[py, px] > th: c += 1
        rates[ang] = c/t*100 if t else 0
    avg = np.mean(list(rates.values()))
    print(f"  th={th:3d}: avg={avg:.0f}% {[f'{k}={v:.0f}%' for k,v in rates.items()]}")

print(f"\n输出: test_output/A_final_result.png")
