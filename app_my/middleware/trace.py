# # app_my/middleware/trace.py
# """
# 阶段 4 中间件①：TraceIdMiddleware（最里层，先添加）。

# 给每个请求发一个"追踪号"：
# - 请求头没带 X-Trace-Id 就生成一个（uuid4 前 16 位够用且短）
# - 塞进 request.state，后续日志/接口想用随时取
# - 响应头原样带回 X-Trace-Id——出问题时用户把响应头截图，就能顺着号查日志

# 阶段 6（可观测性）会把它接进 logger 自动附加；现在先把"号发下来"。
# """
# import uuid

# from starlette.middleware.base import BaseHTTPMiddleware
# from starlette.requests import Request
# from starlette.responses import Response


# class TraceIdMiddleware(BaseHTTPMiddleware):
#     """每个请求生成/透传 X-Trace-Id"""

#     async def dispatch(self, request: Request, call_next):
#         # 上游（比如网关）已经带了就沿用，方便跨服务串联
#         trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
#         request.state.trace_id = trace_id

#         response: Response = await call_next(request)
#         response.headers["X-Trace-Id"] = trace_id
#         return response
# app_my/middleware/trace.py

"""
TraceIdMiddleware（阶段 4 建立，阶段 6 升级）。
阶段 6 升级点：
- trace_id 塞进 contextvars → 同一请求的所有日志自动带号（配合 logging.py）
- 每个请求结束打一行访问日志：方法 / 路径 / 状态码 / 耗时
  → 不用去翻 uvicorn 的访问日志，业务日志里直接看请求全景
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app_my.core.logging import logger, trace_id_var


class TraceIdMiddleware(BaseHTTPMiddleware):
    """每个请求生成/透传 X-Trace-Id，并打通日志"""

    async def dispatch(self, request: Request, call_next):
        # 上游（比如网关）已经带了就沿用，方便跨服务串联
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
        request.state.trace_id = trace_id
        trace_id_var.set(trace_id)          # 从这行往后，本请求所有日志自动带号

        start = time.perf_counter()         # 高精度计时起点
        try:
            response: Response = await call_next(request)
        except Exception:
            # 路由抛异常：先打一行 500 访问日志再往上抛，保证异常请求也有记录
            cost_ms = (time.perf_counter() - start) * 1000
            logger.error("%s %s 500 %.0fms", request.method, request.url.path, cost_ms)
            raise
        cost_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Trace-Id"] = trace_id   # 响应头带回，方便用户报障时给号
        logger.info(
            "%s %s %d %.0fms",
            request.method, request.url.path, response.status_code, cost_ms,
        )
        return response