"""直接检查 API 返回的 PNG 颜色是否正确（从 HSV 检查）"""
import cv2
import numpy as np

img = cv2.imread(r'test_output/api_test/api_no_bbox.png', cv2.IMREAD_UNCHANGED)
alpha = img[:,:,3]
strong = alpha >= 128
print(f"非透明 alpha>128 像素: {strong.sum()}")

hsv = cv2.cvtColor(img[:,:,0:3], cv2.COLOR_BGR2HSV)
if strong.sum() > 0:
    h = hsv[strong][:,0].mean()
    s = hsv[strong][:,1].mean()
    v = hsv[strong][:,2].mean()
    print(f"墨水像素 HSV: H={h:.0f}, S={s:.0f}, V={v:.0f}")
    # 红色 H 应该在 160-179（或 0-15）
    if 160 <= h <= 179 or h <= 15:
        print("✅ 颜色：红色（和纸质印章一致）")
    elif 80 <= h <= 130:
        print("❌ 颜色：蓝/青色（还没校正颜色！）")
    else:
        print("❓ 颜色：HSV H={h}，非红色/蓝色（检查）")
