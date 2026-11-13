# app_my/core/security.py
"""
阶段 4 安全核心：密码哈希 + JWT 签发/校验 + 撤销（黑名单）。

分工：
- hash_password / verify_password：注册存库、登录比对，用的是 bcrypt（自带盐，同一密码每次哈希结果都不同）
- create_access_token / create_refresh_token：签发两种令牌
    - access  token：短命（默认 30 分钟），每次请求都带它，泄露损失小
    - refresh token：长命（默认 7 天），只在"续签"接口用一次，用完即作废（旋转）
- decode_token：把 token 还原成 payload（验签 + 验过期），任何失败都返回 None，调用方只判空
- revoke_token / is_revoked：登出/换新时把 token 的 jti 写进 Redis 黑名单，剩余有效期过后自动消失
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from jose import jwt, JWTError
from passlib.context import CryptContext

from app_my.core.config import settings

# bcrypt 每次哈希做 2^ROUNDS 轮运算：轮数越多越安全也越慢（12 轮约 0.3 秒，登录可接受）
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)

# 令牌类型常量：写死字符串容易拼错，统一从这取
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


# ============================================================ 密码
def hash_password(password: str) -> str:
    """明文密码 -> bcrypt 哈希（存进 users.hashed_password）"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """登录时比对：明文 vs 库里的哈希。永远不要把明文存库。"""
    return pwd_context.verify(plain, hashed)


# ============================================================ JWT
def _create_token(subject: Any, token_type: str, expires_minutes: int, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """
    签发一枚 JWT。payload 各字段：
    - sub（subject）：这个 token 代表谁——按修订版用数据库主键 user.id，不用 username
    - type：access / refresh，防止拿 refresh token 直接访问接口
    - jti（JWT ID）：每枚 token 的唯一编号，撤销黑名单就靠它
    - iat（issued at）/ exp（expire）：签发与过期时间（timezone-aware，3.12+ 不再用 utcnow）
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "jti": uuid4().hex,
        "iat": now,
        "exp": expire,
    }
    # 新增（v3阶段4）：可选 tenant 字段，写入不再覆盖。
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: Any, *, tenant_id: Optional[int] = None, tenant_role: str = "owner", tenant_plan: str = "free") -> str:
    """签发短命 access token（默认 30 分钟）；v3阶段4 起支持携带 tenant 三元组"""
    return _create_token(
        subject,
        TOKEN_TYPE_ACCESS,
        settings.JWT_ACCESS_EXPIRE_MINUTES,
        extra_claims={
            "tenant_id": tenant_id,
            "tenant_role": tenant_role,
            "tenant_plan": tenant_plan,
        } if tenant_id is not None else None,
    )


def create_refresh_token(subject: Any) -> str:
    """签发长命 refresh token（默认 7 天）。refresh token 不携带 tenant（强制登录时再确定）。"""
    return _create_token(subject, TOKEN_TYPE_REFRESH, settings.JWT_REFRESH_EXPIRE_MINUTES)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    验签 + 解码。注意返回的是整个 payload（dict），不是只有 sub：
    黑名单要读 jti、鉴权中间件要读 type，只返回 sub 就得解两次。
    任何失败（错签/过期/篡改/格式坏）都吞掉异常返回 None——调用方只需要 if payload is None。
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ============================================================ 撤销（Redis 黑名单）
def _blacklist_key(jti: str) -> str:
    return f"jwt:blacklist:{jti}"


def revoke_token(payload: Dict[str, Any]) -> int:
    """
    把一枚 token 拉黑。TTL = 剩余有效期：
    token 本身过期后黑名单记录也没必要留，让 Redis 自动清掉。
    返回写入的 TTL 秒数（0 表示 token 本来就过期了，不用拉黑）。
    """
    from app_my.core.redis_client import get_redis  # 函数内导入，避免模块级循环依赖

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return 0
    ttl = int(exp - time.time())
    if ttl <= 0:
        return 0
    get_redis().setex(_blacklist_key(jti), ttl, "1")
    return ttl


def is_revoked(payload: Dict[str, Any]) -> bool:
    """这枚 token 是不是被拉黑过（登出/换新后旧 token 立刻作废）"""
    from app_my.core.redis_client import get_redis

    jti = payload.get("jti")
    if not jti:
        return False
    try:
        return bool(get_redis().exists(_blacklist_key(jti)))
    except Exception:
        # Redis 挂了：放行（fail-open），别让缓存故障把整个鉴权打死；日志在 redis_client 里记
        return False