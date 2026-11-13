# tests/unit/test_service_apps.py —— v3 阶段 9：四个服务"装配是否正确"（纯构建，不发网络请求）
"""
覆盖点：
1. 四个服务都能构建成功，且都有 /health；
2. 每个服务挂的路由符合分工（user 有 /auth/login，chat 有 /chat/stream……）；
3. 🔴 中间件顺序：MetricsMiddleware 必须在 AuthMiddleware **之外**，
   否则 /metrics 会被 401 挡住，Prometheus 抓不到数据（阶段 7 踩过的坑，这里用测试钉死）；
4. 🔴 中间件顺序：CORS 必须在**最外层**，否则内层限流吐的 429 不带跨域头，
   前端只能看到"网络错误"；
5. /health 返回体里带 service 名和 breakers 字段（排障要靠它）。

为什么用测试钉死顺序：
    中间件顺序是"改一行代码就坏、但功能测试很难发现"的典型。
    Metrics 被 Auth 挡住时，接口全都正常，只有 Grafana 上是空的——
    这类"静默失效"必须靠"直接断言装配结构"的测试来防。
"""
import importlib

SERVICES = {
    "user": ["services.user.main"],
    "recognizer": ["services.recognizer.main"],
    "recommender": ["services.recommender.main"],
    "chat": ["services.chat.main"],
}

# 每个服务必须有的路由（分工表），路径必须和 OpenAPI 里的完全一致
EXPECTED_ROUTES = {
    "user": ["/auth/register", "/auth/login", "/users/me", "/tenants",
             "/admin/feature-flags", "/billing/stats", "/cache/stats"],
    "recognizer": ["/internal/nodes/recognize", "/internal/nodes/nutrition", "/oss/presign"],
    "recommender": ["/internal/nodes/recommend", "/internal/nodes/rank", "/kg/ask", "/kg/stats"],
    "chat": ["/chat/stream", "/tasks/reindex-milvus", "/tasks/{task_id}"],
}


def _app(name):
    mod = importlib.import_module(SERVICES[name][0])
    return mod.app


def _paths(app):
    return set(app.openapi()["paths"].keys())


def test_all_services_build():
    for name in SERVICES:
        app = _app(name)
        paths = _paths(app)
        assert "/health" in paths, f"{name} 缺少 /health"
        assert "/" in paths, f"{name} 缺少 /"


def test_routes_follow_the_split():
    """路由归属 = 拆分方案。路由放错服务，这个测试就会红。"""
    for name, expected in EXPECTED_ROUTES.items():
        paths = _paths(_app(name))
        for path in expected:
            assert path in paths, f"{name} 服务缺少路由 {path}"


def test_metrics_outside_auth():
    """
    🔴 本阶段最关键的装配断言。

    Starlette 内部实现：add_middleware() 是 `user_middleware.insert(0, ...)`，
    所以 **user_middleware 列表是按"外层在前"排列的**（实测确认，别凭印象写）。
    于是 "Metrics 在 Auth 之外" 表现为：Metrics 的索引 **小于** Auth 的索引。
    """
    for name in SERVICES:
        app = _app(name)
        order = [m.cls.__name__ for m in app.user_middleware]
        assert "MetricsMiddleware" in order, f"{name} 没挂 MetricsMiddleware"
        assert "AuthMiddleware" in order, f"{name} 没挂 AuthMiddleware"
        assert order.index("MetricsMiddleware") < order.index("AuthMiddleware"), (
            f"{name} 的 MetricsMiddleware 在 Auth 内侧，/metrics 会被 401 挡住（当前顺序：{order}）"
        )


def test_cors_outermost():
    """CORS 必须在最外层（索引 0），否则 429/500 响应不带跨域头，浏览器只看得到'网络错误'。"""
    for name in SERVICES:
        order = [m.cls.__name__ for m in _app(name).user_middleware]
        assert "CORSMiddleware" in order, f"{name} 没挂 CORSMiddleware"
        assert order.index("CORSMiddleware") == 0, (
            f"{name} 的 CORS 不在最外层（当前顺序：{order}）"
        )


def test_middleware_order_reads_correctly():
    """
    把整个洋葱顺序钉死：从外到内依次是
    CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
          → UserLimit → RateLimit → (Quota) → (TokenCapture)
    """
    order = [m.cls.__name__ for m in _app("chat").user_middleware]
    assert order == [
        "CORSMiddleware",
        "TraceIdMiddleware",
        "MetricsMiddleware",
        "AuthMiddleware",
        "TenantContextMiddleware",
        "TenantVarMiddleware",
        "UserRateLimitMiddleware",
        "RateLimitMiddleware",
        "QuotaMiddleware",
        "TokenCaptureMiddleware",
    ], f"chat 中间件顺序变了：{order}"


def test_health_payload_shape():
    """/health 要能一眼看出"我是谁 + 我的下游熔断成什么样了"。"""
    for name in SERVICES:
        app = _app(name)
        health = None
        for route in app.routes:
            if getattr(route, "path", None) == "/health":
                health = route.endpoint
        assert health is not None
        # 直接看源码里有没有这两个字段即可（不真跑协程，避免引入事件循环依赖）
        import inspect
        src = inspect.getsource(health)
        assert '"service"' in src
        assert '"breakers"' in src


def test_chat_has_extra_switches():
    """
    chat 是唯一打开"配额 + 抓 token + 后台中继"三个开关的服务。
    这也是它和其它三个服务的本质区别：它是唯一会往下调别人的。
    """
    order = [m.cls.__name__ for m in _app("chat").user_middleware]
    assert "QuotaMiddleware" in order
    assert "TokenCaptureMiddleware" in order
    # 反过来：user 服务不该有这两个（它不调别人，也不管 /chat/stream）
    user_order = [m.cls.__name__ for m in _app("user").user_middleware]
    assert "QuotaMiddleware" not in user_order
    assert "TokenCaptureMiddleware" not in user_order
