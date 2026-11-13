# app_my/core/audit.py
"""
审计日志工具：业务代码里显式调用 log_audit() 写入敏感操作。

为什么不放中间件：中间件只能拿到"哪个路由被调用"，拿不到"调用了哪个租户的资源 / 邀请了谁"。
把审计埋在 API 层，写在哪里就记哪里，参数可控。
"""
from typing import Optional

from sqlalchemy.orm import Session

from app_my.db.models.audit_log import AuditLog


def log_audit(
    db: Session,
    *,
    action: str,
    tenant_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """
    写一条审计日志。注意：调用方负责 commit，本函数只 add。
    """
    import json

    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_json=payload_json,
    )
    db.add(entry)