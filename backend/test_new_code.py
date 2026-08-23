"""直接调用最新 segment_stamp，检查输出 alpha 分布"""
import sys, os
sys.path.insert(0, r'd:\projects\cyber_stamping\backend')

# 强制清除缓存
for k in list(sys.modules.keys()):
    if 'stamp' in k.lower() or 'app.services' in k:
        del sys.modules[k]

import cv2, numpy as np
from pathlib import Path
from app.services.stamp_segment import segment_stamp

src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
dst = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181_new.png')

result = segment_stamp(src, dst, color='auto')
print(f"结果: {result}")

if result and dst.exists():
    img = cv2.imread(str(dst), cv2.IMREAD_UNCHANGED)
    alpha = img[:,:,3]
    total = alpha.size
    transparent = (alpha == 0).sum()
    opaque = (alpha >= 200).sum()
    semi = ((alpha > 0) & (alpha < 200)).sum()

    # HSV 检查
    hsv = cv2.cvtColor(img[:,:,0:3], cv2.COLOR_BGR2HSV)
    strong = alpha >= 128
    h = hsv[strong][:,0].mean() if strong.sum() > 0 else 0
    s = hsv[strong][:,1].mean() if strong.sum() > 0 else 0

    print(f"总像素: {total}")
    print(f"透明(alpha=0): {transparent} ({transparent/total*100:.1f}%)")
    print(f"不透明(alpha>=200): {opaque} ({opaque/total*100:.1f}%)")
    print(f"半透明: {semi} ({semi/total*100:.1f}%)")
    print(f"HSV: H={h:.0f}, S={s:.0f}")
    print(f"文件大小: {dst.stat().st_size} bytes")

    # 对比旧输出
    old = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181_segmented.png')
    if old.exists():
        old_img = cv2.imread(str(old), cv2.IMREAD_UNCHANGED)
        old_alpha = old_img[:,:,3]
        old_transparent = (old_alpha == 0).sum()
        old_opaque = (old_alpha >= 200).sum()
        print(f"\n--- 旧输出对比 ---")
        print(f"透明: {old_transparent/total*100:.1f}%, 不透明: {old_opaque/total*100:.1f}%")
        print(f"旧文件大小: {old.stat().st_size} bytes")
