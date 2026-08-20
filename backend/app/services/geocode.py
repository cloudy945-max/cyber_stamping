"""高德 Web 服务 API 地理编码：正向（地址→经纬度）+ 逆向（经纬度→地址）。

带本地 SQLite 缓存，未配置 AMAP_KEY 时优雅降级（返回 None，不阻断上传流程）。

文档：
- 正向：https://restapi.amap.com/v3/geocode/geo
- 逆向：https://restapi.amap.com/v3/geocode/regeo
"""
import json
from typing import Optional, TypedDict

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.geocode_cache import GeocodeCache


class GeocodeResult(TypedDict):
    """标准化地理编码结果（正向/逆向统一字段）。"""

    latitude: float
    longitude: float
    country: Optional[str]
    region: Optional[str]  # 省
    city: Optional[str]
    address: Optional[str]


def _cache_key_geocode(address: str) -> str:
    return f"geo:{address.strip()}"


def _cache_key_regeocode(lat: float, lng: float) -> str:
    # 经纬度精度截到 6 位，避免微小抖动产生过多缓存项
    return f"regeo:{round(lat, 6)},{round(lng, 6)}"


def _get_cache(db: Session, key: str) -> Optional[GeocodeResult]:
    row = db.execute(select(GeocodeCache).where(GeocodeCache.key == key)).scalar_one_or_none()
    if not row:
        return None
    try:
        return GeocodeResult(**json.loads(row.value))
    except (json.JSONDecodeError, TypeError):
        return None


def _set_cache(db: Session, key: str, value: GeocodeResult) -> None:
    row = db.execute(
        select(GeocodeCache).where(GeocodeCache.key == key)
    ).scalar_one_or_none()
    payload = json.dumps(value, ensure_ascii=False)
    if row:
        row.value = payload
    else:
        db.add(GeocodeCache(key=key, value=payload))
    db.commit()


def geocode(address: str, db: Session) -> Optional[GeocodeResult]:
    """正向地理编码：地址 → 经纬度 + 行政区划。无 AMAP_KEY 返回 None。"""
    if not address or not settings.amap_key:
        return None

    key = _cache_key_geocode(address)
    cached = _get_cache(db, key)
    if cached:
        return cached

    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"key": settings.amap_key, "address": address},
            timeout=5.0,
        )
        data = resp.json()
    except (httpx.RequestError, ValueError):
        return None

    if data.get("status") != "1" or not data.get("geocodes"):
        return None

    g = data["geocodes"][0]
    try:
        lng, lat = g["location"].split(",")
    except (KeyError, ValueError, AttributeError):
        return None

    result = GeocodeResult(
        latitude=float(lat),
        longitude=float(lng),
        country=g.get("country"),
        region=g.get("province"),
        city=g.get("city") or g.get("district"),
        address=g.get("formatted_address"),
    )
    _set_cache(db, key, result)
    return result


def reverse_geocode(lat: float, lng: float, db: Session) -> Optional[GeocodeResult]:
    """逆向地理编码：经纬度 → 地址 + 行政区划。无 AMAP_KEY 返回 None。"""
    if not settings.amap_key:
        return None

    key = _cache_key_regeocode(lat, lng)
    cached = _get_cache(db, key)
    if cached:
        return cached

    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/regeo",
            params={"key": settings.amap_key, "location": f"{lng},{lat}"},
            timeout=5.0,
        )
        data = resp.json()
    except (httpx.RequestError, ValueError):
        return None

    if data.get("status") != "1" or not data.get("regeocode"):
        return None

    rg = data["regeocode"]
    comp = rg.get("addressComponent") or {}

    result = GeocodeResult(
        latitude=lat,
        longitude=lng,
        country=comp.get("country"),
        region=comp.get("province"),
        city=comp.get("city") or comp.get("district"),
        address=rg.get("formatted_address"),
    )
    _set_cache(db, key, result)
    return result
