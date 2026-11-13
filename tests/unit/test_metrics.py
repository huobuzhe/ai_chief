"""
阶段 7：8 个 metrics 单测
- 不依赖外部服务（Prometheus / Loki / Grafana）
- 只测 4 个埋点 helper + /metrics 端点格式
"""
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY


def test_http_inc_increments_counter():
    """埋点 1：HTTP_REQUESTS 自增"""
    from app_my.core.metrics import HTTP_REQUESTS, http_inc
    before = HTTP_REQUESTS.labels(method="GET", status="2xx", tenant_id="1", path="/x")._value.get()
    http_inc("GET", "/x", 200, tenant_id="1")
    after = HTTP_REQUESTS.labels(method="GET", status="2xx", tenant_id="1", path="/x")._value.get()
    assert after - before == 1.0


def test_http_inc_status_bucketing():
    """埋点 1 状态码归类：404 → 4xx；500 → 5xx"""
    from app_my.core.metrics import HTTP_REQUESTS, http_inc
    http_inc("GET", "/y", 400, tenant_id="1")
    http_inc("GET", "/y", 404, tenant_id="1")
    http_inc("GET", "/y", 500, tenant_id="1")
    # 4xx 计数 ≥ 2
    bucket_4xx = HTTP_REQUESTS.labels(method="GET", status="4xx", tenant_id="1", path="/y")._value.get()
    bucket_5xx = HTTP_REQUESTS.labels(method="GET", status="5xx", tenant_id="1", path="/y")._value.get()
    assert bucket_4xx >= 2
    assert bucket_5xx >= 1


def test_http_inc_anon_tenant():
    """未登录请求：tenant_id = 'anon'"""
    from app_my.core.metrics import HTTP_REQUESTS, http_inc
    http_inc("GET", "/z", 200, tenant_id=None)
    anon = HTTP_REQUESTS.labels(method="GET", status="2xx", tenant_id="anon", path="/z")._value.get()
    assert anon >= 1


def test_tokens_inc():
    """埋点 3：LLM token 增量"""
    from app_my.core.metrics import LLM_TOKENS, tokens_inc
    before = LLM_TOKENS.labels(model="qwen3.7-flash", direction="input")._value.get()
    tokens_inc("qwen3.7-flash", "input", 100)
    after = LLM_TOKENS.labels(model="qwen3.7-flash", direction="input")._value.get()
    assert after - before == 100


def test_cost_inc():
    """埋点 4：LLM 成本（元）累加"""
    from app_my.core.metrics import LLM_COST, cost_inc
    before = LLM_COST.labels(model="qwen3.7-plus")._value.get()
    cost_inc("qwen3.7-plus", 0.012)
    after = LLM_COST.labels(model="qwen3.7-plus")._value.get()
    assert abs(after - before - 0.012) < 1e-9


def test_quota_set():
    """埋点 5：租户配额使用率 Gauge"""
    from app_my.core.metrics import LLM_QUOTA_RATIO, quota_set
    quota_set(42, 0.8)
    val = LLM_QUOTA_RATIO.labels(tenant_id="42")._value.get()
    assert val == 0.8


def test_metrics_endpoint_returns_prometheus_format():
    """/metrics 端点返回 text/plain; version=0.0.4 格式"""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    # 必须包含我们定义的 4 个指标
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "llm_tokens_total" in body
    assert "llm_cost_cny_total" in body


def test_metrics_endpoint_skips_self():
    """/metrics 端点不参与自身计数（验证 metric 端点不污染数据）"""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    # 调用 10 次 /metrics
    for _ in range(10):
        r = client.get("/metrics")
        assert r.status_code == 200
    # 在响应里 grep 自己的路径——不应有 metric 端点的计数
    r = client.get("/metrics")
    assert "path=\"/metrics\"" not in r.text