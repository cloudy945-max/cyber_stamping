"""调试脚本：测试 DoG 方案"""
import cv2
import numpy as np
from pathlib import Path
from scipy import ndimage

src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

cx, cy = w//2, int(h*0.55)
r = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx-r), max(0,cy-r), min(w,cx+r), min(h,cy+r)
roi = img[y0:y1, x0:x1]
roi_h, roi_w = roi.shape[:2]

gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)

# DoG: Difference of Gaussians
configs = [(1, 3), (1, 5), (2, 5), (1, 7), (2, 7)]
c_values = [0, 2, 3]

for s1, s2 in configs:
    g1 = cv2.GaussianBlur(enhanced, (0, 0), s1)
    g2 = cv2.GaussianBlur(enhanced, (0, 0), s2)
    dog = g1.astype(np.int16) - g2.astype(np.int16)
    dog_u8 = np.clip(dog + 128, 0, 255).astype(np.uint8)

    for c in c_values:
        bs = 51
        binary = cv2.adaptiveThreshold(dog_u8, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                        cv2.THRESH_BINARY, bs, c)

        # 统计捕获率
        center_x, center_y = roi_w // 2, roi_h // 2
        rates = []
        for angle_deg in [0, 90, 180, 270]:
            angle = np.radians(angle_deg)
            captured = 0
            total = 0
            for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
                px_x = int(center_x + dist * np.cos(angle))
                px_y = int(center_y + dist * np.sin(angle))
                if 0 <= px_x < roi_w and 0 <= px_y < roi_h:
                    total += 1
                    if binary[px_y, px_x] > 0:
                        captured += 1
            pct = captured / total * 100 if total > 0 else 0
            rates.append(pct)

        fg = cv2.countNonZero(binary)
        fg_pct = fg / (roi_w * roi_h) * 100
        avg_rate = np.mean(rates)
        rate_str = [f"{r:.0f}" for r in rates]
        print(f"DoG s=({s1},{s2}) c={c}: fg={fg_pct:.1f}% rates={rate_str} avg={avg_rate:.0f}%")

        if s1 == 1 and s2 == 5 and c == 2:
            cv2.imwrite(str(Path('test_output/dog_best.png')), binary)
            full_mask = np.zeros((h, w), dtype=np.uint8)
            full_mask[y0:y0+roi_h, x0:x0+roi_w] = binary
            rgba = np.dstack([img, full_mask])
            cv2.imwrite(str(Path('test_output/8181_dog.png')), rgba)

# 同时测试 rembg
print("\n--- Testing rembg ---")
try:
    from rembg import remove
    result = remove(roi)
    if result.shape[2] == 4:
        alpha = result[:,:,3]
        cv2.imwrite(str(Path('test_output/rembg_alpha.png')), alpha)
        full_mask = np.zeros((h, w), dtype=np.uint8)
        full_mask[y0:y0+roi_h, x0:x0+roi_w] = alpha
        rgba = np.dstack([img, full_mask])
        cv2.imwrite(str(Path('test_output/8181_rembg.png')), rgba)
        print(f"rembg: fg={cv2.countNonZero(alpha)} ({cv2.countNonZero(alpha)/(roi_w*roi_h)*100:.1f}%)")
except Exception as e:
    print(f"rembg failed: {e}")
