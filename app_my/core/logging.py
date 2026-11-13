# app_my/core/logging.py
"""
JSON 日志（阶段 1 准备，阶段 6 升级）。
阶段 6 升级点：
- trace_id 存进 contextvars，formatter 自动附加
- 业务代码完全不用改：同一个请求里的所有日志天然带同一个号
- 保留阶段 1 的 extra_ 透传口子，向后兼容
"""
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone


# 请求级上下文变量：每个请求一份，异步并发互不串号
# default="-" 表示"不在请求里"的日志（比如启动日志）用 - 占位
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="-"
)


class JsonFormatter(logging.Formatter):
    """结构化 JSON 输出，方便 ELK/Loki 采集"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": trace_id_var.get(),   # 阶段 6：自动带当前请求的追踪号
        }
        # 透传 extra_ 前缀字段：logger.info("xxx", extra={"extra_user": "tom"})
        for k, v in record.__dict__.items():
            if k.startswith("extra_"):
                log_obj[k.replace("extra_", "")] = v
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    """初始化日志：把根 logger 替换成 JSON 输出到 stdout"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


# 模块级 logger，使用方式：from app_my.core.logging import logger
logger = logging.getLogger("ai_sichu")