# app_my/schemas/auth.py
"""
阶段 4：认证相关的 Pydantic 模型。
只描述“接口进出的数据长什么样”，不连接数据库。
"""

from typing import Optional
from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    """注册请求：用户名 + 密码 + 可选邮箱。"""
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=8, description="密码")
    email: Optional[str] = Field(None, description="可选邮箱")


class LoginIn(BaseModel):
    """登录请求：用户名 + 密码。"""
    username: str
    password: str


class RefreshIn(BaseModel):
    """续签请求：refresh token。"""
    refresh_token: str


class TokenPair(BaseModel):
    """登录/注册/续签的响应：两枚 token + 有效期。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


class UserOut(BaseModel):
    """/users/me 返回的用户信息。"""
    id: int
    username: str
    email: Optional[str]

    model_config = {"from_attributes": True}
