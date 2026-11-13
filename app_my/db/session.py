# app_my/db/session.py
"""
数据库引擎与会话工厂（阶段 5 升级版）。
- write_engine / read_engine：写/读两个引擎（当前同一实例；将来从库只改 .env）
- engine：兼容旧名字（vector_store / init_db 继续用它），指向写引擎
- SessionLocal：改用 RoutingSession——SELECT 自动走读引擎
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app_my.core.config import settings
from app_my.db.routing import RoutingSession

# 连接池参数只对 PostgreSQL 有意义；万一用默认 SQLite 跑（本地无 PG），
# 传 pool_size 会直接 TypeError，所以按 URL 前缀条件加
_write_kwargs: dict = {"pool_pre_ping": True}  # 每次取连接前先 ping，断线自动重连
if settings.DATABASE_URL.startswith("postgres"):
    _write_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )

write_engine = create_engine(settings.DATABASE_URL, **_write_kwargs)   # 写库（经 PgBouncer）

_read_url = settings.DATABASE_READ_URL or settings.DATABASE_URL        # 没配读库 = 暂时同库
_read_kwargs: dict = {"pool_pre_ping": True}
if _read_url.startswith("postgres"):
    _read_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,          # 读池与写池同参数起步，压测后再分别调
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
read_engine = create_engine(_read_url, **_read_kwargs)                 # 读库

engine = write_engine   # 兼容旧代码：vector_store / init_db 继续用 "engine" 这个名字

# autoflush=False：不查库就取属性时别偷偷发 SQL（行为更可预期）
# expire_on_commit=False：commit 后对象属性还在内存里，接口还能读
# class_=RoutingSession：把"按语句类型分流引擎"的能力注入每个会话
SessionLocal = sessionmaker(
    class_=RoutingSession,
    autoflush=False,
    expire_on_commit=False,
)


def get_db():
    """FastAPI 依赖：请求进来自动开一个会话，请求结束自动关（还连接）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()





# # app_my/db/session.py
# """
# 数据库引擎与会话工厂。

# - engine：进程内唯一的"数据库连接池"，所有请求共用
# - SessionLocal：造"会话"（一次数据库对话）的工厂
# - get_db：FastAPI 依赖——每个请求借一个会话，用完自动还（yield + finally）
# """
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker

# from app_my.core.config import settings

# # 连接池参数只对 PostgreSQL 有意义；万一用默认 SQLite 跑（本地无 PG），
# # 传 pool_size 会直接 TypeError，所以按 URL 前缀条件加
# _engine_kwargs: dict = {"pool_pre_ping": True}  # 每次取连接前先 ping，断线自动重连
# if settings.DATABASE_URL.startswith("postgres"):
#     _engine_kwargs.update(
#         pool_size=settings.DB_POOL_SIZE,
#         max_overflow=settings.DB_MAX_OVERFLOW,
#     )

# engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

# # autoflush=False：不查库就取属性时别偷偷发 SQL（行为更可预期）
# # expire_on_commit=False：commit 后对象属性还在内存里，接口还能读
# SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# def get_db():
#     """FastAPI 依赖：请求进来自动开一个会话，请求结束自动关（还连接）"""
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()