# tests/unit/test_routing.py —— 阶段 5：读写分离路由单测（4 个）
"""
覆盖点：
- SELECT 路由到读引擎（读库无表 → 报错证明打的是读库）
- INSERT + commit 路由到写引擎
- 裸 text() 的 INSERT 也路由到写引擎（TextClause 坑的回归测试）
- 读引擎 = 写引擎（未配 DATABASE_READ_URL）时行为如常

做法：用两个 sqlite 文件冒充"写库/读库"，把 session 模块的两个引擎
monkeypatch 成它们——RoutingSession.get_bind 每次调用时才取模块属性，替得动。
"""
import pytest
from sqlalchemy import create_engine, text

import app_my.db.session as session_mod
from app_my.db.routing import RoutingSession


@pytest.fixture()
def engines(tmp_path, monkeypatch):
    """两个不同 sqlite 文件 = 写库/读库分离"""
    w = create_engine(f"sqlite:///{tmp_path}/w.db")
    r = create_engine(f"sqlite:///{tmp_path}/r.db")


    monkeypatch.setattr(session_mod, "write_engine", w)
    monkeypatch.setattr(session_mod, "read_engine", r)

    # ========= 原有：只在写库建表，读库r保持空库 =========
    with w.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
    yield w, r
    w.dispose()
    r.dispose()


def test_select_routes_to_read(engines):
    _, r = engines
    db = session_mod.SessionLocal()
    with pytest.raises(Exception):              # 读库没有 t 表 → 报错 = 打到了读库
        db.execute(text("SELECT * FROM t")).fetchall()
    db.close()


def test_insert_routes_to_write(engines):
    w, r = engines
    db = session_mod.SessionLocal()
    db.execute(text("INSERT INTO t (id, name) VALUES (1, 'x')"))
    db.commit()
    db.close()
    with w.connect() as c:
        assert c.execute(text("SELECT count(*) FROM t")).scalar() == 1   # 进了写库
    # =========【改动：读库没有表，不能直接查询，改用pytest.raises捕获异常】=========
    with pytest.raises(Exception):
    
        with r.connect() as c:
            assert c.execute(text("SELECT count(*) FROM t")).scalar() == 0   # 读库没有


def test_text_clause_write_prefix(engines):
    """裸 text() 的 INSERT 必须走写库（TextClause 无类型信息的坑）"""
    w, _ = engines
    db = session_mod.SessionLocal()
    db.execute(text("INSERT INTO t (id, name) VALUES (2, 'y')"))
    db.commit()
    db.close()
    with w.connect() as c:
        assert c.execute(text("SELECT count(*) FROM t")).scalar() == 1

# =====================【修改：参数从 engines → same_engine】=====================
def test_same_engine_fallback(same_engine):
    """读引擎 = 写引擎（同库）时：查得到自己写的数据"""
    
    db = session_mod.SessionLocal()
    db.execute(text("INSERT INTO t (id, name) VALUES (3, 'z')"))
    db.commit()
    rows = db.execute(text("SELECT * FROM t")).fetchall()
    db.close()
    assert len(rows) == 1

# =====================【新增fixture：专门用于读写同引擎场景】=====================
@pytest.fixture()
def same_engine(tmp_path, monkeypatch):
    """单库：read_engine = write_engine 同一个sqlite库"""
    w = create_engine(f"sqlite:///{tmp_path}/same.db")
    monkeypatch.setattr(session_mod, "write_engine", w)
    monkeypatch.setattr(session_mod, "read_engine", w) # 读写共用同一个引擎
    with w.begin() as conn:
        conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)"))
    yield w
    w.dispose()

