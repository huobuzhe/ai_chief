# app_my/worker/tasks/graph.py  —— v3 阶段 8：Neo4j 知识图谱重建（长任务 ②）
"""
把阶段 3 的建图脚本（scripts/init_kg.py）包成 Celery 任务。

关键取舍：**不复制那 150 行 Cypher，直接复用 scripts/init_kg.py 里已验证的 build()**。
    复制一份"任务专用建图逻辑"看着独立，实则埋雷——以后改了一处忘了改另一处，
    图谱就会出现"脚本建的和任务建的不一样"。DRY（Don't Repeat Yourself）在这里比"看起来清爽"重要。

注意：build() 里是 MERGE 语义——rebuild=False 时只是把现有数据再合并一遍（幂等、不删数据）；
     rebuild=True 会先 `MATCH (n) DETACH DELETE n` 清空全图再建（改了 kg_facts.json 时才需要）。
"""
from typing import Optional

from app_my.worker.base import NotifyTask
from app_my.worker.celery_app import celery_app


@celery_app.task(
    base=NotifyTask,
    name="tasks.rebuild_kg_graph",
    bind=True,
    max_retries=0,     # 图谱重建是"要么成要么不成"，自动重试没意义，失败就让人看日志
)
def rebuild_kg_graph(self, rebuild: bool = False, tenant_id: int = 0, user_id: int = 0) -> dict:
    """
    Neo4j 图谱重建。

    参数：
        rebuild   False（默认）= 增量合并（MERGE，安全、幂等）；
                  True = 先清空全图再重建（谨慎：会短暂清空图谱）
        tenant_id / user_id：通知路由用

    返回：{"nodes": 节点总数, "relationships": 关系总数, "seconds": 耗时}
    """
    import time

    from app_my.core.kg import kg_stats, reset_ingredient_cache, reset_kg_connection

    t0 = time.perf_counter()

    # 复用建图脚本（scripts 是可导入的包，见 scripts/__init__.py）
    from scripts.init_kg import build
    build(rebuild=rebuild)

    # 建图脚本自己开了一个驱动并关掉了；本模块的 kg 连接/食材缓存可能是旧的，重建后清掉
    reset_kg_connection()
    reset_ingredient_cache()

    stats = kg_stats()
    node_total = sum(int(n.get("count", 0) or 0) for n in (stats.get("nodes") or []))
    rel_total = sum(int(r.get("count", 0) or 0) for r in (stats.get("relationships") or []))

    return {
        "nodes": node_total,
        "relationships": rel_total,
        "available": bool(stats.get("available")),
        "seconds": round(time.perf_counter() - t0, 2),
    }