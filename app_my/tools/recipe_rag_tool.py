# app_my/tools/recipe_rag_tool.py
"""
【工具】search_local_recipes —— 本地菜谱库检索（RAG 的"取"这一步）

它是干什么的：
    给一句"食材话"（如 "鸡胸肉 西兰花 减脂"），从阶段 2 建好的菜谱知识库里
    召回最相关的菜谱，返回结构化结果（菜名、食材、步骤、热量、标签…）。

为什么要单独包一层工具：
    1. 阶段 2 的 hybrid_search 返回的是"向量库元数据"（tags 是逗号串、没有食材和步骤），
       节点直接用会很别扭；这里统一补全成"菜谱完整对象"，后续节点只认一种格式。
    2. 工具可以被大模型调用，也可以被代码直接调用（本项目两种都在用：
       推荐节点直接调用它，保证稳定；需要模型自主决策时也能挂给模型）。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app_my.core.logging import logger
from app_my.knowledge.data_loader import load_recipes
from app_my.knowledge.retriever import hybrid_search

from app_my.knowledge.retriever import hybrid_search_v2   # v3阶段6：三路混合检索

# 难度中文 → 分值（1 最简单），重排节点用它做"省事优先"的加分
DIFFICULTY_LEVEL = {"简单": 1, "中等": 2, "困难": 3}


class RecipeSearchInput(BaseModel):
    """工具入参：一个查询词 + 想要几条"""

    query: str = Field(..., description="检索关键词，通常是食材名或饮食目标，例如 '鸡胸肉 西兰花 减脂'")
    k: int = Field(5, ge=1, le=20, description="返回条数，默认 5")


@lru_cache(maxsize=1)
def _recipe_index() -> Dict[str, dict]:
    """
    建立 recipe_id → 完整菜谱 的索引（只建一次，缓存在进程里）。

    用途：hybrid_search 返回的 metadata 里没有 ingredients/steps，
    但展示给用户必须要有，所以按 recipe_id 回原始 JSON 里取。
    """
    return {r["recipe_id"]: r for r in load_recipes()}


def normalize_recipe(raw: dict, score: Optional[float] = None) -> dict:
    """
    把一条菜谱统一成固定结构，兼容两种来源：
      - 阶段 2 向量库的 metadata（tags 是逗号字符串，无 ingredients/steps）
      - recipes.json 里的原始菜谱（tags 是列表）

    返回的字典字段固定，后面所有节点都按这个结构取数，不用再判断类型。
    """
    tags = raw.get("tags", "")
    if isinstance(tags, str):                    # "家常,快手" → ["家常", "快手"]
        tags = [t for t in tags.split(",") if t]
    ingredients = raw.get("ingredients", [])
    steps = raw.get("steps", [])
    difficulty = raw.get("difficulty", "中等")
    return {
        "recipe_id": raw.get("recipe_id"),
        "name": raw.get("name", "未命名菜谱"),
        "cuisine": raw.get("cuisine", ""),
        "difficulty": difficulty,
        "difficulty_level": DIFFICULTY_LEVEL.get(difficulty, 2),  # 中文 → 1/2/3
        "time_minutes": raw.get("time_minutes", 0),
        "calories": raw.get("calories", 0),
        "protein": raw.get("protein", 0),
        "fat": raw.get("fat", 0),
        "carbs": raw.get("carbs", 0),
        "tags": tags,
        "ingredients": list(ingredients),
        "steps": list(steps),
        "score": score,
    }


# def local_recipe_search(query: str, k: int = 5) -> List[dict]:
#     """
#     检索主逻辑（纯函数，方便单测；工具函数 search_local_recipes 只是它的壳）

#     流程：
#         hybrid_search → 逐条按 recipe_id 补全 → normalize_recipe 统一结构
#     """
#     hits = hybrid_search(query, k=k)          # 阶段 2 写好的向量+BM25 混合检索
#     index = _recipe_index()
#     results: List[dict] = []
#     for hit in hits:
#         meta = hit.get("metadata", {}) or {}
#         rid = meta.get("recipe_id")
#         base = index.get(rid) if rid else None
#         # 优先用原始菜谱（字段全），没有就退回用 metadata（至少菜名有）
#         merged = {**meta, **(base or {})}
#         results.append(normalize_recipe(merged, score=hit.get("score")))
#     logger.info(f"recipe_rag_tool: query='{query}' 命中 {len(results)} 条")
#     return results

##6阶段local_recipe_search 函数整体替换
def _hybrid_v2_enabled() -> bool:
    """
    读 Feature Flag（阶段 4 落地）；flag 不存在/异常 = 关（走 v1，稳定优先）。

    修正点：is_feature_enabled 的真实签名是 (db, name, tenant_id) —— 三个都要给。
       原写法 is_feature_enabled("hybrid_v2") 会抛 TypeError 被 except 吞掉，
       结果恒为 False，开关形同摆设。这里补上 db 会话 + 当前租户 id。
    """
    try:
        from app_my.core.feature_flag import is_feature_enabled
        from app_my.core.tenant import current_tenant_id as _tenant_ctx
        from app_my.db.session import SessionLocal

        db = SessionLocal()
        try:
            return bool(is_feature_enabled(db, "hybrid_v2", _tenant_ctx.get()))
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"hybrid_v2 flag 读取失败，本次走 v1：{exc}")
        return False

def local_recipe_search(query: str, k: int = 5) -> List[dict]:
    """
    检索主逻辑（纯函数，方便单测；工具函数 search_local_recipes 只是它的壳）

    流程：
        （Feature Flag 选择 v1 / v2 检索路径）
        hybrid_search / hybrid_search_v2
        → 逐条按 recipe_id 补全 → normalize_recipe 统一结构
    """

    v2 = _hybrid_v2_enabled()                       #  只判一次；原写法在日志里又判了一次（多开一次 DB 会话）
    if v2:
        hits = hybrid_search_v2(query, k=k)         # v3阶段6：三路（向量50+BM25 30+图谱20）
    else:
        hits = hybrid_search(query, k=k)            # v1：两路（向量+BM25）
    index = _recipe_index()
    results: List[dict] = []
    for hit in hits:
        meta = hit.get("metadata", {}) or {}
        rid = meta.get("recipe_id") or hit.get("recipe_id")   # v2 的结构把 recipe_id 放在顶层
        base = index.get(rid) if rid else None
        merged = {**meta, **(base or {})}
        results.append(normalize_recipe(merged, score=hit.get("score")))
    logger.info(f"recipe_rag_tool: query='{query}' 命中 {len(results)} 条 "
                f"（路径={'v2三路' if v2 else 'v1两路'}）")
    return results

@tool("search_local_recipes", args_schema=RecipeSearchInput)
def search_local_recipes(query: str, k: int = 5) -> List[dict]:
    """
    从本地菜谱知识库检索菜谱（向量 + 关键词混合召回）。

    什么时候用：用户给了食材、想问"能做什么菜"时调用。
    注意：只查本地已导入的菜谱库；库里没有结果时才考虑联网搜索。
    """
    return local_recipe_search(query, k)