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