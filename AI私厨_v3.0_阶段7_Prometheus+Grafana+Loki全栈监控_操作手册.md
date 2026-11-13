# AI 私厨 v3.0 阶段 7 操作手册 — Prometheus + Grafana + Loki 全栈可观测

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
- [附录 C：PowerShell 5.1 命令速查表（bash → PowerShell 等价替换）](#附录-cwindows-终端命令速查表bash--powershell-等价替换) —— 🔴 **用 PowerShell 执行报错时先查这里**

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
# 🔴 没有 head，别照抄 bash 那条。用 ConvertFrom-Json 只把规则名挑出来
(curl.exe -s http://127.0.0.1:9090/api/v1/rules | ConvertFrom-Json).data.groups |
  ForEach-Object { $_.rules } |
  Select-Object name, state |
  Format-Table -AutoSize
```

**预期**：4 行，形如

```
name            state
----            -----
HighErrorRate   inactive
HighP99Latency  inactive
TokenCostSpike  inactive
QuotaExhausted  inactive
```

刚加载完是 `inactive`（还没触发）；第十四节制造 5xx 后这条会变成 `firing`。

> 🟡 **如果一条规则都没有**（表格空白）：说明 `prometheus.yml` 的 `rule_files:` 被注释了，或 compose 里 `alerts.yml` 的挂载行被注释了 → 回到第八节步骤 3 / 7.2 检查（本项目已踩过这个坑）。

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

**Git Bash：**
```bash
.venv3/Scripts/python.exe -c "
from app_my.core.metrics import HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO
print('all metrics defined:', [m._name for m in [HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO]])
"
```

**PowerShell 5.1：**

🔴 **不要在 PowerShell 里粘贴上面这段跨行的 `python -c "..."`**——PowerShell 控制台里**每敲一次回车就立即执行一行**，三行代码会被当成三条命令，第一行就报「缺少终止符 `"`」。

✅ **PowerShell 请写成单行**（用分号分隔语句）：

```powershell
& ".venv3\Scripts\python.exe" -c "from app_my.core.metrics import HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO; print([m._name for m in [HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO]])"
```

✅ **或者更稳：写成一个临时 .py 文件再跑**（推荐，避免所有引号/编码坑）：

```powershell
# ① 写文件（Out-File 默认 UTF-8，中文不会乱码）
@'
from app_my.core.metrics import HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO
print([m._name for m in [HTTP_REQUESTS, HTTP_DURATION, LLM_TOKENS, LLM_COST, LLM_QUOTA_RATIO]])
'@ | Out-File -Encoding utf8 _check_metrics.py

# ② 跑
& ".venv3\Scripts\python.exe" _check_metrics.py

# ③ 删掉临时文件
Remove-Item _check_metrics.py
```

**预期**：打印 `['http_requests_total', 'http_request_duration_seconds', 'llm_tokens_total', 'llm_cost_cny_total', 'llm_quota_used_ratio']`。

> 🟡 PowerShell 里 `@'...'@` 是「here-string」（原样字符串），**里面的单引号、反斜杠都不需要转义**，是写多行 Python 最省心的办法。但结束的 `'@` 必须**单独一行、顶格写、后面不能有任何字符**。

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
Start-Process -FilePath ".\.venv3\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","9002" `
  -RedirectStandardOutput "backend.log" -RedirectStandardError "backend.err" `
  -WindowStyle Hidden
Start-Sleep -Seconds 8
curl.exe -s http://127.0.0.1:9002/health
```

> 🔴 **PowerShell 5.1 里绝对不能写 `nohup ... *> backend.log &`**（本手册早期版本写错过，会连报三个错）：
> 1. `nohup` 是 Git Bash 的命令，**PowerShell 里根本不存在** → 报「无法将"nohup"识别为 cmdlet、函数、脚本文件或可运行程序的名称」；
> 2. `*>`（合并标准输出与错误流重定向）是 **PowerShell 6.0 才引入**的，PowerShell 5.1 不认 → 解析失败；
> 3. `&` 在 PowerShell 里是「调用运算符」，**不是后台运行符**（后者是 bash 语义）→ 整行语法错。
>
> ✅ 正确做法就是上面的 `Start-Process`——它才是 PowerShell 的"后台起进程"。`-WindowStyle Hidden` 让它后台跑不弹窗；`-RedirectStandardOutput` / `-RedirectStandardError` 把日志落成两个文件（**PowerShell 5.1 不允许两个流重定向到同一个文件**，必须写成 `backend.log` 和 `backend.err` 两个）。
>
> 🟡 **更省事的办法**：直接在 PyCharm / VS Code 点运行按钮启动 `main.py`——但**必须确认选的是 `.venv3` 解释器**，否则 `prometheus_client` 会 ModuleNotFoundError。
> 🟡 看后端日志：Git Bash 用 `tail -f backend.log`；PowerShell 用 `Get-Content backend.log -Wait -Tail 20`。
> 🟡 命令行末尾的 `` ` ``（反引号）是 PowerShell 的**续行符**，后面**不能有任何空格**，否则续行失效。

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
# 🔴 不要照抄 Git Bash 那条：PowerShell 5.1 没有 grep / head，
#    且 `python` 要写成 `python.exe`（或直接用 .venv3 的解释器）
(curl.exe -s http://127.0.0.1:9090/api/v1/targets | ConvertFrom-Json).data.activeTargets |
  Select-Object @{n='job';e={$_.labels.job}}, health, lastError |
  Format-Table -AutoSize
```

**预期**：看到三行，形如

```
job                health lastError
---                ------ ---------
ai_chief_backend   up
prometheus         up
alertmanager       up
```

`ai_chief_backend` 的 `health=up` 且 `lastError` 为空（绿了 → Prometheus 已能拉到后端）。

> 🟡 **只想看后端这一个目标时**，在末尾管道加过滤：
> ```powershell
> ... | Where-Object { $_.job -eq 'ai_chief_backend' } | Format-Table -AutoSize
> ```

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

**PowerShell 5.1：**
```powershell
# 🔴 两个坑：
#   ① 续行符是反引号 ` 不是反斜杠 \（bash 才是 \）
#   ② PowerShell 5.1 把单引号原样传给原生命令，curl.exe 收到的 body 会带着外层引号 → 报 JSON 解析错
#      最稳的做法：把 JSON 放进一个变量，再用双引号包裹（内部的 " 用 \" 转义）
$body = '{"message": "test 500 trigger"}'
curl.exe -s -X POST http://127.0.0.1:9002/chat/stream `
  -H "Content-Type: application/json" `
  -d $body
```

> 🟡 **如果上面报 `{"detail":"There was an error parsing the body"}`**：那是 PowerShell 5.1 传中文/引号给原生命令的经典编码坑，改用下面这个更保险的写法（先把 body 写成文件，再让 curl 读文件）：
> ```powershell
> '{"message": "test 500 trigger"}' | Out-File -Encoding ascii _body.json
> curl.exe -s -X POST http://127.0.0.1:9002/chat/stream -H "Content-Type: application/json" -d "@_body.json"
> Remove-Item _body.json
> ```

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
```powershell
cd F:\pycharm_aiprogram\ai_chief
git status -sb
```

**预期**：看到 1 个 modified（`docker/docker-compose.v3.yml` / `app_my/core/config.py` / `app_my/core/token_billing.py` / `main.py` / `pyproject.toml` / `.env.example` / `.env`）+ 19 个 untracked（新建文件）。

> 🔴 **提交前务必确认 `.venv3/` 不在这个列表里**——本机 `.gitignore` 只忽略了 `.venv`、没有 `.venv3`，直接 `git add -A` 会把整个虚拟环境（几万个文件）提交进仓库。看到 `.venv3/` 就先补 `.gitignore`（详见《阶段7 最终完整版》第 4 章）。

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
| 🔴 PowerShell 里 `nohup ... *> log &` 报「无法识别 nohup」/ 语法错 | `nohup`(bash 命令) + `*>`(PS6+ 才有) + `&`(PS 里是调用符不是后台符)，三样 PowerShell 5.1 全不支持 | 改用 `Start-Process -FilePath ".\.venv3\Scripts\python.exe" -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","9002" -RedirectStandardOutput backend.log -RedirectStandardError backend.err -WindowStyle Hidden`（见第十二节步骤 3） |
| PowerShell 里 `grep` / `head` / `stat` / `&&` 报「不是 cmdlet 名称」 | 这些是 Linux 外部命令，PowerShell 里不存在 | 查**附录 C 的替换表**：`grep`→`Select-String`、`head`→`Select-Object -First`、`&&`→`if ($?) { }` |
| PowerShell 里 `curl -s ...` 报「找不到接受实际参数"-s"的位置形式参数」 | `curl` 被解析成 `Invoke-WebRequest` 的别名 | 一律写成 `curl.exe`（带 .exe） |
| PowerShell 里 `.venv3\Scripts\python.exe` 报「无法识别」 | 路径以 `.` 开头时，PowerShell 需要调用运算符 | 写成 `& ".venv3\Scripts\python.exe" ...` |
| PowerShell 里粘贴多行 `python -c "..."` 报「字符串缺少终止符」 | 控制台逐行执行，三行被拆成三条命令 | 改单行（分号分隔）；或用 here-string `@'...'@` 写成 .py 文件再跑（见第九节步骤 3） |
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

**Git Bash：**
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

**PowerShell 5.1：**
```powershell
cd F:\pycharm_aiprogram\ai_chief
# 🔴 bash 的 for/do/done + stat -c%s 在 PowerShell 里全是语法错误，用下面这段
foreach ($f in @(
  "docker\prometheus\prometheus.yml",
  "docker\prometheus\alerts.yml",
  "docker\alertmanager\alertmanager.yml",
  "docker\loki\loki-config.yaml",
  "docker\promtail\promtail-config.yaml")) {
  $i = Get-Item $f -Force -ErrorAction SilentlyContinue
  if     ($null -eq $i)        { "MISSING  <- $f" }
  elseif ($i.PSIsContainer)    { "DIR      <- $f" }
  else                         { "FILE(" + $i.Length + "B) <- $f" }
}
```

预期：5 行全是 `FILE(大于 0B)`。出现 `DIR` 或 `FILE(0B)` 都会让容器起不来（见第十八节 `not a directory` 专条）。

- [ ] **`docker ps` 看 5 个容器都是 Up**

```bash
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
```

预期：5 行全是 `Up`。

### B. 端点层

- [ ] **`/metrics` 端点返回 200 + 含 4 个指标**

**Git Bash：**
```bash
curl -s http://127.0.0.1:9002/metrics | grep -E "^(http_requests_total|http_request_duration_seconds|llm_tokens_total|llm_cost_cny_total)" | head -10
```

**PowerShell 5.1：**
```powershell
# 🔴 PowerShell 没有 grep / head。等价写法：Select-String 负责"筛"，Select-Object -First 负责"截断"
(curl.exe -s http://127.0.0.1:9002/metrics) -split "`n" |
  Select-String -Pattern "^(http_requests_total|http_request_duration_seconds|llm_tokens_total|llm_cost_cny_total)" |
  Select-Object -First 10
```

预期：4 行 `# HELP ...` + 几个 `http_requests_total{...} 0`。

- [ ] **Prometheus 抓到了后端**

**Git Bash：**
```bash
curl -s http://127.0.0.1:9090/api/v1/targets | python -m json.tool | grep -E "job|health" | head
```

**PowerShell 5.1：**
```powershell
(curl.exe -s http://127.0.0.1:9090/api/v1/targets | ConvertFrom-Json).data.activeTargets |
  Select-Object @{n='job';e={$_.labels.job}}, health, lastError |
  Format-Table -AutoSize
```

预期：`ai_chief_backend` 的 `health=up`、`lastError` 为空。

- [ ] **Grafana 4 个仪表盘加载成功**

**Git Bash：**
```bash
curl -s http://127.0.0.1:3300/api/search?query=AI%20Chief
```

**PowerShell 5.1：**
```powershell
# Grafana 的 /api/search 需要登录，用 -u 传账密（Git Bash 那条省略了，实际也要）
(curl.exe -s -u admin:admin "http://127.0.0.1:3300/api/search?type=dash-db" | ConvertFrom-Json) |
  Select-Object title, uid | Format-Table -AutoSize
```

预期：返回 4 个仪表盘（HTTP 概览 / Token 成本 / 错误日志 / 告警统计）。

### C. 指标层

- [ ] **`http_requests_total` 自增**

**Git Bash：**
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

**PowerShell 5.1：**
```powershell
# 🔴 多行 python -c 在 PowerShell 控制台会被逐行执行、第一行就报错。
#    这里用 here-string 写成文件再跑，最稳。
@'
import urllib.request
for _ in range(5):
    urllib.request.urlopen("http://127.0.0.1:9002/health").read()
body = urllib.request.urlopen("http://127.0.0.1:9002/metrics").read().decode()
print([l for l in body.split("\n") if "http_requests_total{" in l and "/health" in l][:3])
'@ | Out-File -Encoding utf8 _check_inc.py

& ".venv3\Scripts\python.exe" _check_inc.py
Remove-Item _check_inc.py
```

预期：3 行带 `/health` 的 `http_requests_total{...}` 行，值 > 0。

> 🟡 PowerShell 版刻意**不用 `requests`**、改用标准库 `urllib`——少一个第三方依赖就少一处 `ModuleNotFoundError` 的风险。

### D. 告警层

- [ ] **临时制造 5xx 触发告警**

按第十四节步骤 1 的方式：临时改 `for: 30s` + 临时 `/debug/500` 路由 + 触发。

预期：AlertManager UI（`:9093`）左侧栏 Alerts 列表里有 `HighErrorRate` firing。

- [ ] **验证完恢复告警规则原值 + 删除 `_debug.py`**

**Git Bash：**
```bash
grep -E "for: 30s|for: 2m" docker/prometheus/alerts.yml
```

**PowerShell 5.1：**
```powershell
Select-String -Path docker\prometheus\alerts.yml -Pattern "for: (30s|2m)"
```

预期：只看到 `for: 2m`（绿了 → 原值恢复了）。看到 `for: 30s` 说明**测试阈值没改回去**，生产环境会乱响。

### F. 测试层

- [ ] **pytest 8 个新测试通过**

**Git Bash：**
```bash
.venv3/Scripts/python.exe -m pytest tests/unit/test_metrics.py -v
```

**PowerShell 5.1：**
```powershell
# 🔴 .venv3 以点开头，PowerShell 里必须用 & 调用，否则报"无法识别"
& ".venv3\Scripts\python.exe" -m pytest tests\unit\test_metrics.py -v
```

预期：8 passed。

- [ ] **全量 pytest 通过**

**Git Bash：**
```bash
.venv3/Scripts/python.exe -m pytest -q
```

**PowerShell 5.1：**
```powershell
& ".venv3\Scripts\python.exe" -m pytest -q
```

预期：尾部 `91 passed in X.XXs`。

### G. 提交层

- [ ] **分支已 commit 且 push**

**双终端同一条命令：**
```bash
git log --oneline -5
git status
```

预期：最新 commit 是 `feat(v3-stage7): Prometheus+Grafana+Loki 全栈可观测`；`git status` 干净。

> 🔴 **提交前先确认 `.venv3/` 没被 `git add` 进去**：本机 `.gitignore` 只写了 `.venv`、没写 `.venv3`，所以**千万别直接 `git add .`**。用 `git status -sb` 看一眼，如果列表里有 `.venv3/` 的行，先把 `.venv3/` 加进 `.gitignore` 再提交（详见《阶段7 最终完整版》第 4 章）。

### H. 防漏项

- [ ] **没动阶段 6 的代码**（除非改 token_billing 加 metrics 写入 + 改 pyproject.toml 加 prometheus_client）

**双终端同一条命令：**
```bash
git diff feat/v3-stage6..feat/v3-stage7 --stat
```

预期：除了 `app_my/core/token_billing.py` / `main.py` / `app_my/core/config.py` / `docker/docker-compose.v3.yml` / `pyproject.toml` / `.env*`，其它文件没被改。

- [ ] **`_debug.py` 不在项目里**

**Git Bash：**
```bash
ls app_my/api/_debug.py 2>/dev/null && echo "警告：_debug.py 还在！" || echo "OK"
```

**PowerShell 5.1：**
```powershell
# 🔴 PowerShell 5.1 不支持 && / ||（那是 PowerShell 7+ 才有的），要用 if/else
if (Test-Path app_my\api\_debug.py) { "警告：_debug.py 还在！" } else { "OK" }
```

预期：`OK`。

---

> **下阶段预告**：阶段 8（异步任务 + WebSocket 推送）会用到本阶段埋的 `http_requests_total{tenant_id=...}`、`llm_cost_cny_total` 等指标来验证"任务化前后指标对比"。

---

## 附录 C：PowerShell 5.1 命令速查表（bash → PowerShell 等价替换）

> 🎯 **这一节是专门为你"用 PowerShell 终端执行手册命令报错"准备的**。阶段 7 手册里的命令最初按 Git Bash 习惯写，很多在 PowerShell 5.1 里跑不了。**以后碰到报错，先来这里查对应的替换写法。**

### C.1 一图看懂：为什么会报错

Git Bash 和 PowerShell 是**两套完全不同的命令语言**，只是都能在 Windows 上跑：

| | Git Bash | PowerShell 5.1 |
|---|---|---|
| 出身 | Linux/macOS 的 shell | 微软专门为 Windows 写的 |
| 命令来源 | 外部可执行文件（`/usr/bin/grep` 等） | 内置 cmdlet（`Get-ChildItem` 等） |
| 管道里传的是 | **纯文本** | **对象**（有属性、可以点出来） |
| 续行符 | `\`（反斜杠） | `` ` ``（反引号） |
| 后台运行 | `命令 &` | `Start-Process` |

所以 `grep`、`head`、`stat`、`nohup` 这些**在 PowerShell 里压根不存在**——不是你敲错了，是它们本来就没有。

### C.2 逐条替换表（照着换就行）

| 你想做的事 | Git Bash（❌ PowerShell 跑不了） | PowerShell 5.1（✅ 用这个） |
|---|---|---|
| 在文本里搜关键字 | `grep -E "job\|health"` | `Select-String -Pattern "job\|health"` |
| 只看前 N 行 | `\| head -10` | `\| Select-Object -First 10` |
| 只看后 N 行 | `\| tail -20` | `\| Select-Object -Last 20` |
| 实时追日志 | `tail -f backend.log` | `Get-Content backend.log -Wait -Tail 20` |
| 看文件大小 | `stat -c%s 文件` | `(Get-Item 文件).Length` |
| 判断文件/目录 | `[ -d "$f" ]` / `[ -f "$f" ]` | `(Get-Item $f).PSIsContainer`（`$true`=目录） |
| 遍历一组路径 | `for f in a b c; do ... done` | `foreach ($f in @("a","b","c")) { ... }` |
| 条件成功才执行 | `命令 && echo ok` | **不支持 `&&`** → 用 `if ($?) { echo ok }` |
| 失败才执行 | `命令 \|\| echo fail` | **不支持 `\|\|`** → 用 `if (-not $?) { echo fail }` |
| 判断文件存在 | `ls x 2>/dev/null && ... \|\| ...` | `if (Test-Path x) { ... } else { ... }` |
| 后台起进程 | `nohup 命令 > log 2>&1 &` | `Start-Process -FilePath "..." -ArgumentList "..." -WindowStyle Hidden` |
| 合并输出+错误到一文件 | `命令 > log 2>&1` | **不支持 `*>`（PS6+ 才有）** → 分开：`-RedirectStandardOutput a.log -RedirectStandardError a.err` |
| 访问 HTTP 接口 | `curl -s URL` | `curl.exe -s URL`（🔴 **必须带 `.exe`**） |
| 解析 JSON | `curl ... \| python -m json.tool` | `(curl.exe -s URL \| ConvertFrom-Json)` |
| 建多级目录 | `mkdir -p a/b/c` | `New-Item -ItemType Directory -Force -Path a\b\c` |
| 删文件/目录 | `rm -rf x` | `Remove-Item -Recurse -Force x` |
| 等 N 秒 | `sleep 3` | `Start-Sleep -Seconds 3` |
| 跑 Python | `.venv3/Scripts/python.exe x.py` | `& ".venv3\Scripts\python.exe" x.py`（🔴 **路径以 `.` 开头必须加 `&`**） |

### C.3 三个最容易翻车的点（单独说）

**① `curl` 一定要写 `curl.exe`**

PowerShell 5.1 里 `curl` 是 `Invoke-WebRequest` 这个 cmdlet 的**别名**，两者参数完全不一样。你写 `curl -s http://...` 会报：

```
Invoke-WebRequest : 找不到接受实际参数“-s”的位置形式参数。
```

加上 `.exe` 才是调用真正的 curl 程序。

**② 多行 `python -c "..."` 别直接粘贴**

PowerShell 控制台**敲一次回车就执行一行**，三行 Python 会被当成三条命令，第一行就报「字符串缺少终止符 `"`」。
**解决办法**：用 here-string 写成文件再跑：

```powershell
@'
print("第一行")
print("第二行")
'@ | Out-File -Encoding utf8 _tmp.py
& ".venv3\Scripts\python.exe" _tmp.py
Remove-Item _tmp.py
```

> `@'` 开头、`'@` 结尾。结束的 `'@` 必须**单独一行、顶格**、后面不能有空格。

**③ 传给 curl 的 JSON body 会带引号**

PowerShell 5.1 把单引号内容**原样**传给原生程序，curl.exe 收到的 body 带着外层引号，服务端就报 JSON 解析错。
**解决办法**：写进文件再让 curl 读（`@文件名` 是 curl 的语法，表示"从文件读"）：

```powershell
'{"message": "hello"}' | Out-File -Encoding ascii _body.json
curl.exe -s -X POST http://127.0.0.1:9002/xxx -H "Content-Type: application/json" -d "@_body.json"
Remove-Item _body.json
```

### C.4 一条命令同时看容器状态（最常用，背下这条）

```powershell
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
```

> 🟡 `docker` / `docker compose` / `git` 是真正的 .exe 程序，**在两种终端里写法完全一样**，不用改。需要改的只有上表里那些 `grep`/`head`/`&&` 之类。