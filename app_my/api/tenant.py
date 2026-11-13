# app_my/api/tenant.py
"""/tenants/* 租户管理接口。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_my.core.audit import log_audit
from app_my.core.quota import QUOTAS, get_usage
from app_my.db.models.user import User
from app_my.db.models.tenant import Tenant
from app_my.db.models.tenant_member import TenantMember
from app_my.db.session import get_db
from app_my.schemas.tenant import (
    MemberInviteIn,
    MemberOut,
    QuotaOut,
    TenantCreateIn,
    TenantOut,
)

router = APIRouter()


def _user_role(db: Session, tenant_id: int, user_id: int) -> str | None:
    m = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == user_id)
        )
    )
    return m.role if m else None


@router.get("", response_model=List[TenantOut])
def list_my_tenants(request: Request, db: Session = Depends(get_db)):
    """我的租户列表"""
    user_id = getattr(request.state, "user_id", None)
    rows = db.scalars(
        select(Tenant, TenantMember.role)
        .join(TenantMember, TenantMember.tenant_id == Tenant.id)
        .where(TenantMember.user_id == user_id)
    ).all()
    return [TenantOut(id=t.id, name=t.name, type=t.type, plan=t.plan, role=r) for (t, r) in rows]


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(request: Request, payload: TenantCreateIn, db: Session = Depends(get_db)):
    """创建团队租户（owner=当前用户）"""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未认证")

    t = Tenant(name=payload.name, type="team", plan="free", owner_id=user_id)
    db.add(t)
    db.flush()
    db.add(TenantMember(tenant_id=t.id, user_id=user_id, role="owner"))

    log_audit(db, action="tenant.create", tenant_id=t.id, actor_user_id=user_id,
              resource_type="tenant", resource_id=str(t.id), payload={"name": t.name, "type": "team"})

    db.commit()
    return TenantOut(id=t.id, name=t.name, type=t.type, plan=t.plan, role="owner")


@router.get("/{tenant_id}/quota", response_model=QuotaOut)
def get_quota(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    """租户配额用量（owner/admin 可看全员，普通成员也能看自己的租户）"""
    user_id = getattr(request.state, "user_id", None)
    role = _user_role(db, tenant_id, user_id)
    if role is None:
        raise HTTPException(status_code=403, detail="不是该租户成员")

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")

    plan = tenant.plan
    metrics = {m: {"used": get_usage(tenant_id, m), "limit": lim} for m, lim in QUOTAS.get(plan, QUOTAS["free"]).items()}
    return QuotaOut(plan=plan, metrics=metrics)


@router.get("/{tenant_id}/members", response_model=List[MemberOut])
def list_members(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    role = _user_role(db, tenant_id, user_id)
    if role is None:
        raise HTTPException(status_code=403, detail="不是该租户成员")

    rows = db.execute(
        select(TenantMember, User)
        .join(User, User.id == TenantMember.user_id)
        .where(TenantMember.tenant_id == tenant_id)
    ).all()
    return [MemberOut(user_id=u.id, username=u.username, role=m.role, joined_at=m.joined_at.isoformat())
            for (m, u) in rows]


@router.post("/{tenant_id}/members", response_model=MemberOut, status_code=201)
def invite_member(request: Request, tenant_id: int, payload: MemberInviteIn, db: Session = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    role = _user_role(db, tenant_id, user_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="需要 owner 或 admin 权限")

    target = db.scalar(select(User).where(User.username == payload.username))
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 配额：成员上限
    tenant = db.get(Tenant, tenant_id)
    limit = QUOTAS.get(tenant.plan, QUOTAS["free"])["max_members"]
    current = db.scalar(select(TenantMember).where(TenantMember.tenant_id == tenant_id).limit(limit + 1))
    if current is not None:
        # 真正数一下
        from sqlalchemy import func
        n = db.scalar(select(func.count(TenantMember.id)).where(TenantMember.tenant_id == tenant_id))
        if n >= limit:
            raise HTTPException(status_code=429, detail=f"成员数已达上限 {limit}；升级套餐或移除成员")

    exists = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == target.id)
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="该用户已是成员")

    m = TenantMember(tenant_id=tenant_id, user_id=target.id, role=payload.role)
    db.add(m)
    log_audit(db, action="tenant.invite", tenant_id=tenant_id, actor_user_id=user_id,
              resource_type="user", resource_id=str(target.id), payload={"role": payload.role})
    db.commit()
    return MemberOut(user_id=target.id, username=target.username, role=m.role, joined_at=m.joined_at.isoformat())


@router.delete("/{tenant_id}/members/{member_user_id}", status_code=204)
def remove_member(request: Request, tenant_id: int, member_user_id: int, db: Session = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    role = _user_role(db, tenant_id, user_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="需要 owner 或 admin 权限")

    if member_user_id == user_id:
        raise HTTPException(status_code=400, detail="不能移除自己")

    m = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == member_user_id)
        )
    )
    if m is None:
        raise HTTPException(status_code=404, detail="成员不存在")

    db.delete(m)
    log_audit(db, action="tenant.remove_member", tenant_id=tenant_id, actor_user_id=user_id,
              resource_type="user", resource_id=str(member_user_id))
    db.commit()
    return None