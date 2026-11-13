# app_my/api/kg.py
"""
阶段 3（v3.0）：知识图谱推理接口——回答"XX 病患者能不能吃 YY"

接口（受 JWT 鉴权保护，需要登录后带 access token 访问）：
    GET /kg/ask?ingredient=土豆&condition=糖尿病    多跳推理问答
    GET /kg/stats                                   图谱规模统计（排障/演示用）

为什么这个接口有存在感：
    向量检索（RAG）回答的是"哪些菜谱和你的食材相似"；
    图谱回答的是"你的身体状况和这个食材有什么关系、为什么、影响哪些菜"。
    返回的每一个字段都来自图上一条真实存在的边——可解释、可追溯、不幻觉。


v3 阶段 5 升级：问答与统计挂多级缓存。
- kg 知识是全局的（不随租户变），缓存安全；
- 缓存在 API 层挂（不挂在 core/kg.ask 上），避免单测里 mock 掉 Neo4j 后被旧缓存污染。
"""
from fastapi import APIRouter, Query, Request, HTTPException

from app_my.core import kg as kg_module

from app_my.core.cache import cached

router = APIRouter()

# 模块级包装：图谱问答 10 分钟缓存（知识图谱几乎不变，可以缓存久一些）
_ask_cached = cached(prefix="kg", ttl=600, null_ttl=60)(kg_module.ask)
# 图谱规模统计 1 分钟缓存（演示/排障用，新鲜度要求低）
_stats_cached = cached(prefix="kgstats", ttl=60)(kg_module.kg_stats)

@router.get("/ask")
async def kg_ask(
    request: Request,
    ingredient: str = Query(..., min_length=1, max_length=30, description="食材名，如：土豆"),
    condition: str = Query(..., min_length=1, max_length=30, description="健康状况名，如：糖尿病/痛风/高血压"),
):
    """
    图谱依据的多跳推理：结论 + 理由 + 营养证据 + 受影响菜谱。

    支持"高血糖"这类别名（图上 Condition 节点带 aka 别名列表）。
    图谱不可用时明确返回 graph_available=false（诚实告知，不冒充"没禁忌"）。
    """
    # 5阶段删掉了原来租户鉴权逻辑：tenant_id 相关代码全部移除
    # tenant_id = getattr(request.state, "tenant_id", None)
    # if tenant_id is None:
    #     raise HTTPException(status_code=401, detail="需要登录租户才能调用")
    #return kg_module.ask(ingredient.strip(), condition.strip())
    return _ask_cached(ingredient.strip(), condition.strip())


@router.get("/stats")
async def kg_stats():
    """图谱规模统计：四类节点/四类关系各多少个（演示和排障用）"""
    # 5阶段不再直接调用 kg_module.kg_stats()，调用包装后的缓存版本
    #return kg_module.kg_stats()
    return _stats_cached()
