# app_my/core/mock_llm.py
"""
阶段 10：压测用的 LLM 打桩器（Mock LLM）。

为什么需要它（压测最容易踩的坑）：
    压测想测的是"**我的架构**能扛多少并发"，不是"DashScope 那台服务器能扛多少"。
    但只要请求里带着真 LLM 调用，实测出来的 P99 里就混进了两样不属于你的东西：
        ① 网络往返 + 厂商排队（几十到几百毫秒，且随厂商负载剧烈波动）
        ② 厂商的限流 429 —— 你的服务其实好好的，却被算成"错误率上涨"
    同一套代码连跑两次，数字能差一倍。面试官问"这个 QPS 是谁的 QPS"就答不上来。

    打开 MOCK_LLM=true 后，LLM 那一环被换成一个"固定耗时、固定内容"的假模型，
    请求时延里剩下的只有你自己的代码、数据库、缓存、图谱、网络——这才是该测的东西。

打桩点选在哪（关键设计）：
    打在 `model_router.ainvoke_routed()`——它是全项目**唯一**还在调 LLM 的地方。
    （旧的 `get_chat_model().ainvoke(...)` 调用在 recognizer.py / output.py 里
      早已被注释掉并改走 ainvoke_routed，grep 全项目只剩这一处真调用。）
    所以在这里加一个早返回分支，全链路自动生效，**一行业务代码都不用改**，
    关掉开关立刻恢复真实调用。

    为什么不是打在 models.py 的档位工厂上：
        因为档位（lite/standard）不等于任务（extract/report/vision）。
        同一个 lite 档，"抽食材"要返回 JSON、"生成报告"要返回自然语言——
        从 tier 推不出该给什么格式。ainvoke_routed 才知道 task。
"""
from __future__ import annotations

import asyncio
from typing import Iterator, List

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage

# ------------------------------------------------------------------
# 按任务类型准备的假响应（内容必须符合下游消费者的格式要求）
# ------------------------------------------------------------------
# ① 识别节点（recognizer，task=extract / vision）：要求能从回复里正则抠出一个 JSON 字典。
#    否则 parse_json_payload() 返回 {}，食材清单为空 → 后面推荐/营养节点全部空转，
#    那样测出来的 QPS 是"什么都没干"的 QPS，没有意义。
_MOCK_INGREDIENT_JSON = (
    '```json\n'
    '{"ingredients": ['
    '{"name": "西兰花", "freshness": 9, "amount": "约300g", "usable": true},'
    '{"name": "鸡胸肉", "freshness": 8, "amount": "约200g", "usable": true},'
    '{"name": "鸡蛋", "freshness": 9, "amount": "2个", "usable": true}'
    '], "warnings": []}\n'
    '```'
)

# ② 输出节点（output，task=report）：只要求"有非空文本"，空内容会被它判失败并走兜底报告。
_MOCK_REPORT_TEXT = (
    "【压测模式固定回复】根据您提供的食材，建议采用「白灼西兰花 + 香煎鸡胸肉 + 番茄炒蛋」"
    "三菜一汤的搭配：西兰花提供膳食纤维，鸡胸肉补充优质蛋白，鸡蛋补充卵磷脂。"
    "总热量约 620 kcal，蛋白质 48g，脂肪 22g，碳水 55g，适合控糖人群。"
    "（本段为 MOCK_LLM 模式的固定压测响应，不代表真实模型输出。）"
)

# 假模型引入的额外时延（秒）。为什么需要它，见下方"为什么不是 0"的说明。
MOCK_LATENCY_SEC = 0.05

# task -> 固定响应内容。键名必须和 model_router.route() 认识的任务名完全一致。
_MOCK_TEXT_BY_TASK = {
    "extract": _MOCK_INGREDIENT_JSON,   # 识别节点文字分支
    "vision": _MOCK_INGREDIENT_JSON,   # 识别节点图片分支（mock 时不真的看图）
    "report": _MOCK_REPORT_TEXT,        # 输出节点
}


def _cycling(messages: List[BaseMessage]) -> Iterator[AIMessage]:
    """
    把一份固定响应"无限循环"成迭代器。

    为什么必须循环而不是单个返回值：
        GenericFakeChatModel 的 `messages` 参数要求是一个**迭代器**，
        它每次被调用就 next() 取一条。压测会打几百上千次请求，
        只给一条的话第二次调用就抛 StopIteration → 被当成 LLM 失败 →
        output 节点降级走兜底、recognizer 重试一次，P99 全被重试逻辑污染，
        数据就不可信了。
    """
    while True:
        for m in messages:
            yield m


def mock_model(text: str = _MOCK_REPORT_TEXT) -> GenericFakeChatModel:
    """
    造一个"秒回固定文本"的假对话模型（LangChain 官方提供的测试替身）。

    参数：
        text —— 假模型每次返回的内容，默认是报告文本。
    返回：
        GenericFakeChatModel —— BaseChatModel 的子类，
        invoke / ainvoke / stream / astream 四种调用方式都支持，
        所以同步调用和流式调用都能用（项目里 /chat/stream 是流式）。
    """
    return GenericFakeChatModel(messages=_cycling([AIMessage(content=text)]))


async def ainvoke_mock(task: str, messages) -> AIMessage:
    """
    按任务类型返回一份格式正确的假响应。

    参数：
        task     —— 任务名，取值 "extract" / "vision" / "report"。
                    必须原样传 ainvoke_routed 收到的 task，不能自己判断。
        messages —— 原始提示词列表。这里**故意不读它**：
                    mock 的意义是"不管你问了什么，都给一个格式正确的固定答案"，
                    真去读 prompt 反而会让 mock 行为不可预测。
    返回：
        AIMessage —— 与真实模型返回同类型，调用方 .content 取值方式不变，
                     所以 recognizer / output 两个节点一行都不用改。
    """
    if MOCK_LATENCY_SEC:
        await asyncio.sleep(MOCK_LATENCY_SEC)   # 模拟真实模型的最小耗时，见函数末尾说明
    return AIMessage(content=_MOCK_TEXT_BY_TASK.get(task, _MOCK_REPORT_TEXT))


# ------------------------------------------------------------------
# 为什么假模型还要"故意慢 50ms"，而不是让它 0 耗时？
#
#   如果 MOCK_LATENCY_SEC = 0，压测会量出一个漂亮得不真实的 QPS：
#   瓶颈完全落在数据库 / 图谱 / HTTP 框架上，而 LLM 那一环"白送"。
#   真实业务里 LLM 是每请求必经的一环，压测报告里必须给这一环留个位置，
#   否则上线后第一波流量就被 LLM 的真实耗时打脸。
#   50ms 是"快模型返回一段固定文本"的量级（阶段 2 实测 qwen3.7-flash 关思考模式
#   实测 2 秒内出报告，这里取 50ms 是有意压低，好让架构自身的开销占主导）。
# ------------------------------------------------------------------