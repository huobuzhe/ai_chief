# app_my/ws/manager.py  —— v3 阶段 8：WebSocket 连接管理器
"""
作用：记住"当前有哪些浏览器连着我、分别属于哪个租户"，任务事件来了就按租户投递。

为什么按 tenant_id 分组（而不是一股脑存一个大列表）：
    项目是多租户的——租户 A 的任务结果绝不能推给租户 B 的页面。
    分组之后，投递就是"取这个租户的连接集合，逐个发"，天然隔离。

为什么用模块级单例 manager：
    连接对象活在 FastAPI 进程的内存里，整个进程只能有一份登记表。
    多开 uvicorn worker 时每个进程各有一份，但每个进程都订阅了同一条 Redis 频道，
    各自的连接由各自的进程推 —— 这也是它能水平扩展的原因。
"""
from collections import defaultdict
from typing import Dict, Optional, Set, Tuple

from app_my.core.logging import logger


class ConnectionManager:
    """WebSocket 连接登记表（进程内单例）"""

    def __init__(self) -> None:
        self._by_tenant: Dict[int, Set] = defaultdict(set)   # tenant_id -> 该租户的在线连接集合
        self._meta: Dict[object, Tuple[int, int]] = {}       # 连接对象 -> (tenant_id, user_id)

    async def connect(self, websocket, tenant_id: int, user_id: int) -> None:
        """接受握手，登记到租户分组"""
        await websocket.accept()
        self._by_tenant[int(tenant_id or 0)].add(websocket)
        self._meta[websocket] = (int(tenant_id or 0), int(user_id or 0))
        logger.info("ws: 连接建立 tenant=%s user=%s 当前连接数=%d",
                    tenant_id, user_id, len(self._meta))

    def disconnect(self, websocket) -> None:
        """断开：从两处登记表里摘掉（幂等，重复调用安全）"""
        info = self._meta.pop(websocket, None)
        if not info:
            return
        tenant_id, user_id = info
        group = self._by_tenant.get(tenant_id)
        if group is not None:
            group.discard(websocket)
            if not group:                       # 该租户没人了，把空集合也删掉
                self._by_tenant.pop(tenant_id, None)
        logger.info("ws: 连接断开 tenant=%s user=%s 当前连接数=%d",
                    tenant_id, user_id, len(self._meta))

    async def dispatch(self, event: dict) -> int:
        """
        把一条事件推给该租户的所有在线连接；返回成功送达的连接数。
        发送失败的连接视为已死，顺手清掉（避免越积越多、每次都要重试）。
        """
        tenant_id = int(event.get("tenant_id") or 0)
        targets = list(self._by_tenant.get(tenant_id, ()))
        if not targets:
            return 0                            # 该租户没人在线：任务照跑，只是没人收推送

        sent, dead = 0, []
        for ws in targets:
            try:
                await ws.send_json(event)       # send_json 会自动把 dict 序列化成 JSON 文本帧
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        return sent

    def stats(self) -> dict:
        """当前连接概览（排障/演示用）"""
        return {
            "connections": len(self._meta),
            "tenants": {tid: len(g) for tid, g in self._by_tenant.items()},
        }


# 全局单例：网关、中继、接口都 import 这一个
manager = ConnectionManager()