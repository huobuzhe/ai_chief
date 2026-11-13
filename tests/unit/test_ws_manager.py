# tests/unit/test_ws_manager.py  —— v3 阶段 8：WebSocket 连接管理器（纯内存，不依赖服务）
"""
覆盖点：
1. connect 会 accept 并登记；
2. dispatch 只投给同租户的连接（多租户隔离的命门）；
3. 发送失败的"死连接"会被摘掉，不反复重试；
4. disconnect 幂等；空租户投递返回 0。

注意：这里用 asyncio.run() 在同步用例里跑协程，避免额外引入 pytest-asyncio 配置。
"""
import asyncio

from app_my.ws.manager import ConnectionManager


class FakeWS:
    """假 WebSocket：只实现 manager 用到的那两个方法"""

    def __init__(self, fail: bool = False):
        self.accepted = False
        self.sent = []
        self.fail = fail

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.fail:
            raise RuntimeError("socket already closed")
        self.sent.append(data)


def test_connect_accepts_and_registers():
    m = ConnectionManager()
    ws = FakeWS()
    asyncio.run(m.connect(ws, tenant_id=1, user_id=2))
    assert ws.accepted is True
    assert m.stats()["connections"] == 1


def test_dispatch_only_reaches_same_tenant():
    """租户 1 的事件绝不能进租户 2 的连接"""
    m = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    asyncio.run(m.connect(a, tenant_id=1, user_id=1))
    asyncio.run(m.connect(b, tenant_id=2, user_id=2))

    sent = asyncio.run(m.dispatch({"type": "task", "task_id": "x", "tenant_id": 1}))
    assert sent == 1
    assert len(a.sent) == 1
    assert b.sent == []          # 租户 2 什么都没收到


def test_dispatch_drops_dead_connection():
    m = ConnectionManager()
    dead, alive = FakeWS(fail=True), FakeWS()
    asyncio.run(m.connect(dead, tenant_id=1, user_id=1))
    asyncio.run(m.connect(alive, tenant_id=1, user_id=1))

    sent = asyncio.run(m.dispatch({"tenant_id": 1, "task_id": "y"}))
    assert sent == 1
    assert m.stats()["connections"] == 1     # 死连接已被清理


def test_disconnect_is_idempotent():
    m = ConnectionManager()
    ws = FakeWS()
    asyncio.run(m.connect(ws, tenant_id=1, user_id=1))
    m.disconnect(ws)
    m.disconnect(ws)                          # 再删一次也不能报错
    assert m.stats()["connections"] == 0


def test_dispatch_to_tenant_without_connections_returns_zero():
    m = ConnectionManager()
    assert asyncio.run(m.dispatch({"tenant_id": 99})) == 0