# tests/unit/test_cache.py —— 阶段 5：多级缓存三件套单测（9 个）
"""
覆盖点：
- L1 命中（数据源只执行一次）
- 不同参数 = 不同 key
- singleflight：8 线程并发打同一个 key 只穿透 1 次
- 空值缓存（防穿透）
- TTL 过期重新加载
- 主动失效
- TTL 抖动范围（90%~110%）
- 统计与清零
- 总开关一键关闭
"""
import threading
import time

import pytest

from app_my.core import cache as cache_mod
from app_my.core.cache import cache_stats, cache_stats_reset, cached, invalidate_prefix


@pytest.fixture(autouse=True)
def _l1_only(monkeypatch):
    """每个测试：强制 L2 失效（不依赖 Redis）+ 清空 L1 + 清零统计"""
    monkeypatch.setattr(cache_mod, "_l2_disabled", True)
    monkeypatch.setattr(cache_mod, "_l1", None)
    cache_stats_reset()
    yield
    cache_stats_reset()


def test_cache_hit_single_loader():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def fn(q):
        calls["n"] += 1
        return [q]

    assert fn("a") == ["a"]
    assert fn("a") == ["a"]
    assert calls["n"] == 1                      # 数据源只跑一次
    s = cache_stats()
    assert s["l1_hits"] == 1 and s["misses"] == 1


def test_different_args_different_key():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def fn(q):
        calls["n"] += 1
        return [q]

    fn("a")
    fn("b")
    assert calls["n"] == 2                      # 两个 key 各自穿透


def test_singleflight_concurrent():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def slow(q):
        calls["n"] += 1
        time.sleep(0.2)                         # 模拟慢数据源
        return [q]

    results, errors = [], []

    def worker():
        try:
            results.append(slow("x"))
        except Exception as e:                  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert not errors
    assert calls["n"] == 1                      # 8 个并发只有 1 个穿透
    assert len(results) == 8 and all(r == ["x"] for r in results)


def test_null_value_cached():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60, null_ttl=30)
    def fn(q):
        calls["n"] += 1
        return []

    assert fn("nothing") == []
    assert fn("nothing") == []
    assert calls["n"] == 1                      # 空值也只穿透一次（防穿透）
    assert cache_stats()["null_hits"] == 1


def test_ttl_expiry():
    calls = {"n": 0}

    @cached(prefix="t", ttl=1, null_ttl=1)
    def fn(q):
        calls["n"] += 1
        return [q]

    fn("a")
    time.sleep(1.3)                             # TTL 抖动有 1 秒下限，等满 1.3 秒
    fn("a")
    assert calls["n"] == 2                      # 过期后重新加载


def test_invalidate_prefix():
    @cached(prefix="inv", ttl=60)
    def fn(x):
        return [x]

    fn(1)
    assert invalidate_prefix("inv") == 1        # L1 里清掉 1 条
    fn(1)                                       # 重新执行（不再命中）


def test_jitter_bounds():
    ttls = {cache_mod._jitter_ttl(100) for _ in range(300)}
    assert 90 <= min(ttls) <= 100               # 下界不低于 -10%
    assert 100 <= max(ttls) <= 110              # 上界不超过 +10%
    assert len(ttls) > 50                       # 抖动真的产生了分布


def test_stats_reset():
    @cached(prefix="t", ttl=60)
    def fn(q):
        return [q]

    fn("a")
    fn("a")
    assert cache_stats()["l1_hits"] == 1
    cache_stats_reset()
    assert cache_stats()["l1_hits"] == 0


def test_cache_disabled_switch(monkeypatch):
    #monkeypatch.setattr(type(cache_mod.settings), "CACHE_ENABLED", False)
    monkeypatch.setattr(cache_mod.settings, "CACHE_ENABLED", False)
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def fn(q):
        calls["n"] += 1
        return [q]

    fn("a")
    fn("a")
    assert calls["n"] == 2                      # 开关关闭 = 每次都穿透