# tests/unit/test_ws_gateway.py  —— v3 阶段 8：WebSocket 网关（JWT 鉴权 + 实时投递）
"""
覆盖点：
1. 不带 token / 带 refresh token / 带乱码 token —— 一律握手被拒（1008）；
2. 带合法 access token —— 连上、ping/pong 正常；
3. 往 Redis 发一条任务事件 —— 中继把它推到这个连接上（真·端到端）。

依赖：Redis 6380 在跑（阶段 1 的容器）；relay 由 main.py 的 lifespan 自动启动。
"""
import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app_my.core.config import settings
from app_my.core.notify import build_task_event, publish_task_event
from app_my.core.security import create_access_token, create_refresh_token
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wait_relay_subscribed(timeout: float = 10.0) -> bool:
    """等中继协程在 Redis 上订阅成功（否则事件发了没人收，测试会假失败）"""
    from app_my.core.redis_client import get_redis
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            subs = get_redis().pubsub_numsub(settings.WS_NOTIFY_CHANNEL)
            if subs and subs[0][1] >= 1:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def _access_token(user_id: int = 999, tenant_id: int = 4242) -> str:
    return create_access_token(subject=user_id, tenant_id=tenant_id, tenant_role="owner", tenant_plan="free")


def test_handshake_rejected_without_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/notifications"):
            pass


def test_handshake_rejected_with_refresh_token(client):
    """refresh token 不能拿来连 WS（只认 access token）"""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/notifications?token={create_refresh_token(999)}"):
            pass


def test_handshake_rejected_with_garbage_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/notifications?token=not-a-jwt"):
            pass


def test_ping_pong_and_receive_task_push(client):
    """连上后：ping 得 pong；随后发的事件经 Redis 中继推回本连接"""
    assert _wait_relay_subscribed(), "Redis 中继未在超时内订阅频道，检查 6380 容器"

    token = _access_token(user_id=999, tenant_id=4242)
    with client.websocket_connect(f"/ws/notifications?token={token}") as ws:
        ws.send_text("ping")
        assert ws.receive_json() == {"type": "pong"}

        # 模拟 worker 发一条"营养报告完成"事件（tenant 4242 = 本连接所属租户）
        publish_task_event(build_task_event(
            "task-abc-123", "tasks.generate_nutrition_report", "SUCCESS",
            result={"summary": "估算本餐总热量 215.0 千卡"}, tenant_id=4242, user_id=999,
        ))

        evt = ws.receive_json()
        assert evt["type"] == "task"
        assert evt["task_id"] == "task-abc-123"
        assert evt["status"] == "SUCCESS"
        assert evt["result"]["summary"].startswith("估算本餐总热量")