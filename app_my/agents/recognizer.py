# app_my/agents/recognizer.py
"""
节点① 识别（recognizer）—— 把"用户给了什么食材"变成结构化数据

两个分支（这是修订版方案里缺失的第二个分支）：
    A. 有图：调用多模态模型看图识食材（qwen-omni 一类）
    B. 无图：从用户文字里抽取食材（"我有鸡蛋和西红柿" → [{name: 鸡蛋}, {name: 西红柿}]）
    —— 原方案无图时直接返回空，导致后面所有节点全跳过、用户拿到空回复，
       所以这里必须补上文字抽取分支。

输出契约（后面所有节点都按这个约定消费）：
    state["ingredients"] = [
        {"name": "西兰花", "freshness": 9, "amount": "约300g", "usable": True}, ...
    ]
"""
from __future__ import annotations

import json
import re
from typing import List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# from app_my.core.logging import logger
# from app_my.core.models import get_chat_model, get_vision_model

from app_my.core.logging import logger
from app_my.core.model_router import ainvoke_routed   #  v3阶段2：模型调用改走智能路由

# ============================================================ JSON 解析（容错）
# 优先匹配 ```json ... ``` 代码块；模型偶尔不加代码块，再用"抓第一个大括号"兜底
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_JSON_ANY_RE = re.compile(r"\{.*\}", re.S)


def parse_json_payload(text: str) -> dict:
    """
    从模型回复里抠出 JSON 字典；解析不出来返回 {}（绝不抛异常打断整条工作流）。

    这是"防脆弱"的关键：大模型输出格式天生不稳定，
    解析失败只降级、不崩溃，配合下面的重试，能救回绝大多数情况。
    """
    if not text:
        return {}
    for regex in (_JSON_BLOCK_RE, _JSON_ANY_RE):
        match = regex.search(text)
        if not match:
            continue
        raw = match.group(1) if regex is _JSON_BLOCK_RE else match.group(0)
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    logger.warning("recognizer: 模型输出解析不出 JSON，本次降级为空结果")
    return {}


def message_content_to_text(content) -> str:
    """
    把消息 content 统一成字符串。

    多模态消息的 content 可能是 list： [{"type": "text", "text": "..."}]，
    也可能是普通字符串，这里统一抽取，避免后面到处写 isinstance 判断。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


# ============================================================ 提示词
# 两个分支共用同一份"输出契约"，这样下游节点不需要区分数据是从图来的还是从文字来的
#  排版技巧：提示词示例里需要出现 " ```json ... ``` "，但 Markdown 文档里直接写
#    连续三个反引号会提前关闭外层 python 代码块，导致后面代码崩掉。
#    所以用 chr(96)*3 拼出 ```；实际运行时字符串里仍然是正常的三个反引号。
_BACKTICK3 = chr(96) * 3

_SHARED_SPEC = f"""
输出要求（严格遵守）：
- 只输出一个 {_BACKTICK3}json 代码块，代码块外不要有任何解释文字。
- JSON 结构：
{_BACKTICK3}json
{{
  "ingredients": [
    {{"name": "西兰花", "freshness": 9, "amount": "约300g", "usable": true}}
  ],
  "warnings": ["西红柿表面轻微破损，建议尽快食用"]
}}
{_BACKTICK3}
- name：食材名，尽量用常见叫法（如"西红柿""鸡胸肉""鸡蛋"）。
- freshness：新鲜度，1~10 的整数；文字输入看不出来就给 8。
- amount：能看出来的用量（"约300g""2个"）；看不出来给"适量"。
- usable：还能不能用，true/false。
- warnings：把明显的问题（变质、破损、过期）写进来，没有就给空数组。
"""

IMAGE_SYS = "你是食材识别专家，负责看照片认出所有可见食材，并评估新鲜度与可用量。" + _SHARED_SPEC

TEXT_SYS = (
    "你是食材信息抽取专家。用户会用自然语言描述自己有的食材，"
    "请把它们抽成结构化清单（不要按菜谱反推用户没提到的食材）。" + _SHARED_SPEC
)


# ============================================================ 两个分支的实现
async def _extract_from_image(text: str, image_url: str) -> dict:
    """分支 A：多模态识图。图片读取失败等问题都在这里兜住，返回 {} 让上游降级。"""
    try:
        message = HumanMessage(content=[
            {"type": "text", "text": text or "请识别这张图片里的食材"},
            {"type": "image_url", "image_url": {"url": image_url}},
        ])
        # response = await get_vision_model().ainvoke([SystemMessage(content=IMAGE_SYS), message])
        response = await ainvoke_routed("vision", [SystemMessage(content=IMAGE_SYS), message])
        return parse_json_payload(message_content_to_text(response.content))
    except Exception as e:                        # 网络、模型不支持图片、URL 不可访问……
        logger.error(f"recognizer: 图片识别失败（{type(e).__name__}: {e}）")
        return {}


async def _extract_from_text(text: str) -> dict:
    """
    分支 B：从文字抽取食材。
    第一次解析失败时会自动重试一次——重试时把"只输出 JSON"再强调一遍，
    这是对大模型格式不稳定最省事的兜底手段。
    """
    for attempt in (1, 2):
        try:
            prompt = text if attempt == 1 else f"{text}\n\n（请只输出 JSON 代码块，不要任何解释）"
            # response = await get_chat_model().ainvoke(
            #     [SystemMessage(content=TEXT_SYS), HumanMessage(content=prompt)]
            # )
            response = await ainvoke_routed(
                "extract",
                [SystemMessage(content=TEXT_SYS), HumanMessage(content=prompt)],
                text=text,                       #  v3阶段2：把原文传给路由判复杂度
            )
            data = parse_json_payload(message_content_to_text(response.content))
            if data:
                return data
            logger.warning(f"recognizer: 第 {attempt} 次抽取未得到 JSON，准备重试")
        except Exception as e:
            logger.error(f"recognizer: 文字抽取失败（{type(e).__name__}: {e}）")
            return {}
    return {}


# ============================================================ 节点入口
async def recognize_node(state: dict) -> dict:
    """
    识别节点：读 state.image_url 决定走哪个分支，写回 state.ingredients。

    注意返回值的写法：messages 只放【本次新增】的一条，
    LangGraph 会用 add_messages 规则把它追加到历史消息后面。
    """
    image_url = state.get("image_url") or []
    messages = state.get("messages") or []

    # 取出用户这句话的纯文本（多模态 content 也能转成字符串）
    user_text = message_content_to_text(messages[-1].content) if messages else ""

    if image_url:
        logger.info("recognizer: 有图片，走多模态识别分支")
        data = await _extract_from_image(user_text, image_url[0])
    else:
        logger.info("recognizer: 无图片，走文字抽取分支")
        data = await _extract_from_text(user_text)

    ingredients = data.get("ingredients") or []
    warnings = data.get("warnings") or []

    # 只保留"还能用"的食材做后续营养/推荐（失败的单独提示）
    usable = [i for i in ingredients if i.get("usable", True)]
    summary = (
        f"[识别] 共识别 {len(ingredients)} 种食材，其中可用 {len(usable)} 种。"
        f"警告：{'；'.join(warnings) if warnings else '无'}"
    )
    logger.info(f"recognizer: {summary}")
    return {"ingredients": ingredients, "messages": [AIMessage(content=summary)]}