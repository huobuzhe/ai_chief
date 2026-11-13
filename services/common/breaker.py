# services/common/breaker.py
"""
熔断器（Circuit Breaker）—— 微服务里"防止一个服务挂掉拖垮调用方"的保护开关

生活化比喻：就像家里的电闸。
    正常（CLOSED）   ：电流正常通过，请求照发。
    跳闸（OPEN）     ：连续烧坏几个电器后，电闸自动跳掉，直接拒绝请求，不再往故障服务上砸。
    试探（HALF_OPEN）：等了一会儿，放一个请求过去试试，通了就合闸，不通继续跳着。

为什么必须有它：
    微服务里 A 调 B，B 挂了 → A 的每次请求都要等超时（比如 5 秒）才失败 →
    用户请求全堵在 A 上 → A 的连接池耗尽 → A 也挂 → 一路传染（雪崩）。
    熔断器的作用是"快速失败"：B 已经确定不行了，A 立刻返回降级结果，不再等。

三个可调参数：
    failure_threshold  连续失败几次才跳闸（默认 3）
    recovery_timeout   跳闸后等多久才允许试探（默认 30 秒）
    half_open_max_calls 试探期最多放几个请求过去（默认 1）
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Dict


class BreakerState(str, Enum):
    """熔断器的三种状态。用 str 继承是为了能直接进 JSON/日志。"""
    CLOSED = "closed"        # 正常放行
    OPEN = "open"            # 跳闸，直接拒绝
    HALF_OPEN = "half_open"  # 试探期，放少量请求


class CircuitOpenError(RuntimeError):
    """熔断器处于 OPEN 时抛出的异常，调用方要 catch 它并走降级逻辑。"""


class CircuitBreaker:
    """
    一个"按服务名"独立的熔断器实例。

    线程安全：用 threading.Lock 保护状态读写。
    （uvicorn 单进程里也可能有多线程跑同步代码，加锁最稳妥）
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = BreakerState.CLOSED
        self._failures = 0           # 连续失败计数（成功一次就清零）
        self._opened_at = 0.0        # 跳闸时刻（time.time() 的时间戳）
        self._half_open_calls = 0    # 试探期已经放过去几个请求
        self._last_error = ""        # 最近一次失败原因，便于排错

    # ------------------------------------------------------------------ 状态查询
    @property
    def state(self) -> BreakerState:
        """当前状态。注意：OPEN 状态下如果已经过了恢复时间，会自动降级成 HALF_OPEN。"""
        with self._lock:
            return self._current_state_unlocked()

    def _current_state_unlocked(self) -> BreakerState:
        """内部方法：调用前必须已持有锁。OPEN 超时自动转 HALF_OPEN。"""
        if self._state == BreakerState.OPEN:
            if time.time() - self._opened_at >= self.recovery_timeout:
                self._state = BreakerState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    # ------------------------------------------------------------------ 调用前闸门
    def before_call(self) -> None:
        """
        发请求之前调用。如果处于 OPEN（还没到试探时间），直接抛 CircuitOpenError。

        这一抛很关键：它让调用方"立刻失败"，而不是陪着故障服务耗掉整个超时时间。
        """
        with self._lock:
            state = self._current_state_unlocked()
            if state == BreakerState.OPEN:
                raise CircuitOpenError(
                    f"[{self.name}] 熔断器已跳闸，剩余恢复时间 "
                    f"{max(0.0, self.recovery_timeout - (time.time() - self._opened_at)):.1f}s"
                )
            if state == BreakerState.HALF_OPEN:
                # 试探期有名额限制：超过名额的请求继续拒绝，避免刚有点希望就被打垮
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitOpenError(f"[{self.name}] 试探名额已用完，稍后再试")
                self._half_open_calls += 1

    # ------------------------------------------------------------------ 结果回写
    def record_success(self) -> None:
        """调用成功：连续失败计数清零；如果是试探期，说明服务恢复了，直接合闸。"""
        with self._lock:
            self._failures = 0
            self._last_error = ""
            self._half_open_calls = 0
            self._state = BreakerState.CLOSED

    def record_failure(self, reason: str = "") -> None:
        """调用失败：连续失败计数 +1；达到阈值就跳闸。"""
        with self._lock:
            self._failures += 1
            self._last_error = reason
            if self._state == BreakerState.HALF_OPEN:
                # 试探失败 → 立刻重新跳闸，并把恢复计时器重置（再等一轮）
                self._trip_unlocked()
            elif self._failures >= self.failure_threshold:
                self._trip_unlocked()

    def _trip_unlocked(self) -> None:
        """内部方法：置为 OPEN 并记录跳闸时刻。"""
        self._state = BreakerState.OPEN
        self._opened_at = time.time()
        self._half_open_calls = 0

    # ------------------------------------------------------------------ 观测 / 测试辅助
    def snapshot(self) -> Dict[str, object]:
        """把内部状态导出成字典，给 /health 和指标用。"""
        with self._lock:
            state = self._current_state_unlocked()
            return {
                "name": self.name,
                "state": state.value,
                "failures": self._failures,
                "threshold": self.failure_threshold,
                "last_error": self._last_error,
                "recover_in": (
                    round(max(0.0, self.recovery_timeout - (time.time() - self._opened_at)), 1)
                    if state == BreakerState.OPEN else 0.0
                ),
            }

    def reset(self) -> None:
        """恢复到出厂状态。单测里每个用例跑之前都要调一次，避免用例互相污染。"""
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failures = 0
            self._opened_at = 0.0
            self._half_open_calls = 0
            self._last_error = ""


# 全局注册表：所有熔断器按"服务名"登记在这里，方便 /health 一次性列出全部状态
_REGISTRY: Dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = threading.Lock()


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    """取（必要时创建）某个服务的熔断器。同名只会有一个实例。"""
    with _REGISTRY_LOCK:
        if name not in _REGISTRY:
            _REGISTRY[name] = CircuitBreaker(name, **kwargs)
        return _REGISTRY[name]


def all_snapshots() -> Dict[str, Dict[str, object]]:
    """导出全部熔断器的状态快照，供 /health 展示。"""
    with _REGISTRY_LOCK:
        return {name: b.snapshot() for name, b in _REGISTRY.items()}


def reset_all() -> None:
    """清空注册表（仅测试用）。"""
    with _REGISTRY_LOCK:
        _REGISTRY.clear()
