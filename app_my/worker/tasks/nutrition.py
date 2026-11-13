# app_my/worker/tasks/nutrition.py  —— v3 阶段 8：营养报告生成（长任务 ③）
"""
用户最直观的长任务：提交一串食材，后台算出一份营养报告，算完推到浏览器右下角。

为什么营养报告"适合异步"：
    算营养本身是查表 + 四则运算（很快），但真实报告还要做"同类菜谱检索 + 大模型润色建议"，
    这两步是秒级到十秒级的。用户在页面上等十秒会以为卡死了——所以交后台跑，算完再通知。

本任务用工具 calculate_nutrition（纯查表，稳定可复现、不烧 token），
    所以它也是"不依赖大模型就能完整验证一条链路"的最佳演示任务。
"""
from typing import List, Optional

from app_my.worker.base import NotifyTask
from app_my.worker.celery_app import celery_app


@celery_app.task(
    base=NotifyTask,
    name="tasks.generate_nutrition_report",
    bind=True,
    max_retries=0,
)
def generate_nutrition_report(
    self,
    ingredients: Optional[List[str]] = None,
    tenant_id: int = 0,
    user_id: int = 0,
) -> dict:
    """
    生成营养报告。

    参数：
        ingredients  食材列表，如 ["鸡胸肉 200克", "西兰花 1颗"]（名字后带用量，工具才换算得出克数）
        tenant_id / user_id：通知路由用

    返回：{"ingredients", "total_estimated", "coverage", "unmatched", "summary", "seconds"}
    """
    import time

    from app_my.tools.nutrition_tool import calculate_nutrition

    t0 = time.perf_counter()

    items = [str(x).strip() for x in (ingredients or []) if str(x).strip()]
    if not items:
        raise ValueError("ingredients 不能为空")   # 参数不合法 → 直接失败，让前端看到明确错误

    result = calculate_nutrition.invoke({"ingredients": items})   # LangChain 工具同步调用
    est = result.get("total_estimated", {}) or {}

    summary = (
        f"估算本餐总热量 {est.get('calories', 0)} 千卡；"
        f"蛋白 {est.get('protein', 0)}g / 脂肪 {est.get('fat', 0)}g / 碳水 {est.get('carbs', 0)}g；"
        f"匹配率 {float(result.get('coverage', 0)):.0%}"
    )

    return {
        "ingredients": items,
        "total_estimated": est,
        "coverage": result.get("coverage", 0),
        "unmatched": result.get("unmatched", []),
        "summary": summary,
        "seconds": round(time.perf_counter() - t0, 2),
    }