# AI 私厨 v3.0 阶段 8 说明手册 — Celery 异步任务队列 + WebSocket 实时推送

> **本手册性质**：看懂为什么。全项目**唯一**一处逐行代码解释——每段代码都讲清"在做什么 / 为什么这么写 / 每个参数什么意思 / 这个函数为什么这么写"，让编程小白也能顺着代码看懂它是怎么跑起来、怎么达到目标的。
>
> **与《操作手册》的分工（绝不重复）**：
> - 《操作手册》= **照着做**：步骤 / 命令 / 验证 / 排错，一步不省。本手册**不写**"怎么把服务跑起来"。
> - 《说明手册》（本文件）= **看懂原理**：逐行代码 + 参数含义 + 为什么这么设计。**只此一处**有逐行解释。
>
> **怎么读**：正文每个代码块**行尾都带中文注释**，注释**不加序号**，直接把这一行的作用讲明白。代码块下面是"逐段讲解"，讲这一整段的意图、取舍和坑。首次出现的专业名词统一收进 [二、专业名词解释表](#二专业名词解释表本阶段新出现的名词)。

---

## 目录

- [〇、先建立一张"全局地图"](#〇先建立一张全局地图)
- [一、这个阶段到底解决了什么问题](#一这个阶段到底解决了什么问题)
- [二、专业名词解释表（本阶段新出现的名词）](#二专业名词解释表本阶段新出现的名词)
- [三、配置层：app_my/core/config.py（🔵修改）](#三配置层app_mycoreconfigpy修改)
- [四、任务系统的大脑：app_my/worker/celery_app.py（🟢新建）](#四任务系统的大脑app_myworkercelery_apppy新建)
- [五、任务基类：app_my/worker/base.py（🟢新建）](#五任务基类app_myworkerbasepy新建)
- [六、worker 生命周期信号：app_my/worker/signals.py（🟢新建）](#六worker-生命周期信号app_myworkersignalspy新建)
- [七、跨进程事件通知：app_my/core/notify.py（🟢新建）](#七跨进程事件通知app_mycorenotifypy新建)
- [八、worker 自己的指标：app_my/core/worker_metrics.py（🟢新建）](#八worker-自己的指标app_mycoreworker_metricspy新建)
- [九、三个长任务：app_my/worker/tasks/（🟢新建 4 个文件）](#九三个长任务app_myworkertasks新建-4-个文件)
- [十、WebSocket 连接管理器：app_my/ws/manager.py（🟢新建）](#十websocket-连接管理器app_mywsmanagerpy新建)
- [十一、WebSocket 网关：app_my/ws/gateway.py（🟢新建）](#十一websocket-网关app_mywsgatewaypy新建)
- [十二、Redis 订阅中继：app_my/ws/relay.py（🟢新建）](#十二redis-订阅中继app_mywsrelaypy新建)
- [十三、接口层：app_my/schemas/tasks.py + app_my/api/tasks.py（🟢新建）](#十三接口层app_myschemastaskspy--app_myapitaskspy新建)
- [十四、入口接线：main.py（🔵修改）](#十四入口接线mainpy修改)
- [十五、前端实时客户端：frontend/js/ws.js（🟢新建）](#十五前端实时客户端frontendjswsjs新建)
- [十六、验收脚本：scripts/verify_stage8.py（🟢新建）](#十六验收脚本scriptsverify_stage8py新建)
- [十七、可观测接线：docker/prometheus 两个 yml（🔵修改）](#十七可观测接线dockerprometheus-两个-yml修改)
- [十八、单元测试怎么验证这套机制](#十八单元测试怎么验证这套机制)
- [附：一条数据的完整旅程（把全链路串起来）](#附一条数据的完整旅程把全链路串起来)

---

## 〇、先建立一张"全局地图"

阶段 8 之前，项目是**一个进程**：浏览器请求进来 → FastAPI 处理 → 返回。遇到"重索引要跑 1 分钟"这种活，浏览器就只能干等，而且这个请求会一直占着 FastAPI 的并发额度。

阶段 8 之后，变成了**三方协作**。先把三方的角色记牢，后面所有代码都围绕它们展开：

| 角色 | 是谁 | 在这个阶段干什么 | 代码位置 |
|---|---|---|---|
| **提交方（API 进程）** | 一直在跑的 FastAPI（`main.py`） | 收到请求 → 把任务"塞进 Redis 队列" → **立刻**返回 `task_id` | `app_my/api/tasks.py` |
| **执行方（worker 进程）** | 单独启动的一个 Celery 进程 | 从 Redis 队列取任务 → 真正干活 → 干完把结果写回 Redis、并发一条通知 | `app_my/worker/` |
| **接收方（浏览器）** | 前端页面 | 拿着 `token` 连上 WebSocket → 等 worker 的通知弹出来 | `frontend/js/ws.js` |

三者之间靠 **Redis 6380** 打通。Redis 在这里被拆成三个互不干扰的"格子"（db）：

- **db0** —— 老业务（缓存 / 限流 / 配额 / JWT 黑名单），阶段 8 **不碰**。
- **db1** —— 任务队列（broker）：API 往里塞任务，worker 从里取任务。
- **db2** —— 任务结果（result backend）：worker 把结果写这里，API 的 `GET /tasks/{id}` 从这读。

再加一条**通知专线**：worker 干完活，往 Redis 的一个"广播频道"（`ai_chief:ws:notify`）喊一嗓子；FastAPI 进程里有个常驻协程一直在听这个频道，一听到就把消息转发给它登记的浏览器连接。

```text
                    ┌─────────────────────── Redis 6380 ───────────────────────┐
                    │  db0 业务         db1 任务队列       db2 任务结果           │
                    │  (不动)          (broker)          (backend)             │
                    │                     ▲   │                                │
   ①POST /tasks/... │                     │   │ ④取任务                        │
  ┌───────────┐     │                     │   │              ┌─────────────┐   │
  │  API 进程 │─────┼─②塞任务─────────────┘   └──────────────│  worker 进程│   │
  │ (main.py) │     │                                       │  (celery)   │   │
  └─────┬─────┘     │  ⑤写结果 ────────────────────────────────┘   │         │
        │           │                                             │         │
        │           │  ⑥往频道 ai_chief:ws:notify 喊一嗓子 ◀───────┘         │
        │           └───────────────────────┬─────────────────────────────────┘
        │                                   │
        │ ⑦中继协程一直在听这个频道          │
        └───────────────────────────────────┘
        │
        │ ⑧按 tenant_id 找到对应浏览器连接，推送
        ▼
  ┌───────────┐
  │  浏览器    │  WebSocket: /ws/notifications?token=xxx
  └───────────┘
```

**记住这条主线**：`HTTP 提交 → Redis 队列 → worker 执行 → Redis 广播 → 中继转发 → 浏览器收到`。后面讲每个文件，都是在讲"这条线的哪一段是它负责的"。

---

## 一、这个阶段到底解决了什么问题

### 1.1 同步 = 阻塞，异步 = 解耦

先看**阶段 8 之前**的做法（示意）：

```text
浏览器点"重建图谱" → FastAPI 里直接执行 build()
                   → 光建图要 30 秒
                   → 这 30 秒里：浏览器转圈、这个请求占着连接、万一超时全白干
```

问题有三个：
1. **用户体验差**：页面卡几十秒，不知道死没死。
2. **资源被占**：FastAPI 的并发能力被一个长任务拖住。
3. **不可观测**：任务跑没跑完、跑了几次、慢在哪，全在日志里翻。

**阶段 8 之后**：

```text
浏览器点"重建图谱" → FastAPI 只做一件事：把"重建图谱"这 4 个字塞进 Redis 队列（毫秒级）
                   → 立刻返回 {task_id: "abc-123"}
                   → 浏览器拿着 task_id 继续干别的
                   → 几十秒后，worker 干完了，主动推一条 WebSocket 消息："你的 abc-123 成功啦，结果是..."
                   → 浏览器右下角弹个提示
```

对应到代码，就是四块拼图：

| 拼图 | 解决上面哪个问题 | 关键文件 |
|---|---|---|
| **Celery 任务队列** | 让"执行"和"请求"解耦，请求不再等 | `worker/celery_app.py`、`worker/tasks/*` |
| **三条分级队列** | 让"重索引"别把"营养报告"堵死 | `celery_app.py` 里的 `task_routes` |
| **WebSocket 推送** | 让浏览器"被通知"而不是"反复问" | `ws/` 三个文件 |
| **worker 独立指标** | 让后台任务也能被 Prometheus 监控 | `core/worker_metrics.py` |

### 1.2 为什么不用 HTTP 轮询，非要用 WebSocket？

"任务跑完了怎么告诉浏览器"有两种常见做法：

| 方案 | 怎么工作 | 缺点 |
|---|---|---|
| **轮询（polling）** | 浏览器每 2 秒问一次 `GET /tasks/{id}`："好了吗？好了吗？" | 大部分请求是空跑，浪费带宽和服务端资源；消息还有延迟（最多 2 秒） |
| **WebSocket** | 建一条**长连接**，worker 一有结果就**主动推**过来 | 需要维护长连接（断线要重连、空闲要心跳） |

阶段 8 选 WebSocket，因为项目里"任务完成通知"是一类会持续增长的需求（以后还有告警、系统公告），长连接一次建好，后面所有实时消息都走它。代价就是必须处理"断线重连"和"心跳保活"——这两个正是 `frontend/js/ws.js` 的主要工作量。

---

## 二、专业名词解释表（本阶段新出现的名词）

> 这张表覆盖本阶段**首次出现**的名词。遇到看不懂的词，先回这里查。按"概念 → 在项目里的具体体现"写，不只给字典定义。

| 名词 | 一句话解释 | 在本项目里的具体体现 |
|---|---|---|
| **Celery** | Python 世界最常用的"分布式任务队列"框架。作用：把"要干的活"从请求里摘出来，交给别的进程慢慢干。 | `app_my/worker/celery_app.py` 里那个 `celery_app` 实例。 |
| **任务（task）** | 被 Celery 管理的一段函数。它跟你写的普通函数几乎一样，只是加了个 `@celery_app.task` 装饰器。 | `reindex_milvus` / `rebuild_kg_graph` / `generate_nutrition_report` 三个函数。 |
| **broker（消息代理）** | 存放"待执行任务"的地方。任务先放这里排队，worker 来取。 | Redis `db1`（`redis://localhost:6380/1`）。 |
| **result backend（结果后端）** | 存放"任务执行结果"的地方。API 用它回答"那个任务跑完没、结果是什么"。 | Redis `db2`（`redis://localhost:6380/2`）。 |
| **worker（工作者进程）** | 真正执行任务的独立进程。它从 broker 取任务、跑完把结果写 backend。 | 用 `celery -A ... worker` 单独启动的那个进程。 |
| **队列（queue）** | broker 里的一条"待办列表"。任务按顺序排队，worker 按顺序取。 | `high` / `default` / `low` 三条。 |
| **队列分级 / 削峰** | 按任务重要性分到不同队列，让重要的先跑；积压的任务在队列里排着，慢慢被消费，避免瞬间压垮系统。 | `task_routes` 把重索引送 `high`、图谱重建送 `default`、营养报告送 `low`。 |
| **路由（task_routes）** | 一条"任务名 → 哪条队列"的对照表。 | `celery_app.conf.task_routes` 里那三行。 |
| **`.delay()`** | Celery 的固定写法：把函数 + 参数序列化后投进队列，**立刻**返回一个含 `id` 的结果对象（不等任务跑完）。 | `app_my/api/tasks.py` 里 `reindex_milvus.delay(...)`。 |
| **AsyncResult** | 一个"查询句柄"。拿 `task_id` 构造它，就能问"这任务现在什么状态"。 | `celery.result.AsyncResult(task_id, app=celery_app)`。 |
| **PENDING / STARTED / SUCCESS / FAILURE** | Celery 任务的四种状态：排队中 / 正在跑 / 成功 / 失败。 | `GET /tasks/{task_id}` 返回的 `status` 字段。 |
| **ack（确认）/ acks_late** | worker 收到任务后要不要"回执"。`acks_late=True` = 任务**跑完**才回执，worker 中途崩了任务会被重新投递（不丢活儿）。 | `celery_app.conf` 里 `task_acks_late=True`。 |
| **prefetch（预取）** | worker 一次从队列里"囤"多少条任务到本地内存。囤多了，长任务会把短任务卡在后面。 | `worker_prefetch_multiplier=1`，一次只拿一条。 |
| **eager 模式** | Celery 的"假装有队列"模式。打开后 `.delay()` 不进队列，**当场同步执行**。专门给单元测试用。 | `task_always_eager`（单测里设 `True`）。 |
| **pub/sub（发布 / 订阅）** | Redis 的一种广播机制：一个进程往"频道"发消息，所有订阅了这个频道的进程都能收到。 | worker 发到 `ai_chief:ws:notify`，FastAPI 中继订阅它。 |
| **中继（relay）** | 中间转发的环节。这里指 FastAPI 里那个"从 Redis 收消息 → 转发给浏览器"的常驻协程。 | `app_my/ws/relay.py` 的 `run_relay()`。 |
| **协程（coroutine）** | `async def` 定义的函数，可以在"等待"时让出 CPU 给别的活干，但不新开线程。 | `run_relay` / `dispatch` / `ws_notifications` 都是协程。 |
| **连接管理器** | 一张"当前有哪些浏览器连着我、分别属于哪个租户"的登记表。 | `app_my/ws/manager.py` 的 `ConnectionManager`。 |
| **单例（singleton）** | 整个进程只有一份的全局对象。连接表必须全局唯一，否则推不到。 | `manager = ConnectionManager()`。 |
| **租户隔离** | 多租户系统里，A 租户的数据/消息**绝不能**跑到 B 租户那里。 | 连接按 `tenant_id` 分组，`dispatch` 只推同组连接。 |
| **心跳（heartbeat）/ 保活** | 长连接空闲太久可能被路由器/代理掐断。定期发个小包（`ping`），证明"我还活着"。 | 前端每 25 秒发 `"ping"`，服务端回 `{"type":"pong"}`。 |
| **指数退避（exponential backoff）** | 断线重连时，等待时间一次比一次长（1s → 2s → 4s → …封顶），避免疯狂重试把服务端打挂。 | `ws.js` 里 `BASE_DELAY * 2^retryCount`，最多 15 秒。 |
| **toast** | 页面角落自动出现、几秒后自动消失的小提示条。 | `ws.js` 的 `toast()` 函数（右下角）。 |
| **WebSocket 握手** | 从 HTTP 升级到 WebSocket 长连接的那一次"打招呼"。 | 前端 `new WebSocket(url)`；服务端 `@router.websocket`。 |
| **1008（关闭码）** | WebSocket 协议里表示"策略违规"。本项目用它表示"你没通过鉴权，别连了"。 | `gateway.py` 里 `WS_CLOSE_POLICY_VIOLATION = 1008`。 |
| **Counter / Gauge / Histogram** | Prometheus 三种指标类型：只增不减的计数 / 可增可减的当前值 / 按区间统计分布的直方图。 | `core/worker_metrics.py` 里的四个指标。 |
| **直方图（Histogram）** | 把"耗时"这类数值按区间（桶）统计"有多少次落在 0~0.1s、多少次落在 0.1~0.5s…"。 | `CELERY_TASK_DURATION` + `buckets=(0.1, 0.5, ...)`。 |
| **幂等（idempotent）** | 同样的操作执行一次和执行多次，结果一样（不会重复产生副作用）。 | 重索引用 `recipe_id` 覆盖写；图谱用 `MERGE` 合并。 |
| **DRY 原则** | "Don't Repeat Yourself"——同一份逻辑不要写两遍，避免改一处漏一处。 | 图谱任务直接复用 `scripts/init_kg.py` 的 `build()`，不复制 Cypher。 |
| **发布订阅频道（channel）** | pub/sub 里"面向谁广播"的名字。 | `WS_NOTIFY_CHANNEL = "ai_chief:ws:notify"`。 |
| **scope（作用域）** | Starlette 里表示"这是一个 HTTP 请求还是 WebSocket 连接"的标记。 | HTTP 中间件只处理 `"http"`，不碰 `"websocket"`（这是个大坑，见第十一节）。 |

---
## 三、配置层：app_my/core/config.py（🔵修改）

### 3.1 改了什么、为什么改这里

阶段 8 引入了 6 个新的"可调参数"（broker 地址、结果地址、eager 开关等）。项目里所有配置都集中在一个地方——`app_my/core/config.py` 的 `Settings` 类。**为什么集中**：这样任何模块只要 `from app_my.core.config import settings` 就能读到全部配置，不用到处硬编码字符串；改地址只改一处。这就是"配置与代码分离"。

在 `PROMETHEUS/LOKI` 段之后、`CORS` 段之前，**插入**这一段（🟢新增，其余原有内容不动）：

```python
    # ============================================================
    # 异步任务 + 实时推送（v3 阶段 8 新增）
    # ============================================================
    # Celery broker / result backend：复用阶段 1 起的 Redis 6380，只换 db 编号隔离
    #   现有业务（缓存 / 限流 / 配额 / JWT 黑名单）用 db 0；
    #   broker 用 db 1、result backend 用 db 2 —— 三个 db 互不撞键
    CELERY_BROKER_URL: str = "redis://localhost:6380/1"        # 任务"寄存在哪"：worker 从这里取任务
    CELERY_RESULT_BACKEND: str = "redis://localhost:6380/2"    # 任务结果"存在哪"：API 从这里查状态
    CELERY_TASK_ALWAYS_EAGER: bool = False                     # True = 不进 worker，调用即本地同步执行（单测用）
    CELERY_TASK_RESULT_EXPIRES: int = 3600                     # 任务结果在 Redis 里保留 1 小时，过期自动清
    WORKER_METRICS_PORT: int = 9101                            # Celery worker 自己的指标端口（Prometheus 抓这里）
    WS_NOTIFY_CHANNEL: str = "ai_chief:ws:notify"              # 任务事件走这个 Redis 频道（worker 发、WS 网关收）
```

### 3.2 逐行讲解

| 字段 | 类型 | 值 | 作用 & 为什么是这个值 |
|---|---|---|---|
| `CELERY_BROKER_URL` | `str` | `redis://localhost:6380/1` | 任务队列的地址。**db 选 1**：项目原来所有 Redis 用法都在 `db0`（缓存、限流计数、JWT 黑名单）。如果 broker 也用 db0，Celery 的队列键（`high`/`default`/`low`）可能和业务键撞名或互相 `flush`。换到 db1 就物理隔离了——Redis 的 `SELECT 1` 和 `SELECT 0` 是两套完全独立的键空间。 |
| `CELERY_RESULT_BACKEND` | `str` | `redis://localhost:6380/2` | 任务结果存放地址。**db 选 2**：结果键是 `celery-task-meta-<task_id>`，量会随任务数增长，并且会设置过期时间自动清理。单独放 db2，即使某天结果堆积也不会影响队列（db1）和业务（db0）。 |
| `CELERY_TASK_ALWAYS_EAGER` | `bool` | `False` | 默认关闭。一旦设成 `True`，`.delay()` 就不进 Redis 队列，而是**当场在本进程同步执行**。生产绝不能开（开了就没有"异步"了），它存在的唯一理由是**单元测试**：测试里不想为了跑一个任务去启 worker，就打开它。 |
| `CELERY_TASK_RESULT_EXPIRES` | `int` | `3600`（秒） | 任务结果在 backend 里保留多久。不设的话结果会永远堆在 Redis 里，时间一长内存涨。1 小时足够前端"事后复查"，过期自动删。 |
| `WORKER_METRICS_PORT` | `int` | `9101` | worker 进程暴露 Prometheus 指标的端口。**为什么和阶段 7 的 9002 分开**：9002 是 FastAPI 进程的 `/metrics`，装的是 HTTP 相关指标；worker 是另一个进程，抓不到 FastAPI 的内存指标，必须自己开一个口。两个端口一个 job 抓一个，互不干扰。 |
| `WS_NOTIFY_CHANNEL` | `str` | `ai_chief:ws:notify` | Redis pub/sub 的频道名。worker 往这个名字发，FastAPI 中继订阅这个名字收。**带前缀 `ai_chief:`** 是为了在 Redis 里一眼看出"这是本项目的键"，也能避免和别人的频道撞名。 |

> 🟡 **为什么类型注解非写不可**：`Settings` 用的是 Pydantic。写了 `bool` / `int`，环境变量里的字符串 `"true"` / `"3600"` 会被**自动转换**成 `True` / `3600`；不写注解，从 `.env` 读进来就是字符串，后面 `if settings.CELERY_TASK_ALWAYS_EAGER:` 会把字符串 `"false"` 判成真（非空字符串永远为真）——这是新手极易踩的坑。

---

## 四、任务系统的大脑：app_my/worker/celery_app.py（🟢新建）

### 4.1 这个文件是什么

它是整个任务系统的**唯一实例**，三处地方共用同一个它：

1. **API 进程**：提交任务（`.delay()`）和查结果（`AsyncResult`）都用它；
2. **worker 进程**：启动命令 `celery -A app_my.worker.celery_app:celery_app worker ...` 就是加载它；
3. **单元测试**：打开 eager 模式后，用它来"当场跑任务"。

**为什么只建一个**：如果 API 用一个配置、worker 用另一个，就会出现"API 以为任务在 high 队列、worker 只盯 default 队列"这种对不上的事故。共用一个实例 = 配置天然一致。

### 4.2 完整代码（行尾注释即逐行解释）

```python
from celery import Celery        # Celery 主类，用它创建应用实例
from kombu import Queue          # kombu 是 Celery 的底层消息库；Queue 用来声明队列

from app_my.core.config import settings    # 读上一节的配置（地址、开关都从这里来）

celery_app = Celery("ai_chief")   # 创建实例，名字 "ai_chief" 会出现在任务名/日志里

celery_app.conf.update(           # 一次性把全部配置灌进去
    # ---- 连接 ----
    broker_url=settings.CELERY_BROKER_URL,                    # 任务寄存在 Redis db1
    result_backend=settings.CELERY_RESULT_BACKEND,            # 结果放 Redis db2
    broker_connection_retry_on_startup=True,                  # 启动时 broker 暂时连不上就重试，而不是直接崩

    # ---- 序列化 ----
    task_serializer="json",                                   # 任务参数序列化成 JSON
    result_serializer="json",                                 # 任务结果序列化成 JSON
    accept_content=["json"],                                  # 只接受 JSON，拒绝 pickle

    # ---- 时间 ----
    timezone="Asia/Shanghai",                                 # 展示用时区
    enable_utc=True,                                          # 但内部一律按 UTC 存，避免夏令时/跨时区错乱

    # ---- 可靠性 ----
    task_acks_late=True,                                      # 跑完才确认；worker 崩溃任务会自动重投，不丢
    worker_prefetch_multiplier=1,                             # 一次只预取一条，长任务不囤积
    task_track_started=True,                                  # 允许状态出现 STARTED（否则只有 PENDING→SUCCESS）
    result_expires=settings.CELERY_TASK_RESULT_EXPIRES,       # 结果保留 1 小时后自动清

    # ---- 三条队列 + 任务分级路由 ----
    task_default_queue="default",                             # 没配路由的任务默认进 default
    task_queues=(Queue("high"), Queue("default"), Queue("low")),   # 显式声明三条队列
    task_routes={                                             # 任务名 → 队列 的对照表
        "tasks.reindex_milvus": {"queue": "high"},            # 运维级：向量库重索引，最要紧
        "tasks.rebuild_kg_graph": {"queue": "default"},       # 数据级：图谱重建
        "tasks.generate_nutrition_report": {"queue": "low"},  # 用户级：营养报告，繁但不急
    },

    # ---- 本地/单测：不进 worker，调用即同步执行 ----
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,      # 默认 False；单测里设 True
    task_eager_propagates=True,                               # eager 下任务异常直接抛出（测试才看得见）
    task_store_eager_result=True,                             # eager 的结果也写 backend（GET /tasks 查得到）

    # ---- 启动时要 import 哪些模块，任务才会被注册 ----
    imports=(
        "app_my.worker.tasks.reindex",        # 注册 reindex_milvus 任务
        "app_my.worker.tasks.graph",          # 注册 rebuild_kg_graph 任务
        "app_my.worker.tasks.nutrition",      # 注册 generate_nutrition_report 任务
        "app_my.worker.signals",              # 注册 worker 生命周期信号（起指标服务等）
    ),
)
```

### 4.3 逐项讲解（每一行"不写会怎样"）

**① 连接三行**

- `broker_url`：不写则默认 `amqp://guest@localhost`（RabbitMQ）。本机没有 RabbitMQ，worker 会连不上直接失败。
- `result_backend`：不写则"结果无处可存"，`GET /tasks/{id}` 永远返回 `PENDING`（因为没人记录它变成 SUCCESS 了）。
- `broker_connection_retry_on_startup=True`：Docker 容器重启时 Redis 可能比 worker 晚几秒起来。不写这个，worker 一启动连不上就**直接退出**；写了它，worker 会自己重试。

**② 序列化三行**

- `task_serializer="json"` / `result_serializer="json"`：任务参数和结果都转成 JSON 传输。
- `accept_content=["json"]`：**只接受 JSON**。默认的 `pickle` 能在反序列化时执行任意代码，如果 broker 被攻击者写入恶意 payload 会变成远程代码执行漏洞（RCE）。生产环境必须锁成 JSON——这是个**安全项**，不是可选项。

**③ 时间两行**

- `timezone="Asia/Shanghai"` 管"给人看的时间"，`enable_utc=True` 管"内部存的时间"。两者配合：内部统一 UTC（不会有夏令时切换导致的时刻错乱），展示时转成北京时间。

**④ 可靠性四行（这一组是"任务不丢、不卡"的关键）**

| 配置 | 含义 | 不写会怎样 |
|---|---|---|
| `task_acks_late=True` | worker **跑完**任务才向 broker 确认"我收到了"。 | 默认（`False`）是"一拿到就确认"。如果任务跑到一半 worker 崩了，消息已经确认过了，任务就**永久丢了**。`True` 则重启后重新投递。 |
| `worker_prefetch_multiplier=1` | worker 一次只从队列里"预取"一条到本地。 | 默认是 4。设想 high 队列里排着 1 个重索引 + 4 个紧急小任务，某个 worker 一口气预取了 4 条（含重索引），然后卡在重索引上 1 分钟，那 3 个小任务就在它本地内存里干等。设 1 就"拿一条跑一条"。 |
| `task_track_started=True` | 任务开始执行时把状态写成 `STARTED`。 | 不写则状态从 `PENDING` 直接跳到 `SUCCESS`，前端**看不到"正在跑"**这个中间态，进度提示做不了。 |
| `result_expires=3600` | 结果 1 小时后自动删。 | 不写则结果永久堆积，Redis 内存只涨不降。 |

**⑤ 队列与路由（本阶段的"分级"核心）**

```python
task_default_queue="default",                              # 兜底队列
task_queues=(Queue("high"), Queue("default"), Queue("low")),  # 声明三条队列
task_routes={ "任务名": {"queue": "哪条队列"} },              # 路由表
```

- `task_queues` 里 `Queue("high")` 是**声明**："我要用一条叫 high 的队列"。Redis 是"用了才有"的，声明之后 Celery 才知道要监听它。
- `task_routes` 是**路由表**：里面写的 `"tasks.reindex_milvus"` 不是 Python 函数名，而是任务在 `@celery_app.task(name=...)` 里注册的**全局任务名**。这一点很关键——路由匹配用的是字符串名字，写错一个字母任务就悄悄跑到 default 队列去了（不会报错）。
- **为什么重索引给 `high`**：它是运维操作，跑一次要几十次 embedding 调用，且"数据对不对"直接影响线上检索质量，必须优先跑完。营养报告给 `low`：它是用户随手点的，慢几秒无所谓。

**⑥ eager 三行（只影响单测）**

- `task_always_eager`：默认 `False`。单测里临时设 `True`，`.delay()` 就在当前进程同步跑。
- `task_eager_propagates=True`：eager 模式下任务抛异常**直接往外抛**，测试里 `pytest.raises` 才能断言到错误。不写的话异常被吞掉，测试看不到失败。
  > 🔴 **这里有个隐藏行为**（阶段 8 实测才发现）：`task_eager_propagates=True` 时，任务抛异常会**跳过 `on_failure` 钩子**（Celery 源码 `celery/app/trace.py` 的 `on_error` 里：`if propagate: raise` 直接抛）。所以"测试失败路径"时要**另开一个 propagates=False 的实例**，否则 `on_failure` 里的指标/通知不会被触发。详见 [五、base.py](#五任务基类app_myworkerbasepy新建) 第 5.5 节。
- `task_store_eager_result=True`：让 eager 跑出来的结果也写进 backend，这样 `GET /tasks/{id}` 在测试里也查得到（否则 eager 结果不落盘）。

**⑦ `imports`（任务发现）**

worker 启动时怎么知道"有哪些任务"？靠 `imports` 里列的模块——Celery 挨个 `import` 它们，`@celery_app.task` 装饰器被执行，任务就被注册进注册表。**不写 `imports`，worker 起来会显示"没有任务"**（`[tasks]` 列表为空），提交任务时报 `Received unregistered task`。四项里前三项是任务模块，第四项 `signals` 注册生命周期回调。

---
## 五、任务基类：app_my/worker/base.py（🟢新建）

### 5.1 为什么要有"基类"

三个任务跑完后要做的**附带动作完全一样**：记指标、发通知、算耗时。如果每个任务函数里都抄一遍这三件事，就会出现"改了通知格式要改三个文件"的维护噩梦。

Celery 允许你定义一个**任务基类**，它预留了若干"生命周期钩子"（框架在特定时刻自动调用的方法）。把这些附带动作写进基类的钩子，业务任务就只管"自己的活"。

Celery 的四个人生钩子：

| 钩子 | 什么时候被调用 | 本项目是否用 |
|---|---|---|
| `before_start(task_id, args, kwargs)` | 任务真正开跑**之前** | ✅ 发 STARTED |
| `on_success(retval, task_id, args, kwargs)` | 任务**正常返回** | ✅ 发 SUCCESS |
| `on_failure(exc, task_id, args, kwargs, einfo)` | 任务**抛异常** | ✅ 发 FAILURE |
| `after_return(...)` | 无论成败**都会**跑 | ❌ 本阶段不用 |

> **约定**：所有任务的最后两个关键字参数都叫 `tenant_id` / `user_id`。基类统一从 `self.request.kwargs` 里取，就知道"这条通知该推给谁"。这就是"参数命名约定"的力量——基类不需要知道每个任务具体参数，只认这两个名字。

### 5.2 `_read_ctx()`：从一个任务请求里取出三样东西

```python
def _read_ctx(request) -> tuple:                  # 入参是 Celery 的任务请求上下文对象
    kwargs = getattr(request, "kwargs", None) or {}   # kwargs 可能不存在 → 兜底成空字典，绝不 AttributeError
    tenant_id = int(kwargs.get("tenant_id") or 0)     # 取出租户号；缺省 0；int() 转成整数
    user_id = int(kwargs.get("user_id") or 0)         # 取出用户号；缺省 0

    delivery = getattr(request, "delivery_info", None) or {}   # delivery_info 是"投递信息"，含路由键
    queue = delivery.get("routing_key")                        # 真实 worker 跑时，这里就是实际队列名
    if not queue:                                              # routing_key 为空（eager 模式没有 broker）
        name = getattr(request, "task", "") or ""              # 拿到任务名，如 tasks.reindex_milvus
        route = (celery_app.conf.task_routes or {}).get(name) or {}   # 去路由表里查它该去哪条队列
        queue = route.get("queue") or celery_app.conf.task_default_queue or "default"   # 查不到再兜底 default
    return tenant_id, user_id, queue                           # 三样一起返回
```

**为什么队列要"回退查 task_routes"**（这是实测踩出来的一个坑）：

- 真实 worker 执行时，`request.delivery_info.routing_key` 就是**实际队列名**（`high`/`default`/`low`），直接用就对。
- 但**本地 eager 模式**（单测）没有 broker，`routing_key` 是 `None`。

如果不做回退，单测里指标标签会退化成 `default`，而线上是 `low` —— **同一段代码在测试和线上打出不同的指标标签**，Grafana 面板就会对不上。回退查 `task_routes` 保证两种模式下标签完全一致。

> 💡 注意这里用了 `getattr(x, "attr", None) or {}` 这个模式三连。它同时防两件事：① 属性不存在（`getattr` 给默认 `None`）；② 属性存在但是 `None`（`or {}` 兜底成空字典）。因为 `.get()` 只能在字典上调用，`None.get()` 会崩。这是"防呆代码"的标准写法。

### 5.3 基类本体

```python
class NotifyTask(Task):        # 继承 Celery 的 Task 基类
    """带"事件通知 + 指标"的任务基类；业务任务用它作 base 即可。"""

    abstract = True            # 抽象基类：Celery 不会把它本身当成一个可调用的任务

    def before_start(self, task_id, args, kwargs):     # 任务开跑前自动调用
        """任务开跑前：记开始时间、记 STARTED 指标、发 STARTED 通知"""
        self._s8_t0 = time.perf_counter()              # 用高精度计时器记下起点，挂在 self 上供后面算耗时
        tenant_id, user_id, queue = _read_ctx(self.request)   # 取出"推给谁 + 哪条队列"
        try:
            task_started(self.name, queue)             # 指标：STARTED 计数 +1
            publish_task_event(
                build_task_event(task_id, self.name, "STARTED", tenant_id=tenant_id, user_id=user_id)
            )                                          # 通知：把一条 STARTED 事件发去 Redis 频道
        except Exception as exc:                       # 通知/指标是"附带动作"
            logger.warning("NotifyTask: STARTED 通知失败（忽略）: %s", exc)   # 出问题只记警告，绝不影响任务本身

    def on_success(self, retval, task_id, args, kwargs):   # 任务成功返回后自动调用，retval 是函数返回值
        """任务成功：算耗时、记 SUCCESS 指标、发 SUCCESS 通知（把结果一起带走）"""
        tenant_id, user_id, queue = _read_ctx(self.request)
        seconds = time.perf_counter() - getattr(self, "_s8_t0", time.perf_counter())   # 耗时；没起点就用当前时刻当起点（=0）
        try:
            task_succeeded(self.name, queue, seconds)  # 指标：SUCCESS 计数 +1 + 耗时入直方图
            publish_task_event(
                build_task_event(task_id, self.name, "SUCCESS", result=retval,
                                 tenant_id=tenant_id, user_id=user_id)
            )                                          # 通知：带上任务结果一起发
        except Exception as exc:
            logger.warning("NotifyTask: SUCCESS 通知失败（忽略）: %s", exc)

    def on_failure(self, exc, task_id, args, kwargs, einfo):   # 任务抛异常后自动调用，exc 是异常对象
        """任务失败：算耗时、记 FAILURE 指标、发 FAILURE 通知（把错误摘要带走）"""
        tenant_id, user_id, queue = _read_ctx(self.request)
        seconds = time.perf_counter() - getattr(self, "_s8_t0", time.perf_counter())
        summary = f"{type(exc).__name__}: {exc}"[:500]     # 错误摘要截断到 500 字，通知没必要带超长堆栈
        try:
            task_failed(self.name, queue, seconds)     # 指标：FAILURE 计数 +1 + 失败计数 +1 + 耗时入直方图
            publish_task_event(
                build_task_event(task_id, self.name, "FAILURE", error=summary,
                                 tenant_id=tenant_id, user_id=user_id)
            )                                          # 通知：带上错误摘要
        except Exception as inner:
            logger.warning("NotifyTask: FAILURE 通知失败（忽略）: %s", inner)
```

### 5.4 逐点讲解

**① `abstract = True`**

不加这一行，Celery 会把 `NotifyTask` 本身当成一个"任务"注册进去。加了它，只是"模板"，不注册、不能 `.delay()`。所有业务任务通过 `base=NotifyTask` 继承它。

**② `self._s8_t0 = time.perf_counter()`**

- 用 `time.perf_counter()` 而不是 `time.time()`：`perf_counter` 是**单调递增**的高精度时钟，不受系统时间被手动调整/对时影响，用它算"耗时"才准。
- `_s8_t0` 命名带 `s8` 前缀（stage8）是为了避免和 Celery 内部的属性名撞车。
- 挂在 `self` 上：`before_start` 存，`on_success`/`on_failure` 取。用 `getattr(self, "_s8_t0", time.perf_counter())` 兜底——万一 `before_start` 没跑（异常路径），也不会 `AttributeError`。

**③ 三个 `try / except Exception`**

这是**最关键的设计决策**：通知和指标是"锦上添花"。如果 Redis 抽风导致 `publish` 失败，**绝不能**因此把任务标记成失败——任务本身已经成功了。所以整个附带动作包在 `try` 里，出错只 `logger.warning` 记一笔。这叫**降级**：核心功能与辅助功能解耦，辅助功能坏了不影响核心。

**④ `f"{type(exc).__name__}: {exc}"[:500]`**

- `type(exc).__name__` 拿到异常类名（如 `ValueError`），`{exc}` 拿异常消息（如 `ingredients 不能为空`）。拼成 `"ValueError: ingredients 不能为空"`。
- `[:500]` 截断到 500 字符。某些异常的 `str()` 可能是几百行堆栈，塞进 WebSocket 消息里既没意义又拖慢传输。

### 5.5 那个"隐藏行为"再讲清楚

在 `task_eager_propagates=True` 下跑失败任务时，`on_failure` **不会被调用**。原因在 Celery 源码 `trace.py`：

```python
# 简化后的 Celery 源码
def on_error(self, ...):
    if propagate:      # 如果配置了 task_eager_propagates=True
        raise          # 直接把异常抛出去 —— on_failure 的调用被跳过了
    ...                # 否则才走 on_failure
```

**影响**：单测里想验证"任务失败 → FAILURE 指标 +1"时，用默认配置会失败（因为 `on_failure` 压根没跑）。

**解决**：测试里另建一个 `eager_non_propagates` 配置（`task_eager_propagates=False`），这样异常走正常路径、`on_failure` 被调用。这就是"读源码才发现的坑"——光看文档看不出来。

---

## 六、worker 生命周期信号：app_my/worker/signals.py（🟢新建）

### 6.1 什么是"信号"

Celery 的信号（signal）= 框架在特定时刻"广播"的事件。你挂一个回调（`@signal.connect`）进去，那一刻框架就自动调用你的函数。相当于 Celery 给你留的"插件接口"。

本项目用两个：

| 信号 | 触发时机 | 我们干什么 |
|---|---|---|
| `worker_ready` | worker **启动完成**那一刻（只触发一次） | 启动指标 HTTP 服务 + 首次读队列长度 |
| `task_postrun` | **每个任务跑完**之后 | 刷新队列长度 |
| `worker_shutdown` | worker 关闭时 | 记一条日志 |

**为什么队列长度要在 worker 里量**：队列长度本质是"Redis 里那个 list 有多长"（`LLEN high`）。API 进程不知道 worker 的消费情况，worker 自己最清楚，所以由 worker 侧定时量、写进指标。Prometheus 抓 worker 的 `:9101/metrics` 就能看到积压趋势。

### 6.2 完整代码

```python
from celery.signals import task_postrun, worker_ready, worker_shutdown   # 导入要挂的三个信号

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.core.worker_metrics import queue_depth, start_metrics_server

_IS_WORKER = False          # 只有真正的 worker 进程在 worker_ready 后才会置 True
_METRICS_STARTED = False    # start_http_server 只能调一次，防止重复启动报端口占用
QUEUES = ("high", "default", "low")    # 三条队列的固定名字，多处复用


def refresh_queue_depth() -> None:     # 读三条队列当前长度，写进 celery_queue_depth 指标
    """读三条队列在 Redis 里的当前长度（LLEN），写进 celery_queue_depth 指标"""
    try:
        from app_my.core.redis_client import get_redis   # 函数内导入，避免模块导入期就连 Redis
        r = get_redis()                                   # 拿同步 Redis 客户端
        for q in QUEUES:                                  # 挨个队列
            queue_depth(q, int(r.llen(q) or 0))           # LLEN 取长度；None 兜底 0；写入 Gauge
    except Exception as exc:                              # Redis 抽风不能让指标拖垮 worker
        logger.warning("worker: 读取队列长度失败（忽略）: %s", exc)


@worker_ready.connect                                     # 把这个函数挂到 worker_ready 信号上
def _on_worker_ready(sender=None, **kwargs):              # sender 是发信号的 worker 对象（用不到）
    """worker 就绪：暴露 /metrics、记录一次队列长度"""
    global _IS_WORKER, _METRICS_STARTED                   # 要改模块级变量，必须声明 global
    _IS_WORKER = True                                     # 标记"我是真 worker"，task_postrun 才会干活
    if not _METRICS_STARTED:                              # 只启动一次
        try:
            start_metrics_server(settings.WORKER_METRICS_PORT)   # 起一个后台线程暴露 :9101/metrics
            _METRICS_STARTED = True
            logger.info("worker: 指标已暴露 http://0.0.0.0:%d/metrics", settings.WORKER_METRICS_PORT)
        except Exception as exc:                          # 端口被占等，只警告不崩
            logger.warning("worker: 指标服务启动失败（可能端口被占）: %s", exc)
    refresh_queue_depth()                                 # 首次量一次队列长度
    logger.info("worker: 就绪，队列 %s", " / ".join(QUEUES))


@task_postrun.connect                                     # 挂到"每个任务结束后"
def _on_task_postrun(sender=None, **kwargs):
    """每个任务结束后刷一次队列长度（指标服务没起时直接跳过）"""
    if _IS_WORKER and _METRICS_STARTED:                   # 两个开关都开着才干活（单测里就是空操作）
        refresh_queue_depth()


@worker_shutdown.connect                                  # 挂到"worker 关闭"
def _on_worker_shutdown(sender=None, **kwargs):
    logger.info("worker: 正在关闭")
```

### 6.3 逐点讲解

**① 为什么用模块级 `_IS_WORKER` 开关（这段是"防误伤"的精华）**

`task_postrun` 信号在**本地 eager 模式（单测）里也会触发**！如果不管三七二十一就去连 Redis 数队列长度，单测就会莫名其妙地依赖一个跑着的 Redis，还会打一堆日志。

用一个开关挡住：
- `_IS_WORKER` 默认 `False`，只有**真 worker** 的 `worker_ready` 触发后才置 `True`。
- `_METRICS_STARTED` 同理，确保指标服务只起一次。

单测里这两个开关一直是 `False`，所以 `task_postrun` 就是**空操作**。这叫"运行时环境感知"。

**② `from ... import get_redis` 为什么写在函数里**

`refresh_queue_depth` 里再 import，而不是文件顶部。原因：文件顶部的 import 在**模块加载时**执行一次；如果 Redis 客户端模块加载时就尝试建连接，那么单测一 import `signals.py` 就会卡住。函数内 import 是"用到才连"，把副作用推迟到真正需要时。

**③ `start_http_server` 为什么必须 `try/except`**

`prometheus_client.start_http_server(port)` 会在进程里起一个后台线程监听端口。**同一个端口不能被监听两次**，第二次调用会抛 `OSError: Address already in use`。虽然我们用 `_METRICS_STARTED` 挡了重复调用，但万一 9101 被别的程序占了（比如你手滑开了两个 worker），也不能让整个 worker 崩掉——所以包 `try/except`。

**④ `" / ".join(QUEUES)`**

`QUEUES` 是元组 `("high","default","low")`，`" / ".join(...)` 把它拼成 `high / default / low` 打进日志。用 join 而不是手写字符串，是为了"以后加队列只改 `QUEUES` 一处，日志自动跟着变"。

---
## 七、跨进程事件通知：app_my/core/notify.py（🟢新建）

### 7.1 一段消息要跨两个进程

回顾主线：**worker 进程**跑完任务，要把消息送到**浏览器**。但浏览器连接对象活在 **FastAPI 进程**的内存里，worker 进程碰不到它。两个进程唯一的公共设施就是 **Redis**。

所以分成两半：

```text
worker 进程：build_task_event() 拼消息  →  publish_task_event() 扔进 Redis 频道
FastAPI 进程：relay.py 从 Redis 频道收到  →  推给浏览器（下一节之后讲）
```

`notify.py` 只负责**前半段**：拼消息 + 发消息。

### 7.2 完整代码

```python
import json                                   # 序列化用
from typing import Any, Dict, Optional        # 类型注解

from app_my.core.config import settings        # 读频道名
from app_my.core.logging import logger


def build_task_event(
    task_id: str,              # 任务编号
    name: str,                 # 任务名，如 tasks.reindex_milvus
    status: str,               # 状态：STARTED / SUCCESS / FAILURE
    result: Any = None,        # 成功时的结果；默认 None
    error: Optional[str] = None,   # 失败时的错误摘要；默认 None
    tenant_id: int = 0,        # 推给哪个租户
    user_id: int = 0,          # 谁发起的
) -> Dict[str, Any]:           # 返回一个字典
    """
    构造一条任务事件。字段固定，前端拿到的 JSON 永远长这样，好解析。
    """
    return {
        "type": "task",                    # 事件大类；以后可能还有 "alert" / "system"
        "task_id": task_id,                # 任务编号（前端拿它去 GET /tasks/{id} 查详情）
        "name": name,                      # 任务名
        "status": status,                  # STARTED / SUCCESS / FAILURE
        "result": result,                  # 成功时的结果（小 dict，别塞大对象）
        "error": error,                    # 失败时的错误摘要（已截断 500 字）
        "tenant_id": int(tenant_id or 0),  # 路由键：推给这个租户的所有在线连接
        "user_id": int(user_id or 0),      # 发起人（前端可只给发起人弹提示）
    }


def publish_task_event(payload: Dict[str, Any]) -> int:   # 返回值 = 当时有几个订阅者收到
    """
    把事件发到 Redis 频道，返回"当时有几个订阅者收到"。
    失败不抛异常：通知只是锦上添花，绝不能因为它挂了就把任务标记成失败。
    """
    from app_my.core.redis_client import get_redis   # 函数内导入，避免模块级循环依赖

    try:
        data = json.dumps(payload, ensure_ascii=False, default=str)   # 转 JSON 字符串
        return int(get_redis().publish(settings.WS_NOTIFY_CHANNEL, data))   # 发到频道，返回接收者数
    except Exception as exc:
        logger.warning("notify: 发布任务事件失败（已忽略，不影响任务本身）: %s", exc)
        return 0                                       # 失败返回 0，调用方不用管
```

### 7.3 逐点讲解

**① 为什么 `build_task_event` 和 `publish_task_event` 要拆成两个函数**

这是"**纯函数**与**副作用函数**分离"的经典做法：

- `build_task_event` 是**纯函数**：只根据入参拼一个字典，不碰网络、不碰全局状态。所以**极易测试**——给它参数，断言输出字典即可（单测 `test_notify.py` 就是这么干的）。
- `publish_task_event` 有**副作用**（往 Redis 发消息）。

拆开后，核心逻辑（拼消息结构）可以脱离 Redis 单独验证。

**② `json.dumps(payload, ensure_ascii=False, default=str)` 三个参数**

| 参数 | 值 | 为什么 |
|---|---|---|
| `ensure_ascii=False` | 关掉 ASCII 转义 | 默认 `True` 会把中文变成 `\u4e2d\u6587`（Unicode 转义），体积大还难看。关掉后中文原样输出，日志和消息都直观。 |
| `default=str` | 兜底转换器 | 如果 `payload` 里有 `json` 不认识的对象（比如 `datetime`、`Decimal`），`json.dumps` 默认会抛 `TypeError`。"`default=str`"的意思是：遇到这类对象就调用 `str()` 把它转成字符串。**这是"通知绝不让任务崩"的最后一道保险**——宁可结果里某个字段变成字符串，也不能因为序列化失败而抛异常。 |

**③ `get_redis().publish(channel, data)` 的返回值**

Redis 的 `PUBLISH` 命令返回"**当时有几个订阅者收到了这条消息**"。这里 `int(...)` 转成整数返回。有什么用？——日志里能看到这个值（`ws relay: 事件已投递 N 个连接`），从而判断"是不是根本没人在线"。注意：这个数字是"**进程级**订阅者数"，不是"浏览器连接数"（一个 FastAPI 进程不算有几个浏览器连它，它只是整体订阅了一次）。浏览器连接数是中继里 `manager.dispatch()` 的返回值。

**④ 为什么 `from app_my.core.redis_client import get_redis` 写在函数里**

"避免模块级循环依赖"。可能的依赖环：`redis_client` → 某些模块 → `notify`。如果 `notify` 顶部就 import `redis_client`，Python 在加载 `notify` 时会去加载 `redis_client`，而 `redis_client` 又回头需要 `notify`（或它依赖的模块），就会形成"加载到一半又回头加载"的循环，报 `ImportError`。放到函数里，等真正调用时才 import，此时所有模块都加载完了，环就解开了。

**⑤ 失败静默（返回 0）**

`except` 里不 `raise`，只 `logger.warning` 然后 `return 0`。这是**故意的**：`publish_task_event` 的调用点在 `base.py` 的钩子里，那里已经包了 `try`；这里再兜一层是因为——**通知失败的概率比想象中高**（Redis 抖动、频道被清），而**任务成功与否不该被通知绑架**。这就是"降级设计"。

---

## 八、worker 自己的指标：app_my/core/worker_metrics.py（🟢新建）

### 8.1 为什么不和阶段 7 的 metrics.py 合并

阶段 7 已经有一个 `metrics.py`，装的是 **FastAPI 进程**的指标（HTTP QPS、请求延迟、token 成本）。本文件是 **Celery worker 进程**的指标（任务次数、任务耗时、失败数、队列深度）。

**两个进程各跑各的**：FastAPI 进程里根本没有"Celery 任务开始/结束"这些事件，worker 进程里也没有"HTTP 请求"。硬塞进一个文件会导致：

1. API 进程的 `/metrics` 里平白多出 4 个永远为 0 的 `celery_*` 指标（因为 API 不跑任务）；
2. 两个进程的指标注册表互相污染。

所以分开写，Prometheus 也**分两个 job 抓**：`9002/metrics`（API）和 `9101/metrics`（worker）。

### 8.2 完整代码

```python
from prometheus_client import Counter, Gauge, Histogram, start_http_server   # 三种指标类型 + 启动器

# 任务执行次数：按 任务名 / 队列 / 结果 三个维度拆
CELERY_TASK_TOTAL = Counter(
    "celery_task_total",                                          # 指标名（Prometheus 里的名字）
    "Celery 任务执行次数（按 task / queue / status 拆）",            # 帮助文本（鼠标悬停能看到）
    labelnames=("task", "queue", "status"),                       # 三个标签维度
)

# 任务耗时直方图：看"重索引一次要多久""图谱重建多久"
CELERY_TASK_DURATION = Histogram(
    "celery_task_duration_seconds",                               # 名字带单位 _seconds 是 Prometheus 惯例
    "Celery 任务耗时（秒）",
    labelnames=("task",),
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),   # 分桶边界
)

# 任务失败次数：单独一个 Counter，告警可以直接盯它
CELERY_TASK_FAILURES = Counter(
    "celery_task_failures_total",
    "Celery 任务失败次数",
    labelnames=("task",),
)

# 各队列待处理任务数：worker 侧按"最近一次拉取到的队列长度"更新
CELERY_QUEUE_DEPTH = Gauge(
    "celery_queue_depth",
    "各队列待处理任务数",
    labelnames=("queue",),
)


def task_started(task: str, queue: str) -> None:       # 任务开始
    """任务开始：记一次 STARTED"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="STARTED").inc()   # 指定标签后 +1


def task_succeeded(task: str, queue: str, seconds: float) -> None:   # 任务成功
    """任务成功：记 SUCCESS + 耗时"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="SUCCESS").inc()   # 成功计数 +1
    CELERY_TASK_DURATION.labels(task=task).observe(max(seconds, 0.0))          # 把耗时记进直方图（负数兜底 0）


def task_failed(task: str, queue: str, seconds: float) -> None:      # 任务失败
    """任务失败：记 FAILURE + 失败计数 + 耗时（失败的耗时同样值得看）"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="FAILURE").inc()   # 失败也计入总次数
    CELERY_TASK_FAILURES.labels(task=task).inc()                               # 专门的失败计数 +1
    CELERY_TASK_DURATION.labels(task=task).observe(max(seconds, 0.0))          # 失败耗时也记


def queue_depth(queue: str, depth: int) -> None:      # 更新队列深度
    """更新某队列的待处理数（worker 侧定时调用）"""
    CELERY_QUEUE_DEPTH.labels(queue=queue).set(max(depth, 0))   # Gauge 用 set() 直接赋值（不是 inc）


def start_metrics_server(port: int) -> None:          # 起指标 HTTP 服务
    """
    在 worker 进程里起一个后台线程，对外暴露 /metrics。
    注意：start_http_server 只能调用一次；重复调用会抛 OSError（端口被占）。
    """
    start_http_server(port)                           # 监听端口，Prometheus 直接抓
```

### 8.3 三种指标类型怎么选（这是理解 Prometheus 的钥匙）

| 类型 | 语义 | 用法 | 本项目例子 |
|---|---|---|---|
| **Counter** | **只增不减**的累计值（重启归零）。反映"累计发生了多少次"。 | `.inc()`（可传增量，默认 +1） | `celery_task_total`（任务总次数）、`celery_task_failures_total`（失败次数） |
| **Gauge** | **可增可减**的当前值。反映"此时此刻是多少"。 | `.set(v)` / `.inc()` / `.dec()` | `celery_queue_depth`（队列现在积压几条） |
| **Histogram** | 把数值按**区间分桶**统计分布。反映"大部分落在哪个区间"。 | `.observe(v)` | `celery_task_duration_seconds`（任务耗时分布） |

**关键区别**：`Counter` 只能加不能减，所以它回答不了"现在队列里几条"，得用 `Gauge`。而"这个任务跑了 5 次"是累计的，用 `Counter`。

### 8.4 逐点讲解

**① `labelnames=("task","queue","status")` 是什么**

标签（label）是 Prometheus 的"维度"。同一个指标名 `celery_task_total`，带上不同标签就是不同的"时间序列"。例如：

```text
celery_task_total{task="tasks.reindex_milvus", queue="high",    status="SUCCESS"} 3
celery_task_total{task="tasks.generate_nutrition_report", queue="low", status="STARTED"} 5
```

这样一条查询就能**按维度拆开看**："high 队列重索引成功过几次？"、"low 队列营养报告还在跑几条？"。如果不要标签，就只有一个笼统的总数，看不出是哪个任务。

> 🔴 **划线提醒**：标签值**必须来自有限集合**（如固定的几个任务名、三条队列名）。如果哪天你写了个 `labelnames=("task_id",)`，那每次任务会**新造一条时间序列**——任务跑一万次就多一万条序列，Prometheus 内存会被打爆（这叫"高基数"问题）。所以这里绝不用 `task_id` 当标签。

**② `buckets=(0.1, 0.5, ...)` 怎么理解**

直方图预先划好区间边界。数值落进哪个区间，那个区间的计数 +1。这里的分桶覆盖了从"0.1 秒"到"5 分钟"：

```text
le=0.1s   le=0.5s   le=1s   le=2.5s  ...  le=300s
   │          │        │        │            │
   └─ 慢于 0.1s 的有几条？……
```

有了桶，就能算 P95 / P99 分位数（"95% 的重索引在多少秒内跑完"）。桶的设计要贴合业务：营养报告一般不到 1 秒，重索引可能几十秒到几分钟，所以桶从 0.1 一直铺到 300。

**③ `max(seconds, 0.0)` 和 `max(depth, 0)`**

防御性写法。理论上耗时不可能为负、队列长度不可能为负，但万一时钟回拨或者计算出错得到负数，Prometheus 直方图/计数器**不允许负值**（会有奇怪的图）。`max(x, 0)` 一行保证永远不会写进负数。

**④ `CELERY_TASK_FAILURES` 为什么要单独一个 Counter**

因为**告警要盯它**。`increase(celery_task_failures_total[5m]) > 0` 的意思是"最近 5 分钟内失败次数涨了"。虽然 `celery_task_total{status="FAILURE"}` 也能查失败数，但单独一个指标名更直白，写告警表达式更短，一眼就懂。

**⑤ 模块级创建 vs 函数内创建**

四个指标对象写在**模块顶部**（模块级）。这是 Prometheus 客户端的要求：同一个指标名在一个进程里**只能注册一次**。写在模块顶部，模块被 import 一次就注册一次；如果写在函数里反复调用，第二次会抛 `Duplicated timeseries in CollectorRegistry`。所以"定义指标"永远是模块级。

---
## 九、三个长任务：app_my/worker/tasks/（🟢新建 4 个文件）

### 9.1 目录结构

```text
app_my/worker/tasks/
├── __init__.py      # 包标记（空说明文件，只是让 Python 认出这是"包"）
├── reindex.py       # 长任务 ①：Milvus 菜谱向量重索引   → high
├── graph.py         # 长任务 ②：Neo4j 知识图谱重建       → default
└── nutrition.py     # 长任务 ③：营养报告生成            → low
```

`__init__.py` 只写了一句话注释（"真正的注册发生在 celery_app.py 的 imports 列表里"）。**为什么它是空的**：Python 3 其实允许没有 `__init__.py` 的"命名空间包"，但保留一个空文件是**显式声明"这里是个包"**，也方便把说明写在里面。任务文件的"注册"不靠 `__init__.py`，靠 `celery_app.py` 的 `imports`。

### 9.2 三个任务的共同骨架

每个任务都是这个模式，先记住骨架，再看差异：

```python
@celery_app.task(                 # 把这个函数注册成 Celery 任务
    base=NotifyTask,              # 用带"通知+指标"的基类
    name="tasks.xxx",             # 全局任务名（路由表按这个名字匹配！）
    bind=True,                    # 第一个参数变成 self
    max_retries=N,                # 最多自动重试几次
    default_retry_delay=S,        # 重试间隔秒数（可选）
)
def 任务函数(self, ..., tenant_id=0, user_id=0) -> dict:
    import time                   # 函数内 import
    from ... import 重依赖         # 函数内 import 重依赖（关键！）
    ...                           # 干活的代码
    return {...}                  # 返回一个小 dict（别塞大对象）
```

**四个装饰器参数逐个说清**：

| 参数 | 作用 | 不写的后果 |
|---|---|---|
| `base=NotifyTask` | 指定任务基类（提供 `before_start`/`on_success`/`on_failure`） | 用默认 `Task`，没有通知和指标 |
| `name="tasks.xxx"` | 任务在系统里的**全局唯一名**。`task_routes` 按它匹配队列；前端事件里 `name` 字段也是它 | 不写则自动生成 `<模块>.<函数名>`，名字长且一旦改模块名路由就失效 |
| `bind=True` | 让函数第一个参数是 `self`（任务实例） | 基类的钩子需要 `self`，不 bind 会报错 |
| `max_retries` / `default_retry_delay` | 失败后自动重试的次数与间隔 | 默认重试 3 次、间隔 180 秒，对本项目太长/太频繁，按任务单独调 |

**为什么重依赖（pymilvus、langchain、neo4j）要写在函数体里而不是文件顶部**：

Celery worker 启动时会 `import` 我们列在 `imports` 里的每个任务模块（为了发现任务）。如果这些模块顶部就 `import pymilvus`、`from scripts.init_kg import build`，那 worker **一启动就要加载这一堆重库**，冷启动慢好几秒。更糟的是——**API 进程也会 import 这些任务模块**（因为 `api/tasks.py` 需要 `reindex_milvus.delay()` 这个引用），于是 API 进程也平白多加载一堆东西。

把重依赖推迟到"**任务真正执行的那一刻**"再 import，就实现了**懒加载**：谁真正要跑任务，谁才付加载成本。这是 Celery 任务的标准写法。

---

### 9.3 长任务 ①：reindex.py（Milvus 重索引 → high）

#### 完整代码

```python
from app_my.worker.base import NotifyTask              # 通知+指标基类
from app_my.worker.celery_app import celery_app         # 任务实例

BATCH_SIZE = 10     # DashScope embedding 接口单次最多 10 条文本，超了会被拒


@celery_app.task(
    base=NotifyTask,          # 继承"通知 + 指标"基类
    name="tasks.reindex_milvus",
    bind=True,                # 让第一个参数是 self
    max_retries=1,            # 临时故障最多自动重试 1 次
    default_retry_delay=10,   # 重试间隔 10 秒
)
def reindex_milvus(self, rebuild: bool = True, tenant_id: int = 0, user_id: int = 0) -> dict:
    """
    Milvus 向量库重索引。
    参数：
        rebuild   True = 先删旧集合再从零写；False = 不清场，按 recipe_id upsert 覆盖（增量）
        tenant_id 发起任务的租户（基类用它决定通知推给谁）
        user_id   发起人
    返回：{"rows": 实际写入条数, "expected": 菜谱总数, "row_count": 集合当前行数, "seconds": 耗时}
    """
    import time                                        # 函数内 import（上面解释过原因）

    from app_my.core.cache import invalidate_prefix            # 缓存失效工具
    from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text   # 读菜谱 + 转文本/元数据
    from app_my.knowledge.embedding import embed_texts         # 调 embedding 接口把文本转向量
    from app_my.knowledge.milvus_store import (                # Milvus 操作
        clear_collection,        # 清空集合
        collection_row_count,    # 查集合当前行数
        ensure_collection,       # 确保集合存在（没有就建）
        upsert_recipes,          # 按 recipe_id 覆盖写
    )

    t0 = time.perf_counter()                       # 记开始时间
    recipes = load_recipes()                       # 读 app_my/knowledge/data/recipes.json

    if rebuild:                                    # 只有"全量重建"才清场
        if not clear_collection():                 # 清场失败 = Milvus 没起或连不上
            raise RuntimeError("Milvus 不可用：清场失败，请先确认 ai_chief_milvus 容器已启动")
    if not ensure_collection():                    # 幂等：集合在就直接用，不在就按 schema 建
        raise RuntimeError("Milvus 建集合失败（ensure_collection 返回 False）")

    total = 0                                      # 累计写入条数
    for i in range(0, len(recipes), BATCH_SIZE):   # 按下标每 10 条一批
        batch = recipes[i:i + BATCH_SIZE]          # 切出一批
        texts = [recipe_to_text(r) for r in batch] # 把这批菜谱转成检索文本
        vectors = embed_texts(texts)               # 真实调用 DashScope，一次最多 10 条
        rows = [                                    # 组装这一批要写进 Milvus 的行
            {
                "recipe_id": r["recipe_id"],       # 主键：重复写按 id 覆盖（幂等的第二重保险）
                "text": t,                          # 与 PGVector 存的同一份菜谱文本
                "vector": v,                        # 1024 维向量
                "metadata": recipe_to_metadata(r),  # 检索时直接带出的元数据
            }
            for r, t, v in zip(batch, texts, vectors)   # 三份列表一一配对
        ]
        total += upsert_recipes(rows)              # 写入并累计

    # 数据变了：v1（rag）与 v2（rag2）两条检索路径的缓存都失效，否则用户查到的还是旧菜
    invalidate_prefix("rag")
    invalidate_prefix("rag2")

    return {
        "rows": total,                             # 实际写入条数
        "expected": len(recipes),                  # 菜谱总数
        "row_count": collection_row_count(),       # 集合当前行数
        "seconds": round(time.perf_counter() - t0, 2),   # 耗时，保留两位小数
    }
```

#### 逐点讲解

**① `BATCH_SIZE = 10` 为什么是 10**

因为 DashScope（阿里云通义）的 embedding 接口**单次最多接受 10 条文本**。这不是我们随便定的，是**供应商的接口限制**。写成分批循环，就是为了不超限。写成模块级常量，是为了"以后接口放宽了只改这一处"。

**② `rebuild` 参数两种语义**

- `rebuild=True`：先 `clear_collection()` 清空整个集合，再全量写。用于"**改了菜谱文本**或**换了 embedding 模型**"——因为旧向量的语义已经不对了，必须全部重算。
- `rebuild=False`：不清场，直接按 `recipe_id` `upsert`（有则覆盖，无则新增）。用于"**菜谱新增了几条**，只想补进去"。安全、快。

**③ 为什么要 `raise RuntimeError` 而不是返回错误**

`if not clear_collection(): raise RuntimeError(...)` —— 注意这里和 `base.py` 里"通知失败只警告"的做法**相反**。为什么？因为**这是任务的核心工作**：Milvus 连不上，重索引根本没法干。这种情况必须让任务**失败**（进入 `FAILURE` 状态），`on_failure` 钩子才会发 FAILURE 通知，用户才知道"不是成功了，是环境坏了"。而通知/指标失败不影响核心结果，所以降级。**同一个文件里两种相反策略，标准是"这算不算任务的核心目标"**。

**④ 幂等的"两重保险"**

- 第一重：`ensure_collection()` —— 集合不存在才建，存在就直接用（不会重复建）。
- 第二重：`upsert_recipes()` 按 `recipe_id` 覆盖 —— 同一份菜谱跑两次，结果一样（不是插入两条，而是覆盖）。

幂等的好处：**任务可以安全地重试**。如果中途网络抖动、任务重跑，不会产生重复数据。

**⑤ `invalidate_prefix("rag")` 和 `("rag2")` 为什么两个都要清**

项目里有两条检索路径：`rag`（v1）和 `rag2`（v2）。它们各自缓存了检索结果。重索引后向量全变了，**两条路径的缓存都过期了**。只清一条，用户走另一条路径时拿到的还是旧菜，就会出现"我明明重索引了怎么还是旧数据"的诡异现象。这是"**改了数据要清所有相关缓存**"的典型例子。

**⑥ `round(..., 2)` 保留两位小数**

耗时是给人和日志看的，`12.345678901` 这种长小数没意义。保留两位既够用又好看。

---

### 9.4 长任务 ②：graph.py（Neo4j 图谱重建 → default）

#### 完整代码

```python
from typing import Optional                          # ⚠️ 本行实际未使用（无害，但可删）

from app_my.worker.base import NotifyTask
from app_my.worker.celery_app import celery_app


@celery_app.task(
    base=NotifyTask,
    name="tasks.rebuild_kg_graph",
    bind=True,
    max_retries=0,     # 图谱重建是"要么成要么不成"，自动重试没意义，失败就让人看日志
)
def rebuild_kg_graph(self, rebuild: bool = False, tenant_id: int = 0, user_id: int = 0) -> dict:
    """
    Neo4j 图谱重建。
    参数：
        rebuild   False（默认）= 增量合并（MERGE，安全、幂等）；True = 先清空全图再重建
        tenant_id / user_id：通知路由用
    """
    import time                                                   # 函数内 import

    from app_my.core.kg import kg_stats, reset_ingredient_cache, reset_kg_connection   # 图谱工具

    t0 = time.perf_counter()                                      # 记开始

    from scripts.init_kg import build       # 复用阶段 3 的建图脚本里的 build()
    build(rebuild=rebuild)                  # 真正建图

    # 建图脚本自己开了一个驱动并关掉了；本模块的 kg 连接/食材缓存可能是旧的，重建后清掉
    reset_kg_connection()                   # 让下次用到图谱时重新建连接
    reset_ingredient_cache()                # 清食材缓存（图谱变了，缓存可能过期）

    stats = kg_stats()                      # 取图谱统计
    node_total = sum(int(n.get("count", 0) or 0) for n in (stats.get("nodes") or []))          # 累加各类节点数
    rel_total = sum(int(r.get("count", 0) or 0) for r in (stats.get("relationships") or []))   # 累加各类关系数

    return {
        "nodes": node_total,
        "relationships": rel_total,
        "available": bool(stats.get("available")),      # 图谱是否可用
        "seconds": round(time.perf_counter() - t0, 2),
    }
```

#### 逐点讲解

**① 最关键的设计取舍：不复制 Cypher**

建图脚本 `scripts/init_kg.py` 里有约 150 行 Cypher 查询（Neo4j 的图查询语言）。把这个脚本"任务化"有两条路：

- ❌ 把那段 Cypher 复制进任务文件，改造成"任务专用建图"。
- ✅ **直接 `from scripts.init_kg import build`，复用已验证的 `build()` 函数**。

选后者。原因：如果复制一份，**以后改了脚本忘了改任务**，就会出现"命令行建的图和任务建的图不一样"——这种 bug 极难排查（两份代码看起来都"对"）。这就是 **DRY 原则**（Don't Repeat Yourself）：同一份逻辑只写一遍。代价是任务依赖了 `scripts/` 目录（需要 `scripts/__init__.py` 让它成为可导入的包），但"不重复"比"看起来独立"重要得多。

**② `rebuild=False` 为什么是默认值**

因为 `build()` 内部用的是 **`MERGE`** 语义（"存在就匹配，不存在才创建"），不是 `CREATE`。所以默认的"增量合并"是**幂等且安全**的——只是把现有数据再合并一遍，不会重复建节点、不会删数据。只有"改了 `kg_facts.json` 想彻底重建"时才传 `rebuild=True`（会执行 `MATCH (n) DETACH DELETE n` 清空全图）。默认值选安全的那一侧，是"**默认参数要选不会造成破坏的值**"原则。

**③ 为什么 `max_retries=0`**

重索引任务给了 `max_retries=1`（因为可能是 embedding 接口临时抖动，重试一下可能就好）。但图谱重建**不给重试**：如果建图失败（比如 Cypher 语法错、Neo4j 挂了），重试一遍大概率还是失败，纯粹浪费时间。这种"要么成要么不成"的任务，失败了就发 FAILURE 通知让人看日志。**重试次数要按"失败是不是大概率瞬时的"来决定**。

**④ 为什么建完图要 `reset_kg_connection()` + `reset_ingredient_cache()`**

`build()` 脚本内部**自己新建了 Neo4j 驱动连接、用完关掉**。而本项目 `app_my/core/kg.py` 里可能缓存着一个旧的连接对象和一份旧的食材缓存。图谱数据已经变了，如果不清，下次 RAG 查询用的还是**旧连接/旧缓存**，可能读不到新节点。这两个 `reset_*` 就是"**数据变了，把相关缓存一律作废**"。

**⑤ `sum(... for ... in (stats.get("nodes") or []))` 这一串嵌套**

拆开看：

```python
stats.get("nodes") or []          # 取节点列表；就算是 None 也兜底成空列表
for n in ...                      # 遍历每个类别的节点统计，如 {"label":"Ingredient","count":120}
int(n.get("count", 0) or 0)       # 取 count；缺省 0；None 兜底 0；转整数
sum(...)                          # 全部加起来 = 节点总数
```

为什么要这么绕？因为 `kg_stats()` 返回的结构是"按标签分组的列表"（`[{"label":"A","count":1}, ...]`），要自己求和才是"总节点数"。这一长串全是**防御性写法**（字段可能缺失、值可能是 `None`）。

**⑥ ⚠️ 关于文件顶部那行 `from typing import Optional`**

**这行在本文件里没有被用到**（没有任何地方写 `Optional[...]`）。它是从别的文件复制模板时带过来的。**不影响运行**（Python 不会报未使用 import 的错），但属于"可清理的小瑕疵"。操作手册里已如实标注。

---

### 9.5 长任务 ③：nutrition.py（营养报告 → low）

#### 完整代码

```python
from typing import List, Optional                    # List/Optional 类型注解

from app_my.worker.base import NotifyTask
from app_my.worker.celery_app import celery_app


@celery_app.task(
    base=NotifyTask,
    name="tasks.generate_nutrition_report",
    bind=True,
    max_retries=0,                                   # 纯查表+计算，失败重试没意义
)
def generate_nutrition_report(
    self,
    ingredients: Optional[List[str]] = None,         # 食材列表，默认 None
    tenant_id: int = 0,
    user_id: int = 0,
) -> dict:
    """
    生成营养报告。
    参数：
        ingredients  食材列表，如 ["鸡胸肉 200克", "西兰花 1颗"]（名字后带用量，工具才换算得出克数）
    返回：{"ingredients", "total_estimated", "coverage", "unmatched", "summary", "seconds"}
    """
    import time                                                # 函数内 import

    from app_my.tools.nutrition_tool import calculate_nutrition   # 营养计算工具

    t0 = time.perf_counter()

    items = [str(x).strip() for x in (ingredients or []) if str(x).strip()]   # 清洗：转字符串、去空格、丢掉空串
    if not items:
        raise ValueError("ingredients 不能为空")   # 参数不合法 → 直接失败，让前端看到明确错误

    result = calculate_nutrition.invoke({"ingredients": items})   # LangChain 工具同步调用
    est = result.get("total_estimated", {}) or {}                 # 取汇总营养数据，兜底空 dict

    summary = (                                                    # 拼一句人话总结
        f"估算本餐总热量 {est.get('calories', 0)} 千卡；"
        f"蛋白 {est.get('protein', 0)}g / 脂肪 {est.get('fat', 0)}g / 碳水 {est.get('carbs', 0)}g；"
        f"匹配率 {float(result.get('coverage', 0)):.0%}"
    )

    return {
        "ingredients": items,
        "total_estimated": est,
        "coverage": result.get("coverage", 0),
        "unmatched": result.get("unmatched", []),
        "summary": summary,
        "seconds": round(time.perf_counter() - t0, 2),
    }
```

#### 逐点讲解

**① 为什么营养报告"适合异步"**

算营养本身很快（查表 + 四则运算），但**真实产品里的报告还要做"同类菜谱检索 + 大模型润色建议"**，这两步是秒级到十秒级的。用户在页面上等十秒会以为卡死了——所以交后台跑，算完再弹通知。

而且这个任务用的是 `calculate_nutrition`（**纯查表，不烧 token、可复现**），所以它还是"**不依赖大模型就能完整验证一条链路**"的最佳演示任务——端到端测试就选它。

**② 列表推导式的清洗**

```python
items = [str(x).strip() for x in (ingredients or []) if str(x).strip()]
```

拆开：`ingredients or []` 兜底空列表 → 遍历每个元素 `x` → `str(x).strip()` 转字符串并去掉首尾空格 → **只有 strip 后非空才保留**。一行完成"类型转换 + 去空格 + 过滤空串"。用户如果传 `["鸡蛋 ", "", None]`，结果就是 `["鸡蛋"]`。

**③ `raise ValueError("ingredients 不能为空")`**

参数不合法（空食材列表）时**主动抛异常**。为什么不是返回一个空结果？因为"空食材"是**调用方的错误**，不是"成功算出了 0 卡路里"。抛异常 → 任务 `FAILURE` → `on_failure` 发 FAILURE 通知 → 前端看到明确错误信息。**错误要显式暴露，不要静默吞掉**。

**④ `calculate_nutrition.invoke({"ingredients": items})`**

`calculate_nutrition` 是一个 LangChain **工具**（tool）。LangChain 工具的标准调用方式是 `.invoke(参数字典)`，字典的键是工具定义的参数名（这里就是 `ingredients`）。用 `.invoke()` 而不是直接 `calculate_nutrition(items)`，是因为工具对象需要平台提供的标准调用协议。

**⑤ `:.0%` 是什么**

`f"{0.85:.0%}"` → `"85%"`。格式化说明符 `%` 会**自动乘以 100 并加百分号**，`.0` 表示保留 0 位小数。比手写 `f"{0.85*100:.0f}%"` 更简洁。

**⑥ `float(result.get("coverage", 0))` 为什么要 `float()`**

防御性转换。`coverage` 理论上是个数字，但万一工具返回的是字符串 `"0.85"`，直接 `:.0%` 格式化会抛 `ValueError`。先 `float()` 强制转成数字，保证格式化不出错。

---
## 十、WebSocket 连接管理器：app_my/ws/manager.py（🟢新建）

### 10.1 它管什么

浏览器连上来后，FastAPI 进程里就多了一个"连接对象"。任务事件来了，得知道"**现在有哪些浏览器连着、它们分别属于哪个租户**"，才能把消息送到对的人手里。`ConnectionManager` 就是这张**登记表**。

### 10.2 为什么"按 tenant_id 分组"

项目是**多租户**的——租户 A 的任务结果**绝不能**推给租户 B 的页面。如果只用一个"大列表"存所有连接，推送时就得分不清谁是谁。按 `tenant_id` 分组之后，投递变成"**取这个租户的连接集合，逐个发**"，天然隔离。

数据结构长这样：

```text
_by_tenant = {
    58: {连接对象A, 连接对象B},     # 租户 58 有两个浏览器在线
    77: {连接对象C},                # 租户 77 有一个
}
_meta = {
    连接对象A: (58, 101),           # 连接 A 属于租户 58、用户 101
    连接对象B: (58, 102),
    连接对象C: (77, 201),
}
```

两个字典各有用处：`_by_tenant` 用于"**按租户找连接**"（投递），`_meta` 用于"**按连接找信息**"（断开时知道它属于谁、总数是多少）。

### 10.3 完整代码

```python
from collections import defaultdict                    # 准默认字典：缺失的键自动生成默认值
from typing import Dict, Optional, Set, Tuple          # 类型注解

from app_my.core.logging import logger


class ConnectionManager:
    """WebSocket 连接登记表（进程内单例）"""

    def __init__(self) -> None:
        self._by_tenant: Dict[int, Set] = defaultdict(set)   # tenant_id -> 该租户的在线连接集合（默认空 set）
        self._meta: Dict[object, Tuple[int, int]] = {}       # 连接对象 -> (tenant_id, user_id)

    async def connect(self, websocket, tenant_id: int, user_id: int) -> None:
        """接受握手，登记到租户分组"""
        await websocket.accept()                             # 关键：接受 WebSocket 握手（不 accept 连接建立不了）
        self._by_tenant[int(tenant_id or 0)].add(websocket)  # 塞进该租户的集合（首次自动创建空 set）
        self._meta[websocket] = (int(tenant_id or 0), int(user_id or 0))   # 也记下"这连接是谁的"
        logger.info("ws: 连接建立 tenant=%s user=%s 当前连接数=%d",
                    tenant_id, user_id, len(self._meta))     # 日志里带上当前总连接数，方便排障

    def disconnect(self, websocket) -> None:
        """断开：从两处登记表里摘掉（幂等，重复调用安全）"""
        info = self._meta.pop(websocket, None)               # 从 _meta 删掉并取出信息；不在就返回 None
        if not info:                                         # 本来就不在（重复断开）→ 直接返回
            return
        tenant_id, user_id = info
        group = self._by_tenant.get(tenant_id)
        if group is not None:                                # 该租户的分组还在
            group.discard(websocket)                         # 从集合里摘掉（discard 不报错，remove 会）
            if not group:                                    # 该租户没人了
                self._by_tenant.pop(tenant_id, None)         # 把空集合也删掉，防止 _by_tenant 无限涨
        logger.info("ws: 连接断开 tenant=%s user=%s 当前连接数=%d",
                    tenant_id, user_id, len(self._meta))

    async def dispatch(self, event: dict) -> int:
        """
        把一条事件推给该租户的所有在线连接；返回成功送达的连接数。
        发送失败的连接视为已死，顺手清掉。
        """
        tenant_id = int(event.get("tenant_id") or 0)         # 事件里带的租户号
        targets = list(self._by_tenant.get(tenant_id, ()))   # 取出该租户的所有连接；拷成 list 再遍历
        if not targets:
            return 0                                         # 该租户没人在线：任务照跑，只是没人收推送

        sent, dead = 0, []                                   # 成功数 / 待清理的"死连接"
        for ws in targets:
            try:
                await ws.send_json(event)                    # send_json 自动把 dict 序列化成 JSON 文本帧
                sent += 1                                    # 发成功，计数 +1
            except Exception:
                dead.append(ws)                              # 发失败 → 记进待清理列表
        for ws in dead:
            self.disconnect(ws)                              # 循环外统一清理，避免边遍历边改集合
        return sent

    def stats(self) -> dict:
        """当前连接概览（排障/演示用）"""
        return {
            "connections": len(self._meta),                  # 总连接数
            "tenants": {tid: len(g) for tid, g in self._by_tenant.items()},   # 每个租户各几个
        }


# 全局单例：网关、中继、接口都 import 这一个
manager = ConnectionManager()
```

### 10.4 逐点讲解

**① `defaultdict(set)` 是什么**

普通 `dict` 里访问一个不存在的键会 `KeyError`。`defaultdict(set)` 是"带默认值工厂的字典"——访问不存在的键时**自动创建一个空 `set` 放进去**并返回。

所以 `self._by_tenant[58].add(ws)` 在租户 58 从没出现过时也不会报错，会自动新建 `{}` 再 add。省掉了 `if 58 not in ...: ...=set()` 这类样板代码。

**② `await websocket.accept()` 为什么必须有**

WebSocket 握手是"客户端发 `Upgrade` 请求 → 服务端必须**明确接受**"。`accept()` 就是发出"我接受"的信号。**不 accept 连接建立不起来**（会一直挂着直到超时）。注意它在 `connect()` 的第一行——先接受，再登记。

**③ `disconnect` 的"幂等"设计**

`info = self._meta.pop(websocket, None)`：`pop` 带默认值 `None`，键不存在也不报错。如果 `info` 是 `None`（这连接本来就不在），直接 `return`。这样**同一个连接断开两次不会出错**。

为什么需要幂等？因为断开的触发点有多个：`gateway.py` 的 `finally`、`dispatch` 里发现死连接、将来可能的超时清理。多个路径可能对同一个连接调用 `disconnect`，幂等就安全。

**④ `group.discard()` 而非 `group.remove()`**

- `set.remove(x)`：x 不在集合里会抛 `KeyError`。
- `set.discard(x)`：x 不在也不报错。

在"清理"场景里，我们**不在乎它是否真的在**，只求删干净不报错，所以用 `discard`。

**⑤ `if not group: self._by_tenant.pop(tenant_id, None)`**

某租户的最后一个连接断开后，`_by_tenant[tenant_id]` 会变成一个**空集合**。如果不删，`_by_tenant` 会积累大量"空集合"条目（内存泄漏）。删掉它 = "**租户没人了就把登记也撤掉**"。

**⑥ `targets = list(self._by_tenant.get(tenant_id, ()))` 为什么要 `list(...)`（这是最关键的一个细节）**

遍历集合时**不能修改集合**。而下面 `for ws in targets` 循环里，失败连接会走到 `self.disconnect(ws)`，而 `disconnect` 会 `discard` 掉集合里的元素——**边遍历边改**，Python 会抛 `RuntimeError: Set changed size during iteration`。

`list(...)` 把集合**拷一份**成列表再遍历，遍历的是副本，改原集合就不影响遍历了。

**⑦ 为什么死连接要"顺手清掉"**

`send_json` 抛异常通常意味着"这个连接已经死了"（对端关了页面/断网，但服务端还没收到断开通知）。如果不清理，每次推送都要对这些死连接**白试一遍、白等超时**，越积越多。所以"发失败 = 判定已死 = 清掉"。

**⑧ 为什么是模块级单例**

连接对象活在进程内存里，**整个进程只能有一份登记表**。如果每个模块各自 `ConnectionManager()` 一个，会出现"网关把连接注册到 A 表、中继从 B 表找连接"——永远推不到。`manager = ConnectionManager()` 一行定义全局唯一实例，所有模块 `from app_my.ws.manager import manager` 都用这一个。

> 💡 顺带一提：多开 uvicorn worker 时，**每个进程各有一份 `manager`**，但每个进程都订阅了同一条 Redis 频道，各自的连接由各自的进程推。这正是它**能水平扩展**的原因——加一个进程就多一份处理能力，彼此不干扰。

---

## 十一、WebSocket 网关：app_my/ws/gateway.py（🟢新建）

### 11.1 它负责什么

一个 WebSocket 端点 `/ws/notifications`，做两件事：

1. **握手时鉴权**（游客连不上）；
2. 连上后**只负责"活着"**——收心跳、回 pong。

**注意**：真正的"推送任务事件"**不是**它做的，是 `relay.py` 从 Redis 收到事件后调 `manager.dispatch` 做的。网关只管"连接这一端"。

### 11.2 🔴 两个新手必翻车的点（这段是重点）

**坑一：浏览器原生 WebSocket 不能自定义请求头。**

HTTP 接口用 `Authorization: Bearer <token>` 传令牌。但 `new WebSocket(url)` **没法加 header**——这是浏览器 API 的硬限制，不是偷懒。所以 token 只能塞进 URL 查询参数 `?token=xxx`。

代价：token 会出现在 URL 里，可能进访问日志。所以生产环境一般配 `wss://`（加密）且用**短生命周期 token**。

**坑二：HTTP 中间件管不到 WebSocket。**

`main.py` 里那一堆 `add_middleware`（Auth 鉴权 / 限流 / 指标）都**只处理 `http` 类型的请求**。WebSocket 的 scope 类型是 `"websocket"`，**会绕过它们直达本端点**。所以本端点**必须自己做 JWT 校验**——别指望 `AuthMiddleware` 帮你拦（它会直接被跳过）。

这也意味着：**限流中间件也没保护 WS 端点**。这是后续可以加固的点（本阶段先不做）。

### 11.3 完整代码

```python
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect   # WS 相关类

from app_my.core.logging import logger
from app_my.core.security import TOKEN_TYPE_ACCESS, decode_token, is_revoked   # 复用 HTTP 那套鉴权
from app_my.ws.manager import manager

router = APIRouter()

# WebSocket 协议里 1008 表示"策略违规"（这里是"你没通过鉴权"）
WS_CLOSE_POLICY_VIOLATION = 1008


def _authenticate(token: str):                        # 校验 token，通过返回 (tenant_id, user_id)，否则 None
    """
    校验 ?token= 里的 JWT，通过返回 (tenant_id, user_id)，否则返回 None。
    复用 HTTP 那套 security 模块，保证"HTTP 认的令牌 WS 也认"，不用维护两套鉴权。
    """
    if not token:                                     # 空 token 直接拒
        return None
    payload = decode_token(token)                     # 验签 + 验过期，失败返回 None
    if payload is None:
        return None
    if payload.get("type") != TOKEN_TYPE_ACCESS:      # 只收 access token，不收 refresh token
        return None
    if is_revoked(payload):                           # 登出/换新过的令牌立刻失效
        return None
    try:
        user_id = int(payload.get("sub"))             # 用户 id 在 sub 字段
    except (TypeError, ValueError):                   # sub 缺失或不是数字
        return None
    tenant_id = payload.get("tenant_id") or 0         # 老令牌可能没有 tenant，兜底 0
    return int(tenant_id), user_id


@router.websocket("/notifications")                                  # 注册 WS 路由
async def ws_notifications(websocket: WebSocket, token: str = Query(default="")):   # token 从查询参数取
    """
    建立实时通知长连接。
    用法（浏览器）：const ws = new WebSocket(`ws://127.0.0.1:9002/ws/notifications?token=${accessToken}`);
    通信约定：客户端发 "ping"（保活）；服务端回 '{"type":"pong"}'；任务事件是 {"type":"task", ...}
    """
    auth = _authenticate(token)                       # 鉴权
    if auth is None:
        logger.warning("ws: 鉴权失败，拒绝连接")
        await websocket.close(code=WS_CLOSE_POLICY_VIOLATION)   # 以 1008 关闭（不 accept，省一次握手往返）
        return

    tenant_id, user_id = auth
    await manager.connect(websocket, tenant_id, user_id)   # 通过鉴权 → 登记连接
    try:
        while True:                                    # 长连接主体：一直循环
            msg = await websocket.receive_text()       # 没消息就挂在这里等（异步等待，不占 CPU）
            if msg == "ping":                          # 简易心跳：前端定时发，防中间设备掐空闲连接
                await websocket.send_text('{"type":"pong"}')   # 回一个 pong
    except WebSocketDisconnect:                        # 浏览器关页面/断网 → 走这里
        pass                                           # 正常收尾，不报错
    finally:
        manager.disconnect(websocket)                  # 无论怎么退出，都要注销连接
```

### 11.4 逐点讲解

**① `token: str = Query(default="")` 怎么理解**

FastAPI 的参数声明。`Query(default="")` 表示"这个 `token` 从 **URL 查询参数**里取；没有就默认空字符串"。URL 长这样：`/ws/notifications?token=eyJhbGci...`。注意默认值是 `""` 而不是 `None`——这样后面 `if not token` 判断空字符串即可。

**② `_authenticate` 里四道检查**

| 检查 | 代码 | 拦掉什么 |
|---|---|---|
| 非空 | `if not token: return None` | 没带 token 的裸连 |
| 验签+验过期 | `payload = decode_token(token)` | 伪造的、过期的 token |
| 类型 | `payload.get("type") != TOKEN_TYPE_ACCESS` | refresh token（只能用来换新 access，不能连 WS） |
| 是否被吊销 | `is_revoked(payload)` | 用户已登出/换新后的旧 token |

**复用 HTTP 的 `security` 模块**是关键设计：不自己再写一套 JWT 解析，保证"**HTTP 认的令牌 WS 也认**"，规则永远一致。

**③ `await websocket.close(code=1008)` 而不是先 accept 再 close**

`close()` 可以直接在**未 accept** 时调用，FastAPI/Starlette 会用一个 HTTP 403/拒绝让握手失败。这里**故意不 accept**——省一次握手往返（不必先建立连接再拆）。前端收到 1008，就知道"是鉴权问题，重连也没用"。

**④ `while True` + `await websocket.receive_text()`**

`receive_text()` 是**异步阻塞**：没有消息时，这个协程**让出 CPU**（`await`），事件循环去干别的活。不要理解成"死循环占 CPU"——它一行 CPU 都不占，只是在等消息。

**⑤ `except WebSocketDisconnect`**

当浏览器关闭页面、断网，Starlette 会抛 `WebSocketDisconnect`。这里 `pass` 是**正常的收尾**，不是错误。

**⑥ `finally: manager.disconnect(websocket)`**

`finally` 保证**无论 `try` 里怎么退出**（正常断开、异常、将来加了别的 `break`），都会执行注销。这是"**资源必须配对释放**"的经典写法：`connect` 了就必须 `disconnect`。

**⑦ 为什么 ping/pong 用纯文本而不是 JSON**

`"ping"` 和 `'{"type":"pong"}'`——请求用最简的纯文本，应答用 JSON。做法上其实可以都用 JSON。用纯文本 `"ping"` 只是"**最小化心跳包体积**"的朴素选择（心跳要频繁发，越小越好）。前端收到非 JSON 的 `pong` 时会忽略，收 JSON 才当业务事件。

---

## 十二、Redis 订阅中继：app_my/ws/relay.py（🟢新建）

### 12.1 补上最后一段链路

```text
worker 进程  --publish-->  Redis 频道  --本文件中继-->  本进程的 WebSocket 连接
```

**为什么需要"中继"这一环，不让 worker 直接发 WS？**

因为 worker 进程里**根本没有浏览器连接对象**（连接活在 FastAPI 进程内存里）。worker 唯一能碰到的公共设施就是 Redis。所以分工是：

- worker **只负责**"发到 Redis"；
- FastAPI 进程**负责**"从 Redis 收 + 转发给浏览器"。

### 12.2 🔴 一个会让整个服务卡死的坑

这里的 Redis 订阅**必须用 `redis.asyncio`（异步客户端）**。

如果用**同步**客户端，`pubsub.listen()` 会**阻塞整个线程**等待消息——而 FastAPI 的事件循环就在这个线程上。结果是：**一旦订阅，所有 HTTP 接口全部不再响应**（事件循环被卡死了）。表现为"服务看起来活着，但什么都点不动"。

所以：**异步客户端 + `await`**，等待消息时把 CPU 让出去。

### 12.3 完整代码

```python
import asyncio                                       # 用它的 CancelledError 和 sleep
import json

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.ws.manager import manager

RETRY_SECONDS = 3        # 订阅断开后的重连间隔


async def run_relay() -> None:
    """
    常驻协程：订阅 Redis 频道，把事件派发给本进程的 WebSocket 连接。
    设计成"永不退出"——出错就等 3 秒重连，保证 Redis 重启后自动恢复。
    """
    import redis.asyncio as aioredis                 # 函数内导入：redis 版本旧时，import 本模块也不报错

    while True:                                      # 外层大循环：永不退出（错了就重连）
        client = None                                # 每次重连都建新客户端
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)   # 连 Redis（业务 db0）
            pubsub = client.pubsub()                 # 创建"发布订阅"对象
            await pubsub.subscribe(settings.WS_NOTIFY_CHANNEL)   # 订阅那个频道
            logger.info("ws relay: 已订阅 Redis 频道 %s", settings.WS_NOTIFY_CHANNEL)

            async for message in pubsub.listen():    # 异步迭代：有消息才唤醒（关键！用 await 不卡事件循环）
                if message.get("type") != "message": # 订阅/退订的确认帧，跳过
                    continue
                try:
                    event = json.loads(message["data"])   # 把收到的 JSON 字符串解析回 dict
                except (TypeError, ValueError):
                    logger.warning("ws relay: 收到无法解析的消息，已跳过")
                    continue
                sent = await manager.dispatch(event)      # 派发给该租户的所有连接
                if sent:                                  # 有连接收到才记日志
                    logger.info("ws relay: 事件已投递 %d 个连接（task_id=%s）",
                                sent, event.get("task_id"))
        except asyncio.CancelledError:               # 应用关闭时会被 cancel —— 这是正常流程
            if client is not None:                   # 有客户端就关掉
                try:
                    await client.aclose()
                except Exception:
                    pass
            raise                                    # 往外抛，让 lifespan 干净收尾
        except Exception as exc:                     # 其它错误（Redis 挂了等）
            logger.warning("ws relay: 订阅中断，%d 秒后重连: %s", RETRY_SECONDS, exc)
            await asyncio.sleep(RETRY_SECONDS)       # 等 3 秒再重连
        finally:
            if client is not None:                   # 无论如何都尝试关闭客户端，避免连接泄漏
                try:
                    await client.aclose()
                except Exception:
                    pass
```

### 12.4 逐点讲解

**① `while True` + `try/except` + `finally` 的三层结构**

- **外层 `while True`**：让这个协程"永不退出"。Redis 崩了、网络断了，重连后继续听。
- **`except asyncio.CancelledError: ... raise` 要单独放在 `except Exception` 前面**：因为 `CancelledError` 在 Python 3.8+ 里继承自 `BaseException`（不是 `Exception`），不被 `except Exception` 捕获。**必须显式捕获**，才能做"关闭客户端"的清理，然后 `raise` 把取消信号继续往上抛（让 `lifespan` 知道"我确实退出了"）。
- **`finally`**：不管走哪条路径（正常、取消、异常），都尝试关闭 Redis 客户端，**防止连接泄漏**。

**② `except asyncio.CancelledError` 里为什么 `raise` 而不是 `return`**

`CancelledError` 是"**别人要求你停下**"的信号。如果你 `return` 把它吞了，`lifespan` 里 `await relay_task` 就**永远等不到"已取消"这个结果**，可能卡住。所以清理完后要 `raise` 把它**继续往上抛**。这是 asyncio 的约定。

**③ `from_url(settings.REDIS_URL, decode_responses=True)`

- `settings.REDIS_URL` 是业务库的地址（**db0**）。这里连通的是 db0，因为**Redis 的 pub/sub 频道是全局的、不区分 db**——worker 从哪个 db `publish` 都行，任何 db 上的订阅都能收到。本项目约定统一用 `settings.REDIS_URL`（db0）做这条"通知专线"，与 broker(db1) / backend(db2) 在职责上分开，逻辑清晰。

- `decode_responses=True`：让 Redis 返回的是 **Python 字符串**而不是 `bytes`。不加的话 `message["data"]` 是 `b'{"type":...}'`（字节串），`json.loads` 虽然也能处理，但日志里会到处是 `b'...'` 很乱。

**④ `async for message in pubsub.listen()`**

`pubsub.listen()` 是一个**异步生成器**。`async for` 会一次次 `await` 下一条消息。**没有消息时它挂起等待**，把 CPU 让给事件循环——这就是"不卡死"的关键。每来一条消息，循环体执行一次。

**⑤ `if message.get("type") != "message": continue`**

`pubsub.listen()` 会**同时产出三类帧**：

- `{"type":"subscribe", ...}` — 订阅成功的确认
- `{"type":"unsubscribe", ...}` — 退订确认
- `{"type":"message", "data": "..."}` — **真正的消息**

我们只要 `"message"` 类型，其它跳过。不跳过的话，`message["data"]` 会是订阅确认的数字（不是 JSON），解析会出错。

**⑥ `json.loads` 再包一层 `try/except`**

即使类型是 `"message"`，`data` 也可能不是合法 JSON（比如有人手动往频道发了乱字符串）。单独 try 一下，遇到坏消息**跳过继续**，而不是让整个中继挂掉。**"脏数据不能让整个循环崩"**。

**⑦ `await manager.dispatch(event)`**

调到上一节那个 `dispatch`，把事件推给该租户的所有连接。返回成功送达的连接数。

**⑧ 为什么 `import redis.asyncio as aioredis` 写在函数里**

两个原因：① 避免模块级循环依赖；② `redis.asyncio` 在某些旧版本 redis 包里不存在，写在函数里可以让"import 本模块"在旧环境下也不报错（直到真正调用 `run_relay` 才需要它）。

---
## 十三、接口层：app_my/schemas/tasks.py + app_my/api/tasks.py（🟢新建）

### 13.1 先讲一个分层习惯：schema 与 api 分开

项目一直有个约定：**`schemas/` 只描述"接口进出的数据长什么样"，`api/` 只描述"来处理这个请求"**。两者分开的好处：

- 数据模型可以被多处复用（比如前端文档、其他接口）；
- 接口函数里不用写一堆 `if not body.get(...)` 的手工校验，Pydantic 自动做。

### 13.2 schemas/tasks.py：四个数据模型

```python
from typing import Any, Dict, List, Optional       # 类型注解

from pydantic import BaseModel, Field              # Pydantic 基类 + 字段描述器


class ReindexIn(BaseModel):                        # 重索引请求体
    """Milvus 重索引请求"""
    rebuild: bool = Field(True, description="True=先清场再全量重建；False=不清场，按 recipe_id 覆盖")


class KgRebuildIn(BaseModel):                      # 图谱重建请求体
    """Neo4j 图谱重建请求"""
    rebuild: bool = Field(False, description="True=清空全图再重建（会短暂清空）；False=增量合并")


class NutritionReportIn(BaseModel):                # 营养报告请求体
    """营养报告请求：至少要有一个食材"""
    ingredients: List[str] = Field(..., min_length=1, description="食材列表，如 ['鸡胸肉 200克']")


class TaskSubmitOut(BaseModel):                    # 提交任务的响应体
    """提交任务的响应"""
    task_id: str            # 任务编号：后续查状态、WS 事件里都用它
    name: str               # 任务名（tasks.xxx）
    queue: str              # 落到哪条队列（high/default/low）
    status: str = "PENDING"  # 刚提交必然是 PENDING


class TaskStatusOut(BaseModel):                    # 查询状态的响应体
    """查询任务状态的响应"""
    task_id: str
    status: str                          # PENDING / STARTED / SUCCESS / FAILURE
    result: Optional[Dict[str, Any]] = None   # 成功时的结果
    error: Optional[str] = None               # 失败时的错误摘要
```

**逐点讲解**：

**① `Field(True, description=...)` 的两个参数**

- 第一个位置参数是**默认值**。`rebuild: bool = Field(True)` 等价于 `rebuild: bool = True`，但 `Field` 能额外挂 `description`（会出现在自动生成的 API 文档里，前端一看就懂）。
- `description=` 是**给文档用的**，运行时不影响逻辑。

**② `Field(..., min_length=1)` 里的 `...` 是什么**

`...`（Ellipsis）在 Pydantic 里表示"**这个字段是必填的**，没有默认值"。`min_length=1` 表示"列表**至少 1 个元素**"。这样前端如果传 `{"ingredients": []}`，FastAPI 会**自动返回 422 校验错误**，根本不会走到任务逻辑。**校验交给声明式规则，不写手工 if**。

**③ `Optional[Dict[str, Any]] = None`**

"类型是 `Dict` 或 `None`，默认 `None`"。用于响应体——成功时 `result` 有值，失败时 `error` 有值，另一个是 `None`。

> 🔴 **注意一个常见误解**：这三个 `In` 类里 `rebuild` 的默认值**不同**（重索引 `True`、图谱 `False`）。这不是笔误，是根据**任务本身的危险性**定的：重索引清场后能重建，相对安全，默认全量重建；图谱清场会短暂清空在线图谱，风险大，默认增量安全模式。**默认值要选"不破坏"的那一侧**。

### 13.3 api/tasks.py：四个接口

```python
from celery.result import AsyncResult              # 任务结果查询句柄
from fastapi import APIRouter, Request             # 路由 + 请求对象

from app_my.schemas.tasks import KgRebuildIn, NutritionReportIn, ReindexIn   # 请求模型
from app_my.worker.celery_app import celery_app    # Celery 实例（查结果用）
from app_my.worker.tasks.graph import rebuild_kg_graph               # 三个任务（为了 .delay()）
from app_my.worker.tasks.nutrition import generate_nutrition_report
from app_my.worker.tasks.reindex import reindex_milvus

router = APIRouter()


def _caller(request: Request):                     # 从请求上下文取"谁提交的"
    """从请求上下文取"谁提交的"：租户（推送给谁）+ 用户（谁发起）"""
    tenant_id = int(getattr(request.state, "tenant_id", None) or 0)   # 中间件塞进 state 的租户号
    user_id = int(getattr(request.state, "user_id", None) or 0)       # 中间件塞进 state 的用户号
    return tenant_id, user_id


@router.post("/reindex-milvus")                    # POST /tasks/reindex-milvus
async def submit_reindex(request: Request, body: ReindexIn):        # body 由 Pydantic 自动解析+校验
    """提交 Milvus 菜谱向量重索引（长任务，接口立即返回 task_id）"""
    tenant_id, user_id = _caller(request)                              # 取出调用者信息
    result = reindex_milvus.delay(rebuild=body.rebuild, tenant_id=tenant_id, user_id=user_id)   # 投进队列
    return {"task_id": result.id, "name": "tasks.reindex_milvus", "queue": "high", "status": "PENDING"}


@router.post("/rebuild-kg")
async def submit_rebuild_kg(request: Request, body: KgRebuildIn):
    """提交 Neo4j 知识图谱重建（长任务，接口立即返回 task_id）"""
    tenant_id, user_id = _caller(request)
    result = rebuild_kg_graph.delay(rebuild=body.rebuild, tenant_id=tenant_id, user_id=user_id)
    return {"task_id": result.id, "name": "tasks.rebuild_kg_graph", "queue": "default", "status": "PENDING"}


@router.post("/nutrition-report")
async def submit_nutrition_report(request: Request, body: NutritionReportIn):
    """提交营养报告生成（长任务，接口立即返回 task_id）"""
    tenant_id, user_id = _caller(request)
    result = generate_nutrition_report.delay(
        ingredients=body.ingredients, tenant_id=tenant_id, user_id=user_id
    )
    return {"task_id": result.id, "name": "tasks.generate_nutrition_report", "queue": "low", "status": "PENDING"}


@router.get("/{task_id}")                          # GET /tasks/{task_id}
async def get_task_status(task_id: str):
    """
    查询任务状态。
    返回：PENDING 排队中 / STARTED 正在跑 / SUCCESS 成功 / FAILURE 失败
    """
    res = AsyncResult(task_id, app=celery_app)     # 用 task_id 构造查询句柄
    payload = {"task_id": task_id, "status": res.status, "result": None, "error": None}   # 组装基础响应
    if res.successful():                           # 成功
        payload["result"] = res.result             # 带上结果
    elif res.failed():                             # 失败
        payload["error"] = str(res.result)         # 带上错误信息
    return payload
```

**逐点讲解**：

**① `_caller(request)` 从哪拿 tenant_id / user_id**

`request.state.tenant_id` 和 `request.state.user_id` **不是 FastAPI 自带的**——是阶段 4 的中间件（`TenantContextMiddleware` / `AuthMiddleware`）在请求进来时**塞进 `request.state`** 的。所以本接口只要读它即可，**不用重新解析 token**。这就是"**中间件做统一预处理，路由直接用结果**"的分层收益。

用 `getattr(request.state, "tenant_id", None) or 0` 兜底：万一某个中间件没跑（或没塞这个值），也不会 `AttributeError`，退化成 `0`。

**② `.delay(...)` 是全部魔法所在**

`reindex_milvus.delay(rebuild=..., tenant_id=..., user_id=...)` 干了三件事：

1. 把"函数名 `tasks.reindex_milvus` + 参数字典"**序列化成 JSON**；
2. 按 `task_routes` 找到队列（`high`），**投一条消息进 Redis db1**；
3. **立刻**返回一个 `AsyncResult` 对象（含 `id`）——**不等任务执行**。

这一步通常只要**几毫秒**（就是一次 Redis 写入）。这就是"提交接口毫秒级返回"的由来。

> 🟡 `deliver` 与 `delay` 的区别：`.delay(x)` 是 `.apply_async(args=[x])` 的简写。本项目参数全用**关键字**传（`rebuild=...`, `tenant_id=...`），这样和函数签名一一对应，不易错位。

**③ `result.id` 就是 task_id**

`AsyncResult.id` 是一个 UUID 字符串，由 Celery 生成。前端拿它做两件事：查状态（`GET /tasks/{id}`）、和 WS 推送里的 `task_id` 对号入座。

**④ 三个提交接口的返回值结构**：`{"task_id", "name", "queue", "status"}`。其中 `queue` 是**硬编码**写在返回里的（`"high"` / `"default"` / `"low"`）。严格说可以从 `task_routes` 动态取，但这里直接写常量更直观——**代价是如果改了路由表，这个返回值也要跟着改**（属于"小冗余"，可接受）。

**⑤ `GET /tasks/{task_id}` 的四个状态判断**

```python
res.status          # PENDING / STARTED / SUCCESS / FAILURE
res.successful()    # True 若 SUCCESS
res.failed()        # True 若 FAILURE
res.result          # 成功 → 返回值；失败 → 异常对象
```

`str(res.result)` 在失败时把异常转成字符串（异常对象不能直接 JSON 序列化）。**注意**：如果任务结果已过期（超过 `result_expires` 1 小时），backend 里没记录，`res.status` 会一直是 `PENDING`——这是**故意**的（Celery 不知道是"没提交"还是"过期了"，统一给 PENDING）。

**⑥ 🔴 一个实测踩到的坑：`GET /tasks/{task_id}` 是受鉴权保护的**

`AuthMiddleware` 保护了所有非白名单路径，`/tasks/{id}` 也在其中。所以单测里直接 `GET` 会返回 **401**。修复方式是**带上 `Authorization: Bearer <token>` 头**（测试里加了个 `auth_headers` fixture）。这提醒我们：**新增的接口会默认继承全局中间件的保护**，测的时候别忘了带 token。

---

## 十四、入口接线：main.py（🔵修改）

### 14.1 改了哪四处

| 位置 | 加什么 | 为什么 |
|---|---|---|
| 顶部 import | `import asyncio` | 启动中继协程要用 `asyncio.create_task` |
| 顶部 import | `tasks_api` / `ws_gateway` / `run_relay` | 引入本阶段的两个新路由和中继函数 |
| `lifespan` | 启动时 `create_task(run_relay())`；关闭时 `cancel()` + `await` | 让中继随应用"同生共死" |
| 路由注册区 | `include_router(tasks_api...)` / `include_router(ws_gateway...)` | 把 `/tasks/*` 和 `/ws/*` 挂到应用上 |

### 14.2 完整改动片段

```python
import asyncio                                           # 【新增】创建/取消协程任务要用
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_my.core.config import settings
# ...（原有 import 不动）...
from app_my.api import tasks as tasks_api                # 【新增】异步任务路由
from app_my.ws import gateway as ws_gateway              # 【新增】WS 网关
from app_my.ws.relay import run_relay                    # 【新增】Redis 订阅中继函数


@asynccontextmanager
async def lifespan(app: FastAPI):                        # 应用"启动/关闭"钩子
    """应用生命周期：启动 / 关闭钩子"""
    setup_logging()
    setup_langsmith()
    init_db()                                            # 幂等建表
    logger.info("%s v%s 启动中...", settings.APP_NAME, settings.APP_VERSION)

    # v3阶段8：启动常驻协程，订阅 Redis 频道，把任务完成事件转发给浏览器
    relay_task = asyncio.create_task(run_relay(), name="ws-notify-relay")   # 【新增】把中继协程丢进事件循环
    logger.info("ws relay: 后台订阅任务已启动")

    yield                                                # —— 此处挂起，应用开始对外服务 ——

    # v3阶段8：先取消中继协程再收尾，避免事件循环关闭时报 "Task was destroyed but it is pending"
    relay_task.cancel()                                  # 【新增】请求取消
    try:
        await relay_task                                 # 【新增】等它真正退出（会抛 CancelledError）
    except asyncio.CancelledError:
        pass                                             # 正常现象，吞掉
    logger.info("服务关闭，清理资源...")


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

# ...（中间件一大段不动）...

# ===== 路由 =====
app.include_router(oss.router, prefix="/oss", tags=["阿里云OSS"])
# ...（原有路由不动）...
app.include_router(tasks_api.router, prefix="/tasks", tags=["异步任务(v3阶段8)"])    # 【新增】
app.include_router(ws_gateway.router, prefix="/ws", tags=["WebSocket(v3阶段8)"])     # 【新增】
```

### 14.3 逐点讲解

**① `lifespan` 是什么**

FastAPI 的生命周期管理器。用 `@asynccontextmanager` 装饰的异步生成器：**`yield` 之前**是"启动时执行"，**`yield` 之后**是"关闭时执行"。应用从启动到关闭，`yield` 这个点就是"正式对外服务"的时刻。

**② `asyncio.create_task(run_relay(), name=...)`**

`create_task` 把协程**丢进事件循环后台运行**，立即返回一个 `Task` 对象（不阻塞）。所以启动后，`run_relay` 就在后台"听着 Redis"，而 FastAPI 正常处理 HTTP 请求——**两件事并发进行**。

`name="ws-notify-relay"` 给任务起个名字，调试时（`asyncio.all_tasks()`）能认出是它。

**③ 关闭时为什么要 `cancel()` + `await`**

- `relay_task.cancel()`：给中继发"**请你停下**"的信号。`run_relay` 里那个 `except asyncio.CancelledError` 会捕获到，做完清理后 `raise`。
- `await relay_task`：**等它真的退出了**再往下走。
- 不 `await` 会怎样？应用关闭时事件循环要销毁，但中继协程还挂着没退干净，Python 会打印 `Task was destroyed but it is pending!` 警告，而且 Redis 连接可能没正常关闭。

**④ `except asyncio.CancelledError: pass`**

`await relay_task` 在协程被取消时会**抛 `CancelledError`**（这正是"它退出了"的信号）。这里 `pass` 是正常的——**我们主动取消的，所以收到取消异常是预期行为**，不该当错误。

**⑤ 为什么中继用 `lifespan` 而不是"在模块顶层启动"**

如果在模块顶层调 `asyncio.create_task(...)`，那时**事件循环还没建立**（模块加载发生在 `uvicorn` 建循环之前），会报 `no running event loop`。`lifespan` 保证在"事件循环已在跑、应用即将服务"的时刻启动，时机才正确。

**⑥ 路由 `prefix="/tasks"` + 内部 `@router.get("/{task_id}")`**

最终路径 = 前缀 + 路由路径 = `/tasks/{task_id}`。`include_router` 的 `tags` 参数只影响自动生成的 API 文档分组，不影响功能。

**⑦ 🔴 顺序问题：`tasks_api` 的 `/{task_id}` 会"吃掉"别的路径吗**

`GET /tasks/{task_id}` 是个**通配路径**（任何 `/tasks/xxx` 都能匹配）。要小心：如果将来加 `GET /tasks/stats`，它会被 `/{task_id}` 先匹配到（当成 task_id="stats"）。**规矩是：固定路径要注册在通配路径之前**。本阶段只有 `/{task_id}` 一个 GET，暂时安全，但这是个**日后要记着的坑**。

---
## 十五、前端实时客户端：frontend/js/ws.js（🟢新建）

### 15.1 它要解决三个现实问题

浏览器建一条 WebSocket 长连接很容易（`new WebSocket(url)` 一行）。但**真实网络会断**，所以生产可用的客户端必须处理三件事：

| 问题 | 后果 | 本文件的解法 |
|---|---|---|
| 连接断了（切网、服务器重启、手机熄屏） | 用户再也收不到通知，且不知道 | **断线自动重连 + 指数退避** |
| 长连接空闲太久被中间设备（路由器/NAT/代理）掐断 | 明明没断网却收不到消息 | **定时心跳（每 25 秒发 `ping`）** |
| 用户主动关闭 | 不该反复重连打扰用户 | `manualClosed` 标记，主动关就不重连 |

### 15.2 整体结构：IIFE + 挂一个 `window.Notify`

```javascript
(function (global) {          // 立即执行函数：把内部变量"关起来"，不污染全局
    'use strict';             // 严格模式：把一些隐蔽错误变成显式报错

    var MAX_DELAY = 15000;    // 重连退避上限（15 秒）
    var BASE_DELAY = 1000;    // 首次重连等待 1 秒
    var HEARTBEAT_MS = 25000; // 心跳间隔 25 秒（比常见 30/60 秒空闲超时短）

    var socket = null;        // 当前 WebSocket 实例
    var retryCount = 0;       // 已连续重连次数（用来算退避时长）
    var heartbeatTimer = null;// 心跳定时器
    var reconnectTimer = null;// 重连定时器
    var manualClosed = false; // 主动 close() 时置真，避免把"用户主动断开"当成掉线去重连
    var listeners = [];       // 事件回调列表

    // ... 一堆函数 ...

    global.Notify = {         // 只把对外的 API 暴露出去，内部变量外部碰不到
        connect: connect, close: close, toast: toast,
        on: function (fn) { listeners.push(fn); return fn; },
        off: function (fn) { listeners = listeners.filter(function (f) { return f !== fn; }); },
        isOpen: function () { return !!socket && socket.readyState === 1; }
    };
})(window);                   // 传入 window 作为 global
```

**为什么用 IIFE（立即执行函数）**：所有 `var` 和函数都关在函数作用域里，**不会变成全局变量**（不污染 `window`）。只有 `Notify` 一个对象暴露出去。这是"**模块化**"的朴素实现——**只暴露你要暴露的**。

### 15.3 地址与令牌的处理

```javascript
// 计算后端地址：优先 window.WS_BASE，其次 api.js 的 API_BASE，最后同源
function backendBase() {
    if (global.WS_BASE) return global.WS_BASE;                       // ① 显式指定
    if (typeof API_BASE !== 'undefined' && API_BASE) return API_BASE; // ② 复用 api.js 的地址
    return global.location.origin;                                    // ③ 兜底：与页面同源
}

// 取 token：优先 api.js，其次 window.WS_TOKEN
function currentToken() {
    if (typeof Api !== 'undefined' && Api.getAccessToken) {           // api.js 在
        var t = Api.getAccessToken();
        if (t) return t;
    }
    return global.WS_TOKEN || '';                                     // 否则用全局变量，最后兜底空串
}

// 拼出 ws(s)://host/ws/notifications?token=xxxx
function buildUrl() {
    var base = backendBase().replace(/\/+$/, '');                     // 去掉结尾的斜杠（/\/+$/）
    var url = new URL(base + '/ws/notifications', global.location.href);  // 用 URL 类拼，自动处理各种情况
    url.protocol = (url.protocol === 'https:') ? 'wss:' : 'ws:';     // http→ws、https→wss（安全升级）
    url.search = '?token=' + encodeURIComponent(currentToken());      // token 塞查询参数并做 URL 编码
    return url.toString();
}
```

**逐点讲解**：

**① 三层兜底取地址**

`backendBase()` 依次尝试：显式 `window.WS_BASE` → `api.js` 里的 `API_BASE` → 同源。为什么这么绕？因为**同一个 `ws.js` 要能用在各种部署场景**：开发时前后端可能不同端口（用 `API_BASE`）；生产可能同域（用 `location.origin`）；测试时可能想临时指定（用 `WS_BASE`）。**三级 fallback 让它在哪都能跑**。

**② `typeof Api !== 'undefined'` 为什么不能直接 `if (Api)`**

如果页面**没加载 `api.js`**，直接写 `if (Api)` 会因为 `Api` 这个标识符**从未声明**而抛 `ReferenceError`。`typeof 未声明变量` 是**唯一不会抛错**的检测方式（返回 `"undefined"`）。这是 JS 的一个经典陷阱。

**③ `new URL(base, location.href)` 的好处**

用浏览器的 `URL` 类拼 URL，而不是字符串手工 `base + '/ws/notifications'`。好处：能正确处理 base 里带路径、带端口的情况；`.protocol`、`.search` 是结构化属性，改起来比字符串替换更可靠。

**④ `encodeURIComponent(token)`**

JWT 里含 `.`、`-`、`_` 这些 URL 安全字符，但万一未来 token 格式变了含特殊字符，不编码会破坏 URL 结构。`encodeURIComponent` 是**给"要放进 URL 的字符串"做保底**的标准手段。

**⑤ `https:` → `wss:`**

**页面是 https 时，WebSocket 必须用 wss**（否则浏览器按"混合内容"**直接拒连**）。这行自动升级，避免手动配错。

### 15.4 心跳

```javascript
function startHeartbeat() {
    stopHeartbeat();                                  // 先清旧的，避免重复计时器叠加
    heartbeatTimer = global.setInterval(function () {
        if (socket && socket.readyState === 1) {      // readyState===1 表示 OPEN（只有开着才发）
            try { socket.send('ping'); } catch (e) { /* 发失败就让 onclose 走重连 */ }
        }
    }, HEARTBEAT_MS);
}

function stopHeartbeat() {
    if (heartbeatTimer) { global.clearInterval(heartbeatTimer); heartbeatTimer = null; }
}
```

**逐点讲解**：

- `setInterval` 每 25 秒执行一次，**只有连接是 OPEN 状态才发**。
- `readyState` 的取值：`0=CONNECTING`、`1=OPEN`、`2=CLOSING`、`3=CLOSED`。只有 `1` 能 `send`。
- `try/catch` 包住 `send`：连接正好在这瞬间断的话 `send` 会抛错，捕获它并**什么都不做**（因为 `onclose` 马上会触发，重连逻辑交给那边）。
- 25 秒的来历：很多路由器/负载均衡的**空闲超时是 30 或 60 秒**。取 25 秒比 30 短，保证在设备掐断之前就发了心跳，连接一直"热"着。

### 15.5 指数退避重连

```javascript
function scheduleReconnect() {
    if (manualClosed) return;                         // 用户主动关的，不重连
    if (reconnectTimer) return;                       // 已经在等重连了，别叠加
    var delay = Math.min(BASE_DELAY * Math.pow(2, retryCount), MAX_DELAY); // 1s,2s,4s...最多 15s
    retryCount++;                                     // 次数 +1
    emit({ type: 'status', state: 'reconnecting', delay: delay, attempt: retryCount });  // 通知 UI
    reconnectTimer = global.setTimeout(function () {
        reconnectTimer = null;
        connect();                                    // 等够时间后重连
    }, delay);
}
```

**逐点讲解**：

- `BASE_DELAY * Math.pow(2, retryCount)` = `1000 * 2^n`：第 0 次等 1 秒、第 1 次 2 秒、第 2 次 4 秒……**指数增长**。这就是**指数退避**——网络刚断时快速重试，一直失败就逐渐"放宽"，避免疯狂重连把服务端打垮。
- `Math.min(..., MAX_DELAY)`：封顶 15 秒。否则重试十几次后等待时间会涨到几小时。
- `if (reconnectTimer) return`：防止"重连还没执行时又安排一次"，导致多个定时器叠加。
- `retryCount = 0` 的**重置时机**在 `onopen`（连上了就归零），保证"下次掉线还是从 1 秒开始退避"。

### 15.6 连接与事件处理

```javascript
function connect() {
    if (socket && (socket.readyState === 0 || socket.readyState === 1)) return; // 连着呢（正在连/已打开）
    manualClosed = false;                              // 标记"这是自动/主动连接，不是用户关闭"
    var url = buildUrl();
    if (!currentToken()) {                             // 没 token 连也白连
        emit({ type: 'status', state: 'error', message: '没有 token，无法连接（请先登录）' });
        return;
    }

    try {
        socket = new WebSocket(url);                   // 建连接（此时 readyState=0）
    } catch (e) {                                      // URL 非法等会抛错
        emit({ type: 'status', state: 'error', message: '创建 WebSocket 失败：' + e.message });
        scheduleReconnect();
        return;
    }

    socket.onopen = function () {                      // 连接打开
        retryCount = 0;                                // 连上了就重置退避
        startHeartbeat();                              // 开始心跳
        emit({ type: 'status', state: 'open' });
    };

    socket.onmessage = function (evt) {                // 收到消息
        var data;
        try { data = JSON.parse(evt.data); } catch (e) { return; }  // 非 JSON（如 pong）直接忽略
        if (data && data.type === 'pong') return;      // 心跳应答不用上抛给业务
        emit(data);                                    // 是业务事件 → 抛给所有监听者
    };

    socket.onclose = function (evt) {                  // 连接关闭
        stopHeartbeat();                               // 停心跳
        socket = null;
        if (manualClosed) { emit({ type: 'status', state: 'closed' }); return; }  // 主动关的，不重连
        if (evt && evt.code === 1008) {                // 1008 = 服务端因鉴权失败主动关闭
            emit({ type: 'status', state: 'error', message: '鉴权失败（token 无效或已过期），请重新登录' });
            return;                                    // 重连也没用，直接报错
        }
        emit({ type: 'status', state: 'closed', code: evt && evt.code });
        scheduleReconnect();                           // 其它情况：安排重连
    };

    socket.onerror = function () {                     // 出错
        // onerror 之后浏览器一定会调 onclose，重连交给 onclose，这里只报状态
        emit({ type: 'status', state: 'error', message: '连接出错' });
    };
}
```

**逐点讲解**：

**① `readyState === 0 || 1` 就不重连**

`0` 是"正在连接中"，`1` 是"已打开"。这两种情况都不该再 `new WebSocket`（会造成多条连接）。只有 `null`（还没建）或 `3`（已关闭）才允许新建。

**② `onmessage` 里的两道过滤**

1. `try { JSON.parse } catch { return }`：**非 JSON 的消息直接忽略**。服务端可能发纯文本，解析失败不该报错。
2. `if (data.type === 'pong') return`：心跳应答**不上抛给业务**——业务只关心任务事件，`pong` 是我们的内部协议。

**③ `1008` 特殊处理（这是最容易做错的地方）**

服务端鉴权失败时以 `1008` 关闭。如果一律重连，会陷入"**连上→被拒→重连→连上→被拒**"的死循环，白白耗资源。这里识别到 1008 就**报错、不重连**——因为"token 无效"这个问题**重连一万次也没用**，得让用户去**重新登录**。

**④ `onerror` 里不做重连**

因为浏览器在 `onerror` 之后**一定会接着调 `onclose`**。重连逻辑只放在 `onclose` 里，避免"两处都重连"导致重复。

### 15.7 主动关闭与 toast

```javascript
function close() {
    manualClosed = true;                               // 先标记：接下来的 onclose 是"主动关"，别重连
    stopHeartbeat();
    if (reconnectTimer) { global.clearTimeout(reconnectTimer); reconnectTimer = null; }  // 取消待执行的重连
    if (socket) { try { socket.close(1000, 'client close'); } catch (e) {} }   // 1000 = 正常关闭
}

// 右下角 toast：不依赖任何 CSS 文件，直接内联样式，放哪都能用
function toast(text, kind) {
    var color = kind === 'error' ? '#d93025' : (kind === 'success' ? '#1a7f37' : '#1f6feb');  // 按类型选颜色
    var box = global.document.createElement('div');    // 创建一个 div（不写 innerHTML，避免 XSS）
    box.style.cssText = [                              // 用 cssText 一次性内联样式，不依赖外部 CSS
        'position:fixed', 'right:16px', 'bottom:16px', 'z-index:99999',
        'max-width:340px', 'padding:12px 14px', 'border-radius:10px',
        'background:#fff', 'color:#111', 'font:13px/1.5 sans-serif',
        'box-shadow:0 6px 24px rgba(0,0,0,.18)', 'border-left:4px solid ' + color,
        'white-space:pre-wrap', 'word-break:break-all'
    ].join(';');
    box.textContent = text;                            // 用 textContent 赋值（安全，不会解析 HTML）
    global.document.body.appendChild(box);             // 加到页面
    global.setTimeout(function () {                    // 6 秒后自动移除
        if (box.parentNode) box.parentNode.removeChild(box);
    }, 6000);
}
```

**逐点讲解**：

**① `manualClosed = true` 必须**先**设置**

`close()` 里第一行就置标记，然后才 `socket.close()`。因为 `socket.close()` 会**同步或很快触发 `onclose`**，而 `onclose` 里要读 `manualClosed`。如果不提前设置，`onclose` 会把"主动关闭"误判成"掉线"，触发一次不必要的重连。

**② `close(1000, 'client close')`**

WebSocket 规范里 `1000` 表示"**正常关闭**"（Normal Closure）。带上这个码，服务端知道是客户端正常退出，不是异常断开。

**③ `cssText` 内联样式**

如果把样式写成独立 `.css` 文件，`ws.js` 就**多了一个部署依赖**（用户忘记引 css 就不好看）。全部内联后，**`ws.js` 自包含**——引一个 js 文件就有完整效果。`join(';')` 把样式数组拼成 CSS 字符串。

**④ `textContent` 而不是 `innerHTML`**

如果用 `innerHTML = text`，万一 `text` 里含 `<script>`（比如任务名被恶意构造），会**执行脚本**（XSS 漏洞）。`textContent` 只当**纯文本**，不解析 HTML，安全。**任何"往页面塞动态内容"的地方都该用 `textContent`**。

**⑤ `if (box.parentNode) box.parentNode.removeChild(box)`**

6 秒后移除通知条。先判 `parentNode` 存在（万一它已经被别的逻辑移除了），再移除——**幂等的清理**。

### 15.8 对外 API 与事件模型

```javascript
global.Notify = {
    connect: connect,                                  // 手动连接
    close: close,                                      // 手动断开
    toast: toast,                                      // 弹一个 toast
    on: function (fn) { listeners.push(fn); return fn; },      // 注册事件回调，返回 fn 方便注销
    off: function (fn) { listeners = listeners.filter(function (f) { return f !== fn; }); },  // 注销
    isOpen: function () { return !!socket && socket.readyState === 1; }   // 当前是否已连接
};
```

**事件模型**：`listeners` 是一个回调数组。`emit(event)` 会依次调用每个回调（外面包了 `try/catch`，某个回调出错不影响其它）。业务代码这样用：

```javascript
Notify.connect();                                      // 连上（token 从 api.js 自动取）
Notify.on(function (evt) {                             // 监听
    if (evt.type === 'task' && evt.status === 'SUCCESS') {
        Notify.toast('任务完成：' + evt.name);          // 弹提示
    }
});
```

**`on` 返回 `fn` 的用处**：`var h = Notify.on(fn)`，之后可以 `Notify.off(h)` 精确注销，**避免匿名函数无法注销**的问题。

---
## 十六、验收脚本：scripts/verify_stage8.py（🟢新建）

### 16.1 为什么要有"验收脚本"

单测验证的是"每个零件好不好用"，但**整条链路通不通**（提交 → 排队 → worker → Redis → 中继 → WS）需要一次真实跑。脚本化的好处：**可重复、结论明确（0=通过）**，不用每次手工敲一堆 curl。

脚本有**两种模式**，对应两个不同层次的验证：

| 模式 | 验证什么 | 前置条件 |
|---|---|---|
| `routing` | 任务分级路由是否真的把三个任务送进 `high`/`default`/`low` | **只需 Redis 在跑**（不用 worker、不用 API） |
| `e2e` | 端到端：提交 → 执行 → 推送 → 收到 | API + worker 都在跑 |

### 16.2 `sys.path` 那两行（最常被忽略、也最容易踩的坑）

```python
import asyncio
import json
import os
import sys

# 把项目根目录塞进 sys.path。
# 为什么需要：直接 `python scripts\verify_stage8.py` 时，Python 只把 scripts\ 当作模块搜索路径，
# 于是 `import app_my...` 会报 ModuleNotFoundError: No module named 'app_my'。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 脚本文件的上一级的上一级 = 项目根
if _ROOT not in sys.path:                                            # 不在才插入（避免重复）
    sys.path.insert(0, _ROOT)                                        # 插到最前面，优先搜索
```

**逐点讲解**：

- `__file__` 是**当前脚本文件的路径**；`os.path.abspath` 转成绝对路径；`os.path.dirname` 取"上一级目录"。
- 套两次 `dirname`：第一次得到 `scripts\`，第二次得到项目根 `ai_chief\`。
- `sys.path` 是 Python 的"**模块搜索路径列表**"。`import app_my` 时它挨个目录找 `app_my` 包。把项目根插进去，`app_my` 就在可搜索范围内，`ModuleNotFoundError` 消失。
- `if _ROOT not in sys.path` 判断避免重复插入。

> 🔴 **实测踩坑记录**：不加这两行时，直接跑脚本报 `ModuleNotFoundError: No module named 'app_my'`。这是"**脚本被执行 vs 包被导入**"两种语境下 `sys.path` 差异导致的经典问题。

### 16.3 模式一：分级路由验证

```python
def mode_routing() -> int:
    import redis                                     # 需要直接连 broker 数队列长度
    from app_my.worker.celery_app import celery_app   # 任务实例
    from app_my.worker.tasks.graph import rebuild_kg_graph
    from app_my.worker.tasks.nutrition import generate_nutrition_report
    from app_my.worker.tasks.reindex import reindex_milvus

    # ① 先看路由表：Celery 认为每个任务该去哪条队列
    expected = {
        "tasks.reindex_milvus": "high",
        "tasks.rebuild_kg_graph": "default",
        "tasks.generate_nutrition_report": "low",
    }
    for name, q in expected.items():
        route = celery_app.amqp.router.route({}, name)     # 用 Celery 内部路由器算"该去哪"
        got = route.get("queue") and getattr(route["queue"], "name", route["queue"])   # 取出队列名
        flag = "OK " if got == q else "!! "                # 对/错标记
        print("    %s%-32s 期望=%-8s 实际=%s" % (flag, name, q, got))

    # ② 实测：清空 broker → 发三个任务 → 看三条队列各自的长度
    r = redis.Redis.from_url(celery_app.conf.broker_url, decode_responses=True)   # 连 broker(db1)
    r.flushdb()                                        # 清空 db1（开跑前先确保干净）
    reindex_milvus.delay(rebuild=True, tenant_id=1, user_id=1)               # 投任务 1
    rebuild_kg_graph.delay(rebuild=False, tenant_id=1, user_id=1)            # 投任务 2
    generate_nutrition_report.delay(ingredients=DEMO_INGREDIENTS, tenant_id=1, user_id=1)   # 投任务 3

    lens = {}
    for q in ("high", "default", "low"):
        lens[q] = r.llen(q)                            # LLEN 数每条队列的长度
        print("    %-8s LLEN=%s" % (q, lens[q]))

    r.flushdb()                                        # 收尾再清空，避免残留消息干扰后面

    if lens == {"high": 1, "default": 1, "low": 1}:     # 三队列各 1 条 = 路由正确
        print("\n结果：✅ 分级路由生效")
        return 0
    return 1
```

**逐点讲解**：

**① `celery_app.amqp.router.route({}, name)`**

这是**直接问 Celery 内部路由器**："任务 `name` 该去哪个队列？" 传空字典当数据集、传任务名。返回的 `route["queue"]` 可能是个 `Queue` 对象（带 `.name`）也可能是个字符串，所以用 `getattr(route["queue"], "name", route["queue"])` 兼容两种情况。这一句是把"配置"和"实际行为"做**对照**。

**② `flushdb()` 的注意事项（🔴 重要）**

`r.flushdb()` 会清空**整个当前 db**。这里 `r` 连的是 broker（db1），所以只清队列，**不碰业务 db0**。**如果连的不是 db1 而是 db0，一句 flushdb 就能把用户的缓存、限流计数、JWT 黑名单全清光**——这是高危操作。脚本里专门用 `celery_app.conf.broker_url` 连接，就是为了"**只清对的 db**"。

**③ 为什么跑前必须先停 worker**

如果不启动 worker，投进去的 3 条消息会**静静躺在队列里**，`LLEN` 就是 `1,1,1`。如果 worker 在跑，消息会被**瞬间消费走**，`LLEN` 就变成 `0,0,0`，测不出路由。所以这个模式要求"**先停 worker**"。这是"**要知道你在测什么状态**"的典型例子。

**④ `lens == {"high": 1, "default": 1, "low": 1}` 直接比较字典**

Python 字典的 `==` 比较的是"键值对是否完全相同"，所以这一行就等于"三个队列都恰好 1 条"。简洁。

### 16.4 模式二：端到端验证

```python
def mode_e2e(base_url: str = None) -> int:
    import time
    import websockets                                 # 真连 WS 的库

    if not base_url:
        base_url = os.environ.get("STAGE8_BASE_URL", "http://127.0.0.1:9002")   # 可用环境变量覆盖端口

    import requests                                   # 发 HTTP 请求
    username = "stage8verify_%d" % int(time.time())   # 用时间戳做唯一用户名，避免撞名
    password = "stage8-verify-123"

    # ... 注册 + 登录，拿 token ...
    token = r.json()["access_token"]

    async def run_ws_case() -> int:                   # 用 async 写 WS 逻辑（websockets 库是异步的）
        ws_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = ws_base + "/ws/notifications?token=" + token
        got = []

        async with websockets.connect(ws_url) as ws:   # 建立 WS 连接（with 保证退出时关闭）
            await ws.send("ping")                      # 发心跳
            pong = await asyncio.wait_for(ws.recv(), timeout=5)   # 等 pong（最多 5 秒）
            # ... 提交任务、等待推送 ...
            while time.time() < deadline:              # 循环等推送，最多 90 秒
                raw = await asyncio.wait_for(ws.recv(), timeout=...)   # 等一条消息
                event = json.loads(raw)
                if event.get("type") != "task" or event.get("task_id") != task_id:
                    continue                           # 不是本次任务的事件，跳过
                got.append(event["status"])            # 记录状态
                if event["status"] in ("SUCCESS", "FAILURE"):
                    break                              # 终态，停止等待

        if got and got[0] == "STARTED" and got[-1] == "SUCCESS":   # 事件序列符合预期
            print("\n结果：✅ 端到端链路打通")
            return 0
        return 1

    code = asyncio.run(run_ws_case())                  # 跑异步逻辑

    # 清理临时账号，别在库里留垃圾
    try:
        import psycopg2
        from app_my.core.config import settings
        dsn = settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://", 1)   # 驱动前缀转换
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (username,))   # 参数化删除（防注入）
        conn.close()
    except Exception as exc:
        print("[8] 临时账号清理失败（不影响结论）：%s" % exc)

    return code
```

**逐点讲解**：

**① `os.environ.get("STAGE8_BASE_URL", "http://127.0.0.1:9002")`**

先看环境变量，没有就用默认值 `9002`。

> 🔴 **实测踩坑记录**：最初脚本**硬编码 9002**，但实测时后端临时跑在 **9018**，导致 WS 握手返回 `HTTP 403`（连到错误的服务了）。修复方式就是支持环境变量覆盖：`set STAGE8_BASE_URL=http://127.0.0.1:9018` 后再跑。**硬编码端口是脚本不灵活的头号原因**。

**② `async with websockets.connect(...)`**

`websockets` 库的连接对象是**异步上下文管理器**。`async with` 保证块结束时**自动关闭连接**（即使中间抛异常）。

**③ `asyncio.wait_for(coro, timeout=5)`**

给一个协程加"**超时**"。等 `ws.recv()` 超过 5 秒就抛 `asyncio.TimeoutError`。**没有超时的等待在网络编程里是危险的**（可能永远挂着）。给每个网络等待加超时，是基本素养。

**④ 过滤 `task_id` 的原因**

WS 是**按租户广播**的——同租户可能有别的任务事件混进来。所以只认 `type=="task"` 且 `task_id` 是本次提交的那个。

**⑤ `got[0] == "STARTED" and got[-1] == "SUCCESS"`**

断言"第一条是 STARTED、最后一条是 SUCCESS"。这验证了**完整的生命周期通知**都推到了（不只是最终结果）。如果只有 SUCCESS 没有 STARTED，说明 `before_start` 钩子没发出去。

**⑥ 账号清理的 DSN 转换**

`settings.DATABASE_URL` 用的是 SQLAlchemy 格式 `postgresql+psycopg2://...`，而裸 `psycopg2.connect` **不认 `+psycopg2`** 这个后缀。所以 `.replace("postgresql+psycopg2://", "postgresql://", 1)` 去掉驱动标记（`1` 表示只替换第一处）。**"给不同的库传不同的连接串格式"是常见坑**。

**⑦ `cur.execute("... WHERE username = %s", (username,))` 参数化**

`%s` 占位 + 元组传参，是 `psycopg2` 的**参数化查询**写法。它由驱动负责安全转义，**防止 SQL 注入**。绝不可以用 f-string 把变量拼进 SQL。注意 `(username,)` 那个**逗号**——`(username)` 只是个加了括号的字符串，`(username,)` 才是单元素元组。

### 16.5 `main()` 分发

```python
def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]   # 过滤掉 -开头的选项，只留位置参数
    mode = args[0] if args else ""                              # 第一个位置参数 = 模式
    if mode == "routing":
        return mode_routing()
    if mode == "e2e":
        return mode_e2e()
    print(__doc__)                                              # 没给模式就打帮助
    return 2                                                    # 退出码 2 = 用法错误
```

`return 0` 表示成功、`1` 表示验证失败、`2` 表示用法错误——**用退出码表达结果**，方便将来接 CI（CI 靠退出码判断成功失败）。

---

## 十七、可观测接线：docker/prometheus 两个 yml（🔵修改）

### 17.1 为什么 worker 要单独抓

阶段 7 已经抓了 FastAPI 的 `:9002/metrics`。但 **worker 是另一个进程**，它的 `celery_*` 指标只在它自己的 `:9101/metrics` 上。所以 Prometheus 要多一个 job。

### 17.2 prometheus.yml：新增一个 job

```yaml
  - job_name: "ai_chief_worker"                 # 新任务名
    metrics_path: /metrics                      # 抓取路径
    static_configs:
      - targets: ["host.docker.internal:9101"]  # 从容器里访问宿主机的 9101
        labels:                                 # 给这批指标打标签，便于筛选
          app: ai_chief
          component: celery_worker              # 一眼区分"这是 worker 的指标"
          env: dev
```

**逐点讲解**：

**① `host.docker.internal:9101` 是什么**

Prometheus 跑在 Docker 容器里，worker 跑在**宿主机**上（本项目 worker 直接跑在 Windows 的 venv 里，不在容器）。容器内的 `localhost` 指的是**容器自己**，访问不到宿主机的 9101。`host.docker.internal` 是 Docker Desktop 提供的**特殊主机名**，专门用于"**容器访问宿主机**"。这是 Windows/macOS Docker 的约定（Linux 上需要额外配 `extra_hosts`）。

**② `component: celery_worker` 标签的用处**

有了这个标签，Grafana 里就能写 `{component="celery_worker"}` 只筛 worker 指标；告警规则也能按组件区分。**标签是 Prometheus 的"分类维度"**。

### 17.3 alerts.yml：新增两条告警

```yaml
      - alert: CeleryTaskFailure                        # 告警名
        expr: increase(celery_task_failures_total[5m]) > 0   # 表达式：5 分钟内失败数增长 > 0
        for: 1m                                         # 持续 1 分钟才真正触发（防止抖动误报）
        labels:
          severity: warning                             # 告警级别
          service: ai_chief
          component: celery_worker
        annotations:
          summary: "Celery 任务 {{ $labels.task }} 执行失败"
          description: "任务 {{ $labels.task }} 在最近 5 分钟内出现失败，请查 worker 终端日志确认原因。"

      - alert: CeleryQueueBacklog                       # 队列积压告警
        expr: celery_queue_depth > 10                   # 队列积压超过 10 条
        for: 5m                                         # 持续 5 分钟
        labels:
          severity: warning
        annotations:
          summary: "队列 {{ $labels.queue }} 积压（当前 {{ $value }} 条）"
          description: "队列 {{ $labels.queue }} 待处理任务持续超过 10 条，请检查 worker 是否在正常消费。"
```

**逐点讲解**：

**① `increase(celery_task_failures_total[5m]) > 0`**

- `[5m]` 是**时间窗口**：取最近 5 分钟的数据点。
- `increase(...)` 算这个窗口里 **Counter 增长了多少**（因为 Counter 只增不减，`increase` 自动处理"重启归零"的情况）。
- `> 0` 表示"这 5 分钟里至少失败过 1 次"。

**为什么不直接写 `celery_task_failures_total > 0`**？因为那样会**永久告警**——只要历史上失败过一次，这个数就永远 > 0，告警再也不会恢复。用 `increase([5m])` 才能表达"**最近才发生的失败**"。

**② `for: 1m` / `for: 5m` 的作用**

告警表达式"为真"之后，还要**持续这么久**才真正触发。防的是"**瞬时抖动误报**"：比如某个任务偶发失败一次，1 分钟后再没失败，就不该报警。`for` 是告警的"**冷静期**"。

**③ `{{ $labels.task }}` 模板变量**

在告警文本里**动态插入标签值**。这样告警消息会变成"Celery 任务 **tasks.reindex_milvus** 执行失败"——**一眼知道是哪个任务**，不用去图表里翻。`{{ $value }}` 同理，插入"当前的值"（积压多少条）。

**④ 为什么积压阈值定 10、窗口定 5m**

三条队列平时大多是 0~1 条。超过 10 条说明**worker 明显跟不上提交速度了**（可能挂了、可能卡住）。给 5 分钟窗口，是为了排除"批量提交 15 个任务，1 分钟内就被消化完"的正常瞬时高峰。

---

## 十八、单元测试怎么验证这套机制

本阶段新增 **27 个测试用例**，分 5 个文件。它们不是"重复验收脚本"，而是**逐个零件**地验证机制正确。这里讲每个文件"在测什么机制、为什么这么测"（测试代码本身较长，不逐行贴，重点讲思路）。

### 18.1 `tests/unit/test_celery_app.py`（6 例）— 验证配置正确

测的是"**配置读出来的值对不对**"，而不是"跑起来对不对"：

- 三条队列名是不是 `high`/`default`/`low`；
- `task_routes` 里三个任务各配到哪条队列；
- broker/backend 是不是分别指向 db1/db2；
- `imports` 是不是包含三个任务模块和 signals。

**为什么值得测**：路由表是全字符串配置，**写错一个字母不报错，只是任务悄悄跑错队列**。静态断言能在改配置时立刻发现手滑。

### 18.2 `tests/unit/test_notify.py`（4 例）— 验证事件结构

- `build_task_event` 产出的 dict 是不是**恰好**包含那 8 个字段、`type` 是不是 `"task"`；
- 缺省参数（`result=None`）时结构是否稳定；
- `publish_task_event` 在 Redis 不可用时是否**返回 0 且不抛异常**（验证"降级"行为）。

**为什么值得测**：`build_task_event` 是**纯函数**，测它不需要 Redis，成本极低，收益是"消息结构永远稳定"——前端解析逻辑可以放心写。

### 18.3 `tests/unit/test_ws_manager.py`（5 例）— 验证连接管理与租户隔离

- `connect` 之后连接是否进了正确的租户分组；
- `disconnect` 是否从两张表里都摘干净、是否**幂等**（调两次不报错）；
- `dispatch` 是否**只推给同租户**（这就是"租户隔离"的自动化证明，对应验收标准第 8 条）；
- 某租户的连接发失败时，是否被**清掉**且返回值正确。

**为什么值得测**：租户隔离是**安全属性**——一旦写错，A 租户的数据会泄漏给 B。这种"错不起"的逻辑**必须有测试兜底**。测试里用假的 websocket 对象（mock）来模拟，不依赖真网络。

### 18.4 `tests/unit/test_ws_gateway.py`（4 例）— 验证鉴权

- 无 token、乱码 token、refresh token 三种情况是否都被拒（模拟 `1008`）；
- 合法 token 是否能通过并拿到正确的 `(tenant_id, user_id)`；
- 心跳 `ping` 是否回 `pong`。

**为什么值得测**：WS 端点**绕过了 HTTP 中间件**（第十一节讲过），它的鉴权是**自己写的**。自己写的安全逻辑最需要测试覆盖。这样"以后重构 gateway 时"能立刻发现鉴权被改坏。

> 🟡 这里有个实测修正：断言里的期望值（"估算本餐总热量 **215.0** 千卡"）是**按真实计算结果对齐的**——最初写的是 `268.9`，实测营养工具算出来是 `215.0`，于是改成实际值。**测试的期望值必须来自真实运行，不能凭想象填**。

### 18.5 `tests/unit/test_task_api.py`（8 例）— 验证接口

- 三个提交接口是否都返回 `task_id` 且 `queue` 正确；
- 参数校验（空 `ingredients` 是否 422）；
- `GET /tasks/{id}` 在成功/失败/未完成时各返回什么。

**这里踩了两个坑**：

1. **`GET /tasks/{task_id}` 返回 401**：因为它被 `AuthMiddleware` 保护。修复是**加 `auth_headers` fixture** 带上 token。教训：**新增接口默认继承全局中间件保护**。
2. **失败路径测不到 FAILURE 指标**：因为 `task_eager_propagates=True` 时异常直接抛出、跳过 `on_failure`（第五节讲过）。修复是**新增 `eager_non_propagating` fixture**（`task_eager_propagates=False`），让异常走正常路径。

### 18.6 测试基线

| 口径 | 数量 |
|---|---|
| 阶段 7 收官基线 | 91 passed, 7 deselected |
| 本阶段新增 | 27 例（5 个文件） |
| **阶段 8 收官** | **118 passed, 7 deselected** |

---

## 附：一条数据的完整旅程（把全链路串起来）

最后用**一次真实的"营养报告"提交**，把前面所有文件串成一条线。跟着编号走一遍，你就理解了整个阶段 8：

```text
【提交阶段】
① 浏览器 POST /tasks/nutrition-report  {ingredients:["鸡蛋 100克","西兰花 200克"]}
② main.py 的中间件链：CORS → TraceID → Auth（校验 JWT，塞 request.state.user_id）
   → TenantContext（塞 request.state.tenant_id）→ 限流 → 配额
③ api/tasks.py::submit_nutrition_report 被调用
   → _caller(request) 取出 tenant_id=58, user_id=77
   → generate_nutrition_report.delay(ingredients=..., tenant_id=58, user_id=77)
④ Celery 根据 task_routes 查到 "tasks.generate_nutrition_report" → low 队列
   → 把 {"task":"tasks.generate_nutrition_report","args":[...],"kwargs":{...}} 序列化成 JSON
   → LPUSH 进 Redis db1 的 "low" 列表
⑤ 接口立刻返回 {"task_id":"abc-123","queue":"low","status":"PENDING"}   ← 全程几毫秒

【执行阶段】（worker 进程，独立运行）
⑥ worker 从 Redis db1 的 low 队列取到这条消息
   → 反序列化 → 找到 generate_nutrition_report 函数
⑦ base.py::NotifyTask.before_start 被触发
   → self._s8_t0 = perf_counter() 开始计时
   → _read_ctx: tenant_id=58, user_id=77, queue="low"
   → worker_metrics::task_started("tasks.generate_nutrition_report","low")  再加 celery_task_total +1
   → notify::publish_task_event({type:"task",status:"STARTED",tenant_id:58,...})
   → PUBLISH 到 Redis 频道 ai_chief:ws:notify
⑧ nutrition.py 函数体执行：清洗食材 → calculate_nutrition.invoke(...) → 得 215.0 千卡
⑨ base.py::NotifyTask.on_success 被触发
   → seconds = perf_counter() - _s8_t0
   → task_succeeded(...)  记 SUCCESS + 耗时直方图
   → publish_task_event({type:"task",status:"SUCCESS",result:{...},tenant_id:58,...})

【推送阶段】（FastAPI 进程，一直都在跑）
⑩ relay.py::run_relay 的 `async for message in pubsub.listen()` 收到两条消息（STARTED / SUCCESS）
   → json.loads 解析
   → manager.dispatch(event)  取 tenant_id=58 的连接集合
   → 对每个连接 await ws.send_json(event)
⑪ 浏览器 frontend/js/ws.js 的 socket.onmessage 触发
   → JSON.parse → 不是 pong → emit(event)
   → 业务回调收到 {type:"task",status:"SUCCESS",...} → Notify.toast("任务完成") → 右下角弹绿条
```

**贯穿全链路的三条设计原则**（这才是本阶段真正的知识点）：

1. **解耦**：提交与执行分开（Celery）、执行与推送分开（Redis pub/sub + 中继）。每一环都只做一件事，坏了能单独换。
2. **降级**：通知/指标失败**绝不影响任务本身**（`base.py` / `notify.py` 里的 try/except + 返回 0）。
3. **隔离**：Redis 三个 db 各管一摊（业务/broker/backend）、连接按 tenant_id 分组、eager 模式与真 worker 用开关区分——**互不干扰**。

---

> **至此，阶段 8 说明手册结束。**
> 配套《操作手册》负责"怎么做"，本手册负责"为什么"。
> 下一阶段（阶段 9：微服务拆分 + Kong 网关）会把这里的单体拆成多个服务——**本阶段做的任务解耦，正是拆服务的前提**：长任务已经不在请求线程里了，搬服务时不会把阻塞一起搬过去。

