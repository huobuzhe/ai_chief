# app_my/core/feature_flag.py
"""
Feature Flag：按 tenant_id 哈希分桶的灰度判定。

判定规则：
1. flag.enabled == False → 全员 False
3. tenant_id 在 whitelist_tenants → True
4. hash(tenant_id + flag.name) % 100 < rollout_pct → True
5. 其他 → False

缓存：读多写少，加 60s TTL 内存缓存（flag 改了最多等 1 分钟生效）。
"""
import hashlib
import json
from typing import Optional

from sqlalchemy.orm import Session

from app_my.core.logging import logger
from app_my.core.redis_client import get_redis
from app_my.db.models.feature_flag import FeatureFlag

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 60.0


def _load_flag(db: Session, name: str) -> Optional[dict]:
    """从 DB 读一条 flag，转成 dict（含解析 whitelist JSON）"""
    # name 是 unique 但不是主键，不能用 db.get（db.get 按主键查 id），必须显式 select
    from sqlalchemy import select
    row = db.scalar(select(FeatureFlag).where(FeatureFlag.name == name))
    if row is None:
        return None
    try:
        whitelist = json.loads(row.whitelist_tenants or "[]")
    except json.JSONDecodeError:
        whitelist = []
    return {
        "name": row.name,
        "enabled": row.enabled,
        "rollout_pct": row.rollout_pct,
        "whitelist": [int(x) for x in whitelist],
    }


def _read_with_cache(db: Session, name: str) -> Optional[dict]:
    """60s 内存缓存；过期重读 DB"""
    import time
    now = time.time()
    hit = _CACHE.get(name)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    flag = _load_flag(db, name)
    if flag is not None:
        _CACHE[name] = (now, flag)
    return flag


def invalidate_cache(name: Optional[str] = None) -> None:
    """主动失效缓存（管理员改 flag 后调一次）"""
    if name is None:
        _CACHE.clear()
    else:
        _CACHE.pop(name, None)


def is_feature_enabled(db: Session, name: str, tenant_id: int) -> bool:
    """
    判定某租户能否使用某 flag。

    flag 不存在 = 关（默认关闭是新功能的保守做法）。
    """
    flag = _read_with_cache(db, name)
    if flag is None or not flag["enabled"]:
        return False
    if tenant_id in flag["whitelist"]:
        return True
    h = hashlib.md5(f"{tenant_id}:{name}".encode()).hexdigest()
    bucket = int(h[:8], 16) % 100
    return bucket < flag["rollout_pct"]