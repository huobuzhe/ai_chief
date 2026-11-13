# app_my/schemas/tenant.py
from typing import Literal, List
from pydantic import BaseModel, Field


class TenantOut(BaseModel):
    id: int
    name: str
    type: Literal["personal", "team"]
    plan: Literal["free", "pro", "enterprise"]
    role: str = Field(..., description="当前用户在该租户的角色")


class TenantCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class MemberOut(BaseModel):
    user_id: int
    username: str
    role: str
    joined_at: str


class MemberInviteIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    role: Literal["admin", "member"] = "member"


class QuotaOut(BaseModel):
    plan: str
    metrics: dict