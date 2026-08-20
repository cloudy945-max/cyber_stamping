"""EXIF 元数据提取：从图片读取盖章日期与 GPS 坐标。

仅依赖 Pillow（已在 requirements.txt 中）。
- DateTimeOriginal（在 Exif 子 IFD 中，标签 36867）→ 盖章日期
- GPSInfo（在 GPS 子 IFD 中，通过 IFD.GPSInfo 访问）→ 经纬度

EXIF 缺失或解析失败时返回 None 字段，调用方按降级链处理。
"""
from datetime import date, datetime
from pathlib import Path
from typing import Optional, TypedDict


class ExifResult(TypedDict):
    """EXIF 提取结果：缺失字段为 None。"""

    stamp_date: Optional[date]
    latitude: Optional[float]
    longitude: Optional[float]


def _parse_date(raw) -> Optional[date]:
    """EXIF 日期格式 'YYYY:MM:DD HH:MM:SS' → date。"""
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").date()
    except (ValueError, TypeError):
        return None


def _gps_to_decimal(value) -> Optional[float]:
    """度分秒（3 个 IFDRational）→ 十进制。"""
    try:
        d, m, s = value
        deg = float(d)
        minute = float(m)
        sec = float(s)
        return deg + minute / 60.0 + sec / 3600.0
    except (ValueError, TypeError, IndexError):
        return None


def extract_exif(file_path: Path) -> ExifResult:
    """从图片文件提取 EXIF。失败时所有字段返回 None。"""
    result: ExifResult = {"stamp_date": None, "latitude": None, "longitude": None}

    try:
        from PIL import Image
        from PIL.ExifTags import IFD

        with Image.open(file_path) as img:
            exif = img.getexif()
            if not exif:
                return result

            # 1. 主 IFD 中的 DateTime（兼容老相机没写 DateTimeOriginal 的场景）
            raw_date_main = exif.get(306)

            # 2. Exif 子 IFD：DateTimeOriginal（36867）/ DateTimeDigitized（36868）
            exif_ifd: dict = {}
            try:
                exif_ifd = exif.get_ifd(IFD.Exif) or {}
            except Exception:
                exif_ifd = {}
            raw_date = exif_ifd.get(36867) or exif_ifd.get(36868) or raw_date_main
            result["stamp_date"] = _parse_date(raw_date)

            # 3. GPS 子 IFD
            gps: dict = {}
            try:
                gps = exif.get_ifd(IFD.GPSInfo) or {}
            except Exception:
                gps = {}
            if gps:
                lat_val = gps.get(2)
                lat_ref = gps.get(1)
                lng_val = gps.get(4)
                lng_ref = gps.get(3)

                if lat_val is not None:
                    lat = _gps_to_decimal(lat_val)
                    if lat is not None and lat_ref == "S":
                        lat = -lat
                    result["latitude"] = lat

                if lng_val is not None:
                    lng = _gps_to_decimal(lng_val)
                    if lng is not None and lng_ref == "W":
                        lng = -lng
                    result["longitude"] = lng

    except Exception:
        # 非图片、损坏文件、无权限等，均按无 EXIF 处理，不阻断上传
        pass

    return result
