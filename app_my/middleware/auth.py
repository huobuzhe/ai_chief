# app_my/middleware/auth.py
"""
阶段 4 中间件②：AuthMiddleware（JWT 鉴权）。

职责很单一：受保护接口必须有合法 access token，通过后把 user_id 挂到 request.state，
后面的接口/限流中间件直接读，不用再解一遍 token。

放行名单（白名单）：
- / 、/health、/docs、/redoc、/openapi.json：首页/探针/接口文档，不能拦
- /auth/*：注册登录本身就是要匿名访问的——但 /auth/logout 例外，它需要 token 才有意义
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app_my.core.security import TOKEN_TYPE_ACCESS, decode_token, is_revoked

# 完全放行的路径
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}
# 前缀放行（注意 logout 被单独排除）
PUBLIC_PREFIXES = ("/auth/",)
# 放行前缀里需要鉴权的例外
PROTECTED_EXCEPTIONS = {"/auth/logout"}


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT 鉴权中间件"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 白名单：直接放行，不碰 token
        if path in PUBLIC_PATHS or (
            path.startswith(PUBLIC_PREFIXES) and path not in PROTECTED_EXCEPTIONS
        ):
            return await call_next(request)

        # 1. 取 Authorization: Bearer <token>
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"detail": "未认证：请携带 Authorization: Bearer <access_token>"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = auth_header[len("Bearer "):]

        # 2. 验签 + 验过期（decode_token 内部吞掉所有异常，失败就是 None）
        payload = decode_token(token)
        if payload is None:
            return JSONResponse(
                {"detail": "token 无效或已过期，请重新登录"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. 必须是 access token（refresh token 只能去 /auth/refresh 换新，不能直接访问接口）
        if payload.get("type") != TOKEN_TYPE_ACCESS:
            return JSONResponse(
                {"detail": "请使用 access token 访问接口（refresh token 只用于续签）"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 4. 黑名单：登出/换新过的 token 立刻作废
        if is_revoked(payload):
            return JSONResponse(
                {"detail": "token 已被撤销，请重新登录"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

                # 5. 通过：把身份挂到 request.state，后面随便用
        try:
            request.state.user_id = int(payload["sub"])
        except (KeyError, ValueError):
            return JSONResponse({"detail": "token 内容异常"}, status_code=401)
        request.state.token_payload = payload  # logout 要用 jti 撤销

        # 新增（v3阶段4）：把 token 里的 tenant 字段也透传出来
        # TenantContextMiddleware 会基于这些字段组装 TenantContext
        # 这里只做"读取 + 防御式兜底"，真正的组装在下一层

        return await call_next(request)