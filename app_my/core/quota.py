# app_my/core/quota.py
"""
租户级配额：Redis 固定窗口计数器。

设计要点：
- 键格式 quota:<tenant_id>:<metric>:<YYYYMMDD>：跨天自动换键=自动清零，无需主动清
- INCR + EXPIRE：原子 +1，第一次设置 86400 秒过期；TTL 兜底用 9000 秒防止边界漂移
- 失败策略：Redis 挂了放行（fail-open），配额是保护措施不是主链路
- 不在 keep/retry：INCR 本身就是原子操作，连环 INCR 不存在 race

为什么不直接用 SQL：配额检查在请求热路径上（每次对话都查一次），
Redis 单次 O(1)，SQL 会给 PostgreSQL 加压力；阶段 5 的多级缓存整段再做。
"""
from datetime import datetime, timezone
from typing import Tuple

from app_my.core.logging import logger
from app_my.core.redis_client import get_redis


def _today_key(tenant_id: int, metric: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"quota:{tenant_id}:{metric}:{day}"


def incr_usage(tenant_id: int, metric: str, by: int = 1) -> int:
    """
    给某个租户的某个 metric +1，返回加完后的值。

    返回 -1 表示 Redis 不可用（调用方按 fail-open 继续放行）。
    """
    key = _today_key(tenant_id, metric)
    try:
        r = get_redis()
        val = r.incrby(key, by)
        if val == by:
            r.expire(key, 9000)  # 2.5 小时兜底；正常走跨天换键自然清零
        return int(val)
    except Exception as exc:
        logger.warning("配额计数失败（fail-open）: %s %s", type(exc).__name__, exc)
        return -1


def get_usage(tenant_id: int, metric: str) -> int:
    """查询当前已用量；Redis 挂返回 0（不阻断 UI 显示）"""
    key = _today_key(tenant_id, metric)
    try:
        return int(get_redis().get(key) or 0)
    except Exception:
        return 0


def reset_usage(tenant_id: int, metric: str) -> None:
    """管理员手动重置（测试 / 配额异常恢复用）"""
    try:
        get_redis().delete(_today_key(tenant_id, metric))
    except Exception as exc:
        logger.warning("配额重置失败: %s", exc)


# ============================ 配额档位（按 plan 决定上限） ============================

QUOTAS = {
    "free":       {"chat_daily": 50,  "tokens_daily": 100_000,  "max_members": 5},
    "pro":        {"chat_daily": 500, "tokens_daily": 1_000_000, "max_members": 10},
    "enterprise": {"chat_daily": 5000,"tokens_daily": 10_000_000,"max_members": 100},
}


def get_limit(plan: str, metric: str) -> int:
    """取配额上限；未知 plan 走 free（防御式）"""
    return QUOTAS.get(plan, QUOTAS["free"]).get(metric, 0)


def check_quota(tenant_id: int, plan: str, metric: str) -> Tuple[bool, int, int]:
    """
    配额检查：返回 (是否超限, 已用, 上限)。

    三个返回值让接口层能直接拼结构化错误：
        {detail: "配额超限", metric: "chat_daily", used: 50, limit: 50}
    """
    limit = get_limit(plan, metric)
    if limit == 0:
        return True, 0, 0  # 未配置 = 不限
    used = get_usage(tenant_id, metric)
    return used < limit, used, limit