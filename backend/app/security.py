"""密码哈希与 JWT 工具。

直接使用 bcrypt 库（passlib 1.7.4 与 bcrypt 5.x 不兼容，且 passlib 已停止维护，
故弃用 passlib，改用 bcrypt 原生 API）。
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt

from .config import settings

# bcrypt 单次哈希上限 72 字节。为兼容任意长度密码，先做 sha256+base64 预哈希，
# 再交给 bcrypt。这是避免 72 字节截断的常见做法，且不依赖 passlib。
_PREHASH_LEN = 72  # 仅作文档说明


def _prehash(plain: str) -> bytes:
    """sha256(password) → base64（无填充），固定长度，规避 bcrypt 72 字节上限。"""
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    """明文密码 → bcrypt 哈希字符串。"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(_prehash(plain), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    """签发 JWT。subject 通常为 username。"""
    expire_minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    """解码 JWT，返回 subject（username）；失败返回 None。"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except Exception:
        return None
