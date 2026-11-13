# app_my/db/routing.py —— 阶段 5（v3.0）：读写分离会话
"""
读写分离路由：SELECT 走"读引擎"，INSERT/UPDATE/DELETE 与 commit 冲刷走"写引擎"。

为什么现在就做（明明只有一个 PG 实例）：
- 代码先就位，将来加只读从库时只改 .env 里的 DATABASE_READ_URL，业务代码零改动；
- 读/写两个连接池参数可以分开调（读池大、写池小），为 PgBouncer 治理连接打配合。
"""
from sqlalchemy import Delete, Insert, TextClause, Update
from sqlalchemy.orm import Session

# 裸 text() 写出来的 SQL 没有语句类型可判断，只能按首关键词识别写操作
_WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE")


class RoutingSession(Session):
    """按"语句类型"分流目标引擎的会话类"""

    def get_bind(self, mapper=None, clause=None, **kw):
        # 惰性 import 避免 session.py 与 routing.py 循环依赖
        from app_my.db.session import read_engine, write_engine

        if self._flushing:                            # flush/commit 期间一律走写库
            return write_engine
        if clause is not None and isinstance(clause, (Insert, Update, Delete)):
            return write_engine                      # 结构化写语句（还没 flush 也能识别）
        if clause is not None and isinstance(clause, TextClause):
            head = clause.text.lstrip().upper()      # 裸 SQL：看第一个单词是不是写动词
            if head.startswith(_WRITE_PREFIXES):
                return write_engine
        return read_engine                           # 其余（SELECT / text 查询）走读库