# app_my/agents/nutritionist.py
"""
节点② 营养（nutritionist）—— 算这套食材的热量和营养素

设计要点：
    1. 真正的计算交给工具 calculate_nutrition（查表 + 四则运算，稳定可复现），
       节点只负责"取数据 → 调工具 → 把结论写回 state"。
    2. 把每个食材的用量一起传给工具（"西兰花 约300g"），
       这样工具才能算出"这一餐大概多少热量"，而不是只能算每 100 克。
    3. 结论同时写进两处：
       - state["nutrition"]      给下一个节点（重排、输出）读的原始数据
       - 一条 AIMessage          进入消息流，便于 LangSmith 里复盘、也便于调试
"""
from __future__ import annotations

from langchain_core.messages import AIMessage

from app_my.core.logging import logger
from app_my.tools.nutrition_tool import calculate_nutrition


async def nutrition_node(state: dict) -> dict:
    """营养节点：ingredients → nutrition"""
    ingredients = state.get("ingredients") or []

    # 没有食材就跳过（比如识别失败），但要留一条消息说明"为什么没有营养数据"
    if not ingredients:
        logger.info("nutritionist: 没有食材，跳过营养分析")
        return {"nutrition": {}, "messages": [AIMessage(content="[营养] 无可用食材，跳过营养分析")]}

    # 只算"还能用"的食材；把用量拼在名字后面，工具才能解析出克数
    usable = [i for i in ingredients if i.get("usable", True)]
    entries = []
    for item in usable:
        name = item.get("name", "")
        amount = item.get("amount", "") or ""
        entries.append(f"{name} {amount}".strip())

    if not entries:
        return {"nutrition": {}, "messages": [AIMessage(content="[营养] 食材均不可用，跳过营养分析")]}

    try:
        # .invoke 传字典即可：键名和工具的 args_schema 字段名一致
        result = calculate_nutrition.invoke({"ingredients": entries})
    except Exception as e:
        # 工具层出错（数据文件丢失等）不能让整条工作流挂掉：降级为空结果 + 记日志
        logger.error(f"nutritionist: 营养计算失败（{type(e).__name__}: {e}）")
        return {"nutrition": {}, "messages": [AIMessage(content="[营养] 计算失败，已跳过")]}

    est = result.get("total_estimated", {})
    summary = (
        f"[营养] 估算本餐总热量 {est.get('calories', 0)} 千卡；"
        f"蛋白 {est.get('protein', 0)}g / 脂肪 {est.get('fat', 0)}g / 碳水 {est.get('carbs', 0)}g。"
        f"匹配率 {result.get('coverage', 0):.0%}"
        + (f"；未匹配：{'、'.join(result['unmatched'])}" if result.get("unmatched") else "")
    )
    logger.info(f"nutritionist: {summary}")
    return {"nutrition": result, "messages": [AIMessage(content=summary)]}