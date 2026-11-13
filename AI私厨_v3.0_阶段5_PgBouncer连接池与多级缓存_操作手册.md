# AI 私厨 v3.0 阶段 5 操作手册 — PgBouncer 连接池 + Redis 多级缓存

> **阶段定位**：数据访问提效——连接池治理（PgBouncer）+ 读写分离路由 + 三级缓存（L1 进程内 / L2 Redis / L3 数据源），配套防击穿 / 防雪崩 / 防穿透三件套。对应原方案阶段 5 的「数据层升级」整段。
>
> **本手册性质**：照着做——步骤 / 命令 / 验证 / 排错一站到底。**代码为什么这么写**见配套《说明手册》，本手册不重复解释。
>
> 🔴 **前置硬条件：阶段 4 必须已收官**（多租户 SaaS 化代码已全部落盘、`feat/v3-stage4` 已合并 master、pytest 基线 62 passed）。本阶段多处代码建立在阶段 4 的 feature_flag / 租户中间件之上，跳过阶段 4 直接做本阶段必然报错。
>
> 🟡 本阶段**零新 Python 依赖**（cache 模块只用标准库 + 已有的 redis 包），**新增 1 个容器**（PgBouncer）。

---

## 目录

- [一、阶段目标](#一阶段目标)
- [二、简历叙事（照写）](#二简历叙事照写)
- [三、范围 & 与原方案差异（颜色标注）](#三范围--与原方案差异颜色标注)
- [四、端口与基础设施](#四端口与基础设施)
- [五、文件清单（创建 / 修改）](#五文件清单创建--修改)
- [六、准备（切分支、起服务、跑基线）](#六准备切分支起服务跑基线)
- [七、子模块 1：PgBouncer 容器（配置文件 + 编排）](#七子模块-1pgbouncer-容器配置文件--编排)
- [八、子模块 2：配置项（config.py + .env）](#八子模块-2配置项configpy--env)
- [九、子模块 3：读写分离路由（routing.py + session.py）](#九子模块-3读写分离路由routingpy--sessionpy)
- [十、子模块 4：多级缓存核心（core/cache.py）](#十子模块-4多级缓存核心corecachepy)
- [十一、子模块 5：缓存接入（retriever / kg API / 导入脚本失效钩子）](#十一子模块-5缓存接入retriever--kg-api--导入脚本失效钩子)
- [十二、子模块 6：缓存统计接口（api/cache.py + main.py）](#十二子模块-6缓存统计接口apicachepy--mainpy)
- [十三、子模块 7：单元测试（13 个新测试）](#十三子模块-7单元测试13-个新测试)
- [十四、子模块 8：验证脚本（verify_stage5.py + 提测脚本）](#十四子模块-8验证脚本verify_stage5py--提测脚本)
- [十五、子模块 9：压测对比（bench_cache.py，拿真实数字）](#十五子模块-9压测对比bench_cachepy拿真实数字)
- [十六、提交 Gitee 与 PR 描述](#十六提交-gitee-与-pr-描述)
- [十七、常见错误对照表](#十七常见错误对照表)
- [十八、避坑提示](#十八避坑提示)
- [十九、本阶段防呆自检清单](#十九本阶段防呆自检清单)

---

## 一、阶段目标

让"每一次数据访问"都变快、变稳、变省：

1. **连接池治理**：后端到 PostgreSQL 之间加一层 PgBouncer，应用端 100 个客户端连接复用 20 个数据库真实连接——数据库的连接不再被应用进程数绑架。
2. **读写分离就位**：`SELECT` 走读引擎、写操作走写引擎（当前同库，将来加只读从库只改 `.env` 一行）。
3. **三级缓存**：检索结果 L1（进程内，纳秒）→ L2（Redis，毫秒）→ L3（数据源，百毫秒到秒）逐级兜底；并发打同一个 key 只穿透一次。
4. **可量化的收益**：`/cache/stats` 接口 + 压测脚本给出**你自己机器上跑出来的**命中率与 QPS 提升数字。

**验收标准**（全做到才算收官）：

- 通过 9432 端口（PgBouncer）能正常完成登录、对话、检索全套流程；
- 并发 8 线程打同一个未缓存查询，数据源（embedding 调用 + PG 查询）只执行 1 次；
- `bench_cache.py` 输出"缓存关 vs 开"的 QPS 对比，差距显著；
- pytest 基线 62 → 75 passed（新增 13 个单测）。

---

## 二、简历叙事（照写）

> 在 AI 私厨 v3.0 中独立完成**数据层升级**：引入 **PgBouncer 连接中间层**治理数据库连接（transaction 池化模式，百级客户端连接复用 20 个服务端连接），并落地 **L1 进程内 LRU / L2 Redis / L3 数据源三级缓存**——以 **singleflight（同 key 并发只放一个线程穿透）**防击穿、**TTL ±10% 随机抖动**防雪崩、**空值短 TTL 缓存**防穿透；同时就位 **SQLAlchemy 读写分离路由**（SELECT 自动走读引擎），为水平扩展只读副本预留零改码切换点。缓存命中后检索接口 QPS 提升 **X 倍**（X 用自己压测数字填，阶段 10 汇总），命中率数据经 `/cache/stats` 接口可实时观测。

---

## 三、范围 & 与原方案差异（颜色标注）

| 项 | 原方案（v3.0 十阶段表） | 本阶段做法 | 标签 |
|---|---|---|---|
| PgBouncer 容器 | 阶段 5 数据层 | 同上：transaction 池化 + 宿主机 9432 端口 | 🟢新增 |
| 多级缓存 | 阶段 5 三级缓存 | L1 进程内 TTL-LRU + L2 Redis + L3 数据源 | 🟢新增 |
| singleflight 防击穿 | 阶段 5 提到 | **线程锁实现**（本项目检索调用在同步上下文，threading.Lock 比 asyncio.Lock 通用） | 🔵修改 |
| TTL 抖动防雪崩 | 阶段 5 提到 | ±10% 随机偏移，且**抖动下限 1 秒**（避免测试/极短 TTL 抖成 0） | 🟢新增 |
| 读写分离 | 阶段 5 为主从做准备 | **RoutingSession 按语句类型分流**；裸 `text()` 语句按 SQL 首关键词识别（实测发现 TextClause 无类型信息，必须补这条） | 🔵修改 |
| 缓存一致性 | 阶段 5 策略 | **主动失效**（导入脚本跑完清缓存）+ TTL 自然过期兜底；不做延迟双删（个人项目无高并发写场景，简单策略优先） | 🔵修改 |
| 压测验证 | 阶段 10 Locust | 本阶段先用轻量脚本拿"缓存前后 QPS"对比；全链路压测仍归阶段 10 | 🟣补充 |
| Celery 异步任务 | 原方案阶段 4 | **不包含**——本阶段纯数据层，无异步任务需求 | 🟡提醒 |

🟡 **提醒**：缓存只挂在**全局知识**（菜谱检索、图谱问答）上，这些数据所有租户共享，缓存天然安全。租户私有数据（账单、审计、成员表）**不缓存**——一旦按租户区分的 key 拼错就是数据串号，收益小风险大。

---

## 四、端口与基础设施

| 组件 | 端口 | 说明 |
|---|---|---|
| PgBouncer | **9432**（宿主机）→ 6432（容器） | 🟢 本阶段唯一新端口 |
| 后端 | 9002 | 沿用 |
| PostgreSQL | 5433 | 沿用（现在**只有 PgBouncer 连它**，应用改连 9432） |
| Redis | 6380 | 沿用（新增用途：L2 缓存层） |

> 🟢 已实测确认（2026-09-29）：9432 端口当前空闲。
> 🟡 内存增量：PgBouncer 容器约 10~20MB，忽略不计。

```
连接拓扑（本阶段之后）：

  FastAPI(9002) ──SQLAlchemy写引擎──┐
  FastAPI(9002) ──SQLAlchemy读引擎──┤
                                     ▼
                            PgBouncer(9432)  ← 100 个客户端连接进来，
                                     │            只维持 20 个真实数据库连接
                                     ▼
                          PostgreSQL(5433 容器内 5432)
```

---

## 五、文件清单（创建 / 修改）

### 🟢 新建（8 个）

```
docker/pgbouncer/pgbouncer.ini          PgBouncer 主配置（池化模式/连接数）
docker/pgbouncer/userlist.txt            PgBouncer 客户端账号密码表
app_my/db/routing.py                    读写分离会话类 RoutingSession
app_my/core/cache.py                    多级缓存核心（三件套防护）
app_my/api/cache.py                     /cache/stats 统计接口
scripts/verify_stage5.py                分步验证脚本
scripts/bench_cache.py                  压测对比脚本（拿真实 QPS 数字）
scripts/stage5_check.ps1 / .sh          提测脚本（双终端）
tests/unit/test_cache.py                缓存单测（9 个）
tests/unit/test_routing.py              路由单测（4 个）
```

### 🔵 修改（6 个）

```
docker/docker-compose.v3.yml            增加 pgbouncer 服务
app_my/core/config.py                   新增 4 个配置项
.env                                    DATABASE_URL 端口 5433→9432 + 新配置
app_my/db/session.py                    双引擎 + RoutingSession（整文件替换）
app_my/knowledge/retriever.py           BM25 索引进程内复用 + hybrid_search 挂缓存
app_my/api/kg.py                        ask/stats 挂缓存（API 层）
app_my/main.py                          注册 cache 路由（2 行）
scripts/import_recipes.py               导入完成后主动失效缓存（3 行）
```

> 🟡 `app_my/db/base.py` **不用改**：它 `from app_my.db.session import engine`，新 session.py 里保留了 `engine = write_engine` 这个兼容别名。

---

## 六、准备（切分支、起服务、跑基线）

**操作 1：确认阶段 4 已合并、工作区干净**

```bash
cd F:/pycharm_aiprogram/ai_chief
git branch --show-current        # 应显示 master
git log --oneline -3             # 最新一条应是 feat(v3-stage4) 的合并结果
git status                       # 应无未提交变更（手册 md 除外）
```

**验证**：三条都符合。任何一条不符 → 先回去完成阶段 4 收官，不要跳阶段。

**操作 2：切新分支**

```bash
git checkout -b feat/v3-stage5
```

**操作 3：起基础设施容器**

```bash
docker compose -f docker/docker-compose.v3.yml up -d
docker compose -f docker/docker-compose.v3.yml ps
```

**验证**：pgvector / redis / neo4j 三个容器都是 `Up (healthy)`。

**操作 4：跑基线测试**

```bash
uv run pytest -q
```

**验证**：`62 passed`（阶段 4 收官后的基线）。数字不对先排阶段 4 的问题。

---

## 七、子模块 1：PgBouncer 容器（配置文件 + 编排）

### 7.1 创建 `docker/pgbouncer/pgbouncer.ini`

```ini
; PgBouncer 主配置——"数据库连接的收发室"
; 两个段：[databases] 告诉它后端真库在哪；[pgbouncer] 是它自己的行为规则
[databases]
;                 连接串里写 "ai_sichu" 时，实际转发给 pgvector 容器的 5432
ai_sichu = host=pgvector port=5432 dbname=ai_sichu user=ai_sichu password=ai_sichu

[pgbouncer]
listen_addr = 0.0.0.0          ; 监听所有网卡（容器里必须 0.0.0.0，宿主机才能连）
listen_port = 6432             ; 容器内端口（宿主机映射成 9432）

auth_type = plain              ; 明文密码校验（账号密码写 userlist.txt）
auth_file = /etc/pgbouncer/userlist.txt

pool_mode = transaction        ; 池化粒度：事务级（一个真实连接按"事务"借还）
max_client_conn = 100          ; 最多接 100 个客户端连接（应用侧不用抢）
default_pool_size = 20         ; 每个数据库维持 20 个真实连接
reserve_pool_size = 5          ; 高峰时最多再加 5 个应急连接
reserve_pool_timeout = 3       ; 排队超过 3 秒才启用应急池

server_reset_query = DISCARD ALL   ; 归还连接前清掉会话级残留状态（事务池化必配）
ignore_startup_parameters = extra_float_digits

admin_users = ai_sichu         ; 允许这个账号连 "pgbouncer" 库执行 SHOW POOLS 看池子状态

logfile = /dev/stdout          ; 日志打到容器标准输出（docker logs 直接看）
```

### 7.2 创建 `docker/pgbouncer/userlist.txt`

```text
"ai_sichu" "ai_sichu"
```

> 🟡 注意：这行是 `账号 密码` 两段，各自带双引号，中间一个空格。本地开发密码就是 ai_sichu（沿用现有 PG 容器的账密），不涉及生产密钥。

### 7.3 修改 `docker/docker-compose.v3.yml`

在 `neo4j:` 服务块**后面**、`volumes:` 顶级声明**前面**，加入：

```yaml
  pgbouncer:
    image: docker.m.daocloud.io/edoburu/pgbouncer:1.24.1   # DaoCloud 源（轻量、支持挂载自定义配置）
    container_name: ai_chief_pgbouncer                     # 沿用 ai_chief_* 命名前缀
    restart: unless-stopped
    depends_on:
      pgvector:
        condition: service_healthy                          # 等 PG 健康检查过了再起
    ports:
      - "9432:6432"                                         # 宿主机 9432 -> 容器内 6432
    volumes:
      - ./pgbouncer/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro   # 挂载配置（ro=只读）
      - ./pgbouncer/userlist.txt:/etc/pgbouncer/userlist.txt:ro     # 挂载账号表
```

### 7.4 启动并验证

```bash
docker compose -f docker/docker-compose.v3.yml up -d pgbouncer
docker logs ai_chief_pgbouncer --tail 20
```

**验证 1**：日志里出现 `listening on 0.0.0.0:6432` 字样、无 ERROR。

**验证 2**：绕过应用直接用 Python 连 PgBouncer 查库（Git Bash）：

```bash
uv run python -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=9432, dbname='ai_sichu', user='ai_sichu', password='ai_sichu')
cur = conn.cursor()
cur.execute('SELECT count(*) FROM users')
print('通过 PgBouncer 查到 users 行数:', cur.fetchone()[0])
conn.close()
"
```

**验证 3**：看池子状态（`SHOW POOLS` 是 PgBouncer 的管理命令）：

```bash
uv run python -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=9432, dbname='pgbouncer', user='ai_sichu', password='ai_sichu')
cur = conn.cursor()
cur.execute('SHOW POOLS')
for row in cur.fetchall():
    print(row)
conn.close()
"
```

**验证**：输出表格里有 `ai_sichu` 一行，`cl_active`（活跃客户端连接）≥1，`sv_active`（活跃服务端连接）≥0——这行数据就是"连接复用"的直管证据。

🔴 若验证 2 报 `password authentication failed`：检查 userlist.txt 是否写成了单引号 / 漏了空格 / 没挂载成功（`docker exec ai_chief_pgbouncer cat /etc/pgbouncer/userlist.txt` 查看容器内实际内容）。

---

## 八、子模块 2：配置项（config.py + .env）

### 8.1 修改 `app_my/core/config.py`

在 `DB_POOL_SIZE / DB_MAX_OVERFLOW` 两行**后面**追加：

```python
    DATABASE_READ_URL: str = ""            # v3阶段5 新增：读库连接串；空 = 与 DATABASE_URL 同库（暂无只读从库）
    CACHE_ENABLED: bool = True             # v3阶段5 新增：缓存总开关（排障时一键关闭）
    CACHE_L1_MAXSIZE: int = 512            # v3阶段5 新增：L1 进程内缓存最多存 512 个条目
```

> 🟡 顺手把 `APP_VERSION` 改成 `"3.0.0"`（阶段 4 已改过就跳过）。

### 8.2 修改 `.env`

改一行、加三行：

```bash
# 改：数据库连接从"直连 5433"改为"经过 PgBouncer 9432"
DATABASE_URL=postgresql+psycopg2://ai_sichu:ai_sichu@localhost:9432/ai_sichu
# （保留旧值注释，排障时可切回直连）
# DATABASE_URL=postgresql+psycopg2://ai_sichu:ai_sichu@localhost:5433/ai_sichu

# 加：读库为空 = 与写库相同；将来加从库只改这一行
DATABASE_READ_URL=
# 加：缓存开关
CACHE_ENABLED=true
```

**验证**：

```bash
uv run python -c "
from app_my.core.config import settings
print('写库:', settings.DATABASE_URL)
print('读库:', settings.DATABASE_READ_URL or '(空，回落到写库)')
print('缓存开关:', settings.CACHE_ENABLED)
"
```

**验证**：写库 URL 端口是 9432。

---

## 九、子模块 3：读写分离路由（routing.py + session.py）

### 9.1 新建 `app_my/db/routing.py`

```python
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
```

### 9.2 整文件替换 `app_my/db/session.py`

```python
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
```

**验证**（重启后端前先做导入冒烟）：

```bash
uv run python -c "
from app_my.db.session import write_engine, read_engine, engine, SessionLocal
print('写引擎:', write_engine.url)
print('读引擎:', read_engine.url)
print('engine 别名 = 写引擎:', engine is write_engine)
from sqlalchemy import text
db = SessionLocal()
print('SELECT 1 ->', db.execute(text('SELECT 1')).scalar())
db.close()
"
```

**验证**：两个引擎 URL 都是 9432 端口；`SELECT 1` 返回 1（说明 RoutingSession 通过 PgBouncer 查询成功）。

> 🔴 重启后端（`uv run python main.py`），登录一次、发一次对话，`docker logs ai_chief_pgbouncer --tail 5` 应出现 `login` / `query` 日志——应用流量已切到 PgBouncer。

---

## 十、子模块 4：多级缓存核心（core/cache.py）

新建 `app_my/core/cache.py`（完整文件，直接落盘）：

```python
# app_my/core/cache.py —— 阶段 5（v3.0）：多级缓存
"""
多级缓存（L1 进程内 / L2 Redis / L3 数据源）+ 三件套防护：
- 防击穿 singleflight：并发打同一个 key，只有第一个线程穿透到数据源，其余等结果
- 防雪崩 TTL 抖动：每个 key 的过期时间加 ±10% 随机偏移，避免同批 key 同时失效
- 防穿透 空值短缓存：查到"确实没有"也缓存一小会儿，挡住恶意/重复的无效查询
"""
from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Dict, Optional

from app_my.core.config import settings
from app_my.core.logging import logger

_MISS = object()                 # "缓存里没有"的内部哨兵（不可能是业务值）
_NULL_MARK = "__CACHE_NULL__"    # L2 里存这个字符串 = "查过了，确实没有"
_JITTER = 0.10                   # TTL ±10% 抖动幅度

# ---------------------------------------------------------------- 全局状态（模块级单例）
_l1: Optional["_TTLCache"] = None
_l1_lock = threading.Lock()
_key_locks: Dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()
_l2_disabled = False             # L2（Redis）连续失败后置 True，本进程余生不再碰它

_stats_lock = threading.Lock()
_stats = {
    "l1_hits": 0,        # L1 命中次数（含命中空值）
    "l2_hits": 0,        # L2 命中次数（含命中空值）
    "null_hits": 0,      # 命中的是"空值占位"的次数
    "misses": 0,         # 穿透到数据源执行的次数
    "loader_errors": 0,  # 数据源抛异常次数（不缓存，直接向上抛）
    "invalidations": 0,  # 主动失效次数
}


def _bump(field: str) -> None:
    """线程安全地给统计字段 +1"""
    with _stats_lock:
        _stats[field] += 1


def cache_stats() -> Dict[str, Any]:
    """当前统计快照（/cache/stats 接口用）——数字全部来自真实运行"""
    with _stats_lock:
        snap = dict(_stats)
    hits = snap["l1_hits"] + snap["l2_hits"]
    total = hits + snap["misses"]
    snap["hit_rate"] = round(hits / total, 4) if total else 0.0
    snap["l1_size"] = len(_get_l1()._data)
    return snap


def cache_stats_reset() -> Dict[str, int]:
    """清零统计（压测前后各看一次，差值就是这一轮的真实命中）"""
    with _stats_lock:
        for k in _stats:
            _stats[k] = 0
    return dict(_stats)


# ---------------------------------------------------------------- L1：进程内 TTL 缓存
class _TTLCache:
    """线程安全的进程内 TTL 缓存（容量满时淘汰最久未访问的条目）"""

    def __init__(self, maxsize: int = 512):
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def get(self, key: str) -> Any:
        """取值；过期/不存在都返回 _MISS 哨兵（调用方只认这一个标记）"""
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return _MISS
            value, is_null, expire_at = item
            if expire_at <= time.monotonic():        # 惰性过期：取的时候才判断
                del self._data[key]
                return _MISS
            self._data.move_to_end(key)              # 刚访问过的挪到"最新"端
            return (value, is_null)

    def put(self, key: str, value: Any, is_null: bool, ttl: float) -> None:
        """存值；容量满时淘汰最旧端（LRU 语义）"""
        with self._lock:
            self._data[key] = (value, is_null, time.monotonic() + ttl)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)       # 淘汰"最久未访问"端

    def clear_prefix(self, prefix: str) -> int:
        """删掉所有以 prefix 开头的 key（主动失效用），返回删除数"""
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)


def _get_l1() -> _TTLCache:
    """L1 惰性单例：第一次用到才建（避免 import 时读 settings 的顺序问题）"""
    global _l1
    if _l1 is None:
        with _l1_lock:
            if _l1 is None:
                _l1 = _TTLCache(maxsize=settings.CACHE_L1_MAXSIZE)
    return _l1


# ---------------------------------------------------------------- L2：Redis（可选层）
def _l2_get(key: str) -> Any:
    """从 Redis 取；不可用返回 _MISS（缓存层永远不抛异常挡业务）"""
    global _l2_disabled
    if _l2_disabled:
        return _MISS
    try:
        from app_my.core.redis_client import get_redis
        raw = get_redis().get(key)
        if raw is None:
            return _MISS
        data = json.loads(raw)                       # {"n": 是否空值, "v": 值}
        return (data.get("v"), bool(data.get("n")))
    except Exception:
        _l2_disabled = True                          # 失败一次就降级：剩余请求全走 L1+数据源
        logger.warning("cache: L2(Redis) 不可用，本进程降级为 L1+数据源")
        return _MISS


def _l2_set(key: str, value: Any, is_null: bool, ttl: int) -> None:
    """写入 Redis；失败只记日志（写不进去不影响正确性，只影响命中率）"""
    global _l2_disabled
    if _l2_disabled:
        return
    try:
        from app_my.core.redis_client import get_redis
        payload = json.dumps({"n": is_null, "v": _NULL_MARK if is_null else value},
                             ensure_ascii=False, default=str)
        get_redis().setex(key, max(ttl, 1), payload)
    except Exception:
        _l2_disabled = True
        logger.warning("cache: L2(Redis) 写入失败，降级为 L1+数据源")


def _l2_del_prefix(prefix: str) -> None:
    """删除 Redis 里 prefix: 开头的全部 key（SCAN 游标遍历，不阻塞）"""
    global _l2_disabled
    if _l2_disabled:
        return
    try:
        from app_my.core.redis_client import get_redis
        client = get_redis()
        keys = list(client.scan_iter(match=f"{prefix}:*"))
        if keys:
            client.delete(*keys)
    except Exception:
        _l2_disabled = True


# ---------------------------------------------------------------- singleflight：同 key 只放一个线程进去
def _get_key_lock(key: str) -> threading.Lock:
    with _key_locks_guard:
        lock = _key_locks.get(key)
        if lock is None:
            if len(_key_locks) > 4096:               # 防 key 无限增长：满了就整体清一次
                _key_locks.clear()
            lock = threading.Lock()
            _key_locks[key] = lock
        return lock


# ---------------------------------------------------------------- 工具函数
def _make_key(prefix: str, fn: Callable, args: tuple, kwargs: dict) -> str:
    """prefix + 参数指纹 = 缓存 key。用哈希是因为参数里可能有长文本"""
    raw = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _jitter_ttl(ttl: float) -> float:
    """TTL 加 ±10% 随机抖动（防雪崩：同批写入的 key 不会同一秒集体失效）"""
    return max(1.0, ttl * (1 + random.uniform(-_JITTER, _JITTER)))


# ---------------------------------------------------------------- 装饰器：给函数整体加三级缓存
def cached(prefix: str, ttl: float = 300, null_ttl: float = 30):
    """
    用法：@cached(prefix="rag", ttl=300)
    前置约定：被装饰函数的返回值必须能 JSON 序列化（list/dict/str/数字）。
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not settings.CACHE_ENABLED:            # 总开关：一键关闭（排障时用）
                return fn(*args, **kwargs)
            key = _make_key(prefix, fn, args, kwargs)

            # ---- L1 快路径 ----
            hit = _get_l1().get(key)
            if hit is not _MISS:
                _bump("l1_hits")
                if hit[1]:
                    _bump("null_hits")
                return hit[0]

            # ---- L2 次快路径 ----
            l2_hit = _l2_get(key)
            if l2_hit is not _MISS:
                _get_l1().put(key, l2_hit[0], l2_hit[1], ttl)   # 回填 L1（下次就是纳秒级）
                _bump("l2_hits")
                if l2_hit[1]:
                    _bump("null_hits")
                return l2_hit[0]

            # ---- 慢路径：singleflight 包住数据源 ----
            with _get_key_lock(key):
                hit = _get_l1().get(key)              # double-check：排队时别人可能已加载完
                if hit is not _MISS:
                    _bump("l1_hits")
                    return hit[0]
                l2_hit = _l2_get(key)
                if l2_hit is not _MISS:
                    _get_l1().put(key, l2_hit[0], l2_hit[1], ttl)
                    _bump("l2_hits")
                    return l2_hit[0]

                _bump("misses")
                try:
                    value = fn(*args, **kwargs)       # 真正穿透到数据源/大模型
                except Exception:
                    _bump("loader_errors")            # 出错不缓存（下次还能重试）
                    raise
                is_null = value is None or value == [] or value == {}
                store_ttl = null_ttl if is_null else ttl
                _get_l1().put(key, value, is_null, _jitter_ttl(store_ttl))
                _l2_set(key, value, is_null, int(_jitter_ttl(store_ttl)))
                return value

        return wrapper
    return decorator


# ---------------------------------------------------------------- 主动失效
def invalidate_prefix(prefix: str) -> int:
    """删掉 L1+L2 里该前缀的全部缓存（数据变了主动让缓存失效）"""
    n = _get_l1().clear_prefix(prefix)
    _l2_del_prefix(prefix)
    _bump("invalidations")
    logger.info(f"cache: 已失效前缀 {prefix}（L1 清除 {n} 条）")
    return n
```

**验证**（缓存三件套逻辑冒烟）：

```bash
uv run python -c "
import sys; sys.path.insert(0, '.')
from app_my.core.cache import cached, cache_stats, cache_stats_reset

calls = {'n': 0}

@cached(prefix='smoke', ttl=60)
def slow_query(q):
    calls['n'] += 1
    return ['result:' + q]

slow_query('a')     # 第一次：miss，穿透
slow_query('a')     # 第二次：L1 命中
print('数据源执行次数 =', calls['n'], '（应为 1）')
print('统计 =', cache_stats())
assert calls['n'] == 1
print('SMOKE OK')
"
```

**验证**：`数据源执行次数 = 1`，统计里 `l1_hits=1, misses=1`。

---

## 十一、子模块 5：缓存接入（retriever / kg API / 导入脚本失效钩子）

> 🟡 接入原则（详细理由见说明手册）：**只缓存"全局知识"**——菜谱检索（rag 前缀）与图谱问答（kg 前缀）。租户私有数据一律不进缓存。

### 11.1 修改 `app_my/knowledge/retriever.py`（整文件替换）

```python
# app_my/knowledge/retriever.py
"""
混合检索（Hybrid Search）：
- 向量检索：懂语义（"减脂" 能联想到 "低卡、高蛋白"）
- BM25 检索：懂关键词（菜名、食材的精确命中）
- 两者按 alpha 加权融合，兼顾"懂意思"和"答得准"

v3 阶段 5 升级：
- BM25 索引进程内复用（lru_cache）——之前每次检索都重建一遍索引，纯浪费
- hybrid_search 挂多级缓存——同样的问题不再打 embedding 接口和数据库
"""
from functools import lru_cache
from typing import Dict, List

import jieba
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from app_my.core.cache import cached
from app_my.core.logging import logger
from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
from app_my.knowledge.vector_store import get_vector_store


@lru_cache(maxsize=4)                      # k 取值很少变，缓存几个规格就够
def _build_bm25(k: int) -> BM25Retriever:
    """用种子数据构建 BM25 索引，jieba 中文分词（建好一次进程内复用）"""
    recipes = load_recipes()
    docs = [
        Document(page_content=recipe_to_text(r), metadata=recipe_to_metadata(r))
        for r in recipes
    ]
    return BM25Retriever.from_documents(
        docs,
        k=k,
        preprocess_func=jieba.lcut,   # 🟢 中文分词：把"鸡胸肉减脂"切成 ["鸡胸","肉","减脂"]
    )


@cached(prefix="rag", ttl=300, null_ttl=30)   # 🟢 v3阶段5：三级缓存 + 三件套防护
def hybrid_search(query: str, k: int = 5, alpha: float = 0.7) -> List[Dict]:
    """
    混合检索：向量结果占 alpha 权重，BM25 占 (1-alpha)。

    参数：
        query : 用户的问题，如 "鸡胸肉 减脂"
        k     : 最终返回前 k 条
        alpha : 融合权重，0.7 = 向量 70% + 关键词 30%
    返回：
        [{"content": 原文, "metadata": 菜谱元数据, "score": 融合分}, ...]
    """
    store = get_vector_store()

    # --- 第 1 路：向量检索（PGVector 走标准接口；内存库走自定义接口）---
    if hasattr(store, "as_retriever"):
        retriever = store.as_retriever(search_kwargs={"k": k * 2})
        vector_hits = retriever.invoke(query)
    elif hasattr(store, "similarity_search"):
        vector_hits = store.similarity_search(query, k=k * 2)
    else:
        logger.error("Vector store 不支持任何已知检索接口")
        return []

    # --- 第 2 路：BM25 关键词检索 ---
    bm25 = _build_bm25(k * 2)
    bm25_hits = bm25.invoke(query)

    # --- 融合：倒数排名归一化（RRF 思路）---
    # 排名第 1 得 1.0 分，第 2 得 0.5 分，第 3 得 0.33 分……
    # 两路各按权重相加，同一道菜两路都命中会得高分
    def normalize(hits):
        return {h.page_content: 1.0 / (i + 1) for i, h in enumerate(hits)}

    vec_scores = normalize(vector_hits)
    bm_scores = normalize(bm25_hits)

    combined: Dict[str, float] = {}
    for content, s in vec_scores.items():
        combined[content] = alpha * s
    for content, s in bm_scores.items():
        combined[content] = combined.get(content, 0.0) + (1 - alpha) * s

    sorted_items = sorted(combined.items(), key=lambda x: -x[1])[:k]

    # --- 取回 metadata 组装结果 ---
    all_hits = list(vector_hits) + list(bm25_hits)
    result = []
    for content, score in sorted_items:
        for h in all_hits:
            if h.page_content == content:
                result.append(
                    {"content": content, "metadata": h.metadata, "score": round(score, 4)}
                )
                break
    return result
```

### 11.2 修改 `app_my/api/kg.py`（整文件替换）

```python
# app_my/api/kg.py
"""
阶段 3（v3.0）：知识图谱推理接口——回答"XX 病患者能不能吃 YY"

接口（受 JWT 鉴权保护，需要登录后带 access token 访问）：
    GET /kg/ask?ingredient=土豆&condition=糖尿病    多跳推理问答
    GET /kg/stats                                   图谱规模统计（排障/演示用）

v3 阶段 5 升级：问答与统计挂多级缓存。
- kg 知识是全局的（不随租户变），缓存安全；
- 缓存在 API 层挂（不挂在 core/kg.ask 上），避免单测里 mock 掉 Neo4j 后被旧缓存污染。
"""
from fastapi import APIRouter, Query

from app_my.core import kg as kg_module
from app_my.core.cache import cached

router = APIRouter()

# 模块级包装：图谱问答 10 分钟缓存（知识图谱几乎不变，可以缓存久一些）
_ask_cached = cached(prefix="kg", ttl=600, null_ttl=60)(kg_module.ask)
# 图谱规模统计 1 分钟缓存（演示/排障用，新鲜度要求低）
_stats_cached = cached(prefix="kgstats", ttl=60)(kg_module.kg_stats)


@router.get("/ask")
async def kg_ask(
    ingredient: str = Query(..., min_length=1, max_length=30, description="食材名，如：土豆"),
    condition: str = Query(..., min_length=1, max_length=30, description="健康状况名，如：糖尿病/痛风/高血压"),
):
    """
    图谱依据的多跳推理：结论 + 理由 + 营养证据 + 受影响菜谱。

    支持"高血糖"这类别名（图上 Condition 节点带 aka 别名列表）。
    图谱不可用时明确返回 graph_available=false（诚实告知，不冒充"没禁忌"）。
    """
    return _ask_cached(ingredient.strip(), condition.strip())


@router.get("/stats")
async def kg_stats():
    """图谱规模统计：四类节点/四类关系各多少个（演示和排障用）"""
    return _stats_cached()
```

### 11.3 修改 `scripts/import_recipes.py`（文件末尾加失效钩子）

在 `main()` 函数的**冒烟验证之后、`print` 结束之前**（即 `if __name__ == "__main__":` 之前），追加：

```python
    # v3阶段5：导入完成 = 数据变了，主动让 rag 缓存失效（下次检索重新加载）
    from app_my.core.cache import invalidate_prefix
    n = invalidate_prefix("rag")
    print(f"[缓存] 已失效 rag 前缀缓存（L1 清除 {n} 条），下次检索自动加载新数据")
```

> 🟡 这是"缓存一致性"的主动侧：数据变了→显式失效；万一忘了跑，TTL 300 秒也会自然过期兜底。

**验证**（缓存真的在工作）：

```bash
uv run python -c "
from app_my.core.cache import cache_stats_reset, cache_stats
from app_my.knowledge.retriever import hybrid_search
cache_stats_reset()
r1 = hybrid_search('鸡胸肉 减脂', k=3)   # 第一次：穿透（embedding + PG 查询）
r2 = hybrid_search('鸡胸肉 减脂', k=3)   # 第二次：缓存命中
print('两次结果一致:', r1 == r2)
print('统计:', cache_stats())
"
```

**验证**：`两次结果一致: True`；统计里 `misses=1`、`l1_hits=1`（或 `l2_hits=1`）。

---

## 十二、子模块 6：缓存统计接口（api/cache.py + main.py）

### 12.1 新建 `app_my/api/cache.py`

```python
# app_my/api/cache.py
"""
阶段 5（v3.0）：缓存运行时观测接口——命中率/穿透次数一眼可见。

接口（受 JWT 鉴权保护）：
    GET   /cache/stats    当前统计快照（含命中率）
    POST  /cache/reset    统计清零（压测前用）
    POST  /cache/invalidate/{prefix}   主动失效某前缀缓存（运维用）
"""
from fastapi import APIRouter

from app_my.core.cache import cache_stats, cache_stats_reset, invalidate_prefix

router = APIRouter()


@router.get("/stats")
async def stats():
    """缓存统计快照：命中/穿透/空值/失效/命中率——全部真实运行数字"""
    return cache_stats()


@router.post("/reset")
async def reset():
    """清零统计计数（不动缓存数据，只清计数）"""
    return {"reset": cache_stats_reset()}


@router.post("/invalidate/{prefix}")
async def invalidate(prefix: str):
    """主动失效：prefix 目前有 rag / kg / kgstats 三种"""
    return {"prefix": prefix, "l1_cleared": invalidate_prefix(prefix)}
```

### 12.2 修改 `app_my/main.py`（2 处）

路由导入行改为：

```python
from app_my.api import oss, chat, auth, user, billing, kg, cache   # cache 为 v3阶段5 新增
```

路由注册区追加一行（放在 kg 那行后面）：

```python
app.include_router(cache.router, prefix="/cache", tags=["缓存观测(v3阶段5)"])   # v3阶段5 新增
```

**验证**：重启后端，登录拿 token 后：

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:9002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"你的账号","password":"你的密码"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s http://127.0.0.1:9002/cache/stats -H "Authorization: Bearer $TOKEN"
```

**验证**：返回 JSON 含 `l1_hits / misses / hit_rate` 字段。

---

## 十三、子模块 7：单元测试（13 个新测试）

> 🟡 测试设计原则：**强制 L1-only**（把 `_l2_disabled` 置 True），单测不依赖 Redis 是否在跑——本机有没有起容器结果都一样。

### 13.1 新建 `tests/unit/test_cache.py`

```python
# tests/unit/test_cache.py —— 阶段 5：多级缓存三件套单测（9 个）
"""
覆盖点：
- L1 命中（数据源只执行一次）
- 不同参数 = 不同 key
- singleflight：8 线程并发打同一个 key 只穿透 1 次
- 空值缓存（防穿透）
- TTL 过期重新加载
- 主动失效
- TTL 抖动范围（90%~110%）
- 统计与清零
- 总开关一键关闭
"""
import threading
import time

import pytest

from app_my.core import cache as cache_mod
from app_my.core.cache import cache_stats, cache_stats_reset, cached, invalidate_prefix


@pytest.fixture(autouse=True)
def _l1_only(monkeypatch):
    """每个测试：强制 L2 失效（不依赖 Redis）+ 清空 L1 + 清零统计"""
    monkeypatch.setattr(cache_mod, "_l2_disabled", True)
    monkeypatch.setattr(cache_mod, "_l1", None)
    cache_stats_reset()
    yield
    cache_stats_reset()


def test_cache_hit_single_loader():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def fn(q):
        calls["n"] += 1
        return [q]

    assert fn("a") == ["a"]
    assert fn("a") == ["a"]
    assert calls["n"] == 1                      # 数据源只跑一次
    s = cache_stats()
    assert s["l1_hits"] == 1 and s["misses"] == 1


def test_different_args_different_key():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def fn(q):
        calls["n"] += 1
        return [q]

    fn("a")
    fn("b")
    assert calls["n"] == 2                      # 两个 key 各自穿透


def test_singleflight_concurrent():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def slow(q):
        calls["n"] += 1
        time.sleep(0.2)                         # 模拟慢数据源
        return [q]

    results, errors = [], []

    def worker():
        try:
            results.append(slow("x"))
        except Exception as e:                  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert not errors
    assert calls["n"] == 1                      # 8 个并发只有 1 个穿透
    assert len(results) == 8 and all(r == ["x"] for r in results)


def test_null_value_cached():
    calls = {"n": 0}

    @cached(prefix="t", ttl=60, null_ttl=30)
    def fn(q):
        calls["n"] += 1
        return []

    assert fn("nothing") == []
    assert fn("nothing") == []
    assert calls["n"] == 1                      # 空值也只穿透一次（防穿透）
    assert cache_stats()["null_hits"] == 1


def test_ttl_expiry():
    calls = {"n": 0}

    @cached(prefix="t", ttl=1, null_ttl=1)
    def fn(q):
        calls["n"] += 1
        return [q]

    fn("a")
    time.sleep(1.3)                             # TTL 抖动有 1 秒下限，等满 1.3 秒
    fn("a")
    assert calls["n"] == 2                      # 过期后重新加载


def test_invalidate_prefix():
    @cached(prefix="inv", ttl=60)
    def fn(x):
        return [x]

    fn(1)
    assert invalidate_prefix("inv") == 1        # L1 里清掉 1 条
    fn(1)                                       # 重新执行（不再命中）


def test_jitter_bounds():
    ttls = {cache_mod._jitter_ttl(100) for _ in range(300)}
    assert 90 <= min(ttls) <= 100               # 下界不低于 -10%
    assert 100 <= max(ttls) <= 110              # 上界不超过 +10%
    assert len(ttls) > 50                       # 抖动真的产生了分布


def test_stats_reset():
    @cached(prefix="t", ttl=60)
    def fn(q):
        return [q]

    fn("a")
    fn("a")
    assert cache_stats()["l1_hits"] == 1
    cache_stats_reset()
    assert cache_stats()["l1_hits"] == 0


def test_cache_disabled_switch(monkeypatch):
    monkeypatch.setattr(type(cache_mod.settings), "CACHE_ENABLED", False)
    calls = {"n": 0}

    @cached(prefix="t", ttl=60)
    def fn(q):
        calls["n"] += 1
        return [q]

    fn("a")
    fn("a")
    assert calls["n"] == 2                      # 开关关闭 = 每次都穿透
```

### 13.2 新建 `tests/unit/test_routing.py`

```python
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


def test_same_engine_fallback(engines):
    """读引擎 = 写引擎（同库）时：查得到自己写的数据"""
    w, _ = engines
    db = session_mod.SessionLocal()
    db.execute(text("INSERT INTO t (id, name) VALUES (3, 'z')"))
    db.commit()
    rows = db.execute(text("SELECT * FROM t")).fetchall()
    db.close()
    assert len(rows) == 1
```

### 13.3 跑测试

```bash
uv run pytest -q
```

**验证**：`75 passed`（62 基线 + 13 新增）。任何 FAILED → 对照第十七节错误表。

---

## 十四、子模块 8：验证脚本（verify_stage5.py + 提测脚本）

### 14.1 新建 `scripts/verify_stage5.py`

```python
# scripts/verify_stage5.py
"""
阶段 5 分步验证脚本（手册各章"验证"统一走它，避免 PowerShell 粘贴引号被吃）。

用法（项目根目录执行）：
    uv run python scripts/verify_stage5.py <子命令>

子命令：
    deps      容器状态（pgvector/redis/pgbouncer）
    pgb       通过 9432 完成真实 SQL + SHOW POOLS 看池子
    routing   双引擎构建 + SELECT/INSERT 分流正确
    cache     三件套逻辑（命中/并发单飞/空值/抖动）
    api       /cache/stats 接口（需后端已启动 + 能登录）
    all       以上全部（提测用）
"""
import sys
import threading
import time
import urllib.request
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[OK]  " if ok else "[FAIL]"
    msg = f"{tag} {name}" + (f"  ->  {detail}" if detail else "")
    print(msg)
    RESULTS.append(ok)
    return ok


def check_deps() -> None:
    import subprocess
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    ).stdout
    for c in ("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer"):
        report(f"容器 {c} 运行中", c in out.splitlines(), "" if c in out.splitlines()
               else "docker compose -f docker/docker-compose.v3.yml up -d")


def check_pgb() -> None:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=9432, dbname="ai_sichu",
            user="ai_sichu", password="ai_sichu", connect_timeout=5,
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        report("通过 9432(PgBouncer) 执行 SELECT 1", cur.fetchone()[0] == 1)
        cur.execute("SELECT count(*) FROM users")
        report("经 PgBouncer 查 users 表", True, f"行数 {cur.fetchone()[0]}")
        conn.close()

        admin = psycopg2.connect(
            host="localhost", port=9432, dbname="pgbouncer",
            user="ai_sichu", password="ai_sichu", connect_timeout=5,
        )
        cur = admin.cursor()
        cur.execute("SHOW POOLS")
        rows = cur.fetchall()
        report("SHOW POOLS 可用（连接池观测）", len(rows) > 0, str(rows[:1]))
        admin.close()
    except Exception as e:
        report("PgBouncer 连接失败", False, f"{type(e).__name__}: {e}")


def check_routing() -> None:
    try:
        from sqlalchemy import text
        from app_my.db.session import read_engine, write_engine, engine, SessionLocal
        report("双引擎已构建", True,
               f"write={write_engine.url.render_as_string(hide_password=False).split('@')[1]}")
        db = SessionLocal()
        val = db.execute(text("SELECT 1")).scalar()
        db.close()
        report("RoutingSession 经 PgBouncer 查询", val == 1)
        report("engine 兼容别名仍指向写引擎", engine is write_engine)
    except Exception as e:
        report("路由检查失败", False, f"{type(e).__name__}: {e}")


def check_cache() -> None:
    try:
        from app_my.core import cache as cache_mod
        from app_my.core.cache import cached, cache_stats

        calls = {"n": 0}

        @cached(prefix="verify", ttl=60)
        def slow(q):
            calls["n"] += 1
            time.sleep(0.2)
            return [q]

        slow("x")
        slow("x")
        report("缓存命中（数据源只执行 1 次）", calls["n"] == 1)

        calls["n"] = 0

        def worker():
            slow("y")

        threads = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        report("singleflight：8 并发只穿透 1 次", calls["n"] == 1)

        ttls = {cache_mod._jitter_ttl(100) for _ in range(200)}
        report("TTL 抖动在 ±10% 内", 90 <= min(ttls) and max(ttls) <= 110)

        s = cache_stats()
        report("统计可读（含命中率）", "hit_rate" in s, str(s))
    except Exception as e:
        report("缓存检查失败", False, f"{type(e).__name__}: {e}")


def check_api() -> None:
    base = "http://127.0.0.1:9002"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=3) as resp:
            report("后端存活", json.loads(resp.read()).get("status") == "ok")

        req = urllib.request.Request(
            f"{base}/cache/stats",
            headers={"Authorization": "Bearer <在此填入你的token>"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read())
            report("/cache/stats 可访问", "hit_rate" in body)
        except urllib.error.HTTPError as e:
            report("/cache/stats 可访问", False,
                   f"HTTP {e.code}（401=先登录换 token 填进脚本）")
    except Exception as e:
        report("API 检查失败", False, f"{type(e).__name__}: {e}")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    checks = {
        "deps": check_deps, "pgb": check_pgb, "routing": check_routing,
        "cache": check_cache, "api": check_api,
    }
    if cmd == "all":
        for fn in checks.values():
            fn()
    else:
        checks[cmd]()
    print()
    print(f"结果：{sum(RESULTS)} 通过 / {len(RESULTS) - sum(RESULTS)} 失败")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
```

> 🟡 `check_api` 里 token 那行：先跑 `deps/pgb/routing/cache`，需要验 API 时把登录拿到的 access token 填进 `Bearer <在此填入你的token>`（或干脆不跑 api 子命令，用 12.2 节的 curl 方式验）。

### 14.2 提测脚本 `scripts/stage5_check.sh`（Git Bash）

```bash
#!/bin/bash
# 阶段 5 提测脚本（Git Bash 用）
# 前置：① pgvector + redis + pgbouncer 容器已启动  ② main.py 已启动（9002）
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"

echo "=== 阶段 5 提测开始 ==="

echo "--- 1/3 单元测试 ---"
"$PY" -m pytest -q
RC=$?
if [ $RC -ne 0 ]; then
  echo "[FAIL] 单测未全绿"
  exit $RC
fi

echo "--- 2/3 容器与服务 ---"
for c in ai_chief_pgvector ai_chief_redis ai_chief_pgbouncer; do
  if docker ps --format '{{.Names}}' | grep -q "^$c$"; then
    echo "[OK]   容器 $c 运行中"
  else
    echo "[FAIL] 容器 $c 未运行：docker compose -f docker/docker-compose.v3.yml up -d"
    exit 1
  fi
done
curl -s http://127.0.0.1:9002/health | grep -q ok || { echo "[FAIL] 9002 无响应"; exit 1; }

echo "--- 3/3 全量验证 ---"
"$PY" scripts/verify_stage5.py deps
"$PY" scripts/verify_stage5.py pgb
"$PY" scripts/verify_stage5.py routing
"$PY" scripts/verify_stage5.py cache

echo ""
echo "阶段 5 提测全部通过"
```

### 14.3 提测脚本 `scripts/stage5_check.ps1`（PowerShell 5.1，UTF-8 BOM 保存）

```powershell
# 阶段 5 提测脚本（PowerShell 5.1 用，UTF-8 BOM）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\stage5_check.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$Py = ".venv\Scripts\python.exe"

Write-Host "=== 阶段 5 提测开始 ===" -ForegroundColor Cyan

Write-Host "--- 1/3 单元测试 ---"
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 单测未全绿" -ForegroundColor Red; exit 1 }

Write-Host "--- 2/3 容器与服务 ---"
foreach ($c in @("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer")) {
    $running = docker ps --format '{{.Names}}' | Select-String -SimpleMatch $c
    if ($running) {
        Write-Host "[OK]   容器 $c 运行中" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] 容器 $c 未运行" -ForegroundColor Red
        exit 1
    }
}
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:9002/health" -TimeoutSec 5
    if ($resp.status -ne "ok") { throw "health 异常" }
} catch {
    Write-Host "[FAIL] 9002 无响应：先启动 main.py" -ForegroundColor Red
    exit 1
}

Write-Host "--- 3/3 全量验证 ---"
& $Py scripts\verify_stage5.py deps
& $Py scripts\verify_stage5.py pgb
& $Py scripts\verify_stage5.py routing
& $Py scripts\verify_stage5.py cache

Write-Host ""
Write-Host "阶段 5 提测全部通过" -ForegroundColor Green
```

**验证**：`bash scripts/stage5_check.sh`（或 PowerShell 对应脚本）末行输出"提测全部通过"。

---

## 十五、子模块 9：压测对比（bench_cache.py，拿真实数字）

新建 `scripts/bench_cache.py`：

```python
# scripts/bench_cache.py
"""
阶段 5：缓存开 vs 关 的同机对比压测——简历数字的唯一来源。

测什么：local_recipe_search（真实生产路径：embedding 调用 + PG 查询 + 融合 + 补全）
怎么测：
    off 轮：关掉缓存，连打 10 次（每次真实穿透，花 embedding 额度约 10 次）
    on  轮：打开缓存，先打 1 次填充缓存，再连打 200 次（全命中）
输出：两轮各自的 QPS、平均延迟、命中率——数字全部来自你的机器

用法（项目根目录，后端无需启动）：
    uv run python scripts/bench_cache.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_my.core import cache as cache_mod
from app_my.core.cache import cache_stats_reset, cache_stats, invalidate_prefix

QUERY = "鸡胸肉 西兰花 减脂"      # 一个有代表性的真实查询
OFF_N = 10                         # 关缓存轮次（每次都打 embedding 接口，别设太大）
ON_N = 200                         # 开缓存轮次（纯内存命中，可以多打）


def run_round(n: int) -> tuple:
    cache_stats_reset()
    t0 = time.perf_counter()
    for _ in range(n):
        from app_my.tools.recipe_rag_tool import local_recipe_search
        local_recipe_search(QUERY, k=5)
    cost = time.perf_counter() - t0
    s = cache_stats()
    return cost, n / cost, s


def main() -> None:
    from app_my.tools.recipe_rag_tool import local_recipe_search

    print("=" * 60)
    print("阶段 5 缓存压测（结果填进简历/收官文档）")
    print("=" * 60)

    # --- 轮 1：缓存关（真实穿透：embedding + PG + BM25 融合 + 补全）---
    cache_mod.settings.__class__.CACHE_ENABLED = False
    invalidate_prefix("rag")
    cost_off, qps_off, _ = run_round(OFF_N)
    print(f"\n[关] {OFF_N} 次真实穿透：{cost_off:.1f}s，QPS={qps_off:.2f}，"
          f"平均 {cost_off / OFF_N * 1000:.0f} ms/次")

    # --- 轮 2：缓存开（先填一次，再测命中性能）---
    cache_mod.settings.__class__.CACHE_ENABLED = True
    invalidate_prefix("rag")
    local_recipe_search(QUERY, k=5)          # 填充缓存（这次算 miss）
    cost_on, qps_on, s = run_round(ON_N)
    print(f"[开] {ON_N} 次缓存命中：{cost_on:.2f}s，QPS={qps_on:.1f}，"
          f"平均 {cost_on / ON_N * 1000:.2f} ms/次")
    print(f"     命中统计：L1={s['l1_hits']} L2={s['l2_hits']} 穿透={s['misses']}"
          f" 命中率={s['hit_rate'] * 100:.1f}%")

    print("\n" + "-" * 60)
    print(f"结论：QPS 提升 {qps_on / qps_off:.0f} 倍，"
          f"单次延迟 {cost_off / OFF_N * 1000:.0f}ms -> {cost_on / ON_N * 1000:.2f}ms")
    print("（把这两个数字记下来，收官文档要用）")


if __name__ == "__main__":
    main()
```

**操作与验证**：

```bash
uv run python scripts/bench_cache.py
```

**验证**：输出两轮 QPS 与结论行。🟡 预期形态：关轮 QPS 个位数（每次百毫秒级），开轮 QPS 四位数（纯内存）——具体数字以你机器实测为准，**照抄输出即可，不要改数字**。

---

## 十六、提交 Gitee 与 PR 描述

**操作 1：提交**

```bash
git add docker/pgbouncer/ docker/docker-compose.v3.yml \
        app_my/db/routing.py app_my/db/session.py \
        app_my/core/cache.py app_my/api/cache.py \
        app_my/core/config.py app_my/knowledge/retriever.py \
        app_my/api/kg.py app_my/main.py scripts/ \
        tests/unit/test_cache.py tests/unit/test_routing.py .env.example 2>/dev/null || git add -A

git commit -m "feat(v3-stage5): PgBouncer连接池+多级缓存——singleflight防击穿/TTL抖动防雪崩/空值缓存防穿透+读写分离路由"
git push -u origin feat/v3-stage5
```

> 🔴 `.env` 永远不提交（.gitignore 已排除）；上面 `git add -A` 前先 `git status` 确认没有把 `.env` 或 md 手册误提交（手册要不要进仓库按你阶段 1~4 的习惯保持一致）。

**操作 2：Gitee 上建 PR**（`feat/v3-stage5` → `master`），标题同 commit。

**操作 3：PR 描述（直接复制）**

```markdown
## 阶段 5：数据层升级——PgBouncer 连接池 + 多级缓存

### 改了什么

#### 基础设施
- 新增 PgBouncer 容器（宿主机 9432，transaction 池化模式）：
  max_client_conn=100 / default_pool_size=20 / reserve_pool=5
- 应用 DATABASE_URL 从直连 5433 切换为经 PgBouncer 9432

#### 读写分离
- app_my/db/routing.py：RoutingSession 按"语句类型"分流——
  flush/结构化写语句/裸 text() 写动词 → write_engine；SELECT → read_engine
- （实测踩坑：裸 text() 是 TextClause，isinstance 判不出写语句，必须按 SQL 首关键词补判）
- DATABASE_READ_URL 为空时回落写库——加只读从库时零改码切换

#### 多级缓存（core/cache.py，纯标准库）
- L1 进程内 TTL-LRU（512 条）→ L2 Redis → L3 数据源
- singleflight：threading.Lock per key + double-check，8 并发只穿透 1 次
- TTL ±10% 抖动防雪崩（下限 1 秒）
- 空值短 TTL（30s）缓存防穿透
- 主动失效：invalidate_prefix()（导入脚本跑完自动清 rag 前缀）

#### 接入点（只缓存全局知识，租户私有数据不进缓存）
- hybrid_search（rag 前缀，TTL 300s）+ BM25 索引 lru_cache 进程内复用
- /kg/ask（kg 前缀，TTL 600s）、/kg/stats（kgstats 前缀，TTL 60s）
- 新增 /cache/stats /cache/reset /cache/invalidate/{prefix} 观测接口

#### 测试
- 新增 13 个单测（9 缓存 + 4 路由），默认套件 62 -> 75 passed
- bench_cache.py 同机对比：关缓存 QPS=___ vs 开缓存 QPS=___（自己的实测数字）
- verify_stage5.py 分步验证：deps/pgb/routing/cache/api 全绿

#### 不在本 PR 的内容
- 只读从库实例（代码已就位，等有真实需要再加容器）
- 延迟双删等强一致策略（无高并发写场景，TTL+主动失效足够）
- Locust 全链路压测（归阶段 10）
```

---

## 十七、常见错误对照表

| 现象 | 大概率原因 | 修法 |
|---|---|---|
| PgBouncer 容器反复重启 / 日志 `cannot open config file` | ini 挂载路径写错或文件名不一致 | `docker exec ai_chief_pgbouncer ls /etc/pgbouncer/` 看容器内实际文件；确认 compose 里是 `./pgbouncer/pgbouncer.ini`（相对 docker/ 目录） |
| `password authentication failed for user "ai_sichu"`（经 9432） | userlist.txt 格式错（单引号/缺空格/没挂载） | 内容必须是 `"ai_sichu" "ai_sichu"`；改完 `docker compose -f docker/docker-compose.v3.yml restart pgbouncer` |
| `manifest unknown` 拉不到 edoburu/pgbouncer:1.24.1 | DaoCloud 没同步该 tag | image 换成 `docker.m.daocloud.io/edoburu/pgbouncer:latest` 再 `up -d pgbouncer` |
| 连 9432 报 `connection refused` | 容器没起 / 端口没映射 | `docker ps` 看 ai_chief_pgbouncer；`docker port ai_chief_pgbouncer` 应显示 `6432/tcp -> 0.0.0.0:9432` |
| 切到 9432 后登录报 `prepared statement "..." does not exist` | 事务池化 + 使用了命名预编译语句 | 本项目 psycopg2 默认不用命名预编译语句，理论上不出现；若出现检查是否有人给 engine 加了 `prepare_threshold` 参数，去掉即可 |
| 单测 `test_cache_*` 全 FAIL | settings.CACHE_ENABLED 为 False（.env 里关了） | `.env` 里 `CACHE_ENABLED=true`；或跑单测前临时注释该行 |
| 单测偶发 FAIL（TTL 相关） | 机器负载高，sleep 1.3 秒不够 | 重跑一次；不用改代码（1 秒抖动下限 + 1.3 秒等待已留 30% 余量） |
| `test_routing` 报 `no such table: t`（写库那条） | sqlite 文件残留旧表结构 | 无害重跑即可；tmp_path 每次都是新目录，一般不会遇到 |
| verify_stage5 pgb 子命令 `SHOW POOLS` 报权限错 | ini 里漏了 `admin_users` | pgbouncer.ini 补 `admin_users = ai_sichu` 后 restart 容器 |
| `/cache/stats` 401 | token 过期 / 没带 | 重新登录拿新 access token |
| bench_cache 关轮 QPS 特别低（<1） | embedding 接口限流 | 正常现象（DashScope 有 QPS 限制），如实记录即可——这正说明缓存的价值 |
| pytest 数量不是 75 | 阶段 4 测试基数不对 | 先 `git log` 确认阶段 4 已合并；62+13=75 是硬账 |

---

## 十八、避坑提示

🟡 **PgBouncer 的 `pool_mode` 三选一要想清楚**：session（整会话独占，等于没池化）/ transaction（本阶段选择：事务结束就归还，复用率最高）/ statement（事务中途也归还，多语句事务会被拆散，危险）。个人 Web 项目无长连接需求，transaction 是标准答案。

🟡 **两层池的关系别搞混**：SQLAlchemy 的 `pool_size=10` 是"应用到 PgBouncer"的客户端池；PgBouncer 的 `default_pool_size=20` 是"PgBouncer 到 PostgreSQL"的服务端池。叠加后数据库看到的连接数 = 20（封顶 25），不再随应用进程/worker 数量增长。

🟡 **缓存 key 一定包含函数参数**：`_make_key` 把 args/kwargs 摘要进 key。如果手写 key 只用 prefix 不加参数指纹，"鸡胸肉"和"牛肉"会共用一条缓存——查什么都是同一个结果。

🟡 **空值缓存的时间要短**：30 秒足够挡住恶意扫 key，又不至于"新导入的菜谱 5 分钟内查不到"。

🟡 **L2 降级用"失败一次就永久放弃"**：个人项目里 Redis 挂了通常整轮都挂，反复重试只会给每个请求加超时。降级要降得干脆（和阶段 3 kg 模块同一哲学）。

🟡 **单测强制 L1-only**：`_l2_disabled=True` + 清空 L1 的 autouse fixture，让测试在"有没有起 Redis 容器"两种环境下结果一致。

🔴 **永远不要缓存租户私有数据**（除非 key 里带 tenant_id 且经过审视）：本阶段只挂 rag/kg 两个全局知识前缀，就是这条红线的设计结果。

🔴 **不要用 `KEYS rag:*` 清 Redis**：`KEYS` 是全库扫描会卡住服务；代码里用的是 `SCAN` 游标遍历（`scan_iter`），手工排障时也要用 `SCAN 0 MATCH rag:* COUNT 100`。

🔴 **不要在 `_l2_set` 里静默吞掉数据类型错误**：被缓存函数返回值必须可 JSON 序列化。如果以后想缓存含 `datetime` 的对象，`default=str` 会把它转成字符串——消费方拿到的是字符串不是 datetime，注意口径。

---

## 十九、本阶段防呆自检清单

- [ ] 阶段 4 已合并 master，基线 62 passed（第六节操作 4）
- [ ] `docker ps` 三个容器：pgvector / redis / **pgbouncer**
- [ ] `SHOW POOLS` 能看到 ai_sichu 池子的 cl_active / sv_active
- [ ] `.env` 的 DATABASE_URL 端口是 9432（不是 5433）
- [ ] `engine is write_engine` 为 True（兼容别名没断）
- [ ] 缓存冒烟：同一查询数据源只执行 1 次
- [ ] 8 线程并发只穿透 1 次（singleflight 生效）
- [ ] `/cache/stats` 带 token 返回 hit_rate
- [ ] pytest 75 passed
- [ ] `bench_cache.py` 跑完，两轮数字已记录（要进收官文档）
- [ ] 提交信息格式 `feat(v3-stage5): ...`，PR 已建

---

> **下一步**：全部打勾后告诉 AI"阶段 5 完成"，等待交付《阶段 5 最终完整版》+《阶段 5 问题与解决记录》两份收官文件；然后按《AI私厨_v3.0_阶段6_Milvus与混合检索v2_操作手册.md》开工。
