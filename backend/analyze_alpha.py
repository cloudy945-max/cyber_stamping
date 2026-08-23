"""分析新输出 PNG 的圆形内外 alpha 分布"""
import cv2, numpy as np

img = cv2.imread(r'test_output/module_test/8181_new.png', cv2.IMREAD_UNCHANGED)
alpha = img[:,:,3]
H, W = alpha.shape

# 印章圆心（从日志获取）: 大约在全图中心
# 8181.jpg 尺寸 4032x3024，印章在右下区域
# 从之前的分析 stamp_cx=1364, stamp_cy=1851 是 ROI 坐标
# 但这里没有 bbox，ROI 就是全图
# 让我找到 alpha 的质心
ys, xs = np.where(alpha > 100)
cx = int(xs.mean())
cy = int(ys.mean())
# 找最大半径
dist = np.sqrt((xs - cx)**2 + (ys - cy)**2)
r_max = int(np.percentile(dist, 95))
print(f"alpha 质心: ({cx}, {cy}), 95%半径: {r_max}")

# 圆形内外统计
Y, X = np.ogrid[:H, :W]
d = np.sqrt((X - cx)**2 + (Y - cy)**2)
inside = d <= r_max
outside = d > r_max

print(f"\n圆形内 (r={r_max}):")
in_total = inside.sum()
in_transparent = ((alpha == 0) & inside).sum()
in_opaque = ((alpha >= 200) & inside).sum()
print(f"  透明: {in_transparent/in_total*100:.1f}%")
print(f"  不透明: {in_opaque/in_total*100:.1f}%")

print(f"\n圆形外:")
out_total = outside.sum()
out_opaque = ((alpha >= 200) & outside).sum()
out_semi = ((alpha > 0) & (alpha < 200) & outside).sum()
print(f"  不透明: {out_opaque/out_total*100:.1f}% ({out_opaque} px)")
print(f"  半透明: {out_semi/out_total*100:.1f}% ({out_semi} px)")
