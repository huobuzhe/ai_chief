# 食养工作流与图谱推理平台（AI私厨）

> Agent 应用工程师求职作品集项目之一 · 线上可交互快照：https://huobuzhe.github.io/showcase/

## 一句话介绍

用 LangGraph StateGraph 编排**节点式工作流**（coordinator / nutritionist / recommender / recognizer / ranker / personal_chief 等节点），配合 Neo4j 知识图谱多跳推理，回答「食材 + 病症」的食养与禁忌问题；同时把服务做到可鉴权、可限流、可观测、可压测、可部署。

注意：这是**确定性节点编排的工作流**，不是自主规划 / 相互协作的多智能体系统。

## 这个仓库里有什么

- <code>app_my/</code>：FastAPI 服务主体（路由、配置、中间件、知识图谱、LLM 适配、Mock LLM）
  - <code>app_my/api/chat.py</code> → <code>POST /chat/stream</code> 流式输出（裸文本流，不是 SSE data 帧）
  - <code>app_my/api/kg.py</code> → <code>GET /kg/ask?ingredient=&condition=</code> 图谱多跳推理
  - <code>app_my/api/auth.py</code> → <code>POST /auth/register</code>、<code>POST /auth/login</code>，access token 30 分钟
  - <code>app_my/core/config.py</code>：PORT=8002、CORS_ORIGINS、MOCK_LLM 等配置
  - <code>app_my/middleware/</code>：AuthMiddleware、QuotaMiddleware（对 /chat/stream 限流）、metrics
- <code>langgraph.json</code> 与 <code>app_my/agents/</code>：LangGraph 图定义与专家节点实现
- <code>mcp_server.py</code>：独立的 MCP Server（FastMCP），暴露两个 Tool：<code>ask_knowledge_graph</code>（转发 core/kg.ask）与 <code>chat_chief</code>（转发 coordinator.chat_coordinator）；支持 stdio / streamable-http，惰性 import，不改动主服务
- <code>reports/</code>、<code>benchmarks/</code>：性能压测报告与脚本（并发 60 单体 P99≈3900ms 已劣化、网关 P99≈530ms 等）
- <code>docker/</code>：Neo4j / Redis / Postgres / Milvus / PgBouncer / Prometheus / Grafana / Loki 等编排
- 根目录大量中文阶段手册（阶段 1–10）：工程奠基、智能路由与 Token 计费、Neo4j 知识图谱、多租户 SaaS 化与配额、连接池与多级缓存、混合检索 v2、全栈监控、Celery 异步与 WebSocket 推送、性能压测与 CI-CD、<code>AI私厨_v3.0_阶段10_PR描述.md</code>

## 技术栈

| 层 | 选型 |
|---|---|
| 服务 | Python / FastAPI / Uvicorn，端口 8002 |
| 编排 | LangGraph StateGraph（节点式工作流） |
| 推理 | DashScope LLM（可设 MOCK_LLM=true 免密钥运行）、Function Calling |
| 图谱 | Neo4j 多跳推理；未连接时降级返回「图谱不可用」并记日志 |
| 存储 | Postgres + PgBouncer、Redis 多级缓存、Milvus 混合检索 v2 |
| 工程化 | 多租户与配额、Celery 异步任务、WebSocket 推送、Prometheus + Grafana + Loki |
| 部署 | Docker Compose、GitHub Actions CI |

## 快速开始

1. 复制 <code>.env.example</code> 为 <code>.env</code>，填入 <code>DASHSCOPE_API_KEY</code> 等变量；只想看流程可设 <code>MOCK_LLM=true</code> 跳过真实模型调用。
2. <code>docker compose up -d</code> 起依赖服务（Neo4j / Redis / Postgres / Milvus 等）。
3. <code>uvicorn app_my.main:app --port 8002</code>（或以项目自带方式启动）。
4. <code>POST /auth/register</code> → <code>POST /auth/login</code> 拿 <code>access_token</code>。
5. 带 <code>Authorization: Bearer &lt;token&gt;</code> 调用 <code>POST /chat/stream</code>；<code>GET /kg/ask?ingredient=土豆&amp;condition=糖尿病</code> 验证图谱推理。

## 接口一览

| 接口 | 说明 | 鉴权 |
|---|---|---|
| POST /chat/stream | 流式食养问答，请求体 ChatRequest{message, image_url, thread_id, user_id} | Bearer token |
| GET /kg/ask | 食材 + 病症的图谱多跳推理 | Bearer token |
| GET /kg/stats | 知识图谱规模 | Bearer token |
| POST /auth/register、POST /auth/login | 注册 / 登录，返回 TokenPair | 匿名 |
| GET /health、GET /docs | 健康检查 / OpenAPI | 匿名 |

## 与展示站的关系

https://huobuzhe.github.io/showcase/ 里「食养工作流与图谱推理平台」卡片的 6 个实例，来自本项目 2026-11-13 本机真实运行：<code>/chat/stream</code> 的完整流式输出与无食材降级路径，以及 <code>/kg/ask</code> 的禁忌推理命中 / 未命中与图谱规模。展示页是静态快照，不连接本仓库的服务。

## 安全与免责声明

- <code>.env</code>、虚拟环境、缓存、日志、模型权重、原始语料均未入库；配置变量名见 <code>.env.example</code>。
- 内容仅供学习与工程演示，不构成医疗、营养或临床建议；涉及健康问题请咨询专业人士。
