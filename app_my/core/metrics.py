"""
阶段 7：Prometheus 指标定义中心。
全部用 prometheus_client 官方库手工定义——
- 中间件按 HTTP 请求 / 响应埋点（埋点 1/2）
- token_billing.record() 末尾调用 cost_inc / tokens_inc（埋点 3/4）
- QuotaMiddleware 调用 quota_set（埋点 5）
"""
from prometheus_client import Counter, Histogram, Gauge, REGISTRY as _PROM_REGISTRY


# ===== 埋点 1：HTTP 请求 QPS =====
# label：method / status（200/4xx/5xx 二级）/ tenant_id（没登录就是 "anon"）/ path（用 FastAPI route pattern 不用真实 URL，避免高基数）
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP 请求总数（按 method / status / tenant_id / path 拆）",
    labelnames=("method", "status", "tenant_id", "path"),
)

# ===== 埋点 2：HTTP 请求延迟（直方图）=====
# 默认 buckets 适合 web 请求（0.005s ~ 10s）。直方图 → 自动产生 histogram_quantile() 指标
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求延迟（秒）",
    labelnames=("method", "tenant_id", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ===== 埋点 3：LLM token 消耗 =====
# label：model（flash/plus/max/...）/ direction（input/output）
LLM_TOKENS = Counter(
    "llm_tokens_total",
    "LLM token 消耗总数（按 model / direction 拆）",
    labelnames=("model", "direction"),
)

# ===== 埋点 4：LLM 成本（元）=====
# label：model（flash/plus/max/...）
LLM_COST = Counter(
    "llm_cost_cny_total",
    "LLM 调用成本累计（元）",
    labelnames=("model",),
)

# ===== 埋点 5：租户 LLM 配额使用率 =====
# Gauge：当前瞬时值。0=0%，1=100%
LLM_QUOTA_RATIO = Gauge(
    "llm_quota_used_ratio",
    "租户 LLM 配额使用率（0~1）",
    labelnames=("tenant_id",),
)


def http_inc(method: str, path: str, status_code: int, tenant_id: str = "anon") -> None:
    """HTTP 埋点：QPS Counter + Duration Histogram 一次性记录。
    用一个 helper 把 4 个 label 的拼装集中起来——避免中间件里重复 + 拼错。"""
    # 状态码归类：2xx / 4xx / 5xx（高基数 label 会爆 Prometheus）
    status_bucket = (
        "2xx" if 200 <= status_code < 300
        else "4xx" if 400 <= status_code < 500
        else "5xx" if 500 <= status_code < 600
        else str(status_code)
    )
    tenant_label = str(tenant_id) if tenant_id is not None else "anon"
    HTTP_REQUESTS.labels(method=method, status=status_bucket, tenant_id=tenant_label, path=path).inc()
    # 延迟由调用方传入——histogram 在中间件里 observe


def tokens_inc(model: str, direction: str, amount: int) -> None:
    """Token 埋点：input / output 增量。"""
    LLM_TOKENS.labels(model=model or "unknown", direction=direction).inc(amount)


def cost_inc(model: str, cny: float) -> None:
    """成本埋点：累计（元）。"""
    LLM_COST.labels(model=model or "unknown").inc(cny)


def quota_set(tenant_id: int, ratio: float) -> None:
    """配额埋点：设置租户当前使用率。"""
    LLM_QUOTA_RATIO.labels(tenant_id=str(tenant_id)).set(ratio)