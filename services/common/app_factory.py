# services/common/app_factory.py
"""
服务工厂（create_service_app）—— 四个微服务的"统一装配线"

为什么要有它：
    拆成四个服务后，如果每个服务的 main.py 都抄一遍"加中间件 + 加健康检查 + 加指标端点"，
    很快就会抄歪：某个服务忘了加鉴权、另一个服务的 /metrics 被 401 挡住……
    工厂函数把这套装配固定成一份代码，四个服务共享，顺序只可能错一次。

🔴 本文件最关键的知识点：Starlette 的中间件"洋葱顺序"
    Starlette 规则：**后 add_middleware 的，包在更外层**。
    所以下面代码是"倒着写"的：越靠上的 add 语句，请求越晚经过它（越靠里）。
    请求实际经过顺序（外 → 内）：
        CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
              → UserLimit → RateLimit → (Quota) → 路由
    响应返回时反过来走一遍（内 → 外）。

    🔴 两条不能违反的顺序约束：
    1. MetricsMiddleware 必须 add 在 AuthMiddleware **之前**（这样它才更靠外），
       否则 /metrics 会先被 Auth 拦下返回 401，Prometheus 永远抓不到数据。
    2. CORS 必须最后 add（最外层），否则内层限流吐出的 429 响应不带跨域头，
       浏览器前端只能看到"网络错误"，根本不知道自己是被限流了。
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import List, Optional, Sequence, Tuple

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app_my.core.config import settings
from app_my.core.logging import logger, setup_logging
from app_my.core.tenant import current_tenant_id
from app_my.middleware.auth import AuthMiddleware
from app_my.middleware.metrics import MetricsMiddleware
from app_my.middleware.quota import QuotaMiddleware
from app_my.middleware.rate_limit import RateLimitMiddleware, UserRateLimitMiddleware
from app_my.middleware.tenant import TenantContextMiddleware
from app_my.middleware.trace import TraceIdMiddleware


# ---------------------------------------------------------------- 两个本阶段新增的小中间件
class TenantVarMiddleware(BaseHTTPMiddleware):
    """
    把 request.state.tenant_id 写进 contextvars（current_tenant_id）。

    为什么必须新写一个：
    现有的 TenantContextMiddleware 只写 request.state，**不写 contextvars**。
    单体时代没问题——因为 app_my/agents/coordinator.py 里手动 set 了一次。
    但拆成微服务后，recommender 进程里跑的 recommend_node 深处会调
    local_recipe_search()，它靠 current_tenant_id 做灰度判定；
    这个进程里没人 set，就会一直用默认值 1 —— 灰度/租户隔离静默失效。

    🔴 这是本次拆分最容易漏、且最难查的一个点：
    不报错、不崩溃，只是"租户 B 用成了租户 A 的配置"。
    """

    async def dispatch(self, request: Request, call_next):
        tenant_id = getattr(request.state, "tenant_id", None)
        # 没有租户（未登录 / 内部探测）就保留默认值，不强行写 0
        token = current_tenant_id.set(tenant_id if tenant_id is not None else 1)
        try:
            return await call_next(request)
        finally:
            # 必须 reset：不然同一个线程处理下一个请求时会读到上一个租户（连接池复用场景）
            current_tenant_id.reset(token)


class TokenCaptureMiddleware(BaseHTTPMiddleware):
    """
    把原始 Authorization 头存进 contextvars，供"跨服务调用"时透传。

    为什么需要：chat 服务要去调 recommender 服务，而 recommender 也有 AuthMiddleware
    （鉴权下沉在各自服务内，Kong 不做鉴权）。所以 chat 必须把用户的 JWT 原样带过去，
    否则对方直接 401。

    为什么用 contextvars 而不是一层层传参：
    LangGraph 的节点函数签名是固定的 `async def node(state: dict) -> dict`，
    没法额外塞一个 token 参数。contextvars 让我们"绕开签名"把值带进去。
    """

    async def dispatch(self, request: Request, call_next):
        from services.common.context import set_upstream_token
        set_upstream_token(request.headers.get("authorization", ""))
        return await call_next(request)


# ---------------------------------------------------------------- 工厂函数
def create_service_app(
    service_name: str,
    routers: Sequence[Tuple[APIRouter, str, List[str]]] = (),
    *,
    enable_auth: bool = True,
    enable_quota: bool = False,
    capture_auth: bool = False,
    cors_origins: Optional[List[str]] = None,
    startup_tasks: Sequence[Callable[[], Coroutine]] = (),
) -> FastAPI:
    """
    造一个"装配好"的 FastAPI 服务实例。

    参数：
        service_name   服务名（user / recognizer / recommender / chat），进 /health 和日志
        routers        要挂的路由，每个元素是 (router, prefix, tags) 三元组
        enable_auth    是否挂 JWT 鉴权中间件（四个服务都要 True）
        enable_quota   是否挂租户配额中间件（只有 chat 服务要 True，因为它管 /chat/stream）
        capture_auth   是否捕获 Authorization 头用于跨服务透传（只有 chat 服务要 True）
        cors_origins   允许的跨域来源；不传就用 settings.CORS_ORIGINS
        startup_tasks  要常驻运行的后台协程工厂（如 chat 服务的 Redis 订阅中继）。
                       传进来的是"函数"而不是"协程对象"，因为协程对象只能被 await 一次；
                       传函数才能在每个进程里重新创建。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        logger.info("服务 [%s] 启动中 ...", service_name)

        # 拉起常驻后台协程（如 WS 通知中继），并把句柄存起来以便关闭时取消
        tasks = [asyncio.create_task(factory(), name=f"{service_name}-bg-{i}")
                 for i, factory in enumerate(startup_tasks)]
        if tasks:
            logger.info("服务 [%s] 已启动 %d 个后台协程", service_name, len(tasks))

        yield

        logger.info("服务 [%s] 关闭", service_name)
        # 先取消后台协程再收尾，否则事件循环关闭时会报
        # "Task was destroyed but it is pending!"
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        # 关闭跨服务调用客户端的连接池，否则进程退出会有 "unclosed connector" 警告
        try:
            from services.common.client import aclose_all
            await aclose_all()
        except Exception:
            pass

    app = FastAPI(
        title=f"{settings.APP_NAME} · {service_name}服务",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # ============ 中间件（🔴 倒着 add：越靠上的越靠里）============
    if capture_auth:
        app.add_middleware(TokenCaptureMiddleware)      # 最里层：先把 token 抓到手

    if enable_quota:
        app.add_middleware(QuotaMiddleware)             # 租户配额（只有 chat 用）

    app.add_middleware(RateLimitMiddleware)             # 4. IP 级限流
    app.add_middleware(UserRateLimitMiddleware)         # 3. 用户级限流
    app.add_middleware(TenantVarMiddleware)             # 2.6 写 contextvars（本阶段新增）
    app.add_middleware(TenantContextMiddleware)         # 2.5 租户上下文
    if enable_auth:
        app.add_middleware(AuthMiddleware)              # 2. JWT 鉴权
    app.add_middleware(MetricsMiddleware)               # 1.5 指标埋点 + /metrics（必须在 Auth 之外）
    app.add_middleware(TraceIdMiddleware)               # 1. TraceID
    app.add_middleware(                                 # 0. CORS（最后 add → 最外层）
        CORSMiddleware,
        allow_origins=cors_origins or settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ============ 路由 ============
    for router, prefix, tags in routers:
        app.include_router(router, prefix=prefix, tags=tags)

    # ============ 通用端点：每个服务都有，方便 Kong 探活与排错 ============
    @app.get("/")
    async def root():
        return {"service": service_name, "version": settings.APP_VERSION, "status": "running"}

    @app.get("/health")
    async def health():
        """
        健康检查。除了返回 ok，还带上"我依赖的下游服务熔断器状态"——
        排障时一眼就能看出 chat 是不是把 recommender 熔断了。
        """
        from services.common.breaker import all_snapshots
        return {
            "status": "ok",
            "service": service_name,
            "version": settings.APP_VERSION,
            "breakers": all_snapshots(),
        }

    return app
