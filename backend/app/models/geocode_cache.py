"""高德地理编码缓存表（正向 + 逆向共用一张表）。

key 列存放缓存键：
- 正向：`geo:<address>`
- 逆向：`regeo:<lat,lng精度6位>`

value 列存放 JSON 字符串，含 lat/lng/region/city/address 等字段。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GeocodeCache(Base):
    """地理编码结果本地缓存，避免对高德 API 重复调用。"""

    __tablename__ = "geocode_cache"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=True
    )
