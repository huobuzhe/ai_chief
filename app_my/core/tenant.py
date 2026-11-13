# app_my/core/tenant.py
"""
租户上下文：JWT 解析后注入 request.state 的最小数据单元。

为什么用 dataclass：接口处可以 `tenant.context.owner_id` 自动补全，
可读性比裸 dict 高；又不重，Pydantic 那一套配置成本没必要。
"""
from dataclasses import dataclass
from typing import Optional

import contextvars

# v3阶段6：当前请求的租户 id（上下文变量）
# 为什么需要：检索工具 local_recipe_search 在 langgraph 节点深处执行，拿不到 request 对象，
# 靠这个变量把 /chat/stream 解析出的 tenant_id 一路带到工具里（灰度按租户判定要用）。
current_tenant_id: contextvars.ContextVar[int] = contextvars.ContextVar(
    "current_tenant_id", default=1
)

@dataclass
class TenantContext:
    tenant_id: int
    user_id: int
    role: str = "owner"   # owner / admin / member
    plan: str = "free"    # free / pro / enterprise

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"


def parse_role(role: str) -> str:
    """把字符串归一化到合法角色；非法值降级为 member（防御式）"""
    if role in (ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER):
        return role
    return ROLE_MEMBER