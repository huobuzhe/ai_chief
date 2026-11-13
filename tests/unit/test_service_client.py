# tests/unit/test_service_client.py —— v3 阶段 9：服务间调用客户端（离线，用 MockTransport）
"""
覆盖点：
1. 正常 200 → 原样返回 JSON；
2. 5xx 会重试，重试次数用尽才抛 ServiceCallError；
3. 重试期间对方恢复了 → 成功返回，且熔断器记为成功（没跳闸）；
4. 连续失败到阈值 → 熔断器跳闸，之后的调用**立刻**抛 CircuitOpenError（不再发请求）；
5. 4xx 不重试（请求本身有问题，重试没意义）；
6. trace_id / tenant_id / Authorization 三个头都透传过去了；
7. auth_token 没传时，会从 contextvars 里自动取上游 token。

为什么用 httpx.MockTransport：
    要验证"对方 503""连接失败"这些故障分支，真起服务再杀掉太慢、也不稳定。
    MockTransport 让我们在完全离线的情况下精确控制对方返回什么，
    还能顺手断言"到底发了几次请求""请求头里带了什么"。
"""
import asyncio

import httpx

from services.common import breaker as breaker_mod
from services.common.client import (
    HEADER_TENANT,
    HEADER_TRACE,
    ServiceCallError,
    ServiceClient,
)
from services.common.context import set_upstream_token


def _client(handler, retries=2, threshold=3, recovery=30, **kw):
    """造一个挂在 MockTransport 上的客户端，不发真实网络请求。"""
    breaker_mod.reset_all()
    return ServiceClient(
        "svc",
        base_url="http://mock",
        retries=retries,
        backoff=0.001,                       # 测试里别真睡 0.2 秒
        transport=httpx.MockTransport(handler),
        failure_threshold=threshold,
        recovery_timeout=recovery,
        **kw,
    )


def test_success_returns_json():
    async def handler(request):
        return httpx.Response(200, json={"recipes": [{"name": "番茄炒蛋"}]})

    c = _client(handler)
    out = asyncio.run(c.post("/internal/nodes/recommend", {"ingredients": []}))
    assert out["recipes"][0]["name"] == "番茄炒蛋"
    assert c.breaker_snapshot()["state"] == "closed"
    asyncio.run(c.aclose())


def test_retries_on_5xx_then_succeeds():
    """前两次 503，第三次 200：重试机制真的把这次调用救回来了。"""
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"ok": True})

    c = _client(handler, retries=2)
    out = asyncio.run(c.post("/x", {}))
    assert out["ok"] is True
    assert calls["n"] == 3, "应该一共发了 3 次（1 次正常 + 2 次重试）"
    assert c.breaker_snapshot()["state"] == "closed"
    asyncio.run(c.aclose())


def test_exhausted_retries_raise_and_trip_breaker():
    """一直 503，重试用尽 → 抛错；连续失败到阈值 → 熔断跳闸。"""
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        return httpx.Response(503, text="down")

    # threshold=1：一次"彻底失败的调用"就跳闸。
    # 注意：一次 post() 内部重试 3 次，但只记 **1 次** 熔断失败——
    # 计的是"调用失败次数"，不是"HTTP 请求次数"。
    c = _client(handler, retries=2, threshold=1)
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "应该抛 ServiceCallError"
    except ServiceCallError as e:
        assert "503" in str(e)
    assert calls["n"] == 3
    assert c.breaker_snapshot()["state"] == "open"

    # 第二次调用：已经跳闸，请求数不应该再增加（这就是"快速失败"的价值）
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "跳闸后应该抛 CircuitOpenError"
    except breaker_mod.CircuitOpenError:
        pass
    assert calls["n"] == 3, "跳闸后不应再发请求"
    asyncio.run(c.aclose())


def test_4xx_not_retried():
    """400 是请求本身错了，重试一万次也还是 400 —— 不该浪费重试次数。"""
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        return httpx.Response(422, json={"detail": "bad"})

    c = _client(handler, retries=2)
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "4xx 应该抛 ServiceCallError"
    except ServiceCallError as e:
        assert "422" in str(e)
    assert calls["n"] == 1, "4xx 只该发一次"
    # 4xx 说明对方还活着，不该算熔断失败
    assert c.breaker_snapshot()["state"] == "closed"
    asyncio.run(c.aclose())


def test_headers_propagate():
    """链路追踪的命门：trace_id / tenant_id / Authorization 必须带过去。"""
    seen = {}

    async def handler(request):
        seen["trace"] = request.headers.get(HEADER_TRACE)
        seen["tenant"] = request.headers.get(HEADER_TENANT)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": 1})

    c = _client(handler)
    asyncio.run(c.post(
        "/x", {},
        trace_id="trace-abc123",
        tenant_id=7,
        auth_token="Bearer tok-999",
    ))
    assert seen["trace"] == "trace-abc123"
    assert seen["tenant"] == "7"
    assert seen["auth"] == "Bearer tok-999"
    asyncio.run(c.aclose())


def test_token_falls_back_to_contextvars():
    """没显式传 auth_token 时，自动从 contextvars 里取上游抓到的 token。"""

    async def handler(request):
        return httpx.Response(200, json={"auth": request.headers.get("authorization", "")})

    c = _client(handler)
    set_upstream_token("Bearer upstream-1")
    out = asyncio.run(c.post("/x", {}))
    assert out["auth"] == "Bearer upstream-1"
    set_upstream_token("")            # 还原，避免污染其它用例
    asyncio.run(c.aclose())


def test_connection_error_also_trips():
    """连不上（不是 5xx，是底层异常）同样要记失败并最终跳闸。"""

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    c = _client(handler, retries=0, threshold=1)
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "连接失败应该抛 ServiceCallError"
    except ServiceCallError:
        pass
    assert c.breaker_snapshot()["state"] == "open"
    asyncio.run(c.aclose())
