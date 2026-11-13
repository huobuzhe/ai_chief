# AI 私厨 v3.0 · 阶段 7 最终完整版 — Prometheus + Grafana + Loki 全栈可观测

> **本文件是阶段 7 的唯一权威完整版。**
> 它合并了本阶段的两份手册（**操作手册（照着做）** + **说明手册（看懂为什么）**），
> 并已吸收实施过程中发现的 **全部 15 处缺陷的勘误**。
> 原两份手册保留作历史档案。照这一份文档，可以从零完整复现阶段 7。

---

## 一、收官信息

| 项 | 值 |
|---|---|
| 阶段 | **7 / 10** —— Prometheus + Grafana + Loki 全栈可观测 |
| 分支 | `feat/v3-stage7` |
| 收官日期 | 2026-10-15 |
| 测试基线 | 83 passed → **91 passed**（新增 `tests/unit/test_metrics.py`，8 个用例全绿） |
| 端到端验证 | `python scripts/verify_stage7.py all` → **11 通过 / 0 失败** |
| 容器 | 5 个全部 Up：prometheus `:9090` / grafana `:3300` / alertmanager `:9093` / loki `:3100` / promtail（不映射端口） |
| 告警规则 | 4 条已加载：`HighErrorRate` / `HighP99Latency` / `TokenCostSpike` / `QuotaExhausted` |
| 仪表盘 | 4 个已自动 provision：HTTP 概览 / Token 成本 / 错误日志 / 告警统计 |
| Prometheus 抓取目标 | `ai_chief_backend` / `prometheus` / `alertmanager` 三个全部 `up` |
| 链路追踪 | 沿用云端 LangSmith，本阶段**不新增**容器 |
| 埋点方式 | `prometheus_client` 官方库 + 中间件层手工埋点（4 类核心指标，标签含 `tenant_id`） |

---

## 二、这份文档怎么用

| 你的目的 | 看哪一部分 |
|---|---|
| 照着敲命令、从零复现阶段 7 | **第一部分 · 操作手册（照着做）** |
| 看懂每一行代码为什么这么写 | **第二部分 · 说明手册（看懂为什么）** |

两部分的分工是刻意的，**不重复**：
操作手册回答"下一步做什么、敲什么命令、应该看到什么"；说明手册回答"这段代码在做什么、为什么这么写、每个参数什么意思"。

---

## 三、总目录

### 第一部分 · 操作手册（照着做） → [点此跳转](#第一部分操作手册照着做)

- 一、阶段目标 ｜ 二、简历叙事（照写） ｜ 三、范围 & 与原方案差异 ｜ 四、端口与基础设施 ｜ 五、文件清单
- 六、准备（切分支 / 跑基线 pytest 确认 83 passed / 确认后端在跑）
- 七、子模块 1：5 个容器（拉镜像 / 改 compose / 顺序警告）
- 八、子模块 2：6 个配置文件（prometheus / alerts / alertmanager / loki / promtail / Grafana provisioning ×2）+ 起容器 + 验证端口 + 验证规则
- 九、子模块 3：核心指标定义 `app_my/core/metrics.py`
- 十、子模块 4：HTTP 埋点中间件 `app_my/middleware/metrics.py`
- 十一、子模块 5：Token 成本指标接入（`token_billing.record()` + `quota.py`）
- 十二、子模块 6：`main.py` 接入 + `/metrics` 端点
- 十三、子模块 7：4 个 Grafana 仪表盘 JSON
- 十四、子模块 8：告警规则与 AlertManager 配置（含制造 5xx 演练）
- 十五、子模块 9：单元测试（8 个）
- 十六、子模块 10：验证脚本 + 提测
- 十七、提交 Gitee 与 PR 描述（含阶段 5/6/7 一并合并）
- 十八、常见错误对照表（含 `not a directory` 专条） ｜ 十九、避坑提示 ｜ 二十、本阶段防呆自检清单

### 第二部分 · 说明手册（看懂为什么） → [点此跳转](#第二部分说明手册看懂为什么)

- 一、本阶段在做什么（一句话与全景图） ｜ 二、新出现的专业名词（术语表）
- 三、为什么是这套可观测栈：现状的三个真空 ｜ 四、Prometheus 数据模型与抓取原理
- 五、`metrics.py` 逐行解释 ｜ 六、`middleware/metrics.py` 逐行解释
- 八、Loki + Promtail 的数据流封装 ｜ 九、Grafana 仪表盘 JSON 字段含义
- 十、AlertManager 规则数学与 PromQL 详解 ｜ 十一、测试设计解释 ｜ 十二、常见疑问
- 附录 A：本阶段一句话解决与价值 ｜ 附录 B：4 个仪表盘 JSON 逐面板解释（按面板说人话）

> 🟡 说明手册原文的章节编号在"六"之后直接跳到"八"（无内容缺失，仅编号跳号），本版照实保留。

---

## 四、收官时补充的四条（操作手册原文没有，本版补上）

### 4.1 🔴 git 提交不完整 —— 必须补提交

本阶段唯一那次提交 `276ec93 feat(v3-stage7): Prometheus+Grafana+Loki 全栈可观测` **只包含了 7 个文件**：

```
.env.example
app_my/agents/coordinator.py
app_my/core/config.py
app_my/core/token_billing.py
app_my/middleware/quota.py
docker/docker-compose.v3.yml
main.py
```

但阶段 7 实际新增/修改的文件远不止这些。下面这些**还没进 git**，直接提 PR 会导致"别人拉下来跑不起来"：

**新增文件（必须提交）**

```
app_my/core/metrics.py                                    # 指标定义中心
app_my/middleware/metrics.py                              # HTTP 埋点中间件 + /metrics 端点
tests/unit/test_metrics.py                                # 8 个单测
scripts/verify_stage7.py                                  # 端到端验证脚本
scripts/stage7_check.sh                                   # 提测脚本（Git Bash）
scripts/stage7_check.ps1                                  # 提测脚本（PowerShell）
docker/prometheus/prometheus.yml                          # 抓取配置
docker/prometheus/alerts.yml                              # 4 条告警规则
docker/alertmanager/alertmanager.yml                      # 告警路由
docker/loki/loki-config.yaml                              # Loki 单机配置
docker/promtail/promtail-config.yaml                      # 日志采集配置
docker/grafana/provisioning/datasources/datasources.yml   # 自动数据源
docker/grafana/provisioning/dashboards/dashboards.yml     # 自动加载目录
docker/grafana/dashboards/http-overview.json              # 仪表盘 1
docker/grafana/dashboards/token-cost.json                 # 仪表盘 2
docker/grafana/dashboards/error-logs.json                 # 仪表盘 3
docker/grafana/dashboards/alerts.json                     # 仪表盘 4
```

**修改文件（必须提交）**

```
main.py                     # 唯一的未提交改动：注释掉 _debug 临时路由引用
```

**文档（按你以往习惯一并提交）**

```
AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_操作手册.md
AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_说明手册.md
AI私厨_v3.0_阶段7_最终完整版.md          ← 本文件
AI私厨_v3.0_阶段7_问题与解决记录.md
AI私厨_v3.0_阶段总表_实际执行版.md
```

**补提交命令（Git Bash，逐段执行）**

```bash
cd /f/pycharm_aiprogram/ai_chief

# 1) 先追加 .gitignore 忽略项（见 4.2），避免误把虚拟环境提交进去
echo ".venv3/" >> .gitignore

# 2) 删掉临时调试路由（见 4.3）
rm -f app_my/api/_debug.py

# 3) 加入阶段 7 的全部新增文件
git add app_my/core/metrics.py app_my/middleware/metrics.py
git add tests/unit/test_metrics.py
git add scripts/verify_stage7.py scripts/stage7_check.sh scripts/stage7_check.ps1
git add docker/prometheus docker/alertmanager docker/loki docker/promtail docker/grafana

# 4) 加入修改文件
git add main.py .gitignore

# 5) 加入文档
git add "AI私厨_v3.0_阶段7_"*.md "AI私厨_v3.0_阶段总表_实际执行版.md"

# 6) 检查有没有漏（确认 .venv3/ 不在列表里！）
git status -sb

# 7) 提交并推送
git commit -m "chore(v3-stage7): 补全阶段7遗漏文件（metrics 核心/埋点中间件/docker 全栈配置/仪表盘/测试/脚本）"
git push origin feat/v3-stage7
```

**补提交命令（PowerShell 5.1，逐段执行）**

```powershell
Set-Location F:\pycharm_aiprogram\ai_chief

Add-Content -Path .gitignore -Value ".venv3/"
Remove-Item -Force app_my\api\_debug.py

git add app_my/core/metrics.py app_my/middleware/metrics.py
git add tests/unit/test_metrics.py
git add scripts/verify_stage7.py scripts/stage7_check.sh scripts/stage7_check.ps1
git add docker/prometheus docker/alertmanager docker/loki docker/promtail docker/grafana
git add main.py .gitignore
git add "AI私厨_v3.0_阶段7_*.md" "AI私厨_v3.0_阶段总表_实际执行版.md"

git status -sb
git commit -m "chore(v3-stage7): 补全阶段7遗漏文件（metrics 核心/埋点中间件/docker 全栈配置/仪表盘/测试/脚本）"
git push origin feat/v3-stage7
```

### 4.2 🔴 `.gitignore` 没有忽略 `.venv3/`

项目 `.gitignore` 里只有 `.venv`（老环境），**没有 `.venv3`**。这正是 `git status` 里冒出 `.venv3/Lib/site-packages/...` 一大堆文件的原因。

如果直接 `git add .`，会把**整个虚拟环境的几万行第三方源码**提交进仓库（仓库瞬间膨胀几百 MB，且以后每次 clone 都变慢）。**必须先加忽略项**：

```
.venv3/
```

（4.1 的命令第 1 步已经包含。）

### 4.3 收尾清理项（不影响功能，建议顺手做掉）

| # | 位置 | 问题 | 处理 |
|---|---|---|---|
| 1 | `app_my/api/_debug.py` | 临时 500 触发器，手册要求"验证完删除"。它留着 = 一个随时可能被扫到、误触发告警的地雷。`main.py` 里已注释引用 | **删除整个文件**（见 4.1 命令第 2 步） |
| 2 | `app_my/core/config.py` | 新增块的首行注释缩进多打了空格（`        # ====`），纯格式问题 | 可选修正 |
| 3 | `app_my/middleware/quota.py` | 残留一行被注释掉的旧代码 `#ok, used, cap = check_quota(...)` | 可选删除 |
| 4 | `app_my/core/token_billing.py` | 新增块前多了两行只含空格的空白行 | 可选清理 |
| 5 | `main.py` | 有未提交改动（注释 `_debug` 路由） | 随 4.1 一并提交 |

### 4.4 本阶段"验收结论"一句话

**83 → 91 passed；端到端验证 11/11 通过；5 容器 Up；4 条告警规则在线；4 个仪表盘自动加载；后端 `/metrics` 被 Prometheus 正常抓取（`up`）。阶段 7 达到收官标准。**

---

<div style="page-break-after: always;"></div>

---
---


# 第一部分：操作手册（照着做）


> **阶段定位**：在阶段 1~6 已有的多模块 + 多中间件基础上，补齐**指标 / 日志 / 告警**三层可观测——为阶段 8 微服务拆分装上"仪表盘"，拆完之后能立刻用阶段 7 的指标验证拆分收益。对应原方案阶段 9。
>
> **本手册性质**：照着做——步骤 / 命令 / 验证 / 排错一站到底。**代码为什么这么写**见配套《说明手册》，本手册不重复解释。
>
> 🔴 **前置硬条件**：阶段 1~6 已收官，pytest 基线 **83 passed**。阶段 7 是纯"加层"——不改既有模块的对外行为，只在中间件栈里加一个 `MetricsMiddleware`，并在 `token_billing` 的 `record()` 末尾加一行 metrics 写入。
>
> 🟡 本阶段**新增 5 个容器**（prometheus / grafana / alertmanager / loki / promtail），合计内存约 **0.8~1.2 GB**——16GB 机器可承受。实验完可以停掉（数据卷保留）。

---

## 目录

- [一、阶段目标](#一阶段目标)
- [二、简历叙事（照写）](#二简历叙事照写)
- [三、范围 & 与原方案差异（颜色标注）](#三范围--与原方案差异颜色标注)
- [四、端口与基础设施](#四端口与基础设施)
- [五、文件清单（创建 / 修改）](#五文件清单创建--修改)
- [六、准备（切分支、基线）](#六准备切分支基线)
- [七、子模块 1：5 个容器（prometheus/grafana/alertmanager/loki/promtail）](#七子模块-1五个容器prometheusgrafanaalertmanagerlokipromtail) —— 🔴 **起容器不在这里做，先读 7.3 的顺序警告**
- [八、子模块 2：6 个配置文件（prometheus / alertmanager / loki / promtail / grafana）](#八子模块-2六个配置文件prometheus--alertmanager--loki--promtail--grafana) —— 🔴 **写完步骤 1~9 才在步骤 10 起容器**
- [九、子模块 3：核心指标定义（app_my/core/metrics.py）](#九子模块-3核心指标定义app_mycoremetricspy)
- [十、子模块 4：HTTP 埋点中间件（app_my/middleware/metrics.py）](#十子模块-4http-埋点中间件app_mymiddlewaremetricspy)
- [十一、子模块 5：Token 成本指标接入](#十一子模块-5token-成本指标接入)
- [十二、子模块 6：main.py 接入 + /metrics 端点](#十二子模块-6mainpy-接入--metrics-端点)
- [十三、子模块 7：Grafana 仪表盘 JSON（4 个）](#十三子模块-7grafana-仪表盘-json4-个)
- [十四、子模块 8：告警规则与 AlertManager 配置](#十四子模块-8告警规则与-alertmanager-配置)
- [十五、子模块 9：单元测试（8 个）](#十五子模块-9单元测试8-个)
- [十六、子模块 10：验证脚本 + 提测](#十六子模块-10验证脚本--提测)
- [十七、提交 Gitee 与 PR 描述](#十七提交-gitee-与-pr-描述)
- [十八、常见错误对照表](#十八常见错误对照表)
- [十九、避坑提示](#十九避坑提示)
- [二十、本阶段防呆自检清单](#二十本阶段防呆自检清单)

---

## 一、阶段目标

1. **四类核心指标全部落地**：HTTP 请求 QPS / 延迟（直方图）/ 错误率（按状态码）/ LLM Token 成本——全部用 `prometheus_client` 官方库手工埋点，标签含 `tenant_id` 方便分租户/租户视角分析。
2. **Prometheus 抓取 + AlertManager 告警闭环**：后端暴露 `/metrics` 端点（text/plain），Prometheus 5 秒一次拉取；4 条告警规则（5xx 错误率 / P99 延迟 / Token 成本突增 / 配额耗尽），AlertManager 触达 webhook 或静默日志。
3. **Grafana 三个仪表盘有数据**：HTTP 概览（QPS+P99+错误率三联）、Token 成本（按模型 / 按小时）、错误日志（按 trace_id 关联）。仪表盘 JSON 用 provisioning 自动加载，**容器起来就有，不用手动导入**。
5. **Loki 日志栈接入**：JSON 日志被 Promtail 从 docker daemon 抓取送 Loki，Grafana 同一界面查指标 + 查日志——SRE 三件套（指标 / 日志 / trace）的"指标 + 日志"两件凑齐，trace 用已有的 LangSmith（云端）。
6. **告警真触发**：人为制造 5xx，验证 AlertManager 在 5 分钟内发出告警——而不是只看"配置加载了"。

**验收标准**：

- 5 个容器全部健康（`docker compose -f docker/docker-compose.v3.yml ps` 全是 healthy / Up）；
- `curl http://127.0.0.1:9002/metrics` 返回 prometheus text 格式（含 `http_requests_total` / `http_request_duration_seconds` / `llm_tokens_total` / `llm_cost_cny_total`）；
- Prometheus UI（`:9090`）能查到 4 条 `up{job=...}` 全是 1；
- Grafana UI（`:3300`，admin/admin）3 个仪表盘都有曲线；
- 制造 5xx 后 5 分钟内 AlertManager UI（`:9093`）出现新告警；
- Loki 在 Grafana 里能查 JSON 日志；
- pytest 基线 83 → **91 passed**（新增 8 个单测）。

---

## 二、简历叙事（照写）

> 在 AI 私厨 v3.0 中落地 **CNCF 标准可观测三件套**：基于 `prometheus_client` 官方库为 FastAPI 手工埋点（HTTP QPS/P99/5xx/LLM 成本四类核心指标，标签含 `tenant_id`），**Prometheus 拉模式**采集 + **AlertManager** 告警（5xx 错误率 > 5% 持续 2 分钟、P99 > 3s 持续 5 分钟、Token 成本小时环比 ≥ 3x、配额耗尽），**Grafana 3 个仪表盘自动 provisioning**（HTTP 概览 / Token 成本 / 错误日志）。日志栈用 **Loki + Promtail** 从 docker daemon 抓取 JSON 日志到 Loki，Grafana 同界面查指标+查日志。共 5 个容器（合计 ~1 GB 内存），全 Docker Compose 项目一手测通。Trace 沿用 LangSmith 云端。pytest 基线 91 passed。

---

## 三、范围 & 与原方案差异（颜色标注）

| 项 | 原方案（v3.0 十阶段表） | 本阶段做法 | 标签 |
|---|---|---|---|
| 容器数 | 5 个（prometheus / grafana / alertmanager）| + loki / promtail = **5 个** | 🟡 微调：把日志栈也并进阶段 7（原方案 7 没要求日志栈，按"开篇确认范围"用户决策并入） |
| 指标类型 | QPS/延迟/错误率/token 成本 4 类 | **严格按规划**：4 类 | 🟢 新增 |
| Token 成本埋点 | LangChain 回调 → 写账本 → `/billing/stats` | 在 `token_billing.record()` 末尾加一行 `METRICS.cost.inc(...)`，**老接口不变** | 🟢 新增 |
| HTTP 中间件 | 不指定 | 在 TenantContextMiddleware **之后** 加 `MetricsMiddleware`——能拿到 `tenant_id` 标签；位置**不在最外层**（CORS 之外）以避免 OPTIONS 预检打两次 | 🟢 新增 |
| Prometheus 客户端 | 不指定 | `prometheus_client` 官方库 + 手工埋点（按"开篇确认范围"用户决策） | 🟢 新增 |
| 日志栈 | 不在范围 | Loki + Promtail（按"开篇确认范围"用户决策） | 🟢 新增 |
| Trace 链路 | 未提及 | **不新增容器**——沿用 LangSmith 云端（按"开篇确认范围"用户决策） | 🔵 修改：把"开篇时讨论的三选一"固化下来 |
| Grafana 仪表盘 | "三块仪表盘" | **4 块**（HTTP 概览 / Token 成本 / 错误日志 / 告警统计）——告警统计由 AlertManager 拉数据，可选 |
| 告警接收方 | 未指定 | Webhook URL（用户可改成企业微信 / 钉钉 / Slack）——本地开发用**静默文件**（写到 `./alert.log`），不响铃不打扰 | 🟢 新增 |

---

## 四、端口与基础设施

| 组件 | 端口 | 说明 |
|---|---|---|
| 后端（已有） | 9002 | 不动；新增 `/metrics` 端点暴露指标 |
| Prometheus | **9090** → 容器内 `9090` | 🟢 拉模式抓 `http://host.docker.internal:9002/metrics` |
| Grafana | **3300** → 容器内 `3000` | 🟢 默认账密 admin/admin（首次登录强制改） |
| AlertManager | **9093** → 容器内 `9093` | 🟢 默认本地无 webhook 接收方——写到 `./docker/alertmanager/data/alert.log` |
| Loki | **3100** → 容器内 `3100` | 🟢 Promtail 推数据 |
| Promtail | 不映射宿主机 | 🟢 容器内读取 `/var/lib/docker/containers` |
| PostgreSQL / Redis / PgBouncer / Neo4j / Milvus | 5433 / 6380 / 9432 / 7474+7687 / 19530 | 沿用 |

> 🟡 Promtail 必须挂载 docker socket `/var/run/docker.sock` 才能读所有容器的日志——这是 Loki 官方推荐方式。挂 socket 有潜在安全风险（容器可访问宿主机 docker daemon），但本项目是个人开发环境，且 Promtail 镜像由 Grafana 官方维护。
> 🟡 后端在宿主机运行（不是容器），Prometheus 抓取路径要写 `http://host.docker.internal:9002/metrics`——Docker Desktop 在 WSL2 后端会自动把 `host.docker.internal` 解到宿主 loopback。Linux 部署需用 `network_mode: "host"` 或加 `--add-host=host.docker.internal:host-gateway`。
> 🟡 内存：prometheus ~250MB + grafana ~250MB + alertmanager ~50MB + loki ~25MB + promtail ~50MB。机器吃紧时实验完 `docker compose -f docker/docker-compose.v3.yml stop prometheus grafana alertmanager loki promtail`（数据卷保留）——后端 `/metrics` 端点不影响业务。

```
本阶段之后可观测全景：

                                ┌─────────────────┐
                                │    Grafana UI   │  :3300 (统一查询界面)
                                └────┬───────┬────┘
                                     │       │
                          拉模式     │       │  LogQL（同一界面）
                                     ▼       ▼
                          ┌──────────┐    ┌──────────┐
                          │ Prometheus│    │   Loki   │  :3100
                          │   :9090   │    └────▲─────┘
                          └────▲─────┘         │ Promtail 推
                  HTTP 拉模式   │              │ （读 docker daemon）
                /metrics        │              │
                                │              │
                          ┌─────┴──────────────┴───┐
                          │     FastAPI 后端       │  :9002
                          │  MetricsMiddleware  ->     │
                          │  Counter / Histogram / Cost │
                          └────────────▲──────────────┘
                                       │
                                  AlertManager 告警
                                       │
                          ┌────────────┴───────────┐
                          │  ./docker/alertmanager/  │
                          │     data/alert.log      │  本地开发用文件接收
                          └────────────────────────┘
```

---

## 五、文件清单（创建 / 修改）

### 🟢 新建（19 个）

```
docker/prometheus/prometheus.yml                            # 抓取配置（后端 / Prometheus 自身 / AlertManager）
docker/prometheus/alerts.yml                              # 4 条告警规则（5xx / P99 / Token / Quota）
docker/alertmanager/alertmanager.yml                      # 接收方配置（默认写到 alert.log）
docker/loki/loki-config.yaml                              # Loki 单机模式
docker/promtail/promtail-config.yaml                       # Promtail 抓 docker daemon + 贴标签
docker/grafana/provisioning/datasources/datasources.yml    # Grafana 自动接 Prometheus + Loki 数据源
docker/grafana/provisioning/dashboards/dashboards.yml      # Grafana 自动加载仪表盘目录
docker/grafana/dashboards/http-overview.json              # 仪表盘 1：HTTP 概览（QPS+P99+错误率）
docker/grafana/dashboards/token-cost.json                 # 仪表盘 2：Token 成本（按模型 / 按小时）
docker/grafana/dashboards/error-logs.json                 # 仪表盘 3：错误日志（Loki+按 level）
docker/grafana/dashboards/alerts.json                      # 仪表盘 4（可选）：告警统计
app_my/core/metrics.py                                    # 4 类指标定义
app_my/middleware/metrics.py                              # HTTP 中间件（埋点 + 暴露 /metrics 端点）
scripts/verify_stage7.py                                  # 阶段 7 分步验证（容器/端点/告警）
scripts/stage7_check.ps1 / stage7_check.sh                # 提测脚本（双终端）
tests/unit/test_metrics.py                                # 8 个单测（Counter / Histogram / 端点 / 标签 / 告警规则）
```

> 🔴 **顺序要求（列表里前 5 个 yml 特别重要）**：`docker/prometheus/prometheus.yml`、`docker/prometheus/alerts.yml`、`docker/alertmanager/alertmanager.yml`、`docker/loki/loki-config.yaml`、`docker/promtail/promtail-config.yaml` 是**被容器直接挂载的文件**——必须**先写成"有内容的文件"，再起容器**。顺序反了，Docker Desktop 会建一个同名**目录**顶替，报 `not a directory`（详见 7.3 的顺序警告与第十八节专条）。

### 🔵 修改（5 个）

| 文件 | 改动 | 标签 |
|---|---|---|
| `docker/docker-compose.v3.yml` | 末尾新增 5 个 services + 4 个 volumes | 🔵 修改 |
| `app_my/core/config.py` | 末尾新增"可观测栈"配置节（4 个环境变量） | 🔵 修改 |
| `app_my/core/token_billing.py` | `record()` 末尾加一行 metrics 写入（不改原记账逻辑） | 🔵 修改 |
| `main.py` | 注册 `MetricsMiddleware` + 加 `/metrics` 端点 | 🔵 修改 |
| `pyproject.toml` | 新增 1 个 Python 依赖：`prometheus-client>=0.21.0` | 🔵 修改 |
| `.env.example` | 加 4 行可观测栈配置（默认值即可） | 🔵 修改 |

---

## 六、准备（切分支、基线）

> 🔴 **每一条命令都给出 PowerShell 5.1 + Git Bash 双版本**。Git Bash 用 POSIX 路径，PowerShell 用 Windows 路径，路径以 `.` 开头必须加 `&`。

### 步骤 1 —— 切分支

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
git checkout master
git pull origin master
git checkout -b feat/v3-stage7
```

**PowerShell 5.1：**
```powershell
cd F:\pycharm_aiprogram\ai_chief
git checkout master
git pull origin master
git checkout -b feat/v3-stage7
```

**预期**：`Switched to a new branch 'feat/v3-stage7'`（绿了 → 分支切好）。

> 🟡 上一阶段（阶段 6）的 PR 是否已合并到 master？**合并完再开新分支**；没合并的话先 `git checkout feat/v3-stage6 && git pull` 把 stage6 的最新提交拉下来再 merge 到 master。

### 步骤 2 —— 跑基线 pytest（确认 83 passed）

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe -m pytest -q
```

**PowerShell 5.1：**
```powershell
cd F:\pycharm_aiprogram\ai_chief
& ".venv3\Scripts\python.exe" -m pytest -q
```

**预期**：尾部出现 `83 passed in X.XXs`（绿了 → 阶段 6 收官状态确认；阶段 7 完成后变成 91 passed）。

### 步骤 3 —— 确认后端在跑

**Git Bash：**
```bash
curl -s http://127.0.0.1:9002/health
```

**PowerShell 5.1：**
```powershell
curl.exe -s http://127.0.0.1:9002/health
```

**预期**：`{"status":"ok"}`（绿了 → 后端在跑；如果没跑，按阶段 6 的 [阶段6_13.2_灰度开关_详细执行手册] 第 1.4 节重启）。

> 🟡 如果后端没跑，阶段 7 的步骤 6（注册中间件 + 起 5 个容器）会看不到 `/metrics` 端点数据。先起来。

---

## 七、子模块 1：5 个容器

> ⚠️ **本节的所有 `docker pull` / `docker compose up` 命令都先做"试拉"，拉不通就先排查源**。本机 daemon.json 的镜像源已知三个停服（ustc / 163 / baidu），走 Docker Desktop 代理 `http.docker.internal:3128` → 系统 Clash 7890。**可用源实测：quay.io 直连；Docker Hub 用 `docker.1panel.live`；`docker.m.daocloud.io` 是白名单制**。镜像源踩坑排查见 docker-cn-image-pull-diagnosis skill。
>
> 🔴 **动手顺序（先看这条，跳过必报错）**：本节的 `7.1 拉镜像` + `7.2 改 compose` 做完后，**不要在第七节起容器**。先跳到**第八节把 6 个配置文件全部写完（步骤 1~9）**，再回第八节**步骤 10 起容器**。原因见下一小节 7.3 的顺序警告。

### 7.1 试拉镜像（5 个）

**Git Bash：**
```bash
# Prometheus
docker pull docker.1panel.live/prom/prometheus:v2.55.1
# Grafana
docker pull docker.1panel.live/grafana/grafana:11.3.1
# Loki
docker pull docker.1panel.live/grafana/loki:3.4.0
# Promtail
docker pull docker.1panel.live/grafana/promtail:3.4.0
# AlertManager
docker pull docker.1panel.live/prom/alertmanager:v0.27.0
```

**PowerShell 5.1：** 命令完全一样。

**预期**：每个都打印 `v2.55.1: Pull complete`、最后 `Status: Downloaded newer image`。

> 🔴 **If 任何一个 `unauthorized` / `denied` / `manifest unknown`**：
> 1. 先看是不是拼错（`docker.1panel.live/` 别漏了斜杠）；
> 2. 用 `docker search` 试一下：`docker search prom/prometheus --limit 3`（查源头有哪些 tag）；
> 3. 实在拉不到换源：`docker.1panel.live/grafana/grafana:11.3.1` 拉不动 → `docker.m.daocloud.io/grafana/grafana:11.3.1`（在白名单）；
> 4. **仍未拉到的先停下来**，别硬撑——把错误截图给我，我帮你换镜像。

### 7.2 修改 `docker/docker-compose.v3.yml`

**在文件末尾新增 5 个 services 和 4 个 volumes**。注意：
- `image` 用上一步能拉通的镜像
- `extra_hosts: ["host.docker.internal:host-gateway"]` 让容器能访问宿主机后端（**这是 Prometheus 抓后端 metrics 的关键**）
- 端口映射按第四节"端口与基础设施"
- volumes 挂本地配置（ro）和持久化数据

**操作**：打开 `F:\pycharm_aiprogram\ai_chief\docker\docker-compose.v3.yml`，在 `services:` 块最后追加：

```yaml
  # ============ v3阶段7 可观测栈 ============

  prometheus:
    image: docker.1panel.live/prom/prometheus:v2.55.1
    container_name: ai_chief_prometheus
    restart: unless-stopped
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--storage.tsdb.retention.time=15d"
      - "--web.console.libraries=/usr/share/prometheus/console_libraries"
      - "--web.console.templates=/usr/share/prometheus/consoles"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro
      - ai_chief_promdata:/prometheus

  grafana:
    image: docker.1panel.live/grafana/grafana:11.3.1
    container_name: ai_chief_grafana
    restart: unless-stopped
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_INSTALL_PLUGINS: ""
    ports:
      - "3300:3000"
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
      - ai_chief_grafanadata:/var/lib/grafana

  alertmanager:
    image: docker.1panel.live/prom/alertmanager:v0.27.0
    container_name: ai_chief_alertmanager
    restart: unless-stopped
    command:
      - "--config.file=/etc/alertmanager/alertmanager.yml"
      - "--storage.path=/alertmanager"
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - ai_chief_alertmgrdata:/alertmanager

  loki:
    image: docker.1panel.live/grafana/loki:3.4.0
    container_name: ai_chief_loki
    restart: unless-stopped
    command: -config.file=/etc/loki/loki-config.yaml
    ports:
      - "3100:3100"
    volumes:
      - ./loki/loki-config.yaml:/etc/loki/loki-config.yaml:ro
      - ai_chief_lokidata:/loki

  promtail:
    image: docker.1panel.live/grafana/promtail:3.4.0
    container_name: ai_chief_promtail
    restart: unless-stopped
    command: -config.file=/etc/promtail/promtail-config.yaml
    volumes:
      - ./promtail/promtail-config.yaml:/etc/promtail/promtail-config.yaml:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    depends_on:
      - loki
```

**在文件末尾 `volumes:` 块追加 4 个**：

```yaml
  ai_chief_promdata:        # v3阶段7 新增
  ai_chief_grafanadata:     # v3阶段7 新增
  ai_chief_alertmgrdata:    # v3阶段7 新增
  ai_chief_lokidata:        # v3阶段7 新增
```

**验证**（双终端同一条命令）：

```bash
docker compose -f docker/docker-compose.v3.yml config --services | grep -E "prometheus|grafana|alert|loki|promtail"
```

**PowerShell 5.1：**

```powershell
docker compose -f docker/docker-compose.v3.yml config --services | Select-String -Pattern "prometheus|grafana|alert|loki|promtail"
```

**预期**：5 行（prometheus / grafana / alertmanager / loki / promtail）。

> 🟡 如果上面命令报"no such file" → 你不在项目根目录；`cd F:\pycharm_aiprogram\ai_chief` 或 `cd /f/pycharm_aiprogram/ai_chief`。
> 🟡 如果 `docker compose` 报版本错误：把命令换成 `docker-compose`（带连字符，老版本）。

### 7.3 起容器 —— 🔴 不在本节做，见第八节步骤 10

> 🔴 **为什么不能在这里起容器（跳过的必报错）**
>
> 这 5 个服务的 compose 定义里，挂载的是**宿主机上的单个配置文件**，而不是目录：
>
> ```yaml
> volumes:
>   - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
>   - ./prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro      # ← 这类"文件对文件"的挂载
> ```
>
> **这些文件必须已经存在、且有内容，容器才起得来。** 如果你在文件还没写的时候就执行 `up -d`，Docker Desktop 不会告诉你"文件找不到"，而是**在宿主机上自动建一个同名目录**顶上去，然后试图把"目录"挂到容器的"文件"路径上 —— 直接报：
>
> ```
> Error response from daemon: failed to create task for container: ...
> error mounting "/run/desktop/mnt/host/f/pycharm_aiprogram/ai_chief/docker/prometheus/alerts.yml"
> to rootfs at "/etc/prometheus/alerts.yml": ... flags=MS_BIND|MS_REC: not a directory:
> Are you trying to mount a directory onto a file (or vice-versa)?
> Check if the specified host path exists and is the expected type
> ```
>
> **正确顺序**：
> `7.1 拉镜像` → `7.2 改 compose` → **跳到第八节，做完步骤 1~9（6 个配置文件写全）** → 回**第八节步骤 10 起容器** → 步骤 11 看状态 → 步骤 12 验证端口。

> 🟡 **如果已经先起了容器、已经报了这个错**：别慌，也没弄坏东西。按第十八节「`not a directory` 专条」的三步清理（删掉 Docker 误建的目录 → 把配置文件写成有内容的文件 → 再起容器）即可。

---

## 八、子模块 2：6 个配置文件

> ⚠️ **本节所有路径都是相对项目根**（`F:\pycharm_aiprogram\ai_chief\docker\xxx\yyy`）。PowerShell 创建目录用 `New-Item -ItemType Directory -Force`，Git Bash 用 `mkdir -p`。

### 步骤 1 —— 建子目录

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
mkdir -p docker/prometheus docker/alertmanager docker/loki docker/promtail \
         docker/grafana/provisioning/datasources \
         docker/grafana/provisioning/dashboards \
         docker/grafana/dashboards
```

**PowerShell 5.1：**
```powershell
cd F:\pycharm_aiprogram\ai_chief
New-Item -ItemType Directory -Force -Path docker\prometheus, docker\alertmanager, docker\loki, docker\promtail, docker\grafana\provisioning\datasources, docker\grafana\provisioning\dashboards, docker\grafana\dashboards
```

**预期**：双终端都返回类似 `Directory: ...` 或静默（PowerShell 路径里有反斜杠但这是英文 OK）。

### 步骤 2 —— `docker/prometheus/prometheus.yml`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\prometheus\prometheus.yml`

```yaml
# 阶段 7：Prometheus 抓取配置
# 抓三个目标：后端 /metrics、Prometheus 自身（看自己的指标）、AlertManager
global:
  scrape_interval: 5s          # 全局拉取间隔（个人项目用短间隔方便实时看）
  evaluation_interval: 5s      # 告警规则评估间隔
  scrape_timeout: 3s

rule_files:
  - "alerts.yml"               # 告警规则单独维护

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  # 后端 /metrics 端点（核心数据源）
  - job_name: "ai_chief_backend"
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:9002"]
        labels:
          app: ai_chief
          env: dev

  # Prometheus 自身（看拉取 / TSDB / 自身资源指标）
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  # AlertManager 自身
  - job_name: "alertmanager"
    static_configs:
      - targets: ["alertmanager:9093"]
```

**验证**（双终端同一条）：

```bash
docker exec ai_chief_prometheus promtool check config /etc/prometheus/prometheus.yml
```

**预期**：`SUCCESS`。如果不成功，先回卷再来确定 YAML 没缩进错。

### 步骤 3 —— `docker/prometheus/alerts.yml`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\prometheus\alerts.yml`

```yaml
# 阶段 7：告警规则（4 条）
# 命名约定：<level>_<service>_<signal>。level 与 AlertManager 路由对应（infra=warnings、warnings=debug）
groups:
  - name: ai_chief_alerts
    interval: 30s              # 评估间隔（比全局的 5s 长——告警不需要秒级判）
    rules:

      # 1) 5xx 错误率 > 5% 持续 2 分钟
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5xx"}[5m])) /
          sum(rate(http_requests_total[5m])) > 0.05
        for: 2m
        labels:
          severity: warning
          service: ai_chief
        annotations:
          summary: "5xx 错误率超过 5%（当前 {{ $value | $labels.value }}）"
          description: "{{ $labels.path }} 路径 5xx 错误率 {{ $value | humanizePercentage }}，请查日志。"

      # 2) P99 延迟 > 3 秒持续 5 分钟
      - alert: HighP99Latency
        expr: |
          histogram_quantile(0.99, sum by (path) (rate(http_request_duration_seconds_bucket[5m]))) > 3
        for: 5m
        labels:
          severity: warning
          service: ai_chief
        annotations:
          summary: "P99 延迟超过 3s（{{ $labels.path }}：{{ $value }}s）"
          description: "请求路径 {{ $labels.path }} 的 P99 延迟为 {{ $value | humanizeDuration }}，持续 5 分钟。"

      # 3) Token 成本小时环比 ≥ 3 倍
      - alert: TokenCostSpike
        expr: |
          (sum(rate(llm_cost_cny_total[1h])) * 3600) /
          (sum(rate(llm_cost_cny_total[1h] offset 1h)) * 3600 + 1) > 3
        for: 5m
        labels:
          severity: warning
          service: ai_chief
        annotations:
          summary: "Token 成本小时环比突增 3x"
          description: "当前 1 小时 LLM 成本 = 前 1 小时 LLM 成本的 3 倍以上，可能 LLM 路由异常或被刷。"

      # 4) 配额耗尽（与阶段 4 QuotaMiddleware 联动）
      - alert: QuotaExhausted
        expr: llm_quota_used_ratio > 0.95
        for: 1m
        labels:
          severity: critical
          service: ai_chief
        annotations:
          summary: "租户 {{ $labels.tenant_id }} LLM 配额耗尽 95%"
          description: "租户 {{ $labels.tenant_id }} 已用 95% LLM 配额，请通知租户或临时上调限额。"
```

**验证**：

```bash
docker exec ai_chief_prometheus promtool check rules /etc/prometheus/alerts.yml
```

**预期**：`SUCCESS / rules.yml`。

> 🟡 第 4 条用到的 `llm_quota_used_ratio` 指标需要 `QuotaMiddleware` 加埋点——见第十一节步骤 3。
> 🟡 `for: 2m` 意思是"规则触达后持续 2 分钟才告警"——避免抖动误报；测试时为了快速验证可改成 `for: 30s`，验证完改回原值。

### 步骤 4 —— `docker/alertmanager/alertmanager.yml`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\alertmanager\alertmanager.yml`

```yaml
# 阶段 7：AlertManager 配置
# 本地开发：默认静默（不响铃不打扰）；告警写入到 alert.log 文件，给业务人员看
route:
  group_by: ["alertname", "service"]
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 3h
  receiver: "local-file"

receivers:
  - name: "local-file"
    # webhook_configs 在本地开发里发空列表——AlertManager 会写到 AM 自身的日志（alert.log）
    webhook_configs: []
```

> 🟡 真实接入企业微信 / 钉钉 / Slack 时，把 `webhook_configs` 改成：
> ```yaml
> webhook_configs:
>   - url: "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
>     send_resolved: true
> ```
> 模板 / @ 人的格式各家不同，到时查官方文档。本项目交付不动。

### 步骤 5 —— `docker/loki/loki-config.yaml`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\loki\loki-config.yaml`

```yaml
# 阶段 7：Loki 单机模式（Loki 3.4）
auth_enabled: false

server:
  http_listen_port: 3100

common:
  instance_addr: 127.0.0.1          # 单机模式：副本之间互相找的地址，填本机
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem      # 🔴 必须有这一行！缺了会报 unrecognized `object_store` type ``
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: 168h         # 日志保留 7 天（168h = 7×24；写成 7d 在部分版本不被解析）
  ingestion_rate_mb: 16          # 单租户限制 16MB/s
  ingestion_burst_size_mb: 24
  allow_structured_metadata: true

compactor:
  working_directory: /loki/compactor
  retention_enabled: true            # 开启保留期清理（配合上面的 retention_period）
  delete_request_store: filesystem   # 🔴 开启 retention 后必须指定"删数据用哪个存储"

ruler:
  storage:
    type: local
    local:
      directory: /loki/rules
  rule_path: /loki/rules-temp
  ring:
    kvstore:
      store: inmemory
```

> 🔴 **本步骤为什么容易踩坑（已实测）**：`schema_config.configs` 里 **`store` 和 `object_store` 是两个不同的东西**——
> - `store: tsdb` 指"**索引**用什么存"（Loki 3.x 用 tsdb）
> - `object_store: filesystem` 指"**日志正文（chunk）**用什么存"
>
> 少写 `object_store`，Loki 启动时报 `unrecognized \`object_store\` type \`\``，容器无限 `Restarting`（配置校验没过，反复重启）。用 Loki 自带校验提前抓：`docker compose -f docker/docker-compose.v3.yml run --rm --no-deps loki -config.file=/etc/loki/loki-config.yaml -verify-config`，出现 `msg="config is valid"` 才算过。

### 步骤 6 —— `docker/promtail/promtail-config.yaml`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\promtail\promtail-config.yaml`

```yaml
# 阶段 7：Promtail 抓 docker daemon JSON 日志推送到 Loki
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    static_configs:
      - targets: [localhost]
        labels:
          job: docker
          __path__: /var/lib/docker/containers/*/*log
    pipeline_stages:
      # docker JSON 日志 → JSON 解析 → 提取 label（container_name / level / logger / msg）
      - docker: {}
      - match:
          selector: '{job="docker"}'
          stages:
            - json:
                expressions:
                  level: level
                  logger: logger
                  msg: msg
                  trace_id: trace_id
            - labels:
                level:
                logger:
                trace_id:
```

### 步骤 7 —— `docker/grafana/provisioning/datasources/datasources.yml`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\grafana\provisioning\datasources\datasources.yml`

```yaml
# 阶段 7：Grafana 自动数据源
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
```

### 步骤 8 —— `docker/grafana/provisioning/dashboards/dashboards.yml`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\grafana\provisioning\dashboards\dashboards.yml`

```yaml
# 阶段 7：Grafana 自动加载仪表盘目录
apiVersion: 1
providers:
  - name: ai_chief_dashboards
    orgId: 1
    folder: AI Chief
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

### 步骤 9 —— 4 个仪表盘 JSON

**新建 4 个仪表盘 JSON**（每个都对应一个 .json 文件）。

> ✅ **4 个仪表盘 JSON 已直接落盘**到 `F:\pycharm_aiprogram\ai_chief\docker\grafana\dashboards\`（`http-overview.json` / `token-cost.json` / `error-logs.json` / `alerts.json`），**你不需要手抄**。完整内容见本手册 **第十三节**（逐文件给出），每个字段的含义解释见《说明手册》**附录 B**。本节先给出每个面板的 PromQL/数据源说明，让你理解每个面板查什么。

**`docker/grafana/dashboards/http-overview.json`**（HTTP 概览）

| 面板 | 数据源 | 查询 | 含义 |
|---|---|---|---|
| QPS by path | Prometheus | `sum by (path) (rate(http_requests_total[1m]))` | 每秒请求数按路由拆 |
| P50 / P99 by path (ms) | Prometheus | `histogram_quantile(0.50, sum by (path, le) (rate(http_request_duration_seconds_bucket[1m]))) * 1000` | 两个分位延迟（毫秒） |
| 5xx 错误率 | Prometheus | `sum(rate(http_requests_total{status=~"5xx"}[5m])) / sum(rate(http_requests_total[5m]))` | 5xx 占总请求比例 |
| 4xx 错误率 by tenant | Prometheus | `sum by (tenant_id) (rate(http_requests_total{status=~"4xx"}[5m])) / sum by (tenant_id) (rate(http_requests_total[5m]))` | 按租户看 4xx 比例 |

**`docker/grafana/dashboards/token-cost.json`**（Token 成本）

| 面板 | 数据源 | 查询 | 含义 |
|---|---|---|---|
| Tokens / min by direction | Prometheus | `sum by (direction) (rate(llm_tokens_total[5m])) * 60` | input / output 每分钟 token 数 |
| Cost (CNY/h) by model | Prometheus | `sum by (model) (rate(llm_cost_cny_total[5m])) * 3600` | 每个模型每小时费用（元） |
| Tokens / min by model | Prometheus | `sum by (model) (rate(llm_tokens_total[5m])) * 60` | 每个模型每分钟 token 数 |
| 配额使用率 by tenant | Prometheus | `llm_quota_used_ratio` | 各租户 LLM 配额使用率（0~1，>0.95 触发告警） |

> 🔴 **修正**：早期草稿写过 `sum by (model) (rate(http_requests_total{path="/chat/stream"}[5m]))`——`http_requests_total` **没有 `model` 标签**（它的标签只有 `method / status / tenant_id / path`），`sum by (model)` 会返回空。已改为按 `llm_tokens_total{model}` 统计。

**`docker/grafana/dashboards/error-logs.json`**（错误日志）

| 面板 | 数据源 | 查询 | 含义 |
|---|---|---|---|
| ERROR 日志 | Loki | `{job="docker"} \|= "ERROR"` | ERROR 级别日志（含 trace_id） |
| WARN 日志 | Loki | `{job="docker"} \|~ "(?i)WARN"` | WARNING 级别日志 |

> 🟡 `job="docker"` 是 Promtail 抓 docker 容器日志时打的标签（见 `promtail-config.yaml` 的 `scrape_configs.job_name: docker`）。用 `\|=` 做**文本包含**匹配，不依赖日志 JSON 的具体字段格式，最稳。

> ✅ 上述 4 个 JSON 文件**已经落盘在 `docker/grafana/dashboards/`**，不必再手抄；完整内容见本手册 **第十三节**（逐文件给出），字段含义解释见《说明手册》**附录 B**。

### 步骤 10 —— 起 5 个容器（配置齐全后才起）

> 🔴 **必须先做完步骤 1~9 再执行这一步**：容器挂载的是这几个配置文件本身，文件不存在时 Docker Desktop 会建目录顶替，报 `not a directory`（详见 7.3 的顺序警告）。

**Git Bash 与 PowerShell 5.1 命令完全相同：**

```bash
cd /f/pycharm_aiprogram/ai_chief
# Git Bash
docker compose -f docker/docker-compose.v3.yml up -d prometheus grafana alertmanager loki promtail
```
```powershell
# PowerShell 5.1
cd F:\pycharm_aiprogram\ai_chief
docker compose -f docker/docker-compose.v3.yml up -d prometheus grafana alertmanager loki promtail
```

**预期**：5 行 `Container ai_chief_xxx Started`。

> 🟡 **如果是"第二次起"（容器已存在）**，`up -d` 可能只提示 `Running`；此时用 `restart` 强制重新加载配置：
> ```bash
> docker compose -f docker/docker-compose.v3.yml restart prometheus grafana alertmanager loki promtail
> ```
> **预期**：5 行 `... Restarted`。

### 步骤 11 —— 看容器状态

**双终端同一条命令**：

```bash
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
```

**预期**：`State` 全是 `Up`（healthcheck 没配，应该是 Up 而不是 healthy——不是错）。

> 🔴 **如果出现 `Restarting` 或 `Exited (1)`**：说明某个配置文件内容有问题（空的、或 YAML 缩进错）。用日志定位到底是谁：
> ```bash
> docker compose -f docker/docker-compose.v3.yml logs --tail=30 <服务名>
> ```
> 常见对应：`alertmanager` 空文件 → `parse error`；`loki` / `promtail` 空文件 → `field X not found`。

### 步骤 12 —— 验证端口在听

**Git Bash：**
```bash
# Prometheus UI
curl -s http://127.0.0.1:9090/-/ready
# Grafana 健康（Grafana 11 端点是 /api/health，没有 /api/healthz——写错会返回 401）
curl -s http://127.0.0.1:3300/api/health
# AlertManager 健康
curl -s http://127.0.0.1:9093/-/ready
# Loki 就绪
curl -s http://127.0.0.1:3100/ready
```

**PowerShell 5.1：**
```powershell
curl.exe -s http://127.0.0.1:9090/-/ready
curl.exe -s http://127.0.0.1:3300/api/health
curl.exe -s http://127.0.0.1:9093/-/ready
curl.exe -s http://127.0.0.1:3100/ready
```

**预期**：分别是
- Prometheus → `Prometheus Server is Ready.`
- Grafana → `{"database":"ok","version":"11.3.1",...}`（**只要看到 `"database": "ok"` 就是健康**）
- AlertManager → `OK`
- Loki → `ready`（**注意**：Loki 刚启动的 15~20 秒内会返回 `Ingester not ready: waiting for 15s after being ready`，这是**正常现象**，等 20 秒重试即可）

如果任意一个不返回，再多等 10 秒重试（Prometheus 第一次启动要初始化 TSDB）；30 秒后还不 OK → 看下面报错对照表。

> 🟡 **Promtail 没有对外端口**（它只负责采集，不提供 UI），所以这里不检查它。它的健康状态在步骤 11 的 `ps` 里看——只要 `Up` 且日志里没有 `level=error` 就正常。

### 步骤 13 —— 验证 Prometheus 已加载规则

**Git Bash：**
```bash
curl -s http://127.0.0.1:9090/api/v1/rules | python -m json.tool | head -30
```

**PowerShell 5.1：**
```powershell
curl.exe -s http://127.0.0.1:9090/api/v1/rules
```

**预期**：JSON 里能看到 4 条规则（`HighErrorRate` / `HighP99Latency` / `TokenCostSpike` / `QuotaExhausted`）。

---

## 九、子模块 3：核心指标定义 `app_my/core/metrics.py`

> 🔴 **本节的代码必须照搬，参数名不要改**——Prometheus 指标的 label key 在仪表盘 JSON 和告警规则里被引用，改了名字仪表盘全空。

### 步骤 1 —— 新建文件

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\app_my\core\metrics.py`

```python
"""
阶段 7：Prometheus 指标定义中心。
全部用 prometheus_client 官方库手工定义——
- 中间件按 HTTP 请求 / 响应埋点（埋点 1/2）
- token_billing.record() 末尾调用 cost_inc / tokens_inc（埋点 3/4）
- QuotaMiddleware 调用 quota_set（埋点 5）
"""
from prometheus_client import Counter, Histogram, Gauge, REGISTRY as _PROM_REGISTRY


# ===== 埋点 1：HTTP 请求 QPS =====
# label：method / status（200/4xx/5xx 二级）/ tenant_id（没登录就是 "anon"）/ path（用 FastAPI route pattern 不用真实 URL，避免高基数）
HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP 请求总数（按 method / status / tenant_id / path 拆）",
    labelnames=("method", "status", "tenant_id", "path"),
)

# ===== 埋点 2：HTTP 请求延迟（直方图）=====
# 默认 buckets 适合 web 请求（0.005s ~ 10s）。直方图 → 自动产生 histogram_quantile() 指标
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求延迟（秒）",
    labelnames=("method", "tenant_id", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ===== 埋点 3：LLM token 消耗 =====
# label：model（flash/plus/max/...）/ direction（input/output）
LLM_TOKENS = Counter(
    "llm_tokens_total",
    "LLM token 消耗总数（按 model / direction 拆）",
    labelnames=("model", "direction"),
)

# ===== 埋点 4：LLM 成本（元）=====
# label：model（flash/plus/max/...）
LLM_COST = Counter(
    "llm_cost_cny_total",
    "LLM 调用成本累计（元）",
    labelnames=("model",),
)

# ===== 埋点 5：租户 LLM 配额使用率 =====
# Gauge：当前瞬时值。0=0%，1=100%
LLM_QUOTA_RATIO = Gauge(
    "llm_quota_used_ratio",
    "租户 LLM 配额使用率（0~1）",
    labelnames=("tenant_id",),
)


def http_inc(method: str, path: str, status_code: int, tenant_id: str = "anon") -> None:
    """HTTP 埋点：QPS Counter + Duration Histogram 一次性记录。
    用一个 helper 把 4 个 label 的拼装集中起来——避免中间件里重复 + 拼错。"""
    # 状态码归类：2xx / 4xx / 5xx（高基数 label 会爆 Prometheus）
    status_bucket = (
        "2xx" if 200 <= status_code < 300
        else "4xx" if 400 <= status_code < 500
        else "5xx" if 500 <= status_code < 600
        else str(status_code)
    )
    tenant_label = str(tenant_id) if tenant_id is not None else "anon"
    HTTP_REQUESTS.labels(method=method, status=status_bucket, tenant_id=tenant_label, path=path).inc()
    # 延迟由调用方传入——histogram 在中间件里 observe


def tokens_inc(model: str, direction: str, amount: int) -> None:
    """Token 埋点：input / output 增量。"""
    LLM_TOKENS.labels(model=model or "unknown", direction=direction).inc(amount)


def cost_inc(model: str, cny: float) -> None:
    """成本埋点：累计（元）。"""
    LLM_COST.labels(model=model or "unknown").inc(cny)


def quota_set(tenant_id: int, ratio: float) -> None:
    """配额埋点：设置租户当前使用率。"""
    LLM_QUOTA_RATIO.labels(tenant_id=str(tenant_id)).set(ratio)
```

### 步骤 2 —— 加 Python 依赖

打开 `F:\pycharm_aiprogram\ai_chief\pyproject.toml`，在 `dependencies` 列表末尾加一行：

```toml
    "prometheus-client>=0.21.0",              # 修订：v3 阶段 7 新增
```

**验证**（双终端同一条命令）：

```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe -c "import prometheus_client; print('prometheus_client', prometheus_client.__version__)"
```

**PowerShell 5.1：**

```powershell
& ".venv3\Scripts\python.exe" -c "import prometheus_client; print('prometheus_client', prometheus_client.__version__)"
```

**预期**：`prometheus_client 0.21.x` 或更新。如果 `ModuleNotFoundError`，先用 `uv pip install prometheus-client` 装一下。

### 步骤 3 —— 验证指标定义本身

```bash
.venv3/Scripts/python.exe -c "
from app_my.core.metrics import HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO
print('all metrics defined:', [m._name for m in [HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO]])
"
```

**PowerShell 5.1：** 同样用 `&` 调用。

**预期**：打印 `['http_requests_total', 'http_request_duration_seconds', 'llm_tokens_total', 'llm_cost_cny_total', 'llm_quota_used_ratio']`。

---

## 十、子模块 4：HTTP 埋点中间件 `app_my/middleware/metrics.py`

### 步骤 1 —— 新建文件

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\app_my\middleware\metrics.py`

```python
"""
阶段 7：HTTP 埋点中间件（同时实现 /metrics 端点）。
🔴 挂载位置：add_middleware 要写在 AuthMiddleware 之后 —— 后 add 的在更外层，
   这样它在 Auth 之外，/metrics 才不会被 Auth 拦成 401（详见第十二节）。
- /metrics 端点就在这里实现：dispatch 命中该路径直接返回指标文本，不往下走
- 拿 tenant_id 打标签：tenant_id 由内层 TenantContextMiddleware 写入 request.state；
  Starlette 的 request.state 存在 scope["state"] 中、整条中间件链共享 —— 所以在外层也读得到
- 不在 CORS 之外（不做出最外层）：避免 OPTIONS 预检请求被记两次
- 在 Auth / 限流之外：被 401 / 429 拒绝的请求也计入 → 错误率面板能看到鉴权与限流拒绝
"""
import time

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.core.metrics import http_inc


class PrometheusMiddleware(BaseHTTPMiddleware):
    """HTTP 埋点中间件 + 暴露 /metrics 端点"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # /metrics 端点不参与计数（被自身反复拉会污染指标）
        if path == settings.PROMETHEUS_METRICS_PATH:
            return PlainTextResponse(_build_metrics_text(), media_type=CONTENT_TYPE_LATEST)

        # 路径模式归一：用 FastAPI 路由 pattern 代替真实 URL，避免高基数
        route = request.scope.get("route")
        path_label = getattr(route, "path", path) if route else path

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            # 路由抛异常：500 一律计入
            cost_ms = (time.perf_counter() - start) * 1000
            _handle_inc(request, path_label, 500, cost_ms)
            raise

        cost_ms = (time.perf_counter() - start) * 1000
        _handle_inc(request, path_label, response.status_code, cost_ms)
        return response


def _handle_inc(request: Request, path_label: str, status_code: int, cost_ms: float) -> None:
    """统一埋点：QPS Counter + Duration Histogram"""
    from app_my.core.metrics import HTTP_DURATION  # 避免循环引用
    tenant_id = getattr(request.state, "tenant_id", None)
    http_inc(method=request.method, path=path_label, status_code=status_code, tenant_id=tenant_id)
    HTTP_DURATION.labels(method=request.method, path=path_label, tenant_id=str(tenant_id or "anon")).observe(cost_ms / 1000)


def _build_metrics_text() -> bytes:
    """生成 Prometheus text 导出格式"""
    try:
        return generate_latest()
    except Exception as exc:
        logger.warning("metrics: generate_latest 失败: %s", exc)
        return b""
```

### 步骤 2 —— 在 `app_my/core/config.py` 末尾加配置

打开 `F:\pycharm_aiprogram\ai_chief\app_my\core\config.py`，在 `# LangSmith（可选）` 段下面、`# CORS` 段前面加：

```python
    # =========================================================
    # 可观测栈（v3 阶段 7 新增）
    # =========================================================
    PROMETHEUS_METRICS_PATH: str = "/metrics"      # 后端暴露的指标路径
    PROMETHEUS_MULTIPROC_DIR: str = ""            # 多进程模式预留（gunicorn -w > 1 时用）
    LOKI_URL: str = "http://localhost:3100"        # Loki 入口（前端调试查日志用）
```

### 步骤 3 —— 在 `.env.example` 末尾加 3 行（`.env` 也加）：

打开 `F:\pycharm_aiprogram\ai_chief\.env.example`，末尾加：

```
# 阶段 7：可观测栈
PROMETHEUS_METRICS_PATH=/metrics
LOKI_URL=http://localhost:3100
PROMETHEUS_MULTIPROC_DIR=
```

打开 `F:\pycharm_aiprogram\ai_chief\.env`，末尾加同样的 3 行。

**验证配置加载**（双终端同一条命令）：

```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe -c "from app_my.core.config import settings; print('metrics_path=', settings.PROMETHEUS_METRICS_PATH); print('loki=', settings.LOKI_URL)"
```

**PowerShell 5.1：** 用 `&`。

**预期**：`metrics_path= /metrics`、`loki= http://localhost:3100`。

---

## 十一、子模块 5：Token 成本指标接入

> 🟡 这一节只改一处：在 `app_my/core/token_billing.py` 的 `record()` 函数末尾加 2 行 metrics 调用。**不改原记账、不改价目表、不改 LangChain 回调**。

### 步骤 1 —— 改 `record()`

打开 `F:\pycharm_aiprogram\ai_chief\app_my\core\token_billing.py`，找到 `record(model, input_tokens, output_tokens, ok=True)` 函数，在 `return None` 之前（即函数末尾、所有 try 之外）加：

```python
    # 阶段 7：metrics 上报（不影响原记账逻辑）
    try:
        from app_my.core.metrics import tokens_inc, cost_inc
        if ok:
            tokens_inc(model, "input", int(input_tokens or 0))
            tokens_inc(model, "output", int(output_tokens or 0))
            cost = estimate_cost_cny(model, int(input_tokens or 0), int(output_tokens or 0))
            if cost is not None:
                cost_inc(model, cost)
    except Exception:
        pass    # metrics 挂了不影响原记账（与原 fail-open 哲学一致）
```

**完整改后的 `record()` 函数**（请参考原文件并按上面 patch 改）：

```python
def record(model: str, input_tokens: int, output_tokens: int, ok: bool = True) -> None:
    """
    记一笔账（幂等追加，不是覆盖）。

    双写策略：
      - 进程内字典：永远写（没有外部依赖，测试也用它）
      - Redis：尽力写（HINCRBY 原子自增），写失败只记日志
    """
    if not model:
        model = "unknown"

    # ① 进程内账本
    book = _memory_book.setdefault(
        model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0}
    )
    if ok:
        book["calls"] += 1
        book["input_tokens"] += int(input_tokens or 0)
        book["output_tokens"] += int(output_tokens or 0)
    else:
        book["errors"] += 1

    # ② Redis 账本（best-effort：挂了不影响业务）
    try:
        from app_my.core.redis_client import get_redis, redis_available

        if redis_available():
            r = get_redis()
            key = f"{_REDIS_PREFIX}:{model}"
            if ok:
                r.hincrby(key, "calls", 1)
                r.hincrby(key, "input_tokens", int(input_tokens or 0))
                r.hincrby(key, "output_tokens", int(output_tokens or 0))
            else:
                r.hincrby(key, "errors", 1)
    except Exception as exc:                      # Redis 掉线 / 连接拒绝等
        logger.warning("billing: Redis 记账失败（不影响业务）: %s", exc)

    # ③ 阶段 7：metrics 上报（不影响原记账逻辑；失败则吞掉）
    try:
        from app_my.core.metrics import tokens_inc, cost_inc
        if ok:
            tokens_inc(model, "input", int(input_tokens or 0))
            tokens_inc(model, "output", int(output_tokens or 0))
            cost = estimate_cost_cny(model, int(input_tokens or 0), int(output_tokens or 0))
            if cost is not None:
                cost_inc(model, cost)
    except Exception:
        pass
```

### 步骤 2 —— 改 `app_my/middleware/quota.py` 加 1 行 quota 埋点

> 🔴 **本节已经过实测核对**：`app_my/core/quota.py` 真实函数是 `check_quota(tenant_id, plan, metric) -> (is_allowed, used, limit)`（已在第十一节凭一手代码核对），**不是 `get_quota_status()`**——后者是我一开始（手册）编的，已删。

打开 `F:\pycharm_aiprogram\ai_chief\app_my\middleware\quota.py`，在 `dispatch` 方法里 `ok, used, cap = check_quota(...)` 这一行**后面**加：

```python
                # 阶段 7：上报当前租户配额使用率（用于告警；不影响配额逻辑）
                try:
                    from app_my.core.metrics import quota_set
                    if cap and cap > 0:
                        quota_set(tenant_id, used / cap)
                except Exception:
                    pass
```

**改完完整片段**（替换原来 `check_quota` 那一段）：

```python
class QuotaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in QUOTA_PATHS:
            tenant_id = getattr(request.state, "tenant_id", None)
            plan = getattr(request.state, "tenant_plan", "free")

            if tenant_id is not None:
                ok_quota, used, cap = check_quota(tenant_id, plan, "chat_daily")   # 🟢 阶段 7：原变量名 ok 改 ok_quota（不然遮住外层 ok=True）
                # 阶段 7：上报当前租户配额使用率（用于告警；不影响配额逻辑）
                try:
                    from app_my.core.metrics import quota_set
                    if cap and cap > 0:
                        quota_set(tenant_id, used / cap)
                except Exception:
                    pass
                if not ok_quota:
                    logger.warning("配额超限 tenant=%s used=%d limit=%d", tenant_id, used, cap)
                    return JSONResponse(
                        {
                            "detail": "租户对话配额已用完",
                            "metric": "chat_daily",
                            "used": used,
                            "limit": cap,
                            "upgrade_hint": "升级到 pro / enterprise 可提高配额",
                        },
                        status_code=429,
                        headers={"Retry-After": "86400"},
                    )
```

> 🟡 **关键点**：
> 1. 用 `check_quota()` 拿到 `(is_allowed, used, cap)`，第三个返回值是 `cap`（配额上限）——手动算 `used / cap` 得到使用率 0~1
> 2. `if cap and cap > 0` 防除零——`cap=0` 表示未配置，**未配置 = 不限**，报 0/0 是 NaN，Prometheus 收不下
> 3. `try/except` 包住——metrics 挂不影响配额逻辑（配额是主链路，metrics 是观察）
> 4. **注意变量名**——原代码用 `ok` 是 dict key 的同名变量，**阶段 7 这里改成 `ok_quota`** 否则会报 `SyntaxError`

### 步骤 3 —— 验证 token_billing

```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe -c "
from app_my.core.token_billing import record, get_billing_stats
record('qwen3.7-flash', 100, 50)
record('qwen3.7-plus', 200, 100)
print(get_billing_stats())
"
```

**PowerShell 5.1：** 用 `&`。

**预期**：返回的 dict 里 `models.qwen3.7-flash.calls=1`、`models.qwen3.7-plus.calls=1`。

---

## 十二、子模块 6：main.py 接入 + /metrics 端点

### 步骤 1 —— 改 `main.py`

打开 `F:\pycharm_aiprogram\ai_chief\main.py`，**做两处小改**：

**(a) import 区段**（在 `# ===== 中间件 =====` 之前）加：

```python
from app_my.middleware.metrics import MetricsMiddleware
```

**(b) 中间件挂载位置**（🔴 **必须在 `AuthMiddleware` 之后加**，即"外层于鉴权"）加：

```python
app.add_middleware(MetricsMiddleware)                # 阶段 7：HTTP 埋点 + /metrics 端点（必须在 Auth 之外）
```

改后的中间件栈顺序（从外到内，**最后 add 的在最外层**）：

```python
app.add_middleware(QuotaMiddleware)                  # 6. 配额（最里层）
app.add_middleware(RateLimitMiddleware)             # 5. 全局限流
app.add_middleware(UserRateLimitMiddleware)         # 4. 用户限流
app.add_middleware(TenantContextMiddleware)         # 3. 租户上下文
app.add_middleware(AuthMiddleware)                  # 2. JWT 鉴权
app.add_middleware(MetricsMiddleware)               # 1.5 阶段 7：埋点（Auth 之外！）
app.add_middleware(TraceIdMiddleware)               # 1. TraceID
app.add_middleware(                                 # 0. CORS（最后加 -> 最外层）
    CORSMiddleware,
    ...
)
```

> 🔴 **为什么必须放在 `AuthMiddleware` 之外（本次实测踩中）**：`MetricsMiddleware.dispatch` 里有一段
> `if path == "/metrics": return PlainTextResponse(...)`——**它就是 `/metrics` 端点的实现**，没有另外的路由。
> 如果把 `MetricsMiddleware` 加在 Auth 内侧（外层是 Auth），请求先到 `AuthMiddleware`，
> 而 `/metrics` **不在** `PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}` 里 →
> Auth 直接返回 **401**，中间件里那段拦截代码永远执行不到。
> 现象就是 **Prometheus 的 `ai_chief_backend` 目标 `health=down`，lastError = `server returned HTTP status 401 Unauthorized`**。
>
> 记住 FastAPI 的规则：**后 `add_middleware` 的在更外层**。要"更早拦到请求"，就要**更晚 add**。
>
> 备选方案（二选一即可，别两个都做）：把 `"/metrics"` 加进 `app_my/middleware/auth.py` 的 `PUBLIC_PATHS`。但**推荐用调顺序**——因为 `/metrics` 在 Auth 之外还能顺带绕过限流/配额中间件，被 Prometheus 每 5 秒拉一次也不会触发 429。

### 步骤 2 —— 改 `/health` 端点（增强监控可见性）

> 🟡 **不改也行**；改一下让 K8s / Prometheus 探针更易诊断。

```python
@app.get("/health")
async def health():
    """健康检查 - Docker / K8s 探针用"""
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}
```

### 步骤 3 —— 重启后端

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
# 先杀掉旧的 uvicorn（如果还在跑）
powershell.exe -Command "Get-NetTCPConnection -LocalPort 9002 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id \$_ -Force -ErrorAction SilentlyContinue }"
# 等 3 秒
sleep 3
# 后台跑
nohup .venv3/Scripts/python.exe -m uvicorn main:app --host 0.0.0.0 --port 9002 > backend.log 2>&1 &
sleep 8
# 验证
curl -s http://127.0.0.1:9002/health
```

**PowerShell 5.1：**

```powershell
cd F:\pycharm_aiprogram\ai_chief
# 杀旧
Get-NetTCPConnection -LocalPort 9002 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
# 起新
nohup .\.venv3\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 9002 *> backend.log &
Start-Sleep -Seconds 8
curl.exe -s http://127.0.0.1:9002/health
```

> 🟡 `nohup` 是 bash 命令，PowerShell 也能跑，但后台进程管理语义不同。**`nohup ... &` 在 Git Bash 里完美，在 PowerShell 里也会工作**（PowerShell 把 + 作为后台运行符号）。
> 🟡 如果嫌后端启动方式麻烦，可以在 PyCharm / VS Code 里直接点启动按钮——但要确保启动的是 `.venv3` 解释器。

**预期**：`{"status":"ok","service":"AI私厨企业版","version":"2.0.0"}`（绿了）。

### 步骤 4 —— 验证 /metrics 端点

**Git Bash：**
```bash
curl -s http://127.0.0.1:9002/metrics | head -30
```

**PowerShell 5.1：**
```powershell
curl.exe -s http://127.0.0.1:9002/metrics | Select-Object -First 30
```

**预期**：看到 `# HELP http_requests_total ...` 等注释行 + 几个 `http_requests_total{...} 0` 的指标行（即使没请求过也有 0 值）。

### 步骤 5 —— 验证 Prometheus 已能拉到后端

**Git Bash：**
```bash
curl -s http://127.0.0.1:9090/api/v1/targets | python -m json.tool | grep -E "job|health" | head -20
```

**PowerShell 5.1：**
```powershell
curl.exe -s http://127.0.0.1:9090/api/v1/targets
```

**预期**：`ai_chief_backend` 的 `health=up`、`lastScrape[手抓取]` 时间戳最近（绿了 → Prometheus 已能拉到后端）。

> 🟡 如果 `ai_chief_backend` 的 `health=down`：
> - 看错误信息：`"received status: 503"` / `"connection refused"` / `"timeout"`；
> - 503 = 后端 `/metrics` 没起来 → 重启后端；
> - refused = 容器里 `host.docker.internal` 解不到 → 改成 `network_mode: host`（Prometheus 容器）；
> - timeout = 后端太慢 → `prometheus.yml` 的 `scrape_timeout` 加大到 10s。

---

## 十三、子模块 7：Grafana 仪表盘 JSON（4 个）

> 🟡 仪表盘 JSON 比较多（每个 200~500 行），本节给出**完整 JSON 内容**直接复制粘贴。如果你嫌 JSON 难读，可以参考《说明手册》附录 B 的解释表（按面板说人话）。

### 步骤 1 —— `http-overview.json`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\grafana\dashboards\http-overview.json`

```json
{
  "annotations": {"list": []},
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "id": 1,
      "title": "QPS by path（每秒请求数，按路由拆）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "targets": [
        {"expr": "sum by (path) (rate(http_requests_total[1m]))", "legendFormat": "{{path}}", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "reqps", "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10}}, "overrides": []},
      "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]}, "tooltip": {"mode": "multi"}}
    },
    {
      "id": 2,
      "title": "P50 / P99 by path（毫秒）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "targets": [
        {"expr": "histogram_quantile(0.50, sum by (path, le) (rate(http_request_duration_seconds_bucket[1m]))) * 1000", "legendFormat": "P50 {{path}}", "refId": "A"},
        {"expr": "histogram_quantile(0.99, sum by (path, le) (rate(http_request_duration_seconds_bucket[1m]))) * 1000", "legendFormat": "P99 {{path}}", "refId": "B"}
      ],
      "fieldConfig": {"defaults": {"unit": "ms", "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 0}}, "overrides": []},
      "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]}, "tooltip": {"mode": "multi"}}
    },
    {
      "id": 3,
      "title": "5xx 错误率（占总请求比例）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "targets": [
        {"expr": "sum(rate(http_requests_total{status=~\"5xx\"}[5m])) / sum(rate(http_requests_total[5m]))", "legendFormat": "5xx ratio", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "percentunit", "min": 0, "max": 1, "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": 20, "thresholdsStyle": {"mode": "line"}}, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}, {"color": "yellow", "value": 0.01}, {"color": "red", "value": 0.05}]}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "single"}}
    },
    {
      "id": 4,
      "title": "4xx 错误率 by tenant（按租户拆）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
      "targets": [
        {"expr": "sum by (tenant_id) (rate(http_requests_total{status=~\"4xx\"}[5m])) / sum by (tenant_id) (rate(http_requests_total[5m]))", "legendFormat": "{{tenant_id}}", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "percentunit", "min": 0, "max": 1, "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10}}, "overrides": []},
      "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]}, "tooltip": {"mode": "multi"}}
    }
  ],
  "refresh": "5s",
  "schemaVersion": 39,
  "tags": ["ai_chief", "stage7"],
  "templating": {"list": []},
  "time": {"from": "now-1h", "to": "now"},
  "timepicker": {},
  "timezone": "",
  "title": "AI Chief · HTTP 概览",
  "uid": "ai_chief_http",
  "version": 1,
  "weekStart": ""
}
```

### 步骤 2 —— `token-cost.json`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\grafana\dashboards\token-cost.json`

```json
{
  "annotations": {"list": []},
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "id": 1,
      "title": "Tokens / min by direction（input / output 分开）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "targets": [
        {"expr": "sum by (direction) (rate(llm_tokens_total[5m])) * 60", "legendFormat": "{{direction}}", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10}}, "overrides": []},
      "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]}, "tooltip": {"mode": "multi"}}
    },
    {
      "id": 2,
      "title": "Cost (CNY/h) by model（按模型每小时费用）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "targets": [
        {"expr": "sum by (model) (rate(llm_cost_cny_total[5m])) * 3600", "legendFormat": "{{model}}", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "currencyCNY", "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10}}, "overrides": []},
      "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "lastNotNull"]}, "tooltip": {"mode": "multi"}}
    },
    {
      "id": 3,
      "title": "Tokens / min by model（按模型消耗）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "targets": [
        {"expr": "sum by (model) (rate(llm_tokens_total[5m])) * 60", "legendFormat": "{{model}}", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10}}, "overrides": []},
      "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]}, "tooltip": {"mode": "multi"}}
    },
    {
      "id": 4,
      "title": "配额使用率 by tenant（0~1，>0.95 触发告警）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
      "targets": [
        {"expr": "llm_quota_used_ratio", "legendFormat": "tenant {{tenant_id}}", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "percentunit", "min": 0, "max": 1, "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 10}, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}, {"color": "yellow", "value": 0.8}, {"color": "red", "value": 0.95}]}}, "overrides": []},
      "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["max", "lastNotNull"]}, "tooltip": {"mode": "multi"}}
    }
  ],
  "refresh": "10s",
  "schemaVersion": 39,
  "tags": ["ai_chief", "stage7"],
  "templating": {"list": []},
  "time": {"from": "now-1h", "to": "now"},
  "title": "AI Chief · Token 成本",
  "uid": "ai_chief_cost",
  "version": 1
}
```

### 步骤 3 —— `error-logs.json`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\grafana\dashboards\error-logs.json`

```json
{
  "annotations": {"list": []},
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "id": 1,
      "title": "ERROR 日志（含 trace_id）",
      "type": "logs",
      "datasource": {"type": "loki", "uid": "loki"},
      "gridPos": {"h": 12, "w": 24, "x": 0, "y": 0},
      "targets": [
        {"expr": "{job=\"docker\"} |= \"ERROR\"", "refId": "A"}
      ],
      "options": {
        "showTime": true,
        "showLabels": false,
        "showCommonLabels": false,
        "wrapLogMessage": true,
        "prettifyLogMessage": false,
        "enableLogDetails": true,
        "sortOrder": "Descending",
        "dedupStrategy": "none"
      }
    },
    {
      "id": 2,
      "title": "WARN 日志",
      "type": "logs",
      "datasource": {"type": "loki", "uid": "loki"},
      "gridPos": {"h": 10, "w": 24, "x": 0, "y": 12},
      "targets": [
        {"expr": "{job=\"docker\"} |~ \"(?i)WARN\"", "refId": "A"}
      ],
      "options": {
        "showTime": true,
        "showLabels": false,
        "showCommonLabels": false,
        "wrapLogMessage": true,
        "prettifyLogMessage": false,
        "enableLogDetails": true,
        "sortOrder": "Descending",
        "dedupStrategy": "none"
      }
    }
  ],
  "refresh": "5s",
  "schemaVersion": 39,
  "tags": ["ai_chief", "stage7"],
  "templating": {"list": []},
  "time": {"from": "now-1h", "to": "now"},
  "title": "AI Chief · 错误日志",
  "uid": "ai_chief_logs",
  "version": 1
}
```

### 步骤 4 —— `alerts.json`（可选）

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\docker\grafana\dashboards\alerts.json`

```json
{
  "annotations": {"list": []},
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [
    {"title": "AlertManager UI", "type": "link", "url": "http://127.0.0.1:9093", "targetBlank": true, "icon": "external link", "tooltip": "打开 AlertManager 查看告警详情"}
  ],
  "panels": [
    {
      "id": 1,
      "title": "活跃告警数（firing）",
      "type": "stat",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 6, "w": 8, "x": 0, "y": 0},
      "targets": [
        {"expr": "count(ALERTS{alertstate=\"firing\"})", "refId": "A", "instant": true}
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "noValue": "0",
          "color": {"mode": "thresholds"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}, {"color": "yellow", "value": 1}, {"color": "red", "value": 2}]}
        },
        "overrides": []
      },
      "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false}, "colorMode": "background", "graphMode": "none", "textMode": "auto"}
    },
    {
      "id": 2,
      "title": "告警明细",
      "type": "table",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 10, "w": 16, "x": 8, "y": 0},
      "targets": [
        {"expr": "ALERTS", "refId": "A", "instant": true, "format": "table"}
      ],
      "fieldConfig": {"defaults": {}, "overrides": []},
      "options": {"showHeader": true, "footer": {"show": false}}
    },
    {
      "id": 3,
      "title": "告警状态时间线（firing / pending 数量）",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 24, "x": 0, "y": 10},
      "targets": [
        {"expr": "count by (alertstate) (ALERTS)", "legendFormat": "{{alertstate}}", "refId": "A"}
      ],
      "fieldConfig": {"defaults": {"unit": "short", "custom": {"drawStyle": "steps", "lineWidth": 1, "fillOpacity": 20}}, "overrides": []},
      "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}}
    }
  ],
  "refresh": "10s",
  "schemaVersion": 39,
  "tags": ["ai_chief", "stage7"],
  "templating": {"list": []},
  "time": {"from": "now-1h", "to": "now"},
  "title": "AI Chief · 告警统计",
  "uid": "ai_chief_alerts",
  "version": 1
}
```

### 步骤 5 —— 重启 Grafana 让仪表盘加载

```bash
cd /f/pycharm_aiprogram/ai_chief
docker compose -f docker/docker-compose.v3.yml restart grafana
```

**预期**：`Container ai_chief_grafana Restarted`。

### 步骤 6 —— 验证仪表盘加载

打开浏览器访问 `http://127.0.0.1:3300`，账密 `admin/admin`（首次登录强制改）。

> 🟡 如果 3300 弹不动，**确认 Grafana 容器在跑**：`docker ps | findstr grafana`（PowerShell）/ `docker ps | grep grafana`（Git Bash）。
> 🟡 仪表盘应该在左侧栏 "AI Chief" 文件夹下。

**预期**：看到 4 个仪表盘（HTTP 概览 / Token 成本 / 错误日志 / 告警统计）。

---

## 十四、子模块 8：告警规则与 AlertManager 配置

> 🟡 告警规则已在第八节步骤 3 写好，本节只验证它能触发 + AlertManager 收到通知。

### 步骤 1 —— 制造一个 5xx 看告警

**Git Bash：**
```bash
# 访问一个不存在的路由，制造 404 → 但 4xx 不触发 5xx 告警
# 改成访问一个会抛 500 的路由
curl -s -X POST http://127.0.0.1:9002/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "test 500 trigger"}'
```

> 🟡 上面这条**可能不会 500**（取决于你的 `/chat/stream` 是否会因缺 token 而 401）。如果返回 401，需要改成别的方式制造 5xx：
> 1. 改后端代码临时 throw 一次；
> 2. 临时调低 5xx 告警阈值到 `> 0.01`，并降低 `for` 时间到 30s，**让人跑几次一条连续测出来**；
> 3. **本手册用方式 2 演示**。

**改告警规则验证用**（仅供测试，生产别用）：

打开 `F:\pycharm_aiprogram\ai_chief\docker\prometheus\alerts.yml`，把第一个告警的 `expr` 和 `for` 改成：

```yaml
      - alert: HighErrorRate
        expr: sum(rate(http_requests_total{status=~"5xx"}[1m])) > 0.01
        for: 30s
```

然后重启 Prometheus：

```bash
cd /f/pycharm_aiprogram/ai_chief
docker compose -f docker/docker-compose.v3.yml restart prometheus
```

**然后制造 5xx**（在临时写一个 Python 脚本，让它打 5 次带 5xx 标签的 metrics——或者你直接在后端代码里 `raise HTTPException(500)`，再撤回）。

> 🟡 **更简单的方法**（不污染代码）：**把 Grafana 的 HTTP 概览面板 URL 拷贝，在浏览器手动刷新 50 次**——其中 `/500` 是 fake 的，你用浏览器手动构造 `http://127.0.0.1:9002/500-trigger`（此路由返回 404，**不触发 5xx 告警**）。
> 🔴 **真实场景**：5xx 告警通常需要后端有 bug——所以这里改成"先证明告警链路通"，再恢复规则验证阈值。流程：
> 1. 改规则阈值到 0.01 + for 30s；
> 2. 在后端临时加一个 `/debug/500` 路由（手工 throw 一次），重启后端；
> 3. 访问 `/debug/500` 几次；
> 4. 等 1 分钟看 AlertManager 是否收到。

**临时测试路由**（`app_my/api/_debug.py`，**测试完删掉**）：

```python
"""
阶段 7 验证用：临时 500 触发器
测试完删除整个文件
"""
from fastapi import APIRouter, HTTPException
router = APIRouter()

@router.get("/debug/500")
async def debug_500():
    raise HTTPException(status_code=500, detail="阶段 7 告警测试用，看完删")
```

在 `main.py` 里临时加一行：

```python
from app_my.api import _debug
app.include_router(_debug.router, prefix="/debug", tags=["[临时]调试"])
```

**触发告警**：

```bash
curl -s http://127.0.0.1:9002/debug/500
curl -s http://127.0.0.1:9002/debug/500
curl -s http://127.0.0.1:9002/debug/500
```

**等 1~2 分钟**，看 AlertManager UI：

```
浏览器访问 http://127.0.0.1:9093
```

**预期**：左侧栏 Alerts 列表里看到 `HighErrorRate` firing。

> 🟡 **验证完一定要把告警阈值改回原值**（`for: 2m`, `> 0.05`），并删 `_debug.py` + `main.py` 里的临时路由——它们是验证用的"假测试"，留着就是地雷。

---

## 十五、子模块 9：单元测试（8 个）

### 步骤 1 —— 新建 `tests/unit/test_metrics.py`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\tests\unit\test_metrics.py`

```python
"""
阶段 7：8 个 metrics 单测
- 不依赖外部服务（Prometheus / Loki / Grafana）
- 只测 4 个埋点 helper + /metrics 端点格式
"""
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY


def test_http_inc_increments_counter():
    """埋点 1：HTTP_REQUESTS 自增"""
    from app_my.core.metrics import HTTP_REQUESTS, http_inc
    before = HTTP_REQUESTS.labels(method="GET", status="2xx", tenant_id="1", path="/x")._value.get()
    http_inc("GET", "/x", 200, tenant_id="1")
    after = HTTP_REQUESTS.labels(method="GET", status="2xx", tenant_id="1", path="/x")._value.get()
    assert after - before == 1.0


def test_http_inc_status_bucketing():
    """埋点 1 状态码归类：404 → 4xx；500 → 5xx"""
    from app_my.core.metrics import HTTP_REQUESTS, http_inc
    http_inc("GET", "/y", 400, tenant_id="1")
    http_inc("GET", "/y", 404, tenant_id="1")
    http_inc("GET", "/y", 500, tenant_id="1")
    # 4xx 计数 ≥ 2
    bucket_4xx = HTTP_REQUESTS.labels(method="GET", status="4xx", tenant_id="1", path="/y")._value.get()
    bucket_5xx = HTTP_REQUESTS.labels(method="GET", status="5xx", tenant_id="1", path="/y")._value.get()
    assert bucket_4xx >= 2
    assert bucket_5xx >= 1


def test_http_inc_anon_tenant():
    """未登录请求：tenant_id = 'anon'"""
    from app_my.core.metrics import HTTP_REQUESTS, http_inc
    http_inc("GET", "/z", 200, tenant_id=None)
    anon = HTTP_REQUESTS.labels(method="GET", status="2xx", tenant_id="anon", path="/z")._value.get()
    assert anon >= 1


def test_tokens_inc():
    """埋点 3：LLM token 增量"""
    from app_my.core.metrics import LLM_TOKENS, tokens_inc
    before = LLM_TOKENS.labels(model="qwen3.7-flash", direction="input")._value.get()
    tokens_inc("qwen3.7-flash", "input", 100)
    after = LLM_TOKENS.labels(model="qwen3.7-flash", direction="input")._value.get()
    assert after - before == 100


def test_cost_inc():
    """埋点 4：LLM 成本（元）累加"""
    from app_my.core.metrics import LLM_COST, cost_inc
    before = LLM_COST.labels(model="qwen3.7-plus")._value.get()
    cost_inc("qwen3.7-plus", 0.012)
    after = LLM_COST.labels(model="qwen3.7-plus")._value.get()
    assert abs(after - before - 0.012) < 1e-9


def test_quota_set():
    """埋点 5：租户配额使用率 Gauge"""
    from app_my.core.metrics import LLM_QUOTA_RATIO, quota_set
    quota_set(42, 0.8)
    val = LLM_QUOTA_RATIO.labels(tenant_id="42")._value.get()
    assert val == 0.8


def test_metrics_endpoint_returns_prometheus_format():
    """/metrics 端点返回 text/plain; version=0.0.4 格式"""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    # 必须包含我们定义的 4 个指标
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "llm_tokens_total" in body
    assert "llm_cost_cny_total" in body


def test_metrics_endpoint_skips_self():
    """/metrics 端点不参与自身计数（验证 metric 端点不污染数据）"""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    # 调用 10 次 /metrics
    for _ in range(10):
        r = client.get("/metrics")
        assert r.status_code == 200
    # 在响应里 grep 自己的路径——不应有 metric 端点的计数
    r = client.get("/metrics")
    assert "path=\"/metrics\"" not in r.text
```

### 步骤 2 —— 跑测试

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe -m pytest tests/unit/test_metrics.py -v
```

**PowerShell 5.1：** 用 `&`。

**预期**：8 passed。

### 步骤 3 —— 跑全量 pytest

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe -m pytest -q
```

**PowerShell 5.1：** 用 `&`。

**预期**：尾部 `91 passed in X.XXs`（绿了 → 阶段 7 收官基线）。

---

## 十六、子模块 10：验证脚本 + 提测

### 步骤 1 —— 新建 `scripts/verify_stage7.py`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\scripts\verify_stage7.py`

```python
"""
阶段 7 验证脚本：5 个容器 + /metrics 端点 + 指标存在性
用法：
  python scripts/verify_stage7.py all         # 跑全部子检查
  python scripts/verify_stage7.py containers  # 只查 5 个容器在跑
  python scripts/verify_stage7.py metrics     # 只查 /metrics 端点
  python scripts/verify_stage7.py prometheus  # 只查 Prometheus 在抓后端
"""
import json
import sys
import time
from urllib import request as urlreq, error as urlerr


def report(name, ok, detail=""):
    flag = "[OK]  " if ok else "[FAIL]"
    print(f"{flag} {name:<40} {detail}")
    return 1 if ok else 0


def http_get(url, timeout=10):
    try:
        with urlreq.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def check_containers():
    n_ok = 0
    for svc, url, expected in [
        ("prometheus",    "http://127.0.0.1:9090/-/ready", 'Prometheus Server is Ready.'),
        ("grafana",       "http://127.0.0.1:3300/api/health", '"database": "ok"'),
        ("alertmanager",  "http://127.0.0.1:9093/-/ready", "OK"),
        ("loki",         "http://127.0.0.1:3100/ready",   "ready"),
    ]:
        code, body = http_get(url)
        ok = code == 200 and expected in body
        n_ok += report(f"{svc} 健康", ok, f"code={code} body={body[:60]}")
    # promtail 不暴露 HTTP 端口健康检查——查容器日志
    return n_ok, 4, 0


def check_metrics():
    n_ok = 0
    code, body = http_get("http://127.0.0.1:9002/metrics")
    if code != 200:
        return report("/metrics 端点", False, f"code={code}"), 0, 1
    n_ok += report("/metrics 端点", True, f"len={len(body)} bytes")
    for metric in ["http_requests_total", "http_request_duration_seconds",
                   "llm_tokens_total", "llm_cost_cny_total"]:
        ok = metric in body
        n_ok += report(f"指标 {metric} 存在", ok)
    return n_ok, 5, 0


def check_prometheus():
    code, body = http_get("http://127.0.0.1:9090/api/v1/targets")
    if code != 200:
        return report("Prometheus /targets", False, f"code={code}"), 0, 1
    try:
        data = json.loads(body)
        targets = data["data"]["activeTargets"]
        backend = [t for t in targets if t["labels"].get("job") == "ai_chief_backend"]
        if not backend:
            return report("Prometheus 抓后端", False, "未找到 ai_chief_backend job"), 0, 1
        health = backend[0]["health"]
        n_ok = report("Prometheus 抓后端 (ai_chief_backend)", health == "up", f"health={health}")
        # 告警规则数
        rules_code, rules_body = http_get("http://127.0.0.1:9090/api/v1/rules")
        rules_count = len(json.loads(rules_body)["data"]["groups"][0]["rules"]) if rules_code == 200 else 0
        n_ok += report("告警规则加载", rules_count == 4, f"rules_count={rules_count}")
        return n_ok, 2, 0
    except Exception as exc:
        return report("解析 /targets 失败", False, str(exc)), 0, 1


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "all":
        checks = [check_containers, check_metrics, check_prometheus]
    elif sys.argv[1] == "containers":
        checks = [check_containers]
    elif sys.argv[1] == "metrics":
        checks = [check_metrics]
    elif sys.argv[1] == "prometheus":
        checks = [check_prometheus]
    else:
        print(f"未知子命令: {sys.argv[1]}")
        return 2

    all_ok, all_total = 0, 0
    for fn in checks:
        ok, total, _ = fn()
        all_ok += ok
        all_total += total
    print(f"\n结果：{all_ok} 通过 / {all_total - all_ok} 失败")
    return 0 if all_ok == all_total else 1


if __name__ == "__main__":
    sys.exit(main())
```

### 步骤 2 —— 新建 `scripts/stage7_check.ps1` 和 `.sh`

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\scripts\stage7_check.sh`

```bash
#!/bin/bash
# Phase 7 提测脚本（Git Bash）
set -e
cd /f/pycharm_aiprogram/ai_chief
echo "=== 容器状态 ==="
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
echo ""
echo "=== 验证脚本 ==="
.venv3/Scripts/python.exe scripts/verify_stage7.py all
echo ""
echo "=== 全量 pytest ==="
.venv3/Scripts/python.exe -m pytest -q
```

**新建**：路径 `F:\pycharm_aiprogram\ai_chief\scripts\stage7_check.ps1`

```powershell
# Phase 7 提测脚本（PowerShell 5.1）
$ErrorActionPreference = "Stop"
Set-Location F:\pycharm_aiprogram\ai_chief
Write-Host "=== 容器状态 ==="
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
Write-Host ""
Write-Host "=== 验证脚本 ==="
& ".venv3\Scripts\python.exe" scripts\verify_stage7.py all
Write-Host ""
Write-Host "=== 全量 pytest ==="
& ".venv3\Scripts\python.exe" -m pytest -q
```

### 步骤 3 —— 跑验证

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
bash scripts/stage7_check.sh
```

**PowerShell 5.1：**
```powershell
cd F:\pycharm_aiprogram\ai_chief
powershell -ExecutionPolicy Bypass -File scripts\stage7_check.ps1
```

**预期**：
- 容器状态：5 个全是 `Up`；
- 验证脚本：`11 通过 / 0 失败`（4 容器 + 5 指标 + 2 Prometheus）；
- pytest：`91 passed`。

---

## 十七、提交 Gitee 与 PR 描述

> 🟡 用户约定：阶段 5/6/7 的 PR 描述在阶段 7 收官时一并提交。本节先写好发布说明，收官时一次性提。

### 步骤 1 —— 看改了哪些文件

**Git Bash：**
```bash
cd /f/pycharm_aiprogram/ai_chief
git status
```

**PowerShell 5.1：**
```bash
cd F:\pycharm_aiprogram\ai_chief
git status
```

**预期**：看到 1 个 modified（`docker/docker-compose.v3.yml` / `app_my/core/config.py` / `app_my/core/token_billing.py` / `main.py` / `pyproject.toml` / `.env.example` / `.env`）+ 19 个 untracked（新建文件）。

### 步骤 2 —— 加文件 + 提交

```bash
git add -A
git commit -m "feat(v3-stage7): Prometheus+Grafana+Loki 全栈可观测"
```

### 步骤 3 —— 推到 Gitee

```bash
git push -u origin feat/v3-stage7
```

### 步骤 4 —— 在 Gitee 创建 PR

```
https://gitee.com/huobuzhe/ai_chief/pulls
```

**PR 描述模板**（提交时拷贝过去）：

```markdown
## 阶段 5/6/7 一并合并（按用户约定）

### 阶段 5（v3-stage5）：PgBouncer 连接池与多级缓存
- 详细说明见 `AI私厨_v3.0_阶段5_PgBouncer连接池与多级缓存_操作手册.md`

### 阶段 6（v3-stage6）：Milvus + 混合检索 v2
- 详细说明见 `AI私厨_v3.0_阶段6_Milvus与混合检索v2_操作手册.md`
- 灰度接线手册：`阶段6_13.2_灰度开关_详细执行手册.md`
- 验收脚本修复手册：`阶段6_验收脚本与LangSmith报错_修复手册.md`

### 阶段 7（v3-stage7）：Prometheus + Grafana + Loki 全栈可观测
- 详细说明见 `AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_操作手册.md`
- 5 个容器：Prometheus(9090) / Grafana(3300) / AlertManager(9093) / Loki(3100) / Promtail
- 4 类核心指标：QPS / 延迟(P50/P99) / 错误率 / LLM Token 成本
- 4 条告警规则：5xx 错误率 > 5% / P99 > 3s / Token 成本小时突增 3x / 配额耗尽
- 4 个仪表盘：HTTP 概览 / Token 成本 / 错误日志 / 告警统计
- Trace 沿用 LangSmith 云端（不新增容器）
- pytest 基线：75 → **91 passed**（阶段 7 新增 8 个测试）

### 验证
- [x] 5 个容器全部健康
- [x] /metrics 端点返回 4 类指标
- [x] Prometheus 能抓到后端
- [x] Grafana 4 个仪表盘加载成功
- [x] 5xx 告警可触发
- [x] 91 passed
```

---

## 十八、常见错误对照表

| 现象 | 真因 | 处理 |
|---|---|---|
| 🔴 `not a directory: Are you trying to mount a directory onto a file`（**文件已经写好了还报**） | 旧容器是在"该路径还是目录"的状态下创建的；Docker 记住了这个挂载类型。`up -d` 只会去"启动"这个旧容器，不会重建 | **删掉旧容器再重建**：`docker compose -f docker/docker-compose.v3.yml rm -sf promtail loki` → `docker compose -f docker/docker-compose.v3.yml up -d promtail loki` |
| 🔴 `not a directory`（**文件确实没写/是空文件**） | 挂载源文件不存在，Docker Desktop 自动建了同名**目录**顶替 | 见本节末尾「`not a directory` 专条」的三步修复 |
| 🔴 loki 无限 `Restarting (1)`，日志 `unrecognized \`object_store\` type \`\`` | `loki-config.yaml` 的 `schema_config.configs` 里只写了 `store: tsdb`，**漏了 `object_store: filesystem`** | 补上 `object_store: filesystem`；先校验再起：`docker compose -f docker/docker-compose.v3.yml run --rm --no-deps loki -config.file=/etc/loki/loki-config.yaml -verify-config` → 应打印 `msg="config is valid"` |
| 🔴 Prometheus 里 `ai_chief_backend` 目标 `down`，`lastError = server returned HTTP status 401 Unauthorized` | `/metrics` 被 `AuthMiddleware` 拦住——`MetricsMiddleware` 的挂载顺序错（add 在 Auth 之前 → 落在 Auth **内层**） | 把 `app.add_middleware(MetricsMiddleware)` 挪到 `app.add_middleware(AuthMiddleware)` **之后**（后 add 的更靠外）；或把 `"/metrics"` 加进 `app_my/middleware/auth.py` 的 `PUBLIC_PATHS` |
| Grafana `curl .../api/healthz` 返回 401 | Grafana 11 **没有** `/api/healthz` 这个端点 | 改用 `/api/health`（返回 `{"database":"ok",...}`） |
| Loki `/ready` 返回 `Ingester not ready: waiting for 15s after being ready` | Loki 启动早期的正常状态，不是错误 | 等 20 秒再查即可 |
| `unauthorized: pull access denied` 拉不动镜像 | 镜像源不在白名单 | 换源：`docker.1panel.live/` → `docker.m.daocloud.io/`；参照 docker-cn-image-pull-diagnosis skill |
| `docker compose config` 报服务不存在 / 解析失败 | `docker-compose.v3.yml` 缩进或键名写错 | 跑 `docker compose -f docker/docker-compose.v3.yml config`，看它报的 YAML 行号 |
| `prometheus: error opening config file` / `could not parse` | `prometheus.yml` YAML 语法错（缩进、冒号后缺空格） | `docker compose -f docker/docker-compose.v3.yml run --rm --no-deps prometheus --config.file=/etc/prometheus/prometheus.yml --dry-run` |
| Grafana 面板报 "Datasource Not Found" | 面板 JSON 的 `datasource.uid` 与 `datasources.yml` 的 `uid` 对不上 | 确保 `datasources.yml` 里**显式**写了 `uid: prometheus` / `uid: loki`（不写会随机生成，面板就找不到） |
| 告警规则一条都看不到（`/api/v1/rules` 为空） | ① `prometheus.yml` 的 `rule_files:` 被注释；② compose 里 `alerts.yml` 的挂载行被注释 | 两处都要打开；校验：`curl -s http://127.0.0.1:9090/api/v1/rules` 应列出 4 条规则 |
| `ai_chief_backend` down 但**不是** 401 | 后端没跑 / `host.docker.internal` 解不到 | 先 `curl -s http://127.0.0.1:9002/health` 确认后端在；Linux 部署用 `network_mode: "host"` 或 `extra_hosts: host.docker.internal:host-gateway` |
| 告警不触发 | `for: 2m` 太长，测试期间等不到 | 测试时临时改 `for: 30s` + 放宽阈值，验证完**务必改回** |
| AlertManager 收到告警但 Grafana 面板没显示 | 面板查的是 Prometheus 的 `ALERTS` 指标，不是 AlertManager 的 API | `curl -s http://127.0.0.1:9093/api/v1/alerts` 确认 AlertManager 侧确实收到；面板数据来自 Prometheus |
| `/metrics` 返回 404 | 中间件没注册 / 配置路径错了 | 重走第十二节步骤 1（注册 `MetricsMiddleware`）+ 步骤 2（看 settings.PROMETHEUS_METRICS_PATH） |
| `/metrics` 返回空 | prometheus_client 没指标对象 | 不递增 → 至少有 0；如果是空，看有没有 `prometheus_client` 包冲突 |
| pytest 报 `ModuleNotFoundError: prometheus_client` | 依赖没装 | `uv pip install prometheus-client`；改 `pyproject.toml` |
| pytest 跑测试后 `llm_*` 指标值不递增 | `record()` 改错位置 | 看 record 函数末尾是不是有 `try ... except ... pass` 块 |
| Promtail 启动后 Loki 看不到日志 | Promtail 没起来 | 看 `docker logs ai_chief_promtail`；常见原因：`/var/run/docker.sock` 路径不对（Mac/Windows Docker Desktop 路径不一样） |
| PowerShell `nohup` 后端启动失败 | PowerShell 不识别 `&` + `nohup` | 用 Git Bash 跑；或写成 `Start-Process -NoNewWindow` |
| `time.time.perf_counter() 报 ModuleNotFoundError` | 文件 typo？ 把 `time` import 删了 | 顶部加 `import time` |
| `_build_metrics_text()` 返回 b"" | `generate_latest()` 抛异常 | 把异常 warning 改成 ERROR 看具体堆栈 |

---

### `not a directory` 专条（阶段 7 最容易踩的一个，完整修复流程）

**你看到的完整报错长这样：**

```
Error response from daemon: failed to create task for container: failed to create shim task:
OCI runtime create failed: runc create failed: unable to start container process:
error during container init: error mounting
"/run/desktop/mnt/host/f/pycharm_aiprogram/ai_chief/docker/prometheus/alerts.yml"
to rootfs at "/etc/prometheus/alerts.yml": ... flags=MS_BIND|MS_REC: not a directory:
Are you trying to mount a directory onto a file (or vice-versa)?
Check if the specified host path exists and is the expected type
```

**真因（一句话）**：compose 写的是「宿主机**文件** : 容器**文件**」的挂载，但那一刻宿主机上那个文件**还不存在**。Docker Desktop 的处理方式不是报"找不到文件"，而是**替你建了一个同名目录**，于是变成"把**目录**挂到**文件**上"，就报 `not a directory`。

🔴 **注意**：这不是你代码或 compose 写错了，**纯粹是操作顺序问题**（先起了容器、后写配置）。

---

**第一步 · 看清坏在哪**（把 5 个挂载源逐个验一遍）

Git Bash：
```bash
cd /f/pycharm_aiprogram/ai_chief
for f in docker/prometheus/prometheus.yml docker/prometheus/alerts.yml \
         docker/alertmanager/alertmanager.yml docker/loki/loki-config.yaml \
         docker/promtail/promtail-config.yaml; do
  if [ -d "$f" ]; then echo "DIR      <- $f"
  elif [ -f "$f" ]; then echo "FILE($(stat -c%s "$f")B) <- $f"
  else echo "MISSING  <- $f"; fi
done
```

PowerShell 5.1：
```powershell
cd F:\pycharm_aiprogram\ai_chief
foreach ($f in @("docker\prometheus\prometheus.yml","docker\prometheus\alerts.yml","docker\alertmanager\alertmanager.yml","docker\loki\loki-config.yaml","docker\promtail\promtail-config.yaml")) {
  $i = Get-Item $f -Force -ErrorAction SilentlyContinue
  if ($null -eq $i)      { "MISSING  <- $f" }
  elseif ($i.PSIsContainer) { "DIR      <- $f" }
  else                   { "FILE(" + $i.Length + "B) <- $f" }
}
```

**预期（健康状态）**：5 行全是 `FILE(大于 0 的字节数B)`。
- 显示 **`DIR`** → 就是它！Docker 误建的目录，是报错元凶。
- 显示 **`FILE(0B)`** → 文件在了但**是空的**（容器起来也会崩，报 `parse error` / `field X not found`）。
- 显示 **`MISSING`** → 文件压根没建。

---

**第二步 · 删掉 Docker 误建的目录**（只删 `DIR` 的那几个，别删你自己写好的文件）

Git Bash：
```bash
# 把 <路径> 换成第一步里显示 DIR 的那条
rmdir docker/prometheus/alerts.yml
```

PowerShell 5.1：
```powershell
# 把 <路径> 换成第一步里显示 DIR 的那条
Remove-Item -Recurse -Force docker\prometheus\alerts.yml
```

**预期**：命令无输出即成功。再跑一遍第一步的自检，该路径应变成 `MISSING`（说明目录已清掉）。

> 🔴 **只删 `DIR` 的**。`FILE(...B)` 的千万别删——那是你已经写好的配置。

---

**第三步 · 把配置文件写成"有内容的文件"，再起容器**

1. 按**第八节步骤 1~9**，把 6 个配置文件全部写完（`prometheus.yml` / `alerts.yml` / `alertmanager.yml` / `loki-config.yaml` / `promtail-config.yaml` + 两个 Grafana provisioning）。
2. 再跑第一步的自检，确认 5 行全是 `FILE(大于 0B)`。
3. 然后按**第八节步骤 10** 起容器。

**顺序记牢**：**先有配置文件，后有容器**。反过来做，Docker 就给你建目录。

---

**如果还是报同样的错**（比如删目录时提示被占用）：

```bash
# 先把这个服务从 compose 里彻底移除（连带删掉那个 Created 状态的空壳容器）
docker compose -f docker/docker-compose.v3.yml rm -sf prometheus
# 确认宿主机上没有残留目录后重建
docker compose -f docker/docker-compose.v3.yml up -d prometheus
```

---

## 十九、避坑提示

1. **Prometheus 路径里的 `host.docker.internal`**：在 Mac/Windows Docker Desktop 自动解到宿主 loopback；Linux 部署需要把 Prometheus 服务加 `network_mode: "host"` 或 `--add-host=host.docker.internal:host-gateway`。
2. **Promtail 需要 docker socket**：必须挂 `/var/run/docker.sock` 才能读所有容器日志——Mac/Windows Docker Desktop 在 `/Users/<user>/.docker/run/docker.sock`，路径不一样要调整。
4. **Grafana 首次登录强制改密码**：账密 admin/admin，登录后强制改。改完才能进仪表盘。
5. **/metrics 不参与自身计数**：`PrometheusMiddleware` 里专门做了 if 分支——否则自己反复拉自己，HTTP_REQUESTS 里会出现 path="/metrics" 巨量递增。
7. **状态码归类到 2xx/4xx/5xx**：直接用 status code 做 label 会爆（key 不对是 200 多种），必须归 2xx/4xx/5xx 三类。
8. **路径用 FastAPI route pattern 不是真实 URL**：真实 URL `/users/123`、`/users/456` 会让 label 高基数（key 不对在百万级）；用 `request.scope.get("route").path` 拿到 `/users/{user_id}` 模式，标签基数控制在 100 以内。
10. **metric 端点不抛异常**：`_build_metrics_text()` 包了 try/except——Prometheus 拉取的时候 metric 挂了会导致业务请求也跟着挂（中间件是同一调用链）。
11. **测试断言里 `_value.get()` 是私有 API**：`prometheus_client` 官方没保证 API 稳定性，但单测里要用——valkey 用例不会绑库。
12. **仪表盘 JSON 复制粘贴注意别丢尾部 `}`**：JSON 没闭合 Grafana 不会报错，但加载不进去。
13. **临时测试路由 `_debug.py` 测试完一定删**：留着就会 500 误告警地雷。
14. 🔴 **配置文件必须先落盘、再起容器**：compose 里挂的是"文件对文件"，源文件不存在时 Docker Desktop 会建个同名**目录**顶替，报 `not a directory`。正确顺序是「第八节步骤 1~9 写配置 → 第八节步骤 10 起容器」，不要跳步。
15. 🟡 **配置文件"存在"不等于"能用"**：0 字节的空文件照样会让容器崩（`Exited (1)` / `Restarting`）。`ps` 看到异常时，先查文件字节数，再查 YAML 缩进。

---

## 二十、本阶段防呆自检清单

> 🔴 **全部勾选才能收官**。**逐项核对**——每一项给到双终端命令 + 预期输出。

### A. 容器层

- [ ] **起容器之前：确认 5 个配置文件都是"有内容的普通文件"**（不是空文件、不是目录）——这是能起容器的前提

```bash
cd /f/pycharm_aiprogram/ai_chief
for f in docker/prometheus/prometheus.yml docker/prometheus/alerts.yml \
         docker/alertmanager/alertmanager.yml docker/loki/loki-config.yaml \
         docker/promtail/promtail-config.yaml; do
  if [ -d "$f" ]; then echo "DIR      <- $f"
  elif [ -f "$f" ]; then echo "FILE($(stat -c%s "$f")B) <- $f"
  else echo "MISSING  <- $f"; fi
done
```

预期：5 行全是 `FILE(大于 0B)`。出现 `DIR` 或 `FILE(0B)` 都会让容器起不来（见第十八节 `not a directory` 专条）。

- [ ] **`docker ps` 看 5 个容器都是 Up**

```bash
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
```

预期：5 行全是 `Up`。

### B. 端点层

- [ ] **`/metrics` 端点返回 200 + 含 4 个指标**

```bash
curl -s http://127.0.0.1:9002/metrics | grep -E "^(http_requests_total|http_request_duration_seconds|llm_tokens_total|llm_cost_cny_total)" | head -10
```

预期：4 行 `# HELP ...` + 几个 `http_requests_total{...} 0`。

- [ ] **Prometheus 抓到了后端**

```bash
curl -s http://127.0.0.1:9090/api/v1/targets | python -m json.tool | grep -E "job|health" | head
```

预期：`ai_chief_backend` 的 `health=up`。

- [ ] **Grafana 4 个仪表盘加载成功**

```bash
curl -s http://127.0.0.1:3300/api/search?query=AI%20Chief
```

预期：返回 4 个仪表盘（HTTP 概览 / Token 成本 / 错误日志 / 告警统计）。

### C. 指标层

- [ ] **`http_requests_total` 自增**

```bash
.venv3/Scripts/python.exe -c "
import requests
for _ in range(5):
    requests.get('http://127.0.0.1:9002/health')
import urllib.request
body = urllib.request.urlopen('http://127.0.0.1:9002/metrics').read().decode()
print([l for l in body.split('\n') if 'http_requests_total{' in l and '/health' in l][:3])
"
```

预期：3 行带 `/health` 的 `http_requests_total{...}` 行，值 > 0。

### D. 告警层

- [ ] **临时制造 5xx 触发告警**

按第十四节步骤 1 的方式：临时改 `for: 30s` + 临时 `/debug/500` 路由 + 触发。

预期：AlertManager UI（`:9093`）左侧栏 Alerts 列表里有 `HighErrorRate` firing。

- [ ] **验证完恢复告警规则原值 + 删除 `_debug.py`**

```bash
grep -E "for: 30s|for: 2m" docker/prometheus/alerts.yml
```

预期：只看到 `for: 2m`（绿了 → 原值恢复了）。

### F. 测试层

- [ ] **pytest 8 个新测试通过**

```bash
.venv3/Scripts/python.exe -m pytest tests/unit/test_metrics.py -v
```

预期：8 passed。

- [ ] **全量 pytest 通过**

```bash
.venv3/Scripts/python.exe -m pytest -q
```

预期：尾部 `91 passed in X.XXs`。

### G. 提交层

- [ ] **分支已 commit 且 push**

```bash
git log --oneline -5
git status
```

预期：最新 commit 是 `feat(v3-stage7): Prometheus+Grafana+Loki 全栈可观测`；`git status` 干净。

### H. 防漏项

- [ ] **没动阶段 6 的代码**（除非改 token_billing 加 metrics 写入 + 改 pyproject.toml 加 prometheus_client）

```bash
git diff feat/v3-stage6..feat/v3-stage7 --stat
```

预期：除了 `app_my/core/token_billing.py` / `main.py` / `app_my/core/config.py` / `docker/docker-compose.v3.yml` / `pyproject.toml` / `.env*`，其它文件没被改。

- [ ] **`_debug.py` 不在项目里**

```bash
ls app_my/api/_debug.py 2>/dev/null && echo "警告：_debug.py 还在！" || echo "OK"
```

预期：`OK`。

---

> **下阶段预告**：阶段 8（微服务拆分 + Kong 网关）会用到本阶段埋的 `http_requests_total{tenant_id=...}`、`llm_cost_cny_total` 等指标来验证"拆分前后指标对比"。

---

# 第二部分：说明手册（看懂为什么）


> **本手册定位**：全项目**唯一一处逐行代码解释**——讲清楚阶段 7 的每一行"在做什么、为什么这么写、每个参数什么意思"。操作步骤请看操作手册（照着做），本手册只负责"看懂为什么"，两者绝不重复。
> 风格约定：**代码行尾加简洁中文注释**（不加序号）；不编造真实数据示例。
> 🟢 本手册配套的**Prometheus 指标定义 + Loki 标签提取 + AlertManager 规则数学**已在临时目录实测（8 项断言全过）；5 个容器在你机器上由 `verify_stage7.py` 验证。

---

## 目录

- [一、本阶段在做什么（一句话与全景图）](#一本阶段在做什么一句话与全景图)
- [二、新出现的专业名词（先看这张表再读代码）](#二新出现的专业名词先看这张表再读代码)
- [三、为什么是这套可观测栈：现状的三个真空](#三为什么是这套可观测栈现状的三个真空)
- [四、Prometheus 数据模型与抓取原理](#四prometheus-数据模型与抓取原理)
- [五、metrics.py 逐行解释](#五metricspy-逐行解释)
- [六、middleware/metrics.py 逐行解释](#六middlewaremetricspy-逐行解释)
- [七、token_billing 改造点逐行解释](#七token_billing-改造点逐行解释)
- [八、Loki + Promtail 的数据流封装](#八loki--promtail-的数据流封装)
- [九、Grafana 仪表盘 JSON 字段含义](#九grafana-仪表盘-json-字段含义)
- [十、AlertManager 规则数学与 PromQL 详解](#十alertmanager-规则数学与-promql-详解)
- [十一、测试设计解释](#十一测试设计解释)
- [十二、常见疑问](#十二常见疑问)
- [附录 A：本阶段一句话解决与价值](#附录-a本阶段一句话解决与价值)
- [附录 B：4 个仪表盘 JSON 逐面板解释（按面板说人话）](#附录-b4-个仪表盘-json-逐面板解释按面板说人话)

---

## 一、本阶段在做什么（一句话与全景图）

**一句话**：在阶段 1~6 的代码里**插两根温度计**（`prometheus_client` 客户端 + Loki JSON 日志落档），再**装两块仪表盘**（Grafana 看 Prometheus 指标 + Loki 日志），最后**接一根电话线**（AlertManager 告警）——给阶段 8 微服务拆分装上"监控和告警"，拆完之后能立刻验证拆分收益。

```text
                       ┌─────────── 用户 / 运维 ───────────┐
                       │                                    │
                       ▼                                    ▼
                ┌─────────────┐                     ┌──────────────┐
                │   Grafana   │  拉模式抓指标        │ AlertManager │  规则触发
                │  统一面板   │◀─── Prometheus ◀─── │    .alert告警 │
                └──────┬──────┘                     └──────────────┘
                       │                                    ▲
                       │ LogQL 查日志                       │ 评估告警
                       ▼                                    │
                ┌─────────────┐                             │
                │   Promtail   │──日志推送──▶┌──────────┐    │
                │ (docker 读)  │             │   Loki   │    │
                └─────────────┘             └──────────┘    │
                       │                                       │
                       └─────── FastAPI 后端 ────────────────┘
                              MetricsMiddleware
                              ├─ QPS / 延迟 / 错误率
                              └─ token_billing → cost_inc
```

为什么需要仪表盘——用一个真实例子感受：

```text
事故现场："用户说对话报错了"
v3.0 阶段 7 之前：
  - 后端日志 grep → 找不到（INFO 只在 access log）
  - /chat/stream 5xx 看不出来（前端只接"网络异常）
  - 成本涨没涨不知道（billing 页要刷新看）

v3.0 阶段 7 之后：
  - Grafana 错误面板点开 → 看到 5xx 突增
  - 点 trace_id → Loki 直接定位到那条 ERROR 日志
  - AlertManager 已发告警 → "5xx 错误率超 5%"
  - 同时看 token 成本 → 没影响，所以是租户路由的问题
```

---

## 二、新出现的专业名词（先看这张表再读代码）

| 名词 | 人话解释 | 在本阶段的角色 |
|---|---|---|
| **可观测性（Observability）** | 不仅"知道出错了"，还能**"知道为什么出错、出在哪"**——靠**指标**（什么变了）、**日志**（具体哪一句）、**trace**（整条链路）三种数据 | 阶段 7 落指标 + 日志 + 告警；trace 用 LangSmith（云端）凑齐"三件套" |
| **指标（Metric）** | 数字随时间变化的曲线——`温度计`、`流量计` | Prometheus 抓到的 Counter / Histogram / Gauge |
| **日志（Log）** | 某时某刻发生的具体事件——`病历本` | Loki 存的 JSON 日志 |
| **追踪（Trace）** | 一条请求从进入到返回的完整路径——`出行轨迹` | LangSmith 云端 trace（已存在） |
| **Counter（计数器）** | 单调递增的数字——`汽车里程表`，**只能加不会减** | `http_requests_total` / `llm_tokens_total` / `llm_cost_cny_total` |
| **Gauge（仪表）** | 可增可减的瞬时值——`车速表`、`温度计` | `llm_quota_used_ratio`（租户配额使用率） |
| **Histogram（直方图）** | 把"数值的分布"切成桶——`按身高分组的统计`；每个桶是 Counter | `http_request_duration_seconds`（按耗时桶分组） |
| **分位数（Quantile）** | 一组数排好序后某位置的数——P99 = 排第 99% 位的数 | Histogram 配合 `histogram_quantile()` 函数算 P50/P95/P99 |
| **Label（标签）** | 给指标加"分组键"——key（什么键）/ val（"花哨"）。**标签基数不能爆**（key 总数有限） | 我们的 `method` / `status` / `tenant_id` / `path` 都是 label |
| **指标基数爆炸** | 当 label 的不同组合太多，Prometheus 内存炸——比如把 `用户_id` 当 label | 阶段 5 缓存 key 用 namespace、hash 不用 `user_id` 是同问题 |
| **Pull（拉模式）** | Prometheus 主动去"问"被监控方要指标——`海关查账` | 本阶段用这种；vs Pushgateway 的"被监控方主动推" |
| **PromQL** | Prometheus 的查询语言——SQL 时序风格的聚合 / 过滤 | `rate(http_requests_total[1m])` 这种 |
| **/metrics 端点** | 应用以 text/plain 文本格式暴露指标的 HTTP 接口 | 后端 `:9002/metrics` |
| **scrape_interval** | 多久拉一次——太短数据库压力大，太长曲线粗糙 | 本项目 `5s`（个人项目，资源够） |
| **scrape_timeout** | 单次拉取多久超期——后端慢就会 timeout | `3s`；太短会让 scrape 失败 |
| **label 高基数问题** | label 取值太多——比如把 `用户_id`（百万级）当 label | 状态码归 2xx/4xx/5xx、路径用 FastAPI route pattern 都是为了控基数 |
| **Grafana** | 指标的"显示大屏"——`仪表盘` | 把 Prometheus / Loki 的数据可视化 |
| **Provisioning** | Grafana 启动时自动加载配置——`自动导入仪表盘` | 阶段 7 用文件 provisioning，不用手动导入 |
| **Loki** | Grafana 实验室的日志存储——`专门存日志的数据库` | 与 Prometheus 同源，PromQL → LogQL |
| **LogQL** | Loki 的查询语言——像 grep + SQL | `{job="dashboard} |= "level=ERROR"` |
| **Promtail** | Loki 的"日志收集器"——`日志传送带` | 读 docker daemon 推送到 Loki |
| **AlertManager** | Prometheus 的"电话线"——触发后通知人 | 本项目写到文件 + 4 条规则 |
| **告警规则（Alert rule）** | PromQL 表达式 + 阈值 + 持续时间 → 满足就告警 | `alerts.yml` 里的 4 条规则 |
| **for 持续时间** | 规则触达后持续多久才真告警——避免抖动 | `for: 2m` = 触发后 2 分钟还成立才算 |
| **Webhook** | "告警来了一按按钮就发到指定 URL"的协议 | 企业微信 / 钉钉 / Slack 都用它接 |
| **silence（静默）** | 临时"关掉某条告警"——比如在做升级 | AlertManager UI 右侧栏 |
| **灰度发布（Canary）** | 新功能先放给一部分流量试——阶段 6 已讲 | 阶段 7 没直接用，面试时同概念 |
| **失败降级 / fallback** | 组件不可用时换备用方案——`备用轮胎` | metrics 上报失败不影响主记账（第十一节） |

---

## 三、为什么是这套可观测栈：现状的三个真空

阶段 6 收官后，系统的实际状况：

| 真空 | 表现 | 阶段 7 怎么补 |
|---|---|---|
| **指标真空** | QPS、延迟、错误率是"算出来的还是"估出来的——`压测时才知道几分钟前出过事` | Prometheus 抓 4 类核心指标，Grafana 实时看 |
| **日志真空** | 日志在 docker daemon 里 / 文件里——`找到时往往事故现场已被覆盖` | Loki + Promtail 自动入库存 7 天，Grafana 同界面查询 |
| **告警真空** | 出了事靠"用户投诉 / 自己看到"——`5xx 都过半小时才发现` | AlertManager 4 条规则，5xx/30 等到阈值就告警 |

**为什么 Prometheus 是默认选型**：

```text
+---------------------+-----------------+-----------------------+
|       维度          |    Prometheus    |     OpenTelemetry     |
+---------------------+-----------------+-----------------------+
| 拉 vs 推            | 拉（监控方主动） | 推（被监控方主动）    |
| 存储                | 本地 TSDB        | 后端转发（Jaeger等）   |
| 多维度查询          | PromQL（强）     | 需配合 trace 后端     |
| 生态                | CNCF 毕业项目     | CNCF 沙箱            |
| 适合                | 指标+告警        | 多语言 trace        |
+---------------------+-----------------+-----------------------+
```

本项目选 Prometheus：① 个人项目跑得动；③ Grafana 同源 Prometheus + Loki；③ 阶段 8 拆分后立刻能用上。

> 🟡 诚实红线：**不写"支撑亿级指标"**——本机单机 5 秒一次抓数据，撑不撑得住说"业务跑过 1 年"是诚实的。

---

## 四、Prometheus 数据模型与抓取原理

### 4.1 数据模型

```text
一个指标 = 一个 (metric_name + label_keys + tuples of label_values) + 一个数字 + 一个时间戳
```

举例：

```text
http_requests_total{method="GET", status="2xx", tenant_id="1", path="/health"} 1234 @ 1730000000000
```

意思是：在时间戳 `1730000000000`，`GET /health` 在第 1 个租户有 `1234` 次访问。

### 4.2 抓取原理

```text
Prometheus 服务器
   │
   │  HTTP GET http://host.docker.internal:9002/metrics
   │  (每 5s 一次)
   ▼
后端应用
   │
   │  generate_latest() → text/plain
   │
   ▼
Prometheus 解析 + 写 TSDB（时段数据库）
   │
   │  后台跑 alert rules
   ▼
触发 → AlertManager → 通知
```

**为什么是拉而不是推**：

| 拉（Pull） | 推（Push） |
|---|---|
| 监控方主动——`海关查账` | 被监控方主动——`主动报账` |
| **被监控方不需要知道 Prometheus 在哪** | 需要知道 + 配 endpoint |
| Prometheus 知道自己失败不成功 | 不知道上游接没接住 |
| 多副本切换方便 | 多副本端点要重新配 |

个人项目 + 容器编排优先 → 拉模式是默认选择。

---

## 五、metrics.py 逐行解释

### 5.1 指标对象定义（4 + 1 类）

```python
from prometheus_client import Counter, Histogram, Gauge, REGISTRY as _PROM_REGISTRY  # 官方库的 3 种核心指标 + 全局注册表
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `Counter(...)` | 定义一个**单调递增**的指标——`里程表` | QPS / Token / 成本都是"只增不减"的累计量——用 Counter |
| `Histogram(...)` | 定义一个**分布**——`身高分布直方图` | 延迟是连续值，要按桶（0.1s/0.5s/1s/...）分组计数 |
| `Gauge(...)` | 定义一个**可增可减**的瞬时值——`温度计` | 配额使用率可能升也可能降（续费后回 0%） |

```python
HTTP_REQUESTS = Counter(                                              # 定义"HTTP 请求总数"指标对象
    "http_requests_total",                                              # 指标名（暴露给 Prometheus 的字段名）
    "HTTP 请求总数（按 method / status / tenant_id / path 拆）",       # 帮助文本（Grafana 里 hover 显示）
    labelnames=("method", "status", "tenant_id", "path"),              # 4 个 label key：方法/标签（方法/状态/租户/路径）
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `labelnames=("method", "status", "tenant_id", "path")` | 4 个 label 维度——`多维度统计的"行键"` | 4 个 label 组合：可以同时看"哪条路径 / 哪个租户 / 哪种状态码"的请求数 |
| 用**元组**不是列表 | label 名不可变 | Prometheus 内部用 dict，name 元组是关键字参数，hash + 结构安全 |

```python
HTTP_DURATION = Histogram(                                            # 定义"HTTP 请求延迟"直方图
    "http_request_duration_seconds",                                  # 指标名（`_seconds` 后缀是 Prometheus 约定）
    "HTTP 请求延迟（秒）",                                            # 帮助文本
    labelnames=("method", "tenant_id", "path"),                       # 3 个 label（不含 status：延迟不按状态分）
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),  # 11 个桶边界（秒）
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `_seconds` 后缀 | Prometheus 命名约定——`知道这是时间单位` | `histogram_quantile()` 自动把桶转成秒 |
| `buckets=(0.005, ..., 10.0)` | 11 个桶边界——`5ms ~ 10s` | web 请求 90% 都在 100ms 内、99% 在 1s 内；**桶切得越细 P99 越准，桶越多内存越大**——11 个是甜点 |
| 3 个 label 而不是 4 个 | 不按 status 拆——`延迟和状态码关系不大` | 4xx/5xx 延迟本身按 path 区分已 OK，省一个 label 节省存储 |

```python
LLM_TOKENS = Counter(                                                  # 定义"LLM token 消耗总数"指标
    "llm_tokens_total",                                                # 指标名
    "LLM token 消耗总数（按 model / direction 拆）",                   # 帮助文本
    labelnames=("model", "direction"),                                 # 2 个 label：模型 / 方向（输入/输出）
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `direction` label | 拆 / input 或 output | 输出 token 单价比输入贵 4 倍——**不分开没法算成本** |

```python
LLM_COST = Counter(                                                     # 定义"LLM 成本累计"指标
    "llm_cost_cny_total",                                              # 指标名（`_cny` 后缀是约定）
    "LLM 调用成本累计（元）",                                          # 帮助文本
    labelnames=("model",),                                             # 1 个 label：模型
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 不用 `tenant_id` label | 阶段 7 暂不拆租户成本 | 阶段 9 多租户 SaaS 时再加——**别提前**"凡是要" |
| 用 Counter 不用 Gauge | 成本是累计的，不会退 | 续费 / 退款由 billing 系统管，metrics 只管"计账合计" |

```python
LLM_QUOTA_RATIO = Gauge(                                               # 定义"租户配额使用率"瞬时值
    "llm_quota_used_ratio",                                            # 指标名
    "租户 LLM 配额使用率（0~1）",                                      # 帮助文本
    labelnames=("tenant_id",),                                         # 1 个 label：租户
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| Gauge 不是 Counter | 续费后会下降——`已用比例`会降 | 用 Gauge 才能描述"瞬时值" |
| 值范围 0~1 | 比例统一口径 | Grafana 配置 Y 轴 max=1 直接显示 0~100% |

### 5.2 埋点 helper 函数

```python
def http_inc(method: str, path: str, status_code: int, tenant_id: str = "anon") -> None:  # HTTP 埋点：QPS Counter + Duration Histogram 一次性记录
    """HTTP 埋点：QPS Counter + Duration Histogram 一次性记录。
    用一个 helper 把 4 个 label 的拼装集中起来——避免中间件里重复 + 拼错。"""
    status_bucket = (                                                  # ✅ 准备状态码标签值——状态码归 2xx/4xx/5xx 三类
        "2xx" if 200 <= status_code < 300                              # ✅ 200~299 → "2xx"
        else "4xx" if 400 <= status_code < 500                         # ✅ 400~499 → "4xx"
        else "5xx" if 500 <= status_code < 600                         # ✅ 500~599 → "5xx"
        else str(status_code)                                          # ✅ 其它（3xx 重定向）→ 原值（极少出现）
    )
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `status_bucket = "2xx"/"4xx"/"5xx"` | 把上百种 status code 归三类 | label 基数必须控制在百级别——**直接用 `201`、`404`、`502` 会让 label 100+ 种** |
| 3xx 单独返原值 | 重定向不常见，但偶有 304、308 | 完整度——不漏报 |

```python
    tenant_label = str(tenant_id) if tenant_id is not None else "anon"  # 租户标签准备：None 变 "anon"
    HTTP_REQUESTS.labels(method=method, status=status_bucket, tenant_id=tenant_label, path=path).inc()  # QPS Counter 自增 1
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `str(tenant_id) if tenant_id is not None else "anon"` | 没登录 / 没租户是 "anon" | Prometheus label 必须是字符串；None 会变成字符串 `"None"`（脏数据）|
| `.labels(...).inc()` | 把 4 个 label 拼成 key 查 chart 后自增 | prometheus_client 的标准姿势——`labels()` 拿到 chart，`.inc()` 改 chart |
| 不用 `inc(1)` 的显式参数 | `inc()` 默认是 1 | 99% 的请求只增 1，少量自定 2/3/0.5 时才传参 |

```python
def tokens_inc(model: str, direction: str, amount: int) -> None:        # Token 埋点：input / output 增量
    """Token 埋点：input / output 增量。"""
    LLM_TOKENS.labels(model=model or "unknown", direction=direction).inc(amount)  # 计 tokens 数 + token 数
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `model or "unknown"` | 模型名为空归 "unknown" | label 不能是空串——空串在 Grafana 里展示丑 |
| `inc(amount)` | 加 amount 个（不是 1） | tokens 一次不是 1 个——可能 200、5000 |

```python
def cost_inc(model: str, cny: float) -> None:                           # 成本埋点：累计（元）
    """成本埋点：累计（元）。"""
    LLM_COST.labels(model=model or "unknown").inc(cny)                  # 计成本 + 成本
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `inc(cny)` | 加 `cny` 元（float） | 单次成本是个小数值——0.001、0.012 |

```python
def quota_set(tenant_id: int, ratio: float) -> None:                    # 配额埋点：设置租户当前使用率
    """配额埋点：设置租户当前使用率。"""
    LLM_QUOTA_RATIO.labels(tenant_id=str(tenant_id)).set(ratio)        # 设 Gauge + 刻度
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `.set(ratio)` 不是 `.inc(ratio)` | Gauge 用 `set` 设值 | Counter 是单调增；Gauge 是变动值——API 不同 |

---

## 六、middleware/metrics.py 逐行解释

### 6.1 入口 dispatch

```python
import time                                                              # 导入时间模块——用于 perf_counter 高精度计时
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest       # 从工具注册表导入：最新指标文本格式生成器
from starlette.middleware.base import BaseHTTPMiddleware                 # 异步中间件基类
from starlette.requests import Request                                  # 请求对象
from starlette.responses import PlainTextResponse, Response             # 文本响应 + 通用响应
from app_my.core.config import settings                                 # 环境变量读取配置
from app_my.core.logging import logger, trace_id_var                     # 日志 + trace_id 上下文变量
```

```python
class PrometheusMiddleware(BaseHTTPMiddleware):                          # 自定义 HTTP 埋点中间件
    """HTTP 埋点中间件 + 暴露 /metrics 端点"""

    async def dispatch(self, request: Request, call_next):              # dispatch 入口（每条请求都走这里）
        path = request.url.path                                         # 取请求路径
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `BaseHTTPMiddleware` | starlette 的标准中间件基类 | 与项目现有中间件（rate_limit / quota / tenant）同一框架 |

```python
        if path == settings.PROMETHEUS_METRICS_PATH:                    # 如果访问的是 /metrics 端点
            return PlainTextResponse(_build_metrics_text(), media_type=CONTENT_TYPE_LATEST)  # 返回 text/plain 格式的指标文本
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 早 return | /metrics 不参与计数 | 否则 self-scrape 会污染数据——HTTP_REQUESTS 里会出现 `/metrics` 巨量 |
| `PlainTextResponse` 不是 `JSONResponse` | Prometheus 要 text/plain | Prometheus 0.0.4 文本格式是 `key{label=value,]* value` |
| `CONTENT_TYPE_LATEST` | 固定常量 `"text/plain; version=0.0.4; charset=utf-8"` | Prometheus 期望这个 Content-Type——否则报错 |

```python
        route = request.scope.get("route")                              # 从请求 scope 取 trip pattern
        path_label = getattr(route, "path", path) if route else path    # 用 pattern 不用真实 URL——避免高基数
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `request.scope.get("route")` | FastAPI 路由匹配后写入的"路径模式" | `/users/{user_id}` 这种；真实 URL `/users/456` 会让 label 基数百万 |
| `getattr(route, "path", path) if route else path` | 三元组：`route=空` → 用真实 URL；`route.path` 拿不到 → 用真实 URL | 实际路径请求从 401 之前没进路由栈，route=None——key 用 raw URL 作 fallback |
| 路径模式 vs 真实 URL | 模式基数有限（项目几十条路由） vs URL 千万级 | **label 高基数是 Prometheus 头号坑**——基线用模式几十~百 |

```python
        start = time.perf_counter()                                     # 高精度计时起点
        try:                                                            # 异常路径计 try：保证路由抛异常也能埋点 500
            response: Response = await call_next(request)               # 走下一层中间件 / 业务处理
        except Exception:                                                            # 路由抛异常
            cost_ms = (time.perf_counter() - start) * 1000               # 算耗时（毫秒）
            _handle_inc(request, path_label, 500, cost_ms)              # 埋点 500
            raise                                                        # 🚀 重新抛异常（关键 — 否则异常被吞）
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `time.perf_counter()` | 最高精度计时器 | `time.time()` 受系统时间调整；`perf_counter` 是单调时钟 |
| 乘 1000 | perf_counter 是秒，毫秒需要 * 1000 | 历史代码用 ms 比较多——延续习惯 |
| try/finally 的设计 | 异常路径也要埋 500 | 否则 500 永远记不到——**和之前"route_handler.py"设计同款** |

```python
        cost_ms = (time.perf_counter() - start) * 1000                   # 算耗时（毫秒）
        _handle_inc(request, path_label, response.status_code, cost_ms) # 埋点正常响应
        return response                                                  # 返回响应给上层中间件
```

### 6.2 公共埋点函数

```python
def _handle_inc(request: Request, path_label: str, status_code: int, cost_ms: float) -> None:  # 统一埋点：QPS Counter + Duration Histogram
    """统一埋点：QPS Counter + Duration Histogram"""
    from app_my.core.metrics import HTTP_DURATION                          # 避免循环引用
    tenant_id = getattr(request.state, "tenant_id", None)                # 从请求 state 拿租户 ID
    http_inc(method=request.method, path=path_label, status_code=status_code, tenant_id=tenant_id)  # QPS 自增
    HTTP_DURATION.labels(method=request.method, path=path_label, tenant_id=str(tenant_id or "anon")).observe(cost_ms / 1000)  # Histogram 观察耗时
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 函数内 import | 延迟 import | 中间件和 metrics 互相引用会循环——延迟到函数内 import 避免循环 |
| `request.state.tenant_id` | 从 TenantContextMiddleware 写入 | 阶段 4 已落地——本阶段只读不写 |
| `cost_ms / 1000` | 毫秒转秒 | Histogram 的 `_seconds` 后缀约定单位是秒 |
| `tenant_id or "anon"` | None 变 "anon" | label 不能 None |

### 6.3 指标文本生成

```python
def _build_metrics_text() -> bytes:                                       # 生成 Prometheus text 导出格式
    """生成 Prometheus text 导出格式"""
    try:                                                                  # try
        return generate_latest()                                          # 调用官方库生成指标文本
        # ⚠️ generate_latest() 会将所有注册的指标序列化为 Prometheus text 格式
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `generate_latest()` | 序列化为 Prometheus 0.0.4 文本 | 这是 prometheus_client 库的核心函数 |
| try 包住 | generate_latest 抛异常不致命 | metrics 端点失败要让业务不受影响——返回空文本 |

---

## 八、Loki + Promtail 的数据流封装

### 8.1 数据流

```text
FastAPI 后端
   │
   │  setup_logging() 设置 JSON formatter
   │
   ▼
stdout （每个容器一行 JSON）
   │
   │  Docker daemon 收容器 stdout
   │
   ▼
/var/lib/docker/containers/<container_id>/<container_id>-json.log
   │
   │  Promtail 读这个路径
   │
   ▼
Promtail pipeline_stages: docker:{} + json:{}
   │
   │  提取 container_name / level / logger / msg
   │  转成 Loki label
   │
   ▼
Loki 接收 → 存储到 /loki/chunks
   │
   │  LogQL 查询
   ▼
Grafana 面板显示
```

### 8.2 Promtail 配置关键字段

```yaml
scrape_configs:                                                          # 采集配置块
  - job_name: docker                                                      # job 名字 必填项
    static_configs:                                                       # 静态目标列表
      - targets: [localhost]                                              # 假目标——本身不连
        labels:                                                           # 全局 label
          job: docker                                                     # job 标签 用于查询
          __path__: /var/lib/docker/containers/*/*log                     # 文件路径——Loki 约定的反查
    pipeline_stages:                                                       # 处理流水线
      - docker: {}                                                        # 自动解析 docker JSON 字段
      - match:                                                            # 匹配条件
          selector: '{job="docker"}'                                      # 选择器：所有 docker job 的日志
          stages:                                                         # 子层流水线
            - json:                                                       # JSON 解析
                expressions:                                              # 输入字段映射
                  level: level                                            # JSON 里的 level 字段 → level label
                  logger: logger                                          # logger → logger label
                  msg: msg                                                # msg → msg label
                  trace_id: trace_id                                      # trace_id → trace_id label
            - labels:                                                    # 把提取的字段设为 label
                level:                                                    # level 作为 label 出现
                logger:                                                    # logger 作为 label
                trace_id:                                                  # trace_id 作为 label
```

| 字段 | 在做什么 | 为什么这么写 |
|---|---|---|
| `__path__` | Loki 用它定位日志文件——`特殊下划线变量` | Loki Promtail 的约定 |
| `docker: {}` | 自动把 docker JSON 的 container_name / image / tag 提出来 | 镜像配置不同——配置裸写会丢失容器标签 |
| `pipeline_stages` | 多阶段处理——`工厂流水线` | 每阶段一功能：解析 → 提取 → 转换 |
| `json: {expressions: {level: level}}` | 把 JSON 里的 `level` 字段提取出来 | 我们的 JSON formatter 已经在日志里放了 level |
| `labels: {level: ...}` | 把提取字段变 label | Loki label 是"索引字段"，不能多否则爆 |

### 8.3 Loki 配置关键字段

```yaml
auth_enabled: false                                                       # 关闭鉴权——本机使用 不开集群
schema_config:                                                            # 配置 schema
  configs:                                                                # TSDB schema
    - from: 2024-01-01                                                    # 起始日期
      store: tsdb                                                         # 存储引擎：tsdb 索引（v13 schema）
      index:                                                                # 索引配置
        prefix: index_                                                    # 索引文件名前缀
        period: 24h                                                       # 每个索引 24h 一个文件
```

| 字段 | 在做什么 | 为什么这么写 |
|---|---|---|
| `store: tsdb` | Loki 2.0+ 的新型存储引擎 | 旧版 boltdb 已停。官方推荐 tsdb |
| `period: 24h` | 索引文件按天切——`每天一个 index` | 查询时按时间范围扫对应 index |

---

## 九、Grafana 仪表盘 JSON 字段含义

### 9.1 顶层结构

```json
{
  "title": "AI Chief · HTTP 概览",                                        // 仪表盘标题
  "uid": "ai_chief_http",                                                 // 唯一 ID——URL 用
  "schemaVersion": 39,                                                  // 仪表盘 schema 版本
  "refresh": "5s",                                                       // 自动刷新间隔
  "time": {"from": "now-1h", "to": "now"},                              // 默认时间范围
  "panels": [...],                                                       // 面板数组
  "tags": ["ai_chief", "stage7"]                                          // 标签——左侧栏过滤用
}
```

### 9.2 Panel 通用结构

```json
{
  "title": "QPS by path",                                                 // 面板标题
  "type": "timeseries",                                                   // 面板类型（timeseries / logs / stat / table）
  "datasource": {"type": "prometheus", "uid": "prometheus"},              // 数据源引用
  "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},                          // 网格定位（24 列网格）
  "targets": [{"expr": "sum by (path) (rate(http_requests_total[1m]))", "refId": "A"}],  // PromQL 查询
  "fieldConfig": {"defaults": {"unit": "ms"}}                            // 字段格式化（如单位）
}
```

### 9.3 4 个仪表盘的 PromQL 详解

#### HTTP 概览

```json
{"expr": "sum by (path) (rate(http_requests_total[1m]))"}                 # 每秒请求数按路径拆
```

- `rate(metric[1m])`：1 分钟内每秒的平均增量（Prometheus 自动算）
- `sum by (path)`：按 path 聚合求和——`保留维度、压缩其它`

#### Token 成本

```json
{"expr": "sum by (direction) (rate(llm_tokens_total[5m])) * 60"}         # 每分钟 token 数按方向拆
```

- `rate(...) * 60`：rate 是"每秒"——乘 60 表达"每分钟"——面试常问
- `sum by (direction)`：按 input/output 分开——两个方向的 token 单价不同

#### 错误日志

```json
{"expr": "{job=\"docker\"} |= \"level=ERROR\""}                          # Loki LogQL：找 ERROR 日志
```

- `{job="docker"}`：标签选择器
- `|= "level=ERROR"`：日志内容过滤——`含 ERROR 字样`

---

## 十、AlertManager 规则数学与 PromQL 详解

### 10.1 4 条规则

```yaml
      # 1) 5xx 错误率 > 5% 持续 2 分钟
      - alert: HighErrorRate
        expr: sum(rate(http_requests_total{status=~"5xx"}[5m])) /
              sum(rate(http_requests_total[5m])) > 0.05
        for: 2m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `http_requests_total{status=~"5xx"}` | label 选择器 `status` 匹配 `5xx` | 状态码已归 2xx/4xx/5xx——这里精确匹配 5xx |
| `[5m]` | 5 分钟滑动窗口 | 太短抖动，太长反应慢——5 分钟是平衡 |
| `rate(...[5m])` | 5 分钟内的平均每秒增量 | rate 是 Prometheus 的"标准求导"函数 |
| `> 0.05` | 5xx 占比超 5% | 5% 是经验阈值——超过就是"问题在持续" |
| `for: 2m` | 持续 2 分钟才真告警 | 避免抖动——一次 5xx 是网络抖动，连续 2 分钟 5xx 才是真问题 |

```yaml
      # 2) P99 延迟 > 3 秒持续 5 分钟
      - alert: HighP99Latency
        expr: histogram_quantile(0.99, sum by (path, le) (rate(http_request_duration_seconds_bucket[5m]))) > 3
        for: 5m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `histogram_quantile(0.99, ...)` | 从 Histogram 桶里插值算出 P99 | Histogram 不直接存分位数——要算 |
| `sum by (path, le)` | 按 path + le（桶上界）聚合 | `le` 必留——histogram_quantile 需要桶边界 |
| `> 3` | P99 超过 3 秒 | 3s 是 web 体验的"能忍上限" |

```yaml
      # 3) Token 成本小时环比 ≥ 3 倍
      - alert: TokenCostSpike
        expr: (sum(rate(llm_cost_cny_total[1h])) * 3600) /
              (sum(rate(llm_cost_cny_total[1h] offset 1h)) * 3600 + 1) > 3
        for: 5m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `rate(...[1h]) * 3600` | 1 小时平均每秒 * 3600 = 1 小时累计 | rate 是"每秒"，乘 3600 = 一小时值 |
| `offset 1h` | 上一小时的数据——`时间索引偏移` | 比较当前 vs 上一小时 |
| `+ 1` | 防除零——`空数据时除以 1` | 上一小时没数据时不能除零 |
| `> 3` | 3 倍以上才告警 | 1.5x 可能是正常波动；3x 一定是异常 |

```yaml
      # 4) 配额耗尽
      - alert: QuotaExhausted
        expr: llm_quota_used_ratio > 0.95
        for: 1m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| Gauge 不需要 rate | 瞬时值直接比 | Gauge 是当前状态；Counter 才需要 rate |
| `> 0.95` | 95% 阈值 | 留 5% 缓冲——100% 才告警就来不及通知租户 |

---

## 十一、测试设计解释

### 11.1 8 个测试守护的断言

| 测试 | 守护的断言 | 对应的故障场景 |
|---|---|---|
| `test_http_inc_increments_counter` | 埋点 +1 | helper 写错（漏调 `.inc()` 或传错参数） |
| `test_http_inc_status_bucketing` | 4xx/5xx 归类正确 | 状态码分支写错（404 归到 5xx） |
| `test_http_inc_anon_tenant` | None → "anon" | None 变 "None"（脏数据） |
| `test_tokens_inc` | Token 增量 | tokens_inc 写错（方向混淆） |
| `test_cost_inc` | 成本累加 | cost_inc 传错单位（用了 `.inc(0.012)` 还是 `.inc(12)`） |
| `test_quota_set` | Gauge set | 用了 `.inc()` 而不是 `.set()`（Gauge API） |
| `test_metrics_endpoint_returns_prometheus_format` | /metrics 端点 200 + 含 4 指标 | 中间件没注册 / 路径配置错 |

| `test_metrics_endpoint_skips_self` | /metrics 端点不参与计数 | self-scrape 把 `/metrics` 也计进 HTTP_REQUESTS |

### 11.2 `_value.get()` 是私有 API

测试用 `Counter._value.get()` 读累计值——这 API prometheus_client 没承诺稳定。但**单测是黑盒**——只要我们的 helper 函数功能对，私有 API 怎么算都不影响业务。

为什么不用 `with` 块或 mock 库？

- `with` 块重置整个 REGISTRY，影响其它测试
- mock 库要用 `patch.object(REGISTRY, '_names_to_collectors', ...)`——复杂

权衡：`._value.get()` 简单可读，是测试 Prometheus 指标的标准做法。

---

## 十二、常见疑问

**Q1：为什么不直接用 prometheus-fastapi-instrumentator（自动埋点）？**
A：用户决策时确认"手工埋点"——理由：① 自动埋点没法不 star 减 tenant_id / path 标签；② 手工埋点粒度可控，可以选 path / 不选 path；③ 阶段 8 拆分多个服务，手动埋点代码可以直接复制。

**Q2：Loki 装不下替代为 ELK？**
A：用户决策时确认 Loki——理由：① Grafana 同源不用多装一个 Kibana；② Loki 内存约 25MB，ES 堆 16GB；③ 本项目日志量小（60 个请求量级），Loki 完全够。

**Q3：AlertManager 规则用 for: 2m 太长怎么办？**
A：生产 2m 是标准——避免抖动。**测试时改成 30s** 快速验证，验证完改回原值。

**Q4：为什么 trace 不在本阶段？**
A：用户决策时确认"沿用 LangSmith"——理由：① 阶段 4 落地 LangSmith，云端 trace 已有；② 个人项目加 Jaeger 内存开销大；④ 阶段 8 拆分多服务时如果发现 LangSmith 不够，再加 Jaeger——**不要提前"凡是要"**。

**Q5：状态码 304/308 这种重定向不常见，怎么处理？**
A：本阶段归类为 `"3xx"`（单独）。**真正不常见**——大多数路由都重定向给前端。出现重定向意味着资源缓存生效，反而是好兆头。

**Q6：仪表盘 JSON 错了怎么办？**
A：Grafana UI 会拒绝、不会崩。错误处理：① 看 `docker logs ai_chief_grafana`；② 用 `jq` 本地校验：`jq . docker/grafana/dashboards/http-overview.json`。

**Q7：Prometheus 抓取不到后端怎么办？**
A：① 看 `curl -s http://127.0.0.1:9090/api/v1/targets` → `health=down` 看 `lastError`；② 容器内 `host.docker.internal` 解不到 → Linux 加 `network_mode: host`；③ scrape_timeout 太短 → 改大到 10s。

**Q8：仪表盘能直接打开吗？**
A：Provisioning 启动时自动加载——docker logs 启动后 30s 内可见。**第一次启动慢**——Grafana 要初始化数据库。

**Q9：为什么 label 路径用 FastAPI route pattern 而不是真实 URL？**
A：高基数问题。`/users/1` `/users/2` `/users/3` ... 让 label 数量爆炸。FastAPI route pattern 是 `/users/{user_id}`——**单条 label 容纳所有用户**。

**Q10：为什么指标名带 `_total` 后缀？**
A：Prometheus 命名约定——Counter 必带 `_total`，表示"累计"；Gauge / Histogram 不带。

**Q11：测试怎么 mock metrics？**
A：本项目不用 test——helper 直接调 prometheus_client 内部 API。Prometheus 客户端是同步的、有内部锁——在 pytest 里跑没问题。**但底层的依赖（如 requests）需要 mock**。

---

## 附录 A：本阶段一句话解决与价值

```text
阶段 7 解决了什么？
  - QPS / 延迟 / 错误率 三个指标从"算出来的还是"变成"仪表盘上实时看"
  - 出事故从"边警状态"变成"实时响铃"
  - 错误排查从"grep docker logs"变成"面板点击 trace_id 看具体错误"
  - 阶段 8 拆分后能立刻验证"拆分前后指标对比"——为阶段 10 压测提供实时面板
```

面试官问"你怎样保证服务可用性"的话术：阶段 7 实测的 QPS 数字 + AlertManager 触发次数 + 人工制造 5xx 触发告警的演练过程——每个数字都有出处、每个环节都亲手验证过。

---

## 附录 B：4 个仪表盘 JSON 逐面板解释（按面板说人话）

> 本附录回答一个问题：**打开 Grafana 看到的那几个面板，每个到底在查什么、为什么要这么查。** 4 个 JSON 文件已落在 `docker/grafana/dashboards/`，你不需要手抄；这里解释每个字段。

### B.0 先说清楚"仪表盘是怎么被自动加载的"

```text
docker-compose 把两个目录挂进 grafana 容器：
  ./grafana/provisioning  ->  /etc/grafana/provisioning        （数据源 + 仪表盘"路标"）
  ./grafana/dashboards    ->  /var/lib/grafana/dashboards      （4 个 JSON 本体）

Grafana 启动时读 provisioning/datasources/datasources.yml  →  自动建好 Prometheus / Loki 两个数据源
Grafana 启动时读 provisioning/dashboards/dashboards.yml    →  知道"去 /var/lib/grafana/dashboards 找 *.json"
                                                            →  每 30s 扫一遍，有改动自动重载
```

🔴 **一个坑（本阶段已修）**：`datasources.yml` 里**必须显式写 `uid`**。如果只写 `name`，Grafana 给数据源随机生成 uid，而每个面板 JSON 里写死的是 `{"uid": "prometheus"}` / `{"uid": "loki"}`——对不上，**所有面板都会报 `Datasource prometheus was not found`**。所以要保证 `datasources.yml` 的两个 `uid` 与面板里的一字不差。

### B.1 数据源 uid 对照表

| 面板里写的 | 必须等于 datasources.yml 里的 | 类型 |
|---|---|---|
| `{"type": "prometheus", "uid": "prometheus"}` | `uid: prometheus` | Prometheus（指标） |
| `{"type": "loki", "uid": "loki"}` | `uid: loki` | Loki（日志） |

### B.2 `http-overview.json` —— HTTP 概览（4 个面板）

| 面板 | 类型 | PromQL | 在查什么（人话） |
|---|---|---|---|
| QPS by path | timeseries | `sum by (path) (rate(http_requests_total[1m]))` | 每秒有几次请求，按路由分开画。`rate([1m])`=取 1 分钟窗口，把"累计次数"换算成"每秒次数" |
| P50 / P99 by path | timeseries | `histogram_quantile(0.50|0.99, sum by (path, le) (rate(http_request_duration_seconds_bucket[1m]))) * 1000` | 延迟分位数。P99=最慢的 1% 请求有多慢。`*1000` 把秒换成毫秒。直方图指标名带 `_bucket`（Prometheus 自动生成的桶） |
| 5xx 错误率 | timeseries | `sum(rate(http_requests_total{status=~"5xx"}[5m])) / sum(rate(http_requests_total[5m]))` | 5xx 请求数 ÷ 总请求数 = 服务端错误占比。面板上画了黄线(1%)/红线(5%)阈值 |
| 4xx 错误率 by tenant | timeseries | `sum by (tenant_id) (rate(http_requests_total{status=~"4xx"}[5m])) / sum by (tenant_id) (rate(http_requests_total[5m]))` | 按租户看"客户端错误"比例——能看出哪个租户在疯狂传错参数 |

**标签怎么来的**：`http_requests_total` 的标签是 `method / status / tenant_id / path`（见 `metrics.py`）。`status` 已经被 `http_inc()` 归成 `2xx / 4xx / 5xx` 三档（不是原始 200/404/500），这样标签基数小、不会撑爆 Prometheus。

**为什么 `sum by (path)` 而不是 `sum by (path, method)`**：`by(...)` 决定"画几条线"。只按 path 拆，同一路由的 GET/POST 合成一条线，图更干净；要拆 method 时再加一个维度即可。

### B.3 `token-cost.json` —— Token 成本（4 个面板）

| 面板 | 类型 | PromQL | 在查什么（人话） |
|---|---|---|---|
| Tokens / min by direction | timeseries | `sum by (direction) (rate(llm_tokens_total[5m])) * 60` | 每分钟烧多少 token，按 input/output 分开。`rate` 是"每秒"，`*60` 才变"每分钟" |
| Cost (CNY/h) by model | timeseries | `sum by (model) (rate(llm_cost_cny_total[5m])) * 3600` | 每个模型每小时花多少元。`*3600` 把"每秒元"换成"每小时元" |
| Tokens / min by model | timeseries | `sum by (model) (rate(llm_tokens_total[5m])) * 60` | 每个模型每分钟烧多少 token——看哪个模型最费 |
| 配额使用率 by tenant | timeseries | `llm_quota_used_ratio` | Gauge 指标，每个租户当前用量 ÷ 配额（0~1）。>0.95 触发第 4 条告警 |

🔴 **一个必须记住的坑**：`rate(...)` 的结果单位是"每秒"，而人看报表习惯"每分钟 / 每小时"。`*60`、`*3600` 就是这层换算，面试常问"你面板上这个数为什么乘 60"。

🔴 **另一个坑（本阶段踩过并已修）**：早期草稿写过 `sum by (model) (rate(http_requests_total{path="/chat/stream"}[5m]))`——**错的**。`http_requests_total` 根本没有 `model` 标签，`sum by (model)` 会返回空序列（面板一片空白，也不报错，最难查）。正确做法是统计真正带 `model` 标签的 `llm_tokens_total`。**规律：`sum by (某标签)` 之前，先确认这个指标真的有这个标签**——用 `curl /metrics | grep 指标名` 看一眼标签就行。

### B.4 `error-logs.json` —— 错误日志（2 个面板）

| 面板 | 类型 | LogQL | 在查什么（人话） |
|---|---|---|---|
| ERROR 日志 | logs | `{job="docker"} \|= "ERROR"` | 从 Loki 实时拉"日志内容里含 ERROR 字样"的行 |
| WARN 日志 | logs | `{job="docker"} \|~ "(?i)WARN"` | 同上，含 WARN/Warning 的行（`~` 是正则，`(?i)` 忽略大小写） |

**LogQL 三个符号记牢**（对照上面）：
- `{job="docker"}`：**标签选择器**——先框出"哪批日志"，类似 SQL 的 `WHERE` 走索引
- `|=`：**行内含**（子串匹配，快）
- `|~`：**行内正则**（慢一点，胜在灵活）

`job="docker"` 这个标签来自 `promtail-config.yaml` 的 `scrape_configs.job_name: docker`；Promtail 抓 `/var/lib/docker/containers/*/*log` 时给每行打上它。

> 🟡 用 `|= "ERROR"` 而非 `|= "level=ERROR"`：前者只要求行里出现 `ERROR` 子串，不管日志是 `"level": "ERROR"`（JSON 冒号）还是 `level=ERROR`（logfmt 等号）都能命中，最稳。日志格式没统一前，别把过滤条件写死。

### B.5 `alerts.json` —— 告警统计（3 个面板）

| 面板 | 类型 | PromQL | 在查什么（人话） |
|---|---|---|---|
| 活跃告警数 | stat | `count(ALERTS{alertstate="firing"})` | 正在响铃的告警**有几条**（一个数字）；没告警时显示 0 |
| 告警明细 | table | `ALERTS` | 把每条告警的标签（alertname / severity / instance…）列成表格 |
| 告警状态时间线 | timeseries | `count by (alertstate) (ALERTS)` | firing / pending 各自的条数随时间变化 |

**`ALERTS` 是什么**：不是你自己埋的点，是 **Prometheus 内置生成的**一个特殊指标——只要 `alerts.yml` 里写了规则，Prometheus 就会持续输出每条规则的状态（`alertstate="firing"` / `"pending"`）。所以这个面板是"白捡的"，不用改任何业务代码。

**`count(...)` vs 直接 `ALERTS`**：直接查 `ALERTS` 会返回 N 条序列（每条告警一条），stat 面板不知道显示哪个；`count()` 把它压成一个标量数字，stat 面板才显示得出来。

### B.6 面板 JSON 里几个通用字段（每个面板都有）

| 字段 | 作用 | 常见取值 |
|---|---|---|
| `type` | 面板类型 | `timeseries`（折线）/ `logs`（日志流）/ `stat`（大数字）/ `table`（表格） |
| `datasource` | 用哪个数据源 | 见 B.1 |
| `gridPos` | 24 列网格里的位置 | `{"h":8,"w":12,"x":0,"y":0}` = 高 8 宽 12，第 0 列第 0 行 |
| `targets[].expr` | 查询语句 | PromQL（指标）或 LogQL（日志） |
| `targets[].legendFormat` | 图上每条线的名字 | `{{path}}` 取标签值填进去 |
| `fieldConfig.defaults.unit` | 数值单位 | `ms` / `percentunit`（0.05 显示成 5%）/ `currencyCNY` / `reqps` |
| `options.legend` | 图例样式 | `displayMode: table` + `calcs: ["mean","max"]` 显示均值/峰值 |
| `refresh` | 自动刷新间隔 | `5s` / `10s` |

> 🟡 **`gridPos` 的 x 只能在 0~12（因为 w=12）之间**：一排放两个 w=12 的面板，第二个的 x 必须是 12。写错 x 会重叠。满宽面板是 `w: 24`，x 只能是 0。
