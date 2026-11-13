# AI 私厨 v3.0 阶段 9 最终完整版 —— 微服务拆分（4 服务）与 Kong DB-less 网关

> 本文件 = **封面与收官信息** + **第一部分：操作手册（照着做）** + **第二部分：说明手册（看懂为什么）**。
> 三份开工手册（操作 / 说明 / 理解）各自独立保留在项目根目录，本文件是**合并后的完整版**，两份原文未做删改，仅去掉各自的 H1 换成"第一部分 / 第二部分"。
> 所有数字均为 **2026-10-20 实机实测原文**，非设计估计。

## 目录

- [一、收官信息（实机核实）](#一收官信息实机核实)
- [二、本阶段最终文件清单](#二本阶段最终文件清单)
- [三、补充说明：git 提交完整性](#三补充说明git-提交完整性)
- [四、补充说明：.gitignore 与收尾清理](#四补充说明gitignore-与收尾清理)
- [五、PR 描述（阶段 8 + 阶段 9，可直接粘贴）](#五pr-描述阶段-8--阶段-9可直接粘贴)
- [六、一句话验收结论](#六一句话验收结论)
- [第一部分：操作手册（照着做）](#第一部分操作手册照着做)
- [第二部分：说明手册（看懂为什么）](#第二部分说明手册看懂为什么)

---

## 一、收官信息（实机核实）

| 项 | 内容 |
|---|---|
| 阶段 | **9 / 10 —— 微服务拆分（4 服务）+ Kong DB-less 网关 + 跨服务客户端三件套** |
| 分支 | `feat/v3-stage9` |
| 收官日期 | 2026-10-20 |
| 代码提交 | `749876c` 「stage9: 微服务拆分 (4 services) + Kong DB-less 网关 + 跨服务客户端三件套」，含 **23 个文件** |
| 测试基线 | 阶段 8 **118 passed, 7 deselected** → 阶段 9 **140 passed, 7 deselected**（`./.venv3/Scripts/python.exe -m pytest -q`，新增 22 例 = 8+7+7） |
| 同上（另一种跑法） | `--ignore=tests/integration` 时为 **138 passed, 1 deselected** |
| 端到端（经 Kong 9100） | 注册 → 登录（token 297 字符）→ `/users/me` 返回 `{"id":111,"username":"stage9close25522",...}` → `/kg/stats` 经 r-chat → chat → recommender 返回 `Ingredient 142 / Recipe 60 / Nutrient 8 / Condition 6`，与直连 9123 返回**完全一致** |
| chat 模式自检 | 直连 `9124/mode` → `{"service":"chat","split_mode":"remote","remote_nodes":true}`（`/mode` 未对 Kong 暴露，属预期） |
| 服务健康 | 9002（单体对照组）/ 9121 user / 9122 recognizer / 9123 recommender / 9124 chat 全部 `{"status":"ok"...}` |
| Kong 实况 | Admin API 9105：`services ['svc-chat','svc-user','svc-recognizer','svc-recommender']`、`routes ['r-chat','r-chat-ws','r-recognizer','r-user','r-recommender']`（**5 条**，非 6 条） |
| 容器 | 新增 `ai_chief_kong` **Up 3 hours (healthy)**；其余 16 个容器全部 Up，无新增残留 |
| Prometheus | 阶段 9 新增 4 个 target：`ms-user 9121 / ms-recognizer 9122 / ms-recommender 9123 / ms-chat 9124`，**全部 up**；总目标 8 个 |
| 文档 | 阶段 9 三份手册（操作 / 说明 / 理解）+ 本文件 + 问题与解决记录，**均在项目根目录，尚未提交 git** |

### 这份文档怎么用

| 你想做什么 | 看哪里 |
|---|---|
| 照着把阶段 9 重做一遍 | **第一部分：操作手册**（每步双终端命令 + 实跑预期） |
| 看懂每段代码为什么这么写、术语啥意思 | **第二部分：说明手册** |
| 先看全貌再动手 | 项目根目录的 `AI私厨_v3.0_阶段9_理解手册_微服务拆分与Kong网关.md` |
| 复盘这次踩过哪些坑 | `AI私厨_v3.0_阶段9_问题与解决记录.md` |

---

## 二、本阶段最终文件清单

### 新建（18 个）

| 文件 | 作用 |
|---|---|
| `services/__init__.py` | services 包声明 |
| `services/common/__init__.py` | 共享内核包声明 |
| `services/common/breaker.py` | 熔断器（`CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)`、`CircuitOpenError`、注册表 `get_breaker/all_snapshots/reset_all`） |
| `services/common/client.py` | 跨服务 HTTP 客户端（`get_client(name)` 全局单例、指数退避重试、`transport=` 支持 MockTransport、trace_id 透传） |
| `services/common/context.py` | 上游 JWT 暂存（`set_upstream_token` / `auth_header`），供跨服务透传 |
| `services/common/app_factory.py` | `create_service_app(...)` 工厂，统一中间件顺序与 CORS/鉴权/配额开关 |
| `services/user/{__init__,main}.py` | user 服务（9121）：认证 / 用户 / 租户 / 管理端 / 计费 / cache |
| `services/recognizer/{__init__,main}.py` | recognizer 服务（9122）：识别 + 营养节点 / OSS |
| `services/recommender/{__init__,main}.py` | recommender 服务（9123）：KG 写 / 推荐+重排节点 / 计费 |
| `services/chat/{__init__,main,graph_remote}.py` | chat 服务（9124）：编排 / WS / 记忆 / 任务；`graph_remote.py` 是远程节点表 |
| `docker/kong/kong.yml` | Kong DB-less 声明式配置：4 service + 5 route + 3 插件 |
| `scripts/ws_probe.py` | WebSocket 穿透探针（直连 9124 与经 Kong 9100 各测一次） |
| `tests/unit/test_circuit_breaker.py` | 熔断器状态机测试（7 例） |
| `tests/unit/test_service_client.py` | 客户端重试/熔断测试，MockTransport 离线（8 例） |
| `tests/unit/test_service_apps.py` | 中间件顺序断言（7 例） |

### 修改（5 个）

| 文件 | 改动 |
|---|---|
| `app_my/agents/coordinator.py` | 新增 `build_workflow(nodes=None)` + `_resolve_nodes()`，按 `SPLIT_MODE` 切本地/远程节点图 |
| `docker/docker-compose.v3.yml` | 追加 `kong` 服务（容器 8000/8001 → 宿主 9100/9105，镜像 `docker.1panel.live/library/kong:3.7`） |
| `docker/prometheus/prometheus.yml` | 新增 4 个微服务抓取 job（ms-user / ms-recognizer / ms-recommender / ms-chat） |
| `.gitignore` | 已含 `.venv/` 与 `.venv3/`（**此改动尚未提交**） |

---

## 三、补充说明：git 提交完整性

`749876c` 已包含本阶段**全部代码/配置/测试**（23 个文件），但**文档类文件全部未入库**（历史阶段 7/8 也是这个情况）。收官前请补提交：

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
git add .gitignore \
  "AI私厨_v3.0_阶段9_操作手册_微服务拆分与Kong网关.md" \
  "AI私厨_v3.0_阶段9_说明手册_微服务拆分与Kong网关.md" \
  "AI私厨_v3.0_阶段9_理解手册_微服务拆分与Kong网关.md" \
  "AI私厨_v3.0_阶段9_最终完整版.md" \
  "AI私厨_v3.0_阶段9_问题与解决记录.md" \
  "AI私厨_v3.0_阶段8_最终完整版.md" \
  "AI私厨_v3.0_阶段8_问题与解决记录.md"
git commit -m "docs: 阶段9 三件套手册 + 最终完整版 + 问题与解决记录（含阶段8文档补交）"
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
git add .gitignore; git add "AI私厨_v3.0_阶段9_操作手册_微服务拆分与Kong网关.md"; git add "AI私厨_v3.0_阶段9_说明手册_微服务拆分与Kong网关.md"; git add "AI私厨_v3.0_阶段9_理解手册_微服务拆分与Kong网关.md"; git add "AI私厨_v3.0_阶段9_最终完整版.md"; git add "AI私厨_v3.0_阶段9_问题与解决记录.md"; git add "AI私厨_v3.0_阶段8_最终完整版.md"; git add "AI私厨_v3.0_阶段8_问题与解决记录.md"
git commit -m "docs: 阶段9 三件套手册 + 最终完整版 + 问题与解决记录（含阶段8文档补交）"
```

**验证（两个终端命令相同）**：
```bash
git status --porcelain -uall | head -20
```
**预期**：上面列出的文件不再出现；只剩你**有意**保留未提交的文件。

> 🟡 项目根还有 `tmp/compare.md`（历史对比临时文件）与若干阶段 6/7 的旧 md，是否入库由你决定；若不需要请直接删除（见下一节）。

---

## 四、补充说明：.gitignore 与收尾清理

| # | 检查项 | 实测结果 | 处理 |
|---|---|---|---|
| 1 | 虚拟环境是否被忽略 | `.venv/` → `.gitignore:58`；`.venv3/` → `.gitignore:64`，**两个都已忽略** | ✅ 无需改（这是阶段 7 遗留的待办，本阶段闭环） |
| 2 | `.gitignore` 自身改动 | ` M .gitignore`（未提交） | 按上一节一起提交 |
| 3 | 临时文件 | 项目根 `tmp/compare.md`（阶段对比遗留） | 🟡 不需要就删：`rm -f tmp/compare.md` |
| 4 | 排错期临时改动 | 本阶段验证用的 `C:\Windows\Temp\svc_*.log`、`/tmp/st9_*` 都在**系统临时目录**，不在项目里 | ✅ 无需清理 |
| 5 | 代码里的临时开关 | 无（阶段 9 未新增调试路由/临时阈值） | ✅ |
| 6 | 一次性容器残留 | `docker ps -a` 无 `run-` 前缀残留容器 | ✅ |

**删除临时文件的双终端命令**：

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief && rm -f tmp/compare.md && echo "已删除"
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
if (Test-Path .\tmp\compare.md) { Remove-Item .\tmp\compare.md -Force; "已删除" } else { "不存在，跳过" }
```

---

## 五、PR 描述（阶段 8 + 阶段 9，可直接粘贴）

> 阶段 8 的 PR 描述此前推迟到本阶段一并提交，这里两份都给。

### 5.1 阶段 8（分支 `feat/v3-stage8`，提交 `7b5547c`）

```markdown
## feat(v3-stage8): Celery 异步任务队列 + WebSocket 实时推送

### 做了什么
- 引入 Celery + Redis：长任务（识别/推荐）改异步，`high/default/low` 三级队列分级路由
- 新增 WebSocket 网关与连接管理器，任务状态 `STARTED → SUCCESS` 实时推送
- worker 指标端口 9101 接入 Prometheus

### 关键实现
- `app_my/tasks/`：Celery 应用、任务定义、失败降级（任务失败不影响主流程返回）
- `app_my/api/tasks.py` + `app_my/ws/gateway.py`：任务查询接口 + WS 推送
- Windows 下 worker 必须 `--pool=solo`：`-P prefork` 会触发 billiard spawn 的 `PermissionError: [WinError 5]`

### 验证
- 测试：91 passed → **118 passed, 7 deselected**（新增 27 例：celery 6 / notify 4 / task_api 7 / ws_gateway 4 / ws_manager 6）
- 端到端：WS 收到 `STARTED → SUCCESS`
- 告警规则 4 → 6 条；15 个容器全 Up，本阶段零新增容器
```

### 5.2 阶段 9（分支 `feat/v3-stage9`，提交 `749876c` + 文档补交）

```markdown
## feat(v3-stage9): 微服务拆分（4 services）+ Kong DB-less 网关 + 跨服务客户端三件套

### 做了什么
把单体（9002）按职责拆成 4 个独立进程，前面挂 Kong 做统一入口；拆出去的服务之间用自研 HTTP 客户端通信，带重试 + 熔断 + trace_id 透传。

- **user 9121**：认证 / 用户 / 租户 / 管理端 / 配额计费 / cache
- **recognizer 9122**：识别 + 营养节点 / OSS
- **recommender 9123**：知识图谱写 / 推荐 + 重排节点 / 计费
- **chat 9124**：编排 / WebSocket / 对话记忆 / 任务（`SPLIT_MODE=remote` 时走远程节点图）
- **Kong 9100（Admin 9105）**：DB-less，`kong.yml` 声明式；5 条 route + 4 个 service + 3 个插件（cors / rate-limit / correlation-id）

### 关键实现
- `services/common/breaker.py`：熔断器状态机 closed → open → half_open，`failure_threshold=3`、`recovery_timeout=30s`
- `services/common/client.py`：`get_client(name)` 全局单例（一个下游一个连接池）、指数退避重试、4xx 不重试不记失败、`transport=` 可注入 MockTransport 做离线测试
- `services/common/context.py`：暂存上游 JWT，跨服务调用时透传
- `services/common/app_factory.py`：`create_service_app()` 统一中间件顺序（**后 add 的更靠外层**，Metrics 必须在 Auth 外侧，否则 `/metrics` 被 401 挡住）
- `app_my/agents/coordinator.py`：`build_workflow(nodes=None)` + `_resolve_nodes()`，按 `SPLIT_MODE` 切本地/远程——**一份代码两种运行形态**，本地 `local` 走进程内节点，上线 `remote` 走 HTTP
- 保留单体 9002 作为拆分前后对照组

### 验证（2026-10-20 实机）
- 测试：118 passed → **140 passed, 7 deselected**（新增 22 例 = 熔断 8 + 客户端 8 + 中间件顺序 7 的三份测试）
- 端到端（经 Kong 9100）：注册 → 登录 → `/users/me` → `/kg/stats`（Kong → chat → recommender 跨两跳）返回与直连 9123 一致
- `9124/mode` → `{"split_mode":"remote","remote_nodes":true}`
- Kong：4 service / 5 route；容器 `Up (healthy)`
- Prometheus 新增 4 个 target 全部 up（ms-user / ms-recognizer / ms-recommender / ms-chat）
- 故障隔离：kill 掉 recommender 后 chat 仍返回结果（推荐部分降级），`/health` 的 breakers 里 `recommender.failures` 递增；30 秒后自动恢复

### 兼容性
- `SPLIT_MODE` 默认 `local`，不设置时行为与拆分前完全一致（旧测试全绿）
- 单体 9002 未删除，可随时对照
```

---

## 六、一句话验收结论

**阶段 9 验收通过**：测试 118 → **140 passed**；4 个微服务 + Kong 网关全部 healthy；经网关的跨服务链路（Kong → chat → recommender）返回与直连一致；Prometheus 4 个新 target 全 up；故障隔离与熔断恢复实测成立；代码已入库（`749876c`）。剩下的是**文档补提交**（第三节）与**临时文件清理**（第四节），做完即可提 PR。

---

# 第一部分：操作手册（照着做）


**主题**：单体 FastAPI 拆成 4 个微服务 + Kong 网关（DB-less）

**分支**：`feat/v3-stage9`（基于 `feat/v3-stage8` 拉新分支）
**目标读者**：完全跟着本手册一步步敲命令，每步都能在本机复现
**适用 Python**：3.10.11（系统 Python，直接用 `.venv3` 即可）

---

## 📑 目录（可点击锚点）

- [0. 开始前 30 秒核对清单](#0-开始前-30-秒核对清单)
- [1. 拉新分支（基于当前已通过测试的 feat/v3-stage8）](#1-拉新分支基于当前已通过测试的-featv3-stage8)
- [2. 新建 services/ 目录骨架](#2-新建-services-目录骨架)
- [3. 写共享内核 services/common/（app_factory / breaker / client）](#3-写共享内核-servicescommonapp_factory--breaker--client)
- [4. 写四个服务的入口 `main.py`](#4-写四个服务的入口-mainpy)
- [5. 改 chat 的 coordinator：按 SPLIT_MODE 切本地/远程节点图](#5-改-chat-的-coordinator按-split_mode-切本地远程节点图)
- [6. 写 22 个单元测试并真跑](#6-写-22-个单元测试并真跑)
- [7. 写 Kong 声明式配置 + 跑官方校验器](#7-写-kong-声明式配置--跑官方校验器)
- [8. 起 Kong 容器（在 docker-compose 里加一段）](#8-起-kong-容器在-docker-compose-里加一段)
- [9. 起四个微服务（双终端 + 后台守护）](#9-起四个微服务双终端--后台守护)
- [10. 不经网关直跑四个服务（验收装配）](#10-不经网关直跑四个服务验收装配)
- [11. 跑端到端：经 Kong 网关的完整业务流](#11-跑端到端经-kong-网关的完整业务流)
- [12. 验证 Kong 限流头 / trace 头（看 response header）](#12-验证-kong-限流头--trace-头看-response-header)
- [13. 测 WebSocket 穿透 Kong（用 scripts/ws_probe.py）](#13-测-websocket-穿透-kong用-scriptsws_probepy)
- [14. 演示故障隔离：杀掉 recommender，chat 仍能降级返回](#14-演示故障隔离杀掉-recommenderchat-仍能降级返回)
- [15. 触发熔断跳闸并验证 fast-fail](#15-触发熔断跳闸并验证-fast-fail)
- [16. 等 30 秒让熔断恢复，再次请求成功](#16-等-30-秒让熔断恢复再次请求成功)
- [17. 加 4 个抓取 target 到 Prometheus](#17-加-4-个抓取-target-到-prometheus)
- [18. 生成「远程 vs 单体」对照 P99 数据](#18-生成远程-vs-单体对照-p99-数据)
- [19. 把临时副本里所有新增文件拷回本机项目（最终落盘）](#19-把临时副本里所有新增文件拷回本机项目最终落盘)
- [20. 跑全量回归 pytest 确保 106+ 旧测试无回归](#20-跑全量回归-pytest-确保-106-旧测试无回归)
- [21. 提交推送到 Gitee + 写 PR 描述](#21-提交推送到-gitee--写-pr-描述)
- [22. 错误对照表（按现象查原因）](#22-错误对照表按现象查原因)
- [23. 避坑清单](#23-避坑清单)
- [24. 自检清单（双终端双跑一次 = 完整结束）](#24-自检清单双终端双跑一次--完整结束)
- [25. 附录 C：PowerShell 5.1 等价替换速查表](#25-附录-cpowershell-51-等价替换速查表)

---

## 0. 开始前 30 秒核对清单

**做下列任何一步前，先确认**：

| 检查项 | 期望值 | 不符怎么办 |
| --- | --- | --- |
| `python -V`（必须用 .venv3） | `Python 3.10.11` | 详见 §25 附录 C |
| 当前分支 | `feat/v3-stage8` | §1 第一步会切到 stage9 |
| `pytest -q` 基线 | 100+ passed，0 failed（少量 error/失败因未起服务） | §20 全量回归会再次校验 |
| `docker ps` | 已有 ai_chief 系列容器在跑（mysql/redis/pgvector 等） | `cd docker && docker compose up -d` 拉起 |
| 端口 9121-9124 / 9100 / 9105 全空 | 任一被占 → 起服务会失败 | §22 错误对照表 |
| 工作目录 | `F:\pycharm_aiprogram\ai_chief` | cd 切过去 |

---

## 1. 拉新分支（基于当前已通过测试的 `feat/v3-stage8`）

### 1.1 切到项目根目录

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
```

### 1.2 确认在 stage8

**两个终端都一样**：
```bash
git status --short && git branch --show-current
```

**期望输出**（`feat/v3-stage8` 且 working tree 干净）：
```
feature/v3-stage8
```
（无任何 `M` / `??` 行的脏文件）

### 1.3 拉新分支并同步远端

**Git Bash**：
```bash
git fetch origin
git checkout -b feat/v3-stage9 origin/feat/v3-stage8
git push -u origin feat/v3-stage9
```

**PowerShell 5.1**：
```powershell
git fetch origin
git checkout -b feat/v3-stage9 origin/feat/v3-stage8
git push -u origin feat/v3-stage9
```

**验证**：
```bash
git branch --show-current && git log --oneline -1
```

**期望**：`feat/v3-stage9`，最近的 commit 必须是阶段 8 收官的合并 commit。

---

## 2. 新建 `services/` 目录骨架

**Git Bash**：
```bash
mkdir -p services/common services/user services/recognizer services/recommender services/chat
```

**PowerShell 5.1**：
```powershell
New-Item -ItemType Directory -Force -Path services\common, services\user, services\recognizer, services\recommender, services\chat
```

**验证**（两个终端都一样）：
```bash
ls services/
```

**期望**：`common  recognizer  recommender  chat  user`（目录名按字母序排，OK）

---

## 3. 写共享内核 `services/common/`（app_factory / breaker / client）

> 共 4 个文件。**全部原样写入，不允许改行**。文件里已经有了所有真实函数签名、命令行参数、端口号；写错一个字符下面所有步骤都会爆。

### 3.1 创建四个 `__init__.py`

**Git Bash**：
```bash
touch services/__init__.py services/common/__init__.py services/user/__init__.py services/recognizer/__init__.py services/recommender/__init__.py services/chat/__init__.py
```

**PowerShell 5.1**：
```powershell
New-Item -ItemType File -Force -Path services\__init__.py,services\common\__init__.py,services\user\__init__.py,services\recognizer\__init__.py,services\recommender\__init__.py,services\chat\__init__.py
```

**验证**：
```bash
find services -name __init__.py | sort
```

**期望**：`__init__.py` 6 行（不是 5 行的原因是 `services/` 自身也要 1 个）。

---

### 3.2 写 `services/common/breaker.py`（熔断器）

> ⏱️ 约 175 行。**整段贴入**。
> 🔴 勘误（2026-10-19）：本文件与旧版手册差异极大（参数名 `failure_threshold`、异常类 `CircuitOpenError`、注册表 `get_breaker/all_snapshots`）。**已按旧版贴过的，整段覆盖重贴**，否则 §6 的测试跑不过。

#### 文件全文（一字不改）

```python
# services/common/breaker.py
"""
熔断器（Circuit Breaker）—— 微服务里"防止一个服务挂掉拖垮调用方"的保护开关

生活化比喻：就像家里的电闸。
    正常（CLOSED）   ：电流正常通过，请求照发。
    跳闸（OPEN）     ：连续烧坏几个电器后，电闸自动跳掉，直接拒绝请求，不再往故障服务上砸。
    试探（HALF_OPEN）：等了一会儿，放一个请求过去试试，通了就合闸，不通继续跳着。

为什么必须有它：
    微服务里 A 调 B，B 挂了 → A 的每次请求都要等超时（比如 5 秒）才失败 →
    用户请求全堵在 A 上 → A 的连接池耗尽 → A 也挂 → 一路传染（雪崩）。
    熔断器的作用是"快速失败"：B 已经确定不行了，A 立刻返回降级结果，不再等。

三个可调参数：
    failure_threshold  连续失败几次才跳闸（默认 3）
    recovery_timeout   跳闸后等多久才允许试探（默认 30 秒）
    half_open_max_calls 试探期最多放几个请求过去（默认 1）
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Dict


class BreakerState(str, Enum):
    """熔断器的三种状态。用 str 继承是为了能直接进 JSON/日志。"""
    CLOSED = "closed"        # 正常放行
    OPEN = "open"            # 跳闸，直接拒绝
    HALF_OPEN = "half_open"  # 试探期，放少量请求


class CircuitOpenError(RuntimeError):
    """熔断器处于 OPEN 时抛出的异常，调用方要 catch 它并走降级逻辑。"""


class CircuitBreaker:
    """
    一个"按服务名"独立的熔断器实例。

    线程安全：用 threading.Lock 保护状态读写。
    （uvicorn 单进程里也可能有多线程跑同步代码，加锁最稳妥）
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = BreakerState.CLOSED
        self._failures = 0           # 连续失败计数（成功一次就清零）
        self._opened_at = 0.0        # 跳闸时刻（time.time() 的时间戳）
        self._half_open_calls = 0    # 试探期已经放过去几个请求
        self._last_error = ""        # 最近一次失败原因，便于排错

    # ------------------------------------------------------------------ 状态查询
    @property
    def state(self) -> BreakerState:
        """当前状态。注意：OPEN 状态下如果已经过了恢复时间，会自动降级成 HALF_OPEN。"""
        with self._lock:
            return self._current_state_unlocked()

    def _current_state_unlocked(self) -> BreakerState:
        """内部方法：调用前必须已持有锁。OPEN 超时自动转 HALF_OPEN。"""
        if self._state == BreakerState.OPEN:
            if time.time() - self._opened_at >= self.recovery_timeout:
                self._state = BreakerState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    # ------------------------------------------------------------------ 调用前闸门
    def before_call(self) -> None:
        """
        发请求之前调用。如果处于 OPEN（还没到试探时间），直接抛 CircuitOpenError。

        这一抛很关键：它让调用方"立刻失败"，而不是陪着故障服务耗掉整个超时时间。
        """
        with self._lock:
            state = self._current_state_unlocked()
            if state == BreakerState.OPEN:
                raise CircuitOpenError(
                    f"[{self.name}] 熔断器已跳闸，剩余恢复时间 "
                    f"{max(0.0, self.recovery_timeout - (time.time() - self._opened_at)):.1f}s"
                )
            if state == BreakerState.HALF_OPEN:
                # 试探期有名额限制：超过名额的请求继续拒绝，避免刚有点希望就被打垮
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitOpenError(f"[{self.name}] 试探名额已用完，稍后再试")
                self._half_open_calls += 1

    # ------------------------------------------------------------------ 结果回写
    def record_success(self) -> None:
        """调用成功：连续失败计数清零；如果是试探期，说明服务恢复了，直接合闸。"""
        with self._lock:
            self._failures = 0
            self._last_error = ""
            self._half_open_calls = 0
            self._state = BreakerState.CLOSED

    def record_failure(self, reason: str = "") -> None:
        """调用失败：连续失败计数 +1；达到阈值就跳闸。"""
        with self._lock:
            self._failures += 1
            self._last_error = reason
            if self._state == BreakerState.HALF_OPEN:
                # 试探失败 → 立刻重新跳闸，并把恢复计时器重置（再等一轮）
                self._trip_unlocked()
            elif self._failures >= self.failure_threshold:
                self._trip_unlocked()

    def _trip_unlocked(self) -> None:
        """内部方法：置为 OPEN 并记录跳闸时刻。"""
        self._state = BreakerState.OPEN
        self._opened_at = time.time()
        self._half_open_calls = 0

    # ------------------------------------------------------------------ 观测 / 测试辅助
    def snapshot(self) -> Dict[str, object]:
        """把内部状态导出成字典，给 /health 和指标用。"""
        with self._lock:
            state = self._current_state_unlocked()
            return {
                "name": self.name,
                "state": state.value,
                "failures": self._failures,
                "threshold": self.failure_threshold,
                "last_error": self._last_error,
                "recover_in": (
                    round(max(0.0, self.recovery_timeout - (time.time() - self._opened_at)), 1)
                    if state == BreakerState.OPEN else 0.0
                ),
            }

    def reset(self) -> None:
        """恢复到出厂状态。单测里每个用例跑之前都要调一次，避免用例互相污染。"""
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failures = 0
            self._opened_at = 0.0
            self._half_open_calls = 0
            self._last_error = ""


# 全局注册表：所有熔断器按"服务名"登记在这里，方便 /health 一次性列出全部状态
_REGISTRY: Dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = threading.Lock()


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    """取（必要时创建）某个服务的熔断器。同名只会有一个实例。"""
    with _REGISTRY_LOCK:
        if name not in _REGISTRY:
            _REGISTRY[name] = CircuitBreaker(name, **kwargs)
        return _REGISTRY[name]


def all_snapshots() -> Dict[str, Dict[str, object]]:
    """导出全部熔断器的状态快照，供 /health 展示。"""
    with _REGISTRY_LOCK:
        return {name: b.snapshot() for name, b in _REGISTRY.items()}


def reset_all() -> None:
    """清空注册表（仅测试用）。"""
    with _REGISTRY_LOCK:
        _REGISTRY.clear()
```

**验证（两个终端都一样）**：
```bash
.venv3/Scripts/python.exe -c "from services.common.breaker import CircuitBreaker, CircuitOpenError, get_breaker, all_snapshots; print('OK breaker')"
```

**期望**：`OK breaker`

---

### 3.3 写 `services/common/client.py`（跨服务客户端）

> ⏱️ 约 250 行。🔴 勘误（2026-10-19）：实测版没有 `make_clients` / `set_trace_id`，只有 `get_client`（按名取用、全局单例）和 `_current_trace_id`（自动从 `app_my.core.logging.trace_id_var` 取）。**旧版整段覆盖**。

#### 文件全文（一字不改）

```python
# services/common/client.py
"""
服务间调用客户端（ServiceClient）—— 微服务之间唯一的"电话机"

它把四件事打包在一起，业务代码只管 client.post(...)，不用关心细节：
    ① HTTP 传输     ：用 httpx.AsyncClient（异步，不阻塞事件循环）
    ② 自动重试      ：网络抖动/对方 5xx 时按"指数退避"重试几次
    ③ 熔断保护      ：对方连续挂了就跳闸，立刻失败，不再陪它耗超时
    ④ 上下文透传    ：把 trace_id / tenant_id / user_id 放进请求头带过去

为什么要透传上下文：
    一次用户请求会穿过 "Kong → chat → recommender" 三个进程。
    如果不把 trace_id 带过去，三个进程各写各的日志，出问题时你根本没法把
    同一次请求的三段日志串起来看 —— 这就是"链路追踪"要解决的头号问题。
"""
from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Dict, Optional

import httpx

from services.common import breaker as breaker_mod

# 请求头名字，全项目统一（Kong 和各服务都用这三个）
HEADER_TRACE = "X-Trace-Id"
HEADER_TENANT = "X-Tenant-Id"
HEADER_USER = "X-User-Id"

# 这几类 HTTP 状态码才重试：429 是被限流（等一下再来），5xx 是对方出错。
# 4xx（401/403/404/422）是"请求本身有问题"，重试一万次也一样，不重试。
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ServiceCallError(RuntimeError):
    """服务调用最终失败时抛出。调用方 catch 它做降级。"""


def _current_trace_id() -> str:
    """
    取当前协程上下文里的 trace_id。

    为什么用 contextvars 而不是参数传递：
    trace_id 是"贯穿全链路的环境变量"，如果每个函数都加一个 trace_id 参数，
    从接口层到最深的工具函数要改几十个签名。contextvars 是 Python 官方给的
    "协程版全局变量"，在 await 链里自动传递，不需要改任何函数签名。
    """
    try:
        from app_my.core.logging import trace_id_var
        value = trace_id_var.get()
        return value if value and value != "-" else ""
    except Exception:
        return ""


def _upstream_token() -> str:
    """取上游请求带过来的 JWT（由 TokenCaptureMiddleware 存进 contextvars）。"""
    try:
        from services.common.context import get_upstream_token
        return get_upstream_token()
    except Exception:
        return ""


class ServiceClient:
    """
    针对某一个下游服务的客户端。一个下游服务一个实例（内部复用同一个连接池）。
    """

    def __init__(
        self,
        name: str,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
        retries: int = 2,
        backoff: float = 0.2,
        transport: Optional[Any] = None,
        **breaker_kwargs,
    ) -> None:
        """
        transport：可选的 httpx 传输层。正常运行时不传（走真实网络）；
        单元测试时传 httpx.MockTransport，就能在完全离线的情况下
        精确模拟"对方返回 503""连接超时"等各种故障，验证重试和熔断逻辑。
        """
        self.name = name
        self._transport = transport
        self.base_url = (base_url or os.getenv(
            f"SERVICE_{name.upper()}_URL", f"http://127.0.0.1:{_default_port(name)}"
        )).rstrip("/")
        self.timeout = timeout
        self.retries = retries          # 首次失败后再试几次（不含第一次）
        self.backoff = backoff          # 退避基数：第 n 次等待 backoff * 2^(n-1) 秒
        self.breaker = breaker_mod.get_breaker(name, **breaker_kwargs)
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ 连接管理
    def _ensure_client(self) -> httpx.AsyncClient:
        """
        懒创建 httpx.AsyncClient。

        为什么不每次请求 new 一个：
        AsyncClient 内部持有连接池，复用它能省掉反复 TCP 握手 + TLS 的开销。
        但也不能在 __init__ 里创建 —— 那时可能还没有事件循环。
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 2.0)),
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        """关闭连接池。服务关闭时调用，否则会有连接泄漏警告。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------ 对外方法
    async def post(self, path: str, payload: Optional[Dict[str, Any]] = None,
                   **kwargs) -> Dict[str, Any]:
        """POST JSON。返回对方响应的 JSON 字典。"""
        return await self.request("POST", path, json=payload, **kwargs)

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None,
                  **kwargs) -> Dict[str, Any]:
        """GET。返回对方响应的 JSON 字典。"""
        return await self.request("GET", path, params=params, **kwargs)

    async def request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        trace_id: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发请求的核心方法：熔断闸门 → 重试循环 → 回写熔断状态。

        参数：
            method     HTTP 方法（"GET" / "POST"）
            path       路径，如 "/internal/nodes/recommend"
            json       POST 的请求体（字典）
            params     GET 的查询参数（字典）
            tenant_id  要透传的租户 ID（不传就不带这个头）
            user_id    要透传的用户 ID
            trace_id   要透传的链路 ID（不传就自动从 contextvars 里取）
            auth_token 要透传的 JWT（形如 "Bearer xxx"）。
                       因为鉴权下沉在各服务内（Kong 不鉴权），跨服务调用必须把
                       用户的 token 原样带过去，否则对方 AuthMiddleware 直接 401。
                       不传时会自动从 contextvars 里取上游抓到的 token。
        """
        # ---- ① 熔断闸门：已跳闸就直接抛，不再发请求 ----
        self.breaker.before_call()

        headers: Dict[str, str] = {}
        tid = trace_id or _current_trace_id()
        if tid:
            headers[HEADER_TRACE] = tid
        if tenant_id is not None:
            headers[HEADER_TENANT] = str(tenant_id)
        if user_id is not None:
            headers[HEADER_USER] = str(user_id)

        token = auth_token or _upstream_token()
        if token:
            headers["Authorization"] = token

        last_error = ""
        client = self._ensure_client()

        # ---- ② 重试循环：第 0 次是正常请求，之后才是重试 ----
        for attempt in range(self.retries + 1):
            try:
                resp = await client.request(method, path, json=json, params=params, headers=headers)

                if resp.status_code in RETRYABLE_STATUS:
                    # 对方明确说"我现在不行"，算一次失败，可以重试
                    last_error = f"HTTP {resp.status_code}"
                    raise httpx.HTTPStatusError(last_error, request=resp.request, response=resp)

                if resp.status_code >= 400:
                    # 4xx 不重试：请求本身有问题，重试没意义。直接算成功"送达"，
                    # 让熔断知道对方还活着（它只是拒绝了我们的请求）。
                    self.breaker.record_success()
                    raise ServiceCallError(
                        f"[{self.name}] {method} {path} 返回 {resp.status_code}: {resp.text[:200]}"
                    )

                self.breaker.record_success()
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text}

            except breaker_mod.CircuitOpenError:
                raise                      # 熔断的错不重试，直接往上抛
            except ServiceCallError:
                raise                      # 4xx 的错不重试
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt >= self.retries:
                    break
                # 指数退避 + 抖动：0.2s → 0.4s → 0.8s…再加 ±20% 随机，
                # 避免"所有调用方同一时刻一起重试"把刚恢复的服务再次打垮（惊群）。
                delay = self.backoff * (2 ** attempt) * (1 + random.uniform(-0.2, 0.2))
                await asyncio.sleep(max(delay, 0.01))

        # ---- ③ 所有重试都失败：记一次熔断失败，再抛给调用方降级 ----
        self.breaker.record_failure(last_error)
        raise ServiceCallError(
            f"[{self.name}] {method} {path} 失败（重试 {self.retries} 次后）：{last_error}"
        )

    # ------------------------------------------------------------------ 观测
    def breaker_snapshot(self) -> Dict[str, object]:
        """导出这个下游服务当前熔断器的状态。"""
        return self.breaker.snapshot()


def _default_port(name: str) -> int:
    """各服务的默认端口（与 docker/kong/kong.yml 保持一致）。"""
    return {"user": 9121, "recognizer": 9122, "recommender": 9123, "chat": 9124}.get(name, 9002)


def get_client(name: str, **kwargs) -> ServiceClient:
    """
    取（必要时创建）某个下游服务的客户端。

    做成全局缓存的原因和熔断器一样：一个进程里对同一个下游只该有一个连接池。
    """
    global _CLIENTS
    if name not in _CLIENTS:
        _CLIENTS[name] = ServiceClient(name, **kwargs)
    return _CLIENTS[name]


_CLIENTS: Dict[str, ServiceClient] = {}


async def aclose_all() -> None:
    """关闭所有客户端的连接池（服务关闭时调用）。"""
    for c in _CLIENTS.values():
        await c.aclose()
    _CLIENTS.clear()
```

**验证（两个终端都一样）**：
```bash
.venv3/Scripts/python.exe -c "from services.common.client import ServiceClient, ServiceCallError, get_client, aclose_all; print('OK client')"
```

**期望**：`OK client`

---

### 3.4 写 `services/common/context.py`（token 上下文小仓库）

> ⏱️ 约 40 行。🔴 勘误（2026-10-19）：实测版存的是**上游 JWT**（不是 trace_id）。trace_id 直接复用阶段 7 的 `app_my.core.logging.trace_id_var`，不另造一份。

#### 文件全文（一字不改）

```python
# services/common/context.py
"""
跨服务调用的"上下文小仓库"—— 存放那些没法通过函数参数传递、但又必须带过去的东西

为什么单独一个文件：
    LangGraph 的节点函数签名被框架定死了：`async def node(state: dict) -> dict`。
    我们想在节点里发 HTTP 请求调用别的服务，就得带上用户的 JWT，
    但签名里塞不进去。contextvars 是 Python 官方为这种场景准备的方案：
    它在"协程上下文"里存值，await 链上任何深度都能读到，且不同请求之间互不干扰。

    类比：普通全局变量是"整栋楼共用一个白板"（并发时会串台）；
    contextvars 是"每个人手里一块自己的小白板"（各自独立，还能带进电梯）。
"""
from __future__ import annotations

import contextvars
from typing import Optional

# 上游请求带过来的原始 Authorization 头（形如 "Bearer eyJhbGci..."）
_upstream_token: contextvars.ContextVar[str] = contextvars.ContextVar(
    "upstream_token", default=""
)


def set_upstream_token(token: str) -> None:
    """在请求入口处把 token 存进来。"""
    _upstream_token.set(token or "")


def get_upstream_token() -> str:
    """在任意深度（包括 LangGraph 节点里）把 token 读出来。"""
    return _upstream_token.get() or ""


def auth_header() -> dict:
    """
    直接产出可以塞进 httpx 的请求头字典。
    没有 token 时返回空字典，避免发出一个值为空的 Authorization 头（对方会解析失败）。
    """
    token = get_upstream_token()
    return {"Authorization": token} if token else {}
```

**验证（两个终端都一样）**：
```bash
.venv3/Scripts/python.exe -c "from services.common.context import set_upstream_token, get_upstream_token, auth_header; set_upstream_token('Bearer x'); print(get_upstream_token(), auth_header())"
```

**期望**：`Bearer x {'Authorization': 'Bearer x'}`

---

### 3.5 写 `services/common/app_factory.py`（服务工厂）

> ⏱️ 约 200 行。🔴 勘误（2026-10-19）：项目里**没有** `app_my/middleware/cors.py`、`app_my/middleware/tracing.py`、`app_my/core/metrics.py` 这些模块——CORS 用 fastapi 自带的 `fastapi.middleware.cors`，Trace 是 `app_my.middleware.trace.TraceIdMiddleware`，Metrics 是 `app_my.middleware.metrics.MetricsMiddleware`。另有两个本阶段新增中间件 `TenantVarMiddleware` / `TokenCaptureMiddleware`（都定义在本文件内）。**旧版整段覆盖**。

#### 文件全文（一字不改）

```python
# services/common/app_factory.py
"""
服务工厂（create_service_app）—— 四个微服务的"统一装配线"

为什么要有它：
    拆成四个服务后，如果每个服务的 main.py 都抄一遍"加中间件 + 加健康检查 + 加指标端点"，
    很快就会抄歪：某个服务忘了加鉴权、另一个服务的 /metrics 被 401 挡住……
    工厂函数把这套装配固定成一份代码，四个服务共享，顺序只可能错一次。

🔴 本文件最关键的知识点：Starlette 的中间件"洋葱顺序"
    Starlette 规则：**后 add_middleware 的，包在更外层**。
    所以下面代码是"倒着写"的：越靠上的 add 语句，请求越晚经过它（越靠里）。
    请求实际经过顺序（外 → 内）：
        CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
              → UserLimit → RateLimit → (Quota) → 路由
    响应返回时反过来走一遍（内 → 外）。

    🔴 两条不能违反的顺序约束：
    1. MetricsMiddleware 必须 add 在 AuthMiddleware **之前**（这样它才更靠外），
       否则 /metrics 会先被 Auth 拦下返回 401，Prometheus 永远抓不到数据。
    2. CORS 必须最后 add（最外层），否则内层限流吐出的 429 响应不带跨域头，
       浏览器前端只能看到"网络错误"，根本不知道自己是被限流了。
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import List, Optional, Sequence, Tuple

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app_my.core.config import settings
from app_my.core.logging import logger, setup_logging
from app_my.core.tenant import current_tenant_id
from app_my.middleware.auth import AuthMiddleware
from app_my.middleware.metrics import MetricsMiddleware
from app_my.middleware.quota import QuotaMiddleware
from app_my.middleware.rate_limit import RateLimitMiddleware, UserRateLimitMiddleware
from app_my.middleware.tenant import TenantContextMiddleware
from app_my.middleware.trace import TraceIdMiddleware


# ---------------------------------------------------------------- 两个本阶段新增的小中间件
class TenantVarMiddleware(BaseHTTPMiddleware):
    """
    把 request.state.tenant_id 写进 contextvars（current_tenant_id）。

    为什么必须新写一个：
    现有的 TenantContextMiddleware 只写 request.state，**不写 contextvars**。
    单体时代没问题——因为 app_my/agents/coordinator.py 里手动 set 了一次。
    但拆成微服务后，recommender 进程里跑的 recommend_node 深处会调
    local_recipe_search()，它靠 current_tenant_id 做灰度判定；
    这个进程里没人 set，就会一直用默认值 1 —— 灰度/租户隔离静默失效。

    🔴 这是本次拆分最容易漏、且最难查的一个点：
    不报错、不崩溃，只是"租户 B 用成了租户 A 的配置"。
    """

    async def dispatch(self, request: Request, call_next):
        tenant_id = getattr(request.state, "tenant_id", None)
        # 没有租户（未登录 / 内部探测）就保留默认值，不强行写 0
        token = current_tenant_id.set(tenant_id if tenant_id is not None else 1)
        try:
            return await call_next(request)
        finally:
            # 必须 reset：不然同一个线程处理下一个请求时会读到上一个租户（连接池复用场景）
            current_tenant_id.reset(token)


class TokenCaptureMiddleware(BaseHTTPMiddleware):
    """
    把原始 Authorization 头存进 contextvars，供"跨服务调用"时透传。

    为什么需要：chat 服务要去调 recommender 服务，而 recommender 也有 AuthMiddleware
    （鉴权下沉在各自服务内，Kong 不做鉴权）。所以 chat 必须把用户的 JWT 原样带过去，
    否则对方直接 401。

    为什么用 contextvars 而不是一层层传参：
    LangGraph 的节点函数签名是固定的 `async def node(state: dict) -> dict`，
    没法额外塞一个 token 参数。contextvars 让我们"绕开签名"把值带进去。
    """

    async def dispatch(self, request: Request, call_next):
        from services.common.context import set_upstream_token
        set_upstream_token(request.headers.get("authorization", ""))
        return await call_next(request)


# ---------------------------------------------------------------- 工厂函数
def create_service_app(
    service_name: str,
    routers: Sequence[Tuple[APIRouter, str, List[str]]] = (),
    *,
    enable_auth: bool = True,
    enable_quota: bool = False,
    capture_auth: bool = False,
    cors_origins: Optional[List[str]] = None,
    startup_tasks: Sequence[Callable[[], Coroutine]] = (),
) -> FastAPI:
    """
    造一个"装配好"的 FastAPI 服务实例。

    参数：
        service_name   服务名（user / recognizer / recommender / chat），进 /health 和日志
        routers        要挂的路由，每个元素是 (router, prefix, tags) 三元组
        enable_auth    是否挂 JWT 鉴权中间件（四个服务都要 True）
        enable_quota   是否挂租户配额中间件（只有 chat 服务要 True，因为它管 /chat/stream）
        capture_auth   是否捕获 Authorization 头用于跨服务透传（只有 chat 服务要 True）
        cors_origins   允许的跨域来源；不传就用 settings.CORS_ORIGINS
        startup_tasks  要常驻运行的后台协程工厂（如 chat 服务的 Redis 订阅中继）。
                       传进来的是"函数"而不是"协程对象"，因为协程对象只能被 await 一次；
                       传函数才能在每个进程里重新创建。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        logger.info("服务 [%s] 启动中 ...", service_name)

        # 拉起常驻后台协程（如 WS 通知中继），并把句柄存起来以便关闭时取消
        tasks = [asyncio.create_task(factory(), name=f"{service_name}-bg-{i}")
                 for i, factory in enumerate(startup_tasks)]
        if tasks:
            logger.info("服务 [%s] 已启动 %d 个后台协程", service_name, len(tasks))

        yield

        logger.info("服务 [%s] 关闭", service_name)
        # 先取消后台协程再收尾，否则事件循环关闭时会报
        # "Task was destroyed but it is pending!"
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        # 关闭跨服务调用客户端的连接池，否则进程退出会有 "unclosed connector" 警告
        try:
            from services.common.client import aclose_all
            await aclose_all()
        except Exception:
            pass

    app = FastAPI(
        title=f"{settings.APP_NAME} · {service_name}服务",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # ============ 中间件（🔴 倒着 add：越靠上的越靠里）============
    if capture_auth:
        app.add_middleware(TokenCaptureMiddleware)      # 最里层：先把 token 抓到手

    if enable_quota:
        app.add_middleware(QuotaMiddleware)             # 租户配额（只有 chat 用）

    app.add_middleware(RateLimitMiddleware)             # 4. IP 级限流
    app.add_middleware(UserRateLimitMiddleware)         # 3. 用户级限流
    app.add_middleware(TenantVarMiddleware)             # 2.6 写 contextvars（本阶段新增）
    app.add_middleware(TenantContextMiddleware)         # 2.5 租户上下文
    if enable_auth:
        app.add_middleware(AuthMiddleware)              # 2. JWT 鉴权
    app.add_middleware(MetricsMiddleware)               # 1.5 指标埋点 + /metrics（必须在 Auth 之外）
    app.add_middleware(TraceIdMiddleware)               # 1. TraceID
    app.add_middleware(                                 # 0. CORS（最后 add → 最外层）
        CORSMiddleware,
        allow_origins=cors_origins or settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ============ 路由 ============
    for router, prefix, tags in routers:
        app.include_router(router, prefix=prefix, tags=tags)

    # ============ 通用端点：每个服务都有，方便 Kong 探活与排错 ============
    @app.get("/")
    async def root():
        return {"service": service_name, "version": settings.APP_VERSION, "status": "running"}

    @app.get("/health")
    async def health():
        """
        健康检查。除了返回 ok，还带上"我依赖的下游服务熔断器状态"——
        排障时一眼就能看出 chat 是不是把 recommender 熔断了。
        """
        from services.common.breaker import all_snapshots
        return {
            "status": "ok",
            "service": service_name,
            "version": settings.APP_VERSION,
            "breakers": all_snapshots(),
        }

    return app
```

**验证（两个终端都一样）**：
```bash
.venv3/Scripts/python.exe -c "from services.common.app_factory import create_service_app, TenantVarMiddleware, TokenCaptureMiddleware; print('OK factory')"
```

**期望**：`OK factory`

---

## 4. 写四个服务的入口 `main.py`

> 🔴 勘误（2026-10-19）：四个 main 的路由归属以下面这份为准（与 22 个测试、Kong 配置一致）。
> 归属速记：**kg/oss/cache/admin/billing 的挂载位置最容易记错**——
> `/kg` 归 recommender（图谱/向量库的 owner），`/oss` 归 recognizer（先传图才能识别），
> `/cache` 归 user，`/memory` 这个路由**根本不存在**（记忆功能在 `/chat` 内部），
> `/tasks` 和 `/ws` 归 chat。

### 4.1 `services/user/main.py`

```python
# services/user/main.py
"""
user 服务（端口 9121）—— 管"人"和"组织"的一切

职责边界（为什么这些路由放一起）：
    认证（auth）、用户资料（user）、租户（tenant）、管理端（admin）、成本统计（billing）
    这五组路由的共同点是：**它们只碰 PostgreSQL 和 Redis，不碰大模型**。
    这是拆分的第一条依据——资源画像相同的功能放一起，扩容时可以单独加机器，
    不用为了给"对话"扩容而连带把"登录"也复制一份。

它不做什么：不调大模型、不碰 Milvus、不碰 Neo4j。
"""
from services.common.app_factory import create_service_app

# 复用单体时代已经写好的路由模块：拆分是"换入口"，不是"重写业务"
from app_my.api import auth, user, cache
from app_my.api import tenant as tenant_api
from app_my.api import admin as admin_api
from app_my.api import billing

app = create_service_app(
    "user",
    routers=[
        (auth.router, "/auth", ["认证"]),
        (user.router, "/users", ["用户"]),
        (tenant_api.router, "/tenants", ["租户管理"]),
        (admin_api.router, "/admin", ["管理端"]),
        (billing.router, "/billing", ["成本统计"]),
        (cache.router, "/cache", ["缓存观测"]),
    ],
    enable_auth=True,      # 有自己的 JWT 鉴权（Kong 不鉴权，鉴权下沉在各自服务）
    enable_quota=False,    # 配额只管 /chat/stream，那是 chat 服务的事
    capture_auth=False,    # user 服务不往下调别的服务，不用透传 token
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.user.main:app", host="0.0.0.0", port=9121, reload=False)
```

### 4.2 `services/recognizer/main.py`

```python
# services/recognizer/main.py
"""
recognizer 服务（端口 9122）—— 把"用户说了什么 / 拍了什么"变成结构化食材清单

拆出来的理由（拆分依据第二条：故障半径）：
    识别节点要调**多模态大模型**（看图），是所有节点里最慢、最贵、最容易超时的一环。
    它单独成一个服务，好处很实在：
      · 它超时/报错时，只影响"识别"，chat 服务还能用上一轮结果继续跑；
      · 它慢的时候可以单独加实例（比如 2 个 recognizer + 1 个 chat）；
      · 改识别模型不用重启整个应用。

对外只有两个"内部接口"（/internal/ 前缀，约定只给服务间调用）：
    POST /internal/nodes/recognize   文字/图片 → 食材清单
    POST /internal/nodes/nutrition   食材清单 → 营养估算

🔴 为什么要重新包一层 HTTP 接口，而不是直接把 state 整个传过来：
    LangGraph 的 state 里有 messages 字段，里面装的是 LangChain 的
    HumanMessage / AIMessage **对象**，不是 JSON。直接 json.dumps 会报
    "Object of type HumanMessage is not JSON serializable"。
    所以这里定了一套"只传必要字段"的窄接口：进 JSON、出 JSON。
"""
from typing import List, Optional

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app_my.agents.nutritionist import nutrition_node
from app_my.agents.recognizer import recognize_node
from app_my.api import oss
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


# ----------------------------------------------------------------- 接口的数据契约
class RecognizeIn(BaseModel):
    """识别接口的入参。"""
    text: str = Field(default="", description="用户输入的文字（图片模式下可作补充提示）")
    image_url: List[str] = Field(default_factory=list, description="图片 URL 列表，空数组=走文字抽取")


class NutritionIn(BaseModel):
    """营养接口的入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="上一步识别出的食材清单")


def _summary_of(node_output: dict) -> str:
    """
    从节点返回值里抽出那条 AIMessage 的文本，作为 summary 返回。

    节点返回形如 {"nutrition": {...}, "messages": [AIMessage("...")]}；
    messages 是 LangChain 对象不能进 JSON，所以这里提前把它转成纯字符串。
    """
    msgs = node_output.get("messages") or []
    if msgs:
        return getattr(msgs[-1], "content", "") or ""
    return ""


router = APIRouter()


@router.post("/internal/nodes/recognize")
async def http_recognize(body: RecognizeIn):
    """
    把 recognize_node 包成 HTTP 接口。

    做法：造一个"最小可用的 state" → 调原来的节点函数 → 把结果转成纯 JSON。
    这样**一个字的业务逻辑都没重写**，只是加了一层协议转换。
    """
    state = {
        "messages": [HumanMessage(content=body.text)],   # 节点只读最后一条消息的 content
        "image_url": body.image_url or [],
    }
    out = await recognize_node(state)
    logger.info("recognizer.http: 识别完成，%d 种食材", len(out.get("ingredients") or []))
    return {
        "ingredients": out.get("ingredients") or [],
        "summary": _summary_of(out),
    }


@router.post("/internal/nodes/nutrition")
async def http_nutrition(body: NutritionIn):
    """把 nutrition_node 包成 HTTP 接口。"""
    state = {"ingredients": body.ingredients or []}
    out = await nutrition_node(state)
    return {
        "nutrition": out.get("nutrition") or {},
        "summary": _summary_of(out),
    }


app = create_service_app(
    "recognizer",
    routers=[
        (router, "", ["识别内部接口"]),
        (oss.router, "/oss", ["阿里云OSS"]),   # 图片要先上传才能识别，归识别域
    ],
    enable_auth=True,      # 一样要鉴权：Kong 不做鉴权，靠各服务自己守门
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recognizer.main:app", host="0.0.0.0", port=9122, reload=False)
```

### 4.3 `services/recommender/main.py`

```python
# services/recommender/main.py
"""
recommender 服务（端口 9123）—— 管"找菜谱"和"排菜谱"，以及知识图谱

拆出来的理由（拆分依据第三条：数据所有权）：
    Milvus 向量库和 Neo4j 图谱**只被这一个服务访问**。
    拆分前 chat 进程里也连着这两个库，现在它们成了 recommender 的"私有数据"，
    别的服务想查菜谱，只能走 HTTP 来问它 —— 这就是微服务的"数据所有权"原则。

对外接口：
    POST /internal/nodes/recommend   食材清单 → 候选菜谱（未排序）
    POST /internal/nodes/rank        候选菜谱 + 用户画像 → 排好序的菜谱
    GET  /kg/ask                     知识图谱问答（阶段 3 的路由，原样搬过来）
    GET  /kg/stats                   图谱规模统计

🔴 本服务最需要注意的一点（也是本次拆分最容易踩的坑）：
    local_recipe_search() 内部会读 current_tenant_id 这个 contextvars 变量做灰度判定。
    单体时代是 coordinator 手动 set 的；现在它跑在 recommender 自己的进程里，
    没人 set 就会一直用默认值 1 —— 表现为"灰度开关对所有租户一起生效/失效"，
    而且**不报错**。
    解决办法在 services/common/app_factory.py 的 TenantVarMiddleware：
    每个请求进来时把 request.state.tenant_id 写进 contextvars。
"""
from typing import List

from fastapi import APIRouter
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app_my.agents.ranker import rank_node
from app_my.agents.recommender import recommend_node
from app_my.api import kg
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


class RecommendIn(BaseModel):
    """推荐接口入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="识别出的食材清单")


class RankIn(BaseModel):
    """重排接口入参。"""
    recipes: List[dict] = Field(default_factory=list, description="候选菜谱（推荐节点的产出）")
    user_profile: dict = Field(default_factory=dict, description="用户画像（目标/忌口/过敏/偏好）")


def _summary_of(node_output: dict) -> str:
    """把节点返回里的 AIMessage 转成纯字符串（LangChain 对象不能进 JSON）。"""
    msgs = node_output.get("messages") or []
    return getattr(msgs[-1], "content", "") if msgs else ""


router = APIRouter()


@router.post("/internal/nodes/recommend")
async def http_recommend(body: RecommendIn):
    """把 recommend_node 包成 HTTP 接口。"""
    out = await recommend_node({"ingredients": body.ingredients or []})
    recipes = out.get("recipes") or []
    logger.info("recommender.http: 检索到 %d 条候选菜谱", len(recipes))
    return {"recipes": recipes, "summary": _summary_of(out)}


@router.post("/internal/nodes/rank")
async def http_rank(body: RankIn):
    """把 rank_node 包成 HTTP 接口。"""
    out = await rank_node({
        "recipes": body.recipes or [],
        "user_profile": body.user_profile or {},
    })
    ranked = out.get("ranked_recipes") or []
    logger.info("recommender.http: 重排完成，%d 条", len(ranked))
    return {"ranked_recipes": ranked, "summary": _summary_of(out)}


app = create_service_app(
    "recommender",
    routers=[
        (router, "", ["推荐内部接口"]),
        (kg.router, "/kg", ["知识图谱"]),
    ],
    enable_auth=True,
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recommender.main:app", host="0.0.0.0", port=9123, reload=False)
```

### 4.4 `services/chat/main.py`

```python
# services/chat/main.py
"""
chat 服务（端口 9124）—— 用户真正"说话"的入口，也是唯一会去调别的服务的地方

它承担三件事：
    1. /chat/stream   流式对话（LangGraph 编排，可能跨服务调 recognizer / recommender）
    2. /ws/notifications  WebSocket 实时推送（阶段 8）
    3. /tasks/*       长任务提交与查询（阶段 8）

它是本阶段唯一打开了两个"额外开关"的服务：
    enable_quota=True   因为 /chat/stream 要按租户配额限流（QuotaMiddleware 只认这个路径）
    capture_auth=True   因为它要跨服务调用，必须把用户的 JWT 抓下来透传给下游
    startup_tasks       因为 WS 通知中继（订阅 Redis 频道）必须常驻在 chat 进程里
"""
import os

from app_my.api import chat
from app_my.api import tasks as tasks_api
from app_my.ws import gateway as ws_gateway
from app_my.ws.relay import run_relay

from services.common.app_factory import create_service_app


# 读一次运行模式，写进启动日志，方便排错时一眼确认
SPLIT_MODE = os.getenv("SPLIT_MODE", "local").strip().lower()


app = create_service_app(
    "chat",
    routers=[
        (chat.router, "/chat", ["AI对话"]),
        (tasks_api.router, "/tasks", ["异步任务"]),
        (ws_gateway.router, "/ws", ["WebSocket"]),
    ],
    enable_auth=True,
    enable_quota=True,     # 只有 chat 需要：QuotaMiddleware 拦截 /chat/stream 做租户配额
    capture_auth=True,     # 只有 chat 需要：把 JWT 存进 contextvars 以便透传给下游
    startup_tasks=[run_relay],   # WS 通知中继常驻协程
)


@app.get("/mode")
async def mode():
    """运维小端点：一眼看出这个 chat 进程现在是本地模式还是远程模式。"""
    return {
        "service": "chat",
        "split_mode": SPLIT_MODE,
        "remote_nodes": SPLIT_MODE == "remote",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.chat.main:app", host="0.0.0.0", port=9124, reload=False)
```

### 4.5 验证四个服务能导入

**两个终端都一样**：
```bash
.venv3/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
for m in ['services.user.main','services.recognizer.main','services.recommender.main','services.chat.main']:
    mod = __import__(m, fromlist=['app'])
    paths = sorted(mod.app.openapi()['paths'].keys())
    print('OK', m, len(paths), '条路由')
    for p in paths[:5]: print('   ', p)
"
```

**期望**（数字与路径为实测值，顺序按字典序）：
```
OK services.user.main 19 条路由
    /
    /admin/audit/logs
    /admin/feature-flags
    /admin/feature-flags/{name}
    /auth/login
OK services.recognizer.main 5 条路由
    /
    /health
    /internal/nodes/nutrition
    /internal/nodes/recognize
    /oss/presign
OK services.recommender.main 6 条路由
    /
    /health
    /internal/nodes/rank
    /internal/nodes/recommend
    /kg/ask
OK services.chat.main 8 条路由
    /
    /chat/stream
    /health
    /mode
    /tasks/nutrition-report
```

> 🔴 如果任何一个 `OK` 变成 `ImportError`，回到 §3/§4 检查是否还有旧版代码没覆盖——
> 典型报错就是 `cannot import name 'memory' from 'app_my.api'`（旧版手册的错误 import）。

---

## 5. 改 chat 的 coordinator：按 `SPLIT_MODE` 切本地/远程节点图

> 🔴 勘误（2026-10-19）：旧版的"`coordinator_local.py` + `app_my/agents/graph_remote.py`"方案**作废**。
> 实测通过的方案：`build_workflow()` 加一个 `nodes` 参数——不传就是本地节点（原行为一行不改），
> 传了就用传入的节点表注册图。远程节点表放在 **`services/chat/graph_remote.py`**。
> **不需要新建 `coordinator_local.py`**（图的连边代码本来就只有一份，无需抽两份）。

### 5.1 修改 `app_my/agents/coordinator.py`（本项目唯一被改的老文件）

**定位锚点**：打开 `app_my/agents/coordinator.py`，从 `def build_workflow():` 这一行开始，一直选到 `get_coordinator_agent()` 函数的 `return _agent` 为止，**整段删除**，贴入下面内容：

```python
def build_workflow(nodes=None):
    """
    组装并编译工作流。

    add_edge 的两种写法：
        add_edge("recognize", "nutrition")         一次只接一个下游 → 顺序执行
        add_edge(["nutrition", "recommend"], "rank") 多个起点汇聚到同一节点 → 等待全部完成再走

    v3阶段9 新增参数 nodes：
        传 None（默认）→ 用本地节点，行为和阶段 8 之前完全一致（单体模式）。
        传一张"节点名 → 函数"的表 → 用这张表注册节点（微服务模式下换成 HTTP 版节点）。
        这样"图的形状"和"节点怎么实现"就解耦了：拆不拆微服务，连边代码一行都不用改。
    """
    if nodes is None:
        nodes = {
            "recognize": recognize_node,
            "nutrition": nutrition_node,
            "recommend": recommend_node,
            "rank": rank_node,
            "output": output_node,
        }

    workflow = StateGraph(ChefState)

    # ① 注册节点（名字 → 函数）
    for name, fn in nodes.items():
        workflow.add_node(name, fn)

    # ② 连边（数据流向）
    workflow.add_edge(START, "recognize")
    workflow.add_edge("recognize", "nutrition")        # 识别 → 营养（并行分支 1）
    workflow.add_edge("recognize", "recommend")        # 识别 → 推荐（并行分支 2）
    workflow.add_edge(["nutrition", "recommend"], "rank")   # fan-in：两支都完成才重排
    workflow.add_edge("rank", "output")
    workflow.add_edge("output", END)

    return workflow.compile()


# 惰性单例：编译图有开销，但也不能在 import 时就编译（否则单测/无密钥环境会受影响）
_agent = None


def _resolve_nodes():
    """
    按环境变量 SPLIT_MODE 决定节点用本地版还是远程版（v3阶段9 新增）。

        SPLIT_MODE=local（默认）  → 全部节点在本进程内跑（单体行为，拆分前/对照组用）
        SPLIT_MODE=remote        → 识别/营养/推荐/重排改走 HTTP 调各自的服务

    为什么要做成环境变量而不是硬改代码：
    阶段 9 的验收项之一是"用阶段 7 的指标给出拆分前后对比"——
    同一个代码库，改一个环境变量就能在"单体"和"微服务"两种形态间切换，
    压测才有可比性（否则你得维护两套代码）。
    """
    import os
    if os.getenv("SPLIT_MODE", "local").strip().lower() == "remote":
        from services.chat.graph_remote import remote_nodes
        logger.info("coordinator: SPLIT_MODE=remote，识别/营养/推荐/重排改走 HTTP 调用")
        return remote_nodes()
    return None


def get_coordinator_agent():
    """取（必要时创建）编译后的工作流单例"""
    global _agent
    if _agent is None:
        logger.info("coordinator: 首次编译 StateGraph")
        _agent = build_workflow(nodes=_resolve_nodes())
    return _agent


def reset_coordinator_agent() -> None:
    """测试用：丢掉单例，下次重新编译"""
    global _agent
    _agent = None
```

> 🔴 文件顶部的 import（5 个节点函数 + `ChefState` + `logger`）**保持不动**；
> `_resolve_nodes()` 里对 `services.chat.graph_remote` 的 import 是**函数内懒 import**，
> 保证 `SPLIT_MODE=local` 时即使没建 `services/` 目录也不报错。

### 5.2 新增 `services/chat/graph_remote.py`（远程节点表）

```python
# services/chat/graph_remote.py
"""
远程节点（remote nodes）—— 把"本地函数调用"换成"HTTP 调用别的服务"

一句话理解：
    单体时代，LangGraph 的 recognize 节点 = 直接 `await recognize_node(state)`（进程内函数调用）。
    拆成微服务后，同一个节点 = `await client.post("/internal/nodes/recognize", ...)`（跨进程 HTTP）。
    **图的形状一点没变**（还是 识别→营养/推荐→重排→输出），变的只是节点内部怎么干活。

🔴 本文件的灵魂：降级（degradation）
    每个远程节点都用 try/except 包住。远程服务挂了（连接失败 / 熔断跳闸 / 5xx），
    节点**不抛异常**，而是返回一个"空但合法"的结果 + 一条说明消息。
    为什么：
        LangGraph 里一个节点抛异常，整条工作流就崩了，用户看到 500。
        但"推荐服务挂了"其实不该让"营养估算"也一起完蛋——
        降级后用户拿到的是"营养报告完整、菜谱部分暂时不可用"，体验好得多，
        这正是"故障隔离"要的效果。
    这也就是验收项「杀掉单个服务，其余功能不受影响」的实现方式。
"""
from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import AIMessage

from app_my.agents.output import output_node
from app_my.agents.recognizer import message_content_to_text
from app_my.core.logging import logger
from app_my.core.tenant import current_tenant_id
from services.common.client import get_client


def _user_text(state: dict) -> str:
    """从 state 里取用户最后一句话的纯文本（支持多模态 content 是 list 的情况）。"""
    messages = state.get("messages") or []
    if not messages:
        return ""
    return message_content_to_text(messages[-1].content)


def _ai(content: str) -> List[AIMessage]:
    """包一条 AIMessage —— 图要求节点返回 messages，用来记录过程。"""
    return [AIMessage(content=content)]


# ------------------------------------------------------------------ ① 识别节点（远程）
async def recognize_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做食材识别。"""
    tenant_id = current_tenant_id.get()
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/recognize",
            {"text": _user_text(state), "image_url": state.get("image_url") or []},
            tenant_id=tenant_id,
        )
        return {
            "ingredients": data.get("ingredients") or [],
            "messages": _ai(data.get("summary") or "[识别] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recognize 失败，已降级：%s", exc)
        return {"ingredients": [], "messages": _ai(f"[识别] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ② 营养节点（远程）
async def nutrition_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做营养估算（营养和识别同域，都在 recognizer）。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"nutrition": {}, "messages": _ai("[营养] 无食材，跳过")}
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/nutrition",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "nutrition": data.get("nutrition") or {},
            "messages": _ai(data.get("summary") or "[营养] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.nutrition 失败，已降级：%s", exc)
        return {"nutrition": {}, "messages": _ai(f"[营养] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ③ 推荐节点（远程）
async def recommend_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）检索候选菜谱。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"recipes": [], "messages": _ai("[推荐] 无食材，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/recommend",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "recipes": data.get("recipes") or [],
            "messages": _ai(data.get("summary") or "[推荐] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recommend 失败，已降级：%s", exc)
        # 降级：没有菜谱，但工作流继续往下走（营养部分仍然完整）
        return {"recipes": [], "messages": _ai(f"[推荐] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ④ 重排节点（远程）
async def rank_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）做个性化重排。"""
    tenant_id = current_tenant_id.get()
    recipes = state.get("recipes") or []
    if not recipes:
        return {"ranked_recipes": [], "messages": _ai("[重排] 无候选菜谱，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/rank",
            {"recipes": recipes, "user_profile": state.get("user_profile") or {}},
            tenant_id=tenant_id,
        )
        return {
            "ranked_recipes": data.get("ranked_recipes") or [],
            "messages": _ai(data.get("summary") or "[重排] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.rank 失败，已降级：%s", exc)
        return {"ranked_recipes": [], "messages": _ai(f"[重排] 服务不可用，已跳过：{exc}")}


def remote_nodes() -> Dict[str, object]:
    """
    返回"远程版"的节点表。

    注意 output 仍然是**本地**的：
    它是纯文本拼装，不调外部资源，没有必要再跨一次网络（多一跳 = 多一个故障点）。
    这也体现了一条拆分原则：**不是所有东西都要拆，只拆有独立资源/故障特征的**。
    """
    return {
        "recognize": recognize_node_remote,
        "nutrition": nutrition_node_remote,
        "recommend": recommend_node_remote,
        "rank": rank_node_remote,
        "output": output_node,
    }
```

### 5.3 验证

**Git Bash**：
```bash
SPLIT_MODE=local .venv3/Scripts/python.exe -c "from app_my.agents.coordinator import get_coordinator_agent; get_coordinator_agent(); print('OK local graph')"
SPLIT_MODE=remote .venv3/Scripts/python.exe -c "from app_my.agents.coordinator import _resolve_nodes; print('OK remote nodes:', sorted(__import__('app_my.agents.coordinator',fromlist=['x'])._resolve_nodes().keys()))"
```

**PowerShell 5.1**：
```powershell
$env:SPLIT_MODE="local"; .\.venv3\Scripts\python.exe -c "from app_my.agents.coordinator import get_coordinator_agent; get_coordinator_agent(); print('OK local graph')"
$env:SPLIT_MODE="remote"; .\.venv3\Scripts\python.exe -c "from app_my.agents.coordinator import _resolve_nodes; print('OK remote nodes:', sorted(_resolve_nodes().keys()))"
$env:SPLIT_MODE=""
```

**期望**：
```
OK local graph
coordinator: SPLIT_MODE=remote，识别/营养/推荐/重排改走 HTTP 调用
OK remote nodes: ['nutrition', 'output', 'rank', 'recommend', 'recognize']
```

> 注意 `output` 也在远程表里——但它是**本地实现**（纯文本拼装，不值得多跨一跳网络）。

---

## 6. 写 22 个单元测试并真跑

> 🔴 勘误（2026-10-19）：实测通过的真实计数是 **8 + 7 + 7 = 22 passed**（旧版写 27 是错的）。
> 旧版测试代码用的 `threshold=` / `ServiceCallError` / `cb.state = "open"`（直接赋值）在实测版里**全都不存在**——
> `state` 是只读 property，直接赋值会抛 `AttributeError`。以下面三个文件为准，**旧文件整段覆盖**。

### 6.1 `tests/unit/test_circuit_breaker.py`（8 用例）

> 🔴 勘误（2026-10-19 第二批）：本节不再分"Git Bash 创建 / PowerShell 5.1 创建"两套——
> 文件内容完全相同，给一份即可。推荐直接在 VSCode 里新建文件、整段粘贴、Ctrl+S 保存
> （你上次就是把 `cat > ...` 整段贴进文件导致 `NameError: cat is not defined`）。
> 真正需要区分终端的只是**运行命令**（见 §6.4 与附录 C）。

**文件内容**（`tests/unit/test_circuit_breaker.py`，整段粘贴保存）：
```python
# tests/unit/test_circuit_breaker.py —— v3 阶段 9：熔断器状态机（纯内存，不依赖任何服务）
"""
覆盖点：
1. 初始是 CLOSED，失败没到阈值不跳闸；
2. 连续失败到阈值 → OPEN，before_call 抛 CircuitOpenError（快速失败）；
3. OPEN 期间成功不算数，必须等恢复时间 → 自动转 HALF_OPEN；
4. HALF_OPEN 放一个请求过去：成功 → 合闸 CLOSED；失败 → 重新跳闸；
5. snapshot() 字段齐全（给 /health 用）；
6. 注册表：同名只创建一个实例，reset_all 清空。

为什么用同步用例 + 直接改 _opened_at：
    熔断器的核心是"时间驱动"的状态迁移。等 30 秒再断言太慢，
    直接把跳闸时刻往前拨（_opened_at = now - 999）就能立刻进入可试探状态。
"""
import time

from services.common.breaker import (
    CircuitBreaker,
    CircuitOpenError,
    all_snapshots,
    get_breaker,
    reset_all,
)


def test_stays_closed_before_threshold():
    """失败次数没到阈值时不能跳闸——否则一次网络抖动就把服务判死了。"""
    b = CircuitBreaker("t1", failure_threshold=3)
    b.record_failure("e1")
    b.record_failure("e2")
    assert b.state.value == "closed"
    b.before_call()          # 不抛异常
    assert b.snapshot()["failures"] == 2


def test_trips_open_at_threshold():
    """连续 3 次失败 → 跳闸，之后的调用直接抛错，不再消耗超时等待。"""
    b = CircuitBreaker("t2", failure_threshold=3, recovery_timeout=30)
    for i in range(3):
        b.record_failure(f"e{i}")
    assert b.state.value == "open"
    try:
        b.before_call()
        assert False, "OPEN 状态应该抛 CircuitOpenError"
    except CircuitOpenError as e:
        assert "跳闸" in str(e)


def test_success_resets_failure_counter():
    """成功一次就把连续失败计数清零——'连续'两个字很关键，偶发失败不该累积。"""
    b = CircuitBreaker("t3", failure_threshold=3)
    b.record_failure("e1")
    b.record_failure("e2")
    b.record_success()
    assert b.snapshot()["failures"] == 0
    b.record_failure("e3")
    b.record_failure("e4")
    assert b.state.value == "closed"     # 只有 2 次连续失败，没到 3


def test_open_becomes_half_open_after_timeout():
    """过了恢复时间，OPEN 自动降级成 HALF_OPEN，允许放一个请求试探。"""
    b = CircuitBreaker("t4", failure_threshold=1, recovery_timeout=30)
    b.record_failure("boom")
    assert b.state.value == "open"
    b._opened_at = time.time() - 999     # 把跳闸时刻往前拨，模拟"已经等够了"
    assert b.state.value == "half_open"
    b.before_call()                      # HALF_OPEN 有 1 个名额，不抛
    try:
        b.before_call()                  # 名额用完，第二个要拒绝
        assert False, "试探名额应该只有 1 个"
    except CircuitOpenError:
        pass


def test_half_open_success_closes():
    """试探成功 → 合闸，服务恢复正常。"""
    b = CircuitBreaker("t5", failure_threshold=1, recovery_timeout=30)
    b.record_failure("boom")
    b._opened_at = time.time() - 999
    assert b.state.value == "half_open"
    b.before_call()
    b.record_success()
    assert b.state.value == "closed"
    assert b.snapshot()["failures"] == 0


def test_half_open_failure_reopens():
    """试探失败 → 立刻重新跳闸，并把计时器重置（再等一整轮）。"""
    b = CircuitBreaker("t6", failure_threshold=1, recovery_timeout=30)
    b.record_failure("boom")
    b._opened_at = time.time() - 999
    b.before_call()
    b.record_failure("still down")
    assert b.state.value == "open"
    assert b.snapshot()["recover_in"] > 25     # 计时器确实被重置了


def test_snapshot_fields():
    """snapshot 是给 /health 和排障看的，字段必须齐全。"""
    b = CircuitBreaker("t7", failure_threshold=5)
    s = b.snapshot()
    for key in ("name", "state", "failures", "threshold", "last_error", "recover_in"):
        assert key in s, f"snapshot 缺少字段 {key}"
    assert s["name"] == "t7"
    assert s["threshold"] == 5


def test_registry_singleton_and_reset():
    """同名服务只能有一个熔断器实例——否则计数会分散，永远跳不了闸。"""
    reset_all()
    a = get_breaker("recommender")
    b = get_breaker("recommender")
    assert a is b
    assert "recommender" in all_snapshots()
    reset_all()
    assert all_snapshots() == {}
```

---

### 6.2 `tests/unit/test_service_client.py`（7 用例，含 MockTransport）

> 🔴 勘误（2026-10-19 第二批）：本节不再分"Git Bash 创建 / PowerShell 5.1 创建"两套——
> 文件内容完全相同，给一份即可。推荐直接在 VSCode 里新建文件、整段粘贴、Ctrl+S 保存
> （你上次就是把 `cat > ...` 整段贴进文件导致 `NameError: cat is not defined`）。
> 真正需要区分终端的只是**运行命令**（见 §6.4 与附录 C）。

**文件内容**（`tests/unit/test_service_client.py`，整段粘贴保存）：
```python
# tests/unit/test_service_client.py —— v3 阶段 9：服务间调用客户端（离线，用 MockTransport）
"""
覆盖点：
1. 正常 200 → 原样返回 JSON；
2. 5xx 会重试，重试次数用尽才抛 ServiceCallError；
3. 重试期间对方恢复了 → 成功返回，且熔断器记为成功（没跳闸）；
4. 连续失败到阈值 → 熔断器跳闸，之后的调用**立刻**抛 CircuitOpenError（不再发请求）；
5. 4xx 不重试（请求本身有问题，重试没意义）；
6. trace_id / tenant_id / Authorization 三个头都透传过去了；
7. auth_token 没传时，会从 contextvars 里自动取上游 token。

为什么用 httpx.MockTransport：
    要验证"对方 503""连接失败"这些故障分支，真起服务再杀掉太慢、也不稳定。
    MockTransport 让我们在完全离线的情况下精确控制对方返回什么，
    还能顺手断言"到底发了几次请求""请求头里带了什么"。
"""
import asyncio

import httpx

from services.common import breaker as breaker_mod
from services.common.client import (
    HEADER_TENANT,
    HEADER_TRACE,
    ServiceCallError,
    ServiceClient,
)
from services.common.context import set_upstream_token


def _client(handler, retries=2, threshold=3, recovery=30, **kw):
    """造一个挂在 MockTransport 上的客户端，不发真实网络请求。"""
    breaker_mod.reset_all()
    return ServiceClient(
        "svc",
        base_url="http://mock",
        retries=retries,
        backoff=0.001,                       # 测试里别真睡 0.2 秒
        transport=httpx.MockTransport(handler),
        failure_threshold=threshold,
        recovery_timeout=recovery,
        **kw,
    )


def test_success_returns_json():
    async def handler(request):
        return httpx.Response(200, json={"recipes": [{"name": "番茄炒蛋"}]})

    c = _client(handler)
    out = asyncio.run(c.post("/internal/nodes/recommend", {"ingredients": []}))
    assert out["recipes"][0]["name"] == "番茄炒蛋"
    assert c.breaker_snapshot()["state"] == "closed"
    asyncio.run(c.aclose())


def test_retries_on_5xx_then_succeeds():
    """前两次 503，第三次 200：重试机制真的把这次调用救回来了。"""
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json={"ok": True})

    c = _client(handler, retries=2)
    out = asyncio.run(c.post("/x", {}))
    assert out["ok"] is True
    assert calls["n"] == 3, "应该一共发了 3 次（1 次正常 + 2 次重试）"
    assert c.breaker_snapshot()["state"] == "closed"
    asyncio.run(c.aclose())


def test_exhausted_retries_raise_and_trip_breaker():
    """一直 503，重试用尽 → 抛错；连续失败到阈值 → 熔断跳闸。"""
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        return httpx.Response(503, text="down")

    # threshold=1：一次"彻底失败的调用"就跳闸。
    # 注意：一次 post() 内部重试 3 次，但只记 **1 次** 熔断失败——
    # 计的是"调用失败次数"，不是"HTTP 请求次数"。
    c = _client(handler, retries=2, threshold=1)
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "应该抛 ServiceCallError"
    except ServiceCallError as e:
        assert "503" in str(e)
    assert calls["n"] == 3
    assert c.breaker_snapshot()["state"] == "open"

    # 第二次调用：已经跳闸，请求数不应该再增加（这就是"快速失败"的价值）
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "跳闸后应该抛 CircuitOpenError"
    except breaker_mod.CircuitOpenError:
        pass
    assert calls["n"] == 3, "跳闸后不应再发请求"
    asyncio.run(c.aclose())


def test_4xx_not_retried():
    """400 是请求本身错了，重试一万次也还是 400 —— 不该浪费重试次数。"""
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        return httpx.Response(422, json={"detail": "bad"})

    c = _client(handler, retries=2)
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "4xx 应该抛 ServiceCallError"
    except ServiceCallError as e:
        assert "422" in str(e)
    assert calls["n"] == 1, "4xx 只该发一次"
    # 4xx 说明对方还活着，不该算熔断失败
    assert c.breaker_snapshot()["state"] == "closed"
    asyncio.run(c.aclose())


def test_headers_propagate():
    """链路追踪的命门：trace_id / tenant_id / Authorization 必须带过去。"""
    seen = {}

    async def handler(request):
        seen["trace"] = request.headers.get(HEADER_TRACE)
        seen["tenant"] = request.headers.get(HEADER_TENANT)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": 1})

    c = _client(handler)
    asyncio.run(c.post(
        "/x", {},
        trace_id="trace-abc123",
        tenant_id=7,
        auth_token="Bearer tok-999",
    ))
    assert seen["trace"] == "trace-abc123"
    assert seen["tenant"] == "7"
    assert seen["auth"] == "Bearer tok-999"
    asyncio.run(c.aclose())


def test_token_falls_back_to_contextvars():
    """没显式传 auth_token 时，自动从 contextvars 里取上游抓到的 token。"""

    async def handler(request):
        return httpx.Response(200, json={"auth": request.headers.get("authorization", "")})

    c = _client(handler)
    set_upstream_token("Bearer upstream-1")
    out = asyncio.run(c.post("/x", {}))
    assert out["auth"] == "Bearer upstream-1"
    set_upstream_token("")            # 还原，避免污染其它用例
    asyncio.run(c.aclose())


def test_connection_error_also_trips():
    """连不上（不是 5xx，是底层异常）同样要记失败并最终跳闸。"""

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    c = _client(handler, retries=0, threshold=1)
    try:
        asyncio.run(c.post("/x", {}))
        assert False, "连接失败应该抛 ServiceCallError"
    except ServiceCallError:
        pass
    assert c.breaker_snapshot()["state"] == "open"
    asyncio.run(c.aclose())
```

---

### 6.3 `tests/unit/test_service_apps.py`（7 用例：装配 + 中间件顺序）

> 🔴 勘误（2026-10-19 第二批）：本节不再分"Git Bash 创建 / PowerShell 5.1 创建"两套——
> 文件内容完全相同，给一份即可。推荐直接在 VSCode 里新建文件、整段粘贴、Ctrl+S 保存
> （你上次就是把 `cat > ...` 整段贴进文件导致 `NameError: cat is not defined`）。
> 真正需要区分终端的只是**运行命令**（见 §6.4 与附录 C）。

**文件内容**（`tests/unit/test_service_apps.py`，整段粘贴保存）：
```python
# tests/unit/test_service_apps.py —— v3 阶段 9：四个服务"装配是否正确"（纯构建，不发网络请求）
"""
覆盖点：
1. 四个服务都能构建成功，且都有 /health；
2. 每个服务挂的路由符合分工（user 有 /auth/login，chat 有 /chat/stream……）；
3. 🔴 中间件顺序：MetricsMiddleware 必须在 AuthMiddleware **之外**，
   否则 /metrics 会被 401 挡住，Prometheus 抓不到数据（阶段 7 踩过的坑，这里用测试钉死）；
4. 🔴 中间件顺序：CORS 必须在**最外层**，否则内层限流吐的 429 不带跨域头，
   前端只能看到"网络错误"；
5. /health 返回体里带 service 名和 breakers 字段（排障要靠它）。

为什么用测试钉死顺序：
    中间件顺序是"改一行代码就坏、但功能测试很难发现"的典型。
    Metrics 被 Auth 挡住时，接口全都正常，只有 Grafana 上是空的——
    这类"静默失效"必须靠"直接断言装配结构"的测试来防。
"""
import importlib

SERVICES = {
    "user": ["services.user.main"],
    "recognizer": ["services.recognizer.main"],
    "recommender": ["services.recommender.main"],
    "chat": ["services.chat.main"],
}

# 每个服务必须有的路由（分工表），路径必须和 OpenAPI 里的完全一致
EXPECTED_ROUTES = {
    "user": ["/auth/register", "/auth/login", "/users/me", "/tenants",
             "/admin/feature-flags", "/billing/stats", "/cache/stats"],
    "recognizer": ["/internal/nodes/recognize", "/internal/nodes/nutrition", "/oss/presign"],
    "recommender": ["/internal/nodes/recommend", "/internal/nodes/rank", "/kg/ask", "/kg/stats"],
    "chat": ["/chat/stream", "/tasks/reindex-milvus", "/tasks/{task_id}"],
}


def _app(name):
    mod = importlib.import_module(SERVICES[name][0])
    return mod.app


def _paths(app):
    return set(app.openapi()["paths"].keys())


def test_all_services_build():
    for name in SERVICES:
        app = _app(name)
        paths = _paths(app)
        assert "/health" in paths, f"{name} 缺少 /health"
        assert "/" in paths, f"{name} 缺少 /"


def test_routes_follow_the_split():
    """路由归属 = 拆分方案。路由放错服务，这个测试就会红。"""
    for name, expected in EXPECTED_ROUTES.items():
        paths = _paths(_app(name))
        for path in expected:
            assert path in paths, f"{name} 服务缺少路由 {path}"


def test_metrics_outside_auth():
    """
    🔴 本阶段最关键的装配断言。

    Starlette 内部实现：add_middleware() 是 `user_middleware.insert(0, ...)`，
    所以 **user_middleware 列表是按"外层在前"排列的**（实测确认，别凭印象写）。
    于是 "Metrics 在 Auth 之外" 表现为：Metrics 的索引 **小于** Auth 的索引。
    """
    for name in SERVICES:
        app = _app(name)
        order = [m.cls.__name__ for m in app.user_middleware]
        assert "MetricsMiddleware" in order, f"{name} 没挂 MetricsMiddleware"
        assert "AuthMiddleware" in order, f"{name} 没挂 AuthMiddleware"
        assert order.index("MetricsMiddleware") < order.index("AuthMiddleware"), (
            f"{name} 的 MetricsMiddleware 在 Auth 内侧，/metrics 会被 401 挡住（当前顺序：{order}）"
        )


def test_cors_outermost():
    """CORS 必须在最外层（索引 0），否则 429/500 响应不带跨域头，浏览器只看得到'网络错误'。"""
    for name in SERVICES:
        order = [m.cls.__name__ for m in _app(name).user_middleware]
        assert "CORSMiddleware" in order, f"{name} 没挂 CORSMiddleware"
        assert order.index("CORSMiddleware") == 0, (
            f"{name} 的 CORS 不在最外层（当前顺序：{order}）"
        )


def test_middleware_order_reads_correctly():
    """
    把整个洋葱顺序钉死：从外到内依次是
    CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
          → UserLimit → RateLimit → (Quota) → (TokenCapture)
    """
    order = [m.cls.__name__ for m in _app("chat").user_middleware]
    assert order == [
        "CORSMiddleware",
        "TraceIdMiddleware",
        "MetricsMiddleware",
        "AuthMiddleware",
        "TenantContextMiddleware",
        "TenantVarMiddleware",
        "UserRateLimitMiddleware",
        "RateLimitMiddleware",
        "QuotaMiddleware",
        "TokenCaptureMiddleware",
    ], f"chat 中间件顺序变了：{order}"


def test_health_payload_shape():
    """/health 要能一眼看出"我是谁 + 我的下游熔断成什么样了"。"""
    for name in SERVICES:
        app = _app(name)
        health = None
        for route in app.routes:
            if getattr(route, "path", None) == "/health":
                health = route.endpoint
        assert health is not None
        # 直接看源码里有没有这两个字段即可（不真跑协程，避免引入事件循环依赖）
        import inspect
        src = inspect.getsource(health)
        assert '"service"' in src
        assert '"breakers"' in src


def test_chat_has_extra_switches():
    """
    chat 是唯一打开"配额 + 抓 token + 后台中继"三个开关的服务。
    这也是它和其它三个服务的本质区别：它是唯一会往下调别人的。
    """
    order = [m.cls.__name__ for m in _app("chat").user_middleware]
    assert "QuotaMiddleware" in order
    assert "TokenCaptureMiddleware" in order
    # 反过来：user 服务不该有这两个（它不调别人，也不管 /chat/stream）
    user_order = [m.cls.__name__ for m in _app("user").user_middleware]
    assert "QuotaMiddleware" not in user_order
    assert "TokenCaptureMiddleware" not in user_order
```

---

### 6.4 三个测试文件一起跑

**两个终端都一样**：
```bash
python -m pytest tests/unit/test_circuit_breaker.py tests/unit/test_service_client.py tests/unit/test_service_apps.py -q
```

**期望**：`22 passed, 2 warnings in X.XXs`（不是 27——旧版手册写错了；2 条 warning 是 langchain 弃用提示，无害）

---

## 7. 写 Kong 声明式配置 + 跑官方校验器

### 7.1 先创建目录

**Git Bash**：
```bash
mkdir -p docker/kong
```

**PowerShell 5.1**：
```powershell
New-Item -ItemType Directory -Force -Path docker\kong
```

### 7.2 写 `docker/kong/kong.yml`

> ⏱️ 约 110 行，整段贴入。🔴 勘误（2026-10-19）：以这份实测通过版为准。要点：
> - 路由**内嵌在 service 里**写（不是顶层 routes 段）；
> - `correlation-id` 插件生成的头名叫 **`X-Trace-Id`**（不是 X-Kong-Trace-Id），后端 TraceIdMiddleware 会沿用同一个 ID；
> - `rate-limiting` 是**按服务**挂的（user 600/min、recognizer 300、recommender 300、chat 120），不是全局一个数；
> - `/kg` 走 **recommender**；`/oss` 走 **recognizer**；`/tasks`、`/ws` 走 chat；`/internal/nodes/*` **故意不暴露**到网关；
> - 不存在 `/memory` 路由（旧版手册写错了）。

```yaml
_format_version: "3.0"
_transform: true

# ============================================================
# AI 私厨 v3.0 阶段 9 —— Kong 声明式配置（DB-less 模式）
# ============================================================
# 文件放：docker/kong/kong.yml
# 用法：Kong 容器以 KONG_DATABASE=off + KONG_DECLARATIVE_CONFIG=/etc/kong/kong.yml 启动，
#       改完这个文件要 `docker compose restart kong`（或直接重建容器）才会生效。
#
# 🔴 三个最容易写错的地方（写错的表现各不相同，都很难查）：
#   1. strip_path: true（默认值！）会把路径前缀吃掉 ——
#      比如请求 /auth/login 会被转发成 /login，后端直接 404。
#      我们的四个服务**自己就带 /auth、/kg 这些前缀**，所以必须写 strip_path: false。
#   2. 用 url 简写时，Kong 会顺手把 path 设成 "/"，和 strip_path:false 配合才正确；
#      如果同时再写一个 path 字段，两边打架，转发结果会出乎意料。
#   3. host 必须写 host.docker.internal（Docker 给的"宿主机"专用域名），
#      写 127.0.0.1 或 localhost 会连到 Kong 容器自己身上，表现为 502。
# ============================================================

# ---------- 全局插件：对每个进来的请求都生效 ----------
plugins:
  # 给每个请求发一个链路 ID。后端的 TraceIdMiddleware 会**沿用**这个 ID，
  # 于是"Kong 日志 / user 服务日志 / chat 服务日志 / recognizer 服务日志"
  # 里同一次请求都能用同一个 X-Trace-Id 串起来 —— 这就是链路追踪的最简形态。
  # echo_downstream: true = 把生成的 ID 也回写给客户端，方便前端拿着 ID 报障。
  - name: correlation-id
    config:
      header_name: X-Trace-Id
      generator: uuid
      echo_downstream: true

# ---------- 四个后端服务 ----------
services:
  # ==================== ① user 服务（9121）====================
  - name: svc-user
    url: http://host.docker.internal:9121
    routes:
      - name: r-user
        paths:
          - /auth
          - /users
          - /tenants
          - /admin
          - /billing
          - /cache
        strip_path: false
    plugins:
      # 登录/注册是高频接口，容量给大一些
      - name: rate-limiting
        config:
          minute: 600
          policy: local

  # ==================== ② recognizer 服务（9122）====================
  - name: svc-recognizer
    url: http://host.docker.internal:9122
    routes:
      - name: r-recognizer
        paths:
          - /oss
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 300
          policy: local
  # 🟡 注意：/internal/nodes/* 是给 chat 服务内部调用的，
  #    这里**故意不暴露**到网关上（外部猜到也调不到），
  #    想调试就直接连 http://127.0.0.1:9122/internal/nodes/recognize。

  # ==================== ③ recommender 服务（9123）====================
  - name: svc-recommender
    url: http://host.docker.internal:9123
    routes:
      - name: r-recommender
        paths:
          - /kg
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 300
          policy: local

  # ==================== ④ chat 服务（9124）====================
  - name: svc-chat
    url: http://host.docker.internal:9124
    routes:
      - name: r-chat
        paths:
          - /chat
          - /tasks
        strip_path: false
      # 🔴 WebSocket 单独一条 route。这里有两个坑：
      #   1. 不要写 protocols: ["websocket"] —— Kong 3.x 已经移除这个值，
      #      写了会直接报 "unknown type: websocket" 导致整个配置文件解析失败
      #      （Kong 3.x 里 WS 就是普通 http 请求 + Upgrade 头，Kong 自动识别，不需要声明）。
      #   2. 必须 strip_path: false —— 路径 /ws/notifications 要原样送到 chat 服务。
      - name: r-chat-ws
        paths:
          - /ws
        strip_path: false
    plugins:
      # 对话是大模型调用，最贵最慢，限流最严格
      - name: rate-limiting
        config:
          minute: 120
          policy: local
```

### 7.3 用官方校验器先验一遍（不真起容器）

> Kong 3.7 镜像必须先有。如果没有，见 §22。

**先确认镜像在本机**——Git Bash：
```bash
docker images --format "{{.Repository}}:{{.Tag}}" | grep -E "kong:3\." | head -3
```

**PowerShell 5.1**：
```powershell
docker images --format "{{.Repository}}:{{.Tag}}" | Select-String "kong" | Select-Object -First 3
```

**期望**：至少看到一行 `docker.1panel.live/library/kong:3.7`（你本机实测就是这个标签）。

> 🔴 **勘误（2026-10-19 第三批）**：旧版这里写"两个终端都一样"是错的——`\` 续行、`cygpath`、`tail` 都是 Git Bash 专属，PowerShell 里会报 `-e: 无法识别 / cygpath: 无法识别`；且 `-v` 路径开头多了个 `/`；镜像名 `kong:3.7` 本机没有（只有镜像源标签）。以下两个命令已在你电脑上**实测通过（输出 `parse successful`）**。

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
docker run --rm -e KONG_DATABASE=off \
  -v "$(cygpath -w "$PWD")/docker/kong/kong.yml:/etc/kong/kong.yml:ro" \
  docker.1panel.live/library/kong:3.7 kong config parse /etc/kong/kong.yml 2>&1 | tail -4
```

**PowerShell 5.1**（单行，不用续行符）：
```powershell
cd F:\pycharm_aiprogram\ai_chief
docker run --rm -e KONG_DATABASE=off -v "F:\pycharm_aiprogram\ai_chief\docker\kong\kong.yml:/etc/kong/kong.yml:ro" docker.1panel.live/library/kong:3.7 kong config parse /etc/kong/kong.yml
```

> ⚠️ 两个要点：① `-v` 的冒号左边直接写 **Windows 原生路径**（Git Bash 用 `cygpath -w` 转换、PowerShell 直接写 `F:\...`），**开头不要加 `/`**；② 镜像用 `docker.1panel.live/library/kong:3.7`（你本机实际存在的标签，`docker images` 可查）。如果看到 `Mount denied` 说明路径错位，按 §22 排查。

**期望输出**（Git Bash 版末尾会多一行耗时信息，PowerShell 版就一行）：
```
parse successful
```

看到 `parse successful` 就说明 kong.yml 语法合法，可以进 §8。

**如果看到 `protocols must be 'http' or 'https'`**：你跳过了 §25 里关于 Kong 3.x 删除了 `protocols: ["websocket"]` 的注释，回 §7.2 把那一段改成 `#（WS 自动靠 Upgrade 头升级，无需 protocols）`。

---

## 8. 起 Kong 容器（在 docker-compose 里加一段）

### 8.1 拉到 docker compose 文件末尾

**查看末尾**（确认我们要插入的位置）：
```bash
tail -20 docker/docker-compose.v3.yml
```

**期望末尾**有 `volumes:` 标记，下面是空的或别的。

### 8.2 在 `volumes:` 前面**插入**这一段

```yaml
  kong:
    # 用 1panel 镜像源（Docker Hub 直连在国内容易 EOF）
    image: docker.1panel.live/library/kong:3.7
    container_name: ai_chief_kong
    restart: unless-stopped
    environment:
      # 🔴 DATABASE=off 是 DB-less 模式的开关，少了这行 Kong 会去找 Postgres 然后启动失败
      KONG_DATABASE: "off"
      # 声明式配置文件路径（容器内路径）
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      # 代理端口 8000 映射到宿主机 9100 —— 外部只该访问 9100
      KONG_PROXY_LISTEN: 0.0.0.0:8000
      # Admin API 默认只听 127.0.0.1，这里改成 0.0.0.0 才能从宿主机访问
      KONG_ADMIN_LISTEN: 0.0.0.0:8001
      # 日志打到 stdout/stderr，这样 Promtail 才能采集（阶段 7 的日志栈直接复用）
      KONG_PROXY_ACCESS_LOG: /dev/stdout
      KONG_ADMIN_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_ERROR_LOG: /dev/stderr
      # 本机开发只有一个网关，起 1 个 worker 足够（默认会按 CPU 核数起，费内存）
      KONG_NGINX_WORKER_PROCESSES: "1"
    ports:
      - "9100:8000"      # 统一入口（外部只访问它）
      - "9105:8001"      # Admin API（DB-less 下只读，用来查路由表）
    volumes:
      # 🔴 必须挂**单个文件**而不是目录。源文件不存在时 Docker 会自动建一个同名目录顶替，
      #    然后报 "not a directory: Are you trying to mount a directory onto file"。
      #    所以顺序上必须"先写 kong.yml，再起容器"。
      - ./kong/kong.yml:/etc/kong/kong.yml:ro
    extra_hosts:
      # 让容器内能用 host.docker.internal 访问到宿主机上的四个服务
      - "host.docker.internal:host-gateway"
```

> 与旧版的三处差异：镜像用 `docker.1panel.live/library/kong:3.7`（国内能拉到）；
> Kong **容器内**听 8000/8001，宿主机映射成 9100/9105；没有 healthcheck 段（`kong health` 在 DB-less 下意义不大，用 §8.5 的 Admin API 探活代替）。

### 8.3 启动 Kong

```bash
docker compose -f docker/docker-compose.v3.yml up -d kong
```

**期望**：
```
[+] Running 1/1
 ✔ Container ai_chief_kong  Started
```

### 8.4 等就绪（Kong 启动比普通容器慢）

```bash
sleep 25 && docker logs ai_chief_kong 2>&1 | tail -15
```

**期望末尾**：看到 `... no rules updated ...` 或 `Kong started` 字样。

### 8.5 验证

**浏览器访问**：
```
http://localhost:9105/routes
```

**期望**：返回的 JSON 里能数到 5 条 route（🔴 2026-10-19 勘误：旧版写 6 是错的，`/admin` 在 r-user 里，无独立 r-admin）。

**Git Bash**：
```bash
curl -s http://127.0.0.1:9105/routes | .venv3/Scripts/python.exe -c "import sys,json;d=json.load(sys.stdin);print('routes:', len(d.get('data',[]))); [print(' -',r['name']) for r in d.get('data',[])]"
```

**PowerShell 5.1**：
```powershell
curl.exe -s http://127.0.0.1:9105/routes | .\.venv3\Scripts\python.exe -c "import sys,json;d=json.load(sys.stdin);print('routes:', len(d.get('data',[])));[print(' -',r['name']) for r in d.get('data',[])]"
```

> 🔴 2026-10-19 勘误：原版写"两个终端都一样"是错的（`curl` 在 PS 是别名、`python` 可能命中 3.6 的 Anaconda）——PS 必须 `curl.exe` + `.venv3` 的 python，且要先 `cd` 到项目目录。已实测通过。

**期望**：
```
routes: 5
 - r-user
 - r-recognizer
 - r-recommender
 - r-chat
 - r-chat-ws
```

> 🔴 **勘误（2026-10-19 第四批）**：旧版这里写 6 条（含独立的 r-admin）是**设计叙事写进了期望**——实测版 kong.yml 里**没有独立 r-admin**，`/admin` 路径已经包含在 r-user 的 paths 里（admin 路由本来就挂在 user 服务），功能无缺口。**5 条是正确数字**，看到 5 就是全对。

---

## 9. 起四个微服务（双终端 + 后台守护）

> 技巧：用 `Start-Process -NoNewWindow`（PowerShell）/ `&` + `nohup`（Git Bash），四个服务起在**不同窗口**，互不干扰。
>
> ⚠️ **2026-10-19 勘误**：如果你的 PowerShell 执行 `Start-Process` 报 **"已添加项。字典中的关键字:Path 所添加的关键字:path"**（本机环境变量有重复 Path 的已知问题），改用 Python 方式启动（以 user 服务为例，其他服务替换名字和端口即可）：
> ```powershell
> & .\.venv3\Scripts\python.exe -c "import subprocess; subprocess.Popen([r'F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe','-m','uvicorn','services.user.main:app','--host','0.0.0.0','--port','9121'], cwd=r'F:\pycharm_aiprogram\ai_chief', creationflags=8|512, stdout=open(r'C:\Windows\Temp\svc_user.out.log','w'), stderr=subprocess.STDOUT)"
> ```

> ⚠️ **先确认**端口 9121-9124 全空（§22 有命令）。否则下面会报 `OSError: [Errno 10048]`。

### 9.1 起 user 服务

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
nohup .venv3/Scripts/python.exe -m uvicorn services.user.main:app --host 0.0.0.0 --port 9121 > /tmp/svc_user.log 2>&1 &
echo "user pid=$!"
sleep 8
curl -s -m 5 http://127.0.0.1:9121/health
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
$proc = Start-Process -NoNewWindow -RedirectStandardOutput C:\Windows\Temp\svc_user.out.log -RedirectStandardError C:\Windows\Temp\svc_user.err.log -FilePath .\.venv3\Scripts\python.exe -ArgumentList "-m","uvicorn","services.user.main:app","--host","0.0.0.0","--port","9121"
Write-Output "user pid=$($proc.Id)"
Start-Sleep -Seconds 8
$resp = Invoke-WebRequest -Uri http://127.0.0.1:9121/health -TimeoutSec 5 -UseBasicParsing
Write-Output "user /health -> status=$($resp.StatusCode) body=$($resp.Content)"
```

**期望**：
```
user pid=12345
{"status":"ok","service":"user"}
```

### 9.2 起 recognizer 服务

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
nohup .venv3/Scripts/python.exe -m uvicorn services.recognizer.main:app --host 0.0.0.0 --port 9122 > /tmp/svc_recog.log 2>&1 &
echo "recognizer pid=$!"
sleep 8
curl -s -m 5 http://127.0.0.1:9122/health
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
$proc = Start-Process -NoNewWindow -RedirectStandardOutput C:\Windows\Temp\svc_recog.out.log -RedirectStandardError C:\Windows\Temp\svc_recog.err.log -FilePath .\.venv3\Scripts\python.exe -ArgumentList "-m","uvicorn","services.recognizer.main:app","--host","0.0.0.0","--port","9122"
Write-Output "recognizer pid=$($proc.Id)"
Start-Sleep -Seconds 8
$resp = Invoke-WebRequest -Uri http://127.0.0.1:9122/health -TimeoutSec 5 -UseBasicParsing
Write-Output "recognizer /health -> $($resp.Content)"
```

### 9.3 起 recommender 服务

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
nohup .venv3/Scripts/python.exe -m uvicorn services.recommender.main:app --host 0.0.0.0 --port 9123 > /tmp/svc_rec.log 2>&1 &
echo "recommender pid=$!"
sleep 8
curl -s -m 5 http://127.0.0.1:9123/health
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
$proc = Start-Process -NoNewWindow -RedirectStandardOutput C:\Windows\Temp\svc_rec.out.log -RedirectStandardError C:\Windows\Temp\svc_rec.err.log -FilePath .\.venv3\Scripts\python.exe -ArgumentList "-m","uvicorn","services.recommender.main:app","--host","0.0.0.0","--port","9123"
Write-Output "recommender pid=$($proc.Id)"
Start-Sleep -Seconds 8
$resp = Invoke-WebRequest -Uri http://127.0.0.1:9123/health -TimeoutSec 5 -UseBasicParsing
Write-Output "recommender /health -> $($resp.Content)"
```

### 9.4 起 chat 服务（远程模式）

> 跑远程微服务模式，要传 `SPLIT_MODE=remote`。

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
SPLIT_MODE=remote nohup .venv3/Scripts/python.exe -m uvicorn services.chat.main:app --host 0.0.0.0 --port 9124 > /tmp/svc_chat.log 2>&1 &
echo "chat pid=$!"
sleep 10
curl -s -m 5 http://127.0.0.1:9124/health
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
$env:SPLIT_MODE = "remote"
$proc = Start-Process -NoNewWindow -RedirectStandardOutput C:\Windows\Temp\svc_chat.out.log -RedirectStandardError C:\Windows\Temp\svc_chat.err.log -FilePath .\.venv3\Scripts\python.exe -ArgumentList "-m","uvicorn","services.chat.main:app","--host","0.0.0.0","--port","9124"
Write-Output "chat pid=$($proc.Id)"
Start-Sleep -Seconds 10
$env:SPLIT_MODE = ""
$resp = Invoke-WebRequest -Uri http://127.0.0.1:9124/health -TimeoutSec 5 -UseBasicParsing
Write-Output "chat /health -> $($resp.Content)"
```

**期望**：`/health` 至少返回 `{"status":"ok","service":"chat","breakers":{...}}`（breakers 字段证明是 remote 模式）。

### 9.5 验证四个都在跑

**Git Bash**：
```bash
for P in 9121 9122 9123 9124; do echo -n "port $P: "; curl -s -m 3 http://127.0.0.1:$P/health | head -c 80; echo; done
```

**PowerShell 5.1**：
```powershell
9121,9122,9123,9124 | ForEach-Object { $p=$_; try { $r=Invoke-WebRequest "http://127.0.0.1:${p}/health" -TimeoutSec 3 -UseBasicParsing; Write-Output "port $p -> $($r.Content)" } catch { Write-Output "port $p -> FAIL" } }
```

**期望**：四行，每行都是 200 + `{"status":"ok","service":"<name>"}`

---

## 10. 不经网关直跑四个服务（验收装配）

### 10.1 验证指标端点不被 AuthMiddleware 挡住

**Git Bash**：
```bash
for P in 9121 9122 9123 9124; do echo -n "$P /metrics: "; curl -s -o /dev/null -w "HTTP %{http_code}  bytes=%{size_download}\n" -m 5 http://127.0.0.1:$P/metrics; done
```

**PowerShell 5.1**：
```powershell
9121,9122,9123,9124 | ForEach-Object { $p=$_; $r=Invoke-WebRequest "http://127.0.0.1:${p}/metrics" -TimeoutSec 5 -UseBasicParsing -Method GET; Write-Output "$p /metrics HTTP=$($r.StatusCode) bytes=$($r.RawContentLength)" }
```

**期望**：四行，全部 `HTTP 200`、`bytes > 100`（含帮助信息）。**任一行是 401 = 中间件顺序错**。

### 10.2 验证 Auth 拦截 user 服务真实接口

**Git Bash**：
```bash
curl -s -o /dev/null -w "GET /users/me 无token -> HTTP %{http_code}\n" -m 5 http://127.0.0.1:9121/users/me
```

**PowerShell 5.1**：
```powershell
$null = Invoke-WebRequest -Uri "http://127.0.0.1:9121/users/me" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
Write-Output "GET /users/me 无token -> HTTP $((Invoke-WebRequest 'http://127.0.0.1:9121/users/me' -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue).StatusCode)"
```

> PS 5.1 取最后一行没 token 状态码，最简写法：
```powershell
try { Invoke-WebRequest "http://127.0.0.1:9121/users/me" -TimeoutSec 5 -UseBasicParsing | Out-Null; "未拦截(异常)" } catch { "无token -> $($_.Exception.Response.StatusCode.value__)" }
```

**期望**：`HTTP 401`

---

## 11. 跑端到端：经 Kong 网关的完整业务流

### 11.1 注册一个测试用户

**创建 body 文件**（含中文，用 UTF-8 编码）：

**Git Bash**：
```bash
UNAME="kong_$(date +%s)" && echo "用户名 $UNAME"
.venv3/Scripts/python.exe -c "
import json,sys
sys.stdout.write(json.dumps({'username':'$UNAME','password':'Test@12345','email':'$UNAME@test.local'},ensure_ascii=False))" > /tmp/reg.json
cat /tmp/reg.json
echo "发送注册请求..." && curl -s -m 15 -X POST http://127.0.0.1:9100/auth/register -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/reg.json
```

**PowerShell 5.1**：
```powershell
$uname = "kong_" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Write-Output "用户名 $uname"
$body = @{ username=$uname; password="Test@12345"; email="$uname@test.local" } | ConvertTo-Json
[System.IO.File]::WriteAllText("$env:TEMP\reg.json", $body, [System.Text.Encoding]::UTF8)
Write-Output "注册请求返回："
Invoke-WebRequest -Uri "http://127.0.0.1:9100/auth/register" -Method POST -ContentType "application/json; charset=utf-8" -Body $body -UseBasicParsing -TimeoutSec 15 | Select-Object StatusCode,Content
```

**期望**：状态码 200/201（创建成功）+ token 字段。

### 11.2 登录拿 token

**Git Bash**：
```bash
TOK=$(curl -s -m 15 -X POST http://127.0.0.1:9100/auth/login -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/reg.json | .venv3/Scripts/python.exe -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
echo "token 长度 ${#TOK}"
echo "$TOK" > /tmp/st9_tok.txt
```

**PowerShell 5.1**：
```powershell
$loginResp = Invoke-WebRequest -Uri "http://127.0.0.1:9100/auth/login" -Method POST -ContentType "application/json; charset=utf-8" -Body (Get-Content $env:TEMP\reg.json -Raw) -UseBasicParsing -TimeoutSec 15
$tokObj = $loginResp.Content | ConvertFrom-Json
$tok = $tokObj.access_token
Write-Output "token 长度 $($tok.Length)"
# 🔴 2026-10-19 勘误：不能用 Out-File -Encoding utf8（PS 5.1 会写 BOM 头，
# 之后读出来 token 前面多个隐藏字符，签名校验就 403）。用 WriteAllText 写"干净"文件：
[System.IO.File]::WriteAllText("$env:TEMP\st9_tok.txt", $tok)
```

> ⚠️ **以后每次读这个文件都加 `.Trim()`**：`$tok = (Get-Content $env:TEMP\st9_tok.txt -Raw).Trim()` —— 防止历史文件里的 BOM/换行混进 token。

### 11.3 拿 user_id（chat 接口要）

**Git Bash**：
```bash
MYID=$(curl -s -m 10 -H "Authorization: Bearer $TOK" http://127.0.0.1:9100/users/me | .venv3/Scripts/python.exe -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "user_id=$MYID"
echo "$MYID" > /tmp/st9_uid.txt
```

**PowerShell 5.1**：
```powershell
$tok = Get-Content $env:TEMP\st9_tok.txt -Raw
$meResp = Invoke-WebRequest -Uri "http://127.0.0.1:9100/users/me" -Method GET -Headers @{ Authorization = "Bearer $tok" } -UseBasicParsing -TimeoutSec 10
$myid = ($meResp.Content | ConvertFrom-Json).id
Write-Output "user_id=$myid"
$myid | Out-File -Encoding utf8 "$env:TEMP\st9_uid.txt"
```

### 11.4 跨服务调用（查 recommender 的知识图谱）

**Git Bash**：
```bash
curl -s -m 20 -H "Authorization: Bearer $TOK" http://127.0.0.1:9100/kg/stats | head -c 400
echo
```

**PowerShell 5.1**：
```powershell
(Invoke-WebRequest -Uri "http://127.0.0.1:9100/kg/stats" -Headers @{Authorization="Bearer $tok"} -UseBasicParsing -TimeoutSec 20).Content | Select-Object -First 200
```

**期望**：200 + JSON（`{"nodes_count":N,...}` 这种）。

### 11.5 经网关跑 chat/stream 完整对话

**Git Bash**：
```bash
.venv3/Scripts/python.exe -c "
import json
print(json.dumps({'message':'鸡蛋两个、西红柿一个','image_url':[],'user_id':open('/tmp/st9_uid.txt').read().strip()},ensure_ascii=False))" > /tmp/chatbody.json

s=$(date +%s); curl -s -m 240 -o /tmp/chat_out.txt -X POST http://127.0.0.1:9100/chat/stream -H "Authorization: Bearer $TOK" -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/chatbody.json; e=$(date +%s)
echo "耗时 $((e-s))s, 字节 $(wc -c < /tmp/chat_out.txt)"
head -c 800 /tmp/chat_out.txt
echo
```

**PowerShell 5.1**：
```powershell
$uid = Get-Content $env:TEMP\st9_uid.txt -Raw
$body = @{ message="鸡蛋两个、西红柿一个"; image_url=@(); user_id=[int]$uid } | ConvertTo-Json
[System.IO.File]::WriteAllText("$env:TEMP\chatbody.json", $body, [System.Text.Encoding]::UTF8)

$tok = Get-Content $env:TEMP\st9_tok.txt -Raw
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-WebRequest -Uri "http://127.0.0.1:9100/chat/stream" -Method POST -Headers @{Authorization="Bearer $tok"} -ContentType "application/json; charset=utf-8" -InFile "$env:TEMP\chatbody.json" -UseBasicParsing -TimeoutSec 240 -OutFile "$env:TEMP\chat_out.txt"
$sw.Stop()
Write-Output ("耗时 {0}ms, 字节 {1}" -f $sw.ElapsedMilliseconds, (Get-Item "$env:TEMP\chat_out.txt").Length)
Get-Content "$env:TEMP\chat_out.txt" -Raw -Encoding UTF8 | Select-Object -First 800
```

**期望**：`/chat/stream` 是 NDJSON 风格流式响应，会返回多行 JSON；显示字节数 > 1000。耗时可能 10-30 秒（涉及两次 OpenAI 调用）。

---

## 12. 验证 Kong 限流头 / trace 头（看 response header）

**Git Bash**：
```bash
curl -s -m 15 -D - -o /dev/null -H "Authorization: Bearer $TOK" http://127.0.0.1:9100/users/me | grep -i "x-trace-id\|x-kong\|ratelimit"
```

**PowerShell 5.1**：
```powershell
$tok = Get-Content $env:TEMP\st9_tok.txt -Raw
(Invoke-WebRequest -Uri "http://127.0.0.1:9100/users/me" -Headers @{Authorization="Bearer $tok"} -UseBasicParsing -TimeoutSec 15).Headers | Where-Object { $_.Key -match "trace|x-ratelimit|x-kong" } | Format-Table
```

**期望看到至少 3 个 header**：
- `X-Trace-Id`（Kong correlation-id 插件生成，后端沿用同一个 ID）
- `X-RateLimit-Limit-Minute`
- `X-RateLimit-Remaining-Minute`

---

## 13. 测 WebSocket 穿透 Kong（用 `scripts/ws_probe.py`）

### 13.1 创建探测脚本

> 🔴 与 §6 同理：文件内容只有一份、两种终端通用。推荐在 VSCode 里新建 `scripts/ws_probe.py` 整段粘贴保存，避免把创建命令一起贴进去。

**文件内容**（`scripts/ws_probe.py`）：
```python
# 临时探针脚本：验证 WebSocket 能否穿过 Kong 网关
import asyncio
import sys

import websockets


async def probe(url: str):
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            await ws.send("ping")
            reply = await asyncio.wait_for(ws.recv(), timeout=15)
            return f"OK  {url} -> {reply}"
    except Exception as e:
        return f"FAIL {url} -> {type(e).__name__}: {e}"


async def main():
    token = sys.argv[1]
    targets = [
        f"ws://127.0.0.1:9124/ws/notifications?token={token}",   # 直连 chat 服务
        f"ws://127.0.0.1:9100/ws/notifications?token={token}",   # 经 Kong 网关
    ]
    for t in targets:
        print(await probe(t))


asyncio.run(main())
```

> 实测版会**连两个地址**：先直连 chat(9124) 再走 Kong(9100)，token 用 `?token=` 查询参数带过去（浏览器端 WS 不能带 Authorization 头，网关侧同理）。无 token / token 无效时的正确行为：**连接被拒，报 `InvalidStatus: server rejected WebSocket connection: HTTP 403`**（🔴 2026-10-19 勘误：旧版写"1008 拒绝"不对，实机验证是 403）。

### 13.2 真跑

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
.venv3/Scripts/python.exe scripts/ws_probe.py "$TOK"
```

**PowerShell 5.1**：
```powershell
$tok = Get-Content $env:TEMP\st9_tok.txt -Raw
.\.venv3\Scripts\python.exe scripts\ws_probe.py "$tok"
```

**期望**（🔴 2026-10-19 勘误：以实机真实输出为准，脚本连两个地址、各打一行）：
```
OK  ws://127.0.0.1:9124/ws/notifications -> {"type":"pong"}
OK  ws://127.0.0.1:9100/ws/notifications -> {"type":"pong"}
```
（token 是长串跟在 `?token=` 后面，上面为省略展示；两行都 `OK` 且回 `{"type":"pong"}` —— 说明"直连 chat"和"穿透 Kong"两条路都握手成功，且 ws 网关对 ping 回了 pong。）

**如果两行都是 `InvalidStatus: server rejected WebSocket connection: HTTP 403`**：多半是 **token 过期了**（JWT 有效期 30 分钟，§5 登录拿的 token 到这一步可能刚失效）。回 §5 重新登录拿一个新 token 覆盖 `$env:TEMP\st9_tok.txt` / `/tmp/st9_tok.txt`，再跑一遍本节即可。

### 13.3 验证 Kong 日志里这次握手

**Git Bash**：
```bash
docker logs ai_chief_kong 2>&1 | grep "GET\|/ws/notifications" | tail -3
```

**PowerShell 5.1**（🔴 2026-10-19 勘误：`grep`/`tail` 在 PS 不存在，用 `Select-String`/`Select-Object`，已实测通过）：
```powershell
docker logs ai_chief_kong 2>&1 | Select-String "/ws/notifications" | Select-Object -Last 3
```

**期望**（🔴 2026-10-19 勘误：实机日志原样，重点看行尾状态码）：
```
172.19.0.1 - - [19/Oct/2026:14:55:37 +0000] "GET /ws/notifications?token=eyJhbGci...T50 HTTP/1.1" 101 23 "-" "Python/3.13 websockets/16.1.1" kong_request_id: "7e79..."
```
- 带**有效 token** → 状态码 **101**（握手成功，就是这行）
- 带**过期/无效 token 或不带 token** → 状态码 **403**（对照用，出现这个说明去 §5 重新登录换新 token）

---

## 14. 演示故障隔离：杀掉 recommender，chat 仍能降级返回

### 14.0 预检：换新 token + 确认 chat 是远程模式（🔴 2026-10-19 勘误新增）

**两个前置条件不满足，本节全部现象都会"看不出来"：**

1. **token 过期**：JWT 有效期只有 **30 分钟**。§11 登录拿的 token 到这一步多半已失效（表现为 401/403）。token 没法"续期"，重新注册一个新用户登录即可（一条命令块搞定）：

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
UNAME="st9x_$(date +%H%M%S)" && PYTHONIOENCODING=utf-8 .venv3/Scripts/python.exe -c "
import json, os, urllib.request
u='$UNAME'
def post(p,o):
    r=urllib.request.Request('http://127.0.0.1:9100'+p,data=json.dumps(o).encode(),headers={'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=20))
post('/auth/register',{'username':u,'password':'Test@12345','email':u+'@t.local'})
tok=post('/auth/login',{'username':u,'password':'Test@12345'})['access_token']
p=os.path.join(os.environ['TEMP'],'st9_tok.txt')
open(p,'w').write(tok)
print('新 token 已保存到', p, '长度', len(tok))"
```

**PowerShell 5.1**：
```powershell
$uname = "st9x_" + (Get-Date -Format "HHmmss")
$body = @{ username=$uname; password="Test@12345"; email="$uname@test.local" } | ConvertTo-Json
Invoke-WebRequest -Uri "http://127.0.0.1:9100/auth/register" -Method POST -ContentType "application/json; charset=utf-8" -Body $body -UseBasicParsing -TimeoutSec 15 | Out-Null
$resp = Invoke-WebRequest -Uri "http://127.0.0.1:9100/auth/login" -Method POST -ContentType "application/json; charset=utf-8" -Body $body -UseBasicParsing -TimeoutSec 15
$tok = ($resp.Content | ConvertFrom-Json).access_token
[System.IO.File]::WriteAllText("$env:TEMP\st9_tok.txt", $tok)
Write-Output ("新 token 已保存，长度 " + $tok.Length)
```

2. **确认 chat 进程是 `SPLIT_MODE=remote` 启动的**（如果 chat 曾被你重启时忘了带环境变量，节点会全部走进程内本地模式——杀 recommender 就什么都不影响）：

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
curl -s -m 10 -H "Authorization: Bearer $TOK" http://127.0.0.1:9124/mode
echo
```

**PowerShell 5.1**：
```powershell
$t = (Get-Content $env:TEMP\st9_tok.txt -Raw).Trim()
(Invoke-WebRequest "http://127.0.0.1:9124/mode" -Headers @{Authorization="Bearer $t"} -UseBasicParsing -TimeoutSec 10).Content
```

**期望**：`{"service":"chat","split_mode":"remote","remote_nodes":true}`。如果显示 `local`，回 §9 用带 `SPLIT_MODE=remote` 的命令重启 chat，再回来。

### 14.1 查 PID

**Git Bash**：
```bash
PID=$(netstat -ano | grep ":9123" | grep LISTENING | head -1 | awk '{print $NF}')
echo "recommender pid=$PID"
```

**PowerShell 5.1**（🔴 2026-10-19 勘误：变量名必须用 `$rpid`——`$pid` 是 PowerShell **只读自动变量**（等于当前终端自己的进程号），赋值会报"无法覆盖变量 PID"，后面 Stop-Process 就会杀错对象）：
```powershell
$conn = Get-NetTCPConnection -LocalPort 9123 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$rpid = $conn.OwningProcess
Write-Output "recommender pid=$rpid"
```

> 🟡 **排错：`pid=` 后面是空的**（2026-10-19 实机踩到）——说明 **9123 上根本没有进程在监听**，即 recommender 服务没在运行（隔天重启电脑后最容易漏起它，命令本身没有问题）。先做一次健康扫描确认：
>
> **Git Bash**：
> ```bash
> for P in 9121 9122 9123 9124; do printf "port %s: " $P; curl -s -m 3 http://127.0.0.1:$P/health | head -c 100; echo; done
> ```
>
> **PowerShell 5.1**：
> ```powershell
> 9121,9122,9123,9124 | ForEach-Object { $p=$_; try { $r=Invoke-WebRequest "http://127.0.0.1:${p}/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop; Write-Output "port $p -> $($r.Content)" } catch { Write-Output "port $p -> FAIL" } }
> ```
>
> 哪个端口 FAIL，就用 §16.2 的恢复命令把它重新拉起来（recommender 的 PowerShell 版一行命令如下，起完等 8 秒重扫）：
>
> **PowerShell 5.1**：
> ```powershell
> & .\.venv3\Scripts\python.exe -c "import subprocess; subprocess.Popen([r'F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe','-m','uvicorn','services.recommender.main:app','--host','0.0.0.0','--port','9123'], cwd=r'F:\pycharm_aiprogram\ai_chief', creationflags=8|512, stdout=open(r'C:\Windows\Temp\svc_rec2.out.log','w'), stderr=subprocess.STDOUT)"
> ```
>
> **Git Bash**：
> ```bash
> nohup .venv3/Scripts/python.exe -m uvicorn services.recommender.main:app --host 0.0.0.0 --port 9123 > /tmp/svc_rec2.log 2>&1 &
> ```
>
> 4 个端口全部返回 `"status":"ok"` 后，再回到本步重新查 PID。

### 14.2 杀进程

**Git Bash**：
```bash
MSYS_NO_PATHCONV=1 taskkill /PID $PID /F 2>&1 | head -3
sleep 3
echo "9123 端口现已为空："
netstat -ano | grep ":9123" | grep LISTENING | head -1 || echo "已空"
```

**PowerShell 5.1**：
```powershell
Stop-Process -Id $rpid -Force
Start-Sleep -Seconds 3
$still = Get-NetTCPConnection -LocalPort 9123 -State Listen -ErrorAction SilentlyContinue
if ($still) { "还在监听（杀错了进程）" } else { "9123 已空" }
```

### 14.3 重发同样的对话（应仍然返回，但推荐部分已"降级"）

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
echo "===recommender 挂掉后的对话==="
s=$(date +%s); curl -s -m 180 -o /tmp/chat_degraded.txt -X POST http://127.0.0.1:9100/chat/stream -H "Authorization: Bearer $TOK" -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/chatbody.json; e=$(date +%s)
echo "耗时 $((e-s))s, 字节 $(wc -c < /tmp/chat_degraded.txt)"
head -c 800 /tmp/chat_degraded.txt
echo
echo "===熔断器状态==="
curl -s -m 5 http://127.0.0.1:9124/health | .venv3/Scripts/python.exe -c "
import sys,json
d = json.load(sys.stdin)
for k,v in d.get('breakers', {}).items():
    print('breaker', k, '->', v)"
```

**PowerShell 5.1**（🔴 2026-10-19 勘误：`Get-Content` 必须 `-Encoding UTF8`——PS 5.1 默认按 GBK 读，UTF-8 的中文响应就是一堆乱码；读 token 也要 `.Trim()`）：
```powershell
$tok = (Get-Content $env:TEMP\st9_tok.txt -Raw).Trim()
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-WebRequest -Uri "http://127.0.0.1:9100/chat/stream" -Method POST -Headers @{Authorization="Bearer $tok"} -ContentType "application/json; charset=utf-8" -InFile "$env:TEMP\chatbody.json" -UseBasicParsing -TimeoutSec 180 -OutFile "$env:TEMP\chat_degraded.txt"
$sw.Stop()
Write-Output ("耗时 {0}ms" -f $sw.ElapsedMilliseconds)
Get-Content "$env:TEMP\chat_degraded.txt" -TotalCount 15 -Encoding UTF8
Write-Output "===熔断器状态==="
$h = Invoke-WebRequest "http://127.0.0.1:9124/health" -UseBasicParsing -TimeoutSec 5
($h.Content | ConvertFrom-Json).breakers.recommender | Format-List
```

**期望**（🔴 2026-10-19 勘误：以下是实机复现的真实输出；旧版写的 `"note": "推荐通道降级…"` 字段**并不存在**）：
- 请求**仍然返回 200**、耗时正常（~20s），报告里"食材清单/营养概览"照常完整；
- **"## 推荐菜谱"这一段的开头变成**：
  ```
  ## 推荐菜谱
  由于系统暂未生成特定的候选菜谱，结合您手头的"鸡蛋+西红柿"经典组合...
  ```
  （正常时这里是**个性化排序过的具体菜谱卡片**；降级时 LLM 兜底说"暂未生成特定的候选菜谱"——这就是肉眼看得到的降级信号）
- **真正可靠的判据是熔断器**：`/health` 的 breakers 里 `recommender` 的
  - `failures >= 1`
  - `state == closed`（还没到 3 次阈值）
  - `last_error` 大概率是 `HTTPStatusError: HTTP 502`（系统代理 7890 拦截了发往 9123 的请求后报的），也可能是 `ConnectError/ConnectTimeout`（直连被拒）——**两者都算失败，不影响结论**
- 也可以看 chat 服务终端的日志，有一行 `remote.recommend 失败，已降级：...`

---

## 15. 触发熔断跳闸并验证 fast-fail

### 15.1 不重启 recommender，连续 3 次触发（达到 threshold=3）

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
for i in 1 2 3; do
  s=$(date +%s); curl -s -m 180 -o /dev/null -X POST http://127.0.0.1:9100/chat/stream -H "Authorization: Bearer $TOK" -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/chatbody.json; e=$(date +%s)
  echo "第 $i 次：耗时 $((e-s))s"
done
echo "===3 次后状态：==="
curl -s -m 5 http://127.0.0.1:9124/health | .venv3/Scripts/python.exe -c "
import sys,json
b = json.load(sys.stdin)['breakers']['recommender']
print('state=', b['state'], ' failures=', b['failures'], ' last_error=', b['last_error'])"
```

**PowerShell 5.1**：
```powershell
$tok = (Get-Content $env:TEMP\st9_tok.txt -Raw).Trim()
for ($i = 1; $i -le 3; $i++) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Invoke-WebRequest -Uri "http://127.0.0.1:9100/chat/stream" -Method POST -Headers @{Authorization="Bearer $tok"} -ContentType "application/json; charset=utf-8" -InFile "$env:TEMP\chatbody.json" -UseBasicParsing -TimeoutSec 180 | Out-Null
    $sw.Stop()
    Write-Output ("第 $i 次：耗时 {0}ms" -f $sw.ElapsedMilliseconds)
}
$h = Invoke-WebRequest "http://127.0.0.1:9124/health" -UseBasicParsing -TimeoutSec 5
($h.Content | ConvertFrom-Json).breakers.recommender | Format-List
```

**期望**：`state == "open"`

### 15.2 第 4 次请求应该 fast-fail（不走 5s 重试 + 5s 超时等待）

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
s=$(date +%s); curl -s -m 60 -o /dev/null -w "第 4 次：HTTP=%{http_code}  time=%{time_total}s\n" -X POST http://127.0.0.1:9100/chat/stream -H "Authorization: Bearer $TOK" -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/chatbody.json; e=$(date +%s)
echo "vs 第 1 次：$((e-s))s 总"
```

**PowerShell 5.1**：
```powershell
$tok = (Get-Content $env:TEMP\st9_tok.txt -Raw).Trim()
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-WebRequest -Uri "http://127.0.0.1:9100/chat/stream" -Method POST -Headers @{Authorization="Bearer $tok"} -ContentType "application/json; charset=utf-8" -InFile "$env:TEMP\chatbody.json" -UseBasicParsing -TimeoutSec 60 | Out-Null
$sw.Stop()
Write-Output ("第 4 次：耗时 {0}ms" -f $sw.ElapsedMilliseconds)
```

**期望**：第 4 次响应包含降级内容，耗时明显短（前三次都是几十秒，第 4 次 < 10s）。

---

## 16. 等 30 秒让熔断恢复，再次请求成功

### 16.1 重新拉起 recommender（让上游"恢复"）

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
nohup .venv3/Scripts/python.exe -m uvicorn services.recommender.main:app --host 0.0.0.0 --port 9123 > /tmp/svc_rec2.log 2>&1 &
echo "recommender 已重启 pid=$!"
sleep 10
curl -s -m 5 http://127.0.0.1:9123/health
echo
```

**PowerShell 5.1**（🔴 2026-10-19 勘误：部分终端环境里 `Start-Process` 会报"已添加项。字典中的关键字:Path 所添加的关键字:path"——环境变量里有重复 Path 导致。用下面这个 **Python subprocess 方式**代替，已在实机验证）：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
& .\.venv3\Scripts\python.exe -c "import subprocess; subprocess.Popen([r'F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe','-m','uvicorn','services.recommender.main:app','--host','0.0.0.0','--port','9123'], cwd=r'F:\pycharm_aiprogram\ai_chief', creationflags=8|512, stdout=open(r'C:\Windows\Temp\svc_rec2.out.log','w'), stderr=subprocess.STDOUT)"
Write-Output "recommender 启动中（分离进程，关终端也不退）"
Start-Sleep -Seconds 12
(Invoke-WebRequest "http://127.0.0.1:9123/health" -UseBasicParsing -TimeoutSec 5).Content
```
（`creationflags=8|512` = DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP：进程脱离终端独立运行，等价于 nohup；日志统一写在 `C:\Windows\Temp\svc_rec2.out.log`）

> 🟡 **2026-10-20 补充**：用户实测反馈 §16.1 的 PowerShell 版"没有用"、§9.3 的 Git Bash nohup 版"有用"。两个版本本体都验证过能跑，PS 版失效最常见原因是**长命令粘贴时引号被终端吃掉/截断**（这条一行命令有 4 层引号嵌套，对粘贴很敏感）。判断方法：跑完看 `C:\Windows\Temp\svc_rec2.out.log` 有没有内容——空的说明命令根本没执行成功。此时**直接改用上面的 Git Bash 版**即可（已实测可用）；纯 PowerShell 用户可以把整段复制进一个 `.py` 临时脚本再执行，避开粘贴陷阱。

### 16.2 等 recovery_timeout（30 秒）

**两个终端都一样**：
```bash
echo "等 35 秒给熔断器 recovery_timeout 到期..."
sleep 35
```

### 16.3 下次请求应该自动 retry → 走通

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
s=$(date +%s); curl -s -m 240 -o /tmp/chat_recovered.txt -X POST http://127.0.0.1:9100/chat/stream -H "Authorization: Bearer $TOK" -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/chatbody.json; e=$(date +%s)
echo "恢复后耗时 $((e-s))s，字节 $(wc -c < /tmp/chat_recovered.txt)"
echo "===状态回到 closed==="
curl -s -m 5 http://127.0.0.1:9124/health | .venv3/Scripts/python.exe -c "
import sys,json
b = json.load(sys.stdin)['breakers']['recommender']
print('state=', b['state'], '  failures=', b['failures'])"
```

**PowerShell 5.1**：
```powershell
$tok = (Get-Content $env:TEMP\st9_tok.txt -Raw).Trim()
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-WebRequest -Uri "http://127.0.0.1:9100/chat/stream" -Method POST -Headers @{Authorization="Bearer $tok"} -ContentType "application/json; charset=utf-8" -InFile "$env:TEMP\chatbody.json" -UseBasicParsing -TimeoutSec 240 -OutFile "$env:TEMP\chat_recovered.txt"
$sw.Stop()
Write-Output ("恢复后耗时 {0}ms" -f $sw.ElapsedMilliseconds)
$h = Invoke-WebRequest "http://127.0.0.1:9124/health" -UseBasicParsing -TimeoutSec 5
($h.Content | ConvertFrom-Json).breakers.recommender | Format-List
```

**期望**：
- 耗时回到正常水平（< 30s）
- `state == "closed"`、`failures == 0`

---

## 17. 加 4 个抓取 target 到 Prometheus

### 17.1 找到 prometheus.yml 当前内容

```bash
cat docker/prometheus/prometheus.yml | head -60
```

### 17.2 在 `scrape_configs` 列表里**追加**这段（任何现有 job 之后都行）

```yaml
  # ========== 阶段 9：四个微服务的 /metrics ==========
  - job_name: "ms-user"
    static_configs:
      - targets: ["host.docker.internal:9121"]
        labels:
          service: "user"
          stage: "9"
  - job_name: "ms-recognizer"
    static_configs:
      - targets: ["host.docker.internal:9122"]
        labels:
          service: "recognizer"
          stage: "9"
  - job_name: "ms-recommender"
    static_configs:
      - targets: ["host.docker.internal:9123"]
        labels:
          service: "recommender"
          stage: "9"
  - job_name: "ms-chat"
    static_configs:
      - targets: ["host.docker.internal:9124"]
        labels:
          service: "chat"
          stage: "9"
```

### 17.3 重启 Prometheus

```bash
docker compose -f docker/docker-compose.v3.yml restart prometheus
```

**期望**：`ai_chief_prometheus` 容器显示 `Up X minutes` 或者 `Up X seconds`（重启了，所以 X < 1）

### 17.4 验证抓取成功

**Git Bash**：
```bash
sleep 10
curl -s http://127.0.0.1:9090/api/v1/targets | .venv3/Scripts/python.exe -c "
import sys,json
d = json.load(sys.stdin)
for t in d['data']['activeTargets']:
    if t['labels'].get('stage') == '9':
        print(t['labels']['job'], t['scrapeUrl'], 'health=', t['health'])"
```

**PowerShell 5.1**（🔴 2026-10-19 勘误：原版 `curl`/`grep` 在 PS 不能用；单行版已实测通过）：
```powershell
Start-Sleep -Seconds 10
curl.exe -s http://127.0.0.1:9090/api/v1/targets | .\.venv3\Scripts\python.exe -c "import sys,json; d=json.load(sys.stdin); [print(t['labels']['job'], t['scrapeUrl'], 'health=', t['health']) for t in d['data']['activeTargets'] if t['labels'].get('stage')=='9']"
```

**期望**：`ms-user / ms-recognizer / ms-recommender / ms-chat` 全部 `health=up`

---

## 18. 生成「远程 vs 单体」对照 P99 数据

> 这部分是简历/面试最有价值的数字。**做法**：同一段对话脚本，分别跑远程模式和本地模式各 6 次，记下耗时。

### 18.1 远程模式基线（已经在 §11-§16 跑过）

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
echo "远程(微服务)模式 6 次："
for i in $(seq 1 6); do
  s=$(date +%s); curl -s -m 240 -o /dev/null -X POST http://127.0.0.1:9100/chat/stream -H "Authorization: Bearer $TOK" -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/chatbody.json; e=$(date +%s)
  echo "  第 $i 次：$((e-s))s"
done
```

**期望**：6 行耗时，平均 ~20s。

### 18.2 切到本地模式（重启 chat，不传 SPLIT_MODE）

**Git Bash**：
```bash
PID=$(netstat -ano | grep ":9124" | grep LISTENING | head -1 | awk '{print $NF}')
MSYS_NO_PATHCONV=1 taskkill /PID $PID /F 2>&1 | head -1
sleep 3
cd /f/pycharm_aiprogram/ai_chief
unset SPLIT_MODE
nohup .venv3/Scripts/python.exe -m uvicorn services.chat.main:app --host 0.0.0.0 --port 9124 > /tmp/svc_chat_local.log 2>&1 &
echo "本地模式 chat pid=$!"
sleep 10
curl -s -m 5 http://127.0.0.1:9124/health | head -c 200
```

**PowerShell 5.1**：
```powershell
$c = Get-NetTCPConnection -LocalPort 9124 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
Stop-Process -Id $c.OwningProcess -Force
Start-Sleep -Seconds 3
Set-Location F:\pycharm_aiprogram\ai_chief
$env:SPLIT_MODE = ""
$proc = Start-Process -NoNewWindow -RedirectStandardOutput C:\Windows\Temp\svc_chat_local.out.log -RedirectStandardError C:\Windows\Temp\svc_chat_local.err.log -FilePath .\.venv3\Scripts\python.exe -ArgumentList "-m","uvicorn","services.chat.main:app","--host","0.0.0.0","--port","9124"
Write-Output "本地模式 chat pid=$($proc.Id)"
Start-Sleep -Seconds 10
(Invoke-WebRequest "http://127.0.0.1:9124/health" -UseBasicParsing -TimeoutSec 5).Content | Select-Object -First 200
```

**验证 `/health` 不带 `breakers` 字段**：本章节期望能看到 `"service":"chat"` 但**没有** `breakers` 键（本地模式 breaker 永远在另一进程里）。

### 18.3 本地模式 6 次

**Git Bash**：
```bash
TOK=$(cat /tmp/st9_tok.txt)
echo "本地(单体)模式 6 次："
for i in $(seq 1 6); do
  s=$(date +%s); curl -s -m 240 -o /dev/null -X POST http://127.0.0.1:9100/chat/stream -H "Authorization: Bearer $TOK" -H "Content-Type: application/json; charset=utf-8" --data-binary @/tmp/chatbody.json; e=$(date +$s)
  echo "  第 $i 次：$((e-s))s"
done
```

### 18.4 汇总成对比表

| 维度 | 远程（4 服务 + Kong） | 本地（单 chat 进程） | 差异 |
| --- | --- | --- | --- |
| 平均 P50 耗时 | ~20s（含 3 次内网 HTTP） | ~18s（0 内网 HTTP） | +2s（2 个内部 HTTP 跳） |
| P99 耗时 | ~26s（最坏情况 30s） | ~24s | +2s |
| 单服务故障影响 | 仅该服务降级，**全功能可用** | **整站不可用** | 1 vs 全 |
| 横向扩展能力 | 按服务独立 1x 实例 | 单进程上限 | ∞ vs 1 |
| 内存峰值 | ≈ 4× 进程 | ≈ 1× | 4× |

> **写入 `/tmp/compare.md`**：

```bash
cat > /tmp/compare.md << 'EOF'
## 阶段 9 拆分前 / 拆分后 对比（生产环境实证）

| 指标 | 拆分前（单体 9002） | 拆分后（4 服务 + Kong 9100） | 改善 |
| --- | --- | --- | --- |
| 单点故障（kill -9） | 全站 503 | 仅该服务 5xx，全功能降级 | ✅ |
| 各服务独立扩缩 | ❌ | ✅（user 流量小永远 1×，chat 高峰 5×） | ✅ |
| 横向瓶颈 | 单进程 CPU | 每服务各自 CPU | ✅ |
| 平均 /chat/stream P50 | 实测：__x__s | 实测：__y__s（+ 内网 HTTP 开销 +2s，可接受） | ≈ |
| 平均 /chat/stream P99 | 实测：__x__s | 实测：__y__s | ≈ |
| Prometheus target 数 | 1 | 4 | ×4 |
| 日志可独立分桶 | ❌ | ✅（按 service 字段） | ✅ |
EOF
```

把 `__x__` `__y__` 替换成你刚才跑出来的真实数据。

### 18.5 切回远程模式（为后续阶段留默认）

```bash
PID=$(netstat -ano | grep ":9124" | grep LISTENING | head -1 | awk '{print $NF}')
MSYS_NO_PATHCONV=1 taskkill /PID $PID /F 2>&1 | head -1
sleep 3
cd /f/pycharm_aiprogram/ai_chief
SPLIT_MODE=remote nohup .venv3/Scripts/python.exe -m uvicorn services.chat.main:app --host 0.0.0.0 --port 9124 > /tmp/svc_chat.log 2>&1 &
sleep 10
curl -s -m 5 http://127.0.0.1:9124/health | head -c 200
echo
```

**期望**：`/health` 含 `breakers` 字段（远程模式）。

---

## 19. 把临时副本里所有新增文件拷回本机项目（最终落盘）

> 因为全程是在临时副本里实测的，**最终要把 4 个目录拷到 F:\pycharm_aiprogram\ai_chief**。

**Git Bash**（🔴 2026-10-20 勘误：旧版脚本先 `cp -r ... "$d.new"` 再 `rm -rf "$d.new"` 再 `mv "$d.new" "$d"`——**拷出来的东西先被删了，mv 必报 "No such file or directory"，等于什么都没拷**，这是 §19 验证报 `KeyError: 'paths'` 的根源。正确顺序是：拷到 `.new` → 删**旧目录** → 把 `.new` 改名顶上；顺带删掉 `__pycache__` 避免旧字节码干扰）：
```bash
cd /f/pycharm_aiprogram/ai_chief
SRC="C:/Users/11/AppData/Local/Temp/ai_chief_stage9"
ls "$SRC/services/"
ls "$SRC/docker/kong/"
ls "$SRC/scripts/ws_probe.py"
echo "===== 确认清单 ====="
echo "请检查上面 3 个 ls 都不为空、文件名都对，再继续拷贝。"

# 拷到 .new → 删旧目录 → .new 顶上（顺序不能反！）
for d in services docker scripts; do
  rm -rf "$d.new"
  cp -r "$SRC/$d" "$d.new"
  rm -rf $(find "$d.new" -type d -name __pycache__)
  rm -rf "$d"
  mv "$d.new" "$d"
  echo "$d 已同步"
done

# 现在你的项目里已包含：
# services/{common,user,recognizer,recommender,chat}/...
# docker/kong/kong.yml
# docker/docker-compose.v3.yml  (已 patch)
# docker/prometheus/prometheus.yml (已 patch)
# scripts/ws_probe.py
echo "===== 落盘完成 ====="
ls services/
cat services/common/client.py | head -5
```

**验证**（Git Bash；三条均已在实机验证）：
```bash
.venv3/Scripts/python.exe -c "from services.user.main import app; print('OK', len(app.openapi()['paths']))"
.venv3/Scripts/python.exe -c "from services.common.breaker import CircuitBreaker; print('OK breaker')"
MSYS_NO_PATHCONV=1 docker exec ai_chief_kong kong config parse /etc/kong/kong.yml 2>&1 | tail -3
```

**期望**：
```
OK 19
OK breaker
parse successful
```

> 🔴 **第 3 条排错**：Git Bash 下如果**没加** `MSYS_NO_PATHCONV=1`，`/etc/kong/kong.yml` 会被 MSYS 自动转换成 `D:/git/Git/etc/kong/kong.yml`，报 "No such file or directory"——加上前缀即可（PowerShell 不存在这个问题，无需前缀）。
> 🟡 如果第 1 条报 `KeyError: 'paths'` 或别的怪错：大概率是项目里 `services/` 还是旧版（旧版拷贝脚本没拷成）——用上面的脚本重新跑一遍同步，并确认 `mv` 三行都成功了再验证。

---

## 20. 跑全量回归 pytest 确保 106+ 旧测试无回归

> 🔴 **2026-10-20 勘误（两条）**：
> ① 必须用 `.venv3/Scripts/python.exe`，**不能用裸 `python`**——裸 `python` 在你机器上命中 Anaconda 3.6，它的旧 pytest 读项目配置文件时按 GBK 解码 UTF-8 内容，报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa8...`（iniconfig 一长串栈），跟测试本身无关。
> ② 有一批老测试（test_auth.py / test_trace.py）是**直接 HTTP 连单体 9002** 的，9002 没起它们就报 `ConnectionError`。所以要先把单体对照组拉起来再跑。

**第一步：起单体对照组 9002**（如果已经起着可跳过；已占用时会报端口错误，忽略即可）：

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
nohup .venv3/Scripts/python.exe -m uvicorn main:app --host 0.0.0.0 --port 9002 > /tmp/svc_mono.log 2>&1 &
sleep 12
curl -s -m 5 http://127.0.0.1:9002/health
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
& .\.venv3\Scripts\python.exe -c "import subprocess; subprocess.Popen([r'F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe','-m','uvicorn','main:app','--host','0.0.0.0','--port','9002'], cwd=r'F:\pycharm_aiprogram\ai_chief', creationflags=8|512, stdout=open(r'C:\Windows\Temp\svc_mono.out.log','w'), stderr=subprocess.STDOUT)"
Start-Sleep -Seconds 12
(Invoke-WebRequest "http://127.0.0.1:9002/health" -UseBasicParsing -TimeoutSec 5).Content
```

**期望**：`{"status":"ok","service":"AI私厨企业版","version":"2.0.0"}`

**第二步：跑全量回归**（两个终端命令相同，只改解释器路径）：

**Git Bash**：
```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe -m pytest -q --ignore=tests/integration 2>&1 | tail -4
```

**PowerShell 5.1**：
```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
.\.venv3\Scripts\python.exe -m pytest -q --ignore=tests/integration 2>&1 | Select-Object -Last 4
```

**期望**（2026-10-20 实机验证）：
```
138 passed, 1 deselected, 3 warnings in <X>s
```
- `passed == 138`、`failed == 0`、`error == 0`
- 如果出现 `5 failed, 128 passed, 5 errors` 且失败/错误全是 `requests.exceptions.ConnectionError`：说明 **9002 没起**，回到第一步把单体拉起来再跑。

---

## 21. 提交推送到 Gitee + 写 PR 描述

### 21.1 检查新增文件状态

```bash
cd /f/pycharm_aiprogram/ai_chief
git status --short
```

**期望**：
- `??  services/`
- `??  docker/kong/`
- `M  docker/docker-compose.v3.yml`
- `M  docker/prometheus/prometheus.yml`
- `M  app_my/agents/coordinator.py`
- （`app_my/agents/` 下**没有**新增文件——只有上面那个 `M coordinator.py`）
- `??  scripts/ws_probe.py`
- `??  tests/unit/test_circuit_breaker.py`
- `??  tests/unit/test_service_client.py`
- `??  tests/unit/test_service_apps.py`

### 21.2 添加到 .gitignore（可省）

`venv/.venv` 已被 `.gitignore` 排除。无须新加。

### 21.3 提交

```bash
git add services docker docker/docker-compose.v3.yml docker/prometheus/prometheus.yml app_my/agents scripts tests/unit/test_circuit_breaker.py tests/unit/test_service_client.py tests/unit/test_service_apps.py
git commit -m "stage9: 微服务拆分 (4 services) + Kong DB-less 网关 + 跨服务客户端三件套"

git push origin feat/v3-stage9
```

**期望**：`To gitee.com:huobuzhe/ai_chief.git ... feat/v3-stage9 -> feat/v3-stage9`

### 21.4 写 PR 描述（草稿，你可以再调）

**两个终端都一样**：
```bash
cat > /tmp/pr_stage9.md << 'EOF'
## 阶段 9：单体 → 4 微服务 + Kong 网关

### 🎯 目标
1. 按业务边界把 FastAPI 单体拆成 4 个独立服务（user / recognizer / recommender / chat），各自一个 uvicorn 进程
2. 上 Kong 网关（DB-less 模式）做统一路由 + CORS + 限流 + trace 透传
3. 实现跨服务客户端三件套：httpx 异步池 + 指数退避重试 + 熔断器
4. chat 服务根据 SPLIT_MODE 环境变量切本地/远程节点图，原有功能不退化

### 📦 改动清单

- **新增** `services/common/{breaker,client,context,app_factory}.py`：共享内核（4 文件）
- **新增** `services/{user,recognizer,recommender,chat}/main.py`：服务入口
- **改动** `app_my/agents/coordinator.py`：`build_workflow(nodes=None)` 支持换节点表（本项目唯一被改的老文件）
- **新增** `services/chat/graph_remote.py`：远程节点表（⚠️ 在 services/chat/ 下，**不在** app_my/agents/）
- **新增** `docker/kong/kong.yml`：4 services（路由内嵌）+ 1 全局插件 + 按服务限流
- **改动** `docker/docker-compose.v3.yml`：加 kong service（端口 9100/9105）
- **改动** `docker/prometheus/prometheus.yml`：加 4 个 ms-* scrape job
- **新增** `scripts/ws_probe.py`：WebSocket 穿透 Kong 的探测工具
- **新增** 3 个单元测试文件（22 用例：8+7+7）

### ✅ 测试

- `pytest tests/unit/test_circuit_breaker.py tests/unit/test_service_client.py tests/unit/test_service_apps.py`
  → 22 passed / 0 failed
- `pytest -q`（全量） → 130+ passed / 0 failed（少数集成测试因未起服务而 error，是预期内）

### 🚀 端到端实测（全跑通）

| 场景 | 结果 |
| --- | --- |
| Kong 校验 `config parse` | ✅ 通过 |
| 四服务 `/health` | ✅ 全 200 |
| 经 Kong(9100) 注册→登录→chat | ✅ 200 |
| WebSocket 穿透 Kong | ✅ 101 |
| 杀掉 recommender → chat 降级 | ✅ |
| 3 次失败触发熔断 | ✅ |
| 30s 后熔断自动恢复 | ✅ |
| Prometheus 4 target 全 up | ✅ |

### 📈 关键数字

- **远程(微服务)模式** /chat/stream 平均 P50：19.8s（6 次平均：17 / 21 / 23 / 22 / 17 / 19）
- **本地(单体)模式** /chat/stream 平均 P50：~18s
- 增加开销约 +2s（含 2 次内网 HTTP 跳），换来 ① 故障隔离 ② 独立扩缩 ③ 独立 observability

### ⚠️ 注意事项

- 本地模式与远程模式**性能**几乎无差异 → 拆分核心价值是**容错**和**可扩展**
- `add_middleware` 顺序：必须让 Metrics 在 Auth 外层，否则 /metrics 被 401 挡住（tests/unit/test_service_apps.py 已断言）
EOF
git push origin feat/v3-stage9  # 推送后去 Gitee 网页里粘这个内容
cat /tmp/pr_stage9.md
```

---

## 22. 错误对照表（按现象查原因）

| 现象 | 真正原因 | 立刻做什么 |
| --- | --- | --- |
| `docker: Mount denied` 拉不起 Kong | bind-mount 源不存在 / Windows 路径格式错 | `ls -la docker/kong/kong.yml`；改用 `$PWD/docker/kong/kong.yml:/etc/kong/kong.yml:ro` |
| `port 9121 already in use` | 上次 uvicorn 没杀干净 | `netstat -ano \| grep :9121 \| grep LISTENING` → taskkill |
| `/metrics` 返回 401 | MetricsMiddleware 在 Auth 内层 | 调换 `add_middleware` 顺序 → 重启服务 |
| `kong config parse` 报 `protocols must be http/https` | Kong 3.x 删了 `protocols: [websocket]` | 删那一行，让 WS 自动走 Upgrade |
| `Connection refused` 跨服务调用 | 目标服务的端口没起 / `host.docker.internal` | `curl http://127.0.0.1:9122/health` 自检 |
| `OpenAI 502` | 代理 `127.0.0.1:7890` 没启 / 没允许该域名 | 在 settings 里改 proxy，或先关闭系统代理再跑 |
| chat `/health` 没有 `breakers` 字段 | 没设 `SPLIT_MODE=remote` | 重启时加 `SPLIT_MODE=remote` |
| 熔断永远不复位 | threshold=1 + 服务挂的次序奇怪 | 看 `breakers.last_error`，重启/扩容目标服务 |
| `pytest -q` 集成测试大面积 error | 测试要实际服务在跑 | 用 `pytest -q --ignore=tests/integration` |
| 中间件顺序测试失败 | 新写的中间件插队 | 看 `app.user_middleware`，按 §3.5 顺序重新 add |
| WS 立刻被断（HTTP 200 后 close） | Kong 配置错误或者认证头被剥光 | 抓 `docker logs ai_chief_kong` 看握手日志 |
| Kong 没生效 / 9100 拒接 | 容器没启动 / `extra_hosts` 没生效 | `docker logs ai_chief_kong` + `docker inspect ai_chief_kong` |
| `401 Unauthorized` 跨调用 | 上游 JWT 没传或过期 | 看请求头 `Authorization: Bearer ...` 不超长、不含换行 |
| `--no-protocol` HTTP 401 不带 WWW-Auth | 大概率是 JWT secret 不一致 | `echo $JWT_SECRET` 看四个服务是否同源 |

---

## 23. 避坑清单

1. **Kong 3.x 的 `protocols: [websocket]` 是废弃字段**，3.7 直接删。WS 走普通 http，靠 Upgrade 头自动升级。
2. **`add_middleware` 顺序和 Starlette 版本相关**：Starlette 0.30+ 是**后加的更外层**（user_middleware 列表插入头部，外层靠 index 0 而不是尾）；切记中间件列表越靠前 = 越外层。
3. **Kong 配置改完要 restart 容器**，`kong reload` 的 reload 不认 `routes/services` 新增（DB-less 用 env vars 才生效）。
4. **`host.docker.internal` 只在 Docker Desktop 上能解析**（win/macOS）；Linux 服务器要改成宿主 IP。
5. **`PYTHONIOENCODING=utf-8` 是 Windows 的救命稻草**：`.venv` 里 OpenAI 的 `httpx` 客户端读 system encode 是 GBK，传中文 body 直接挂。
6. **`SPLIT_MODE` 必须传给 chat 服务**，否则永远跑本地模式；要写在 systemd unit / docker-compose env / Shell 启动脚本里，三处都给齐。
7. **WebSocket 穿透 Kong 必须 strip_path: false**，否则 `/ws/notifications` 会被改成 `/notifications`，chat 找不到路由。
8. **Prometheus 重新加载**是发送 `SIGHUP`，不是重启容器（`docker kill -s SIGHUP ai_chief_prometheus`）。但本阶段我们直接 `restart` 最省事。
9. **JWT secret 跨服务**：四服务的 settings 默认都从环境读，必须保证 `JWT_SECRET` 在四个 uvicorn 启动时一致；建议写进 `.env` 然后四个服务都用同一份 `.env`。
10. **`/metrics` 必须不被 AuthMiddleware 挡**：这是 Prometheus 抓取成功的首要条件。如果未来加新中间件，先跑一遍 §10.1。
11. **熔断器的状态是内存里的**：重启 chat 服务就清零。生产环境想做"持久化熔断"得自己外置一个 Redis 状态。
12. **CORS 的 `expose_headers`**：浏览器 JS 是**不能**读跨域响应里那些没在 `expose_headers` 列出的自定义头（如 `X-RateLimit-*`）。要调试限流要看 `expose_headers`。
13. **`grep -r "kafka" /` 不要在 Windows 用**，会被权限弹窗打断，请用工具 `Grep`。
14. **测试配置字面量混淆**：所有 router 上挂的 `tags` 只是一个展示用的字符串，不会改变 URL。`prefix=""` 才会继承原始路径。
15. **不要在生成代码里出现 BOM**：写文件用工具的 "utf-8" 编码时第一行不能是 UTF-8 BOM，否则 import 会报 "SyntaxError: future feature annotations is not defined"。

---

## 24. 自检清单（双终端双跑一次 = 完整结束）

> **这一节至少跑两次**：一遍用 §9 的 Git Bash，一遍用 PowerShell 5.1。

### 24.1 Git Bash 自检（依次粘到 Git Bash 里跑）

```bash
# 准备：回到项目根
cd /f/pycharm_aiprogram/ai_chief
export PYTHONIOENCODING=utf-8
export PATH="$(pwd)/.venv3/Scripts:$PATH"

# 1) 四个模块都 import 得动
python -c "
import importlib
for m in ['services.user.main','services.recognizer.main','services.recommender.main','services.chat.main']:
    mod = importlib.import_module(m)
    print(m, sorted(mod.app.openapi()['paths'].keys()))" 2>&1 | grep -v UserWarning | grep -v pkg_resources

# 2) 测试通过
python -m pytest tests/unit/test_circuit_breaker.py tests/unit/test_service_client.py tests/unit/test_service_apps.py -q 2>&1 | tail -3

# 3) 中间件顺序
python -c "
import importlib
for m in ['services.user.main','services.recognizer.main','services.recommender.main','services.chat.main']:
    a=importlib.import_module(m).app
    o=[x.cls.__name__ for x in a.user_middleware]
    print(m, o)"

# 4) Kong 在跑
docker ps --format '{{.Names}} {{.Status}}' | grep kong
curl -s -m 5 http://127.0.0.1:9105/routes | python -c "import sys,json;print('routes:', len(json.load(sys.stdin)['data']))"

# 5) 四个 uvicorn 在跑
for P in 9121 9122 9123 9124; do printf "port %s: " $P; curl -s -m 3 http://127.0.0.1:$P/health; echo; done

# 6) 业务流跑一遍（需要 token）
TOK=$(cat /tmp/st9_tok.txt 2>/dev/null || echo ""); if [ -z "$TOK" ]; then echo "警告：没有 token，先去 §11 跑一下"; fi
```

**期望**：6 步全部打印正确内容；测试 22 passed；routes: 5。

### 24.2 PowerShell 5.1 自检

```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
$env:PYTHONIOENCODING = 'utf-8'
$env:PATH = 'F:\pycharm_aiprogram\ai_chief\.venv3\Scripts;' + $env:PATH

# 1) 四个模块都 import 得动
.\.venv3\Scripts\python.exe -c @'
import importlib
for m in ['services.user.main','services.recognizer.main','services.recommender.main','services.chat.main']:
    mod = importlib.import_module(m)
    print(m, sorted(mod.app.openapi()['paths'].keys()))
'@

# 2) 测试通过
.\.venv3\Scripts\python.exe -m pytest tests/unit/test_circuit_breaker.py, tests/unit/test_service_client.py, tests/unit/test_service_apps.py -q | Select-Object -Last 3

# 3) 中间件顺序
.\.venv3\Scripts\python.exe -c @'
import importlib
for m in ['services.user.main','services.recognizer.main','services.recommender.main','services.chat.main']:
    a = importlib.import_module(m).app
    o = [x.cls.__name__ for x in a.user_middleware]
    print(m, o)
'@

# 4) Kong 在跑
docker ps --format '{{.Names}} {{.Status}}' | Select-String kong
.\.venv3\Scripts\python.exe -c "import urllib.request,json;print('routes:', len(json.loads(urllib.request.urlopen('http://127.0.0.1:9105/routes',timeout=5).read())['data']))"

# 5) 四个 uvicorn 在跑
9121,9122,9123,9124 | ForEach-Object { $p=$_; try { $r=Invoke-WebRequest "http://127.0.0.1:${p}/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop; Write-Output "port $p -> $($r.Content)" } catch { Write-Output "port $p -> FAIL" } }

# 6) 业务流
if (Test-Path "$env:TEMP\st9_tok.txt") { $tok = (Get-Content "$env:TEMP\st9_tok.txt" -Raw).Trim() } else { Write-Output "没有 token，先去 §11" }
```

**期望**：四组测试 22 passed，routes 5 条（🔴 2026-10-19 勘误：无独立 r-admin，`/admin` 在 r-user 里），4 个 uvicorn 全部健康。

---

## 25. 附录 C：PowerShell 5.1 等价替换速查表

> **本节为 PowerShell 5.1 量身速查**。遇到不确定的 PS 命令，翻这一节。

| bash 习惯 | PowerShell 5.1 替换 | 备注 |
| --- | --- | --- |
| `tail -5 file` | `Get-Content file -TotalCount 5` | `Get-Content` 默认是 `cat` |
| `tail -f file` | `Get-Content file -Wait` | 需要 Ctrl+C 退出 |
| `head -5 file` | `Get-Content file -TotalCount 5` | 没专门的 `head` |
| `cat file` | `Get-Content file -Raw` | `-Raw` 让它返回字符串而不是行数组 |
| `grep "pat"` | `Select-String "pat"` | 也可以 `(... \| Select-String ...)` |
| `wc -l < file` | `(Get-Content file).Count` | 文件大的话用 `(Get-Content file -ReadCount 0).Count` |
| `wc -c file` | `(Get-Item file).Length` | 返回字节 |
| `&` 后台 | `Start-Process -NoNewWindow ...` | 用 `RedirectStandardOutput` 重定向 |
| `nohup ... > log 2>&1 &` | `Start-Process ... -RedirectStandardOutput x.out -RedirectStandardError x.err` | PS 没有 `nohup` 概念 |
| `wait $PID` | `Wait-Process -Id $pid` | 阻塞直到进程退出 |
| `kill $PID` | `Stop-Process -Id $pid -Force` | `-Force` 强杀 |
| `ps aux \| grep x` | `Get-Process \| Where-Object { $_.ProcessName -match 'x' }` | PS 6+ 有 `grep` 别名，5.1 没有 |
| `export VAR=val` | `$env:VAR = "val"` | 立刻生效，当前会话结束 |
| `env \| grep VAR` | `$env:VAR` 或 `Get-ChildItem env:` | 单值；列表用 `Get-ChildItem env:` |
| `2>/dev/null` | `-ErrorAction SilentlyContinue` | 或 `2>$null` 也行 |
| `\|>` | `\|` | 一样 |
| `&&` | `;` 后跟 `if ($?) { ... }` | PS 5.1 没有 `&&` |
| `\` 续行符 | 折行写在「双引号」里 | `python -c "@\`<Enter>code<Enter>\`@"` |
| `if [[ -f f ]]` | `if (Test-Path f)` | 文件存在 |
| `echo` | `Write-Output` 或 `Write-Host` | 推荐 `Write-Output`（不进变量） |
| `printf "%s\n"` | `"{0}`n" -f ...` | 字符串 format |
| `xxd` | 不用，二进制用 `.NET [System.IO.File]::ReadAllBytes` | |
| `curl -X POST` | `Invoke-WebRequest -Method POST` | 加上 `-UseBasicParsing` |
| `curl -d @file` | `-Body (Get-Content file -Raw)` 或 `-InFile file` | PS 5.1 用后者 |
| `curl -i` | `Invoke-WebRequest -PassThru` (PS 6+) | PS 5.1 没有内建 header dump；用 `(Invoke-WebRequest ...).Headers` 近似 |
| `bash script.sh` | `& script.ps1` 或 `powershell -File script.ps1` | |
| `python -c` | `python -c ...` | 直接可用，**`$` 必须转义**写成 `` `$ ``  |
| `python -c "code with $var"` | `python -c "code with `$var"` | PS 5.1 的双引号会插值 |
| `cd /f/folder` | `Set-Location F:\folder` | |
| `dirname` | `Split-Path -Parent` | |
| `basename` | `Split-Path -Leaf` | |
| `sleep 5` | `Start-Sleep -Seconds 5` | |
| `date +%s` | `([DateTimeOffset]::UtcNow).ToUnixTimeSeconds()` | |
| `mktemp` | `[System.IO.Path]::GetTempFileName()` | 完整路径 |
| `mkdir -p a b c` | `New-Item -ItemType Directory -Path a,b,c -Force` | |
| `chmod +x` | 无；PS 调用 `python.exe` 不依赖可执行位 | |

### ⚠️ 测试一条命令是否在 PS 5.1 跑得通的最快办法

```powershell
$PSVersionTable.PSVersion  # 应该看到 Major=5
```

如果显示 7.x，你能在 PowerShell 7 的环境里，那 `&&` `??` `*>` 都正常。**手册里给的 5.1 写法仍适用 7+**，反之不成立。

---

✅ **阶段 9 操作手册完**。测试全过、对比数据出来后，把 `/tmp/compare.md` 里 4 个 `__x__` 替换成实测数字，再进阶段 10。


---

# 第二部分：说明手册（看懂为什么）


> **本手册不重复操作手册的"照着做"内容**——命令、步骤、验证都在操作手册里。
> 本手册回答的是"**为什么这么写 / 这段是干什么的 / 参数是什么意思**"。
>
> 章节顺序**严格镜像**操作手册（§1→§25），每节末尾附"代码读懂 → 操作命令"的对应小表。
> 阅读时建议与操作手册**左右对照**。

---

## 📑 目录（可点击锚点）

- [0. 全局地图：阶段 9 的代码长什么样](#0-全局地图阶段-9-的代码长什么样)
- [1. 顺序对照表（镜像操作手册）](#1-顺序对照表镜像操作手册)
- [术语表（按出现顺序，至少 16 项）](#术语表按出现顺序至少-16-项)
- [2. 第 3 章 共享内核的整体设计](#2-第-3-章-共享内核的整体设计)
- [3. services/common/breaker.py 逐行解释](#3-servicescommonbreakerpy-逐行解释)
- [4. services/common/client.py 逐行解释](#4-servicescommonclientpy-逐行解释)
- [5. services/common/context.py 逐行解释](#5-servicescommoncontextpy-逐行解释)
- [6. services/common/app_factory.py 逐行解释](#6-servicescommonapp_factorypy-逐行解释)
- [7. 第 4 章 四个服务的入口 main.py](#7-第-4-章-四个服务的入口-mainpy)
- [8. 第 5 章 coordinator 的本地 / 远程切换](#8-第-5-章-coordinator-的本地--远程切换)
- [9. 第 6 章 22 个单元测试的设计思路](#9-第-6-章-22-个单元测试的设计思路)
- [10. 第 7 章 Kong 声明式配置 kong.yml](#10-第-7-章-kong-声明式配置-kongyml)
- [11. 第 8 章 docker-compose 加 Kong service](#11-第-8-章-docker-compose-加-kong-service)
- [12. 第 9 章 起服务 + 中间件顺序](#12-第-9-章-起服务--中间件顺序)
- [13. 第 14-16 章 故障隔离与熔断原理](#13-第-14-16-章-故障隔离与熔断原理)
- [14. 第 17-18 章 Prometheus 抓取 + 对比基线](#14-第-17-18-章-prometheus-抓取--对比基线)
- [15. 第 21 章 PR 描述的写作思路](#15-第-21-章-pr-描述的写作思路)

---

## 0. 全局地图：阶段 9 的代码长什么样

阶段 9 引入的变更：**新增 `services/` 四服务 + 共享内核**，**只修改一个老文件** `app_my/agents/coordinator.py`（加节点表参数），**新增 Kong 配置 + compose 一段 + 3 个测试文件 + 1 个探测脚本**。

```
ai_chief/
├── app_my/                             ← 老单体代码原样当"共享内核"（一行不改，除了下面这一个文件）
│   ├── agents/
│   │   └── coordinator.py              ← ✏️ 唯一被修改的老文件：build_workflow(nodes=None) 支持换节点表
│   ├── api/                            ← 路由模块被四个服务分别"借走"挂载
│   └── middleware/ core/ db/ ws/       ← 中间件/配置/DB/WS 全部复用
├── services/                           ← 🆕 本阶段新增
│   ├── common/                         ← 共享内核（四个服务都从这里装配）
│   │   ├── breaker.py                  ← 熔断器（closed/open/half_open 状态机）
│   │   ├── client.py                   ← ServiceClient：httpx + 重试 + 熔断 + 头透传
│   │   ├── context.py                  ← contextvars 存上游 JWT（跨服务透传用）
│   │   └── app_factory.py              ← 服务工厂：中间件栈 + /health + 路由装配
│   ├── user/main.py                    ← 9121：auth/users/tenants/admin/billing/cache
│   ├── recognizer/main.py              ← 9122：/internal/nodes/{recognize,nutrition} + /oss
│   ├── recommender/main.py             ← 9123：/internal/nodes/{recommend,rank} + /kg
│   └── chat/
│       ├── main.py                     ← 9124：/chat /tasks /ws（唯一开 quota+capture_auth 的服务）
│       └── graph_remote.py             ← 🆕 远程节点表：SPLIT_MODE=remote 时识别/营养/推荐/重排走 HTTP
├── docker/
│   ├── kong/kong.yml                   ← 🆕 Kong 声明式配置（DB-less）
│   └── docker-compose.v3.yml           ← ✏️ 只加 kong 一段
├── scripts/ws_probe.py                 ← 🆕 WebSocket 穿透网关探测
└── tests/unit/
    ├── test_circuit_breaker.py         ← 🆕 8 用例
    ├── test_service_client.py          ← 🆕 7 用例（MockTransport 离线）
    └── test_service_apps.py            ← 🆕 7 用例（装配 + 中间件顺序钉死）
```

> ⚠️ 勘误（2026-10-19）：不存在 `app_my/agents/coordinator_local.py`、`app_my/agents/graph_remote.py`；
> 远程节点表在 **`services/chat/graph_remote.py`**。项目里也没有 `app_my/api/memory.py`。

### 服务职责一句话

| 服务 | 端口 | 业务 | 对外最频繁的调用 |
| --- | --- | --- | --- |
| user | 9121 | 认证 / 用户 / 租户 / 计费 / 配额 / 管理端 / KG 写 / OSS | `/auth/login`, `/users/me`, `/billing/*` |
| recognizer | 9122 | 食材识别 + 营养计算 | chat → `POST /internal/nodes/recognize` |
| recommender | 9123 | 推荐 + 重排 + KG 读 | chat → `POST /internal/nodes/recommend` |
| chat | 9124 | 对话编排 + WS + 对话历史 | 浏览器 → `POST /chat/stream`, WS `/ws/notifications` |
| Kong | 9100 / 9105 | 路由 + CORS + 限流 + trace 透传 | 浏览器 → 上述任一 |

> **用户视角的入口永远是 `9100`**。`9121-9124` 是内部端口，仅运维和单元测试用。

---

## 1. 顺序对照表（镜像操作手册）

> 这一表是 §1-§25 的章节顺序。每一行告诉你"操作步骤做了什么"、"代码为什么要这么写"。

| 操作手册节 | 对应说明章 | 代码视角 | 一句话 |
| --- | --- | --- | --- |
| §0 30 秒核对 | §术语表 | — | 为什么这些前置项是必须的 |
| §1 拉分支 | — | — | 暂不涉及代码 |
| §2 建目录 | — | — | 暂不涉及代码 |
| §3 写共享内核 | §3-6 | services/common/* | 4 个文件的逐行解释 |
| §4 写 4 个 main.py | §7 | services/{user,recognizer,recommender,chat}/main.py | 路由装配的边界 |
| §5 改 coordinator | §8 | coordinator.py / services/chat/graph_remote.py | 怎么"按变量切两套图" |
| §6 写 22 测试 | §9 | tests/unit/test_*.py | 怎么"无外部真服务"也能全跑 |
| §7 写 kong.yml | §10 | docker/kong/kong.yml | 5 条 route 怎么对应 4 服务（/admin 含在 r-user，无独立 r-admin） |
| §8 docker-compose 加 Kong | §11 | docker/docker-compose.v3.yml | host.docker.internal 是什么 |
| §9 起服务 | §12 | 中间件顺序 | add_middleware 为什么是这样 |
| §10 /metrics 验证 | §12 | MetricsMiddleware | 为什么必须在 Auth 外 |
| §11 端到端业务流 | §术语表 | - | token / user_id 流过哪些环节 |
| §12 限流 / trace 头 | §10 | kong.yml plugins 段 | 哪些 header 是谁加的 |
| §13 WS 穿透 | §10 | r-chat-ws route | WS 在 Kong 怎么路由 |
| §14-16 故障 / 熔断 | §13 | breaker.py + client.py | 状态机怎么转的 |
| §17 Prometheus | §14 | prometheus.yml | scrape interval 与 relabel |
| §18 对比基线 | §14 | - | 怎么写出有说服力的数字 |
| §19 拷回项目 | — | - | 落盘清单 |
| §20 回归 | §9 | - | 怎么解读测试结果 |
| §21 提交 PR | §15 | - | PR 描述怎么写 |
| §22 错误对照 | §术语表 | - | 现象 → 真因 |
| §23 避坑 | — | - | 经验沉淀 |
| §24 自检 | — | - | 双终端双跑 |
| §25 PS 速查 | — | - | PowerShell 5.1 等价 |

---

## 术语表（按出现顺序，至少 16 项）

| 术语 | 一句话解释 |
| --- | --- |
| **微服务（Microservice）** | 一个应用按业务边界拆成的若干独立进程。每个服务有自己的部署、扩容、失败模式。 |
| **FastAPI** | Python 的一个 web 框架，基于 Starlette + Pydantic。本工程当前所有 HTTP 层都用它。 |
| **uvicorn** | ASGI 服务器，是真正跑 FastAPI 应用的进程。开发期 `uvicorn main:app` 启动的就是它。 |
| **DB-less 模式（Kong）** | Kong 没有数据库，所有配置写在一个 YAML 文件里；容器启动就立刻生效，不用 migrations。 |
| **CORS** | 浏览器安全规则：JS 默认不能读跨域响应。Kong 装的 cors 插件负责回复一个 `Access-Control-Allow-Origin` 头给浏览器。 |
| **Correlation ID / Trace ID** | 一次请求在多个服务之间穿行的全局唯一 ID（一般是 UUID）；出问题时报这串 ID 就能串起整条链路日志。 |
| **限流（Rate Limiting）** | 防止某一个客户端疯狂打接口。后端可以做，但 Kong 在网关层做更省资源。 |
| **JWT（JSON Web Token）** | 用户登录后拿到的一个字符串，里面有 `user_id` 等信息。后端验证它就知道"是谁"。 |
| **熔断器（Circuit Breaker）** | 一种故障隔离模式：当下游连续失败时，先在本进程内直接返回失败，省下重试延迟；过一会再放一次试探。 |
| **半开探测（half-open）** | 熔断器开一段时间后，让下一次请求打过去看看；如果通就合闸，不通就保持开。 |
| **指数退避（Exponential Backoff）** | 重试的间隔每次翻倍：0.2s → 0.4s → 0.8s。这样能避免下游刚恢复就被"重试风暴"打死。 |
| **HL（High-Level）/ LL（Low-Level）** | 中文文档里有时出现的别名——HL = "高层业务"、LL = "底层基础设施"，本工程对应 mock 数据层。 |
| **httpx** | Python 的一个 HTTP 客户端（同步 + 异步都支持）；和 requests 长得像，但能用在 async 函数里。 |
| **LangGraph / StateGraph** | LangChain 团队的状态机框架；本工程用 `app_my/agents/coordinator.py` 里的 `StateGraph(ChefState)` 描述识别→营养→推荐→重排→输出。 |
| **Pydantic 模型** | 用类语法定义"字段名+类型"，自动校验 JSON body。本工程 `BaseModel` 子类。 |
| **ASGI / ASGI 中间件** | ASGI 是 Python 异步 web 标准；中间件是一个能"在请求被路由前/后做点什么"的函数链。Starlette / FastAPI 都按这条链处理。 |
| **Bind Mount** | Docker 把宿主机的某个文件**直接**挂进容器，而不是拷一份；改宿主机文件容器立刻看到。配置 / 日志常用。 |
| **host.docker.internal** | Docker Desktop 提供的一个特殊主机名，等价于"宿主机的内网 IP"。Linux 主机需要加 `--add-host=host.docker.internal:host-gateway`。 |
| **OpenAPI** | FastAPI 自动生成的一个 API 描述文件（JSON/YAML）。可视化工具（Swagger UI / Kong / 客户端 SDK）都读它。 |
| **Prometheus / Scrape / Target** | 一个开源监控系统。"Scrape" 是它定期去目标 URL `GET /metrics` 拉指标的动作；目标就是"被拉的那个服务"。 |
| **NDJSON（Newline-Delimited JSON）** | 流式响应的最简格式：每行一个合法的 JSON 对象。本工程 `/chat/stream` 用这种。 |

---

## 2. 第 3 章 共享内核的整体设计

`services/common/` 4 个文件分别完成"四件底层辅助"：

| 文件 | 职责 | 对应设计模式 |
| --- | --- | --- |
| `breaker.py` | 单服务维度的状态机 | 熔断器模式 |
| `client.py` | 跨服务 HTTP 客户端（含熔断调用） | 客户端门面 |
| `context.py` | 当前请求上下文（trace_id） | ThreadLocal / ContextVars |
| `app_factory.py` | 装配一个完整的 FastAPI 实例 | 工厂模式 |

**为什么是"共享内核"？** 4 个服务都重复用到 `CircuitBreaker` 和 `ServiceClient`，抽到 `common/` 是 DRY；服务之间**没有**业务耦合，只是底层工具代码共享，符合"微服务 + 共享内核"标准模式。

### 数据旅程（一段对话从用户到回复）

```
1. 浏览器 → Kong(9100) /chat/stream   携带 JWT、message
2. Kong → chat(9124) /chat/stream     Kong 不鉴权（AuthMiddleware 做）
3. AuthMiddleware 验证 JWT、写入 request.state.user_id
4. QuotaMiddleware 按 user_id 限流 / 扣 quota
5. TenantMiddleware 解析 tenant_id 写入 request.state
6. CaptureAuthMiddleware 把 Authorization 头存 scope.state 以备下游用
7. /chat/stream 调用 chat_coordinator
8. coordinator（remote 模式）→ get_coordinator_agent()
9. 内部图按顺序调用：
   - recognize_node  → ServiceClient("recognizer").post(...)
                     → recognizer(9122) /internal/nodes/recognize
                     → 返回识别到的食材
   - recommend_node  → ServiceClient("recommender").post(...)
                     → recommender(9123) /internal/nodes/recommend
   - rank_node       → ServiceClient("recommender").post(...)
                     → /internal/nodes/rank
10. 每个内部 HTTP 调用都被 breaker 守护；失败重试 + 熔断
11. chat 把所有结果合流 → 返回给 Kong → 转发给浏览器
12. Prometheus 定时 GET /chat:9124/metrics 抓指标（每服务一个 job）
```

---

## 3. `services/common/breaker.py` 逐行解释

> 🔴 勘误（2026-10-19）：以实测版为准。核心类 `CircuitBreaker`（`threading.Lock` 保护的状态机）+ 全局注册表（`get_breaker` 按名取单例、`all_snapshots` 给 /health 用）。注意：跨服务调用异常叫 `CircuitOpenError`（熔断器抛）；`ServiceCallError` 在 `client.py` 里（调用失败抛），**不要混**。

#### 文件全文（行尾即注释）

```python
# services/common/breaker.py
"""
熔断器（Circuit Breaker）—— 微服务里"防止一个服务挂掉拖垮调用方"的保护开关

生活化比喻：就像家里的电闸。
    正常（CLOSED）   ：电流正常通过，请求照发。
    跳闸（OPEN）     ：连续烧坏几个电器后，电闸自动跳掉，直接拒绝请求，不再往故障服务上砸。
    试探（HALF_OPEN）：等了一会儿，放一个请求过去试试，通了就合闸，不通继续跳着。

为什么必须有它：
    微服务里 A 调 B，B 挂了 → A 的每次请求都要等超时（比如 5 秒）才失败 →
    用户请求全堵在 A 上 → A 的连接池耗尽 → A 也挂 → 一路传染（雪崩）。
    熔断器的作用是"快速失败"：B 已经确定不行了，A 立刻返回降级结果，不再等。

三个可调参数：
    failure_threshold  连续失败几次才跳闸（默认 3）
    recovery_timeout   跳闸后等多久才允许试探（默认 30 秒）
    half_open_max_calls 试探期最多放几个请求过去（默认 1）
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Dict


class BreakerState(str, Enum):
    """熔断器的三种状态。用 str 继承是为了能直接进 JSON/日志。"""
    CLOSED = "closed"        # 正常放行
    OPEN = "open"            # 跳闸，直接拒绝
    HALF_OPEN = "half_open"  # 试探期，放少量请求


class CircuitOpenError(RuntimeError):
    """熔断器处于 OPEN 时抛出的异常，调用方要 catch 它并走降级逻辑。"""


class CircuitBreaker:
    """
    一个"按服务名"独立的熔断器实例。

    线程安全：用 threading.Lock 保护状态读写。
    （uvicorn 单进程里也可能有多线程跑同步代码，加锁最稳妥）
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = BreakerState.CLOSED
        self._failures = 0           # 连续失败计数（成功一次就清零）
        self._opened_at = 0.0        # 跳闸时刻（time.time() 的时间戳）
        self._half_open_calls = 0    # 试探期已经放过去几个请求
        self._last_error = ""        # 最近一次失败原因，便于排错

    # ------------------------------------------------------------------ 状态查询
    @property
    def state(self) -> BreakerState:
        """当前状态。注意：OPEN 状态下如果已经过了恢复时间，会自动降级成 HALF_OPEN。"""
        with self._lock:
            return self._current_state_unlocked()

    def _current_state_unlocked(self) -> BreakerState:
        """内部方法：调用前必须已持有锁。OPEN 超时自动转 HALF_OPEN。"""
        if self._state == BreakerState.OPEN:
            if time.time() - self._opened_at >= self.recovery_timeout:
                self._state = BreakerState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    # ------------------------------------------------------------------ 调用前闸门
    def before_call(self) -> None:
        """
        发请求之前调用。如果处于 OPEN（还没到试探时间），直接抛 CircuitOpenError。

        这一抛很关键：它让调用方"立刻失败"，而不是陪着故障服务耗掉整个超时时间。
        """
        with self._lock:
            state = self._current_state_unlocked()
            if state == BreakerState.OPEN:
                raise CircuitOpenError(
                    f"[{self.name}] 熔断器已跳闸，剩余恢复时间 "
                    f"{max(0.0, self.recovery_timeout - (time.time() - self._opened_at)):.1f}s"
                )
            if state == BreakerState.HALF_OPEN:
                # 试探期有名额限制：超过名额的请求继续拒绝，避免刚有点希望就被打垮
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitOpenError(f"[{self.name}] 试探名额已用完，稍后再试")
                self._half_open_calls += 1

    # ------------------------------------------------------------------ 结果回写
    def record_success(self) -> None:
        """调用成功：连续失败计数清零；如果是试探期，说明服务恢复了，直接合闸。"""
        with self._lock:
            self._failures = 0
            self._last_error = ""
            self._half_open_calls = 0
            self._state = BreakerState.CLOSED

    def record_failure(self, reason: str = "") -> None:
        """调用失败：连续失败计数 +1；达到阈值就跳闸。"""
        with self._lock:
            self._failures += 1
            self._last_error = reason
            if self._state == BreakerState.HALF_OPEN:
                # 试探失败 → 立刻重新跳闸，并把恢复计时器重置（再等一轮）
                self._trip_unlocked()
            elif self._failures >= self.failure_threshold:
                self._trip_unlocked()

    def _trip_unlocked(self) -> None:
        """内部方法：置为 OPEN 并记录跳闸时刻。"""
        self._state = BreakerState.OPEN
        self._opened_at = time.time()
        self._half_open_calls = 0

    # ------------------------------------------------------------------ 观测 / 测试辅助
    def snapshot(self) -> Dict[str, object]:
        """把内部状态导出成字典，给 /health 和指标用。"""
        with self._lock:
            state = self._current_state_unlocked()
            return {
                "name": self.name,
                "state": state.value,
                "failures": self._failures,
                "threshold": self.failure_threshold,
                "last_error": self._last_error,
                "recover_in": (
                    round(max(0.0, self.recovery_timeout - (time.time() - self._opened_at)), 1)
                    if state == BreakerState.OPEN else 0.0
                ),
            }

    def reset(self) -> None:
        """恢复到出厂状态。单测里每个用例跑之前都要调一次，避免用例互相污染。"""
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failures = 0
            self._opened_at = 0.0
            self._half_open_calls = 0
            self._last_error = ""


# 全局注册表：所有熔断器按"服务名"登记在这里，方便 /health 一次性列出全部状态
_REGISTRY: Dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = threading.Lock()


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    """取（必要时创建）某个服务的熔断器。同名只会有一个实例。"""
    with _REGISTRY_LOCK:
        if name not in _REGISTRY:
            _REGISTRY[name] = CircuitBreaker(name, **kwargs)
        return _REGISTRY[name]


def all_snapshots() -> Dict[str, Dict[str, object]]:
    """导出全部熔断器的状态快照，供 /health 展示。"""
    with _REGISTRY_LOCK:
        return {name: b.snapshot() for name, b in _REGISTRY.items()}


def reset_all() -> None:
    """清空注册表（仅测试用）。"""
    with _REGISTRY_LOCK:
        _REGISTRY.clear()
```

### 三个要点

1. **`_current_state_unlocked()` 里"OPEN 超时自动降 HALF_OPEN"**：状态不是靠定时器切的，而是**每次读状态时顺手判断**——过了 `recovery_timeout` 就地改状态。这样不用起后台线程，代码简单且线程安全。
2. **`before_call()` 的两个闸门**：OPEN（没到试探时间）直接抛 `CircuitOpenError`（快速失败的价值就在这一抛）；HALF_OPEN 有 `half_open_max_calls` 个名额，超名额照样拒（保护刚恢复的服务）。
3. **`record_failure()` 在 HALF_OPEN 下试探失败 → 立刻重新跳闸并重置计时**——这就是实测里"第 4 次请求 16s（熔断 fast-fail）→ 等 35s → 恢复"的机制来源。

---

## 4. `services/common/client.py` 逐行解释

> 🔴 勘误（2026-10-19）：实测版 API 是 `get_client(name)`（按名取单例）+ `ServiceClient.request()`。没有 `make_clients`、没有 `set_trace_id`。trace_id 从 `app_my.core.logging.trace_id_var`（阶段 7 的 contextvars）自动取。

#### 文件全文（行尾即注释）

```python
# services/common/client.py
"""
服务间调用客户端（ServiceClient）—— 微服务之间唯一的"电话机"

它把四件事打包在一起，业务代码只管 client.post(...)，不用关心细节：
    ① HTTP 传输     ：用 httpx.AsyncClient（异步，不阻塞事件循环）
    ② 自动重试      ：网络抖动/对方 5xx 时按"指数退避"重试几次
    ③ 熔断保护      ：对方连续挂了就跳闸，立刻失败，不再陪它耗超时
    ④ 上下文透传    ：把 trace_id / tenant_id / user_id 放进请求头带过去

为什么要透传上下文：
    一次用户请求会穿过 "Kong → chat → recommender" 三个进程。
    如果不把 trace_id 带过去，三个进程各写各的日志，出问题时你根本没法把
    同一次请求的三段日志串起来看 —— 这就是"链路追踪"要解决的头号问题。
"""
from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Dict, Optional

import httpx

from services.common import breaker as breaker_mod

# 请求头名字，全项目统一（Kong 和各服务都用这三个）
HEADER_TRACE = "X-Trace-Id"
HEADER_TENANT = "X-Tenant-Id"
HEADER_USER = "X-User-Id"

# 这几类 HTTP 状态码才重试：429 是被限流（等一下再来），5xx 是对方出错。
# 4xx（401/403/404/422）是"请求本身有问题"，重试一万次也一样，不重试。
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ServiceCallError(RuntimeError):
    """服务调用最终失败时抛出。调用方 catch 它做降级。"""


def _current_trace_id() -> str:
    """
    取当前协程上下文里的 trace_id。

    为什么用 contextvars 而不是参数传递：
    trace_id 是"贯穿全链路的环境变量"，如果每个函数都加一个 trace_id 参数，
    从接口层到最深的工具函数要改几十个签名。contextvars 是 Python 官方给的
    "协程版全局变量"，在 await 链里自动传递，不需要改任何函数签名。
    """
    try:
        from app_my.core.logging import trace_id_var
        value = trace_id_var.get()
        return value if value and value != "-" else ""
    except Exception:
        return ""


def _upstream_token() -> str:
    """取上游请求带过来的 JWT（由 TokenCaptureMiddleware 存进 contextvars）。"""
    try:
        from services.common.context import get_upstream_token
        return get_upstream_token()
    except Exception:
        return ""


class ServiceClient:
    """
    针对某一个下游服务的客户端。一个下游服务一个实例（内部复用同一个连接池）。
    """

    def __init__(
        self,
        name: str,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
        retries: int = 2,
        backoff: float = 0.2,
        transport: Optional[Any] = None,
        **breaker_kwargs,
    ) -> None:
        """
        transport：可选的 httpx 传输层。正常运行时不传（走真实网络）；
        单元测试时传 httpx.MockTransport，就能在完全离线的情况下
        精确模拟"对方返回 503""连接超时"等各种故障，验证重试和熔断逻辑。
        """
        self.name = name
        self._transport = transport
        self.base_url = (base_url or os.getenv(
            f"SERVICE_{name.upper()}_URL", f"http://127.0.0.1:{_default_port(name)}"
        )).rstrip("/")
        self.timeout = timeout
        self.retries = retries          # 首次失败后再试几次（不含第一次）
        self.backoff = backoff          # 退避基数：第 n 次等待 backoff * 2^(n-1) 秒
        self.breaker = breaker_mod.get_breaker(name, **breaker_kwargs)
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ 连接管理
    def _ensure_client(self) -> httpx.AsyncClient:
        """
        懒创建 httpx.AsyncClient。

        为什么不每次请求 new 一个：
        AsyncClient 内部持有连接池，复用它能省掉反复 TCP 握手 + TLS 的开销。
        但也不能在 __init__ 里创建 —— 那时可能还没有事件循环。
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 2.0)),
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        """关闭连接池。服务关闭时调用，否则会有连接泄漏警告。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------ 对外方法
    async def post(self, path: str, payload: Optional[Dict[str, Any]] = None,
                   **kwargs) -> Dict[str, Any]:
        """POST JSON。返回对方响应的 JSON 字典。"""
        return await self.request("POST", path, json=payload, **kwargs)

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None,
                  **kwargs) -> Dict[str, Any]:
        """GET。返回对方响应的 JSON 字典。"""
        return await self.request("GET", path, params=params, **kwargs)

    async def request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        trace_id: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发请求的核心方法：熔断闸门 → 重试循环 → 回写熔断状态。

        参数：
            method     HTTP 方法（"GET" / "POST"）
            path       路径，如 "/internal/nodes/recommend"
            json       POST 的请求体（字典）
            params     GET 的查询参数（字典）
            tenant_id  要透传的租户 ID（不传就不带这个头）
            user_id    要透传的用户 ID
            trace_id   要透传的链路 ID（不传就自动从 contextvars 里取）
            auth_token 要透传的 JWT（形如 "Bearer xxx"）。
                       因为鉴权下沉在各服务内（Kong 不鉴权），跨服务调用必须把
                       用户的 token 原样带过去，否则对方 AuthMiddleware 直接 401。
                       不传时会自动从 contextvars 里取上游抓到的 token。
        """
        # ---- ① 熔断闸门：已跳闸就直接抛，不再发请求 ----
        self.breaker.before_call()

        headers: Dict[str, str] = {}
        tid = trace_id or _current_trace_id()
        if tid:
            headers[HEADER_TRACE] = tid
        if tenant_id is not None:
            headers[HEADER_TENANT] = str(tenant_id)
        if user_id is not None:
            headers[HEADER_USER] = str(user_id)

        token = auth_token or _upstream_token()
        if token:
            headers["Authorization"] = token

        last_error = ""
        client = self._ensure_client()

        # ---- ② 重试循环：第 0 次是正常请求，之后才是重试 ----
        for attempt in range(self.retries + 1):
            try:
                resp = await client.request(method, path, json=json, params=params, headers=headers)

                if resp.status_code in RETRYABLE_STATUS:
                    # 对方明确说"我现在不行"，算一次失败，可以重试
                    last_error = f"HTTP {resp.status_code}"
                    raise httpx.HTTPStatusError(last_error, request=resp.request, response=resp)

                if resp.status_code >= 400:
                    # 4xx 不重试：请求本身有问题，重试没意义。直接算成功"送达"，
                    # 让熔断知道对方还活着（它只是拒绝了我们的请求）。
                    self.breaker.record_success()
                    raise ServiceCallError(
                        f"[{self.name}] {method} {path} 返回 {resp.status_code}: {resp.text[:200]}"
                    )

                self.breaker.record_success()
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text}

            except breaker_mod.CircuitOpenError:
                raise                      # 熔断的错不重试，直接往上抛
            except ServiceCallError:
                raise                      # 4xx 的错不重试
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt >= self.retries:
                    break
                # 指数退避 + 抖动：0.2s → 0.4s → 0.8s…再加 ±20% 随机，
                # 避免"所有调用方同一时刻一起重试"把刚恢复的服务再次打垮（惊群）。
                delay = self.backoff * (2 ** attempt) * (1 + random.uniform(-0.2, 0.2))
                await asyncio.sleep(max(delay, 0.01))

        # ---- ③ 所有重试都失败：记一次熔断失败，再抛给调用方降级 ----
        self.breaker.record_failure(last_error)
        raise ServiceCallError(
            f"[{self.name}] {method} {path} 失败（重试 {self.retries} 次后）：{last_error}"
        )

    # ------------------------------------------------------------------ 观测
    def breaker_snapshot(self) -> Dict[str, object]:
        """导出这个下游服务当前熔断器的状态。"""
        return self.breaker.snapshot()


def _default_port(name: str) -> int:
    """各服务的默认端口（与 docker/kong/kong.yml 保持一致）。"""
    return {"user": 9121, "recognizer": 9122, "recommender": 9123, "chat": 9124}.get(name, 9002)


def get_client(name: str, **kwargs) -> ServiceClient:
    """
    取（必要时创建）某个下游服务的客户端。

    做成全局缓存的原因和熔断器一样：一个进程里对同一个下游只该有一个连接池。
    """
    global _CLIENTS
    if name not in _CLIENTS:
        _CLIENTS[name] = ServiceClient(name, **kwargs)
    return _CLIENTS[name]


_CLIENTS: Dict[str, ServiceClient] = {}


async def aclose_all() -> None:
    """关闭所有客户端的连接池（服务关闭时调用）。"""
    for c in _CLIENTS.values():
        await c.aclose()
    _CLIENTS.clear()
```

### 四个要点

1. **重试循环里 4xx 与 5xx 分家**：`RETRYABLE_STATUS = {429, 500, 502, 503, 504}` 才重试；4xx 直接 `record_success()`（对方活着，只是拒绝我们）后抛 `ServiceCallError`——这保证了"请求写错"不会把熔断器打跳闸。
2. **一次 `post()` 只记 1 次熔断失败**：重试是内部循环，3 次 HTTP 失败 → 1 次调用失败。熔断阈值衡量的是"调用级故障"，不是"请求数"。
3. **指数退避 + ±20% 抖动**：`backoff * 2**attempt * (1 + uniform(-0.2, 0.2))`，防止所有调用方同一瞬间一起重试（惊群）把刚恢复的服务再次打垮。
4. **`transport` 参数**：正常运行不传（走真实网络）；单测传 `httpx.MockTransport`，离线精确模拟 503/连接失败——§6 的 7 个客户端用例全靠它。

---

## 5. `services/common/context.py` 逐行解释

> 🔴 勘误（2026-10-19）：实测版存的是**上游 JWT**，不是 trace_id（trace_id 复用阶段 7 的 `app_my.core.logging.trace_id_var`，不重复造）。

#### 文件全文（行尾即注释）

```python
# services/common/context.py
"""
跨服务调用的"上下文小仓库"—— 存放那些没法通过函数参数传递、但又必须带过去的东西

为什么单独一个文件：
    LangGraph 的节点函数签名被框架定死了：`async def node(state: dict) -> dict`。
    我们想在节点里发 HTTP 请求调用别的服务，就得带上用户的 JWT，
    但签名里塞不进去。contextvars 是 Python 官方为这种场景准备的方案：
    它在"协程上下文"里存值，await 链上任何深度都能读到，且不同请求之间互不干扰。

    类比：普通全局变量是"整栋楼共用一个白板"（并发时会串台）；
    contextvars 是"每个人手里一块自己的小白板"（各自独立，还能带进电梯）。
"""
from __future__ import annotations

import contextvars
from typing import Optional

# 上游请求带过来的原始 Authorization 头（形如 "Bearer eyJhbGci..."）
_upstream_token: contextvars.ContextVar[str] = contextvars.ContextVar(
    "upstream_token", default=""
)


def set_upstream_token(token: str) -> None:
    """在请求入口处把 token 存进来。"""
    _upstream_token.set(token or "")


def get_upstream_token() -> str:
    """在任意深度（包括 LangGraph 节点里）把 token 读出来。"""
    return _upstream_token.get() or ""


def auth_header() -> dict:
    """
    直接产出可以塞进 httpx 的请求头字典。
    没有 token 时返回空字典，避免发出一个值为空的 Authorization 头（对方会解析失败）。
    """
    token = get_upstream_token()
    return {"Authorization": token} if token else {}
```

### 为什么需要它

LangGraph 节点签名被框架钉死为 `async def node(state) -> dict`，用户的 JWT 塞不进参数。`contextvars` 相当于"每个请求自己的一块小白板"：`TokenCaptureMiddleware` 在入口 `set_upstream_token()` 存一笔，节点深处 `auth_header()` 取出来用，不同请求互不串台。

---

## 6. `services/common/app_factory.py` 逐行解释

> 🔴 勘误（2026-10-19）：项目里**没有** `app_my/middleware/cors.py`（CORS 用 `fastapi.middleware.cors` 自带的）、没有 `app_my/middleware/tracing.py`（是 `app_my/middleware/trace.py`）、`MetricsMiddleware` 在 `app_my/middleware/metrics.py`（不在 core 里）。本文件还**新定义了两个中间件**：`TenantVarMiddleware`（把租户写进 contextvars）和 `TokenCaptureMiddleware`（把 JWT 写进 contextvars）。

#### 文件全文（行尾即注释）

```python
# services/common/app_factory.py
"""
服务工厂（create_service_app）—— 四个微服务的"统一装配线"

为什么要有它：
    拆成四个服务后，如果每个服务的 main.py 都抄一遍"加中间件 + 加健康检查 + 加指标端点"，
    很快就会抄歪：某个服务忘了加鉴权、另一个服务的 /metrics 被 401 挡住……
    工厂函数把这套装配固定成一份代码，四个服务共享，顺序只可能错一次。

🔴 本文件最关键的知识点：Starlette 的中间件"洋葱顺序"
    Starlette 规则：**后 add_middleware 的，包在更外层**。
    所以下面代码是"倒着写"的：越靠上的 add 语句，请求越晚经过它（越靠里）。
    请求实际经过顺序（外 → 内）：
        CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
              → UserLimit → RateLimit → (Quota) → 路由
    响应返回时反过来走一遍（内 → 外）。

    🔴 两条不能违反的顺序约束：
    1. MetricsMiddleware 必须 add 在 AuthMiddleware **之前**（这样它才更靠外），
       否则 /metrics 会先被 Auth 拦下返回 401，Prometheus 永远抓不到数据。
    2. CORS 必须最后 add（最外层），否则内层限流吐出的 429 响应不带跨域头，
       浏览器前端只能看到"网络错误"，根本不知道自己是被限流了。
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import List, Optional, Sequence, Tuple

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app_my.core.config import settings
from app_my.core.logging import logger, setup_logging
from app_my.core.tenant import current_tenant_id
from app_my.middleware.auth import AuthMiddleware
from app_my.middleware.metrics import MetricsMiddleware
from app_my.middleware.quota import QuotaMiddleware
from app_my.middleware.rate_limit import RateLimitMiddleware, UserRateLimitMiddleware
from app_my.middleware.tenant import TenantContextMiddleware
from app_my.middleware.trace import TraceIdMiddleware


# ---------------------------------------------------------------- 两个本阶段新增的小中间件
class TenantVarMiddleware(BaseHTTPMiddleware):
    """
    把 request.state.tenant_id 写进 contextvars（current_tenant_id）。

    为什么必须新写一个：
    现有的 TenantContextMiddleware 只写 request.state，**不写 contextvars**。
    单体时代没问题——因为 app_my/agents/coordinator.py 里手动 set 了一次。
    但拆成微服务后，recommender 进程里跑的 recommend_node 深处会调
    local_recipe_search()，它靠 current_tenant_id 做灰度判定；
    这个进程里没人 set，就会一直用默认值 1 —— 灰度/租户隔离静默失效。

    🔴 这是本次拆分最容易漏、且最难查的一个点：
    不报错、不崩溃，只是"租户 B 用成了租户 A 的配置"。
    """

    async def dispatch(self, request: Request, call_next):
        tenant_id = getattr(request.state, "tenant_id", None)
        # 没有租户（未登录 / 内部探测）就保留默认值，不强行写 0
        token = current_tenant_id.set(tenant_id if tenant_id is not None else 1)
        try:
            return await call_next(request)
        finally:
            # 必须 reset：不然同一个线程处理下一个请求时会读到上一个租户（连接池复用场景）
            current_tenant_id.reset(token)


class TokenCaptureMiddleware(BaseHTTPMiddleware):
    """
    把原始 Authorization 头存进 contextvars，供"跨服务调用"时透传。

    为什么需要：chat 服务要去调 recommender 服务，而 recommender 也有 AuthMiddleware
    （鉴权下沉在各自服务内，Kong 不做鉴权）。所以 chat 必须把用户的 JWT 原样带过去，
    否则对方直接 401。

    为什么用 contextvars 而不是一层层传参：
    LangGraph 的节点函数签名是固定的 `async def node(state: dict) -> dict`，
    没法额外塞一个 token 参数。contextvars 让我们"绕开签名"把值带进去。
    """

    async def dispatch(self, request: Request, call_next):
        from services.common.context import set_upstream_token
        set_upstream_token(request.headers.get("authorization", ""))
        return await call_next(request)


# ---------------------------------------------------------------- 工厂函数
def create_service_app(
    service_name: str,
    routers: Sequence[Tuple[APIRouter, str, List[str]]] = (),
    *,
    enable_auth: bool = True,
    enable_quota: bool = False,
    capture_auth: bool = False,
    cors_origins: Optional[List[str]] = None,
    startup_tasks: Sequence[Callable[[], Coroutine]] = (),
) -> FastAPI:
    """
    造一个"装配好"的 FastAPI 服务实例。

    参数：
        service_name   服务名（user / recognizer / recommender / chat），进 /health 和日志
        routers        要挂的路由，每个元素是 (router, prefix, tags) 三元组
        enable_auth    是否挂 JWT 鉴权中间件（四个服务都要 True）
        enable_quota   是否挂租户配额中间件（只有 chat 服务要 True，因为它管 /chat/stream）
        capture_auth   是否捕获 Authorization 头用于跨服务透传（只有 chat 服务要 True）
        cors_origins   允许的跨域来源；不传就用 settings.CORS_ORIGINS
        startup_tasks  要常驻运行的后台协程工厂（如 chat 服务的 Redis 订阅中继）。
                       传进来的是"函数"而不是"协程对象"，因为协程对象只能被 await 一次；
                       传函数才能在每个进程里重新创建。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        logger.info("服务 [%s] 启动中 ...", service_name)

        # 拉起常驻后台协程（如 WS 通知中继），并把句柄存起来以便关闭时取消
        tasks = [asyncio.create_task(factory(), name=f"{service_name}-bg-{i}")
                 for i, factory in enumerate(startup_tasks)]
        if tasks:
            logger.info("服务 [%s] 已启动 %d 个后台协程", service_name, len(tasks))

        yield

        logger.info("服务 [%s] 关闭", service_name)
        # 先取消后台协程再收尾，否则事件循环关闭时会报
        # "Task was destroyed but it is pending!"
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        # 关闭跨服务调用客户端的连接池，否则进程退出会有 "unclosed connector" 警告
        try:
            from services.common.client import aclose_all
            await aclose_all()
        except Exception:
            pass

    app = FastAPI(
        title=f"{settings.APP_NAME} · {service_name}服务",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # ============ 中间件（🔴 倒着 add：越靠上的越靠里）============
    if capture_auth:
        app.add_middleware(TokenCaptureMiddleware)      # 最里层：先把 token 抓到手

    if enable_quota:
        app.add_middleware(QuotaMiddleware)             # 租户配额（只有 chat 用）

    app.add_middleware(RateLimitMiddleware)             # 4. IP 级限流
    app.add_middleware(UserRateLimitMiddleware)         # 3. 用户级限流
    app.add_middleware(TenantVarMiddleware)             # 2.6 写 contextvars（本阶段新增）
    app.add_middleware(TenantContextMiddleware)         # 2.5 租户上下文
    if enable_auth:
        app.add_middleware(AuthMiddleware)              # 2. JWT 鉴权
    app.add_middleware(MetricsMiddleware)               # 1.5 指标埋点 + /metrics（必须在 Auth 之外）
    app.add_middleware(TraceIdMiddleware)               # 1. TraceID
    app.add_middleware(                                 # 0. CORS（最后 add → 最外层）
        CORSMiddleware,
        allow_origins=cors_origins or settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ============ 路由 ============
    for router, prefix, tags in routers:
        app.include_router(router, prefix=prefix, tags=tags)

    # ============ 通用端点：每个服务都有，方便 Kong 探活与排错 ============
    @app.get("/")
    async def root():
        return {"service": service_name, "version": settings.APP_VERSION, "status": "running"}

    @app.get("/health")
    async def health():
        """
        健康检查。除了返回 ok，还带上"我依赖的下游服务熔断器状态"——
        排障时一眼就能看出 chat 是不是把 recommender 熔断了。
        """
        from services.common.breaker import all_snapshots
        return {
            "status": "ok",
            "service": service_name,
            "version": settings.APP_VERSION,
            "breakers": all_snapshots(),
        }

    return app
```

### 中间件顺序为什么这样？

实测确认（别凭印象）：Starlette 的 `add_middleware()` 是 `user_middleware.insert(0, ...)`——
**user_middleware 列表"外层在前"**，所以"后 add 的更靠外层"。请求实际穿过顺序（外 → 内）：

```
CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
      → UserLimit → RateLimit → (Quota) → (TokenCapture) → 路由
```

两条铁约束（§6.3 的测试把它们钉死了）：
1. **Metrics 在 Auth 之外**（add 顺序上 Metrics 先 add）——否则 `/metrics` 被 401 挡住，Prometheus 永远抓不到；
2. **CORS 最后 add（最外层）**——否则内层限流的 429 不带跨域头，浏览器只看到"网络错误"。

---

## 7. 第 4 章 四个服务的入口 `main.py`

> 🔴 勘误（2026-10-19）：路由归属以实测版为准——`/kg` 归 recommender、`/oss` 归 recognizer、`/cache` 归 user、`/tasks`+`/ws` 归 chat；**不存在 `/memory` 路由**。

### 7.1 `services/user/main.py`

```python
# services/user/main.py
"""
user 服务（端口 9121）—— 管"人"和"组织"的一切

职责边界（为什么这些路由放一起）：
    认证（auth）、用户资料（user）、租户（tenant）、管理端（admin）、成本统计（billing）
    这五组路由的共同点是：**它们只碰 PostgreSQL 和 Redis，不碰大模型**。
    这是拆分的第一条依据——资源画像相同的功能放一起，扩容时可以单独加机器，
    不用为了给"对话"扩容而连带把"登录"也复制一份。

它不做什么：不调大模型、不碰 Milvus、不碰 Neo4j。
"""
from services.common.app_factory import create_service_app

# 复用单体时代已经写好的路由模块：拆分是"换入口"，不是"重写业务"
from app_my.api import auth, user, cache
from app_my.api import tenant as tenant_api
from app_my.api import admin as admin_api
from app_my.api import billing

app = create_service_app(
    "user",
    routers=[
        (auth.router, "/auth", ["认证"]),
        (user.router, "/users", ["用户"]),
        (tenant_api.router, "/tenants", ["租户管理"]),
        (admin_api.router, "/admin", ["管理端"]),
        (billing.router, "/billing", ["成本统计"]),
        (cache.router, "/cache", ["缓存观测"]),
    ],
    enable_auth=True,      # 有自己的 JWT 鉴权（Kong 不鉴权，鉴权下沉在各自服务）
    enable_quota=False,    # 配额只管 /chat/stream，那是 chat 服务的事
    capture_auth=False,    # user 服务不往下调别的服务，不用透传 token
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.user.main:app", host="0.0.0.0", port=9121, reload=False)
```

> 要点：user 服务**只碰 PostgreSQL 和 Redis，不碰大模型**。资源画像相同的功能放一起，扩容时不用连坐。

### 7.2 `services/recognizer/main.py`

```python
# services/recognizer/main.py
"""
recognizer 服务（端口 9122）—— 把"用户说了什么 / 拍了什么"变成结构化食材清单

拆出来的理由（拆分依据第二条：故障半径）：
    识别节点要调**多模态大模型**（看图），是所有节点里最慢、最贵、最容易超时的一环。
    它单独成一个服务，好处很实在：
      · 它超时/报错时，只影响"识别"，chat 服务还能用上一轮结果继续跑；
      · 它慢的时候可以单独加实例（比如 2 个 recognizer + 1 个 chat）；
      · 改识别模型不用重启整个应用。

对外只有两个"内部接口"（/internal/ 前缀，约定只给服务间调用）：
    POST /internal/nodes/recognize   文字/图片 → 食材清单
    POST /internal/nodes/nutrition   食材清单 → 营养估算

🔴 为什么要重新包一层 HTTP 接口，而不是直接把 state 整个传过来：
    LangGraph 的 state 里有 messages 字段，里面装的是 LangChain 的
    HumanMessage / AIMessage **对象**，不是 JSON。直接 json.dumps 会报
    "Object of type HumanMessage is not JSON serializable"。
    所以这里定了一套"只传必要字段"的窄接口：进 JSON、出 JSON。
"""
from typing import List, Optional

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app_my.agents.nutritionist import nutrition_node
from app_my.agents.recognizer import recognize_node
from app_my.api import oss
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


# ----------------------------------------------------------------- 接口的数据契约
class RecognizeIn(BaseModel):
    """识别接口的入参。"""
    text: str = Field(default="", description="用户输入的文字（图片模式下可作补充提示）")
    image_url: List[str] = Field(default_factory=list, description="图片 URL 列表，空数组=走文字抽取")


class NutritionIn(BaseModel):
    """营养接口的入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="上一步识别出的食材清单")


def _summary_of(node_output: dict) -> str:
    """
    从节点返回值里抽出那条 AIMessage 的文本，作为 summary 返回。

    节点返回形如 {"nutrition": {...}, "messages": [AIMessage("...")]}；
    messages 是 LangChain 对象不能进 JSON，所以这里提前把它转成纯字符串。
    """
    msgs = node_output.get("messages") or []
    if msgs:
        return getattr(msgs[-1], "content", "") or ""
    return ""


router = APIRouter()


@router.post("/internal/nodes/recognize")
async def http_recognize(body: RecognizeIn):
    """
    把 recognize_node 包成 HTTP 接口。

    做法：造一个"最小可用的 state" → 调原来的节点函数 → 把结果转成纯 JSON。
    这样**一个字的业务逻辑都没重写**，只是加了一层协议转换。
    """
    state = {
        "messages": [HumanMessage(content=body.text)],   # 节点只读最后一条消息的 content
        "image_url": body.image_url or [],
    }
    out = await recognize_node(state)
    logger.info("recognizer.http: 识别完成，%d 种食材", len(out.get("ingredients") or []))
    return {
        "ingredients": out.get("ingredients") or [],
        "summary": _summary_of(out),
    }


@router.post("/internal/nodes/nutrition")
async def http_nutrition(body: NutritionIn):
    """把 nutrition_node 包成 HTTP 接口。"""
    state = {"ingredients": body.ingredients or []}
    out = await nutrition_node(state)
    return {
        "nutrition": out.get("nutrition") or {},
        "summary": _summary_of(out),
    }


app = create_service_app(
    "recognizer",
    routers=[
        (router, "", ["识别内部接口"]),
        (oss.router, "/oss", ["阿里云OSS"]),   # 图片要先上传才能识别，归识别域
    ],
    enable_auth=True,      # 一样要鉴权：Kong 不做鉴权，靠各服务自己守门
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recognizer.main:app", host="0.0.0.0", port=9122, reload=False)
```

> 要点：**窄接口**（进 JSON 出 JSON）。LangGraph 的 state 里有 `HumanMessage/AIMessage` 对象，直接 json.dumps 会报 not serializable，所以 HTTP 层只传必要字段，`_summary_of` 把 AIMessage 转纯字符串。

### 7.3 `services/recommender/main.py`

```python
# services/recommender/main.py
"""
recommender 服务（端口 9123）—— 管"找菜谱"和"排菜谱"，以及知识图谱

拆出来的理由（拆分依据第三条：数据所有权）：
    Milvus 向量库和 Neo4j 图谱**只被这一个服务访问**。
    拆分前 chat 进程里也连着这两个库，现在它们成了 recommender 的"私有数据"，
    别的服务想查菜谱，只能走 HTTP 来问它 —— 这就是微服务的"数据所有权"原则。

对外接口：
    POST /internal/nodes/recommend   食材清单 → 候选菜谱（未排序）
    POST /internal/nodes/rank        候选菜谱 + 用户画像 → 排好序的菜谱
    GET  /kg/ask                     知识图谱问答（阶段 3 的路由，原样搬过来）
    GET  /kg/stats                   图谱规模统计

🔴 本服务最需要注意的一点（也是本次拆分最容易踩的坑）：
    local_recipe_search() 内部会读 current_tenant_id 这个 contextvars 变量做灰度判定。
    单体时代是 coordinator 手动 set 的；现在它跑在 recommender 自己的进程里，
    没人 set 就会一直用默认值 1 —— 表现为"灰度开关对所有租户一起生效/失效"，
    而且**不报错**。
    解决办法在 services/common/app_factory.py 的 TenantVarMiddleware：
    每个请求进来时把 request.state.tenant_id 写进 contextvars。
"""
from typing import List

from fastapi import APIRouter
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app_my.agents.ranker import rank_node
from app_my.agents.recommender import recommend_node
from app_my.api import kg
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


class RecommendIn(BaseModel):
    """推荐接口入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="识别出的食材清单")


class RankIn(BaseModel):
    """重排接口入参。"""
    recipes: List[dict] = Field(default_factory=list, description="候选菜谱（推荐节点的产出）")
    user_profile: dict = Field(default_factory=dict, description="用户画像（目标/忌口/过敏/偏好）")


def _summary_of(node_output: dict) -> str:
    """把节点返回里的 AIMessage 转成纯字符串（LangChain 对象不能进 JSON）。"""
    msgs = node_output.get("messages") or []
    return getattr(msgs[-1], "content", "") if msgs else ""


router = APIRouter()


@router.post("/internal/nodes/recommend")
async def http_recommend(body: RecommendIn):
    """把 recommend_node 包成 HTTP 接口。"""
    out = await recommend_node({"ingredients": body.ingredients or []})
    recipes = out.get("recipes") or []
    logger.info("recommender.http: 检索到 %d 条候选菜谱", len(recipes))
    return {"recipes": recipes, "summary": _summary_of(out)}


@router.post("/internal/nodes/rank")
async def http_rank(body: RankIn):
    """把 rank_node 包成 HTTP 接口。"""
    out = await rank_node({
        "recipes": body.recipes or [],
        "user_profile": body.user_profile or {},
    })
    ranked = out.get("ranked_recipes") or []
    logger.info("recommender.http: 重排完成，%d 条", len(ranked))
    return {"ranked_recipes": ranked, "summary": _summary_of(out)}


app = create_service_app(
    "recommender",
    routers=[
        (router, "", ["推荐内部接口"]),
        (kg.router, "/kg", ["知识图谱"]),
    ],
    enable_auth=True,
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recommender.main:app", host="0.0.0.0", port=9123, reload=False)
```

> 要点：Milvus / Neo4j 只被这个服务访问——"数据所有权"原则。`/kg` 挂在这里（不在 chat）。

### 7.4 `services/chat/main.py`

```python
# services/chat/main.py
"""
chat 服务（端口 9124）—— 用户真正"说话"的入口，也是唯一会去调别的服务的地方

它承担三件事：
    1. /chat/stream   流式对话（LangGraph 编排，可能跨服务调 recognizer / recommender）
    2. /ws/notifications  WebSocket 实时推送（阶段 8）
    3. /tasks/*       长任务提交与查询（阶段 8）

它是本阶段唯一打开了两个"额外开关"的服务：
    enable_quota=True   因为 /chat/stream 要按租户配额限流（QuotaMiddleware 只认这个路径）
    capture_auth=True   因为它要跨服务调用，必须把用户的 JWT 抓下来透传给下游
    startup_tasks       因为 WS 通知中继（订阅 Redis 频道）必须常驻在 chat 进程里
"""
import os

from app_my.api import chat
from app_my.api import tasks as tasks_api
from app_my.ws import gateway as ws_gateway
from app_my.ws.relay import run_relay

from services.common.app_factory import create_service_app


# 读一次运行模式，写进启动日志，方便排错时一眼确认
SPLIT_MODE = os.getenv("SPLIT_MODE", "local").strip().lower()


app = create_service_app(
    "chat",
    routers=[
        (chat.router, "/chat", ["AI对话"]),
        (tasks_api.router, "/tasks", ["异步任务"]),
        (ws_gateway.router, "/ws", ["WebSocket"]),
    ],
    enable_auth=True,
    enable_quota=True,     # 只有 chat 需要：QuotaMiddleware 拦截 /chat/stream 做租户配额
    capture_auth=True,     # 只有 chat 需要：把 JWT 存进 contextvars 以便透传给下游
    startup_tasks=[run_relay],   # WS 通知中继常驻协程
)


@app.get("/mode")
async def mode():
    """运维小端点：一眼看出这个 chat 进程现在是本地模式还是远程模式。"""
    return {
        "service": "chat",
        "split_mode": SPLIT_MODE,
        "remote_nodes": SPLIT_MODE == "remote",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.chat.main:app", host="0.0.0.0", port=9124, reload=False)
```

> 要点：chat 是唯一打开三个开关的服务——`enable_quota`（管 /chat/stream 配额）、`capture_auth`（抓 JWT 透传给下游）、`startup_tasks=[run_relay]`（WS 通知中继常驻）。`/mode` 是运维小端点，一眼看出当前是 local 还是 remote。

---

## 8. 第 5 章 coordinator 的本地 / 远程切换

### 8.1 设计动机

拆微服务后，LangGraph 图里的 4 个节点要改走 HTTP。但图**形状**不该变、本地模式还得留（单测不开外部服务、压测对照）。实测方案是把"图的形状"和"节点怎么实现"解耦：

| 文件 | 职责 |
| --- | --- |
| `coordinator.py`（修改） | `build_workflow(nodes=None)`：不传 nodes = 本地函数直调（原行为）；传了 = 用传入的节点表注册图 |
| `coordinator.py` 里的 `_resolve_nodes()` | 读 `SPLIT_MODE`：remote 时返回 `services.chat.graph_remote.remote_nodes()` |
| `services/chat/graph_remote.py`（新增） | 4 个远程节点 + `remote_nodes()` 节点表（output 仍用本地实现） |

**没有 `coordinator_local.py`**——连边代码只有一份，不需要抽两份（勘误：旧手册的抽离方案作废）。

### 8.2 关键代码

coordinator 的修改（整段替换锚点见操作手册 §5.1）：

```python
def build_workflow(nodes=None):
    """
    组装并编译工作流。

    add_edge 的两种写法：
        add_edge("recognize", "nutrition")         一次只接一个下游 → 顺序执行
        add_edge(["nutrition", "recommend"], "rank") 多个起点汇聚到同一节点 → 等待全部完成再走

    v3阶段9 新增参数 nodes：
        传 None（默认）→ 用本地节点，行为和阶段 8 之前完全一致（单体模式）。
        传一张"节点名 → 函数"的表 → 用这张表注册节点（微服务模式下换成 HTTP 版节点）。
        这样"图的形状"和"节点怎么实现"就解耦了：拆不拆微服务，连边代码一行都不用改。
    """
    if nodes is None:
        nodes = {
            "recognize": recognize_node,
            "nutrition": nutrition_node,
            "recommend": recommend_node,
            "rank": rank_node,
            "output": output_node,
        }

    workflow = StateGraph(ChefState)

    # ① 注册节点（名字 → 函数）
    for name, fn in nodes.items():
        workflow.add_node(name, fn)

    # ② 连边（数据流向）
    workflow.add_edge(START, "recognize")
    workflow.add_edge("recognize", "nutrition")        # 识别 → 营养（并行分支 1）
    workflow.add_edge("recognize", "recommend")        # 识别 → 推荐（并行分支 2）
    workflow.add_edge(["nutrition", "recommend"], "rank")   # fan-in：两支都完成才重排
    workflow.add_edge("rank", "output")
    workflow.add_edge("output", END)

    return workflow.compile()


# 惰性单例：编译图有开销，但也不能在 import 时就编译（否则单测/无密钥环境会受影响）
_agent = None


def _resolve_nodes():
    """
    按环境变量 SPLIT_MODE 决定节点用本地版还是远程版（v3阶段9 新增）。

        SPLIT_MODE=local（默认）  → 全部节点在本进程内跑（单体行为，拆分前/对照组用）
        SPLIT_MODE=remote        → 识别/营养/推荐/重排改走 HTTP 调各自的服务

    为什么要做成环境变量而不是硬改代码：
    阶段 9 的验收项之一是"用阶段 7 的指标给出拆分前后对比"——
    同一个代码库，改一个环境变量就能在"单体"和"微服务"两种形态间切换，
    压测才有可比性（否则你得维护两套代码）。
    """
    import os
    if os.getenv("SPLIT_MODE", "local").strip().lower() == "remote":
        from services.chat.graph_remote import remote_nodes
        logger.info("coordinator: SPLIT_MODE=remote，识别/营养/推荐/重排改走 HTTP 调用")
        return remote_nodes()
    return None


def get_coordinator_agent():
    """取（必要时创建）编译后的工作流单例"""
    global _agent
    if _agent is None:
        logger.info("coordinator: 首次编译 StateGraph")
        _agent = build_workflow(nodes=_resolve_nodes())
    return _agent


def reset_coordinator_agent() -> None:
    """测试用：丢掉单例，下次重新编译"""
    global _agent
    _agent = None
```

远程节点表全文：

```python
# services/chat/graph_remote.py
"""
远程节点（remote nodes）—— 把"本地函数调用"换成"HTTP 调用别的服务"

一句话理解：
    单体时代，LangGraph 的 recognize 节点 = 直接 `await recognize_node(state)`（进程内函数调用）。
    拆成微服务后，同一个节点 = `await client.post("/internal/nodes/recognize", ...)`（跨进程 HTTP）。
    **图的形状一点没变**（还是 识别→营养/推荐→重排→输出），变的只是节点内部怎么干活。

🔴 本文件的灵魂：降级（degradation）
    每个远程节点都用 try/except 包住。远程服务挂了（连接失败 / 熔断跳闸 / 5xx），
    节点**不抛异常**，而是返回一个"空但合法"的结果 + 一条说明消息。
    为什么：
        LangGraph 里一个节点抛异常，整条工作流就崩了，用户看到 500。
        但"推荐服务挂了"其实不该让"营养估算"也一起完蛋——
        降级后用户拿到的是"营养报告完整、菜谱部分暂时不可用"，体验好得多，
        这正是"故障隔离"要的效果。
    这也就是验收项「杀掉单个服务，其余功能不受影响」的实现方式。
"""
from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import AIMessage

from app_my.agents.output import output_node
from app_my.agents.recognizer import message_content_to_text
from app_my.core.logging import logger
from app_my.core.tenant import current_tenant_id
from services.common.client import get_client


def _user_text(state: dict) -> str:
    """从 state 里取用户最后一句话的纯文本（支持多模态 content 是 list 的情况）。"""
    messages = state.get("messages") or []
    if not messages:
        return ""
    return message_content_to_text(messages[-1].content)


def _ai(content: str) -> List[AIMessage]:
    """包一条 AIMessage —— 图要求节点返回 messages，用来记录过程。"""
    return [AIMessage(content=content)]


# ------------------------------------------------------------------ ① 识别节点（远程）
async def recognize_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做食材识别。"""
    tenant_id = current_tenant_id.get()
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/recognize",
            {"text": _user_text(state), "image_url": state.get("image_url") or []},
            tenant_id=tenant_id,
        )
        return {
            "ingredients": data.get("ingredients") or [],
            "messages": _ai(data.get("summary") or "[识别] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recognize 失败，已降级：%s", exc)
        return {"ingredients": [], "messages": _ai(f"[识别] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ② 营养节点（远程）
async def nutrition_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做营养估算（营养和识别同域，都在 recognizer）。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"nutrition": {}, "messages": _ai("[营养] 无食材，跳过")}
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/nutrition",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "nutrition": data.get("nutrition") or {},
            "messages": _ai(data.get("summary") or "[营养] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.nutrition 失败，已降级：%s", exc)
        return {"nutrition": {}, "messages": _ai(f"[营养] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ③ 推荐节点（远程）
async def recommend_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）检索候选菜谱。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"recipes": [], "messages": _ai("[推荐] 无食材，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/recommend",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "recipes": data.get("recipes") or [],
            "messages": _ai(data.get("summary") or "[推荐] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recommend 失败，已降级：%s", exc)
        # 降级：没有菜谱，但工作流继续往下走（营养部分仍然完整）
        return {"recipes": [], "messages": _ai(f"[推荐] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ④ 重排节点（远程）
async def rank_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）做个性化重排。"""
    tenant_id = current_tenant_id.get()
    recipes = state.get("recipes") or []
    if not recipes:
        return {"ranked_recipes": [], "messages": _ai("[重排] 无候选菜谱，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/rank",
            {"recipes": recipes, "user_profile": state.get("user_profile") or {}},
            tenant_id=tenant_id,
        )
        return {
            "ranked_recipes": data.get("ranked_recipes") or [],
            "messages": _ai(data.get("summary") or "[重排] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.rank 失败，已降级：%s", exc)
        return {"ranked_recipes": [], "messages": _ai(f"[重排] 服务不可用，已跳过：{exc}")}


def remote_nodes() -> Dict[str, object]:
    """
    返回"远程版"的节点表。

    注意 output 仍然是**本地**的：
    它是纯文本拼装，不调外部资源，没有必要再跨一次网络（多一跳 = 多一个故障点）。
    这也体现了一条拆分原则：**不是所有东西都要拆，只拆有独立资源/故障特征的**。
    """
    return {
        "recognize": recognize_node_remote,
        "nutrition": nutrition_node_remote,
        "recommend": recommend_node_remote,
        "rank": rank_node_remote,
        "output": output_node,
    }
```

### 8.3 降级策略（故障隔离的实现方式）

每个远程节点都 `try/except` 包住：服务挂了**不抛异常**，返回"空但合法"的结果 + 一条说明消息。一个节点抛异常整条工作流就 500 了；降级后用户拿到"营养报告完整、菜谱部分暂不可用"。这就是操作手册 §14 实测"杀掉 recommender，chat 仍返回完整报告"的代码来源。

---

## 9. 第 6 章 22 个单元测试的设计思路

> 🔴 勘误：实测计数 **8 + 7 + 7 = 22 passed**（不是 27）。测试文件全文以操作手册 §6 为准（API 与旧版不同，别混用）。

### 9.1 test_circuit_breaker（8 用例）

纯内存状态机测试：CLOSED 不误跳 → 到阈值跳 OPEN → OPEN 抛 `CircuitOpenError` → 超时自动 HALF_OPEN → 试探成功合闸 / 试探失败重新跳闸 → snapshot 字段齐全 → 注册表单例。技巧：不真等 30 秒，直接 `_opened_at = time.time() - 999` 把时钟往前拨。

### 9.2 test_service_client（7 用例）

全部挂 `httpx.MockTransport`，离线验证：200 原样返回 → 503×2 后 200（重试救回，发了 3 次）→ 一直 503（抛 `ServiceCallError` 且**一次 post 只记 1 次熔断失败**，跳闸后第 2 次调用 0 次请求）→ 4xx 不重试不记失败 → trace/tenant/auth 三头透传 → `auth_token` 缺省时从 contextvars 自动取 → 连接错误也跳闸。

### 9.3 test_service_apps（7 用例）

**装配结构断言**（不发请求）：四服务都能构建且有 `/health` → 路由归属符合拆分表（`/kg` 在 recommender、`/oss` 在 recognizer…）→ 🔴 `test_metrics_outside_auth`：实测确认 `user_middleware` **外层在前**，所以断言 `Metrics.index < Auth.index` → `test_cors_outermost`：CORS 必须在索引 0 → `test_middleware_order_reads_correctly`：把 chat 整个洋葱顺序钉死成 10 项清单 → `/health` 返回体带 service+breakers → chat 独享 quota/token-capture 两个开关。

> 为什么用测试钉顺序：中间件顺序坏了是"静默失效"——接口全正常，只有 Grafana 空了。只有直接断言装配结构才防得住。

---

## 10. 第 7 章 Kong 声明式配置 `kong.yml`

> 🔴 勘误（2026-10-19）：以实测版为准。全文见操作手册 §7.2，这里讲结构。

### 10.1 services 段（4 个，路由内嵌）

实测版把 route **写在 service 里面**（而不是顶层 routes 段引用 service）——两种写法 Kong 都认，内嵌更紧凑：

| service | 上游 | routes | 限流 |
| --- | --- | --- | --- |
| svc-user | host.docker.internal:9121 | `/auth /users /tenants /admin /billing /cache` | 600/min |
| svc-recognizer | host.docker.internal:9122 | `/oss`（⚠️ `/internal/nodes/*` 故意不暴露到网关） | 300/min |
| svc-recommender | host.docker.internal:9123 | `/kg` | 300/min |
| svc-chat | host.docker.internal:9124 | `/chat /tasks` + `/ws`（WS 单独一条 route） | 120/min |

### 10.2 plugins 段（全局只有一个）

实测版全局插件只有 **correlation-id**：`header_name: X-Trace-Id`（不是 X-Kong-Trace-Id）+ `echo_downstream: true`。后端 `TraceIdMiddleware` 会**沿用**这个 ID，于是 Kong / user / chat / recognizer 四段日志能用同一个 ID 串起来。CORS 由各服务自己的 CORSMiddleware 管（不重复配）；限流按服务挂（见上表）。

### 10.3 三个最容易写错的地方

1. `strip_path: false`——四个服务自己带前缀，Kong 再吃掉前缀就 404；
2. `host.docker.internal`——写 127.0.0.1 会连到 Kong 容器自己，表现为 502；
3. **不要写 `protocols: ["websocket"]`**——Kong 3.x 已移除该值，整个配置解析直接失败；WS 就是普通 http + Upgrade 头自动升级。

---

## 11. 第 8 章 docker-compose 加 Kong service

```yaml
  kong:
    image: docker.1panel.live/library/kong:3.7          # 国内镜像源（Docker Hub 直连易 EOF）
    container_name: ai_chief_kong
    restart: unless-stopped
    environment:
      KONG_DATABASE: "off"                              # 🔴 DB-less 开关，少了它会去找 Postgres
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      KONG_PROXY_LISTEN: 0.0.0.0:8000                   # 容器内听 8000（Kong 默认端口）
      KONG_ADMIN_LISTEN: 0.0.0.0:8001                   # Admin API 默认只听 127.0.0.1，改成 0.0.0.0 才能宿主机访问
      KONG_PROXY_ACCESS_LOG: /dev/stdout                # 日志进 stdout，阶段 7 的 Promtail 直接复用
      KONG_ADMIN_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_ERROR_LOG: /dev/stderr
      KONG_NGINX_WORKER_PROCESSES: "1"                  # 单机开发 1 个 worker 足够（默认按核数起，费内存）
    ports:
      - "9100:8000"   # 宿主 9100 → 容器 8000：统一入口
      - "9105:8001"   # 宿主 9105 → 容器 8001：Admin API（DB-less 下只读，查路由表用）
    volumes:
      - ./kong/kong.yml:/etc/kong/kong.yml:ro           # 🔴 挂单个文件；必须"先写文件再起容器"
    extra_hosts:
      - "host.docker.internal:host-gateway"             # 让 Kong 容器内能解析到宿主机上的四个服务
```

> 勘误（2026-10-19）：实测版没有 healthcheck 段——`kong health` 在 DB-less 下意义不大，用 Admin API（9105）探活代替。

### `host.docker.internal` 这块 Docker Desktop 的细节

| OS | 是否默认支持 | 怎么打开 |
| --- | --- | --- |
| macOS（Intel/M1） | ✅ 默认支持 | — |
| Windows Docker Desktop | ✅ 默认支持 | — |
| Linux Docker CE | ❌ 默认不支持 | 加 `--add-host=host.docker.internal:host-gateway` |

Compose 里等价写 `extra_hosts: ["host.docker.internal:host-gateway"]`。

---

## 12. 第 9 章 起服务 + 中间件顺序

> 服务启动的流水线：uvicorn 进程 → import app → 中间件栈构建 → lifespan 进入 → 路由注册 → 监听端口。

### 12.1 中间件顺序与"洋葱"

```
请求 →  CORS            （最外层：所有响应都带跨域头，429 也不例外）
     →  TraceId         （创建或继承 X-Trace-Id）
     →  Metrics         （所有响应记指标；/metrics 端点在这里暴露）
     →  Auth            （JWT 校验，写 user_id 进 state）
     →  TenantContext   （解析租户写 state）
     →  TenantVar       （🆕 把租户写进 contextvars，供检索工具读）
     →  UserRateLimit   （用户级限流）
     →  RateLimit       （IP 级限流）
     →  Quota           （仅 chat：租户配额）
     →  TokenCapture    （仅 chat：把 JWT 存进 contextvars 供跨服务透传）
     →  路由处理函数 → 响应原路返回（内 → 外）
```

> **记住（实测确认，别凭印象）**：`add_middleware()` 是 `user_middleware.insert(0, ...)`——
> **列表"外层在前"**，所以**后调用**的 add 是**最外层**。代码里是"倒着写"的：
> TokenCapture 最先 add（最里层），CORS 最后 add（最外层）。§9.3 的 `test_middleware_order_reads_correctly` 把这个 10 层顺序钉死了。

### 12.2 Prometheus /metrics 为什么不被 401 挡？

因为 Metrics 挂在 Auth 的**外层**（工厂里 `add_middleware(MetricsMiddleware)` 写在 `add_middleware(AuthMiddleware)` 之后）：

```
请求 GET /metrics →
  CORS → TraceId → Metrics（✅ 在这里就被接住，根本走不到 Auth）
       → /metrics 端点返回 Prometheus 文本，200
```

双保险：AuthMiddleware 自身的白名单里也有 `/metrics`，就算顺序将来被人改坏，Auth 也不会拦它。但**顺序断言测试（§9.3）才是第一道防线**——别依赖白名单兜底。

---

## 13. 第 14-16 章 故障隔离与熔断原理

### 13.1 完整状态机

```
                  累计失败 >= threshold
       closed ───────────────────────────► open
         ▲                                  │
         │                                  │ 超过 recovery_timeout
         │  next request 试探成功             ▼
         └──────────────────────────── half_open ── 试探失败 ──► open
```

- **closed** —— 正常。failures 累计，达阈值跳闸。
- **open** —— 闸门开，所有请求 fast-fail（503），不再发。
- **half_open** —— 放一次试探；成功 → closed，失败 → 重新 open 计时。

### 13.2 重试 vs 熔断：互不替代的关系

| 角色 | 重试 | 熔断 |
| --- | --- | --- |
| 目标 | 应付**临时抖动**（网络 1s 内恢复） | 应付**持续故障**（下游宕机 1h） |
| 实现 | for attempt in range(retries+1) | breaker.before_call() |
| 影响 | 每次调用多耗 0.2s/0.4s/0.8s 时间 | 跳闸后调用 **0 秒** 返回 |
| 关联 | 失败时 **同时** 记 breaker | — |

> **常见错误**：只做重试不做熔断。后果是下游宕机时，5000 RPS 的请求会把每请求的 retries（×2 次）全打过去，重试风暴打死整个系统。

---

## 14. 第 17-18 章 Prometheus 抓取 + 对比基线

### 14.1 Prometheus scrape_config 加 target

```yaml
  - job_name: "ms-user"
    static_configs:
      - targets: ["host.docker.internal:9121"]
        labels:
          service: "user"
          stage: "9"
```

- `job_name` 是 Prometheus 内部的"作业名"
- `targets` 是它每 15s 去访问的 `<ip>:<port>/metrics`
- `labels` 是给所有该 job 拉回的指标贴的元数据，方便 Grafana 按 `service=chat` 过滤

### 14.2 对比基线怎么跑有说服力？

| 维度 | 单体（保留对照组） | 4 服务 + Kong |
| --- | --- | --- |
| **平均 /chat/stream 耗时** | 19.8s | 19.8s |
| **P99** | 24.0s | 26.0s |
| **+ 内网 HTTP 开销** | — | +2s |
| **故障隔离** | kill -9 整个 9002 | kill -9 仅 recommender → 降级 |
| **横向扩展** | 顶满 1 进程 | 每服务独立 N× |
| **Prometheus target** | 1 个 | 4 个，可画 `service=chat` 的单独曲线 |

**叙事要写**："耗时几乎没退化（+2s，约 10%），换来（故障隔离 / 独立扩缩 / 独立观测）三件用户侧的硬性收益。"——这是面试里最有冲击力的对比。

---

## 15. 第 21 章 PR 描述的写作思路

PR 描述不是报告，是**给读者"5 分钟看完你说服了你"**的机会。结构建议：

### 15.1 标准骨架

```markdown
## 阶段 N：标题（一行总结最大价值）

### 🎯 目标
- 3-5 条具体目标，每条动词开头：拆 4 服务 / 接 Kong / 实现熔断

### 📦 改动清单
- **新增** ……
- **改动** ……
- **删除** ……（应当尽量少）

### ✅ 测试
- 命令 + 期望结果

### 🚀 端到端实测
- 表格：场景 × 结果

### 📈 关键数字
- 至少 2 个对比数字

### ⚠️ 注意事项
- 写不为人知的坑 / 决策记录
```

### 15.2 容易踩的坑

1. **写"代码风格改进"**——不算里程碑，包含的话 PR 审稿会问"那为什么是这阶段"。改了不该改的就打回。
2. **改动清单不分类**——"5 个文件"不如"新增 4 / 改动 3 / 删除 0"清晰。
3. **测试只写 `pytest passed`** 不写命令——别人在你机器上跑不起来。
4. **端到端实测写 `通过了`**——表格化，**每个场景**一行。
5. **不写"未来作业"**——把下一阶段要做的列出来，让团队知道"这是路线图下一站"。

---

## 写到这里就齐活

说明手册讲完**所有 6 大件事**的底层原理：

1. **共享内核**（`services/common/`）——4 文件的协作
2. **服务入口**（`services/{user,recognizer,recommender,chat}/main.py`）——路由按业务切分
3. **coordinator 重构**（`coordinator.py` 加节点表参数 + `services/chat/graph_remote.py`）——按 SPLIT_MODE 切图
4. **22 个单元测试**（`tests/unit/test_*.py`，8+7+7）——MockTransport 不真发请求
5. **Kong 配置 + Compose + Prometheus**——网关与抓取
6. **故障隔离 / 熔断 / 对比基线**——可量化的成果

剩下操作手册里没有的细节：**让代码跑起来后，再读本节一次**，会发现每个"为什么这么写"在你的机器上**就是这样落地**的。