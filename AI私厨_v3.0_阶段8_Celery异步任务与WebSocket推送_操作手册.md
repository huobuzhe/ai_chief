# AI 私厨 v3.0 阶段 8 操作手册 — Celery 异步任务队列 + WebSocket 实时推送

> **阶段定位**：把三件"长任务"（Milvus 菜谱向量重索引 / Neo4j 图谱重建 / 营养报告生成）从同步请求里剥离出来，接口立刻返回 `task_id`，worker 在后台慢慢跑，跑完通过 WebSocket 主动推给浏览器。对应原规划阶段 4，被后移到全栈监控（阶段 7）之后、微服务拆分（阶段 9）之前——因为阶段 9 拆服务时，长任务必须先解耦，否则搬服务会把阻塞一起搬过去。
>
> **本手册性质**：照着做——步骤 / 命令 / 验证 / 排错一站到底。**代码为什么这么写**见配套《说明手册》，本手册不重复解释。
>
> 🔴 **前置硬条件**：阶段 1~7 已收官。开工前 pytest 基线必须是 **91 passed, 7 deselected**（阶段 7 收官值）。阶段 8 收官值 **118 passed, 7 deselected**（净增 27 例）。
>
> 🟡 **本阶段不新增任何容器**——broker 与 result backend 复用阶段 1 起就在跑的 **Redis 6380**，只换 `db` 编号隔离（业务 db0 / broker db1 / backend db2）。16GB 机器零额外内存压力。
>
> 🟢 **本手册里每一段代码、每一条命令，都已在项目源码的临时副本 + 你机器上真实运行的一整套容器（Redis 6380 / PostgreSQL 5433 / Milvus / Neo4j）上实测通过**。实测结论见 [二十三、启动与验证](#二十三启动与验证端到端实测记录)。

---

## 目录

- [一、阶段目标与验收标准](#一阶段目标与验收标准)
- [二、简历叙事（照写）](#二简历叙事照写)
- [三、范围 & 与原方案差异（颜色标注）](#三范围--与原方案差异颜色标注)
- [四、端口、Redis db 分配与文件归属](#四端口redis-db-分配与文件归属)
- [五、文件清单（新建 / 修改）](#五文件清单新建--修改)
- [六、准备：切分支、核基线、装 Celery](#六准备切分支核基线装-celery)
- [七、子模块 1：新增 6 个配置项（app_my/core/config.py 🔵修改）](#七子模块-1新增-6-个配置项app_mycoreconfigpy--修改)
- [八、子模块 2：任务事件通知（app_my/core/notify.py 🟢新建）](#八子模块-2任务事件通知app_mycorenotifypy--新建)
- [九、子模块 3：worker 自己的指标（app_my/core/worker_metrics.py 🟢新建）](#九子模块-3worker-自己的指标app_mycoreworker_metricspy--新建)
- [十、子模块 4：Celery 应用实例（app_my/worker/ 🟢新建 2 个文件）](#十子模块-4celery-应用实例app_myworker--新建-2-个文件)
- [十一、子模块 5：任务基类 NotifyTask（app_my/worker/base.py 🟢新建）](#十一子模块-5任务基类-notifytaskapp_myworkerbasepy--新建)
- [十二、子模块 6：worker 生命周期信号（app_my/worker/signals.py 🟢新建）](#十二子模块-6worker-生命周期信号app_myworkersignalspy--新建)
- [十三、子模块 7：三个长任务（app_my/worker/tasks/ 🟢新建 4 个文件）](#十三子模块-7三个长任务app_myworkertasks--新建-4-个文件)
- [十四、子模块 8：接口数据模型（app_my/schemas/tasks.py 🟢新建）](#十四子模块-8接口数据模型app_myschemastaskspy--新建)
- [十五、子模块 9：任务提交与查询接口（app_my/api/tasks.py 🟢新建）](#十五子模块-9任务提交与查询接口app_myapitaskspy--新建)
- [十六、子模块 10：WebSocket 三件套（app_my/ws/ 🟢新建 4 个文件）](#十六子模块-10websocket-三件套app_myws--新建-4-个文件)
- [十七、子模块 11：main.py 接入（🔵修改）](#十七子模块-11mainpy-接入-修改)
- [十八、子模块 12：前端 WS 客户端（frontend/ 🟢新建 2 个文件）](#十八子模块-12前端-ws-客户端frontend--新建-2-个文件)
- [十九、子模块 13：Prometheus 抓 worker + 2 条告警（🔵修改 2 个 yml）](#十九子模块-13prometheus-抓-worker--2-条告警-修改-2-个-yml)
- [二十、子模块 14：验收脚本（scripts/verify_stage8.py 🟢新建）](#二十子模块-14验收脚本scriptsverify_stage8py--新建)
- [二十一、子模块 15：单元测试（27 例 🟢新建 5 个文件）](#二十一子模块-15单元测试27-例--新建-5-个文件)
- [二十二、requirements.txt 登记（🔵修改）](#二十二requirementstxt-登记-修改)
- [二十三、启动与验证（端到端实测记录）](#二十三启动与验证端到端实测记录)
- [二十四、提交 Gitee 与 PR 描述](#二十四提交-gitee-与-pr-描述)
- [二十五、常见错误对照表](#二十五常见错误对照表)
- [二十六、避坑提示](#二十六避坑提示)
- [二十七、本阶段防呆自检清单](#二十七本阶段防呆自检清单)

---

## 一、阶段目标与验收标准

### 1.1 阶段目标

1. **Celery 任务队列落地**：以 Redis 6380 为 broker（db1）与 result backend（db2），建 `high` / `default` / `low` **三条分级队列**，按任务重要性与耗时分流，避免"一个重索引把营养报告堵死"。
2. **三个长任务异步化**：Milvus 重索引（high）、Neo4j 图谱重建（default）、营养报告（low）全部改为 Celery task。**提交接口毫秒级返回 `task_id`**，不再让浏览器干等几十秒。
3. **任务状态可查**：`GET /tasks/{task_id}` 返回 `PENDING / STARTED / SUCCESS / FAILURE` + 结果或错误摘要。
4. **WebSocket 实时推送闭环**：`/ws/notifications`，JWT 鉴权（走 `?token=` 查询参数），连接按 `tenant_id` 分组；worker 任务结束 → Redis pub/sub → FastAPI 常驻中继 → 推给该租户所有在线连接。
5. **任务可观测**：worker 进程独立暴露 `:9101/metrics`（任务次数 / 耗时直方图 / 失败数 / 队列深度），接入阶段 7 的 Prometheus，并补 2 条告警（任务失败 / 队列积压）。
6. **前端 WS 客户端**：`frontend/js/ws.js` 负责断线指数退避重连 + 心跳保活 + 右下角 toast；配套一个验证页 `frontend/stage8-tasks.html`。

### 1.2 验收标准（逐条可验）

| # | 验收项 | 判定方式 |
|---|---|---|
| 1 | pytest 基线 91 → **118 passed, 7 deselected** | `pytest -q` 看尾行 |
| 2 | 分级路由真的生效 | `scripts\verify_stage8.py routing` 输出 `high=1 default=1 low=1` |
| 3 | 提交接口不阻塞 | 耗时 < 50ms，响应含 `task_id`（见 23.6） |
| 4 | worker 起来日志正确 | 日志里 `transport: redis://localhost:6380/1`、`results: ...6380/2`、三队列、三任务 |
| 5 | worker 指标可抓 | `curl http://127.0.0.1:9101/metrics` 有 `celery_task_total` / `celery_queue_depth` |
| 6 | WS 鉴权有效 | 无 token / refresh token / 乱码 token 一律被 `1008` 拒绝 |
| 7 | 端到端推送成功 | `scripts\verify_stage8.py e2e` 输出 `STARTED → SUCCESS` |
| 8 | 租户隔离有效 | 单测 `test_dispatch_only_reaches_same_tenant` 通过 |
| 9 | 浏览器右下角弹通知 | 打开 `frontend/stage8-tasks.html`，登录后提交营养报告，页面右下角出现绿色 toast |
| 10 | 通知失败不影响任务 | 单测 `test_publish_task_event_swallows_redis_error` 通过 |

---

## 二、简历叙事（照写）

> 落地 **Celery 分布式任务队列 + WebSocket 实时推送**：把知识库向量重索引、Neo4j 图谱重建、营养报告生成等长任务从同步请求中剥离，接口由"等几十秒"变为毫秒级返回 `task_id`；按 `high / default / low` **三级队列分流削峰**，broker 与 result backend 复用 Redis 并做 **db 级键空间隔离**（db0 业务 / db1 broker / db2 backend）。实现 **JWT 鉴权**的 WebSocket 网关（浏览器 WS 无法自定义 header，令牌走查询参数），连接池按 `tenant_id` 分组，worker 侧通过 **Redis pub/sub** 跨进程中继任务事件，实现"任务完成即时推送"，与既有 SSE 流式对话形成**双协议实时通信**架构。任务级指标（次数 / 耗时直方图 / 失败 / 队列深度）经独立端口接入 Prometheus，并配任务失败与队列积压告警。pytest 91 → 118 passed（新增 27 例）。

---

## 三、范围 & 与原方案差异（颜色标注）

| 项 | 原方案（阶段总表·草案） | 本阶段做法 | 标签 |
|---|---|---|---|
| broker 选型 | "建议复用 Redis 6380；备选 RabbitMQ" | **复用 Redis 6380**，broker=db1 / backend=db2 / 业务=db0 | 🟡 开工确认：用户决策选 Redis，不额外起 RabbitMQ（省 ~0.5GB 内存） |
| 长任务范围 | 重索引 / 图谱重建 / 营养报告 | **三个全做** | 🟡 开工确认：用户决策"全部都要" |
| 任务分级队列 | high / default / low | 严格按规划 | 🟢 新增 |
| 任务状态查询 | `GET /tasks/{task_id}` | 严格按规划 | 🟢 新增 |
| WebSocket 网关 | JWT 鉴权、按 tenant 分组 | 严格按规划，**令牌走 `?token=` 查询参数** | 🟢 新增 |
| 完成即推送 | worker 回写 Redis pub/sub → WS 网关订阅后推 | 严格按规划，多一个常驻"中继协程"（`ws/relay.py`） | 🟢 新增 |
| 前端 WS 客户端 | "右下角 toast，断线自动重连" | `frontend/js/ws.js` + `frontend/stage8-tasks.html` | 🟢 新增 |
| worker 指标 | "prometheus_client **multiprocess 模式**" | **改用单进程 `start_http_server(9101)`** | 🔵 修改：Windows + `--pool=solo` 就是单进程，multiprocess 模式（要 `PROMETHEUS_MULTIPROC_DIR` + 环境变量）纯属多余复杂度 |
| 全局重试策略 | 未提及 | 重索引 `max_retries=1`，图谱重建/营养报告 `max_retries=0` | 🟢 新增：区分"临时抖动可重试"与"要么成要么不成" |
| 任务接口前缀 | 未指定 | `/tasks/*`（4 个端点） | 🟢 新增 |
| 依赖 | — | 新增 `celery==5.6.3`（带出 kombu/amqp/billiard/vine 等） | 🟢 新增 |
| 容器 | — | **0 个新容器** | 🟣 补充：全复用现有 Redis |

---

## 四、端口、Redis db 分配与文件归属

### 4.1 端口（本阶段新增 1 个端口）

| 组件 | 端口 | 归属 | 状态 |
|---|---|---|---|
| 后端 API | 9002 | 阶段 1 | ✅ 已在跑 |
| Redis（业务 db0） | 6380 | 阶段 1 | ✅ |
| PostgreSQL（经 PgBouncer） | 9432 | 阶段 1/5 | ✅ |
| Milvus | 19530 | 阶段 6 | ✅ |
| Neo4j | 7474 / 7687 | 阶段 3 | ✅ |
| Prometheus | 9090 | 阶段 7 | ✅ |
| Grafana | 3300 | 阶段 7 | ✅ |
| AlertManager | 9093 | 阶段 7 | ✅ |
| Loki | 3100 | 阶段 7 | ✅ |
| **Celery worker 指标** | **9101** | **阶段 8** | 🟢 新增 |
| **`/ws/notifications`** | 挂在 9002 上 | **阶段 8** | 🟢 新增（不占新端口） |
| Celery worker 进程 | 无端口 | 阶段 8 | 🟢 新增（前台进程） |

### 4.2 🔴 Redis db 分配（最关键的一张表）

同一个 Redis 6380，用 **db 编号**做物理隔离。三套数据互不可见，不可能撞键：

| db | 用途 | 谁在写 | 谁在读 |
|---|---|---|---|
| **db0** | 业务：缓存（rag/rag2）、限流计数、配额、JWT 黑名单 | API 进程 | API 进程 |
| **db1** | **Celery broker**（任务消息队列 `high`/`default`/`low`） | API 进程（投递）/ worker（消费） | worker |
| **db2** | **Celery result backend**（任务状态与返回值） | worker | API 进程（`GET /tasks/{id}`） |

> 🟡 为什么不用"同一 db + 不同 key 前缀"？因为 Celery 的 broker key 名就是队列名（`high`/`default`/`low`），前缀是全局配置项，改起来影响所有队列；而 db 编号隔离是 Celery 原生支持、零风险、一眼看懂。**实测已确认**：broker 里的 key 只有 `high` / `default` / `low` 和一个 `_kombu.binding.default`，完全不碰业务 key（业务 db0 实测始终有 31 个 key，没被污染）。

### 4.3 worker 与 API 的关系

```
                    ┌──────────────────────────────────────┐
   浏览器 ──HTTP──▶ │  FastAPI 进程 (uvicorn :9002)        │
      │             │   ├─ POST /tasks/*  → 投递任务       │
      │             │   ├─ GET  /tasks/{id} → 读 db2 查状态 │
      │             │   └─ 常驻协程 ws/relay 订阅 Redis 频道 │
      │             └───────────┬──────────────────────────┘
      │  ws://.../ws/notifications?token=xxx                │
      └─────────────────────────┤ publish/subscribe (Redis 6380)
                                │
                    ┌───────────▼──────────────────────────┐
                    │  Celery worker 进程 (--pool=solo)     │
                    │   ├─ 从 db1 取任务                    │
                    │   ├─ 跑完写结果到 db2                 │
                    │   └─ 跑完 publish 事件到频道           │
                    │      ai_chief:ws:notify              │
                    └──────────────────────────────────────┘
```

🔴 **两个进程必须同时活着**：worker 不在 → 任务永远 `PENDING`；API 不在 → 没人订阅频道，worker 发了通知也没人收。

---

## 五、文件清单（新建 / 修改）

### 5.1 🟢 新建（24 个）

| 分组 | 文件 | 作用 |
|---|---|---|
| 核心 | `app_my/core/notify.py` | 构造 + 发布任务事件（Redis 频道） |
| 核心 | `app_my/core/worker_metrics.py` | worker 侧 4 个 Prometheus 指标 + 指标 HTTP 服务 |
| worker | `app_my/worker/__init__.py` | 包标记 |
| worker | `app_my/worker/celery_app.py` | **Celery 全局唯一实例**（broker/队列/路由） |
| worker | `app_my/worker/base.py` | `NotifyTask` 基类（三个生命周期钩子：通知 + 指标） |
| worker | `app_my/worker/signals.py` | `worker_ready` / `task_postrun` / `worker_shutdown` |
| worker | `app_my/worker/tasks/__init__.py` | 包标记 |
| worker | `app_my/worker/tasks/reindex.py` | 长任务①：Milvus 向量重索引（high） |
| worker | `app_my/worker/tasks/graph.py` | 长任务②：Neo4j 图谱重建（default） |
| worker | `app_my/worker/tasks/nutrition.py` | 长任务③：营养报告（low） |
| 接口 | `app_my/schemas/tasks.py` | 5 个 Pydantic 进出模型 |
| 接口 | `app_my/api/tasks.py` | 4 个端点（3 提交 + 1 查询） |
| WS | `app_my/ws/__init__.py` | 包标记 |
| WS | `app_my/ws/manager.py` | 连接管理器（按 `tenant_id` 分组）+ 全局单例 |
| WS | `app_my/ws/gateway.py` | `/ws/notifications` 端点（WS 侧 JWT 鉴权） |
| WS | `app_my/ws/relay.py` | 常驻协程：订阅 Redis 频道 → 派发给本进程连接 |
| 前端 | `frontend/js/ws.js` | WS 客户端（重连退避 + 心跳 + toast） |
| 前端 | `frontend/stage8-tasks.html` | 手工验证页（登录 / 连接 / 提交 / 看日志） |
| 脚本 | `scripts/verify_stage8.py` | 验收脚本（`routing` / `e2e` 两种模式） |
| 测试 | `tests/unit/test_celery_app.py` | 6 例 |
| 测试 | `tests/unit/test_notify.py` | 4 例 |
| 测试 | `tests/unit/test_ws_manager.py` | 5 例 |
| 测试 | `tests/unit/test_ws_gateway.py` | 4 例 |
| 测试 | `tests/unit/test_task_api.py` | 8 例 |

### 5.2 🔵 修改（5 个）

| 文件 | 改什么 |
|---|---|
| `app_my/core/config.py` | 在阶段 7 的 PROMETHEUS/LOKI 段之后、CORS 段之前，插入 6 个配置项 |
| `main.py` | 加 `import asyncio`、3 个 import、lifespan 里启动/取消中继协程、注册 2 个路由 |
| `requirements.txt` | 追加 Celery 及其直接依赖的钉版行 |
| `docker/prometheus/prometheus.yml` | 加一个 `ai_chief_worker` 抓取任务（`host.docker.internal:9101`） |
| `docker/prometheus/alerts.yml` | 加 2 条告警（`CeleryTaskFailure` / `CeleryQueueBacklog`） |

---

## 六、准备：切分支、核基线、装 Celery

### 6.1 打开 PowerShell，进入项目根目录

```powershell
cd F:\pycharm_aiprogram\ai_chief
```

**预期**：命令提示符变成 `PS F:\pycharm_aiprogram\ai_chief>`。

> 本手册后续所有命令都假设你**已经在这个目录**。如果你换了目录，每条命令前都要先 `cd F:\pycharm_aiprogram\ai_chief`。

### 6.2 确认 Python 解释器是对的（🔴 本机有多个 Python）

```powershell
.\.venv3\Scripts\python.exe -V
```

**预期输出**：

```
Python 3.13.14
```

> 🔴 必须是 `3.13.x`。如果是 `3.6.5`，说明你用错了解释器（本机 Anaconda base 和 `F:\pycharm_aiprogram\.venv` 都是 3.6.5），换回 `.\.venv3\Scripts\python.exe`。本阶段代码用了 `def _read_ctx(request) -> tuple`、`List[str]` 等较新写法，3.6 会直接语法报错。

### 6.3 切分支

```powershell
git status
```

**预期**：`nothing to commit, working tree clean`，或只列出你知道的改动。若有未提交改动，先处理掉再切分支。

```powershell
git checkout -b feat/v3-stage8
```

**预期输出**：`Switched to a new branch 'feat/v3-stage8'`（若已存在该分支，改用 `git checkout feat/v3-stage8`）。

```powershell
git branch --show-current
```

**预期**：`feat/v3-stage8`

### 6.4 核对基线（🔴 必须 91 passed）

```powershell
.\.venv3\Scripts\python.exe -m pytest -q
```

**预期输出尾行**：

```
91 passed, 7 deselected, ... warnings in ...s
```

> 🔴 **如果不是 91 passed**，先停下来排查，别往下做。基线不对，后面新增 27 例后你无法判断是自己写错了还是老测试本来就是红的。
>
> 🟡 `7 deselected` 是 `pytest.ini` 里 `-m "not llm and not kg and not tenant and not quota"` 过滤掉的需要真实大模型/图谱的用例，正常。

### 6.5 确认容器齐活（🔴 缺一个后面就会报奇怪的错）

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}"
```

**预期**：至少能看到这些处于 `Up`（有健康检查的显示 `(healthy)`）：

```
ai_chief_redis        Up ... (healthy)
ai_chief_pgvector     Up ... (healthy)
ai_chief_pgbouncer    Up ...
ai_chief_milvus       Up ... (healthy)
ai_chief_neo4j        Up ... (healthy)
ai_chief_prometheus   Up ...
ai_chief_grafana      Up ...
ai_chief_alertmanager Up ...
ai_chief_loki         Up ...
ai_chief_promtail     Up ...
```

**缺容器的补救**：

```powershell
docker compose -f docker/docker-compose.v3.yml up -d
```

然后再跑一次 `docker ps` 确认。

### 6.6 🔴 安装 Celery（**没装的话，后面所有步骤都会失败**）

> ⚠️ **顺序警告**：Celery **必须在写代码之前装好**。因为后面写测试、跑 `--collect-only`、起 worker 都要 import celery，没装就是 `ModuleNotFoundError: No module named 'celery'`。

```powershell
.\.venv3\Scripts\python.exe -m pip install "celery[redis]==5.6.3"
```

**预期输出**（节选，末尾一定是 Successfully installed）：

```
Collecting celery[redis]==5.6.3
  Downloading celery-5.6.3-py3-none-any.whl ...
Collecting kombu<5.7,>=5.6.0 ...
Collecting billiard<5.0,>=4.2.0 ...
Collecting amqp<6.0,>=5.4.0 ...
Collecting vine<6.0,>=5.1.0 ...
...
Successfully installed amqp-5.4.1 billiard-4.3.1 celery-5.6.3 click-didyoumean-0.3.1
  click-plugins-1.1.1.2 click-repl-0.4.1 kombu-5.6.2 prompt-toolkit-3.0.53
  python-dateutil-2.9.0.post0 tzlocal-5.4.4 vine-5.1.0 wcwidth-0.2.14
```

> 🟡 `redis` 已经在阶段 1 装过了（本机是 `redis 8.1.0`），实测与 Celery 5.6.3 兼容，不会重复装。

### 6.7 验证 Celery 装好了

```powershell
.\.venv3\Scripts\python.exe -c "import celery, kombu, amqp, billiard; print('celery', celery.__version__); print('kombu', kombu.__version__); print('amqp', amqp.__version__); print('billiard', billiard.__version__)"
```

**预期输出**：

```
celery 5.6.3
kombu 5.6.2
amqp 5.4.1
billiard 4.3.1
```

再验证 worker 子命令可用：

```powershell
.\.venv3\Scripts\python.exe -m celery --version
```

**预期输出**：`5.6.3 (recovery)`

> 🟡 用 `python -m celery` 而不是直接敲 `celery`，可以完全避免"Windows 上 Scripts 目录不在 PATH"的问题，后面手册统一用这种写法。

---

## 七、子模块 1：新增 6 个配置项（app_my/core/config.py 🔵 修改）

### 7.1 定位插入点

打开 `app_my/core/config.py`，找到这段（阶段 7 加的）：

```python
    # =========================================================
    # 可观测栈（v3 阶段 7 新增）
    # =========================================================
    PROMETHEUS_METRICS_PATH: str = "/metrics"      # 后端暴露的指标路径
    PROMETHEUS_MULTIPROC_DIR: str = ""            # 多进程模式预留（gunicorn -w > 1 时用）
    LOKI_URL: str = "http://localhost:3100"        # Loki 入口（前端调试查日志用）
```

紧接着它下面、`# CORS` 那段**之前**，插入下面整块。

### 7.2 插入内容

```python
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
```

### 7.3 验证

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.core.config import settings; print(settings.CELERY_BROKER_URL); print(settings.CELERY_RESULT_BACKEND); print(settings.CELERY_TASK_ALWAYS_EAGER); print(settings.CELERY_TASK_RESULT_EXPIRES); print(settings.WORKER_METRICS_PORT); print(settings.WS_NOTIFY_CHANNEL)"
```

**预期输出**（一行一个）：

```
redis://localhost:6380/1
redis://localhost:6380/2
False
3600
9101
ai_chief:ws:notify
```

> 🟡 本阶段**不需要**往 `.env` 里加任何东西——这 6 个配置都有合理默认值。想改（比如换端口）就在 `.env` 里写同名变量覆盖。

---

## 八、子模块 2：任务事件通知（app_my/core/notify.py 🟢 新建）

### 8.1 新建文件 `app_my/core/notify.py`，完整内容

```python
# app_my/core/notify.py  —— v3 阶段 8：任务事件通知（跨进程）
"""
一条"任务完成"的消息要跨两个进程传递：
    Celery worker 进程（跑任务）  ──发布──▶  Redis 频道  ──订阅──▶  FastAPI 进程（WS 网关）
所以这里只放两件事：
1. build_task_event()：把"哪个任务、什么状态、结果是什么"拼成一个固定结构的 dict；
2. publish_task_event()：把 dict 序列化成 JSON，往 Redis 频道里扔一发。

为什么走 Redis 发布订阅（pub/sub）而不是在 worker 里直接调 WebSocket：
    worker 进程里没有浏览器连接（连接对象在 FastAPI 进程的内存里），
    两个进程唯一的公共通道就是 Redis —— 发布订阅天生就是干这个的。
"""
import json
from typing import Any, Dict, Optional

from app_my.core.config import settings
from app_my.core.logging import logger


def build_task_event(
    task_id: str,
    name: str,
    status: str,
    result: Any = None,
    error: Optional[str] = None,
    tenant_id: int = 0,
    user_id: int = 0,
) -> Dict[str, Any]:
    """
    构造一条任务事件。字段固定，前端拿到的 JSON 永远长这样，好解析。
    status 只会有三种：STARTED（开始）/ SUCCESS（成功）/ FAILURE（失败）。
    tenant_id 是"该推给谁"的路由键——WS 网关按它找到对应租户的连接。
    """
    return {
        "type": "task",                    # 事件大类：以后可能还有 "alert" / "system" 等
        "task_id": task_id,                # 任务编号（前端拿它去掉 GET /tasks/{id} 查详情）
        "name": name,                      # 任务名，如 tasks.reindex_milvus
        "status": status,                  # STARTED / SUCCESS / FAILURE
        "result": result,                  # 成功时的结果（小 dict，别塞大对象）
        "error": error,                    # 失败时的错误摘要（取前 500 字，太长没意义）
        "tenant_id": int(tenant_id or 0),  # 路由键：推给这个租户的所有在线连接
        "user_id": int(user_id or 0),      # 发起人（前端可只给发起人弹提示）
    }


def publish_task_event(payload: Dict[str, Any]) -> int:
    """
    把事件发到 Redis 频道，返回"当时有几个订阅者收到"。
    失败不抛异常：通知只是锦上添花，绝不能因为它挂了就把任务标记成失败。
    """
    from app_my.core.redis_client import get_redis  # 函数内导入，避免模块级循环依赖

    try:
        data = json.dumps(payload, ensure_ascii=False, default=str)  # default=str 兜底：遇到不能序列化的对象就转字符串
        return int(get_redis().publish(settings.WS_NOTIFY_CHANNEL, data))
    except Exception as exc:
        logger.warning("notify: 发布任务事件失败（已忽略，不影响任务本身）: %s", exc)
        return 0
```

### 8.2 验证

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.core.notify import build_task_event, publish_task_event; import json; e = build_task_event('t1','tasks.x','SUCCESS', result={'a':1}, tenant_id=9, user_id=2); print(json.dumps(e, ensure_ascii=False)); print('subscribers =', publish_task_event(e))"
```

**预期输出**：

```
{"type": "task", "task_id": "t1", "name": "tasks.x", "status": "SUCCESS", "result": {"a": 1}, "error": null, "tenant_id": 9, "user_id": 2}
subscribers = 0
```

> 🟡 `subscribers = 0` 是**正确**的：此刻没有 API 进程在订阅这个频道（你没起 uvicorn，或起了但没走 lifespan）。等 API 起来后再发，就会变成 `1`。

> 🟡 上面这条命令用了 `print('subscribers =', ...)` 而不是中文，是为了避免 PowerShell 5.1 在中文环境下把控制台输出搞成乱码。**本手册里凡是"预期输出"含中文的地方，如果实际打出乱码，属于终端编码问题、不是代码问题**；可先执行 `$OutputEncoding = [System.Text.Encoding]::UTF8; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 再跑。

---

## 九、子模块 3：worker 自己的指标（app_my/core/worker_metrics.py 🟢 新建）

### 9.1 新建文件 `app_my/core/worker_metrics.py`，完整内容

```python
# app_my/core/worker_metrics.py  —— v3 阶段 8：Celery worker 自己的指标
"""
为什么单开一个文件、不和阶段 7 的 metrics.py 合并：
    metrics.py 是"FastAPI 进程"的指标（HTTP QPS / 延迟 / token 成本），
    本文件是"Celery worker 进程"的指标（任务次数 / 耗时 / 失败 / 队列深度）。
    两个进程各跑各的，Prometheus 也分两个 job 抓（9002/metrics 与 9101/metrics）。
    分开写的好处：API 进程不会平白无故多出 4 个一直是 0 的 celery_* 指标。

暴露方式：worker 启动后开一个极小的 HTTP 服务（prometheus_client.start_http_server），
    Prometheus 直接抓 http://host.docker.internal:9101/metrics 即可。
"""
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# 任务执行次数：按 任务名 / 队列 / 结果 三个维度拆
CELERY_TASK_TOTAL = Counter(
    "celery_task_total",
    "Celery 任务执行次数（按 task / queue / status 拆）",
    labelnames=("task", "queue", "status"),
)

# 任务耗时直方图：看"重索引一次要多久""图谱重建多久"
CELERY_TASK_DURATION = Histogram(
    "celery_task_duration_seconds",
    "Celery 任务耗时（秒）",
    labelnames=("task",),
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
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


def task_started(task: str, queue: str) -> None:
    """任务开始：记一次 STARTED"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="STARTED").inc()


def task_succeeded(task: str, queue: str, seconds: float) -> None:
    """任务成功：记 SUCCESS + 耗时"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="SUCCESS").inc()
    CELERY_TASK_DURATION.labels(task=task).observe(max(seconds, 0.0))


def task_failed(task: str, queue: str, seconds: float) -> None:
    """任务失败：记 FAILURE + 失败计数 + 耗时（失败的耗时同样值得看）"""
    CELERY_TASK_TOTAL.labels(task=task, queue=queue, status="FAILURE").inc()
    CELERY_TASK_FAILURES.labels(task=task).inc()
    CELERY_TASK_DURATION.labels(task=task).observe(max(seconds, 0.0))


def queue_depth(queue: str, depth: int) -> None:
    """更新某队列的待处理数（worker 侧定时调用）"""
    CELERY_QUEUE_DEPTH.labels(queue=queue).set(max(depth, 0))


def start_metrics_server(port: int) -> None:
    """
    在 worker 进程里起一个后台线程，对外暴露 /metrics。
    注意：start_http_server 只能调用一次；重复调用会抛 OSError（端口被占），
    所以 worker_ready 信号里要 try/except 兜住。
    """
    start_http_server(port)
```

### 9.2 验证

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.core.worker_metrics import task_started, task_succeeded, CELERY_TASK_TOTAL; task_started('tasks.x','low'); task_succeeded('tasks.x','low',0.3); print(sorted((str(s.labels), s._value.get()) for s in CELERY_TASK_TOTAL._metrics.values()))"
```

**预期输出**（顺序可能不同）：

```
[("{'task': 'tasks.x', 'queue': 'low', 'status': 'STARTED'}", 1.0), ("{'task': 'tasks.x', 'queue': 'low', 'status': 'SUCCESS'}", 1.0)]
```

---

## 十、子模块 4：Celery 应用实例（app_my/worker/ 🟢 新建 2 个文件）

### 10.1 先建目录

在项目根目录执行（PowerShell）：

```powershell
New-Item -ItemType Directory -Force -Path app_my\worker\tasks, app_my\ws | Out-Null
Get-ChildItem app_my\worker, app_my\ws | Select-Object FullName
```

**预期**：列出 `app_my\worker\tasks`、`app_my\ws` 两个目录（目录已存在时这条命令是幂等的，不报错）。

### 10.2 新建 `app_my/worker/__init__.py`，完整内容

```python
# app_my/worker/__init__.py
"""v3 阶段 8：Celery 异步任务 worker 包（与 API 共用一个 celery_app 实例）。"""
```

**验证**：

```powershell
Get-ChildItem app_my\worker\__init__.py | Select-Object FullName, Length
```

**预期**：能看到该文件，`Length` 大于 0。

### 10.3 🔴 新建 `app_my/worker/celery_app.py`，完整内容（本阶段最核心的文件）

```python
# app_my/worker/celery_app.py  —— v3 阶段 8：Celery 应用（全局唯一实例）
"""
这个文件是"任务系统的大脑"：一个 Celery 实例，三处地方共用它——
1. 提交任务的 API 进程（app_my/api/tasks.py 用 celery_app.AsyncResult 查结果）；
2. 执行任务的 worker 进程（启动命令 `celery -A app_my.worker.celery_app:celery_app worker ...`）；
3. 单元测试（把 task_always_eager 打开，任务就地同步执行，不用起 worker）。

关键配置逐项说清（每一行都是"不写会怎样"级别的重要）：
- broker_url        ：任务"寄存在哪"。worker 从这个 Redis db 取任务。不配则默认 amqp://guest@localhost，本机没有 RabbitMQ 就直接连不上。
- result_backend    ：任务结果"存在哪"。API 用它查状态。不配则查不到结果，只能拿到 PENDING。
- task_serializer   ：任务参数怎么序列化。默认 json，安全（pickle 有反序列化执行任意代码的风险）。
- task_track_started：任务开始执行时把状态写成 STARTED。不写就永远是 PENDING→SUCCESS，看不到"正在跑"。
- task_acks_late    ：任务"跑完才 ack"。worker 中途崩了任务会被重新投递，不丢任务。
- worker_prefetch_multiplier：worker 一次预取几条。设 1 = 拿一条跑一条，长任务不会被一个 worker 全囤走。
- task_queues       ：声明三条队列 high / default / low。
- task_routes       ：把不同任务名路由到不同队列（这就是"任务分级"）。
- timezone/enable_utc：统一按 UTC 存时间，展示时区给 Asia/Shanghai（避免夏令时/跨时区错乱）。
"""
from celery import Celery
from kombu import Queue

from app_my.core.config import settings

celery_app = Celery("ai_chief")

celery_app.conf.update(
    # ---- 连接 ----
    broker_url=settings.CELERY_BROKER_URL,                    # 复用 Redis 6380 的 db 1，与业务 db 0 隔离
    result_backend=settings.CELERY_RESULT_BACKEND,            # 结果放 Redis 6380 的 db 2
    broker_connection_retry_on_startup=True,                  # 启动时 broker 暂时连不上就重试（而不是直接崩）

    # ---- 序列化 ----
    task_serializer="json",                                   # 任务参数用 JSON
    result_serializer="json",                                 # 任务结果用 JSON
    accept_content=["json"],                                  # 只接受 JSON，拒绝 pickle

    # ---- 时间 ----
    timezone="Asia/Shanghai",
    enable_utc=True,

    # ---- 可靠性 ----
    task_acks_late=True,                                      # 跑完才确认，worker 崩溃任务自动重投
    worker_prefetch_multiplier=1,                             # 一次只预取一条，长任务不囤积
    task_track_started=True,                                  # 允许状态出现 STARTED
    result_expires=settings.CELERY_TASK_RESULT_EXPIRES,       # 结果保留 1 小时后自动清

    # ---- 三条队列 + 任务分级路由 ----
    task_default_queue="default",
    task_queues=(Queue("high"), Queue("default"), Queue("low")),
    task_routes={
        "tasks.reindex_milvus": {"queue": "high"},            # 运维级：向量库重索引，最要紧
        "tasks.rebuild_kg_graph": {"queue": "default"},       # 数据级：图谱重建
        "tasks.generate_nutrition_report": {"queue": "low"},  # 用户级：营养报告，繁但不急
    },

    # ---- 本地/单测：不进 worker，调用即同步执行 ----
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,      # 默认 False；单测里设 True
    task_eager_propagates=True,                               # eager 模式下任务异常直接抛出（测试才看得见）
    task_store_eager_result=True,                             # eager 的结果也写 backend（这样 GET /tasks 查得到）

    # ---- 启动时要 import 哪些模块，任务才会被注册 ----
    # worker 和 API 都靠它把三个任务 + 信号接进来；不写的话 worker 起来后"找不到任务"
    imports=(
        "app_my.worker.tasks.reindex",
        "app_my.worker.tasks.graph",
        "app_my.worker.tasks.nutrition",
        "app_my.worker.signals",
    ),
)
```

### 10.4 🔴 顺序提醒

> **不要现在验证 `celery_app.py`**。它的 `imports` 里引用了 3 个任务模块和 1 个信号模块，此刻还没建，直接 import 会报 `ModuleNotFoundError: No module named 'app_my.worker.tasks.reindex'`。
>
> **正确顺序**：先把 **十一（base.py）、十二（signals.py）、十三（tasks/ 四个文件）** 全部落盘，再回到 **13.5** 节一起验证。这也是本手册把验证步骤放在模块全部写完之后的唯一原因。

---

## 十一、子模块 5：任务基类 NotifyTask（app_my/worker/base.py 🟢 新建）

### 11.1 新建文件 `app_my/worker/base.py`，完整内容

```python
# app_my/worker/base.py  —— v3 阶段 8：所有任务共用的基类（负责通知 + 指标）
"""
为什么要有基类：
    每个任务跑完都干同样三件事——记指标、发通知、算耗时。
    写在基类的钩子里，业务任务就只管"自己的活"，不用每处复制一遍胶水代码。

Celery 给任务预留了四个生命周期钩子，我们在其中三个上做文章：
    before_start(task_id, args, kwargs)   任务真正开跑之前（发 STARTED 事件 + 记开始）
    on_success(retval, task_id, ...)      正常返回（发 SUCCESS 事件 + 记成功 + 耗时）
    on_failure(exc, task_id, ...)         抛异常（发 FAILURE 事件 + 记失败 + 耗时）
    after_return(...)                     无论成败都会跑（本阶段不用）

约定：所有任务的最后两个关键字参数都叫 tenant_id / user_id，
    这样基类能统一从 self.request.kwargs 里取出来，知道"这条通知该推给谁"。
"""
import time

from celery import Task

from app_my.core.logging import logger
from app_my.core.notify import build_task_event, publish_task_event
from app_my.core.worker_metrics import task_failed, task_started, task_succeeded
from app_my.worker.celery_app import celery_app


def _read_ctx(request) -> tuple:
    """
    从任务请求上下文里取出三样东西：
        tenant_id —— 推送给哪个租户（路由键）
        user_id   —— 谁发起的
        queue     —— 这条任务走的是哪条队列（high/default/low），给指标当标签
    kwargs 里没传就兜底成 0，绝不因为缺参数崩掉。

    为什么队列要"回退查 task_routes"：
        真实 worker 执行时，request.delivery_info.routing_key 就是实际队列名；
        但本地 eager 模式（单测）没有 broker，routing_key 是 None。
        这时去 celery_app.conf.task_routes 里查本任务配的队列，保证两种模式下
        打出来的指标标签完全一致（否则单测里看到的是 default，线上是 low，对不上）。
    """
    kwargs = getattr(request, "kwargs", None) or {}
    tenant_id = int(kwargs.get("tenant_id") or 0)
    user_id = int(kwargs.get("user_id") or 0)

    delivery = getattr(request, "delivery_info", None) or {}
    queue = delivery.get("routing_key")
    if not queue:
        name = getattr(request, "task", "") or ""
        route = (celery_app.conf.task_routes or {}).get(name) or {}
        queue = route.get("queue") or celery_app.conf.task_default_queue or "default"
    return tenant_id, user_id, queue


class NotifyTask(Task):
    """带"事件通知 + 指标"的任务基类；业务任务用它作 base 即可。"""

    abstract = True     # 抽象基类，Celery 不会把它本身当成一个任务

    def before_start(self, task_id, args, kwargs):
        """任务开跑前：记开始时间、记 STARTED 指标、发 STARTED 通知"""
        self._s8_t0 = time.perf_counter()
        tenant_id, user_id, queue = _read_ctx(self.request)
        try:
            task_started(self.name, queue)
            publish_task_event(
                build_task_event(task_id, self.name, "STARTED", tenant_id=tenant_id, user_id=user_id)
            )
        except Exception as exc:      # 通知/指标是"附带动作"，出问题也不能影响任务本身
            logger.warning("NotifyTask: STARTED 通知失败（忽略）: %s", exc)

    def on_success(self, retval, task_id, args, kwargs):
        """任务成功：算耗时、记 SUCCESS 指标、发 SUCCESS 通知（把结果一起带走）"""
        tenant_id, user_id, queue = _read_ctx(self.request)
        seconds = time.perf_counter() - getattr(self, "_s8_t0", time.perf_counter())
        try:
            task_succeeded(self.name, queue, seconds)
            publish_task_event(
                build_task_event(task_id, self.name, "SUCCESS", result=retval,
                                 tenant_id=tenant_id, user_id=user_id)
            )
        except Exception as exc:
            logger.warning("NotifyTask: SUCCESS 通知失败（忽略）: %s", exc)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败：算耗时、记 FAILURE 指标、发 FAILURE 通知（把错误摘要带走）"""
        tenant_id, user_id, queue = _read_ctx(self.request)
        seconds = time.perf_counter() - getattr(self, "_s8_t0", time.perf_counter())
        summary = f"{type(exc).__name__}: {exc}"[:500]     # 错误摘要截断，通知没必要带超长堆栈
        try:
            task_failed(self.name, queue, seconds)
            publish_task_event(
                build_task_event(task_id, self.name, "FAILURE", error=summary,
                                 tenant_id=tenant_id, user_id=user_id)
            )
        except Exception as inner:
            logger.warning("NotifyTask: FAILURE 通知失败（忽略）: %s", inner)
```

---

## 十二、子模块 6：worker 生命周期信号（app_my/worker/signals.py 🟢 新建）

### 12.1 新建文件 `app_my/worker/signals.py`，完整内容

```python
# app_my/worker/signals.py  —— v3 阶段 8：worker 生命周期信号（只负责"起指标服务 + 刷队列长度"）
"""
Celery 的"信号（signal）"= 框架在特定时刻广播的事件，我们挂个回调进去干活。
这里用两个：
    worker_ready  —— worker 启动完成的那一刻：开指标 HTTP 服务 + 读一次队列长度
    task_postrun  —— 每个任务跑完之后：刷新队列长度（这样 Grafana 上能看出"积压在涨还是消"）

为什么要用模块级 _IS_WORKER 开关：
    task_postrun 在"本地 eager 模式"下也会触发（单测里就是），
    但单测不该去连 Redis 数队列长度。用 worker_ready 置位的开关一挡，单测里就是空操作。
"""
from celery.signals import task_postrun, worker_ready, worker_shutdown

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.core.worker_metrics import queue_depth, start_metrics_server

_IS_WORKER = False          # 只有真正的 worker 进程在 worker_ready 后才会置 True
_METRICS_STARTED = False    # start_http_server 只能调一次，防止重复启动报端口占用
QUEUES = ("high", "default", "low")


def refresh_queue_depth() -> None:
    """读三条队列在 Redis 里的当前长度（LLEN），写进 celery_queue_depth 指标"""
    try:
        from app_my.core.redis_client import get_redis
        r = get_redis()
        for q in QUEUES:
            queue_depth(q, int(r.llen(q) or 0))
    except Exception as exc:      # Redis 抽风不能让指标拖垮 worker
        logger.warning("worker: 读取队列长度失败（忽略）: %s", exc)


@worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):
    """worker 就绪：暴露 /metrics、记录一次队列长度"""
    global _IS_WORKER, _METRICS_STARTED
    _IS_WORKER = True
    if not _METRICS_STARTED:
        try:
            start_metrics_server(settings.WORKER_METRICS_PORT)
            _METRICS_STARTED = True
            logger.info("worker: 指标已暴露 http://0.0.0.0:%d/metrics", settings.WORKER_METRICS_PORT)
        except Exception as exc:
            logger.warning("worker: 指标服务启动失败（可能端口被占）: %s", exc)
    refresh_queue_depth()
    logger.info("worker: 就绪，队列 %s", " / ".join(QUEUES))


@task_postrun.connect
def _on_task_postrun(sender=None, **kwargs):
    """每个任务结束后刷一次队列长度（指标服务没起时直接跳过）"""
    if _IS_WORKER and _METRICS_STARTED:
        refresh_queue_depth()


@worker_shutdown.connect
def _on_worker_shutdown(sender=None, **kwargs):
    logger.info("worker: 正在关闭")
```

> 🟡 `QUEUES` 这个元组在 `signals.py` 与 `celery_app.py` 的 `task_queues` 是"两处各写一遍"。这是刻意的：`signals.py` 只想知道"要去 Redis 数哪几个 key"，不需要 import `celery_app`（否则会形成 `celery_app` → `imports` → `signals` → `celery_app` 的循环依赖）。改队列名时记得两边一起改。

---

## 十三、子模块 7：三个长任务（app_my/worker/tasks/ 🟢 新建 4 个文件）

### 13.1 新建 `app_my/worker/tasks/__init__.py`，完整内容

```python
# app_my/worker/tasks/__init__.py
"""
v3 阶段 8：三个长任务。放这里只是"包标记"，
真正的注册发生在 app_my/worker/celery_app.py 的 imports 列表里。
"""
```

### 13.2 新建 `app_my/worker/tasks/reindex.py`，完整内容（长任务①，high 队列）

```python
# app_my/worker/tasks/reindex.py  —— v3 阶段 8：Milvus 菜谱向量重索引（长任务 ①）
"""
把阶段 6 的导入脚本（scripts/import_recipes_milvus.py）搬进 Celery 任务。
同步脚本要人守着终端跑，还卡在 API 进程里；任务化之后：
    接口立刻返回 task_id → worker 慢慢跑（要调几十次 embedding 接口）→ 跑完推送结果。

为什么函数体里才 import（而不是文件顶部 import）：
    Celery 启动时要 import 本模块来"发现任务"，如果顶部就 import pymilvus / langchain，
    worker 启动会慢好几秒，而且 API 进程（也会 import 到本模块）平白多加载一堆东西。
    把重依赖推迟到"任务真正执行"的那一刻，是 Celery 任务的标准写法。
"""
from app_my.worker.base import NotifyTask
from app_my.worker.celery_app import celery_app

BATCH_SIZE = 10     # DashScope embedding 接口单次最多 10 条文本，超了会被拒


@celery_app.task(
    base=NotifyTask,          # 继承"通知 + 指标"基类
    name="tasks.reindex_milvus",
    bind=True,                # 让第一个参数是 self（本任务其实用不到，但基类钩子需要绑定实例）
    max_retries=1,            # 临时故障（比如 embedding 接口抖一下）最多自动重试 1 次
    default_retry_delay=10,   # 重试间隔 10 秒
)
def reindex_milvus(self, rebuild: bool = True, tenant_id: int = 0, user_id: int = 0) -> dict:
    """
    Milvus 向量库重索引。

    参数：
        rebuild   True = 先删旧集合再从零写（改了菜谱文本/换 embedding 模型时用）；
                  False = 不清场，直接按 recipe_id upsert 覆盖（增量刷新，安全）
        tenant_id 发起任务的租户（基类用它决定通知推给谁）
        user_id   发起人

    返回：{"rows": 实际写入条数, "expected": 菜谱总数, "row_count": 集合当前行数, "seconds": 耗时}
    """
    import time

    from app_my.core.cache import invalidate_prefix
    from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
    from app_my.knowledge.embedding import embed_texts
    from app_my.knowledge.milvus_store import (
        clear_collection,
        collection_row_count,
        ensure_collection,
        upsert_recipes,
    )

    t0 = time.perf_counter()
    recipes = load_recipes()                       # 读 app_my/knowledge/data/recipes.json

    if rebuild:
        if not clear_collection():                 # 清场失败 = Milvus 没起或连不上
            raise RuntimeError("Milvus 不可用：清场失败，请先确认 ai_chief_milvus 容器已启动")
    if not ensure_collection():                    # 幂等：集合在就直接用，不在就按 schema 建
        raise RuntimeError("Milvus 建集合失败（ensure_collection 返回 False）")

    total = 0
    for i in range(0, len(recipes), BATCH_SIZE):
        batch = recipes[i:i + BATCH_SIZE]
        texts = [recipe_to_text(r) for r in batch]
        vectors = embed_texts(texts)               # 真实调用 DashScope，一次最多 10 条
        rows = [
            {
                "recipe_id": r["recipe_id"],       # 主键：重复写按 id 覆盖（幂等的第二重保险）
                "text": t,                          # 与 PGVector 存的同一份菜谱文本
                "vector": v,                        # 1024 维向量
                "metadata": recipe_to_metadata(r),  # 检索时直接带出的元数据
            }
            for r, t, v in zip(batch, texts, vectors)
        ]
        total += upsert_recipes(rows)

    # 数据变了：v1（rag）与 v2（rag2）两条检索路径的缓存都失效，否则用户查到的还是旧菜
    invalidate_prefix("rag")
    invalidate_prefix("rag2")

    return {
        "rows": total,
        "expected": len(recipes),
        "row_count": collection_row_count(),
        "seconds": round(time.perf_counter() - t0, 2),
    }
```

> 🟡 这个任务**会真实调用 DashScope embedding 接口并写 Milvus**。跑一次要几十秒、消耗额度。想来一次"真跑"，等 23.4 节 worker 起来后，用 `frontend/stage8-tasks.html` 的第①个按钮提交即可。

### 13.3 新建 `app_my/worker/tasks/graph.py`，完整内容（长任务②，default 队列）

```python
# app_my/worker/tasks/graph.py  —— v3 阶段 8：Neo4j 知识图谱重建（长任务 ②）
"""
把阶段 3 的建图脚本（scripts/init_kg.py）包成 Celery 任务。

关键取舍：**不复制那 150 行 Cypher，直接复用 scripts/init_kg.py 里已验证的 build()**。
    复制一份"任务专用建图逻辑"看着独立，实则埋雷——以后改了一处忘了改另一处，
    图谱就会出现"脚本建的和任务建的不一样"。DRY（Don't Repeat Yourself）在这里比"看起来清爽"重要。

注意：build() 里是 MERGE 语义——rebuild=False 时只是把现有数据再合并一遍（幂等、不删数据）；
     rebuild=True 会先 `MATCH (n) DETACH DELETE n` 清空全图再建（改了 kg_facts.json 时才需要）。
"""
from typing import Optional

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
        rebuild   False（默认）= 增量合并（MERGE，安全、幂等）；
                  True = 先清空全图再重建（谨慎：会短暂清空图谱）
        tenant_id / user_id：通知路由用

    返回：{"nodes": 节点总数, "relationships": 关系总数, "seconds": 耗时}
    """
    import time

    from app_my.core.kg import kg_stats, reset_ingredient_cache, reset_kg_connection

    t0 = time.perf_counter()

    # 复用建图脚本（scripts 是可导入的包，见 scripts/__init__.py）
    from scripts.init_kg import build
    build(rebuild=rebuild)

    # 建图脚本自己开了一个驱动并关掉了；本模块的 kg 连接/食材缓存可能是旧的，重建后清掉
    reset_kg_connection()
    reset_ingredient_cache()

    stats = kg_stats()
    node_total = sum(int(n.get("count", 0) or 0) for n in (stats.get("nodes") or []))
    rel_total = sum(int(r.get("count", 0) or 0) for r in (stats.get("relationships") or []))

    return {
        "nodes": node_total,
        "relationships": rel_total,
        "available": bool(stats.get("available")),
        "seconds": round(time.perf_counter() - t0, 2),
    }
```

> 🟡 这个文件顶部的 `from typing import Optional` 目前没被用到（历史遗留），留着无害；想让 lint 完全干净，直接删掉这一行即可。本手册保留原样，以便与你机器上实测通过的代码逐字一致。

### 13.4 新建 `app_my/worker/tasks/nutrition.py`，完整内容（长任务③，low 队列）

```python
# app_my/worker/tasks/nutrition.py  —— v3 阶段 8：营养报告生成（长任务 ③）
"""
用户最直观的长任务：提交一串食材，后台算出一份营养报告，算完推到浏览器右下角。

为什么营养报告"适合异步"：
    算营养本身是查表 + 四则运算（很快），但真实报告还要做"同类菜谱检索 + 大模型润色建议"，
    这两步是秒级到十秒级的。用户在页面上等十秒会以为卡死了——所以交后台跑，算完再通知。

本任务用工具 calculate_nutrition（纯查表，稳定可复现、不烧 token），
    所以它也是"不依赖大模型就能完整验证一条链路"的最佳演示任务。
"""
from typing import List, Optional

from app_my.worker.base import NotifyTask
from app_my.worker.celery_app import celery_app


@celery_app.task(
    base=NotifyTask,
    name="tasks.generate_nutrition_report",
    bind=True,
    max_retries=0,
)
def generate_nutrition_report(
    self,
    ingredients: Optional[List[str]] = None,
    tenant_id: int = 0,
    user_id: int = 0,
) -> dict:
    """
    生成营养报告。

    参数：
        ingredients  食材列表，如 ["鸡胸肉 200克", "西兰花 1颗"]（名字后带用量，工具才换算得出克数）
        tenant_id / user_id：通知路由用

    返回：{"ingredients", "total_estimated", "coverage", "unmatched", "summary", "seconds"}
    """
    import time

    from app_my.tools.nutrition_tool import calculate_nutrition

    t0 = time.perf_counter()

    items = [str(x).strip() for x in (ingredients or []) if str(x).strip()]
    if not items:
        raise ValueError("ingredients 不能为空")   # 参数不合法 → 直接失败，让前端看到明确错误

    result = calculate_nutrition.invoke({"ingredients": items})   # LangChain 工具同步调用
    est = result.get("total_estimated", {}) or {}

    summary = (
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

### 13.5 🔴 四个任务模块 + celery_app 一起验证（不需要 worker、不需要容器）

**验证 A：任务注册、队列、路由**

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.worker.celery_app import celery_app; print('tasks:', sorted(n for n in celery_app.tasks if n.startswith('tasks.'))); print('queues:', [q.name for q in celery_app.conf.task_queues]); print('routes:', celery_app.conf.task_routes)"
```

**预期输出**：

```
tasks: ['tasks.generate_nutrition_report', 'tasks.rebuild_kg_graph', 'tasks.reindex_milvus']
queues: ['high', 'default', 'low']
routes: {'tasks.reindex_milvus': {'queue': 'high'}, 'tasks.rebuild_kg_graph': {'queue': 'default'}, 'tasks.generate_nutrition_report': {'queue': 'low'}}
```

**验证 B：代理配置正确（broker/backend 分 db）**

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.worker.celery_app import celery_app; print('broker :', celery_app.conf.broker_url); print('backend:', celery_app.conf.result_backend); print('serializer:', celery_app.conf.task_serializer, celery_app.conf.result_serializer, celery_app.conf.accept_content); print('acks_late:', celery_app.conf.task_acks_late, 'prefetch:', celery_app.conf.worker_prefetch_multiplier, 'track_started:', celery_app.conf.task_track_started)"
```

**预期输出**：

```
broker : redis://localhost:6380/1
backend: redis://localhost:6380/2
serializer: json json ['json']
acks_late: True prefetch: 1 track_started: True
```

**验证 C：营养任务本地同步真跑（不碰任何容器）**

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.worker.celery_app import celery_app; celery_app.conf.task_always_eager = True; from app_my.worker.tasks.nutrition import generate_nutrition_report; r = generate_nutrition_report.delay(ingredients=['鸡蛋 100克','西兰花 200克']); print('state =', r.state); import json; print(json.dumps(r.get(), ensure_ascii=False))"
```

**预期输出**（数字是真实计算值，与本次实测一致）：

```
state = SUCCESS
{"ingredients": ["鸡蛋 100克", "西兰花 200克"], "total_estimated": {"calories": 215.0, "protein": 21.5, "fat": 10.0, "carbs": 11.4}, "coverage": 1.0, "unmatched": [], "summary": "估算本餐总热量 215.0 千卡；蛋白 21.5g / 脂肪 10.0g / 碳水 11.4g；匹配率 100%", "seconds": 0.01}
```

> 🟢 上面这段输出是**本次实测的真实结果**（在你的容器 + 项目源码副本上跑出来的），不是编造的示例。`215.0` 千卡 ≈ 鸡蛋 100 克（约 144 千卡）+ 西兰花 200 克（约 71 千卡）。
>
> 🔴 验证 C 时**不需要** Redis / Milvus / Neo4j 任何一个容器——eager 模式完全不碰 broker。

> 🟡 如果你在验证 C 里看到 `state = SUCCESS` 但 `seconds` 略有不同（比如 0.02），完全正常，那是机器速度差异。

---

## 十四、子模块 8：接口数据模型（app_my/schemas/tasks.py 🟢 新建）

### 14.1 新建文件 `app_my/schemas/tasks.py`，完整内容

```python
# app_my/schemas/tasks.py  —— v3 阶段 8：异步任务接口的进出数据模型
"""只描述"接口进出的数据长什么样"，不碰任务与数据库（和 schemas/auth.py 一个风格）。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReindexIn(BaseModel):
    """Milvus 重索引请求"""
    rebuild: bool = Field(True, description="True=先清场再全量重建；False=不清场，按 recipe_id 覆盖")


class KgRebuildIn(BaseModel):
    """Neo4j 图谱重建请求"""
    rebuild: bool = Field(False, description="True=清空全图再重建（会短暂清空）；False=增量合并")


class NutritionReportIn(BaseModel):
    """营养报告请求：至少要有一个食材"""
    ingredients: List[str] = Field(..., min_length=1, description="食材列表，如 ['鸡胸肉 200克']")


class TaskSubmitOut(BaseModel):
    """提交任务的响应"""
    task_id: str            # 任务编号：后续查状态、WS 事件里都用它
    name: str               # 任务名（tasks.xxx）
    queue: str              # 落到哪条队列（high/default/low）
    status: str = "PENDING"  # 刚提交必然是 PENDING


class TaskStatusOut(BaseModel):
    """查询任务状态的响应"""
    task_id: str
    status: str                          # PENDING / STARTED / SUCCESS / FAILURE
    result: Optional[Dict[str, Any]] = None   # 成功时的结果
    error: Optional[str] = None               # 失败时的错误摘要
```

> 🟡 `TaskSubmitOut` / `TaskStatusOut` 目前不在路由签名里显式声明（端点直接 return dict），保留它们是为了给 OpenAPI 文档和后续前端联调做"契约参考"。想让 `/docs` 里显示响应模型，把端点改成 `response_model=TaskSubmitOut` 即可。

### 14.2 验证

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.schemas.tasks import NutritionReportIn, ReindexIn; print('reindex default rebuild =', ReindexIn().rebuild); print('nutrition =', NutritionReportIn(ingredients=['鸡蛋 100克']).ingredients)"
```

**预期输出**：

```
reindex default rebuild = True
nutrition = ['鸡蛋 100克']
```

再单独验证"空食材列表被拒"：

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.schemas.tasks import NutritionReportIn; from pydantic import ValidationError
try:
    NutritionReportIn(ingredients=[])
    print('NOT rejected -> BUG')
except ValidationError as e:
    print('empty list rejected OK, errors =', len(e.errors()))"
```

**预期输出**：`empty list rejected OK, errors = 1`

> 🟡 上面这段是多行 `-c`，PowerShell 5.1 直接粘贴多行可能只执行第一行。**更稳的做法**：把这两行存成 `tmp_check.py` 再跑 `.\.venv3\Scripts\python.exe tmp_check.py`，跑完删掉。若你懒得弄，只看前一条命令的输出也算通过。

---

## 十五、子模块 9：任务提交与查询接口（app_my/api/tasks.py 🟢 新建）

### 15.1 新建文件 `app_my/api/tasks.py`，完整内容

```python
# app_my/api/tasks.py  —— v3 阶段 8：长任务提交 + 状态查询接口
"""
四个接口（全部受 JWT 鉴权保护，跟着 AuthMiddleware 走，无需额外写鉴权）：
    POST /tasks/reindex-milvus      提交 Milvus 重索引      → 队列 high
    POST /tasks/rebuild-kg          提交图谱重建            → 队列 default
    POST /tasks/nutrition-report    提交营养报告            → 队列 low
    GET  /tasks/{task_id}           查任务状态与结果

设计要点：
- 提交接口做的最重的事只是"往 Redis 丢一条消息"，所以是毫秒级返回 —— 这就是"任务异步化"的收益。
- `.delay(...)` 是 Celery 的固定写法：把函数名 + 参数序列化后投进队列，立刻返回一个 AsyncResult（含 id）。
  它不会等任务跑完（除非 CELERY_TASK_ALWAYS_EAGER=True，那是单测模式）。
- 状态查询直接问 Celery 的 result backend（Redis db2），拿到 PENDING/STARTED/SUCCESS/FAILURE。
"""
from celery.result import AsyncResult
from fastapi import APIRouter, Request

from app_my.schemas.tasks import KgRebuildIn, NutritionReportIn, ReindexIn
from app_my.worker.celery_app import celery_app
from app_my.worker.tasks.graph import rebuild_kg_graph
from app_my.worker.tasks.nutrition import generate_nutrition_report
from app_my.worker.tasks.reindex import reindex_milvus

router = APIRouter()


def _caller(request: Request):
    """从请求上下文取"谁提交的"：租户（推送给谁）+ 用户（谁发起）"""
    tenant_id = int(getattr(request.state, "tenant_id", None) or 0)
    user_id = int(getattr(request.state, "user_id", None) or 0)
    return tenant_id, user_id


@router.post("/reindex-milvus")
async def submit_reindex(request: Request, body: ReindexIn):
    """提交 Milvus 菜谱向量重索引（长任务，接口立即返回 task_id）"""
    tenant_id, user_id = _caller(request)
    result = reindex_milvus.delay(rebuild=body.rebuild, tenant_id=tenant_id, user_id=user_id)
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


@router.get("/{task_id}")
async def get_task_status(task_id: str):
    """
    查询任务状态。

    返回：
        status = PENDING   —— 排队中 / 尚未被 worker 取走
        status = STARTED   —— worker 正在跑
        status = SUCCESS   —— 跑完了，result 字段是任务返回值
        status = FAILURE   —— 跑挂了，error 字段是错误摘要
    """
    res = AsyncResult(task_id, app=celery_app)
    payload = {"task_id": task_id, "status": res.status, "result": None, "error": None}
    if res.successful():
        payload["result"] = res.result
    elif res.failed():
        payload["error"] = str(res.result)
    return payload
```

> 🔴 注意 `_caller()` 读的是 `request.state.tenant_id` / `request.state.user_id`——这两个值由阶段 4 的 `AuthMiddleware` / `TenantContextMiddleware` 挂上去。所以**`main.py` 里中间件顺序不能动**，否则这里取到的是 `0`，通知会推给"租户 0"，浏览器永远收不到。
>
> 🟡 为什么提交接口不用 `response_model=TaskSubmitOut`？因为本项目其它接口（阶段 4/5/7）都是直接 `return dict`，保持一致；上面 `schemas/tasks.py` 里的两个 Out 模型是给文档/前端做契约参考的。

### 15.2 验证（需先把 main.py 改完，见第十七节）

改完 `main.py` 后，用 **17.6** 节的两条命令一次验证 `/tasks/*` 与 `/ws/notifications` 都在路由表里。

---

## 十六、子模块 10：WebSocket 三件套（app_my/ws/ 🟢 新建 4 个文件）

### 16.1 新建 `app_my/ws/__init__.py`，完整内容

```python
# app_my/ws/__init__.py
"""v3 阶段 8：WebSocket 实时推送包（连接管理 + 网关 + Redis 订阅中继）。"""
```

### 16.2 新建 `app_my/ws/manager.py`，完整内容

```python
# app_my/ws/manager.py  —— v3 阶段 8：WebSocket 连接管理器
"""
作用：记住"当前有哪些浏览器连着我、分别属于哪个租户"，任务事件来了就按租户投递。

为什么按 tenant_id 分组（而不是一股脑存一个大列表）：
    项目是多租户的——租户 A 的任务结果绝不能推给租户 B 的页面。
    分组之后，投递就是"取这个租户的连接集合，逐个发"，天然隔离。

为什么用模块级单例 manager：
    连接对象活在 FastAPI 进程的内存里，整个进程只能有一份登记表。
    多开 uvicorn worker 时每个进程各有一份，但每个进程都订阅了同一条 Redis 频道，
    各自的连接由各自的进程推 —— 这也是它能水平扩展的原因。
"""
from collections import defaultdict
from typing import Dict, Optional, Set, Tuple

from app_my.core.logging import logger


class ConnectionManager:
    """WebSocket 连接登记表（进程内单例）"""

    def __init__(self) -> None:
        self._by_tenant: Dict[int, Set] = defaultdict(set)   # tenant_id -> 该租户的在线连接集合
        self._meta: Dict[object, Tuple[int, int]] = {}       # 连接对象 -> (tenant_id, user_id)

    async def connect(self, websocket, tenant_id: int, user_id: int) -> None:
        """接受握手，登记到租户分组"""
        await websocket.accept()
        self._by_tenant[int(tenant_id or 0)].add(websocket)
        self._meta[websocket] = (int(tenant_id or 0), int(user_id or 0))
        logger.info("ws: 连接建立 tenant=%s user=%s 当前连接数=%d",
                    tenant_id, user_id, len(self._meta))

    def disconnect(self, websocket) -> None:
        """断开：从两处登记表里摘掉（幂等，重复调用安全）"""
        info = self._meta.pop(websocket, None)
        if not info:
            return
        tenant_id, user_id = info
        group = self._by_tenant.get(tenant_id)
        if group is not None:
            group.discard(websocket)
            if not group:                       # 该租户没人了，把空集合也删掉
                self._by_tenant.pop(tenant_id, None)
        logger.info("ws: 连接断开 tenant=%s user=%s 当前连接数=%d",
                    tenant_id, user_id, len(self._meta))

    async def dispatch(self, event: dict) -> int:
        """
        把一条事件推给该租户的所有在线连接；返回成功送达的连接数。
        发送失败的连接视为已死，顺手清掉（避免越积越多、每次都要重试）。
        """
        tenant_id = int(event.get("tenant_id") or 0)
        targets = list(self._by_tenant.get(tenant_id, ()))
        if not targets:
            return 0                            # 该租户没人在线：任务照跑，只是没人收推送

        sent, dead = 0, []
        for ws in targets:
            try:
                await ws.send_json(event)       # send_json 会自动把 dict 序列化成 JSON 文本帧
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        return sent

    def stats(self) -> dict:
        """当前连接概览（排障/演示用）"""
        return {
            "connections": len(self._meta),
            "tenants": {tid: len(g) for tid, g in self._by_tenant.items()},
        }


# 全局单例：网关、中继、接口都 import 这一个
manager = ConnectionManager()
```

### 16.3 🔴 新建 `app_my/ws/gateway.py`，完整内容（两个新手大坑都在这里）

```python
# app_my/ws/gateway.py  —— v3 阶段 8：WebSocket 网关（/ws/notifications）
"""
一个 WebSocket 端点，两件事：
1. 握手时鉴权（游客连不上）；
2. 连上后只负责"活着"——收心跳、回 pong；真正的推送由 ws/relay.py 从 Redis 收到事件后调 manager 发。

🔴 新手最容易翻车的点：浏览器原生 WebSocket 不能自定义请求头！
    HTTP 接口用 `Authorization: Bearer <token>` 传令牌，
    但 `new WebSocket(url)` 没法加 header —— 所以 token 只能塞进 URL 查询参数 `?token=`。
    这不是"偷懒"，是浏览器 API 的限制（WS 握手不能带自定义头）。
    代价是 token 会出现在 URL 里（可能进日志），因此生产环境一般配 wss:// 且用短命 token。

🔴 第二个坑：HTTP 中间件管不到 WebSocket。
    main.py 里那些 add_middleware（Auth / 限流 / 指标）只处理 http 类型的请求；
    WebSocket 的 scope 类型是 "websocket"，会绕过它们直达本端点。
    所以本端点必须自己做 JWT 校验 —— 别指望 AuthMiddleware 帮你拦。
"""
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app_my.core.logging import logger
from app_my.core.security import TOKEN_TYPE_ACCESS, decode_token, is_revoked
from app_my.ws.manager import manager

router = APIRouter()

# WebSocket 协议里 1008 表示"策略违规"（这里是"你没通过鉴权"）
WS_CLOSE_POLICY_VIOLATION = 1008


def _authenticate(token: str):
    """
    校验 ?token= 里的 JWT，通过返回 (tenant_id, user_id)，否则返回 None。
    复用 HTTP 那套 security 模块，保证"HTTP 认的令牌 WS 也认"，不用维护两套鉴权。
    """
    if not token:
        return None
    payload = decode_token(token)                                  # 验签 + 验过期，失败返回 None
    if payload is None:
        return None
    if payload.get("type") != TOKEN_TYPE_ACCESS:                   # 只收 access token，不收 refresh
        return None
    if is_revoked(payload):                                        # 登出/换新过的令牌立刻失效
        return None
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    tenant_id = payload.get("tenant_id") or 0                      # 老令牌可能没有 tenant，兜底 0
    return int(tenant_id), user_id


@router.websocket("/notifications")
async def ws_notifications(websocket: WebSocket, token: str = Query(default="")):
    """
    建立实时通知长连接。

    用法（浏览器）：
        const ws = new WebSocket(`ws://127.0.0.1:9002/ws/notifications?token=${accessToken}`);

    通信约定：
        客户端 → 服务端：发文本 "ping"（保活）
        服务端 → 客户端：回 '{"type":"pong"}'；任务事件则是 {"type":"task", ...}
    """
    auth = _authenticate(token)
    if auth is None:
        # 未通过鉴权：直接以 1008 关闭（不 accept，省一次握手往返）
        logger.warning("ws: 鉴权失败，拒绝连接")
        await websocket.close(code=WS_CLOSE_POLICY_VIOLATION)
        return

    tenant_id, user_id = auth
    await manager.connect(websocket, tenant_id, user_id)
    try:
        while True:
            msg = await websocket.receive_text()     # 没消息就挂在这里等（异步等待，不占 CPU）
            if msg == "ping":                        # 简易心跳：前端定时发，防止中间设备掐掉空闲连接
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass                                         # 浏览器关页面/断网 → 走这里，正常收尾
    finally:
        manager.disconnect(websocket)
```

### 16.4 新建 `app_my/ws/relay.py`，完整内容

```python
# app_my/ws/relay.py  —— v3 阶段 8：Redis 订阅中继（把 worker 的通知送进浏览器）
"""
补上最后一段链路：
    worker 进程  --publish-->  Redis 频道  --本文件中继-->  本进程的 WebSocket 连接

为什么需要"中继"这一环（直接让 worker 发 WS 不行吗）：
    worker 进程里根本没有浏览器连接对象（连接活在 FastAPI 进程内存里），
    worker 唯一能碰到的公共设施就是 Redis。所以：
    worker 只负责"发到 Redis"，FastAPI 进程负责"从 Redis 收 + 转发给浏览器"。

实现细节：用 redis.asyncio（异步客户端）在事件循环里 await 收消息，
    绝不能用同步客户端——同步的 listen() 会把整个 FastAPI 的事件循环卡死，
    表现为"一订阅，所有接口全不响应"。
"""
import asyncio
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
    import redis.asyncio as aioredis      # 函数内导入：redis 没装或版本旧时，import 本模块也不报错

    while True:
        client = None
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(settings.WS_NOTIFY_CHANNEL)
            logger.info("ws relay: 已订阅 Redis 频道 %s", settings.WS_NOTIFY_CHANNEL)

            async for message in pubsub.listen():          # 阻塞式异步迭代：有消息才唤醒
                if message.get("type") != "message":        # 订阅/退订的确认帧，跳过
                    continue
                try:
                    event = json.loads(message["data"])
                except (TypeError, ValueError):
                    logger.warning("ws relay: 收到无法解析的消息，已跳过")
                    continue
                sent = await manager.dispatch(event)
                if sent:
                    logger.info("ws relay: 事件已投递 %d 个连接（task_id=%s）",
                                sent, event.get("task_id"))
        except asyncio.CancelledError:
            # 应用关闭时会被 cancel，这是正常流程：把连接关掉再往外抛，让 lifespan 干净收尾
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass
            raise
        except Exception as exc:
            logger.warning("ws relay: 订阅中断，%d 秒后重连: %s", RETRY_SECONDS, exc)
            await asyncio.sleep(RETRY_SECONDS)
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass
```

> 🟡 注意 `relay.py` 订阅的是 `settings.REDIS_URL`（**db0**，业务库），而 `notify.py` 发布时用的是 `get_redis()`——它也是 `REDIS_URL`（db0）。**发布与订阅必须在同一个 db**，两边都用 `REDIS_URL` 就自然对上了。不要手滑把它改成 `CELERY_BROKER_URL`。

### 16.5 验证（WS 三件套可独立 import，不依赖 main.py）

```powershell
.\.venv3\Scripts\python.exe -c "from app_my.ws.manager import manager; from app_my.ws import gateway, relay; print('manager:', manager.stats()); print('gateway routes:', [r.path for r in gateway.router.routes]); print('relay callable:', callable(relay.run_relay))"
```

**预期输出**：

```
manager: {'connections': 0, 'tenants': {}}
gateway routes: ['/notifications']
relay callable: True
```

---

## 十七、子模块 11：main.py 接入（🔵 修改）

> 🔴 **本子模块共 4 处改动，改完再验证。** 改动位置全部集中在"顶部 import"、"lifespan"、"路由注册"三块，不碰中间件顺序。

### 17.1 改动 1：顶部加 `import asyncio`

把 `main.py` 开头：

```python
# main.py - AI 私厨 v2.0 修订版入口
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
```

改成：

```python
# main.py - AI 私厨 v2.0 修订版入口
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
```

### 17.2 改动 2：加 3 个 import

找到这一行（阶段 5 加的）：

```python
from app_my.api import oss, chat, auth, user, billing, kg, tenant as tenant_api, admin as admin_api, cache   # cache 为 v3阶段5 新增
```

在它**下面**插入：

```python
from app_my.api import tasks as tasks_api   # v3阶段8 新增：异步任务提交/查询

from app_my.ws import gateway as ws_gateway          # v3阶段8 新增：WebSocket 实时推送网关
from app_my.ws.relay import run_relay               # v3阶段8 新增：Redis 订阅中继
```

### 17.3 改动 3：lifespan 里启动 / 取消中继协程

找到 lifespan 函数里的这一段：

```python
    logger.info("Debug: %s", settings.DEBUG)

    yield

    logger.info("服务关闭，清理资源...")
```

改成：

```python
    logger.info("Debug: %s", settings.DEBUG)

    # v3阶段8：启动常驻协程，订阅 Redis 频道，把任务完成事件转发给浏览器
    relay_task = asyncio.create_task(run_relay(), name="ws-notify-relay")
    logger.info("ws relay: 后台订阅任务已启动")

    yield

    # v3阶段8：先取消中继协程再收尾，避免事件循环关闭时报 "Task was destroyed but it is pending"
    relay_task.cancel()
    try:
        await relay_task
    except asyncio.CancelledError:
        pass
    logger.info("服务关闭，清理资源...")
```

> 🔴 **关键点**：`create_task` 必须在 `yield` **之前**（启动阶段），`cancel` 必须在 `yield` **之后**（关闭阶段）。写反了表现为"服务一起来中继就被取消"，日志里会立刻出现 `ws relay: 订阅中断`。

### 17.4 改动 4：注册 2 个路由

找到路由注册段这一行：

```python
app.include_router(admin_api.router, prefix="/admin", tags=["管理端(v3阶段4)"])         # v3阶段4 新增
```

在它**下面**插入：

```python
app.include_router(tasks_api.router, prefix="/tasks", tags=["异步任务(v3阶段8)"])       # v3阶段8 新增
app.include_router(ws_gateway.router, prefix="/ws", tags=["WebSocket(v3阶段8)"])        # v3阶段8 新增
```

### 17.5 改动 5：**不要动中间件顺序**

`main.py` 里这段**保持原样**：

```python
app.add_middleware(QuotaMiddleware)                  # 5. 租户配额（最里层）
app.add_middleware(RateLimitMiddleware)             # 4. 全局/IP 级限流（最里层）
app.add_middleware(UserRateLimitMiddleware)         # 3. 用户级限流
app.add_middleware(TenantContextMiddleware)         # 2.5 租户上下文（v3阶段4 新增）
app.add_middleware(AuthMiddleware)                  # 2. JWT 鉴权
app.add_middleware(MetricsMiddleware)                #1.5  阶段 7：HTTP 埋点 + /metrics 端点（必须在 Auth 之外）
app.add_middleware(TraceIdMiddleware)               # 1. TraceID
app.add_middleware(CORSMiddleware, ...)             # 0. CORS（最后加 -> 最外层）
```

> 🔴 阶段 8 的 `/tasks/*` 靠 `AuthMiddleware` 鉴权、靠 `TenantContextMiddleware` 提供 `tenant_id`。**动了顺序这两件事就都坏了**。WS 端点不受中间件影响（它自己鉴权），也不用为它加中间件。

### 17.6 验证（路由表 + 静态导入）

**验证 A：能否正常 import（语法/引用错误会在这里暴露）**

```powershell
.\.venv3\Scripts\python.exe -c "import main; print('import main OK')"
```

**预期输出**：`import main OK`（可能有 `pkg_resources is deprecated` 之类的告警，不影响）。

**验证 B：路由表里有 5 个阶段 8 端点**

```powershell
.\.venv3\Scripts\python.exe -c "import main; [print(('%s' % (getattr(r,'path','?'))).ljust(34), getattr(r,'methods',None) or 'WEBSOCKET') for r in main.app.routes if '/tasks' in getattr(r,'path','') or '/ws' in getattr(r,'path','')]"
```

**预期输出**：

```
/tasks/reindex-milvus              {'POST'}
/tasks/rebuild-kg                  {'POST'}
/tasks/nutrition-report            {'POST'}
/tasks/{task_id}                   {'GET'}
/ws/notifications                  WEBSOCKET
```

> 🟢 `/ws/notifications` 显示 `WEBSOCKET` 而不是 `{'GET'}`，说明它被正确注册为 WebSocket 路由（而不是被当成普通 HTTP 路由）。这一条是本阶段最容易出错的地方之一，务必核对。

---

## 十八、子模块 12：前端 WS 客户端（frontend/ 🟢 新建 2 个文件）

### 18.1 新建 `frontend/js/ws.js`，完整内容

```javascript
// frontend/js/ws.js —— v3 阶段 8：WebSocket 实时通知客户端
// 职责：连上 /ws/notifications，收到任务事件就回调；断线自动重连；定时心跳保活；右下角 toast。
// 依赖：可选 api.js（提供 Api.getAccessToken()）。没加载就用 window.WS_TOKEN。
(function (global) {
    'use strict';

    var MAX_DELAY = 15000;    // 重连退避上限（15 秒）
    var BASE_DELAY = 1000;    // 首次重连等待 1 秒
    var HEARTBEAT_MS = 25000; // 心跳间隔：比常见 30/60 秒的空闲超时短一点，防止被中间设备掐断

    var socket = null;        // 当前 WebSocket 实例
    var retryCount = 0;       // 已连续重连次数（用来算退避时长）
    var heartbeatTimer = null;// 心跳定时器
    var reconnectTimer = null;// 重连定时器
    var manualClosed = false; // 主动 close() 时置真，避免把"用户主动断开"也当成掉线去重连
    var listeners = [];       // 事件回调列表

    // 计算后端地址：优先 window.WS_BASE，其次 api.js 的 API_BASE，最后同源
    function backendBase() {
        if (global.WS_BASE) return global.WS_BASE;
        if (typeof API_BASE !== 'undefined' && API_BASE) return API_BASE;
        return global.location.origin;
    }

    // 取 token：优先 api.js，其次 window.WS_TOKEN
    function currentToken() {
        if (typeof Api !== 'undefined' && Api.getAccessToken) {
            var t = Api.getAccessToken();
            if (t) return t;
        }
        return global.WS_TOKEN || '';
    }

    // 拼出 ws(s)://host/ws/notifications?token=xxxx
    // 🔴 token 只能走查询参数：浏览器原生 WebSocket 不支持自定义请求头
    function buildUrl() {
        var base = backendBase().replace(/\/+$/, '');
        var url = new URL(base + '/ws/notifications', global.location.href);
        url.protocol = (url.protocol === 'https:') ? 'wss:' : 'ws:';
        url.search = '?token=' + encodeURIComponent(currentToken());
        return url.toString();
    }

    function emit(event) {
        for (var i = 0; i < listeners.length; i++) {
            try { listeners[i](event); } catch (e) { console.error('[ws] 回调异常', e); }
        }
    }

    function startHeartbeat() {
        stopHeartbeat();
        heartbeatTimer = global.setInterval(function () {
            if (socket && socket.readyState === 1) {
                try { socket.send('ping'); } catch (e) { /* 发失败就让 onclose 走重连 */ }
            }
        }, HEARTBEAT_MS);
    }

    function stopHeartbeat() {
        if (heartbeatTimer) { global.clearInterval(heartbeatTimer); heartbeatTimer = null; }
    }

    function scheduleReconnect() {
        if (manualClosed) return;
        if (reconnectTimer) return;                     // 已经在等重连了，别叠加
        var delay = Math.min(BASE_DELAY * Math.pow(2, retryCount), MAX_DELAY); // 1s,2s,4s...最多 15s
        retryCount++;
        emit({ type: 'status', state: 'reconnecting', delay: delay, attempt: retryCount });
        reconnectTimer = global.setTimeout(function () {
            reconnectTimer = null;
            connect();
        }, delay);
    }

    function connect() {
        if (socket && (socket.readyState === 0 || socket.readyState === 1)) return; // 连着呢
        manualClosed = false;
        var url = buildUrl();
        if (!currentToken()) {
            emit({ type: 'status', state: 'error', message: '没有 token，无法连接（请先登录）' });
            return;
        }

        try {
            socket = new WebSocket(url);
        } catch (e) {
            emit({ type: 'status', state: 'error', message: '创建 WebSocket 失败：' + e.message });
            scheduleReconnect();
            return;
        }

        socket.onopen = function () {
            retryCount = 0;                              // 连上了就重置退避
            startHeartbeat();
            emit({ type: 'status', state: 'open' });
        };

        socket.onmessage = function (evt) {
            var data;
            try { data = JSON.parse(evt.data); } catch (e) { return; } // 非 JSON（如 pong）忽略
            if (data && data.type === 'pong') return;                  // 心跳应答不用上抛
            emit(data);
        };

        socket.onclose = function (evt) {
            stopHeartbeat();
            socket = null;
            if (manualClosed) { emit({ type: 'status', state: 'closed' }); return; }
            // 1008 = 服务端因鉴权失败主动关闭：重连也没用，直接报错让人去重新登录
            if (evt && evt.code === 1008) {
                emit({ type: 'status', state: 'error', message: '鉴权失败（token 无效或已过期），请重新登录' });
                return;
            }
            emit({ type: 'status', state: 'closed', code: evt && evt.code });
            scheduleReconnect();
        };

        socket.onerror = function () {
            // onerror 之后浏览器一定会调 onclose，重连逻辑交给 onclose，这里只报状态
            emit({ type: 'status', state: 'error', message: '连接出错' });
        };
    }

    function close() {
        manualClosed = true;
        stopHeartbeat();
        if (reconnectTimer) { global.clearTimeout(reconnectTimer); reconnectTimer = null; }
        if (socket) { try { socket.close(1000, 'client close'); } catch (e) {} }
    }

    // 右下角 toast：不依赖任何 CSS 文件，直接内联样式，放哪都能用
    function toast(text, kind) {
        var color = kind === 'error' ? '#d93025' : (kind === 'success' ? '#1a7f37' : '#1f6feb');
        var box = global.document.createElement('div');
        box.style.cssText = [
            'position:fixed', 'right:16px', 'bottom:16px', 'z-index:99999',
            'max-width:340px', 'padding:12px 14px', 'border-radius:10px',
            'background:#fff', 'color:#111', 'font:13px/1.5 sans-serif',
            'box-shadow:0 6px 24px rgba(0,0,0,.18)', 'border-left:4px solid ' + color,
            'white-space:pre-wrap', 'word-break:break-all'
        ].join(';');
        box.textContent = text;
        global.document.body.appendChild(box);
        global.setTimeout(function () { if (box.parentNode) box.parentNode.removeChild(box); }, 6000);
    }

    global.Notify = {
        connect: connect,
        close: close,
        toast: toast,
        on: function (fn) { listeners.push(fn); return fn; },
        off: function (fn) { listeners = listeners.filter(function (f) { return f !== fn; }); },
        isOpen: function () { return !!socket && socket.readyState === 1; }
    };
})(window);
```

### 18.2 新建 `frontend/stage8-tasks.html`，完整内容

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>AI 私厨 · 阶段 8 异步任务与实时推送 · 验证页</title>
<style>
  body { font: 14px/1.6 "Microsoft YaHei", sans-serif; margin: 0; padding: 20px; background: #f6f8fa; color: #1f2328; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: #57606a; margin-bottom: 16px; }
  .card { background: #fff; border: 1px solid #d0d7de; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
  label { min-width: 74px; color: #57606a; }
  input { padding: 6px 8px; border: 1px solid #d0d7de; border-radius: 6px; font-size: 13px; }
  input.grow { flex: 1; min-width: 220px; }
  button { padding: 6px 12px; border: 1px solid #d0d7de; background: #fff; border-radius: 6px; cursor: pointer; font-size: 13px; }
  button:hover { background: #f3f4f6; }
  button.primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  button.primary:hover { background: #1a5fd0; }
  #state { font-weight: 600; }
  #state.open { color: #1a7f37; }
  #state.closed { color: #d93025; }
  #log { height: 320px; overflow: auto; background: #0d1117; color: #c9d1d9; border-radius: 8px; padding: 10px 12px; font: 12px/1.6 Consolas, monospace; white-space: pre-wrap; }
  .hint { color: #57606a; font-size: 12px; }
</style>
</head>
<body>
  <h1>AI 私厨 · 阶段 8 验证页</h1>
  <div class="sub">Celery 异步任务 + WebSocket 实时推送 —— 提交长任务，任务跑完后右下角自动弹通知。</div>

  <div class="card">
    <div class="row">
      <label>后端地址</label>
      <input id="api" class="grow" value="http://127.0.0.1:9002">
      <span class="hint">默认 9002；若用临时端口验证请改成对应端口</span>
    </div>
    <div class="row">
      <label>账号</label>
      <input id="user" value="stage8_demo">
      <label style="min-width:auto">密码</label>
      <input id="pass" type="password" value="stage8-demo-123">
      <button id="btnReg">注册（已存在会失败，可忽略）</button>
      <button id="btnLogin" class="primary">登录并连接</button>
      <button id="btnClose">断开</button>
    </div>
    <div class="row">
      <label>连接状态</label>
      <span id="state" class="closed">未连接</span>
    </div>
  </div>

  <div class="card">
    <div class="row">
      <button id="btnReindex">① 提交 Milvus 重索引（high 队列）</button>
      <button id="btnKg">② 提交图谱重建（default 队列）</button>
      <button id="btnNutri">③ 提交营养报告（low 队列）</button>
      <button id="btnPing">发心跳 ping</button>
    </div>
    <div class="hint">任务跑完会有右上角的<b>绿色成功提示</b>；失败是红色。日志区能看到 STARTED → SUCCESS 两条推送。</div>
  </div>

  <div class="card">
    <div id="log"></div>
  </div>

<script src="js/ws.js"></script>
<script>
// ---- 小工具 ----
const $ = (id) => document.getElementById(id);
const logEl = $('log');
function log(msg) {
  const t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  logEl.textContent += `[${t}] ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}
function setState(text, cls) { const s = $('state'); s.textContent = text; s.className = cls; }

let token = '';
const base = () => $('api').value.replace(/\/+$/, '');

// ---- 登录（顺带把地址喂给 ws.js）----
async function login() {
  window.WS_BASE = base();
  const username = $('user').value, password = $('pass').value;
  const r = await fetch(base() + '/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) { log('登录失败 HTTP ' + r.status + ' ' + (await r.text())); return; }
  const data = await r.json();
  token = data.access_token;
  window.WS_TOKEN = token;
  log('登录成功，token 前缀 ' + token.slice(0, 20) + '...');
  Notify.connect();
}

async function register() {
  window.WS_BASE = base();
  const r = await fetch(base() + '/auth/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: $('user').value, password: $('pass').value, email: $('user').value + '@demo.local' }),
  });
  log('注册 HTTP ' + r.status + '（409 = 已存在，正常）');
}

// ---- 提交任务 ----
async function submit(path, body, label) {
  const r = await fetch(base() + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
    body: JSON.stringify(body),
  });
  if (!r.ok) { log(label + ' 提交失败 HTTP ' + r.status + ' ' + (await r.text())); return; }
  const data = await r.json();
  log(label + ' 已提交 task_id=' + data.task_id + ' 队列=' + data.queue + ' 状态=' + data.status);
}

// ---- 订阅 WebSocket 事件 ----
Notify.on((ev) => {
  if (ev.type === 'status') {
    if (ev.state === 'open') { setState('已连接', 'open'); log('WS 已连接'); }
    else if (ev.state === 'closed') { setState('已断开', 'closed'); log('WS 关闭 code=' + ev.code); }
    else if (ev.state === 'reconnecting') { setState('重连中（第 ' + ev.attempt + ' 次）', 'closed'); log('WS 将在 ' + ev.delay + 'ms 后重连'); }
    else if (ev.state === 'error') { setState('出错', 'closed'); log('WS 错误：' + ev.message); }
    return;
  }
  if (ev.type === 'task') {
    const tag = ev.status === 'SUCCESS' ? '[OK]' : (ev.status === 'FAILURE' ? '[FAIL]' : '[..]');
    log(tag + ' 推送 ' + ev.status + ' · ' + ev.name + ' · task_id=' + ev.task_id);
    if (ev.result) log('   结果：' + JSON.stringify(ev.result));
    if (ev.error) log('   错误：' + ev.error);
    if (ev.status === 'SUCCESS') Notify.toast('任务完成：' + ev.name.split('.').pop() + '\n' + JSON.stringify(ev.result), 'success');
    if (ev.status === 'FAILURE') Notify.toast('任务失败：' + ev.name.split('.').pop() + '\n' + ev.error, 'error');
  }
});

// ---- 按钮绑定 ----
$('btnReg').onclick = () => register().catch(e => log('注册异常 ' + e.message));
$('btnLogin').onclick = () => login().catch(e => log('登录异常 ' + e.message));
$('btnClose').onclick = () => { Notify.close(); setState('未连接', 'closed'); };
$('btnReindex').onclick = () => submit('/tasks/reindex-milvus', { rebuild: true }, '重索引').catch(e => log('提交异常 ' + e.message));
$('btnKg').onclick = () => submit('/tasks/rebuild-kg', { rebuild: false }, '图谱重建').catch(e => log('提交异常 ' + e.message));
$('btnNutri').onclick = () => submit('/tasks/nutrition-report', { ingredients: ['鸡蛋 100克', '西兰花 200克'] }, '营养报告').catch(e => log('提交异常 ' + e.message));
$('btnPing').onclick = () => log('心跳由 ws.js 每 25 秒自动发送 "ping"，服务端回 {"type":"pong"}；此处无需手动操作');

// 支持用 ?api=http://127.0.0.1:9018 预填后端地址（方便换端口验证）
const qs = new URLSearchParams(location.search);
if (qs.get('api')) $('api').value = qs.get('api');
if (qs.get('user')) $('user').value = qs.get('user');

log('页面就绪。请先“注册”（首次）再“登录并连接”。');
</script>
</body>
</html>
```

### 18.3 验证（用 Node 校验语法，不需要浏览器）

```powershell
node --check frontend\js\ws.js
```

**预期**：**没有任何输出**，且 `$LASTEXITCODE` 为 0（`node --check` 通过时不打印东西）。

```powershell
echo $LASTEXITCODE
```

**预期**：`0`

> 🟡 上面两行是**分开执行**的，因为 `node --check` 成功时无输出，靠 `$LASTEXITCODE` 判断。若报 `SyntaxError`，逐字对照上面代码检查（最常见是中文引号被编辑器自动替换成了全角）。

> 🔴 **诚实说明**：`ws.js` 的逻辑（拼 URL、连接、收任务事件、心跳、状态回调）已用 **Node 22 自带 WebSocket** 真实加载运行并验证通过（见 23.7）。`stage8-tasks.html` 的页面交互（点按钮、看右下角 toast）**需要你在浏览器里点一遍确认**——本环境无法安装浏览器做自动化点击。所以验收标准第 9 条请你在 23.7 后用浏览器自查。

---

## 十九、子模块 13：Prometheus 抓 worker + 2 条告警（🔵 修改 2 个 yml）

> 🟣 **这一节是"让阶段 7 的仪表盘也能看到任务"的补充**。跳过它阶段 8 的功能照样跑通，只是 worker 的指标没人抓。建议做完。

### 19.1 改 `docker/prometheus/prometheus.yml`

找到这一段：

```yaml
  # Prometheus 自身（看拉取 / TSDB / 自身资源指标）
  - job_name: "prometheus"
```

在它**上面**插入（注意保持 2 空格缩进）：

```yaml
  # Celery worker 的 /metrics 端点（v3 阶段 8 新增）
  # worker 跑在宿主机（不是容器），所以从容器里用 host.docker.internal 访问 9101
  - job_name: "ai_chief_worker"
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:9101"]
        labels:
          app: ai_chief
          component: celery_worker
          env: dev

```

### 19.2 改 `docker/prometheus/alerts.yml`

在文件**最后**追加（缩进要和已有规则对齐：`- alert:` 前面是 6 个空格）：

```yaml

      # 5) Celery 任务失败（v3 阶段 8 新增）
      # 任何任务在 5 分钟窗口内出现失败，立即告警——长任务失败通常意味着外部依赖（Milvus/Neo4j/DashScope）出问题
      - alert: CeleryTaskFailure
        expr: increase(celery_task_failures_total[5m]) > 0
        for: 1m
        labels:
          severity: warning
          service: ai_chief
          component: celery_worker
        annotations:
          summary: "Celery 任务 {{ $labels.task }} 执行失败"
          description: "任务 {{ $labels.task }} 在最近 5 分钟内出现失败，请查 worker 终端日志确认原因。"

      # 6) 队列积压（v3 阶段 8 新增）
      # 队列深度持续 > 10，说明 worker 处理不过来（任务太长/太少 worker/死循环）
      - alert: CeleryQueueBacklog
        expr: celery_queue_depth > 10
        for: 5m
        labels:
          severity: warning
          service: ai_chief
          component: celery_worker
        annotations:
          summary: "队列 {{ $labels.queue }} 积压（当前 {{ $value }} 条）"
          description: "队列 {{ $labels.queue }} 待处理任务持续超过 10 条，请检查 worker 是否在正常消费。"
```

### 19.3 验证 YAML 语法（两种方式，任选一种）

**方式 A：用 Python 解析（不需要动容器，最快）**

```powershell
.\.venv3\Scripts\python.exe -c "import yaml; p=yaml.safe_load(open('docker/prometheus/prometheus.yml',encoding='utf-8')); print('jobs:', [j['job_name'] for j in p['scrape_configs']]); a=yaml.safe_load(open('docker/prometheus/alerts.yml',encoding='utf-8')); print('alerts:', [r['alert'] for g in a['groups'] for r in g['rules']])"
```

**预期输出**：

```
jobs: ['ai_chief_backend', 'ai_chief_worker', 'prometheus', 'alertmanager']
alerts: ['HighErrorRate', 'HighP99Latency', 'TokenCostSpike', 'QuotaExhausted', 'CeleryTaskFailure', 'CeleryQueueBacklog']
```

**方式 B：用 Prometheus 自带工具校验（更权威）**

```powershell
docker exec ai_chief_prometheus promtool check config /etc/prometheus/prometheus.yml
```

**预期输出**：

```
Checking /etc/prometheus/prometheus.yml
  SUCCESS: 1 rule files found
SUCCESS: /etc/prometheus/prometheus.yml is valid prometheus config file syntax
```

> 🟡 方式 B 校验的是**容器里**的 `/etc/prometheus/prometheus.yml`。如果你改了宿主机文件但还没让容器重新读，校验的还是老内容。所以顺序是：**先改文件 → 再重启容器 → 再校验**。

### 19.4 让 Prometheus 重新加载配置

```powershell
docker restart ai_chief_prometheus
```

**预期**：输出容器名 `ai_chief_prometheus`。

等 10 秒后确认 Prometheus 认出了新的 worker 抓取任务：

```powershell
Start-Sleep -Seconds 10
.\.venv3\Scripts\python.exe -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:9090/api/v1/targets')); [print(t['labels']['job'], t['health'], t['scrapeUrl']) for t in d['data']['activeTargets'] if 'ai_chief' in t['labels']['job']]"
```

**预期输出**（此刻 worker 还没起，`ai_chief_worker` 会是 `down`，**这是正常的**）：

```
ai_chief_backend up http://host.docker.internal:9002/metrics
ai_chief_worker down http://host.docker.internal:9101/metrics
```

> 🟡 等 **23.4** 节 worker 起来后，再跑一次这条命令，`ai_chief_worker` 会变成 `up`。这就是"worker 指标已接入 Prometheus"的铁证。

---

## 二十、子模块 14：验收脚本（scripts/verify_stage8.py 🟢 新建）

### 20.1 新建 `scripts/verify_stage8.py`，完整内容

> 🔴 注意顶部那两行 `sys.path` 处理——**没有它，直接 `python scripts\verify_stage8.py` 会报 `ModuleNotFoundError: No module named 'app_my'`**。这是实测踩到的坑，别删。

```python
# scripts/verify_stage8.py —— v3 阶段 8 验收脚本（两种模式）
#
#   模式一 routing：验证"任务分级路由"是否真的把三个任务送进 high / default / low
#                   —— 只需要 Redis 在跑，不需要 worker、不需要 API
#                   🔴 跑之前请先停掉 worker（否则任务被 worker 消费走，队列会是 0）
#
#   模式二 e2e    ：验证端到端链路：提交任务 → worker 执行 → Redis pub/sub → 中继 → WebSocket
#                   —— 需要 API(9002) + worker 都在跑
#
# 用法（在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#   .\.venv3\Scripts\python.exe scripts\verify_stage8.py routing
#   .\.venv3\Scripts\python.exe scripts\verify_stage8.py e2e
import asyncio
import json
import os
import sys

# 把项目根目录塞进 sys.path。
# 为什么需要：直接 `python scripts\verify_stage8.py` 时，Python 只把 scripts\ 当作模块搜索路径，
# 于是 `import app_my...` 会报 ModuleNotFoundError: No module named 'app_my'。
# 这两行把"脚本所在目录的上一级"（= 项目根）加进去，无论从哪个目录调用都能跑通。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DEMO_INGREDIENTS = ["鸡蛋 100克", "西兰花 200克"]


# ============================================================ 模式一：分级路由
def mode_routing() -> int:
    import redis
    from app_my.worker.celery_app import celery_app
    from app_my.worker.tasks.graph import rebuild_kg_graph
    from app_my.worker.tasks.nutrition import generate_nutrition_report
    from app_my.worker.tasks.reindex import reindex_milvus

    print("=" * 66)
    print("模式一：任务分级路由验证")
    print("=" * 66)

    # ① 先看路由表：Celery 认为每个任务该去哪条队列
    print("\n[1] 路由表（celery_app.conf.task_routes）")
    expected = {
        "tasks.reindex_milvus": "high",
        "tasks.rebuild_kg_graph": "default",
        "tasks.generate_nutrition_report": "low",
    }
    for name, q in expected.items():
        route = celery_app.amqp.router.route({}, name)
        got = route.get("queue") and getattr(route["queue"], "name", route["queue"])
        flag = "OK " if got == q else "!! "
        print("    %s%-32s 期望=%-8s 实际=%s" % (flag, name, q, got))

    # ② 实测：清空 broker → 发三个任务 → 看三条队列各自的长度
    r = redis.Redis.from_url(celery_app.conf.broker_url, decode_responses=True)
    r.flushdb()
    print("\n[2] broker 已清空（%s）" % celery_app.conf.broker_url)

    reindex_milvus.delay(rebuild=True, tenant_id=1, user_id=1)
    rebuild_kg_graph.delay(rebuild=False, tenant_id=1, user_id=1)
    generate_nutrition_report.delay(ingredients=DEMO_INGREDIENTS, tenant_id=1, user_id=1)
    print("[3] 三个任务已发送（未启动 worker，消息暂存在 broker 里）")

    print("\n[4] 三条队列的待处理数（LLEN）：")
    lens = {}
    for q in ("high", "default", "low"):
        lens[q] = r.llen(q)
        print("    %-8s LLEN=%s" % (q, lens[q]))

    r.flushdb()
    print("\n[5] broker 已再次清空（避免残留消息干扰后面的 worker）")

    if lens == {"high": 1, "default": 1, "low": 1}:
        print("\n结果：✅ 分级路由生效 —— 三个任务分别落到 high / default / low")
        return 0
    print("\n结果：❌ 路由不符合预期。若某条队列是 0，请确认 worker 是否已经停掉。")
    return 1


# ============================================================ 模式二：端到端
def mode_e2e(base_url: str = None) -> int:
    import time

    import websockets

    if not base_url:
        # 默认 9002（项目实际端口）；换端口时用环境变量覆盖，例如：
        #   set STAGE8_BASE_URL=http://127.0.0.1:9018
        base_url = os.environ.get("STAGE8_BASE_URL", "http://127.0.0.1:9002")

    print("=" * 66)
    print("模式二：端到端链路验证（API=%s）" % base_url)
    print("=" * 66)

    # 延迟导入：只有 e2e 模式才需要 requests / psycopg2
    import requests

    username = "stage8verify_%d" % int(time.time())
    password = "stage8-verify-123"

    print("\n[1] 注册 + 登录临时账号 %s ..." % username)
    r = requests.post(
        base_url + "/auth/register",
        json={"username": username, "password": password, "email": username + "@verify.local"},
        timeout=15,
    )
    print("    注册 HTTP %s" % r.status_code)
    if r.status_code not in (200, 201):
        print("    注册失败，响应：%s" % r.text[:300])
        return 1
    r = requests.post(
        base_url + "/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    print("    登录 HTTP %s，token 前缀 %s..." % (r.status_code, token[:20]))

    async def run_ws_case() -> int:
        ws_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = ws_base + "/ws/notifications?token=" + token
        got = []

        async with websockets.connect(ws_url) as ws:
            print("\n[2] WebSocket 握手成功（token 走 ?token= 查询参数）")

            await ws.send("ping")
            pong = await asyncio.wait_for(ws.recv(), timeout=5)
            print("[3] 心跳 ping → 服务端回：%s" % pong)

            headers = {"Authorization": "Bearer " + token}
            resp = requests.post(
                base_url + "/tasks/nutrition-report",
                json={"ingredients": DEMO_INGREDIENTS},
                headers=headers,
                timeout=15,
            )
            print("\n[4] 提交营养报告任务 HTTP %s" % resp.status_code)
            if resp.status_code != 200:
                print("    提交失败，响应：%s" % resp.text[:300])
                return 1
            sub = resp.json()
            task_id = sub["task_id"]
            print("    task_id=%s 队列=%s 状态=%s" % (task_id, sub["queue"], sub["status"]))

            print("\n[5] 等待 WebSocket 推送（最多 90 秒）...")
            deadline = time.time() + 90
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(deadline - time.time(), 0.1))
                except asyncio.TimeoutError:
                    print("    超时：没有收到推送（检查 worker 是否启动）")
                    break
                event = json.loads(raw)
                if event.get("type") != "task" or event.get("task_id") != task_id:
                    continue
                got.append(event["status"])
                print("    收到推送：status=%s" % event["status"])
                if event.get("result"):
                    print("        结果：%s" % json.dumps(event["result"], ensure_ascii=False))
                if event.get("error"):
                    print("        错误：%s" % event["error"])
                if event["status"] in ("SUCCESS", "FAILURE"):
                    break

            print("\n[6] 用 GET /tasks/{id} 复核状态")
            st = requests.get(base_url + "/tasks/" + task_id, headers=headers, timeout=15)
            print("    HTTP %s → %s" % (st.status_code, json.dumps(st.json(), ensure_ascii=False)[:400]))

        print("\n[7] 收到的事件序列：%s" % got)
        if got and got[0] == "STARTED" and got[-1] == "SUCCESS":
            print("\n结果：✅ 端到端链路打通（提交 → 排队 → worker 执行 → 推送回客户端）")
            return 0
        print("\n结果：❌ 事件序列不符合预期（应为 STARTED → SUCCESS）")
        return 1

    code = asyncio.run(run_ws_case())

    # 清理临时账号，别在库里留垃圾
    try:
        import psycopg2

        from app_my.core.config import settings

        dsn = settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://", 1)
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (username,))
        conn.close()
        print("[8] 临时账号 %s 已删除" % username)
    except Exception as exc:  # 清理失败不影响验收结论
        print("[8] 临时账号清理失败（不影响结论）：%s" % exc)

    return code


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    mode = args[0] if args else ""
    if mode == "routing":
        return mode_routing()
    if mode == "e2e":
        return mode_e2e()
    print(__doc__)
    print("请指定模式：routing 或 e2e")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

### 20.2 验证（不需要 worker，随时可跑）

> 🔴 跑之前请**确认 worker 没在跑**（`Get-Process python | Where-Object {$_.Path -like '*ai_chief*'}` 看一下，或直接跳过——如果队列数是 0，脚本会提示你）。

```powershell
.\.venv3\Scripts\python.exe scripts\verify_stage8.py routing
```

**预期输出**（本次实测输出，逐字一致）：

```
==================================================================
模式一：任务分级路由验证
==================================================================

[1] 路由表（celery_app.conf.task_routes）
    OK tasks.reindex_milvus             期望=high     实际=high
    OK tasks.rebuild_kg_graph           期望=default  实际=default
    OK tasks.generate_nutrition_report  期望=low      实际=low

[2] broker 已清空（redis://localhost:6380/1）
[3] 三个任务已发送（未启动 worker，消息暂存在 broker 里）

[4] 三条队列的待处理数（LLEN）：
    high     LLEN=1
    default  LLEN=1
    low      LLEN=1

[5] broker 已再次清空（避免残留消息干扰后面的 worker）

结果：✅ 分级路由生效 —— 三个任务分别落到 high / default / low
```

> 🟢 这一步的实测意义：它证明了"任务分级"不只是配置写对了，而是**消息真的落进了三条不同的 Redis list**。这是本阶段最容易被"看起来对、其实没生效"蒙过去的地方。
>
> 🟡 `e2e` 模式的运行放在 **23.6** 节（需要 API 和 worker 都起着）。

---

## 二十一、子模块 15：单元测试（27 例 🟢 新建 5 个文件）

> 🟡 这 27 例**全部不需要 worker 进程**：`test_celery_app.py` 用 eager 模式就地跑任务，`test_ws_gateway.py` 用 `TestClient` 跑一个进程内的 API，只有 Redis 6380 必须在跑。

### 21.1 新建 `tests/unit/test_celery_app.py`（6 例）

```python
# tests/unit/test_celery_app.py  —— v3 阶段 8：Celery 配置与任务执行（不依赖 worker）
"""
覆盖点：
1. broker / result backend 真的落在 Redis 6380 的 db1 / db2（与业务 db0 隔离）；
2. 三条队列 high/default/low 声明齐全；
3. 三个任务名都注册了，且路由到正确队列；
4. eager 模式下营养任务真跑通、返回真实营养数字；
5. 参数不合法时任务真失败、并且 FAILURE 指标 +1。
"""
import pytest

from app_my.core.worker_metrics import CELERY_TASK_FAILURES
from app_my.worker.celery_app import celery_app

NUTRITION = "tasks.generate_nutrition_report"
REINDEX = "tasks.reindex_milvus"
KG = "tasks.rebuild_kg_graph"


@pytest.fixture()
def eager():
    """把 Celery 切到"调用即本地执行"模式，跑完恢复原值（不影响其它用例）"""
    old = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = old


@pytest.fixture()
def eager_non_propagating():
    """
    eager + 不抛异常的组合，专门用来验证"失败路径"。

    为什么失败用例必须关掉 task_eager_propagates：
        Celery 在 eager 模式下如果开着 propagate，异常会立刻原样抛出（方便测试断言异常），
        但代价是"跳过" on_failure 通知这条链（源码 trace.py 的 on_error 里 `if propagate: raise`）。
        要看到 FAILURE 指标和通知，就得关掉 propagate，让 Celery 走正常的失败处理流程。
    """
    old_eager = celery_app.conf.task_always_eager
    old_prop = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = old_eager
    celery_app.conf.task_eager_propagates = old_prop


def test_broker_and_backend_are_isolated_redis_dbs():
    """broker 用 db1、backend 用 db2 —— 与业务缓存的 db0 分开"""
    assert celery_app.conf.broker_url == "redis://localhost:6380/1"
    assert celery_app.conf.result_backend == "redis://localhost:6380/2"


def test_three_queues_declared():
    """三条分级队列必须在"""
    names = {q.name for q in celery_app.conf.task_queues}
    assert names == {"high", "default", "low"}


def test_tasks_registered_and_routed():
    """三个任务已注册，且路由到各自队列"""
    for name in (NUTRITION, REINDEX, KG):
        assert name in celery_app.tasks, f"{name} 未注册"
    assert celery_app.conf.task_routes[REINDEX] == {"queue": "high"}
    assert celery_app.conf.task_routes[KG] == {"queue": "default"}
    assert celery_app.conf.task_routes[NUTRITION] == {"queue": "low"}


def test_serializer_is_json():
    """任务参数/结果必须是 JSON 序列化（安全：不用 pickle）"""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_nutrition_task_runs_eager_and_returns_real_numbers(eager):
    """营养任务在本地同步跑一遍：返回结构完整、数字是真实计算值"""
    from app_my.worker.tasks.nutrition import generate_nutrition_report

    r = generate_nutrition_report.delay(ingredients=["鸡胸肉 200克", "西兰花 1颗"], tenant_id=1, user_id=1)
    assert r.state == "SUCCESS"
    data = r.get()
    assert data["ingredients"] == ["鸡胸肉 200克", "西兰花 1颗"]
    assert data["coverage"] == 1.0                       # 两个食材都命中营养库
    assert data["total_estimated"]["calories"] > 0       # 热量算出来了
    assert "千卡" in data["summary"]


def test_nutrition_task_fails_on_empty_ingredients(eager_non_propagating, monkeypatch):
    """空食材 → 任务状态 FAILURE、失败指标 +1、且发出 FAILURE 通知（带正确的 tenant）"""
    from app_my.worker import base
    from app_my.worker.tasks.nutrition import generate_nutrition_report

    captured = []
    monkeypatch.setattr(base, "publish_task_event", lambda payload: (captured.append(payload), 1)[1])

    before = CELERY_TASK_FAILURES.labels(task=NUTRITION)._value.get()
    r = generate_nutrition_report.delay(ingredients=[], tenant_id=3, user_id=5)
    after = CELERY_TASK_FAILURES.labels(task=NUTRITION)._value.get()

    assert r.state == "FAILURE"                       # 状态是失败
    assert after - before == 1.0                      # 失败计数 +1
    assert captured[-1]["status"] == "FAILURE"        # 发了 FAILURE 通知
    assert captured[-1]["tenant_id"] == 3             # 通知带对了租户（推给谁）
    assert "ValueError" in captured[-1]["error"]      # 错误摘要有内容
```

> 🔴 最后这个用例里有**两个坑**，都是实测踩出来的：
> 1. **必须用 `eager_non_propagating` 而不是 `eager`**。Celery 在 eager + `task_eager_propagates=True` 时，异常会被直接抛出、**跳过 `on_failure`**（源码 `trace.py` 的 `on_error`：`if propagate: raise`）。用 `eager` 的话 `r.state` 拿不到 `FAILURE`，指标也不会 +1，测试必挂。
> 2. `monkeypatch.setattr(base, "publish_task_event", ...)` 替换的是 **`base` 模块里那个已导入的名字**，不是 `notify` 模块里的原函数。替换错了就捕获不到通知。

### 21.2 新建 `tests/unit/test_notify.py`（4 例）

```python
# tests/unit/test_notify.py  —— v3 阶段 8：任务事件构造与发布
"""
覆盖点：
1. build_task_event 字段固定、tenant_id/user_id 转成 int；
2. publish_task_event 真往 Redis 发（返回订阅者数量，是 int）；
3. Redis 抛异常时返回 0，不把异常往外抛（通知不能拖垮任务）。
"""
from app_my.core import notify


def test_build_task_event_shape():
    evt = notify.build_task_event("t-1", "tasks.generate_nutrition_report", "SUCCESS",
                                  result={"a": 1}, tenant_id="7", user_id="11")
    assert evt["type"] == "task"
    assert evt["task_id"] == "t-1"
    assert evt["status"] == "SUCCESS"
    assert evt["result"] == {"a": 1}
    assert evt["error"] is None
    assert evt["tenant_id"] == 7        # 字符串被转成 int
    assert evt["user_id"] == 11


def test_build_task_event_failure_carries_error():
    evt = notify.build_task_event("t-2", "tasks.reindex_milvus", "FAILURE", error="RuntimeError: boom")
    assert evt["status"] == "FAILURE"
    assert evt["error"] == "RuntimeError: boom"
    assert evt["result"] is None


def test_publish_task_event_returns_subscriber_count(monkeypatch):
    """把 get_redis 换成假的：publish 返回 3，则函数返回 3"""
    class FakeRedis:
        def publish(self, channel, data):
            assert channel                        # 频道名非空
            assert isinstance(data, str)          # 已经序列化成 JSON 字符串
            return 3

    monkeypatch.setattr("app_my.core.redis_client.get_redis", lambda: FakeRedis())
    n = notify.publish_task_event(notify.build_task_event("t-3", "tasks.x", "STARTED"))
    assert n == 3


def test_publish_task_event_swallows_redis_error(monkeypatch):
    """Redis 挂了也不能抛异常，返回 0 即可"""
    class BrokenRedis:
        def publish(self, channel, data):
            raise ConnectionError("redis down")

    monkeypatch.setattr("app_my.core.redis_client.get_redis", lambda: BrokenRedis())
    n = notify.publish_task_event(notify.build_task_event("t-4", "tasks.x", "SUCCESS"))
    assert n == 0
```

> 🟡 这里 monkeypatch 的目标是 **`app_my.core.redis_client.get_redis`**（而不是 `notify.get_redis`）——因为 `notify.publish_task_event` 内部是**函数内 import** 的，每次调用都去 `redis_client` 模块取一次，所以替换那里才生效。

### 21.3 新建 `tests/unit/test_ws_manager.py`（5 例）

```python
# tests/unit/test_ws_manager.py  —— v3 阶段 8：WebSocket 连接管理器（纯内存，不依赖服务）
"""
覆盖点：
1. connect 会 accept 并登记；
2. dispatch 只投给同租户的连接（多租户隔离的命门）；
3. 发送失败的"死连接"会被摘掉，不反复重试；
4. disconnect 幂等；空租户投递返回 0。

注意：这里用 asyncio.run() 在同步用例里跑协程，避免额外引入 pytest-asyncio 配置。
"""
import asyncio

from app_my.ws.manager import ConnectionManager


class FakeWS:
    """假 WebSocket：只实现 manager 用到的那两个方法"""

    def __init__(self, fail: bool = False):
        self.accepted = False
        self.sent = []
        self.fail = fail

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.fail:
            raise RuntimeError("socket already closed")
        self.sent.append(data)


def test_connect_accepts_and_registers():
    m = ConnectionManager()
    ws = FakeWS()
    asyncio.run(m.connect(ws, tenant_id=1, user_id=2))
    assert ws.accepted is True
    assert m.stats()["connections"] == 1


def test_dispatch_only_reaches_same_tenant():
    """租户 1 的事件绝不能进租户 2 的连接"""
    m = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    asyncio.run(m.connect(a, tenant_id=1, user_id=1))
    asyncio.run(m.connect(b, tenant_id=2, user_id=2))

    sent = asyncio.run(m.dispatch({"type": "task", "task_id": "x", "tenant_id": 1}))
    assert sent == 1
    assert len(a.sent) == 1
    assert b.sent == []          # 租户 2 什么都没收到


def test_dispatch_drops_dead_connection():
    m = ConnectionManager()
    dead, alive = FakeWS(fail=True), FakeWS()
    asyncio.run(m.connect(dead, tenant_id=1, user_id=1))
    asyncio.run(m.connect(alive, tenant_id=1, user_id=1))

    sent = asyncio.run(m.dispatch({"tenant_id": 1, "task_id": "y"}))
    assert sent == 1
    assert m.stats()["connections"] == 1     # 死连接已被清理


def test_disconnect_is_idempotent():
    m = ConnectionManager()
    ws = FakeWS()
    asyncio.run(m.connect(ws, tenant_id=1, user_id=1))
    m.disconnect(ws)
    m.disconnect(ws)                          # 再删一次也不能报错
    assert m.stats()["connections"] == 0


def test_dispatch_to_tenant_without_connections_returns_zero():
    m = ConnectionManager()
    assert asyncio.run(m.dispatch({"tenant_id": 99})) == 0
```

> 🟡 用 `asyncio.run()` 而不是 `@pytest.mark.asyncio`，是为了**不改 `pytest.ini`**（本项目没配 `asyncio_mode`）。这样新增测试文件不用动全局配置，风险最低。

### 21.4 新建 `tests/unit/test_ws_gateway.py`（4 例）

```python
# tests/unit/test_ws_gateway.py  —— v3 阶段 8：WebSocket 网关（JWT 鉴权 + 实时投递）
"""
覆盖点：
1. 不带 token / 带 refresh token / 带乱码 token —— 一律握手被拒（1008）；
2. 带合法 access token —— 连上、ping/pong 正常；
3. 往 Redis 发一条任务事件 —— 中继把它推到这个连接上（真·端到端）。

依赖：Redis 6380 在跑（阶段 1 的容器）；relay 由 main.py 的 lifespan 自动启动。
"""
import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app_my.core.config import settings
from app_my.core.notify import build_task_event, publish_task_event
from app_my.core.security import create_access_token, create_refresh_token
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wait_relay_subscribed(timeout: float = 10.0) -> bool:
    """等中继协程在 Redis 上订阅成功（否则事件发了没人收，测试会假失败）"""
    from app_my.core.redis_client import get_redis
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            subs = get_redis().pubsub_numsub(settings.WS_NOTIFY_CHANNEL)
            if subs and subs[0][1] >= 1:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def _access_token(user_id: int = 999, tenant_id: int = 4242) -> str:
    return create_access_token(subject=user_id, tenant_id=tenant_id, tenant_role="owner", tenant_plan="free")


def test_handshake_rejected_without_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/notifications"):
            pass


def test_handshake_rejected_with_refresh_token(client):
    """refresh token 不能拿来连 WS（只认 access token）"""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/notifications?token={create_refresh_token(999)}"):
            pass


def test_handshake_rejected_with_garbage_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/notifications?token=not-a-jwt"):
            pass


def test_ping_pong_and_receive_task_push(client):
    """连上后：ping 得 pong；随后发的事件经 Redis 中继推回本连接"""
    assert _wait_relay_subscribed(), "Redis 中继未在超时内订阅频道，检查 6380 容器"

    token = _access_token(user_id=999, tenant_id=4242)
    with client.websocket_connect(f"/ws/notifications?token={token}") as ws:
        ws.send_text("ping")
        assert ws.receive_json() == {"type": "pong"}

        # 模拟 worker 发一条"营养报告完成"事件（tenant 4242 = 本连接所属租户）
        publish_task_event(build_task_event(
            "task-abc-123", "tasks.generate_nutrition_report", "SUCCESS",
            result={"summary": "估算本餐总热量 215.0 千卡"}, tenant_id=4242, user_id=999,
        ))

        evt = ws.receive_json()
        assert evt["type"] == "task"
        assert evt["task_id"] == "task-abc-123"
        assert evt["status"] == "SUCCESS"
        assert evt["result"]["summary"].startswith("估算本餐总热量")
```

> 🔴 `_wait_relay_subscribed()` 那个轮询是**必需的**：`TestClient(app)` 触发 lifespan、`create_task(run_relay())` 是异步的，主协程不会等它订阅完就继续往下跑。不等待就直接 publish，事件会"发出去没人收"，测试偶发失败（假失败）。用 `pubsub_numsub` 查订阅者数量是最可靠的确认方式。

### 21.5 新建 `tests/unit/test_task_api.py`（8 例）

```python
# tests/unit/test_task_api.py  —— v3 阶段 8：任务提交/查询接口
"""
覆盖点：
1. 不登录取不到任务接口（401）；
2. 三个提交接口都返回 task_id + 正确的队列名（high/default/low）；
3. 营养报告参数校验（空列表 → 422）；
4. GET /tasks/{id} 能正确翻译 SUCCESS / FAILURE 两种状态。

手法说明：这里把"任务对象的 .delay"换成假的，只验证接口契约，
    不真的投递任务（真投递的验证在 test_celery_app.py 的 eager 用例里做）。
    monkeypatch 的目标是 "app_my.api.tasks.reindex_milvus" —— 也就是 api 模块里
    那三个 import 进来的名字，替换它们等于换掉接口看到的任务对象。
"""
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app_my.core.security import create_access_token
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers():
    token = create_access_token(subject=1, tenant_id=1, tenant_role="owner", tenant_plan="free")
    return {"Authorization": f"Bearer {token}"}


def _stub_task(task_id: str):
    """假任务对象：只有一个 .delay()，返回带 id 的东西，模拟 Celery 投递后的返回"""
    class _Stub:
        def delay(self, **kwargs):
            return SimpleNamespace(id=task_id)
    return _Stub()


def test_submit_requires_auth(client):
    r = client.post("/tasks/nutrition-report", json={"ingredients": ["鸡蛋 2个"]})
    assert r.status_code == 401


def test_submit_nutrition_report(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app_my.api.tasks.generate_nutrition_report", _stub_task("fake-nutrition-001"))
    r = client.post("/tasks/nutrition-report", json={"ingredients": ["鸡蛋 2个"]}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == "fake-nutrition-001"
    assert body["name"] == "tasks.generate_nutrition_report"
    assert body["queue"] == "low"
    assert body["status"] == "PENDING"


def test_submit_nutrition_report_rejects_empty_list(client, auth_headers):
    r = client.post("/tasks/nutrition-report", json={"ingredients": []}, headers=auth_headers)
    assert r.status_code == 422          # Pydantic min_length=1 拦住了


def test_submit_reindex_uses_high_queue(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app_my.api.tasks.reindex_milvus", _stub_task("fake-reindex-002"))
    r = client.post("/tasks/reindex-milvus", json={"rebuild": False}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["queue"] == "high"


def test_submit_rebuild_kg_uses_default_queue(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app_my.api.tasks.rebuild_kg_graph", _stub_task("fake-kg-003"))
    r = client.post("/tasks/rebuild-kg", json={"rebuild": False}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["queue"] == "default"


def test_get_task_status_success(client, auth_headers, monkeypatch):
    class _FakeResult:
        status = "SUCCESS"
        result = {"rows": 60, "row_count": 60}

        def successful(self):
            return True

        def failed(self):
            return False

    monkeypatch.setattr("app_my.api.tasks.AsyncResult", lambda task_id, app=None: _FakeResult())
    r = client.get("/tasks/whatever", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "SUCCESS"
    assert r.json()["result"]["rows"] == 60


def test_get_task_status_failure(client, auth_headers, monkeypatch):
    class _FakeResult:
        status = "FAILURE"
        result = RuntimeError("Milvus 不可用：清场失败")

        def successful(self):
            return False

        def failed(self):
            return True

    monkeypatch.setattr("app_my.api.tasks.AsyncResult", lambda task_id, app=None: _FakeResult())
    r = client.get("/tasks/whatever", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "FAILURE"
    assert "Milvus" in r.json()["error"]


def test_get_task_status_requires_auth(client):
    """查任务状态同样要登录"""
    r = client.get("/tasks/whatever")
    assert r.status_code == 401
```

> 🔴 `test_get_task_status_*` 这两个用例**必须带 `auth_headers`**。`GET /tasks/{task_id}` 走的是全局 `AuthMiddleware`，不带 `Authorization` 头直接返回 401。这是实测时踩到的坑：一开始漏了 `auth_headers`，两个用例全红。

### 21.6 跑测试

**先只跑阶段 8 新增的 5 个文件**（跑得快，出错好定位）：

```powershell
.\.venv3\Scripts\python.exe -m pytest tests/unit/test_celery_app.py tests/unit/test_notify.py tests/unit/test_ws_manager.py tests/unit/test_ws_gateway.py tests/unit/test_task_api.py -v
```

**预期输出尾行**：

```
============================= 27 passed in ...s ==============================
```

**再跑全量（基线核对）**：

```powershell
.\.venv3\Scripts\python.exe -m pytest -q
```

**预期输出尾行**：

```
118 passed, 7 deselected, ... warnings in ...s
```

> 🟢 118 = 阶段 7 的 91 + 阶段 8 的 27。这个数字对上了，就说明你既没漏测、也没把老测试弄坏。
>
> 🟡 `test_ws_gateway.py` 第一次跑可能比平时慢一点（要等中继订阅，最多 10 秒），属正常。

---

## 二十二、requirements.txt 登记（🔵 修改）

### 22.1 追加钉版行

在 `requirements.txt` **最后一行**（当前是 `neo4j==6.3.1`）之后追加下面这些行：

```
celery==5.6.3
kombu==5.6.2
amqp==5.4.1
billiard==4.3.1
vine==5.1.0
click-didyoumean==0.3.1
click-plugins==1.1.1.2
click-repl==0.4.1
python-dateutil==2.9.0.post0
tzlocal==5.4.4
prompt-toolkit==3.0.53
```

> 🟡 这里只钉 Celery 自己 + 它带出来的**直接依赖**（你机器上实测解析到的版本）。`wcwidth`、`six` 等更底层的传递依赖不列（`pip install -r` 时会自动解析）。**如果你机器上 `pip install` 解析出的版本和上面不一致，以你的为准**——执行下面这条命令看实际结果：
>
> ```powershell
> .\.venv3\Scripts\python.exe -m pip freeze | Select-String -Pattern "celery|kombu|amqp|billiard|vine|click-|dateutil|tzlocal|prompt-toolkit"
> ```

### 22.2 验证

```powershell
Get-Content requirements.txt -Tail 11
```

**预期**：列出上面那 11 行。

再确认依赖可复现（不会因为 requirements.txt 写错而装不上）：

```powershell
.\.venv3\Scripts\python.exe -m pip install -r requirements.txt --dry-run 2>&1 | Select-Object -Last 5
```

**预期**：末尾出现 `Would install ...` 或 `Requirement already satisfied` 之类的提示，**不应出现 `ERROR: No matching distribution found`**。

---

## 二十三、启动与验证（端到端实测记录）

> 本节所有输出都是**本次实测的真实结果**（在你的容器 + 项目源码副本上跑出来的）。

### 23.1 🔴 启动顺序总览（照这个顺序来，不要跳）

| 步骤 | 做什么 | 在哪个终端 | 为什么必须在这个位置 |
|---|---|---|---|
| 1 | 装 Celery | 任意 | 没装后面全报 `No module named 'celery'` |
| 2 | 写完全部代码 + 跑单测 | 任意 | 代码不对，起了服务也是白起 |
| 3 | 改 2 个 Prometheus yml → 重启 Prometheus | 任意 | 可选，但要在 worker 起来前完成 |
| 4 | **确认容器在跑**（尤其 Redis 6380） | 终端 A | broker 不通，worker 起不来 |
| 5 | **起 API**（uvicorn 9002） | **终端 A** | API 一起来就订阅 Redis 频道（中继） |
| 6 | **起 worker** | **终端 B** | worker 起来才有人消费队列 |
| 7 | 分级路由验证（`routing`） | 终端 A | 🔴 **必须在 worker 起来前做**，否则任务被消费走 |
| 8 | 端到端验证（`e2e`） | 终端 A | 需要 API + worker 都活着 |
| 9 | 浏览器手工验证 | 浏览器 | 验收标准第 9 条 |

> 🔴 **顺序陷阱**：`routing` 模式靠"消息堆在队列里没人消费"来数长度，所以它必须在 **worker 起来之前**跑。如果你已经起了 worker，要么先 Ctrl+C 停掉 worker，要么直接跳过 routing（它只验证路由，e2e 会顺带证明路由通了）。

### 23.2 步骤 4：确认容器在跑

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}" | Select-String "ai_chief"
```

**预期**：`ai_chief_redis` 状态含 `Up ... (healthy)`，`ai_chief_pgvector`、`ai_chief_milvus`、`ai_chief_neo4j` 同理。

单独确认 Redis 6380 通：

```powershell
docker exec ai_chief_redis redis-cli ping
```

**预期**：`PONG`

### 23.3 步骤 5：终端 A — 起 API（🔴 必须重启，老进程不会加载新代码）

> ⚠️ 如果你之前有阶段 7 的 uvicorn 在跑（占着 9002），**先停掉它**：在那个终端按 `Ctrl+C`，或按 23.9 的方法按端口杀进程。

在**终端 A**执行：

```powershell
cd F:\pycharm_aiprogram\ai_chief
.\.venv3\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 9002
```

**预期输出**（关键几行）：

```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
{"...", "level": "INFO", "logger": "ai_sichu", "msg": "AI私厨企业版 v2.0.0 启动中...", "trace_id": "-"}
{"...", "level": "INFO", "logger": "ai_sichu", "msg": "监听: http://0.0.0.0:9002", "trace_id": "-"}
{"...", "level": "INFO", "logger": "ai_sichu", "msg": "Debug: False", "trace_id": "-"}
{"...", "level": "INFO", "logger": "ai_sichu", "msg": "ws relay: 后台订阅任务已启动", "trace_id": "-"}
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:9002 (Press CTRL+C to quit)
{"...", "level": "INFO", "logger": "ai_sichu", "msg": "ws relay: 已订阅 Redis 频道 ai_chief:ws:notify", "trace_id": "-"}
```

**🔴 三条必须看到的日志**：

1. `ws relay: 后台订阅任务已启动`
2. `ws relay: 已订阅 Redis 频道 ai_chief:ws:notify` ← **没有这一条，任务事件就永远推不到浏览器**
3. `Uvicorn running on http://0.0.0.0:9002`

> 🔴 **不要加 `--reload`**。阶段 8 的 API 进程里多了一个常驻中继协程，热重载会重复创建/销毁协程与 Redis 订阅，容易出现"旧订阅没退、新订阅又来"的混乱。改代码就用 23.9 的方式重启。

**保持这个终端不动**，另开一个 PowerShell 窗口继续。

### 23.4 步骤 6：终端 B — 起 worker

新开一个 PowerShell 窗口（这就是**终端 B**），执行：

```powershell
cd F:\pycharm_aiprogram\ai_chief
.\.venv3\Scripts\python.exe -m celery -A app_my.worker.celery_app:celery_app worker --loglevel=info --pool=solo -Q high,default,low -n stage8@%h
```

> 🔴 **`--pool=solo` 不能省**。Windows 上 Celery 默认的 `prefork`（billiard 多进程池）会因为缺 `fork` 系统调用而直接报错退出。`--pool=solo` = 单进程串行执行，开发机上最稳。
>
> 🟡 `-n stage8@%h` 是给这个 worker 起名（`stage8@你的主机名`），方便和其它 worker 区分。

**预期输出**（关键部分）：

```
 -------------- stage8@DESKTOP-XXXXXXX v5.6.3 (recovery)
--- ***** -----
-- ******* ---- Windows-10-10.0.19045-SP0 2026-10-15 14:39:37
- *** --- * ---
- ** ---------- [config]
- ** ---------- .> app:         ai_chief:0x...........
- ** ---------- .> transport:   redis://localhost:6380/1        ← broker 是 db1
- ** ---------- .> results:     redis://localhost:6380/2        ← backend 是 db2
- *** --- * --- .> concurrency: 16 (solo)
-- ******* ---- .> task events: OFF (enable -E to monitor tasks in this worker)
--- ***** -----
 -------------- [queues]
                .> default          exchange=default(direct) key=default
                .> high             exchange=default(direct) key=default
                .> low              exchange=default(direct) key=default

[tasks]
  . tasks.generate_nutrition_report
  . tasks.rebuild_kg_graph
  . tasks.reindex_milvus

[...: INFO/MainProcess] Connected to redis://localhost:6380/1
[...: INFO/MainProcess] mingle: searching for neighbors
[...: INFO/MainProcess] mingle: all alone
[...: INFO/MainProcess] worker: 指标已暴露 http://0.0.0.0:9101/metrics
[...: INFO/MainProcess] Redis 客户端已创建: redis://localhost:6380/0
[...: INFO/MainProcess] worker: 就绪，队列 high / default / low
[...: INFO/MainProcess] stage8@DESKTOP-XXXXXXX ready.
```

**🔴 五条必须核对的内容**：

| # | 必须看到 | 说明 |
|---|---|---|
| 1 | `transport: redis://localhost:6380/1` | broker 落在 db1（不是 db0！） |
| 2 | `results: redis://localhost:6380/2` | backend 落在 db2 |
| 3 | `[queues]` 下有 `high` / `default` / `low` 三条 | 分级队列声明成功 |
| 4 | `[tasks]` 下有三个 `tasks.xxx` | 三个任务注册成功 |
| 5 | `worker: 指标已暴露 http://0.0.0.0:9101/metrics` + `ready.` | 指标服务起了、worker 就绪 |

**在终端 A（或第三个窗口）验证 worker 指标**：

```powershell
curl.exe -s http://127.0.0.1:9101/metrics | Select-String -Pattern "^celery_"
```

**预期输出**（此时还没跑过任务，所以计数是 0 或只有队列深度）：

```
celery_queue_depth{queue="high"} 0.0
celery_queue_depth{queue="default"} 0.0
celery_queue_depth{queue="low"} 0.0
```

> 🟡 `celery_task_total` 要等第一个任务跑完才会出现（Counter 的带标签子指标是"被观测过才创建"）。

**顺便验证 Prometheus 已经抓到 worker**（如果你做了第十九节）：

```powershell
.\.venv3\Scripts\python.exe -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:9090/api/v1/targets')); [print(t['labels']['job'], t['health'], t['scrapeUrl']) for t in d['data']['activeTargets'] if 'ai_chief' in t['labels']['job']]"
```

**预期输出**（现在两条都应该是 `up`）：

```
ai_chief_backend up http://host.docker.internal:9002/metrics
ai_chief_worker up http://host.docker.internal:9101/metrics
```

### 23.5 步骤 7：分级路由验证（🔴 **先别急着做这一步看下面的警告**）

> 🔴 **`routing` 模式必须在"没有 worker 消费"的前提下跑**。你现在 worker 已经起来了，所以有两条路：
>
> - **路线 A（推荐）**：去终端 B 按 `Ctrl+C` 停掉 worker → 跑 routing → 再重新起 worker。
> - **路线 B**：直接跳过 routing，跑到 23.6 的 e2e（e2e 会真实跑通三个队列之一，说明路由是通的）。
>
> 下面按**路线 A** 写。

**① 在终端 B 按 `Ctrl+C` 停掉 worker**

**预期**：终端 B 输出 `worker: 正在关闭`，提示符回来。

**② 在终端 A 跑 routing**

```powershell
.\.venv3\Scripts\python.exe scripts\verify_stage8.py routing
```

**预期输出**：

```
==================================================================
模式一：任务分级路由验证
==================================================================

[1] 路由表（celery_app.conf.task_routes）
    OK tasks.reindex_milvus             期望=high     实际=high
    OK tasks.rebuild_kg_graph           期望=default  实际=default
    OK tasks.generate_nutrition_report  期望=low      实际=low

[2] broker 已清空（redis://localhost:6380/1）
[3] 三个任务已发送（未启动 worker，消息暂存在 broker 里）

[4] 三条队列的待处理数（LLEN）：
    high     LLEN=1
    default  LLEN=1
    low      LLEN=1

[5] broker 已再次清空（避免残留消息干扰后面的 worker）

结果：✅ 分级路由生效 —— 三个任务分别落到 high / default / low
```

**③ 用 redis-cli 手工复核一遍（可选，但很直观）**

```powershell
.\.venv3\Scripts\python.exe scripts\verify_stage8.py routing | Out-Null
docker exec ai_chief_redis redis-cli -n 1 KEYS "*"
```

**预期**：只会看到 `1) "high"` 之类的队列 key（脚本第 5 步已经清空，所以更可能返回 `(empty array)`）。这条命令主要是让你确认 **broker 的 key 空间里没有业务 key**。

**④ 重新起 worker（回到终端 B，跑 23.4 那条命令）**

### 23.6 步骤 8：端到端验证（API + worker 都在跑）

在终端 A 执行：

```powershell
.\.venv3\Scripts\python.exe scripts\verify_stage8.py e2e
```

**预期输出**（本次实测原文）：

```
==================================================================
模式二：端到端链路验证（API=http://127.0.0.1:9002）
==================================================================

[1] 注册 + 登录临时账号 stage8verify_1792046956 ...
    注册 HTTP 201
    登录 HTTP 200，token 前缀 eyJhbGciOiJIUzI1NiIs...

[2] WebSocket 握手成功（token 走 ?token= 查询参数）
[3] 心跳 ping → 服务端回：{"type":"pong"}

[4] 提交营养报告任务 HTTP 200
    task_id=b624d8c5-... 队列=low 状态=PENDING

[5] 等待 WebSocket 推送（最多 90 秒）...
    收到推送：status=STARTED
    收到推送：status=SUCCESS
        结果：{"ingredients": ["鸡蛋 100克", "西兰花 200克"], "total_estimated": {"calories": 215.0, "protein": 21.5, "fat": 10.0, "carbs": 11.4}, "coverage": 1.0, "unmatched": [], "summary": "估算本餐总热量 215.0 千卡；蛋白 21.5g / 脂肪 10.0g / 碳水 11.4g；匹配率 100%", "seconds": 0.01}

[6] 用 GET /tasks/{id} 复核状态
    HTTP 200 → {"task_id": "b624d8c5-...", "status": "SUCCESS", ...}

[7] 收到的事件序列：['STARTED', 'SUCCESS']

结果：✅ 端到端链路打通（提交 → 排队 → worker 执行 → 推送回客户端）
[8] 临时账号 stage8verify_1792046956 已删除
```

**同时去终端 B 看 worker 日志**，应该能看到：

```
[...: INFO/MainProcess] Task tasks.generate_nutrition_report[xxxx] received
[...: INFO/MainProcess] Task tasks.generate_nutrition_report[xxxx] succeeded in 0.37s: {...}
```

**再去终端 A 看 API 日志**，应该能看到：

```
{"...", "msg": "ws: 连接建立 tenant=58 user=77 当前连接数=1", ...}
{"...", "msg": "ws relay: 事件已投递 1 个连接（task_id=...）", ...}
{"...", "msg": "ws relay: 事件已投递 1 个连接（task_id=...）", ...}
{"...", "msg": "ws: 连接断开 tenant=58 user=77 当前连接数=0", ...}
```

**🔴 这三处日志同时出现，才叫"链路真的通了"**：

| 位置 | 日志 | 证明了什么 |
|---|---|---|
| worker 终端 | `Task ... received` / `succeeded` | worker 真的执行了任务 |
| API 终端 | `ws relay: 事件已投递 1 个连接` | 通知跨进程送到了 API，并推给了浏览器连接 |
| 脚本输出 | `['STARTED', 'SUCCESS']` | 客户端真的收到了两条推送 |

**再验证 worker 指标涨上去了**：

```powershell
curl.exe -s http://127.0.0.1:9101/metrics | Select-String -Pattern "celery_task_total|celery_task_duration_seconds_count"
```

**预期输出**（本次实测）：

```
celery_task_total{queue="low",status="STARTED",task="tasks.generate_nutrition_report"} 1.0
celery_task_total{queue="low",status="SUCCESS",task="tasks.generate_nutrition_report"} 1.0
celery_task_duration_seconds_count{task="tasks.generate_nutrition_report"} 1.0
```

> 🟢 注意标签里是 `queue="low"`——这正是 `base.py::_read_ctx` 那个"回退查 task_routes"发挥作用的结果。如果不做这个回退，标签会退化成 `default`，指标就和真实队列对不上了。

**验证"提交接口真的不阻塞"（毫秒级返回）**：

```powershell
.\.venv3\Scripts\python.exe -c "import time,requests; b='http://127.0.0.1:9002'; u='stage8perf_%d'%time.time(); p='stage8-pass-123'; requests.post(b+'/auth/register',json={'username':u,'password':p,'email':u+'@t.local'}); t=requests.post(b+'/auth/login',json={'username':u,'password':p}).json()['access_token']; h={'Authorization':'Bearer '+t}; t0=time.perf_counter(); r=requests.post(b+'/tasks/nutrition-report',json={'ingredients':['鸡蛋 100克']},headers=h); dt=(time.perf_counter()-t0)*1000; print('HTTP', r.status_code, 'took %.1f ms' % dt); print(r.json())"
```

**预期输出**（耗时通常在 10~60ms 之间，取决于机器）：

```
HTTP 200 took 23.4 ms
{'task_id': '...', 'name': 'tasks.generate_nutrition_report', 'queue': 'low', 'status': 'PENDING'}
```

> 🟡 这个临时账号 `stage8perf_*` 不会被自动清理。想清掉：`docker exec ai_chief_pgvector psql -U ai_sichu -d ai_sichu -c "DELETE FROM users WHERE username LIKE 'stage8perf_%';"`

### 23.7 前端 `ws.js` 的真实行为验证（用 Node，不需要浏览器）

> 🟢 这一步是**替代"浏览器自动化"的真实验证**：Node 22 自带全局 `WebSocket` / `fetch` / `URL`，所以可以直接把 `frontend/js/ws.js` 加载进 Node，用真实网络跑一遍它的连接与事件回调逻辑。

把下面这段存成项目根目录的 `_verify_wsjs.js`：

```javascript
// 在 Node 里加载 frontend/js/ws.js，验证：URL 拼接、真实连接、事件回调、状态回调
'use strict';
const path = require('path');

const API = 'http://127.0.0.1:9002';
const USER = 'stage8_wsjs_' + Date.now();

global.window = global;
global.location = { href: API + '/x.html', origin: API };
global.document = {
  createElement: () => ({ style: {}, textContent: '', parentNode: null }),
  body: { appendChild() {}, removeChild() {} },
};
global.WS_BASE = API;   // 让 ws.js 用这个地址（而不是默认推导）

(async () => {
  await fetch(API + '/auth/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: 'wsjs-pass-123', email: USER + '@t.local' }),
  });
  const lr = await fetch(API + '/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: 'wsjs-pass-123' }),
  });
  global.WS_TOKEN = (await lr.json()).access_token;
  console.log('[0] 登录成功');

  require(path.join(__dirname, 'frontend', 'js', 'ws.js'));
  console.log('[1] ws.js 已加载，方法：', Object.keys(window.Notify).join(', '));

  const events = [];
  let opened = null;
  const openedPromise = new Promise((res) => { opened = res; });
  const donePromise = new Promise((res) => { global.__done = res; });

  window.Notify.on((ev) => {
    if (ev.type === 'status') {
      console.log('[2] 状态:', ev.state, ev.message || '');
      if (ev.state === 'open') opened();
      if (ev.state === 'error') global.__done && global.__done();
      return;
    }
    if (ev.type === 'task') {
      events.push(ev.status);
      console.log('[4] 收到任务推送:', ev.status, '|', ev.name);
      if (ev.status === 'SUCCESS' || ev.status === 'FAILURE') global.__done && global.__done();
    }
  });

  window.Notify.connect();
  await Promise.race([openedPromise, new Promise((r) => setTimeout(r, 8000))]);
  console.log('[3] isOpen() =', window.Notify.isOpen());

  const sub = await fetch(API + '/tasks/nutrition-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + global.WS_TOKEN },
    body: JSON.stringify({ ingredients: ['鸡蛋 100克', '西兰花 200克'] }),
  });
  console.log('[3.5] 提交任务 HTTP', sub.status, JSON.stringify(await sub.json()));

  await Promise.race([donePromise, new Promise((r) => setTimeout(r, 60000))]);
  window.Notify.close();

  console.log('[5] 事件序列:', JSON.stringify(events));
  const ok = events[0] === 'STARTED' && events[events.length - 1] === 'SUCCESS';
  console.log(ok ? '[OK] ws.js 行为正确' : '[FAIL] 未收到预期事件');
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
```

跑它：

```powershell
node _verify_wsjs.js
```

**预期输出**（本次实测原文）：

```
[0] 登录成功
[1] ws.js 已加载，方法： connect, close, toast, on, off, isOpen
[2] 状态: open
[3] isOpen() = true
[3.5] 提交任务 HTTP 200 {"task_id":"4de88740-...","name":"tasks.generate_nutrition_report","queue":"low","status":"PENDING"}
[4] 收到任务推送: STARTED | 任务: tasks.generate_nutrition_report
[4] 收到任务推送: SUCCESS | 任务: tasks.generate_nutrition_report
[5] 事件序列: ["STARTED","SUCCESS"]
[OK] ws.js 行为正确
```

> 🟢 这一步的实测意义：**证明 `frontend/js/ws.js` 不是"看起来对"的代码**——它真的拼出了正确的 `ws://` 地址、真的连上了网关、真的收到了两条任务事件、状态回调也是对的。
>
> 🟡 临时账号 `stage8_wsjs_*` 自己清一下：`docker exec ai_chief_pgvector psql -U ai_sichu -d ai_sichu -c "DELETE FROM users WHERE username LIKE 'stage8_%';"`

### 23.8 步骤 9：浏览器手工验证（验收标准第 9 条，需要你自己点）

**① 起一个静态服务器给前端页面用**（新开一个窗口，叫终端 C）：

```powershell
cd F:\pycharm_aiprogram\ai_chief\frontend
..\.venv3\Scripts\python.exe -m http.server 9000 --bind 127.0.0.1
```

**预期**：`Serving HTTP on 127.0.0.1 port 9000 ...`

> 🟡 用 9000 是因为项目 `frontend/js/api.js` 里写死了"页面在 9000 时后端走 9002"。我们的验证页 `stage8-tasks.html` 自己管地址（用输入框），所以端口其实随意，但用 9000 最不容易和别的东西冲突。

**② 浏览器打开验证页**

```
http://127.0.0.1:9000/stage8-tasks.html
```

**③ 依次点击**

| 步 | 操作 | 预期 |
|---|---|---|
| 1 | 点【注册（已存在会失败，可忽略）】 | 日志区出现 `注册 HTTP 201`（第二次点是 `409`，正常） |
| 2 | 点【登录并连接】 | 日志出现 `登录成功…` 与 `WS 已连接`，右上角状态变绿色「已连接」 |
| 3 | 点【③ 提交营养报告】 | 日志出现 `营养报告 已提交 task_id=... 队列=low` |
| 4 | 等 1~2 秒 | 日志出现 `[..] 推送 STARTED` 然后 `[OK] 推送 SUCCESS …`；**右下角弹出白底绿边 toast**，内容是「任务完成：generate_nutrition_report + 结果 JSON」 |
| 5 | 点【① 提交 Milvus 重索引】 | 会跑几十秒（真调 embedding + 写 Milvus）。跑完弹 toast，结果里有 `rows` / `expected` / `row_count` |

**④ 顺手验证"断线自动重连"**

在终端 C 按 `Ctrl+C` 停掉静态服务器？**不行**——那样页面本身就没了。正确做法是**停掉 API**（终端 A 按 `Ctrl+C`）：

- 预期：页面右上角状态变成「重连中（第 N 次）」，日志不断出现 `WS 将在 XXXXms 后重连`
- 再把 API 起回来（23.3 那条命令）
- 预期：约 1~2 秒内自动恢复为「已连接」，**不需要刷新页面**

> 🟢 这个"停 API → 自动重连"的演示，就是简历里"断线自动重连"那句话的证据。

### 23.9 停止与重启（终端重启一步不省）

**停 API（终端 A）**：在该终端按 `Ctrl+C`

**预期**：输出 `服务关闭，清理资源...`，提示符回来。

**停 worker（终端 B）**：按 `Ctrl+C`

**预期**：输出 `worker: 正在关闭`，提示符回来。

**停静态服务器（终端 C）**：按 `Ctrl+C`

**🔴 如果某个终端已经关了、但端口还被占着**（比如上次没正常退出）：

```powershell
# 查 9002 被谁占着
Get-NetTCPConnection -LocalPort 9002 -State Listen | Select-Object OwningProcess
# 按上面查到的 PID 杀（把 12345 换成实际 PID）
Stop-Process -Id 12345 -Force
```

一次性查三个端口：

```powershell
foreach ($p in 9002,9000,9101) { $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($c) { "PORT $p -> pid $($c.OwningProcess -join ',')" } else { "PORT $p : free" } }
```

**🔴 改了代码之后怎么重启**：

| 改了什么 | 要重启谁 |
|---|---|
| `app_my/worker/**` 下任何文件 | **只重启 worker**（终端 B）；API 也要重启，因为 API 进程也 import 了任务模块（`api/tasks.py` 依赖它们） |
| `app_my/api/**`、`app_my/ws/**`、`main.py` | **重启 API**（终端 A） |
| `app_my/core/config.py` | **两个都重启**（配置被两个进程各读一次） |
| 只改 `tests/**` | 都不用重启，直接重跑 pytest |

**关闭时想清空任务残留**（可选）：

```powershell
docker exec ai_chief_redis redis-cli -n 1 FLUSHDB   # 只清 broker（db1）
docker exec ai_chief_redis redis-cli -n 2 FLUSHDB   # 只清 backend（db2）
```

> 🔴 **千万不要** `redis-cli FLUSHALL`——那会把 db0 的业务缓存/配额/限流一起清掉。

### 23.10 本次实测结论汇总

| 验收项 | 结果 | 证据 |
|---|---|---|
| pytest 全量 | ✅ **118 passed, 7 deselected** | 阶段 7 的 91 + 新增 27 |
| 阶段 8 新增用例 | ✅ **27 passed** | 5 个测试文件 |
| broker/backend 分 db | ✅ | worker 日志 `transport: .../1`、`results: .../2` |
| 三条分级队列 | ✅ | worker 日志 `[queues] high/default/low` |
| 三任务注册 | ✅ | worker 日志 `[tasks]` 三条 |
| 分级路由实测 | ✅ | `high=1 default=1 low=1`（routing 模式） |
| worker 指标 | ✅ | `curl :9101/metrics` 有 `celery_queue_depth` / `celery_task_total` |
| WS 鉴权 | ✅ | 无 token / refresh / 乱码 → 1008 拒绝（4 例单测） |
| 端到端推送 | ✅ | 脚本输出 `['STARTED','SUCCESS']`；API 日志 `事件已投递 1 个连接` |
| 前端 ws.js 行为 | ✅ | Node 真实跑通，输出 `[OK] ws.js 行为正确` |
| 前端页面 toast | ⚠️ **待你自查** | 本环境无法装浏览器自动化，请按 23.8 手动点一遍 |

---

## 二十四、提交 Gitee 与 PR 描述

### 24.1 提交前自检

```powershell
.\.venv3\Scripts\python.exe -m pytest -q
```

**必须**：`118 passed, 7 deselected`。不是这个数就别提交。

```powershell
git status --short
```

**预期**：能看到新增的 `app_my/worker/`、`app_my/ws/`、`app_my/api/tasks.py`、`app_my/schemas/tasks.py`、`app_my/core/notify.py`、`app_my/core/worker_metrics.py`、`frontend/js/ws.js`、`frontend/stage8-tasks.html`、`scripts/verify_stage8.py`、`tests/unit/test_*.py`，以及修改的 `main.py`、`app_my/core/config.py`、`requirements.txt`、`docker/prometheus/*.yml`、两本手册。

**🔴 提交前务必确认没有把这些也加进来**：

```powershell
git status --short | Select-String -Pattern "_verify_|\.log$|\.env$"
```

**预期**：没有输出。若有，说明你把临时验证脚本或日志加进来了——先用 `git rm --cached <文件>` 移出，再往 `.gitignore` 里补规则。

### 24.2 提交

```powershell
git add -A
git commit -m "feat(v3-stage8): Celery 异步任务队列 + WebSocket 实时推送

- Celery 5.6.3：broker=Redis db1 / result backend=Redis db2，与业务 db0 隔离
- 三级队列 high/default/low + task_routes 任务分级
- 三个长任务异步化：Milvus 重索引(high) / Neo4j 图谱重建(default) / 营养报告(low)
- 任务接口：POST /tasks/{reindex-milvus,rebuild-kg,nutrition-report} + GET /tasks/{id}
- WebSocket /ws/notifications：JWT 走 ?token= 查询参数，连接按 tenant_id 分组
- Redis pub/sub 跨进程中继：worker -> Redis 频道 -> API relay -> 浏览器
- NotifyTask 基类：before_start/on_success/on_failure 统一发通知 + 记指标
- worker 指标独立端口 9101，接入 Prometheus + 2 条告警
- 前端 ws.js：指数退避重连 + 心跳保活 + 右下角 toast
- 验收脚本 scripts/verify_stage8.py（routing / e2e 两种模式）
- pytest 91 -> 118 passed（新增 27 例）
"
```

**预期**：`[feat/v3-stage8 xxxxxxx] feat(v3-stage8): ...` 加一行文件变更统计。

### 24.3 推送

```powershell
git push -u origin feat/v3-stage8
```

**预期**：`branch 'feat/v3-stage8' set up to track 'origin/feat/v3-stage8'`，并显示 `remote: ...` 一堆 Gitee 的提示。

### 24.4 PR 描述（阶段 8）

> 在 Gitee 上从 `feat/v3-stage8` 向 `main` 提 PR，标题与描述照抄下面。

**标题**：`feat(v3-stage8): Celery 异步任务队列 + WebSocket 实时推送`

**描述**：

```markdown
## 做了什么

把三件长任务（Milvus 向量重索引 / Neo4j 图谱重建 / 营养报告）从同步请求中剥离，接口毫秒级返回 `task_id`；任务跑完通过 WebSocket 主动推送回浏览器。

## 核心改动

### 任务队列
- Celery 5.6.3，broker=Redis 6380 **db1**、result backend=**db2**，与业务缓存/限流/配额的 **db0** 物理隔离
- 三条分级队列 `high` / `default` / `low`，`task_routes` 按任务名分流
- `task_acks_late=True`（worker 崩了任务不丢）、`worker_prefetch_multiplier=1`（长任务不囤积）、`task_track_started=True`（看得到 STARTED）
- 序列化只允许 JSON，禁用 pickle

### 三个长任务
| 任务 | 队列 | 重试 | 说明 |
|---|---|---|---|
| `tasks.reindex_milvus` | high | 1 次 | 复用阶段 6 的 embedding + Milvus 写入，跑完失效 rag/rag2 缓存 |
| `tasks.rebuild_kg_graph` | default | 0 | 直接复用 `scripts/init_kg.py::build()`，不复制 Cypher |
| `tasks.generate_nutrition_report` | low | 0 | 调用营养工具，返回热量/蛋白/脂肪/碳水/匹配率 |

### 任务接口
- `POST /tasks/reindex-milvus`、`POST /tasks/rebuild-kg`、`POST /tasks/nutrition-report` → 立即返回 `task_id`
- `GET /tasks/{task_id}` → `PENDING / STARTED / SUCCESS / FAILURE` + `result` / `error`
- 全部复用阶段 4 的 JWT 鉴权与租户上下文，无需额外鉴权代码

### WebSocket 实时推送
- `/ws/notifications`，**JWT 走 `?token=` 查询参数**（浏览器原生 WS 不能自定义 header）
- WS 端点在中间件之外，因此**自己校验 JWT**（含 refresh token 拒绝、黑名单校验）
- 连接管理按 `tenant_id` 分组，跨租户绝不串推；死连接自动摘除
- 链路：worker 任务钩子 `publish` → Redis 频道 `ai_chief:ws:notify` → API 常驻 `run_relay` 协程 → 本进程 WS 连接
- 客户端心跳 `ping` → 服务端 `pong`

### 可观测
- worker 独立指标端口 **9101**：`celery_task_total{task,queue,status}`、`celery_task_duration_seconds`、`celery_task_failures_total`、`celery_queue_depth`
- Prometheus 新增 `ai_chief_worker` 抓取任务；新增 2 条告警 `CeleryTaskFailure` / `CeleryQueueBacklog`

### 前端
- `frontend/js/ws.js`：指数退避重连（1s→2s→4s…上限 15s）、25 秒心跳保活、右下角 `toast`、1008 鉴权失败不重连
- `frontend/stage8-tasks.html`：手工验证页（注册/登录/连接/提交三个任务/看推送日志）

### 验收脚本
- `scripts/verify_stage8.py routing`：实测三个任务分别落进 high/default/low（LLEN=1/1/1）
- `scripts/verify_stage8.py e2e`：注册→建 WS→提交任务→收到 `STARTED`→`SUCCESS`→查状态→清理测试账号

## 测试

- 新增 27 例，全部通过
- 全量：**118 passed, 7 deselected**（阶段 7 基线 91）
- 新增覆盖：Celery 配置/路由/eager 真跑/失败路径、通知构造与降级、连接管理器租户隔离、WS 握手鉴权三态、任务接口契约 8 例

## 实测验证（本机真实跑过）

- 真实 worker 启动：`transport: redis://localhost:6380/1`、`results: redis://localhost:6380/2`、三队列、三任务、`指标已暴露 http://0.0.0.0:9101/metrics`
- 端到端：提交营养报告 → worker 执行 0.37s → 两条事件经中继推回客户端 → `GET /tasks/{id}` 返回 SUCCESS
- worker 指标实测：`celery_task_total{queue="low",status="SUCCESS",task="tasks.generate_nutrition_report"} 1.0`
- 前端 `ws.js` 用 Node 22 真实加载运行测通（连接/事件/状态回调）

## 破坏性变更

无。既有接口行为不变；`main.py` 只新增 import / lifespan 协程 / 2 条路由，中间件顺序未动。
新增一个对外端口 9101（worker 指标），仅本机/Beta 环境使用。
```

### 24.5 🟡 遗留：阶段 5 / 6 / 7 的 PR 描述

按之前约定，PR 描述推迟到下一阶段开工时一起补。目前**仍缺**：

| 阶段 | 分支 | 状态 |
|---|---|---|
| 阶段 5（PgBouncer + 多级缓存） | `feat/v3-stage5` | 🟡 缺 PR 描述 |
| 阶段 6（Milvus + 混合检索 v2） | `feat/v3-stage6` | 🟡 缺 PR 描述 |
| 阶段 7（Prometheus + Grafana + Loki） | `feat/v3-stage7` | 🟡 缺 PR 描述 |
| **阶段 8** | `feat/v3-stage8` | ✅ 本节已给 |

> 🟡 需要我一并补 5/6/7 的 PR 描述时，说一声即可——我会按你各阶段的收官文档生成同样的格式。

---

## 二十五、常见错误对照表

> 按"你在屏幕上看到的报错原文"查。绝大多数行都能一眼定位。

### 25.1 安装 / 依赖类

| 报错 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'celery'` | 没装 Celery，或用错了解释器 | 跑 6.6 的 `pip install "celery[redis]==5.6.3"`，并确认用的是 `.\.venv3\Scripts\python.exe` |
| `ModuleNotFoundError: No module named 'app_my'` | 直接 `python scripts\verify_stage8.py`，`sys.path` 里没有项目根 | 确认脚本顶部那两行 `sys.path.insert` 没被删；或改用 `python -m scripts.verify_stage8 routing` |
| `SyntaxError: future feature annotations is not defined` | 用错了解释器（本机 3.6.5） | 换成 `.\.venv3\Scripts\python.exe`（3.13.14） |
| `ERROR: No matching distribution found for celery==5.6.3` | 网络/镜像问题 | 换源：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple "celery[redis]==5.6.3"` |

### 25.2 worker 启动类

| 报错 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'app_my.worker.tasks.reindex'` | `celery_app.py` 的 `imports` 引用了还没建的文件 | 先把第十一~十三节的文件全部落盘 |
| `ValueError: not enough values to unpack` / `OSError: [WinError 87]` / 立刻退出且无有用日志 | Windows 上用了 `prefork` 池 | 加 `--pool=solo`（见 23.4） |
| `ConnectionRefusedError: [WinError 10061]` 连 `localhost:6380` | Redis 容器没起 | `docker compose -f docker/docker-compose.v3.yml up -d redis` |
| `consumer: Cannot connect to redis://localhost:6380/1: ...` | broker 地址写错，或 Redis 没起 | 核对 `config.py` 的 `CELERY_BROKER_URL`；核对容器 |
| `[queues]` 下只有 `celery` 一条 | 忘了 `-Q high,default,low`，或 `task_queues` 没配 | 检查启动命令带 `-Q`；检查 `celery_app.py` 的 `task_queues` |
| `[tasks]` 下没有 `tasks.xxx` | `imports` 写错/任务模块 import 失败 | 跑 13.5 验证 A；看 worker 启动日志里有没有 traceback |
| `KeyError: 'tasks.reindex_milvus'` 或 `Received unregistered task` | API 端与 worker 端的任务名不一致 | 核对 `name=` 与 `task_routes` 的键是否一致 |
| `OSError: [WinError 10048] 通常每个套接字地址...只允许使用一次` | 9101 被占（上次 worker 没退干净） | 见 23.9 的按端口杀进程 |

### 25.3 接口 / 任务类

| 现象 | 原因 | 解决 |
|---|---|---|
| `POST /tasks/*` 返回 `401 未认证` | 没带 `Authorization: Bearer <token>` | 先 `/auth/login` 拿 access_token |
| `POST /tasks/*` 返回 `503` 或长时间挂住 | Redis 不通（投递不出去） | 确认容器与 `CELERY_BROKER_URL` |
| `GET /tasks/{id}` 永远 `PENDING` | **worker 没在跑**（最常见） | 去终端 B 起 worker |
| 提交返回 200 有 `task_id`，但前端没推送 | API 没订阅频道 | 看 API 日志有没有 `ws relay: 已订阅 Redis 频道`；没有就重启 API |
| `POST /tasks/nutrition-report` 返回 `422` | `ingredients` 是空列表 | Pydantic `min_length=1` 拦的，属预期 |
| 任务状态 `FAILURE`，`error` 含 `Milvus 不可用` | Milvus 容器没起 | `docker ps` 看 `ai_chief_milvus` |
| 任务状态 `FAILURE`，`error` 含 `ValueError: ingredients 不能为空` | 任务真收到空参数了 | 检查提交端参数 |
| 重索引任务跑了很久没结束 | 真在调 embedding 接口（正常，几十秒） | 看 worker 日志有无滚动；`/tasks/{id}` 状态应是 `STARTED` |

### 25.4 WebSocket 类

| 现象 | 原因 | 解决 |
|---|---|---|
| 浏览器控制台 `WebSocket connection to ... failed` | URL 端口/协议写错 | 核对 `ws://127.0.0.1:9002/ws/notifications?token=xxx` |
| 浏览器 `close code 1008` | token 无效/过期/是 refresh token/已登出 | 重新登录拿新的 access_token |
| 连上了但收不到推送 | ① worker 没跑 ② API 没订阅 ③ 租户不匹配 | 依次核对 23.6 的三处日志；注意 `tenant_id` 必须一致 |
| 推送给了别人 / 别的租户收到 | 连接按 `tenant_id` 分组，但 token 里的 tenant 不对 | 用同一账号登录；核对 `create_access_token` 时传的 `tenant_id` |
| 连上后几十秒自动断开 | 中间设备掐空闲连接 | `ws.js` 已内置 25 秒心跳，确认页面加载的是新版 `ws.js` |
| `curl` 测 WS 拿不到结果 | curl 不擅长 WS 握手 | 用 `scripts\verify_stage8.py e2e` 或浏览器的 `new WebSocket(...)` |
| 页面里 `ws://` 但后端是 `wss://`（或反之） | 协议不一致 | `ws.js` 会按 `WS_BASE` 自动选 `ws`/`wss`，检查传入的地址协议 |

### 25.5 测试类

| 报错 | 原因 | 解决 |
|---|---|---|
| `test_nutrition_task_fails_on_empty_ingredients` 挂在 `r.state == "FAILURE"` | 用了 `eager` fixture（`task_eager_propagates=True` 会跳过 `on_failure`） | 必须用 `eager_non_propagating`（见 21.1 的说明） |
| `test_get_task_status_*` 返回 401 而非 200 | 用例漏了 `auth_headers` | 两个用例都要带 `headers=auth_headers` |
| `test_ping_pong_and_receive_task_push` 偶发失败 | 中继还没订阅完就 publish | 确认 `_wait_relay_subscribed()` 没被删；确认 Redis 6380 在跑 |
| `Redis 中继未在超时内订阅频道` | Redis 容器没起 / lifespan 没跑 | `docker exec ai_chief_redis redis-cli ping` 应回 `PONG` |
| 全量跑到 `118 passed` 之外的数字 | 基线不对或漏/多写了用例 | 阶段 7 基线 91 + 新增 27 = 118；核对 `git stash` 前后 |

### 25.6 指标 / 告警类

| 现象 | 原因 | 解决 |
|---|---|---|
| `curl :9101/metrics` 连不上 | worker 没起或没到 `ready.` | 看终端 B 是否出现 `worker: 指标已暴露`；`Get-NetTCPConnection -LocalPort 9101` |
| Prometheus 里 `ai_chief_worker` 一直 `down` | worker 没起；或 Docker 里访问不到宿主机 | 起 worker；确认 Docker Desktop 的 `host.docker.internal` 可用 |
| `promtool check config` 报 YAML 错 | 缩进不对（`- alert:` 前必须是 6 空格） | 用 19.3 方式 A 的 Python 解析定位行号 |
| 告警规则没生效 | 改了 yml 没重启 Prometheus | `docker restart ai_chief_prometheus` |
| `celery_task_total` 一个都没有 | 还没跑过任何任务（Counter 子指标延迟创建） | 提交一次营养报告再看 |

---

## 二十六、避坑提示

### 26.1 🔴 五个"一定会踩"的坑

1. **Windows 上必须 `--pool=solo`**。不加就报错退出，而且日志可能只有一句不痛不痒的 `OSError`。这是 Windows + Celery 的经典组合坑。
2. **WebSocket 不能带自定义 header**。`new WebSocket(url, {headers: {...}})` 是**无效**的（第二个参数只支持子协议字符串）。令牌只能走 `?token=`，或者连上后首帧发 token。本阶段选了前者。
3. **HTTP 中间件管不到 WebSocket**。`AuthMiddleware` 只处理 `scope["type"] == "http"`。WS 的 scope 是 `"websocket"`，会**绕过所有中间件**直达端点。所以 `gateway.py` 必须自己鉴权——这是"以为有中间件兜底、结果游客也能连"的根源。
4. **通知失败绝不能影响任务**。`publish_task_event` 里 `except Exception` 返回 0 是**刻意**的，不是偷懒。Redis 抖一下就把任务标成 FAILURE，是设计错误。
5. **`routing` 验证必须在 worker 停掉时做**。worker 在跑的时候，任务刚进队列就被消费走，`LLEN` 永远是 0，你会误以为"路由坏了"。

### 26.2 🟡 容易忽略的细节

- **`create_task` 必须在 `yield` 之前，`cancel` 必须在 `yield` 之后**。写反了服务一启动中继就死。
- **不要把 `relay.py` 的订阅改成 `CELERY_BROKER_URL`**。发布（`notify.py` 用 `get_redis()` → db0）与订阅（`relay.py` 用 `REDIS_URL` → db0）必须在同一个 db。改到 db1 就永远收不到。
- **Redis 只清 db1/db2，永远别 `FLUSHALL`**。db0 里有限流计数、配额、JWT 黑名单、缓存——清掉会让线上行为全部重置。
- **`requirements.txt` 的钉版以你机器为准**。我用的是"直接依赖 + 实测版本"，`pip install -r` 时更底层的传递依赖由 pip 解析。
- **`prometheus.yml` 加 job 后要重启容器**，不是改完就生效。
- **前端页面必须存成 UTF-8**。这个 HTML/CSS/JS 里有中文，如果编辑器存成 GBK，浏览器会乱码。
- **本手册 18.2 的 HTML 里，日志前缀用的是 `[OK]` / `[FAIL]` / `[..]` 而不是 emoji**。这是刻意的：避免编辑器编码差异导致 emoji 变问号。功能完全一样。

### 26.3 🟣 与后续阶段的联动（提前记住）

- **阶段 9（微服务拆分 + Kong 网关）**：Kong 转发 WebSocket 必须显式配 `Upgrade` / `Connection` 头，否则网关后面的浏览器连不上。届时记得给 `/ws/*` 单独配一条 route。
- **阶段 9 拆服务时**，worker 要不要独立成服务？建议先不拆——worker 本来就是独立进程，和 API 只是共用代码库。拆成独立仓库的收益小、同步成本高。
- **多 worker 水平扩展**：现在就可以再加一个 worker 消费 `low` 队列（`-Q low`），API 侧代码不用改。因为中继是"每个 API 进程各订阅一次、各推自己的连接"，天然支持多实例。
- **`--pool=threads` 什么时候用**：当任务里有大量 IO 等待（如批量调 embedding）且想并行时，可以试 `--pool=threads --concurrency=4`。但要注意任务本身的线程安全性（本阶段三个任务都是"各干各的"，安全）。

---

## 二十七、本阶段防呆自检清单

> 全部打勾才算阶段 8 真正做完。**每一项都给了可执行的验证命令**，不要凭感觉。

### 27.1 环境与依赖

- [ ] `.\.venv3\Scripts\python.exe -V` 输出 `Python 3.13.x`
- [ ] `.\.venv3\Scripts\python.exe -m celery --version` 输出 `5.6.3 (recovery)`
- [ ] `docker exec ai_chief_redis redis-cli ping` 输出 `PONG`
- [ ] `docker ps` 里 `ai_chief_redis` / `ai_chief_pgvector` / `ai_chief_milvus` / `ai_chief_neo4j` 全部 `Up`

### 27.2 代码落盘（对照第五节文件清单逐个数）

- [ ] `app_my/core/notify.py` 新建
- [ ] `app_my/core/worker_metrics.py` 新建
- [ ] `app_my/worker/__init__.py`、`celery_app.py`、`base.py`、`signals.py` 新建
- [ ] `app_my/worker/tasks/__init__.py`、`reindex.py`、`graph.py`、`nutrition.py` 新建
- [ ] `app_my/schemas/tasks.py`、`app_my/api/tasks.py` 新建
- [ ] `app_my/ws/__init__.py`、`manager.py`、`gateway.py`、`relay.py` 新建
- [ ] `frontend/js/ws.js`、`frontend/stage8-tasks.html` 新建
- [ ] `scripts/verify_stage8.py` 新建
- [ ] 5 个 `tests/unit/test_*.py` 新建
- [ ] `app_my/core/config.py` 加了 6 个配置项
- [ ] `main.py` 4 处改完（import asyncio / 3 个 import / lifespan / 2 条路由）
- [ ] `requirements.txt` 追加了 11 行
- [ ] `docker/prometheus/prometheus.yml`、`alerts.yml` 改完

### 27.3 静态验证（不依赖服务）

- [ ] `python -c "import main"` 输出 `import main OK`
- [ ] 路由表里有 5 个阶段 8 端点，且 `/ws/notifications` 显示 `WEBSOCKET`
- [ ] `python -c "...celery_app.conf..."` 显示 broker=.../1、backend=.../2、三队列、三路由
- [ ] eager 模式跑营养任务返回 SUCCESS + 真实营养数字
- [ ] `node --check frontend\js\ws.js` 无输出且 `$LASTEXITCODE` 为 0
- [ ] `python -c "import yaml; ..."` 两条 yml 解析通过（job 4 个、alert 6 条）

### 27.4 运行验证（依赖服务）

- [ ] API 日志出现 `ws relay: 已订阅 Redis 频道 ai_chief:ws:notify`
- [ ] worker 日志出现 `transport: redis://localhost:6380/1` 与 `results: redis://localhost:6380/2`
- [ ] worker 日志出现 `[queues]` 三条与 `[tasks]` 三条
- [ ] worker 日志出现 `worker: 指标已暴露 http://0.0.0.0:9101/metrics` 与 `ready.`
- [ ] `curl :9101/metrics` 返回 `celery_queue_depth{queue="high"} 0.0` 等三行
- [ ] `scripts\verify_stage8.py routing` 输出 `high=1 default=1 low=1`、结尾 ✅
- [ ] `scripts\verify_stage8.py e2e` 输出 `['STARTED','SUCCESS']`、结尾 ✅
- [ ] API 日志出现 `ws relay: 事件已投递 1 个连接`
- [ ] `curl :9101/metrics` 出现 `celery_task_total{queue="low",...}`
- [ ] （可选）Prometheus targets 里 `ai_chief_worker up`
- [ ] `node _verify_wsjs.js` 输出 `[OK] ws.js 行为正确`

### 27.5 浏览器手工验证（你自己点）

- [ ] 打开 `http://127.0.0.1:9000/stage8-tasks.html`，注册 + 登录后状态变「已连接」
- [ ] 点③提交营养报告，日志出现 `STARTED` → `SUCCESS`
- [ ] **右下角出现绿色 toast**（验收标准第 9 条）
- [ ] 点① 提交重索引，几十秒后收到 toast（结果含 `rows` / `row_count`）
- [ ] 停掉 API 后，页面显示「重连中」；API 起回来自动恢复，不用刷新

### 27.6 测试与提交

- [ ] `pytest tests/unit/test_celery_app.py tests/unit/test_notify.py tests/unit/test_ws_manager.py tests/unit/test_ws_gateway.py tests/unit/test_task_api.py -v` 输出 `27 passed`
- [ ] `pytest -q` 输出 `118 passed, 7 deselected`
- [ ] `git status --short` 里没有被误加进来的临时脚本/日志/`.env`
- [ ] 已 `commit` + `push -u origin feat/v3-stage8`
- [ ] 已在 Gitee 提 PR（描述用 24.4 那份）

### 27.7 收尾清理（可选但推荐）

- [ ] 删掉临时验证脚本：`Remove-Item _verify_wsjs.js -ErrorAction SilentlyContinue`
- [ ] 清掉测试账号：`docker exec ai_chief_pgvector psql -U ai_sichu -d ai_sichu -c "DELETE FROM users WHERE username LIKE 'stage8%';"`
- [ ] 清掉 broker/backend 残留：`docker exec ai_chief_redis redis-cli -n 1 FLUSHDB`（**只清 db1，别 FLUSHALL**）

---

## 附：本阶段文件速查表

| 层 | 文件 | 一句话作用 |
|---|---|---|
| 配置 | `app_my/core/config.py` | broker/backend/频道/worker 指标端口 |
| 通知 | `app_my/core/notify.py` | 造事件 + 发 Redis 频道 |
| 指标 | `app_my/core/worker_metrics.py` | 4 个 `celery_*` 指标 + 9101 服务 |
| 引擎 | `app_my/worker/celery_app.py` | Celery 实例 + 三队列 + 分级路由 |
| 粘合 | `app_my/worker/base.py` | `NotifyTask`：通知 + 指标 + 耗时 |
| 生命周期 | `app_my/worker/signals.py` | `worker_ready` 起指标服务、`task_postrun` 刷队列长度 |
| 任务① | `app_my/worker/tasks/reindex.py` | Milvus 重索引（high，可重试 1 次） |
| 任务② | `app_my/worker/tasks/graph.py` | Neo4j 重建（default，复用 init_kg.build） |
| 任务③ | `app_my/worker/tasks/nutrition.py` | 营养报告（low，纯查表不烧 token） |
| 契约 | `app_my/schemas/tasks.py` | 5 个 Pydantic 模型 |
| 接口 | `app_my/api/tasks.py` | 3 提交 + 1 查询 |
| 连接表 | `app_my/ws/manager.py` | 按 `tenant_id` 分组的连接登记表 |
| 端点 | `app_my/ws/gateway.py` | `/ws/notifications` + WS 侧 JWT 鉴权 |
| 中继 | `app_my/ws/relay.py` | Redis 订阅 → 本进程连接派发 |
| 入口 | `main.py` | 起/停中继协程 + 注册路由 |
| 前端 | `frontend/js/ws.js` | 重连退避 + 心跳 + toast |
| 前端 | `frontend/stage8-tasks.html` | 手工验证页 |
| 脚本 | `scripts/verify_stage8.py` | `routing` / `e2e` 两种验收 |
| 测试 | `tests/unit/test_{celery_app,notify,ws_manager,ws_gateway,task_api}.py` | 27 例 |

---

**阶段 8 操作手册 · 完**

> 下一阶段（阶段 9：微服务拆分 + Kong 网关）开工时，我会先跟你确认范围，再交付新的「操作手册 + 说明手册」两件套。
> 阶段 8 收官时（跑完 27.6 的提交与 PR），我会按工作流交付「最终完整版 md + 问题与解决记录 md」。
