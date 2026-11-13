# app_my/middleware/rate_limit.py
"""
阶段 4 中间件③④：双层限流（Redis 固定窗口计数）。

两个类共用一套逻辑，只差"按谁数"：
- UserRateLimitMiddleware：按登录用户数（匿名请求按 IP 数），默认 20 次/分钟
- RateLimitMiddleware  ：按客户端 IP 数，默认 60 次/分钟

关键设计：
1. 取 IP 用 X-Forwarded-For 首段（修订版 M4：Nginx 反代后 request.client.host
   永远是 127.0.0.1，按它限流等于全网共用一个名额，直接失效）
2. 固定窗口：键里带分钟数（rl:user:7:1700000123），INCR 一次 +1；
   超过配额返回 429 并带 Retry-After
3. Redis 挂了就放行（fail-open）：限流是保护措施，不能反过来把主服务打死；
   每次失败记一条 warning 日志
"""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.core.redis_client import get_redis


def _client_ip(request: Request) -> str:
    """
    拿"真实客户端 IP"。
    X-Forwarded-For 形如 "1.2.3.4, 10.0.0.1"——第一段是最原始的客户端 IP，
    后面是途经的各层代理；没有这个头（本地直连）就回退 request.client.host。
    """
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class _BaseRateLimitMiddleware(BaseHTTPMiddleware):
    """
    限流基类：子类只声明 scope（按谁数）和 limit（数多少）。
    放成基类是为了两个限流器不复制粘贴同一份 INCR/429 逻辑。
    """

    scope: str = "ip"          # "ip" 或 "user"
    limit: int = 60            # 每分钟配额

    def _make_key(self, request: Request) -> str:
        """限流键：rl:<scope>:<身份>:<当前分钟序号>，跨分钟自动换键=自动清零"""
        minute = int(time.time() // 60)
        if self.scope == "user":
            identity = getattr(request.state, "user_id", None) or _client_ip(request)
        else:
            identity = _client_ip(request)
        return f"rl:{self.scope}:{identity}:{minute}"

    async def dispatch(self, request: Request, call_next):
        key = self._make_key(request)
        try:
            client = get_redis()
            current = client.incr(key)          # 原子 +1，返回加完的值
            if current == 1:                    # 这个窗口的第一笔：设置过期
                client.expire(key, 61)          # 61 秒兜底，防止键漏删常驻内存
            if current > self.limit:
                logger.warning("限流触发 key=%s 当前=%d 配额=%d", key, current, self.limit)
                response: Response = JSONResponse(
                    {"detail": f"请求太频繁（限 {self.limit} 次/分钟），请稍后再试"},
                    status_code=429,
                )
                response.headers["Retry-After"] = "60"  # 告诉客户端多久后再试
                return response
        except Exception as exc:
            # fail-open：Redis 故障时放行并记日志，别让缓存打死主服务
            logger.warning("限流跳过（Redis 不可用）: %s %s", type(exc).__name__, exc)
        return await call_next(request)


class UserRateLimitMiddleware(_BaseRateLimitMiddleware):
    """用户级限流（在 Auth 之后，所以能读到 request.state.user_id）"""

    scope = "user"

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        self.limit = requests_per_minute or settings.RATE_LIMIT_USER_PER_MINUTE


class RateLimitMiddleware(_BaseRateLimitMiddleware):
    """全局/IP 级限流"""

    scope = "ip"

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        self.limit = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE