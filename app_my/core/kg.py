# app_my/core/kg.py
"""
阶段 3（v3.0）：知识图谱查询封装——向量检索管"相似"，图谱管"关系推理"

为什么需要图谱（向量检索做不到的事）：
    RAG 检索"土豆"能召回土豆相关菜谱（相似度），
    但回答不了"糖尿病患者能不能吃土豆、为什么、哪些菜要小心"——
    这是关系推理：Condition-(禁忌)->Ingredient-(入菜)->Recipe，
    三跳路径上每一跳都是明确的边，答案有据可查（区别于模型的"幻觉式回答"）。

设计三原则：
1. 图谱是增强不是依赖：Neo4j 挂了/没建图，所有查询返回空结果并记日志，
   主流程（对话/推荐）照常工作——图谱只在可用时"加分"，永远不"挡路"。
2. 查询收口：所有 Cypher 写在本模块，业务代码（ranker/api）不碰图查询语法，
   换图数据库时只改这里。
3. 诚实推理：图里没有边就回答"未发现禁忌关联"，不编造——
   知识图谱的价值恰恰在于"知道什么"和"不知道什么"一样清楚。

图模型（由 scripts/init_kg.py 构建）：
    (:Ingredient {name})-[:IN_RECIPE {amount}]->(:Recipe {recipe_id, name, ...})
    (:Ingredient)-[:RICH_IN {level: 高}]->(:Nutrient {name})
    (:Ingredient)-[:CONTRAINDICATED_FOR {level, reason}]->(:Condition {name, aka})
    (:Ingredient)-[:BENEFICIAL_FOR {reason}]->(:Condition {name, aka})
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app_my.core.config import settings
from app_my.core.logging import logger

# 禁忌等级 -> 扣分力度（ranker 用；等级语义：避免=能不吃就不吃，限量/适量=控制份量）
LEVEL_WEIGHT = {"避免": 8, "限量": 4, "适量": 2}

# 用户画像的"目标"到图谱"健康状况"的映射：控糖目标的人群按糖尿病饮食原则对待
GOAL_TO_CONDITION = {"控糖": "糖尿病"}

_driver = None            # 驱动单例（惰性创建）
_driver_failed = False    # 曾连接失败就不再反复尝试（避免每次请求都等超时）


def _get_driver():
    """惰性创建 Neo4j 驱动单例。连接失败标记 _driver_failed，后续直接放弃。"""
    global _driver, _driver_failed
    if _driver is not None:
        return _driver
    if _driver_failed:
        return None
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            connection_timeout=5,           # 连不上 5 秒内放弃，不拖慢主流程
            max_connection_pool_size=4,     # 个人项目用不了多少并发连接
        )
        driver.verify_connectivity()        # 立刻验证一次，失败走 except
        _driver = driver
        logger.info(f"kg: 已连接 Neo4j（{settings.NEO4J_URI}）")
        return _driver
    except Exception as exc:
        _driver_failed = True
        logger.warning(f"kg: Neo4j 不可用（{type(exc).__name__}: {exc}），图谱推理降级为跳过")
        return None


def kg_available() -> bool:
    """图谱当前是否可用（ranker/api 层用它决定走图谱还是跳过）"""
    return _get_driver() is not None


def _run(cypher: str, **params) -> List[dict]:
    """
    执行一条只读 Cypher，返回 [{列名: 值}, ...]。

    任何异常（语法/连接/超时）都吞掉返回空列表——
    图谱是增强能力，查询失败不能让推荐/对话挂掉。
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            return [record.data() for record in session.run(cypher, **params)]
    except Exception as exc:
        logger.warning(f"kg: 查询失败（已降级为空结果）: {exc}")
        return []


def reset_kg_connection() -> None:
    """测试用：丢弃驱动单例和失败标记，下一次访问重新连接"""
    global _driver, _driver_failed
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
    _driver = None
    _driver_failed = False


# ============================================================
# 画像 → 状况（ranker 的入口逻辑）
# ============================================================

def derive_conditions(profile: dict) -> List[str]:
    """
    从用户画像推导"健康状况"列表（图谱 Condition 节点名）。

    两个来源：
      1. goal 字段：控糖 → 糖尿病（画像目标暗含饮食禁忌）
      2. health_conditions 字段：用户显式填写的（如 ["痛风", "高血压"]），
         没有就空——阶段 3 先支持画像文件里手工配置，阶段 9 多租户后开放给前端编辑。
    """
    conds: List[str] = []
    goal = profile.get("goal")
    if goal in GOAL_TO_CONDITION:
        conds.append(GOAL_TO_CONDITION[goal])
    for c in profile.get("health_conditions") or []:
        if c and c not in conds:
            conds.append(c)
    return conds


# ============================================================
# 查询 1：状况 → 忌口/推荐映射（ranker 重排用）
# ============================================================

def get_condition_guidance(conditions: List[str]) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """
    拿到一组健康状况的完整饮食指引。

    返回 (avoid_map, prefer_map)：
        avoid_map  = {食材名: {"condition", "level", "reason", "weight"}}
                     同一食材命中多种状况时取扣分最重的（更保守，安全第一）
        prefer_map = {食材名: {"condition", "reason"}}

    数据来自两条 Cypher（一次取全图相关边，比逐食材查快得多）：
        (:Ingredient)-[c:CONTRAINDICATED_FOR]->(:Condition)
        (:Ingredient)-[b:BENEFICIAL_FOR]->(:Condition)
    """
    if not conditions:
        return {}, {}
    rows = _run(
        """
        MATCH (i:Ingredient)-[r:CONTRAINDICATED_FOR]->(cond:Condition)
        WHERE cond.name IN $conditions
        RETURN i.name AS ingredient, cond.name AS condition,
               r.level AS level, r.reason AS reason
        """,
        conditions=conditions,
    )
    avoid_map: Dict[str, dict] = {}
    for row in rows:
        weight = LEVEL_WEIGHT.get(row["level"], 2)
        old = avoid_map.get(row["ingredient"])
        # 保留扣分更重的那条（多状况冲突时按最严格的算）
        if old is None or weight > old["weight"]:
            avoid_map[row["ingredient"]] = {
                "condition": row["condition"],
                "level": row["level"],
                "reason": row["reason"],
                "weight": weight,
            }

    rows = _run(
        """
        MATCH (i:Ingredient)-[b:BENEFICIAL_FOR]->(cond:Condition)
        WHERE cond.name IN $conditions
        RETURN i.name AS ingredient, cond.name AS condition, b.reason AS reason
        """,
        conditions=conditions,
    )
    prefer_map = {row["ingredient"]: row for row in rows}

    if avoid_map or prefer_map:
        logger.info(
            f"kg: 状况 {conditions} → 忌口 {len(avoid_map)} 项 / 推荐 {len(prefer_map)} 项"
        )
    return avoid_map, prefer_map


# ============================================================
# 查询 2：多跳推理问答（/kg/ask 用，验收场景）
# ============================================================

def ask(ingredient: str, condition: str) -> dict:
    """
    图谱依据的推理问答：「{condition}患者能不能吃 {ingredient}」

    三跳证据链，一次查清：
      ① 直连边   Ingredient-[CONTRAINDICATED_FOR/BENEFICIAL_FOR]->Condition
                 → 结论（避免/限量/推荐）+ 理由（边上带着，人写的策展知识）
      ② 营养证据 Ingredient-[RICH_IN]->Nutrient
                 → 这个结论在营养学上的依据（如 土豆-高碳水）
      ③ 影响菜谱 Ingredient-[IN_RECIPE]->Recipe
                 → 含这个食材的菜谱清单（重排节点同样会压制它们）

    图里没有边 ≠ "能吃"，而是"图谱未收录"——回答里明确说，不编造。
    """
    # 图谱不可用时明确告知（区别于"图谱查过了没这条知识"）
    if not kg_available():
        return {
            "ingredient": ingredient,
            "condition": condition,
            "verdict": "图谱不可用",
            "reason": f"Neo4j 未连接（{settings.NEO4J_URI}），无法推理",
            "nutrients": [],
            "affected_recipes": [],
            "graph_available": False,
        }

    # ① 直连禁忌边
    contra = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[r:CONTRAINDICATED_FOR]->(c:Condition)
        WHERE c.name = $condition OR $condition IN c.aka
        RETURN r.level AS level, r.reason AS reason
        """,
        ingredient=ingredient,
        condition=condition,
    )
    # ① 直连推荐边
    benefit = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[b:BENEFICIAL_FOR]->(c:Condition)
        WHERE c.name = $condition OR $condition IN c.aka
        RETURN b.reason AS reason
        """,
        ingredient=ingredient,
        condition=condition,
    )

    # 结论综合（禁忌优先于推荐——安全第一）
    if contra:
        level = contra[0]["level"]
        verdict = "不建议食用" if level == "避免" else "建议控制食用量"
        reason = contra[0]["reason"]
    elif benefit:
        verdict = "推荐食用"
        reason = benefit[0]["reason"]
    else:
        verdict = "未发现禁忌关联"
        reason = "图谱未收录该食材与该状况的关系，请咨询专业营养师"

    # ② 营养证据（无禁忌时也返回，供参考）
    nutrients = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[r:RICH_IN]->(n:Nutrient)
        RETURN n.name AS nutrient, r.level AS level, n.note AS note
        """,
        ingredient=ingredient,
    )

    # ③ 受影响菜谱（两跳：食材-入菜->菜谱）
    recipes = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[:IN_RECIPE]->(rc:Recipe)
        RETURN rc.recipe_id AS recipe_id, rc.name AS name, rc.calories AS calories
        ORDER BY rc.name
        """,
        ingredient=ingredient,
    )

    return {
        "ingredient": ingredient,
        "condition": condition,
        "verdict": verdict,
        "reason": reason,
        "nutrients": nutrients,
        "affected_recipes": recipes,
        "graph_available": True,
    }

# ============================================================
# 查询 3：文本 → 食材命中 → 菜谱（v3阶段6 混合检索的第三路）
# ============================================================

from functools import lru_cache


@lru_cache(maxsize=1)
def _ingredient_names() -> List[str]:
    """全图食材名列表（建一次进程内复用；重建图谱后重启后端生效）"""
    rows = _run("MATCH (i:Ingredient) RETURN i.name AS name")
    return [r["name"] for r in rows]


def reset_ingredient_cache() -> None:
    """重建图谱后调用：清掉食材名缓存，下次查询重新加载"""
    _ingredient_names.cache_clear()


def match_recipes_from_query(query: str, limit: int = 10) -> List[str]:
    """
    混合检索的第三路（图谱信号）：查询文本 → 命中的食材 → 两跳到菜谱。

    与向量/BM25 的本质区别：图谱返回的是"图上有边的事实"——
    查询里有"西兰花"，返回的菜谱一定真含西兰花（IN_RECIPE 边存在），
    不靠相似度猜测，没有幻觉。

    返回按"命中食材数"降序的 recipe_id 列表；图谱不可用/没命中返回空列表
    （上层会把它当成"这一路缺席"，权重自动重分配）。
    """
    names = _ingredient_names()
    if not names:
        return []
    # 子串匹配：查询"香煎鸡胸肉配西兰花"能命中食材"鸡胸肉"（分词不必精确）
    matched = [n for n in names if n and n in query]
    if not matched:
        return []
    rows = _run(
        """
        MATCH (i:Ingredient)-[:IN_RECIPE]->(rc:Recipe)
        WHERE i.name IN $names
        RETURN rc.recipe_id AS rid, count(DISTINCT i) AS hits
        ORDER BY hits DESC
        LIMIT $limit
        """,
        names=matched,
        limit=limit,
    )
    logger.info(f"kg: 查询命中食材 {matched} -> 图谱路返回 {len(rows)} 道菜")
    return [r["rid"] for r in rows]


def kg_stats() -> dict:
    """图谱规模统计（排障/演示用：节点和关系各多少）"""
    nodes = _run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC")
    rels = _run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC")
    return {"nodes": nodes, "relationships": rels, "available": kg_available()}