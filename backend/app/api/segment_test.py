"""印章分割测试 API（独立于现有上传流程）。

端点：
- POST /api/segment-test  上传图片 + 可选 bbox → 返回分割后的 PNG

测试用，跑通后整合到正式上传流程。
"""
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image

from ..config import settings
from ..deps import get_current_user
from ..models.user import User
from ..services.stamp_segment import segment_stamp, segment_stamp_v2

router = APIRouter(prefix="/api/segment-test", tags=["segment-test"])

# 临时目录，存放分割中间文件
_TMP = settings._resolve(settings.data_dir) / "segment_test_tmp"
_TMP.mkdir(parents=True, exist_ok=True)


def _to_png(upload: UploadFile) -> Path:
    """把上传图片转为 PNG 临时文件（统一后续处理输入）。"""
    # 用 PIL 打开（支持 HEIC 等格式，main.py 已注册 heif opener）
    img = Image.open(upload.file)
    if img.mode != "RGB":
        img = img.convert("RGB")
    tmp = _TMP / f"{uuid.uuid4().hex}.png"
    img.save(tmp, "PNG")
    return tmp


@router.post("")
async def segment_test(
    file: UploadFile = File(..., description="印章照片"),
    bbox_x0: Optional[int] = Form(None),
    bbox_y0: Optional[int] = Form(None),
    bbox_x1: Optional[int] = Form(None),
    bbox_y1: Optional[int] = Form(None),
    color: str = Form("red"),
    method: str = Form("extractor"),
    preset: str = Form("default"),
    _: User = Depends(get_current_user),
):
    """上传图片 + 可选框选区域 → 返回分割后的透明背景 PNG。

    bbox 四个字段都提供时才生效；color 支持 red/blue/black。
    method: extractor（高保真 Alpha，新） / legacy（R-G+rembg，旧）。
    preset: default / preserve_light / conservative（仅 extractor 模式）。
    """
    try:
        src = _to_png(file)
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": f"图片读取失败：{e}"})

    bbox = None
    if all(v is not None for v in (bbox_x0, bbox_y0, bbox_x1, bbox_y1)):
        bbox = (bbox_x0, bbox_y0, bbox_x1, bbox_y1)  # type: ignore[assignment]

    dst = _TMP / f"{src.stem}_seg.png"
    if method == "legacy":
        result = segment_stamp(src, dst, bbox=bbox, color=color)
    else:
        result = segment_stamp_v2(src, dst, bbox=bbox, preset=preset)

    if result is None:
        return JSONResponse(
            status_code=422,
            content={"detail": "未检测到指定颜色区域，请尝试框选印章位置或更换颜色"},
        )

    return FileResponse(
        path=str(result),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
