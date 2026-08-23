"""验证颜色校正是否生效"""
import sys
sys.path.insert(0, '.')
from pathlib import Path
import cv2
import numpy as np

# 读输入和输出
inp = cv2.imread(r'test_output/module_test/8181.jpg')
out = cv2.imread(r'test_output/module_test/8181_segmented.png', cv2.IMREAD_UNCHANGED)

print(f"输入: {inp.shape}")
print(f"输出: {out.shape}")

# 墨水区域：输出的 alpha >= 128
alpha = out[:,:,3]
strong = alpha >= 128
print(f"墨水强像素数: {strong.sum()}")

# 对比输入和输出中对应像素的 BGR
if strong.sum() > 0:
    # 输入对应强墨水像素（同样坐标）
    inp_strong = inp[strong]
    out_strong = out[strong][:,0:3]  # 只取 BGR
    
    print(f"\n输入墨水区域 BGR:")
    print(f"  B mean: {inp_strong[:,0].mean():.1f}")
    print(f"  G mean: {inp_strong[:,1].mean():.1f}")
    print(f"  R mean: {inp_strong[:,2].mean():.1f}")
    
    print(f"\n输出墨水区域 BGR:")
    print(f"  B mean: {out_strong[:,0].mean():.1f}")
    print(f"  G mean: {out_strong[:,1].mean():.1f}")
    print(f"  R mean: {out_strong[:,2].mean():.1f}")
    
    # HSV 对比
    inp_hsv = cv2.cvtColor(inp, cv2.COLOR_BGR2HSV)
    out_hsv = cv2.cvtColor(out[:,:,0:3], cv2.COLOR_BGR2HSV)
    
    print(f"\n输入墨水 HSV:")
    ihsv = inp_hsv[strong]
    print(f"  H mean: {ihsv[:,0].mean():.1f}")
    print(f"  S mean: {ihsv[:,1].mean():.1f}")
    print(f"  V mean: {ihsv[:,2].mean():.1f}")
    
    print(f"\n输出墨水 HSV:")
    ohsv = out_hsv[strong]
    print(f"  H mean: {ohsv[:,0].mean():.1f}")
    print(f"  S mean: {ohsv[:,1].mean():.1f}")
    print(f"  V mean: {ohsv[:,2].mean():.1f}")
