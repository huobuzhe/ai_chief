# main.py - AI 私厨 v2.0 修订版入口
import asyncio           #阶段8
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_my.core.config import settings
from app_my.core.logging import setup_logging, logger
from app_my.core.tracing import setup_langsmith
#from app_my.api import oss, chat, auth, user   # auth/user/recipe 在阶段 4 之后引入
from app_my.middleware.trace import TraceIdMiddleware
from app_my.middleware.auth import AuthMiddleware
from app_my.middleware.rate_limit import (
    RateLimitMiddleware,
    UserRateLimitMiddleware,
)
from app_my.middleware.tenant import TenantContextMiddleware   # v3阶段4 新增
from app_my.middleware.quota import QuotaMiddleware           # v3阶段4 新增
from app_my.db.base import init_db
#from app_my.api import oss, chat, auth, user, billing   # auth/user/recipe 在阶段 4 之后引入；billing 为 v3阶段2 新增
#from app_my.api import oss, chat, auth, user, billing, kg   # kg 为 v3阶段3 新增（知识图谱推理）
#from app_my.api import oss, chat, auth, user, billing, kg, tenant as tenant_api, admin as admin_api   # v3阶段4 新增 tenant + admin 路由
from app_my.api import oss, chat, auth, user, billing, kg, tenant as tenant_api, admin as admin_api, cache   # cache 为 v3阶段5 新增

from app_my.middleware.metrics import MetricsMiddleware

from app_my.api import tasks as tasks_api   # v3阶段8 新增：异步任务提交/查询

from app_my.ws import gateway as ws_gateway          # v3阶段8 新增：WebSocket 实时推送网关
from app_my.ws.relay import run_relay               # v3阶段8 新增：Redis 订阅中继


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动 / 关闭钩子"""
    setup_logging()
    setup_langsmith()
    init_db()  # 阶段 4：幂等建表（users 表不存在就建，存在跳过）
    logger.info("%s v%s 启动中...", settings.APP_NAME, settings.APP_VERSION)
    logger.info("监听: http://%s:%d", settings.HOST, settings.PORT)
    # logger.info("Debug: %s", settings.DEBUG)
    # yield
    # logger.info("服务关闭，清理资源...")


    logger.info("Debug: %s", settings.DEBUG)

    # v3阶段8：启动常驻协程，订阅 Redis 频道，把任务完成事件转发给浏览器
    relay_task = asyncio.create_task(run_relay(), name="ws-notify-relay")
    logger.info("ws relay: 后台订阅任务已启动")

    yield

    # v3阶段8：先取消中继协程再收尾，避免事件循环关闭时报 "Task was destroyed but it is pending"
    relay_task.cancel()
    try:
        await relay_task
    except asyncio.CancelledError:
        pass
    logger.info("服务关闭，清理资源...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# # ===== 中间件 =====
# # CORS 放这里就够（阶段 0 已经在 ALLOWED_ORIGINS 里加了 "null"）；
# # 阶段 4 还会叠加 Trace ID / 鉴权 / 限流，注意顺序：
# #   阶段 4 最终顺序（CORS 最外层）：TraceId -> Auth -> UserLimit -> RateLimit -> CORS(最后)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.CORS_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# ===== 中间件（阶段 4 最终版）=====
# Starlette 规则：后 add 的包在外层。所以要"请求先进 CORS、最后进限流"，
# 就得按"限流 -> 用户限流 -> 鉴权 -> TraceID -> CORS"的顺序 add（倒着写）。
# 请求进入方向：CORS -> TraceID -> Auth -> UserLimit -> RateLimit -> 路由
# 响应返回方向：路由 -> RateLimit -> UserLimit -> Auth -> TraceID -> CORS(加跨域头)
# 关键点（M5 修复）：CORS 必须最外层，内层限流吐的 429 才能带上跨域头，
#                   否则浏览器里前端只能看到"网络错误"，不知道是被限流了。
# 关键点（M4 修复）：UserLimit 在 Auth 之后，才数得到"登录用户"，否则全是匿名。

app.add_middleware(QuotaMiddleware)                  # 5. 租户配额（最里层）
app.add_middleware(RateLimitMiddleware)             # 4. 全局/IP 级限流（最里层）
app.add_middleware(UserRateLimitMiddleware)         # 3. 用户级限流
app.add_middleware(TenantContextMiddleware)         # 2.5 租户上下文（v3阶段4 新增）
app.add_middleware(AuthMiddleware)                  # 2. JWT 鉴权

app.add_middleware(MetricsMiddleware)                #1.5  阶段 7：HTTP 埋点 + /metrics 端点（必须在 Auth 之外）

app.add_middleware(TraceIdMiddleware)               # 1. TraceID
app.add_middleware(                                 # 0. CORS（最后加 -> 最外层）
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 路由 =====
app.include_router(oss.router, prefix="/oss", tags=["阿里云OSS"])
app.include_router(chat.router, prefix="/chat", tags=["AI对话"])
app.include_router(auth.router, prefix="/auth", tags=["认证(阶段4)"])
app.include_router(user.router, prefix="/users", tags=["用户(阶段4)"])
app.include_router(billing.router, prefix="/billing", tags=["成本统计(v3阶段2)"])   #  v3阶段2 新增
app.include_router(kg.router, prefix="/kg", tags=["知识图谱(v3阶段3)"])            #  v3阶段3 新增
app.include_router(cache.router, prefix="/cache", tags=["缓存观测(v3阶段5)"])   # v3阶段5 新增


app.include_router(tenant_api.router, prefix="/tenants", tags=["租户管理(v3阶段4)"])   # v3阶段4 新增
app.include_router(admin_api.router, prefix="/admin", tags=["管理端(v3阶段4)"])         # v3阶段4 新增


app.include_router(tasks_api.router, prefix="/tasks", tags=["异步任务(v3阶段8)"])       # v3阶段8 新增
app.include_router(ws_gateway.router, prefix="/ws", tags=["WebSocket(v3阶段8)"])        # v3阶段8 新增

# from app_my.api import _debug
# app.include_router(_debug.router, prefix="/debug", tags=["[临时]调试"])

@app.get("/")
async def root():
    """服务元信息"""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "env": "dev" if settings.DEBUG else "prod",
    }


# @app.get("/health")
# async def health():
#     """健康检查 - Docker / K8s 探针用"""
#     return {"status": "ok"}

#阶段7 K8s / Prometheus 探针更易诊断
@app.get("/health")
async def health():
    """健康检查 - Docker / K8s 探针用"""
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
