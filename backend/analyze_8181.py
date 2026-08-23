"""彻底分析 8181.jpg 真实内容，明确到底是什么样的场景"""
import cv2
import numpy as np
from pathlib import Path

src = Path(r'test_output/module_test/8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]
print(f"图片尺寸: {w}x{h}")

# 看整张图
cv2.imwrite("test_output/debug_full.jpg", img)

# 转 HSV，看印章颜色范围
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# 统计整个图像的颜色分布
print(f"\n全图 HSV 统计:")
print(f"  H: min={hsv[:,:,0].min()}, max={hsv[:,:,0].max()}, mean={hsv[:,:,0].mean():.1f}")
print(f"  S: min={hsv[:,:,1].min()}, max={hsv[:,:,1].max()}, mean={hsv[:,:,1].mean():.1f}")
print(f"  V: min={hsv[:,:,2].min()}, max={hsv[:,:,2].max()}, mean={hsv[:,:,2].mean():.1f}")

# BGR 通道统计
b_ch, g_ch, r_ch = cv2.split(img)
print(f"\n全图 BGR 统计:")
print(f"  B: min={b_ch.min()}, max={b_ch.max()}, mean={b_ch.mean():.1f}")
print(f"  G: min={g_ch.min()}, max={g_ch.max()}, mean={g_ch.mean():.1f}")
print(f"  R: min={r_ch.min()}, max={r_ch.max()}, mean={r_ch.mean():.1f}")

# 印章可能是红色或蓝紫色
# 红色检测：H 接近 0 或 180
red_mask = cv2.inRange(hsv, (0, 50, 50), (15, 255, 255)) | cv2.inRange(hsv, (165, 50, 50), (180, 255, 255))
print(f"\n红色像素数 (H<15 或 H>165, S>50, V>50): {cv2.countNonZero(red_mask)} ({cv2.countNonZero(red_mask)/(h*w)*100:.2f}%)")

# 蓝紫色检测
purple_mask = cv2.inRange(hsv, (130, 30, 30), (170, 255, 255))
print(f"蓝紫色像素数 (H 130-170, S>30, V>30): {cv2.countNonZero(purple_mask)} ({cv2.countNonZero(purple_mask)/(h*w)*100:.2f}%)")

# 看印章区域（中心偏下）的颜色
cx, cy = w//2, int(h*0.55)
r_roi = int(min(w,h)*0.18)
roi = img[cy-r_roi:cy+r_roi, cx-r_roi:cx+r_roi]
roi_h, roi_w = roi.shape[:2]
cv2.imwrite("test_output/debug_seal_roi.jpg", roi)
roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

print(f"\n印章 ROI ({roi_w}x{roi_h}) HSV 统计:")
print(f"  H: min={roi_hsv[:,:,0].min()}, max={roi_hsv[:,:,0].max()}, mean={roi_hsv[:,:,0].mean():.1f}")
print(f"  S: min={roi_hsv[:,:,1].min()}, max={roi_hsv[:,:,1].max()}, mean={roi_hsv[:,:,1].mean():.1f}")
print(f"  V: min={roi_hsv[:,:,2].min()}, max={roi_hsv[:,:,2].max()}, mean={roi_hsv[:,:,2].mean():.1f}")

# ROI 内的 BGR
rb, rg, rr = cv2.split(roi)
print(f"\n印章 ROI BGR:")
print(f"  B: min={rb.min()}, max={rb.max()}, mean={rb.mean():.1f}")
print(f"  G: min={rg.min()}, max={rg.max()}, mean={rg.mean():.1f}")
print(f"  R: min={rr.min()}, max={rr.max()}, mean={rr.mean():.1f}")

# 印章颜色：R-G 差值
r_minus_g = rr.astype(np.int16) - rg.astype(np.int16)
print(f"\n印章 ROI R-G 差值: min={r_minus_g.min()}, max={r_minus_g.max()}, mean={r_minus_g.mean():.1f}")
print(f"  R-G > 20 的像素: {(r_minus_g > 20).sum()} ({(r_minus_g > 20).sum()/(roi_w*roi_h)*100:.2f}%)")
print(f"  R-G > 10 的像素: {(r_minus_g > 10).sum()} ({(r_minus_g > 10).sum()/(roi_w*roi_h)*100:.2f}%)")
print(f"  R-G > 0 的像素: {(r_minus_g > 0).sum()} ({(r_minus_g > 0).sum()/(roi_w*roi_h)*100:.2f}%)")

# 印章 vs 周围纸张背景
# 采样印章周围 200px 区域
bg_roi = img[cy+r_roi:cy+r_roi+200, cx-r_roi:cx+r_roi]
if bg_roi.size > 0:
    bb, bg_, br = cv2.split(bg_roi)
    print(f"\n背景区域 BGR: B={bb.mean():.1f}, G={bg_.mean():.1f}, R={br.mean():.1f}")
    print(f"  R-G 均值: {(br.astype(np.int16)-bg_.astype(np.int16)).mean():.1f}")

# 用高S/V筛选印章色
high_sv = (hsv[:,:,1] > 40) & (hsv[:,:,2] < 250) & (hsv[:,:,2] > 30)
high_sv_colors = hsv[high_sv]
print(f"\n高饱和度低亮度像素数: {high_sv.sum()} ({high_sv.sum()/(h*w)*100:.2f}%)")
if len(high_sv_colors) > 0:
    print(f"  H 范围: {high_sv_colors[:,0].min()}-{high_sv_colors[:,0].max()}, 均值={high_sv_colors[:,0].mean():.1f}")
    print(f"  S 范围: {high_sv_colors[:,1].min()}-{high_sv_colors[:,1].max()}, 均值={high_sv_colors[:,1].mean():.1f}")
