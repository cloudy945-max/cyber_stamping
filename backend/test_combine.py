"""组合 rembg + 自适应阈值"""
import cv2
import numpy as np
from pathlib import Path
from scipy import ndimage
from app.services.background_removal import _get_session

src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

cx, cy = w//2, int(h*0.55)
r = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx-r), max(0,cy-r), min(w,cx+r), min(h,cy+r)
roi = img[y0:y1, x0:x1]
roi_h, roi_w = roi.shape[:2]

# 1. rembg 处理
print("Loading rembg...")
session = _get_session()
from rembg import remove
rembg_result = remove(roi, session=session)
rembg_alpha = rembg_result[:,:,3]
# 二值化 alpha (>128 = foreground)
_, rembg_binary = cv2.threshold(rembg_alpha, 128, 255, cv2.THRESH_BINARY)
print(f"rembg: {cv2.countNonZero(rembg_binary)} ({cv2.countNonZero(rembg_binary)/(roi_w*roi_h)*100:.1f}%)")

# 2. 自适应阈值
gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)
adapt_binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                       cv2.THRESH_BINARY_INV, 51, 5)
print(f"adapt: {cv2.countNonZero(adapt_binary)} ({cv2.countNonZero(adapt_binary)/(roi_w*roi_h)*100:.1f}%)")

# 3. OR 组合
combined = cv2.bitwise_or(rembg_binary, adapt_binary)
print(f"combined: {cv2.countNonZero(combined)} ({cv2.countNonZero(combined)/(roi_w*roi_h)*100:.1f}%)")

# 4. 去噪
k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, k2)

# 连通块去噪
labeled, num = ndimage.label(cleaned > 0)
sizes = ndimage.sum(cleaned > 0, labeled, range(1, num + 1))
min_sz = 30
keep = np.zeros_like(cleaned > 0, dtype=bool)
for i in range(1, num + 1):
    if sizes[i-1] >= min_sz:
        keep = keep | (labeled == i)
result = keep.astype(np.uint8) * 255

# 5. 统计捕获率
center_x, center_y = roi_w // 2, roi_h // 2
print("Combined capture rate:")
for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
    angle = np.radians(angle_deg)
    captured = 0
    total = 0
    for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
        px_x = int(center_x + dist * np.cos(angle))
        px_y = int(center_y + dist * np.sin(angle))
        if 0 <= px_x < roi_w and 0 <= px_y < roi_h:
            total += 1
            if result[px_y, px_x] > 0:
                captured += 1
    pct = captured / total * 100 if total > 0 else 0
    print(f"  Angle {angle_deg}: {pct:.0f}%")

print(f"\nFinal: {cv2.countNonZero(result)} ({cv2.countNonZero(result)/(roi_w*roi_h)*100:.1f}%)")

# 6. 生成 RGBA
full_mask = np.zeros((h, w), dtype=np.uint8)
full_mask[y0:y0+roi_h, x0:x0+roi_w] = result
rgba = np.dstack([img, full_mask])
cv2.imwrite(str(Path('test_output/8181_combined_final.png')), rgba)
print("Saved: test_output/8181_combined_final.png")
