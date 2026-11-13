# 食养工作流与图谱推理平台（AI私厨）

> Agent 应用工程师求职作品集项目之一 · [在线功能快照](https://huobuzhe.github.io/showcase/) · [本仓库](https://github.com/huobuzhe/ai_chief) · [导入 PR #1](https://github.com/huobuzhe/ai_chief/pull/1)

## 0. 一分钟了解

用 LangGraph StateGraph 编排**节点式工作流**（coordinator / nutritionist / recommender / recognizer / ranker / personal_chief 等节点），配合 Neo4j 知识图谱多跳推理，回答「食材 + 病症」的食养与禁忌问题；同时把服务做到可鉴权、可限流、可观测、可压测、可部署。

**注意**：这是**确定性节点编排的工作流**，不是自主规划 / 相互协作的多智能体系统。本文里的接口、命令、配置名都来自仓库真实代码，按「运行前置做法 → 快速开始」执行即可把服务跑起来。

### 能做什么

- 输入「高血压患者日常食养」，得到**流式**输出的食养建议（<code>POST /chat/stream</code>，裸文本流）。
- 输入「土豆 + 糖尿病」，走 Neo4j 知识图谱多跳推理给出禁忌 / 宜忌判断（<code>GET /kg/ask</code>）；图谱没连上时自动降级并记日志，服务不会挂。
- 注册 / 登录拿 JWT，接口按用户限流、按租户隔离、按配额控制（阶段 1–10 的工程能力）。
- 用 <code>MOCK_LLM=true</code> 在**没有大模型 API Key** 的情况下跑通整条链路，方便本地开发与压测。
- 看压测报告、监控大盘、CI 配置，了解一个 Agent 服务从「能跑」到「能上线」要补哪些工程件。

### 不做什么（边界）

- 不提供医疗诊断、处方或剂量建议；健康问题请咨询专业人士。
- 不是自主规划型多智能体；节点顺序由 StateGraph 固定。
- 仓库不含 <code>.env</code>、虚拟环境、模型权重、原始语料、日志与缓存，需要自己准备。

## 1. 项目功能详解（用这些能力做了什么）

### 1.1 LangGraph StateGraph 节点式工作流
入口 <code>app_my/agents/coordinator.py</code> 的 <code>chat_coordinator</code> 按状态图依次调度专家节点（coordinator → recognizer → nutritionist → recommender → ranker → personal_chief），每个节点只做一件事，节点间通过共享 state 传递。<code>langgraph.json</code> 声明图，<code>app_my/agents/</code> 是实现。这样做的好处：流程可复现、单点可测、失败可定位，而不是让模型自由规划。

### 1.2 知识图谱多跳推理
<code>app_my/core/kg.py</code> 的 <code>ask(ingredient, condition)</code> 对 Neo4j 做多跳查询（食材 → 成分 → 病症禁忌）。<code>GET /kg/ask?ingredient=土豆&condition=糖尿病</code> 与 <code>GET /kg/stats</code> 对外暴露；未连图谱时返回「图谱不可用」并降级（<code>core/kg.py</code> 里记日志），不会抛 500。

### 1.3 流式问答与降级路径
<code>POST /chat/stream</code> 返回 <code>text/event-stream</code>，但生产的是**裸文本流**（逐段 yield 字符串，不是 SSE <code>data:</code> 帧），前端按裸流读取即可。无食材 / 无法识别时走降级路径，仍返回结构化说明。

### 1.4 账号、鉴权、配额、限流、多租户
<code>app_my/api/auth.py</code> 提供 <code>POST /auth/register</code> 与 <code>POST /auth/login</code>（返回 access_token，默认 30 分钟）；<code>app_my/middleware/</code> 下 AuthMiddleware / QuotaMiddleware（对 <code>/chat/stream</code> 配额）/ RateLimitMiddleware / TenantContextMiddleware / TraceIdMiddleware / MetricsMiddleware 依次生效。公共路径白名单见 <code>app_my/middleware/auth.py</code> 的 <code>PUBLIC_PATHS</code>。

### 1.5 可观测、异步与压测
Celery 异步任务 + WebSocket 网关（<code>app_my/ws/</code>）、Redis Pub/Sub 中继；Prometheus + Grafana + Loki 监控；<code>reports/</code> 与 <code>benchmarks/</code> 存压测报告（并发 60 单体 P99≈3900ms 已劣化、网关 P99≈530ms）。这些证明的不是「模型多聪明」，而是「服务在并发下会怎样、怎么测出来」。

### 1.6 一键部署
<code>docker/docker-compose.yml</code> 编排 pgvector（PG16 + 向量扩展）、redis、api、nginx 四个容器，nginx 对外 8001，本地开发 API 直连 8002。

### 1.7 独立 MCP Server（增量文件）
根目录 <code>mcp_server.py</code> 用 FastMCP 暴露两个 Tool：<code>ask_knowledge_graph</code>（转发 <code>core/kg.ask</code>）与 <code>chat_chief</code>（转发 <code>coordinator.chat_coordinator</code>）；支持 stdio 与 streamable-http，惰性 import，**不被主服务 import**，因此不影响原有代码。

## 2. 知识点与技术栈（以及用它们做了什么）

| 知识点 / 技术 | 在项目里的位置 | 用来做了什么 |
|---|---|---|
| Python ≥ 3.13、FastAPI、Uvicorn | <code>main.py</code>、<code>app_my/api/</code> | 提供 REST / 流式接口，端口 8002，自动 <code>/docs</code> 文档 |
| LangGraph StateGraph、LangChain | <code>langgraph.json</code>、<code>app_my/agents/</code> | 确定性节点式编排、状态传递、工具 / Function Calling 接入 |
| DashScope（qwen3-omni-flash / text-embedding-v3） | <code>.env.example</code>、<code>app_my/core/</code> | 生成回答与向量化；<code>MOCK_LLM=true</code> 时换成固定响应的假模型（<code>app_my/core/mock_llm.py</code>）免密钥跑链路 |
| Neo4j 图数据库 | <code>app_my/core/kg.py</code> | 食材 → 成分 → 病症的多跳禁忌推理，未连接时降级 |
| PostgreSQL / PgBouncer / PGVector、SQLite | <code>.env.example</code> 的 <code>DATABASE_URL</code>、<code>app_my/db/</code> | 用户 / 业务数据、向量检索、连接池 |
| Redis | 限流计数、JWT 黑名单、多级缓存、Celery broker、WS Pub/Sub | 支撑配额、限流与异步任务 |
| JWT（python-jose / passlib / bcrypt） | <code>app_my/api/auth.py</code> | 注册登录、Bearer 鉴权、token 过期控制 |
| 中间件链（TraceId / Auth / Quota / RateLimit / Tenant / Metrics） | <code>app_my/middleware/</code> | 链路追踪、鉴权、配额、限流、多租户、指标采集 |
| Celery + WebSocket | <code>app_my/api/tasks.py</code>、<code>app_my/ws/</code> | 异步任务提交 / 查询、任务完成事件实时推送浏览器 |
| Prometheus / Grafana / Loki | <code>docker/</code>、<code>PROMETHEUS_METRICS_PATH</code> | 指标、大盘、日志聚合 |
| Docker Compose + nginx | <code>docker/</code> | 一键起依赖与网关，容器健康检查由 depends_on 控制 |
| pytest / GitHub Actions | <code>tests/</code>、<code>.github/workflows/</code> | 单测与 CI 回归 |
| MCP（FastMCP） | <code>mcp_server.py</code> | 让外部 Host（如 Claude Desktop）以标准协议调用本项目两个能力 |
| CORS（含 <code>"null"</code> 来源） | <code>app_my/core/config.py:148</code> | 允许本地 <code>file://</code> 静态页直接 fetch 本机服务 |

## 3. 目录结构：该打开哪些文件

| 路径 | 是什么 | 什么时候打开 |
|---|---|---|
| <code>main.py</code> | FastAPI app 装配（lifespan、中间件、路由挂载） | 想知道服务怎么启动、中间件顺序 |
| <code>app_my/core/config.py</code> | 所有配置项（PORT=8002、MOCK_LLM、CORS_ORIGINS、DATABASE_URL 等） | 改端口、开关 Mock、看默认值 |
| <code>.env.example</code> | 环境变量样例（<code>.env</code> 的模板） | **第一步**：复制成 <code>.env</code> 后填写 |
| <code>app_my/api/chat.py</code>、<code>app_my/api/kg.py</code>、<code>app_my/api/auth.py</code> | 三个核心路由 | 调接口前确认请求体 / 参数 |
| <code>app_my/agents/</code>、<code>langgraph.json</code> | 工作流节点与图定义 | 想改节点逻辑 |
| <code>app_my/core/kg.py</code>、<code>app_my/core/mock_llm.py</code> | 图谱推理、假模型 | 排查降级 / 免密钥运行 |
| <code>mcp_server.py</code> | 独立 MCP Server | 想用 MCP 协议接入 |
| <code>requirements.txt</code>、<code>pyproject.toml</code> | pip 与 uv 两套依赖清单（<code>requires-python >= 3.13</code>） | 安装依赖 |
| <code>docker/</code> | compose、api Dockerfile、nginx 配置 | 一键起全栈 |
| <code>reports/</code>、<code>benchmarks/</code> | 压测报告与脚本 | 看性能证据 |
| <code>tests/</code> | 单元 / 接口测试 | 跑 <code>pytest</code> |
| 根目录中文阶段手册（阶段 1–10） | 工程演进记录：奠基、路由与 Token 计费、Neo4j、多租户配额、连接池与缓存、混合检索 v2、全栈监控、Celery/WS、压测与 CI-CD | 想了解每个阶段为什么这么设计 |

## 4. 运行前置做法（Prerequisites）

1. **Python 3.13+**（<code>pyproject.toml</code> 的 <code>requires-python = ">=3.13"</code>）；包管理可用 pip 或 uv。
2. **Git**（克隆仓库）；**Docker Desktop**（可选，用于一键起 Postgres / Redis / Neo4j 等依赖）。
3. **大模型 API Key（可选）**：<code>DASHSCOPE_API_KEY</code>。只想跑通链路 / 压测时把 <code>MOCK_LLM=true</code> 写进 <code>.env</code>，密钥留空即可。
4. **Neo4j（可选）**：知识图谱推理需要；不装也能跑，接口会返回降级结果。
5. **端口**：API <code>8002</code>、nginx <code>8001</code>、Postgres <code>5432</code>、Redis <code>6379</code>；本地开发请确认未被占用。
6. **不要提交 <code>.env</code>**：仓库 <code>.gitignore</code> 已排除它；本文所有密钥都只写在本地 <code>.env</code>。

## 5. 快速开始（详细步骤 + 可复制命令）

### 5.1 拿到代码并安装依赖

~~~bash
git clone https://github.com/huobuzhe/ai_chief.git
cd ai_chief
python -m venv .venv
~~~

激活虚拟环境（二选一）：

~~~powershell
.venv\Scripts\activate
~~~

~~~bash
source .venv/bin/activate
~~~

安装依赖（pip 方式）：

~~~bash
pip install -r requirements.txt
~~~

若使用 uv（<code>pyproject.toml</code> 用的 <code>uv_build</code> 后端）：

~~~bash
uv sync
~~~

### 5.2 生成配置文件

~~~powershell
Copy-Item .env.example .env
~~~

~~~bash
cp .env.example .env
~~~

用文本编辑器**打开 <code>.env</code>**，按需修改：

~~~text
APP_ENV=dev
DEBUG=true
PORT=8002
MOCK_LLM=true
DASHSCOPE_API_KEY=
DATABASE_URL=sqlite:///./db/personal_chief.db
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=["http://127.0.0.1:8002","http://localhost:8002","null"]
~~~

说明：<code>MOCK_LLM=true</code> 时 <code>app_my/core/mock_llm.py</code> 顶替真实模型，整条链路可跑；<code>/chat/stream</code> 之外还依赖 Redis 的后台中继任务，若没起 Redis 只是后台日志告警，接口本身仍可测。要完整体验请执行 5.6 的 Docker Compose。

### 5.3 启动服务

~~~bash
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
~~~

（等价写法：<code>uv run uvicorn main:app --reload</code>；生产去掉 <code>--reload</code> 并加 <code>--workers</code>。）

浏览器打开 [http://127.0.0.1:8002/docs](http://127.0.0.1:8002/docs) 看交互式 API 文档，打开 [http://127.0.0.1:8002/health](http://127.0.0.1:8002/health) 看健康检查。

### 5.4 注册、登录、拿 token

~~~bash
curl -X POST http://127.0.0.1:8002/auth/register -H 'Content-Type: application/json' -d '{"username":"demo","email":"demo@example.com","password":"demo1234"}'
curl -X POST http://127.0.0.1:8002/auth/login -H 'Content-Type: application/json' -d '{"username":"demo","password":"demo1234"}'
~~~

第二条命令返回的 <code>access_token</code> 复制到下面命令的 <code>&lt;token&gt;</code> 位置。<code>/chat/stream</code> 不在公开路径白名单里，**必须带 Bearer token**。

### 5.5 调两个核心接口

~~~bash
curl -N -X POST http://127.0.0.1:8002/chat/stream -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' -d '{"message":"高血压患者日常食养","thread_id":"t1","user_id":"u1"}'
curl 'http://127.0.0.1:8002/kg/ask?ingredient=土豆&condition=糖尿病' -H 'Authorization: Bearer <token>'
curl 'http://127.0.0.1:8002/kg/stats' -H 'Authorization: Bearer <token>'
~~~

Windows PowerShell 里请把 <code>curl</code> 换成 <code>curl.exe</code>（PowerShell 的 <code>curl</code> 是 <code>Invoke-WebRequest</code> 别名）。<code>-N</code> 表示不缓冲，能看到逐段吐字。

### 5.6 完整依赖一键起（Docker Compose）

~~~bash
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps
~~~

启动后 nginx 在 [http://127.0.0.1:8001](http://127.0.0.1:8001)，compose 内的 API 通过服务名互联。停止：

~~~bash
docker compose -f docker/docker-compose.yml down
~~~

### 5.7 跑测试与 MCP Server

~~~bash
pytest -q
python mcp_server.py
python mcp_server.py --transport streamable-http --port 8003
~~~

第一条跑单测；第二条以 stdio 启动 MCP Server（供本地 Host 接入）；第三条以 HTTP 方式监听 8003。

## 6. 接口一览

| 接口 | 请求 / 说明 | 鉴权 |
|---|---|---|
| <code>POST /chat/stream</code> | ChatRequest{message, image_url, thread_id, user_id} → 裸文本流 | Bearer token |
| <code>GET /kg/ask?ingredient=&condition=</code> | 食材 + 病症的图谱多跳推理 | Bearer token |
| <code>GET /kg/stats</code> | 知识图谱规模 | Bearer token |
| <code>POST /auth/register</code> | 注册（username/email/password） | 匿名 |
| <code>POST /auth/login</code> | 登录 → TokenPair{access_token, refresh_token, expires_in} | 匿名 |
| <code>GET /health</code>、<code>GET /docs</code> | 健康检查 / OpenAPI | 匿名 |

## 7. 工程证据

- <code>reports/</code> 内压测报告：并发 60 单体 P99≈3900ms 已劣化、网关 P99≈530ms，/chat/stream 与 /kg/ask 在并发下的变化倍数。
- <code>benchmarks/</code> 内压测脚本，可复跑。
- <code>docker/</code> 与 <code>.github/workflows/</code>：部署编排与 CI。

## 8. 与展示站的关系

[在线功能快照](https://huobuzhe.github.io/showcase/) 里「食养工作流与图谱推理平台」卡片的 6 个实例，来自本项目 2026-11-13 本机真实运行：<code>/chat/stream</code> 的完整流式输出与无食材降级路径，以及 <code>/kg/ask</code> 的禁忌推理命中 / 未命中与图谱规模。[展示站源码](https://github.com/huobuzhe/showcase) 是静态快照，不连接本仓库的服务。

## 9. 常见问题

- **401 / 未授权**：<code>/chat/stream</code> 需要 Bearer token，先走 5.4。
- **流式没有输出**：检查 <code>MOCK_LLM</code>、<code>DASHSCOPE_API_KEY</code>；<code>-N</code> 或浏览器 fetch 按裸文本流读取，不要按 SSE <code>data:</code> 帧解析。
- **kg 返回「图谱不可用」**：Neo4j 未启动，这是预期降级；起 Neo4j 或忽略。
- **端口被占用**：改 <code>.env</code> 的 <code>PORT</code> 或停掉占用进程。
- **静态页跨域失败**：<code>CORS_ORIGINS</code> 需包含 <code>"null"</code>（<code>file://</code>）或你的前端来源。

## 10. 安全与免责声明

- <code>.env</code>、虚拟环境、缓存、日志、模型权重、原始语料均未入库；配置变量名见 <code>.env.example</code>，生产环境务必改掉 <code>JWT_SECRET</code>。
- 内容仅供学习与工程演示，不构成医疗、营养或临床建议；涉及健康问题请咨询专业人士。
