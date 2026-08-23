"""直接测试 HSV 映射公式"""
import cv2
import numpy as np

img = cv2.imread(r'test_output/module_test/8181.jpg')
h, w = img.shape[:2]

# 读已经生成的结果，得到 alpha
out = cv2.imread(r'test_output/module_test/8181_segmented.png', cv2.IMREAD_UNCHANGED)
alpha = out[:,:,3]
ink = alpha >= 32
print(f"墨水像素: {ink.sum()}")

img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
orig = img_hsv[ink]
print(f"输入墨水 HSV H 均值: {orig[:,0].mean():.1f}")

# 测试不同映射
h_orig = orig[:, 0].astype(np.float32)
h_mean = h_orig.mean()
print(f"h_mean = {h_mean}")

# 公式 1：当前代码
h_new1 = 172.0 + (h_orig - h_mean) * 0.3
print(f"公式1 (172 + (x - mu)*0.3): {h_new1.mean():.1f}")

# 公式 2：完全平移（系数 1.0）
h_new2 = 172.0 + (h_orig - h_mean) * 1.0
print(f"公式2 (172 + (x - mu)*1.0): {h_new2.mean():.1f}")

# 公式 3：直接设目标（不保留相对差异）
h_new3 = np.full_like(h_orig, 172.0)
print(f"公式3 (固定 172): {h_new3.mean():.1f}")

# 公式 4：偏移 +100 度（97 + 100 = 197 mod 179 = 18） 不对
# OpenCV H: 红 = 0-15, 160-179
# 蓝紫 H ≈ 90-110，要到红 ≈ 170
# 直接 delta = 170 - 97 = 73
h_new4 = h_orig + 73
h_new4 = np.where(h_new4 > 179, h_new4 - 180, h_new4)  # 循环
print(f"公式4 (直接+73): {h_new4.mean():.1f}")

# 把公式4转成 BGR 看视觉效果
h_new = h_new4.astype(np.uint8)
s_new = np.clip(orig[:,1].astype(np.float32)*1.8+40, 60, 255).astype(np.uint8)
v_new = orig[:,2]

new_pix = np.stack([h_new, s_new, v_new], axis=1).reshape(-1,1,3)
new_bgr = cv2.cvtColor(new_pix, cv2.COLOR_HSV2BGR).reshape(-1,3)

# 保存测试：把原图的墨水像素替换后保存
test_img = img.copy()
test_img[ink] = new_bgr
# 低 alpha 清黑
low = alpha < 16
test_img[low] = [0,0,0]
rgba = np.dstack([test_img, alpha])
cv2.imwrite("test_output/test_formula4.png", rgba)

# 统计输出后的 HSV
out2 = cv2.cvtColor(test_img, cv2.COLOR_BGR2HSV)
print(f"\n公式4 最终墨水 HSV:")
print(f"  H mean={out2[ink][:,0].mean():.1f}")
print(f"  S mean={out2[ink][:,1].mean():.1f}")
print(f"  V mean={out2[ink][:,2].mean():.1f}")
print(f"\n输出: test_output/test_formula4.png")
