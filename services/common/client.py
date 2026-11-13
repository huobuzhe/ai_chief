# services/common/client.py
"""
服务间调用客户端（ServiceClient）—— 微服务之间唯一的"电话机"

它把四件事打包在一起，业务代码只管 client.post(...)，不用关心细节：
    ① HTTP 传输     ：用 httpx.AsyncClient（异步，不阻塞事件循环）
    ② 自动重试      ：网络抖动/对方 5xx 时按"指数退避"重试几次
    ③ 熔断保护      ：对方连续挂了就跳闸，立刻失败，不再陪它耗超时
    ④ 上下文透传    ：把 trace_id / tenant_id / user_id 放进请求头带过去

为什么要透传上下文：
    一次用户请求会穿过 "Kong → chat → recommender" 三个进程。
    如果不把 trace_id 带过去，三个进程各写各的日志，出问题时你根本没法把
    同一次请求的三段日志串起来看 —— 这就是"链路追踪"要解决的头号问题。
"""
from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Dict, Optional

import httpx

from services.common import breaker as breaker_mod

# 请求头名字，全项目统一（Kong 和各服务都用这三个）
HEADER_TRACE = "X-Trace-Id"
HEADER_TENANT = "X-Tenant-Id"
HEADER_USER = "X-User-Id"

# 这几类 HTTP 状态码才重试：429 是被限流（等一下再来），5xx 是对方出错。
# 4xx（401/403/404/422）是"请求本身有问题"，重试一万次也一样，不重试。
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ServiceCallError(RuntimeError):
    """服务调用最终失败时抛出。调用方 catch 它做降级。"""


def _current_trace_id() -> str:
    """
    取当前协程上下文里的 trace_id。

    为什么用 contextvars 而不是参数传递：
    trace_id 是"贯穿全链路的环境变量"，如果每个函数都加一个 trace_id 参数，
    从接口层到最深的工具函数要改几十个签名。contextvars 是 Python 官方给的
    "协程版全局变量"，在 await 链里自动传递，不需要改任何函数签名。
    """
    try:
        from app_my.core.logging import trace_id_var
        value = trace_id_var.get()
        return value if value and value != "-" else ""
    except Exception:
        return ""


def _upstream_token() -> str:
    """取上游请求带过来的 JWT（由 TokenCaptureMiddleware 存进 contextvars）。"""
    try:
        from services.common.context import get_upstream_token
        return get_upstream_token()
    except Exception:
        return ""


class ServiceClient:
    """
    针对某一个下游服务的客户端。一个下游服务一个实例（内部复用同一个连接池）。
    """

    def __init__(
        self,
        name: str,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
        retries: int = 2,
        backoff: float = 0.2,
        transport: Optional[Any] = None,
        **breaker_kwargs,
    ) -> None:
        """
        transport：可选的 httpx 传输层。正常运行时不传（走真实网络）；
        单元测试时传 httpx.MockTransport，就能在完全离线的情况下
        精确模拟"对方返回 503""连接超时"等各种故障，验证重试和熔断逻辑。
        """
        self.name = name
        self._transport = transport
        self.base_url = (base_url or os.getenv(
            f"SERVICE_{name.upper()}_URL", f"http://127.0.0.1:{_default_port(name)}"
        )).rstrip("/")
        self.timeout = timeout
        self.retries = retries          # 首次失败后再试几次（不含第一次）
        self.backoff = backoff          # 退避基数：第 n 次等待 backoff * 2^(n-1) 秒
        self.breaker = breaker_mod.get_breaker(name, **breaker_kwargs)
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ 连接管理
    def _ensure_client(self) -> httpx.AsyncClient:
        """
        懒创建 httpx.AsyncClient。

        为什么不每次请求 new 一个：
        AsyncClient 内部持有连接池，复用它能省掉反复 TCP 握手 + TLS 的开销。
        但也不能在 __init__ 里创建 —— 那时可能还没有事件循环。
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 2.0)),
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        """关闭连接池。服务关闭时调用，否则会有连接泄漏警告。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------ 对外方法
    async def post(self, path: str, payload: Optional[Dict[str, Any]] = None,
                   **kwargs) -> Dict[str, Any]:
        """POST JSON。返回对方响应的 JSON 字典。"""
        return await self.request("POST", path, json=payload, **kwargs)

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None,
                  **kwargs) -> Dict[str, Any]:
        """GET。返回对方响应的 JSON 字典。"""
        return await self.request("GET", path, params=params, **kwargs)

    async def request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        trace_id: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发请求的核心方法：熔断闸门 → 重试循环 → 回写熔断状态。

        参数：
            method     HTTP 方法（"GET" / "POST"）
            path       路径，如 "/internal/nodes/recommend"
            json       POST 的请求体（字典）
            params     GET 的查询参数（字典）
            tenant_id  要透传的租户 ID（不传就不带这个头）
            user_id    要透传的用户 ID
            trace_id   要透传的链路 ID（不传就自动从 contextvars 里取）
            auth_token 要透传的 JWT（形如 "Bearer xxx"）。
                       因为鉴权下沉在各服务内（Kong 不鉴权），跨服务调用必须把
                       用户的 token 原样带过去，否则对方 AuthMiddleware 直接 401。
                       不传时会自动从 contextvars 里取上游抓到的 token。
        """
        # ---- ① 熔断闸门：已跳闸就直接抛，不再发请求 ----
        self.breaker.before_call()

        headers: Dict[str, str] = {}
        tid = trace_id or _current_trace_id()
        if tid:
            headers[HEADER_TRACE] = tid
        if tenant_id is not None:
            headers[HEADER_TENANT] = str(tenant_id)
        if user_id is not None:
            headers[HEADER_USER] = str(user_id)

        token = auth_token or _upstream_token()
        if token:
            headers["Authorization"] = token

        last_error = ""
        client = self._ensure_client()

        # ---- ② 重试循环：第 0 次是正常请求，之后才是重试 ----
        for attempt in range(self.retries + 1):
            try:
                resp = await client.request(method, path, json=json, params=params, headers=headers)

                if resp.status_code in RETRYABLE_STATUS:
                    # 对方明确说"我现在不行"，算一次失败，可以重试
                    last_error = f"HTTP {resp.status_code}"
                    raise httpx.HTTPStatusError(last_error, request=resp.request, response=resp)

                if resp.status_code >= 400:
                    # 4xx 不重试：请求本身有问题，重试没意义。直接算成功"送达"，
                    # 让熔断知道对方还活着（它只是拒绝了我们的请求）。
                    self.breaker.record_success()
                    raise ServiceCallError(
                        f"[{self.name}] {method} {path} 返回 {resp.status_code}: {resp.text[:200]}"
                    )

                self.breaker.record_success()
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text}

            except breaker_mod.CircuitOpenError:
                raise                      # 熔断的错不重试，直接往上抛
            except ServiceCallError:
                raise                      # 4xx 的错不重试
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt >= self.retries:
                    break
                # 指数退避 + 抖动：0.2s → 0.4s → 0.8s…再加 ±20% 随机，
                # 避免"所有调用方同一时刻一起重试"把刚恢复的服务再次打垮（惊群）。
                delay = self.backoff * (2 ** attempt) * (1 + random.uniform(-0.2, 0.2))
                await asyncio.sleep(max(delay, 0.01))

        # ---- ③ 所有重试都失败：记一次熔断失败，再抛给调用方降级 ----
        self.breaker.record_failure(last_error)
        raise ServiceCallError(
            f"[{self.name}] {method} {path} 失败（重试 {self.retries} 次后）：{last_error}"
        )

    # ------------------------------------------------------------------ 观测
    def breaker_snapshot(self) -> Dict[str, object]:
        """导出这个下游服务当前熔断器的状态。"""
        return self.breaker.snapshot()


def _default_port(name: str) -> int:
    """各服务的默认端口（与 docker/kong/kong.yml 保持一致）。"""
    return {"user": 9121, "recognizer": 9122, "recommender": 9123, "chat": 9124}.get(name, 9002)


def get_client(name: str, **kwargs) -> ServiceClient:
    """
    取（必要时创建）某个下游服务的客户端。

    做成全局缓存的原因和熔断器一样：一个进程里对同一个下游只该有一个连接池。
    """
    global _CLIENTS
    if name not in _CLIENTS:
        _CLIENTS[name] = ServiceClient(name, **kwargs)
    return _CLIENTS[name]


_CLIENTS: Dict[str, ServiceClient] = {}


async def aclose_all() -> None:
    """关闭所有客户端的连接池（服务关闭时调用）。"""
    for c in _CLIENTS.values():
        await c.aclose()
    _CLIENTS.clear()
