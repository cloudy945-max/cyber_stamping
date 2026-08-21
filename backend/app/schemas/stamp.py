"""印章相关 Pydantic 模型。"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StampBase(BaseModel):
    """印章记录共享字段。"""

    stamp_date: Optional[date] = None
    country: Optional[str] = None
    location_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    type: Optional[str] = None
    notes: Optional[str] = None
    is_photo_only: bool = False


class StampCreate(StampBase):
    """上传时通过表单字段提交的元数据（图片以 UploadFile 单独传）。"""


class StampUpdate(BaseModel):
    """部分更新；所有字段可选。"""

    stamp_date: Optional[date] = None
    country: Optional[str] = None
    location_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    type: Optional[str] = None
    notes: Optional[str] = None
    is_photo_only: Optional[bool] = None


class StampOut(StampBase):
    """响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_path: str
    sticker_path: Optional[str] = None
    process_status: str
