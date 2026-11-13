# app_my/middleware/tenant.py
"""
TenantContextMiddleware：在 AuthMiddleware 之后跑，从 token payload 拿出 default_tenant_id
组装成 TenantContext 挂到 request.state.tenant。

为什么放 Auth 之后：Auth 已经把 token 解出来放到 request.state.token_payload；
这里直接读 payload['tenant_id']，省一次 JWT 解码。

失败策略：token 里没有 tenant_id（老 token 或管理员专用 token）就放行 None，
由 API 层决定要不要拒绝——中间件太严格会堵死 /auth/refresh。
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app_my.core.tenant import TenantContext


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        payload = getattr(request.state, "token_payload", None)
        tenant_id = None
        role = "member"
        plan = "free"

        if payload is not None:
            tid = payload.get("tenant_id")
            if isinstance(tid, int):
                tenant_id = tid
            role = payload.get("tenant_role", "owner")  # 默认 owner 是为了兼容老 token（个人租户就是 owner）
            plan = payload.get("tenant_plan", "free")

        user_id = getattr(request.state, "user_id", None)
        request.state.tenant_id = tenant_id
        request.state.tenant_role = role
        request.state.tenant_plan = plan
        request.state.tenant = (
            TenantContext(tenant_id=tenant_id, user_id=user_id or 0, role=role, plan=plan)
            if tenant_id is not None and user_id is not None
            else None
        )

        return await call_next(request)