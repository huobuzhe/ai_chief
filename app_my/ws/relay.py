# app_my/ws/relay.py  —— v3 阶段 8：Redis 订阅中继（把 worker 的通知送进浏览器）
"""
补上最后一段链路：
    worker 进程  --publish-->  Redis 频道  --本文件中继-->  本进程的 WebSocket 连接

为什么需要"中继"这一环（直接让 worker 发 WS 不行吗）：
    worker 进程里根本没有浏览器连接对象（连接活在 FastAPI 进程内存里），
    worker 唯一能碰到的公共设施就是 Redis。所以：
    worker 只负责"发到 Redis"，FastAPI 进程负责"从 Redis 收 + 转发给浏览器"。

实现细节：用 redis.asyncio（异步客户端）在事件循环里 await 收消息，
    绝不能用同步客户端——同步的 listen() 会把整个 FastAPI 的事件循环卡死，
    表现为"一订阅，所有接口全不响应"。
"""
import asyncio
import json

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.ws.manager import manager

RETRY_SECONDS = 3        # 订阅断开后的重连间隔


async def run_relay() -> None:
    """
    常驻协程：订阅 Redis 频道，把事件派发给本进程的 WebSocket 连接。
    设计成"永不退出"——出错就等 3 秒重连，保证 Redis 重启后自动恢复。
    """
    import redis.asyncio as aioredis      # 函数内导入：redis 没装或版本旧时，import 本模块也不报错

    while True:
        client = None
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(settings.WS_NOTIFY_CHANNEL)
            logger.info("ws relay: 已订阅 Redis 频道 %s", settings.WS_NOTIFY_CHANNEL)

            async for message in pubsub.listen():          # 阻塞式异步迭代：有消息才唤醒
                if message.get("type") != "message":        # 订阅/退订的确认帧，跳过
                    continue
                try:
                    event = json.loads(message["data"])
                except (TypeError, ValueError):
                    logger.warning("ws relay: 收到无法解析的消息，已跳过")
                    continue
                sent = await manager.dispatch(event)
                if sent:
                    logger.info("ws relay: 事件已投递 %d 个连接（task_id=%s）",
                                sent, event.get("task_id"))
        except asyncio.CancelledError:
            # 应用关闭时会被 cancel，这是正常流程：把连接关掉再往外抛，让 lifespan 干净收尾
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass
            raise
        except Exception as exc:
            logger.warning("ws relay: 订阅中断，%d 秒后重连: %s", RETRY_SECONDS, exc)
            await asyncio.sleep(RETRY_SECONDS)
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass