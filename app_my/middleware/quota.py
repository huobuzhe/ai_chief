# app_my/middleware/quota.py
"""
QuotaMiddleware：对 chat_daily 做租户级配额检查。

为什么只挡 chat：token 消耗 / 成员上限走不同路径（token 在账单结算时记、成员上限在邀请时挡）。
中间件层只做最热的"对话次数/天"。

哪些路径走配额：/chat/stream；其他 / 的配额检查在 API 内做。

失败策略：Redis 挂 → 放行（fail-open），配额只是保护。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app_my.core.logging import logger
from app_my.core.quota import incr_usage, check_quota


QUOTA_PATHS = {"/chat/stream"}


class QuotaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in QUOTA_PATHS:
            tenant_id = getattr(request.state, "tenant_id", None)
            plan = getattr(request.state, "tenant_plan", "free")

            if tenant_id is not None:
                #ok, used, cap = check_quota(tenant_id, plan, "chat_daily")
                ok_quota, used, cap = check_quota(tenant_id, plan, "chat_daily")   #  阶段 7：原变量名 ok 改 ok_quota（不然遮住外层 ok=True）


                 # 阶段 7：上报当前租户配额使用率（用于告警；不影响配额逻辑）
                try:
                    from app_my.core.metrics import quota_set
                    if cap and cap > 0:
                        quota_set(tenant_id, used / cap)
                except Exception:
                    pass
                
                if not ok_quota:
                    logger.warning("配额超限 tenant=%s used=%d limit=%d", tenant_id, used, cap)
                    return JSONResponse(
                        {
                            "detail": "租户对话配额已用完",
                            "metric": "chat_daily",
                            "used": used,
                            "limit": cap,
                            "upgrade_hint": "升级到 pro / enterprise 可提高配额",
                        },
                        status_code=429,
                        headers={"Retry-After": "86400"},
                    )

        response: Response = await call_next(request)

        # 请求过了之后再 INCR（包括本请求），路径写在这里
        if request.url.path in QUOTA_PATHS:
            tenant_id = getattr(request.state, "tenant_id", None)
            if tenant_id is not None:
                incr_usage(tenant_id, "chat_daily", 1)

        return response