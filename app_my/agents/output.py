# app_my/agents/output.py
"""
节点⑤ 输出整合（output）—— H1 修复：让用户真正收到一份可读回复

为什么必须补这个节点：
    原方案图里最后一步是 rank → END，工作流算完了却没有任何节点把
    "食材 + 营养 + 排序后的菜谱"整合成人话，接口层拿不到内容 → 用户收到空回复。
    本节点做两件事：
        ① 把这些结构化结论交给大模型，写成一份友好的 Markdown 报告；
        ② 如果模型调用失败/超时，就用代码拼一份"兜底报告"——
           宁可格式朴素，也绝不给用户空回复（这是可用性底线）。
"""
from __future__ import annotations

from typing import List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# from app_my.core.logging import logger
# from app_my.core.models import get_chat_model

from app_my.core.logging import logger
from app_my.core.model_router import ainvoke_routed   #  v3阶段2：报告生成改走智能路由（standard 档）

OUTPUT_SYS = """你是 AI 私厨的输出整合助手。你会收到系统各环节的分析结果，
请把它们整理成一份结构清晰、语气亲切的 Markdown 报告，包含：

## 食材清单
列出识别到的食材（含新鲜度提示、不可用的单独提醒）

## 营养概览
用一两句话概括估算热量与三大营养素（注明是估算值）

## 推荐菜谱
最多 3 道，每道给出：菜名、为什么推荐（结合用户目标/忌口）、主要食材、简要步骤、热量

## 小贴士
结合用户的目标（减脂/增肌/控糖）给 1~2 条实用建议

要求：
- 只写用户关心的内容，不要复述系统内部流程（不要出现"识别节点""RAG"等字眼）
- 不要编造没有提供的数据；数据缺失就如实说"暂缺"
- 全文用中文，Markdown 标题层级从 ## 开始
"""


def _fmt_ingredients(ingredients: List[dict]) -> str:
    """把食材列表拼成一行行文本，供提示词或兜底报告使用"""
    if not ingredients:
        return "（未识别到食材）"
    lines = []
    for i in ingredients:
        flag = "" if i.get("usable", True) else "（已不可用）"
        lines.append(f"- {i.get('name', '?')} {i.get('amount', '')} 新鲜度 {i.get('freshness', '-')}/10{flag}")
    return "\n".join(lines)


def _fmt_recipes(ranked: List[dict]) -> str:
    """把排序后的菜谱拼成文本（最多 3 道）"""
    if not ranked:
        return "（暂无候选菜谱）"
    blocks = []
    for idx, r in enumerate(ranked[:3], start=1):
        reason = "；".join(r.get("rank_reasons") or []) or "与食材匹配"
        steps = " → ".join(r.get("steps") or []) or "（暂无步骤）"
        blocks.append(
            f"{idx}. **{r.get('name')}**（{r.get('cuisine', '')}，{r.get('time_minutes', '-')}分钟，"
            f"约 {r.get('calories', '-')} 千卡）\n"
            f"   - 推荐理由：{reason}\n"
            f"   - 主要食材：{'、'.join(r.get('ingredients') or []) or '（暂缺）'}\n"
            f"   - 做法：{steps}"
        )
    return "\n".join(blocks)


def build_fallback_markdown(ingredients: List[dict], nutrition: dict, ranked: List[dict], profile: dict) -> str:
    """
    兜底报告：不调用大模型，纯代码拼装。
    用于模型不可用（欠费、超时、网络故障）时，保证用户至少拿到结论。
    """
    est = (nutrition or {}).get("total_estimated", {})
    nutrition_line = (
        f"估算总热量 {est.get('calories')} 千卡，"
        f"蛋白 {est.get('protein')}g / 脂肪 {est.get('fat')}g / 碳水 {est.get('carbs')}g（估算值）"
        if est else "暂缺（食材未匹配到营养库）"
    )
    return (
        f"## 食材清单\n{_fmt_ingredients(ingredients)}\n\n"
        f"## 营养概览\n{nutrition_line}\n\n"
        f"## 推荐菜谱\n{_fmt_recipes(ranked)}\n\n"
        f"## 小贴士\n- 当前饮食目标：{profile.get('goal', '普通')}；"
        f"忌口：{'、'.join(profile.get('forbidden') or []) or '无'}。\n"
        f"- 回复由本地规则生成（模型暂不可用），建议稍后重试以获得更详细的建议。"
    )


async def output_node(state: dict) -> dict:
    """
    输出节点：
      1) 把 state 里的结构化结论写成提示词
      2) 调模型生成 Markdown（失败则用兜底报告）
      3) 写入 state.final_answer，并作为最后一条消息进入消息流
    """
    ingredients = state.get("ingredients") or []
    nutrition = state.get("nutrition") or {}
    ranked = state.get("ranked_recipes") or []
    profile = state.get("user_profile") or {}
    messages = state.get("messages") or []
    user_text = messages[0].content if messages else ""
    if isinstance(user_text, list):        # 多模态输入时取其中的文本部分
        user_text = " ".join(b.get("text", "") for b in user_text if isinstance(b, dict))

    prompt = f"""用户原话：{user_text}

识别到的食材：
{_fmt_ingredients(ingredients)}

营养分析结果（JSON）：
{nutrition}

候选菜谱（已按用户画像排序，含推荐理由）：
{_fmt_recipes(ranked)}

用户画像：{profile}
"""
    try:
        #response = await get_chat_model().ainvoke([SystemMessage(content=OUTPUT_SYS), HumanMessage(content=prompt)])
        response = await ainvoke_routed("report", [SystemMessage(content=OUTPUT_SYS), HumanMessage(content=prompt)], text=user_text)
        final = response.content if isinstance(response.content, str) else str(response.content)
        if not final.strip():                       # 模型返回空内容也走兜底
            raise ValueError("模型返回空内容")
        logger.info(f"output: 模型生成最终报告 {len(final)} 字")
    except Exception as e:
        logger.error(f"output: 生成失败，改用兜底报告（{type(e).__name__}: {e}）")
        final = build_fallback_markdown(ingredients, nutrition, ranked, profile)

    return {"final_answer": final, "messages": [AIMessage(content=final)]}