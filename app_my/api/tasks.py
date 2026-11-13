# app_my/api/tasks.py  —— v3 阶段 8：长任务提交 + 状态查询接口
"""
四个接口（全部受 JWT 鉴权保护，跟着 AuthMiddleware 走，无需额外写鉴权）：
    POST /tasks/reindex-milvus      提交 Milvus 重索引      → 队列 high
    POST /tasks/rebuild-kg          提交图谱重建            → 队列 default
    POST /tasks/nutrition-report    提交营养报告            → 队列 low
    GET  /tasks/{task_id}           查任务状态与结果

设计要点：
- 提交接口做的最重的事只是"往 Redis 丢一条消息"，所以是毫秒级返回 —— 这就是"任务异步化"的收益。
- `.delay(...)` 是 Celery 的固定写法：把函数名 + 参数序列化后投进队列，立刻返回一个 AsyncResult（含 id）。
  它不会等任务跑完（除非 CELERY_TASK_ALWAYS_EAGER=True，那是单测模式）。
- 状态查询直接问 Celery 的 result backend（Redis db2），拿到 PENDING/STARTED/SUCCESS/FAILURE。
"""
from celery.result import AsyncResult
from fastapi import APIRouter, Request

from app_my.schemas.tasks import KgRebuildIn, NutritionReportIn, ReindexIn
from app_my.worker.celery_app import celery_app
from app_my.worker.tasks.graph import rebuild_kg_graph
from app_my.worker.tasks.nutrition import generate_nutrition_report
from app_my.worker.tasks.reindex import reindex_milvus

router = APIRouter()


def _caller(request: Request):
    """从请求上下文取"谁提交的"：租户（推送给谁）+ 用户（谁发起）"""
    tenant_id = int(getattr(request.state, "tenant_id", None) or 0)
    user_id = int(getattr(request.state, "user_id", None) or 0)
    return tenant_id, user_id


@router.post("/reindex-milvus")
async def submit_reindex(request: Request, body: ReindexIn):
    """提交 Milvus 菜谱向量重索引（长任务，接口立即返回 task_id）"""
    tenant_id, user_id = _caller(request)
    result = reindex_milvus.delay(rebuild=body.rebuild, tenant_id=tenant_id, user_id=user_id)
    return {"task_id": result.id, "name": "tasks.reindex_milvus", "queue": "high", "status": "PENDING"}


@router.post("/rebuild-kg")
async def submit_rebuild_kg(request: Request, body: KgRebuildIn):
    """提交 Neo4j 知识图谱重建（长任务，接口立即返回 task_id）"""
    tenant_id, user_id = _caller(request)
    result = rebuild_kg_graph.delay(rebuild=body.rebuild, tenant_id=tenant_id, user_id=user_id)
    return {"task_id": result.id, "name": "tasks.rebuild_kg_graph", "queue": "default", "status": "PENDING"}


@router.post("/nutrition-report")
async def submit_nutrition_report(request: Request, body: NutritionReportIn):
    """提交营养报告生成（长任务，接口立即返回 task_id）"""
    tenant_id, user_id = _caller(request)
    result = generate_nutrition_report.delay(
        ingredients=body.ingredients, tenant_id=tenant_id, user_id=user_id
    )
    return {"task_id": result.id, "name": "tasks.generate_nutrition_report", "queue": "low", "status": "PENDING"}


@router.get("/{task_id}")
async def get_task_status(task_id: str):
    """
    查询任务状态。

    返回：
        status = PENDING   —— 排队中 / 尚未被 worker 取走
        status = STARTED   —— worker 正在跑
        status = SUCCESS   —— 跑完了，result 字段是任务返回值
        status = FAILURE   —— 跑挂了，error 字段是错误摘要
    """
    res = AsyncResult(task_id, app=celery_app)
    payload = {"task_id": task_id, "status": res.status, "result": None, "error": None}
    if res.successful():
        payload["result"] = res.result
    elif res.failed():
        payload["error"] = str(res.result)
    return payload