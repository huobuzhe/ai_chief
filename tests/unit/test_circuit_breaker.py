# tests/unit/test_circuit_breaker.py —— v3 阶段 9：熔断器状态机（纯内存，不依赖任何服务）
"""
覆盖点：
1. 初始是 CLOSED，失败没到阈值不跳闸；
2. 连续失败到阈值 → OPEN，before_call 抛 CircuitOpenError（快速失败）；
3. OPEN 期间成功不算数，必须等恢复时间 → 自动转 HALF_OPEN；
4. HALF_OPEN 放一个请求过去：成功 → 合闸 CLOSED；失败 → 重新跳闸；
5. snapshot() 字段齐全（给 /health 用）；
6. 注册表：同名只创建一个实例，reset_all 清空。

为什么用同步用例 + 直接改 _opened_at：
    熔断器的核心是"时间驱动"的状态迁移。等 30 秒再断言太慢，
    直接把跳闸时刻往前拨（_opened_at = now - 999）就能立刻进入可试探状态。
"""
import time

from services.common.breaker import (
    CircuitBreaker,
    CircuitOpenError,
    all_snapshots,
    get_breaker,
    reset_all,
)


def test_stays_closed_before_threshold():
    """失败次数没到阈值时不能跳闸——否则一次网络抖动就把服务判死了。"""
    b = CircuitBreaker("t1", failure_threshold=3)
    b.record_failure("e1")
    b.record_failure("e2")
    assert b.state.value == "closed"
    b.before_call()          # 不抛异常
    assert b.snapshot()["failures"] == 2


def test_trips_open_at_threshold():
    """连续 3 次失败 → 跳闸，之后的调用直接抛错，不再消耗超时等待。"""
    b = CircuitBreaker("t2", failure_threshold=3, recovery_timeout=30)
    for i in range(3):
        b.record_failure(f"e{i}")
    assert b.state.value == "open"
    try:
        b.before_call()
        assert False, "OPEN 状态应该抛 CircuitOpenError"
    except CircuitOpenError as e:
        assert "跳闸" in str(e)


def test_success_resets_failure_counter():
    """成功一次就把连续失败计数清零——'连续'两个字很关键，偶发失败不该累积。"""
    b = CircuitBreaker("t3", failure_threshold=3)
    b.record_failure("e1")
    b.record_failure("e2")
    b.record_success()
    assert b.snapshot()["failures"] == 0
    b.record_failure("e3")
    b.record_failure("e4")
    assert b.state.value == "closed"     # 只有 2 次连续失败，没到 3


def test_open_becomes_half_open_after_timeout():
    """过了恢复时间，OPEN 自动降级成 HALF_OPEN，允许放一个请求试探。"""
    b = CircuitBreaker("t4", failure_threshold=1, recovery_timeout=30)
    b.record_failure("boom")
    assert b.state.value == "open"
    b._opened_at = time.time() - 999     # 把跳闸时刻往前拨，模拟"已经等够了"
    assert b.state.value == "half_open"
    b.before_call()                      # HALF_OPEN 有 1 个名额，不抛
    try:
        b.before_call()                  # 名额用完，第二个要拒绝
        assert False, "试探名额应该只有 1 个"
    except CircuitOpenError:
        pass


def test_half_open_success_closes():
    """试探成功 → 合闸，服务恢复正常。"""
    b = CircuitBreaker("t5", failure_threshold=1, recovery_timeout=30)
    b.record_failure("boom")
    b._opened_at = time.time() - 999
    assert b.state.value == "half_open"
    b.before_call()
    b.record_success()
    assert b.state.value == "closed"
    assert b.snapshot()["failures"] == 0


def test_half_open_failure_reopens():
    """试探失败 → 立刻重新跳闸，并把计时器重置（再等一整轮）。"""
    b = CircuitBreaker("t6", failure_threshold=1, recovery_timeout=30)
    b.record_failure("boom")
    b._opened_at = time.time() - 999
    b.before_call()
    b.record_failure("still down")
    assert b.state.value == "open"
    assert b.snapshot()["recover_in"] > 25     # 计时器确实被重置了


def test_snapshot_fields():
    """snapshot 是给 /health 和排障看的，字段必须齐全。"""
    b = CircuitBreaker("t7", failure_threshold=5)
    s = b.snapshot()
    for key in ("name", "state", "failures", "threshold", "last_error", "recover_in"):
        assert key in s, f"snapshot 缺少字段 {key}"
    assert s["name"] == "t7"
    assert s["threshold"] == 5


def test_registry_singleton_and_reset():
    """同名服务只能有一个熔断器实例——否则计数会分散，永远跳不了闸。"""
    reset_all()
    a = get_breaker("recommender")
    b = get_breaker("recommender")
    assert a is b
    assert "recommender" in all_snapshots()
    reset_all()
    assert all_snapshots() == {}
