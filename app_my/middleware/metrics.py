"""
阶段 7：HTTP 埋点中间件（同时实现 /metrics 端点）。
🔴 挂载位置：add_middleware 要写在 AuthMiddleware 之后 —— 后 add 的在更外层，
   这样它在 Auth 之外，/metrics 才不会被 Auth 拦成 401（详见第十二节）。
- /metrics 端点就在这里实现：dispatch 命中该路径直接返回指标文本，不往下走
- 拿 tenant_id 打标签：tenant_id 由内层 TenantContextMiddleware 写入 request.state；
  Starlette 的 request.state 存在 scope["state"] 中、整条中间件链共享 —— 所以在外层也读得到
- 不在 CORS 之外（不做出最外层）：避免 OPTIONS 预检请求被记两次
- 在 Auth / 限流之外：被 401 / 429 拒绝的请求也计入 → 错误率面板能看到鉴权与限流拒绝
"""
import time

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.core.metrics import http_inc


#class PrometheusMiddleware(BaseHTTPMiddleware):
class MetricsMiddleware(BaseHTTPMiddleware):
    """HTTP 埋点中间件 + 暴露 /metrics 端点"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # /metrics 端点不参与计数（被自身反复拉会污染指标）
        if path == settings.PROMETHEUS_METRICS_PATH:
            return PlainTextResponse(_build_metrics_text(), media_type=CONTENT_TYPE_LATEST)

        # 路径模式归一：用 FastAPI 路由 pattern 代替真实 URL，避免高基数
        route = request.scope.get("route")
        path_label = getattr(route, "path", path) if route else path

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            # 路由抛异常：500 一律计入
            cost_ms = (time.perf_counter() - start) * 1000
            _handle_inc(request, path_label, 500, cost_ms)
            raise

        cost_ms = (time.perf_counter() - start) * 1000
        _handle_inc(request, path_label, response.status_code, cost_ms)
        return response


def _handle_inc(request: Request, path_label: str, status_code: int, cost_ms: float) -> None:
    """统一埋点：QPS Counter + Duration Histogram"""
    from app_my.core.metrics import HTTP_DURATION  # 避免循环引用
    tenant_id = getattr(request.state, "tenant_id", None)
    http_inc(method=request.method, path=path_label, status_code=status_code, tenant_id=tenant_id)
    HTTP_DURATION.labels(method=request.method, path=path_label, tenant_id=str(tenant_id or "anon")).observe(cost_ms / 1000)


def _build_metrics_text() -> bytes:
    """生成 Prometheus text 导出格式"""
    try:
        return generate_latest()
    except Exception as exc:
        logger.warning("metrics: generate_latest 失败: %s", exc)
        return b""