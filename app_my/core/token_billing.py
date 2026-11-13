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
   
   
    # ③ 阶段 7：metrics 上报（不影响原记账逻辑；失败则吞掉）
    try:
        from app_my.core.metrics import tokens_inc, cost_inc
        if ok:
            tokens_inc(model, "input", int(input_tokens or 0))
            tokens_inc(model, "output", int(output_tokens or 0))
            cost = estimate_cost_cny(model, int(input_tokens or 0), int(output_tokens or 0))
            if cost is not None:
                cost_inc(model, cost)
    except Exception:
        pass


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


def get_billing_stats(*, tenant_id: Optional[int] = None) -> dict:
    """
    生成 /billing/stats 的完整统计。

    三个数字的关系（省多少钱的口径）：
        baseline = 所有【已计价模型的调用】假设全部走标准档(qwen3.7-plus)的费用
        actual   = 当前实际发生的费用（含走 lite 省下的部分）
        saved    = (baseline - actual) / baseline
    注意：价目未配置的模型（如视觉）只展示 token，不参与省钱比例计算。

    v3阶段4 新增 tenant_id 参数：当前按租户拆账本的最简实现——保留原 totals，
    仅把 tenant_id 透传到响应里；后续阶段可把 Redis key 改成 billing:v1:<tenant_id>:<model>。
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

    result = {
        "totals": {**totals, "estimated_cost_cny": round(total_cost, 6)},
        "models": models_out,
        "unpriced_models": unpriced,
        "routing": {
            "all_standard_baseline_cny": round(baseline_cost, 6),   # 全走 plus 的假想成本
            "actual_cost_cny": round(total_cost, 6),                # 路由后实际成本
            "saved_percent": saved_percent,                         # 真实节省百分比
        },
    }
    if tenant_id is not None:
        result["tenant_id"] = tenant_id  # 标记当前是按租户视角返回
    return result


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