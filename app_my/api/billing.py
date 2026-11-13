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
from fastapi import APIRouter, Request

from app_my.core.token_billing import get_billing_stats

router = APIRouter()


# @router.get("/stats")
# async def billing_stats():
#     """
#     Token 计费统计。

#     数据来源：每次模型调用结束时由 BillingCallbackHandler 自动记账，
#     进程重启不丢（Redis 持久累计）。
#     """
#     return get_billing_stats()
@router.get("/stats")
async def billing_stats(request: Request):
    """
    v3阶段4 起：按当前租户统计 token 消耗。
    租户上下文缺失时（管理员视角），返回全量（兼容老调用）。
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    return get_billing_stats(tenant_id=tenant_id)