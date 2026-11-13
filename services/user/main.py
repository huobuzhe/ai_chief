# services/user/main.py
"""
user 服务（端口 9121）—— 管"人"和"组织"的一切

职责边界（为什么这些路由放一起）：
    认证（auth）、用户资料（user）、租户（tenant）、管理端（admin）、成本统计（billing）
    这五组路由的共同点是：**它们只碰 PostgreSQL 和 Redis，不碰大模型**。
    这是拆分的第一条依据——资源画像相同的功能放一起，扩容时可以单独加机器，
    不用为了给"对话"扩容而连带把"登录"也复制一份。

它不做什么：不调大模型、不碰 Milvus、不碰 Neo4j。
"""
from services.common.app_factory import create_service_app

# 复用单体时代已经写好的路由模块：拆分是"换入口"，不是"重写业务"
from app_my.api import auth, user, cache
from app_my.api import tenant as tenant_api
from app_my.api import admin as admin_api
from app_my.api import billing

app = create_service_app(
    "user",
    routers=[
        (auth.router, "/auth", ["认证"]),
        (user.router, "/users", ["用户"]),
        (tenant_api.router, "/tenants", ["租户管理"]),
        (admin_api.router, "/admin", ["管理端"]),
        (billing.router, "/billing", ["成本统计"]),
        (cache.router, "/cache", ["缓存观测"]),
    ],
    enable_auth=True,      # 有自己的 JWT 鉴权（Kong 不鉴权，鉴权下沉在各自服务）
    enable_quota=False,    # 配额只管 /chat/stream，那是 chat 服务的事
    capture_auth=False,    # user 服务不往下调别的服务，不用透传 token
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.user.main:app", host="0.0.0.0", port=9121, reload=False)
