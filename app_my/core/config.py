# app_my/core/config.py
"""
AI 私厨 v2.0 - 全局配置中心
- 使用 pydantic-settings 自动加载 .env
- 通过 @lru_cache() 保证全局唯一实例
- 所有环境变量集中管理；业务模块必须从这里读，不允许散落 os.getenv
"""
from functools import lru_cache
import os
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """统一配置入口"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ============================================================
    # 基础服务
    # ============================================================
    APP_NAME: str = "AI私厨企业版"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False)
    HOST: str = "0.0.0.0"
    PORT: int = 8002                       # 阶段 0 已修正：项目实际端口就是 8002

    # ============================================================
    # 安全
    # ============================================================
    JWT_SECRET: str = Field(default="change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天
    JWT_ACCESS_EXPIRE_MINUTES: int = 30          #  阶段4 新增：access token 短命（泄露损失小）
    JWT_REFRESH_EXPIRE_MINUTES: int = 60 * 24 * 7  #  阶段4 新增：refresh token 长命 7 天
    BCRYPT_ROUNDS: int = 12

    # ============================================================
    # 模型（阿里云百炼 DashScope，OpenAI 兼容协议）
    # ============================================================
    # 修订：原版 DASHSCOPE_API_KEY: str 没有默认值，本地无 key 直接挂；
    #       改为默认空串，让 settings 在导入时不报错；真正的校验放在调用前的 guard 里。
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    CHAT_MODEL: str = "qwen3.7-flash"  # 抽到 settings，agents 不再写死
    VISION_MODEL: str = "qwen3.8-omni-flash-realtime"  # 阶段3 新增：识别节点看图用的多模态模型
    EMBEDDING_MODEL: str = "qwen3.7-text-embedding"
    MODEL_LITE: str = "qwen3.7-flash"       #  v3阶段2 新增：轻量档（简单任务，成本优先）
    MODEL_STANDARD: str = "qwen3.7-plus"    #  v3阶段2 新增：标准档（复杂任务，质量优先）

    # ============================================================
    # 联网搜索（Tavily）
    # ============================================================
    # 修订：删除原版 TAVILY 字段，统一用 TAVILY_API_KEY（避免 if settings.TAVILY 这种死代码）
    TAVILY_API_KEY: str = ""

    # ============================================================
    # 阿里云 OSS
    # 修订：键名统一为 ALIBABA_CLOUD_*，与 SDK 默认读取、oss.py 一致
    # ============================================================
    ALIBABA_CLOUD_ACCESS_KEY_ID: str = ""
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET: str = ""
    OSS_ENDPOINT: str = "oss-cn-beijing.aliyuncs.com"

    # ============================================================
    # 数据库
    # 本地默认 SQLite；生产切到 PostgreSQL（psycopg2 同步路径）
    # ============================================================
    DATABASE_URL: str = "sqlite:///./db/personal_chief.db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    DATABASE_READ_URL: str = ""            # v3阶段5 新增：读库连接串；空 = 与 DATABASE_URL 同库（暂无只读从库）
    CACHE_ENABLED: bool = True             # v3阶段5 新增：缓存总开关（排障时一键关闭）
    CACHE_L1_MAXSIZE: int = 512            # v3阶段5 新增：L1 进程内缓存最多存 512 个条目

    # ============================================================
    # Redis
    # ============================================================
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_PER_MINUTE: int = 60            # 全局/IP 级
    RATE_LIMIT_USER_PER_MINUTE: int = 20       # 用户级

        # ============================================================
    # Neo4j 知识图谱（v3阶段3 新增；默认值与 docker-compose 里的容器一致）
    # ============================================================
    NEO4J_URI: str = "bolt://localhost:7687"   # Bolt 协议端口（查询用）
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "ai_chief_kg"

        # ============================================================
    # Milvus 向量库（v3阶段6 新增；默认值与 docker-compose 里的容器一致）
    # ============================================================
    MILVUS_URI: str = "http://localhost:19530"     # gRPC over HTTP 端口
    MILVUS_COLLECTION: str = "recipes_v2"          # 集合名（v2 区别于 PGVector 的 recipes）

    # ============================================================
    # LangSmith（可选）
    # ============================================================
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_TRACING: bool = False
    LANGSMITH_PROJECT: str = "ai-sichu-v2"     # 修订：原 lc-course 是示例名

        # =========================================================
    # 可观测栈（v3 阶段 7 新增）
    # =========================================================
    PROMETHEUS_METRICS_PATH: str = "/metrics"      # 后端暴露的指标路径
    PROMETHEUS_MULTIPROC_DIR: str = ""            # 多进程模式预留（gunicorn -w > 1 时用）
    LOKI_URL: str = "http://localhost:3100"        # Loki 入口（前端调试查日志用）


        # ============================================================
    # 异步任务 + 实时推送（v3 阶段 8 新增）
    # ============================================================
    # Celery broker / result backend：复用阶段 1 起的 Redis 6380，只换 db 编号隔离
    #   现有业务（缓存 / 限流 / 配额 / JWT 黑名单）用 db 0；
    #   broker 用 db 1、result backend 用 db 2 —— 三个 db 互不撞键
    CELERY_BROKER_URL: str = "redis://localhost:6380/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6380/2"
    CELERY_TASK_ALWAYS_EAGER: bool = False        # True = 不进 worker，调用即本地同步执行（单测用）
    CELERY_TASK_RESULT_EXPIRES: int = 3600        # 任务结果在 Redis 里保留 1 小时，过期自动清
    WORKER_METRICS_PORT: int = 9101               # Celery worker 自己的指标端口（Prometheus 抓这里）
    WS_NOTIFY_CHANNEL: str = "ai_chief:ws:notify"  # 任务事件走这个 Redis 频道（worker 发、WS 网关收）

    
    # ============================================================
    # 性能压测（v3 阶段 10 新增）
    # ============================================================
    # MOCK_LLM：压测时把大模型调用换成固定响应的假模型（详见 app_my/core/mock_llm.py）。
    #   默认 false = 走真实 DashScope 调用，正常开发 / 跑单测完全不受影响。
    #   压测时用环境变量临时打开即可，不必改 .env（避免忘记改回来）。
    MOCK_LLM: bool = False
    # 压测目标名，只用于日志/报告标注，不影响业务（真正打哪个地址由 locust --host 决定）
    BENCH_TARGET_NAME: str = "monolith"      # monolith=单体 9002；gateway=经 Kong 网关 9100


    # ============================================================
    # CORS
    # ============================================================
    CORS_ORIGINS: List[str] = [
        "http://localhost:8001",
        "http://127.0.0.1:8002",   # 本项目实际端口
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "null",                    # 修订：file:// 双击打开页面需要
    ]

    @field_validator("JWT_SECRET")
    @classmethod
    def _refuse_default_secret_in_prod(cls, v: str) -> str:
        """非 DEBUG 模式下拒绝使用默认 JWT_SECRET"""
        debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        if v == "change-me-in-production" and not debug:
            raise ValueError(
                "JWT_SECRET 仍为默认值 'change-me-in-production'。"
                "请在 .env 中设置强随机密钥（生成方式：`openssl rand -hex 32`）。"
                "或临时将 DEBUG=true 以便调试，但禁止部署时使用。"
            )
        return v


@lru_cache()
def get_settings() -> Settings:
    """全局唯一配置实例"""
    return Settings()


# 全局快捷访问：from app_my.core.config import settings
settings = get_settings()