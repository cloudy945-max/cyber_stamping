"""印章记录模型。"""
from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Stamp(Base, TimestampMixin):
    """印章记录主表。P1 仅启用上传必需字段，其余字段在后续阶段补齐。"""

    __tablename__ = "stamps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 图片：原图 + 抠图后贴纸（P2 才会有 sticker_path）
    original_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sticker_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # 时间
    stamp_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    uploaded_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # 地点（P2 由 EXIF+逆地理编码自动填充，P1 可手填）
    location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)

    # 分类
    type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # 内容
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # 套章关联（P4 启用；series 表 P4 才建，此处先留外键但表暂不存在则迁移会报错，
    # 因此 P1 阶段先用 nullable 的整数字段，到 P4 再加 ForeignKey）
    series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    series_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 是否纯照片打卡
    is_photo_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 处理状态：pending / processing / done / failed（P2 管线启用）
    process_status: Mapped[str] = mapped_column(String(16), default="done", nullable=False)
