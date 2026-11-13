# app_my/agents/ranker.py
"""
节点④ 重排（ranker）—— 用"用户画像"给候选菜谱二次排序

这是"个性化"真正落地的地方：
    RAG 只保证"和食材相关"，重排负责"和这个人合适"。
    打分维度（每个维度都是一个小加分/减分，规则透明、可解释）：
        ① 目标匹配    减脂→低脂/减脂标签；增肌→高蛋白；控糖→低糖
        ② 过敏食材    命中 → 直接剔除（不是扣分，是不给）
        ③ 忌口食材    命中 → 重扣
        ④ 不爱吃      命中 → 轻扣
        ⑤ 省事优先    难度越低越加分（简单 1 / 中等 2 / 困难 3）
        ⑥ 时间成本    30 分钟以上略扣分
        ⑦ 偏好标签    命中偏好标签加分
        ⑧ 图谱禁忌    v3阶段3 新增：知识图谱按"健康状况"压制/加分
                     （控糖用户 → 图谱查出土豆"限量"、西兰花"推荐"，扣分带图谱理由）

修订版对照（两处实测必须改的地方）：
    - 我们的 recipes.json 里 difficulty 是中文（"简单/中等/困难"），
      原方案直接拿它当数字参与运算，排序结果会是错的；
      这里统一用 difficulty_level（1/2/3，在工具层已经转换好）。
    - 原方案没有"过敏"概念，只有 forbidden；过敏属于硬约束，必须剔除。
"""
from __future__ import annotations
import re
from typing import List, Tuple

from langchain_core.messages import AIMessage
from app_my.core import kg as kg_module   #  v3阶段3：知识图谱推理（不可用时自动跳过）
from app_my.core.logging import logger

# 与图谱一致的食材名切分规则（"鸡蛋 3个" -> "鸡蛋"，两边规则必须相同才能对上名字）
_ING_RE = re.compile(r"\s+")

def _ingredient_names(recipe: dict) -> List[str]:
    """菜谱的食材名列表（去掉用量部分）"""
    return [_ING_RE.split(x.strip())[0] for x in recipe.get("ingredients") or [] if x.strip()]


def _score_recipe(
    recipe: dict,
    profile: dict,
    kg_avoid: Dict[str, dict] | None = None,     # 🔵 v3阶段3：图谱忌口映射
    kg_prefer: Dict[str, dict] | None = None,     # 🔵 v3阶段3：图谱推荐映射
) -> Tuple[float, List[str]]:
    """
    给一条菜谱打分，返回 (分数, 理由列表)。

    分数越高越推荐；理由列表会被输出节点用来说"为什么推荐它"，让推荐可解释。
    """
    score = 0.0
    reasons: List[str] = []

    goal = profile.get("goal", "普通")
    tags = set(recipe.get("tags") or [])
    ing_text = " ".join(recipe.get("ingredients") or [])

    # ① 目标匹配
    if goal == "减脂" and ({"减脂", "低脂", "低卡"} & tags):
        score += 5
        reasons.append("符合减脂目标")
    if goal == "增肌" and ({"高蛋白", "增肌"} & tags):
        score += 5
        reasons.append("符合增肌目标")
    if goal == "控糖" and ({"低糖", "控糖", "清淡"} & tags):
        score += 5
        reasons.append("符合控糖目标")

    # ② 忌口：命中直接重扣（过敏在 recommend 之后统一剔除，见 rank_recipes）
    for bad in profile.get("forbidden") or []:
        if bad and (bad in ing_text or bad in recipe.get("name", "")):
            score -= 10
            reasons.append(f"含忌口食材 {bad}")

    # ③ 不爱吃：轻扣
    for dislike in profile.get("dislikes") or []:
        if dislike and (dislike in ing_text or dislike in recipe.get("name", "")):
            score -= 3
            reasons.append(f"含不爱吃的 {dislike}")

    # ④ 偏好标签
    for tag in profile.get("prefer_tags") or []:
        if tag and tag in tags:
            score += 2
            reasons.append(f"符合偏好 {tag}")

    # ⑤ 省事优先：难度越低加分越多（简单 +1.0 / 中等 +0.5 / 困难 +0）
    level = recipe.get("difficulty_level", 2)
    score += (3 - level) * 0.5
    if level == 1:
        reasons.append("做法简单")

    # ⑥ 时间成本：超过 30 分钟略扣分（上班族晚饭场景）
    minutes = recipe.get("time_minutes", 0) or 0
    if minutes and minutes > 30:
        score -= 1
        reasons.append(f"耗时较长（{minutes}分钟）")

    # ⑦ 热量维度：减脂目标下，热量低的再加一点
    calories = recipe.get("calories", 0) or 0
    if goal == "减脂" and calories and calories < 250:
        score += 2
        reasons.append(f"热量较低（{calories}千卡）")
    if goal == "增肌" and (recipe.get("protein", 0) or 0) >= 20:
        score += 2
        reasons.append(f"蛋白充足（{recipe.get('protein')}g）")



        # ⑧ 图谱推理（v3阶段3）：按健康状况压制/加分，理由带图谱依据
    if kg_avoid or kg_prefer:
        names = set(_ingredient_names(recipe))
        # 禁忌：一条菜谱只按最重的一条扣（避免土豆+米饭双重扣把分数打到负无穷）
        worst = None
        for name in names:
            hit = (kg_avoid or {}).get(name)
            if hit and (worst is None or hit["weight"] > worst["weight"]):
                worst = {**hit, "ingredient": name}
        if worst:
            score -= worst["weight"]
            reasons.append(
                f"图谱提示：{worst['ingredient']}对{worst['condition']}患者{worst['level']}——{worst['reason']}"
            )
        # 推荐：命中一种就加分（说明这道菜对该状况友好）
        for name in names:
            hit = (kg_prefer or {}).get(name)
            if hit:
                score += 2
                reasons.append(f"图谱推荐：{name}适合{hit['condition']}人群——{hit['reason']}")
                break

    return round(score, 2), reasons


def rank_recipes(recipes: List[dict], profile: dict) -> List[dict]:
    """
    批量重排（纯函数，方便单测）。

    顺序：先剔过敏 → 查图谱指引（一次查全，不逐菜谱查） → 再打分 → 按分数倒序。
    """
    allergies = [a for a in (profile.get("allergies") or []) if a]

    # 🔵 v3阶段3：从画像推导健康状况，一次性查出忌口/推荐映射
    # （图谱不可用时返回两个空字典，下面的打分维度⑧自动跳过——主流程不受影响）
    conditions = kg_module.derive_conditions(profile)
    kg_avoid, kg_prefer = ({}, {})
    if conditions:
        kg_avoid, kg_prefer = kg_module.get_condition_guidance(conditions)
        if kg_avoid or kg_prefer:
            logger.info(f"ranker: 图谱指引已加载（状况={conditions}，忌口 {len(kg_avoid)} 项）")

    kept: List[dict] = []
    for r in recipes:
        ing_text = " ".join(r.get("ingredients") or [])
        if any(a in ing_text or a in r.get("name", "") for a in allergies):
            logger.info(f"ranker: 剔除含过敏食材的菜谱「{r.get('name')}」")
            continue
        score, reasons = _score_recipe(r, profile, kg_avoid, kg_prefer)
        kept.append({**r, "rank_score": score, "rank_reasons": reasons})

    return sorted(kept, key=lambda x: -x.get("rank_score", 0))


async def rank_node(state: dict) -> dict:
    """重排节点：recipes + user_profile → ranked_recipes"""
    recipes = state.get("recipes") or []
    profile = state.get("user_profile") or {}

    if not recipes:
        logger.info("ranker: 没有候选菜谱，跳过重排")
        return {"ranked_recipes": [], "messages": [AIMessage(content="[重排] 无候选菜谱，跳过")]}

    ranked = rank_recipes(recipes, profile)
    top = ranked[0] if ranked else None
    summary = (
        f"[重排] 目标={profile.get('goal', '普通')}，"
        f"忌口={profile.get('forbidden') or '无'}，过敏={profile.get('allergies') or '无'}，"
        f"共排序 {len(ranked)} 条"
        + (f"，首选「{top['name']}」得分 {top['rank_score']}" if top else "")
    )
    logger.info(f"ranker: {summary}")
    return {"ranked_recipes": ranked, "messages": [AIMessage(content=summary)]}