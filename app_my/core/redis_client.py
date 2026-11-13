# app_my/core/redis_client.py
"""
阶段 4 Redis 客户端：限流计数 + JWT 黑名单都用它。

为什么全局只建一个客户端：
- redis-py 的 Redis 对象自带连接池，进程内共享一个就够，每次新建反而浪费连接
- 懒加载（第一次用到才连），这样单元测试不装 Redis 也能 import 本模块不报错
"""
from functools import lru_cache

import redis

from app_my.core.config import settings
from app_my.core.logging import logger


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    """
    全局唯一 Redis 客户端（懒加载单例）。
    decode_responses=True：返回 str 而不是 bytes，少写一层 .decode()。
    """
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    logger.info("Redis 客户端已创建: %s", settings.REDIS_URL)
    return client


def redis_available() -> bool:
    """探活：PING-PONG 通了返回 True（启动自检 / 提测脚本用）"""
    try:
        return bool(get_redis().ping())
    except Exception as exc:
        logger.warning("Redis 不可用: %s", exc)
        return False