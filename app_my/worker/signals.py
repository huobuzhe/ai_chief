# app_my/worker/signals.py  —— v3 阶段 8：worker 生命周期信号（只负责"起指标服务 + 刷队列长度"）
"""
Celery 的"信号（signal）"= 框架在特定时刻广播的事件，我们挂个回调进去干活。
这里用两个：
    worker_ready  —— worker 启动完成的那一刻：开指标 HTTP 服务 + 读一次队列长度
    task_postrun  —— 每个任务跑完之后：刷新队列长度（这样 Grafana 上能看出"积压在涨还是消"）

为什么要用模块级 _IS_WORKER 开关：
    task_postrun 在"本地 eager 模式"下也会触发（单测里就是），
    但单测不该去连 Redis 数队列长度。用 worker_ready 置位的开关一挡，单测里就是空操作。
"""
from celery.signals import task_postrun, worker_ready, worker_shutdown

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.core.worker_metrics import queue_depth, start_metrics_server

_IS_WORKER = False          # 只有真正的 worker 进程在 worker_ready 后才会置 True
_METRICS_STARTED = False    # start_http_server 只能调一次，防止重复启动报端口占用
QUEUES = ("high", "default", "low")


def refresh_queue_depth() -> None:
    """读三条队列在 Redis 里的当前长度（LLEN），写进 celery_queue_depth 指标"""
    try:
        from app_my.core.redis_client import get_redis
        r = get_redis()
        for q in QUEUES:
            queue_depth(q, int(r.llen(q) or 0))
    except Exception as exc:      # Redis 抽风不能让指标拖垮 worker
        logger.warning("worker: 读取队列长度失败（忽略）: %s", exc)


@worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):
    """worker 就绪：暴露 /metrics、记录一次队列长度"""
    global _IS_WORKER, _METRICS_STARTED
    _IS_WORKER = True
    if not _METRICS_STARTED:
        try:
            start_metrics_server(settings.WORKER_METRICS_PORT)
            _METRICS_STARTED = True
            logger.info("worker: 指标已暴露 http://0.0.0.0:%d/metrics", settings.WORKER_METRICS_PORT)
        except Exception as exc:
            logger.warning("worker: 指标服务启动失败（可能端口被占）: %s", exc)
    refresh_queue_depth()
    logger.info("worker: 就绪，队列 %s", " / ".join(QUEUES))


@task_postrun.connect
def _on_task_postrun(sender=None, **kwargs):
    """每个任务结束后刷一次队列长度（指标服务没起时直接跳过）"""
    if _IS_WORKER and _METRICS_STARTED:
        refresh_queue_depth()


@worker_shutdown.connect
def _on_worker_shutdown(sender=None, **kwargs):
    logger.info("worker: 正在关闭")