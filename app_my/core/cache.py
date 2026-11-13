# app_my/core/cache.py —— 阶段 5（v3.0）：多级缓存
"""
多级缓存（L1 进程内 / L2 Redis / L3 数据源）+ 三件套防护：
- 防击穿 singleflight：并发打同一个 key，只有第一个线程穿透到数据源，其余等结果
- 防雪崩 TTL 抖动：每个 key 的过期时间加 ±10% 随机偏移，避免同批 key 同时失效
- 防穿透 空值短缓存：查到"确实没有"也缓存一小会儿，挡住恶意/重复的无效查询
"""
from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Dict, Optional

from app_my.core.config import settings
from app_my.core.logging import logger

_MISS = object()                 # "缓存里没有"的内部哨兵（不可能是业务值）
_NULL_MARK = "__CACHE_NULL__"    # L2 里存这个字符串 = "查过了，确实没有"
_JITTER = 0.10                   # TTL ±10% 抖动幅度

# ---------------------------------------------------------------- 全局状态（模块级单例）
_l1: Optional["_TTLCache"] = None
_l1_lock = threading.Lock()
_key_locks: Dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()
_l2_disabled = False             # L2（Redis）连续失败后置 True，本进程余生不再碰它

_stats_lock = threading.Lock()
_stats = {
    "l1_hits": 0,        # L1 命中次数（含命中空值）
    "l2_hits": 0,        # L2 命中次数（含命中空值）
    "null_hits": 0,      # 命中的是"空值占位"的次数
    "misses": 0,         # 穿透到数据源执行的次数
    "loader_errors": 0,  # 数据源抛异常次数（不缓存，直接向上抛）
    "invalidations": 0,  # 主动失效次数
}


def _bump(field: str) -> None:
    """线程安全地给统计字段 +1"""
    with _stats_lock:
        _stats[field] += 1


def cache_stats() -> Dict[str, Any]:
    """当前统计快照（/cache/stats 接口用）——数字全部来自真实运行"""
    with _stats_lock:
        snap = dict(_stats)
    hits = snap["l1_hits"] + snap["l2_hits"]
    total = hits + snap["misses"]
    snap["hit_rate"] = round(hits / total, 4) if total else 0.0
    snap["l1_size"] = len(_get_l1()._data)
    return snap


def cache_stats_reset() -> Dict[str, int]:
    """清零统计（压测前后各看一次，差值就是这一轮的真实命中）"""
    with _stats_lock:
        for k in _stats:
            _stats[k] = 0
    return dict(_stats)


# ---------------------------------------------------------------- L1：进程内 TTL 缓存
class _TTLCache:
    """线程安全的进程内 TTL 缓存（容量满时淘汰最久未访问的条目）"""

    def __init__(self, maxsize: int = 512):
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def get(self, key: str) -> Any:
        """取值；过期/不存在都返回 _MISS 哨兵（调用方只认这一个标记）"""
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return _MISS
            value, is_null, expire_at = item
            if expire_at <= time.monotonic():        # 惰性过期：取的时候才判断
                del self._data[key]
                return _MISS
            self._data.move_to_end(key)              # 刚访问过的挪到"最新"端
            return (value, is_null)

    def put(self, key: str, value: Any, is_null: bool, ttl: float) -> None:
        """存值；容量满时淘汰最旧端（LRU 语义）"""
        with self._lock:
            self._data[key] = (value, is_null, time.monotonic() + ttl)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)       # 淘汰"最久未访问"端

    def clear_prefix(self, prefix: str) -> int:
        """删掉所有以 prefix 开头的 key（主动失效用），返回删除数"""
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)


def _get_l1() -> _TTLCache:
    """L1 惰性单例：第一次用到才建（避免 import 时读 settings 的顺序问题）"""
    global _l1
    if _l1 is None:
        with _l1_lock:
            if _l1 is None:
                _l1 = _TTLCache(maxsize=settings.CACHE_L1_MAXSIZE)
    return _l1


# ---------------------------------------------------------------- L2：Redis（可选层）
def _l2_get(key: str) -> Any:
    """从 Redis 取；不可用返回 _MISS（缓存层永远不抛异常挡业务）"""
    global _l2_disabled
    if _l2_disabled:
        return _MISS
    try:
        from app_my.core.redis_client import get_redis
        raw = get_redis().get(key)
        if raw is None:
            return _MISS
        data = json.loads(raw)                       # {"n": 是否空值, "v": 值}
        return (data.get("v"), bool(data.get("n")))
    except Exception:
        _l2_disabled = True                          # 失败一次就降级：剩余请求全走 L1+数据源
        logger.warning("cache: L2(Redis) 不可用，本进程降级为 L1+数据源")
        return _MISS


def _l2_set(key: str, value: Any, is_null: bool, ttl: int) -> None:
    """写入 Redis；失败只记日志（写不进去不影响正确性，只影响命中率）"""
    global _l2_disabled
    if _l2_disabled:
        return
    try:
        from app_my.core.redis_client import get_redis
        payload = json.dumps({"n": is_null, "v": _NULL_MARK if is_null else value},
                             ensure_ascii=False, default=str)
        get_redis().setex(key, max(ttl, 1), payload)
    except Exception:
        _l2_disabled = True
        logger.warning("cache: L2(Redis) 写入失败，降级为 L1+数据源")


def _l2_del_prefix(prefix: str) -> None:
    """删除 Redis 里 prefix: 开头的全部 key（SCAN 游标遍历，不阻塞）"""
    global _l2_disabled
    if _l2_disabled:
        return
    try:
        from app_my.core.redis_client import get_redis
        client = get_redis()
        keys = list(client.scan_iter(match=f"{prefix}:*"))
        if keys:
            client.delete(*keys)
    except Exception:
        _l2_disabled = True


# ---------------------------------------------------------------- singleflight：同 key 只放一个线程进去
def _get_key_lock(key: str) -> threading.Lock:
    with _key_locks_guard:
        lock = _key_locks.get(key)
        if lock is None:
            if len(_key_locks) > 4096:               # 防 key 无限增长：满了就整体清一次
                _key_locks.clear()
            lock = threading.Lock()
            _key_locks[key] = lock
        return lock


# ---------------------------------------------------------------- 工具函数
def _make_key(prefix: str, fn: Callable, args: tuple, kwargs: dict) -> str:
    """prefix + 参数指纹 = 缓存 key。用哈希是因为参数里可能有长文本"""
    raw = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _jitter_ttl(ttl: float) -> float:
    """TTL 加 ±10% 随机抖动（防雪崩：同批写入的 key 不会同一秒集体失效）"""
    return max(1.0, ttl * (1 + random.uniform(-_JITTER, _JITTER)))


# ---------------------------------------------------------------- 装饰器：给函数整体加三级缓存
def cached(prefix: str, ttl: float = 300, null_ttl: float = 30):
    """
    用法：@cached(prefix="rag", ttl=300)
    前置约定：被装饰函数的返回值必须能 JSON 序列化（list/dict/str/数字）。
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not settings.CACHE_ENABLED:            # 总开关：一键关闭（排障时用）
                return fn(*args, **kwargs)
            key = _make_key(prefix, fn, args, kwargs)

            # ---- L1 快路径 ----
            hit = _get_l1().get(key)
            if hit is not _MISS:
                _bump("l1_hits")
                if hit[1]:
                    _bump("null_hits")
                return hit[0]

            # ---- L2 次快路径 ----
            l2_hit = _l2_get(key)
            if l2_hit is not _MISS:
                _get_l1().put(key, l2_hit[0], l2_hit[1], ttl)   # 回填 L1（下次就是纳秒级）
                _bump("l2_hits")
                if l2_hit[1]:
                    _bump("null_hits")
                return l2_hit[0]

            # ---- 慢路径：singleflight 包住数据源 ----
            with _get_key_lock(key):
                hit = _get_l1().get(key)              # double-check：排队时别人可能已加载完
                if hit is not _MISS:
                    _bump("l1_hits")
                    return hit[0]
                l2_hit = _l2_get(key)
                if l2_hit is not _MISS:
                    _get_l1().put(key, l2_hit[0], l2_hit[1], ttl)
                    _bump("l2_hits")
                    return l2_hit[0]

                _bump("misses")
                try:
                    value = fn(*args, **kwargs)       # 真正穿透到数据源/大模型
                except Exception:
                    _bump("loader_errors")            # 出错不缓存（下次还能重试）
                    raise
                is_null = value is None or value == [] or value == {}
                store_ttl = null_ttl if is_null else ttl
                _get_l1().put(key, value, is_null, _jitter_ttl(store_ttl))
                _l2_set(key, value, is_null, int(_jitter_ttl(store_ttl)))
                return value

        return wrapper
    return decorator


# ---------------------------------------------------------------- 主动失效
def invalidate_prefix(prefix: str) -> int:
    """删掉 L1+L2 里该前缀的全部缓存（数据变了主动让缓存失效）"""
    n = _get_l1().clear_prefix(prefix)
    _l2_del_prefix(prefix)
    _bump("invalidations")
    logger.info(f"cache: 已失效前缀 {prefix}（L1 清除 {n} 条）")
    return n