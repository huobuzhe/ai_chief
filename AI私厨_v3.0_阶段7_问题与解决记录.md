# AI 私厨 v3.0 · 阶段 7 问题与解决记录

> **阶段**：7 / 10 —— Prometheus + Grafana + Loki 全栈可观测
> **分支**：`feat/v3-stage7`　｜　**收官日期**：2026-10-15
> **本阶段产出**：容器 5 个 ｜ 配置文件 9 个 ｜ 代码改动 5 处 ｜ 单测 8 个 ｜ 验证脚本 3 个
> **共记录问题 15 个** —— 其中 **手册自身缺陷 12 个**（照着手册做必然踩坑的那类）

---

## 目录

- [一、一分钟结论](#一一分钟结论)
- [二、背景](#二背景)
- [三、问题总览](#三问题总览)
- [四、问题详情](#四问题详情)
  - [问题 1　起容器顺序倒置，触发 not a directory（变体一）](#问题-1起容器顺序倒置触发-not-a-directory变体一)
  - [问题 2　旧容器缓存了目录挂载类型，文件明明正常仍报 not a directory（变体二）](#问题-2旧容器缓存了目录挂载类型文件明明正常仍报-not-a-directory变体二)
  - [问题 3　Loki 无限重启：配置漏了 object_store](#问题-3loki-无限重启配置漏了-object_store)
  - [问题 4　Prometheus 抓后端 401：中间件挂载顺序错](#问题-4prometheus-抓后端-401中间件挂载顺序错)
  - [问题 5　4 条告警规则一条没加载：两处被注释](#问题-54-条告警规则一条没加载两处被注释)
  - [问题 6　Grafana 健康端点写错](#问题-6grafana-健康端点写错)
  - [问题 7　悬空引用说明手册附录 B](#问题-7悬空引用说明手册附录-b)
  - [问题 8　数据源缺 uid，所有仪表盘报 Datasource not found](#问题-8数据源缺-uid所有仪表盘报-datasource-not-found)
  - [问题 9　token-cost.json 的 JSON 根本解析不了](#问题-9token-costjson-的-json-根本解析不了)
  - [问题 10　token-cost.json 用错标签，面板静默空白](#问题-10token-costjson-用错标签面板静默空白)
  - [问题 11　手册调用了不存在的函数 get_quota_status](#问题-11手册调用了不存在的函数-get_quota_status)
  - [问题 12　验证脚本期望值大小写错](#问题-12验证脚本期望值大小写错)
  - [问题 13　国内拉不到镜像](#问题-13国内拉不到镜像)
  - [问题 14　docker compose run 残留一次性容器](#问题-14docker-compose-run-残留一次性容器)
  - [问题 15　收官发现：提交不完整 + gitignore 漏项 + 临时文件未删](#问题-15收官发现提交不完整--gitignore-漏项--临时文件未删)
- [五、修改清单总表](#五修改清单总表)
- [六、经验教训](#六经验教训)

---

## 一、一分钟结论

阶段 7 最终 **83 → 91 passed**、端到端验证 **11/11 通过**、5 个容器全部 `Up`、4 条告警规则在线、4 个仪表盘自动加载。

但整个过程**不是一次做成的**：先在"起容器"这一步被 `not a directory` 拦住，接着 Loki 无限重启、Prometheus 抓后端 401、告警规则一条不生效、仪表盘全部找不到数据源……**前后修了 15 个问题，其中 12 个是我写的手册本身有缺陷**——也就是说，如果没有人替你把这些坑填掉，照着手册一步步做是**必然失败的**。

三个最该记住的结论：

1. **顺序即正确性**。本阶段两个"看起来完全无关"的故障，根因都是顺序：bind mount 的"先写文件、后起容器"，中间件的"后 add 的更靠外层"。
2. **容器 Up ≠ 功能通**。本阶段 3 个最隐蔽的问题（401、uid 不匹配、rule_files 被注释）全部是"容器跑得好好的、但功能不通"，而且其中 2 个**不报任何错**（面板静默空白）。
3. **凡是"参见/调用/引用"的地方，都必须落到真实存在的东西上**。本阶段踩了 3 次同类坑：悬空的"附录 B"、不存在的 `get_quota_status()`、指标上不存在的 `model` 标签。

---

## 二、背景

### 阶段 7 要做什么

给已经跑通 1~6 阶段的 AI 私厨加上**全栈可观测**：

- **指标**：Prometheus 抓后端 `/metrics`，看 QPS / 延迟 P50-P99 / 错误率 / LLM Token 成本 四类核心指标（标签含 `tenant_id`）
- **仪表盘**：Grafana 4 个（HTTP 概览 / Token 成本 / 错误日志 / 告警统计），靠 provisioning 自动加载
- **告警**：4 条规则（5xx 错误率 > 5% / P99 > 3s / Token 成本小时突增 3x / 配额耗尽），触发进 AlertManager
- **日志**：Loki 存 + Promtail 采集（抓 Docker 容器 JSON 日志）
- **Trace**：沿用云端 LangSmith，不新增容器
- **埋点方式**：`prometheus_client` 官方库 + 中间件层手工埋点

### 为什么"手册缺陷"占比这么高

阶段 7 的特点是**配置面极宽**：5 个容器、9 个配置文件、4 份仪表盘 JSON、跨 6 个代码文件接线。这类"胶水阶段"的正确性不体现在算法里，而体现在**每一个字面量都对不对**——uid 对不对得上、端点路径有没有写错、标签集有没有这个键、yaml 少不漏一行。任何一处对不上，表现往往是"静默失效"而非报错。

所以本记录的问题主体是"配置与引用的一致性缺陷"，而不是"代码逻辑 bug"。

### 排查手段（本次实际用到的）

```bash
# 1. 看容器真实状态与日志（不看"以为"，看"实际"）
docker compose -f docker/docker-compose.v3.yml ps
docker logs ai_chief_loki --tail 30

# 2. 配置类容器：起之前先用自带的校验器验配置
docker compose -f docker/docker-compose.v3.yml run --rm --no-deps loki \
  -config.file=/etc/loki/loki-config.yaml -verify-config
docker exec ai_chief_prometheus promtool check config /etc/prometheus/prometheus.yml
docker exec ai_chief_prometheus promtool check rules  /etc/prometheus/alerts.yml

# 3. 端点类：直接 curl，看真实返回
curl -s http://127.0.0.1:9090/api/v1/targets      # Prometheus 抓了谁、通不通
curl -s http://127.0.0.1:9090/api/v1/rules        # 告警规则加载没有
curl -s -u admin:admin http://127.0.0.1:3300/api/datasources
curl -s -u admin:admin "http://127.0.0.1:3300/api/search?type=dash-db"

# 4. 宿主机侧：判断每个挂载源到底是"文件"还是"目录"
for f in docker/prometheus/prometheus.yml docker/loki/loki-config.yaml ...; do
  [ -d "$f" ] && echo "DIR     $f" || { [ -f "$f" ] && echo "FILE $f" || echo "MISSING $f"; }
done
```

---

## 三、问题总览

| # | 问题 | 类型 | 严重度 | 根因一句话 | 状态 |
|---|---|---|---|---|---|
| 1 | `not a directory`（变体一） | 手册缺陷 | 🔴 高 | 起容器排在了写配置**之前**，Docker 自动建同名目录顶替 | ✅ 已修（手册顺序重排） |
| 2 | `not a directory`（变体二） | 手册缺陷 | 🔴 高 | 旧容器缓存了"目录"挂载类型，`up -d` 只启动不重建 | ✅ 已修（`rm -sf` 重建） |
| 3 | Loki 无限 `Restarting` | 手册缺陷 | 🔴 高 | `loki-config` 漏 `object_store: filesystem` | ✅ 已修（+ `-verify-config` 验证） |
| 4 | Prometheus 抓后端 401 | 手册缺陷 | 🔴 高 | `MetricsMiddleware` 挂在 Auth **内侧**，拦截代码永不执行 | ✅ 已修（顺序对调） |
| 5 | 告警规则 0 条 | 工作区残留 | 🔴 高 | `rule_files:` 与 `alerts.yml` 挂载**两处都被注释** | ✅ 已修 |
| 6 | Grafana 健康端点 401 | 手册缺陷 | 🟡 中 | 写成 `/api/healthz`，实际是 `/api/health` | ✅ 已修 |
| 7 | 悬空引用"附录 B" | 手册缺陷 | 🟡 中 | 操作手册引用了根本不存在的一节 | ✅ 已修（补附录 B） |
| 8 | 仪表盘全报 Datasource not found | 手册缺陷 | 🔴 高 | 数据源没写 `uid`，与面板里写死的 uid 对不上 | ✅ 已修 |
| 9 | JSON 无法解析 | 手册缺陷 | 🔴 高 | 内层双引号未转义 | ✅ 已修（+ 批量 json 校验） |
| 10 | Token 面板静默空白 | 手册缺陷 | 🟡 中 | 查了指标上不存在的 `model` 标签 | ✅ 已修 |
| 11 | 调用了不存在的函数 | 手册缺陷 | 🔴 高 | `get_quota_status()` 实际不存在 | ✅ 已修（改用 `check_quota`） |
| 12 | 验证脚本误报 FAIL | 手册缺陷 | 🟢 低 | 期望值大小写写错（`ready.` vs `Ready.`） | ✅ 已修 |
| 13 | 镜像拉不动 | 环境 | 🟡 中 | 国内镜像源停服 | ✅ 已解决（换源） |
| 14 | 残留一次性容器 | 操作 | 🟢 低 | `docker compose run` 留下的 `*-run-*` 容器 | ✅ 已清理 |
| 15 | 提交不完整 / `.venv3` 未忽略 / 临时文件未删 | 收官遗留 | 🔴 高 | 提交时只 add 了改动文件、没 add 新增文件 | ⏳ 待补（见最终完整版第 4 章） |

> **类型说明**：`手册缺陷` = 我写的操作/说明手册本身有错，用户照着做必然踩坑；`工作区残留` = 之前排错时留下的临时改动没复原；`环境` = 本机 Docker/网络环境；`收官遗留` = 收官时发现的上交完整性问题。

---

## 四、问题详情

### 问题 1　起容器顺序倒置，触发 not a directory（变体一）

**现象**

```
Error response from daemon: error mounting "/run/desktop/mnt/host/f/pycharm_aiprogram/ai_chief/docker/prometheus/alerts.yml"
to rootfs at "/etc/prometheus/alerts.yml": ... flags=MS_BIND|MS_REC: not a directory:
Are you trying to mount a directory onto a file (or vice-versa)?
```

**定位**

compose 里写的是"**文件对文件**"挂载（`./prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro`）。而手册把「7.3 起容器」排在了第八节「写这 6 个配置文件」**前面**。

宿主机上没有这个文件时，Docker Desktop **不会报"文件不存在"**——它会**自动创建一个同名目录**顶上。于是"目录"被挂到容器里本该是"文件"的位置 → `not a directory`。

排查：

```bash
for f in docker/prometheus/prometheus.yml docker/prometheus/alerts.yml docker/alertmanager/alertmanager.yml \
         docker/loki/loki-config.yaml docker/promtail/promtail-config.yaml; do
  if [ -d "$f" ]; then echo "DIR     <- $f"; elif [ -f "$f" ]; then echo "FILE($(stat -c%s "$f")B) <- $f"; else echo "MISSING <- $f"; fi
done
```

结果：5 个路径全部存在但**都是 0 字节空文件**（说明配置根本没写就起容器了）。

**解决**

把手册的顺序理顺（**先写配置、再起容器**）：

1. 7.3「起容器」→ 改成**顺序警告** + 原始报错 + 正确顺序
2. 原 7.4 / 7.5（看状态 / 验证端口）移入第八节
3. 第八节原「步骤 10 重启容器」→ 改为**步骤 10 起容器**；新增步骤 11 看状态、步骤 12 验证端口；原步骤 11 → 步骤 13 验证规则
4. 第十八节新增 **`not a directory` 专条**：三步修复（自检 DIR/FILE/MISSING → 删误建目录 → 写配置再起容器）+ 兜底 `rm -sf` 重建
5. 第二十节自检清单 A 增加"起容器前确认 5 个文件都是**非空普通文件**"

**验证**

按新顺序执行 → 5 个容器全部 `Up`。

**预防**

> 凡是"文件对文件"的 bind mount，**起容器前先确保宿主机文件是"有内容的普通文件"**。
> 给用户的每一步都加上一条自检命令，比事后排错便宜得多。

---

### 问题 2　旧容器缓存了目录挂载类型，文件明明正常仍报 not a directory（变体二）

**现象**

同样报 `not a directory`，但这次宿主机侧检查显示——**7 个挂载源全是正常文件**，`promtail-config.yaml` 有 891 B 内容。文件没问题，却还是报挂载错。

容器状态：

```
ai_chief_promtail    Exited (127)
ai_chief_loki        Restarting (1)
ai_chief_prometheus  Created
```

**定位**

那个 promtail 容器是在"**该路径还是目录**"的**旧状态**下被创建的（当时 Docker 自动建了目录）。容器创建时就**固化了挂载点类型**，Docker 记下"这里是目录"。

后来把目录删掉、改回文件，再执行 `docker compose up -d` —— **对已存在的容器，`up -d` 只会去"启动"它，不会重建**。所以它带着旧的"目录"记忆继续报错。`restart` 同理，也无效。

**解决**

```bash
cd /f/pycharm_aiprogram/ai_chief
# 删掉需要重建的旧容器（-f 连带删除运行中的）
docker compose -f docker/docker-compose.v3.yml rm -sf promtail loki prometheus grafana
# 重新创建并启动
docker compose -f docker/docker-compose.v3.yml up -d prometheus grafana alertmanager loki promtail
```

**验证**

两重验证，确认"文件本身没问题、纯粹是旧容器作祟"：

```bash
# ① 用一次性新容器挂同一个文件 —— 成功（promtail 正常读到 docker 日志）
docker compose -f docker/docker-compose.v3.yml run --rm --no-deps promtail \
  -config.file=/etc/promtail/promtail-config.yaml -dry-run

# ② 重建后容器状态
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
# → 5 行全部 Up
```

**预防**

> 只要**改过挂载源的类型**（目录 ↔ 文件），就必须 `docker compose rm -sf <svc>` 重建容器。
> `up -d` / `restart` 都不会重新计算挂载点类型。

---

### 问题 3　Loki 无限重启：配置漏了 object_store

**现象**

```
ai_chief_loki   Restarting (1) 2 seconds ago
```

日志：

```
level=error msg="invalid schema config" err="unrecognized 'object_store' type ''"
```

**定位**

`docker/loki/loki-config.yaml` 的 `schema_config.configs` 里只写了：

```yaml
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      schema: v13
```

**漏了 `object_store`**。Loki 3.x 里这两个是**两回事**：

| 字段 | 指什么 |
|---|---|
| `store` | 索引（index）用什么存 |
| `object_store` | 日志正文（chunk）用什么存 |

少写 `object_store` → 配置校验不过 → 容器反复重启。**而且手册里同一段配置也是这么写的**——即用户照抄手册必崩。

**解决**

补齐配置（同时修手册里同款错误）：

```yaml
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem      # 🔴 必须有这一行
      schema: v13
      index:
        prefix: index_
        period: 24h
```

另外两处连带修正：

- 开了 `retention_period`（日志保留 7 天）就必须给 `compactor.retention_enabled: true` + `delete_request_store: filesystem`，否则 Loki 会拒绝启动
- 补 `instance_addr`、`limits_config.allow_structured_metadata: true`

**验证**

用 Loki 自带的校验器先验配置，**通过再起容器**：

```bash
docker compose -f docker/docker-compose.v3.yml run --rm --no-deps loki \
  -config.file=/etc/loki/loki-config.yaml -verify-config
# → level=info msg="config is valid"

curl -s http://127.0.0.1:3100/ready
# → ready
```

**预防**

> 配置驱动的容器，**先 verify 再 up**：
> - Loki：`-config.file=... -verify-config`
> - Prometheus：`promtool check config` / `promtool check rules`
> - Promtail：`-config.file=... -dry-run`
>
> 这一招把"起容器→看日志→猜原因"的循环，压缩成一条命令。

---

### 问题 4　Prometheus 抓后端 401：中间件挂载顺序错

**现象**

Prometheus 的 `ai_chief_backend` 抓取目标：

```
health = down
lastError = server returned HTTP status 401 Unauthorized
```

手动验证也一样：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9002/metrics
# → 401
```

**定位**

`/metrics` **不是一个路由**，而是 `MetricsMiddleware.dispatch` 里的一段拦截：

```python
async def dispatch(self, request, call_next):
    if path == settings.PROMETHEUS_METRICS_PATH:
        return PlainTextResponse(_build_metrics_text(), media_type=CONTENT_TYPE_LATEST)
```

而手册第十二节把 `add_middleware(MetricsMiddleware)` 放在了 `AuthMiddleware` **内侧**。

关键点：**FastAPI 的中间件是"栈式"的——后 `add_middleware` 的更靠外层**（与直觉相反）。所以：

```
请求 → CORS → TraceId → Auth ← 在这里就返回 401 了
                        → Metrics （永远轮不到）
                        → Tenant → 限流 → 配额 → 路由
```

请求先撞上 `AuthMiddleware`，它直接 401 返回，`MetricsMiddleware` 里那段拦截**根本执行不到**。而且 `/metrics` 也不在 `app_my/middleware/auth.py` 的 `PUBLIC_PATHS` 白名单里。

**解决**

手册改为：`MetricsMiddleware` **必须在 `add_middleware(AuthMiddleware)` 之后 add**（落盘的 `main.py` 第 72 行就是这样），并补上原理说明。正确的栈顺序（从外到内）：

```python
app.add_middleware(QuotaMiddleware)             # 5. 配额（最里层）
app.add_middleware(RateLimitMiddleware)         # 4. 全局限流
app.add_middleware(UserRateLimitMiddleware)     # 3. 用户限流
app.add_middleware(TenantContextMiddleware)     # 2.5 租户上下文
app.add_middleware(AuthMiddleware)              # 2. JWT 鉴权
app.add_middleware(MetricsMiddleware)           # 1.5 埋点 + /metrics（在 Auth 之外！）
app.add_middleware(TraceIdMiddleware)           # 1. TraceID
app.add_middleware(CORSMiddleware, ...)         # 0. CORS（最后 add → 最外层）
```

> 备选方案：把 `"/metrics"` 加进 `PUBLIC_PATHS`。但那样等于让指标端点**对公网裸奔**，不如放在 Auth 外层 + 部署层限制（本机场景无所谓，上生产要评估）。

**验证**

```bash
curl -s http://127.0.0.1:9090/api/v1/targets
# → ai_chief_backend  health=up
```

**预防**

> 写"某中间件负责拦截某特殊路径"时，**先确认它在栈中的相对位置**。
> FastAPI：`add_middleware` 后进先出。想让它拦住更外层的检查，它就必须**更晚 add**。

---

### 问题 5　4 条告警规则一条没加载：两处被注释

**现象**

```bash
curl -s http://127.0.0.1:9090/api/v1/rules
```

返回空（`groups: []`）。Grafana 的告警统计面板一片空白，第十四节的告警演练必然失败。

**定位**

两处**互补**的开关都被注释了：

1. `docker/prometheus/prometheus.yml` 里：
   ```yaml
   # rule_files:
   #   - "alerts.yml"
   ```
2. `docker/docker-compose.v3.yml` 里第 148 行附近：
   ```yaml
   #- ./prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro
   ```

这是**之前排查挂载报错时留下的工作区残留**——当时为了让 Prometheus 先起来，临时注释掉，事后忘了复原。两处缺一不可：只打开 compose 挂载，Prometheus 不知道要加载它；只打开 `rule_files`，文件根本没进容器。

**解决**

两处都打开：

```yaml
# prometheus.yml
rule_files:
  - "alerts.yml"
```

```yaml
# docker-compose.v3.yml
- ./prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro
```

**验证**

```bash
docker exec ai_chief_prometheus promtool check rules /etc/prometheus/alerts.yml   # 语法
curl -s http://127.0.0.1:9090/api/v1/rules
# → HighErrorRate / HighP99Latency / TokenCostSpike / QuotaExhausted（4 条，state=inactive）
```

**预防**

> 排错时留下的"临时注释"，**必须成对复原**（挂载行 + 引用它的配置）。
> 收官自检清单里加一条：`grep -rn "^\s*#.*alerts\|^\s*#.*rule_files" docker/`。

---

### 问题 6　Grafana 健康端点写错

**现象**

```bash
curl -s http://127.0.0.1:3300/api/healthz
# → 401（而不是预期的 200 / ok）
```

**定位**

Grafana **11.3.1 没有 `/api/healthz` 这个端点**。正确的健康端点是 `/api/health`。手册步骤 12 和验证脚本 `check_containers()` 都写错了。

**解决**

- 手册步骤 12：改为 `/api/health`，并注明"Grafana 11 没有 healthz，写错会返回 401"
- `scripts/verify_stage7.py` 的 `check_containers()`：URL 与期望值一起改（期望 `"database": "ok"`）

**验证**

```bash
curl -s http://127.0.0.1:3300/api/health
# → {"database":"ok","version":"11.3.1","commit":"64...","enterpriseCommit":""}
```

**预防**

> 写健康检查 URL 前，**先对着真实容器 curl 一次**，不凭记忆写。
> （顺带：Prometheus 是 `/-/ready`、AlertManager 是 `/-/ready`、Loki 是 `/ready`——四个都不一样。）

---

### 问题 7　悬空引用说明手册附录 B

**现象**

用户按操作手册第八节步骤 9 去找"完整 JSON 在**说明手册附录 B**"，翻遍说明手册**只有附录 A**，找不到附录 B。于是回头问"完整 JSON 在哪"。

**定位**

操作手册有两处写着"完整 JSON 见说明手册附录 B 粘贴"——但**附录 B 从未被创建**。这是纯写作事故：正文引用了一个不存在的章节。

另外，其实**完整 JSON 一直都在操作手册自己的第十三节**（4 个完整代码块），那两处引用是多余且错误的导流。

**解决**

1. **说明手册补上附录 B**（此前被引用却不存在）：4 个仪表盘的**逐面板解释**、provisioning 自动加载机制、LogQL 三个符号（`{}` / `|=` / `|~`）、`rate()*60` 为什么要乘 60、`gridPos` 网格规则
2. 操作手册两处引用改为："JSON 已落盘到 `docker/grafana/dashboards/`，内容见本节（第十三节）"
3. 同时把第十三节的 4 个 JSON 代码块与**实际落盘文件逐字对齐**（避免"手册一套、文件一套"）

**验证**

```bash
grep -n "附录 B" 操作手册.md 说明手册.md
# → 两边引用一致，不再悬空
```

**预防**

> 手册里任何"参见某处"的交叉引用，**落笔前先确认目标章节存在**。
> 交付前跑一遍 `grep -o "见.*节\|见附录.*" *.md` 抽查。

---

### 问题 8　数据源缺 uid，所有仪表盘报 Datasource not found

**现象**

Grafana 起来后打开任意仪表盘，面板全部提示 **Datasource not found**（或直接空白）。

**定位**

`docker/grafana/provisioning/datasources/datasources.yml` 里只写了 `name`，**没写 `uid`**：

```yaml
datasources:
  - name: Prometheus      # 只有 name，没有 uid
    type: prometheus
    url: http://prometheus:9090
```

Grafana 对没指定 uid 的数据源会**随机生成一个 uid**。而 4 个仪表盘 JSON 里，每个面板都写死了：

```json
"datasource": {"type": "prometheus", "uid": "prometheus"}
```

两边对不上 → 所有面板都找不到数据源。

**解决**

显式指定 uid，且与仪表盘里写的字面一致：

```yaml
datasources:
  - name: Prometheus
    uid: prometheus          # 🔴 必须显式写，且与面板 JSON 里的 uid 一致
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
  - name: Loki
    uid: loki
    type: loki
    url: http://loki:3100
```

**验证**

```bash
curl -s -u admin:admin http://127.0.0.1:3300/api/datasources
# → Prometheus uid=prometheus / Loki uid=loki

# 再逐个确认 4 个仪表盘面板引用的 uid
for f in http-overview token-cost error-logs alerts; do
  python -c "import json;d=json.load(open(r'docker/grafana/dashboards/$f.json',encoding='utf-8'));print('$f', sorted({p['datasource']['uid'] for p in d['panels']}))"
done
# → 全部落在 {prometheus} / {loki} / {prometheus, loki} 内
```

**预防**

> **provisioning 的数据源一定要显式写 `uid`**，并让仪表盘 JSON 引用**同一个字符串**。
> 建议约定：`uid` = `name` 的小写形式。这样"复制粘贴改名字"也不会错。

---

### 问题 9　token-cost.json 的 JSON 根本解析不了

**现象**

把手册第十三节里的 `token-cost.json` 内容复制进文件，Grafana 加载失败；用 Python 校验直接报语法错。

**定位**

面板查询里有一句：

```json
{"expr": "sum by (model) (rate(http_requests_total{path="/chat/stream"}[5m])) * 60"}
```

内层的双引号 **没有转义**，JSON 字符串在这里就提前终止了 → 整个文件无法解析。

**解决**

1. 修正转义：`{path=\"/chat/stream\"}`（或干脆去掉这个无用的路径过滤）
2. 把操作手册里**全部 4 个 ```json 代码块抽出来做批量校验**：

```bash
python - <<'PY'
import re, json
txt = open('AI私厨_v3.0_阶段7_..._操作手册.md', encoding='utf-8').read()
blocks = re.findall(r'```json\n(.*?)```', txt, re.S)
ok = bad = 0
for i, b in enumerate(blocks, 1):
    try:
        json.loads(b); ok += 1
    except Exception as e:
        bad += 1; print(f'[FAIL] 块{i}: {e}')
print(f'可解析 {ok} / 失败 {bad}')
PY
# 修之前：可解析 3 / 失败 1
# 修之后：可解析 4 / 失败 0
```

**验证**

批量校验 4/4 通过；4 个落盘文件用 `json.load` 逐个校验通过。

**预防**

> 手册里嵌的 JSON 代码块，**交付前跑一次 `json.loads` 批量校验**。
> 这类错误对读者极其不友好：他不知道自己抄错了还是文档错了。

---

### 问题 10　token-cost.json 用错标签，面板静默空白

**现象**

"Token 成本"仪表盘里有一个"**调用次数 by model**"面板，永远是空白——**而且不报任何错**。

**定位**

查询写的是：

```
sum by (model) (rate(http_requests_total{path="/chat/stream"}[5m])) * 60
```

但 `http_requests_total` 的标签只有 **`method` / `status` / `tenant_id` / `path`**——**根本没有 `model` 这个标签**。

PromQL 里 `by (model)` 对不存在的标签做聚合 → 结果为空向量 → 面板**静默无数据**。这是最难查的一类错误：容器健康、Prometheus 正常、Grafana 正常，就是没数据。

**解决**

改用真正带 `model` 标签的指标：

```
sum by (model) (rate(llm_tokens_total[5m])) * 60
```

（`llm_tokens_total` 的标签是 `model` + `direction`。）

**验证**

```bash
curl -s http://127.0.0.1:9002/metrics | grep "^llm_tokens_total"
# → llm_tokens_total{direction="input",model="qwen3.7-flash"} ...
```

面板出现数据。

**预防**

> 写 PromQL 之前，**先 `curl /metrics | grep <指标名>` 看清这个指标的"真实标签集"**。
> 别照着别的指标猜——不同指标标签完全不同，猜错的表现就是"面板空白且不报错"。

---

### 问题 11　手册调用了不存在的函数 get_quota_status

**现象**

按手册步骤去调 `get_quota_status(tenant_id)` 上报配额使用率 —— 但 `app_my/core/quota.py` 里**根本没有这个函数**（`ImportError`）。

**定位**

我在写手册时，凭印象编了一个"应该存在"的函数名。真实情况是：配额逻辑用的是

```python
def check_quota(tenant_id, plan, metric) -> tuple[bool, int, int]:
    """返回 (是否允许, 已用, 上限)"""
```

没有 `get_quota_status`。

连带发现第二个坑：`QuotaMiddleware` 里原本写的是

```python
ok, used, cap = check_quota(tenant_id, plan, "chat_daily")
```

而这个 `ok` 会和后面 `JSONResponse` 里的 `ok=True`（dict 的 key）**撞名**，容易读错。

**解决**

```python
#ok, used, cap = check_quota(tenant_id, plan, "chat_daily")
ok_quota, used, cap = check_quota(tenant_id, plan, "chat_daily")   # 改名 ok_quota，避免遮蔽外层 ok

# 阶段 7：上报当前租户配额使用率（用于告警；不影响配额逻辑）
try:
    from app_my.core.metrics import quota_set
    if cap and cap > 0:
        quota_set(tenant_id, used / cap)      # 手工算使用率 = 已用 / 上限
except Exception:
    pass

if not ok_quota:
    ...  # 原超限逻辑
```

**验证**

`llm_quota_used_ratio{tenant_id="..."}` 有值；`QuotaExhausted` 告警规则能读取到该指标。

**预防**

> 🔴 **本阶段踩中的最硬红线**（用户长期反复强调过）：
> 写"调用某函数 / 某接口"的步骤之前，**必须先用工具核对真实签名**——读源码、`inspect.signature`、查 OpenAPI。
> **核对过的才写；不确定就不写。**
> 凭印象编函数名的代价是：用户按手册做，得到 `ImportError`，还会以为是自己的问题。

---

### 问题 12　验证脚本期望值大小写错

**现象**

`python scripts/verify_stage7.py containers` 里，Prometheus 一项误报 `[FAIL]`，但实际上 Prometheus 是好的。

**定位**

期望值写成 `Prometheus Server is ready.`（小写 r），而真实返回是 `Prometheus Server is Ready.`（大写 R）。字符串包含判断大小写敏感 → 误判。

**解决**

- 改成 `Prometheus Server is Ready.`
- Grafana 一项同时改 URL（`/api/healthz` → `/api/health`）与期望值（`"database": "ok"`）

**验证**

```bash
python scripts/verify_stage7.py all
# → 结果：11 通过 / 0 失败
```

**预防**

> 健康检查的期望字符串，**从真实响应里复制**，不要手打。

---

### 问题 13　国内拉不到镜像

**现象**

`docker pull` 报 `unauthorized: pull access denied` / `denied` / `no such manifest`。

**定位**

本机 `~/.docker/daemon.json` 里的三个 registry-mirrors（ustc / 163 / baidu）**都已停服**，等于没配；daemon 走 Docker Desktop 代理 `http.docker.internal:3128` → 系统 Clash 7890。

**解决**

实测可用源：

| 源 | 可用性 |
|---|---|
| `quay.io` 直连 | ✅ 可拉（etcd 等） |
| `docker.1panel.live` | ✅ 可拉 Docker Hub（prometheus / grafana / loki / promtail / alertmanager 都走它） |
| `docker.m.daocloud.io` | ⚠️ 白名单制（milvus 可、etcd/minio 不可） |

**预防**

> 见技能 `docker-cn-image-pull-diagnosis`。
> 另注：`docker.1panel.live` 只同步"一份最新镜像数据"，`:latest` 与当前最新对应的 RELEASE tag 可用，**历史 tag 一律 denied**——适合"能跑就行"，不适合 pin 历史版本。

---

### 问题 14　docker compose run 残留一次性容器

**现象**

做配置校验时用了 `docker compose run --rm --no-deps`，个别情况下在 `docker ps -a` 里留下 `ai_chief-promtail-run-74501519d2e6` 这类一次性容器。

**解决**

```bash
docker rm -f ai_chief-promtail-run-xxxxxxxx
docker ps -a --filter "name=run-" --format "{{.Names}}"
```

**预防**

> 校验完顺手看一眼 `docker ps -a | grep run-`。虽然 `--rm` 大多会自清，但容器创建失败时可能残留。

---

### 问题 15　收官发现：提交不完整 + gitignore 漏项 + 临时文件未删

**现象**

收官核查 `git status` 时发现：

- 阶段 7 的提交 `276ec93` **只包含 7 个文件**，但 `metrics.py`、整个 `docker/` 配置目录、测试、脚本、手册**全是 untracked**
- `.venv3/` 下的**数千个第三方依赖文件**冒出来成为 untracked（`.gitignore` 里只有 `.venv`，没有 `.venv3`）
- `app_my/api/_debug.py`（手册要求"验证完删除"的临时 500 触发器）**还躺在代码目录里**（`main.py` 里已注释引用）

**定位**

- 提交时只 `git add` 了"改动的老文件"，新增文件忘了加
- `.gitignore` 是更早写的，后来新建的虚拟环境目录名叫 `.venv3`，没补进去
- 验证完忘了删临时路由

**解决**

见《AI私厨_v3.0_阶段7_最终完整版.md》**第 4 章**的三条（含完整补提交命令，Git Bash + PowerShell 双版本）。

**预防**

> 每阶段收官前固定跑三件事：
> 1. `git status -sb` —— 逐条核对"该提交的都提交了、不该提交的都被忽略"
> 2. `grep -n "venv" .gitignore` —— 新增虚拟环境目录名有没有补进忽略
> 3. 过一遍手册里的"验证完必须删除/改回"清单（临时路由、临时阈值）

---

## 五、修改清单总表

### 5.1 代码（`app_my/` 与 `main.py`）

| 文件 | 类型 | 改了什么 | 对应问题 |
|---|---|---|---|
| `app_my/core/metrics.py` | 🟢 新增 | 5 个指标对象（HTTP_REQUESTS / HTTP_DURATION / LLM_TOKENS / LLM_COST / LLM_QUOTA_RATIO）+ 4 个埋点 helper | — |
| `app_my/middleware/metrics.py` | 🟢 新增 | HTTP 埋点中间件 + `/metrics` 端点实现 | 问题 4 |
| `app_my/core/token_billing.py` | 🔵 修改 | `record()` 末尾加 metrics 上报（token + 成本），失败吞掉不影响记账 | — |
| `app_my/core/config.py` | 🔵 修改 | 新增 3 个配置项：`PROMETHEUS_METRICS_PATH` / `PROMETHEUS_MULTIPROC_DIR` / `LOKI_URL` | — |
| `app_my/middleware/quota.py` | 🔵 修改 | 加 `quota_set` 上报；`ok` → `ok_quota` 改名 | 问题 11 |
| `app_my/agents/coordinator.py` | 🔵 修改 | `chat_coordinator()` 接收 `tenant_id` 并写入上下文变量 | — |
| `main.py` | 🔵 修改 | 注册 `MetricsMiddleware`（**位置必须在 Auth 之后**）；注释掉 `_debug` 引用 | 问题 4 / 15 |
| `app_my/api/_debug.py` | ⚠️ 待删 | 临时 500 触发器，验证完应删除 | 问题 15 |

### 5.2 配置（`docker/`）

| 文件 | 类型 | 改了什么 | 对应问题 |
|---|---|---|---|
| `docker/docker-compose.v3.yml` | 🔵 修改 | 新增 5 个服务；**打开 `alerts.yml` 挂载**（原被注释） | 问题 5 |
| `docker/prometheus/prometheus.yml` | 🟢 新增 | 抓取配置；**打开 `rule_files:`**（原被注释） | 问题 5 |
| `docker/prometheus/alerts.yml` | 🟢 新增 | 4 条告警规则 | — |
| `docker/alertmanager/alertmanager.yml` | 🟢 新增 | 告警路由（本地静默 + 写 alert.log） | — |
| `docker/loki/loki-config.yaml` | 🟢 新增 | **补 `object_store: filesystem`** + compactor retention 三项 | 问题 3 |
| `docker/promtail/promtail-config.yaml` | 🟢 新增 | 抓 Docker 容器 JSON 日志推 Loki | — |
| `docker/grafana/provisioning/datasources/datasources.yml` | 🟢 新增 | 数据源；**显式补 `uid`** | 问题 8 |
| `docker/grafana/provisioning/dashboards/dashboards.yml` | 🟢 新增 | 仪表盘自动加载目录 | — |
| `docker/grafana/dashboards/http-overview.json` | 🟢 新增 | 4 面板（QPS / P50-P99 / 5xx 率 / 4xx by tenant） | 问题 10 |
| `docker/grafana/dashboards/token-cost.json` | 🟢 新增 | 4 面板；**修 JSON 转义 + 改对标签** | 问题 9 / 10 |
| `docker/grafana/dashboards/error-logs.json` | 🟢 新增 | 2 面板（ERROR / WARN 日志，Loki） | — |
| `docker/grafana/dashboards/alerts.json` | 🟢 新增 | 3 面板（活跃告警数 / 明细 / 时间线） | — |
| `.env` / `.env.example` | 🔵 修改 | 加 3 行可观测栈配置 | — |

### 5.3 测试与脚本

| 文件 | 类型 | 改了什么 | 对应问题 |
|---|---|---|---|
| `tests/unit/test_metrics.py` | 🟢 新增 | 8 个单测（4 埋点 + `/metrics` 格式 + 自身不计数） | — |
| `scripts/verify_stage7.py` | 🟢 新增 | 端到端验证（容器 / 端点 / 规则）；**修期望值大小写** | 问题 12 |
| `scripts/stage7_check.sh` / `.ps1` | 🟢 新增 | 提测脚本（双终端） | — |

### 5.4 文档

| 文件 | 改了什么 | 对应问题 |
|---|---|---|
| 操作手册 | 顺序重排（7.3/八节）；`not a directory` 专条；中间件顺序 + 原理；健康端点；附录引用；JSON 与落盘对齐；错误对照表扩到 14 行；避坑加第 14/15 条；自检清单加"起容器前文件非空" | 1,2,3,4,5,6,7,9,10 |
| 说明手册 | **新增附录 B**（4 仪表盘逐面板解释 + provisioning 机制 + LogQL 符号 + gridPos 规则） | 7 |
| **最终完整版**（新） | 合并两份手册 + 收官信息 + 第 4 章补充四条 | 全部 |
| **问题与解决记录**（本文件） | — | 全部 |

---

## 六、经验教训

### 1. 顺序即正确性

本阶段两个看似毫不相关的故障，根因都是**顺序**：

| 场景 | 正确顺序 | 错了会怎样 |
|---|---|---|
| bind mount | 先写"有内容的文件"，再起容器 | Docker 建同名目录顶替 → `not a directory` |
| FastAPI 中间件 | 拦截特殊路径的中间件要**更晚 add**（更靠外） | 被外层中间件截胡 → 401 |

**通用教训**：凡是有"谁先谁后"的地方，手册里必须**显式写出顺序要求**，并给一个能"当场验证顺序对不对"的命令。用户照着做失败一次的成本，远高于我多写三行警告。

### 2. 容器 Up ≠ 功能通

本阶段最阴的三类问题，容器状态都是绿的：

| 表现 | 真因 | 为什么难查 |
|---|---|---|
| 抓取目标 401 | 中间件顺序 | 容器健康、日志无异常 |
| 仪表盘全空白 | 数据源 uid 不匹配 | Grafana 不报错，只显示 "not found" |
| 告警规则 0 条 | 两处配置被注释 | Prometheus 正常启动，`/rules` 返回空数组 |

**通用教训**：验收不能只看 `docker ps`。要按"**数据流**"逐段验：容器在 → 端口通 → 端点能返数据 → 下游能拿到数据（`/api/v1/targets` 是 `up`）。

### 3. 凡"引用/调用"必核对

本阶段踩了三次**同一类**坑，而且分属三个层面：

| 层面 | 错误 | 后果 |
|---|---|---|
| 文档 | 引用"说明手册附录 B"，该节不存在 | 用户翻不到东西 |
| 代码 | 调用 `get_quota_status()`，函数不存在 | `ImportError` |
| 数据 | 查 `http_requests_total` 的 `model` 标签 | 面板静默空白 |

**通用教训**：写任何"参见 X / 调用 Y / 按 Z 标签查"之前，**先用工具确认 X/Y/Z 真实存在**。这三件事都可以在 30 秒内验证完，但如果不验证，用户要花半小时才能发现。

### 4. 配置类容器：先 verify 再 up

一条命令换掉一轮"起容器 → 看日志 → 猜原因"：

```bash
docker compose -f docker/docker-compose.v3.yml run --rm --no-deps <svc> <bin> <verify-flag>
```

| 服务 | 校验方式 |
|---|---|
| Loki | `loki -config.file=... -verify-config` |
| Prometheus | `promtool check config` / `promtool check rules` |
| Promtail | `promtail -config.file=... -dry-run` |

**通用教训**：把这条写进下一阶段的准备工作里（阶段 8 配 Celery、阶段 9 配 Kong 都能用）。

### 5. 静默失效比报错更贵

本阶段最耗时的两个问题（标签用错、rule_files 被注释）**都不产生任何错误输出**。报错至少会告诉你"哪里不对"；静默失效只会让你怀疑"是不是我代码写错了"——而其实只是配置里少了一行、标签名不对。

**通用教训**：给"可能静默失效"的环节配一个**主动断言**。例如收官时把 `/api/v1/rules` 的返回条数写成断言（本次 `verify_stage7.py` 已经这么做了：`rules_count == 4`）。

### 6. 排错留下的"临时"必须成对清理

本阶段的 `rule_files` / `alerts.yml` 挂载被注释、`_debug.py` 未删、`git add` 漏文件——**全部是"临时"没清干净**。

**通用教训**：每阶段收官固定三件事：`git status -sb` 逐条核对、`grep venv .gitignore`、过一遍"验证完必须删除/改回"清单。

---

> **阶段 7 复盘一句话**：这一阶段的价值不在"又加了几个容器"，而在**第一次把服务从"能跑"推到"可观测、可告警"**——并且用 15 个真实故障换来了上面 6 条可复用的经验。这些经验会直接用在阶段 8（Celery + WebSocket）和阶段 9（微服务拆分 + Kong）上。
