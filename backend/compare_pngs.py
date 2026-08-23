"""直接对比两个 PNG 文件的墨水颜色"""
import cv2, numpy as np, os

# 1. 本地调用 segment_stamp 输出（已知红色 H=172）
p1 = r'test_output/module_test/8181_segmented.png'
# 2. API 返回的输出
p2 = r'test_output/api_test/api_no_bbox.png'

print(f"{' 文件':<35} | H mean | S mean | V mean | 判定")
print('-'*80)
for label, p in [('local segment_stamp', p1), ('API /segment-test', p2)]:
    if not os.path.exists(p):
        print(f"{label:<35} | 不存在")
        continue
    img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    alpha = img[:,:,3]
    strong = alpha >= 128
    hsv = cv2.cvtColor(img[:,:,0:3], cv2.COLOR_BGR2HSV)
    if strong.sum() > 0:
        h = hsv[strong][:,0].mean()
        s = hsv[strong][:,1].mean()
        v = hsv[strong][:,2].mean()
        if 160 <= h <= 179 or h <= 15:
            verdict = '红色 ✅'
        elif 80 <= h <= 130:
            verdict = '蓝青 ❌'
        else:
            verdict = '其他'
        size = os.path.getsize(p)
        print(f"{label:<35} | {h:6.1f} | {s:6.1f} | {v:6.1f} | {verdict} ({size} bytes)")
