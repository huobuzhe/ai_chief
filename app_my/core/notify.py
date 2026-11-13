# app_my/core/notify.py  —— v3 阶段 8：任务事件通知（跨进程）
"""
一条"任务完成"的消息要跨两个进程传递：
    Celery worker 进程（跑任务）  ──发布──▶  Redis 频道  ──订阅──▶  FastAPI 进程（WS 网关）
所以这里只放两件事：
1. build_task_event()：把"哪个任务、什么状态、结果是什么"拼成一个固定结构的 dict；
2. publish_task_event()：把 dict 序列化成 JSON，往 Redis 频道里扔一发。

为什么走 Redis 发布订阅（pub/sub）而不是在 worker 里直接调 WebSocket：
    worker 进程里没有浏览器连接（连接对象在 FastAPI 进程的内存里），
    两个进程唯一的公共通道就是 Redis —— 发布订阅天生就是干这个的。
"""
import json
from typing import Any, Dict, Optional

from app_my.core.config import settings
from app_my.core.logging import logger


def build_task_event(
    task_id: str,
    name: str,
    status: str,
    result: Any = None,
    error: Optional[str] = None,
    tenant_id: int = 0,
    user_id: int = 0,
) -> Dict[str, Any]:
    """
    构造一条任务事件。字段固定，前端拿到的 JSON 永远长这样，好解析。
    status 只会有三种：STARTED（开始）/ SUCCESS（成功）/ FAILURE（失败）。
    tenant_id 是"该推给谁"的路由键——WS 网关按它找到对应租户的连接。
    """
    return {
        "type": "task",                    # 事件大类：以后可能还有 "alert" / "system" 等
        "task_id": task_id,                # 任务编号（前端拿它去掉 GET /tasks/{id} 查详情）
        "name": name,                      # 任务名，如 tasks.reindex_milvus
        "status": status,                  # STARTED / SUCCESS / FAILURE
        "result": result,                  # 成功时的结果（小 dict，别塞大对象）
        "error": error,                    # 失败时的错误摘要（取前 500 字，太长没意义）
        "tenant_id": int(tenant_id or 0),  # 路由键：推给这个租户的所有在线连接
        "user_id": int(user_id or 0),      # 发起人（前端可只给发起人弹提示）
    }


def publish_task_event(payload: Dict[str, Any]) -> int:
    """
    把事件发到 Redis 频道，返回"当时有几个订阅者收到"。
    失败不抛异常：通知只是锦上添花，绝不能因为它挂了就把任务标记成失败。
    """
    from app_my.core.redis_client import get_redis  # 函数内导入，避免模块级循环依赖

    try:
        data = json.dumps(payload, ensure_ascii=False, default=str)  # default=str 兜底：遇到不能序列化的对象就转字符串
        return int(get_redis().publish(settings.WS_NOTIFY_CHANNEL, data))
    except Exception as exc:
        logger.warning("notify: 发布任务事件失败（已忽略，不影响任务本身）: %s", exc)
        return 0