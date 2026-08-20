"""印章 CRUD 与图片上传/获取路由。"""
import os
import uuid
from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models.stamp import Stamp
from ..models.user import User
from ..schemas.stamp import StampOut, StampUpdate
from ..services.exif import extract_exif
from ..services.geocode import geocode, reverse_geocode
from ..services.pipeline import process_pipeline

router = APIRouter(prefix="/api/stamps", tags=["stamps"])

# 允许的图片扩展名（白名单）
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def _save_original(file: UploadFile) -> str:
    """把上传的图片保存到 original 目录，返回相对项目根的存储路径。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式：{ext}")
    filename = f"{uuid.uuid4().hex}{ext}"
    abs_path = settings._resolve(settings.original_dir) / filename
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    with abs_path.open("wb") as f:
        f.write(file.file.read())
    # 数据库存相对项目根的路径，前端通过 /api/stamps/{id}/image 获取
    return f"stamps/original/{filename}"


@router.post("", response_model=StampOut, status_code=201)
def create_stamp(
    file: UploadFile = File(..., description="印章原图"),
    stamp_date: Optional[date] = Form(None),
    location_name: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    type: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    is_photo_only: bool = Form(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Stamp:
    """上传一枚印章：保存原图 + EXIF 提取 + 地理编码补全 + 写库。

    字段优先级：用户表单输入 > 照片 EXIF > 默认值（today / None）。
    """
    saved_path = _save_original(file)
    today = date.today()

    # 1. EXIF 提取（仅在用户未提供对应字段时才用 EXIF 补全）
    abs_img = settings._resolve(settings.data_dir) / saved_path
    exif = extract_exif(abs_img)
    final_date = stamp_date or exif["stamp_date"] or today
    lat = latitude if latitude is not None else exif["latitude"]
    lng = longitude if longitude is not None else exif["longitude"]

    # 2. 地理编码补全：有经纬度则逆向补地址；有地址无经纬度则正向补坐标
    loc_name, addr, c, r = location_name, address, city, region

    if lat is not None and lng is not None:
        rev = reverse_geocode(lat, lng, db)
        if rev:
            if not addr:
                addr = rev["address"]
            if not c:
                c = rev["city"]
            if not r:
                r = rev["region"]
            if not loc_name:
                loc_name = rev["address"]
    elif addr or loc_name:
        query_addr = addr or loc_name
        fwd = geocode(query_addr or "", db)
        if fwd:
            lat, lng = fwd["latitude"], fwd["longitude"]
            if not c:
                c = fwd["city"]
            if not r:
                r = fwd["region"]
            if not addr:
                addr = fwd["address"]

    stamp = Stamp(
        original_path=saved_path,
        stamp_date=final_date,
        uploaded_at=today,
        location_name=loc_name,
        address=addr,
        city=c,
        region=r,
        latitude=lat,
        longitude=lng,
        type=type,
        notes=notes,
        is_photo_only=is_photo_only,
        process_status="pending",  # 管线跑完改 done/failed
    )
    db.add(stamp)
    db.commit()
    db.refresh(stamp)

    # 同步触发图像处理管线（增强 + 抠图）；异常隔离不阻断主响应
    process_pipeline(stamp, db)
    db.refresh(stamp)
    return stamp


@router.get("", response_model=List[StampOut])
def list_stamps(
    city: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    q: Optional[str] = Query(None, description="关键词（地点名/备注）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> List[Stamp]:
    """列表查询：支持城市/类型/日期范围/关键词筛选 + 分页，按盖章日期倒序。"""
    query = db.query(Stamp)
    if city:
        query = query.filter(Stamp.city == city)
    if type:
        query = query.filter(Stamp.type == type)
    if date_from:
        query = query.filter(Stamp.stamp_date >= date_from)
    if date_to:
        query = query.filter(Stamp.stamp_date <= date_to)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Stamp.location_name.ilike(like)) | (Stamp.notes.ilike(like))
        )
    query = query.order_by(Stamp.stamp_date.desc(), Stamp.id.desc())
    offset = (page - 1) * page_size
    return query.offset(offset).limit(page_size).all()


@router.get("/{stamp_id}", response_model=StampOut)
def get_stamp(
    stamp_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Stamp:
    stamp = db.get(Stamp, stamp_id)
    if not stamp:
        raise HTTPException(status_code=404, detail="印章不存在")
    return stamp


@router.put("/{stamp_id}", response_model=StampOut)
def update_stamp(
    stamp_id: int,
    payload: StampUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Stamp:
    stamp = db.get(Stamp, stamp_id)
    if not stamp:
        raise HTTPException(status_code=404, detail="印章不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(stamp, k, v)
    db.commit()
    db.refresh(stamp)
    return stamp


@router.delete("/{stamp_id}", status_code=204)
def delete_stamp(
    stamp_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    stamp = db.get(Stamp, stamp_id)
    if not stamp:
        raise HTTPException(status_code=404, detail="印章不存在")
    # 删除关联图片文件（original_path / sticker_path 均相对 data_dir 存储）
    for rel in (stamp.original_path, stamp.sticker_path):
        if not rel:
            continue
        candidate = settings._resolve(settings.data_dir) / rel
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError:
                pass
    db.delete(stamp)
    db.commit()


@router.get("/{stamp_id}/image")
def get_stamp_image(
    stamp_id: int,
    variant: str = Query("original", pattern="^(original|sticker)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> FileResponse:
    """获取图片（原图或贴纸）。需登录。"""
    stamp = db.get(Stamp, stamp_id)
    if not stamp:
        raise HTTPException(status_code=404, detail="印章不存在")
    rel = stamp.original_path if variant == "original" else stamp.sticker_path
    if not rel:
        raise HTTPException(status_code=404, detail="该变体图片不存在")
    abs_path = settings._resolve(settings.data_dir) / rel
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="图片文件缺失")
    # no-store：避免浏览器缓存含 access_token 的图片响应
    # （token 过期后旧缓存会 401，且 URL 含 token 不宜缓存）
    return FileResponse(abs_path, headers={"Cache-Control": "no-store"})


@router.post("/{stamp_id}/reprocess", response_model=StampOut)
def reprocess_stamp(
    stamp_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Stamp:
    """重跑图像处理管线（调整增强参数后或上次失败时调用）。原图不丢。"""
    stamp = db.get(Stamp, stamp_id)
    if not stamp:
        raise HTTPException(status_code=404, detail="印章不存在")
    process_pipeline(stamp, db)
    db.refresh(stamp)
    return stamp
