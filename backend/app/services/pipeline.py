"""印章上传处理管线编排：原图 → 增强 → 抠图 → 生成 sticker_path。

DESIGN 中处理顺序：EXIF → 地理编码 → 印章增强 → rembg 抠图 → 写库。
本模块聚焦「增强 → 抠图」段；EXIF 与地理编码已在 stamps.py 上传流程中完成。

设计要点：
- 同步执行（个人应用数据量小，单图处理 2-5 秒可接受）
- 异常隔离：任一步骤失败 → process_status='failed'，原图仍可访问
- sticker 失败时 sticker_path=None，前端 image?variant=sticker 返回 404（前端可降级用 original）
"""
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models.stamp import Stamp
from .background_removal import remove_background
from .enhance import enhance_image


def process_pipeline(stamp: Stamp, db: Session) -> None:
    """对已落库的印章执行增强 + 抠图，更新 sticker_path 与 process_status。

    原图路径不变；增强结果与贴纸存到 stamps/sticker/ 下。
    出错不抛异常，仅落 process_status=failed，保证上传主流程不被阻断。
    """
    if not stamp.original_path:
        return

    abs_original = settings._resolve(settings.data_dir) / stamp.original_path
    if not abs_original.exists():
        stamp.process_status = "failed"
        db.commit()
        return

    stamp.process_status = "processing"
    db.commit()

    try:
        # 临时文件名（同名前缀，便于人工排查）
        base = abs_original.stem  # 例：9c18fcea...
        sticker_dir = settings._resolve(settings.sticker_dir)
        enhanced_path = sticker_dir / f"{base}_enhanced.png"
        sticker_path = sticker_dir / f"{base}_sticker.png"

        # 1. 增强（失败时返回原图路径，继续抠图）
        used_enhanced = enhance_image(abs_original, enhanced_path)

        # 2. 抠图（失败返回 None，sticker_path 留空）
        result: Optional[Path] = remove_background(used_enhanced, sticker_path)

        if result is not None:
            # 写相对路径（与 original_path 同样以 stamps/ 起头）
            stamp.sticker_path = f"stamps/sticker/{result.name}"
            stamp.process_status = "done"
        else:
            stamp.sticker_path = None
            stamp.process_status = "failed"  # 抠图失败但增强成功也算可恢复

        db.commit()
    except Exception:
        # 兜底：任何未预期异常都不阻断上传主响应
        stamp.process_status = "failed"
        db.commit()
