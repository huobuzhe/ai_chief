# app_my/api/cache.py
"""
阶段 5（v3.0）：缓存运行时观测接口——命中率/穿透次数一眼可见。

接口（受 JWT 鉴权保护）：
    GET   /cache/stats    当前统计快照（含命中率）
    POST  /cache/reset    统计清零（压测前用）
    POST  /cache/invalidate/{prefix}   主动失效某前缀缓存（运维用）
"""
from fastapi import APIRouter

from app_my.core.cache import cache_stats, cache_stats_reset, invalidate_prefix

router = APIRouter()


@router.get("/stats")
async def stats():
    """缓存统计快照：命中/穿透/空值/失效/命中率——全部真实运行数字"""
    return cache_stats()


@router.post("/reset")
async def reset():
    """清零统计计数（不动缓存数据，只清计数）"""
    return {"reset": cache_stats_reset()}


@router.post("/invalidate/{prefix}")
async def invalidate(prefix: str):
    """主动失效：prefix 目前有 rag / kg / kgstats 三种"""
    return {"prefix": prefix, "l1_cleared": invalidate_prefix(prefix)}