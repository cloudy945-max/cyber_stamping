"""分析 rembg 抠图结果：alpha 通道分布、前景区域、是否成功抠出印章。"""
from pathlib import Path

import numpy as np
from PIL import Image

sticker = Path(r"d:\projects\cyber_stamping\backend\test_output\8181_sticker.png")
original = Path(r"d:\projects\cyber_stamping\backend\test_output\8181_original.jpg")

with Image.open(sticker) as img:
    arr = np.array(img)
    alpha = arr[:, :, 3]

H, W = alpha.shape
total = H * W

# alpha 分布
fully_transparent = (alpha == 0).sum()
fully_opaque = (alpha == 255).sum()
partial = ((alpha > 0) & (alpha < 255)).sum()

print("=" * 60)
print("rembg 抠图结果分析")
print("=" * 60)
print(f"尺寸: {W} x {H}")
print(f"完全透明 (α=0):   {fully_transparent:>10} ({fully_transparent/total*100:.1f}%)")
print(f"完全不透明 (α=255): {fully_opaque:>10} ({fully_opaque/total*100:.1f}%)")
print(f"半透明 (0<α<255):  {partial:>10} ({partial/total*100:.1f}%)")

# 前景连通区域分析
from scipy import ndimage

binary = alpha > 128
labeled, num_features = ndimage.label(binary)
print(f"\n前景连通块数量: {num_features}")

if num_features > 0:
    # 每个连通块的面积
    sizes = ndimage.sum(binary, labeled, range(1, num_features + 1))
    sizes_sorted = np.sort(sizes)[::-1]
    print("前 5 大连通块面积:")
    for i, s in enumerate(sizes_sorted[:5]):
        print(f"  #{i+1}: {int(s)} 像素 ({s/total*100:.2f}%)")

    # 最大块（可能是印章主体）的边界框
    largest_idx = np.argmax(sizes) + 1
    slices = ndimage.find_objects(labeled == largest_idx)[0]
    y0, y1 = slices[0].start, slices[0].stop
    x0, x1 = slices[1].start, slices[1].stop
    print(f"\n最大块边界框: x=[{x0},{x1}], y=[{y0},{y1}]")
    print(f"最大块尺寸: {x1-x0} x {y1-y0}")
    print(f"占图比例: 宽{(x1-x0)/W*100:.1f}% 高{(y1-y0)/H*100:.1f}%")

# 裁剪最大块保存，便于查看
if num_features > 0:
    crop = Image.open(sticker).crop((max(0, x0-20), max(0, y0-20), min(W, x1+20), min(H, y1+20)))
    crop_path = Path(r"d:\projects\cyber_stamping\backend\test_output\8181_largest_blob.png")
    crop.save(crop_path)
    print(f"\n最大块裁剪已保存: {crop_path}")

# 同时保存 alpha 通道可视化
alpha_vis = Image.fromarray(alpha)
alpha_path = Path(r"d:\projects\cyber_stamping\backend\test_output\8181_alpha.png")
alpha_vis.save(alpha_path)
print(f"alpha 通道已保存: {alpha_path}")
