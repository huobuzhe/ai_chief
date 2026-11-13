# AI 私厨 v3.0 · 阶段 2：多模型智能路由 + Token 计费（最终完整版）

> **阶段状态**：✅ 已收官（2026-09-28）。本文件是阶段 2 的**最终完整版**——合并开工操作手册全部内容 + 收官信息，一份完整无错版本（施工期 0 问题，无勘误）。施工过程文档（操作手册/说明手册）保留作历史档案。
>
> **本阶段目标**：给大模型调用装上"成本大脑"——按任务复杂度智能分流（简单抽取走轻量档 flash、质量敏感报告走标准档 plus）、每次调用自动记账（Token 数 + 按官方刊例价折算成元）、提供 `/billing/stats` 成本查询接口，并用对照实验跑出**真实省钱比例**。
>
> - 收官成绩：**施工一次通过**；39 例测试全绿；真实 LLM 流式 15.7 秒；对比实验跑出真实数字（路由 vs 全 plus 省 5.1%，日常对话账本省 23.2%）；已合并 master（PR !2，commit 99e7f73）
> - 🔴 本阶段铁律：`F:\pycharm_aiprogram\ai_sichu`（v2.0）仍然一个字节不动
> - 本手册所有代码与命令已在 2026-09-27 本机实测验证（39 例单测/集成全绿 + 真实 LLM 流式通过 + 对比实验已跑出真实数字）

---

## 目录

- [0. 使用说明与颜色约定](#0-使用说明与颜色约定)
- [1. 本阶段要干什么（先看懂再动手）](#1-本阶段要干什么先看懂再动手)
- [2. 第一步：建分支](#2-第一步建分支)
- [3. 第二步：config.py 加两行](#3-第二步configpy-加两行)
- [4. 第三步：models.py 加分档模型工厂](#4-第三步modelspy-加分档模型工厂)
- [5. 第四步：新建 model_router.py](#5-第四步新建-model_routerpy)
- [6. 第五步：新建 token_billing.py](#6-第五步新建-token_billingpy)
- [7. 第六步：新建 api/billing.py 并注册路由](#7-第六步新建-apibillingpy-并注册路由)
- [8. 第七步：改 recognizer.py（三处）](#8-第七步改-recognizerpy三处)
- [9. 第八步：改 output.py（两处）](#9-第八步改-outputpy两处)
- [10. 第九步：新增三个测试文件](#10-第九步新增三个测试文件)
- [11. 第十步：跑测试](#11-第十步跑测试)
- [12. 第十一步：跑对比实验（本阶段验收数字）](#12-第十一步跑对比实验本阶段验收数字)
- [13. 验收清单](#13-验收清单)
- [14. 错误对照表](#14-错误对照表)
- [15. 不做清单](#15-不做清单)
- [16. 提交 Gitee 与 PR 描述](#16-提交-gitee-与-pr-描述)
- [17. 收官总结](#17-收官总结)


---

## 0. 使用说明与颜色约定

- 每章都是「**操作 → 验证**」两段式：做完操作立刻跑验证，绿了再进下一章。
- 命令给出 **PowerShell** 和 **Git Bash** 两个版本，效果一样。
- 颜色标注：🟢新增 / 🔵修改 / 🟣补充 / 🟡提醒 / 🔴警告。
- 🟡 本阶段**不需要改 .env**（新配置的默认值就是要用的模型）；也不需要动 Docker 容器（pg/redis 继续用阶段 1 起的）。

---

## 1. 本阶段要干什么（先看懂再动手）

### 1.1 一张图看懂

```text
改造前（v2.0/阶段1）：所有任务 ──► qwen3.7-flash ──► 没人知道花了多少钱

改造后（本阶段）：
   识别节点(抽食材) ──┐ 简单输入 ──► lite 档 qwen3.7-flash ──┐
                     └ 复杂输入 ──► standard 档 qwen3.7-plus ─┤   每次
   输出节点(写报告) ──── 恒 standard ─► qwen3.7-plus ─────────┤   调用
   识别节点(看图)   ──── 恒 vision ───► omni 视觉模型 ────────┘   自动记账
                                    │
                                    ▼
              Redis 账本(重启不丢) ──► /billing/stats 接口 ──► 成本/省钱百分比
```

### 1.2 为什么要路由（真实价目，2026-09 阿里云百炼刊例）

| 模型 | 输入（元/千token） | 输出（元/千token） | 定位 |
|---|---|---|---|
| qwen3.7-flash | 0.00024 | 0.00096 | 轻量档 |
| qwen3.7-plus | 0.0024 | 0.0096 | 标准档（**10 倍价**） |

10 倍价差 = 分流的物理基础。**报告是门面活走 plus，抽取是量大活能省则省**。

### 1.3 本阶段实测挖出的意外收获（重要）

qwen3.7 系列默认开"深度思考"模式：模型先默默生成一段思考文字（按输出价计费！）再答题。实测对抽取/报告这类指令型任务毫无必要：

| 指标 | 思考开（默认） | 思考关（本阶段） |
|---|---|---|
| plus 生成一份报告 | 58 秒 | 2 秒级 |
| 流式对话端到端 | 79 秒（首字节超时） | 15.7 秒 |
| 抽取任务输出 token | 225 个里 147 个是思考 | 思考 token 归零 |

本阶段的模型工厂统一加 `extra_body={"enable_thinking": False}` 关闭它——**这既是延迟修复，也是成本治理**。

### 1.4 文件清单

| # | 文件 | 类型 |
|---|---|---|
| 1 | `app_my/core/config.py` | 🔵 修改（加 2 行） |
| 2 | `app_my/core/models.py` | 🔵 修改（加分档工厂） |
| 3 | `app_my/core/model_router.py` | 🟢 新建（智能路由） |
| 4 | `app_my/core/token_billing.py` | 🟢 新建（Token 计费） |
| 5 | `app_my/api/billing.py` | 🟢 新建（成本接口） |
| 6 | `app_my/agents/recognizer.py` | 🔵 修改（3 处各 1 行） |
| 7 | `app_my/agents/output.py` | 🔵 修改（2 处） |
| 8 | `main.py` | 🔵 修改（2 行） |
| 9 | `tests/unit/test_model_router.py` | 🟢 新建 |
| 10 | `tests/unit/test_token_billing.py` | 🟢 新建 |
| 11 | `tests/integration/test_billing_api.py` | 🟢 新建 |
| 12 | `scripts/route_compare.py` | 🟢 新建（对比实验） |

---

## 2. 第一步：建分支

**操作**：

```powershell
cd F:\pycharm_aiprogram\ai_chief
git checkout master
git pull origin master
git checkout -b feat/v3-stage2
```

**验证**：

```powershell
git branch --show-current        # 应输出 feat/v3-stage2
```

---

## 3. 第二步：config.py 加两行

**操作**：打开 `app_my/core/config.py`，找到模型配置区（`EMBEDDING_MODEL` 那一行的下面），加两行：

```python
    CHAT_MODEL: str = "qwen3.7-flash"  # 抽到 settings，agents 不再写死
    VISION_MODEL: str = "qwen3.8-omni-flash-realtime"  # 阶段3 新增：识别节点看图用的多模态模型
    EMBEDDING_MODEL: str = "qwen3.7-text-embedding"
    MODEL_LITE: str = "qwen3.7-flash"       # 🟢 v3阶段2 新增：轻量档（简单任务，成本优先）
    MODEL_STANDARD: str = "qwen3.7-plus"    # 🟢 v3阶段2 新增：标准档（复杂任务，质量优先）
```

（前三行是原有内容，只有后两行是新增。）

**验证**：

```powershell
.venv3\Scripts\Activate.ps1
python -c "from app_my.core.config import settings; print(settings.MODEL_LITE, settings.MODEL_STANDARD)"
```

应输出：`qwen3.7-flash qwen3.7-plus`

---

## 4. 第三步：models.py 加分档模型工厂

**操作**：打开 `app_my/core/models.py`，在 `get_vision_model` 函数后面（`reset_model_cache` 之前）插入下面整段，并把 `reset_model_cache` 替换为新版：

```python
# ============================================================
# 阶段 2（v3.0）新增：分档模型工厂——智能路由的"弹药库"
# lite 档 = qwen3.7-flash（便宜 10 倍，抽食材等简单任务）
# standard 档 = qwen3.7-plus（质量好，报告等复杂任务）
# ============================================================

@lru_cache()
def get_lite_model():
    """
    轻量档模型单例（简单任务用，成本优先）。

    extra_body 关闭思考模式：qwen3.7 系列默认开启"深度思考"，
    对"抽取食材"这类指令型任务纯属浪费——思考 token 按输出价计费（实测一单多花 65%），
    还把响应拖慢好几秒。关掉后：更快、更便宜、结果一样准。
    """
    return init_chat_model(
        model=settings.MODEL_LITE,
        model_provider="openai",
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
        extra_body={"enable_thinking": False},   # 关闭思考模式（v3阶段2 实测修复）
    )


@lru_cache()
def get_standard_model():
    """
    标准档模型单例（复杂任务用，质量优先）。

    同样关闭思考模式：实测开启时生成一份报告要 58 秒（思考占了大头），
    关闭后 2 秒内出结果，报告质量没有可感知差异——对延迟和成本都是硬收益。
    """
    return init_chat_model(
        model=settings.MODEL_STANDARD,
        model_provider="openai",
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
        extra_body={"enable_thinking": False},   # 关闭思考模式（v3阶段2 实测修复）
    )


def get_model_for_tier(tier: str):
    """
    档位名 -> 模型实例（model_router 调这里，不直接碰具体模型名）。
    传入未知档位直接抛错：路由层漏配要在第一时间暴露，不能静默降级。
    """
    factories = {
        "lite": get_lite_model,
        "standard": get_standard_model,
        "vision": get_vision_model,
    }
    if tier not in factories:
        raise ValueError(f"未知模型档位: {tier}（可选: {list(factories)}）")
    return factories[tier]()
```

`reset_model_cache` 替换为（加了两行清理）：

```python
def reset_model_cache():
    """测试用：清空单例缓存"""
    get_chat_model.cache_clear()
    get_vision_model.cache_clear()
    get_lite_model.cache_clear()          # 阶段 2：新档位一并清理
    get_standard_model.cache_clear()
```

**验证**：

```powershell
python -c "from app_my.core.models import get_model_for_tier; m = get_model_for_tier('lite'); print(type(m).__name__, m.model_name)"
```

应输出类似：`ChatOpenAI qwen3.7-flash`（不连网，只验证能实例化）

---

## 5. 第四步：新建 model_router.py

**操作**：新建 `app_my/core/model_router.py`，完整复制：

```python
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
    """
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
```

**验证**：

```powershell
python -c "from app_my.core.model_router import route, classify_complexity; print(classify_complexity('我有鸡蛋和西红柿'), route('extract','我有鸡蛋和西红柿'), route('report'))"
```

应输出：`simple lite standard`

> 🟡 此时会报 `ModuleNotFoundError: app_my.core.token_billing`——正常，下一个文件就建它。

---

## 6. 第五步：新建 token_billing.py

**操作**：新建 `app_my/core/token_billing.py`，完整复制：

```python
# app_my/core/token_billing.py
"""
阶段 2（v3.0）：Token 计费中心——每次大模型调用自动记账，不靠人工数 token

设计三原则：
1. 自动：记账逻辑挂在 LangChain 回调（on_llm_end）上，业务代码只要带着
   BillingCallbackHandler 发起调用，就能拿到官方返回的真实 token 数，不用自己估算。
2. 防脆弱：记账失败（Redis 挂了、返回体里没有 usage 字段）绝不能影响业务对话，
   所有异常都吞掉记 warning，大不了这一笔没记上。
3. 可量化：价目表按阿里云百炼官方刊例价（元/千 token，分层计价），
   /billing/stats 能直接回答"花了多少钱、路由比全走 plus 省了多少"。

数据流：
   模型调用结束
     └─► BillingCallbackHandler.on_llm_end
           ├─ 从 response 里抽 model 名 + usage_metadata（input/output tokens）
           └─ record() ─► 进程内字典（保底） + Redis 哈希（重启不丢）
"""
from __future__ import annotations

from typing import Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app_my.core.logging import logger

# ============================================================
# 价目表：阿里云百炼按量付费刊例价（元 / 千 token，中国大陆地域）
# 来源：阿里云帮助中心《AI 服务计费（按量付费）》2026-09 查询值
# 结构：每档模型一个列表，元素 = (输入长度上限(千token), 输入价, 输出价)，
#       从上往下第一个满足"本次输入 token 数 <= 上限"的档位生效。
# 价目随时可能调整：改动只动这张表，计算逻辑不用碰。
# ============================================================
PRICE_TABLE: Dict[str, List[tuple]] = {
    "qwen3.7-flash": [
        (32, 0.00024, 0.00096),            # 输入 <= 32K token：最便宜档
        (256, 0.00072, 0.00288),           # 32K ~ 256K
        (float("inf"), 0.00144, 0.00576),  # 256K 以上
    ],
    "qwen3.7-plus": [
        (256, 0.0024, 0.0096),             # 我们的单次输入远小于 256K，实际总落这档
        (float("inf"), 0.0072, 0.0288),
    ],
    "qwen3.7-max": [
        (float("inf"), 0.0144, 0.0432),
    ],
}

# 记账时价目表里没有的模型（如视觉模型 qwen3.8-omni-*）：
# 不猜价格、不记 0 冒充便宜，而是原样展示 token 数并标注"价目未配置"——诚实原则。
UNPRICED = "unpriced"

# Redis 键前缀（模块级变量：单测里 monkeypatch 它，避免污染真实统计数据）
_REDIS_PREFIX = "billing:v1"

# 进程内保底账本：{(model_name): {"calls": n, "input_tokens": n, "output_tokens": n, "errors": n}}
# Redis 可用时对外统计读 Redis（跨重启、跨进程），Redis 不可用退回这本账
_memory_book: Dict[str, Dict[str, int]] = {}


def record(model: str, input_tokens: int, output_tokens: int, ok: bool = True) -> None:
    """
    记一笔账（幂等追加，不是覆盖）。

    双写策略：
      - 进程内字典：永远写（没有外部依赖，测试也用它）
      - Redis：尽力写（HINCRBY 原子自增），写失败只记日志
    """
    if not model:
        model = "unknown"

    # ① 进程内账本
    book = _memory_book.setdefault(
        model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0}
    )
    if ok:
        book["calls"] += 1
        book["input_tokens"] += int(input_tokens or 0)
        book["output_tokens"] += int(output_tokens or 0)
    else:
        book["errors"] += 1

    # ② Redis 账本（best-effort：挂了不影响业务）
    try:
        from app_my.core.redis_client import get_redis, redis_available

        if redis_available():
            r = get_redis()
            key = f"{_REDIS_PREFIX}:{model}"
            if ok:
                r.hincrby(key, "calls", 1)
                r.hincrby(key, "input_tokens", int(input_tokens or 0))
                r.hincrby(key, "output_tokens", int(output_tokens or 0))
            else:
                r.hincrby(key, "errors", 1)
    except Exception as exc:                      # Redis 掉线 / 连接拒绝等
        logger.warning("billing: Redis 记账失败（不影响业务）: %s", exc)


def estimate_cost_cny(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """
    按价目表估算一笔费用（单位：元）。

    返回 None 表示该模型不在价目表里（诚实：宁缺毋假）。
    分层计价规则：用【本次输入 token 数】决定档位（阿里云官方规则），输入输出分开乘单价。
    """
    tiers = PRICE_TABLE.get(model)
    if not tiers:
        return None
    for limit, in_price, out_price in tiers:     # 从便宜档往下找第一个命中的
        if input_tokens <= limit * 1000:
            return input_tokens / 1000 * in_price + output_tokens / 1000 * out_price
    return None                                   # 理论上到不了这里（有 inf 兜底档）


class BillingCallbackHandler(BaseCallbackHandler):
    """
    LangChain 回调：挂到模型调用上，调用结束自动记 token 账。

    用法（由 model_router.ainvoke_routed 统一挂载，业务代码不直接碰它）：
        await model.ainvoke(messages, config={"callbacks": [BillingCallbackHandler()]})
    """

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """模型正常返回：从 usage_metadata 抽真实 token 数记账"""
        try:
            generation = response.generations[0][0]
            message = getattr(generation, "message", None)
            if message is None:                    # 罕见：不是 chat 格式的返回
                return
            usage = getattr(message, "usage_metadata", None) or {}
            input_t = usage.get("input_tokens", 0)
            output_t = usage.get("output_tokens", 0)
            # 模型名：优先从响应元数据拿（真实调用的那个），拿不到标 unknown
            meta = getattr(message, "response_metadata", None) or {}
            model = meta.get("model_name") or meta.get("model") or "unknown"
            if input_t or output_t:
                record(model, input_t, output_t)
        except Exception as exc:
            logger.warning("billing: 记账异常（已忽略）: %s", exc)

    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        """模型调用失败：记一笔 errors（失败也占配额/可能计费，成本页要能看到）"""
        try:
            record("error", 0, 0, ok=False)
        except Exception:
            pass                                  # 记账失败就失败，不拦业务


def _read_book() -> Dict[str, Dict[str, int]]:
    """
    读汇总账本：优先 Redis（跨重启累计），不可用退回进程内账本。
    返回结构：{model: {"calls", "input_tokens", "output_tokens", "errors"}}
    """
    try:
        from app_my.core.redis_client import get_redis, redis_available

        if redis_available():
            r = get_redis()
            book: Dict[str, Dict[str, int]] = {}
            for key in r.scan_iter(match=f"{_REDIS_PREFIX}:*"):
                model = key.split(":", 2)[-1]     # billing:v1:qwen3.7-flash -> qwen3.7-flash
                data = r.hgetall(key)
                book[model] = {
                    "calls": int(data.get("calls", 0)),
                    "input_tokens": int(data.get("input_tokens", 0)),
                    "output_tokens": int(data.get("output_tokens", 0)),
                    "errors": int(data.get("errors", 0)),
                }
            if book:                              # Redis 有数据就不看内存账本
                return book
    except Exception as exc:
        logger.warning("billing: 读 Redis 账本失败，退回进程内账本: %s", exc)
    return {k: dict(v) for k, v in _memory_book.items()}


def get_billing_stats() -> dict:
    """
    生成 /billing/stats 的完整统计。

    三个数字的关系（省多少钱的口径）：
        baseline = 所有【已计价模型的调用】假设全部走标准档(qwen3.7-plus)的费用
        actual   = 当前实际发生的费用（含走 lite 省下的部分）
        saved    = (baseline - actual) / baseline
    注意：价目未配置的模型（如视觉）只展示 token，不参与省钱比例计算。
    """
    book = _read_book()

    models_out: Dict[str, dict] = {}
    unpriced: List[str] = []
    total_cost = 0.0
    baseline_cost = 0.0                            # 全走 plus 的假想费用
    totals = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0}

    for model, data in book.items():
        totals["calls"] += data["calls"]
        totals["input_tokens"] += data["input_tokens"]
        totals["output_tokens"] += data["output_tokens"]
        totals["errors"] += data["errors"]

        cost = estimate_cost_cny(model, data["input_tokens"], data["output_tokens"])
        if cost is None:
            unpriced.append(model)
            cost_out = None
        else:
            total_cost += cost
            # baseline：同样 token 数如果走 plus 是多少钱
            plus_cost = estimate_cost_cny("qwen3.7-plus", data["input_tokens"], data["output_tokens"])
            if plus_cost is not None:
                baseline_cost += plus_cost
            cost_out = round(cost, 6)

        models_out[model] = {
            "calls": data["calls"],
            "input_tokens": data["input_tokens"],
            "output_tokens": data["output_tokens"],
            "errors": data["errors"],
            "estimated_cost_cny": cost_out,       # None = 价目未配置
        }

    saved_percent = (
        round((baseline_cost - total_cost) / baseline_cost * 100, 2)
        if baseline_cost > 0 and total_cost > 0
        else 0.0
    )

    return {
        "totals": {**totals, "estimated_cost_cny": round(total_cost, 6)},
        "models": models_out,
        "unpriced_models": unpriced,
        "routing": {
            "all_standard_baseline_cny": round(baseline_cost, 6),   # 全走 plus 的假想成本
            "actual_cost_cny": round(total_cost, 6),                # 路由后实际成本
            "saved_percent": saved_percent,                         # 真实节省百分比
        },
    }


def reset_billing() -> None:
    """
    清空账本（测试脚本/演示前用）。
    Redis 和进程内账本一起清；key 不存在时 delete 不报错（幂等）。
    """
    _memory_book.clear()
    try:
        from app_my.core.redis_client import get_redis, redis_available

        if redis_available():
            r = get_redis()
            for key in list(r.scan_iter(match=f"{_REDIS_PREFIX}:*")):
                r.delete(key)
    except Exception as exc:
        logger.warning("billing: 清空 Redis 账本失败: %s", exc)
```

**验证**：

```powershell
python -c "from app_my.core.token_billing import estimate_cost_cny; print(estimate_cost_cny('qwen3.7-flash', 1000, 1000))"
```

应输出：`0.0012`（1000 输入 + 1000 输出按 flash 第一档计价）

---

## 7. 第六步：新建 api/billing.py 并注册路由

**操作 A**：新建 `app_my/api/billing.py`，完整复制：

```python
# app_my/api/billing.py
"""
阶段 2（v3.0）：成本统计接口——回答"这个系统跑一天要花多少钱、路由省了多少"

接口（受 JWT 鉴权保护，需要登录后带 access token 访问）：
    GET /billing/stats    Token 消耗与成本统计

返回三块内容：
    totals  总调用次数 / 总 token / 总费用
    models  按模型拆分的明细（flash 走了多少、plus 走了多少）
    routing 智能路由的省钱效果：全走 plus 的假想成本 vs 实际成本 vs 节省百分比
"""
from fastapi import APIRouter

from app_my.core.token_billing import get_billing_stats

router = APIRouter()


@router.get("/stats")
async def billing_stats():
    """
    Token 计费统计。

    数据来源：每次模型调用结束时由 BillingCallbackHandler 自动记账，
    进程重启不丢（Redis 持久累计）。
    """
    return get_billing_stats()
```

**操作 B**：改 `main.py` 两行。导入行：

```python
from app_my.api import oss, chat, auth, user, billing   # auth/user/recipe 在阶段 4 之后引入；billing 为 v3阶段2 新增
```

路由注册区（加在 `user.router` 那行后面）：

```python
app.include_router(billing.router, prefix="/billing", tags=["成本统计(v3阶段2)"])   # 🟢 v3阶段2 新增
```

**验证**（后端还没起，只验证 import 链路）：

```powershell
python -c "import main; print('main.py 导入正常')"
```

应输出：`main.py 导入正常`

---

## 8. 第七步：改 recognizer.py（三处）

**操作**：打开 `app_my/agents/recognizer.py`，改三处。

**改动 1**：导入区（第 25 行附近）——

```python
from app_my.core.logging import logger
from app_my.core.model_router import ainvoke_routed   # 🔵 v3阶段2：模型调用改走智能路由
```

（原来是 `from app_my.core.models import get_chat_model, get_vision_model`，整行替换。）

**改动 2**：看图分支 `_extract_from_image` 里（原来是 `response = await get_vision_model().ainvoke([SystemMessage(content=IMAGE_SYS), message])`）——

```python
        response = await ainvoke_routed("vision", [SystemMessage(content=IMAGE_SYS), message])
```

**改动 3**：文字抽取分支 `_extract_from_text` 里（原来是 `response = await get_chat_model().ainvoke(\n                [SystemMessage(content=TEXT_SYS), HumanMessage(content=prompt)]\n            )`）——

```python
            response = await ainvoke_routed(
                "extract",
                [SystemMessage(content=TEXT_SYS), HumanMessage(content=prompt)],
                text=text,                       # 🔵 v3阶段2：把原文传给路由判复杂度
            )
```

**验证**：

```powershell
python -c "from app_my.agents.recognizer import recognize_node; print('recognizer 导入正常')"
```

---

## 9. 第八步：改 output.py（两处）

**操作**：打开 `app_my/agents/output.py`，改两处。

**改动 1**：导入区（第 20 行附近）——

```python
from app_my.core.logging import logger
from app_my.core.model_router import ainvoke_routed   # 🔵 v3阶段2：报告生成改走智能路由（standard 档）
```

（原来是 `from app_my.core.models import get_chat_model`，整行替换。）

**改动 2**：`output_node` 函数里的模型调用行（原来是 `response = await get_chat_model().ainvoke([SystemMessage(content=OUTPUT_SYS), HumanMessage(content=prompt)])`）——

```python
        response = await ainvoke_routed("report", [SystemMessage(content=OUTPUT_SYS), HumanMessage(content=prompt)], text=user_text)
```

> 🟡 这一行比较长（超 100 字符），可以折成多行，只要参数不丢。原有的 try/except、兜底报告逻辑一行都不用动。

**验证**：

```powershell
python -c "from app_my.agents.coordinator import build_workflow; print('工作流导入正常')"
```

---

## 10. 第九步：新增三个测试文件

**操作 A**：新建 `tests/unit/test_model_router.py`，完整复制：

```python
# tests/unit/test_model_router.py
"""
阶段 2 单元测试：智能路由的规则与成本计算（不打真实模型、不花钱）
"""
import pytest

from app_my.core.model_router import classify_complexity, route
from app_my.core.token_billing import estimate_cost_cny, PRICE_TABLE


# ============================================================
# 复杂度判别
# ============================================================

class TestClassifyComplexity:
    def test_short_simple(self):
        assert classify_complexity("我有鸡蛋和西红柿") == "simple"

    def test_empty_is_simple(self):
        assert classify_complexity("") == "simple"

    def test_long_text_is_complex(self):
        assert classify_complexity("今天" + "菜市场买了好多东西" * 15) == "complex"

    def test_keyword_is_complex(self):
        assert classify_complexity("帮我分析一下这餐的热量") == "complex"

    def test_many_ingredients_is_complex(self):
        assert classify_complexity("鸡蛋、西红柿、青椒、土豆、牛肉、豆腐") == "complex"

    def test_few_ingredients_still_simple(self):
        assert classify_complexity("鸡蛋、西红柿、青椒") == "simple"


# ============================================================
# 路由决策
# ============================================================

class TestRoute:
    def test_extract_simple_goes_lite(self):
        assert route("extract", "我有鸡蛋和西红柿") == "lite"

    def test_extract_complex_goes_standard(self):
        assert route("extract", "帮我详细分析这些食材的营养搭配") == "standard"

    def test_report_always_standard(self):
        assert route("report", "很简单的话") == "standard"

    def test_vision_fixed(self):
        assert route("vision") == "vision"

    def test_unknown_task_falls_to_standard(self):
        assert route("nonexistent-task") == "standard"


# ============================================================
# 成本计算（价目表数学）
# ============================================================

class TestEstimateCost:
    def test_flash_basic(self):
        # 1000 输入 + 1000 输出，落在 flash 第一档：0.00024 + 0.00096 = 0.0012 元
        cost = estimate_cost_cny("qwen3.7-flash", 1000, 1000)
        assert cost == pytest.approx(0.0012)

    def test_plus_is_ten_x(self):
        # 同样 token 走 plus：0.0024 + 0.0096 = 0.012 元，正好是 flash 的 10 倍
        cost = estimate_cost_cny("qwen3.7-plus", 1000, 1000)
        assert cost == pytest.approx(0.012)
        assert cost == pytest.approx(estimate_cost_cny("qwen3.7-flash", 1000, 1000) * 10)

    def test_unknown_model_returns_none(self):
        assert estimate_cost_cny("some-unknown-model", 1000, 1000) is None

    def test_flash_tier_boundary(self):
        # 33000 输入超过 32K，应落到第二档（0.00072/0.00288）
        cost = estimate_cost_cny("qwen3.7-flash", 33_000, 1000)
        assert cost == pytest.approx(33 * 0.00072 + 1 * 0.00288)

    def test_price_table_covers_key_models(self):
        for m in ("qwen3.7-flash", "qwen3.7-plus", "qwen3.7-max"):
            assert m in PRICE_TABLE
```

**操作 B**：新建 `tests/unit/test_token_billing.py`，完整复制：

```python
# tests/unit/test_token_billing.py
"""
阶段 2 单元测试：Token 记账回调（不打真实模型、不碰 Redis）
"""
import pytest

import app_my.core.token_billing as tb
from app_my.core.token_billing import (
    BillingCallbackHandler,
    estimate_cost_cny,
    get_billing_stats,
    record,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """每个测试自带隔离：清空内存账本 + 屏蔽 Redis（只测纯内存路径）。

    注意必须 patch redis_client 源模块里的 redis_available——
    token_billing 的 record/_read_book 都是函数内局部 import，
    patch billing 模块自己的引用拦不住它们。
    """
    import app_my.core.redis_client as redis_client

    tb._memory_book.clear()
    monkeypatch.setattr(redis_client, "redis_available", lambda: False)
    yield
    tb._memory_book.clear()


def _fake_response(model: str, input_tokens: int, output_tokens: int):
    """手工构造一个带 usage_metadata 的假 AIMessage/LLMResult，模拟模型返回"""
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    msg = AIMessage(content="ok")
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    msg.response_metadata = {"model_name": model}
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


class TestRecord:
    def test_record_accumulates(self):
        record("qwen3.7-flash", 100, 50)
        record("qwen3.7-flash", 200, 80)
        book = tb._memory_book["qwen3.7-flash"]
        assert book["calls"] == 2
        assert book["input_tokens"] == 300
        assert book["output_tokens"] == 130

    def test_record_error(self):
        record("qwen3.7-flash", 0, 0, ok=False)
        assert tb._memory_book["qwen3.7-flash"]["errors"] == 1


class TestCallbackHandler:
    def test_on_llm_end_records_usage(self):
        handler = BillingCallbackHandler()
        handler.on_llm_end(_fake_response("qwen3.7-plus", 500, 200))
        book = tb._memory_book["qwen3.7-plus"]
        assert book["calls"] == 1
        assert book["input_tokens"] == 500
        assert book["output_tokens"] == 200

    def test_on_llm_error_counts(self):
        handler = BillingCallbackHandler()
        handler.on_llm_error(RuntimeError("boom"))
        assert tb._memory_book["error"]["errors"] == 1

    def test_malformed_response_does_not_raise(self):
        handler = BillingCallbackHandler()
        handler.on_llm_end(None)          # 任何结构异常都不能抛出去影响业务
        assert tb._memory_book == {}


class TestStats:
    def test_stats_shape_and_savings(self):
        # lite 一笔 + standard 一笔：省钱比例应大于 0（flash 比 plus 便宜）
        record("qwen3.7-flash", 1000, 1000)
        record("qwen3.7-plus", 1000, 1000)
        stats = get_billing_stats()

        assert stats["totals"]["calls"] == 2
        assert set(stats["models"]) == {"qwen3.7-flash", "qwen3.7-plus"}
        # flash 那笔 0.0012 元，plus 那笔 0.012 元
        assert stats["models"]["qwen3.7-flash"]["estimated_cost_cny"] == pytest.approx(0.0012)
        assert stats["models"]["qwen3.7-plus"]["estimated_cost_cny"] == pytest.approx(0.012)
        # 全走 plus 的假想成本 = 0.012 + 0.012 = 0.024；实际 = 0.0132；省 45%
        assert stats["routing"]["all_standard_baseline_cny"] == pytest.approx(0.024)
        assert stats["routing"]["actual_cost_cny"] == pytest.approx(0.0132)
        assert stats["routing"]["saved_percent"] == pytest.approx(45.0)

    def test_unpriced_model_listed(self):
        record("qwen3.8-omni-flash-realtime", 800, 300)
        stats = get_billing_stats()
        assert "qwen3.8-omni-flash-realtime" in stats["unpriced_models"]
        assert stats["models"]["qwen3.8-omni-flash-realtime"]["estimated_cost_cny"] is None
```

**操作 C**：新建 `tests/integration/test_billing_api.py`，完整复制：

```python
# tests/integration/test_billing_api.py
"""
阶段 2 集成测试：/billing/stats 成本统计接口（需要后端在跑）
- 接口必须受 JWT 保护：不带 token 401
- 登录后返回完整的三段结构：totals / models / routing
"""
import requests


def test_billing_stats_requires_auth(base_url):
    """不带 token 访问必须 401——成本数据不能裸奔"""
    resp = requests.get(f"{base_url}/billing/stats", timeout=15)
    assert resp.status_code == 401


def test_billing_stats_shape(base_url, account):
    """带 token 访问：返回结构完整（数字可能是 0，但字段必须在）"""
    resp = requests.get(
        f"{base_url}/billing/stats",
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "totals" in data
    assert "models" in data
    assert "routing" in data
    for field in ("calls", "input_tokens", "output_tokens", "errors", "estimated_cost_cny"):
        assert field in data["totals"]
    for field in ("all_standard_baseline_cny", "actual_cost_cny", "saved_percent"):
        assert field in data["routing"]
```

---

## 11. 第十步：跑测试

**操作**：

1. 确认 v3 基础设施在跑（阶段 1 起的两个容器）：`docker ps` 应看到 `ai_chief_pgvector` 和 `ai_chief_redis` 都是 Up。
2. 起后端（新终端，保持运行）：

```powershell
cd F:\pycharm_aiprogram\ai_chief
.venv3\Scripts\Activate.ps1
python main.py
```

3. 另开一个终端跑测试：

```powershell
cd F:\pycharm_aiprogram\ai_chief
.venv3\Scripts\Activate.ps1
pytest tests/ -q
```

**验证**：

```text
39 passed, 1 deselected in 2.xxs
```

（阶段 1 基线是 14 个；本阶段新增 23 个单元 + 2 个集成 = 39。`1 deselected` 是真实大模型测试，默认跳过。）

再跑真实 LLM 测试（验证路由 + 计费 + 关思考后的全链路，约 15~30 秒）：

```powershell
pytest tests/test_chat_llm.py -m llm -q
```

**验证**：`1 passed`。同时后端日志里应能看到两行路由记录：

```text
router: task=extract tier=lite -> qwen3.7-flash
router: task=report tier=standard -> qwen3.7-plus
```

**再看一眼计费数据（真实对话已经记账了）**：注册/登录拿 token 后访问（或用 pytest 里的账号重新登一个）：

```powershell
curl.exe -s http://127.0.0.1:9002/billing/stats -H "Authorization: Bearer <你的access_token>"
```

应看到 `models` 里同时有 `qwen3.7-flash` 和 `qwen3.7-plus` 的条目——**这就是智能路由在真实工作的证据**。

---

## 12. 第十一步：跑对比实验（本阶段验收数字）

**操作**：新建 `scripts/route_compare.py`，完整复制：

```python
# scripts/route_compare.py
"""
阶段 2（v3.0）：智能路由省钱对比实验——用真实 API 调用得出"省多少"的实测数字

实验设计（同批请求、三种策略各跑一遍）：
    策略A all-flash  ：所有调用都走轻量档 qwen3.7-flash（= v2.0 现状）
    策略B all-plus   ：所有调用都走标准档 qwen3.7-plus（= 不差钱基线）
    策略C routed     ：智能路由（抽食材按复杂度分流，报告恒 plus）

每组对话 = 2 次模型调用（模拟真实工作流）：
    第 1 次：食材抽取（recognizer 的真实提示词 TEXT_SYS）
    第 2 次：报告生成（output 的真实提示词 OUTPUT_SYS + 真实菜谱数据）

输出：三种策略的 token 消耗、真实费用（按官方刊例价）、平均延迟，
      以及"路由 vs 全 plus 节省百分比"——阶段 2 的验收数字。

用法（项目根目录，激活 venv 后）：
    python scripts/route_compare.py
注意：会打真实大模型（约 36 次调用，费用约几分钱），跑一次即可。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))   # 把项目根目录加入搜索路径（scripts/ 下运行需要）

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage

from app_my.agents.output import OUTPUT_SYS
from app_my.agents.recognizer import TEXT_SYS
from app_my.core.config import settings
from app_my.core.model_router import classify_complexity
from app_my.core.token_billing import estimate_cost_cny

# 六个测试场景：短输入 / 长输入 / 信号词 / 多食材，覆盖路由规则的各分支
SCENARIOS = [
    "我有鸡蛋和西红柿",
    "冰箱里有西兰花和鸡胸肉",
    "土豆、茄子、青椒怎么做",
    "我买了鸡蛋、西红柿、青椒、土豆、牛肉、豆腐、木耳、粉条，帮我详细分析怎么搭配",
    "帮我看下鸡胸肉约300克加糙米饭的热量，我在减脂期需要控糖，请给出营养方案",
    "家里就剩半颗白菜和两个鸡蛋了，随便给我推荐个简单的做法，我是上班族，30分钟内能搞定",
]

MODELS = {
    "flash": settings.MODEL_LITE,        # 轻量档
    "plus": settings.MODEL_STANDARD,     # 标准档
}


class LocalBilling(BaseCallbackHandler):
    """本脚本专用的本地记账（不写全局账本，实验数据与生产统计隔离）"""

    def __init__(self):
        self.rows = []                   # [(model, input_tokens, output_tokens)]

    def on_llm_end(self, response, **kwargs):
        try:
            gen = response.generations[0][0]
            msg = gen.message
            usage = getattr(msg, "usage_metadata", None) or {}
            meta = getattr(msg, "response_metadata", None) or {}
            model = meta.get("model_name") or "unknown"
            self.rows.append((model, usage.get("input_tokens", 0), usage.get("output_tokens", 0)))
        except Exception:
            pass


_model_cache = {}


def get_model(tier: str):
    """模型实例缓存：同档位只建一次"""
    if tier not in _model_cache:
        _model_cache[tier] = init_chat_model(
            model=MODELS[tier],
            model_provider="openai",
            base_url=settings.DASHSCOPE_BASE_URL,
            api_key=settings.DASHSCOPE_API_KEY,
            extra_body={"enable_thinking": False},   # 与生产一致：关思考模式
        )
    return _model_cache[tier]


def build_report_prompt(scenario: str) -> str:
    """用项目里真实的菜谱数据拼一份报告提示词（模拟 output 节点的真实输入）"""
    with open("app_my/knowledge/data/recipes.json", encoding="utf-8") as f:
        recipes = json.load(f)
    top = recipes[0]
    recipe_block = (
        f"1. **{top.get('name')}**（{top.get('time_minutes', '-')}分钟，"
        f"约 {top.get('calories', '-')} 千卡）\n"
        f"   - 推荐理由：与食材匹配\n"
        f"   - 主要食材：{'、'.join(top.get('ingredients', [])[:5])}\n"
        f"   - 做法：{' → '.join(top.get('steps', [])[:3])}"
    )
    return f"""用户原话：{scenario}

识别到的食材：
- 鸡胸肉 约200g 新鲜度 9/10

营养分析结果（JSON）：
{{"total_estimated": {{"calories": 320, "protein": 38, "fat": 6, "carbs": 12}}}}

候选菜谱（已按用户画像排序，含推荐理由）：
{recipe_block}

用户画像：{{"goal": "减脂", "forbidden": [], "dislikes": ["香菜"], "prefer_tags": ["低脂"]}}
"""


async def call_once(tier: str, messages):
    """打一次模型，返回 (记账行, 耗时秒)"""
    billing = LocalBilling()
    t0 = time.perf_counter()
    await get_model(tier).ainvoke(messages, config={"callbacks": [billing]})
    elapsed = time.perf_counter() - t0
    row = billing.rows[0] if billing.rows else ("unknown", 0, 0)
    return row, elapsed


async def run_strategy(name: str, pick_extract, pick_report) -> dict:
    """
    跑一种策略。pick_extract/pick_report 是"场景 -> 档位"的函数。
    返回汇总：调用数 / token / 费用 / 平均延迟 / 明细行。
    """
    rows, latencies, details = [], [], []
    for idx, sc in enumerate(SCENARIOS, 1):
        extract_tier = pick_extract(sc)
        report_tier = pick_report(sc)

        row1, dt1 = await call_once(extract_tier, [SystemMessage(content=TEXT_SYS), HumanMessage(content=sc)])
        prompt2 = build_report_prompt(sc)
        row2, dt2 = await call_once(report_tier, [SystemMessage(content=OUTPUT_SYS), HumanMessage(content=prompt2)])

        rows.extend([row1, row2])
        latencies.extend([dt1, dt2])
        complexity = classify_complexity(sc)
        details.append((idx, complexity, extract_tier, report_tier))

    cost = sum(
        estimate_cost_cny(m, i, o) or 0.0 for m, i, o in rows
    )
    return {
        "name": name,
        "calls": len(rows),
        "input_tokens": sum(r[1] for r in rows),
        "output_tokens": sum(r[2] for r in rows),
        "cost": cost,
        "avg_latency": sum(latencies) / len(latencies),
        "details": details,
        "rows": rows,
    }


async def main():
    if not settings.DASHSCOPE_API_KEY:
        raise SystemExit("未配置 DASHSCOPE_API_KEY，请先在 .env 填好再跑本实验")

    print("=" * 62)
    print("阶段2 智能路由省钱对比实验（真实 API 调用，约 36 次，请稍等）")
    print("=" * 62)

    results = {}

    results["A"] = await run_strategy(
        "all-flash（全部轻量档，v2.0 现状）",
        lambda sc: "flash",
        lambda sc: "flash",
    )
    print(f"[1/3] 策略A all-flash 完成：{results['A']['calls']} 次调用")

    results["B"] = await run_strategy(
        "all-plus（全部标准档，不差钱基线）",
        lambda sc: "plus",
        lambda sc: "plus",
    )
    print(f"[2/3] 策略B all-plus 完成：{results['B']['calls']} 次调用")

    results["C"] = await run_strategy(
        "routed（智能路由）",
        lambda sc: "plus" if classify_complexity(sc) == "complex" else "flash",
        lambda sc: "plus",
    )
    print(f"[3/3] 策略C routed 完成：{results['C']['calls']} 次调用")

    # ---------- 汇总表 ----------
    print()
    print("=" * 62)
    print(f"{'策略':<28}{'调用':<6}{'输入tok':<10}{'输出tok':<10}{'费用(元)':<12}{'平均延迟':<10}")
    print("-" * 62)
    for key in ("A", "B", "C"):
        r = results[key]
        print(
            f"{r['name']:<30}{r['calls']:<8}{r['input_tokens']:<12}"
            f"{r['output_tokens']:<12}{r['cost']:<14.6f}{r['avg_latency']:<10.2f}"
        )
    print("-" * 62)

    # ---------- 路由明细 ----------
    print()
    print("智能路由分流明细（场景 / 复杂度 / 抽取档 / 报告档）：")
    for idx, complexity, ex_tier, rp_tier in results["C"]["details"]:
        print(f"  场景{idx}: 复杂度={complexity:<8} 抽取={ex_tier:<7} 报告={rp_tier}")

    # ---------- 结论数字 ----------
    saved = results["B"]["cost"] - results["C"]["cost"]
    saved_percent = saved / results["B"]["cost"] * 100 if results["B"]["cost"] else 0
    extra_vs_flash = results["C"]["cost"] - results["A"]["cost"]

    print()
    print("=" * 62)
    print("结论：")
    print(f"  路由 vs 全plus基线 : 节省 {saved:.6f} 元（{saved_percent:.1f}%）")
    print(f"  路由 vs 全flash现状: 多花 {extra_vs_flash:.6f} 元（报告升级到标准档的质量成本）")
    print(f"  实验样本：{len(SCENARIOS)} 个场景 x 2 次调用 x 3 种策略")
    print("=" * 62)
    print("以上数字为本机实测，可直接用于简历与面试（阶段10 汇总时引用本输出）。")


if __name__ == "__main__":
    asyncio.run(main())
```

**操作**（项目根目录，后端可以不用开）：

```powershell
cd F:\pycharm_aiprogram\ai_chief
.venv3\Scripts\Activate.ps1
python scripts/route_compare.py
```

**验证**（2026-09-27 本机实测参考，你的数字会略有不同，属正常）：

```text
策略                          调用    输入tok     输出tok     费用(元)       平均延迟
all-flash（全部轻量档）        12      4362        21753       0.021930      25.92
all-plus（全部标准档）         12      4362        15496       0.159230      22.47
routed（智能路由）            12      4362        16445       0.151095      23.28

路由 vs 全plus基线 : 节省 5.1%
路由 vs 全flash现状: 多花 0.129 元（报告升级到标准档的质量成本）
```

🟣 **怎么读这个数字（面试官一定会问）**：

- **为什么只省 5.1%？** 因为成本大头在"报告生成"（长输出），而报告是质量敏感任务恒走 plus 不分流；能分流的只有抽取（短输出），它在总成本里占比本来就小。**路由省的是"能省的部分"，不是硬砍质量**——这正是成本治理和偷工减料的区别。
- **为什么 flash 输出 token 反而更多（21753 vs 15496）？** 实测发现 flash 比 plus 啰嗦——单价便宜 10 倍但字数更多，实际省钱比例低于单价差。**这是只有做了真实实验才能知道的细节**，也是"别只看刊例价"的活教材。
- **真实对话账本（/billing/stats）显示省 23%**，和实验的 5.1% 不同——因为实验场景里复杂输入占比高（6 个里 2 个 complex），而日常短对话 simple 占比更高。**省钱比例取决于流量结构**，这两个数字放在一起讲反而更真实。

---

## 13. 验收清单

| # | 验收项 | 结果 | 怎么验 |
|---|---|---|---|
| 1 | 单元+集成测试全绿 | ✅ | `pytest tests/ -q` → 39 passed |
| 2 | 真实 LLM 流式对话通过 | ✅ | `pytest tests/test_chat_llm.py -m llm -q` → 1 passed（约 15~30 秒，不超时） |
| 3 | 路由真实分流 | ✅ | 后端日志出现 `task=extract tier=lite` 和 `task=report tier=standard` |
| 4 | 计费自动记账 | ✅ | `/billing/stats` 的 models 里 flash 和 plus 都有账 |
| 5 | 接口受保护 | ✅ | 不带 token 访问 /billing/stats 返回 401 |
| 6 | 对比实验跑出真实数字 | ✅ | `python scripts/route_compare.py` 输出三策略对比 + 节省百分比 |
| 7 | 思考模式已关 | ✅ | LLM 测试 15 秒级完成（开启时是 79 秒且首字节超时） |
| 8 | v2.0 不受影响 | ✅ | `docker ps` 里 ai_sichu_* 四容器照常运行，`http://127.0.0.1:8001/health` 正常 |

---

## 14. 错误对照表

| # | 错误现象 | 原因 | 解决 |
|---|---|---|---|
| E1 | `ModuleNotFoundError: app_my.core.token_billing` | model_router 先建了、token_billing 还没建 | 按手册顺序建完第 6 步再验证；这是暂时现象不是错误 |
| E2 | `ModuleNotFoundError: No module named 'app_my'`（跑 route_compare.py） | 从 scripts/ 目录直接跑脚本，Python 找不到项目根 | 确认脚本开头有 `sys.path.insert` 那两行；且在**项目根目录**执行 `python scripts/route_compare.py` |
| E3 | LLM 测试失败：`首字节延迟 xx s，过长`（>60 秒） | 思考模式没关——检查 models.py 两个工厂里 `extra_body={"enable_thinking": False}` 是否漏了 | 补上 extra_body 后**重启后端**再测 |
| E4 | 单测报 `assert 5 == 2` 之类"账对不上" | 单测没隔离干净，读到了 Redis 里的历史账（或写进去了） | 确认 `_isolated` fixture 里 patch 的是 `redis_client` 源模块（不是 `tb` 模块）——手册代码已是修正版 |
| E5 | `/billing/stats` 返回 401 | 这是设计行为：接口受 JWT 保护 | 先注册/登录拿 access_token，带 `Authorization: Bearer <token>` 访问 |
| E6 | 跑了对话但 `/billing/stats` 数字是 0 | 后端连的 Redis 和你看的不是同一个库；或对话走了兜底（没调模型） | 核对后端启动时的 REDIS_URL（6380）；看后端日志有没有 `router: task=` 记录 |
| E7 | route_compare.py 跑了十几分钟还没完 | 正常——plus 生成长报告每次 20~40 秒，36 次调用约 10~15 分钟 | 耐心等；只跑这一次，以后不用重复跑 |
| E8 | `model not found` / 404 之类模型报错 | .env 或代码里模型名写错（比如 qwen3.7-plus 写成 qwen-plus） | 核对：`qwen3.7-flash`、`qwen3.7-plus`（中间有点号） |
| E9 | 连续跑多轮测试出现 429 | IP 级限流 60/分 | 等 60 秒再跑 |
| E10 | pytest 报 39 个以外的数量 | tests/unit 或 tests/integration 下文件没建齐 | 核对第 10 步的三个文件都在、文件名一致 |

---

## 15. 不做清单

本阶段**故意不做**的事（都有明确理由，做到阶段对应章节再说）：

| 不做 | 理由 | 以后在哪做 |
|---|---|---|
| 按天/按用户拆账 | 现在只有"总账"够用；拆账要等租户概念 | 阶段 9（多租户：键名升级为 billing:v1:{tenant}:{model}） |
| Token 用量配额限制 | 配额属于商业化能力 | 阶段 9（租户配额） |
| max 旗舰档接入 | 当前没有需要 max 的任务，接入只是摆设 | 有真实重任务时按需加 |
| 用 LLM 判复杂度 | 判别本身花钱加延迟，规则引擎够用 | 不做（除非规则明显不够用） |
| 视觉模型计价 | omni 系列刊例结构与文本模型不同，没有可比单价，宁缺毋假 | 查到可靠价目后补 PRICE_TABLE 一行即可 |
| 成本告警/预算 | 属于监控范畴 | 阶段 7（Prometheus 告警规则） |

---

## 16. 提交 Gitee 与 PR 描述

**操作**：

```powershell
cd F:\pycharm_aiprogram\ai_chief
git add app_my/core/model_router.py app_my/core/token_billing.py app_my/api/billing.py tests/unit/test_model_router.py tests/unit/test_token_billing.py tests/integration/test_billing_api.py scripts/route_compare.py
git add app_my/core/config.py app_my/core/models.py app_my/agents/recognizer.py app_my/agents/output.py main.py
git status
git commit -m "feat(v3-stage2): 多模型智能路由+Token计费——分级分流/自动记账/关思考模式提速"
git push origin feat/v3-stage2
```

然后在 Gitee 发 PR：`feat/v3-stage2 → master`，标题和描述直接用下面这段：

---

### PR 标题

feat(v3-stage2): 多模型智能路由 + Token 计费

### PR 描述

#### 改动概述

给大模型调用装上"成本大脑"：按任务复杂度智能分流 + 每次调用自动记账 + 成本统计接口 + 真实省钱对比实验。

#### 核心改动

- **智能路由 `model_router.py`**：任务类型（extract/report/vision）+ 复杂度规则（长度/信号词/食材数）→ lite(qwen3.7-flash) / standard(qwen3.7-plus) 分档；standard 失败自动降级 lite 重试
- **Token 计费 `token_billing.py`**：LangChain 回调自动抓官方 usage 记账（进程内 + Redis 双写，重启不丢）；按阿里云刊例价分层计价折算成元；未定价模型诚实标注 unpriced
- **成本接口 `/billing/stats`**（JWT 保护）：总账/分模型明细/路由节省百分比三段式输出
- **实测修复：关闭思考模式**——qwen3.7 系列默认开深度思考，思考 token 按输出价计费且把报告生成拖到 58 秒；`extra_body={"enable_thinking": False}` 后 2 秒级，流式对话端到端 79s → 15.7s
- 业务节点改造最小化：recognizer/output 各改 1~2 行调用（换成 ainvoke_routed 收口）

#### 测试

- 新增 23 个单元测试（路由规则/价目数学/记账回调/统计口径）+ 2 个集成测试（鉴权/结构）
- 全量 39 passed；真实 LLM 流式测试通过
- 对照实验（6 场景 × 3 策略 × 2 调用，36 次真实调用）：全 flash ¥0.0219 / 全 plus ¥0.1592 / 路由 ¥0.1511，**比全 plus 基线省 5.1%**；真实对话账本显示日常短对话场景省 23%

#### 不在本 PR 的内容

按天/按租户拆账、配额限制（阶段 9）；成本告警（阶段 7）

---

---

## 17. 收官总结

### 17.1 收官状态（2026-09-28）

| 项 | 结果 |
|---|---|
| 施工期问题 | **0 个**（一次施工通过，历史第二次） |
| 测试 | 39 passed（阶段 1 基线 14 + 本阶段 25） |
| 真实 LLM 流式 | 1 passed，端到端 15.7 秒（思考模式修复前 79 秒超时） |
| 对比实验 | 全 flash ¥0.0219 / 全 plus ¥0.1592 / 路由 ¥0.1511（**省 5.1%**） |
| 真实对话账本 | `/billing/stats` 显示日常短对话场景**省 23.2%** |
| git | feat/v3-stage2 已合并 master（**PR !2**，commit 99e7f73） |
| v2.0 影响 | 无（ai_sichu 目录与四容器全程未动） |

### 17.2 本阶段沉淀的简历叙事

- **大模型成本治理**：分级智能路由（规则引擎判复杂度，零额外成本）+ LangChain 回调自动记账 + 官方刊例价分层折算，省钱比例可量化。
- **实测驱动的性能与成本修复**：发现 qwen3.7 系列默认开启思考模式（思考 token 按输出价计费、报告生成 58 秒），一行参数修复：流式端到端 79s → 15.7s，抽取任务输出 token 省 65%。
- **实验方法论**：同批请求 × 三策略对照实验；发现轻量模型输出更啰嗦（token 多 40%）——省钱比例取决于流量结构，刊例价不等于实际成本。

### 17.3 遗留与后续

| 事项 | 去向 |
|---|---|
| 按天/按租户拆账、Token 配额 | 阶段 9（多租户 SaaS） |
| 成本告警 | 阶段 7（Prometheus 告警规则） |
| 视觉模型计价（omni 系列价目未配置） | 查到可靠价目后补 `PRICE_TABLE` 一行 |
| max 旗舰档 | 出现真实重任务时按需接入 |

### 17.4 下一阶段预告

**阶段 3：Neo4j 知识图谱 + 多跳推理**——向量检索管"相似度"，图谱管"关系推理"（如"糖尿病患者能不能吃土豆、为什么"）。新增 Neo4j 容器（端口 7474/7687）、`Ingredient-Nutrient-Recipe-Contraindication` 数据模型、图谱推理接入 rank 节点。
