# app_my/core/tracing.py
"""
阶段 1 准备好 LangSmith 接入入口
- 调用 setup_langsmith() 后，LangChain 自动从环境变量读取配置
"""
import os
from app_my.core.config import settings


def setup_langsmith() -> None:
    """启动时调用一次即可；无 API key 时静默跳过"""
    if not settings.LANGSMITH_API_KEY:
        return
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.LANGSMITH_TRACING else "false"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT