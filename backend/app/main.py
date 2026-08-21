"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

# 注册 HEIC/HEIF 支持（iPhone 默认格式），须在导入 PIL 前执行
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .api import auth, stamps, stats, views
from .config import settings
from .database import SessionLocal
from .models.base import Base
from .models.geocode_cache import GeocodeCache  # noqa: F401  注册到 Base.metadata
from .models.stamp import Stamp  # noqa: F401  确保被 import 以注册到 Base.metadata
from .models.user import User  # noqa: F401
from .security import hash_password


def _init_db() -> None:
    """建表 + 初始化管理员账号（仅 P1 用 create_all；P2 起用 Alembic 迁移）。"""
    from .database import engine

    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.admin_username).first()
        if not existing:
            db.add(User(username=settings.admin_username, password_hash=hash_password(settings.admin_password)))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动与关闭钩子。"""
    settings.ensure_dirs()
    _init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

# 跨域：开发期放行 Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stamps.router)
app.include_router(stats.router)
app.include_router(views.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"app": settings.app_name, "status": "ok"}
