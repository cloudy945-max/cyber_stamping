"""认证相关 Pydantic 模型。"""
from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    expires_in: Optional[int] = None  # 秒


class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True
