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
    """上传一枚印章：保存原图 + 写库。P2 会在此之后触发处理管线。"""
    saved_path = _save_original(file)
    today = date.today()
    stamp = Stamp(
        original_path=saved_path,
        stamp_date=stamp_date or today,
        uploaded_at=today,
        location_name=location_name,
        address=address,
        city=city,
        region=region,
        latitude=latitude,
        longitude=longitude,
        type=type,
        notes=notes,
        is_photo_only=is_photo_only,
        process_status="done",  # P1 直接 done；P2 改为 pending 由管线异步处理
    )
    db.add(stamp)
    db.commit()
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
    return FileResponse(abs_path)
