# app_my/worker/base.py  —— v3 阶段 8：所有任务共用的基类（负责通知 + 指标）
"""
为什么要有基类：
    每个任务跑完都干同样三件事——记指标、发通知、算耗时。
    写在基类的钩子里，业务任务就只管"自己的活"，不用每处复制一遍胶水代码。

Celery 给任务预留了四个生命周期钩子，我们在其中三个上做文章：
    before_start(task_id, args, kwargs)   任务真正开跑之前（发 STARTED 事件 + 记开始）
    on_success(retval, task_id, ...)      正常返回（发 SUCCESS 事件 + 记成功 + 耗时）
    on_failure(exc, task_id, ...)         抛异常（发 FAILURE 事件 + 记失败 + 耗时）
    after_return(...)                     无论成败都会跑（本阶段不用）

约定：所有任务的最后两个关键字参数都叫 tenant_id / user_id，
    这样基类能统一从 self.request.kwargs 里取出来，知道"这条通知该推给谁"。
"""
import time

from celery import Task

from app_my.core.logging import logger
from app_my.core.notify import build_task_event, publish_task_event
from app_my.core.worker_metrics import task_failed, task_started, task_succeeded
from app_my.worker.celery_app import celery_app


def _read_ctx(request) -> tuple:
    """
    从任务请求上下文里取出三样东西：
        tenant_id —— 推送给哪个租户（路由键）
        user_id   —— 谁发起的
        queue     —— 这条任务走的是哪条队列（high/default/low），给指标当标签
    kwargs 里没传就兜底成 0，绝不因为缺参数崩掉。

    为什么队列要"回退查 task_routes"：
        真实 worker 执行时，request.delivery_info.routing_key 就是实际队列名；
        但本地 eager 模式（单测）没有 broker，routing_key 是 None。
        这时去 celery_app.conf.task_routes 里查本任务配的队列，保证两种模式下
        打出来的指标标签完全一致（否则单测里看到的是 default，线上是 low，对不上）。
    """
    kwargs = getattr(request, "kwargs", None) or {}
    tenant_id = int(kwargs.get("tenant_id") or 0)
    user_id = int(kwargs.get("user_id") or 0)

    delivery = getattr(request, "delivery_info", None) or {}
    queue = delivery.get("routing_key")
    if not queue:
        name = getattr(request, "task", "") or ""
        route = (celery_app.conf.task_routes or {}).get(name) or {}
        queue = route.get("queue") or celery_app.conf.task_default_queue or "default"
    return tenant_id, user_id, queue


class NotifyTask(Task):
    """带"事件通知 + 指标"的任务基类；业务任务用它作 base 即可。"""

    abstract = True     # 抽象基类，Celery 不会把它本身当成一个任务

    def before_start(self, task_id, args, kwargs):
        """任务开跑前：记开始时间、记 STARTED 指标、发 STARTED 通知"""
        self._s8_t0 = time.perf_counter()
        tenant_id, user_id, queue = _read_ctx(self.request)
        try:
            task_started(self.name, queue)
            publish_task_event(
                build_task_event(task_id, self.name, "STARTED", tenant_id=tenant_id, user_id=user_id)
            )
        except Exception as exc:      # 通知/指标是"附带动作"，出问题也不能影响任务本身
            logger.warning("NotifyTask: STARTED 通知失败（忽略）: %s", exc)

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功：算耗时、记 SUCCESS 指标、发 SUCCESS 通知（把结果一起带走）"""
        tenant_id, user_id, queue = _read_ctx(self.request)
        seconds = time.perf_counter() - getattr(self, "_s8_t0", time.perf_counter())
        try:
            task_succeeded(self.name, queue, seconds)
            publish_task_event(
                build_task_event(task_id, self.name, "SUCCESS", result=retval,
                                 tenant_id=tenant_id, user_id=user_id)
            )
        except Exception as exc:
            logger.warning("NotifyTask: SUCCESS 通知失败（忽略）: %s", exc)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败：算耗时、记 FAILURE 指标、发 FAILURE 通知（把错误摘要带走）"""
        tenant_id, user_id, queue = _read_ctx(self.request)
        seconds = time.perf_counter() - getattr(self, "_s8_t0", time.perf_counter())
        summary = f"{type(exc).__name__}: {exc}"[:500]     # 错误摘要截断，通知没必要带超长堆栈
        try:
            task_failed(self.name, queue, seconds)
            publish_task_event(
                build_task_event(task_id, self.name, "FAILURE", error=summary,
                                 tenant_id=tenant_id, user_id=user_id)
            )
        except Exception as inner:
            logger.warning("NotifyTask: FAILURE 通知失败（忽略）: %s", inner)