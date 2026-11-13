# app_my/schemas/admin.py
from typing import List, Optional
from pydantic import BaseModel, Field


class AuditLogOut(BaseModel):
    id: int
    tenant_id: Optional[int]
    actor_user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    payload_json: Optional[str]
    created_at: str


class FeatureFlagOut(BaseModel):
    name: str
    enabled: bool
    rollout_pct: int
    whitelist: List[int]
    description: str


class FeatureFlagUpdateIn(BaseModel):
    enabled: bool
    rollout_pct: int = Field(..., ge=0, le=100)
    whitelist: List[int] = []
    description: str = ""