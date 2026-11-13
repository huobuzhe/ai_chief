# services/common/context.py
"""
跨服务调用的"上下文小仓库"—— 存放那些没法通过函数参数传递、但又必须带过去的东西

为什么单独一个文件：
    LangGraph 的节点函数签名被框架定死了：`async def node(state: dict) -> dict`。
    我们想在节点里发 HTTP 请求调用别的服务，就得带上用户的 JWT，
    但签名里塞不进去。contextvars 是 Python 官方为这种场景准备的方案：
    它在"协程上下文"里存值，await 链上任何深度都能读到，且不同请求之间互不干扰。

    类比：普通全局变量是"整栋楼共用一个白板"（并发时会串台）；
    contextvars 是"每个人手里一块自己的小白板"（各自独立，还能带进电梯）。
"""
from __future__ import annotations

import contextvars
from typing import Optional

# 上游请求带过来的原始 Authorization 头（形如 "Bearer eyJhbGci..."）
_upstream_token: contextvars.ContextVar[str] = contextvars.ContextVar(
    "upstream_token", default=""
)


def set_upstream_token(token: str) -> None:
    """在请求入口处把 token 存进来。"""
    _upstream_token.set(token or "")


def get_upstream_token() -> str:
    """在任意深度（包括 LangGraph 节点里）把 token 读出来。"""
    return _upstream_token.get() or ""


def auth_header() -> dict:
    """
    直接产出可以塞进 httpx 的请求头字典。
    没有 token 时返回空字典，避免发出一个值为空的 Authorization 头（对方会解析失败）。
    """
    token = get_upstream_token()
    return {"Authorization": token} if token else {}
