# app_my/db/base.py
"""
SQLAlchemy 声明基类 + 建表入口。

- Base：所有 ORM 模型的公共父类，SQLAlchemy 靠它收集"一共有哪些表"
- init_db()：幂等建表（存在就跳过），在 main.py 的 lifespan 启动阶段调用一次
  项目还没引入 Alembic 迁移工具（阶段 7 之后再考虑），先用 create_all 顶住
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型继承它；本身不对应任何表"""


def init_db() -> None:
    """
    建表（幂等）。必须在 import 了模型之后再调 create_all：
    SQLAlchemy 只会为"已经 import 过、注册到 Base.metadata"的类建表，
    所以这里函数内 import models 把 User 先注册进来。
    """
    from app_my.db.session import engine  # 函数内导入，避免模块级循环依赖
    import app_my.db.models  # noqa: F401  触发模型注册

    Base.metadata.create_all(bind=engine)