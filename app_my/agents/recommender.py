# app_my/agents/recommender.py
"""
节点③ 推荐（recommender）—— 先查自家菜谱库，查不到再联网

为什么要这个顺序：
    本地库是我们自己导入、有完整食材/步骤/热量的"可信数据"；
    联网结果格式五花八门、还可能指到广告页。所以：
        本地 RAG 有结果 → 用本地（不联网，省额度、结果可控）
        本地结果为空   → 才用 Tavily 兜底，且结果一样要经过统一结构包装

修订版对照：
    - H2：`TavilySearch` 的密钥参数名实测是 `tavily_api_key`（不是 api_key），
      且不要依赖 SDK 去读环境变量（本项目 .env 由 pydantic-settings 读取，
      不会自动进 os.environ），所以要显式传。
    - 并行：本节点与营养节点同时跑（都由识别节点触发），互不依赖。
"""
from __future__ import annotations

from typing import List

from langchain_core.messages import AIMessage

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.tools.recipe_rag_tool import local_recipe_search, normalize_recipe


def _get_tavily():
    """
    惰性创建 Tavily 搜索工具：没有配 TAVILY_API_KEY 就返回 None（不报错、不联网）。
    这样"没联网额度"也是一种正常降级状态，而不是故障。
    """
    if not settings.TAVILY_API_KEY:
        logger.info("recommender: 未配置 TAVILY_API_KEY，跳过联网兜底")
        return None
    try:
        from langchain_tavily import TavilySearch

        return TavilySearch(
            tavily_api_key=settings.TAVILY_API_KEY,   # 实测参数名（见文件头 H2 说明）
            max_results=5,
            topic="general",
        )
    except Exception as e:
        logger.error(f"recommender: Tavily 初始化失败（{type(e).__name__}: {e}）")
        return None


def _web_to_recipe(item: dict) -> dict:
    """把一条网页搜索结果包装成和本地菜谱同构的字典，方便下游统一处理"""
    return normalize_recipe({
        "name": item.get("title", "网页菜谱"),
        "tags": ["联网结果"],
        "ingredients": [],
        "steps": [item.get("content", "")[:200]],
        "difficulty": "中等",
    }) | {"source_url": item.get("url", ""), "origin": "web"}


async def recommend_node(state: dict) -> dict:
    """推荐节点：ingredients → recipes（候选菜谱，未排序）"""
    ingredients = state.get("ingredients") or []
    if not ingredients:
        logger.info("recommender: 没有食材，跳过推荐")
        return {"recipes": [], "messages": [AIMessage(content="[推荐] 无食材，跳过菜谱检索")]}

    # 用前 5 个可用食材拼查询词（太多会把检索意图稀释掉）
    names = [i.get("name", "") for i in ingredients if i.get("usable", True)][:5]
    query = " ".join([n for n in names if n])

    # ---------- 第 1 路：本地 RAG ----------
    rag_recipes: List[dict] = []
    try:
        rag_recipes = local_recipe_search(query, k=5)
    except Exception as e:
        logger.error(f"recommender: 本地检索失败（{type(e).__name__}: {e}）")

    # ---------- 第 2 路：联网兜底（只在本地没结果时触发）----------
    web_recipes: List[dict] = []
    if not rag_recipes:
        tavily = _get_tavily()
        if tavily:
            try:
                res = tavily.invoke({"query": f"{query} 家常菜谱 做法"})
                # Tavily 返回结构：{"results": [...]} 或直接 list，两种都兼容
                items = res.get("results", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])
                web_recipes = [_web_to_recipe(i) for i in items]
            except Exception as e:
                logger.error(f"recommender: 联网检索失败（{type(e).__name__}: {e}）")

    # ---------- 去重（本地结果优先，同名只留一条）----------
    seen, unique = set(), []
    for r in rag_recipes + web_recipes:
        key = r.get("name", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    summary = f"[推荐] 本地库命中 {len(rag_recipes)} 条，联网兜底 {len(web_recipes)} 条，去重后 {len(unique)} 条。"
    logger.info(f"recommender: {summary}")
    return {"recipes": unique[:10], "messages": [AIMessage(content=summary)]}