"""测试正式模块 stamp_segment.py：验证 bbox 框选分割效果。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pillow_heif

pillow_heif.register_heif_opener()

from PIL import Image

from app.services.stamp_segment import segment_stamp

HEIC = Path(r"d:\projects\cyber_stamping\IMG_8181.HEIC")
OUT = Path(r"d:\projects\cyber_stamping\backend\test_output\module_test")
OUT.mkdir(parents=True, exist_ok=True)

# 转 JPEG（模拟上传后的原图）
jpg = OUT / "8181.jpg"
with Image.open(HEIC) as img:
    img.convert("RGB").save(jpg, "JPEG", quality=92)

# 测试 1：无 bbox（全图自动分割）
print("=" * 50)
print("测试1: 无 bbox 全图分割")
print("=" * 50)
dst1 = OUT / "no_bbox.png"
r1 = segment_stamp(jpg, dst1, bbox=None, color="red")
print(f"结果: {r1}")

# 测试 2：带 bbox（模拟用户框选印章区域）
# 根据之前分析印章边界框 x=[693,2036] y=[1291,2412]，稍放宽
print("\n" + "=" * 50)
print("测试2: 带 bbox 框选分割")
print("=" * 50)
bbox = (600, 1200, 2100, 2500)  # (x0, y0, x1, y1)
dst2 = OUT / "with_bbox.png"
r2 = segment_stamp(jpg, dst2, bbox=bbox, color="red")
print(f"结果: {r2}")

print(f"\n输出目录: {OUT}")
