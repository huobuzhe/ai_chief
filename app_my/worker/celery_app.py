# app_my/worker/celery_app.py  —— v3 阶段 8：Celery 应用（全局唯一实例）
"""
这个文件是"任务系统的大脑"：一个 Celery 实例，三处地方共用它——
1. 提交任务的 API 进程（app_my/api/tasks.py 用 celery_app.AsyncResult 查结果）；
2. 执行任务的 worker 进程（启动命令 `celery -A app_my.worker.celery_app:celery_app worker ...`）；
3. 单元测试（把 task_always_eager 打开，任务就地同步执行，不用起 worker）。

关键配置逐项说清（每一行都是"不写会怎样"级别的重要）：
- broker_url        ：任务"寄存在哪"。worker 从这个 Redis db 取任务。不配则默认 amqp://guest@localhost，本机没有 RabbitMQ 就直接连不上。
- result_backend    ：任务结果"存在哪"。API 用它查状态。不配则查不到结果，只能拿到 PENDING。
- task_serializer   ：任务参数怎么序列化。默认 json，安全（pickle 有反序列化执行任意代码的风险）。
- task_track_started：任务开始执行时把状态写成 STARTED。不写就永远是 PENDING→SUCCESS，看不到"正在跑"。
- task_acks_late    ：任务"跑完才 ack"。worker 中途崩了任务会被重新投递，不丢任务。
- worker_prefetch_multiplier：worker 一次预取几条。设 1 = 拿一条跑一条，长任务不会被一个 worker 全囤走。
- task_queues       ：声明三条队列 high / default / low。
- task_routes       ：把不同任务名路由到不同队列（这就是"任务分级"）。
- timezone/enable_utc：统一按 UTC 存时间，展示时区给 Asia/Shanghai（避免夏令时/跨时区错乱）。
"""
from celery import Celery
from kombu import Queue

from app_my.core.config import settings

celery_app = Celery("ai_chief")

celery_app.conf.update(
    # ---- 连接 ----
    broker_url=settings.CELERY_BROKER_URL,                    # 复用 Redis 6380 的 db 1，与业务 db 0 隔离
    result_backend=settings.CELERY_RESULT_BACKEND,            # 结果放 Redis 6380 的 db 2
    broker_connection_retry_on_startup=True,                  # 启动时 broker 暂时连不上就重试（而不是直接崩）

    # ---- 序列化 ----
    task_serializer="json",                                   # 任务参数用 JSON
    result_serializer="json",                                 # 任务结果用 JSON
    accept_content=["json"],                                  # 只接受 JSON，拒绝 pickle

    # ---- 时间 ----
    timezone="Asia/Shanghai",
    enable_utc=True,

    # ---- 可靠性 ----
    task_acks_late=True,                                      # 跑完才确认，worker 崩溃任务自动重投
    worker_prefetch_multiplier=1,                             # 一次只预取一条，长任务不囤积
    task_track_started=True,                                  # 允许状态出现 STARTED
    result_expires=settings.CELERY_TASK_RESULT_EXPIRES,       # 结果保留 1 小时后自动清

    # ---- 三条队列 + 任务分级路由 ----
    task_default_queue="default",
    task_queues=(Queue("high"), Queue("default"), Queue("low")),
    task_routes={
        "tasks.reindex_milvus": {"queue": "high"},            # 运维级：向量库重索引，最要紧
        "tasks.rebuild_kg_graph": {"queue": "default"},       # 数据级：图谱重建
        "tasks.generate_nutrition_report": {"queue": "low"},  # 用户级：营养报告，繁但不急
    },

    # ---- 本地/单测：不进 worker，调用即同步执行 ----
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,      # 默认 False；单测里设 True
    task_eager_propagates=True,                               # eager 模式下任务异常直接抛出（测试才看得见）
    task_store_eager_result=True,                             # eager 的结果也写 backend（这样 GET /tasks 查得到）

    # ---- 启动时要 import 哪些模块，任务才会被注册 ----
    # worker 和 API 都靠它把三个任务 + 信号接进来；不写的话 worker 起来后"找不到任务"
    imports=(
        "app_my.worker.tasks.reindex",
        "app_my.worker.tasks.graph",
        "app_my.worker.tasks.nutrition",
        "app_my.worker.signals",
    ),
)