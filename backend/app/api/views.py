"""聚合视图接口：地图标记点等只读视图。"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models.stamp import Stamp
from ..models.user import User

router = APIRouter(prefix="/api/views", tags=["views"])


class MapPoint(BaseModel):
    """地图标记点：最小字段集，前端按需用 id 再拉详情或图片。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: float
    longitude: float
    location_name: Optional[str] = None
    type: Optional[str] = None
    city: Optional[str] = None
    stamp_date: Optional[date] = None
    is_photo_only: bool = False


@router.get("/map/points", response_model=List[MapPoint])
def map_points(
    city: Optional[str] = Query(None, description="按城市筛选"),
    type: Optional[str] = Query(None, description="按类型筛选"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[Stamp]:
    """返回所有有经纬度的印章，供前端在地图上点 marker。"""
    stmt = (
        select(Stamp)
        .where(Stamp.latitude.is_not(None))
        .where(Stamp.longitude.is_not(None))
        .order_by(Stamp.stamp_date.desc())
    )
    if city:
        stmt = stmt.where(Stamp.city == city)
    if type:
        stmt = stmt.where(Stamp.type == type)
    return db.execute(stmt).scalars().all()
