# tests/unit/test_notify.py  —— v3 阶段 8：任务事件构造与发布
"""
覆盖点：
1. build_task_event 字段固定、tenant_id/user_id 转成 int；
2. publish_task_event 真往 Redis 发（返回订阅者数量，是 int）；
3. Redis 抛异常时返回 0，不把异常往外抛（通知不能拖垮任务）。
"""
from app_my.core import notify


def test_build_task_event_shape():
    evt = notify.build_task_event("t-1", "tasks.generate_nutrition_report", "SUCCESS",
                                  result={"a": 1}, tenant_id="7", user_id="11")
    assert evt["type"] == "task"
    assert evt["task_id"] == "t-1"
    assert evt["status"] == "SUCCESS"
    assert evt["result"] == {"a": 1}
    assert evt["error"] is None
    assert evt["tenant_id"] == 7        # 字符串被转成 int
    assert evt["user_id"] == 11


def test_build_task_event_failure_carries_error():
    evt = notify.build_task_event("t-2", "tasks.reindex_milvus", "FAILURE", error="RuntimeError: boom")
    assert evt["status"] == "FAILURE"
    assert evt["error"] == "RuntimeError: boom"
    assert evt["result"] is None


def test_publish_task_event_returns_subscriber_count(monkeypatch):
    """把 get_redis 换成假的：publish 返回 3，则函数返回 3"""
    class FakeRedis:
        def publish(self, channel, data):
            assert channel                        # 频道名非空
            assert isinstance(data, str)          # 已经序列化成 JSON 字符串
            return 3

    monkeypatch.setattr("app_my.core.redis_client.get_redis", lambda: FakeRedis())
    n = notify.publish_task_event(notify.build_task_event("t-3", "tasks.x", "STARTED"))
    assert n == 3


def test_publish_task_event_swallows_redis_error(monkeypatch):
    """Redis 挂了也不能抛异常，返回 0 即可"""
    class BrokenRedis:
        def publish(self, channel, data):
            raise ConnectionError("redis down")

    monkeypatch.setattr("app_my.core.redis_client.get_redis", lambda: BrokenRedis())
    n = notify.publish_task_event(notify.build_task_event("t-4", "tasks.x", "SUCCESS"))
    assert n == 0