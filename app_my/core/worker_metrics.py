# app_my/core/worker_metrics.py  —— v3 阶段 8：Celery worker 自己的指标
"""
为什么单开一个文件、不和阶段 7 的 metrics.py 合并：
    metrics.py 是"FastAPI 进程"的指标（HTTP QPS / 延迟 / token 成本），
    本文件是"Celery worker 进程"的指标（任务次数 / 耗时 / 失败 / 队列深度）。
    两个进程各跑各的，Prometheus 也分两个 job 抓（9002/metrics 与 9101/metrics）。
    分开写的好处：API 进程不会平白无故多出 4 个一直是 0 的 celery_* 指标。

暴露方式：worker 启动后开一个极小的 HTTP 服务（prometheus_client.start_http_server），
    Prometheus 直接抓 http://host.docker.internal:9101/metrics 即可。
"""
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# 任务执行次数：按 任务名 / 队列 / 结果 三个维度拆
CELERY_TASK_TOTAL = Counter(
    "celery_task_total",
    "Celery 任务执行次数（按 task / queue / status 拆）",
    labelnames=("task", "queue", "status"),
)

# 任务耗时直方图：看"重索引一次要多久""图谱重建多久"
CELERY_TASK_DURATION = Histogram(
    "celery_task_duration_seconds",
    "Celery 任务耗时（秒）",
    labelnames=("task",),
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

# 任务失败次数：单独一个 Counter，告警可以直接盯它
CELERY_TASK_FAILURES = Counter(
    "celery_task_failures_total",
    "Celery 任务失败次数",
    labelnames=("task",),
)

# 各队列待处理任务数：worker 侧按"最近一次拉取到的队列长度"更新
CELERY_QUEUE_DEPTH = Gauge(
    "celery_queue_depth",
    "各队列待处理任务数",
    labelnames=("queue",),
)


def task_started(task: str, queue: str) -> None:
    """任务开始：记一次 STARTED"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="STARTED").inc()


def task_succeeded(task: str, queue: str, seconds: float) -> None:
    """任务成功：记 SUCCESS + 耗时"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="SUCCESS").inc()
    CELERY_TASK_DURATION.labels(task=task).observe(max(seconds, 0.0))


def task_failed(task: str, queue: str, seconds: float) -> None:
    """任务失败：记 FAILURE + 失败计数 + 耗时（失败的耗时同样值得看）"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="FAILURE").inc()
    CELERY_TASK_FAILURES.labels(task=task).inc()
    CELERY_TASK_DURATION.labels(task=task).observe(max(seconds, 0.0))


def queue_depth(queue: str, depth: int) -> None:
    """更新某队列的待处理数（worker 侧定时调用）"""
    CELERY_QUEUE_DEPTH.labels(queue=queue).set(max(depth, 0))


def start_metrics_server(port: int) -> None:
    """
    在 worker 进程里起一个后台线程，对外暴露 /metrics。
    注意：start_http_server 只能调用一次；重复调用会抛 OSError（端口被占），
    所以 worker_ready 信号里要 try/except 兜住。
    """
    start_http_server(port)