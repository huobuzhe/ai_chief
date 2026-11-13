# AI 私厨 v3.0 阶段 8 最终完整版 — Celery 异步任务队列 + WebSocket 实时推送

> 本文件 = **收官信息 + 收官补充** + **第一部分：操作手册（照着做）** + **第二部分：说明手册（看懂为什么）**。
> 两份原手册（开工时交付）保留在项目根目录作历史档案，本文件把它们合并成一份"无勘误、可直接照做"的完整版。
> 另有《AI私厨_v3.0_阶段8_理解手册_大白话与图解.md》（看全貌用）与《AI私厨_v3.0_阶段8_问题与解决记录.md》（复盘用）。

---

## 目录

- [一、收官信息（全部实测）](#一收官信息全部实测)
- [二、这份文档怎么用](#二这份文档怎么用)
- [三、两份手册的章节顺序对照](#三两份手册的章节顺序对照)
- [四、收官补充四条（操作手册里没有的）](#四收官补充四条操作手册里没有的)
  - [4.1 git 提交完整性](#41-git-提交完整性)
  - [4.2 `.gitignore` 的两个问题](#42-gitignore-的两个问题)
  - [4.3 收尾清理项](#43-收尾清理项)
  - [4.4 一句话验收结论](#44-一句话验收结论)
- [第一部分：操作手册（照着做）](#第一部分操作手册照着做)
- [第二部分：说明手册（看懂为什么）](#第二部分说明手册看懂为什么)

---

## 一、收官信息（全部实测）

> 以下每条都是 2026-10-15 在本机 `F:\pycharm_aiprogram\ai_chief` 现场跑出来的真实输出，不是"应该是"。

| 项目 | 实测值 |
|---|---|
| 阶段编号 | **8 / 10** —— Celery 异步任务队列 + WebSocket 实时推送 |
| 分支 / 提交 | `feat/v3-stage8` / `7b5547c`（47 个文件，含阶段 7 的补提交） |
| 收官日期 | 2026-10-15 |
| 测试基线 | 阶段 7 **91 passed** → 阶段 8 **118 passed, 7 deselected**（新增 27 例：celery 6 / notify 4 / task_api 7 / ws_gateway 4 / ws_manager 6） |
| 分级路由 | `verify_stage8.py routing` → `high LLEN=1 / default LLEN=1 / low LLEN=1`，结果 `[ok]` |
| 端到端 | `verify_stage8.py e2e` → 事件序列 `['STARTED','SUCCESS']`，结果 `[ok]`（task_id `99a6d466-…`，队列 `low`，耗时 0.03 s） |
| 路由自检 | `check_stage8_routes.py` → **matched: 5**（`/tasks/reindex-milvus`、`/tasks/rebuild-kg`、`/tasks/nutrition-report`、`/tasks/{task_id}`、`/ws/notifications`） |
| worker 指标 | `curl http://127.0.0.1:9101/metrics` → 有 `celery_task_total{queue,status,task}`、`celery_task_duration_seconds_count`、`celery_queue_depth{queue}` |
| Prometheus | `/api/v1/targets` → **4 个 job 全 up**（`ai_chief_backend` / `ai_chief_worker` / `prometheus` / `alertmanager`） |
| 告警规则 | `/api/v1/rules` → `ai_chief_alerts` **6 条**（阶段 7 的 4 条 + 本阶段「任务失败率」「队列积压」2 条） |
| Grafana | 4 个仪表盘仍在（`ai_chief_http` / `ai_chief_cost` / `ai_chief_alerts` / `ai_chief_logs`），本阶段未新增面板 |
| 容器 | `docker ps` → **15 个全 Up**；本阶段**新增 0 个容器**（broker 复用阶段 1 的 Redis 6380，分 db1/db2） |
| 新增端口 | 仅 **9101**（worker 指标），HTTP 侧不变（API 仍 9002） |

### 1.1 本阶段五个可量化的成果（简历可直接抄）

1. **长任务异步化**：营养报告 / Milvus 重索引 / Neo4j 图谱重建三个重活从 HTTP 请求里剥离，提交即返回任务编号。
2. **三级队列分级路由**：运维级 → `high`、数据级 → `default`、用户级 → `low`，实测三条队列各落 1 条，互不堵塞。
3. **WebSocket 实时推送**：`?token=` 鉴权握手 + `ping/pong` 心跳 + 租户隔离派发，端到端实测收到 `STARTED → SUCCESS`。
4. **worker 可观测**：独立指标端口 9101（4 个 `celery_*` 指标）接入阶段 7 的 Prometheus，并补 2 条告警。
5. **测试 +27**：91 → 118 passed，新增 5 个测试文件覆盖 Celery 配置、通知降级、接口鉴权、WS 握手、连接管理。

---

## 二、这份文档怎么用

| 你想干什么 | 看哪里 |
|---|---|
| **照着把代码敲出来** | → [第一部分：操作手册](#第一部分操作手册照着做)（每步有 PowerShell 命令 + 预期输出 + 验证） |
| **搞懂每一行为什么这么写** | → [第二部分：说明手册](#第二部分说明手册看懂为什么)（逐行注释 + 术语表） |
| **看不懂整个阶段在干嘛** | → 《AI私厨_v3.0_阶段8_理解手册_大白话与图解.md》（比喻 + 全景图 + 时序图 + Q&A） |
| **查踩过的坑** | → 《AI私厨_v3.0_阶段8_问题与解决记录.md》（12 个问题，逐条"现象→定位→解决→验证→预防"） |
| **准备提交 / 提 PR** | → 直接看下面[第四章](#四收官补充四条操作手册里没有的) |

---

## 三、两份手册的章节顺序对照

> 两份手册**讲的同一批文件，但排序不同**：操作手册按**执行顺序**（先建配置、再建任务、最后接线），说明手册按**理解顺序**（先讲大脑 celery_app、再讲四肢）。
> 首次照做请跟**操作手册**；回头查"为什么"再跟**说明手册**，用这张表定位。

| 执行顺序 | 操作手册章节 | 说明手册章节 |
|---|---|---|
| 1 | 六、准备：切分支、核基线、装 Celery | 一、这个阶段到底解决了什么问题 / 二、专业名词解释表 |
| 2 | 七、子模块 1：新增 6 个配置项（config.py） | 三、配置层：`app_my/core/config.py` |
| 3 | 八、子模块 2：任务事件通知（notify.py） | 七、跨进程事件通知：`app_my/core/notify.py` |
| 4 | 九、子模块 3：worker 指标（worker_metrics.py） | 八、worker 自己的指标：`app_my/core/worker_metrics.py` |
| 5 | 十、子模块 4：Celery 应用实例（celery_app.py） | 四、任务系统的大脑：`app_my/worker/celery_app.py` |
| 6 | 十一、子模块 5：任务基类 NotifyTask（base.py） | 五、任务基类：`app_my/worker/base.py` |
| 7 | 十二、子模块 6：worker 生命周期信号（signals.py） | 六、worker 生命周期信号：`app_my/worker/signals.py` |
| 8 | 十三、子模块 7：三个长任务（tasks/） | 九、三个长任务：`app_my/worker/tasks/` |
| 9 | 十四、子模块 8：接口数据模型（schemas/tasks.py） | 十三、接口层：schemas + api |
| 10 | 十五、子模块 9：任务提交与查询接口（api/tasks.py） | 十三、接口层：schemas + api |
| 11 | 十六、子模块 10：WebSocket 三件套（ws/） | 十、manager / 十一、gateway / 十二、relay |
| 12 | 十七、子模块 11：main.py 接入 | 十四、入口接线：`main.py` |
| 13 | 十八、子模块 12：前端 WS 客户端（frontend/） | 十五、前端实时客户端：`frontend/js/ws.js` |
| 14 | 十九、子模块 13：Prometheus 抓 worker + 2 条告警 | 十七、可观测接线：`docker/prometheus` 两个 yml |
| 15 | 二十、子模块 14：验收脚本（verify_stage8.py） | 十六、验收脚本：`scripts/verify_stage8.py` |
| 16 | 二十一、子模块 15：单元测试（27 例） | 十八、单元测试怎么验证这套机制 |
| — | 二十四、提交 Gitee 与 PR 描述 | 附：一条数据的完整旅程 |

---

## 四、收官补充四条（操作手册里没有的）

### 4.1 git 提交完整性

**现状（实测 `git status --porcelain` + `git show --stat HEAD`）**：

- ✅ 提交 `7b5547c` 共 **47 个文件**，阶段 8 的代码、配置、测试、脚本**全部已入库**；
- ✅ 阶段 7 遗留的"提交不完整"问题**已被这次提交顺带解决**（`docker/` 全部配置、`metrics.py`×2、`test_metrics.py`、`verify_stage7.py`、`stage7_check.*` 都在里面）；
- ⚠️ 但下面这些**仍未跟踪**，需要补一次 `git add`：

```text
?? .venv3/                                                   ← 🔴 千万别加（虚拟环境）
?? AI私厨_v3.0_阶段总表_实际执行版.md
?? AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_操作手册.md
?? AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_说明手册.md
?? AI私厨_v3.0_阶段7_最终完整版.md
?? AI私厨_v3.0_阶段7_理解手册_大白话与图解.md
?? AI私厨_v3.0_阶段7_问题与解决记录.md
?? AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_操作手册.md
?? AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_说明手册.md
?? AI私厨_v3.0_阶段8_理解手册_大白话与图解.md
?? AI私厨_v3.0_阶段8_最终完整版.md
?? AI私厨_v3.0_阶段8_问题与解决记录.md
?? 阶段6_13.2_灰度开关_详细执行手册.md
?? 阶段6_验收脚本与LangSmith报错_修复手册.md
```

**PowerShell（推荐，逐个显式 add，绝不 `git add .`）**：

```powershell
cd F:\pycharm_aiprogram\ai_chief
git add "AI私厨_v3.0_阶段总表_实际执行版.md"
git add "AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_操作手册.md"
git add "AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_说明手册.md"
git add "AI私厨_v3.0_阶段7_最终完整版.md"
git add "AI私厨_v3.0_阶段7_理解手册_大白话与图解.md"
git add "AI私厨_v3.0_阶段7_问题与解决记录.md"
git add "AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_操作手册.md"
git add "AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_说明手册.md"
git add "AI私厨_v3.0_阶段8_理解手册_大白话与图解.md"
git add "AI私厨_v3.0_阶段8_最终完整版.md"
git add "AI私厨_v3.0_阶段8_问题与解决记录.md"
git add "阶段6_13.2_灰度开关_详细执行手册.md"
git add "阶段6_验收脚本与LangSmith报错_修复手册.md"
git status --porcelain          # 预期：只剩 "M .gitignore"，?? 里不再有任何 md
```

**Git Bash**：

```bash
cd /f/pycharm_aiprogram/ai_chief
for f in "AI私厨_v3.0_阶段总表_实际执行版.md" \
         "AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_操作手册.md" \
         "AI私厨_v3.0_阶段7_Prometheus+Grafana+Loki全栈监控_说明手册.md" \
         "AI私厨_v3.0_阶段7_最终完整版.md" \
         "AI私厨_v3.0_阶段7_理解手册_大白话与图解.md" \
         "AI私厨_v3.0_阶段7_问题与解决记录.md" \
         "AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_操作手册.md" \
         "AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_说明手册.md" \
         "AI私厨_v3.0_阶段8_理解手册_大白话与图解.md" \
         "AI私厨_v3.0_阶段8_最终完整版.md" \
         "AI私厨_v3.0_阶段8_问题与解决记录.md" \
         "阶段6_13.2_灰度开关_详细执行手册.md" \
         "阶段6_验收脚本与LangSmith报错_修复手册.md"; do
  git add "$f"
done
git status --porcelain
```

> 🔴 **为什么不能用 `git add .`**：`.venv3/` 现在还没被 `.gitignore` 覆盖（见 4.2），一条 `git add .` 会把几万个虚拟环境文件提交进仓库。

---

### 4.2 `.gitignore` 的两个问题

**问题 A：文件尾部被写成了 UTF-16LE，git 已把整个文件当二进制**

实测（Python 读原始字节）：

```text
bytes: 631   has NUL: True   CRLF: 0   LF: 63
尾部: ...health.json\n~\x00\\\x00$\x00*\x00\r\x00\n\x00venv/\nvenv/\n__pycache__/\n...
```

`git diff .gitignore` 的输出是 `Binary files a/.gitignore and b/.gitignore differ` —— 这就是 NUL 字节导致的。
根因：PowerShell 5.1 的 `>` / `Add-Content` 默认是 **UTF-16LE**，用它们往 `.gitignore` 追加内容就会混入 NUL。
后果：看不了 diff、合并时容易整文件冲突、部分工具会跳过这个文件。

**问题 B：追加的忽略项里仍然没有 `.venv3`**

实测 `git status` 依然显示 `?? .venv3/`。当前环境目录名就是 `.venv3`，而忽略列表里只有 `.venv` 和 `venv/`。

**修法（一次性用 UTF-8 重写整个文件，两份命令任选其一）**：

**PowerShell（🔴 必须用 `-Encoding utf8`，否则又写坏）**：

```powershell
cd F:\pycharm_aiprogram\ai_chief
$lines = @(
  '# Python-generated files', '__pycache__/', '*.py[oc]', 'build/', 'dist/', 'wheels/', '*.egg-info', '',
  '# Virtual environments', '.venv', '.venv3', 'venv/', 'env/', '',
  '# Environment variables / secrets', '.env', '.env.*', '!.env.example', '.env.txt', '',
  '# IDE', '.idea/', '.vscode/', '',
  '# OS files', '.DS_Store', 'Thumbs.db', '',
  '# Database files', 'db/*.db', 'db/*.sqlite', '*.sqlite', '',
  '# Test / coverage', '.pytest_cache/', '.coverage', 'htmlcov/', '.mypy_cache/', '.ruff_cache/', '',
  '# LangGraph', '.langgraph_api/', '',
  '# Stage 1 verification temporary files', 'main.log', 'main.err.log', 'main.pid', 'main.out.log',
  'main.py.bak.stage1', 'health.json', '',
  '# Stage 8 temporary files', '_verify_wsjs.js', 'backend.log', 'backend.err', 'worker.log', 'worker.err'
)
[System.IO.File]::WriteAllLines("$PWD\.gitignore", $lines, (New-Object System.Text.UTF8Encoding($false)))
git diff --stat .gitignore          # 预期：能正常显示文本 diff，不再是 "Binary files differ"
git status --porcelain              # 预期：?? 里 .venv3/ 消失，只剩 "M .gitignore"
```

**Git Bash**：

```bash
cd /f/pycharm_aiprogram/ai_chief
cat > .gitignore <<'EOF'
# Python-generated files
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info

# Virtual environments
.venv
.venv3
venv/
env/

# Environment variables / secrets
.env
.env.*
!.env.example
.env.txt

# IDE
.idea/
.vscode/

# OS files
.DS_Store
Thumbs.db

# Database files
db/*.db
db/*.sqlite
*.sqlite

# Test / coverage
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# LangGraph
.langgraph_api/

# Stage 1 verification temporary files
main.log
main.err.log
main.pid
main.out.log
main.py.bak.stage1
health.json

# Stage 8 temporary files
_verify_wsjs.js
backend.log
backend.err
worker.log
worker.err
EOF
git diff --stat .gitignore
git status --porcelain
```

**验证（两条都要跑）**：

```powershell
git check-ignore -v .venv3            # 预期：输出 ".gitignore:11:.venv3	.venv3"
git status --porcelain                # 预期：不再出现 "?? .venv3/"
```

---

### 4.3 收尾清理项

| # | 待清理 | 状态（实测） | 处理命令 |
|---|---|---|---|
| 1 | `app_my/api/_debug.py` | **仍存在**（阶段 7 留下的临时 500 触发器；`main.py` 第 123–124 行已注释引用，不挂载所以无害） | PowerShell：`Remove-Item .\app_my\api\_debug.py`<br>Git Bash：`rm app_my/api/_debug.py` |
| 2 | `_verify_wsjs.js` | **仍存在且已进提交**（根目录的 Node 语法校验临时脚本） | PowerShell：`Remove-Item .\_verify_wsjs.js`<br>Git Bash：`rm _verify_wsjs.js` |
| 3 | `-H`、`-d` | **两个 0 字节文件，已在版本库里**（commit `621fb9f`，阶段 5 时误提交：某次 `curl -H ... -d ...` 参数被引号吃掉，shell 把它们当文件名创建了） | PowerShell：`git rm --cached -- "-H" "-d"; Remove-Item -- "-H","-d"`<br>Git Bash：`git rm --cached -- -H -d && rm -- -H -d` |
| 4 | `frontend/` 与根目录的日志 | 本阶段验证产生的 `backend.log` / `worker.log` 之类（如果生成过） | 已在 4.2 的 `.gitignore` 里登记，无需删除 |

删完后**必须**复跑一次全量测试确认没删错东西：

```powershell
.\.venv3\Scripts\python.exe -m pytest -q          # 预期：118 passed, 7 deselected
```

> ⚠️ 注意：`pytest` 里 `test_health` / `test_auth` / `test_trace` / `test_billing_api` 这 12 个用例**需要后端在跑**（连 `http://127.0.0.1:9002`）。
> 后端没起时会看到 `requests.exceptions.ConnectionError` 导致 6 failed + 6 errors —— **这是环境问题，不是代码问题**。起后端再跑即可全绿。

---

### 4.4 一句话验收结论

**阶段 8 验收通过**：测试 91 → **118 passed**；分级路由 `high/default/low` 各 1 条；端到端 WebSocket 收到 `STARTED → SUCCESS`；worker 指标 9101 被 Prometheus 抓到（`ai_chief_worker up`）；告警规则 4 → **6 条**；15 个容器全 Up、本阶段零新增容器。代码已全部入库（`7b5547c`），剩下的是 4.1~4.3 的文档补提交与清理，做完即可提 PR。

---

# 第一部分：操作手册（照着做）

> 以下为《AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_操作手册.md》原文（已吸收全部勘误，目录锚点已修正）。


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


---

# 第二部分：说明手册（看懂为什么）

> 以下为《AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_说明手册.md》原文（目录锚点已修正）。


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

