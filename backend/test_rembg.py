"""测试 rembg 抠图效果"""
import cv2
import numpy as np
from pathlib import Path
from app.services.background_removal import remove_background, _get_session

src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

# 裁取 ROI
cx, cy = w//2, int(h*0.55)
r = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx-r), max(0,cy-r), min(w,cx+r), min(h,cy+r)
roi = img[y0:y1, x0:x1]

# 保存 ROI 为临时文件
roi_path = Path('test_output/roi_temp.png')
cv2.imwrite(str(roi_path), roi)

# 用 rembg 处理
dst = Path('test_output/8181_rembg.png')
print("Loading rembg session...")
session = _get_session()
if session is not None:
    from rembg import remove
    result = remove(roi, session=session)
    if result.shape[2] == 4:
        alpha = result[:,:,3]
        print(f"rembg alpha: fg={cv2.countNonZero(alpha)} ({cv2.countNonZero(alpha)/(roi.shape[0]*roi.shape[1])*100:.1f}%)")

        # 统计捕获率
        roi_h, roi_w = alpha.shape
        center_x, center_y = roi_w // 2, roi_h // 2
        for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
            angle = np.radians(angle_deg)
            captured = 0
            total = 0
            for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
                px_x = int(center_x + dist * np.cos(angle))
                px_y = int(center_y + dist * np.sin(angle))
                if 0 <= px_x < roi_w and 0 <= px_y < roi_h:
                    total += 1
                    if alpha[px_y, px_x] > 0:
                        captured += 1
            pct = captured / total * 100 if total > 0 else 0
            print(f"  Angle {angle_deg}: {pct:.0f}%")

        # 保存全图 RGBA
        full_mask = np.zeros((h, w), dtype=np.uint8)
        full_mask[y0:y0+roi_h, x0:x0+roi_w] = alpha
        rgba = np.dstack([img, full_mask])
        cv2.imwrite(str(dst), rgba)
        print(f"Saved: {dst}")
else:
    print("rembg session not available")
