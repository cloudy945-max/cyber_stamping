"""ORM 模型聚合导入：方便 `from app.models import Base, User, Stamp`。"""
from .base import Base
from .user import User
from .stamp import Stamp

__all__ = ["Base", "User", "Stamp"]
