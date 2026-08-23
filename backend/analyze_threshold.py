"""分析不同 HSV 阈值下红色像素的覆盖率，找出文字丢失原因。

关键：印章区域 S mean=45，说明大量红色像素 S<70 被当前阈值丢弃。
"""
from pathlib import Path

import cv2
import numpy as np

OUT = Path(r"d:\projects\cyber_stamping\backend\test_output\threshold")
OUT.mkdir(parents=True, exist_ok=True)
SRC = Path(r"d:\projects\cyber_stamping\backend\test_output\8181_original.jpg")

img = cv2.imread(str(SRC))
x0, y0, x1, y1 = 693, 1291, 2036, 2412
crop = img[y0:y1, x0:x1]
hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
cw, ch = crop.shape[1], crop.shape[0]
total = cw * ch

# 不同 S 阈值测试
print("=" * 70)
print("不同 S 阈值下红色像素覆盖率")
print("=" * 70)
print(f"{'S阈值':<8} {'V阈值':<8} {'红色像素':<12} {'覆盖率':<10}")
print("-" * 40)

for s_th in [70, 50, 40, 30, 20, 10]:
    for v_th in [50, 30, 20]:
        lower1 = np.array([0, s_th, v_th])
        upper1 = np.array([10, 255, 255])
        lower2 = np.array([170, s_th, v_th])
        upper2 = np.array([180, 255, 255])
        m1 = cv2.inRange(hsv, lower1, upper1)
        m2 = cv2.inRange(hsv, lower2, upper2)
        mask = cv2.bitwise_or(m1, m2)
        cnt = int((mask > 0).sum())
        print(f"S>={s_th:<5} V>={v_th:<5} {cnt:<12} {cnt/total*100:.1f}%")

# 重点对比 S=70 vs S=30
print("\n" + "=" * 70)
print("S=70 vs S=30 对比")
print("=" * 70)

for s_th, name in [(70, "strict"), (30, "loose")]:
    lower1 = np.array([0, s_th, 30])
    upper1 = np.array([10, 255, 255])
    lower2 = np.array([170, s_th, 30])
    upper2 = np.array([180, 255, 255])
    m1 = cv2.inRange(hsv, lower1, upper1)
    m2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(m1, m2)
    
    # 形态学
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, k)
    
    # 凸包
    from scipy import ndimage
    binary = cleaned > 0
    labeled, num = ndimage.label(binary)
    if num > 0:
        sizes = ndimage.sum(binary, labeled, range(1, num + 1))
        largest = np.argmax(sizes) + 1
        blob = (labeled == largest).astype(np.uint8)
        contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            hull = cv2.convexHull(contours[0])
            hull_mask = np.zeros_like(blob)
            cv2.drawContours(hull_mask, [hull], -1, 1, thickness=cv2.FILLED)
            
            # 保存凸包版贴纸
            full_mask = np.zeros((img.shape[0], img.shape[1]), dtype=np.uint8)
            cv2.drawContours(full_mask[y0:y1, x0:x1], [hull], -1, 255, thickness=cv2.FILLED)
            rgba = np.dstack([img, full_mask])
            from PIL import Image
            Image.fromarray(rgba, "RGBA").save(str(OUT / f"hull_s{s_th}.png"))
            
            print(f"S>={s_th}: 红色={int((mask>0).sum())} 凸包={int(hull_mask.sum())} ({hull_mask.sum()/total*100:.1f}%)")

# 另一个思路：不用凸包，而是放宽 HSV + 膨胀连接 + 孔洞填充
print("\n" + "=" * 70)
print("方案：放宽HSV + 膨胀 + 孔洞填充（不用凸包）")
print("=" * 70)

# S=30 的红色 mask
lower1 = np.array([0, 30, 30])
upper1 = np.array([10, 255, 255])
lower2 = np.array([170, 30, 30])
upper2 = np.array([180, 255, 255])
m1 = cv2.inRange(hsv, lower1, upper1)
m2 = cv2.inRange(hsv, lower2, upper2)
red_loose = cv2.bitwise_or(m1, m2)

# 大核膨胀连接断线
k_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
dilated = cv2.dilate(red_loose, k_dilate)

# 孔洞填充（flood fill 背景，取反）
from scipy import ndimage
filled = ndimage.binary_fill_holes(dilated > 0).astype(np.uint8) * 255

# 取最大连通块
binary = filled > 0
labeled, num = ndimage.label(binary)
if num > 0:
    sizes = ndimage.sum(binary, labeled, range(1, num + 1))
    largest = np.argmax(sizes) + 1
    final = (labeled == largest).astype(np.uint8) * 255
    print(f"最终覆盖: {int((final>0).sum())} 像素 ({(final>0).sum()/total*100:.1f}%)")
    
    # 保存
    cv2.imwrite(str(OUT / "loose_red.png"), red_loose)
    cv2.imwrite(str(OUT / "loose_filled.png"), final)
    
    # 生成贴纸
    full_mask = np.zeros((img.shape[0], img.shape[1]), dtype=np.uint8)
    full_mask[y0:y1, x0:x1] = final
    rgba = np.dstack([img, full_mask])
    from PIL import Image
    Image.fromarray(rgba, "RGBA").save(str(OUT / "loose_sticker.png"))

print(f"\n对比图已保存到: {OUT}")
