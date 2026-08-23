"""检查 A_final_result.png 的真实内容"""
import cv2
import numpy as np
from pathlib import Path

img = cv2.imread("test_output/A_final_result.png", cv2.IMREAD_UNCHANGED)
print(f"形状: {img.shape}")
print(f"通道数: {img.shape[2]}")

alpha = img[:,:,3]
print(f"\nalpha 统计:")
print(f"  min={alpha.min()}, max={alpha.max()}")
print(f"  alpha>0: {(alpha>0).sum()} ({(alpha>0).sum()/alpha.size*100:.2f}%)")
print(f"  alpha=0: {(alpha==0).sum()} ({(alpha==0).sum()/alpha.size*100:.2f}%)")

# 检查圆形区域外的 alpha
h, w = alpha.shape
cx, cy = 1364, 1851
r = 678
Y, X = np.ogrid[:h, :w]
dist = np.sqrt((X - cx)**2 + (Y - cy)**2)
outside = dist > r
inside = dist <= r

print(f"\n圆形区域外 (dist > r):")
print(f"  像素数: {outside.sum()}")
print(f"  alpha>0: {(alpha[outside]>0).sum()}")
print(f"  最大 alpha: {alpha[outside].max()}")

print(f"\n圆形区域内 (dist <= r):")
print(f"  像素数: {inside.sum()}")
print(f"  alpha>0: {(alpha[inside]>0).sum()}")
print(f"  alpha=0: {(alpha[inside]==0).sum()}")

# 检查印章中心区域
center_region = (abs(X - cx) < 50) & (abs(Y - cy) < 50)
print(f"\n印章中心 100x100 区域:")
print(f"  alpha 统计: min={alpha[center_region].min()}, max={alpha[center_region].max()}")

# 保存一个只显示 alpha 的图
cv2.imwrite("test_output/A_alpha_only.png", alpha)

# 保存一个 alpha 反向显示（透明部分白色）
inverted = 255 - alpha
cv2.imwrite("test_output/A_alpha_inverted.png", inverted)
