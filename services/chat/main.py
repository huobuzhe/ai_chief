# services/chat/main.py
"""
chat 服务（端口 9124）—— 用户真正"说话"的入口，也是唯一会去调别的服务的地方

它承担三件事：
    1. /chat/stream   流式对话（LangGraph 编排，可能跨服务调 recognizer / recommender）
    2. /ws/notifications  WebSocket 实时推送（阶段 8）
    3. /tasks/*       长任务提交与查询（阶段 8）

它是本阶段唯一打开了两个"额外开关"的服务：
    enable_quota=True   因为 /chat/stream 要按租户配额限流（QuotaMiddleware 只认这个路径）
    capture_auth=True   因为它要跨服务调用，必须把用户的 JWT 抓下来透传给下游
    startup_tasks       因为 WS 通知中继（订阅 Redis 频道）必须常驻在 chat 进程里
"""
import os

from app_my.api import chat
from app_my.api import tasks as tasks_api
from app_my.ws import gateway as ws_gateway
from app_my.ws.relay import run_relay

from services.common.app_factory import create_service_app


# 读一次运行模式，写进启动日志，方便排错时一眼确认
SPLIT_MODE = os.getenv("SPLIT_MODE", "local").strip().lower()


app = create_service_app(
    "chat",
    routers=[
        (chat.router, "/chat", ["AI对话"]),
        (tasks_api.router, "/tasks", ["异步任务"]),
        (ws_gateway.router, "/ws", ["WebSocket"]),
    ],
    enable_auth=True,
    enable_quota=True,     # 只有 chat 需要：QuotaMiddleware 拦截 /chat/stream 做租户配额
    capture_auth=True,     # 只有 chat 需要：把 JWT 存进 contextvars 以便透传给下游
    startup_tasks=[run_relay],   # WS 通知中继常驻协程
)


@app.get("/mode")
async def mode():
    """运维小端点：一眼看出这个 chat 进程现在是本地模式还是远程模式。"""
    return {
        "service": "chat",
        "split_mode": SPLIT_MODE,
        "remote_nodes": SPLIT_MODE == "remote",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.chat.main:app", host="0.0.0.0", port=9124, reload=False)
