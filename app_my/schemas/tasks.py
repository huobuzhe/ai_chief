# app_my/schemas/tasks.py  —— v3 阶段 8：异步任务接口的进出数据模型
"""只描述"接口进出的数据长什么样"，不碰任务与数据库（和 schemas/auth.py 一个风格）。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReindexIn(BaseModel):
    """Milvus 重索引请求"""
    rebuild: bool = Field(True, description="True=先清场再全量重建；False=不清场，按 recipe_id 覆盖")


class KgRebuildIn(BaseModel):
    """Neo4j 图谱重建请求"""
    rebuild: bool = Field(False, description="True=清空全图再重建（会短暂清空）；False=增量合并")


class NutritionReportIn(BaseModel):
    """营养报告请求：至少要有一个食材"""
    ingredients: List[str] = Field(..., min_length=1, description="食材列表，如 ['鸡胸肉 200克']")


class TaskSubmitOut(BaseModel):
    """提交任务的响应"""
    task_id: str            # 任务编号：后续查状态、WS 事件里都用它
    name: str               # 任务名（tasks.xxx）
    queue: str              # 落到哪条队列（high/default/low）
    status: str = "PENDING"  # 刚提交必然是 PENDING


class TaskStatusOut(BaseModel):
    """查询任务状态的响应"""
    task_id: str
    status: str                          # PENDING / STARTED / SUCCESS / FAILURE
    result: Optional[Dict[str, Any]] = None   # 成功时的结果
    error: Optional[str] = None               # 失败时的错误摘要