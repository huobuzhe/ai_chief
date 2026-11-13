# services/chat/graph_remote.py
"""
远程节点（remote nodes）—— 把"本地函数调用"换成"HTTP 调用别的服务"

一句话理解：
    单体时代，LangGraph 的 recognize 节点 = 直接 `await recognize_node(state)`（进程内函数调用）。
    拆成微服务后，同一个节点 = `await client.post("/internal/nodes/recognize", ...)`（跨进程 HTTP）。
    **图的形状一点没变**（还是 识别→营养/推荐→重排→输出），变的只是节点内部怎么干活。

🔴 本文件的灵魂：降级（degradation）
    每个远程节点都用 try/except 包住。远程服务挂了（连接失败 / 熔断跳闸 / 5xx），
    节点**不抛异常**，而是返回一个"空但合法"的结果 + 一条说明消息。
    为什么：
        LangGraph 里一个节点抛异常，整条工作流就崩了，用户看到 500。
        但"推荐服务挂了"其实不该让"营养估算"也一起完蛋——
        降级后用户拿到的是"营养报告完整、菜谱部分暂时不可用"，体验好得多，
        这正是"故障隔离"要的效果。
    这也就是验收项「杀掉单个服务，其余功能不受影响」的实现方式。
"""
from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import AIMessage

from app_my.agents.output import output_node
from app_my.agents.recognizer import message_content_to_text
from app_my.core.logging import logger
from app_my.core.tenant import current_tenant_id
from services.common.client import get_client


def _user_text(state: dict) -> str:
    """从 state 里取用户最后一句话的纯文本（支持多模态 content 是 list 的情况）。"""
    messages = state.get("messages") or []
    if not messages:
        return ""
    return message_content_to_text(messages[-1].content)


def _ai(content: str) -> List[AIMessage]:
    """包一条 AIMessage —— 图要求节点返回 messages，用来记录过程。"""
    return [AIMessage(content=content)]


# ------------------------------------------------------------------ ① 识别节点（远程）
async def recognize_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做食材识别。"""
    tenant_id = current_tenant_id.get()
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/recognize",
            {"text": _user_text(state), "image_url": state.get("image_url") or []},
            tenant_id=tenant_id,
        )
        return {
            "ingredients": data.get("ingredients") or [],
            "messages": _ai(data.get("summary") or "[识别] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recognize 失败，已降级：%s", exc)
        return {"ingredients": [], "messages": _ai(f"[识别] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ② 营养节点（远程）
async def nutrition_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做营养估算（营养和识别同域，都在 recognizer）。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"nutrition": {}, "messages": _ai("[营养] 无食材，跳过")}
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/nutrition",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "nutrition": data.get("nutrition") or {},
            "messages": _ai(data.get("summary") or "[营养] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.nutrition 失败，已降级：%s", exc)
        return {"nutrition": {}, "messages": _ai(f"[营养] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ③ 推荐节点（远程）
async def recommend_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）检索候选菜谱。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"recipes": [], "messages": _ai("[推荐] 无食材，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/recommend",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "recipes": data.get("recipes") or [],
            "messages": _ai(data.get("summary") or "[推荐] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recommend 失败，已降级：%s", exc)
        # 降级：没有菜谱，但工作流继续往下走（营养部分仍然完整）
        return {"recipes": [], "messages": _ai(f"[推荐] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ④ 重排节点（远程）
async def rank_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）做个性化重排。"""
    tenant_id = current_tenant_id.get()
    recipes = state.get("recipes") or []
    if not recipes:
        return {"ranked_recipes": [], "messages": _ai("[重排] 无候选菜谱，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/rank",
            {"recipes": recipes, "user_profile": state.get("user_profile") or {}},
            tenant_id=tenant_id,
        )
        return {
            "ranked_recipes": data.get("ranked_recipes") or [],
            "messages": _ai(data.get("summary") or "[重排] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.rank 失败，已降级：%s", exc)
        return {"ranked_recipes": [], "messages": _ai(f"[重排] 服务不可用，已跳过：{exc}")}


def remote_nodes() -> Dict[str, object]:
    """
    返回"远程版"的节点表。

    注意 output 仍然是**本地**的：
    它是纯文本拼装，不调外部资源，没有必要再跨一次网络（多一跳 = 多一个故障点）。
    这也体现了一条拆分原则：**不是所有东西都要拆，只拆有独立资源/故障特征的**。
    """
    return {
        "recognize": recognize_node_remote,
        "nutrition": nutrition_node_remote,
        "recommend": recommend_node_remote,
        "rank": rank_node_remote,
        "output": output_node,
    }
