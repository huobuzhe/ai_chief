# AI 私厨 v3.0 · 阶段 10 问题与解决记录

> **阶段**：10 / 10 —— Locust 性能压测 + Gitee Go CI/CD + 生产级部署
> **分支 / 收官日期**：`feat/v3-stage10` / 2026-10-21
> **本阶段产出**：打桩器（MOCK_LLM + 假 embedding）、压测脚本三件套、生产镜像与编排、CI 流水线与本地等价脚本、验收脚本、2 个新测试文件、三份手册
> **共记录问题 16 个**，其中 **手册自身缺陷 7 个**、代码/脚本缺陷 2 个、配置缺陷 4 个、环境类 2 个、收官遗留 3 个（有交叉）

---

## 目录

- [一、一分钟结论](#一一分钟结论)
- [二、背景](#二背景)
- [三、问题总览](#三问题总览)
- [四、问题详情](#四问题详情)
  - [问题 1：§7.5 单测必报 ModuleNotFoundError](#问题-175-单测必报-modulenotfounderror)
  - [问题 2：run_bench.ps1 报「意外的标记 }」等 3 条语法错](#问题-2run_benchps1-报意外的标记-等-3-条语法错)
  - [问题 3：CI 本地验证第 2 步必 FAIL（importlib.util）](#问题-3ci-本地验证第-2-步必-failimportlibutil)
  - [问题 4：生产容器无限重启（缺 prometheus_client）](#问题-4生产容器无限重启缺-prometheus_client)
  - [问题 5：加了依赖重启容器仍报同样的错（镜像没重建 + 缺 image 标签）](#问题-5加了依赖重启容器仍报同样的错镜像没重建--缺-image-标签)
  - [问题 6：Kong 端口在监听但请求全超时（worker OOM）](#问题-6kong-端口在监听但请求全超时worker-oom)
  - [问题 7：容器全 healthy 但接口全 500（localhost 视角错）](#问题-7容器全-healthy-但接口全-500localhost-视角错)
  - [问题 8：环境变量覆盖没生效（YAML 锚点浅合并）](#问题-8环境变量覆盖没生效yaml-锚点浅合并)
  - [问题 9：手册 §15.3 网关路径写错（/api/v1 前缀）](#问题-9手册-153-网关路径写错apiv1-前缀)
  - [问题 10：修好 Neo4j 后 /kg/ask 仍返回旧的失败](#问题-10修好-neo4j-后-kgask-仍返回旧的失败)
  - [问题 11：§17.3 验证报「未认证 / Token 已过期」+ body 解析失败](#问题-11173-验证报未认证--token-已过期-body-解析失败)
  - [问题 12：§13.4 限流验证永远测不出 429（虚构路径）](#问题-12134-限流验证永远测不出-429虚构路径)
  - [问题 13：手册里 5 处数字是编的，不是实测的](#问题-13手册里-5-处数字是编的不是实测的)
  - [问题 14：压测留下 549 个垃圾账号，手册初版没这一步](#问题-14压测留下-549-个垃圾账号手册初版没这一步)
  - [问题 15：三份手册从未入库（.gitignore 的 *.md + NUL 字节）](#问题-15三份手册从未入库gitignore-的-md--nul-字节)
  - [问题 16：备份文件 kong.yml.bak 被提交进仓库](#问题-16备份文件-kongymlbak-被提交进仓库)
- [五、修改清单总表](#五修改清单总表)
- [六、经验教训](#六经验教训)

---

## 一、一分钟结论

1. **这一阶段 16 个问题里，7 个是我写手册写错的**——不是你操作错。最典型的是"路径虚构"（`/api/v1/xxx`）和"数字编造"（把设计值当实测值写进预期输出）。修法已经固化成一条铁律：**手册里写的每个 URL/函数名/数字，落笔前必须 grep 源码或实跑取原文**。
2. **"容器 Up ≠ 能用，语法 OK ≠ 能跑"是两条独立的高频坑**。前者表现为 `docker ps` 全绿但接口全 500（本阶段连中两次：缺依赖、localhost 视角错）；后者表现为脚本静态语法 0 错误、一跑就 `AttributeError`（`importlib.util` 那次）。判定必须看**运行时证据**：`docker ps` 的 STATUS 有没有 `Restarting`、`docker logs` 的 traceback、真实跑一遍命令。
3. **收官最容易被静默吞掉的是文档**：`.gitignore` 里一行 `*.md` 让三份手册从未入库，而 `git status` 因为忽略规则**看起来是干净的**。"工作区干净"不等于"提交完整"。

---

## 二、背景

阶段 10 要做三件事：① 用 Locust 压测，把阶段 9 的微服务拆分从"架构上更好"变成"有数据支撑"；② 补生产级部署（gunicorn + 非 root + 资源上限）；③ 建 CI/CD。

这类问题高发的原因：**本阶段第一次把"应用"从宿主机进程搬进容器**，而容器的网络视角、依赖来源、进程模型全和宿主机不同——宿主机上验证过的所有假设（localhost 能连库、依赖都装过、单进程能起）在容器里全部失效，且失效方式都是"构建/启动成功、运行时才炸"。

本次用到的排查手段（后面反复出现）：
- `docker ps` 看 STATUS 里的 `Restarting (n)`，`docker logs --tail N` 抓 traceback
- `docker exec <容器> printenv 变量名` —— 查容器**实际**生效的环境变量（不看配置文件怎么写）
- `docker exec <容器> bash -c 'exec 3<>/dev/tcp/host/端口'` —— 从容器内直连上游，区分"网络不通"还是"应用不处理"
- `[System.Management.Automation.Language.Parser]::ParseFile` —— 拿 PowerShell 语法错误的**行号**
- Python 按 GBK/ANSI 解码 `.ps1`，对比引擎"眼中"的文本 —— 定位编码类玄学错误

---

## 三、问题总览

| # | 问题 | 类型 | 严重度 | 根因一句话 | 状态 |
|---|---|---|---|---|---|
| 1 | §7.5 跑单测报 `No module named 'scripts.locust_report'` | 手册缺陷 | 高 | 手册让在第七节跑全量单测，但依赖文件第九节才创建 | ✅ 已勘误 |
| 2 | `run_bench.ps1` 报"意外的标记 }"等 3 条语法错 | 环境 + 手册缺陷 | 高 | 文件存成无 BOM 的 UTF-8，PS 5.1 按 GBK 解码，奇数中文字节吞掉收尾引号 | ✅ 已解决 |
| 3 | `ci_local.sh/.ps1` 第 2 步 `AttributeError: importlib has no attribute 'util'` | 脚本缺陷 | 中 | `import importlib` 却用 `importlib.util.find_spec` | ✅ 已修 |
| 4 | 生产容器 `Restarting`，日志 `No module named 'prometheus_client'` | 配置缺陷 | 高 | 运行时依赖没写进 requirements.txt，只在开发 venv 里装过 | ✅ 已修 |
| 5 | 加了依赖、重启容器仍报同样错 | 配置缺陷 | 中 | 只 `up -d` 没重 build；且 compose 缺 `image:` 标签，用的是自建旧镜像 | ✅ 已修 |
| 6 | Kong 端口监听但请求全超时 | 配置缺陷 | 高 | 默认每核 1 worker（13 个），512m 被 OOM（`exited on signal 9`） | ✅ 已修 |
| 7 | 容器全 healthy 但接口全 500 | 配置缺陷 | 高 | `.env` 的 localhost 是宿主机视角，容器里 localhost 指它自己 | ✅ 已修 |
| 8 | 环境变量覆盖没生效 | 配置缺陷 | 中 | YAML 锚点是浅合并，各服务自己的 `environment:` 覆盖了锚点里的 | ✅ 已修 |
| 9 | 手册 §15.3 网关路径 `/api/v1/auth/login` 是错的 | 手册缺陷 | 中 | Kong 路由是 `/auth`（strip_path:false），服务也没 `/api/v1` 前缀 | ✅ 已勘误 |
| 10 | 修好 Neo4j 后 `/kg/ask` 仍返回旧的失败 | 环境 | 低 | 图谱问答有 600 秒 Redis 缓存，旧失败结果还在缓存里 | ✅ 已验证 |
| 11 | §17.3 验证报"未认证 / Token 已过期" + body 解析失败 | 手册缺陷 | 高 | ① 路径同样多了 `/api/v1`；② curl 内联中文 body 被 GBK 转码 | ✅ 已勘误 |
| 12 | §13.4 限流验证永远看不到 429 | 手册缺陷 | 中 | 打的是虚构路径 `/api/v1/health`，请求不经过限流插件 | ✅ 已勘误 |
| 13 | 手册 5 处数字是设计值不是实测值 | 手册缺陷 | 中 | 写手册时凭印象填数，没实跑 | ✅ 已改成实测原文 |
| 14 | 压测留下 549 个 `bench_` 垃圾账号 | 手册缺陷（遗漏） | 中 | 手册初版没有"清理压测账号"这一步 | ✅ 已补 §17.4 |
| 15 | 三份手册从未入库 | 收官遗留 | 高 | `.gitignore:10` 的 `*.md` + 第 52~54 行 NUL 字节损坏 | 🟡 待用户执行 |
| 16 | `docker/kong/kong.yml.bak` 备份文件进了提交 | 收官遗留 | 低 | 备份后未删除、未加忽略 | 🟡 待用户执行 |

---

## 四、问题详情

### 问题 1：§7.5 单测必报 ModuleNotFoundError

**现象**（用户实测原文）：

```
ModuleNotFoundError: No module named 'scripts.locust_report'
1 error during collection
```

**定位**：`tests/unit/test_stage10_bench_report.py` 要 `import scripts.locust_report`，而 `scripts/locust_report.py` 按手册要到**第九节**才创建。用户做到第七节跑全量单测，必然报错。

**解决**：§7.5 的命令加 `--ignore=tests/unit/test_stage10_bench_report.py`，预期从 141 改为 **132 passed**（124 旧 + 8 打桩）；在 §9 收尾处补一步"落盘 `locust_report.py` 后去掉 `--ignore` 重跑 = 141 passed"；§20 自检清单同步。

**验证**（项目内实测）：

```
132 passed, 3 warnings in 12.08s
```

**预防**：**分步手册的每个中间检查点，必须按"这一步能看到哪些文件"计算预期值**，不能拿全集跑出来的数字当中间值。

---

### 问题 2：run_bench.ps1 报「意外的标记 }」等 3 条语法错

**现象**：

```
表达式或语句中包含意外的标记"}"
数组索引表达式丢失或无效
语句块或类型定义中缺少右"}"
```

**定位**：拿 `[Parser]::ParseFile` 拿到行号后，把引擎"眼中"的文本 dump 出来，第 79 行变成：

```
Write-Host "[璀﹀憡] Redis...棰濇竻闄? -ForegroundColor Yellow
```

字符串**收尾引号被吃掉**。完整机制：
1. `.ps1` 存成 UTF-8 **无 BOM**；
2. PowerShell 5.1 读无 BOM 脚本按系统 ANSI（CP936/GBK）解码；
3. 中文"配额清理失败，跳过配额清除"13 字 = 39 字节（**奇数**），GBK 两两配对后**落单的最后一字节把后面的 `"` 吞了**（Windows 解码器与 Python 不同：Python 会回退重同步保留引号，Windows 连引号一起吞）；
4. 引号没收口 → 字符串跨行继续吞后面的 `}` 和 `catch` → 三条连锁错误。

**解决**：给文件加 UTF-8 BOM（3 字节头，内容不动）。两个文件（`run_bench.ps1`、`ci_local.ps1`）加 BOM 后 ParseFile 均 **0 错误**。

**验证**：自查命令 `Get-Content -Encoding Byte -TotalCount 3` 应返回 `239,187,191`。

**预防**：**含中文的 `.ps1` 一律存成 UTF-8 with BOM**；手册里给出 VS Code「通过编码保存」和一条 PowerShell 写回命令两种修法。

---

### 问题 3：CI 本地验证第 2 步必 FAIL（importlib.util）

**现象**（实跑原文）：

```
[FAIL] 检查关键依赖
AttributeError: module 'importlib' has no attribute 'util'
```

**定位**：`ci_local.sh` / `ci_local.ps1` 里写的是 `import importlib, sys`，但下面用了 `importlib.util.find_spec(...)`。`importlib.util` 是子模块，必须显式导入。

**解决**：改成 `import importlib.util, sys`（两份脚本都改）。

**验证**：重跑 `bash scripts/ci_local.sh` → **6 步全部 PASS**：

```
[PASS] Python 版本 / 检查关键依赖 / 跑单元测试 / 校验生产编排 / 校验压测脚本语法 / 冒烟导入
全部通过 ✅ —— 流水线的命令在本机都跑得通，可以 push 了
```

**预防**：**静态语法验证 ≠ 实跑**。这两个脚本当初只做了语法检查就写"预期全 PASS"，用户一跑就红。凡手册里写"预期输出"的命令，必须真跑一次抄原文。

---

### 问题 4：生产容器无限重启（缺 prometheus_client）

**现象**：`docker ps` 里 5 个容器都 `Up`，但 recognizer/user 的 STATUS 是 `Restarting (3)`，9100/9123/9124 全部 `000`。日志：

```
ModuleNotFoundError: No module named 'prometheus_client'
[ERROR] Reason: Worker failed to boot.
```

**定位**：`prometheus_client` 是**运行时依赖**（`app_my/middleware/metrics.py` 直接 import），但没写进 `requirements.txt`——只在 `.venv3` 里装过（阶段 7 装的）。所以 `docker build` 成功、容器启动即崩。

**解决**：`docker/requirements.prod.txt` 加 `prometheus-client==0.26.0`（版本与开发 venv 一致），**重新 build 镜像**。

**验证**：`docker run --rm ai-chief-svc:prod python -c "import prometheus_client"` → `镜像里有 prometheus_client`。

**预防**：**"本机 import 成功"不等于"镜像里有"**。判据：新增运行时依赖后，`docker run --rm <镜像> python -c "import <包>"` 验一次。

---

### 问题 5：加了依赖重启容器仍报同样的错（镜像没重建 + 缺 image 标签）

**现象**：新镜像里已有 `prometheus_client`（docker run 验证通过），但容器日志还是同一个 `ModuleNotFoundError`。

**定位**：对比镜像 ID 发现——compose 里 4 个服务只写了 `build:` **没有 `image:` 标签**，所以 `up -d` 用的是 compose 自己现场构建的旧镜像（`ai_chief_prod-svc-user`，构建时还没有新依赖）；手工 `docker build -t ai-chief-svc:prod` 出来的镜像**根本没被用上**。

**解决**：`x-svc-common` 加一行 `image: ai-chief-svc:prod`，让 compose 用构建好的镜像；然后 `up -d`（这次输出 `Recreated` 才算数）。

**验证**：4 个容器 `Recreated` → 全部 `Up (healthy)`，9121~9124 全 200。

**预防**：① 改了 `requirements*.txt` 必须**重新 build**，光 `up -d` 没用；② compose 里同时写 `build:` 和 `image:`，否则"我 build 了"和"容器在用的"是两个东西。

---

### 问题 6：Kong 端口在监听但请求全超时（worker OOM）

**现象**：4 个应用服务全 healthy，但 Kong 变 unhealthy、9100 不通；`docker exec kong kong health` 却说 healthy。TCP 能连上，curl 一直挂着不回包。

**定位**：过滤噪音日志（broker.lua / worker.lua / SIGIO）后看到：

```
worker process ... exited on signal 9
```

Kong 默认**每核起 1 个 worker**（本机 13 核 = 13 个），`mem_limit: 512m` 被撑爆，worker 被 OOM kill——所以端口在监听但没人处理请求。

**解决**：`KONG_NGINX_WORKER_PROCESSES: "2"`。

**验证**：`--force-recreate kong` 后 5 个容器全 `(healthy)`，9100 有响应。

**预防**：**容器内存上限要和"进程数 × 单进程占用"一起算**。Kong 这类默认按核数起 worker 的组件，进容器前先把 worker 数固定。

---

### 问题 7：容器全 healthy 但接口全 500（localhost 视角错）

**现象**：5 个容器全 `Up (healthy)`，但走 Kong 打 `/auth/login` 稳定 500；直连 9121 也是 500；而 `/kg` 路由却正常。逐个加请求头测试，发现**任何附加头都触发 500**。

**定位**：抓 svc-user 的 Python traceback：

```
connection to server at "localhost", port 9432 failed: Connection refused
```

`.env` 里的 `DATABASE_URL=...localhost:9432` 是**宿主机进程**视角；容器里 localhost 指容器自己，连不上宿主机端口上的 PgBouncer。同理还有 Redis(6380)、Milvus(19530)、Loki(3100)、Neo4j(7687，`.env` 里根本没写、走 config 默认值)。

**解决**：新建 `docker/env.prod-override`，把这些连接串改成 `host.docker.internal`，通过 `env_file` 列表第二位覆盖。

**验证**：`docker exec ai_chief_prod_user printenv DATABASE_URL` → `...host.docker.internal:9432...`；重建后登录返回 401、token 299 字符。

**预防**：**容器里 `localhost` 永远指容器自己**；连宿主机服务一律用 `host.docker.internal`（compose 里配 `extra_hosts: host.docker.internal:host-gateway`）。且 **healthcheck 只探自己，healthy 不代表依赖通**——必须补一次真实业务请求。

---

### 问题 8：环境变量覆盖没生效（YAML 锚点浅合并）

**现象**：按上一题把覆盖写进 `x-svc-common` 的 `environment:` 段，重建容器后 `printenv` 显示的还是 `localhost`。

**定位**：compose 的 YAML 锚点合并是**浅合并**——每个服务自己那段 `environment:`（WEB_PORT / APP_MODULE / WEB_WORKERS）把锚点里的整个 `environment:` 段替换掉了。

**解决**：改用 `env_file` 列表（后面的文件覆盖前面的同名变量）：

```yaml
env_file:
  - ../.env                 # 先加载全量（宿主机视角）
  - ./env.prod-override     # 再用容器视角覆盖
```

**验证**：`docker exec ai_chief_prod_user printenv DATABASE_URL` → host.docker.internal 生效。

**预防**：**YAML 锚点合并是浅的**——子级同名字段会整体替换，不是逐键合并。要"部分覆盖"就用 `env_file` 列表，别用锚点里的 `environment:`。

---

### 问题 9：手册 §15.3 网关路径写错（/api/v1 前缀）

**现象**：走 Kong 打 `/api/v1/auth/login` 返回 404，直连 svc-user 同样路径返回 401（我当时误判成"凭据错误正确返回"）。

**定位**：`grep docker/kong/kong.yml` 的 routes → 真实路径是 `/auth`、`/chat`、`/kg`（`strip_path: false`，服务自带前缀）。`/api/v1` 是我凭印象编的。

**解决**：手册两处 URL 改成 `/auth/login`。

**验证**：走 Kong `/auth/login` 带正确凭据 → 200 + token。

**预防**：**写"调用某接口"的步骤前，必须 grep 路由定义确认真实路径**（这条铁律阶段 6 就定过，本阶段又犯）。

---

### 问题 10：修好 Neo4j 后 /kg/ask 仍返回旧的失败

**现象**：NEO4J_URI 已改成 `host.docker.internal`，容器环境变量也对，但 `/kg/ask` 仍返回"图谱不可用"。

**定位**：图谱问答挂了阶段 5 的 `cached(ttl=600)`——**600 秒 Redis 缓存**里存的是之前失败的结果。

**解决**：换一个 `ingredient` 参数（绕开缓存键）验证。

**验证**：换参数后返回真实图谱推理：`"GI值较高，升血糖快，建议控制份量"`。

**预防**：**"改了配置却看不到变化"先怀疑缓存**。排错时养成"换参数/清缓存再验一次"的习惯。

---

### 问题 11：§17.3 验证报「未认证 / Token 已过期」+ body 解析失败

**现象**（用户截图）：

```
{"detail":"Token 已过期，请重新登录"}
TOKEN 为空 → {"detail":"未认证，请携带 Authorization: Bearer <access_token>"}
```

**定位**：两个原因叠加。
① 手册写了 `/api/v1/auth/...`，但 `main.py` 挂载就是 `/auth`、`/chat`、`/kg`（**没有 `/api/v1` 前缀**）；鉴权中间件 `PUBLIC_PREFIXES = ("/auth/",)` 匹配不到 → 401。拿旧 token 打过一次就看到"Token 已过期"。
② 路径改对后 `/chat/stream` 报 `{"detail":"There was an error parsing the body"}`——Windows 的 `curl.exe` 处理命令行参数按本地编码（GBK）转码，**内联中文 body 必乱码**。实测对照：内联失败、`-d @UTF8文件` 成功、Python urllib 成功。

**解决**：§17.3 整节重写——正确路径 + 中文 body 写临时文件用 `-d @文件` + PowerShell 用 `[System.Text.Encoding]::UTF8.GetBytes($body)`（PS 5.1 传字符串按 ISO-8859-1 发）。

**验证**（项目内实测）：

```
① {"id":667,"username":"stage10check11","email":null}
② token长度: 299
③ ## 食材清单 / **鸡蛋**：新鲜度良好 (8/10)   ← 真实 LLM 输出
```

**预防**：① **同一概念出现多处，勘误时必须全局 grep**（这次是修 §15.3 时没搜 §17.3，漏了一处，用户多跑一趟）；② **手册里凡"手工 curl 带中文 body"的步骤，一律用 `-d @文件` 或 Python 脚本，禁止内联中文**。

---

### 问题 12：§13.4 限流验证永远测不出 429（虚构路径）

**现象**：手册让连打 20 次 `http://127.0.0.1:9100/api/v1/health`，写"预期 200 或 404，关键是看不到 429"。

**定位**：Kong 里**没有 `/api/v1/health` 这条路由**，请求直接 404——**根本不经过任何服务和限流插件**，所以无论限流值调没调，都不可能返回 429，这个检查等于没测。

**解决**：改成打真实路由 `POST /auth/login` 20 次。

**验证**（限流恢复 600/min 后实测）：

```
401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401
```

**预防**：**验证步骤选的端点，必须真的会经过你要验证的那个环节**。写"用 X 验证限流"前先确认 X 会走限流插件。

---

### 问题 13：手册里 5 处数字是编的，不是实测的

**现象**：写手册时凭印象填了预期输出，用户跑出来对不上。

**定位**：自查发现 5 处——① §14.1 试水压测的整张表；② embedding 前 3 个分量；③ 跨进程稳定性数值；④ `docker compose config --services` 的服务顺序（写成字母序，实际是声明顺序）；⑤ §17.4 空目录清理"删 3 个"（实跑只删 2 个，第 3 个里有试水轮 CSV 不算空）。

**解决**：逐条实跑，把原文抄进手册。例如试水压测实测原文：

```
BENCH SUMMARY  target=:9002  peak_users=5  total=54  failures=0
/auth/login 15 /chat/stream 7 /kg/ask 22 ... TOTAL 54
```

**验证**：全部改成实测值后，用户按手册跑能对上。

**预防**：**数字型期望（行数/通过数/HTTP 码/端口数）一律取实跑原文，禁止"设计叙事"**。

---

### 问题 14：压测留下 549 个垃圾账号，手册初版没这一步

**现象**：跑完 8 轮压测后查库——**579 个用户里 549 个是 `bench_<随机串>`**（Locust 每个虚拟用户 `on_start` 注册一个）。

**定位**：手册 §17 初版只有"恢复限流 / 重启服务 / 确认恢复"三步，**没有清理压测账号**这一步。

**解决**：新增 §17.4，给出"先查后删"的双终端命令 + 清理空报告目录命令。

**验证**（实跑）：

```
已删除行数: 549 / 剩余用户总数: 30 / 剩余 bench_ 用户: 0
```

**预防**：**凡是"压测/造数据"的步骤，收尾章节必须配一条对应的清理步骤**，且清理命令要"先 SELECT 看数量、再 DELETE"。

---

### 问题 15：三份手册从未入库（.gitignore 的 *.md + NUL 字节）

**现象**（收官核实发现）：`git status --porcelain` 干净，但 `git show --name-only HEAD` 只有 57 个文件，没有一份 md；`git log --diff-filter=A --name-only | grep "\.md$"` 只返回 `README.md`——**整个仓库历史只提交过一个 md**。

**定位**：
1. `.gitignore:10` 有 `*.md`，忽略所有 Markdown → 手册被静默忽略，`git status` 不显示；
2. `.gitignore` 第 52~54 行含 **NUL 字节**（`'~\x00\\\x00$\x00*\x00'`），git 把文件当二进制：`git show --stat HEAD -- .gitignore` → `Bin 527 -> 649 bytes, 0 insertions(+), 0 deletions(-)`。是 PowerShell 追加内容留下的 UTF-16LE 残迹。

**解决**（已写进最终完整版第一、二章，待用户执行）：
- `git add -f` 强制补交 4 个 md（三份手册 + 压测报告）
- 把 `*.md` 改成 `tmp/*.md`，并用 UTF-8（无 BOM）重写 `.gitignore` 清掉 NUL

**验证命令**：`git check-ignore -v <手册路径>` 应无输出；`git diff --stat -- .gitignore` 不再显示 `Bin`。

**预防**：**收官时必须用 `git show --name-only HEAD` 对照 `git status`，而不是只看 `git status`**；改 `.gitignore`/`.env`/yml 一律用 Git Bash 的 `cat > f <<'EOF'` 或 PowerShell 的 `[System.IO.File]::WriteAllLines(..., UTF8Encoding($false))`。

---

### 问题 16：备份文件 kong.yml.bak 被提交进仓库

**现象**：`git show --name-only HEAD` 里有 `docker/kong/kong.yml.bak`。

**定位**：§6.2 让备份 `kong.yml`（为临时调高限流做准备），但恢复章节只让 `git checkout` 恢复原文件，**没让删掉这份 .bak**，于是它跟着 `git add` 进了提交。

**解决**：删除 + 建议加进 `.gitignore`；已写进最终完整版第三章清理表。

**验证**：`rm -f docker/kong/kong.yml.bak && git status --short`。

**预防**：**凡"临时备份/临时改动"，在同一阶段收尾清单里必须有一条对应的删除项**。

---

## 五、修改清单总表

### 5.1 业务代码

| 文件 | 改动 | 说明 |
|---|---|---|
| `app_my/core/mock_llm.py` | 🟢 新建 | 假模型：`MOCK_LATENCY_SEC=0.05`、按 task 分派固定响应、`ainvoke_mock()` |
| `app_my/core/config.py` | 🔵 改 | 新增 `MOCK_LLM: bool = False`、`BENCH_TARGET_NAME: str = "monolith"` |
| `app_my/core/model_router.py` | 🔵 改 | `ainvoke_routed()` 开头加 4 行：命中 `settings.MOCK_LLM` 就走打桩分支（唯一出口） |
| `app_my/knowledge/embedding.py` | 🔵 改 | 新增 `_mock_embedding()`（md5 做种子 → 确定性、L2 归一化 → 模长 1.0）、`MOCK_DIMENSION=1024`，`embed_texts/embed_query` 加 mock 分支 |

### 5.2 脚本

| 文件 | 改动 | 说明 |
|---|---|---|
| `benchmarks/locustfile.py` | 🟢 新建 | 3 个场景（登录/对话/图谱问答，权重 3/2/5）、`_live` 峰值并发计数、跑完打印 `BENCH SUMMARY` |
| `scripts/run_bench.sh` / `.ps1` | 🟢 新建 | 压测编排：多目标 × 多并发档 × 每档时长，自动清配额、分目录存 CSV |
| `scripts/locust_report.py` | 🟢 新建 | 汇总 CSV → 对比表 + 拐点表 + Markdown 报告 |
| `scripts/verify_stage10.py` | 🟢 新建 | 33 项验收（文件/打桩/服务健康/生产编排/压测产物） |
| `scripts/ci_local.sh` / `.ps1` | 🟢 新建 → 🔵 修 | 本地跑一遍 CI 命令；修 `import importlib.util` |

### 5.3 配置与部署

| 文件 | 改动 | 说明 |
|---|---|---|
| `docker/requirements.prod.txt` | 🟢 新建 → 🔵 修 | `-r requirements.txt` + gunicorn==23.0.0 + **prometheus-client==0.26.0**（问题 4） |
| `docker/Dockerfile.svc` | 🟢 新建 | DaoCloud 源 python:3.13-slim、非 root、UvicornWorker、Python urllib 做 HEALTHCHECK |
| `docker/docker-compose.prod.yml` | 🟢 新建 → 🔵 修 | 加 `image:` 标签（问题 5）、`env_file` 双文件（问题 8）、Kong worker 数（问题 6） |
| `docker/env.prod-override` | 🟢 新建 | 容器视角连接串覆盖层（问题 7） |
| `.gitee/workflows/pipeline.yml` | 🟢 新建 | 2 阶段：单测 + 编排校验/镜像构建 |
| `docker/kong/kong.yml` | 🔵 临时改 → ✅ 已恢复 | 压测时临时调高限流，收官已回到 600/300/300/120 |
| `docker/kong/kong.yml.bak` | 🟡 待删 | 备份残留，误进提交（问题 16） |

### 5.4 测试

| 文件 | 改动 | 说明 |
|---|---|---|
| `tests/unit/test_stage10_mock_llm.py` | 🟢 新建 | 8 例：打桩内容可解析、embedding 确定性/维度/归一化、开关接线 |
| `tests/unit/test_stage10_bench_report.py` | 🟢 新建 | 9 例：CSV 解析、三张表生成、拐点判定 |

### 5.5 文档

| 文件 | 改动 | 说明 |
|---|---|---|
| `AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md` | 新建 + 6 批勘误 | §7.5 / §9.2 / §10.3+10.4 / §11 / §13.4 / §15.3 / §17.3 / §17.4 / 错误表 26~37 行 |
| `AI私厨_v3.0_阶段10_说明手册_性能压测与CI-CD.md` | 新建 + 勘误 | 同步 `importlib.util`、2 处目录锚点 |
| `AI私厨_v3.0_阶段10_理解手册_性能压测与CI-CD.md` | 新建 + 勘误 | 时序图路由 `/api/v1/chat` → `/chat` |
| `AI私厨_v3.0_阶段10_最终完整版.md` | 🟢 新建（本次） | 封面 + 4 章补充说明 + 两份手册原文（6358 行） |
| `AI私厨_v3.0_阶段10_问题与解决记录.md` | 🟢 新建（本次） | 本文件 |
| `AI私厨_v3.0_阶段10_PR描述.md` | 🟢 新建（本次） | 提 PR 时直接粘贴 |

---

## 六、经验教训

1. **手册里的每个 URL / 函数名 / 数字，落笔前必须 grep 源码或实跑取原文。** 本阶段 7 个手册缺陷里 5 个栽在这（`/api/v1` 前缀 ×2、虚构 `/health` 路径、编造数字 ×5、"删 3 个"实为 2 个）。
2. **勘误要全局 grep，不能只改发现的那一处。** 修 §15.3 时没搜 `/api/v1`，漏掉 §17.3，用户多跑一趟才发现。
3. **容器 Up ≠ 能用（看 STATUS 有没有 Restarting + 看日志 traceback）；语法 OK ≠ 能跑（真跑一次）。** 这两条本阶段各中两次。
4. **"本机 import 成功" ≠ "镜像里有这个包"。** 改依赖必须重新 build，并用 `docker run --rm <镜像> python -c "import x"` 验证。
5. **容器里 localhost 指它自己**，连宿主机服务一律 `host.docker.internal`；healthcheck 只探自己，healthy 不代表依赖通。
6. **YAML 锚点是浅合并**，子级同名字段整体替换；要"部分覆盖"用 `env_file` 列表。
7. **容器内存上限要和进程数一起算**（Kong 默认每核 1 worker）。
8. **含中文的 `.ps1` 必须 UTF-8 with BOM**；curl 内联中文 body 必乱码，用 `-d @文件` 或 Python。
9. **改配置看不到效果，先怀疑缓存**（kg 有 600s 缓存）。
10. **分步手册的中间检查点，要按"这一步能看到哪些文件"计算预期值**，不能拿全集数字。
11. **压测/造数据必须有对应的清理步骤**（549 个 bench_ 账号）。
12. **"工作区干净" ≠ "提交完整"**：`git status` 看不见被忽略的文件，收官要用 `git show --name-only HEAD` 对照。
13. **临时备份/临时阈值必须在同一阶段的收尾清单里有删除项**。
