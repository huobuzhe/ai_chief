# PR 描述：把 AI私厨（食养工作流与图谱推理平台） 完整工程导入 GitHub

> 本文件同时作为该仓库首个 Pull Request 的描述，便于招聘方一眼看清「改了什么、为什么、怎么验证」。

## 这个 PR 做了什么

把本地开发完成的 AI私厨（食养工作流与图谱推理平台） 工程导入此仓库：源码、接口契约、阶段文档、评测 / 压测证据与 CI 配置一次性纳入版本管理，作为 Agent 应用工程师求职作品集的可核查证据。

## 为什么

招聘方能打开、能读、能复现的工程证据，比截图和口头描述更有说服力；尤其是「评测怎么做」「数据从哪来」「服务怎么起」这三件事，需要落在仓库里而不是聊天记录里。

## 包含内容

- FastAPI 服务主体 app_my/ 与 LangGraph StateGraph 节点式工作流编排
- Neo4j 知识图谱多跳推理、/chat/stream 流式问答、/kg/ask、鉴权与配额中间件
- 独立 MCP Server（mcp_server.py，两个 Tool）与 Function Calling 接线
- Docker Compose 编排、监控（Prometheus / Grafana / Loki）、Celery / WebSocket、压测报告
- 阶段 1–10 中文工程手册与 阶段10 PR 描述文档

## 不包含（安全与体积）

- <code>.env</code> 与任何真实密钥、令牌、口令
- 虚拟环境（.venv / .venv3）、Python / 测试缓存、本机日志
- 模型权重、大体积语料与向量索引（体积大且可再生）
- 本机临时文件与个人笔记

但保留了 <code>.env.example</code> 与文档，别人可以按说明自行复现环境。

## 如何验证

1. 复制 .env.example 为 .env，或设 MOCK_LLM=true 免密钥跑通流程
2. docker compose up -d 起依赖后启动服务（默认端口 8002）
3. POST /auth/register → /auth/login 拿 token，再调 POST /chat/stream 与 GET /kg/ask
4. 打开 https://huobuzhe.github.io/showcase/ 查看「食养工作流与图谱推理平台」卡片的运行快照

## 数据来源与诚实说明

展示站 https://huobuzhe.github.io/showcase/ 的 15 条运行实例来自 2026-11-13 本机真实运行，本仓库对应其中一部分；评测报告里的 <code>pipeline_selfcheck</code> / <code>llm_mode=fake</code> 只是自检口径，不是系统质量结论，压测数字只代表本机环境。静态展示页不连接后端。

## 关联链接

- 线上作品集快照：https://huobuzhe.github.io/showcase/
- 展示站源码：https://github.com/huobuzhe/showcase
- 本仓库：https://github.com/huobuzhe/ai_chief
- 同系列另一个项目 MedEviRAG：https://github.com/huobuzhe/MedEviRAG
