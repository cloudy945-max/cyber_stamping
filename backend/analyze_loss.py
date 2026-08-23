"""分析当前分割结果丢失了什么细节。

对比：
- 原图印章区域的颜色分布
- 当前 alpha 通道覆盖率
- 凸包/区域生长能补回多少
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

OUT = Path(r"d:\projects\cyber_stamping\backend\test_output\seg")
SRC = Path(r"d:\projects\cyber_stamping\backend\test_output\8181_original.jpg")

img = cv2.imread(str(SRC))
H, W = img.shape[:2]

# 印章边界框（之前分析结果）
x0, y0, x1, y1 = 693, 1291, 2036, 2412
crop = img[y0:y1, x0:x1]
ch, cw = crop.shape[:2]
crop_total = ch * cw

print("=" * 60)
print("印章区域颜色分布分析")
print("=" * 60)
print(f"印章边界框: {cw}x{ch} = {crop_total} 像素")

# BGR → HSV
hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

# 当前红色阈值
lower1 = np.array([0, 70, 50])
upper1 = np.array([10, 255, 255])
lower2 = np.array([170, 70, 50])
upper2 = np.array([180, 255, 255])
m1 = cv2.inRange(hsv, lower1, upper1)
m2 = cv2.inRange(hsv, lower2, upper2)
red_mask = cv2.bitwise_or(m1, m2)
red_pixels = int((red_mask > 0).sum())
print(f"\n当前 HSV 红色阈值像素: {red_pixels} ({red_pixels/crop_total*100:.1f}%)")

# 分析印章区域的所有颜色
print("\n印章区域 H/S/V 分布:")
h_chan = hsv[:, :, 0].flatten()
s_chan = hsv[:, :, 1].flatten()
v_chan = hsv[:, :, 2].flatten()
print(f"  H: min={h_chan.min()} max={h_chan.max()} mean={h_chan.mean():.0f}")
print(f"  S: min={s_chan.min()} max={s_chan.max()} mean={s_chan.mean():.0f}")
print(f"  V: min={v_chan.min()} max={v_chan.max()} mean={v_chan.mean():.0f}")

# 低饱和像素（白色/浅色留白）
low_sat = (s_chan < 70).sum()
print(f"\n低饱和像素 (S<70, 印章内留白): {low_sat} ({low_sat/crop_total*100:.1f}%)")

# 高亮像素（白色背景）
high_v = (v_chan > 200).sum()
print(f"高亮像素 (V>200, 白色): {high_v} ({high_v/crop_total*100:.1f}%)")

# 当前分割结果的 alpha 通道
sticker = cv2.imread(str(OUT / "04_stamp_sticker.png"), cv2.IMREAD_UNCHANGED)
if sticker is not None and sticker.shape[2] == 4:
    alpha = sticker[y0:y1, x0:x1, 3]
    fg = int((alpha > 0).sum())
    print(f"\n当前分割前景（边界框内）: {fg} ({fg/crop_total*100:.1f}%)")
    print(f"丢失的印章细节: {crop_total - fg} 像素 ({(crop_total-fg)/crop_total*100:.1f}%)")

# 方案验证：凸包能补回多少
print("\n" + "=" * 60)
print("方案验证：凸包补全")
print("=" * 60)

# 形态学后红色 mask
k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
cleaned = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, k_close)
cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, k_open)

# 凸包
binary = cleaned > 0
labeled, num = ndimage.label(binary)
if num > 0:
    sizes = ndimage.sum(binary, labeled, range(1, num + 1))
    largest = np.argmax(sizes) + 1
    blob = (labeled == largest).astype(np.uint8)
    
    # 凸包
    contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        hull = cv2.convexHull(contours[0])
        hull_mask = np.zeros_like(blob)
        cv2.drawContours(hull_mask, [hull], -1, 1, thickness=cv2.FILLED)
        hull_pixels = int(hull_mask.sum())
        print(f"凸包覆盖像素: {hull_pixels} ({hull_pixels/crop_total*100:.1f}%)")
        print(f"凸包比红色阈值多补回: {hull_pixels - red_pixels} 像素")

# 方案验证：Flood Fill 区域生长
print("\n" + "=" * 60)
print("方案验证：Flood Fill 区域生长")
print("=" * 60)
# 从红色像素种子做 flood fill，把被红色包围的浅色区域也纳入
# 用 cv2.floodFill：从种子点开始，颜色相近的像素标记为前景
# 更简单的方法：对红色 mask 做膨胀→取反→floodfill 外部背景→取反得到内部

# 方法：闭运算大核 + 孔洞填充
k_big = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
dilated = cv2.dilate(cleaned, k_big)
# 找孔洞：膨胀后的反区域中，被前景包围的部分
filled = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, k_big)
filled_pixels = int((filled > 0).sum())
print(f"大核闭运算填充像素: {filled_pixels} ({filled_pixels/crop_total*100:.1f}%)")

# 保存对比图
cv2.imwrite(str(OUT / "10_red_only.png"), red_mask)
cv2.imwrite(str(OUT / "11_convex_hull.png"), hull_mask * 255)
cv2.imwrite(str(OUT / "12_filled.png"), filled)

# 生成凸包版本的贴纸
hull_full = np.zeros((H, W), dtype=np.uint8)
cv2.drawContours(hull_full[y0:y1, x0:x1], [hull], -1, 255, thickness=cv2.FILLED)
rgba = np.dstack([img, hull_full])
Image.fromarray(rgba, "RGBA").save(str(OUT / "13_hull_sticker.png"))

print(f"\n对比图已保存:")
print(f"  10_red_only.png    - 纯红色阈值 ({red_pixels/crop_total*100:.1f}%)")
print(f"  11_convex_hull.png - 凸包补全 ({hull_pixels/crop_total*100:.1f}%)")
print(f"  12_filled.png      - 大核填充 ({filled_pixels/crop_total*100:.1f}%)")
print(f"  13_hull_sticker.png - 凸包版贴纸")
