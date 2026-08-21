"""地理编码：正向（地址→经纬度）+ 逆向（经纬度→地址）。

多源策略，保证全球覆盖：
- 高德 API：国内精度最高，已配置 AMAP_KEY 时优先使用
- BigDataCloud：全球免费、无需 key、国内可访问，高德未覆盖时兜底

带本地 SQLite 缓存，所有源共享同一缓存键。
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
    region: Optional[str]  # 省/州
    city: Optional[str]
    address: Optional[str]


def _cache_key_geocode(address: str) -> str:
    return f"geo:{address.strip()}"


def _str(v) -> Optional[str]:
    """高德 API 海外查询时某些字段返回 [] 而非字符串，统一规整为 str | None。"""
    if isinstance(v, str) and v:
        return v
    return None


def _cache_key_regeocode(lat: float, lng: float) -> str:
    # 经纬度精度截到 6 位，避免微小抖动产生太多缓存项
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


# ---------------------------- 高德 ----------------------------

def _amap_geocode(address: str) -> Optional[GeocodeResult]:
    """高德正向地理编码。"""
    if not settings.amap_key:
        return None
    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"key": settings.amap_key, "address": address},
            timeout=10.0,
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
    return GeocodeResult(
        latitude=float(lat),
        longitude=float(lng),
        country=_str(g.get("country")),
        region=_str(g.get("province")),
        city=_str(g.get("city")) or _str(g.get("district")),
        address=_str(g.get("formatted_address")),
    )


def _amap_reverse_geocode(lat: float, lng: float) -> Optional[GeocodeResult]:
    """高德逆向地理编码。国内精度最高。"""
    if not settings.amap_key:
        return None
    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/regeo",
            params={"key": settings.amap_key, "location": f"{lng},{lat}"},
            timeout=10.0,
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
        country=_str(comp.get("country")),
        region=_str(comp.get("province")),
        city=_str(comp.get("city")) or _str(comp.get("district")),
        address=_str(rg.get("formatted_address")),
    )
    # 高德对海外返回字段为 []，若没有任何有用信息则视为失败
    if not any([result["country"], result["region"], result["city"], result["address"]]):
        return None
    # 高德只覆盖国内，成功即说明在国内，country 缺省填"中国"
    if not result["country"]:
        result["country"] = "中国"
    return result


# ---------------------------- BigDataCloud（全球兜底） ----------------------------

def _bdc_reverse_geocode(lat: float, lng: float) -> Optional[GeocodeResult]:
    """BigDataCloud 逆向地理编码。全球覆盖，无需 key，国内可访问。

    文档：https://www.bigdatacloud.com/reverse-geocode
    """
    try:
        resp = httpx.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lng, "localityLanguage": "zh"},
            timeout=10.0,
            follow_redirects=True,
        )
        data = resp.json()
    except (httpx.RequestError, ValueError):
        return None

    country = _str(data.get("countryName"))
    region = _str(data.get("principalSubdivision"))
    city = _str(data.get("city")) or _str(data.get("locality"))
    # 详细地址：拼接 市 + 区
    parts = []
    if city:
        parts.append(city)
    locality = _str(data.get("locality"))
    if locality and locality != city:
        parts.append(locality)
    address_str = "".join(parts) if parts else None

    if not any([country, region, city, address_str]):
        return None
    return GeocodeResult(
        latitude=lat,
        longitude=lng,
        country=country,
        region=region,
        city=city,
        address=address_str,
    )


def _bdc_geocode(address: str) -> Optional[GeocodeResult]:
    """BigDataCloud 正向地理编码（search）。

    使用 BigDataCloud 的 geocode 接口，需免费 key（此处简化为走逆向兜底，
    正向仍以高德优先）。
    """
    # BigDataCloud 正向需要 API key，此处仅作为逆向兜底
    return None


# ---------------------------- 对外接口（多源 fallback） ----------------------------

def geocode(address: str, db: Session) -> Optional[GeocodeResult]:
    """正向地理编码：地址 → 经纬度 + 行政区划。

    优先高德（国内精度高），失败回退 BigDataCloud。两者均失败返回 None。
    """
    if not address:
        return None

    key = _cache_key_geocode(address)
    cached = _get_cache(db, key)
    if cached:
        return cached

    # 1. 高德优先
    result = _amap_geocode(address)
    # 2. 回退 BigDataCloud（正向暂未实现，仅逆向可用）
    if result is None:
        result = _bdc_geocode(address)

    if result is not None:
        _set_cache(db, key, result)
    return result


def reverse_geocode(lat: float, lng: float, db: Session) -> Optional[GeocodeResult]:
    """逆向地理编码：经纬度 → 地址 + 行政区划，全球覆盖。

    策略：高德（国内准）→ 失败回退 BigDataCloud（全球）。两者均失败返回 None。
    """
    key = _cache_key_regeocode(lat, lng)
    cached = _get_cache(db, key)
    if cached:
        return cached

    # 1. 高德优先（国内精度最高，且无速率限制）
    result = _amap_reverse_geocode(lat, lng)
    # 2. 高德未覆盖（海外/无key）→ BigDataCloud 兜底
    if result is None:
        result = _bdc_reverse_geocode(lat, lng)

    if result is not None:
        _set_cache(db, key, result)
    return result
