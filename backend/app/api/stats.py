"""统计聚合接口：总览 / 月份分布 / 类型分布 / 地区 Top N。

数据量小（个人项目），直接 SQL 聚合，无需缓存层。
所有接口均需登录。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models.stamp import Stamp
from ..models.user import User

router = APIRouter(prefix="/api/stats", tags=["stats"])


class Overview(BaseModel):
    """总览：关键指标卡片。"""

    total: int                    # 印章总数
    cities: int                   # 去重城市数
    regions: int                  # 去重省/大区数
    photo_only: int                # 仅照片打卡数
    with_sticker: int             # 已成功抠图的贴纸数
    earliest_date: Optional[str]  # 最早盖章日期 YYYY-MM-DD
    latest_date: Optional[str]    # 最近盖章日期


class MonthBucket(BaseModel):
    month: str   # YYYY-MM
    count: int


class TypeBucket(BaseModel):
    type: Optional[str]
    count: int


class RegionBucket(BaseModel):
    region: Optional[str]
    count: int


@router.get("/overview", response_model=Overview)
def overview(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Overview:
    """关键指标：总数、城市数、地区数、贴纸数、时间跨度。"""
    total = db.execute(select(func.count(Stamp.id))).scalar_one()

    cities = db.execute(
        select(func.count(func.distinct(Stamp.city))).where(Stamp.city.is_not(None))
    ).scalar_one()

    regions = db.execute(
        select(func.count(func.distinct(Stamp.region))).where(Stamp.region.is_not(None))
    ).scalar_one()

    photo_only = db.execute(
        select(func.count(Stamp.id)).where(Stamp.is_photo_only.is_(True))
    ).scalar_one()

    with_sticker = db.execute(
        select(func.count(Stamp.id)).where(Stamp.sticker_path.is_not(None))
    ).scalar_one()

    earliest = db.execute(select(func.min(Stamp.stamp_date))).scalar()
    latest = db.execute(select(func.max(Stamp.stamp_date))).scalar()

    return Overview(
        total=total,
        cities=cities,
        regions=regions,
        photo_only=photo_only,
        with_sticker=with_sticker,
        earliest_date=earliest.isoformat() if earliest else None,
        latest_date=latest.isoformat() if latest else None,
    )


@router.get("/by-month", response_model=List[MonthBucket])
def by_month(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[MonthBucket]:
    """按月份聚合：补齐无盖章月份为 0，方便折线图渲染。

    用 SQLite 的 substr(stamp_date, 1, 7) 取 YYYY-MM，避免 strftime 跨数据库差异。
    """
    rows = db.execute(
        select(
            func.substr(Stamp.stamp_date, 1, 7).label("month"),
            func.count(Stamp.id).label("cnt"),
        )
        .where(Stamp.stamp_date.is_not(None))
        .group_by("month")
        .order_by("month")
    ).all()

    if not rows:
        return []

    # 补齐中间空缺月份
    result: List[MonthBucket] = []
    prev: Optional[str] = None
    for month, cnt in rows:
        if prev is not None:
            y, m = map(int, prev.split("-"))
            ny, nm = map(int, month.split("-"))
            # 向前推进直到追上当前 month
            while (y, m) < (ny, nm):
                m += 1
                if m > 12:
                    m = 1
                    y += 1
                if (y, m) == (ny, nm):
                    break
                result.append(MonthBucket(month=f"{y:04d}-{m:02d}", count=0))
        result.append(MonthBucket(month=month, count=cnt))
        prev = month
    return result


@router.get("/by-type", response_model=List[TypeBucket])
def by_type(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[TypeBucket]:
    """按类型聚合，按数量倒序。NULL 归类为 '未分类'。"""
    rows = db.execute(
        select(Stamp.type, func.count(Stamp.id))
        .group_by(Stamp.type)
        .order_by(func.count(Stamp.id).desc())
    ).all()
    return [TypeBucket(type=t or "未分类", count=c) for t, c in rows]


@router.get("/by-region", response_model=List[RegionBucket])
def by_region(
    top: int = Query(10, ge=1, le=50, description="返回前 N 个地区，其余归入 Other"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[RegionBucket]:
    """按省/地区聚合 Top N，其余归入 Other（个人项目数量少通常用不到）。"""
    rows = db.execute(
        select(Stamp.region, func.count(Stamp.id).label("cnt"))
        .group_by(Stamp.region)
        .order_by(func.count(Stamp.id).desc())
    ).all()

    result: List[RegionBucket] = []
    other_cnt = 0
    for i, (region, cnt) in enumerate(rows):
        if i < top:
            result.append(RegionBucket(region=region or "未知地区", count=cnt))
        else:
            other_cnt += cnt
    if other_cnt > 0:
        result.append(RegionBucket(region="其他", count=other_cnt))
    return result
