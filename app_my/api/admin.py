# app_my/api/admin.py
"""/admin/* 管理端：审计日志 + Feature Flag。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_my.core.audit import log_audit
from app_my.core.feature_flag import invalidate_cache
from app_my.db.models.audit_log import AuditLog
from app_my.db.models.feature_flag import FeatureFlag
from app_my.db.session import get_db
from app_my.schemas.admin import AuditLogOut, FeatureFlagOut, FeatureFlagUpdateIn

router = APIRouter()


def _require_admin(request: Request, db: Session, tenant_id: int):
    """admin 路由要求当前用户在该 tenant 是 owner 或 admin。"""
    from app_my.db.models.tenant_member import TenantMember
    user_id = getattr(request.state, "user_id", None)
    m = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == user_id)
        )
    )
    if m is None or m.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="需要 owner 或 admin 权限")
    return user_id


@router.get("/audit/logs", response_model=List[AuditLogOut])
def list_audit_logs(request: Request, tenant_id: int, db: Session = Depends(get_db), limit: int = 50):
    _require_admin(request, db, tenant_id)
    rows = db.scalars(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()
    return [AuditLogOut(
        id=r.id, tenant_id=r.tenant_id, actor_user_id=r.actor_user_id,
        action=r.action, resource_type=r.resource_type, resource_id=r.resource_id,
        payload_json=r.payload_json, created_at=r.created_at.isoformat(),
    ) for r in rows]


@router.get("/feature-flags", response_model=List[FeatureFlagOut])
def list_flags(db: Session = Depends(get_db)):
    rows = db.scalars(select(FeatureFlag).order_by(FeatureFlag.name)).all()
    import json
    out = []
    for r in rows:
        try:
            wl = json.loads(r.whitelist_tenants or "[]")
        except json.JSONDecodeError:
            wl = []
        out.append(FeatureFlagOut(name=r.name, enabled=r.enabled, rollout_pct=r.rollout_pct, whitelist=wl, description=r.description))
    return out


@router.post("/feature-flags/{name}", response_model=FeatureFlagOut)
def upsert_flag(name: str, payload: FeatureFlagUpdateIn, db: Session = Depends(get_db)):
    import json
    row = db.scalar(select(FeatureFlag).where(FeatureFlag.name == name))
    if row is None:
        row = FeatureFlag(name=name)
        db.add(row)
    row.enabled = payload.enabled
    row.rollout_pct = payload.rollout_pct
    row.whitelist_tenants = json.dumps(payload.whitelist)
    row.description = payload.description
    db.commit()
    invalidate_cache(name)
    log_audit(db, action="feature_flag.update", actor_user_id=None, resource_type="feature_flag", resource_id=name,
              payload={"enabled": payload.enabled, "rollout_pct": payload.rollout_pct})
    return FeatureFlagOut(name=row.name, enabled=row.enabled, rollout_pct=row.rollout_pct,
                          whitelist=payload.whitelist, description=row.description)