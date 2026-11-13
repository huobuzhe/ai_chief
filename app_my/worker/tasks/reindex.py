# app_my/worker/tasks/reindex.py  —— v3 阶段 8：Milvus 菜谱向量重索引（长任务 ①）
"""
把阶段 6 的导入脚本（scripts/import_recipes_milvus.py）搬进 Celery 任务。
同步脚本要人守着终端跑，还卡在 API 进程里；任务化之后：
    接口立刻返回 task_id → worker 慢慢跑（要调几十次 embedding 接口）→ 跑完推送结果。

为什么函数体里才 import（而不是文件顶部 import）：
    Celery 启动时要 import 本模块来"发现任务"，如果顶部就 import pymilvus / langchain，
    worker 启动会慢好几秒，而且 API 进程（也会 import 到本模块）平白多加载一堆东西。
    把重依赖推迟到"任务真正执行"的那一刻，是 Celery 任务的标准写法。
"""
from app_my.worker.base import NotifyTask
from app_my.worker.celery_app import celery_app

BATCH_SIZE = 10     # DashScope embedding 接口单次最多 10 条文本，超了会被拒


@celery_app.task(
    base=NotifyTask,          # 继承"通知 + 指标"基类
    name="tasks.reindex_milvus",
    bind=True,                # 让第一个参数是 self（本任务其实用不到，但基类钩子需要绑定实例）
    max_retries=1,            # 临时故障（比如 embedding 接口抖一下）最多自动重试 1 次
    default_retry_delay=10,   # 重试间隔 10 秒
)
def reindex_milvus(self, rebuild: bool = True, tenant_id: int = 0, user_id: int = 0) -> dict:
    """
    Milvus 向量库重索引。

    参数：
        rebuild   True = 先删旧集合再从零写（改了菜谱文本/换 embedding 模型时用）；
                  False = 不清场，直接按 recipe_id upsert 覆盖（增量刷新，安全）
        tenant_id 发起任务的租户（基类用它决定通知推给谁）
        user_id   发起人

    返回：{"rows": 实际写入条数, "expected": 菜谱总数, "row_count": 集合当前行数, "seconds": 耗时}
    """
    import time

    from app_my.core.cache import invalidate_prefix
    from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
    from app_my.knowledge.embedding import embed_texts
    from app_my.knowledge.milvus_store import (
        clear_collection,
        collection_row_count,
        ensure_collection,
        upsert_recipes,
    )

    t0 = time.perf_counter()
    recipes = load_recipes()                       # 读 app_my/knowledge/data/recipes.json

    if rebuild:
        if not clear_collection():                 # 清场失败 = Milvus 没起或连不上
            raise RuntimeError("Milvus 不可用：清场失败，请先确认 ai_chief_milvus 容器已启动")
    if not ensure_collection():                    # 幂等：集合在就直接用，不在就按 schema 建
        raise RuntimeError("Milvus 建集合失败（ensure_collection 返回 False）")

    total = 0
    for i in range(0, len(recipes), BATCH_SIZE):
        batch = recipes[i:i + BATCH_SIZE]
        texts = [recipe_to_text(r) for r in batch]
        vectors = embed_texts(texts)               # 真实调用 DashScope，一次最多 10 条
        rows = [
            {
                "recipe_id": r["recipe_id"],       # 主键：重复写按 id 覆盖（幂等的第二重保险）
                "text": t,                          # 与 PGVector 存的同一份菜谱文本
                "vector": v,                        # 1024 维向量
                "metadata": recipe_to_metadata(r),  # 检索时直接带出的元数据
            }
            for r, t, v in zip(batch, texts, vectors)
        ]
        total += upsert_recipes(rows)

    # 数据变了：v1（rag）与 v2（rag2）两条检索路径的缓存都失效，否则用户查到的还是旧菜
    invalidate_prefix("rag")
    invalidate_prefix("rag2")

    return {
        "rows": total,
        "expected": len(recipes),
        "row_count": collection_row_count(),
        "seconds": round(time.perf_counter() - t0, 2),
    }