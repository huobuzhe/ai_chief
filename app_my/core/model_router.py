# app_my/core/model_router.py
"""
阶段 2（v3.0）：多模型智能路由——按"任务类型 + 复杂度"决定用哪个档位的模型

为什么要路由（一句话）：
    qwen3.7-plus 的单价是 qwen3.7-flash 的 10 倍。
    "从一句话里抽食材"这种简单任务 flash 完全够用，杀鸡不用牛刀；
    "把营养+菜谱+画像整合成一份报告"是质量敏感任务，值得花 plus 的钱。
    路由 = 让每一分钱花在刀刃上，并且这个"省了多少"是可以被计费系统量化的。

路由规则（规则引擎，不是再用一个 LLM 去判复杂度——那样判别本身就花钱，得不偿失）：
    任务类型 → 默认档位：
        extract  抽食材（识别节点文字分支）  → lite（简单任务）
        report   生成最终报告（输出节点）    → standard（质量敏感）
        vision   看图识食材                 → 固定视觉模型（档位概念不适用）
    复杂度再修正：
        extract 遇到复杂输入（很长 / 关键词多 / 食材特别多）→ 升 standard，
        长指令的抽取容易漏项，用强模型更稳。
        report 恒 standard：报告直接面向用户，质量优先于成本。

降级链（fallback）：
    standard 调用失败（限流/网络/欠费）→ 自动换 lite 重试一次；
    lite 失败没有更便宜的档可退 → 异常抛给调用方（output 节点还有纯代码兜底报告）。
"""
from __future__ import annotations

import re
from typing import Optional

from langchain_core.callbacks import AsyncCallbackHandler

from app_my.core.config import settings

from app_my.core.logging import logger
from app_my.core.models import get_model_for_tier
from app_my.core.token_billing import BillingCallbackHandler

# ============================================================
# 复杂度判别（纯规则，零成本零延迟）
# ============================================================

# 复杂任务的信号词：出现任何一个，说明用户要的不是"顺手一抽"
_COMPLEX_KEYWORDS = (
    "详细", "分析", "为什么", "怎么搭配", "营养方案", "减脂计划", "增肌计划",
    "控糖", "忌口", "过敏", "热量差", "卡路里", "搭配建议",
)

# 食材罗列的常见分隔符：数一数用户报了多少样东西
_INGREDIENT_SEP_RE = re.compile(r"[、,，;；/和与还有及]")


def classify_complexity(text: str) -> str:
    """
    判别一段用户输入的复杂度，返回 "simple" 或 "complex"。

    三条规则（命中任意一条即 complex）：
      1. 长文本：超过 120 字——信息量大，轻量模型容易漏抽
      2. 信号词：包含"详细/分析/为什么/控糖"等质量敏感词
      3. 食材多：按分隔符粗数 >= 6 样——清单越长越需要稳定的模型
    """
    if not text:
        return "simple"
    if len(text) > 120:
        return "complex"
    if any(kw in text for kw in _COMPLEX_KEYWORDS):
        return "complex"
    if len(_INGREDIENT_SEP_RE.split(text)) >= 6:
        return "complex"
    return "simple"


# ============================================================
# 路由决策
# ============================================================

def route(task: str, text: str = "") -> str:
    """
    任务 + 输入 → 模型档位（lite / standard / vision）。

    返回的是档位名，不是模型名——模型名在 models.py 里由配置决定，
    这样换模型（比如以后 flash 升级）只改 .env，路由规则不用动。
    """
    if task == "vision":
        return "vision"                                   # 识图固定走视觉模型
    if task == "report":
        return "standard"                                 # 报告质量敏感，恒标准档
    if task == "extract":
        return "standard" if classify_complexity(text) == "complex" else "lite"
    # 未知任务类型：给标准档（宁可多花点钱，不要答不出）
    logger.warning("router: 未知任务类型 %s，按 standard 处理", task)
    return "standard"


# ============================================================
# 带计费的统一调用入口（业务节点只跟这个函数打交道）
# ============================================================

async def ainvoke_routed(task: str, messages, text: str = ""):
    """
    路由 + 调用 + 计费 + 降级，一站式完成。

    业务节点（recognizer / output）以后不再直接 get_chat_model().ainvoke(...)，
    而是调本函数——模型选哪档、记账、失败降级，全部在这里收口：
      ① route() 决定档位
      ② 挂 BillingCallbackHandler 调用（结束自动记 token 账）
    
      ③ 非 lite 档失败 → 自动换 lite 重试一次（降级链）
      ④ v3阶段10 新增：MOCK_LLM=true 时走打桩分支，直接返回格式正确的假响应

    参数：
        task     —— 任务名，取值 "extract" / "report" / "vision"。决定用哪档模型。
        messages —— 提示词列表，直接透传给模型的 ainvoke()。
        text     —— 用户原始输入。只在路由判复杂度时用得到（extract 任务），
                    决定"简单问题走 lite、复杂问题走 standard"。
    返回：
        AIMessage —— 模型回复消息；调用方只读 .content。
    """
    # ---------- v3阶段10：压测打桩分支 ----------
    # 放在最前面，且**在任何网络调用之前**返回：
    #   · 压测量的是本项目架构的容量，不是模型厂商的容量（理由见 app_my/core/mock_llm.py）
    #   · 打桩后不挂 BillingCallbackHandler —— 没有真 token，自然不该记账，
    #     否则 mock 压测会把假用量写进账单表，把阶段 2 的计费数据污染掉
    #   · 这里 import 而不是模块顶层 import：生产环境不 import 测试替身
    if settings.MOCK_LLM:
        from app_my.core.mock_llm import ainvoke_mock
        response = await ainvoke_mock(task, messages)
        logger.info("router: MOCK_LLM 命中，task=%s 直接返回固定响应", task)
        return response

    tier = route(task, text)

    model = get_model_for_tier(tier)

    # 计费回调：每次调用结束 on_llm_end 自动抽 usage 记账
    callbacks = [BillingCallbackHandler()]

    try:
        response = await model.ainvoke(messages, config={"callbacks": callbacks})
        logger.info("router: task=%s tier=%s -> %s", task, tier, getattr(model, "model_name", tier))
        return response
    except Exception as exc:
        # lite 没得降，vision 换 lite 也看不了图——直接抛给调用方走它自己的兜底
        if tier in ("lite", "vision"):
            raise
        logger.warning(
            "router: %s 档调用失败（%s: %s），自动降级 lite 重试",
            tier, type(exc).__name__, exc,
        )
        lite = get_model_for_tier("lite")
        return await lite.ainvoke(messages, config={"callbacks": callbacks})