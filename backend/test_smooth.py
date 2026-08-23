"""生成边缘平滑版本 v_smooth.png，与 v_before_smooth.png 对比"""
import cv2
import numpy as np
from PIL import Image

SRC = r'd:\projects\cyber_stamping\backend\test_output\api_test\v_before_smooth.png'
OUT = r'd:\projects\cyber_stamping\backend\test_output\api_test\v_smooth.png'

img = cv2.imread(SRC, cv2.IMREAD_UNCHANGED)
H, W = img.shape[:2]
alpha = img[:, :, 3].copy()
bgr = img[:, :, :3].copy()

# 对 alpha 通道做高斯模糊（3x3），实现边缘抗锯齿
# 只模糊 alpha 边缘区域（alpha 在 20-235 之间的像素附近）
alpha_blurred = cv2.GaussianBlur(alpha, (3, 3), 0.8)

# 只在边缘区域应用模糊（保留内部硬边缘）
# 找边缘：alpha 梯度大的地方
grad = cv2.Laplacian(alpha, cv2.CV_64F)
edge_mask = np.abs(grad) > 5
# 扩张边缘区域 2px
k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
edge_mask_dilated = cv2.dilate(edge_mask.astype(np.uint8) * 255, k3, iterations=1) > 0

# 在边缘区域用模糊后的 alpha，其他区域保留原始 alpha
smooth_alpha = alpha.copy()
smooth_alpha[edge_mask_dilated] = alpha_blurred[edge_mask_dilated]

# 输出
rgba = np.dstack([bgr, smooth_alpha])
Image.fromarray(rgba, "RGBA").save(OUT, "PNG")

# 统计
total = H * W
transp = int((smooth_alpha == 0).sum())
opaque = int((smooth_alpha >= 200).sum())
semi = int(((smooth_alpha > 0) & (smooth_alpha < 200)).sum())
print(f"v_smooth.png: transparent={transp/total*100:.1f}% opaque={opaque/total*100:.1f}% semi={semi/total*100:.1f}%")
print(f"Saved to {OUT}")
