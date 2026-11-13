# services/common/__init__.py
"""
services.common —— 四个微服务共享的"内核三件套"

    breaker.py      熔断器（连续失败就跳闸，快速失败，防雪崩）
    client.py       服务间调用客户端（httpx + 重试 + 熔断 + 上下文透传）
    app_factory.py  服务装配工厂（统一的中间件顺序 + /health + /metrics）
    context.py      contextvars 小仓库（跨函数传递 token，不改函数签名）
"""
