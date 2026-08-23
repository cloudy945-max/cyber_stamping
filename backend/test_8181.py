"""测试 IMG_8181.HEIC：1) EXIF GPS 2) rembg 抠图效果。

运行：python test_8181.py
"""
import sys
from pathlib import Path

# 确保导入 backend 包
sys.path.insert(0, str(Path(__file__).parent))

import pillow_heif

pillow_heif.register_heif_opener()

from PIL import Image

from app.services.exif import extract_exif

HEIC = Path(r"d:\projects\cyber_stamping\IMG_8181.HEIC")
OUT_DIR = Path(r"d:\projects\cyber_stamping\backend\test_output")
OUT_DIR.mkdir(exist_ok=True)


# 1. EXIF GPS
print("=" * 60)
print("1. EXIF GPS 提取")
print("=" * 60)
exif = extract_exif(HEIC)
print(f"日期: {exif['stamp_date']}")
print(f"纬度: {exif['latitude']}")
print(f"经度: {exif['longitude']}")
if exif["latitude"] and exif["longitude"]:
    print(
        f"Google Maps: https://www.google.com/maps?q={exif['latitude']},{exif['longitude']}"
    )
    print(
        f"高德地图:   https://uri.amap.com/marker?position={exif['longitude']},{exif['latitude']}"
    )

# 2. 转换 HEIC → JPEG
print("\n" + "=" * 60)
print("2. HEIC → JPEG 转换")
print("=" * 60)
jpg_path = OUT_DIR / "8181_original.jpg"
with Image.open(HEIC) as img:
    print(f"原始尺寸: {img.size}, 模式: {img.mode}")
    rgb = img.convert("RGB")
    rgb.save(jpg_path, "JPEG", quality=92)
print(f"已保存: {jpg_path}")

# 3. rembg 抠图
print("\n" + "=" * 60)
print("3. rembg 抠图测试")
print("=" * 60)
from app.services.background_removal import remove_background, _get_session, _u2net_home

print(f"U2NET_HOME: {_u2net_home()}")
session = _get_session()
print(f"rembg session: {'available' if session else 'NOT AVAILABLE'}")

if session:
    sticker_path = OUT_DIR / "8181_sticker.png"
    result = remove_background(jpg_path, sticker_path)
    if result:
        with Image.open(result) as out:
            print(f"抠图结果尺寸: {out.size}, 模式: {out.mode}")
        print(f"已保存: {result}")
    else:
        print("抠图失败")
else:
    print("跳过抠图：模型未就位")
