"""FastAPI 依赖注入。"""
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models.user import User
from .security import decode_access_token

# tokenUrl 指向登录接口路径
# auto_error=False：header 无 token 时不立即抛 401，交给 get_current_user 统一处理
# （这样 <img src> 标签可以通过 query 参数 access_token 传 token）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    access_token: Optional[str] = Query(
        None,
        description="备用：通过 query 参数传 token，供 <img src> 等无法设置 header 的场景使用",
    ),
    db: Session = Depends(get_db),
) -> User:
    """从 JWT 解析当前用户。未登录或用户不存在则 401。

    支持两种 token 传递方式：
    1. 标准 Authorization: Bearer <token> header（axios/fetch）
    2. query 参数 ?access_token=<token>（<img src>、<a href> 等浏览器原生标签）
    """
    actual_token = token or access_token
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未能验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not actual_token:
        raise credentials_exc
    username = decode_access_token(actual_token)
    if not username:
        raise credentials_exc
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise credentials_exc
    return user
