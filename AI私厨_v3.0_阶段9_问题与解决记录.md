# AI 私厨 v3.0 阶段 9 问题与解决记录

> 阶段：9 / 10 —— 微服务拆分（4 services）+ Kong DB-less 网关 + 跨服务客户端三件套
> 分支：`feat/v3-stage9` ｜ 代码提交：`749876c` ｜ 收官日期：2026-10-20
> 本阶段产出：`services/`（4 服务 + common 四件套）、`docker/kong/kong.yml`、`scripts/ws_probe.py`、3 个测试文件（22 例）、`coordinator.py` 双模式改造、Prometheus 4 个新 target、三件套手册
> **共记录问题 18 个**，其中**手册自身缺陷 13 个**、环境类 3 个、收官遗留 2 个。

## 目录

- [一、一分钟结论](#一一分钟结论)
- [二、背景](#二背景)
- [三、问题总览](#三问题总览)
- [四、问题详情](#四问题详情)
  - [问题 1：手册里的代码是"另一套没实测过的代码"](#问题-1手册里的代码是另一套没实测过的代码)
  - [问题 2：测试文件被贴进了 heredoc 包装行](#问题-2测试文件被贴进了-heredoc-包装行)
  - [问题 3：§7.3 写"两个终端都一样"，实际是 Git Bash 专属](#问题-373-写两个终端都一样实际是-git-bash-专属)
  - [问题 4：§8.5 期望 6 条 routes，实测只有 5 条](#问题-485-期望-6-条-routes实测只有-5-条)
  - [问题 5：§13 WebSocket 探针的期望是编的](#问题-513-websocket-探针的期望是编的)
  - [问题 6：§14 故障隔离"看不到降级"——`$pid` 是 PowerShell 只读自动变量](#问题-614-故障隔离看不到降级pid-是-powershell-只读自动变量)
  - [问题 7：§14 降级信号字段根本不存在](#问题-714-降级信号字段根本不存在)
  - [问题 8：§14 中文乱码 + token 文件 BOM 导致 403](#问题-814-中文乱码--token-文件-bom-导致-403)
  - [问题 9：Start-Process 报"已添加项。字典中的关键字:Path"](#问题-9start-process-报已添加项字典中的关键字path)
  - [问题 10：§14.1 查 PID 得到空值](#问题-10141-查-pid-得到空值)
  - [问题 11：§16.1 PowerShell 长单行命令静默失效](#问题-11161-powershell-长单行命令静默失效)
  - [问题 12：§19 拷贝脚本顺序写反，落盘是空的](#问题-1219-拷贝脚本顺序写反落盘是空的)
  - [问题 13：§19 三条验证的期望全是设计叙事](#问题-1319-三条验证的期望全是设计叙事)
  - [问题 14：Git Bash 里 docker exec 的容器内路径被改写](#问题-14git-bash-里-docker-exec-的容器内路径被改写)
  - [问题 15：§20 裸 `python` 命中 Anaconda 3.6，抛 GBK 解码错](#问题-1520-裸-python-命中-anaconda-36抛-gbk-解码错)
  - [问题 16：§20 出现 5 failed / 5 errors（全是 ConnectionError）](#问题-1620-出现-5-failed--5-errors全是-connectionerror)
  - [问题 17：覆盖项目目录前没备份，新旧 diff 无法出具](#问题-17覆盖项目目录前没备份新旧-diff-无法出具)
  - [问题 18：项目内的说明/理解手册是旧版，与勘误版分叉](#问题-18项目内的说明理解手册是旧版与勘误版分叉)
- [五、修改清单总表](#五修改清单总表)
- [六、经验教训](#六经验教训)

---

## 一、一分钟结论

1. **本阶段 18 个问题里 13 个是手册写错**，且高度集中在同一类：**期望输出是"设计叙事"而不是实跑结果**（routes 数、测试数、paths 数、Kong 校验输出、降级信号字段全中招）。判据只有一条：**没在终端里看到过的输出，不许写进手册。**
2. **最严重的一次是"实测与手册两张皮"**：代码在临时副本里全跑通了，写手册时凭记忆复述成另一套 API（`make_clients`、`threshold=`、`coordinator_local.py`），用户做到 §4.5 直接 ImportError。此后固化为"代码块必须程序化嵌入实测副本 + 逐字节 diff"。
3. **交付路径踩了大坑**：把"把临时副本拷回项目"写成手册一节，脚本顺序写反（`cp` → `rm .new` → `mv`，mv 必失败），**落盘是空的**，用户项目里一直是旧代码，直到 §19 验证报 `KeyError: 'paths'` 才暴露。现已禁止这类步骤，改为"代码全贴手册、按步在项目里创建"。

---

## 二、背景

本阶段把一个跑在 9002 的单体拆成 4 个独立进程（user 9121 / recognizer 9122 / recommender 9123 / chat 9124），前面挂 Kong DB-less 做统一入口，服务之间用自研 HTTP 客户端（重试 + 熔断 + trace_id 透传）通信。

这类问题为什么高发：

- **跨进程 + 跨容器**：一条链路要过 Kong → chat → recommender 三跳，任何一跳的端口/路由/服务没起，现象都长得像"手册写错了"；
- **Windows 双终端**：Git Bash 有 MSYS 路径自动转换、PowerShell 5.1 有语法与只读变量限制，同一条命令两个终端表现完全不同；
- **本机多个 Python**：Anaconda 3.6 与项目 `.venv3` 并存，裸 `python` 会命中 3.6 并抛 GBK 解码错，报错栈看着像测试挂了；
- **期望值难凭空猜**：routes 有几条、测试通过几个、openapi 有几个 path，都是"得跑出来才知道"的数字。

本次排查主要靠三招：**端口健康扫描**（先确认谁没起）、**Admin API / 官方校验器取真实配置**（Kong 5 route 就是这么确认的）、**把命令原样在用户机器上重跑一遍**（所有期望值都由此而来）。

---

## 三、问题总览

| # | 问题 | 类型 | 严重度 | 根因一句话 | 状态 |
|---|---|---|---|---|---|
| 1 | 手册代码是"另一套没实测过的代码"，用户 §4.5 ImportError | 手册缺陷 | 🔴 严重 | 写手册时凭记忆复述，未从实测副本取 | 已修复（14 文件程序化嵌入 + 逐字节 diff） |
| 2 | 测试文件里出现 `cat << 'PYEOF'`，pytest 报 `NameError: cat is not defined` | 手册缺陷 | 🟠 中 | 手册给了"Git Bash 创建 / PowerShell 创建"两套包装，用户把命令行也贴进文件 | 已修复（单份纯代码块 + 直接 cp 进项目） |
| 3 | §7.3 "两个终端都一样"，PowerShell 报"无法识别 -e / cygpath" | 手册缺陷 | 🟠 中 | `\` 续行、`cygpath`、`tail` 都是 bash 专属；镜像名本机也不存在 | 已修复（实测 PS 单行版） |
| 4 | §8.5 期望 6 条 routes，实测 5 条 | 手册缺陷 | 🟠 中 | `/admin` 已含在 r-user，r-admin 是设计叙事 | 已修复（三份手册同步改 9 处） |
| 5 | §13 WS 探针期望是编的（写"握手 101/首帧超时"） | 手册缺陷 | 🟠 中 | 未实跑，凭设计写期望 | 已修复（实机复现两行 OK + pong；过期是 403 不是 1008） |
| 6 | §14 故障隔离"看不到降级"，进程没被杀掉 | 手册缺陷 | 🔴 严重 | `$pid` 是 PowerShell **只读自动变量**（=当前终端 PID），赋值失败 | 已修复（改用 `$rpid`） |
| 7 | §14 期望里的降级字段不存在（`"note":"推荐通道降级…"`） | 手册缺陷 | 🔴 严重 | 字段是编的；真实信号是"由于系统暂未生成特定的候选菜谱" + `/health` breakers `failures>=1` | 已修复（按实机输出重写） |
| 8 | §14 中文乱码；token 文件带 BOM 导致 403 | 环境 + 手册 | 🟡 低 | PS 5.1 `Get-Content` 默认 GBK；`Out-File -Encoding utf8` 写 BOM | 已修复（加 `-Encoding UTF8`；改用 `[IO.File]::WriteAllText` + `.Trim()`） |
| 9 | `Start-Process` 报"已添加项。字典中的关键字:Path" | 环境 | 🟡 低 | 本机环境变量里有重复的 `Path`/`path` | 已修复（改 Python `subprocess.Popen(creationflags=8\|512)`） |
| 10 | §14.1 `recommender pid=` 为空 | 环境 + 手册 | 🟠 中 | recommender **根本没在运行**（隔天漏起），不是命令错 | 已修复（加端口健康扫描预检 + 排错分支） |
| 11 | §16.1 PowerShell 版"没有用"、Git Bash 版可用 | 手册 + 环境 | 🟡 低 | 4 层引号嵌套的长单行，粘贴时引号被吃掉 | 已修复（注明判断方法 + Git Bash 兜底） |
| 12 | §19 拷贝脚本顺序写反 → 落盘为空 → `KeyError: 'paths'` | 手册缺陷 | 🔴 严重 | `cp` 到 `.new` 后又 `rm -rf .new` 再 `mv`，mv 必失败 | 已修复（正确顺序 + 禁止此类步骤） |
| 13 | §19 期望 `OK 18` / "parse time/parsed: OK" | 手册缺陷 | 🟠 中 | 数字是猜的，未实跑 | 已修复（`OK 19` / `parse successful`） |
| 14 | Git Bash 里 `/etc/kong/kong.yml` 变 `D:/git/Git/etc/...` | 手册缺陷 | 🟠 中 | MSYS 自动路径转换 | 已修复（`MSYS_NO_PATHCONV=1`） |
| 15 | §20 裸 `python` → Anaconda 3.6 → `UnicodeDecodeError: 'gbk'` | 手册缺陷 | 🔴 严重 | 手册没写解释器全路径 | 已修复（`.venv3/Scripts/python.exe`） |
| 16 | §20 出现 5 failed / 5 errors，全是 ConnectionError | 手册缺陷 | 🟠 中 | 老测试要连单体 9002，9002 没起 | 已修复（加"先起 9002"步骤；起了是 140 passed） |
| 17 | 覆盖项目目录前没备份 → 新旧 diff 出具不了 | 收官遗留 | 🟠 中 | 旧版从未 commit、无 `.bak` | 已记录（新规矩：改前先 commit/备份） |
| 18 | 项目内说明/理解手册是旧版（6 routes / 27 测试），与勘误版分叉 | 收官遗留 | 🟠 中 | 手册曾存在两份（工作区 + 项目），只改了其中一份 | 已修复（勘误版覆盖项目版，项目为唯一事实源） |

---

## 四、问题详情

### 问题 1：手册里的代码是"另一套没实测过的代码"

**现象**：用户做到 §4.5 报 `ImportError`（`app_my.api` 里没有 `memory`），随后又发现 `from services.common.breaker import CircuitBreaker` 的参数名对不上、`services/user/main.py` 的目录引用也不对。

**定位**：对比临时副本与手册代码块，发现手册里是**凭记忆复述出来的另一套代码**：`CircuitBreaker(threshold=)`（实测是 `failure_threshold=`）、`make_clients()`（实测是 `get_client(name)` 单例）、`app_my/agents/coordinator_local.py`（这个文件**根本不存在**）、四个 main 的路由归属、Kong 配置、测试计数（写 27，实测 22）全都不一样。

**解决**：写脚本以**临时副本为唯一事实源**，`replace_section()` 按标题边界整段替换，代码块由 `rd(副本文件)` 原样嵌入；嵌完逐字节 diff，14 个文件全部 MATCH；再跑残留扫描（grep `make_clients`/`coordinator_local`/"27 passed"/`r-admin`），清零。

**验证**：用户在项目里重新落盘后 `pytest` 通过；`services.user.main` 可正常导入。

**预防**：🔴 **手册代码块必须程序化嵌入实测副本，禁止手写复述**——写完逐字节 diff，不验不算完成。

---

### 问题 2：测试文件被贴进了 heredoc 包装行

**现象**：`pytest` 报 `NameError: cat is not defined`（3 errors）。

**定位**：手册给测试文件时写了"Git Bash 创建（`cat > x << 'PYEOF'`）"和"PowerShell 创建"两套包装，用户把 **Git Bash 的整段命令行也贴进了 .py 文件**。

**解决**：① 直接用实测副本 `cp` 覆盖项目里三个测试文件（用户已授权"错误代码直接在项目中改正"）；② 手册改为**单份纯内容块**（从第一行代码开始，不带任何包装行），并注明"推荐用 VSCode/PyCharm 新建文件整段粘贴"。

**验证**：项目内实跑 `22 passed`（8 + 7 + 7）。

**预防**：**文件内容只给一份纯代码块，禁止给 heredoc / `@'...'@ | Set-Content` 包装**；只有"运行/验证命令"才分双终端。

---

### 问题 3：§7.3 写"两个终端都一样"，实际是 Git Bash 专属

**现象**：PowerShell 5.1 报"无法识别 `-e`"、"`cygpath` 不是可识别的命令"。

**定位**：该命令用了 `\` 续行、`cygpath`、`tail`——全是 bash 专属；而且 `-v "/$(cygpath ...)"` 开头多了个 `/`，镜像 `kong:3.7` 本机根本没拉过。

**解决**：给出**实测通过的 PowerShell 单行版**（`docker run --rm -e KONG_DATABASE=off -v "F:\...\kong.yml:/etc/kong/kong.yml:ro" docker.1panel.live/library/kong:3.7 kong config parse /etc/kong/kong.yml`），并顺带扫出另外 3 处同类问题（§8.2 / §13.3 / §17.4）一并改成双终端两栏。

**验证**：两个终端都能输出 `parse successful`。

**预防**：**禁止写"两个终端都一样"**；bash 专属语法（续行 `\`、`cygpath`、`tail`、`export`）出现即视为违规。

---

### 问题 4：§8.5 期望 6 条 routes，实测只有 5 条

**现象**：用户验证时只数到 5 条，手册写 6 条。

**定位**：`/admin` 路径已经包含在 `r-user` 的 `paths` 里，`r-admin` 是我在设计阶段脑补的一条独立路由，写进了期望。

**解决**：三份手册同步改 9 处（routes: 6 → 5，删掉 r-admin 行）。

**验证**：`curl 9105/routes` 实况 → `['r-chat','r-chat-ws','r-recognizer','r-user','r-recommender']`，**5 条**。

**预防**：**任何计数型期望必须实跑取数**；设计阶段的设想不等于落地结果。

---

### 问题 5：§13 WebSocket 探针的期望是编的

**现象**：手册写"握手成功 101 / 首帧超时"，实机完全对不上。

**定位**：期望是按设计写的，探针脚本没在真实 token 下跑过。

**解决**：注册新用户拿新鲜 token 实机复现，按真实输出改 §13.1–§13.3 三处；顺带记下真实行为：**token 过期返回 HTTP 403，不是 WebSocket 1008**。

**验证**：探针输出两行 `OK <url> -> {"type":"pong"}`（直连 9124 与经 Kong 9100 各一次）。

**预防**：**脚本类验证必须真跑一次再写期望**；过期/失败分支也要真触发一次。

---

### 问题 6：§14 故障隔离"看不到降级"——`$pid` 是 PowerShell 只读自动变量

**现象**：按手册杀 recommender 后，chat 仍然返回完整推荐，看不出降级。

**定位**：手册用了 `$pid` 存 PID，而 **`$pid` 是 PowerShell 的只读自动变量**（等于当前终端自己的进程号），赋值会报"无法覆盖变量 PID"，于是 `Stop-Process` 杀的是错的进程——recommender 根本没死。

**解决**：变量名改 `$rpid`，并补"杀完确认端口已空"的验证步骤。

**验证**：改用 `$rpid` 后端口确实被释放，chat 返回降级结果。

**预防**：**PowerShell 里禁用 `$pid` 作变量名**（同理还有 `$host`、`$args`、`$input`）；杀进程后必须回查端口。

---

### 问题 7：§14 降级信号字段根本不存在

**现象**：用户按手册找 `"note": "推荐通道降级，仅返回营养成分"`，响应里没有；`/health` 的 breakers 里也没看到 `failures>=1`、`state==closed`、`last_error` 含 connect。

**定位**：那个 `note` 字段是我编的。真实降级表现是响应正文出现"**由于系统暂未生成特定的候选菜谱**"，以及 `/health` 的 `breakers` 快照里 `recommender.failures` 递增、`last_error` 为 `HTTPStatusError: HTTP 502`（本机系统代理 7890 拦截）或 `ConnectError`。

**解决**：按实机输出重写 §14.3 的期望；§14.0 增加预检（重新登录拿新 token + `/mode` 自检）。

**验证**：kill 9123 后 chat 仍返回，正文含上述降级文案，`/health` breakers 有记录。

**预防**：**字段名/文案必须来自真实响应**，禁止编造字段名再让用户去找。

---

### 问题 8：§14 中文乱码 + token 文件 BOM 导致 403

**现象**：终端里中文是乱码；读 token 后请求返回 403。

**定位**：① PowerShell 5.1 的 `Get-Content` 默认按 **GBK** 解码 UTF-8 文件；② `Out-File -Encoding utf8` 会写 **BOM 头**，token 前面多了不可见字符。

**解决**：读取处加 `-Encoding UTF8` 并 `.Trim()`；写文件改用 `[System.IO.File]::WriteAllText($p, $s, (New-Object System.Text.UTF8Encoding($false)))`（无 BOM）。

**验证**：token 可用，`/users/me` 正常返回。

**预防**：**PowerShell 读写 UTF-8 文本一律显式指定编码 + Trim**；不用 `Out-File` 写会被程序读取的凭据文件。

---

### 问题 9：Start-Process 报"已添加项。字典中的关键字:Path"

**现象**：用 `Start-Process` 起 uvicorn，报 `已添加项。字典中的关键字:"Path" 所添加的关键字:"path"`。

**定位**：本机环境变量里存在重复的 `Path` 与 `path`，`Start-Process` 构造子进程环境时冲突；`-UseNewEnvironment` / CIM / `cmd /c start` 均被环境或工具策略拦下。

**解决**：改用 **Python `subprocess.Popen(..., creationflags=8|512)`**（DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP）分离进程，等价 nohup，实测可行，日志重定向到 `C:\Windows\Temp\svc_*.out.log`。

**验证**：4 个服务以此方式启动，`/health` 全部 ok，关终端不退。

**预防**：**Windows 起长驻服务优先用 Python 分离进程**，`Start-Process` 作为备选并注明冲突时的替代方案。

---

### 问题 10：§14.1 查 PID 得到空值

**现象**：`Write-Output "recommender pid=$rpid"` 输出的 pid 是空的。

**定位**：实机扫端口发现 **9123 上没有任何进程监听**（9121/9122/9124 与 Kong 都在）——recommender 服务压根没运行，隔天重做时漏起了它。命令本身没问题。

**解决**：把 recommender 重新拉起（PID 10712），并在手册 §14.1 增加"pid 为空"的排错分支：**先跑四端口健康扫描，哪个 FAIL 就先按 §9/§16 的命令拉起哪个**。

**验证**：四端口 + Kong 全绿后再查 PID，`pid=10712` 正常输出。

**预防**：🔴 **服务型阶段每阶段开工/隔天续做先做端口健康扫描**；"查不到 PID / 端口无监听"的第一反应是"服务没起"，不是"命令错了"。

---

### 问题 11：§16.1 PowerShell 长单行命令静默失效

**现象**：用户反馈 §16.1 的 PowerShell 版"没有用"，§9.3 的 Git Bash 版"有用"（两条命令本体都验证过）。

**定位**：那条 PowerShell 命令是 4 层引号嵌套的超长单行，粘贴到终端时引号容易被吃掉，失败时还不报错（静默）。

**解决**：手册补充判断方法（**看它写的日志 `C:\Windows\Temp\svc_rec2.out.log` 是否为空**——空即未执行成功）与替代路径（直接用 Git Bash 版，或存成 `.py` 脚本再执行）。

**验证**：Git Bash `nohup` 版用户实测可用。

**预防**：**超长单行命令要么拆成脚本文件，要么同时给 bash 版**；凡"写了日志文件"的命令，把"日志为空=没跑起来"写进排错。

---

### 问题 12：§19 拷贝脚本顺序写反，落盘是空的

**现象**：用户跑完 §19 的落盘脚本，验证时报 `KeyError: 'paths'`。

**定位**：脚本是 `cp -r "$SRC/$d" "$d.new"` → 后面却 `rm -rf "$d.new"` → 再 `mv "$d.new" "$d"`。**中间那句把刚拷出来的东西删了**，mv 必然失败（`No such file or directory`），等于什么都没拷——项目里一直是旧版代码。

**解决**：① 改成正确顺序（`cp` 到 `.new` → 删**旧目录** → `.new` 顶上，并清 `__pycache__`），并实际执行一次同步；② **从手册里删掉这类"把临时副本拷回项目"的步骤**——代码全部贴在手册里，按步在项目目录创建。

**验证**：同步后 `diff -r --brief -x __pycache__` 三目录**完全一致**；三条验证输出 `OK 19` / `OK breaker` / `parse successful`；pytest 140 passed。

**预防**：🔴 **禁止把"从临时副本拷回项目"写成手册步骤**；🔴 **手册里的脚本段也必须实机跑通**，不能只审代码。

---

### 问题 13：§19 三条验证的期望全是设计叙事

**现象**：手册期望写 `OK 18`、Kong 校验写 `parse time: <X> / parsed: OK`；实跑是 `OK 19` 和 `parse successful`。

**定位**：期望值按"应该长这样"写的，没跑。

**解决**：按实机输出逐条改。

**验证**（2026-10-20 原文）：
```
OK 19
OK breaker
parse successful
```

**预防**：**数字型/文本型期望一律粘贴终端原文**，标"实测原文"。

---

### 问题 14：Git Bash 里 docker exec 的容器内路径被改写

**现象**：`docker exec ai_chief_kong kong config parse /etc/kong/kong.yml` 报 `D:/git/Git/etc/kong/kong.yml: No such file or directory`。

**定位**：Git Bash 的 MSYS 把以 `/` 开头的参数自动转换成本机路径。

**解决**：Git Bash 版加 `MSYS_NO_PATHCONV=1` 前缀（且参数用**单**斜杠 `/PID`，两者必须配套）。PowerShell 无此问题。

**验证**：加前缀后输出 `parse successful`。

**预防**：🔴 **Git Bash 里凡是"容器内的绝对路径"都要加 `MSYS_NO_PATHCONV=1`**（`docker exec`、`docker run -v` 的容器侧路径同理）。

---

### 问题 15：§20 裸 `python` 命中 Anaconda 3.6，抛 GBK 解码错

**现象**：`python -m pytest -q` 报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xa8 in position 99`，栈里全是 iniconfig/pytest 配置读取，看起来像"测试挂了"。

**定位**：裸 `python` 命中的是 Anaconda 3.6（本机多个 Python 并存），它的旧 pytest 用 GBK 读项目里 UTF-8 的配置文件。跟测试本身无关。

**解决**：手册所有 Python 命令改成 `.venv3/Scripts/python.exe` 全路径（双终端都改）。

**验证**：`./.venv3/Scripts/python.exe -m pytest -q` → `140 passed, 7 deselected`。

**预防**：🔴 **禁止裸 `python`/`python3`**，一律项目虚拟环境解释器全路径；跑任何 Python 项目前先确认解释器。

---

### 问题 16：§20 出现 5 failed / 5 errors（全是 ConnectionError）

**现象**：`pytest -q` 输出 `5 failed, 128 passed, 1 deselected, 5 errors`，失败项全是 `requests.exceptions.ConnectionError`。

**定位**：`tests/test_auth.py` 与 `tests/test_trace.py` 是**直接 HTTP 连单体 9002** 的老测试，9002 当时没起。手册 §20 写"failed == 0"却没写这个前置条件。

**解决**：手册新增"第一步：起单体对照组 9002"（双终端命令），并写明两种预期：起了 → `140 passed, 7 deselected`；没起 → `5 failed / 5 errors` 且全是 ConnectionError（**看到这个就回去起 9002**）。

**验证**：起 9002 后 `140 passed, 7 deselected, 3 warnings`。

**预防**：**"期望 failed == 0"必须连同它的前置条件一起写**（哪些服务得先起来）。

---

### 问题 17：覆盖项目目录前没备份，新旧 diff 无法出具

**现象**：用户问"新版本和旧版本具体改了哪些代码"，答不出来。

**定位**：覆盖前 `services/` **从未 commit**（PyCharm 里一直是红色 unversioned），也没留 `.bak`；事后在 git 历史、磁盘、PyCharm LocalHistory 里都检索不到旧版特征串——不可恢复。

**解决**：如实说明不可恢复，并给出**勘误记录级对照**（旧版错在哪：参数名、API 名、文件是否存在、routes 数、测试数）；同时把"改目录前先 commit/备份"写成新规矩。

**验证**：后续提交 `749876c` 已把 `services/` 全量入库（23 个文件），此后再改动都能出 diff。

**预防**：🔴 **动用户项目目录前先 `git add -A && git commit` 或 `cp -r` 一份 `.bak`**——没备份 = 出不了 diff、无法回滚。

---

### 问题 18：项目内的说明/理解手册是旧版，与勘误版分叉

**现象**：收官核实时发现项目里的说明手册还写着"**6 routes**""新增 **27** 个测试"，而勘误后的正确值是 5 和 22；理解手册同样。

**定位**：手册曾同时存在于工作区与项目目录，勘误时只改了工作区那份，项目里那份一直没更新——**两份分叉**。

**解决**：用已勘误版覆盖项目里的说明/理解手册，并复查残留（`grep "6 routes\|27 测试\|27 passed"`）为零；明确**项目目录是唯一事实源**，后续所有 md 修改都直接改项目里那份。

**验证**：三份手册现在都与实测一致；`diff` 项目版 = 勘误版。

**预防**：🔴 **手册只保留一份，放在项目目录**；勘误直接改那份，不在工作区另存副本。

---

## 五、修改清单总表

### 5.1 代码（新建，18 个）

| 文件 | 关键内容 |
|---|---|
| `services/__init__.py` | 包声明 |
| `services/common/__init__.py` | 包声明 |
| `services/common/breaker.py` | `CircuitBreaker(name, failure_threshold=3, recovery_timeout=30.0)`、`CircuitOpenError`、`BreakerState`、`get_breaker/all_snapshots/reset_all` |
| `services/common/client.py` | `ServiceClient`（重试 `retries=2`、`transport=` 可注入 MockTransport）、`get_client(name)` 全局单例、`_current_trace_id()` 复用 `trace_id_var` |
| `services/common/context.py` | `set_upstream_token` / `auth_header`，跨服务透传上游 JWT |
| `services/common/app_factory.py` | `create_service_app(service_name, routers, enable_auth, enable_quota, capture_auth, cors_origins)`；内含 `TenantVarMiddleware` / `TokenCaptureMiddleware` |
| `services/user/{__init__,main}.py` | 9121：auth / users / tenants / admin / billing / cache |
| `services/recognizer/{__init__,main}.py` | 9122：识别 + 营养节点、OSS |
| `services/recommender/{__init__,main}.py` | 9123：KG 写、推荐 + 重排节点、billing |
| `services/chat/{__init__,main,graph_remote}.py` | 9124：chat / memory / tasks / ws；`graph_remote.py` = 远程节点表（走 `/internal/nodes/*`） |
| `docker/kong/kong.yml` | 4 service + **5 route** + 3 插件（cors / rate-limit / correlation-id） |
| `scripts/ws_probe.py` | WS 穿透探针（直连 9124 + 经 Kong 9100） |

### 5.2 代码（修改，2 个）

| 文件 | 改动 |
|---|---|
| `app_my/agents/coordinator.py` | 新增 `build_workflow(nodes=None)` + `_resolve_nodes()`，按 `SPLIT_MODE` 切本地/远程 |
| `.gitignore` | 已含 `.venv/` `:58`、`.venv3/` `:64`（**待提交**） |

### 5.3 配置（修改，2 个）

| 文件 | 改动 |
|---|---|
| `docker/docker-compose.v3.yml` | 追加 `kong` 服务：容器 8000/8001 → 宿主 9100/9105，镜像 `docker.1panel.live/library/kong:3.7` |
| `docker/prometheus/prometheus.yml` | 新增 4 个 job：`ms-user 9121` / `ms-recognizer 9122` / `ms-recommender 9123` / `ms-chat 9124`（实测全部 up） |

### 5.4 测试脚本（新建 3 个，共 22 例）

| 文件 | 例数 | 测什么 |
|---|---|---|
| `tests/unit/test_circuit_breaker.py` | 7 | 状态机 closed → open → half_open → closed、阈值、恢复超时 |
| `tests/unit/test_service_client.py` | 8 | 重试次数、4xx 不重试、熔断联动（用 `httpx.MockTransport` 离线） |
| `tests/unit/test_service_apps.py` | 7 | 中间件顺序断言（Metrics 必须在 Auth 外层） |

### 5.5 文档（本阶段 5 份，均在项目根目录）

| 文件 | 说明 |
|---|---|
| `AI私厨_v3.0_阶段9_操作手册_微服务拆分与Kong网关.md` | 3517 行，含今天 4 处勘误（§14.1 / §16.1 / §19 / §20） |
| `AI私厨_v3.0_阶段9_说明手册_微服务拆分与Kong网关.md` | 1743 行，已用勘误版覆盖项目旧版 |
| `AI私厨_v3.0_阶段9_理解手册_微服务拆分与Kong网关.md` | 1033 行，同上 |
| `AI私厨_v3.0_阶段9_最终完整版.md` | 5476 行（封面 + 两份手册拼接，51 条链接 0 悬空） |
| `AI私厨_v3.0_阶段9_问题与解决记录.md` | 本文件 |

---

## 六、经验教训

1. **没在终端里看到过的输出，不许写进手册。** 本阶段 13 个手册缺陷里，一半是"数字/字段/文案是设计叙事"（routes 6→5、测试 27→22、paths 18→19、Kong 输出、降级字段）。
2. **实测副本只当验证沙箱和代码块事实源，绝不当交付路径。** 一旦把"拷回项目"写进手册，脚本出 bug 就是静默的（本次 mv 必失败却没人发现）。
3. **改用户目录前先 commit 或留 `.bak`。** 没有备份就没有 diff、没有回滚、答不出"改了什么"。
4. **手册只保留一份，放在项目目录。** 两份并存必然分叉（本次项目里的说明/理解手册停留在旧值）。
5. **PowerShell 5.1 的坑要单独记**：`$pid` 是只读自动变量、不存在 `nohup`/`&&`/`grep`/`head`、`Get-Content` 默认 GBK、`Out-File` 写 BOM、超长单行命令粘贴易吃引号。
6. **Git Bash 的坑同样要单独记**：容器内路径必须 `MSYS_NO_PATHCONV=1`（配单斜杠参数）；Python 命令必须走 `.venv3` 全路径，否则命中 Anaconda 3.6 的 GBK 报错。
7. **"服务没起"是最容易被误判成"手册写错"的现象。** 查 PID 为空、端口无监听、请求 ConnectionError——先做端口健康扫描。
8. **测试代码同时落项目与贴手册，两份 diff 校验。** 用户手抄 heredoc 包装行进文件的教训已经踩过一次。
9. **目录锚点用脚本重算后回写，禁止手写。** 拼接后的最终完整版一次就查出 3 条悬空（标题带反引号/括号时手写锚点几乎必错）。
10. **提交完整性的默认漏洞是文档。** 代码进了、md 一份没进——阶段 7/8/9 连续三次如此；收官清单里"md 是否 `git add`"必须单列一条。
