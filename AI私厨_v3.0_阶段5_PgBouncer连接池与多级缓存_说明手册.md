# AI 私厨 v3.0 · 阶段 5：PgBouncer 连接池 + 多级缓存（新增内容说明手册）

> **本手册定位**：全项目**唯一一处逐行代码解释**——讲清楚阶段 5 的每一行"在做什么、为什么这么写、每个参数什么意思"。操作步骤请看操作手册（照着做），本手册只负责"看懂为什么"，两者绝不重复。
> 风格约定：代码行尾加简洁中文注释；解释表不加序号；不编造真实数据示例。
> 🟢 本手册配套代码已在临时目录用 Python 3.13 实测：缓存 16 项断言、路由 6 项断言全过；实测过程中抓出并修复了两个真实 bug（见第六、七节的"实测坑"框）。

---

## 目录

- [一、本阶段在做什么（一句话与全景图）](#一本阶段在做什么一句话与全景图)
- [二、新出现的专业名词（先看这张表再读代码）](#二新出现的专业名词先看这张表再读代码)
- [三、为什么需要 PgBouncer：一条连接的真实成本](#三为什么需要-pgbouncer一条连接的真实成本)
- [四、pgbouncer.ini + userlist.txt 逐行解释](#四pgbouncerini--userlisttxt-逐行解释)
- [五、routing.py + session.py：读写分离逐行解释](#五routingpy--sessionpy读写分离逐行解释)
- [六、cache.py：L1 进程内缓存逐行解释](#六cachepy-l1-进程内缓存逐行解释)
- [七、cache.py：L2 Redis 层与 singleflight 逐行解释](#七cachepy-l2-redis-层与-singleflight-逐行解释)
- [八、cache.py：cached 装饰器逐行解释（主流程）](#八cachepy-cached-装饰器逐行解释主流程)
- [九、缓存接入点：为什么只挂 rag 和 kg](#九缓存接入点为什么只挂-rag-和-kg)
- [十、观测接口与压测脚本：数字怎么读](#十观测接口与压测脚本数字怎么读)
- [十一、测试设计解释：13 个单测在守护什么](#十一测试设计解释13-个单测在守护什么)
- [十二、常见疑问](#十二常见疑问)

---

## 一、本阶段在做什么（一句话与全景图)

**一句话**：让"每一次数据访问"先过一道便宜的分流闸门——连接由 PgBouncer 统一收发、读和写分道走、查过的结果就近记住——越靠近用户的那层越快，越贵的层越少被打扰。

```text
用户请求
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│ FastAPI (9002)                                                │
│   ┌────────────────────────────────────────────┐              │
│   │ L1 进程内 TTL-LRU 缓存（纳秒级，512 条）      │  ← 命中就直接返回
│   └──────────────┬─────────────────────────────┘              │
│                  │ 未命中                                    │
│   ┌──────────────▼─────────────────────────────┐              │
│   │ L2 Redis 缓存（毫秒级，跨进程共享）           │  ← 命中回填 L1
│   └──────────────┬─────────────────────────────┘              │
│                  │ 未命中（singleflight：同 key 只放 1 个线程） │
│   ┌──────────────▼─────────────────────────────┐              │
│   │ L3 数据源（百毫秒~秒级）                      │              │
│   │   embedding 接口 + PG 查询 + BM25 融合        │              │
│   └──────────────┬─────────────────────────────┘              │
└──────────────────┼───────────────────────────────────────────┘
                   │ SQL（读走读引擎，写走写引擎）
                   ▼
          PgBouncer (9432)   ← 100 个客户端连接复用 20 个真实连接
                   │
                   ▼
          PostgreSQL (5433)
```

对用户可感知的变化：同一个问题问第二遍，答案秒回（不再等 embedding 接口几百毫秒）；对简历可量化的变化：`/cache/stats` 的命中率 + 压测脚本的 QPS 倍数。

---

## 二、新出现的专业名词（先看这张表再读代码）

| 名词 | 人话解释 | 在本阶段的角色 |
|---|---|---|
| **连接池（Connection Pool）** | 提前建好一批数据库连接放在"池子"里，谁要用借一个、用完还回去——避免每次查询都付"建立连接"的启动成本 | SQLAlchemy 自带一个（应用侧）；PgBouncer 是另一个（数据库侧） |
| **PgBouncer** | PostgreSQL 官方生态里最常用的轻量连接池中间件（C 写的，内存占用 ~10MB） | 本阶段新容器，坐在应用和 PG 中间 |
| **pool_mode（池化粒度）** | PgBouncer 归还真实连接的时机：`session`=客户端断开才还（复用率低）；`transaction`=事务提交就还（复用率高，本阶段选它）；`statement`=每条语句执行完就还（会拆散事务，危险） | pgbouncer.ini 里最重要的一行 |
| **读写分离（Read/Write Split）** | 查询走只读副本、写入走主库——读多写少的系统靠它横向扩容 | RoutingSession 代码就位，当前读写同库 |
| **LRU（Least Recently Used）** | "最近最少使用"淘汰法：缓存满了优先扔最久没人碰的条目 | L1 的容量淘汰策略 |
| **TTL（Time To Live）** | "存活时间"：一条缓存从写入到自动作废的秒数 | 每个前缀各自的过期参数 |
| **缓存穿透** | 查一个**根本不存在**的 key，缓存永远不可能命中，每次都打到数据库；恶意攻击常用手段 | 解法：空值短 TTL 缓存（查过了也记下来"没有"） |
| **缓存击穿** | 某个**热点 key 恰好过期**的一瞬间，成千上万并发同时打到数据库 | 解法：singleflight——同一 key 并发只放一个线程去加载，其余等结果 |
| **缓存雪崩** | **一大批 key 同时到期**（比如同时写入、同 TTL），数据库瞬间被打爆 | 解法：TTL ±10% 随机抖动，到期时间错开 |
| **singleflight** | "单飞"：同一 key 的并发请求合并成一次真实加载 | `_get_key_lock` + double-check 实现 |
| **哨兵值（sentinel）** | 一个"绝不可能是业务值"的特殊对象，用来区分"缓存里没有"和"缓存里存了 None/空" | `_MISS = object()` |
| **缓存命中率（hit_rate）** | 命中次数 ÷（命中 + 穿透）——缓存有没有白干，一眼看出 | `/cache/stats` 的核心字段 |
| **惰性过期** | 到期的缓存条目**不主动删**，等下次被取到时才发现过期顺手删掉——省一个后台线程 | `_TTLCache.get` 的写法 |
| **幂等（idempotent）** | 同一个操作重复执行，结果不变 | 导入脚本清空再导、缓存失效再失效，都幂等 |
| **EXPIRE / SETEX** | Redis 命令：给 key 设存活时间 / 写值同时设过期 | L2 写入用 `setex`（一条命令原子完成两件事） |
| **SCAN** | Redis 的游标式遍历，找一批 key 不阻塞服务（`KEYS *` 会卡死） | L2 主动失效用 `scan_iter` |
| **JSONB** | PostgreSQL 的 JSON 二进制存储类型（向量库元数据在用，本阶段不碰它） | 已有概念，复习 |
| **PgBouncer 的 SHOW POOLS** | PgBouncer 自带的管理命令，输出"客户端连接数/服务端连接数"——连接复用的直管证据 | verify 脚本的 pgb 子命令 |

---

## 三、为什么需要 PgBouncer：一条连接的真实成本

**PostgreSQL 的每个连接是一个服务端进程**（不是线程）。进程意味着：独立内存、独立调度、fork 成本。连接数一高：

```text
每条连接 ≈ 几 MB 内存 + 一个进程调度槽位
100 条连接 ≈ 数据库本身还没干活，先吃掉几百 MB 和大量上下文切换
```

而"连接建了又拆、拆了又建"同样是浪费——TCP 三次握手 + PG 身份认证 + 后端进程 fork，一次下来几十毫秒。

**PgBouncer 的解法**：它替数据库"扛住"一百个客户端连接（这些连接很便宜，只是 TCP），而在它到 PostgreSQL 之间只维持 20 条真实连接，**按事务借还**：

```text
应用侧 100 个客户端连接  ──┐
应用侧 100 个客户端连接  ──┤            ┌─ 真实连接 #1（事务 A 用完 → 事务 B 接着用）
应用侧 100 个客户端连接  ──┼── PgBouncer ┼─ 真实连接 #2
        ...              ──┤            └─ ... 共 20 条
应用侧 100 个客户端连接  ──┘
```

**为什么 transaction 模式敢这么借还**：因为一个事务执行期间连接不能换人（服务器状态是会话级的），但事务一提交，连接上的"用户状态"就干净了——`server_reset_query = DISCARD ALL` 再保险地清一遍残留（比如有人 SET 过时区），下个事务进来时连接和新的一样。

**两层池（SQLAlchemy 池 + PgBouncer 池）叠加后**：数据库看到的连接数封顶在 20+5，**不再随应用 worker 数量增长**——这就是简历里"连接治理"的技术实质。

---

## 四、pgbouncer.ini + userlist.txt 逐行解释

```ini
[databases]
ai_sichu = host=pgvector port=5432 dbname=ai_sichu user=ai_sichu password=ai_sichu
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `[databases]` 段 | "连接串里的库名 → 真实后端"的映射表 | 应用连 PgBouncer 时写的库名还是 `ai_sichu`（应用零感知），PgBouncer 负责转发到真库 |
| `host=pgvector` | 后端主机名写的是 **compose 服务名** | 容器之间在同一个 docker 网络里，服务名就是内部 DNS 名；宿主机的 5433 映射是给"容器外"用的 |

```ini
[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = plain
auth_file = /etc/pgbouncer/userlist.txt
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `listen_addr = 0.0.0.0` | 监听容器内所有网卡 | 写 `127.0.0.1` 只有容器自己能连，宿主机端口映射就废了——容器场景的固定写法 |
| `listen_port = 6432` | PgBouncer 的经典默认端口 | 宿主机映射成 9432（v3 的 9xxx 端口段约定），容器内外各用各的 |
| `auth_type = plain` | 对客户端做明文密码校验 | 密码表在 userlist.txt；本地开发够用，生产要换 SCRAM |
| `auth_file` | 指向账号密码表 | 挂载进容器的只读文件 |

```ini
pool_mode = transaction
max_client_conn = 100
default_pool_size = 20
reserve_pool_size = 5
reserve_pool_timeout = 3
server_reset_query = DISCARD ALL
ignore_startup_parameters = extra_float_digits
admin_users = ai_sichu
logfile = /dev/stdout
```

| 参数 | 含义 | 本项目取值与理由 |
|---|---|---|
| `pool_mode` | 归还连接的粒度（session/transaction/statement） | `transaction`：Web 应用每个请求就是一两个短事务，复用率最高 |
| `max_client_conn` | 允许的客户端连接总数 | `100`：SQLAlchemy 写池 10+20溢出 + 读池 10+20 + 脚本/psql 手工连接，上限足够宽裕 |
| `default_pool_size` | 每个数据库维持的真实连接数 | `20`：单机 PG 的合理甜点——连接越多不一定越快（进程调度开销反噬） |
| `reserve_pool_size` | 排队超时后启用的应急连接数 | `5`：突发流量缓冲垫 |
| `reserve_pool_timeout` | 客户端排队多久才动用应急池 | `3` 秒：短平快，别让人干等 |
| `server_reset_query` | 连接归还前执行的清理 SQL | `DISCARD ALL`：清掉 SET 过的会话变量，**transaction 模式必配**（否则上个用户设置的时区会"串"给下个） |
| `ignore_startup_parameters` | 容忍客户端发来的额外启动参数 | 某些驱动会发 `extra_float_digits`，不忽略直接拒连 |
| `admin_users` | 允许执行 SHOW 命令的账号 | 排障和演示用：`SHOW POOLS` 一眼看到连接复用 |
| `logfile = /dev/stdout` | 日志写标准输出 | `docker logs` 直接看，不用进容器找文件 |

**userlist.txt 只有一行**：`"ai_sichu" "ai_sichu"`——账号、密码两段各带双引号。PgBouncer 的密码表格式自 1.x 以来就是这副"老派样子"，格式错了报的就是 `password authentication failed`。

---

## 五、routing.py + session.py：读写分离逐行解释

### 5.1 RoutingSession：SQLAlchemy 的"换道闸口"

先理解机制：SQLAlchemy 里每个 Session 执行语句前都会调一次 `get_bind()` 问"我这条语句该发给哪个引擎"。**默认它只会返回唯一绑定的引擎——我们重写这个方法，按语句特征返回不同的引擎**，读写分离就完成了。

```python
_WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE")
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 元组常量 | 裸 SQL 的"写动词"清单 | 见下面 TextClause 的坑——裸 SQL 没有类型信息，只能看第一个单词 |

```python
class RoutingSession(Session):
    def get_bind(self, mapper=None, clause=None, **kw):
        from app_my.db.session import read_engine, write_engine   # 惰性 import 防循环依赖

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

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `self._flushing` | SQLAlchemy 在 flush 阶段把这个内部标志置 True | ORM 的 `db.add(user); db.commit()` 里 INSERT 语句是 flush 时生成的，此时 `clause` 参数拿不到语句本体——只能靠这个标志兜住"flush 期间必走写库" |
| `isinstance(clause, (Insert, ...))` | 用语句对象的**类型**判断 | `db.execute(users.insert().values(...))` 这种结构化语句，类型就是 `Insert`——最可靠的判据 |
| `TextClause` 分支 | 裸 `text("INSERT ...")` 的补判 | 🟢 **实测坑**：临时目录测试发现 `text("INSERT INTO ...")` 产生的是 `TextClause`，`isinstance` 判不出来、被当成 SELECT 走了读库——**数据写丢了**。这就是 `_WRITE_PREFIXES` 存在的理由 |
| `clause.text.lstrip().upper()` | 取 SQL 原文首词并统一大写 | `startswith` 匹配 "insert ..." 和 "INSERT ..."；`lstrip` 防手滑写了前导空格 |
| `return read_engine` 兜底 | 其余全部走读库 | 宁可保守：判断不了的语句去读库（读库错了顶多查不到，写库错了是数据事故） |

### 5.2 session.py：双引擎 + 兼容别名

```python
write_engine = create_engine(settings.DATABASE_URL, **_write_kwargs)   # 写库（经 PgBouncer）

_read_url = settings.DATABASE_READ_URL or settings.DATABASE_URL        # 没配读库 = 暂时同库
read_engine = create_engine(_read_url, **_read_kwargs)                 # 读库

engine = write_engine   # 兼容旧代码：vector_store / init_db 继续用 "engine" 这个名字
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 两个 `create_engine` | 写引擎、读引擎各自独立 | 引擎=连接池的载体；分开建才能分开调池参数、分开指向不同库 |
| `settings.DATABASE_READ_URL or settings.DATABASE_URL` | 空串回落到写库 URL | "代码就位、实例后补"：现在没从库，**加从库那天只改 .env 一行**，这就是"零改码切换点" |
| `engine = write_engine` | 老名字继续存在 | vector_store.py（PGVector 向量库）和 base.py（建表）都 `import engine`——别名保住它们零改动；建表本来就该走写库，语义也正确 |

```python
SessionLocal = sessionmaker(
    class_=RoutingSession,
    autoflush=False,
    expire_on_commit=False,
)
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `class_=RoutingSession` | 会话工厂产出"我们的会话类" | 所有用 `SessionLocal()` 造出来的会话自动带分流能力 |
| `autoflush=False` | 查询前不要自动把未提交的改动刷进数据库 | 行为可预期——什么时候发 SQL 由代码说了算 |
| `expire_on_commit=False` | commit 后对象属性不过期 | 否则接口返回前读个属性都会偷偷再发一遍 SELECT |
| 注意**没传 bind** | 会话工厂不绑死引擎 | 绑死了 get_bind 的返回值就没意义了；路由靠的就是"每次问" |

---

## 六、cache.py：L1 进程内缓存逐行解释

### 6.1 模块级全局状态

```python
_MISS = object()                 # "缓存里没有"的内部哨兵（不可能是业务值）
_NULL_MARK = "__CACHE_NULL__"    # L2 里存这个字符串 = "查过了，确实没有"
_JITTER = 0.10                   # TTL ±10% 抖动幅度

_l1: Optional["_TTLCache"] = None
_l1_lock = threading.Lock()
_key_locks: Dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()
_l2_disabled = False             # L2（Redis）连续失败后置 True，本进程余生不再碰它
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `_MISS = object()` | 造一个全世界独一份的对象 | 区分"缓存没有"和"缓存里存了 None/空列表"这两种语义——用 None 当"没有"的话，"真存了个 None"就永远区分不出来 |
| `_NULL_MARK` | 空值在 L2 的替身 | Redis 里只能存字符串/字节；空结果序列化成这个记号，读回来知道"这是空值占位，不是数据" |
| `_l1 = None` + `_l1_lock` | L1 惰性单例 | 第一次用到才建——避免 import 本模块时就去读 settings（配置还没就绪的顺序问题） |
| `_key_locks` | key → 锁的字典 | singleflight 的"每把锁只管一个 key"：查鸡胸肉和查牛肉互不排队 |
| `_l2_disabled` | Redis 失败标记 | 失败一次终身降级——和阶段 3 kg 模块的 `_driver_failed` 同一哲学：**增强组件降级要降得干脆** |

### 6.2 _TTLCache：带 TTL 的线程安全 LRU

```python
class _TTLCache:
    def __init__(self, maxsize: int = 512):
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self._maxsize = maxsize
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `OrderedDict` | 记住插入/访问顺序的字典 | LRU 的地基：它能 `move_to_end`（挪到最新端）和 `popitem(last=False)`（从最旧端弹出），普通 dict 做不到这两下的语义 |
| `threading.Lock` | 一把大锁护住整个字典 | FastAPI 的同步路由跑在线程池里——多线程同时 get/put 必须互斥；锁粒度粗但操作全是内存级，锁一下也就微秒 |

```python
    def get(self, key: str) -> Any:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return _MISS
            value, is_null, expire_at = item
            if expire_at <= time.monotonic():
                del self._data[key]
                return _MISS
            self._data.move_to_end(key)
            return (value, is_null)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `time.monotonic()` | 单调递增时钟 | 比 `time.time()` 合适：系统时间会被 NTP/手动改，改完后 TTL 判断会错乱；monotonic 只往前走 |
| `expire_at <= now` 就地删除 | **惰性过期** | 不用后台线程扫过期——取到谁家发现谁家过期，顺手删掉；没被取到的过期条目顶多占点内存，容量淘汰时自然被清 |
| `move_to_end(key)` | 刚访问的挪到"最新"端 | LRU 的 R：被访问=有价值，淘汰时从另一端扔"最久没人碰"的 |
| 返回 `(value, is_null)` 元组 | 把"是不是空值"带出去 | 调用方统计 `null_hits` 要用；命中空值和命中真值走不同计数 |

```python
    def put(self, key: str, value: Any, is_null: bool, ttl: float) -> None:
        with self._lock:
            self._data[key] = (value, is_null, time.monotonic() + ttl)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)       # 淘汰"最久未访问"端
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 存三元组 `(值, 是否空, 过期时间)` | 状态内聚在条目里 | 过期判断不需要任何外部结构 |
| `while` 而不是 `if` | 容量超了连续淘汰 | 理论上 put 一次只超 1 条，但防御性写法对边界更稳（比如未来改小 maxsize） |
| `popitem(last=False)` | 从"最旧"端弹出 | OrderedDict 的 `last=False` = 先插入/最久未动的一端——这就是 LRU 淘汰 |

```python
def _get_l1() -> _TTLCache:
    global _l1
    if _l1 is None:
        with _l1_lock:
            if _l1 is None:
                _l1 = _TTLCache(maxsize=settings.CACHE_L1_MAXSIZE)
    return _l1
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 双重检查锁定 | 先无锁快判，为空才上锁再判一次 | 99.9% 的调用走第一行直接返回；只有第一次建对象才付锁成本。这是单例的标准写法（Java/Python 通用套路） |
| `global _l1` | 声明要写模块级变量 | Python 里函数内**赋值**模块变量必须声明 global，否则会创建一个同名局部变量——本模块实测踩过这个坑的反面教材见 7.1 |

---

## 七、cache.py：L2 Redis 层与 singleflight 逐行解释

### 7.1 L2 读写（含实测抓出的第一个 bug）

```python
def _l2_get(key: str) -> Any:
    global _l2_disabled
    if _l2_disabled:
        return _MISS
    try:
        from app_my.core.redis_client import get_redis
        raw = get_redis().get(key)
        if raw is None:
            return _MISS
        data = json.loads(raw)
        return (data.get("v"), bool(data.get("n")))
    except Exception:
        _l2_disabled = True
        logger.warning("cache: L2(Redis) 不可用，本进程降级为 L1+数据源")
        return _MISS
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `from ... import get_redis` 写在函数里 | 函数内局部导入 | 没装 redis 包 / Redis 没起时，import 本模块不报错——和 token_billing、kg 模块同款思路 |
| `raw is None` 返回 `_MISS` | Redis 的"没有"翻译成缓存层的"没有" | redis-py 查不到 key 返回 None；统一翻译成哨兵，主流程就不用认识 Redis 的返回类型 |
| `json.loads(raw)` 还原 | Redis 里存的是 JSON 字符串 | `{"n": true/false, "v": 值}` 的信封格式：n 标记空值、v 装数据 |
| `except Exception` 一把抓 | 任何 L2 问题都不许冒泡 | **缓存层永远不能挡业务**：Redis 挂了就是降级，不是事故 |
| `_l2_disabled = True` | 降级开关 | 排队等超时比没有缓存更糟；失败一次本进程就不再碰它 |

> 🟢 **实测坑（global 声明）**：临时目录首跑时 `_l2_set` 抛 `UnboundLocalError`——因为函数体里出现了 `_l2_disabled = True` 这行**赋值**，Python 就把 `_l2_disabled` 当成了局部变量，而上面 `if _l2_disabled:` 读它时还没赋值。修法就是函数开头补 `global _l2_disabled`。**规则：函数里既要读又要写模块级变量，必须声明 global**。`_l2_set` 和 `_l2_del_prefix` 都要声明（它们都有 except 分支的赋值）。

```python
def _l2_set(key: str, value: Any, is_null: bool, ttl: int) -> None:
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
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `ensure_ascii=False` | 中文直接存 UTF-8 | 默认 True 会把中文转成 `\uXXXX` 转义串——多占一倍空间还不可读 |
| `default=str` | 序列化不了的类型降级成字符串 | datetime 等类型不至于让整个写入炸掉；代价是消费方拿到字符串（见操作手册避坑） |
| `setex(key, ttl, value)` | 写值 + 设过期，一条命令 | 等价于 SET + EXPIRE 两步，但原子完成——两步之间断线会出现"永不过期"的脏数据 |
| `max(ttl, 1)` | TTL 至少 1 秒 | Redis 的 setex 不接受 0/负数（会报错）；抖动函数已经保证 ≥1，这里再兜底一次 |

```python
def _l2_del_prefix(prefix: str) -> None:
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
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `scan_iter(match=...)` | 游标式找 key | 🔴 `KEYS rag:*` 是全库单线程扫描，key 多时能把 Redis 卡住几秒；SCAN 分批走完全不让出服务。手工排障也一样要用 SCAN |
| `client.delete(*keys)` | 把列表拆成位置参数批量删 | `delete('a','b','c')` 一次网络往返删完，比循环单删省 RTT |

### 7.2 singleflight：并发合并的机关

```python
def _get_key_lock(key: str) -> threading.Lock:
    with _key_locks_guard:
        lock = _key_locks.get(key)
        if lock is None:
            if len(_key_locks) > 4096:
                _key_locks.clear()
            lock = threading.Lock()
            _key_locks[key] = lock
        return lock
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 字典查锁 | 每个 key 一把专用锁 | 查"鸡胸肉"的线程和查"牛肉"的线程**互不阻塞**——锁的粒度细到 key 级 |
| `_key_locks_guard` | 保护"锁字典"本身的那把锁 | 字典本身的 get/set 也要互斥（字典不是线程安全的读写场景）；这是"锁的锁"，很常见的两层结构 |
| 超过 4096 整体清空 | 防内存无限涨 | key 是无限多的（查询千变万化），锁却可以粗放管理：清空瞬间正在用的锁对象还捏在持锁线程手里，不影响正确性，只是新来的 key 重建锁 |

**为什么用 threading.Lock 而不是 asyncio.Lock**：本项目检索调用链（recipe_rag_tool → hybrid_search）在 LangGraph 的同步执行上下文里跑，FastAPI 也把同步函数丢线程池——**线程是真实的并发单位**。asyncio.Lock 只能挡协程，挡不住线程。

### 7.3 工具函数

```python
def _make_key(prefix: str, fn: Callable, args: tuple, kwargs: dict) -> str:
    raw = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `fn.__module__ + __qualname__` | 函数的"全名"进 key | 两个模块都有叫 `search` 的函数时不会撞车 |
| `sorted(kwargs.items())` | 关键字参数排序后再拼 | `f(a=1,b=2)` 和 `f(b=2,a=1)` 是同一次调用，排序后指纹一致 |
| `sha1(...)[:16]` | 摘要前 16 个十六进制字符 | 查询文本可能几百字，key 太长浪费内存和 Redis 带宽；16 位十六进制 = 64 bit，撞车概率对 512 条的缓存来说约等于零 |

```python
def _jitter_ttl(ttl: float) -> float:
    return max(1.0, ttl * (1 + random.uniform(-_JITTER, _JITTER)))
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `random.uniform(-0.1, 0.1)` | ±10% 均匀随机偏移 | 100 条同时写入的缓存，过期时间散布在 90~110 秒——到期不再"齐步走" |
| `max(1.0, ...)` | 下限 1 秒 | 抖动把 0.5 秒的 TTL 抖成 0.45 会导致测试和短 TTL 场景行为怪异；1 秒下限让世界可预期 |

---

## 八、cache.py：cached 装饰器逐行解释（主流程）

装饰器是本模块的"总装车间"——数据在 L1、L2、singleflight、数据源之间的完整旅程：

```python
def cached(prefix: str, ttl: float = 300, null_ttl: float = 30):
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not settings.CACHE_ENABLED:
                return fn(*args, **kwargs)
            key = _make_key(prefix, fn, args, kwargs)
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `prefix` | 缓存 key 的前缀（"rag"/"kg"/"kgstats"） | 主动失效按前缀批量清——"数据属于哪个家族"的身份证 |
| `ttl` | 正常值的存活秒数 | 检索 300s（菜谱不常变）、图谱问答 600s（知识几乎不变）、图谱统计 60s（演示用，要求新鲜一点） |
| `null_ttl` | **空值**的存活秒数 | 30s：挡穿透够用，又不至于"新数据 5 分钟查不到" |
| `@wraps(fn)` | 把原函数的名字/文档拷给包装函数 | 没有它，函数改名成 `wrapper`——日志和调试信息全乱了 |

```python
            # ---- L1 快路径 ----
            hit = _get_l1().get(key)
            if hit is not _MISS:
                _bump("l1_hits")
                if hit[1]:
                    _bump("null_hits")
                return hit[0]
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 命中即返回 | 零网络、零序列化，纳秒级 | 90% 以上的流量应该终结在这里 |
| `hit[1]` 判断空值 | 空值命中单独计数 | `null_hits` 高 = 有人在反复查不存在的东西——这本身就是个有价值的信号 |

```python
            # ---- L2 次快路径 ----
            l2_hit = _l2_get(key)
            if l2_hit is not _MISS:
                _get_l1().put(key, l2_hit[0], l2_hit[1], ttl)   # 回填 L1
                _bump("l2_hits")
                if l2_hit[1]:
                    _bump("null_hits")
                return l2_hit[0]
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| **回填 L1** | L2 命中后顺手写进 L1 | 跨进程共享的代价只付一次：下一个请求连 Redis 都不用跑。这是多级缓存的标准姿势 |
| 回填用的 `ttl` | 按正常 TTL 回填 | L2 里的原值自己有自己的 TTL（可能只剩 3 秒），L1 重新给满 300 秒——**L1/L2 的 TTL 独立计算**，不会级联提前失效 |

```python
            # ---- 慢路径：singleflight 包住数据源 ----
            with _get_key_lock(key):
                hit = _get_l1().get(key)              # double-check
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
                    _bump("loader_errors")
                    raise
                is_null = value is None or value == [] or value == {}
                store_ttl = null_ttl if is_null else ttl
                _get_l1().put(key, value, is_null, _jitter_ttl(store_ttl))
                _l2_set(key, value, is_null, int(_jitter_ttl(store_ttl)))
                return value
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `with _get_key_lock(key)` | 同 key 并发只有第一个线程能进 | 后到的线程在锁上排队——**这就是防击穿的全部机关** |
| **double-check** | 拿到锁后再查一遍 L1/L2 | 排队期间第一个线程可能已经把结果放进去了——不复查的话队里的每个线程还会各打一遍数据源，singleflight 就白做了 |
| `raise` 不缓存异常 | 出错的原样上抛 | 缓存错误 = 把一次瞬时故障固化成 5 分钟——宁可下次重试 |
| `is_null` 三连判 | None / 空列表 / 空字典都算"查过了没有" | 空结果是合法的缓存对象（防穿透的靶子） |
| `_jitter_ttl` 两处调用 | L1 和 L2 **各自**抖动一次 | 存储层的雪崩各自防各自的（两个抖动值不同，天然错开） |
| `int(...)` 给 L2 | Redis 的 setex 要整数秒 | L1 的 TTL 是 float 没关系，L2 必须取整 |

### 主动失效

```python
def invalidate_prefix(prefix: str) -> int:
    n = _get_l1().clear_prefix(prefix)
    _l2_del_prefix(prefix)
    _bump("invalidations")
    return n
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 两层都清 | L1 按前缀删 + L2 SCAN 删 | 只清一层=另一半还是旧数据，回填机制会把旧的又灌回来 |
| 返回删除数 | 给调用方一个"清了几条"的凭据 | 导入脚本打印它，用户知道缓存真的动了 |

**一致性策略的取舍**（面试常问）：本项目用「**主动失效（写路径显式调）+ TTL 自然过期（兜底）**」，而不是"写库后删缓存/延迟双删"——因为被缓存的 rag/kg 数据的"写"只发生在导入脚本这一个入口，显式失效可控；等真有多点写入时再上更重的策略，**没有并发写就不要付并发写的复杂度**。

---

## 九、缓存接入点：为什么只挂 rag 和 kg

| 接入点 | 前缀 | TTL | 为什么安全 |
|---|---|---|---|
| `retriever.hybrid_search` | `rag` | 300s | 菜谱库是**全局知识**——所有租户看到同一份，缓存不区分租户也不会串数据 |
| `/kg/ask` | `kg` | 600s | 图谱知识同样是全局的；而且知识图谱只在重建时变 |
| `/kg/stats` | `kgstats` | 60s | 统计数字，演示用 |

**为什么不缓存别的**：

- **租户私有数据**（账单、审计、成员、配额用量）：如果缓存，key 必须带 tenant_id；一旦拼错 key，租户 A 就能"命中"租户 B 的缓存——**数据串号比慢更严重**。收益（省一次 PG 查询）远小于风险。
- **BM25 索引复用（lru_cache）**：这不是数据缓存，是**对象复用**——原来每次检索都重建 BM25 索引（分词 72 条菜谱），现在建一次进程内复用。`@lru_cache(maxsize=4)` 缓存的是"k 值 → 索引对象"。

**为什么 kg 的缓存挂在 API 层而不是 `core/kg.ask` 上**：单测会 mock 掉 Neo4j 的 `_run` 来测推理逻辑——如果 `ask` 本身带缓存，第一个测试的结果会污染后面所有测试（mock 换了、缓存还是旧的）。挂在 API 层（`_ask_cached = cached(...)(kg_module.ask)`），core 层保持纯净可测。**"缓存包在离 I/O 最近的一层"** 是可测性和性能的平衡点。

---

## 十、观测接口与压测脚本：数字怎么读

`/cache/stats` 返回的每个字段怎么读：

| 字段 | 含义 | 健康形态 |
|---|---|---|
| `l1_hits` | 进程内命中数 | 占绝对大头（最便宜） |
| `l2_hits` | Redis 命中数 | 重启后初期较高，随后被 L1 消化 |
| `misses` | 真实穿透数 | 等于"不同查询的去重数"——每条都对应一次 embedding 花费 |
| `null_hits` | 空值命中数 | 高的话看看是不是有人反复查不存在的东西 |
| `hit_rate` | 命中率 | 个人项目 0.9+ 正常；低说明查询太发散或 TTL 太短 |
| `l1_size` | L1 当前条目数 | 逼近 512 说明容量在制约（可以调 CACHE_L1_MAXSIZE） |

`bench_cache.py` 的设计意图——**公平对比**：

| 设计 | 理由 |
|---|---|
| 两轮跑同一个查询、同一个 k | 只变量是"缓存开/关"，别的一切相同 |
| 关轮只打 10 次 | 每次都真实调用 DashScope embedding——次数多了费额度也触发限流 |
| 开轮先打 1 次填充 | 把"首次 miss"排除在计时外——**测的是稳态命中性能**，不是冷启动 |
| `cache_stats_reset()` 两轮各清一次 | 计数从零开始，输出的命中率就是这一轮的真实值 |

读数要点：关轮的 QPS 数字会很难看（个位数）——**这是正常的、真实的**：它包含了 embedding 接口往返的几百毫秒。开轮的四位数 QPS 同样真实：纯内存字典读取。倍数关系（几百倍）不是吹牛，是"网络调用 vs 内存读取"的物理差距，面试被追问时讲清楚这个 gap 的构成（embedding RTT + PG 查询 + BM25 融合）就非常加分。

---

## 十一、测试设计解释：13 个单测在守护什么

| 测试 | 守护的断言 | 对应的故障场景 |
|---|---|---|
| `test_cache_hit_single_loader` | 二次调用不再穿透 | 缓存根本没生效（装饰器漏挂） |
| `test_different_args_different_key` | 不同参数各自缓存 | key 没含参数——"查什么都是同一个结果"的灾难 bug |
| `test_singleflight_concurrent` | 8 线程并发只穿透 1 次 | 防击穿失效（锁没按 key 分、或漏了 double-check） |
| `test_null_value_cached` | 空值只穿透一次 | 防穿透失效（空值没走 null_ttl 分支） |
| `test_ttl_expiry` | 过期后重新加载 | TTL 判断写错（永不过期 = 脏数据永驻） |
| `test_invalidate_prefix` | 主动失效真删了东西 | 导入新菜谱后还查到旧结果 |
| `test_jitter_bounds` | 抖动在 ±10% 内且有分布 | 防雪崩失效（抖动没生效=齐步走进化雪崩） |
| `test_stats_reset` | 清零后从零数 | 压测数字被上一轮污染 |
| `test_cache_disabled_switch` | 开关关=每次穿透 | 排障开关失灵（想关关不掉） |
| `test_select_routes_to_read` | SELECT 打到读库 | 读没分出去（读压力全压主库） |
| `test_insert_routes_to_write` | INSERT 进了写库 | 写被打去读库（数据丢失事故） |
| `test_text_clause_write_prefix` | 裸 text() INSERT 走写库 | **实测抓出的 bug 的回归测试**——防止将来重构时把 TextClause 分支删掉 |
| `test_same_engine_fallback` | 同库模式下一切如常 | DATABASE_READ_URL 为空时的回落路径 |

**两个工程化设计**：

- `autouse` fixture 强制 L1-only：`monkeypatch.setattr(cache_mod, "_l2_disabled", True)`——单测不依赖"你今天有没有起 Redis 容器"，在任何机器结果一致。
- 路由测试用两个 sqlite 文件冒充主从库 + monkeypatch 替换 `session_mod.write_engine/read_engine`：RoutingSession 的 `get_bind` 每次调用时才 `from app_my.db.session import ...` 取模块属性，**替得动**——这是把"惰性 import"从防循环依赖的技巧，额外变成了可测试性红利。

---

## 十二、常见疑问

**Q1：SQLAlchemy 已经有连接池了，为什么还要 PgBouncer？**
A：它们池的东西不同。SQLAlchemy 池的是"我这个进程到数据库的连接"，**每个进程各自为政**——4 个 uvicorn worker × 各 10 连接 = 40 条真实连接，还没算脚本和手工 psql。PgBouncer 池在"所有客户端到数据库"这一层，不管来多少进程，数据库永远只看到 20 条。前者管进程内复用，后者管全局收口。

**Q2：pool_pre_ping 和 PgBouncer 的 server_reset_query 是不是重复了？**
A：不重复。`pool_pre_ping` 是应用侧"借出连接前 SELECT 1 确认活着"（防应用↔PgBouncer 之间的死连接）；`server_reset_query` 是 PgBouncer 侧"归还真实连接前 DISCARD ALL 清状态"（防会话变量串台）。一个管链路活性，一个管状态卫生。

**Q3：为什么 L1 不直接用 Redis？进程内字典有什么不可替代的？**
A：数量级。进程内 dict 命中是**纳秒**级（无网络、无序列化），Redis 命中是**毫秒**级（TCP 往返 + JSON 解析）——差 5~6 个数量级。L2 的价值在"跨进程/跨重启共享"（后端重启 L1 全空，L2 还热着）。

**Q4：TTL 抖动 ±10%，300 秒的 TTL 也就是 ±30 秒，够防雪崩吗？**
A：够。雪崩的成因是"同一批 key **同一秒**集体失效"。300s±30s 意味着到期时间散布在 60 秒的窗口里——数据库的冲击被摊薄成持续的小流量。雪崩怕的是齐步走，不是总量。

**Q5：singleflight 为什么不顺便把"正在加载"的请求变成等待同一个 Future？**
A：threading.Lock 的"排队等结果"在语义上就是这件事的简化版（等第一个线程放完数据，double-check 后从缓存拿）。Python 的 Future/事件方案要引入线程间传值、异常广播等复杂度——**当前场景锁+double-check 已经把穿透次数压到 1，多付的复杂度换不来收益**。

**Q6：缓存了 hybrid_search，那"查询同样问题的两个不同租户"会拿到同一个结果——没问题吗？**
A：没问题，而且是**刻意设计**。菜谱知识对全体租户是同一份事实（就像维基百科的词条），共享缓存正是收益来源。需要区分租户的是"谁搜过、搜了几次"（那是配额/审计的事，阶段 4 已做，且不进缓存）。

**Q7：PgBouncer 挂了会怎样？**
A：`pool_pre_ping` 会让 SQLAlchemy 发现连接全断，报连接错误——PgBouncer 是链路一环，它挂等于数据库不可达。这不是缓存那种"增强组件"可以优雅降级的场景；好在它 10MB 内存、无状态，重启即恢复（`restart: unless-stopped` 已配自动拉起）。

**Q8：为什么 bench 不测"8 线程并发"？**
A：并发正确性已经由单测的 singleflight 测试守护（8 线程 1 穿透）。压测脚本要的是**简历数字**（QPS/延迟），单线程顺序打出的数字最干净、最好解释——并发数会成为解释数字时的第二个变量，徒增追问空间。

---

> **配套阅读**：操作手册讲"照着做"，本手册讲"为什么"；阶段 6 开工后会以本手册为基线继续演进（Milvus 检索路径天然也是 L3 数据源的一种）。
