"""调试正式函数的 8 方向捕获率。"""
import sys, types
from pathlib import Path
import cv2
import numpy as np

# 读 alpha 文件
alpha = cv2.imread(r"test_output/8181_alpha_channel.png", cv2.IMREAD_GRAYSCALE)
h, w = alpha.shape

# 取 bbox 对应 ROI
short = min(w, h)
r_roi = int(short * 0.25)
cx_img, cy_img = w // 2, int(h * 0.55)
x0, y0, x1, y1 = max(0,cx_img-r_roi), max(0,cy_img-r_roi), min(w,cx_img+r_roi), min(h,cy_img+r_roi)
roi_a = alpha[y0:y1, x0:x1]
roi_h, roi_w = roi_a.shape[:2]
cx, cy = roi_w//2, roi_h//2

print(f"ROI size: {roi_w}x{roi_h}, alpha max={roi_a.max()}")
print(f"alpha 非零: {(roi_a>0).sum()/(roi_w*roi_h)*100:.1f}%")
print(f"alpha >32: {(roi_a>32).sum()/(roi_w*roi_h)*100:.1f}%")
print(f"alpha >128: {(roi_a>128).sum()/(roi_w*roi_h)*100:.1f}%")
print(f"alpha >200: {(roi_a>200).sum()/(roi_w*roi_h)*100:.1f}%")

# 8方向捕获率
def cap(alpha, th=32):
    rates = {}
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        angle = np.radians(angle_deg)
        c = 0
        t = 0
        for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
            px = int(cx + dist * np.cos(angle))
            py = int(cy + dist * np.sin(angle))
            if 0 <= px < roi_w and 0 <= py < roi_h:
                t += 1
                if alpha[py, px] > th:
                    c += 1
        rates[angle_deg] = c/t*100 if t else 0
    return rates

for th in [10, 32, 64, 128, 200]:
    rates = cap(roi_a, th)
    avg = np.mean(list(rates.values()))
    print(f"  th={th:3d}: avg={avg:.0f}% {[f'{k}={v:.0f}%' for k,v in rates.items()]}")
