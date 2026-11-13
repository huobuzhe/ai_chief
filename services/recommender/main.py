# services/recommender/main.py
"""
recommender 服务（端口 9123）—— 管"找菜谱"和"排菜谱"，以及知识图谱

拆出来的理由（拆分依据第三条：数据所有权）：
    Milvus 向量库和 Neo4j 图谱**只被这一个服务访问**。
    拆分前 chat 进程里也连着这两个库，现在它们成了 recommender 的"私有数据"，
    别的服务想查菜谱，只能走 HTTP 来问它 —— 这就是微服务的"数据所有权"原则。

对外接口：
    POST /internal/nodes/recommend   食材清单 → 候选菜谱（未排序）
    POST /internal/nodes/rank        候选菜谱 + 用户画像 → 排好序的菜谱
    GET  /kg/ask                     知识图谱问答（阶段 3 的路由，原样搬过来）
    GET  /kg/stats                   图谱规模统计

🔴 本服务最需要注意的一点（也是本次拆分最容易踩的坑）：
    local_recipe_search() 内部会读 current_tenant_id 这个 contextvars 变量做灰度判定。
    单体时代是 coordinator 手动 set 的；现在它跑在 recommender 自己的进程里，
    没人 set 就会一直用默认值 1 —— 表现为"灰度开关对所有租户一起生效/失效"，
    而且**不报错**。
    解决办法在 services/common/app_factory.py 的 TenantVarMiddleware：
    每个请求进来时把 request.state.tenant_id 写进 contextvars。
"""
from typing import List

from fastapi import APIRouter
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app_my.agents.ranker import rank_node
from app_my.agents.recommender import recommend_node
from app_my.api import kg
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


class RecommendIn(BaseModel):
    """推荐接口入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="识别出的食材清单")


class RankIn(BaseModel):
    """重排接口入参。"""
    recipes: List[dict] = Field(default_factory=list, description="候选菜谱（推荐节点的产出）")
    user_profile: dict = Field(default_factory=dict, description="用户画像（目标/忌口/过敏/偏好）")


def _summary_of(node_output: dict) -> str:
    """把节点返回里的 AIMessage 转成纯字符串（LangChain 对象不能进 JSON）。"""
    msgs = node_output.get("messages") or []
    return getattr(msgs[-1], "content", "") if msgs else ""


router = APIRouter()


@router.post("/internal/nodes/recommend")
async def http_recommend(body: RecommendIn):
    """把 recommend_node 包成 HTTP 接口。"""
    out = await recommend_node({"ingredients": body.ingredients or []})
    recipes = out.get("recipes") or []
    logger.info("recommender.http: 检索到 %d 条候选菜谱", len(recipes))
    return {"recipes": recipes, "summary": _summary_of(out)}


@router.post("/internal/nodes/rank")
async def http_rank(body: RankIn):
    """把 rank_node 包成 HTTP 接口。"""
    out = await rank_node({
        "recipes": body.recipes or [],
        "user_profile": body.user_profile or {},
    })
    ranked = out.get("ranked_recipes") or []
    logger.info("recommender.http: 重排完成，%d 条", len(ranked))
    return {"ranked_recipes": ranked, "summary": _summary_of(out)}


app = create_service_app(
    "recommender",
    routers=[
        (router, "", ["推荐内部接口"]),
        (kg.router, "/kg", ["知识图谱"]),
    ],
    enable_auth=True,
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recommender.main:app", host="0.0.0.0", port=9123, reload=False)
