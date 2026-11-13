# AI 私厨 v3.0 阶段 8 问题与解决记录
### Celery 异步任务队列 + WebSocket 实时推送

> **阶段**：8 / 10　**分支**：`feat/v3-stage8`　**提交**：`7b5547c`　**收官日期**：2026-10-15
> **本阶段产出**：26 个新建文件 + 5 个修改文件；测试 91 → **118 passed**；分级路由与端到端各 `[ok]`
> **共记录问题 12 个**：其中**手册自身缺陷 5 个**、**环境 2 个**、**收官遗留 3 个**、**工作区残留 2 个**
> 🔴 与阶段 7 不同（15 个里 12 个是手册写错），本阶段**代码层零事故**——代码提交后一次跑通；问题集中在"文档可点击性"和"收尾 hygiene"上。

---

## 目录

- [一、一分钟结论](#一一分钟结论)
- [二、背景](#二背景)
- [三、问题总览](#三问题总览)
- [四、问题详情](#四问题详情)
  - [问题 1：操作手册目录 13 条锚点悬空（emoji 后的空格）](#问题-1操作手册目录-13-条锚点悬空emoji-后的空格)
  - [问题 2：说明手册目录 1 条锚点少一个连字符](#问题-2说明手册目录-1-条锚点少一个连字符)
  - [问题 3：两份手册章节顺序不镜像](#问题-3两份手册章节顺序不镜像)
  - [问题 4：操作手册只有 PowerShell 命令，0 个 Git Bash 块](#问题-4操作手册只有-powershell-命令0-个-git-bash-块)
  - [问题 5：手册写"不加 --pool=solo 报 OSError"，实测是 WinError 5](#问题-5手册写不加---poolsolo-报-oserror实测是-winerror-5)
  - [问题 6：`.gitignore` 被写成 UTF-16LE，git 当二进制处理](#问题-6gitignore-被写成-utf-16legit-当二进制处理)
  - [问题 7：`.gitignore` 仍没有 `.venv3`（阶段 7 遗留未闭环）](#问题-7gitignore-仍没有-venv3阶段-7-遗留未闭环)
  - [问题 8：10 份 md 手册未纳入 git](#问题-810-份-md-手册未纳入-git)
  - [问题 9：`app_my/api/_debug.py` 临时 500 触发器仍未删（跨阶段遗留）](#问题-9app_myapi_debugpy-临时-500-触发器仍未删跨阶段遗留)
  - [问题 10：临时脚本 `_verify_wsjs.js` 混进了提交](#问题-10临时脚本-_verify_wsjsjs-混进了提交)
  - [问题 11：版本库里有两个 0 字节的 `-H` / `-d` 垃圾文件](#问题-11版本库里有两个-0-字节的--h---d-垃圾文件)
  - [问题 12：12 个测试用例依赖后端在线，后端没起会误判为代码回归](#问题-1212-个测试用例依赖后端在线后端没起会误判为代码回归)
- [五、修改清单总表](#五修改清单总表)
- [六、经验教训](#六经验教训)

---

## 一、一分钟结论

1. **代码没问题，文档有瑕疵**。阶段 8 提交后 `pytest` 一次就到 118 passed，`routing` 和 `e2e` 两个验收脚本一次通过。真正要修的是：两份手册**共 14 条目录链接点不动**（emoji 与中文之间的空格让锚点多出一个连字符），以及 **`.gitignore` 被 PowerShell 用 UTF-16LE 追加内容后 git 把它当二进制**。
2. **收尾 hygiene 是这一阶段的头号风险**。实测发现 4 类残留：`_debug.py`（阶段 7 的 500 地雷）、`_verify_wsjs.js`（临时脚本已进提交）、`-H`/`-d`（阶段 5 误提交的两个空文件）、10 份 md 手册未跟踪。它们都不影响运行，但会原样进 PR。
3. **"看起来像回归，其实是环境"**。第一次跑 `pytest` 拿到 `6 failed, 106 passed, 6 errors`——12 个用例全是 `requests.exceptions.ConnectionError`，因为它们连 `127.0.0.1:9002`。起后端后立刻 `118 passed`。**看到 ConnectionError 先想起服务，不要先去改代码。**

---

## 二、背景

### 2.1 本阶段做了什么

把三个"重活"（Milvus 向量重索引、Neo4j 图谱重建、营养报告生成）从 HTTP 请求里剥离出来：API 进程收单即返回任务编号，Celery worker 从 Redis 队列取单执行，通过 Redis pub/sub 把状态事件推回 API 进程，再由 WebSocket 长连接实时推给浏览器。同时给 worker 加了独立指标端口 9101，接入阶段 7 的 Prometheus，补 2 条告警。

### 2.2 为什么这次的问题长这样

阶段 7 的 15 个事故里 12 个是"手册写错导致用户照做必踩"——那次之后我们把三条规矩写进了开工技能：**顺序规范**、**双终端规范**、**零悬空引用校验**。阶段 8 是第一次全面执行这套规矩的阶段，所以：

- 代码层**没有**出现"编造函数 / 顺序倒置 / 挂载失败"这类事故（规矩生效了）；
- 但**"零悬空引用"这一条只在写完后靠脚本才查出来**——说明规矩立了还不够，必须**交付前跑脚本**（阶段 8 收官时跑了，查出 14 条）；
- `.gitignore` 的问题则是**跨阶段遗留**：阶段 7 收官时就发现"缺 `.venv3`"，当时只在文档里给了命令，用户执行时用 PowerShell 追加 → 又引入了 UTF-16 编码问题。**"给命令"不等于"已闭环"**。

### 2.3 本次排查用到的手段

| 手段 | 用途 |
|---|---|
| `git status --porcelain` + `git show --stat HEAD` | 对照"上一次提交到底含哪些文件"与"哪些还 untracked"，一次定位提交完整性问题 |
| 自写校验脚本（跳过代码块后统计标题锚点 vs 目录链接） | 一次查出 14 条悬空目录链接 |
| Python 读 `.gitignore` 原始字节 | 发现 NUL 字节 → 判定 UTF-16LE → git 按二进制处理 |
| 实测 `celery worker` 不加 `--pool=solo` | 拿到真实报错 `PermissionError: [WinError 5]`，验证手册描述是否准确 |
| `curl /api/v1/targets`、`/api/v1/rules` | 确认 worker 指标真的被 Prometheus 抓到、告警规则真的加载了 |

---

## 三、问题总览

| # | 问题 | 类型 | 严重度 | 根因一句话 | 状态 |
|---|---|---|---|---|---|
| 1 | 操作手册目录 13 条锚点悬空 | 手册缺陷 | 中 | 标题里 emoji 与中文之间有空格，锚点多出一个连字符 | ✅ 已修（脚本重算 28 条） |
| 2 | 说明手册目录 1 条锚点悬空 | 手册缺陷 | 低 | 手写的锚点少了一个连字符 | ✅ 已修 |
| 3 | 两份手册章节顺序不镜像 | 手册缺陷 | 低 | 操作手册按执行顺序、说明手册按理解顺序 | ✅ 已缓解（最终完整版补顺序对照表） |
| 4 | 操作手册 0 个 Git Bash 块 | 手册缺陷 | 低 | 全部 28 个代码块只有 PowerShell 版 | ⚠️ 待补（不影响当前收官） |
| 5 | 手册写"报 OSError"，实测是 WinError 5 | 手册缺陷 | 低 | 描述凭印象写，未实测 | ✅ 已修（理解手册写实测原文） |
| 6 | `.gitignore` 被写成 UTF-16LE | 环境 | 中 | PowerShell 5.1 的 `>` / `Add-Content` 默认 UTF-16LE | ⚠️ 待用户执行（最终完整版 4.2） |
| 7 | `.gitignore` 仍没有 `.venv3` | 收官遗留 | **高** | 阶段 7 遗留未闭环，`git add .` 会提交整个虚拟环境 | ⚠️ 待用户执行 |
| 8 | 10 份 md 手册未纳入 git | 收官遗留 | 中 | 只提交了代码，文档没 add | ⚠️ 待用户执行（4.1 有完整清单） |
| 9 | `_debug.py` 临时 500 触发器未删 | 收官遗留 | 中 | 阶段 7 遗留，跨阶段带到本分支 | ⚠️ 待用户执行（4.3） |
| 10 | `_verify_wsjs.js` 混进提交 | 工作区残留 | 低 | 临时校验脚本忘了删就 `git add` | ⚠️ 待用户执行（4.3） |
| 11 | 版本库里有 `-H` / `-d` 两个 0 字节文件 | 工作区残留 | 低 | 阶段 5 某次 curl 参数被引号吃掉，shell 当成文件名创建 | ⚠️ 待用户执行（4.3） |
| 12 | 12 个用例依赖后端在线 | 环境 | 中 | 测试连 `127.0.0.1:9002`，后端没起就 ConnectionError | ✅ 已定位（起后端即 118 passed） |

---

## 四、问题详情

### 问题 1：操作手册目录 13 条锚点悬空（emoji 后的空格）

**类型**：手册缺陷　**严重度**：中

**现象**
用脚本按 GitHub 锚点规则（去标点、空格转连字符、英文转小写）比对手册内 28 条目录链接与真实标题，结果 **13 条指向不存在的锚点**——在支持目录跳转的阅读器里点了没反应：

```text
TOC 链接数: 28 | 悬空: 13
 ❌ 七子模块-1新增-6-个配置项app_mycoreconfigpy-修改
 ❌ 八子模块-2任务事件通知app_mycorenotifypy-新建
 ❌ 九子模块-3worker-自己的指标app_mycoreworker_metricspy-新建
 ❌ 十子模块-4celery-应用实例app_myworker-新建-2-个文件
 ❌ 十一子模块-5任务基类-notifytaskapp_myworkerbasepy-新建
 ❌ 十二子模块-6worker-生命周期信号app_myworkersignalspy-新建
 ❌ 十三子模块-7三个长任务app_myworkertasks-新建-4-个文件
 ❌ 十四子模块-8接口数据模型app_myschemastaskspy-新建
 ❌ 十五子模块-9任务提交与查询接口app_myapitaskspy-新建
 ❌ 十六子模块-10websocket-三件套app_myws-新建-4-个文件
 ❌ 十八子模块-12前端-ws-客户端frontend-新建-2-个文件
 ❌ 二十子模块-14验收脚本scriptsverify_stage8py-新建
 ❌ 二十一子模块-15单元测试27-例-新建-5-个文件
```

**定位**
拿第 7 章对照：

```text
真实标题：七、子模块 1：新增 6 个配置项（app_my/core/config.py 🔵 修改）
真实锚点：七子模块-1新增-6-个配置项app_mycoreconfigpy--修改     ← emoji 前后各一个空格 → 两个连字符
目录写的：七子模块-1新增-6-个配置项app_mycoreconfigpy-修改      ← 只写了一个
```

即：**写目录时按"🔵修改"（无空格）算锚点，实际标题是"🔵 修改"（有空格）**，emoji 被规则剔除后留下两个空格 → 双连字符。凡是带 🔵/🟢 且 emoji 后有空格的中文标题，全部中招（13 条）。

**解决**
写脚本（跳过代码块内的 `#` 注释行，只取真标题）重新计算锚点并回写目录链接：

```python
# 归一化匹配：把连续连字符压成一个再比对，命中就用真实锚点替换
new_text, n = re.subn(r"\[([^\]]+)\]\(#([^)]+)\)", repl, text)
```

操作手册替换 28 条、说明手册 22 条。

**验证**

```text
AI私厨_v3.0_阶段8_..._操作手册.md | 行数 3848
  TOC 链接数: 28 | 悬空: 0
```

**预防**
**目录锚点一律用脚本生成，禁止手写。** 交付前必跑"跳过代码块 → 提取标题 → 计算锚点 → 比对目录链接"的校验脚本；CJK 标题尤其注意 emoji 与文字之间的空格会变成额外连字符。

---

### 问题 2：说明手册目录 1 条锚点少一个连字符

**类型**：手册缺陷　**严重度**：低

**现象**
说明手册 22 条目录链接里有 1 条悬空，且与问题 1 的"双连字符"不是同一类：

```text
悬空链接: '十七可观测接线dockerprometheus两个-yml修改'
真实锚点: '十七可观测接线dockerprometheus-两个-yml修改'
```

**定位**
标题是 `## 十七、可观测接线：docker/prometheus 两个 yml（🔵修改）`，其中 `两个` 与 `yml` 之间有空格 → 应转成一个连字符；手写时漏了 → `两个-yml` 变成了 `两个yml`（实际是漏在 `dockerprometheus` 与 `两个` 之间）。归一化匹配也救不了（差异不是连续连字符，而是少了一个）。

**解决**
单独重算这一条的锚点并替换：

```text
old: #十七可观测接线dockerprometheus两个-yml修改
new: #十七可观测接线dockerprometheus-两个-yml修改
```

**验证**

```text
AI私厨_v3.0_阶段8_..._说明手册.md | 行数 2471
  TOC 链接数: 22 | 悬空: 0
```

**预防**
同问题 1：**锚点脚本生成，不手写**。

---

### 问题 3：两份手册章节顺序不镜像

**类型**：手册缺陷　**严重度**：低

**现象**
两份手册讲同一批文件，但章节顺序差异很大：

| 文件 | 操作手册 | 说明手册 |
|---|---|---|
| `config.py` | 七 | 三 |
| `notify.py` | 八 | **七** |
| `worker_metrics.py` | 九 | **八** |
| `celery_app.py` | **十** | **四** |
| `base.py` | 十一 | 五 |
| `signals.py` | 十二 | 六 |
| `ws/` 三件套 | 十六 | 十~十二 |
| `api/tasks.py` | 十五 | **十三**（在 ws 之后） |
| `verify_stage8.py` | 二十 | **十六**（在 prometheus 之前） |
| `prometheus/*.yml` | 十九 | **十七** |

用户按操作手册敲到第 8 步（notify.py）想回头查"为什么这么写"，在说明手册里得到的是第 7 章——序号对不上，容易以为漏看了。

**定位**
不是写错，是**排序原则不同**：操作手册按**执行顺序**（先建配置和通知，才能建任务），说明手册按**理解顺序**（先讲"大脑" celery_app，再讲四肢）。

**解决**
不重排（说明手册的理解顺序本身是合理的），改为在**最终完整版**里补一张**《三、两份手册的章节顺序对照》**表（执行顺序 ↔ 操作手册章 ↔ 说明手册章，16 行），读者按表定位即可。

**验证**
最终完整版第 3 章 16 行对照表已落盘，目录链接 `#三两份手册的章节顺序对照` 可点击。

**预防**
开工写手册时，若两份排序原则确实不同，**必须在交付物里附一张顺序对照表**（这条已写进开工技能 4.2）。

---

### 问题 4：操作手册只有 PowerShell 命令，0 个 Git Bash 块

**类型**：手册缺陷　**严重度**：低

**现象**
统计两份手册的代码块语言分布：

```text
操作手册：powershell 28 块、python 33 块、yaml 3 块、bash 0 块
说明手册：python 13 块、text 5 块、javascript 4 块、bash 0 块
```

全文搜不到 "Git Bash" 字样。

**定位**
阶段 7 之后用户主要用 PowerShell 跑命令（阶段 7 的痛点正是 bash 命令在 PS 里报错），所以阶段 8 手册干脆只写了 PowerShell。**方向是对的，但覆盖不全**——用户两个终端都在用。

**解决**
本阶段**未改动**（收官阶段重排 28 个代码块风险大于收益）；在问题记录里登记为待补项。最终完整版 4.1/4.2 的补提交与 `.gitignore` 修复命令**已给双终端版本**（PowerShell + Git Bash），作为补偿。

**验证**
最终完整版第 4 章所有可执行步骤均有两套命令。

**预防**
**每步双代码块**（bash + powershell）是开工技能的硬性要求，禁止写"PowerShell 命令完全一样"。本阶段属于回归，下一阶段开工时必须补齐。

---

### 问题 5：手册写"不加 --pool=solo 报 OSError"，实测是 WinError 5

**类型**：手册缺陷　**严重度**：低

**现象**
操作手册 26.1 第 1 条写："Windows 上必须 `--pool=solo`。不加就报错退出，而且日志可能只有一句不痛不痒的 `OSError`。"

**定位**
收官时实测（故意不加 `--pool=solo` 起 worker）：

```
PermissionError: [WinError 5] 拒绝访问。
  File "<string>", line 1, in <module>
    from billiard.spawn import spawn_main; spawn_main(parent_pid=26048, pipe_handle=840)
  File "...\billiard\reduction.py", line 165, in detach
    return _winapi.DuplicateHandle(
```

真实报错是 **`PermissionError: [WinError 5] 拒绝访问`**，来自 billiard 的多进程 spawn，不是 `OSError`（虽然 `PermissionError` 是 `OSError` 的子类，但**用户拿 "OSError" 去搜是搜不到答案的**——搜出来全是别的东西）。

**解决**
在《理解手册》第 6.1 节写实测原文（含完整 traceback 片段），并注明"手册里原话写的是 OSError，实测是 PermissionError [WinError 5]，来自 billiard 的多进程 spawn"。

**验证**
实测复现成功（`timeout 25 ... worker --loglevel=info -n nopool@%h` → exit 124，日志含 WinError 5）。

**预防**
**手册里凡是写"会报 XXX 错"，必须真的触发一次把原文抄下来**，不许凭印象写错误类型。这条要写进开工技能。

---

### 问题 6：`.gitignore` 被写成 UTF-16LE，git 当二进制处理

**类型**：环境　**严重度**：中

**现象**

```bash
$ git diff .gitignore
diff --git a/.gitignore b/.gitignore
index 53c9fc4..e2b0604 100644
Binary files a/.gitignore and b/.gitignore differ      # ← git 把它当二进制了
```

**定位**
用 Python 读原始字节：

```text
bytes: 631   has NUL: True   CRLF: 0   LF: 63
尾部：...health.json\n~\x00\\\x00$\x00*\x00\r\x00\n\x00venv/\nvenv/\n__pycache__/\n...
```

`~\x00\\\x00$\x00*\x00` 就是 UTF-16LE 编码的 `~\$*\r\n`——文件尾部被插入了一段 UTF-16LE 文本，NUL 字节让 git 判定为二进制。
根因：**PowerShell 5.1 的 `>` / `Add-Content` 默认编码是 UTF-16LE**，用它往 `.gitignore` 追加内容就会混入 NUL。

**解决**
一次性用 **UTF-8 无 BOM** 重写整个 `.gitignore`（完整命令见最终完整版 4.2，PowerShell 版用 `[System.IO.File]::WriteAllLines(..., New-Object System.Text.UTF8Encoding($false))`，Git Bash 版用 `cat > .gitignore <<'EOF'`）。

**验证**

```text
修复后预期：
  git diff --stat .gitignore   → 正常显示文本 diff，不再是 "Binary files differ"
  git status --porcelain       → 只剩 "M .gitignore"，不再有 "?? .venv3/"
```

**预防**
**改 `.gitignore` / 任何配置文件，一律用 Git Bash 的 `cat > file <<'EOF'`，或 PowerShell 显式指定 `-Encoding utf8`。** 绝不用裸 `>` 或 `Add-Content` 追加。

---

### 问题 7：`.gitignore` 仍没有 `.venv3`（阶段 7 遗留未闭环）

**类型**：收官遗留　**严重度**：**高**

**现象**

```bash
$ git status --porcelain
?? .venv3/        # ← 虚拟环境目录，几万个文件，还没被忽略
```

**定位**
当前项目的虚拟环境目录名是 `.venv3`（Python 3.13.14），而 `.gitignore` 里只有 `.venv` 和 `venv/`——**`.venv3` 匹配不上**。这个问题在阶段 7 收官时就发现了，当时只在文档里给了命令，没有闭环。

**解决**
随问题 6 一起修（重写 `.gitignore`，忽略列表补 `.venv3`）。

**验证**

```powershell
git check-ignore -v .venv3      # 预期输出：.gitignore:11:.venv3	.venv3
git status --porcelain          # 预期：?? 里不再有 .venv3/
```

**预防**
① **`.gitignore` 的忽略项要跟 `ls -d .venv*` 的实际目录名逐一对照**；② 收官时"待用户执行"的事项，下一阶段开工前必须先复查是否闭环——**给了命令 ≠ 已经修好**。

---

### 问题 8：10 份 md 手册未纳入 git

**类型**：收官遗留　**严重度**：中

**现象**

```bash
$ git status --porcelain | grep '??'
?? AI私厨_v3.0_阶段总表_实际执行版.md
?? AI私厨_v3.0_阶段7_..._操作手册.md
?? AI私厨_v3.0_阶段7_..._说明手册.md
?? AI私厨_v3.0_阶段7_最终完整版.md
?? AI私厨_v3.0_阶段7_理解手册_大白话与图解.md
?? AI私厨_v3.0_阶段7_问题与解决记录.md
?? AI私厨_v3.0_阶段8_..._操作手册.md
?? AI私厨_v3.0_阶段8_..._说明手册.md
?? AI私厨_v3.0_阶段8_理解手册_大白话与图解.md
?? AI私厨_v3.0_阶段8_最终完整版.md
?? AI私厨_v3.0_阶段8_问题与解决记录.md
?? 阶段6_13.2_灰度开关_详细执行手册.md
?? 阶段6_验收脚本与LangSmith报错_修复手册.md
```

**定位**
提交 `7b5547c` 只 `git add` 了代码/配置/测试/脚本（47 个文件），文档一份都没加。与阶段 7 同病：代码提交和文档提交分两次做，文档那次总是被忘。

**解决**
最终完整版 4.1 给了**逐个显式 `git add`** 的完整清单（PowerShell 13 行 + Git Bash 循环版），并明确禁止 `git add .`（因为 `.venv3` 还没被忽略）。

**验证**
执行后 `git status --porcelain` 预期只剩 ` M .gitignore`。

**预防**
**收官清单里"提交完整性"必须是第一项**，且检查方式是 `git status --porcelain` 的 `??` 列表与 `git show --stat HEAD` 对照——只看"`git commit` 成功了"是不够的。

---

### 问题 9：`app_my/api/_debug.py` 临时 500 触发器仍未删（跨阶段遗留）

**类型**：收官遗留　**严重度**：中

**现象**

```python
# app_my/api/_debug.py（仍在本分支里）
"""
阶段 7 验证用：临时 500 触发器
测试完删除整个文件
"""
@router.get("/debug/500")
async def debug_500():
    raise HTTPException(status_code=500, detail="阶段 7 告警测试用，看完删")
```

**定位**
阶段 7 为了验证"错误率告警"临时加的路由。当前 `main.py` 第 123–124 行已把引用注释掉（`# from app_my.api import _debug`），所以**运行时无害**——但文件还在版本库里，一旦哪天有人取消注释，就等于在生产埋了一个"点一下就 500 + 触发告警"的地雷。阶段 7 收官时就列为遗留，本阶段仍未清理。

**解决**

```powershell
Remove-Item .\app_my\api\_debug.py
```

```bash
rm app_my/api/_debug.py
```

**验证**
删除后 `pytest -q` 仍应 `118 passed`（该文件未被任何测试引用）。

**预防**
**所有"验证用临时路由/脚本"，文件名加 `_debug` / `_verify` 前缀**，并在收官清单里单列一条"临时文件是否复原"。带前缀才能在收官时一眼扫出来。

---

### 问题 10：临时脚本 `_verify_wsjs.js` 混进了提交

**类型**：工作区残留　**严重度**：低

**现象**

```bash
$ git show --name-only --format="" HEAD | head -1
_verify_wsjs.js          # ← 项目根目录出现一个 .js 文件，且已入库
```

**定位**
阶段 8 写 `frontend/js/ws.js` 时，为了"不用浏览器也能验证语法"，临时在根目录写了这个 Node 校验脚本（68 行）。验证完忘了删，`git add` 时被一起提交。

**解决**

```powershell
Remove-Item .\_verify_wsjs.js
```

```bash
rm _verify_wsjs.js
```

同时已在最终完整版 4.2 的新 `.gitignore` 里登记 `_verify_wsjs.js`，防止再被误 add。

**验证**
`git status --porcelain` 不再出现该文件；`pytest -q` 仍 `118 passed`。

**预防**
**临时验证脚本一律写进系统临时目录或 `.gitignore` 已覆盖的目录**，不要落在项目根目录；`git add` 前先 `git status` 扫一遍 `??` 列表。

---

### 问题 11：版本库里有两个 0 字节的 `-H` / `-d` 垃圾文件

**类型**：工作区残留　**严重度**：低

**现象**

```bash
$ git ls-files | grep '^-'
-H
-d
$ ls -la -- "-H" "-d"
-rw-r--r-- 1 11 197121 0 Oct 14 16:17 -H
-rw-r--r-- 1 11 197121 0 Oct 14 16:17 -d
```

**定位**

```bash
$ git log --diff-filter=A --format="%h %s" -- "-H"
621fb9f feat(v3-stage5): PgBouncer连接池+多级缓存...
```

两个 0 字节文件，是**阶段 5 误提交**的：某次 `curl -H "..." -d "..."` 在 Git Bash 里引号被吃掉，shell 把 `-H` 和 `-d` 后面的内容当成了文件名，于是创建了这两个空文件，随后被 `git add .` 收进仓库。

**解决**

```powershell
git rm --cached -- "-H" "-d"; Remove-Item -- "-H","-d"
```

```bash
git rm --cached -- -H -d && rm -- -H -d
```

**验证**

```bash
git ls-files | grep '^-'      # 预期：无输出
```

**预防**
① **以 `-` 开头的文件名一律用 `--` 分隔符**（`rm -- -H`），否则会被命令当成参数；② 根目录出现"看起来像命令行参数"的文件时，先怀疑是命令引号没配对。

---

### 问题 12：12 个测试用例依赖后端在线，后端没起会误判为代码回归

**类型**：环境　**严重度**：中

**现象**
收官第一次跑全量测试：

```text
FAILED tests/integration/test_billing_api.py::test_billing_stats_requires_auth
FAILED tests/test_auth.py::test_me_without_token - requests.exceptions.ConnectionError
FAILED tests/test_health.py::test_health_ok - requests.exceptions.ConnectionError
FAILED tests/test_trace.py::test_trace_id_generated - requests.exceptions.ConnectionError
...
6 failed, 106 passed, 7 deselected, 3 warnings, 6 errors in 32.93s
```

**定位**
这 12 个（`test_health` / `test_auth` / `test_trace` / `test_billing_api`）都用 `conftest.py` 的 `base_url` 夹具连 `http://127.0.0.1:9002`——**后端没起，全都是 `ConnectionError`，与代码无关**。起后端后：

```text
118 passed, 7 deselected, 3 warnings in 9.55s
```

**解决**
无需改代码。收官流程里把"起后端"列为跑测试的前置步骤；并在最终完整版 4.3 明确写出这条警示。

**验证**

```powershell
& ".\.venv3\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 9002
# 另开一个终端
.\.venv3\Scripts\python.exe -m pytest -q        # 118 passed, 7 deselected
```

**预防**
**看到 `ConnectionError` / `ConnectionRefused` 先确认被测服务是否在线，不要先去改代码。** 更好做法：给这批用例打 `@pytest.mark.needs_server`，默认跳过，避免误导。

---

## 五、修改清单总表

### 5.1 代码（阶段 8 新建 26 / 修改 5，全部在 `7b5547c`）

| 文件 | 类型 | 说明 |
|---|---|---|
| `app_my/worker/celery_app.py` | 🟢 新建 | Celery 实例 + 三条队列 + 分级路由 + `imports` |
| `app_my/worker/base.py` | 🟢 新建 | `NotifyTask` 基类：三回调发事件 + 打点 |
| `app_my/worker/signals.py` | 🟢 新建 | worker 就绪信号：起 9101 指标服务 + 刷队列深度 |
| `app_my/worker/tasks/{reindex,graph,nutrition}.py` | 🟢 新建 | 三个长任务，分别落 high / default / low |
| `app_my/core/notify.py` | 🟢 新建 | 事件构造 + Redis publish（失败吞异常） |
| `app_my/core/worker_metrics.py` | 🟢 新建 | 4 个 `celery_*` 指标 + HTTP 指标服务 |
| `app_my/schemas/tasks.py`、`app_my/api/tasks.py` | 🟢 新建 | 3 个提交接口 + 1 个查询接口 + 数据模型 |
| `app_my/ws/{manager,gateway,relay}.py` | 🟢 新建 | 连接池 / 鉴权网关 / Redis 订阅中继 |
| `frontend/js/ws.js`、`frontend/stage8-tasks.html` | 🟢 新建 | 浏览器 WS 客户端 + 演示页 |
| `app_my/core/config.py` | 🔵 修改 | 加 6 个配置（broker / backend / eager / 过期 / 9101 / 频道） |
| `main.py` | 🔵 修改 | 注册路由 + lifespan 起停 relay |
| `requirements.txt` | 🔵 修改 | 登记 celery / websockets |

### 5.2 配置

| 文件 | 类型 | 说明 |
|---|---|---|
| `docker/prometheus/prometheus.yml` | 🔵 修改 | 新增 job `ai_chief_worker`（`host.docker.internal:9101`） |
| `docker/prometheus/alerts.yml` | 🔵 修改 | 新增 2 条告警（任务失败率 / 队列积压），总计 4 → 6 条 |
| `.gitignore` | ⚠️ 待修 | 需 UTF-8 重写 + 补 `.venv3` + 登记临时文件（见 4.2） |

### 5.3 测试与脚本

| 文件 | 类型 | 说明 |
|---|---|---|
| `tests/unit/test_celery_app.py` | 🟢 新建 | 6 例（序列化 / eager 执行真的算 / 空输入报错） |
| `tests/unit/test_notify.py` | 🟢 新建 | 4 例（事件形状 / 失败携带 error / Redis 挂了返回 0） |
| `tests/unit/test_task_api.py` | 🟢 新建 | 7 例（鉴权 / 队列分级 / 状态查询） |
| `tests/unit/test_ws_gateway.py` | 🟢 新建 | 4 例（无 token / refresh / 垃圾 token 全拒 + ping-pong + 收到推送） |
| `tests/unit/test_ws_manager.py` | 🟢 新建 | 6 例（租户隔离 / 死连接清理 / 重复断开幂等） |
| `scripts/verify_stage8.py` | 🟢 新建 | routing / e2e 两种验收模式 |
| `scripts/check_stage8_routes.py` | 🟢 新建 | 路由自检（matched: 5） |
| `_verify_wsjs.js` | ⚠️ 待删 | 临时脚本，误入提交 |

### 5.4 文档（本阶段新增 / 修改）

| 文件 | 说明 |
|---|---|
| `AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_操作手册.md` | 🔵 修改：**目录 28 条锚点全部重算**（原 13 条悬空） |
| `AI私厨_v3.0_阶段8_Celery异步任务与WebSocket推送_说明手册.md` | 🔵 修改：**目录 22 条锚点重算**（原 1 条悬空） |
| `AI私厨_v3.0_阶段8_最终完整版.md` | 🟢 新建：收官信息 + 顺序对照表 + 补充四条 + 两份手册合并（6639 行） |
| `AI私厨_v3.0_阶段8_理解手册_大白话与图解.md` | 🟢 新建：9 章，486 行（比喻 / 全景图 / 七步走 / 联动图 / 时序图 / Q&A / 面试话术） |
| `AI私厨_v3.0_阶段8_问题与解决记录.md` | 🟢 新建：本文件 |

---

## 六、经验教训

1. **目录锚点必须脚本生成，绝不手写。** CJK 标题 + emoji 的组合下，"emoji 后面有没有空格"会直接决定锚点是单连字符还是双连字符。本阶段 14 条悬空全是这么来的。交付前跑一次"标题 vs 目录链接"比对脚本，成本 30 秒。
2. **手册里写"会报 XXX 错"必须真触发一次。** 本阶段"OSError vs PermissionError [WinError 5]"就是一个典型：凭印象写的错误类型，用户拿去搜会搜到完全不同的东西。
3. **"给了命令"≠"已闭环"。** 阶段 7 收官时发现 `.gitignore` 缺 `.venv3`，只在文档里给命令 → 阶段 8 收官时发现不但没修，还因为用 PowerShell 追加引入了 UTF-16 编码问题。收官清单里的"待用户执行"项，下一阶段开工前必须复查。
4. **PowerShell 5.1 的 `>` / `Add-Content` 默认 UTF-16LE——改任何配置文件都要显式指定 UTF-8。** 判断方法：`git diff` 一出 `Binary files differ`，先查 NUL 字节。
5. **收官第一件事是 `git status --porcelain` + `git show --stat HEAD` 对照。** "commit 成功了"不代表该进的都进去了——本阶段代码 47 个文件全在，但 10 份文档一份没进。
6. **临时文件的命名要能被一眼扫出来。** `_debug.py`、`_verify_*.js` 这类前缀命名，让本阶段收官时能快速列出清理清单。反例是 `-H` / `-d`：看起来像命令行参数，实际是引号没配对产生的垃圾。
7. **看到 `ConnectionError` 先确认服务在线。** 本阶段第一次跑测试拿到 `6 failed + 6 errors`，全是后端没起——差点被当成代码回归去查。
8. **两份手册排序原则不同是允许的，但必须附顺序对照表。** 操作手册按执行顺序、说明手册按理解顺序，各有道理；代价是读者要跨序号定位。一张 16 行的对照表就能解决。

---

> **下一步**：按《AI私厨_v3.0_阶段8_最终完整版.md》第 4 章执行补提交（4.1）、`.gitignore` 重写（4.2）、临时文件清理（4.3），然后再提 PR。
> **再下一步**：阶段 9 = 微服务拆分 + Kong 网关（9100）。提前记住两件事——Kong 转发 WebSocket 必须显式配 `Upgrade` / `Connection` 头；worker 建议先不拆（它本来就是独立进程，拆成独立仓库收益小、同步成本高）。
