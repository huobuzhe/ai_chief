# app_my/api/auth.py
"""
阶段 4 认证接口：注册 / 登录 / 续签 / 登出。

流程全景：
- POST /auth/register  匿名可用：建用户（密码只存 bcrypt 哈希）
- POST /auth/login     匿名可用：验密码，发一对 token（access 30 分钟 + refresh 7 天）
- POST /auth/refresh   匿名可用（凭 refresh token 本身）：换新的一对，旧 refresh 作废（旋转）
- POST /auth/logout    需要 access token：把它拉黑，立刻失效
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_my.core.config import settings
from app_my.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_revoked,
    revoke_token,
    verify_password,
)
from app_my.db.models.user import User
from app_my.db.models.tenant import Tenant
from app_my.db.models.tenant_member import TenantMember
from app_my.core.audit import log_audit
from app_my.db.session import get_db
from app_my.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair, UserOut

router = APIRouter()


def _token_pair(user_id: int, tenant_id: Optional[int] = None, tenant_role: str = "owner", tenant_plan: str = "free") -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user_id, tenant_id=tenant_id, tenant_role=tenant_role, tenant_plan=tenant_plan),
        refresh_token=create_refresh_token(user_id),
        expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    """注册：用户名查重 -> 建号。201 表示"创建成功"。"""
    exists = db.scalar(select(User).where(User.username == data.username))
    if exists:
        raise HTTPException(status_code=409, detail="用户名已被注册")

    user = User(
        username=data.username,
        email=data.email or None,  # 空串转 None，别占着唯一索引
        hashed_password=hash_password(data.password),
    )
    db.add(user)

    db.flush()  # 拿到 user.id 但不 commit

    # 新增（v3阶段4）：注册时自动建一个个人租户，owner=当前用户
    tenant = Tenant(name=f"{user.username}-个人", type="personal", plan="free", owner_id=user.id)
    db.add(tenant)
    db.flush()

    member = TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner")
    db.add(member)

    user.default_tenant_id = tenant.id
    log_audit(db, action="tenant.create", tenant_id=tenant.id, actor_user_id=user.id,
              resource_type="tenant", resource_id=str(tenant.id), payload={"name": tenant.name, "type": "personal"})


    db.commit()
    db.refresh(user)  # 重新读库拿到数据库生成的 id / created_at
    return user


@router.post("/login", response_model=TokenPair)
def login(data: LoginIn, db: Session = Depends(get_db)):
    """
    登录：用户名密码对上就发 token。
    注意错误提示故意不区分"用户不存在/密码错"——防止有人拿报错枚举有效用户名。
    """
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    # 新增（v3阶段4）：拿到 default_tenant_id；缺则兜底建一个个人租户
    tenant_id = user.default_tenant_id
    if tenant_id is None:
        tenant = Tenant(name=f"{user.username}-个人", type="personal", plan="free", owner_id=user.id)
        db.add(tenant)
        db.flush()
        db.add(TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner"))
        user.default_tenant_id = tenant.id
        db.commit()
        db.refresh(user)
        tenant_id = tenant.id

    role = "owner"   # 个人租户默认 owner
    plan = "free"
    return _token_pair(user.id, tenant_id, role, plan)


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    """
    续签（旋转）：拿有效 refresh token 换新的一对，旧 refresh 立刻拉黑。
    这样 refresh token 泄露也只能用一次，窗口极小。
    """
    payload = decode_token(data.refresh_token)
    if payload is None or payload.get("type") != TOKEN_TYPE_REFRESH or is_revoked(payload):
        raise HTTPException(status_code=401, detail="refresh_token 无效、已过期或已被使用")

    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    revoke_token(payload)  # 旧的 refresh 一次性作废
    # 续签时沿用当前默认租户；老用户没 tenant 时传 None（token 不带 tenant claims，兼容）
    return _token_pair(user.id, user.default_tenant_id)


@router.post("/logout")
def logout(request: Request):
    """
    登出：把当前 access token 拉黑（AuthMiddleware 已验过并放在 request.state）。
    有效期剩下的时间过后，黑名单键自动过期消失，不占 Redis。
    """
    payload = getattr(request.state, "token_payload", None)
    if payload:
        ttl = revoke_token(payload)
        return {"detail": "已退出登录，当前 token 已撤销", "blacklist_ttl_seconds": ttl}
    # 理论到不了这里（AuthMiddleware 会先拦），防御式兜底
    raise HTTPException(status_code=401, detail="未认证")


@router.post("/switch-tenant")
def switch_tenant(request: Request, payload: dict, db: Session = Depends(get_db)):
    """
    切换当前默认租户，返回新的 access token。

    请求体: {"tenant_id": int}
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未认证")

    target_id = payload.get("tenant_id")
    if not isinstance(target_id, int):
        raise HTTPException(status_code=400, detail="tenant_id 必须是整数")

    member = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == target_id) & (TenantMember.user_id == user_id)
        )
    )
    if member is None:
        raise HTTPException(status_code=403, detail="你不是该租户的成员")

    tenant = db.get(Tenant, target_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")

    # 更新默认租户
    user = db.get(User, user_id)
    user.default_tenant_id = target_id
    db.commit()

    log_audit(db, action="auth.switch_tenant", tenant_id=target_id, actor_user_id=user_id,
              resource_type="tenant", resource_id=str(target_id))

    return _token_pair(user_id, target_id, member.role, tenant.plan)