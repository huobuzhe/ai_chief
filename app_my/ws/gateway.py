# app_my/ws/gateway.py  —— v3 阶段 8：WebSocket 网关（/ws/notifications）
"""
一个 WebSocket 端点，两件事：
1. 握手时鉴权（游客连不上）；
2. 连上后只负责"活着"——收心跳、回 pong；真正的推送由 ws/relay.py 从 Redis 收到事件后调 manager 发。

 新手最容易翻车的点：浏览器原生 WebSocket 不能自定义请求头！
    HTTP 接口用 `Authorization: Bearer <token>` 传令牌，
    但 `new WebSocket(url)` 没法加 header —— 所以 token 只能塞进 URL 查询参数 `?token=`。
    这不是"偷懒"，是浏览器 API 的限制（WS 握手不能带自定义头）。
    代价是 token 会出现在 URL 里（可能进日志），因此生产环境一般配 wss:// 且用短命 token。

 第二个坑：HTTP 中间件管不到 WebSocket。
    main.py 里那些 add_middleware（Auth / 限流 / 指标）只处理 http 类型的请求；
    WebSocket 的 scope 类型是 "websocket"，会绕过它们直达本端点。
    所以本端点必须自己做 JWT 校验 —— 别指望 AuthMiddleware 帮你拦。
"""
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app_my.core.logging import logger
from app_my.core.security import TOKEN_TYPE_ACCESS, decode_token, is_revoked
from app_my.ws.manager import manager

router = APIRouter()

# WebSocket 协议里 1008 表示"策略违规"（这里是"你没通过鉴权"）
WS_CLOSE_POLICY_VIOLATION = 1008


def _authenticate(token: str):
    """
    校验 ?token= 里的 JWT，通过返回 (tenant_id, user_id)，否则返回 None。
    复用 HTTP 那套 security 模块，保证"HTTP 认的令牌 WS 也认"，不用维护两套鉴权。
    """
    if not token:
        return None
    payload = decode_token(token)                                  # 验签 + 验过期，失败返回 None
    if payload is None:
        return None
    if payload.get("type") != TOKEN_TYPE_ACCESS:                   # 只收 access token，不收 refresh
        return None
    if is_revoked(payload):                                        # 登出/换新过的令牌立刻失效
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    tenant_id = payload.get("tenant_id") or 0                      # 老令牌可能没有 tenant，兜底 0
    return int(tenant_id), user_id


@router.websocket("/notifications")
async def ws_notifications(websocket: WebSocket, token: str = Query(default="")):
    """
    建立实时通知长连接。

    用法（浏览器）：
        const ws = new WebSocket(`ws://127.0.0.1:9002/ws/notifications?token=${accessToken}`);

    通信约定：
        客户端 → 服务端：发文本 "ping"（保活）
        服务端 → 客户端：回 '{"type":"pong"}'；任务事件则是 {"type":"task", ...}
    """
    auth = _authenticate(token)
    if auth is None:
        # 未通过鉴权：直接以 1008 关闭（不 accept，省一次握手往返）
        logger.warning("ws: 鉴权失败，拒绝连接")
        await websocket.close(code=WS_CLOSE_POLICY_VIOLATION)
        return

    tenant_id, user_id = auth
    await manager.connect(websocket, tenant_id, user_id)
    try:
        while True:
            msg = await websocket.receive_text()     # 没消息就挂在这里等（异步等待，不占 CPU）
            if msg == "ping":                        # 简易心跳：前端定时发，防止中间设备掐掉空闲连接
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass                                         # 浏览器关页面/断网 → 走这里，正常收尾
    finally:
        manager.disconnect(websocket)