# AI 私厨 v3.0 · 阶段 10 最终完整版（性能压测 + CI/CD + 生产级部署）

> 本文件 = **封面 + 收官信息 + 总目录 + 补充说明** + **操作手册原文** + **说明手册原文**。
> 前四章是收官时新写的（现场核实出来的问题与待办），后面两部分是开工时交付的两份手册原文，一字未改。

---

## 封面：收官信息（2026-10-21 现场实测）

| 项 | 实测结果 |
|---|---|
| 阶段 / 内容 | **10 / 10** —— Locust 性能压测（单体 vs 微服务）+ Gitee Go CI/CD + 生产级部署（gunicorn + 非 root + 资源上限 + 日志轮转） |
| 分支 | `feat/v3-stage10` |
| 收官日期 | 2026-10-21 |
| 最新提交 | `49371f8 feat: v3-stage10 完成阶段功能，新增mock llm、benchmark、docker部署脚本与单元测试`（**57 个文件**） |
| 测试基线（tests/unit） | **124 → 141 passed**（+8 打桩 +9 报告） |
| 测试基线（全量） | **157 passed, 7 deselected** |
| 端到端验证 | `python scripts/verify_stage10.py --bench-dir reports/bench_20261021_171618` → **33 项全部 OK** |
| 压测 | 8 轮（单体 + 网关 × 10/20/40/60 并发），**失败率全部 0.00%** |
| 压测结论 | 单体拐点 **60 并发**（P99 3900ms）；微服务同档 P99 **530ms**，未劣化；登录场景 60 并发 **2700ms → 390ms（-86%）** |
| 生产部署 | 5 个容器（kong + 4 服务）**全部 Up (healthy)**；走 Kong 9100 端到端：错误凭据 401 ✓、token 299 字符 ✓、图谱真实推理 ✓、对话真实 LLM ✓ |
| CI 本地等价验证 | `bash scripts/ci_local.sh` → **6 步全部 PASS** |
| 容器现状 | 开发栈 17 个容器在跑（Kong `Up 43 minutes (healthy)`）；生产栈 5 个容器验证通过后已停 |
| 🔴 git 完整性 | **三份手册 md 与 `压测报告.md` 从未入库**（`.gitignore:10` 的 `*.md` 规则），详见第一章 |

### 这份文档怎么用

| 你想干什么 | 看哪部分 |
|---|---|
| 动手做（步骤 / 命令 / 预期输出） | **第一部分：操作手册** |
| 看不懂某行代码 | **第二部分：说明手册**（含 30 个专业名词解释表） |
| 忘了全貌、想看图解 | 同目录下的 `AI私厨_v3.0_阶段10_理解手册_性能压测与CI-CD.md`（大白话 + ASCII/Mermaid 双份图，9 章） |
| 提交 / 提 PR 前要补的事 | **下面第一～三章**（收官新增） |
| 排错 | 第一部分 §十八 错误对照表（37 行）+ 同目录下的《问题与解决记录》 |

---

## 总目录

- [封面：收官信息（2026-10-21 现场实测）](#封面收官信息2026-10-21-现场实测)
- [一、补充说明：git 提交完整性（🔴 必做）](#一补充说明git-提交完整性-必做)
- [二、补充说明：.gitignore 漏项与编码损坏](#二补充说明gitignore-漏项与编码损坏)
- [三、补充说明：收尾清理项](#三补充说明收尾清理项)
- [四、补充说明：一句话验收结论](#四补充说明一句话验收结论)
- [第一部分：操作手册（照着做）](#第一部分操作手册照着做)
- [第二部分：说明手册（看懂为什么）](#第二部分说明手册看懂为什么)

---

## 一、补充说明：git 提交完整性（🔴 必做）

### 1.1 实测发现了什么

```
$ git status --porcelain          # 工作区"干净"
（无输出）

$ git show --name-only --format="" HEAD | wc -l
57

$ git log --diff-filter=A --name-only --format="" | grep -i "\.md$" | sort -u
README.md                          # ← 全仓库历史只提交过这一个 md
```

**工作区干净 ≠ 提交完整**。三份手册和压测报告被 `.gitignore` 静默忽略了，`git status` 根本不显示它们，所以看着"什么都提交了"，其实 PR 里一份文档都没有。

### 1.2 补提交的完整清单

**Git Bash：**

```bash
cd /f/pycharm_aiprogram/ai_chief
git add -f "AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md" \
         "AI私厨_v3.0_阶段10_说明手册_性能压测与CI-CD.md" \
         "AI私厨_v3.0_阶段10_理解手册_性能压测与CI-CD.md" \
         "reports/bench_20261021_171618/压测报告.md"
git status --short
```

**PowerShell 5.1：**

```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
git add -f "AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md"
git add -f "AI私厨_v3.0_阶段10_说明手册_性能压测与CI-CD.md"
git add -f "AI私厨_v3.0_阶段10_理解手册_性能压测与CI-CD.md"
git add -f "reports/bench_20261021_171618/压测报告.md"
git status --short
```

**预期输出**（4 行 A = 新增待提交）：

```
A  AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md
A  AI私厨_v3.0_阶段10_说明手册_性能压测与CI-CD.md
A  AI私厨_v3.0_阶段10_理解手册_性能压测与CI-CD.md
A  reports/bench_20261021_171618/压测报告.md
```

> 🟡 `-f`（force）是**绕过** `*.md` 规则的临时办法。长期请按第二章把 `.gitignore` 改对，否则下次阶段还会再漏一次。

---

## 二、补充说明：.gitignore 漏项与编码损坏

### 2.1 两个问题（都是实测出来的）

| # | 问题 | 实测证据 |
|---|---|---|
| 1 | **第 10 行 `*.md` 忽略所有 Markdown** | `git check-ignore -v "AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md"` → `.gitignore:10:*.md` |
| 2 | **第 52~54 行含 NUL 字节，文件被 git 当二进制** | `git show --stat HEAD -- .gitignore` → ` .gitignore \| Bin 527 -> 649 bytes, 1 file changed, 0 insertions(+), 0 deletions(-)`；Python 读原始字节确认第 52 行为 `'~\x00\\\x00$\x00*\x00'` |

问题 2 是 PowerShell 用 `>` / `Add-Content` 追加内容留下的 **UTF-16LE 残迹**（NUL 字节混进 UTF-8 文本）。后果：`git diff` 显示 `Binary files differ`，改了什么看不出来。

### 2.2 修法（任选一种终端，改完立刻能验证）

**方案 A：Git Bash（推荐，不会产生编码问题）**

```bash
cd /f/pycharm_aiprogram/ai_chief
# ① 先把带 NUL 的三行整段替换掉，并把 *.md 改成只忽略 tmp 下的 md
python - <<'EOF'
from pathlib import Path
p = Path(".gitignore")
lines = [l for l in p.read_text(encoding="utf-8").splitlines() if "\x00" not in l]
out = []
for l in lines:
    if l.strip() == "*.md":
        out.append("# *.md  ← 原规则会忽略手册/报告，已改为只忽略 tmp 下的草稿")
        out.append("tmp/*.md")
    else:
        out.append(l)
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("已重写，剩余行数:", len(out))
EOF
# ② 验证
git diff --stat -- .gitignore          # 不再是 "Bin ..." 就是修好了
git check-ignore -v "AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md" || echo "手册不再被忽略 ✅"
```

**方案 B：PowerShell 5.1（必须用 UTF8Encoding($false)，否则又会写成 UTF-16LE）**

```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
$lines = Get-Content .gitignore -Encoding UTF8 | Where-Object { $_ -notmatch "\x00" }
$out = foreach ($l in $lines) {
    if ($l.Trim() -eq "*.md") { "# *.md  ← 原规则会忽略手册/报告"; "tmp/*.md" } else { $l }
}
[System.IO.File]::WriteAllLines("$PWD\.gitignore", $out, (New-Object System.Text.UTF8Encoding($false)))
git diff --stat -- .gitignore
git check-ignore -v "AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md"
```

**预期输出**：

```
 .gitignore | 4 +-
 1 file changed, 2 insertions(+), 2 deletions(-)
手册不再被忽略 ✅          # check-ignore 无输出（退出码 1）
```

---

## 三、补充说明：收尾清理项

| # | 检查项 | 实测结果 | 处理 |
|---|---|---|---|
| 1 | `docker/kong/kong.yml.bak`（压测前备份） | **已被提交进 49371f8** | 🟡 建议删除并加进 `.gitignore`：`rm -f docker/kong/kong.yml.bak` |
| 2 | `tmp/compare.md`（阶段 9 遗留） | 757 字节，**仍在**（阶段 9 最终完整版第 4 章记过这项，未闭环） | 🟡 `rm -f tmp/compare.md` |
| 3 | `docker/kong/kong.yml` 限流值 | **已恢复 600/300/300/120** ✅ | 无需处理（§17.1 已闭环） |
| 4 | `MOCK_LLM` 开关 | **已关闭**（17.3 实测对话返回真实 LLM 内容）✅ | 无需处理 |
| 5 | 生产容器 | 验证通过后**已停**（5 个） | 需要就 `docker compose -f docker/docker-compose.prod.yml up -d` |
| 6 | 一次性容器残留（`run-` 前缀） | `docker ps -a` 无残留 ✅ | 无需处理 |
| 7 | 压测残留账号 | 已清理 **549 个 `bench_` 账号**（579 → 30）✅ | 后续测试账号 `stage10check11`/`prodcheck2` 可手动删 |
| 8 | 试水轮目录 `reports/bench_20261021_171316` | 只有 u5 四个 CSV | 🟡 可删：`rm -rf reports/bench_20261021_171316` |
| 9 | 代码里的临时开关 / 调试路由 | 无 ✅ | 无需处理 |

**一键清理（Git Bash）**：

```bash
rm -f docker/kong/kong.yml.bak tmp/compare.md
rm -rf reports/bench_20261021_171316
git status --short
```

**PowerShell 5.1**：

```powershell
Remove-Item docker\kong\kong.yml.bak -ErrorAction SilentlyContinue
Remove-Item tmp\compare.md -ErrorAction SilentlyContinue
Remove-Item reports\bench_20261021_171316 -Recurse -Force -ErrorAction SilentlyContinue
git status --short
```

---

## 四、补充说明：一句话验收结论

> **阶段 10 目标全部达成**：用 Locust 在 Mock LLM 模式下测出**单体 60 并发出现拐点（P99 3900ms）、微服务同档仅 530ms**，把阶段 9 的"微服务拆分"从"架构上更优雅"变成了"**有数据支撑的性能收益**"（登录场景 P99 -86%）；同时补齐了**生产级部署**（gunicorn 多 worker + 非 root + 资源上限 + 日志轮转）和 **CI/CD**（Gitee Go 流水线 + 本地等价验证脚本），33 项验收全 OK、单测 141 passed、全量 157 passed。
>
> **提 PR 前只剩两件事**：① 按第一章补提交 4 个 md；② 按第二章修 `.gitignore` 的 `*.md` 与 NUL 字节。

---

# 第一部分：操作手册（照着做）

## 性能压测 + CI/CD + 生产级部署

> **本手册怎么用**：从上往下做，一步一步来。每个代码块都写清楚了"在哪个路径建文件、内容是什么"，你只要新建文件、把内容整段粘贴进去保存即可。
> 每一步后面都跟着**验证命令（Git Bash + PowerShell 两版）**、**预期输出（本次实机实测原文）**和**排错提示**。
>
> **动手之前先记住三件事**：
> 1. **所有 Python 命令都用 `./.venv3/Scripts/python.exe`（或 `.\.venv3\Scripts\python.exe`）**，不要写裸 `python`。你机器上装过 Anaconda，裸 `python` 会命中 3.6 版本，读 UTF-8 配置文件时按 GBK 解，直接报 `UnicodeDecodeError`，报错栈看着像"测试挂了"，其实是解释器错了。
> 2. **本文所有"预期输出"都是 2026-10-20 在你这台机器上真跑出来的原文**，不是设计出来的。你看到的数字应该和这里一致；不一致时，以你实测的为准，并回头看排错提示。
> 3. **压测会改 2 个地方**：重启 5 个服务（带 mock 开关）、临时调高 Kong 网关限流。第六节和第十四节给了恢复步骤，别跳过。

---

## 目录

- [一、阶段目标与验收标准](#一阶段目标与验收标准)
- [二、简历叙事（照写）](#二简历叙事照写)
- [三、范围与原方案差异](#三范围与原方案差异)
- [四、端口、资源与文件归属](#四端口资源与文件归属)
- [五、文件清单](#五文件清单)
- [六、准备：切分支、备份、装依赖、核基线](#六准备切分支备份装依赖核基线)
- [七、落盘代码（一）：给大模型调用装上开关与打桩器](#七落盘代码一给大模型调用装上开关与打桩器)
- [八、落盘代码（二）：压测脚本](#八落盘代码二压测脚本)
- [九、落盘代码（三）：压测编排与报告生成](#九落盘代码三压测编排与报告生成)
- [十、落盘代码（四）：生产级部署](#十落盘代码四生产级部署)
- [十一、落盘代码（五）：CI/CD 与本地等价验证](#十一落盘代码五cicd-与本地等价验证)
- [十二、落盘代码（六）：验收脚本](#十二落盘代码六验收脚本)
- [十三、跑压测：前置条件](#十三跑压测前置条件)
- [十四、跑压测：正式执行](#十四跑压测正式执行)
- [十五、生产部署实测](#十五生产部署实测)
- [十六、CI 本地验证与提交](#十六ci-本地验证与提交)
- [十七、恢复现场（压测后必做）](#十七恢复现场压测后必做)
- [十八、常见错误对照表](#十八常见错误对照表)
- [十九、避坑提示](#十九避坑提示)
- [二十、防呆自检清单](#二十防呆自检清单)
- [附录 A：文件清单速查](#附录-a文件清单速查)
- [附录 B：本次实测数据原文](#附录-b本次实测数据原文)
- [附录 C：PowerShell 5.1 等价替换速查表](#附录-cpowershell-51-等价替换速查表)

---

## 一、阶段目标与验收标准

这个阶段要回答一个问题：**「微服务拆分 + 网关」到底带来了什么？** 并且把结论变成能写进简历、扛得住面试追问的实测数字。

具体四件事：

| # | 做什么 | 怎么算完成 | 判定方式 |
|---|---|---|---|
| 1 | 把大模型调用换成可打桩的开关 | `MOCK_LLM=true` 时全程零外部调用 | `grep dashscope 服务日志` 结果为 0 |
| 2 | 写 Locust 压测脚本（三场景） | 登录 / 对话 / 图谱问答都能压 | `locust --list` 能看到 `BenchUser` |
| 3 | 单体 vs 网关对比压测 + 阶梯加压找拐点 | 两组数据齐全，能算出拐点 | `scripts/locust_report.py` 出报告 |
| 4 | 生产级部署 + CI/CD | 镜像能构建、compose 能起、流水线命令本机全通 | `docker compose config` 退出码 0 |

**验收清单**（做完逐条打勾，全勾了才算这个阶段收官）：

- [ ] `pytest tests/unit` → **141 passed**（阶段 9 是 124，新增 17）
- [ ] `scripts/verify_stage10.py` → **验收通过：33 项全部 OK**
- [ ] 压测产出 8 个 CSV（单体 4 档 + 网关 4 档），`压测报告.md` 三张表齐全
- [ ] 报告里能读出：单体拐点 = 60 并发；网关最高档未劣化
- [ ] `docker compose -f docker/docker-compose.prod.yml config` 退出码 0
- [ ] `bash scripts/ci_local.sh` 全 PASS

---

## 二、简历叙事（照写）

> **AI 私厨 v3.0 · 性能工程与工程效能**（个人项目，单机 Docker 环境）
>
> - 用 **Locust** 设计三场景压测（登录 / 流式对话 / 图谱多跳推理），对**拆分前后的两套架构做同脚本对比**，阶梯加压定位性能拐点：单体架构在 **60 并发**时 P99 从 290ms 劣化到 **3900ms**，而拆分后的微服务架构同一档位 P99 仅 **670ms**（劣化 5.8 倍），定位到瓶颈是单进程内 bcrypt 密码哈希的 CPU 争抢，拆分后被分摊到 4 个进程。
> - 建立**性能打桩机制**（`MOCK_LLM` 开关 + 统一出口早返回），把大模型调用从压测链路中摘除，使压测结果只反映自身架构容量、可重复复现，避免被外部模型服务的波动污染。
> - 用 **Gitee Go** 建 CI 流水线（单测 → 配置校验 → 镜像构建），并提供本地等价验证脚本保证"流水线里的命令在本机就能跑通"，把"CI 挂了才发现"变成"提交前就知道"。
> - 生产部署用 **Docker Compose + gunicorn（多 worker / ASGI worker 类）**，配健康检查、资源上限与日志轮转；容器非 root 运行。

面试追问预案见《说明手册》附录与《理解手册》第九章。

---

## 三、范围与原方案差异

| # | 内容 | 标签 | 说明 |
|---|---|---|---|
| 1 | Locust 压测脚本（三场景） | 🟢 新增 | 原规划就写了"登录/对话/推荐"，落到 `benchmarks/locustfile.py` |
| 2 | 压测报告（QPS / P99 / 错误率拐点） | 🟢 新增 | 新增 `scripts/locust_report.py` 自动汇总，不手抄数字 |
| 3 | CI/CD 流水线 | 🔵 修改 | 原规划写"Gitee Go 或 GitHub Actions"，按你的仓库在 Gitee，选 Gitee Go |
| 4 | 单体 vs 微服务对比压测 | 🟣 补充 | 原规划只说"拆分前后 P99/QPS 对比"（阶段 7 手册里欠下的账），这次用同一份脚本打两个目标补上 |
| 5 | **LLM 打桩机制** | 🟢 新增 | 原规划没提。不做的话压测数字里混着外部模型耗时，结论不可复现 |
| 6 | **生产级部署** | 🟣 补充 | 《整体规划》第 80 行写了"主线用 Docker Compose 生产级部署收官"，但没定义内容，这里补齐 |
| 7 | **向量打桩（embedding）** | 🟢 新增 | 实测时发现 embedding 是热路径上漏网的外部调用，不打桩的话对话场景仍在真调外部服务 |
| 8 | 简历定稿 | 🔵 推迟 | 原规划把"简历定稿"放在本阶段末尾，改为随阶段收官一起出（沿用你阶段 8/9 的老规矩） |

🟡 **没做的**：K8s + Helm + HPA（原规划的"可选阶段 A"），本阶段不动。

---

## 四、端口、资源与文件归属

### 4.1 端口（本阶段不新增端口）

| 组件 | 端口 | 归属 | 本阶段是否改动 |
|---|---|---|---|
| 单体（对照目标） | 9002 | 阶段 8 之前的老入口 | 只重启（带 mock 开关） |
| user 服务 | 9121 | 阶段 9 | 只重启（带 mock 开关） |
| recognizer 服务 | 9122 | 阶段 9 | 只重启（带 mock 开关） |
| recommender 服务 | 9123 | 阶段 9 | 只重启（带 mock 开关） |
| chat 服务 | 9124 | 阶段 9 | 只重启（带 mock 开关） |
| Kong 网关 | 9100 / 9105 | 阶段 9 | 🔵 **临时调高限流，压测后恢复** |

### 4.2 资源分配（生产 compose）

| 服务 | APP_MODULE | 端口 | worker 数 | 内存上限 | 为什么这么分 |
|---|---|---|---|---|---|
| svc-user | `services.user.main:app` | 9121 | 2 | 768M | 登录走 bcrypt（`BCRYPT_ROUNDS=12`），CPU 密集，多核才划算 |
| svc-recognizer | `services.recognizer.main:app` | 9122 | 2 | 768M | 识别链路中等 |
| svc-recommender | `services.recommender.main:app` | 9123 | 3 | 768M | 图谱 + 向量检索是 IO 密集，多 worker 能把等待时间重叠掉 |
| svc-chat | `services.chat.main:app` | 9124 | 3 | 768M | 编排 + 流式长连接，单请求可能几十秒 |
| kong | — | 9100 / 9105 | — | 512M | 网关本身很轻 |

> 🔴 **worker 数不是越多越好**：每个 worker 是一个独立进程，各自带一份连接池和 L1 缓存。4 个 worker × 768M 上限意味着最坏情况能吃掉 3GB，16GB 机器上同时起 4 个服务会开始和数据库抢内存。实测里 recommender 的 IO 密集型确实需要更多 worker，但再多就要实测对比了。

### 4.3 文件归属

| 目录 | 本阶段新增/修改 |
|---|---|
| `app_my/core/` | 修改 `config.py`、`model_router.py`；新增 `mock_llm.py` |
| `app_my/knowledge/` | 修改 `embedding.py` |
| `benchmarks/` | 新增 `locustfile.py` |
| `scripts/` | 新增 `run_bench.sh`、`run_bench.ps1`、`locust_report.py`、`ci_local.sh`、`ci_local.ps1`、`verify_stage10.py` |
| `docker/` | 新增 `Dockerfile.svc`、`requirements.prod.txt`、`docker-compose.prod.yml`；**修改** `kong/kong.yml`（临时，压测后恢复） |
| `.gitee/workflows/` | 新增 `pipeline.yml` |
| `tests/unit/` | 新增 `test_stage10_mock_llm.py`、`test_stage10_bench_report.py` |
| `reports/` | 压测产物（建议加进 `.gitignore`，别把几十个 CSV 提交进仓库） |

---

## 五、文件清单

### 5.1 需要你新建/覆盖的业务代码（7 个文件）

| # | 文件 | 动作 | 手册位置 |
|---|---|---|---|
| 1 | `app_my/core/mock_llm.py` | 新建 | §7.1 |
| 2 | `app_my/core/config.py` | 修改（加 2 个配置项） | §7.2 |
| 3 | `app_my/core/model_router.py` | 修改（加打桩分支） | §7.3 |
| 4 | `app_my/knowledge/embedding.py` | 修改（加向量打桩） | §7.4 |
| 5 | `benchmarks/locustfile.py` | 新建 | §8.1 |
| 6 | `scripts/locust_report.py` | 新建 | §9.2 |
| 7 | `scripts/verify_stage10.py` | 新建 | §12.1 |

### 5.2 需要你新建/覆盖的脚本与配置（6 个文件）

| # | 文件 | 动作 | 手册位置 |
|---|---|---|---|
| 8 | `scripts/run_bench.sh` | 新建（Git Bash） | §9.1 |
| 9 | `scripts/run_bench.ps1` | 新建（PowerShell） | §9.3 |
| 10 | `scripts/ci_local.sh` | 新建（Git Bash） | §11.2 |
| 11 | `scripts/ci_local.ps1` | 新建（PowerShell） | §11.3 |
| 12 | `docker/Dockerfile.svc` | 新建 | §10.1 |
| 13 | `docker/requirements.prod.txt` | 新建 | §10.2 |
| 14 | `docker/docker-compose.prod.yml` | 新建 | §10.3 |
| 15 | `.gitee/workflows/pipeline.yml` | 新建 | §11.1 |

### 5.3 我已经直接写进你项目的（2 个文件）

> ✅ 这两个测试文件我已经放进 `F:\pycharm_aiprogram\ai_chief\tests\unit\`，你不用自己建：
> - `tests/unit/test_stage10_mock_llm.py`
> - `tests/unit/test_stage10_bench_report.py`
>
---

## 六、准备：切分支、备份、装依赖、核基线

这一节不做任何"阶段 10 的事"，只把工作台收拾干净。**四条全部做完再往下走**。

### 6.1 切一条新分支

为什么要切：阶段 10 会改 3 个已有业务文件（`config.py` / `model_router.py` / `embedding.py`）并临时改一次 Kong 限流，放在单独分支上，出问题能一键回退。

**Git Bash：**

```bash
cd /f/pycharm_aiprogram/ai_chief
git checkout -b feat/v3-stage10
git branch --show-current
```

**PowerShell 5.1：**

```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
git checkout -b feat/v3-stage10
git branch --show-current
```

**预期输出**（两版一致）：

```
feat/v3-stage10
```

> 🔴 如果你看到 `fatal: a branch named 'feat/v3-stage10' already exists`，说明之前建过。先确认分支上没有未提交的改动（`git status`），再 `git checkout feat/v3-stage10` 直接切过去即可。

### 6.2 把 Kong 网关配置恢复原值并备份

🔴 **先说清楚当前状态**：我（AI）在 2026-10-20 做阶段 10 的实跑验证时，为了跑通压测，**已经把你项目里 `docker/kong/kong.yml` 的限流调高了**（600→60000、300→30000、300→30000、120→12000）。这份改动**没有提交**，所以现在 `git status` 里它是 `M`。

也就是说：**你现在手里这份已经是"压测版"，不是原版**。原版（600/300/300/120）在 git 的 HEAD 里。

所以这一步要做的是"**先恢复到原版，再备份一份**"，而不是直接备份当前文件（那样备份到的会是压测版）。

**Git Bash：**

```bash
git checkout -- docker/kong/kong.yml
git diff --stat docker/kong/kong.yml
cp docker/kong/kong.yml docker/kong/kong.yml.bak
ls -l docker/kong/kong.yml.bak
```

**PowerShell 5.1：**

```powershell
git checkout -- docker/kong/kong.yml
git diff --stat docker/kong/kong.yml
Copy-Item docker\kong\kong.yml docker\kong\kong.yml.bak
Get-Item docker\kong\kong.yml.bak | Select-Object Name, Length
```

**预期输出**：

- `git diff --stat` **没有任何输出**（空 = 工作区和 HEAD 一致 = 已恢复原版）
- 备份文件存在、Length 不为 0

**顺手确认一下恢复后的值确实是原版**：

**Git Bash：**

```bash
grep -n "minute:" docker/kong/kong.yml
```

**PowerShell 5.1：**

```powershell
Select-String -Path docker\kong\kong.yml -Pattern "minute:" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
```

**预期输出**（本次实测原文）：

```
52:          minute: 600
66:          minute: 300
83:          minute: 300
108:          minute: 120
```

> 这四个数就是原版：**600 / 300 / 300 / 120**（每分钟）。第十三节压测时会临时调高，第十七节再调回来。
> 🔴 如果你这里看到的已经是 `60000`，说明 `git checkout` 没生效（可能文件被锁或你有别的未提交改动冲突），先 `git status` 看清楚再动手，别硬来。

### 6.3 装压测依赖（locust / gunicorn）

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -m pip install "locust==2.32.5" "gunicorn==23.0.0"
./.venv3/Scripts/python.exe -m locust --version
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe -m pip install "locust==2.32.5" "gunicorn==23.0.0"
.\.venv3\Scripts\python.exe -m locust --version
```

**预期输出**（本次实测原文）：

```
locust 2.32.5 from F:\pycharm_aiprogram\ai_chief\.venv3\Lib\site-packages\locust (Python 3.13.14)
```

> 🟡 **gunicorn 装上但装了也没法在 Windows 上跑**。这不是装错了：gunicorn 依赖 `fcntl` 模块（Unix 才有），Windows 上 `import gunicorn` 会直接 `ModuleNotFoundError: No module named 'fcntl'`。
> 它在本项目里的唯一用途是**打进 Linux 容器镜像里跑**（第十节）。所以：
> - 不要在本机试着启动 gunicorn，会失败；
> - 也不要因为"装了不能跑"就跳过安装——第十节的 `requirements.prod.txt` 需要它，第十五节构建镜像时会用。
>
> 验证它"装上了"（只看版本号，不启动）：
>
> **Git Bash：** `./.venv3/Scripts/python.exe -m pip show gunicorn | head -2`
> **PowerShell：** `.\.venv3\Scripts\python.exe -m pip show gunicorn | Select-Object -First 2`
>
> 预期看到 `Name: gunicorn` / `Version: 23.0.0`。

### 6.4 核基线：现有单测有多少个

为什么要核：**先记住"阶段 10 之前是多少个"**，才知道新增的测试是不是真的加进去了，而不是"跑通了但一个都没收集到"。

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -m pytest tests/unit -q 2>&1 | tail -5
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe -m pytest tests/unit -q 2>&1 | Select-Object -Last 5
```

**预期输出**（本次实测原文）：

```
ERROR tests/unit/test_stage10_bench_report.py
ERROR tests/unit/test_stage10_mock_llm.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
3 warnings, 2 errors in 2.90s
```

🔴 **看到这个不是坏了，是"还没开始"**。这两个测试文件是我上一轮已经写进你项目里的（§5.3 那两个），它们 `import app_my.core.mock_llm`，而这个模块要等你做完第七节才存在。所以现在必然报 `ModuleNotFoundError`。

**你要记录的数字是"排除这两个之后"的基线**。跑这条命令确认旧测试全绿：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -m pytest tests/unit -q --ignore=tests/unit/test_stage10_mock_llm.py --ignore=tests/unit/test_stage10_bench_report.py 2>&1 | tail -3
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe -m pytest tests/unit -q --ignore=tests/unit/test_stage10_mock_llm.py --ignore=tests/unit/test_stage10_bench_report.py 2>&1 | Select-Object -Last 3
```

**预期输出**：

```
124 passed, 3 warnings in 9.31s
```

> 数字记下来：**124**。阶段 10 做完之后应该变成 **141**（124 + 8 个打桩测试 + 9 个报告测试）。第十六节会再核一次。
>
> 🟡 如果你这里看到的是别的数字（比如 123 或 125），说明阶段 9 收官后你又改过项目。**以你实测的为准**，把 124 替换成你的数字，后面所有"新增 N 个"的说法跟着改。

**本节检查点**：分支名对、备份文件在、locust 有版本、旧测试 124 passed。四条全对才能进第七节。

---

## 七、落盘代码（一）：给大模型调用装上开关与打桩器

这一节改 4 个文件：**1 个新建 + 3 个改已有**。顺序不能乱——先建 `mock_llm.py`（被别的引用），再改配置（开关），再改出口（接线），最后改向量（补漏网的那个外部依赖）。

每一步统一四段：**① 建/改哪个文件 → ② 内容是什么 → ③ 怎么验证 → ④ 预期看到什么**。

### 7.1 新建 `app_my/core/mock_llm.py`（LLM 打桩器）

**① 路径**：在项目根目录 `F:\pycharm_aiprogram\ai_chief` 下新建 `app_my\core\mock_llm.py`（`app_my/core/` 目录已存在，只建文件）。

**② 内容**（整段复制进去保存）：

```python
# app_my/core/mock_llm.py
"""
阶段 10：压测用的 LLM 打桩器（Mock LLM）。

为什么需要它（压测最容易踩的坑）：
    压测想测的是"**我的架构**能扛多少并发"，不是"DashScope 那台服务器能扛多少"。
    但只要请求里带着真 LLM 调用，实测出来的 P99 里就混进了两样不属于你的东西：
        ① 网络往返 + 厂商排队（几十到几百毫秒，且随厂商负载剧烈波动）
        ② 厂商的限流 429 —— 你的服务其实好好的，却被算成"错误率上涨"
    同一套代码连跑两次，数字能差一倍。面试官问"这个 QPS 是谁的 QPS"就答不上来。

    打开 MOCK_LLM=true 后，LLM 那一环被换成一个"固定耗时、固定内容"的假模型，
    请求时延里剩下的只有你自己的代码、数据库、缓存、图谱、网络——这才是该测的东西。

打桩点选在哪（关键设计）：
    打在 `model_router.ainvoke_routed()`——它是全项目**唯一**还在调 LLM 的地方。
    （旧的 `get_chat_model().ainvoke(...)` 调用在 recognizer.py / output.py 里
      早已被注释掉并改走 ainvoke_routed，grep 全项目只剩这一处真调用。）
    所以在这里加一个早返回分支，全链路自动生效，**一行业务代码都不用改**，
    关掉开关立刻恢复真实调用。

    为什么不是打在 models.py 的档位工厂上：
        因为档位（lite/standard）不等于任务（extract/report/vision）。
        同一个 lite 档，"抽食材"要返回 JSON、"生成报告"要返回自然语言——
        从 tier 推不出该给什么格式。ainvoke_routed 才知道 task。
"""
from __future__ import annotations

import asyncio
from typing import Iterator, List

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage

# ------------------------------------------------------------------
# 按任务类型准备的假响应（内容必须符合下游消费者的格式要求）
# ------------------------------------------------------------------
# ① 识别节点（recognizer，task=extract / vision）：要求能从回复里正则抠出一个 JSON 字典。
#    否则 parse_json_payload() 返回 {}，食材清单为空 → 后面推荐/营养节点全部空转，
#    那样测出来的 QPS 是"什么都没干"的 QPS，没有意义。
_MOCK_INGREDIENT_JSON = (
    '```json\n'
    '{"ingredients": ['
    '{"name": "西兰花", "freshness": 9, "amount": "约300g", "usable": true},'
    '{"name": "鸡胸肉", "freshness": 8, "amount": "约200g", "usable": true},'
    '{"name": "鸡蛋", "freshness": 9, "amount": "2个", "usable": true}'
    '], "warnings": []}\n'
    '```'
)

# ② 输出节点（output，task=report）：只要求"有非空文本"，空内容会被它判失败并走兜底报告。
_MOCK_REPORT_TEXT = (
    "【压测模式固定回复】根据您提供的食材，建议采用「白灼西兰花 + 香煎鸡胸肉 + 番茄炒蛋」"
    "三菜一汤的搭配：西兰花提供膳食纤维，鸡胸肉补充优质蛋白，鸡蛋补充卵磷脂。"
    "总热量约 620 kcal，蛋白质 48g，脂肪 22g，碳水 55g，适合控糖人群。"
    "（本段为 MOCK_LLM 模式的固定压测响应，不代表真实模型输出。）"
)

# 假模型引入的额外时延（秒）。为什么需要它，见下方"为什么不是 0"的说明。
MOCK_LATENCY_SEC = 0.05

# task -> 固定响应内容。键名必须和 model_router.route() 认识的任务名完全一致。
_MOCK_TEXT_BY_TASK = {
    "extract": _MOCK_INGREDIENT_JSON,   # 识别节点文字分支
    "vision": _MOCK_INGREDIENT_JSON,   # 识别节点图片分支（mock 时不真的看图）
    "report": _MOCK_REPORT_TEXT,        # 输出节点
}


def _cycling(messages: List[BaseMessage]) -> Iterator[AIMessage]:
    """
    把一份固定响应"无限循环"成迭代器。

    为什么必须循环而不是单个返回值：
        GenericFakeChatModel 的 `messages` 参数要求是一个**迭代器**，
        它每次被调用就 next() 取一条。压测会打几百上千次请求，
        只给一条的话第二次调用就抛 StopIteration → 被当成 LLM 失败 →
        output 节点降级走兜底、recognizer 重试一次，P99 全被重试逻辑污染，
        数据就不可信了。
    """
    while True:
        for m in messages:
            yield m


def mock_model(text: str = _MOCK_REPORT_TEXT) -> GenericFakeChatModel:
    """
    造一个"秒回固定文本"的假对话模型（LangChain 官方提供的测试替身）。

    参数：
        text —— 假模型每次返回的内容，默认是报告文本。
    返回：
        GenericFakeChatModel —— BaseChatModel 的子类，
        invoke / ainvoke / stream / astream 四种调用方式都支持，
        所以同步调用和流式调用都能用（项目里 /chat/stream 是流式）。
    """
    return GenericFakeChatModel(messages=_cycling([AIMessage(content=text)]))


async def ainvoke_mock(task: str, messages) -> AIMessage:
    """
    按任务类型返回一份格式正确的假响应。

    参数：
        task     —— 任务名，取值 "extract" / "vision" / "report"。
                    必须原样传 ainvoke_routed 收到的 task，不能自己判断。
        messages —— 原始提示词列表。这里**故意不读它**：
                    mock 的意义是"不管你问了什么，都给一个格式正确的固定答案"，
                    真去读 prompt 反而会让 mock 行为不可预测。
    返回：
        AIMessage —— 与真实模型返回同类型，调用方 .content 取值方式不变，
                     所以 recognizer / output 两个节点一行都不用改。
    """
    if MOCK_LATENCY_SEC:
        await asyncio.sleep(MOCK_LATENCY_SEC)   # 模拟真实模型的最小耗时，见函数末尾说明
    return AIMessage(content=_MOCK_TEXT_BY_TASK.get(task, _MOCK_REPORT_TEXT))


# ------------------------------------------------------------------
# 为什么假模型还要"故意慢 50ms"，而不是让它 0 耗时？
#
#   如果 MOCK_LATENCY_SEC = 0，压测会量出一个漂亮得不真实的 QPS：
#   瓶颈完全落在数据库 / 图谱 / HTTP 框架上，而 LLM 那一环"白送"。
#   真实业务里 LLM 是每请求必经的一环，压测报告里必须给这一环留个位置，
#   否则上线后第一波流量就被 LLM 的真实耗时打脸。
#   50ms 是"快模型返回一段固定文本"的量级（阶段 2 实测 qwen3.7-flash 关思考模式
#   实测 2 秒内出报告，这里取 50ms 是有意压低，好让架构自身的开销占主导）。
# ------------------------------------------------------------------
```

**③ 验证**（确认文件语法没问题、能被导入）：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -c "import app_my.core.mock_llm as m; print('OK', m.MOCK_LATENCY_SEC, len(m._MOCK_TEXT_BY_TASK))"
```

**PowerShell 5.1：**

```powershell
@'
import app_my.core.mock_llm as m
print("OK", m.MOCK_LATENCY_SEC, len(m._MOCK_TEXT_BY_TASK))
'@ | Set-Content -Encoding UTF8 _t.py
.\.venv3\Scripts\python.exe _t.py
Remove-Item _t.py
```

**④ 预期输出**：

```
OK 0.05 3
```

> 三个数字的含义：`0.05` = 假模型固定耗时 50ms；`3` = 准备了 3 种任务的假响应（extract/vision/report）。
>
> 🔴 如果报 `ModuleNotFoundError: No module named 'langchain_core'` → 说明你用的是裸 `python`（命中 Anaconda 3.6），回头看手册开头第 1 条。
> 🔴 如果报 `SyntaxError` → 复制时漏了行，特别是文件末尾那段 `"""..."""` 之后的注释块别漏。

### 7.2 改 `app_my/core/config.py`（加两个开关）

**① 路径**：`F:\pycharm_aiprogram\ai_chief\app_my\core\config.py`（**已有文件，只插入，不要覆盖**）

**② 怎么改**：用编辑器打开，搜索这一行：

```python
    WS_NOTIFY_CHANNEL: str = "ai_chief:ws:notify"
```

在它**下面**、紧挨着的 `# ====== CORS ======` 那一段**之前**，插入下面这几行：

```python

    # ============================================================
    # 性能压测（v3 阶段 10 新增）
    # ============================================================
    # MOCK_LLM：压测时把大模型调用换成固定响应的假模型（详见 app_my/core/mock_llm.py）。
    #   默认 false = 走真实 DashScope 调用，正常开发 / 跑单测完全不受影响。
    #   压测时用环境变量临时打开即可，不必改 .env（避免忘记改回来）。
    MOCK_LLM: bool = False
    # 压测目标名，只用于日志/报告标注，不影响业务（真正打哪个地址由 locust --host 决定）
    BENCH_TARGET_NAME: str = "monolith"      # monolith=单体 9002；gateway=经 Kong 网关 9100
```

> 🟡 **为什么 `WS_NOTIFY_CHANNEL` 只有一行却要插在它后面**：它是"异步任务"那一段的最后一行。插在它后面 = 新配置成为一个独立小节，不会被别的配置段夹住。你只要保证插完的样子是：
>
> ```
>     WS_NOTIFY_CHANNEL: str = "ai_chief:ws:notify"  # 任务事件走这个 Redis 频道（worker 发、WS 网关收）
> 
>     # ============================================================
>     # 性能压测（v3 阶段 10 新增）
>     # ============================================================
>     ...
>     BENCH_TARGET_NAME: str = "monolith"
> 
>     # ============================================================
>     # CORS
>     # ============================================================
> ```

**③ 验证**：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -c "from app_my.core.config import settings; print('MOCK_LLM=', settings.MOCK_LLM); print('BENCH=', settings.BENCH_TARGET_NAME)"
```

**PowerShell 5.1：**

```powershell
@'
from app_my.core.config import settings
print("MOCK_LLM=", settings.MOCK_LLM)
print("BENCH=", settings.BENCH_TARGET_NAME)
'@ | Set-Content -Encoding UTF8 _t.py
.\.venv3\Scripts\python.exe _t.py
Remove-Item _t.py
```

**④ 预期输出**：

```
MOCK_LLM= False
BENCH= monolith
```

> 🔴 **`MOCK_LLM` 必须是 `False`**。如果是 `True`，说明你 `.env` 里写了 `MOCK_LLM=true`。默认值必须是关的——否则你平时开发、跑测试拿到的全是假数据，还查不出为什么。
>
> 顺便验证"环境变量能覆盖它"（这是第十三节压测时要用的机制）：
>
> **Git Bash：** `MOCK_LLM=true ./.venv3/Scripts/python.exe -c "from app_my.core.config import settings; print(settings.MOCK_LLM)"` → 预期 `True`
> **PowerShell：** `$env:MOCK_LLM="true"; .\.venv3\Scripts\python.exe -c "from app_my.core.config import settings; print(settings.MOCK_LLM)"; Remove-Item Env:MOCK_LLM` → 预期 `True`

### 7.3 改 `app_my/core/model_router.py`（在唯一出口接上打桩）

**① 路径**：`F:\pycharm_aiprogram\ai_chief\app_my\core\model_router.py`（**已有文件，两处小改**）

**② 怎么改 —— 改动 1（加 import）**：在文件靠上的 import 区，找到这一行：

```python
from app_my.core.logging import logger
```

在它**上面**加一行：

```python
from app_my.core.config import settings
```

**② 怎么改 —— 改动 2（加早返回分支）**：找到 `async def ainvoke_routed` 的文档字符串结尾，原文是这三行：

```python
      ③ 非 lite 档失败 → 自动换 lite 重试一次（降级链）
    """
    tier = route(task, text)
```

把它**替换成**下面这一整段：

```python
      ③ 非 lite 档失败 → 自动换 lite 重试一次（降级链）
      ④ v3阶段10 新增：MOCK_LLM=true 时走打桩分支，直接返回格式正确的假响应

    参数：
        task     —— 任务名，取值 "extract" / "report" / "vision"。决定用哪档模型。
        messages —— 提示词列表，直接透传给模型的 ainvoke()。
        text     —— 用户原始输入。只在路由判复杂度时用得到（extract 任务），
                    决定"简单问题走 lite、复杂问题走 standard"。
    返回：
        AIMessage —— 模型回复消息；调用方只读 .content。
    """
    # ---------- v3阶段10：压测打桩分支 ----------
    # 放在最前面，且**在任何网络调用之前**返回：
    #   · 压测量的是本项目架构的容量，不是模型厂商的容量（理由见 app_my/core/mock_llm.py）
    #   · 打桩后不挂 BillingCallbackHandler —— 没有真 token，自然不该记账，
    #     否则 mock 压测会把假用量写进账单表，把阶段 2 的计费数据污染掉
    #   · 这里 import 而不是模块顶层 import：生产环境不 import 测试替身
    if settings.MOCK_LLM:
        from app_my.core.mock_llm import ainvoke_mock
        response = await ainvoke_mock(task, messages)
        logger.info("router: MOCK_LLM 命中，task=%s 直接返回固定响应", task)
        return response

    tier = route(task, text)
```

> 🔴 **改完必须核对的一点**：`tier = route(task, text)` 这行**只有一次**，且在 `if settings.MOCK_LLM:` 块的**后面**。如果你搜到两行，说明替换时把原文残留了，会直接导致"打桩分支返回后还去算 tier"——虽然不会报错（因为 return 了），但代码会变得难读且容易误改。
>
> 🟡 **为什么 import 写在函数里而不是文件顶部**：`mock_llm.py` 是测试替身，生产环境不该被 import。写在函数里，只有 `MOCK_LLM=true` 时才加载，正常路径零开销。

**③ 验证**：

**Git Bash：**

```bash
grep -n "MOCK_LLM\|ainvoke_mock\|^    tier = route" app_my/core/model_router.py
```

**PowerShell 5.1：**

```powershell
Select-String -Path app_my\core\model_router.py -Pattern "MOCK_LLM|ainvoke_mock|^    tier = route" | ForEach-Object { "$($_.LineNumber): $($_.Line)" }
```

**④ 预期输出**（行号以你实际文件为准，但**必须正好 4 行**）：

```
32:from app_my.core.config import settings
110:    if settings.MOCK_LLM:
112:        response = await ainvoke_mock(task, messages)
131:    tier = route(task, text)
```

验证"打桩真的生效"（**不联网**就能返回，说明走的是 mock 分支）：

**Git Bash：**

```bash
MOCK_LLM=true ./.venv3/Scripts/python.exe -c "
import asyncio
from app_my.core.model_router import ainvoke_routed
r = asyncio.run(ainvoke_routed('extract', [], 'x'))
print('打桩返回:', r.content[:40])
"
```

**PowerShell 5.1：**

```powershell
$env:MOCK_LLM="true"
@'
import asyncio
from app_my.core.model_router import ainvoke_routed
r = asyncio.run(ainvoke_routed("extract", [], "x"))
print("打桩返回:", r.content[:40])
'@ | Set-Content -Encoding UTF8 _t.py
.\.venv3\Scripts\python.exe _t.py
Remove-Item _t.py
Remove-Item Env:MOCK_LLM
```

**预期输出**：

```
打桩返回: ```json
{"ingredients": [{"name": "西兰花",
```

> 这条命令**故意不带任何 API Key**（虽然 `.env` 里有），能秒回就证明没走网络。如果它卡了几秒才返回，说明打桩没生效、在真调 DashScope——回头检查 `settings.MOCK_LLM` 是不是真的读到 `true`。

### 7.4 改 `app_my/knowledge/embedding.py`（补上漏网的那个外部调用）

**为什么要改这个文件**：`chat` 场景每次请求都要把用户问题向量化一次（查本地菜谱库）。这**也是一个大模型调用**（DashScope 的 text-embedding-v3），但它在 `embedding.py` 里，不在 `model_router` 的出口上——光改 7.3 会漏掉它，压测时每一次对话仍然在联网。

**① 路径**：`F:\pycharm_aiprogram\ai_chief\app_my\knowledge\embedding.py`（**已有文件，4 处小改**）

**② 改动 1（加 3 个 import）**：文件顶部原来是这样：

```python
import hashlib
import math
import random
from functools import lru_cache
from typing import List
```

如果你没有这三行 `import hashlib / math / random`，在 `from functools import lru_cache` **上面**加上它们：

```python
import hashlib
import math
import random
```

**② 改动 2（加维度常量）**：找到：

```python
from app_my.core.config import settings
```

在它**下面**加：

```python

# Milvus 集合的向量维度，必须与真实 embedding 模型输出一致（app_my/knowledge/milvus_store.py 里 DIMENSION = 1024）。
# 打桩时如果维度对不上，pymilvus 会在检索时直接抛 "vector dimension mismatch"，
# 表现为所有 chat 请求 500 —— 所以这个数字不是随手填的。
MOCK_DIMENSION = 1024
```

同时把 `dimensions=1024,` 改成 `dimensions=MOCK_DIMENSION,`（在 `get_embedding_model()` 里）。

**② 改动 3（加 `_mock_embedding` 函数）**：在 `def embed_texts` **上面**插入：

```python
def _mock_embedding(text: str) -> List[float]:
    """
    给一段文本算一个"稳定的假向量"，不联网。

    两个必须做对的地方，做错了压测数据就不可信：

    1）种子用 hashlib.md5，不能用内置 hash()
       Python 3 默认开启哈希随机化（PYTHONHASHSEED），同一个字符串在不同进程里
       hash() 的结果不一样。用内置 hash() 会导致每次重启服务，同一个查询的检索结果
       都在变——压测报告里"推荐命中率"这类数字就没有可比性了。

    2）必须做 L2 归一化
       Milvus 集合用的是 COSINE（余弦相似度）度量。余弦相似度在数学上会自动除以模长，
       但全零向量会让分母为 0。归一化成单位向量后，点积就等于余弦值，
       检索分数落在 [-1, 1]，和真实 embedding 的分布一致，报告里的分数才读得懂。
    """
    # md5 取前 8 位十六进制当整数种子：稳定、跨进程一致、分布够散
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)                  # 用独立 Random 实例，别碰全局 random 状态
    vec = [rng.uniform(-1.0, 1.0) for _ in range(MOCK_DIMENSION)]
    norm = math.sqrt(sum(v * v for v in vec))   # 算模长（勾股定理）
    return [v / norm for v in vec]              # 每个分量除以模长 → 单位向量
```

**② 改动 4（两个函数加早返回）**：

```python
def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量向量化（每 10 条一批自动发送）"""
    if settings.MOCK_LLM:
        return [_mock_embedding(t) for t in texts]
    return get_embedding_model().embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """单条向量化（用户查询用）"""
    if settings.MOCK_LLM:
        return _mock_embedding(text)
    return get_embedding_model().embed_query(text)
```

**③ 验证**：

**Git Bash：**

```bash
MOCK_LLM=true ./.venv3/Scripts/python.exe -c "
from app_my.knowledge.embedding import embed_query, MOCK_DIMENSION
from app_my.knowledge.milvus_store import DIMENSION
v = embed_query('西红柿炒蛋')
s = sum(x*x for x in v) ** 0.5
print('维度=', len(v), ' 与Milvus一致=', MOCK_DIMENSION == DIMENSION)
print('模长=', round(s, 6), '（必须是 1.0）')
print('前3个分量=', [round(x, 4) for x in v[:3]])
"
```

**PowerShell 5.1：**

```powershell
$env:MOCK_LLM="true"
@'
from app_my.knowledge.embedding import embed_query, MOCK_DIMENSION
from app_my.knowledge.milvus_store import DIMENSION
v = embed_query("西红柿炒蛋")
s = sum(x*x for x in v) ** 0.5
print("维度=", len(v), " 与Milvus一致=", MOCK_DIMENSION == DIMENSION)
print("模长=", round(s, 6), "（必须是 1.0）")
print("前3个分量=", [round(x, 4) for x in v[:3]])
'@ | Set-Content -Encoding UTF8 _t.py
.\.venv3\Scripts\python.exe _t.py
Remove-Item _t.py
Remove-Item Env:MOCK_LLM
```

**④ 预期输出**（本次实测原文，三个数字必须完全一致）：

```
维度= 1024  与Milvus一致= True
模长= 1.0
前3个分量= [0.0334, 0.0513, -0.0361]
```

> 注意：第一行我脚本里印的是 `模长= 1.0（必须是 1.0）`，你看到 `1.0` 就对了。

> 🔴 **三个数字一个都不能错**：
> - 维度不是 1024 → Milvus 检索报 `vector dimension mismatch`，所有 chat 请求 500；
> - 模长不是 1.0 → 归一化漏了，COSINE 检索结果不可比；
> - 前 3 个分量每次跑都不一样 → 你用了内置 `hash()` 而不是 `md5`，跨进程不稳定。
>
> 再验证一次"跨进程稳定"（跑两遍，输出必须一字不差）：
>
> **Git Bash：** `MOCK_LLM=true ./.venv3/Scripts/python.exe -c "from app_my.knowledge.embedding import embed_query; print(round(embed_query('abc')[0], 8))"` 连跑两次
> **PowerShell：** `$env:MOCK_LLM="true"; .\.venv3\Scripts\python.exe -c "from app_my.knowledge.embedding import embed_query; print(round(embed_query('abc')[0], 8))"; .\.venv3\Scripts\python.exe -c "from app_my.knowledge.embedding import embed_query; print(round(embed_query('abc')[0], 8))"; Remove-Item Env:MOCK_LLM`
>
> 两次都应是同一个数（本次实测两次都是 `0.04675479`）。

### 7.5 本节收尾：跑一次单测

做完 7.1～7.4，上一节那两个"红着的"测试应该转绿了。

> 🔴 **勘误（2026-10-21，实测修正）**：这里**必须加 `--ignore=tests/unit/test_stage10_bench_report.py`**。原因：`test_stage10_bench_report.py` 要导入 `scripts/locust_report.py`，而那个文件要到**第九节**才会创建——现在跑必然报 `ModuleNotFoundError: No module named 'scripts.locust_report'`（1 error during collection）。这是手册初版的顺序错误：消费步骤（跑报告测试）排在产出步骤（落盘 locust_report.py）之前了。该测试文件会在 9.5 节落盘后转绿，最终仍是 141 passed。

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -m pytest tests/unit -q --ignore=tests/unit/test_stage10_bench_report.py 2>&1 | tail -3
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe -m pytest tests/unit -q --ignore=tests/unit/test_stage10_bench_report.py | Select-Object -Last 3
```

**预期输出**（本次实测原文）：

```
132 passed, 3 warnings in 12.08s
```

（末尾的耗时每次会略有不同，**关键是 `132 passed` 这半句** = 124 旧 + 8 mock。）

> 🔴 **判读**：
> - **132 passed** → 正确，继续第八节；
> - **124 passed** → 8 个 mock 测试没被收集到，检查 `tests/unit/test_stage10_mock_llm.py` 是否存在；
> - **1 error during collection，提到 `mock_llm`** → 7.1/7.3 没做完，回去补；
> - 此时如果**没加** `--ignore` 就报 `ModuleNotFoundError: No module named 'scripts.locust_report'` → 正常现象，不是你做错了，加上 `--ignore` 即可。

---

## 八、落盘代码（二）：压测脚本

### 8.1 新建 `benchmarks/locustfile.py`

**① 路径**：先建目录，再建文件。

**Git Bash：**

```bash
mkdir -p benchmarks
```

**PowerShell 5.1：**

```powershell
New-Item -ItemType Directory -Force -Path benchmarks | Out-Null
```

然后在 `F:\pycharm_aiprogram\ai_chief\benchmarks\locustfile.py` 新建文件，内容如下（整段复制）：

```python
# benchmarks/locustfile.py
"""
阶段 10：AI 私厨 v3.0 性能压测脚本（Locust）

这个脚本干什么
--------------
    同一份脚本、打到两个不同的目标，用来说明一件事：
    「微服务拆分 + 网关」到底带来了什么（或者没带来什么）。
        目标 A（单体）：--host http://127.0.0.1:9002   ← 阶段 8 之前的单体，所有接口在一个进程里
        目标 B（微服务）：--host http://127.0.0.1:9100  ← 阶段 9 拆成 4 个服务 + Kong 网关入口
    两个目标跑同一份脚本、同样并发，得到两张数据表，
    差值就是"拆分的代价与收益"——阶段 7 手册里欠着的那个"拆分前后 P99/QPS 对比"。

三个压测场景（都是真实接口，字段与 app_my/schemas 里的 Pydantic 模型一一对应）
--------------------------------------------------------------------------------
    login       POST /auth/login          登录。慢在 bcrypt 校验（BCRYPT_ROUNDS=12，CPU 密集），
                                             典型场景：用户反复登录、切账号
    chat        POST /chat/stream         流式对话。最重的一条链路：
                                             识别 → 营养 → 推荐（本地 RAG + 图谱）→ 重排 → 出报告
    recommend   GET  /kg/ask              图谱多跳推理。轻量但真实碰 Neo4j，
                                             还能顺带量出阶段 5 缓存的命中率影响

跑之前必须满足的条件（不满足的话，测出来的数字是废的）
------------------------------------------------------
    ① 服务端 MOCK_LLM=true        不打真实大模型，见 app_my/core/mock_llm.py
    ② 服务端限流阈值调高          RATE_LIMIT_PER_MINUTE / RATE_LIMIT_USER_PER_MINUTE
                                  默认 60/min、20/min，压测会直接吃到 429
    ③ 清掉当天配额计数            free 套餐 chat_daily 上限 50 次，压测几十秒就打满
    ④ Kong 网关限流调高（只压目标 B 时）  chat 默认 120/min = 2 QPS
    这四条在本阶段操作手册里都有对应步骤与验证命令。

用法（完整命令见操作手册，这里只给最常敲的两条）
------------------------------------------------
    # 压单体（Git Bash）
    MOCK_LLM=true RATE_LIMIT_PER_MINUTE=1000000 RATE_LIMIT_USER_PER_MINUTE=1000000 \
      ./.venv3/Scripts/python.exe -m uvicorn main:app --port 9002

    ./.venv3/Scripts/python.exe -m locust -f benchmarks/locustfile.py \
      --headless --host http://127.0.0.1:9002 --users 20 --spawn-rate 5 \
      --run-time 90s --csv reports/bench_monolith
"""
import os
import random
import uuid

from locust import HttpUser, between, events, task

# ============================================================
# 1. 压测参数（都可以用环境变量覆盖，不用改代码）
# ============================================================

# 图谱问答的两个入参池。故意用"多个取值"而不是固定一个：
# /kg/ask 上挂了阶段 5 的 10 分钟缓存（cached(ttl=600)），只压一个固定组合的话，
# 第一个请求之后全命中缓存，测出来的 QPS 是"Redis 返回"的 QPS，
# 根本反映不出 Neo4j 的能力。用 10×3=30 种组合，缓存命中率才接近真实使用。
INGREDIENT_POOL = [
    "土豆", "西红柿", "鸡蛋", "鸡胸肉", "西兰花",
    "牛肉", "豆腐", "虾", "黄瓜", "茄子",
]
CONDITION_POOL = ["糖尿病", "痛风", "高血压"]

# 对话场景的用户输入池。刻意混合了长短句和"详细/分析"这类信号词，
# 让阶段 2 的智能路由真的在 lite/standard 档之间切换（压测要覆盖真实分支，不是只压一条路）。
MESSAGE_POOL = [
    "我手里有西红柿、鸡蛋和土豆，能做什么菜？",
    "帮我分析一下这些食材的营养搭配",
    "推荐三个适合控糖的菜谱",
    "中午随便吃点啥",
    "鸡胸肉和西兰花怎么做好吃，详细说一下做法",
    "我减脂期，这些食材怎么搭配",
]

# 虚拟用户等待时间（秒）。取 1~2s 而不是 0，
# 模拟真人"看完上一条再发下一条"的节奏；设 0 是闭压力测（会把服务打满，只适合找极限）。
WAIT_MIN = float(os.getenv("BENCH_WAIT_MIN", "1"))
WAIT_MAX = float(os.getenv("BENCH_WAIT_MAX", "2"))

# 请求超时。chat 走完整链路（含本地 RAG 和图谱查询），默认 60s 足够，
# 但设长一点是为了"宁可慢也别算成失败"——超时会被 Locust 记成错误，虚高错误率最难看。
HTTP_TIMEOUT = float(os.getenv("BENCH_TIMEOUT", "60"))


# ============================================================
# 2. 虚拟用户
# ============================================================
class BenchUser(HttpUser):
    """
    一个虚拟用户 = 一个虚拟的人。

    on_start 在"这个人刚进场"时跑一次：注册一个专属账号并登录，拿到 token。
    为什么每人都注册而不是共用一个账号：
        · 用户名有唯一约束，共用会在并发注册时互相撞
        · 真实场景本来就是不同的人登录不同的账号
        · 附带好处：登录场景压的是"多个不同账号的密码校验"，
          比同一个账号反复校验更接近真实的 CPU 负载（bcrypt 有内存硬开销，不能被"缓存命中"稀释）
    """

    # 两次请求之间的停顿。所有 User 类都能通过这个属性调整施压节奏。
    wait_time = between(WAIT_MIN, WAIT_MAX)

    def on_start(self):
        """进场准备：注册 + 登录，拿到后面所有请求要用的 token。"""
        _live["now"] += 1
        if _live["now"] > _live["peak"]:
            _live["peak"] = _live["now"]

        # 每个 VU 一个唯一用户名。uuid 前 8 位足够唯一，又不会把数据库撑大。
        self.username = "bench_" + uuid.uuid4().hex[:10]
        self.password = "Bench@12345"          # 满足 schemas/auth.py 里 min_length=8
        self.token = ""

        # name= 是"统计归类名"。不写的话 Locust 会按真实 URL 聚合，
        # 而 /kg/ask?ingredient=土豆&condition=糖尿病 每个请求的 URL 都不一样
        # → 统计表里会出现几十行、每行一次请求，没法看。写死一个 name 就聚成一类。
        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/register", json=payload,
                              name="/auth/register [准备]", catch_response=True) as r:
            # 409 = 用户名已存在（同一用户名基本不可能，但网络重试可能撞上）→ 不算失败
            if r.status_code == 409:
                pass
            elif r.status_code not in (200, 201):
                r.failure(f"准备阶段注册失败 HTTP {r.status_code}")

        with self.client.post("/auth/login", json=payload,
                              name="/auth/login [准备]", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"准备阶段登录失败 HTTP {r.status_code}")
            else:
                self.token = r.json().get("access_token", "")

    def on_stop(self):
        """离场：把在线计数减回来（保持峰值统计准确）。"""
        _live["now"] -= 1

    def _headers(self):
        """统一带上 Authorization 头。所有受保护接口都要它（无 token 直接 401）。"""
        return {"Authorization": f"Bearer {self.token}"}

    # ---------------- 场景 1：登录 ----------------
    @task(3)
    def scenario_login(self):
        """
        压 POST /auth/login。

        权重 3：这个场景故意用**已注册好的本账号**再登录一次，
        目的是让 bcrypt 反复做密码校验（BCRYPT_ROUNDS=12，CPU 密集型），
        从而量出"CPU 被密码哈希吃掉多少"。真实生产里登录也是 CPU 瓶颈大户。
        """
        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/login", json=payload, name="/auth/login",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                # 401 在这里就是限流/配额打满了，属于压测配置问题，要在报告里写清楚而不是当"业务错误"
                r.failure(f"登录失败 HTTP {r.status_code}")

    # ---------------- 场景 2：对话（完整链路） ----------------
    @task(2)
    def scenario_chat(self):
        """
        压 POST /chat/stream（流式对话）。

        为什么权重最低（2）：这是全项目最重的一条链路，一次请求要串五个节点，
        还碰本地向量检索和知识图谱。它决定的是"用户感知到的响应时间"，
        不是"系统吞吐"。两种指标都要，就靠它 + recommend 两个场景互补。
        """
        payload = {
            "message": random.choice(MESSAGE_POOL),
            "thread_id": "bench_" + uuid.uuid4().hex[:8],   # 每次新会话，避免历史串味
            "user_id": None,          # 传 null = 按访客处理，不查用户画像（少一次 DB 查询）
        }
        with self.client.post("/chat/stream", json=payload, name="/chat/stream",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"对话失败 HTTP {r.status_code}")
            else:
                # 🔴 不要检查 "data:" 这种 SSE 帧头！本项目的 /chat/stream 虽然
                # Content-Type 写的是 text/event-stream，但 coordinator 里是直接
                # `yield content`（纯文本），并没有按 SSE 协议包一层 data: 前缀。
                # 压测 v1 的脚本在这里判过 "data:"，结果 100% 请求被判失败、
                # 失败率直接冲到 10%+，白白浪费一轮压测。
                # 这里只判断"有没有内容吐出来"，这才是链路通没通的真实信号。
                if not (r.text or "").strip():
                    r.failure("对话返回空正文（链路没有产出内容）")

    # ---------------- 场景 3：图谱推荐 ----------------
    @task(5)
    def scenario_recommend(self):
        """
        压 GET /kg/ask（知识图谱多跳推理）。

        权重最高（5）：它最轻，用它把"架构本身的极限 QPS"顶出来。
        对话场景的 QPS 受 LLM 和 RAG 拖累，不能代表架构吞吐，
        这两个数字放一起看才有意义（一个测上限，一个测真实体验）。
        """
        ingredient = random.choice(INGREDIENT_POOL)
        condition = random.choice(CONDITION_POOL)
        with self.client.get("/kg/ask", params={"ingredient": ingredient, "condition": condition},
                             name="/kg/ask", headers=self._headers(), catch_response=True,
                             timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"图谱问答失败 HTTP {r.status_code}")


# ============================================================
# 3. 跑完自动打印一张"场景 × 目标"对照表
# ============================================================
# 为什么要自己打印一遍，而不直接看 Locust 自带表格：
#   ① 自带表格里 `[准备]` 的请求（注册/首次登录）混在里面，会把成功率拉低
#   ② 压测完真正要写进报告的是"P99 和失败数"两个数，自带表要人眼找
#   ③ 打印时带上目标名，复制进报告时不会搞不清这张表是哪一轮的

# 峰值并发数。locust 2.32 的 StatsEntry 上**没有** num_users 属性，
# 退出时 runner 也已经被回收（读 environment.runner.user_count 只会拿到 0），
# 所以自己数一遍：每个虚拟用户进场 +1、离场 -1，记住过程中的最大值。
#
# 为什么不在 on_start 里用 event 钩子去记：
#   locust 的事件名没有 events.user_started（只有 init/start/stop/quitting/request 等），
#   写错一个字母就是 AttributeError，整个文件加载失败、压测根本起不来。
#   而且 on_start 是同步执行的（locust 用 gevent 协作式调度，不会在这里被打断），
#   所以加减计数不存在竞态，最朴素的做法反而最稳。
_live = {"now": 0, "peak": 0}


def _rps(entry) -> float:
    """
    算这个场景的实际吞吐量（请求/秒）。

    🔴 locust 2.32 的 StatsEntry 上没有 total_rps 属性了（老版本才有），
    也没有 total_time。只有 total_response_time（耗时总和，毫秒）、
    start_time 和 last_request_timestamp（都是 time.time() 的秒级浮点）。
    所以 RPS 只能自己按"请求数 ÷ 这批请求跨越的秒数"算：
        第一次请求记下 start_time，最后一次请求的时间是 last_request_timestamp。
    注意分母用 last - start 而不是整轮时长：
    虚拟用户是陆续发请求的，首尾之间才是真实有请求的时间窗。
    """
    span = float(getattr(entry, "last_request_timestamp", 0) or 0) - float(getattr(entry, "start_time", 0) or 0)
    if span <= 0:
        return 0.0
    return entry.num_requests / span


@events.quitting.add_listener
def _print_bench_summary(environment, **_kwargs):
    """压测进程退出时触发，把关键指标打成一排，方便直接粘进报告。"""
    # 🔴 整个函数体必须包在 try 里。locust 对事件监听器里抛出的异常只是记一条日志，
    #    **不会**让压测失败——于是表现是"压测跑完了、CSV 也生成了，但屏幕上什么都没有"，
    #    人只会怀疑是不是自己命令敲错了。
    #    阶段 10 开发时就因为写了一个 locust 2.32 里不存在的属性，连续三轮压测白跑。
    #    包一层 try，任何字段名变化都会变成屏幕上的一行报错，而不是静默消失。
    try:
        _print_bench_summary_inner(environment)
    except Exception as exc:                       # noqa: BLE001 —— 这里就是要兜住一切
        print("")
        print("=" * 96)
        print(f"BENCH SUMMARY 生成失败：{type(exc).__name__}: {exc}")
        print("（压测数据本身没丢，看同目录下的 *_stats.csv 即可；这条报错请反馈以修脚本）")
        print("=" * 96)


def _print_bench_summary_inner(environment):
    stats = environment.stats
    host = str(environment.host or "")
    target = host.rsplit(":", 1)[-1].strip("/") or "unknown"

    # 🔴 取单条统计必须同时给"显示名 + HTTP 方法"：stats.get(name, method)。
    #    只传一个参数会返回空的 Entry（num_requests=0），表里场景行会全部消失。
    #    名字里带 " [准备]" 后缀的（注册/首次登录）是每个 VU 的进场开销，不是被测场景，不列进表。
    scenarios = (
        ("/auth/login", "POST"),
        ("/chat/stream", "POST"),
        ("/kg/ask", "GET"),
    )

    print("")
    print("=" * 96)
    peak = _live["peak"]
    print(f"BENCH SUMMARY  target=:{target}  peak_users={peak}"
          f"  total={stats.total.num_requests}  failures={stats.total.num_failures}")
    print("-" * 96)
    print(f"{'场景':<16}{'请求数':>9}{'失败':>7}{'失败率':>9}{'平均ms':>10}{'P50ms':>9}{'P95ms':>9}{'P99ms':>9}{'RPS':>8}")
    print("-" * 96)

    for name, method in scenarios:
        entry = stats.get(name, method)
        if entry.num_requests == 0:
            print(f"{name:<16}{'（本轮未执行）':>9}")
            continue
        fail_rate = entry.num_failures / entry.num_requests * 100
        print(f"{name:<16}{entry.num_requests:>9}{entry.num_failures:>7}{fail_rate:>8.1f}%"
              f"{entry.avg_response_time:>10.0f}"
              f"{entry.get_response_time_percentile(0.50):>9.0f}"
              f"{entry.get_response_time_percentile(0.95):>9.0f}"
              f"{entry.get_response_time_percentile(0.99):>9.0f}"
              f"{_rps(entry):>8.1f}")

    total = stats.total
    if total.num_requests:
        print("-" * 96)
        print(f"{'TOTAL':<16}{total.num_requests:>9}{total.num_failures:>7}"
              f"{total.num_failures / total.num_requests * 100:>8.1f}%"
              f"{total.avg_response_time:>10.0f}"
              f"{total.get_response_time_percentile(0.50):>9.0f}"
              f"{total.get_response_time_percentile(0.95):>9.0f}"
              f"{total.get_response_time_percentile(0.99):>9.0f}"
              f"{_rps(total):>8.1f}")
    print("=" * 96)
```

**③ 验证 —— 先看 Locust 能不能识别到这个用户类**（**不需要服务在跑**，这条只检查脚本加载）：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -m locust -f benchmarks/locustfile.py --list
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe -m locust -f benchmarks\locustfile.py --list
```

**④ 预期输出**：

```
BenchUser
    @tag
```

> 🔴 `--list` **没有** `-f` 之外的要求，也不连服务端。只要它打印出 `BenchUser`，就说明：文件语法没问题、`from locust import ...` 全部导入成功、事件监听器注册成功。
> 如果报 `AttributeError: module 'locust' has no attribute ...` 或 `AttributeError: ... events`，说明脚本里用到了 locust 2.32 里不存在的名字（比如 `events.user_started`），检查文件末尾那段。

**本节检查点**：`benchmarks/locustfile.py` 存在、`--list` 打印出 `BenchUser`。

---

## 九、落盘代码（三）：压测编排与报告生成

这一节 3 个文件：`run_bench.sh`（Git Bash 编排）+ `run_bench.ps1`（PowerShell 编排）+ `locust_report.py`（汇总成报告）。

> 🟡 **两个编排脚本内容等价、挑一个用就行**。你要是用 Git Bash 跑压测（推荐，因为 `run_bench.sh` 是我在你机器上完整实跑过的那个），照样要把 `.ps1` 也建好——第十二节的验收脚本会检查它存在，CI 也可能用到。

### 9.1 新建 `scripts/run_bench.sh`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\scripts\run_bench.sh`（`scripts/` 目录已存在）

**② 内容**（整段复制）：

```bash
#!/usr/bin/env bash
# =============================================================================
# scripts/run_bench.sh —— 阶段 10 压测编排脚本（Git Bash 版）
# =============================================================================
# 这个脚本干什么：
#   把"压测"这件很啰嗦的事收成一条命令——自动对每个目标、每个并发档位各跑一轮
#   Locust，每轮的 CSV 分开存放，最后汇总成一张表。
#   手敲 6~8 次 locust 命令既容易漏参数，又容易忘记清配额，结果前后两轮数据不可比。
#
# 怎么用（都在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#   bash scripts/run_bench.sh                     # 默认：两个目标 × 单档 20 用户 × 60 秒
#   bash scripts/run_bench.sh gateway             # 只压网关
#   bash scripts/run_bench.sh all "10,20,40,60" 30   # 两个目标 × 4 个并发档 × 每档 30 秒（找拐点用）
#
# 为什么参数是"逗号分隔的档位列表"而不是单一并发数：
#   要回答"错误率拐点在哪"，就必须一路加压，直到 P99 明显变差或出现失败。
#   一档一档跑，才能把拐点画出来；只跑一档只能得到"某个并发下还行"，写不进报告。
#
# 🔴 跑之前必须已经满足的条件（否则测出来的是"限流值"，不是"架构容量"）：
#   ① 服务端 MOCK_LLM=true 启动（不真调大模型）
#   ② 服务端 RATE_LIMIT_PER_MINUTE / RATE_LIMIT_USER_PER_MINUTE 调高
#   ③ 当天租户配额已清（free 套餐 chat_daily 只有 50 次）
#   ④ Kong 网关 rate-limiting 已调高
#   ⑤ 5 个服务都健康（9002 / 9121 / 9122 / 9123 / 9124）
#   这五条在操作手册里都有对应步骤和验证命令。
# =============================================================================

set -euo pipefail

# ---------- 参数 ----------
TARGET_SCOPE="${1:-all}"                                  # all | monolith | gateway
USERS_LIST="${2:-20}"                                     # 逗号分隔，如 "10,20,40,60"
RUN_SECONDS="${3:-60}"                                    # 每档跑多少秒

# ---------- 路径与解释器 ----------
cd "$(dirname "$0")/.."                                     # 切到项目根目录（不管从哪调都能跑）

# 解释器允许用环境变量覆盖：PY=/path/to/python.exe bash scripts/run_bench.sh
# 默认用项目自己的虚拟环境。**绝不能写裸 python**——Windows 上会先命中 Anaconda 3.6，
# 那个环境的 pytest/库版本太老，读 UTF-8 配置时按 GBK 解，直接 UnicodeDecodeError。
PY="${PY:-./.venv3/Scripts/python.exe}"

# 🔴 这一步检查不能省。少了它，"解释器路径不存在"这条错误会被后面的
#    `... | grep ... || true` 整个吞掉：屏幕上只看到"目标=monolith 并发=5"
#    然后一行结果都没有、reports 目录空着，人会以为是自己哪里写错了，
#    实际上压测压根没启动（阶段 10 第一版脚本就踩了这个坑）。
if [ ! -f "$PY" ]; then
  echo "[中止] 找不到虚拟环境解释器: $PY"
  echo "       · 确认你是在项目根目录（含 .venv3 的那个）执行的"
  echo "       · 或者显式指定：PY=/绝对路径/python.exe bash scripts/run_bench.sh"
  exit 1
fi

LOCUSTFILE="benchmarks/locustfile.py"
if [ ! -f "$LOCUSTFILE" ]; then
  echo "[中止] 找不到压测脚本: $LOCUSTFILE（当前目录 $(pwd)）"
  exit 1
fi

REPORT_DIR="reports/bench_$(date +%Y%m%d_%H%M%S)"         # 按时间戳分目录，避免覆盖上一轮
mkdir -p "$REPORT_DIR"

# ---------- 目标表：名字 → 地址 ----------
# monolith = 阶段 8 之前的单体，所有接口在一个进程里
# gateway  = 阶段 9 拆成 4 个服务后、经 Kong 网关的入口（用户真正访问的那个地址）
declare -A HOSTS=(
  [monolith]="http://127.0.0.1:9002"
  [gateway]="http://127.0.0.1:9100"
)
ORDER=(monolith gateway)                                   # 固定顺序，压测顺序一致才不会互相干扰

# ---------- 前置检查：服务必须先活着 ----------
echo "=============================================================="
echo " 阶段 10 压测开始  $(date '+%Y-%m-%d %H:%M:%S')"
echo " 输出目录: $REPORT_DIR"
echo "=============================================================="

for p in 9002 9121 9122 9123 9124; do
  if ! curl -s -m 3 "http://127.0.0.1:$p/health" > /dev/null; then
    echo "[中止] 端口 $p 不通。按操作手册先把 5 个服务起好再压测。"
    exit 1
  fi
done
echo "[前置检查] 5 个服务 health 全部通过"

# 清当天配额：free 套餐 chat_daily 上限 50 次，压测几十秒就会打满，
# 之后所有 chat 请求返回 429，报告里就变成"一堆 429"，看不出真实容量。
docker exec ai_chief_redis redis-cli --scan --pattern "quota:*" 2>/dev/null | while read -r k; do
  [ -n "$k" ] && docker exec ai_chief_redis redis-cli DEL "$k" > /dev/null
done
echo "[前置检查] 已清空当天租户配额计数"

# ---------- 主循环 ----------
IFS=',' read -r -a USER_ARRAY <<< "$USERS_LIST"

for target in "${ORDER[@]}"; do
  if [ "$TARGET_SCOPE" != "all" ] && [ "$TARGET_SCOPE" != "$target" ]; then
    continue
  fi
  host="${HOSTS[$target]}"
  for users in "${USER_ARRAY[@]}"; do
    csv="$REPORT_DIR/${target}_u${users}"
    echo ""
    echo "--------------------------------------------------------------"
    echo " 目标=$target  地址=$host  并发=$users  时长=${RUN_SECONDS}s"
    echo "--------------------------------------------------------------"
    # --headless        不开网页界面，直接命令行跑（CI/脚本里必须加）
    # --spawn-rate      每秒启动多少个虚拟用户。这里取"3 秒内把本档用户全起完"，
    #                    而不是一秒全上：一秒全上时，头几秒全是冷启动（连接池要新建、
    #                    Milvus/Neo4j 要重连），这些慢请求会把平均值和 P99 整体拉高，
    #                    测出来的不是"稳态容量"。留 3 秒爬坡，这 3 秒在 45 秒的一轮里
    #                    只占 7%，对结果的影响可以忽略。
    # --csv             输出 CSV：_stats.csv（分场景明细）/ _stats_history.csv（时间序列，找拐点用）/ _failures.csv
    # 🔴 这里**故意不接 `| grep` 过滤**：一接管道，locust 自己报的任何错（找不到文件、
    #    参数写错、解释器起不来）都会被过滤掉，只剩一行安静的分隔线，
    #    排查时完全看不出发生了什么。让它原样打出来，乱一点但可追溯。
    spawn=$(( users / 3 ))
    [ "$spawn" -lt 1 ] && spawn=1
    "$PY" -m locust -f "$LOCUSTFILE" \
      --headless \
      --host "$host" \
      --users "$users" \
      --spawn-rate "$spawn" \
      --run-time "${RUN_SECONDS}s" \
      --csv "$csv" \
      --csv-full-history \
      --only-summary
  done
done

echo ""
echo "=============================================================="
echo " 压测结束，结果 CSV 在: $REPORT_DIR"
echo " 下一步：用报告脚本把它汇总成一张对比表"
echo "   $PY scripts/locust_report.py --dir \"$REPORT_DIR\""
echo "=============================================================="
```

**③ 验证 —— 只做"能加载、参数解析对"的静态检查，先别真跑**（真跑在第十四节）：

**Git Bash：**

```bash
bash -n scripts/run_bench.sh && echo "语法 OK"
ls -l scripts/run_bench.sh
```

**PowerShell 5.1：**

```powershell
& "C:\Program Files\Git\bin\bash.exe" -n scripts/run_bench.sh
if ($LASTEXITCODE -eq 0) { "语法 OK" }
Get-Item scripts\run_bench.sh | Select-Object Name, Length
```

**④ 预期输出**：

```
语法 OK
```

> 🔴 如果你的 Git 装在别的路径（比如 `D:\git\Git`），把上面 `C:\Program Files\Git\bin\bash.exe` 换成你的路径。用 `where.exe bash` 可以查到。
> 🟡 `run_bench.sh` 里用了 `declare -A`（bash 4 关联数组）。Git for Windows 自带的 bash 是 4.x，没问题。如果你用的是很老的 WSL bash 3.x，会报 `declare: -A: invalid option`——换 Git Bash 即可。

### 9.2 新建 `scripts/run_bench.ps1`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\scripts\run_bench.ps1`

**② 内容**（整段复制）：

```powershell
# =============================================================================
# scripts/run_bench.ps1 —— 阶段 10 压测编排脚本（Windows PowerShell 5.1 版）
# =============================================================================
# 和 scripts/run_bench.sh 是同一件事的两种终端写法，参数、输出、判定口径完全一致。
# 为什么必须写两遍：
#     PowerShell 5.1 和 bash 的语法差异很大——bash 里的 && / grep / head / nohup
#     在 5.1 里要么不存在、要么语义完全不同。给一份"两边都能用"的命令是不存在的，
#     只能各写一份。如果你用的是 PowerShell，就用这个文件，别去改 sh 那个。
#
# 用法（在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#   .\scripts\run_bench.ps1
#   .\scripts\run_bench.ps1 -Target gateway
#   .\scripts\run_bench.ps1 -Target all -UsersList "10,20,40,60" -Duration 45
#
# 🔴 如果提示"无法加载文件，因为在此系统上禁止运行脚本"，先执行一次：
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    （-Scope Process 只对当前窗口生效，关闭就恢复，不会污染系统设置）
# =============================================================================

[CmdletBinding()]
param(
    # all = 单体 + 网关都压；monolith = 只压单体；gateway = 只压网关
    [string]$Target = 'all',
    # 逗号分隔的并发档位列表
    [string]$UsersList = '20',
    # 每档跑多少秒
    [int]$Duration = 60
)

$ErrorActionPreference = 'Stop'

# ---------- 路径与解释器 ----------
# 切到脚本所在目录的上一级 = 项目根目录（不管从哪调都能跑）
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# 解释器允许覆盖：$env:BENCH_PY='D:\path\python.exe'; .\scripts\run_bench.ps1
$PY = if ($env:BENCH_PY) { $env:BENCH_PY } else { Join-Path $Root '.venv3\Scripts\python.exe' }

# 🔴 这段检查不能省。少了它，"解释器路径不存在"会被后面的错误处理吞掉，
#    屏幕上只看到"目标=monolith 并发=5"然后什么都没有、reports 目录空着，
#    人会以为是自己命令敲错了（阶段 10 第一版就踩过这个坑）。
if (-not (Test-Path $PY)) {
    Write-Host "[中止] 找不到虚拟环境解释器: $PY" -ForegroundColor Red
    Write-Host "       · 确认你在项目根目录（含 .venv3 的那个）执行"
    Write-Host "       · 或显式指定：`$env:BENCH_PY='D:\abs\path\python.exe'"
    exit 1
}

$LocustFile = Join-Path $Root 'benchmarks\locustfile.py'
if (-not (Test-Path $LocustFile)) {
    Write-Host "[中止] 找不到压测脚本: $LocustFile（当前目录 $(Get-Location)）" -ForegroundColor Red
    exit 1
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$ReportDir = Join-Path $Root "reports\bench_$stamp"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

# ---------- 目标表：名字 → 地址 ----------
$Targets = [ordered]@{
    'monolith' = 'http://127.0.0.1:9002'
    'gateway'  = 'http://127.0.0.1:9100'
}

Write-Host "=============================================================="
Write-Host (" 阶段 10 压测开始  " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host " 输出目录: $ReportDir"
Write-Host "=============================================================="

# ---------- 前置检查 ----------
# 用 try/catch 而不是 -ErrorAction SilentlyContinue：
# 端口不通要能立刻报错退出，不能静默跳过然后压测半天发现全是 ConnectionError
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    $ok = $false
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$p/health" -TimeoutSec 3
        $ok = $true
    } catch {
        $ok = $false
    }
    if (-not $ok) {
        Write-Host "[中止] 端口 $p 不通。按操作手册先把 5 个服务起好再压测。" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[前置检查] 5 个服务 health 全部通过"

# 清当天配额：free 套餐 chat_daily 上限 50 次，压测几十秒就会打满，
# 之后所有 chat 请求返回 429，报告里就变成"一堆 429"，看不出真实容量。
$keys = & docker exec ai_chief_redis redis-cli --scan --pattern 'quota:*' 2>$null
foreach ($k in $keys) {
    if ($k) { & docker exec ai_chief_redis redis-cli DEL $k | Out-Null }
}
Write-Host "[前置检查] 已清空当天租户配额计数"

# ---------- 主循环 ----------
foreach ($name in $Targets.Keys) {
    if ($Target -ne 'all' -and $Target -ne $name) { continue }
    $hostUrl = $Targets[$name]
    foreach ($users in ($UsersList -split ',')) {
        $users = $users.Trim()
        if (-not $users) { continue }
        # 爬坡速率：3 秒内把本档用户起完。
        # 一秒全上时头几秒全是冷启动（连接池新建、Milvus/Neo4j 重连），
        # 这些慢请求会把平均值和 P99 整体拉高，测出来的不是稳态容量。
        $spawn = [math]::Max(1, [math]::Floor([int]$users / 3))
        $csv = Join-Path $ReportDir "${name}_u${users}"

        Write-Host ""
        Write-Host "--------------------------------------------------------------"
        Write-Host " 目标=$name  地址=$hostUrl  并发=$users  时长=${Duration}s"
        Write-Host "--------------------------------------------------------------"

        # PowerShell 5.1 没有 && ，参数必须一个一个用逗号串起来传给外部命令，
        # 不能像 bash 那样靠换行续接（反斜杠续行是 PS 6+ 才有的语法）
        & $PY -m locust -f $LocustFile `
            --headless `
            --host $hostUrl `
            --users $users `
            --spawn-rate $spawn `
            --run-time "${Duration}s" `
            --csv $csv `
            --csv-full-history `
            --only-summary

        # 判断外部命令的退出码必须用 $LASTEXITCODE，不能用 $?
        # （$? 判断的是 PowerShell 自己的语句成功与否，对外部程序不可靠）
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[警告] 本轮 locust 退出码 $LASTEXITCODE —— 检查上面的错误输出" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "=============================================================="
Write-Host " 压测结束，结果 CSV 在: $ReportDir"
Write-Host " 下一步：用报告脚本把它汇总成一张对比表"
Write-Host "   $PY scripts\locust_report.py --dir `"$ReportDir`""
Write-Host "=============================================================="
```

**③ 验证 —— PowerShell 语法解析检查**（不实际执行）：

```powershell
$err = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path scripts\run_bench.ps1).Path, [ref]$null, [ref]$err)
if ($err.Count -eq 0) { "语法 OK" } else { $err | ForEach-Object { $_.Message } }
```

**④ 预期输出**：

```
语法 OK
```

> 🔴 **勘误 + 避坑（2026-10-21 实机踩坑补充）：`.ps1` 必须保存为「UTF-8 with BOM」**
>
> 本脚本首次落盘时保存成了无 BOM 的 UTF-8，ParseFile 报了 3 个莫名其妙的错误：
> `表达式或语句中包含意外的标记"}"` / `数组索引表达式丢失或无效` / `语句块或类型定义中缺少右"}"`。
>
> **原因**：PowerShell 5.1 读**无 BOM** 的脚本时按系统 ANSI（CP936/GBK）解码。脚本里的中文字符串（如"配额清理失败，跳过配额清除"是 13 个字 = 39 字节，奇数）按 GBK 两两配对后，落单的最后一个字节会把紧随其后的 `"` 收尾引号一起吞掉——字符串没了收口就跨行继续吞 `}` 和 `catch`，产生上面三个连锁错误。（代码本身没有任何语法问题，UTF-8 视角解析是 0 错误。）
>
> **自查**（一行判断有没有 BOM）：
>
> ```powershell
> $b = [System.IO.File]::ReadAllBytes('scripts\run_bench.ps1')[0..2]; ($b -join ',') -eq '239,187,191'
> ```
>
> 输出 `True` = 有 BOM（正确）；`False` = 无 BOM（要修）。
>
> **修复方法（二选一）**：
> - **VS Code**：右下角点编码"UTF-8" → "通过编码保存" → 选 **"UTF-8 with BOM"**；
> - **PowerShell 一条命令**（直接在项目根目录执行）：
>
> ```powershell
> $t = [System.IO.File]::ReadAllText('scripts\run_bench.ps1', [Text.Encoding]::UTF8); [System.IO.File]::WriteAllText('scripts\run_bench.ps1', $t, [Text.Encoding]::UTF8)
> ```
>
> （.NET 的 `Encoding.UTF8` 写入时自带 BOM。）
>
> **适用范围**：本阶段所有含中文的 `.ps1`——`run_bench.ps1`、`ci_local.ps1`（11.3 节）都要保证带 BOM，之后写 PowerShell 脚本也照此办理。

> 🟡 **诚实说明**：这个脚本我只能做静态语法验证，没有在你机器上完整跑过一轮压测（本次压测是用 `run_bench.sh` 在 Git Bash 里跑完的）。它是仿照已实跑的 `.sh` 逐行翻译的，参数、顺序、判定口径一致。如果你用 PowerShell 跑压测，建议**先用单档小并发试一次**（`.\scripts\run_bench.ps1 -Target monolith -UsersList "5" -Duration 15`），确认输出正常再跑完整档位。

### 9.3 新建 `scripts/locust_report.py`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\scripts\locust_report.py`

**② 内容**（整段复制）：

```python
#!/usr/bin/env python
# =============================================================================
# scripts/locust_report.py —— 阶段 10 压测结果汇总器
# =============================================================================
# 这个脚本干什么：
#   把 run_bench.sh 跑出来的一堆 CSV（每轮一个 *_stats.csv）汇总成
#   ① 同并发下「单体 vs 网关」对比表
#   ② 「并发数 → 吞吐量 / P99 / 失败率」的拐点曲线表
#   ③ 一份 Markdown 报告文件（可以直接贴进简历/项目文档）
#
# 为什么不直接看 Locust 自带表格：
#   Locust 一次只给一轮的结果，而且 `[准备]` 的注册/登录请求混在里面。
#   要回答"拆分到底值不值"、"错误率在哪个并发开始爆"这两个问题，
#   必须把多轮结果放在一起横向比——那就是这个脚本的活。
#
# 怎么用：
#   ./.venv3/Scripts/python.exe scripts/locust_report.py --dir reports/bench_20261020_143000
#   ./.venv3/Scripts/python.exe scripts/locust_report.py --dir reports/xxx --out reports/xxx/压测报告.md
#
# 依赖：只用 Python 标准库（csv / argparse / pathlib），不装任何新东西。
# =============================================================================
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# 压测场景定义：显示名 → CSV 里的 Name
# 只收这三个；名字里带 " [准备]" 后缀的（注册 / 首次登录）是每个虚拟用户的进场开销，
# 不是被测场景，混进来会把平均响应时间和成功率都带偏。
SCENARIOS = (
    ("/auth/login", "POST", "登录"),
    ("/chat/stream", "POST", "对话"),
    ("/kg/ask", "GET", "图谱问答"),
)

TARGET_LABEL = {
    "monolith": "单体（9002 直连）",
    "gateway": "微服务（9100 经 Kong 网关）",
}

# 拐点判定阈值：满足任意一条就算"这一档开始劣化"
FAIL_RATE_THRESHOLD = 1.0     # 错误率超过 1%
P99_THRESHOLD_MS = 1000.0     # 或者 P99 超过 1000 毫秒


def _to_float(value: str) -> float:
    """把 CSV 里的字符串安全转成 float（空串/脏数据一律当 0，不让报告崩掉）。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_stats_csv(path: Path) -> dict:
    """
    解析一个 Locust stats CSV，返回 {场景名: {指标}}。

    Locust 2.32 写出的列名（照抄自真实文件，不要凭记忆改）：
        Type, Name, Request Count, Failure Count, Median Response Time,
        Average Response Time, Min Response Time, Max Response Time,
        Average Content Size, Requests/s, Failures/s, 50%, 66%, 75%, 80%,
        90%, 95%, 98%, 99%, 99.9%, 99.99%, 100%
    注意 "Requests/s" 这一列是**聚合口径**的每秒请求数，
    报告里的 QPS 直接用它，不要自己再用 请求数÷时长 算一遍（口径不一样）。
    """
    result = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("Name") or "").strip()
            if not name or name.endswith("[准备]"):
                continue
            req = _to_int(row.get("Request Count", "0"))
            fail = _to_int(row.get("Failure Count", "0"))
            result[name] = {
                "requests": req,
                "failures": fail,
                "fail_rate": (fail / req * 100) if req else 0.0,
                "avg_ms": _to_float(row.get("Average Response Time", "0")),
                "p50_ms": _to_float(row.get("50%", "0")),
                "p95_ms": _to_float(row.get("95%", "0")),
                "p99_ms": _to_float(row.get("99%", "0")),
                "max_ms": _to_float(row.get("Max Response Time", "0")),
                "rps": _to_float(row.get("Requests/s", "0")),
            }
    return result


def load_rounds(report_dir: Path) -> list:
    """
    扫目录，把所有 `<target>_u<并发数>_stats.csv` 收成一轮压测记录。

    返回的每个元素：
        {"target": "monolith", "users": 20, "stats": {...}, "csv": 文件路径}
    """
    pattern = re.compile(r"^(?P<target>[a-z]+)_u(?P<users>\d+)_stats\.csv$")
    rounds = []
    for csv_path in sorted(report_dir.glob("*_stats.csv")):
        m = pattern.match(csv_path.name)
        if not m:
            continue
        stats = parse_stats_csv(csv_path)
        if not stats:
            print(f"[跳过] {csv_path.name} 里没有可用的场景数据", file=sys.stderr)
            continue
        rounds.append({
            "target": m.group("target"),
            "users": int(m.group("users")),
            "stats": stats,
            "csv": csv_path,
        })
    # 排序：先按并发数，再按目标，保证同一并发的单体/网关挨在一起
    rounds.sort(key=lambda r: (r["users"], r["target"]))
    return rounds


def _aggregated(stats: dict) -> dict:
    """
    取汇总行。

    Locust 会写一行 Name="Aggregated"（Type="Aggregated"），
    它把这一轮所有请求合在一起算，是报告里"总 QPS / 总失败率"的来源。
    """
    return stats.get("Aggregated", {})


def build_comparison_table(rounds: list) -> list:
    """
    生成「同一并发下，单体 vs 网关」逐场景对比表。

    只对比两边都跑过的并发档位——某一档缺一边就不进表，
    避免出现"网关有数据、单体是空"的半截对比（那种表放进报告最容易误导人）。
    """
    by_users = {}
    for r in rounds:
        by_users.setdefault(r["users"], {})[r["target"]] = r

    rows = []
    for users in sorted(by_users):
        pair = by_users[users]
        if "monolith" not in pair or "gateway" not in pair:
            continue
        mono = pair["monolith"]["stats"]
        gw = pair["gateway"]["stats"]
        for name, _method, label in SCENARIOS:
            if name not in mono or name not in gw:
                continue
            m, g = mono[name], gw[name]
            # P99 的相对差：(网关 - 单体) / 单体。单体为 0 时不算百分比，直接留空。
            delta = ((g["p99_ms"] - m["p99_ms"]) / m["p99_ms"] * 100) if m["p99_ms"] else None
            rows.append({
                "users": users,
                "label": label,
                "name": name,
                "mono_rps": m["rps"],
                "gw_rps": g["rps"],
                "mono_p99": m["p99_ms"],
                "gw_p99": g["p99_ms"],
                "delta_p99_pct": delta,
                "mono_fail": m["fail_rate"],
                "gw_fail": g["fail_rate"],
            })
    return rows


def build_knee_table(rounds: list) -> list:
    """生成「并发档位 → 总吞吐 / 总 P99 / 总失败率」的拐点表。"""
    rows = []
    for r in rounds:
        agg = _aggregated(r["stats"])
        if not agg:
            continue
        degraded = agg["fail_rate"] > FAIL_RATE_THRESHOLD or agg["p99_ms"] > P99_THRESHOLD_MS
        rows.append({
            "target": r["target"],
            "users": r["users"],
            "requests": agg["requests"],
            "failures": agg["failures"],
            "fail_rate": agg["fail_rate"],
            "rps": agg["rps"],
            "avg_ms": agg["avg_ms"],
            "p95_ms": agg["p95_ms"],
            "p99_ms": agg["p99_ms"],
            "max_ms": agg["max_ms"],
            "degraded": degraded,
        })
    return rows


def find_knee(knee_rows: list, target: str):
    """
    找某个目标"开始劣化"的第一档并发；全程不劣化则返回 None。

    判定口径（和报告里写的口径必须一致）：
        失败率 > 1%  或  P99 > 1000ms
    返回 None 表示"压到最高档都还没到拐点"——这本身也是结论，
    说明这台机器上还没摸到真实上限（要继续加压才会爆）。
    """
    rows = [r for r in knee_rows if r["target"] == target]
    rows.sort(key=lambda r: r["users"])
    for r in rows:
        if r["degraded"]:
            return r["users"]
    return None


def _median(values: list):
    """取中位数。空列表返回 None（调用方要自己处理，不能直接除）。"""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    # 奇数个取中间那个；偶数个取中间两个的平均
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def render_markdown(rounds: list, comparison: list, knee: list, report_dir: Path) -> str:
    """
    把三张表渲染成一份 Markdown 报告。

    🔴 这里每一行都**不带**结尾换行符，最后统一用 "\\n".join() 拼起来。
    两条写法混着用（有的行带 \\n 有的不带）就会出现"整张表挤成一行"，
    在渲染器里显示成一条永远滚不完的长表格，完全没法读。
    """
    out = []
    out.append("# AI 私厨 v3.0 · 阶段 10 性能压测报告")
    out.append("")
    out.append(f"> 数据来源：`{report_dir}` 下的 Locust CSV（本机实跑）")
    out.append("> 口径说明：LLM 调用为 **Mock 模式**（`MOCK_LLM=true`），"
               "测的是本项目架构本身的容量，不含外部大模型服务的耗时。")

    out.append("")
    out.append("## 一、总览：并发 → 容量与劣化")
    out.append("")
    out.append("| 目标 | 并发 | 总请求 | 失败 | 失败率 | 总QPS | 平均ms | P95ms | P99ms | 已劣化 |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    knee_mono = find_knee(knee, "monolith")
    knee_gw = find_knee(knee, "gateway")
    for r in knee:
        out.append(
            f"| {TARGET_LABEL.get(r['target'], r['target'])} | {r['users']} | {r['requests']} | "
            f"{r['failures']} | {r['fail_rate']:.2f}% | {r['rps']:.1f} | {r['avg_ms']:.0f} | "
            f"{r['p95_ms']:.0f} | {r['p99_ms']:.0f} | {'是' if r['degraded'] else ''} |"
        )

    out.append("")
    out.append("## 二、单体 vs 微服务（同一并发、同一脚本）")
    out.append("")
    out.append("| 并发 | 场景 | 单体QPS | 网关QPS | 单体P99ms | 网关P99ms | 网关P99增幅 | 单体失败率 | 网关失败率 |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for c in comparison:
        delta = f"{c['delta_p99_pct']:+.0f}%" if c["delta_p99_pct"] is not None else "—"
        out.append(
            f"| {c['users']} | {c['label']}（{c['name']}） | {c['mono_rps']:.2f} | {c['gw_rps']:.2f} | "
            f"{c['mono_p99']:.0f} | {c['gw_p99']:.0f} | {delta} | "
            f"{c['mono_fail']:.2f}% | {c['gw_fail']:.2f}% |"
        )

    out.append("")
    out.append("## 三、结论（脚本自动判定，口径见下）")
    out.append("")
    out.append(f"- 劣化判定口径：错误率 > {FAIL_RATE_THRESHOLD}% **或** P99 > {P99_THRESHOLD_MS:.0f} ms")
    out.append(f"- 单体架构拐点：**{f'{knee_mono} 并发' if knee_mono else '未触及（最高档仍达标）'}**")
    out.append(f"- 微服务架构拐点：**{f'{knee_gw} 并发' if knee_gw else '未触及（最高档仍达标）'}**")

    if comparison:
        # 为什么用中位数而不是直接取最大值：
        #   某个并发档的 P99 可能被一次 GC / 一次冷连接 / 一次限流重试拉高，
        #   取最大会把这种偶发噪声当成"网关开销最大的场景"写进结论，
        #   结论就错了（实测里 20 并发的 /kg/ask 就出现过一次 310ms 的偶发尖刺，
        #   而 40 并发同样场景只有 21ms）。取各档增幅的中位数才代表常态。
        per_scene = {}
        for c in comparison:
            if c["delta_p99_pct"] is not None:
                per_scene.setdefault(c["label"], []).append(c["delta_p99_pct"])
        ranked = sorted(
            ((label, _median(vals)) for label, vals in per_scene.items() if _median(vals) is not None),
            key=lambda kv: kv[1], reverse=True,
        )
        if ranked:
            worst_label, worst_val = ranked[0]
            best_label, best_val = ranked[-1]
            out.append(f"- 网关开销中位数最大的场景：**{worst_label}**（各档中位数 {worst_val:+.0f}%）")
            out.append(f"- 网关开销中位数最小的场景：**{best_label}**（各档中位数 {best_val:+.0f}%）")

    out.append("")
    out.append("---")
    out.append("")
    out.append("### 复现方式")
    out.append("")
    out.append("```bash")
    out.append('bash scripts/run_bench.sh all "10,20,40,60" 45')
    out.append(".venv3/Scripts/python.exe scripts/locust_report.py --dir <输出目录>")
    out.append("```")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 10 压测结果汇总器")
    parser.add_argument("--dir", required=True, help="run_bench.sh 的输出目录（含 *_stats.csv）")
    parser.add_argument("--out", default="", help="把 Markdown 报告写到哪个文件；不给就打印到屏幕")
    args = parser.parse_args()

    report_dir = Path(args.dir)
    if not report_dir.is_dir():
        print(f"[错误] 目录不存在: {report_dir}", file=sys.stderr)
        return 1

    rounds = load_rounds(report_dir)
    if not rounds:
        print(f"[错误] {report_dir} 里没找到任何 *_stats.csv。"
              f"先跑 bash scripts/run_bench.sh 生成压测结果。", file=sys.stderr)
        return 1

    comparison = build_comparison_table(rounds)
    knee = build_knee_table(rounds)
    markdown = render_markdown(rounds, comparison, knee, report_dir)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"[完成] 报告已写入 {out_path}")
        print(f"       共解析 {len(rounds)} 轮压测、{len(comparison)} 行对比、{len(knee)} 行拐点数据")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> 🟡 Python 版本说明：代码里 `def find_knee(...) -> int | None` 这种写法需要 Python 3.10 以上。你的 `.venv3` 是 3.13，没问题。如果你哪天换到 3.9，要把 `int | None` 改成 `Optional[int]` 并在顶部加 `from typing import Optional`。

**③ 验证 —— 用已有的真实压测数据跑一遍**（如果你的 `reports/` 下还没有数据，跳到第十四节跑完再回来）：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe scripts/locust_report.py --dir reports/bench_20261020_143045
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe scripts\locust_report.py --dir reports\bench_20261020_143045
```

**④ 预期输出**（本次实测原文，目录名换成你自己的）：

```
# AI 私厨 v3.0 · 阶段 10 性能压测报告

> 数据来源：`reports/bench_20261020_143045` 下的 Locust CSV（本机实跑）
> 口径说明：LLM 调用为 **Mock 模式**（`MOCK_LLM=true`），测的是本项目架构本身的容量，不含外部大模型服务的耗时。

## 一、总览：并发 → 容量与劣化

| 目标 | 并发 | 总请求 | 失败 | 失败率 | 总QPS | 平均ms | P95ms | P99ms | 已劣化 |
|---|---|---|---|---|---|---|---|---|---|
| 单体（9002 直连） | 10 | 342 | 0 | 0.00% | 6.9 | 178 | 350 | 470 |  |
...
```

完整三张表见**附录 B**。

**本节检查点**：`run_bench.sh` 语法 OK、`run_bench.ps1` 语法 OK、`locust_report.py` 能跑出三张表。

**顺手补一次 7.5 欠下的全量单测**（现在 `locust_report.py` 已存在，报告测试能收集了）：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -m pytest tests/unit -q 2>&1 | tail -3
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe -m pytest tests/unit -q | Select-Object -Last 3
```

**预期输出**（本次实测原文）：

```
141 passed, 3 warnings in 12.08s
```

（132 + 9 = 141。`test_stage10_bench_report.py` 的 9 个用例在这里转绿。）

---

## 十、落盘代码（四）：生产级部署

这一节 3 个文件。它们的**顺序有讲究**：`requirements.prod.txt` → `Dockerfile.svc` → `docker-compose.prod.yml`。因为 Dockerfile 里要 `COPY requirements.prod.txt`，compose 里要 `build.dockerfile: docker/Dockerfile.svc`——**被引用的必须先存在**（顺序铁律）。

### 10.1 新建 `docker/requirements.prod.txt`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\docker\requirements.prod.txt`

**② 内容**（很短，整段复制）：

```text
# =============================================================
# docker/requirements.prod.txt —— 生产镜像要装的依赖
# =============================================================
# 第一行的 -r requirements.txt 是 pip 的"继承"语法：
#   把开发用的依赖清单整份继承过来，这里只补生产额外需要的。
# 为什么不直接复制粘贴一份：
#   两份清单会立刻开始漂移——哪天你往 requirements.txt 加了个包，
#   生产的这份没有，镜像构建成功但运行时报 ModuleNotFoundError，
#   而且是"只有容器里才会崩"，本机怎么测都测不出来。
-r requirements.txt

# gunicorn：生产级 WSGI/ASGI 服务器。
#   开发时用 `uvicorn main:app`（单进程、改代码热重载方便）；
#   生产用 gunicorn 管多个 uvicorn worker（多核 + 进程挂了自动拉起）。
#   版本锁 23.0.0：不锁的话不同时间构建的镜像里 gunicorn 版本可能不一样，
#   出问题时"本机好的、测试环境坏的"最难查。
gunicorn==23.0.0

# prometheus_client：运行时依赖（app_my/middleware/metrics.py 直接 import 它）。
#   它没写进 requirements.txt，只在开发虚拟环境里装过；
#   生产镜像构建时不报错，但容器一启动 import 就崩、然后无限重启。
#   版本锁 0.26.0，与开发虚拟环境保持一致。
prometheus-client==0.26.0
```

**③ 验证**：

**Git Bash：**

```bash
cat docker/requirements.prod.txt
```

**PowerShell 5.1：**

```powershell
Get-Content docker\requirements.prod.txt
```

**④ 预期输出**：

```
-r requirements.txt
gunicorn==23.0.0
prometheus-client==0.26.0
```

（前面带 `#` 的注释行也算存在，只要这三行有效行在就行。）

> 🔴 **`prometheus-client` 这一行不能少**。它是运行时依赖（`app_my/middleware/metrics.py` 直接 import），但没写进 `requirements.txt`——
> 本机虚拟环境里装了所以跑得好好的，**容器里没有**，构建时不报错、一启动就 `ModuleNotFoundError` 然后无限重启。
> 判据：`docker ps` 里容器 STATUS 显示 `Restarting (3)`，日志末尾是 `Reason: Worker failed to boot.`。

> 🟡 `-r requirements.txt` 是**相对于 `requirements.prod.txt` 所在目录**解析的。Dockerfile 里我们把它俩都拷到了 `/app/` 下的同一层，所以能找到。如果你把 `requirements.prod.txt` 挪到别的目录，这行要改成 `-r ../requirements.txt`。

### 10.2 新建 `docker/Dockerfile.svc`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\docker\Dockerfile.svc`

**② 内容**（整段复制）：

```dockerfile
# =============================================================================
# docker/Dockerfile.svc —— 阶段 10 生产级服务镜像
# =============================================================================
# 和开发机上的跑法有什么不同（一句话一个理由）：
#   ① 用 gunicorn 起多 worker    —— 单进程 uvicorn 一个进程扛不住多核，
#                                    且进程挂了整个服务就没了；gunicorn 会自愈重启 worker
#   ② worker 类是 UvicornWorker  —— 我们的服务是 FastAPI（ASGI，异步），
#                                    必须配 ASGI worker 才能真的并发，用同步 worker 会把
#                                    异步全堵死，/chat/stream 这种长连接直接卡成串行
#   ③ 加 HEALTHCHECK             —— 没有它，容器"起来了但应用没起来"时
#                                    docker ps 显示 Up，只有用户报障才发现
#   ④ 用非 root 用户跑           —— 镜像被拖库时，root 权限等于把整台机器交出去
#   ⑤ --workers 用环境变量传     —— 每个服务的最优 worker 数不一样，
#                                    写死在 Dockerfile 里就得为每个服务建一个镜像
#
# 为什么不能在本机 Windows 上试这套命令：
#   gunicorn 依赖 fcntl / os.fork，这两个 Windows 没有。
#   在 Windows 里 import gunicorn 会直接 ModuleNotFoundError: No module named 'fcntl'。
#   所以它只能在容器里跑——这也是"生产镜像"和"本机开发"必须分开的原因。
#
# 构建（在项目根目录执行）：
#   docker build -f docker/Dockerfile.svc -t ai-chief-svc:prod .
# 验证（起起来看 /health）：
#   docker run --rm -d --name svc-smoke -p 9131:9121 \
#     -e APP_MODULE=services.user.main:app -e WEB_WORKERS=2 ai-chief-svc:prod
#   curl http://127.0.0.1:9131/health
# =============================================================================
FROM docker.m.daocloud.io/library/python:3.13-slim
# 🔴 为什么 FROM 写的是 DaoCloud 完整地址，而不是官方的 `python:3.13-slim`：
#    本机 Docker Desktop 配的 Registry Mirrors（USTC / 163 / 百度）当前全部连不上，
#    写官方地址会在这里直接失败：
#        failed to do request: Head "https://docker.mirrors.ustc.edu.cn/v2/...": EOF
#    DaoCloud 是项目 docker-compose.v3.yml 里一直在用的源（redis 就走的它），
#    本地已有这个基础镜像的缓存，用它既能构建成功、又不引入新的外部依赖。
#    换机器构建如果提示找不到镜像，把这里换成对方能访问的等价镜像即可，内容不受影响。

WORKDIR /app

# PYTHONUTF8=1        容器默认是 ASCII（POSIX locale），中文日志/菜谱数据一打印就 UnicodeEncodeError
# PYTHONDONTWRITEBYTECODE=1  不生成 .pyc：容器只读也用不上，还能让镜像小一点
# PIP_INDEX_URL       国内源，不然拉依赖要十几分钟
ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 🔴 这里**不装 curl**（很多教程会 apt-get install curl，但那是给自己挖坑）：
#    ① 容器内访问 deb.debian.org 常年 502/DNS 失败（实测 trixie 源直接 Bad Gateway），
#       一旦 apt 装不上，整条 docker build 当场失败，后面所有步骤都跑不到；
#    ② slim 镜像自带 Python，用 Python 的 urllib 做健康检查完全够用，
#       多装一个二进制换一份网络依赖，不划算。
#    所以健康检查改用下面 HEALTHCHECK 里的一行 Python。

# 先只拷依赖清单、再装依赖：Docker 按层缓存，
# 这样"改代码重新构建"时这一层能用缓存，不用每次重装一遍依赖。
# 🔴 两份都要拷、且分两行写：`COPY a b ./x` 这种"多源到单目标"的写法，
#    目标不是目录时会直接报 must be a directory，构建当场失败。
COPY requirements.txt ./requirements.txt
COPY docker/requirements.prod.txt ./requirements.prod.txt
RUN pip install --no-cache-dir -r requirements.prod.txt

# 再拷代码（顺序不能反：依赖在前、代码在后，改代码才不会触发依赖重装）
COPY app_my ./app_my
COPY services ./services
COPY main.py ./main.py

# 非 root 运行：容器被攻破时把损失限制在这个用户能碰到的范围内
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# 这两个参数在 docker run / compose 里覆盖，决定了"跑哪个服务"和"起几个 worker"
ENV APP_MODULE=services.user.main:app \
    WEB_WORKERS=2 \
    WEB_PORT=9121 \
    WEB_TIMEOUT=120

EXPOSE 9121

# 健康检查：每 30 秒打一次自己的 /health，连续 3 次失败才标记 unhealthy。
# 用 Python 的 urllib 而不是 curl：
#   slim 镜像里没有 curl（为了不装它我们已经删掉了整条 apt-get），
#   而 Python 一定有，urllib.request.urlopen 就是一次最朴素的 HTTP GET。
#   退出码 0 = 健康；urlopen 对连接失败/非 2xx 都会抛异常，
#   异常会让 python 进程非 0 退出，正好被 Docker 判成 unhealthy。
# start_period=40s 是启动宽限期：服务启动要连数据库、建连接池，
# 不设宽限期的话启动慢一点就会被判 unhealthy，compose 会不停地重启它。
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('WEB_PORT','9121')+'/health',timeout=4).read()" || exit 1

# 用 shell 形式（不是 exec 形式）写 CMD，
# 因为要展开 ${APP_MODULE} 这些环境变量；exec 形式的 JSON 数组不会做变量替换。
CMD gunicorn "${APP_MODULE}" \
      -k uvicorn.workers.UvicornWorker \
      --workers "${WEB_WORKERS}" \
      --bind "0.0.0.0:${WEB_PORT}" \
      --timeout "${WEB_TIMEOUT}" \
      --graceful-timeout 30 \
      --access-logfile - \
      --error-logfile -
```

**③ 验证 —— 只做静态检查，先不构建**（构建在第十五节，很慢）：

**Git Bash：**

```bash
ls -l docker/Dockerfile.svc
grep -c "FROM\|COPY\|HEALTHCHECK\|CMD" docker/Dockerfile.svc
```

**PowerShell 5.1：**

```powershell
Get-Item docker\Dockerfile.svc | Select-Object Name, Length
(Select-String -Path docker\Dockerfile.svc -Pattern "^(FROM|COPY|HEALTHCHECK|CMD)" -AllMatches).Matches.Count
```

**④ 预期输出**（计数）：

```
FROM / COPY / HEALTHCHECK / CMD 指令共 9 条
```

具体是：1 个 `FROM` + 5 个 `COPY` + 1 个 `HEALTHCHECK` + 1 个 `CMD` = 8 条（加上续行里的不算）。**只要你看到 `FROM` 1 条、`COPY` 5 条、`HEALTHCHECK` 1 条、`CMD` 1 条就对了**。

> 🔴 **最容易抄错的两处**：
> 1. `HEALTHCHECK` 那行的 `CMD python -c "..."` —— 里面的双引号和单引号嵌套，复制时容易丢。丢一个引号，构建能过，但健康检查永远失败（容器一直 unhealthy）。
> 2. `CMD gunicorn` 用的是**反斜杠续行**（`\`），不是 PowerShell 的反引号。在 Dockerfile 里必须写 `\`。

### 10.3 新建 `docker/docker-compose.prod.yml`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\docker\docker-compose.prod.yml`

**② 内容**（整段复制，比较长）：

```yaml
# =============================================================================
# docker/docker-compose.prod.yml —— 阶段 10 生产级编排（4 个服务 + Kong 网关）
# =============================================================================
# 和"开发/压测时怎么跑"的区别：
#   开发/压测：在宿主机用 `uvicorn main:app --port 9121` 直接起（改代码热重载方便）
#   生产    ：每个服务一个容器，gunicorn 起多 worker，挂健康检查、资源上限、日志轮转
#
# 基础设施（PostgreSQL 5433 / Redis 6380 / Neo4j / Milvus / 监控栈）**不在这里**，
# 沿用 docker/docker-compose.v3.yml 起的那批容器，理由是沿用项目一贯的原则
# "用到哪个阶段起哪个容器"，而且基础设施本身已经有数据卷、不该和应用的生命周期绑死。
# 应用容器通过 host.docker.internal 访问宿主机上的基础设施（和 Kong 现在访问服务的方式一致）。
#
# 用法（在项目根目录 F:\pycharm_aiprogram\ai_chief 执行）：
#   1) 先确认基础设施在跑：docker compose -f docker/docker-compose.v3.yml ps
#   2) 构建镜像：          docker compose -f docker/docker-compose.prod.yml build
#   3) 起应用：            docker compose -f docker/docker-compose.prod.yml up -d
#   4) 看健康状态：        docker compose -f docker/docker-compose.prod.yml ps
#   5) 停应用：            docker compose -f docker/docker-compose.prod.yml down
#
# 🔴 第一次 up 之前必须有一个 .env 文件（JWT_SECRET、DASHSCOPE_API_KEY 等都从它读）。
#    没有 .env 时容器会起不来，日志里是 pydantic 的 ValidationError
#    "JWT_SECRET 仍为默认值 'change-me-in-production'"。
# =============================================================================

name: ai_chief_prod

# 四个应用服务共用的启动骨架，用 YAML 锚点复用（改一处、四个服务都生效）
x-svc-common: &svc-common
  # 🔴 image 必须写：不带它时 compose 会自己现场构建一份名字类似 ai_chief_prod-svc-user 的镜像，
  #    15.1 用 docker build -t 构建的 ai-chief-svc:prod 根本不会被用上——
  #    结果是"你 build 了新镜像、容器却还跑在 compose 自建的旧镜像里"，改了依赖也不生效。
  #    写上 image 后：compose 直接用这个标签的镜像，本地没有它才会自己 build。
  image: ai-chief-svc:prod
  build:
    context: ..                          # 构建上下文 = 项目根目录（要能 COPY app_my / services / main.py）
    dockerfile: docker/Dockerfile.svc
  # 🔴 env_file 是列表，**后面的文件覆盖前面的同名变量**：
  #    .env 的连接串是"宿主机进程"视角（localhost）；容器里 localhost 指容器自己，
  #    连不上宿主机端口上的 PgBouncer/Redis/Neo4j/Milvus —— 表现为接口 500。
  #    覆盖层必须放列表第二位。⚠️ 不要写在各服务的 environment 里：
  #    YAML 锚点是浅合并，服务自己的 environment 段会**整个替换**锚点的同名 key，覆盖会丢。
  env_file:
    - ../.env                            # 先加载全量配置（宿主机视角）
    - ./env.prod-override                # 再用容器视角覆盖连接串（这个文件见下面 10.4）
  restart: unless-stopped                # 崩了自动拉起；手动 stop 就不起来（不会和人工操作抢）
  # 让容器能访问"宿主机"：Linux 上 Docker 20.10+ 用这个特殊值把宿主机 IP 注入 /etc/hosts
  # 我们的 DB / Redis / Neo4j / Milvus 都跑在宿主机端口上（5433 / 6380 / 7687 / 19530），
  # 没有这一行，容器里的 127.0.0.1 指的是它自己，连数据库一律 Connection refused。
  extra_hosts:
    - "host.docker.internal:host-gateway"
  # 日志轮转：不设的话，一个跑几周的容器日志能把系统盘写满
  logging:
    driver: json-file
    options:
      max-size: "10m"                    # 单个日志文件超过 10MB 就切新文件
      max-file: "3"                      # 最多留 3 个，总共封顶 30MB
  # 资源上限：一个服务内存泄漏时不至于把整台机器拖死
  mem_limit: 768m
  cpus: 1.0

services:
  # ==================== ① user 服务 ====================
  svc-user:
    <<: *svc-common
    container_name: ai_chief_prod_user
    environment:
      APP_MODULE: services.user.main:app   # 决定容器里跑哪份代码（同一个镜像靠它复用给 4 个服务）
      WEB_PORT: "9121"
      WEB_WORKERS: "2"                     # 2 worker：登录是 bcrypt 计算（CPU 密集），多核才有收益
      # 生产环境不再用 mock——压测才打桩，压测完这个开关必须留在 false
      MOCK_LLM: "false"
    ports:
      - "9121:9121"
    healthcheck:
      # 用 Python urllib 探活，不用 curl：镜像里没装 curl（见 Dockerfile.svc 里的说明）
      test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9121/health',timeout=4).read()"]
      interval: 30s
      timeout: 5s
      start_period: 40s                    # 启动宽限：建连接池、连 Neo4j 都要时间
      retries: 3

  # ==================== ② recognizer 服务 ====================
  svc-recognizer:
    <<: *svc-common
    container_name: ai_chief_prod_recognizer
    environment:
      APP_MODULE: services.recognizer.main:app
      WEB_PORT: "9122"
      WEB_WORKERS: "2"
      MOCK_LLM: "false"
    ports:
      - "9122:9122"
    healthcheck:
      # 用 Python urllib 探活，不用 curl：镜像里没装 curl（见 Dockerfile.svc 里的说明）
      test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9122/health',timeout=4).read()"]
      interval: 30s
      timeout: 5s
      start_period: 40s
      retries: 3

  # ==================== ③ recommender 服务 ====================
  svc-recommender:
    <<: *svc-common
    container_name: ai_chief_prod_recommender
    environment:
      APP_MODULE: services.recommender.main:app
      WEB_PORT: "9123"
      WEB_WORKERS: "3"                     # 3 worker：图谱 + 向量检索是 IO 密集，
                                           # 多开一点 worker 能把等待时间重叠掉（压测实测见报告）
      MOCK_LLM: "false"
    ports:
      - "9123:9123"
    healthcheck:
      # 用 Python urllib 探活，不用 curl：镜像里没装 curl（见 Dockerfile.svc 里的说明）
      test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9123/health',timeout=4).read()"]
      interval: 30s
      timeout: 5s
      start_period: 40s
      retries: 3

  # ==================== ④ chat 服务 ====================
  svc-chat:
    <<: *svc-common
    container_name: ai_chief_prod_chat
    environment:
      APP_MODULE: services.chat.main:app
      WEB_PORT: "9124"
      WEB_WORKERS: "3"
      # 🔴 生产必须 remote：chat 服务要**跨服务调用**前三个服务，
      #    local 模式会退化成"在自己进程里跑全部节点"，等于白拆
      SPLIT_MODE: "remote"
      MOCK_LLM: "false"
      # 对话是流式长连接：单请求可能几十秒，gunicorn 默认 30s 超时会把它掐断
      WEB_TIMEOUT: "120"
    ports:
      - "9124:9124"
    healthcheck:
      # 用 Python urllib 探活，不用 curl：镜像里没装 curl（见 Dockerfile.svc 里的说明）
      test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9124/health',timeout=4).read()"]
      interval: 30s
      timeout: 5s
      start_period: 40s
      retries: 3
    depends_on:
      # depends_on 只保证"启动顺序"，不保证"对面已经能服务"——
      # 真正保险靠 healthcheck + 重试，chat 侧的 ServiceClient 自带熔断器（阶段 9 加的）
      svc-user:
        condition: service_started
      svc-recognizer:
        condition: service_started
      svc-recommender:
        condition: service_started

  # ==================== ⑤ Kong 网关 ====================
  # 复用阶段 9 的 kong.yml（5 条路由 / 4 个 service / 限流插件），一个字都不用改：
  # 服务从"宿主机进程"变成"容器"，但端口没变，Kong 里的 host.docker.internal:9121 照样能通。
  kong:
    # 🔴 写国内源的完整地址 + 与本地已缓存的版本号一致（3.7）：
    #    官方 `kong:3.9-ubuntu` 在本机会去 Docker Hub 拉，
    #    而本机配的三个 Registry Mirrors（USTC/163/百度）当前都连不上，
    #    结果是 compose up 卡在 "pulling kong" 最后失败。
    #    换成 DaoCloud 源 + 本地已有的 3.7，直接命中缓存，秒起。
    #    （阶段 9 的 docker-compose.v3.yml 里用的也是这个镜像，版本保持一致。）
    image: docker.m.daocloud.io/library/kong:3.7
    container_name: ai_chief_prod_kong
    restart: unless-stopped
    environment:
      KONG_DATABASE: "off"                                  # DB-less：配置全在 yaml 里，不额外起 Postgres
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      KONG_PROXY_LISTEN: "0.0.0.0:9100"                     # 用户入口
      KONG_ADMIN_LISTEN: "0.0.0.0:9101"                     # 管理口（容器内）
      # 🔴 必须限制 worker 数：Kong 默认一个 CPU 核起一个 worker（本机 13 核 = 13 个），
      #    512m 内存限制下被 OOM 杀（日志：worker process ... exited on signal 9），
      #    表现为端口在监听但请求全部超时（curl 卡住直到 timeout）。2 个对网关绰绰有余。
      KONG_NGINX_WORKER_PROCESSES: "2"
    volumes:
      - ./kong/kong.yml:/etc/kong/kong.yml:ro               # ro = 只读挂载，容器改不了配置
    ports:
      - "9100:9100"                                         # 网关入口（和开发时同一个端口）
      - "9105:9101"                                         # 管理口映射到 9105（避开 9101 已被 worker metrics 占用）
    extra_hosts:
      - "host.docker.internal:host-gateway"
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    mem_limit: 512m
    healthcheck:
      # Kong 自带 kong health 子命令，直接用，不需要额外装东西
      test: ["CMD", "kong", "health"]
      interval: 30s
      timeout: 5s
      retries: 3
    depends_on:
      svc-user:
        condition: service_started
      svc-chat:
        condition: service_started
```

**③ 验证 —— 让 Docker 自己解析一遍**（这一步**必须做**，YAML 合法 ≠ compose 合法）：

**Git Bash：**

```bash
docker compose -f docker/docker-compose.prod.yml config > /dev/null; echo "退出码=$?"
```

**PowerShell 5.1：**

```powershell
docker compose -f docker/docker-compose.prod.yml config | Out-Null
"退出码=$LASTEXITCODE"
```

**④ 预期输出**：

```
退出码=0
```

> 🔴 **退出码必须是 0**。非 0 时把 `> /dev/null` 去掉重跑一次看具体报错。最常见的两类：
> - `services.svc-user.build.context` 路径不对 → 确认你是**在项目根目录**执行的，且 `docker/Dockerfile.svc` 已存在（10.2 做完没）；
> - YAML 缩进错误 → 逐行对照上面代码块，`environment:` 下的键必须比 `environment:` 多缩进 2 格。

再确认 5 个服务都被解析出来了：

**Git Bash：**

```bash
docker compose -f docker/docker-compose.prod.yml config --services
```

**PowerShell 5.1：**

```powershell
docker compose -f docker/docker-compose.prod.yml config --services
```

**预期输出**（本次实测原文）：

```
svc-recommender
svc-user
svc-recognizer
svc-chat
kong
```

（顺序是 compose 文件里的声明顺序，不是字母序，谁先谁后无所谓，**5 行一个都不能少**。）

**本节检查点**：4 个文件都在（`requirements.prod.txt` / `Dockerfile.svc` / `docker-compose.prod.yml` / `env.prod-override`）、`docker compose config` 退出码 0、`--services` 列出 5 个。

### 10.4 新建 `docker/env.prod-override`（🟢 勘误新增，没有它接口必 500）

**为什么**：`.env` 里的连接串写的是 `localhost` —— 那是**宿主机进程**（uvicorn）的视角。容器里 `localhost` 指**容器自己**，连不上宿主机端口上的 PgBouncer/Redis/Neo4j。实测翻车表现：走网关登录返回 500，容器日志：

```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at "localhost" (::1), port 9432 failed: Connection refused
```

这是踩坑数最深的一个：容器显示 `(healthy)`（healthcheck 只探自己），接口却全 500。

**在项目 `docker/` 目录新建 `env.prod-override`，内容如下（整份替换）**：

```properties
# =============================================================
# docker/env.prod-override —— 生产容器专用环境覆盖层
# =============================================================
# 为什么要有这个文件：
#   项目根的 .env 里的连接串写的是 localhost —— 那是**宿主机进程**（uvicorn）的视角。
#   容器里 localhost 指容器自己，连不上宿主机端口上的 PgBouncer/Redis/Milvus/Loki，
#   表现为接口 500，日志：connection to server at "localhost", port 9432 failed: Connection refused。
#
# 生效方式：docker-compose.prod.yml 的 env_file 是一个列表，**后面的文件覆盖前面的同名变量**：
#   env_file:
#     - ../.env                  # 先加载全量配置（宿主机视角）
#     - ./env.prod-override      # 再用容器视角覆盖下面这几个
#
# 注意：改完这个文件要 `docker compose -f docker/docker-compose.prod.yml up -d` 重建容器才生效。
# =============================================================

DATABASE_URL=postgresql+psycopg2://ai_sichu:ai_sichu@host.docker.internal:9432/ai_sichu
REDIS_URL=redis://host.docker.internal:6380/0
MILVUS_URI=http://host.docker.internal:19530
LOKI_URL=http://host.docker.internal:3100
# Neo4j 在 .env 里没写（config.py 用默认值 bolt://localhost:7687），容器里同样要指到宿主机
NEO4J_URI=bolt://host.docker.internal:7687
```

**验证**（Git Bash / PowerShell 通用）：

```bash
docker compose -f docker/docker-compose.prod.yml up -d
docker exec ai_chief_prod_user printenv DATABASE_URL
```

**预期输出**：

```
postgresql+psycopg2://ai_sichu:ai_sichu@host.docker.internal:9432/ai_sichu
```

> 🔴 必须是 `host.docker.internal`。还是 `localhost` 说明覆盖层没生效——检查 compose 的 `env_file` 列表里它在 `.env` **后面**。

---

## 十一、落盘代码（五）：CI/CD 与本地等价验证

### 11.1 新建 `.gitee/workflows/pipeline.yml`

**① 路径**：先建目录（注意 `.gitee` 是**带点开头的隐藏目录**），再建文件。

**Git Bash：**

```bash
mkdir -p .gitee/workflows
ls -d .gitee/workflows
```

**PowerShell 5.1：**

```powershell
New-Item -ItemType Directory -Force -Path .gitee\workflows | Out-Null
Get-Item .gitee\workflows | Select-Object FullName
```

然后新建 `F:\pycharm_aiprogram\ai_chief\.gitee\workflows\pipeline.yml`，内容如下：

```yaml
# =============================================================================
# .gitee/workflows/pipeline.yml —— 阶段 10 持续集成流水线（Gitee Go）
# =============================================================================
# 放在仓库根目录的 .gitee/workflows/ 下，Gitee 会自动识别并接管。
#
# 🔴 必须先说清楚一件事（别被"配置写完就以为能跑"骗了）：
#    任何云端 CI（Gitee Go / GitHub Actions / GitLab CI）的 YAML **都没法在你本机实跑**，
#    生效与否取决于云端怎么解析这份文件、以及云端构建环境里装了什么。
#    所以本阶段额外给了 scripts/ci_local.sh / ci_local.ps1：
#    把流水线里每一条命令在你本机按顺序跑一遍。
#    它能证明的是"这些命令本身是通的"，不能保证"云端一定接受这份 YAML 的语法"。
#    真要确认，只能 push 到 Gitee 看构建记录。
#
# 流水线干什么（两个阶段）：
#   阶段一 test：装依赖 → 跑单元测试（不依赖任何外部服务）
#   阶段二 build：校验生产编排文件可解析 + 压测脚本语法正确 → 构建生产镜像
#
# 为什么单测只跑 tests/unit 而不是整个 tests：
#     tests/integration 下的用例需要后端服务真的起着（它们会 HTTP 打 127.0.0.1:9002），
#     CI 容器里没有后端服务也没有数据库，跑必然 ConnectionError。
#     云端 CI 里"起全套微服务 + 数据库"代价太大，所以只跑不依赖服务的纯单测——
#     这是绝大多数真实项目 CI 的常态（集成测试放单独的流水线/环境里跑）。
# =============================================================================

version: '1.0'

# name 是流水线的唯一标识（英文、无空格）；displayName 是在 Gitee 页面上显示的名字
name: ai-chief-ci
displayName: 'AI私厨 v3.0 持续集成'

# ---------- 触发器 ----------
triggers:
  push:
    # PRECISE = 精确匹配分支：只有 push 到这些分支才触发
    - matchType: PRECISE
      branch: master
    - matchType: PRECISE
      branch: main

# ---------- 阶段 ----------
stages:
  # ============ 阶段一：测试 ============
  - stage:
      name: test-stage
      displayName: '单元测试'
      failFast: false          # false = 这个阶段里有 step 失败也继续跑完剩下的，方便一次看全所有错误
      steps:
        - step: build@python    # Gitee Go 提供的 Python 构建环境
          name: run-pytest
          displayName: '安装依赖并跑单测'
          inputs:
            pythonVersion: '3.13'
            # 每条命令都在仓库根目录下执行（Gitee Go 已自动 clone 并 cd 进去）
            # set -e：任何一条命令失败就立刻让这个 step 失败——
            # 不加的话 pip 装失败也会继续往下跑，最后 pytest 报一堆莫名错误，很难定位
            goals: |
              set -e
              echo "=== Python 版本 ==="
              python -V
              echo "=== 安装依赖 ==="
              python -m pip install --upgrade pip
              pip install -r requirements.txt
              echo "=== 跑单元测试（不依赖外部服务）==="
              python -m pytest tests/unit -q --no-header -p no:cacheprovider

  # ============ 阶段二：构建 ============
  - stage:
      name: build-stage
      displayName: '配置校验与镜像构建'
      failFast: true           # true = 失败就停，配置都解析不了就没必要继续构建镜像
      steps:
        - step: build@python
          name: verify-config
          displayName: '校验配置与脚本'
          inputs:
            pythonVersion: '3.13'
            goals: |
              set -e
              pip install --upgrade pip
              pip install -r requirements.txt
              pip install pyyaml
              echo "=== 校验生产编排 docker-compose.prod.yml 可被解析 ==="
              python -c "import yaml;yaml.safe_load(open('docker/docker-compose.prod.yml',encoding='utf-8'));print('compose OK')"
              echo "=== 校验压测脚本语法 ==="
              python -m py_compile benchmarks/locustfile.py scripts/locust_report.py
              echo "=== 冒烟：核心模块能被导入 ==="
              python -c "import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm; print('import OK')"

        - step: build@docker
          name: build-image
          displayName: '构建生产镜像'
          inputs:
            # 相对仓库根目录
            dockerFileName: docker/Dockerfile.svc
            dockerImageName: ai-chief-svc
            dockerImageTag: 'stage10'
# -----------------------------------------------------------------------------
# 🟡 关于最后一个 step 的两种写法：
#    Gitee Go 不同版本对 docker 构建 step 的参数位置要求不一样：
#      新版本：参数直接写在 step 下（如上）
#      老版本：参数要挪到 inputs: 下面
#    push 之后如果这个 step 报"参数不存在"，把 dockerFileName / dockerImageName / dockerImageTag
#    三行整体缩进到 inputs: 下面即可。命令层面不受影响。
#    若你的 Gitee 仓库没开通制品库/镜像构建能力，直接删掉这个 step，
#    前面两个 step 已经能构成一条"绿色流水线"。
# -----------------------------------------------------------------------------
```

**③ 验证 —— YAML 能被解析**（只验证语法，不代表 Gitee 一定接受）：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -c "import yaml; d=yaml.safe_load(open('.gitee/workflows/pipeline.yml',encoding='utf-8')); print('name=', d['name']); print('stages=', [s['stage']['name'] for s in d['stages']])"
```

**PowerShell 5.1：**

```powershell
@'
import yaml
d = yaml.safe_load(open(".gitee/workflows/pipeline.yml", encoding="utf-8"))
print("name=", d["name"])
print("stages=", [s["stage"]["name"] for s in d["stages"]])
'@ | Set-Content -Encoding UTF8 _t.py
.\.venv3\Scripts\python.exe _t.py
Remove-Item _t.py
```

**④ 预期输出**：

```
name= ai-chief-ci
stages= ['test-stage', 'build-stage']
```

### 11.2 新建 `scripts/ci_local.sh`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\scripts\ci_local.sh`

**② 内容**（整段复制）：

```bash
#!/usr/bin/env bash
# =============================================================================
# scripts/ci_local.sh —— 阶段 10：在本地把 CI 流水线的每一步跑一遍（Git Bash 版）
# =============================================================================
# 为什么要这个脚本：
#   云端 CI（Gitee Go）的 YAML 你在本机**跑不了**——它只在 Gitee 服务器上生效。
#   如果直接把 .gitee/workflows/pipeline.yml 提交上去才发现命令写错，
#   一来一回要好几分钟，而且错误藏在云端日志里不好查。
#   这个脚本把流水线里每一条命令按顺序在你本机跑一遍：
#   能过 = 这些命令本身是通的，push 之后失败的风险就只剩"云端环境差异"这一项。
#
# 和流水线唯一的区别：
#   流水线里是 `pip install -r requirements.txt`（每次全新环境都要装，慢）；
#   这里改成"检查关键依赖在不在"，缺哪个提示哪个——本机早就装好了，
#   没必要每次跑都重装一遍（本项目依赖装一次要 5~6 分钟）。
#
# 用法（项目根目录执行）：
#   bash scripts/ci_local.sh
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."

# 解释器允许覆盖：PY=/path/to/python.exe bash scripts/ci_local.sh
PY="${PY:-./.venv3/Scripts/python.exe}"
if [ ! -f "$PY" ]; then
  echo "[中止] 找不到虚拟环境解释器: $PY"
  echo "       请在项目根目录执行，或显式指定：PY=<绝对路径> bash scripts/ci_local.sh"
  exit 1
fi

FAILED=0
# 小工具：跑一条命令，成功打 PASS、失败打 FAIL 并记一笔（不中断，跑完全部再看）
run_step() {
  local title="$1"; shift
  echo ""
  echo "--------------------------------------------------------------"
  echo " 步骤: $title"
  echo "--------------------------------------------------------------"
  if "$@"; then
    echo "[PASS] $title"
  else
    echo "[FAIL] $title"
    FAILED=$((FAILED + 1))
  fi
}

echo "=============================================================="
echo " 阶段 10 · CI 本地等价验证  $(date '+%Y-%m-%d %H:%M:%S')"
echo " 对应 .gitee/workflows/pipeline.yml 的每个 step"
echo "=============================================================="

# ---------- 阶段一：单元测试（对应 CI 的 test-stage） ----------
run_step "Python 版本（CI 用的是 3.13）" "$PY" -V

# CI 里是 pip install -r requirements.txt；本地改成"检查关键依赖能 import"
run_step "检查关键依赖是否已安装" "$PY" -c "
import importlib.util, sys
need = ['fastapi', 'uvicorn', 'sqlalchemy', 'redis', 'pytest', 'httpx', 'yaml', 'pydantic_settings']
missing = [m for m in need if importlib.util.find_spec(m) is None]
if missing:
    print('缺失依赖:', missing)
    print('请执行: $PY -m pip install -r requirements.txt')
    sys.exit(1)
print('关键依赖齐全:', len(need), '个')
"

# 只跑 tests/unit：这一批不依赖任何外部服务，是 CI 里唯一能稳定跑通的部分
run_step "跑单元测试（tests/unit，不依赖外部服务）" \
  "$PY" -m pytest tests/unit -q --no-header -p no:cacheprovider

# ---------- 阶段二：配置与脚本校验（对应 CI 的 build-stage 第一个 step） ----------
run_step "校验生产编排 docker-compose.prod.yml 可被解析" "$PY" -c "
import yaml
d = yaml.safe_load(open('docker/docker-compose.prod.yml', encoding='utf-8'))
assert 'services' in d, 'compose 文件里没有 services'
print('生产编排解析通过，共', len(d['services']), '个服务:', list(d['services']))
"

run_step "校验压测脚本语法" "$PY" -m py_compile benchmarks/locustfile.py scripts/locust_report.py

run_step "冒烟：核心模块能被导入" "$PY" -c "
import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm
print('核心模块 import OK（含阶段10新增的 mock_llm）')
"

# ---------- 镜像构建（本机也能做，但很慢，默认跳过） ----------
echo ""
echo "--------------------------------------------------------------"
echo " 镜像构建（CI 的最后一个 step）——默认跳过"
echo " 想在本机真跑一遍就执行："
echo "   docker build -f docker/Dockerfile.svc -t ai-chief-svc:prod ."
echo "--------------------------------------------------------------"

echo ""
echo "=============================================================="
if [ "$FAILED" -eq 0 ]; then
  echo " 全部通过 ✅ —— 流水线的命令在本机都跑得通，可以 push 了"
else
  echo " 有 $FAILED 个步骤失败 ❌ —— 修完再 push，否则云端一定会红"
fi
echo "=============================================================="
exit "$FAILED"
```

### 11.3 新建 `scripts/ci_local.ps1`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\scripts\ci_local.ps1`

**② 内容**（整段复制）：

```powershell
# =============================================================================
# scripts/ci_local.ps1 —— 阶段 10：本地跑一遍 CI 的每个步骤（PowerShell 5.1 版）
# =============================================================================
# 和 scripts/ci_local.sh 是同一件事的两种终端写法。
# 作用：把 .gitee/workflows/pipeline.yml 里的命令在本机跑一遍——
#       云端流水线你没法在本地跑，但如果这些命令本机都通，push 上去出问题的概率就很低。
#
# 用法（项目根目录执行）：
#   .\scripts\ci_local.ps1
#
# 🔴 如果提示"无法加载文件，因为在此系统上禁止运行脚本"，先执行一次：
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    （只对当前窗口生效，关掉就恢复）
# =============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$PY = if ($env:BENCH_PY) { $env:BENCH_PY } else { Join-Path $Root '.venv3\Scripts\python.exe' }
if (-not (Test-Path $PY)) {
    Write-Host "[中止] 找不到虚拟环境解释器: $PY" -ForegroundColor Red
    exit 1
}

$Failed = 0

# 跑一条命令并记录成败。
# 用 $LASTEXITCODE 判断外部命令结果（不能用 $?，那是判断 PowerShell 语句自己的）
function Invoke-Step {
    param([string]$Title, [scriptblock]$Action)
    Write-Host ""
    Write-Host "--------------------------------------------------------------"
    Write-Host " 步骤: $Title"
    Write-Host "--------------------------------------------------------------"
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[FAIL] $Title（退出码 $LASTEXITCODE）" -ForegroundColor Red
            $script:Failed++
        } else {
            Write-Host "[PASS] $Title"
        }
    } catch {
        Write-Host "[FAIL] $Title —— $($_.Exception.Message)" -ForegroundColor Red
        $script:Failed++
    }
}

Write-Host "=============================================================="
Write-Host (" 阶段 10 · CI 本地等价验证  " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host " 对应 .gitee/workflows/pipeline.yml 的每个 step"
Write-Host "=============================================================="

# ---------- 阶段一：单元测试 ----------
Invoke-Step "Python 版本（CI 用的是 3.13）" { & $PY -V }

Invoke-Step "检查关键依赖是否已安装" {
    & $PY -c @"
import importlib.util, sys
need = ['fastapi','uvicorn','sqlalchemy','redis','pytest','httpx','yaml','pydantic_settings']
missing = [m for m in need if importlib.util.find_spec(m) is None]
if missing:
    print('缺失依赖:', missing); sys.exit(1)
print('关键依赖齐全:', len(need), '个')
"@
}

Invoke-Step "跑单元测试（tests/unit，不依赖外部服务）" {
    & $PY -m pytest tests/unit -q --no-header -p no:cacheprovider
}

# ---------- 阶段二：配置与脚本校验 ----------
Invoke-Step "校验生产编排 docker-compose.prod.yml 可被解析" {
    & $PY -c @"
import yaml
d = yaml.safe_load(open('docker/docker-compose.prod.yml', encoding='utf-8'))
assert 'services' in d, 'compose 文件里没有 services'
print('生产编排解析通过，共', len(d['services']), '个服务:', list(d['services']))
"@
}

Invoke-Step "校验压测脚本语法" {
    & $PY -m py_compile benchmarks/locustfile.py scripts/locust_report.py
}

Invoke-Step "冒烟：核心模块能被导入" {
    & $PY -c @"
import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm
print('核心模块 import OK（含阶段10新增的 mock_llm）')
"@
}

Write-Host ""
Write-Host "=============================================================="
if ($Failed -eq 0) {
    Write-Host " 全部通过 —— 流水线的命令在本机都跑得通，可以 push 了" -ForegroundColor Green
} else {
    Write-Host " 有 $Failed 个步骤失败 —— 修完再 push，否则云端一定会红" -ForegroundColor Red
}
Write-Host "=============================================================="
exit $Failed
```

> 🟡 注意 `ci_local.ps1` 里用了 **here-string `@"..."@`** 来写多行 Python。这个写法有个硬要求：**结尾的 `"@` 必须顶格**（行首不能有空格），否则 PowerShell 会一直等输入、卡住不返回。整段复制就不会有问题；如果你手动缩进过它，就会卡。
>
> 🔴 同 9.2 的勘误：这个文件也必须存成 **UTF-8 with BOM**（它含中文，无 BOM 会在 11.3 的语法检查里报同样的三个错误）。自查命令把路径换成 `scripts\ci_local.ps1` 即可。

**③ 验证（两个脚本都只做语法检查，真跑在第十六节）**：

**Git Bash：**

```bash
bash -n scripts/ci_local.sh && echo "ci_local.sh 语法 OK"
```

**PowerShell 5.1：**

```powershell
& "C:\Program Files\Git\bin\bash.exe" -n scripts/ci_local.sh
if ($LASTEXITCODE -eq 0) { "ci_local.sh 语法 OK" }
$err = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path scripts\ci_local.ps1).Path, [ref]$null, [ref]$err)
if ($err.Count -eq 0) { "ci_local.ps1 语法 OK" } else { $err | ForEach-Object { $_.Message } }
```

**④ 预期输出**：

```
ci_local.sh 语法 OK
ci_local.ps1 语法 OK
```

**本节检查点**：`pipeline.yml` 能解析出 2 个 stage、两个 ci_local 脚本语法 OK。

---

## 十二、落盘代码（六）：验收脚本

### 12.1 新建 `scripts/verify_stage10.py`

**① 路径**：`F:\pycharm_aiprogram\ai_chief\scripts\verify_stage10.py`

**② 内容**（整段复制）：

```python
# scripts/verify_stage10.py —— v3 阶段 10 验收脚本
#
# 这个脚本干什么：
#     一句话回答"阶段 10 到底做完没有"。它按交付物逐条检查，最后给一个总的
#     OK / FAIL 结论。不合格就打印缺什么、去哪补。
#
#     它和 pytest 的分工：
#         pytest     —— 测"代码逻辑对不对"（阶段 9 有 124 个，本阶段新增 17 个）
#         本脚本     —— 测"该有的东西在不在、能不能跑起来"（文件、配置、容器、端口、报告）
#     两者都绿，才算这个阶段收官。
#
# 用法（在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#     .\.venv3\Scripts\python.exe scripts\verify_stage10.py
#     .\.venv3\Scripts\python.exe scripts\verify_stage10.py --bench-dir reports/bench_20261020_143045
#
# 退出码：0 = 全过；1 = 有 FAIL。可直接用于 CI 判断。
import argparse
import os
import subprocess
import sys
from pathlib import Path

# 把项目根目录塞进 sys.path。
# 为什么需要：直接 `python scripts\verify_stage10.py` 时，Python 只把 scripts\ 当作模块搜索路径，
# 于是 `import app_my...` 会报 ModuleNotFoundError: No module named 'app_my'。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

PASS, FAIL = "OK  ", "FAIL"
_results: list = []          # [(标记, 说明, 细节)]


def check(label: str, ok: bool, detail: str = "") -> bool:
    """记录一条检查结果并打印。全程收集，最后统一统计，不中途退出。"""
    _results.append((PASS if ok else FAIL, label, detail))
    print("  %s %-46s %s" % (PASS if ok else FAIL, label, detail))
    return ok


# ============================================================
# ① 交付文件是否都在
# ============================================================
def check_files() -> None:
    print("\n[1] 交付文件")
    expected = {
        # LLM 打桩（阶段 10 新增的业务代码）
        "app_my/core/mock_llm.py": "对话模型打桩器",
        "app_my/knowledge/embedding.py": "向量打桩（含 MOCK_DIMENSION）",
        "app_my/core/config.py": "MOCK_LLM 配置开关",
        "app_my/core/model_router.py": "统一入口的打桩早返回分支",
        # 压测
        "benchmarks/locustfile.py": "压测脚本（三场景）",
        "scripts/run_bench.sh": "压测编排（Git Bash）",
        "scripts/locust_report.py": "压测结果汇总器",
        # 生产部署
        "docker/Dockerfile.svc": "生产镜像定义",
        "docker/requirements.prod.txt": "生产依赖（含 gunicorn）",
        "docker/docker-compose.prod.yml": "生产编排（4 服务 + 网关）",
        # CI/CD
        ".gitee/workflows/pipeline.yml": "Gitee Go 流水线",
        # 测试
        "tests/unit/test_stage10_mock_llm.py": "打桩单元测试",
        "tests/unit/test_stage10_bench_report.py": "汇总器单元测试",
    }
    for rel, desc in expected.items():
        p = Path(_ROOT) / rel
        ok = p.is_file() and p.stat().st_size > 0
        check(rel, ok, f"{desc}" + ("" if ok else f"（缺失或为空）"))


# ============================================================
# ② 打桩代码是否真的接上了（不能只看文件在不在）
# ============================================================
def check_mock_wiring() -> None:
    print("\n[2] LLM 打桩接线")
    # 2.1 配置项存在且默认关闭（默认必须是关的，否则正常跑测试会误伤）
    try:
        from app_my.core.config import settings
        check("config 里有 MOCK_LLM 配置", hasattr(settings, "MOCK_LLM"),
              f"当前值={getattr(settings, 'MOCK_LLM', 'N/A')}")
        check("MOCK_LLM 默认是关闭的", settings.MOCK_LLM is False,
              "压测才临时打开；默认开着会让普通请求全部返回假数据")
    except Exception as exc:
        check("能读取 settings", False, f"{type(exc).__name__}: {exc}")

    # 2.2 统一入口里真的有打桩分支
    try:
        from app_my.core import model_router
        src = Path(model_router.__file__).read_text(encoding="utf-8")
        check("ainvoke_routed 里有 MOCK_LLM 分支", "MOCK_LLM" in src,
              "打桩必须挂在唯一出口上，否则绕过去了照样真调模型")
        check("打桩分支不挂计费回调", "ainvoke_mock" in src,
              "mock 没有真 token，不该记账")
    except Exception as exc:
        check("能导入 model_router", False, f"{type(exc).__name__}: {exc}")

    # 2.3 embedding 打桩：维度必须是 1024（和 Milvus 集合一致）
    try:
        from app_my.knowledge.embedding import MOCK_DIMENSION
        from app_my.knowledge.milvus_store import DIMENSION
        check("打桩向量维度与 Milvus 集合一致",
              MOCK_DIMENSION == DIMENSION,
              f"打桩={MOCK_DIMENSION} Milvus={DIMENSION}")
    except Exception as exc:
        check("能读取向量维度常量", False, f"{type(exc).__name__}: {exc}")

    # 2.4 打桩输出真的能被下游解析（这是压测数据可信的前提）
    try:
        import asyncio
        from app_my.core.mock_llm import ainvoke_mock
        from app_my.agents.recognizer import parse_json_payload
        data = parse_json_payload(asyncio.run(ainvoke_mock("extract", [])).content)
        n = len(data.get("ingredients") or [])
        check("extract 打桩能被识别节点解析", n >= 1, f"解析出 {n} 种食材（0 会导致链路空转）")
    except Exception as exc:
        check("打桩输出可被解析", False, f"{type(exc).__name__}: {exc}")


# ============================================================
# ③ 五个服务是否都健康
# ============================================================
def check_services() -> None:
    print("\n[3] 服务健康")
    try:
        import requests
    except ImportError:
        check("requests 可用", False, "装一下：pip install requests")
        return
    for port, name in ((9002, "单体"), (9121, "user"), (9122, "recognizer"),
                       (9123, "recommender"), (9124, "chat")):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=3)
            ok = r.status_code == 200
            detail = f"{name}" + (f" → {r.json().get('status')}" if ok else f" HTTP {r.status_code}")
        except Exception:
            ok, detail = False, f"{name} 连不上（端口 {port}）"
        check(f"端口 {port} 健康", ok, detail)


# ============================================================
# ④ 生产编排能否被 Docker 解析
# ============================================================
def check_prod_compose() -> None:
    print("\n[4] 生产编排与 CI 配置")
    # 4.1 先用 PyYAML 兜一层（不依赖 docker 命令）
    try:
        import yaml
        for rel in ("docker/docker-compose.prod.yml", ".gitee/workflows/pipeline.yml"):
            p = Path(_ROOT) / rel
            try:
                yaml.safe_load(p.read_text(encoding="utf-8"))
                check(f"{rel} YAML 可解析", True)
            except Exception as exc:
                check(f"{rel} YAML 可解析", False, f"{type(exc).__name__}: {exc}")
    except ImportError:
        check("PyYAML 可用", False, "装一下：pip install pyyaml")

    # 4.2 compose 必须能被 docker 自己解析（YAML 合法 ≠ compose 合法）
    compose = Path(_ROOT) / "docker" / "docker-compose.prod.yml"
    if compose.is_file():
        try:
            proc = subprocess.run(
                ["docker", "compose", "-f", str(compose), "config"],
                capture_output=True, text=True, timeout=60, cwd=str(Path(_ROOT) / "docker"),
            )
            check("docker compose config 通过", proc.returncode == 0,
                  "" if proc.returncode == 0 else (proc.stderr or proc.stdout)[:120])
        except FileNotFoundError:
            check("docker 命令可用", False, "没装 Docker 或不在 PATH 里")
        except subprocess.TimeoutExpired:
            check("docker compose config 通过", False, "超时")

    # 4.3 compose 里必须真的定义了 4 个服务 + 网关
    try:
        import yaml
        data = yaml.safe_load(compose.read_text(encoding="utf-8"))
        svcs = set(data.get("services", {}))
        need = {"svc-user", "svc-recognizer", "svc-recommender", "svc-chat", "kong"}
        check("compose 含 4 个服务 + 网关", need <= svcs,
              f"实际={sorted(svcs)}" if not need <= svcs else "")
    except Exception as exc:
        check("能读取 compose 结构", False, f"{type(exc).__name__}: {exc}")


# ============================================================
# ⑤ 压测产物与报告
# ============================================================
def check_bench(bench_dir: str) -> None:
    print("\n[5] 压测产物")
    if not bench_dir:
        print("  --   （跳过：没指定 --bench-dir。跑完 bash scripts/run_bench.sh 后可加这个参数复查）")
        return
    d = Path(bench_dir)
    if not d.is_absolute():
        d = Path(_ROOT) / d
    if not d.is_dir():
        check("压测输出目录存在", False, f"{d} 不存在")
        return

    stats_files = sorted(d.glob("*_stats.csv"))
    check("存在压测结果 CSV", len(stats_files) > 0, f"找到 {len(stats_files)} 个")

    # 单体和网关的档位必须一致，否则对比表出不来
    mono = {f.name.split("_u")[1].split("_")[0] for f in stats_files if f.name.startswith("monolith")}
    gw = {f.name.split("_u")[1].split("_")[0] for f in stats_files if f.name.startswith("gateway")}
    check("单体与网关都跑了压测", bool(mono) and bool(gw),
          f"单体档位={sorted(mono)} 网关档位={sorted(gw)}")

    report = d / "压测报告.md"
    if check("压测报告已生成", report.is_file(), str(report.name) if report.is_file() else "缺失"):
        text = report.read_text(encoding="utf-8")
        # 表格必须一行一行渲染，不能挤成一行
        check("报告表格分行正常", any(line.startswith("| 目标 |") for line in text.splitlines()),
              "如果这里挂了，多半是拼接时漏了换行")
        check("报告含拐点结论", "拐点" in text)


# ============================================================
# 汇总
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 10 验收")
    parser.add_argument("--bench-dir", default="", help="run_bench.sh 的输出目录")
    args = parser.parse_args()

    print("=" * 78)
    print(" AI 私厨 v3.0 · 阶段 10 验收")
    print("=" * 78)

    check_files()
    check_mock_wiring()
    check_services()
    check_prod_compose()
    check_bench(args.bench_dir)

    failed = [r for r in _results if r[0] == FAIL]
    print("\n" + "=" * 78)
    if failed:
        print(" 验收未通过：%d / %d 项失败" % (len(failed), len(_results)))
        for _tag, label, detail in failed:
            print("   - %s  %s" % (label, detail))
        print("=" * 78)
        return 1
    print(" 验收通过：%d 项全部 OK" % len(_results))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**③ 验证（只确认语法，真跑在第十六节）**：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -m py_compile scripts/verify_stage10.py && echo "语法 OK"
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe -m py_compile scripts\verify_stage10.py
if ($LASTEXITCODE -eq 0) { "语法 OK" }
```

**④ 预期输出**：

```
语法 OK
```

> 🟡 这个脚本依赖 `requests`（用来探 5 个端口）。你项目里肯定有（阶段 9 的服务间调用就用它）。万一没有：`./.venv3/Scripts/python.exe -m pip install requests`。

**本节检查点**：`verify_stage10.py` 语法 OK。

到这里，**所有代码都落盘完了**。下面是"跑"的部分。

---

## 十三、跑压测：前置条件

🔴 **这一节是整个阶段最容易出错的地方**。压测命令本身很简单（第十四节就一条），但如果前置条件没满足，你跑出来的会是"限流的数字"而不是"架构的数字"，报告里全是 429，白跑一轮。

五个条件，一个一个来：

| # | 条件 | 为什么 | 怎么做 |
|---|---|---|---|
| ① | 5 个服务带 `MOCK_LLM=true` 重启 | 否则每次请求都真调 DashScope，测的是厂商 | 13.2 |
| ② | 服务端限流调到极大 | 默认 60/min、20/min，压测几秒就 429 | 13.2 同一条命令 |
| ③ | 清掉当天租户配额 | free 套餐 chat_daily 上限 50 次 | 13.3 |
| ④ | Kong 网关限流调高 | chat 默认 120/min = 2 QPS | 13.4 |
| ⑤ | 5 个服务都健康 | 有一台没起，压测全是 ConnectionError | 13.5 |

### 13.1 停掉现在正在跑的 5 个服务

你现在有 5 个 uvicorn 进程占着 9002 / 9121 / 9122 / 9123 / 9124。要换成带 mock 的，必须先停掉。

**Git Bash：**

```bash
for p in 9002 9121 9122 9123 9124; do
  pid=$(netstat -ano | grep ":$p " | grep LISTENING | awk '{print $5}' | head -1)
  if [ -n "$pid" ]; then echo "停端口 $p（PID $pid）"; taskkill //PID "$pid" //F > /dev/null 2>&1; fi
done
sleep 2
for p in 9002 9121 9122 9123 9124; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 2 "http://127.0.0.1:$p/health")
  echo "端口 $p -> $code"
done
```

**PowerShell 5.1：**

```powershell
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        $pidToKill = $conn[0].OwningProcess
        Write-Host "停端口 $p（PID $pidToKill）"
        Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 2
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$p/health" -TimeoutSec 2 -UseBasicParsing
        Write-Host "端口 $p -> $($r.StatusCode)"
    } catch {
        Write-Host "端口 $p -> 已停（连不上）"
    }
}
```

**预期输出**：5 个端口全部变成"连不上 / 000 / 已停"。

> 🔴 **`taskkill //PID` 里的双斜杠不是笔误**。Git Bash 会把 `/PID` 这种单斜杠参数当成路径去转换（MSYS 路径转换），写成 `//PID` 才能原样传给 Windows。这是阶段 7 就踩过的坑。
> 🟡 如果你有别的重要程序也在用这些端口（比如你手动开着的调试服务），`Stop-Process -Force` 会一并杀掉。确认 `Get-NetTCPConnection` 拿到的 PID 确实是你的 python 再执行。

### 13.2 用压测参数重启 5 个服务

**这一节有 5 条命令，一条都不能少。**

先建一个放日志的目录（日志很重要——服务起不来时全靠它排查）：

**Git Bash / PowerShell 通用：**

```bash
mkdir -p logs
```

```powershell
New-Item -ItemType Directory -Force -Path logs | Out-Null
```

**Git Bash —— 5 条启动命令**（一条一条复制执行）：

```bash
cd /f/pycharm_aiprogram/ai_chief

# ① 单体（9002）—— SPLIT_MODE 不设 = 默认 local = 所有节点在自己进程内跑，这就是"拆分前"
MOCK_LLM=true RATE_LIMIT_PER_MINUTE=1000000 RATE_LIMIT_USER_PER_MINUTE=1000000 \
  nohup ./.venv3/Scripts/python.exe -m uvicorn main:app --port 9002 > logs/bench_9002.log 2>&1 &

# ② user 服务（9121）
MOCK_LLM=true RATE_LIMIT_PER_MINUTE=1000000 RATE_LIMIT_USER_PER_MINUTE=1000000 \
  nohup ./.venv3/Scripts/python.exe -m uvicorn services.user.main:app --port 9121 > logs/bench_9121.log 2>&1 &

# ③ recognizer 服务（9122）
MOCK_LLM=true RATE_LIMIT_PER_MINUTE=1000000 RATE_LIMIT_USER_PER_MINUTE=1000000 \
  nohup ./.venv3/Scripts/python.exe -m uvicorn services.recognizer.main:app --port 9122 > logs/bench_9122.log 2>&1 &

# ④ recommender 服务（9123）
MOCK_LLM=true RATE_LIMIT_PER_MINUTE=1000000 RATE_LIMIT_USER_PER_MINUTE=1000000 \
  nohup ./.venv3/Scripts/python.exe -m uvicorn services.recommender.main:app --port 9123 > logs/bench_9123.log 2>&1 &

# ⑤ chat 服务（9124）—— 🔴 必须带 SPLIT_MODE=remote，否则它自己跑完全部节点，等于没拆
MOCK_LLM=true SPLIT_MODE=remote RATE_LIMIT_PER_MINUTE=1000000 RATE_LIMIT_USER_PER_MINUTE=1000000 \
  nohup ./.venv3/Scripts/python.exe -m uvicorn services.chat.main:app --port 9124 > logs/bench_9124.log 2>&1 &
```

**PowerShell 5.1 —— 5 条启动命令**（PowerShell 没有 `nohup`，用 `Start-Process`）：

```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
$py = "F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe"

# ① 单体（9002）
$env:MOCK_LLM = "true"
$env:RATE_LIMIT_PER_MINUTE = "1000000"
$env:RATE_LIMIT_USER_PER_MINUTE = "1000000"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--port","9002" `
    -NoNewWindow -RedirectStandardOutput "logs\bench_9002.log" -RedirectStandardError "logs\bench_9002.err.log"

# ② user 服务（9121）
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.user.main:app","--port","9121" `
    -NoNewWindow -RedirectStandardOutput "logs\bench_9121.log" -RedirectStandardError "logs\bench_9121.err.log"

# ③ recognizer 服务（9122）
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.recognizer.main:app","--port","9122" `
    -NoNewWindow -RedirectStandardOutput "logs\bench_9122.log" -RedirectStandardError "logs\bench_9122.err.log"

# ④ recommender 服务（9123）
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.recommender.main:app","--port","9123" `
    -NoNewWindow -RedirectStandardOutput "logs\bench_9123.log" -RedirectStandardError "logs\bench_9123.err.log"

# ⑤ chat 服务（9124）—— 必须带 SPLIT_MODE=remote
$env:SPLIT_MODE = "remote"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.chat.main:app","--port","9124" `
    -NoNewWindow -RedirectStandardOutput "logs\bench_9124.log" -RedirectStandardError "logs\bench_9124.err.log"
```

> 🔴 **PowerShell 版的坑**：`$env:SPLIT_MODE = "remote"` 设置之后，**当前窗口里后续启动的所有进程都会带上它**。所以必须把它放在最后一条（chat 之后没有别的要起了）。如果你想再起单体，先 `Remove-Item Env:SPLIT_MODE`。
>
> 🔴 **`SPLIT_MODE=remote` 这个开关不在 `config.py` 里**，它是 `app_my/agents/coordinator.py` 用 `os.getenv("SPLIT_MODE", "local")` 直接读的环境变量。设了之后 chat 服务才会通过 HTTP 去调 9121/9122/9123——这才是"拆开"的状态。不设的话它自己内部跑完，压出来的就不是微服务的数据。

**等待 20 秒让服务起来，然后验证**：

**Git Bash：**

```bash
sleep 20
for p in 9002 9121 9122 9123 9124; do
  echo -n "$p -> "; curl -s -m 3 "http://127.0.0.1:$p/health" | head -c 120; echo
done
```

**PowerShell 5.1：**

```powershell
Start-Sleep -Seconds 20
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$p/health" -TimeoutSec 3
        Write-Host "$p -> $($r.status) / $($r.service)"
    } catch { Write-Host "$p -> 失败: $($_.Exception.Message)" }
}
```

**预期输出**（本次实测原文）：

```
9002 -> ok / AI私厨企业版
9121 -> ok / user
9122 -> ok / recognizer
9123 -> ok / recommender
9124 -> ok / chat
```

> 🔴 **如果某个端口起不来**，看对应的日志：`cat logs/bench_9124.log`（Git Bash）或 `Get-Content logs\bench_9124.log -Tail 30`（PowerShell）。最常见的两类错误：
> - `pydantic_core._pydantic_core.ValidationError: JWT_SECRET 仍为默认值` → `.env` 没读到，确认你在项目根目录执行的；
> - `Address already in use` → 13.1 没杀干净，回到 13.1 重来。

**确认 mock 真的生效了**（这一条最关键）：

**Git Bash：**

```bash
curl -s -m 5 "http://127.0.0.1:9124/health" | head -c 200; echo
grep -c "MOCK_LLM" logs/bench_9124.log
```

**PowerShell 5.1：**

```powershell
(Select-String -Path logs\bench_9124.log -Pattern "MOCK_LLM" -AllMatches).Matches.Count
```

预期：`grep -c` 输出 `0` 也算正常（启动日志里不会主动打 MOCK_LLM）。**真正可靠的检查是 14.2 压测跑完后看有没有真调用**。这里只要 5 个端口都 `ok` 就继续。

### 13.3 清掉当天租户配额

free 套餐的 `chat_daily` 上限是 50 次。压测几十秒就打满，之后所有对话请求返回 429，报告里变成"一堆 429"。

**Git Bash：**

```bash
docker exec ai_chief_redis redis-cli --scan --pattern "quota:*" | while read -r k; do
  [ -n "$k" ] && docker exec ai_chief_redis redis-cli DEL "$k" > /dev/null
done
docker exec ai_chief_redis redis-cli --scan --pattern "quota:*" | wc -l
```

**PowerShell 5.1：**

```powershell
$keys = & docker exec ai_chief_redis redis-cli --scan --pattern 'quota:*' 2>$null
foreach ($k in $keys) { if ($k) { & docker exec ai_chief_redis redis-cli DEL $k | Out-Null } }
$after = & docker exec ai_chief_redis redis-cli --scan --pattern 'quota:*' 2>$null
"剩余配额键: " + ($after | Where-Object { $_ }).Count
```

**预期输出**：

```
剩余配额键: 0
```

> 🟡 `run_bench.sh` 里**已经内置了这一步**（每轮压测前自动清）。这里单独做一次，是为了让你在手动单轮测试时也不会被配额坑。

### 13.4 调高 Kong 网关限流并重启网关

Kong 的 chat 路由默认 120 次/分钟 = 2 QPS，压测一秒就超。

**第一步：改配置。** 用编辑器打开 `docker/kong/kong.yml`，把这 4 个数字改掉（行号见下面）：

| 行号 | 原值 | 改成 | 属于 |
|---|---|---|---|
| 52 | `minute: 600` | `minute: 60000` | svc-user |
| 66 | `minute: 300` | `minute: 30000` | svc-recognizer |
| 83 | `minute: 300` | `minute: 30000` | svc-recommender |
| 108 | `minute: 120` | `minute: 12000` | svc-chat |

**Git Bash（用 sed 一键改，省得手动找）：**

```bash
sed -i '52s/minute: 600/minute: 60000/; 66s/minute: 300/minute: 30000/; 83s/minute: 300/minute: 30000/; 108s/minute: 120/minute: 12000/' docker/kong/kong.yml
grep -n "minute:" docker/kong/kong.yml
```

**PowerShell 5.1：**

```powershell
$f = "docker\kong\kong.yml"
$lines = Get-Content $f
$map = @{ 51 = '60000'; 65 = '30000'; 82 = '30000'; 107 = '12000' }   # 注意：数组下标 = 行号 - 1
foreach ($i in $map.Keys) {
    $lines[$i] = $lines[$i] -replace 'minute: \d+', "minute: $($map[$i])"
}
Set-Content -Path $f -Value $lines -Encoding UTF8
Select-String -Path $f -Pattern "minute:" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
```

**预期输出（两版一致）**：

```
52:          minute: 60000
66:          minute: 30000
83:          minute: 30000
108:          minute: 12000
```

**第二步：让 Kong 重新加载配置。** Kong 是 DB-less 模式，Admin API 是只读的，**改完文件必须重启容器**才生效。

**Git Bash：**

```bash
docker restart ai_chief_kong
sleep 12
curl -s -o /dev/null -w "Kong 状态=%{http_code}\n" -m 5 http://127.0.0.1:9105/status
```

**PowerShell 5.1：**

```powershell
docker restart ai_chief_kong
Start-Sleep -Seconds 12
try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:9105/status" -TimeoutSec 5 -UseBasicParsing; "Kong 状态=" + $r.StatusCode }
catch { "Kong 状态=失败: " + $_.Exception.Message }
```

**预期输出**：

```
Kong 状态=200
```

> 🔴 **`docker restart` 后要等 10~15 秒**。Kong 冷启动要解析整个 kong.yml，没等够就压测会拿到 503。
> 🔴 端口 **9105** 是阶段 9 里 Kong 管理口的映射（避开已被 worker metrics 占用的 9101）。如果你项目里映射的是别的端口，用 `docker ps --format "{{.Names}}\t{{.Ports}}" | grep kong` 查一下。

**验证限流确实放宽了**（连打 20 次登录看有没有 429）：

> 🔴 **勘误**：之前写的 `GET /api/v1/health` 是虚构路径——Kong 里没有这条路由，请求根本到不了任何服务、也过不了限流插件，永远只会 404，**这个检查等于没测**。必须打真实路由（`/auth/login`）才能经过限流插件。

**Git Bash：**

```bash
for i in $(seq 1 20); do curl -s -o /dev/null -w "%{http_code} " -m 3 -X POST http://127.0.0.1:9100/auth/login -H "Content-Type: application/json" -d '{"username":"nobody","password":"wrong"}'; done; echo
```

**PowerShell 5.1：**

```powershell
1..20 | ForEach-Object {
    try { (Invoke-WebRequest -Uri "http://127.0.0.1:9100/auth/login" -Method POST -ContentType "application/json" -Body '{"username":"nobody","password":"wrong"}' -TimeoutSec 3 -UseBasicParsing).StatusCode } catch { $_.Exception.Response.StatusCode.value__ }
}
```

**预期输出**（本次实测原文，限流值恢复 600/min 后）：20 个 `401`（凭据错误被拒，**没有 429**）：

```
401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401 401
```

> 判据：**看不到 429** 就算限流已放宽。如果混着 429，说明第 13.3 步改限流没生效（Kong 是 DB-less，改 kong.yml 必须 `docker restart` 才加载）。

### 13.5 最后总检查

**Git Bash：**

```bash
for p in 9002 9121 9122 9123 9124; do
  echo -n "$p -> "; curl -s -o /dev/null -w "%{http_code}\n" -m 3 "http://127.0.0.1:$p/health"
done
docker ps --format "{{.Names}}" | grep -E "kong|redis|neo4j|milvus|pgvector"
```

**PowerShell 5.1：**

```powershell
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    try { "$p -> " + (Invoke-WebRequest -Uri "http://127.0.0.1:$p/health" -TimeoutSec 3 -UseBasicParsing).StatusCode }
    catch { "$p -> 失败" }
}
docker ps --format "{{.Names}}" | Select-String -Pattern "kong|redis|neo4j|milvus|pgvector"
```

**预期输出**：

```
9002 -> 200
9121 -> 200
9122 -> 200
9123 -> 200
9124 -> 200
ai_chief_kong
ai_chief_redis
ai_chief_neo4j
ai_chief_milvus
ai_chief_pgvector
```

**五个 200 + 五个容器都在，才能进第十四节。**

---

## 十四、跑压测：正式执行

### 14.1 先跑一轮小的试试水（强烈建议）

别一上来就跑 8 轮。**先跑 1 轮 15 秒的，确认数据出来了再跑全套**。整套跑完要 12 分钟左右，中途发现参数错了很浪费。

**Git Bash：**

```bash
bash scripts/run_bench.sh monolith 5 15
```

**PowerShell 5.1：**

```powershell
.\scripts\run_bench.ps1 -Target monolith -UsersList "5" -Duration 15
```

**预期输出**（本次实测原文，你的数字会略有不同）：

```
================================================================================
BENCH SUMMARY  target=:9002  peak_users=5  total=54  failures=0
--------------------------------------------------------------------------------
场景                    请求数     失败      失败率      平均ms    P50ms    P95ms    P99ms     RPS
--------------------------------------------------------------------------------
/auth/login            15      0     0.0%       194      190      200      200     1.3
/chat/stream            7      0     0.0%       137      130      170      170     0.6
/kg/ask                22      0     0.0%        10       11       14       15     1.7
--------------------------------------------------------------------------------
TOTAL                  54      0     0.0%       118      140      270      290     3.7
================================================================================
```

> 🔴 **三个必须满足的判据**：
> 1. `failures=0` —— 有失败就说明前置条件没满足（回去看第十三节）；
> 2. 三个场景**都有数字** —— 哪个是 0 说明该场景报错了，看上面的错误输出；
> 3. `RPS` 不是 0.0 —— 是 0 说明压测压根没打进去。
>
> **数量级参考**（本次实测）：登录 ≈ 190ms（慢，因为 bcrypt 哈希很吃 CPU）、对话 ≈ 140ms、图谱 ≈ 10ms。
> 数字本身每次都会变，**只要量级对得上就行**。如果你这里登录只有 5ms，反而要警惕——说明 bcrypt 没真的在算（检查 `.env` 里的 `BCRYPT_ROUNDS`）。


### 14.2 确认没有真的调用大模型（压测数据可信的前提）

试水跑完之后，查一下服务日志里有没有出现 DashScope 的字样。

**Git Bash：**

```bash
grep -ci "dashscope\|MOCK_LLM 命中" logs/bench_9124.log
grep -ci "dashscope" logs/bench_9002.log
```

**PowerShell 5.1：**

```powershell
"9124 含 dashscope/MOCK: " + (Select-String -Path logs\bench_9124.log -Pattern "dashscope|MOCK_LLM 命中" -AllMatches).Matches.Count
"9002 含 dashscope: " + (Select-String -Path logs\bench_9002.log -Pattern "dashscope" -AllMatches).Matches.Count
```

**预期输出**：

- 第一个数字 **> 0** —— 说明走的是 mock 分支（`MOCK_LLM 命中` 是我们在 model_router.py 里加的日志）
- 第二个数字 **= 0** —— 说明没有真的去调 DashScope

> 🟡 实际上 `MOCK_LLM 命中` 这条日志每次请求都会打，所以第一个数字会很大（几百上千），这是正常的。

### 14.3 跑完整 8 轮（找拐点）

试水通过后，跑全套：**2 个目标 × 4 个并发档（10/20/40/60）× 每档 45 秒**。

**Git Bash（推荐，这个我完整实跑过）：**

```bash
bash scripts/run_bench.sh all "10,20,40,60" 45
```

**PowerShell 5.1：**

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\run_bench.ps1 -Target all -UsersList "10,20,40,60" -Duration 45
```

**耗时**：约 12 分钟（8 轮 × 45 秒 + 爬坡 + 间隔）。

**预期看到的**：8 组分隔线，每组一个 `BENCH SUMMARY` 表，最后一行提示输出目录：

```
==============================================================
 压测结束，结果 CSV 在: reports/bench_20261020_153000
 下一步：用报告脚本把它汇总成一张对比表
   ./.venv3/Scripts/python.exe scripts/locust_report.py --dir "reports/bench_20261020_153000"
==============================================================
```

> 🟡 **把那个目录名记下来**（比如 `reports/bench_20261020_153000`），下一步要用。

**确认 8 个 CSV 都生成了**：

**Git Bash：**

```bash
ls reports/bench_*_u*_stats.csv 2>/dev/null | wc -l
ls -1 reports/$(ls -1t reports | head -1)/ | head -20
```

**PowerShell 5.1：**

```powershell
(Get-ChildItem -Path reports -Recurse -Filter "*_stats.csv").Count
$latest = Get-ChildItem reports -Directory | Sort-Object Name -Descending | Select-Object -First 1
"最新目录: " + $latest.Name
Get-ChildItem $latest.FullName | Select-Object -ExpandProperty Name
```

**预期**：`*_stats.csv` 共 **8 个**（monolith_u10/u20/u40/u60 + gateway_u10/u20/u40/u60）。

### 14.4 生成报告

把上一步记下的目录名填进去。

**Git Bash：**

```bash
./.venv3/Scripts/python.exe scripts/locust_report.py --dir reports/bench_20261020_153000 --out reports/bench_20261020_153000/压测报告.md
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe scripts\locust_report.py --dir reports\bench_20261020_153000 --out reports\bench_20261020_153000\压测报告.md
```

**预期输出**：

```
[完成] 报告已写入 reports\bench_20261020_153000\压测报告.md
       共解析 8 轮压测、12 行对比、8 行拐点数据
```

> 两个数字的含义：`8 轮` = 2 目标 × 4 档；`12 行对比` = 4 档 × 3 场景；`8 行拐点` = 8 轮各一行。

**确认报告没挤成一行**（这是个真实的坑，脚本里专门处理过）：

**Git Bash：**

```bash
head -20 reports/bench_20261020_153000/压测报告.md
```

**PowerShell 5.1：**

```powershell
Get-Content reports\bench_20261020_153000\压测报告.md -TotalCount 20
```

**预期输出**：开头几行 + 一张**分行显示**的表（每行一条 `| ... |`）。如果你看到一整行超长的内容，说明表格没分行——回头检查 `render_markdown` 里有没有行尾带了 `\n`。

**本节检查点**：8 个 CSV、`压测报告.md` 三张表齐全、表格分行正常、失败率为 0。

---

## 十五、生产部署实测

三件事：构建镜像 → 校验编排 → 起容器。

### 15.1 构建生产镜像

🔴 **这一步很慢（本次实测 12 分 49 秒）**，因为要 `pip install` 整个项目的依赖。放后台跑，别干等。

**Git Bash / PowerShell 通用：**

```bash
docker build -f docker/Dockerfile.svc -t ai-chief-svc:prod .
```

**预期输出**（本次实测的**最后 10 行**，前面还有几十行 `pip install` 的滚动日志）：

```
#10 [6/9] COPY app_my ./app_my
#10 DONE 1.8s

#11 [7/9] COPY services ./services
#11 DONE 1.7s

#12 [8/9] COPY main.py ./main.py
#12 DONE 1.6s

#13 [9/9] RUN useradd --create-home --uid 1000 appuser     && chown -R appuser:appuser /app
#13 DONE 10.8s

#14 exporting to image
#14 exporting layers
#14 exporting layers 4.4s done
#14 writing image sha256:908938e08c14a69f96e8391ccdd464ecd6544154c636b799755810edb5814f0f 0.1s done
#14 naming to docker.io/library/ai-chief-svc:prod 0.1s done
#14 DONE 5.0s

 1 warning found (use docker --debug to expand):
 - JSONArgsRecommended: JSON arguments recommended for CMD to prevent unintended behavior related to OS signals (line 93)
```

> 🟡 **最后那个 warning 是正常的，不用管它**。它建议把 `CMD` 写成 JSON 数组形式，但我们**故意**用 shell 形式——因为要展开 `${APP_MODULE}` 这些环境变量，JSON 形式不做变量替换。代价是 gunicorn 收到的信号会经过一层 shell，对本项目无影响。

**验证镜像存在**：

```bash
docker images ai-chief-svc
```

**预期输出**：

```
REPOSITORY       TAG       IMAGE ID       CREATED          SIZE
ai-chief-svc     prod      908938e08c14   2 minutes ago    520MB
```

> `IMAGE ID` 会不同，`SIZE` 约 520MB。🔴 如果你看不到这一行，说明构建失败了——往上翻找 `[9/9]` 之前的红色报错。

### 15.2 校验生产编排

**Git Bash：**

```bash
docker compose -f docker/docker-compose.prod.yml config > /dev/null; echo "退出码=$?"
docker compose -f docker/docker-compose.prod.yml config --services
```

**PowerShell 5.1：**

```powershell
docker compose -f docker/docker-compose.prod.yml config | Out-Null
"退出码=$LASTEXITCODE"
docker compose -f docker/docker-compose.prod.yml config --services
```

**预期输出**（本次实测原文）：

```
退出码=0
svc-recommender
svc-user
svc-recognizer
svc-chat
kong
```

### 15.3 起生产容器（谨慎：会抢端口）

🔴 **必读的前置条件**：生产编排会把容器绑到 **9121 / 9122 / 9123 / 9124 / 9100** 这 5 个端口。而你刚刚（第十三节）**在这 5 个端口上起了 uvicorn 进程**，并且 `ai_chief_kong` 容器也占着 9100。

**两边直接抢端口，`up -d` 一定失败**（报 `address already in use`）。

所以顺序是：**先停掉第十三节起的那 5 个进程 + Kong 容器，再 up 生产容器**。

> 🟡 **本次我没有实跑 `up -d`** —— 因为它会顶掉你正在跑的压测环境，而压测数据是这一阶段的产出物。下面给的是完整命令和判定方法；**建议你在第十七节"恢复现场"之后再做这一步**，那时端口是干净的。

**第 1 步：停掉占端口的东西**：

**Git Bash：**

```bash
for p in 9002 9121 9122 9123 9124; do
  pid=$(netstat -ano | grep ":$p " | grep LISTENING | awk '{print $5}' | head -1)
  if [ -n "$pid" ]; then taskkill //PID "$pid" //F > /dev/null 2>&1; fi
done
docker stop ai_chief_kong
sleep 3
```

**PowerShell 5.1：**

```powershell
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Stop-Process -Id $conn[0].OwningProcess -Force -ErrorAction SilentlyContinue }
}
docker stop ai_chief_kong
Start-Sleep -Seconds 3
```

**第 2 步：起生产容器**：

```bash
docker compose -f docker/docker-compose.prod.yml up -d
```

**第 3 步：等健康检查通过（约 60 秒），看状态**：

**Git Bash：**

```bash
sleep 60
docker compose -f docker/docker-compose.prod.yml ps
```

**PowerShell 5.1：**

```powershell
Start-Sleep -Seconds 60
docker compose -f docker/docker-compose.prod.yml ps
```

**预期输出**：5 行，每行 `STATUS` 出现 `(healthy)`（刚起来时可能是 `(health: starting)`，再等 30 秒）：

```
NAME                          SERVICE             STATUS              PORTS
ai_chief_prod_chat            svc-chat            Up (healthy)        0.0.0.0:9124->9124/tcp
ai_chief_prod_kong            kong                Up (healthy)        0.0.0.0:9100->9100/tcp, 0.0.0.0:9105->8001/tcp
ai_chief_prod_recognizer      svc-recognizer      Up (healthy)        0.0.0.0:9122->9122/tcp
ai_chief_prod_recommender     svc-recommender     Up (healthy)        0.0.0.0:9123->9123/tcp
ai_chief_prod_user            svc-user            Up (healthy)        0.0.0.0:9121->9121/tcp
```

> 🔴 **容器"起来了" ≠ "能用"——这次就是栽在这里，务必看完**
>
> 本次实测的翻车现场：5 个容器在 `docker ps` 里**全都显示为 `Up`**，但 `recognizer` 和 `user` 的 STATUS 是 **`Restarting (3)`**，9100 / 9123 / 9124 三个端口全是 `000`。
>
> 病根：`prometheus_client` 是**运行时依赖**（`app_my/middleware/metrics.py` 第 13 行直接 `from prometheus_client import ...`），但它**没有写进 `requirements.txt`**——只在你的开发虚拟环境 `.venv3` 里装过（阶段 7 装的）。于是：
>
> - `docker build` → **成功** ✅（pip 装依赖时并不知道运行时会 import 它）
> - 容器启动 → `ModuleNotFoundError` → gunicorn worker 崩溃 → 拉起 → 再崩 → **无限重启**
>
> **三步定位法**（以后容器起不来都按这个查，通用）：
>
> **第 1 步：看 STATUS 有没有 `Restarting`**
>
> ```bash
> docker ps --filter "name=ai_chief_prod" --format "{{.Names}}\t{{.Status}}"
> ```
>
> 只要看到 `Restarting (N)`，就是进程启动失败了，**再等也不会好**。
>
> **第 2 步：看日志末尾的真实报错**
>
> ```bash
> docker logs --tail 30 ai_chief_prod_user
> ```
>
> 本次实跑的末尾两行（原文）：
>
> ```
> ModuleNotFoundError: No module named 'prometheus_client'
> [2026-10-21 09:57:10 +0000] [7] [ERROR] Reason: Worker failed to boot.
> ```
>
> 🟡 `Worker failed to boot.` 是 gunicorn 的**通用说法**（任何 worker 起不来都这么写），真正的病根在**它上面那一行**。别照着这句去搜，要往上看一行。
>
> **第 3 步：补依赖 + 重新构建**
>
> ```bash
> docker build -f docker/Dockerfile.svc -t ai-chief-svc:prod .
> docker compose -f docker/docker-compose.prod.yml up -d
> ```
>
> 🔴 **改了 `requirements.prod.txt` 之后必须重新 build**。光 `up -d` 重启容器没用——依赖是**固化在镜像里**的，旧镜像里的包不会自己长出来。

**第 4 步：验证非 root 运行**（这是 Dockerfile 里专门做的）：

```bash
docker exec ai_chief_prod_user id
```

**预期输出**：

```
uid=1000(appuser) gid=1000(appuser) groups=1000(appuser)
```

> 🔴 必须是 `uid=1000(appuser)`。如果是 `uid=0(root)`，说明 `USER appuser` 那行没生效。

**第 5 步：验证走网关能通**：

**Git Bash：**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -m 5 http://127.0.0.1:9100/auth/login -X POST -H "Content-Type: application/json" -d '{"username":"nobody","password":"wrong"}'
```

**PowerShell 5.1：**

```powershell
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:9100/auth/login" -Method POST `
       -ContentType "application/json" -Body '{"username":"nobody","password":"wrong"}' -TimeoutSec 5 -UseBasicParsing
  "HTTP " + $r.StatusCode
} catch { "HTTP " + $_.Exception.Response.StatusCode.value__ }
```

**预期输出**：`401`（用户名密码错误）。**关键是能收到 HTTP 响应**，说明"网关 → svc-user"这条链路通了。如果是 `000` 或 `503`：

```bash
docker logs ai_chief_prod_user --tail 30
```

**第 6 步：收工，把生产容器停掉**（避免和后面的步骤抢端口）：

```bash
docker compose -f docker/docker-compose.prod.yml down
```

**本节检查点**：镜像存在（约 520MB）、`config` 退出码 0、5 个容器 healthy、`id` 显示 appuser、网关能返回 401。

---

## 十六、CI 本地验证与提交

### 16.1 跑 CI 本地等价验证

**Git Bash（推荐，这个我完整实跑过）：**

```bash
bash scripts/ci_local.sh
```

**PowerShell 5.1：**

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\ci_local.ps1
```

**预期输出**（本次实测的结构，数字以你实际为准）：

```
==============================================================
 阶段 10 · CI 本地等价验证  2026-10-20 15:20:33
 对应 .gitee/workflows/pipeline.yml 的每个 step
==============================================================

--------------------------------------------------------------
 步骤: Python 版本（CI 用的是 3.13）
--------------------------------------------------------------
Python 3.13.14
[PASS] Python 版本（CI 用的是 3.13）

--------------------------------------------------------------
 步骤: 检查关键依赖是否已安装
--------------------------------------------------------------
关键依赖齐全: 8 个
[PASS] 检查关键依赖是否已安装

--------------------------------------------------------------
 步骤: 跑单元测试（tests/unit，不依赖外部服务）
--------------------------------------------------------------
141 passed, 3 warnings in 11.87s
[PASS] 跑单元测试（tests/unit，不依赖外部服务）

--------------------------------------------------------------
 步骤: 校验生产编排 docker-compose.prod.yml 可被解析
--------------------------------------------------------------
生产编排解析通过，共 5 个服务: ['svc-user', 'svc-recognizer', 'svc-recommender', 'svc-chat', 'kong']
[PASS] 校验生产编排 docker-compose.prod.yml 可被解析

--------------------------------------------------------------
 步骤: 校验压测脚本语法
--------------------------------------------------------------
[PASS] 校验压测脚本语法

--------------------------------------------------------------
 步骤: 冒烟：核心模块能被导入
--------------------------------------------------------------
核心模块 import OK（含阶段10新增的 mock_llm）
[PASS] 冒烟：核心模块能被导入

--------------------------------------------------------------
 镜像构建（CI 的最后一个 step）——默认跳过
 想在本机真跑一遍就执行：
   docker build -f docker/Dockerfile.svc -t ai-chief-svc:prod .
--------------------------------------------------------------

==============================================================
 全部通过 ✅ —— 流水线的命令在本机都跑得通，可以 push 了
==============================================================
```

> 🔴 **必须是 `全部通过` 且一条 `[FAIL]` 都没有**。有 FAIL 就按标题定位：
> - `检查关键依赖` FAIL → 看它打印的"缺失依赖"列表，用 `./.venv3/Scripts/python.exe -m pip install <包名>` 补上；
> - `跑单元测试` FAIL → 回到 7.5；
> - `校验生产编排` FAIL → 回到 10.3；
> - `冒烟` FAIL → `mock_llm.py` 没建好，回到 7.1。

### 16.2 跑阶段验收脚本

把第十四节的压测目录填进去。

**Git Bash：**

```bash
./.venv3/Scripts/python.exe scripts/verify_stage10.py --bench-dir reports/bench_20261020_153000
```

**PowerShell 5.1：**

```powershell
.\.venv3\Scripts\python.exe scripts\verify_stage10.py --bench-dir reports\bench_20261020_153000
```

**预期输出**：

```
==============================================================================
 AI 私厨 v3.0 · 阶段 10 验收
==============================================================================

[1] 交付文件
  OK   app_my/core/mock_llm.py                      对话模型打桩器
  OK   app_my/knowledge/embedding.py                向量打桩（含 MOCK_DIMENSION）
  OK   app_my/core/config.py                       MOCK_LLM 配置开关
  OK   app_my/core/model_router.py                 统一入口的打桩早返回分支
  OK   benchmarks/locustfile.py                    压测脚本（三场景）
  OK   scripts/run_bench.sh                        压测编排（Git Bash）
  OK   scripts/locust_report.py                    压测结果汇总器
  OK   docker/Dockerfile.svc                       生产镜像定义
  OK   docker/requirements.prod.txt                生产依赖（含 gunicorn）
  OK   docker/docker-compose.prod.yml              生产编排（4 服务 + 网关）
  OK   .gitee/workflows/pipeline.yml               Gitee Go 流水线
  OK   tests/unit/test_stage10_mock_llm.py         打桩单元测试
  OK   tests/unit/test_stage10_bench_report.py     汇总器单元测试

[2] LLM 打桩接线
  OK   config 里有 MOCK_LLM 配置                   当前值=False
  OK   MOCK_LLM 默认是关闭的                       压测才临时打开
  OK   ainvoke_routed 里有 MOCK_LLM 分支           打桩必须挂在唯一出口上
  OK   打桩分支不挂计费回调                         mock 没有真 token，不该记账
  OK   打桩向量维度与 Milvus 集合一致               打桩=1024 Milvus=1024
  OK   extract 打桩能被识别节点解析                 解析出 3 种食材

[3] 服务健康
  OK   端口 9002 健康                              单体 → ok
  OK   端口 9121 健康                              user → ok
  OK   端口 9122 健康                              recognizer → ok
  OK   端口 9123 健康                              recommender → ok
  OK   端口 9124 健康                              chat → ok

[4] 生产编排与 CI 配置
  OK   docker/docker-compose.prod.yml YAML 可解析
  OK   .gitee/workflows/pipeline.yml YAML 可解析
  OK   docker compose config 通过
  OK   compose 含 4 个服务 + 网关

[5] 压测产物
  OK   存在压测结果 CSV                            找到 8 个
  OK   单体与网关都跑了压测                        单体档位=['10','20','40','60'] 网关档位=['10','20','40','60']
  OK   压测报告已生成                              压测报告.md
  OK   报告表格分行正常
  OK   报告含拐点结论

==============================================================================
 验收通过：33 项全部 OK
==============================================================================
```

> 🔴 **最后一行必须是 `验收通过：33 项全部 OK`**。
> - 如果 `[3] 服务健康` 里有 FAIL —— 说明服务没起。按 13.2 把 5 个服务起回来再跑。
> - 如果 `[5] 压测产物` 整块跳过 —— 你忘了加 `--bench-dir` 参数。

### 16.3 提交

**Git Bash：**

```bash
git add -A
git status --short
git commit -m "feat(stage10): 性能压测 + CI/CD + 生产级部署"
```

**PowerShell 5.1：**

```powershell
git add -A
git status --short
git commit -m "feat(stage10): 性能压测 + CI/CD + 生产级部署"
```

**预期输出**：

```
[feat/v3-stage10 xxxxxxx] feat(stage10): 性能压测 + CI/CD + 生产级部署
 17 files changed, ...
```

（14 个新增 + 3 个修改 = 17。如果你的数字对不上，多半是 `reports/` 被计入了——压测 CSV 建议加进 `.gitignore`，别提交。）

> 🟡 **提交前确认一件事**：`git status --short` 里**不应该**出现 `docker/kong/kong.yml`。它应该在第十七节恢复原值了（若还显示 `M`，说明第十七节没做完）。

---

## 十七、恢复现场（压测后必做）

🔴 **这一节千万别跳过**。压测改了 3 处现场，不恢复的话你下次开发会遇到莫名其妙的问题（比如所有对话都返回同一段假菜谱）。

| # | 改了什么 | 不恢复的后果 | 恢复办法 |
|---|---|---|---|
| ① | Kong 限流调高到 60000 | 网关限流形同虚设 | 17.1 |
| ② | 服务带 `MOCK_LLM=true` 跑着 | 所有对话返回假数据，还查不出为什么 | 17.2 |
| ③ | 限流阈值调到 1000000 | 限流中间件等于关了 | 17.2 同一批命令 |

### 17.1 恢复 Kong 限流

**Git Bash：**

```bash
git checkout -- docker/kong/kong.yml
grep -n "minute:" docker/kong/kong.yml
docker restart ai_chief_kong
sleep 12
curl -s -o /dev/null -w "Kong 状态=%{http_code}\n" -m 5 http://127.0.0.1:9105/status
```

**PowerShell 5.1：**

```powershell
git checkout -- docker/kong/kong.yml
Select-String -Path docker\kong\kong.yml -Pattern "minute:" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
docker restart ai_chief_kong
Start-Sleep -Seconds 12
try { "Kong 状态=" + (Invoke-WebRequest -Uri "http://127.0.0.1:9105/status" -TimeoutSec 5 -UseBasicParsing).StatusCode }
catch { "Kong 状态=失败" }
```

**预期输出**：

```
52:          minute: 600
66:          minute: 300
83:          minute: 300
108:          minute: 120
Kong 状态=200
```

**顺手删掉备份**（留着容易和真文件混淆）：

**Git Bash：** `rm -f docker/kong/kong.yml.bak`
**PowerShell：** `Remove-Item docker\kong\kong.yml.bak -ErrorAction SilentlyContinue`

### 17.2 用正常参数重启 5 个服务

和 13.2 的命令**几乎一样，只是去掉 `MOCK_LLM=true` 和限流参数**。

**Git Bash：**

```bash
cd /f/pycharm_aiprogram/ai_chief
for p in 9002 9121 9122 9123 9124; do
  pid=$(netstat -ano | grep ":$p " | grep LISTENING | awk '{print $5}' | head -1)
  if [ -n "$pid" ]; then taskkill //PID "$pid" //F > /dev/null 2>&1; fi
done
sleep 2

nohup ./.venv3/Scripts/python.exe -m uvicorn main:app --port 9002 > logs/svc_9002.log 2>&1 &
nohup ./.venv3/Scripts/python.exe -m uvicorn services.user.main:app --port 9121 > logs/svc_9121.log 2>&1 &
nohup ./.venv3/Scripts/python.exe -m uvicorn services.recognizer.main:app --port 9122 > logs/svc_9122.log 2>&1 &
nohup ./.venv3/Scripts/python.exe -m uvicorn services.recommender.main:app --port 9123 > logs/svc_9123.log 2>&1 &
SPLIT_MODE=remote nohup ./.venv3/Scripts/python.exe -m uvicorn services.chat.main:app --port 9124 > logs/svc_9124.log 2>&1 &

sleep 20
for p in 9002 9121 9122 9123 9124; do
  echo -n "$p -> "; curl -s -m 3 "http://127.0.0.1:$p/health" | head -c 60; echo
done
```

**PowerShell 5.1：**

```powershell
Set-Location F:\pycharm_aiprogram\ai_chief
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Stop-Process -Id $conn[0].OwningProcess -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 2

# 🔴 先把压测用的环境变量清掉，否则新起的进程会继承
Remove-Item Env:MOCK_LLM -ErrorAction SilentlyContinue
Remove-Item Env:RATE_LIMIT_PER_MINUTE -ErrorAction SilentlyContinue
Remove-Item Env:RATE_LIMIT_USER_PER_MINUTE -ErrorAction SilentlyContinue

$py = "F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--port","9002" -NoNewWindow -RedirectStandardOutput "logs\svc_9002.log" -RedirectStandardError "logs\svc_9002.err.log"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.user.main:app","--port","9121" -NoNewWindow -RedirectStandardOutput "logs\svc_9121.log" -RedirectStandardError "logs\svc_9121.err.log"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.recognizer.main:app","--port","9122" -NoNewWindow -RedirectStandardOutput "logs\svc_9122.log" -RedirectStandardError "logs\svc_9122.err.log"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.recommender.main:app","--port","9123" -NoNewWindow -RedirectStandardOutput "logs\svc_9123.log" -RedirectStandardError "logs\svc_9123.err.log"
$env:SPLIT_MODE = "remote"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","services.chat.main:app","--port","9124" -NoNewWindow -RedirectStandardOutput "logs\svc_9124.log" -RedirectStandardError "logs\svc_9124.err.log"

Start-Sleep -Seconds 20
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    try { "$p -> " + (Invoke-RestMethod -Uri "http://127.0.0.1:$p/health" -TimeoutSec 3).status }
    catch { "$p -> 失败" }
}
```

**预期输出**：5 个端口全是 `ok`。

> 🔴 **PowerShell 版那三行 `Remove-Item Env:` 不能省**。13.2 里你设置过 `$env:MOCK_LLM="true"`，它一直留在当前窗口的环境里，不清掉的话这里新起的进程照样是 mock 模式。

### 17.3 确认恢复成功（关键一验）

发一条真请求，看返回是不是真的模型输出（而不是"【压测模式固定回复】"开头）。

> 🔴 **勘误（实测踩坑后修正，两处）**：
> ① **路径没有 `/api/v1` 前缀**。`main.py` 里挂载就是 `/auth`、`/chat`、`/kg`（Kong 网关转发时也不带前缀）。之前写的 `/api/v1/auth/register` 不在鉴权中间件的放行名单里（`PUBLIC_PREFIXES = ("/auth/",)`），会被 401 拦下，返回「未认证」——如果你之前拿旧 token 打过一次，还会看到「Token 已过期，请重新登录」，都是这一个原因。
> ② **中文 body 不能直接内联在 `curl -d` 里**。Windows 的 curl.exe 处理命令行参数时按本地编码（GBK）转码，UTF-8 中文会被转成乱码字节，服务端报 `{"detail":"There was an error parsing the body"}`。解法：先把 body 写进 UTF-8 临时文件，再用 `-d @文件` 发送（实测通过）。

**Git Bash：**

```bash
# ① 注册（重复执行会返回 409 "用户名已被注册"，不影响后面，忽略即可）
curl -s -m 20 -X POST http://127.0.0.1:9002/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"stage10check","password":"Check@12345"}' | head -c 200; echo

# ② 登录拿 token（预期 access_token 长度约 299）
TOKEN=$(curl -s -m 10 -X POST http://127.0.0.1:9002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"stage10check","password":"Check@12345"}' \
  | ./.venv3/Scripts/python.exe -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
echo "token长度: ${#TOKEN}"

# ③ 中文 body 写临时文件（UTF-8），用 @文件 发送
printf '{"message":"我手里有鸡蛋和西红柿，能做什么菜？","thread_id":"stage10check","user_id":null}' > _chat_body.tmp.json
curl -s -m 60 -X POST http://127.0.0.1:9002/chat/stream \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @_chat_body.tmp.json | head -c 200; echo
rm -f _chat_body.tmp.json
```

**预期输出**（本次实测原文）：

```
① {"id":667,"username":"stage10check11","email":null}     ← 首次注册；409 "用户名已被注册" 也算过
② token长度: 299
③ ## 食材清单
*   **鸡蛋**：新鲜度良好 (8/10)
*   **西红柿**：新鲜度良好 (8/10)
```

③ 返回**真实模型生成**的菜谱建议（有识别新鲜度、营养数字），就说明 `MOCK_LLM` 已恢复关闭。

**PowerShell 5.1：**

```powershell
# ① 注册（409 已被注册也忽略）
$null = Invoke-RestMethod -Uri "http://127.0.0.1:9002/auth/register" -Method POST -ContentType "application/json" -Body '{"username":"stage10check","password":"Check@12345"}' -ErrorAction SilentlyContinue
# ② 登录
$login = Invoke-RestMethod -Uri "http://127.0.0.1:9002/auth/login" -Method POST -ContentType "application/json" -Body '{"username":"stage10check","password":"Check@12345"}'
"token长度: $($login.access_token.Length)"
# ③ 中文 body 必须转成 UTF-8 字节数组再传：
#    PS 5.1 的 Invoke-RestMethod 直接传字符串时按 ISO-8859-1 编码发送，中文必乱码
$body = '{"message":"我手里有鸡蛋和西红柿，能做什么菜？","thread_id":"stage10check","user_id":null}'
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$r = Invoke-WebRequest -Uri "http://127.0.0.1:9002/chat/stream" -Method POST -Headers @{Authorization="Bearer $($login.access_token)"} -ContentType "application/json" -Body $bodyBytes -TimeoutSec 60 -UseBasicParsing
$r.Content.Substring(0, [Math]::Min(200, $r.Content.Length))
```

> 🟡 PowerShell 版我做过静态核对，但 **Invoke-RestMethod 这条链路没有在你机器上完整实跑过**（实测走的是 Git Bash + Python）。如果你跑 PS 版报 body 解析错误，用上面 Git Bash 版验证，结论一样。

> 🔴 **如果 ③ 的输出以「【压测模式固定回复】」开头**，说明 `MOCK_LLM` 还在生效 —— 回到 17.2 重做，重点检查 PowerShell 的 `Remove-Item Env:MOCK_LLM`。
> 🟡 如果 ② 的 token长度 是 0，看 ① 的返回：409（用户已存在）可忽略，其它报错按第十八节错误表排查。

**本节检查点**：Kong 限流回到 600/300/300/120、5 个服务正常跑、真实对话返回真实内容。

### 17.4 清理压测残留账号（🟢 初版遗漏，本次补上）

**为什么**：`locustfile.py` 的 `on_start` 给每个虚拟用户注册一个 `bench_<随机串>` 账号。你跑了 8 轮压测，这些账号全留在 `users` 表里——它们不会自己消失，下次压测还会再堆一批。

本次实测：数据库总共 **579 个用户，其中 549 个是 `bench_` 开头的压测账号**（真实用户只有 30 个）。

**① 先看看有多少（只查不删，安全）**：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -c "
import sqlalchemy as sa
e = sa.create_engine('postgresql+psycopg2://ai_sichu:ai_sichu@localhost:9432/ai_sichu')
with e.connect() as c:
    print('用户总数:', c.execute(sa.text('select count(*) from users')).scalar())
    print('bench_ 用户数:', c.execute(sa.text(\"select count(*) from users where username like 'bench_%'\")).scalar())
"
```

**PowerShell 5.1：**（多行 Python 用 here-string，**结尾的 `"@` 必须顶格**）

```powershell
& .\.venv3\Scripts\python.exe -c @"
import sqlalchemy as sa
e = sa.create_engine('postgresql+psycopg2://ai_sichu:ai_sichu@localhost:9432/ai_sichu')
with e.connect() as c:
    print('用户总数:', c.execute(sa.text('select count(*) from users')).scalar())
    print('bench_ 用户数:', c.execute(sa.text(""select count(*) from users where username like 'bench_%'""))).scalar())
"@
```

**预期输出**（本次实测原文）：

```
用户总数: 579
bench_ 用户数: 549
```

**② 删除压测账号**：

**Git Bash：**

```bash
./.venv3/Scripts/python.exe -c "
import sqlalchemy as sa
e = sa.create_engine('postgresql+psycopg2://ai_sichu:ai_sichu@localhost:9432/ai_sichu')
with e.begin() as c:
    r = c.execute(sa.text(\"DELETE FROM users WHERE username LIKE 'bench_%'\"))
    print('已删除行数:', r.rowcount)
    print('剩余用户总数:', c.execute(sa.text('select count(*) from users')).scalar())
    print('剩余 bench_ 用户:', c.execute(sa.text(\"select count(*) from users where username like 'bench_%'\"))).scalar())
"
```

**PowerShell 5.1：**

```powershell
& .\.venv3\Scripts\python.exe -c @"
import sqlalchemy as sa
e = sa.create_engine('postgresql+psycopg2://ai_sichu:ai_sichu@localhost:9432/ai_sichu')
with e.begin() as c:
    r = c.execute(sa.text(""DELETE FROM users WHERE username LIKE 'bench_%'"")))
    print('已删除行数:', r.rowcount)
    print('剩余用户总数:', c.execute(sa.text('select count(*) from users')).scalar())
    print('剩余 bench_ 用户:', c.execute(sa.text(""select count(*) from users where username like 'bench_%'""))).scalar())
"@
```

**预期输出**（本次实测原文）：

```
已删除行数: 549
剩余用户总数: 30
剩余 bench_ 用户: 0
```

> 🔴 **`DELETE` 前务必确认 `WHERE` 条件写的是 `LIKE 'bench_%'`**。少写了 WHERE 就是清空整张表——没有后悔药。
> 上面这条语句只删 `username` 以 `bench_` 开头的行，你自己的账号（比如 `stage10check`、`admin`）不受影响。
>
> 🟡 **删除前"剩余用户总数"应该是个小数字**（本项目是 30）。如果你看到剩余 500+，说明你的真实账号也被误判成压测账号了——立刻停止，检查 `WHERE` 条件。

**③ 顺手清掉压测报告目录里的空文件夹**：

前几次失败的压测尝试会留下空目录（本次实测有 3 个）。它们不影响运行，但看着乱：

**Git Bash：**

```bash
find reports -maxdepth 1 -type d -name "bench_*" -empty -print -delete
```

**PowerShell 5.1：**

```powershell
Get-ChildItem -Path reports -Directory -Filter "bench_*" | Where-Object { (Get-ChildItem $_.FullName).Count -eq 0 } | ForEach-Object { Write-Host "删除空目录: $($_.Name)"; Remove-Item $_.FullName }
```

**预期输出**（本次实测原文）：被删的空目录名，每行一个：

```
reports/bench_20261021_171152
reports/bench_20261021_171247
```

> 🟡 **本次实际只删掉 2 个**，不是 3 个。第 3 个 `bench_20261021_171316` 看着像失败尝试，但里面留着 4 个 `monolith_u5_*` 的 CSV（那是 14.1 试水轮跑出来的），**不算空目录所以被保留了**——这是对的，别手动删它。
> 你自己的目录名和时间戳会不同，**只要"被删的数量 ≤ 你看到的总数减 1"就正常**。

> 🟡 只有**空的**才会被删。装了 CSV 和报告的那个目录（`bench_20261021_171618`）会保留——那是你的压测成果，别删。

**本节检查点**：`bench_` 用户为 0、真实用户数正常、空报告目录已清。

---

## 十八、常见错误对照表

按"你看到的报错"查。这些**全都是我在实跑阶段 10 时真踩过的**，不是编的。

| # | 现象 / 报错 | 真正的原因 | 怎么修 |
|---|---|---|---|
| 1 | `ModuleNotFoundError: No module named 'app_my'` | 命令行不在项目根目录，或用了裸 `python` | 用 `./.venv3/Scripts/python.exe`，且 `cd` 到含 `app_my` 的那层 |
| 2 | `UnicodeDecodeError: 'gbk' codec can't decode` | 裸 `python` 命中了 Anaconda 3.6 | 同上，一律用 `./.venv3/Scripts/python.exe` |
| 3 | `MOCK_LLM=true` 设了但打桩没生效 | 服务是从**旧代码**起的（改完代码必须重启进程） | 按 13.1 杀进程 → 13.2 重启 |
| 4 | `AttributeError: module 'locust' has no attribute ...` / `events.user_started` | locust 2.32 里没有这些名字 | 用手册里给的版本，别自己加 `events.user_started` |
| 5 | 压测跑完但屏幕上**没有** `BENCH SUMMARY` | 事件监听器里抛异常被 locust 静默吞掉 | 脚本已包 `try/except`，会打印"生成失败"；按提示改 |
| 6 | 所有场景都是 0 请求 | `stats.get(name)` 少传了 method | 必须是 `stats.get(name, method)` |
| 7 | 压测失败率 10%+，全是 `/chat/stream` | 脚本里判了 `"data:"` SSE 帧头，但本项目 `/chat/stream` 是纯文本 | 改成只判断返回非空 |
| 8 | `vector dimension mismatch` / chat 全 500 | 打桩向量维度 ≠ Milvus 的 1024 | 确认 `MOCK_DIMENSION == DIMENSION`（7.4） |
| 9 | 同一查询每次检索结果都不一样 | 用了内置 `hash()`（PYTHONHASHSEED 随机化） | 改用 `hashlib.md5` 做种子 |
| 10 | 压测几十秒后开始大面积 429 | 配额满了（free 套餐 chat_daily=50） | 13.3 清配额键 |
| 11 | 压测一开始就 429 | 服务端限流 60/min、20/min | 13.2 把两个 `RATE_LIMIT_*` 调到 1000000 |
| 12 | 压网关时 429 | Kong rate-limiting 120/min | 13.4 调高 + `docker restart ai_chief_kong` |
| 13 | 改了 kong.yml 但不生效 | DB-less 模式必须**重启容器**才加载新配置 | `docker restart ai_chief_kong` 并等 12 秒 |
| 14 | `docker build` 卡在 `Head "https://docker.mirrors.ustc.edu.cn/v2/...": EOF` | 本机配的镜像源全挂了 | Dockerfile 的 `FROM` 已改成 DaoCloud 源；确认你抄的是这一行 |
| 15 | `docker build` 在 `apt-get update` 报 `502 Bad Gateway` | 容器内访问 deb.debian.org 不通 | 手册里的 Dockerfile **根本没有** apt-get（健康检查改用 Python urllib） |
| 16 | `COPY requirements.txt docker/... ./x` 报 `must be a directory` | 多源 COPY 的目标不是目录 | 分两行写，各拷各的 |
| 17 | `import gunicorn` → `ModuleNotFoundError: No module named 'fcntl'` | gunicorn 不支持 Windows | **正常现象**。它只在 Linux 容器里用，别在本机启动 |
| 18 | `docker compose up -d` 报 `address already in use` | 端口被宿主机的 uvicorn 进程或旧 Kong 容器占着 | 15.3 第 1 步先停 |
| 19 | 容器一直 `(unhealthy)` | 健康检查用的 curl 不存在 / start_period 太短 | 手册用 Python urllib；`start_period: 40s` 别改小 |
| 20 | `pydantic ValidationError: JWT_SECRET 仍为默认值` | 容器没读到 `.env` | 确认 compose 的 `env_file: - ../.env` 指向正确 |
| 21 | 报告表格挤成一行 | `render_markdown` 里有的行带 `\n` 有的不带 | 统一不带，最后 `"\n".join(out)` |
| 22 | PowerShell 报"禁止运行脚本" | 执行策略限制 | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| 23 | PowerShell 里 `&&` / `grep` / `head` 报错 | PowerShell 5.1 没有这些 | 见附录 C 的替换表 |
| 24 | `taskkill /PID xxx` 报路径错误 | Git Bash 做了 MSYS 路径转换 | 写成 `taskkill //PID` |
| 25 | 对话一直返回「【压测模式固定回复】」 | `MOCK_LLM` 环境变量残留在终端里 | PowerShell：`Remove-Item Env:MOCK_LLM` |
| 26 | `.ps1` 语法检查报 `意外的标记"}"` / `数组索引表达式丢失或无效` / `缺少右"}"`，但代码看着没问题 | 文件是**无 BOM 的 UTF-8**，PowerShell 5.1 按 GBK 解码把中文后面的 `"` 吞了 | 存成 **UTF-8 with BOM**（见 9.2 的勘误块，含自查命令和两种修法） |
| 27 | `pytest` 报 `No module named 'scripts.locust_report'`（7.5 处） | 手册顺序：`locust_report.py` 到第九节才创建 | 7.5 的命令带 `--ignore=tests/unit/test_stage10_bench_report.py`，预期 **132 passed**（已勘误） |
| 28 | 生产容器 STATUS 显示 `Restarting (3)`，端口全是 `000`，日志末尾 `Reason: Worker failed to boot.` | 镜像里缺运行时依赖（`prometheus_client` 没写进 `requirements.txt`） | 往 `docker/requirements.prod.txt` 加 `prometheus-client==0.26.0`，见 15.3 的三步定位法 |
| 29 | `ci_local.sh / .ps1` 第 2 步 `[FAIL]`，报 `AttributeError: module 'importlib' has no attribute 'util'` | 脚本里写了 `import importlib` 却用了 `importlib.util` | 改成 `import importlib.util, sys`（两份脚本都已修正） |
| 30 | 往 `requirements.prod.txt` 加了包，重启容器还是报同一个 `ModuleNotFoundError` | 只 `up -d` 没有重新 build，依赖固化在旧镜像里 | 必须 `docker build -f docker/Dockerfile.svc -t ai-chief-svc:prod .` 再 `up -d` |
| 31 | `docker build` 了新镜像、容器却还跑旧代码/旧依赖 | compose 里服务**没写 `image:` 标签**，`up -d` 用的是 compose 自建的旧镜像（`ai_chief_prod-svc-*`） | x-svc-common 里加 `image: ai-chief-svc:prod`（见 10.3），再 `up -d`（会 Recreate） |
| 32 | 容器 `(healthy)` 但接口全 500，日志 `connection to server at "localhost", port 9432 failed: Connection refused` | `.env` 的 `localhost` 是宿主机视角，容器里 localhost 指容器自己 | 新建 `docker/env.prod-override` 覆盖连接串（见 10.4），`env_file` 列表里放 `.env` **后面** |
| 33 | Kong `Up (healthy)` 但 9100 请求全部超时；日志有 `worker process ... exited on signal 9` | Kong 默认每核一个 worker（13 核 = 13 个），512m 内存被 OOM 杀 | Kong 环境变量加 `KONG_NGINX_WORKER_PROCESSES: "2"` 后重建容器 |
| 34 | 修好 Neo4j 后 `/kg/ask` 仍返回旧的「图谱不可用」 | kg 问答有 **600 秒 Redis 缓存**，旧失败结果还在缓存里 | 换一个 ingredient 参数验证（绕过缓存键），或等 10 分钟缓存过期 |
| 35 | 17.3 验证报「未认证 / Token 已过期」 | 手册写了 `/api/v1/auth/...`，但真实路由**没有 `/api/v1` 前缀**，被鉴权中间件 401 拦截 | 改用 `/auth/register`、`/auth/login`、`/chat/stream`（已勘误） |
| 36 | 路径改对后 `/chat/stream` 报 `{"detail":"There was an error parsing the body"}` | Windows 的 `curl.exe` 处理命令行参数按本地编码（GBK）转码，**内联中文 body 必乱码**；PS 5.1 的 Invoke-RestMethod 传字符串按 ISO-8859-1 发 | Git Bash：中文 body 写临时文件用 `-d @文件`；PowerShell：`[System.Text.Encoding]::UTF8.GetBytes($body)` 再传（均已实测写进 17.3） |
| 37 | 13.4 限流验证永远看不到 429 | 原来打的是虚构路径 `/api/v1/health`，Kong 无此路由直接 404，**请求根本不经过限流插件** | 打真实路由 `POST /auth/login` 20 次（已勘误，实测 20 个 401） |

---

## 十九、避坑提示

### 19.1 顺序铁律（最容易翻车的地方）

阶段 7 的血泪教训在本阶段同样适用：**消费步骤永远排在产出步骤之后**。本阶段有三处：

1. **`requirements.prod.txt` → `Dockerfile.svc` → `docker-compose.prod.yml`**
   Dockerfile 要 `COPY requirements.prod.txt`，compose 要 `build.dockerfile: docker/Dockerfile.svc`。**反过来建，构建一定失败**。
2. **停进程 → 改配置 → 起进程**
   改完 `kong.yml` 必须 `docker restart`；改完 Python 代码必须**杀掉旧进程再起**（uvicorn 不带 `--reload` 时不会自己加载新代码）。
3. **压测 → 恢复 → 提生产容器**
   生产容器和压测进程抢同一批端口，必须先把压测的停掉。

### 19.2 关于"我说的数字和你跑出来的不一样"

本手册所有数字都是 2026-10-20 在你这台机器上实跑的原文。但你重跑时**不可能完全一致**，因为：

- 机器当时的负载不同（你开着多少浏览器标签、有没有别的容器在跑）；
- 数据库/图谱里的数据量在变（压测会注册几千个 `bench_xxx` 用户！）；
- 每轮的抽样不同。

**判据是"量级"和"趋势"，不是"逐位相等"**：

| 指标 | 本次实测 | 你的值应该 |
|---|---|---|
| 登录平均耗时 | 190ms | 100~300ms |
| 对话平均耗时 | 137ms | 80~250ms |
| 图谱平均耗时 | 10ms | 5~30ms |
| 单体拐点 | 60 并发 | 40~80 并发都算正常 |
| 网关最高档 | 未劣化 | 至少不该比单体更早劣化 |

> 🔴 **如果趋势反了**（比如网关比单体还慢很多、网关先劣化），那不是误差，是配置错了。回去查：
> ① 9124 是不是漏了 `SPLIT_MODE=remote`；② Kong 限流是不是没调高（网关在 429）；③ 有没有别的服务在抢 CPU。

### 19.3 压测数据会污染你的数据库

每轮压测会注册 `bench_<随机>` 用户（60 并发 × 45 秒 ≈ 60 个用户，8 轮 ≈ 480 个）。这些用户名带 `bench_` 前缀，不影响业务，但**会一直躺在你的 PostgreSQL 里**。

想清理的话（压测全部做完之后）：

**Git Bash：**

```bash
docker exec ai_chief_pgvector psql -U postgres -d ai_chief -c "DELETE FROM users WHERE username LIKE 'bench_%';"
```

**PowerShell 5.1：**

```powershell
docker exec ai_chief_pgvector psql -U postgres -d ai_chief -c "DELETE FROM users WHERE username LIKE 'bench_%';"
```

> 🟡 库名/用户名以你 `.env` 里的 `DATABASE_URL` 为准，不一定是 `ai_chief`。🔴 这条是 `DELETE`，**先确认前缀写对了再执行**。

### 19.4 关于 gunicorn 在 Windows 上"装了不能用"

再强调一次，因为这是本阶段最容易被误判为"出错了"的地方：

- 6.3 里我们装了 `gunicorn==23.0.0`；
- 但你在 Windows 上**永远无法启动它**（缺 `fcntl`）；
- 它唯一的用途是打进 Linux 容器镜像（15.1 已验证构建成功）。

**不要**因为"装了跑不起来"就去删它，也不要去搜"Windows 怎么装 fcntl"（无解）。

### 19.5 关于 Gitee Go 流水线

- 云端 YAML **没法在本机验证**。本阶段能证明的是"流水线里的每条命令在本机都能跑通"（`ci_local.sh`）。
- 真正的验证只有一次：`git push` 到 Gitee，看构建记录。
- 如果 `build-image` 那个 step 报"参数不存在"，按 11.1 文件末尾注释里说的，把三个参数缩进到 `inputs:` 下面。
- 如果你的仓库没开镜像构建能力，直接删掉那个 step——前两个 step 已经构成一条能绿的流水线。

### 19.6 关于两个 .ps1 脚本的验证强度

🟡 **如实说明**：`run_bench.ps1` 和 `ci_local.ps1` 我只做了**静态语法解析验证**，没有在你机器上完整跑过一轮（本次压测是用 `run_bench.sh` 在 Git Bash 跑完的）。

- 它们是照着已实跑的 `.sh` 逐行翻译的，参数、顺序、判定口径一致；
- PowerShell 5.1 的禁用语法（附录 C）都规避了；
- 但你第一次用它们跑压测时，**建议先用小档位试一次**（`-UsersList "5" -Duration 15`），确认输出正常再跑全套。

我不会假装"两边都实测过"——这条是刻意的。

---

## 二十、防呆自检清单

做完逐条打勾。**全勾了才算这个阶段收官**。

### 代码落盘（§7 ~ §12）

- [ ] `app_my/core/mock_llm.py` 新建，能 `import`（7.1）
- [ ] `app_my/core/config.py` 加了 `MOCK_LLM` / `BENCH_TARGET_NAME`，默认 `False`（7.2）
- [ ] `app_my/core/model_router.py` 有 4 处关键改动，打桩能秒回（7.3）
- [ ] `app_my/knowledge/embedding.py` 打桩维度 1024、模长 1.0、跨进程稳定（7.4）
- [ ] `pytest tests/unit --ignore=tests/unit/test_stage10_bench_report.py` = **132 passed**（7.5；九节落盘 `locust_report.py` 后，去掉 `--ignore` 重跑应为 **141 passed**）
- [ ] `benchmarks/locustfile.py` 建好，`locust --list` 能看到 `BenchUser`（8.1）
- [ ] `scripts/run_bench.sh` / `run_bench.ps1` / `locust_report.py` 语法 OK（9.1~9.3）
- [ ] `docker/requirements.prod.txt` / `Dockerfile.svc` / `docker-compose.prod.yml` 三个都在（10.1~10.3）
- [ ] `docker compose -f docker/docker-compose.prod.yml config` **退出码 0**（10.3）
- [ ] `.gitee/workflows/pipeline.yml` 能解析出 2 个 stage（11.1）
- [ ] `scripts/ci_local.sh` / `ci_local.ps1` 语法 OK（11.2~11.3）
- [ ] `scripts/verify_stage10.py` 语法 OK（12.1）

### 跑压测（§13 ~ §14）

- [ ] 5 个服务带 `MOCK_LLM=true` + 高限流重启，9124 带 `SPLIT_MODE=remote`（13.2）
- [ ] 当天配额已清（13.3）
- [ ] Kong 限流调到 60000/30000/30000/12000 并重启容器（13.4）
- [ ] 5 个端口全 200、5 个基础容器都在（13.5）
- [ ] 试水 1 轮 15 秒：`failures=0`、三场景都有数、RPS 非 0（14.1）
- [ ] 日志里没有真的调 DashScope（14.2）
- [ ] 完整 8 轮跑完，8 个 `*_stats.csv`（14.3）
- [ ] `压测报告.md` 生成，三张表齐全且分行正常（14.4）

### 生产部署与 CI（§15 ~ §16）

- [ ] `docker build` 成功，镜像约 520MB（15.1）
- [ ] `docker compose config` 退出码 0、5 个服务（15.2）
- [ ] 5 个容器 healthy、`id` 显示 `uid=1000(appuser)`（15.3）
- [ ] `bash scripts/ci_local.sh` **全部通过**，无 `[FAIL]`（16.1）
- [ ] `verify_stage10.py --bench-dir ...` → **验收通过：33 项全部 OK**（16.2）
- [ ] `git commit` 完成，且 `git status` 里没有 `docker/kong/kong.yml`（16.3）

### 恢复现场（§17）

- [ ] Kong 限流回到 **600 / 300 / 300 / 120**（17.1）
- [ ] 5 个服务用正常参数重启（17.2）
- [ ] 真实对话返回**真实模型内容**，不是「【压测模式固定回复】」（17.3）

---

## 附录 A：文件清单速查

| 文件路径 | 动作 | 节 | 被谁引用 |
|---|---|---|---|
| `app_my/core/mock_llm.py` | 🟢新建 | 7.1 | `model_router.ainvoke_routed` |
| `app_my/core/config.py` | 🔵改 | 7.2 | 全局（新增 `MOCK_LLM`/`BENCH_TARGET_NAME`） |
| `app_my/core/model_router.py` | 🔵改 | 7.3 | recognizer / output 两个节点 |
| `app_my/knowledge/embedding.py` | 🔵改 | 7.4 | 本地 RAG 检索 |
| `benchmarks/locustfile.py` | 🟢新建 | 8.1 | `run_bench.sh` / `.ps1` |
| `scripts/run_bench.sh` | 🟢新建 | 9.1 | 你手动执行 |
| `scripts/run_bench.ps1` | 🟢新建 | 9.2 | 你手动执行 |
| `scripts/locust_report.py` | 🟢新建 | 9.3 | 你手动执行 |
| `docker/requirements.prod.txt` | 🟢新建 | 10.1 | `Dockerfile.svc` |
| `docker/Dockerfile.svc` | 🟢新建 | 10.2 | `docker-compose.prod.yml` |
| `docker/docker-compose.prod.yml` | 🟢新建 | 10.3 | 你手动执行 |
| `.gitee/workflows/pipeline.yml` | 🟢新建 | 11.1 | Gitee 云端 |
| `scripts/ci_local.sh` | 🟢新建 | 11.2 | 你手动执行 |
| `scripts/ci_local.ps1` | 🟢新建 | 11.3 | 你手动执行 |
| `scripts/verify_stage10.py` | 🟢新建 | 12.1 | 你手动执行 |
| `tests/unit/test_stage10_mock_llm.py` | 🟢已写入 | 5.3 | pytest（8 个用例） |
| `tests/unit/test_stage10_bench_report.py` | 🟢已写入 | 5.3 | pytest（9 个用例） |

**临时文件（用完可删）**：

- `docker/kong/kong.yml.bak` —— 17.1 删
- `logs/bench_*.log`、`logs/svc_*.log` —— 可留作排查
- `_t.py`（PowerShell 验证时临时生成的）—— 每次跑完脚本自动删

---

## 附录 B：本次实测数据原文

> 以下三张表是 **2026-10-20 在你这台机器上真实跑出来的**完整报告（`reports/bench_20261020_143045`），不是设计出来的。
> 口径：LLM 为 Mock 模式（`MOCK_LLM=true`），测的是本项目架构自身的容量。

### 表一：总览（并发 → 容量与劣化）

| 目标 | 并发 | 总请求 | 失败 | 失败率 | 总QPS | 平均ms | P95ms | P99ms | 已劣化 |
|---|---|---|---|---|---|---|---|---|---|
| 微服务（9100 经 Kong 网关） | 10 | 291 | 0 | 0.00% | 6.6 | 103 | 200 | 260 |  |
| 单体（9002 直连） | 10 | 293 | 0 | 0.00% | 6.6 | 95 | 200 | 290 |  |
| 微服务（9100 经 Kong 网关） | 20 | 579 | 0 | 0.00% | 13.0 | 104 | 220 | 330 |  |
| 单体（9002 直连） | 20 | 584 | 0 | 0.00% | 13.2 | 104 | 210 | 290 |  |
| 微服务（9100 经 Kong 网关） | 40 | 1153 | 0 | 0.00% | 26.0 | 108 | 270 | 360 |  |
| 单体（9002 直连） | 40 | 1170 | 0 | 0.00% | 26.4 | 106 | 270 | 390 |  |
| 微服务（9100 经 Kong 网关） | 60 | 1713 | 0 | 0.00% | 38.7 | 130 | 420 | 670 |  |
| 单体（9002 直连） | 60 | 1627 | 0 | 0.00% | 36.8 | 231 | 900 | 3900 | **是** |

### 表二：单体 vs 微服务（同一并发、同一脚本）

| 并发 | 场景 | 单体QPS | 网关QPS | 单体P99ms | 网关P99ms | 网关P99增幅 | 单体失败率 | 网关失败率 |
|---|---|---|---|---|---|---|---|---|
| 10 | 登录（/auth/login） | 1.85 | 1.71 | 210 | 230 | +10% | 0.00% | 0.00% |
| 10 | 对话（/chat/stream） | 1.15 | 1.49 | 130 | 220 | +69% | 0.00% | 0.00% |
| 10 | 图谱问答（/kg/ask） | 3.16 | 2.91 | 16 | 15 | -6% | 0.00% | 0.00% |
| 20 | 登录（/auth/login） | 3.90 | 3.35 | 220 | 220 | +0% | 0.00% | 0.00% |
| 20 | 对话（/chat/stream） | 2.92 | 2.54 | 140 | 500 | +257% | 0.00% | 0.00% |
| 20 | 图谱问答（/kg/ask） | 5.50 | 6.23 | 15 | 310 | +1967% | 0.00% | 0.00% |
| 40 | 登录（/auth/login） | 7.32 | 7.13 | 230 | 220 | -4% | 0.00% | 0.00% |
| 40 | 对话（/chat/stream） | 5.28 | 4.83 | 170 | 220 | +29% | 0.00% | 0.00% |
| 40 | 图谱问答（/kg/ask） | 12.01 | 12.25 | 16 | 21 | +31% | 0.00% | 0.00% |
| 60 | 登录（/auth/login） | 10.26 | 11.55 | 3000 | 560 | **-81%** | 0.00% | 0.00% |
| 60 | 对话（/chat/stream） | 6.96 | 6.94 | 240 | 320 | +33% | 0.00% | 0.00% |
| 60 | 图谱问答（/kg/ask） | 16.84 | 17.52 | 48 | 43 | -10% | 0.00% | 0.00% |

### 表三：结论（脚本自动判定）

- 劣化判定口径：错误率 > 1.0% **或** P99 > 1000 ms
- 单体架构拐点：**60 并发**
- 微服务架构拐点：**未触及（最高档仍达标）**
- 网关开销中位数最大的场景：**对话**（各档中位数 +51%）
- 网关开销中位数最小的场景：**登录**（各档中位数 -2%）

### 怎么读这三张表

1. **看拐点**：单体在 60 并发时 P99 从 290ms 跳到 **3900ms**（跳了 13 倍）， microservices 同样 60 并发只有 670ms。**这就是拆分最硬的收益**。
2. **看登录那一行（-81%）**：单体 60 并发时登录 P99 = 3000ms，网关 = 560ms。原因是单进程里 bcrypt 的 CPU 争抢（密码哈希是 CPU 密集型，一个进程里几十个并发全在抢 CPU），拆开后分摊到多个进程/服务。
3. **看对话那一行（+51% 中位数）**：这是**拆分的代价**——一次对话要多跳一次网关。50% 的额外开销换来 60 并发下不崩，值不值要按你的业务量判断。
4. **看 20 并发图谱那一行（+1967%）**：这是**噪声**，不是结论。15ms → 310ms 是偶发的冷连接/GC 尖刺。所以脚本用"各档中位数"而不是最大值来下结论——这就是为什么表三写的是"+51%"而不是"+1967%"。

> 🟡 面试时如果被追问"你这个 +1967% 怎么回事"，标准答案是：**"那是单轮偶发尖刺，我用各档中位数来消除噪声，中位数是 +51%。压测报告必须做这一步，否则结论会被一次 GC 带偏。"** 这反而是加分项。

---

## 附录 C：PowerShell 5.1 等价替换速查表

PowerShell 5.1（Windows 10 自带）**不支持**下面这些写法。左列是 Git Bash 里的写法，右列是 PowerShell 5.1 的等价替换。

| Git Bash 写法 | PowerShell 5.1 等价 | 说明 |
|---|---|---|
| `cmd1 && cmd2` | `cmd1; if ($?) { cmd2 }` | 5.1 没有 `&&`（PS7+ 才有） |
| `cmd1 \|\| cmd2` | `cmd1; if (-not $?) { cmd2 }` | 同上 |
| `nohup cmd &` | `Start-Process -FilePath cmd -NoNewWindow -RedirectStandardOutput out.log` | 没有 nohup |
| `grep "x" file` | `Select-String -Path file -Pattern "x"` | — |
| `grep -n "x" file` | `Select-String -Path file -Pattern "x" \| ForEach-Object { $_.LineNumber }` | 带行号 |
| `head -20 file` | `Get-Content file -TotalCount 20` | — |
| `tail -20 file` | `Get-Content file -Tail 20` | — |
| `wc -l < file` | `(Get-Content file).Count` | 计数 |
| `2>/dev/null` | `-ErrorAction SilentlyContinue` 或 `2>$null` | 错误重定向 |
| `export VAR=x` | `$env:VAR = "x"` | 环境变量 |
| `unset VAR` | `Remove-Item Env:VAR` | 删环境变量 |
| `VAR=x cmd` | `$env:VAR="x"; cmd; Remove-Item Env:VAR` | 临时环境变量（**必须手动清理**） |
| `curl ...` | `Invoke-WebRequest ... -UseBasicParsing` | `curl` 在 PS 里是别名，行为不同；要写 `curl.exe` 才是真的 curl |
| `$(cmd)` | `$(cmd)` | 一样 |
| `for i in $(seq 1 20)` | `1..20 \| ForEach-Object { }` | 循环 |
| `sleep 20` | `Start-Sleep -Seconds 20` | — |
| `mkdir -p a/b` | `New-Item -ItemType Directory -Force -Path a\b` | — |
| `ls -1 dir` | `Get-ChildItem dir \| Select-Object -ExpandProperty Name` | — |
| `rm -f file` | `Remove-Item file -ErrorAction SilentlyContinue` | — |
| `stat -c %s file` | `(Get-Item file).Length` | 文件大小 |
| 多行 `python -c "..."` | `@'...'@ \| Set-Content t.py; python t.py` | here-string，**结尾 `"@` 必须顶格** |
| `echo $?`（看外部命令退出码） | `$LASTEXITCODE` | 🔴 `$?` 判断的是 PS 语句，不是外部程序 |

### 一条万能的"在 PowerShell 里跑多行 Python"模板

```powershell
@'
import sys
print("hello", sys.version)
'@ | Set-Content -Encoding UTF8 _t.py
.\.venv3\Scripts\python.exe _t.py
Remove-Item _t.py
```

> 🔴 **结尾的 `'@` 必须顶格、前面不能有任何空格**，否则 PowerShell 会一直等输入、卡住不返回。

---

**手册结束。** 做完第二十节的全部勾选项，阶段 10 就收官了。下一步是阶段 11（如果总表里有的话），或者做全项目的收官整理。



---

# 第二部分：说明手册（看懂为什么）

## 看懂为什么：逐行代码解释 + 专业名词

> **这份手册和《操作手册》的分工**：
> - **操作手册 = 照着做**：建什么文件、粘贴什么内容、跑什么命令、看到什么算成功。
> - **说明手册 = 看懂为什么**（本文件）：每一行代码在做什么、为什么这么写、每个参数什么意思。
>
> **全项目只有这一处做逐行代码解释**，操作手册里不再重复。
>
> **代码里的注释规则**：每段代码我都在**行尾加了中文注释**解释该行作用，**注释不加序号**，方便你直接照抄落盘。
> 代码块下面再用"这一段在做什么 / 为什么要这么写"讲一遍设计理由。

---

## 目录

- [一、这一阶段到底在干什么](#一这一阶段到底在干什么)
- [二、章节顺序对照表](#二章节顺序对照表)
- [三、专业名词解释表](#三专业名词解释表)
- [四、逐行解释：app_my/core/mock_llm.py](#四逐行解释app_mycoremock_llmpy)
- [五、逐行解释：app_my/core/config.py（改动）](#五逐行解释app_mycoreconfigpy改动)
- [六、逐行解释：app_my/core/model_router.py（改动）](#六逐行解释app_mycoremodel_routerpy改动)
- [七、逐行解释：app_my/knowledge/embedding.py（改动）](#七逐行解释app_myknowledgeembeddingpy改动)
- [八、逐行解释：benchmarks/locustfile.py](#八逐行解释benchmarkslocustfilepy)
- [九、逐行解释：scripts/run_bench.sh](#九逐行解释scriptsrun_benchsh)
- [十、逐行解释：scripts/locust_report.py](#十逐行解释scriptslocust_reportpy)
- [十一、逐行解释：docker/Dockerfile.svc](#十一逐行解释dockerdockerfilesvc)
- [十二、逐行解释：docker/docker-compose.prod.yml](#十二逐行解释dockerdocker-composeprodyml)
- [十三、逐行解释：.gitee/workflows/pipeline.yml](#十三逐行解释giteeworkflowspipelineyml)
- [十四、逐行解释：scripts/ci_local.sh](#十四逐行解释scriptsci_localsh)
- [十五、逐行解释：scripts/verify_stage10.py](#十五逐行解释scriptsverify_stage10py)
- [十六、PowerShell 版脚本的翻译要点](#十六powershell-版脚本的翻译要点)
- [十七、面试追问预案](#十七面试追问预案)

---

## 一、这一阶段到底在干什么

一句话：**回答"微服务拆分到底值不值"，并把答案变成可复现的数字；顺带把项目从"能跑"升级成"能交付"。**

拆成四块：

```
① 打桩（Mock）  →  让压测测的是"我的架构"，不是"大模型厂商的服务器"
② 压测（Locust）→  同一份脚本打两个架构，跑出 P99 / QPS / 拐点
③ 生产部署      →  gunicorn 多 worker + 容器健康检查 + 非 root + 资源上限
④ CI/CD         →  提交即跑单测与校验，附本地等价脚本保证"提交前就知道"
```

**为什么必须先做①再做②**：压测的原始数据（响应时间）里混着外部大模型调用的耗时。那个耗时随厂商负载剧烈波动，两次跑能差一倍。不摘掉它，你得到的数字是"DashScope 今天的网速"，不是"你的架构能扛多少并发"。面试官一问"这个 QPS 是谁的 QPS"就答不上来。

---

## 二、章节顺序对照表

说明手册的章节顺序**镜像操作手册的执行顺序**，方便你两边对照着看。

| 操作手册节 | 做了什么 | 本手册对应章节 |
|---|---|---|
| §7.1 | 新建 `mock_llm.py` | [四](#四逐行解释app_mycoremock_llmpy) |
| §7.2 | 改 `config.py` 加开关 | [五](#五逐行解释app_mycoreconfigpy改动) |
| §7.3 | 改 `model_router.py` 接上打桩 | [六](#六逐行解释app_mycoremodel_routerpy改动) |
| §7.4 | 改 `embedding.py` 打桩 | [七](#七逐行解释app_myknowledgeembeddingpy改动) |
| §8.1 | 新建 `locustfile.py` | [八](#八逐行解释benchmarkslocustfilepy) |
| §9.1 | 新建 `run_bench.sh` | [九](#九逐行解释scriptsrun_benchsh) |
| §9.3 | 新建 `locust_report.py` | [十](#十逐行解释scriptslocust_reportpy) |
| §10.2 | 新建 `Dockerfile.svc` | [十一](#十一逐行解释dockerdockerfilesvc) |
| §10.3 | 新建 `docker-compose.prod.yml` | [十二](#十二逐行解释dockerdocker-composeprodyml) |
| §11.1 | 新建 `pipeline.yml` | [十三](#十三逐行解释giteeworkflowspipelineyml) |
| §11.2 | 新建 `ci_local.sh` | [十四](#十四逐行解释scriptsci_localsh) |
| §12.1 | 新建 `verify_stage10.py` | [十五](#十五逐行解释scriptsverify_stage10py) |
| §9.2 / §11.3 | 两个 `.ps1` 脚本 | [十六](#十六powershell-版脚本的翻译要点) |

---

## 三、专业名词解释表

本阶段新出现的名词，按"你在哪一步会遇到它"排序。

| 名词 | 一句话解释 | 在本项目里具体指什么 |
|---|---|---|
| **压测（Load Test / Benchmark）** | 用程序模拟很多用户同时访问，量出系统能扛多少、什么时候开始变慢 | Locust 起 10/20/40/60 个虚拟用户打你的接口 |
| **并发数（Concurrency）** | 同一时刻有多少个"用户"在发请求 | `--users 60` = 60 个虚拟用户同时在打 |
| **QPS / RPS / 吞吐** | 每秒处理多少个请求（Queries/Requests Per Second） | 报告里"总QPS"那一列 |
| **P99 / P95 / P50** | 百分位响应时间。P99 = 把最慢的 1% 请求算进来时的耗时 | **P99 比平均值重要得多**——平均值会被大量快请求稀释，P99 才反映"最倒霉的用户等多久" |
| **平均值（avg / mean）** | 所有请求耗时的算术平均 | 参考价值最低，只看它会被误导 |
| **拐点（Knee / 性能拐点）** | 并发加到某一档，响应时间突然明显变差的那个点 | 单体在 60 并发时 P99 从 290ms 跳到 3900ms |
| **劣化（Degradation）** | 性能明显变差的状态 | 本项目判定口径：错误率 > 1% **或** P99 > 1000ms |
| **打桩 / Mock** | 用一个"假的、行为固定的"替身换掉真实依赖 | `MOCK_LLM=true` 时把大模型换成返回固定文本的假模型 |
| **测试替身（Test Double）** | Mock 的学名，泛指测试时替换真实对象的假东西 | LangChain 的 `GenericFakeChatModel` |
| **热路径（Hot Path）** | 每次请求都会走到的代码路径 | `/chat/stream` 里"识别→营养→推荐→重排→出报告"整条链 |
| **bcrypt** | 一种**故意很慢**的密码哈希算法（慢是为了防暴力破解） | 登录慢就慢在它身上，占 CPU |
| **CPU 密集型 vs IO 密集型** | CPU 密集 = 一直在算（bcrypt）；IO 密集 = 一直在等（查数据库、等网络） | 登录=CPU密集；图谱查询=IO密集。**两者的最优 worker 数不同** |
| **worker（工作进程）** | 真正处理请求的进程。多 worker = 多个进程并行 | gunicorn 起 2~3 个 UvicornWorker |
| **gunicorn** | 生产级 Python 应用服务器，管多个 worker，worker 挂了自动拉起 | **不支持 Windows**（缺 `fcntl`），只能在 Linux 容器里跑 |
| **ASGI / WSGI** | Python Web 应用的两种接口规范。ASGI 支持异步和长连接（WebSocket、SSE）；WSGI 只支持同步 | 我们的服务是 FastAPI（ASGI），所以 worker 类必须选 `UvicornWorker` |
| **UvicornWorker** | gunicorn 的一种 worker 类型，内部跑 uvicorn（ASGI 服务器） | `-k uvicorn.workers.UvicornWorker` |
| **Docker 层缓存（Layer Cache）** | Docker 按 Dockerfile 的每一行缓存一层，没变的行直接用缓存 | 所以"先拷依赖清单装依赖，再拷代码" |
| **健康检查（HEALTHCHECK）** | 容器自己定期探一下"我的应用还活着吗" | 每 30 秒打一次自己的 `/health` |
| **start_period** | 健康检查的"启动宽限期"，这段时间内的失败不算数 | 设 40s，否则服务启动慢一点就被判 unhealthy 然后被反复重启 |
| **非 root 运行** | 容器里用普通用户（uid 1000）跑应用，不用管理员 | 容器被攻破时把损失限制在这个用户能碰到的范围 |
| **日志轮转（Log Rotation）** | 日志文件超过一定大小就切新文件、保留有限个 | `max-size: 10m` + `max-file: "3"` = 最多 30MB |
| **资源上限（mem_limit / cpus）** | 限制单个容器最多能用多少内存和 CPU | 一个服务内存泄漏时不至于拖死整台机器 |
| **CI / CD** | 持续集成 / 持续部署。代码一提交就自动跑测试、构建 | Gitee Go 流水线 |
| **流水线（Pipeline）** | CI 里的一组有序步骤 | 本项目的 `test-stage` → `build-stage` |
| **YAML 锚点（Anchor）** | YAML 里给一段内容起个名字，后面用 `<<: *名字` 复用 | `x-svc-common: &svc-common` 让 4 个服务共用一套配置 |
| **DB-less 模式** | Kong 不用数据库，配置全写在一个 yaml 文件里 | 改配置必须**重启容器**才生效（Admin API 是只读的） |
| **率限制（Rate Limiting）** | 限制单位时间内的请求次数 | Kong 插件 120/min；中间件 60/min、20/min |
| **配额（Quota）** | 按套餐限制总量，比如免费用户一天 50 次对话 | Redis 里 `quota:<租户>:<指标>:<日期>` 计数 |
| **L2 归一化** | 把一个向量的长度缩成 1（每个分量除以模长） | 打桩向量的模长必须 = 1.0 |
| **余弦相似度（COSINE）** | 用两个向量的夹角衡量相似度，忽略长度 | Milvus 集合用的度量方式 |
| **PYTHONHASHSEED** | Python 的哈希随机化开关，默认开启，导致内置 `hash()` 每次进程结果不同 | 所以打桩种子必须用 `hashlib.md5`，不能用 `hash()` |
| **SSE（Server-Sent Events）** | 服务端流式推送的一种协议，格式是 `data: xxx\n\n` | 🔴 本项目 `/chat/stream` **只是** Content-Type 写了 `text/event-stream`，实际是纯文本，没有 `data:` 前缀 |
| **DB-less Kong Admin API** | Kong 在 DB-less 模式下的管理接口，只读 | 改限流只能改 yaml + 重启 |

---

## 四、逐行解释：app_my/core/mock_llm.py

### 4.1 这一段在做什么

提供一个"假的大模型"。打开开关后，所有走 `model_router.ainvoke_routed()` 的调用都会拿到一份**格式正确、耗时固定**的假回复，完全不联网。

### 4.2 代码逐行

```python
from __future__ import annotations          # 让 Python 3.9 也能写 list[dict] 这种新式类型标注

import asyncio                              # 异步 sleep 用，模拟模型耗时
from typing import Iterator, List           # 类型标注用的两个泛型

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
#                                            LangChain 官方提供的"假对话模型"，支持 invoke/ainvoke/stream/astream 四种调用方式
from langchain_core.messages import AIMessage, BaseMessage
#                                            AIMessage = 模型回复消息；BaseMessage = 所有消息的基类

# ---- 按任务类型准备的假响应 ----
_MOCK_INGREDIENT_JSON = (                   # 给"识别食材"任务用的假回复，必须能被 parse_json_payload 抠出 JSON
    '```json\n'                             # 故意包一层 markdown 代码围栏，和真实模型常见的输出格式一致
    '{"ingredients": ['                     # 食材列表，字段名必须和下游 recognizer 期待的一致
    '{"name": "西兰花", "freshness": 9, "amount": "约300g", "usable": true},'
    #                                        freshness=新鲜度 1~10；usable=是否可用
    '{"name": "鸡胸肉", "freshness": 8, "amount": "约200g", "usable": true},'
    '{"name": "鸡蛋", "freshness": 9, "amount": "2个", "usable": true}'
    '], "warnings": []}\n'                  # warnings 空数组，避免下游取这个键时 KeyError
    '```'
)

_MOCK_REPORT_TEXT = (                       # 给"生成报告"任务用的假回复，只要求非空文本
    "【压测模式固定回复】根据您提供的食材，建议采用「白灼西兰花 + 香煎鸡胸肉 + 番茄炒蛋」"
    "三菜一汤的搭配：西兰花提供膳食纤维，鸡胸肉补充优质蛋白，鸡蛋补充卵磷脂。"
    "总热量约 620 kcal，蛋白质 48g，脂肪 22g，碳水 55g，适合控糖人群。"
    "（本段为 MOCK_LLM 模式的固定压测响应，不代表真实模型输出。）"
    #                                        末尾这句声明很重要：万一哪天忘了关开关，看到它能立刻反应过来
)

MOCK_LATENCY_SEC = 0.05                     # 假模型的固定耗时 50ms（为什么不是 0，见 4.3）

_MOCK_TEXT_BY_TASK = {                      # task 名 → 假响应内容；键名必须和 model_router.route() 认识的任务名一致
    "extract": _MOCK_INGREDIENT_JSON,       # 识别节点（文字输入）
    "vision": _MOCK_INGREDIENT_JSON,        # 识别节点（图片输入），mock 时不真的看图
    "report": _MOCK_REPORT_TEXT,            # 输出节点（生成菜谱报告）
}


def _cycling(messages: List[BaseMessage]) -> Iterator[AIMessage]:
    """把固定响应"无限循环"成迭代器"""
    while True:                             # 无限循环，永远不 StopIteration
        for m in messages:                  # 把传入的消息列表一条条吐出来
            yield m                         # yield = 每次调用取一条，不一次性返回


def mock_model(text: str = _MOCK_REPORT_TEXT) -> GenericFakeChatModel:
    """造一个秒回固定文本的假对话模型"""
    return GenericFakeChatModel(messages=_cycling([AIMessage(content=text)]))
    #      messages 参数要求传"迭代器"，不是单条消息；所以要把 AIMessage 包进 _cycling


async def ainvoke_mock(task: str, messages) -> AIMessage:
    """按任务类型返回格式正确的假响应"""
    if MOCK_LATENCY_SEC:                    # 如果配了耗时（None 或 0 就跳过）
        await asyncio.sleep(MOCK_LATENCY_SEC)   # 异步等待，不阻塞事件循环
    return AIMessage(content=_MOCK_TEXT_BY_TASK.get(task, _MOCK_REPORT_TEXT))
    #      .get(task, 默认) —— 遇到不认识的任务名就退回报告文本，避免 KeyError 让请求 500
```

### 4.3 三个"为什么必须这么写"

**① 为什么 `_cycling` 要无限循环？**

`GenericFakeChatModel` 的 `messages` 参数要求是一个**迭代器**，它每次被调用就 `next()` 取一条。压测会打几百上千次请求。如果只给一条，第二次调用就抛 `StopIteration` → 被当成"模型调用失败" → output 节点降级走兜底报告、recognizer 重试一次。**P99 全被重试逻辑污染，数据不可信**。

**② 为什么假模型还要"故意慢 50ms"，而不是 0 耗时？**

如果 `MOCK_LATENCY_SEC = 0`，压测会量出一个漂亮得不真实的 QPS——瓶颈完全落在数据库/图谱/HTTP 框架上，而 LLM 那一环"白送"。真实业务里 LLM 是每请求必经的一环，压测报告必须给它留个位置，否则上线后第一波流量就被真实耗时打脸。

50ms 是"快模型返回一段固定文本"的量级（阶段 2 实测 qwen3.7-flash 关思考模式 2 秒内出报告，这里取 50ms 是**有意压低**，好让架构自身的开销占主导）。

**③ 为什么打桩点选在 `model_router.ainvoke_routed` 而不是 `models.py` 的工厂函数？**

因为**档位（lite/standard）不等于任务（extract/report/vision）**。同一个 lite 档，"抽食材"要返回 JSON、"生成报告"要返回自然语言——从 tier 推不出该给什么格式。只有 `ainvoke_routed` 才知道 `task`。

而且 `ainvoke_routed` 是全项目**唯一**还在调 LLM 的地方（旧的 `get_chat_model().ainvoke(...)` 早已被改走这里）。在这里加一个早返回分支，**一行业务代码都不用改**，关掉开关立刻恢复。

---

## 五、逐行解释：app_my/core/config.py（改动）

### 5.1 这一段在做什么

加两个配置项：一个总开关、一个标注用的名字。

### 5.2 代码逐行

```python
    # ============================================================
    # 性能压测（v3 阶段 10 新增）
    # ============================================================
    MOCK_LLM: bool = False                  # 压测总开关。默认 False —— 正常开发/跑测试绝不能受影响
    BENCH_TARGET_NAME: str = "monolith"     # 只用于日志标注，不影响业务（真正打哪个地址由 locust --host 决定）
```

### 5.3 为什么默认必须是 `False`

这不是随便定的。如果默认 `True`：

- 你平时开发时，所有对话都返回同一段假菜谱；
- 跑集成测试时全绿但毫无意义；
- **最可怕的是你查不出原因**——代码没报错，接口也返回 200，只是内容永远是那一段。

所以：**压测才临时用环境变量打开，平时必须是关的。**

### 5.4 为什么用环境变量而不是改 `.env`

`.env` 是长期配置，改了容易忘记改回来。环境变量只在那一条命令里生效：

```bash
MOCK_LLM=true ./.venv3/Scripts/python.exe -m uvicorn main:app --port 9002
```

这条命令一结束，开关就消失了。关掉终端更是彻底清干净。

> 🔴 **唯一的例外是 PowerShell**：`PS$env:MOCK_LLM="true"` 设置后会**一直留在那个窗口里**，后面启动的所有进程都会继承。所以操作手册 17.2 里专门写了 `Remove-Item Env:MOCK_LLM` 来清理。

---

## 六、逐行解释：app_my/core/model_router.py（改动）

### 6.1 这一段在做什么

在"所有 LLM 调用的唯一出口"上加一个早返回分支。

### 6.2 代码逐行

```python
from app_my.core.config import settings     # 新增：要读 MOCK_LLM 开关，得先能拿到 settings

async def ainvoke_routed(task: str, messages, text: str = ""):
    """路由 + 调用 + 计费 + 降级，一站式完成"""
    # ---------- 压测打桩分支 ----------
    if settings.MOCK_LLM:                   # 开关打开？
        from app_my.core.mock_llm import ainvoke_mock
        #   为什么在函数里 import 而不是文件顶部：生产环境不该 import 测试替身，
        #   写在函数里就只有开关打开时才会加载，正常路径零开销
        response = await ainvoke_mock(task, messages)
        #          await —— ainvoke_mock 是异步函数（里面要 asyncio.sleep）
        logger.info("router: MOCK_LLM 命中，task=%s 直接返回固定响应", task)
        #          留一条日志，方便你事后确认"到底走没走打桩"
        return response                     # 直接返回，后面的 route/model/计费全都不执行

    tier = route(task, text)                # 原逻辑：决定用哪一档模型（lite / standard）
    model = get_model_for_tier(tier)        # 原逻辑：按档位拿到模型实例
    callbacks = [BillingCallbackHandler()]  # 原逻辑：挂计费回调，调用结束自动记 token 账
```

### 6.3 三个关键设计

**① 为什么必须放在函数最前面？**

放在"任何网络调用之前"。只要它前面有一行 `route()` 或 `get_model_for_tier()`，那行就可能触发网络或读配置，打桩的意义就打折了。

**② 为什么不挂 `BillingCallbackHandler`？**

mock 没有真实 token 消耗，自然不该记账。如果挂了，压测会把**假用量写进账单表**，把阶段 2 建立的计费数据污染掉——而且这种污染是"看起来正常的数字"，很难发现。

**③ 参数怎么传？**

- `task`：原样透传，让 mock 知道该返回 JSON 还是自然语言；
- `messages`：**原样透传但不读它**。mock 的意义是"不管你问了什么，都给一个格式正确的固定答案"。真去读 prompt 反而会让 mock 行为不可预测。

---

## 七、逐行解释：app_my/knowledge/embedding.py（改动）

### 7.1 这一段在做什么

把"文本转向量"也打桩。这是**最容易漏掉的一个外部依赖**——它不在 `model_router` 的出口上，但 chat 场景每次请求都要向量化一次用户问题。

### 7.2 代码逐行

```python
import hashlib                              # 算 md5，用作随机数种子
import math                                 # 算平方根（模长）
import random                               # 生成伪随机向量

MOCK_DIMENSION = 1024                       # 必须和 Milvus 集合的 DIMENSION 一致，否则检索报维度不匹配


def _mock_embedding(text: str) -> List[float]:
    """给一段文本算一个稳定的假向量，不联网"""
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    #      md5(text) → 十六进制串 → 取前 8 位 → 按 16 进制转成整数
    #      为什么用 md5 而不是内置 hash()：Python 默认开启哈希随机化（PYTHONHASHSEED），
    #      同一个字符串在不同进程里 hash() 结果不一样。用它会导致每次重启服务，
    #      同一个查询的检索结果都在变，压测报告的"命中率"就没有可比性了
    rng = random.Random(seed)               # 用独立 Random 实例，别碰全局 random 状态（否则影响别的代码）
    vec = [rng.uniform(-1.0, 1.0) for _ in range(MOCK_DIMENSION)]
    #      生成 1024 个 [-1, 1) 之间的随机数，组成一个向量
    norm = math.sqrt(sum(v * v for v in vec))   # 算模长（勾股定理推广到多维）
    return [v / norm for v in vec]              # 每个分量除以模长 → 单位向量（L2 归一化）


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量向量化"""
    if settings.MOCK_LLM:                       # 开关打开
        return [_mock_embedding(t) for t in texts]   # 每条文本算一个假向量，不联网
    return get_embedding_model().embed_documents(texts)  # 原逻辑：真调 DashScope


def embed_query(text: str) -> List[float]:
    """单条向量化（用户查询用）"""
    if settings.MOCK_LLM:                       # 同上
        return _mock_embedding(text)
    return get_embedding_model().embed_query(text)
```

### 7.3 两个必须做对的地方（做错了数据就不可信）

**① 种子必须用 `hashlib.md5`，不能用内置 `hash()`**

Python 3 默认开启哈希随机化（`PYTHONHASHSEED`），同一个字符串在**不同进程**里 `hash()` 的结果不一样。用它会导致：每次重启服务，同一个查询的检索结果都在变——压测报告里"推荐命中率"这类数字就没有可比性了。

验证方法（操作手册 7.4）：连跑两次同一个查询，输出必须一字不差。

**② 必须做 L2 归一化**

Milvus 集合用的是 **COSINE（余弦相似度）** 度量。余弦相似度在数学上会自动除以模长，但全零向量会让分母为 0。归一化成单位向量后，点积就等于余弦值，检索分数落在 `[-1, 1]`，和真实 embedding 的分布一致，报告里的分数才读得懂。

验证方法：模长必须 = 1.0。

**③ 维度必须是 1024**

和 `app_my/knowledge/milvus_store.py` 里的 `DIMENSION` 一致。打桩时如果维度对不上，`pymilvus` 会在检索时直接抛 `vector dimension mismatch`，表现为**所有 chat 请求 500**。所以这个数字不是随手填的。

---

## 八、逐行解释：benchmarks/locustfile.py

### 8.1 这一段在做什么

定义"虚拟用户长什么样、做什么动作"。同一个文件打到两个不同的地址，就能对比两个架构。

### 8.2 代码逐行：参数区

```python
INGREDIENT_POOL = ["土豆", "西红柿", "鸡蛋", "鸡胸肉", "西兰花",
                   "牛肉", "豆腐", "虾", "黄瓜", "茄子",]
#   图谱问答的"食材"入参池。故意用多个取值而不是固定一个：
#   /kg/ask 上挂了阶段 5 的 10 分钟缓存，只压一个固定组合的话，
#   第一个请求之后全命中缓存，测出来的是"Redis 返回"的 QPS，反映不出 Neo4j 的能力。
#   10 种食材 × 3 种病症 = 30 种组合，缓存命中率才接近真实使用

CONDITION_POOL = ["糖尿病", "痛风", "高血压"]     # 图谱问答的"病症"入参池

MESSAGE_POOL = [
    "我手里有西红柿、鸡蛋和土豆，能做什么菜？",
    "帮我分析一下这些食材的营养搭配",
    "推荐三个适合控糖的菜谱",
    "中午随便吃点啥",
    "鸡胸肉和西兰花怎么做好吃，详细说一下做法",
    "我减脂期，这些食材怎么搭配",
]
#   对话输入池。刻意混合了长短句和"详细/分析"这类信号词，
#   让阶段 2 的智能路由真的在 lite/standard 档之间切换（压测要覆盖真实分支，不是只压一条路）

WAIT_MIN = float(os.getenv("BENCH_WAIT_MIN", "1"))    # 虚拟用户两次请求之间的最短停顿（秒）
WAIT_MAX = float(os.getenv("BENCH_WAIT_MAX", "2"))    # 最长停顿。取 1~2s 而不是 0，模拟真人节奏
#   设 0 是"闭压力测"——会把服务打满，只适合找极限，不适合测稳态容量

HTTP_TIMEOUT = float(os.getenv("BENCH_TIMEOUT", "60"))  # 请求超时 60 秒
#   设长一点是为了"宁可慢也别算成失败"——超时会被 Locust 记成错误，虚高错误率最难看
```

### 8.3 代码逐行：虚拟用户类

```python
class BenchUser(HttpUser):                  # 继承 Locust 的 HttpUser = 会用 HTTP 发请求的虚拟用户
    wait_time = between(WAIT_MIN, WAIT_MAX) # 两个动作之间随机等 1~2 秒

    def on_start(self):                     # 每个虚拟用户"进场"时跑一次
        _live["now"] += 1                   # 在线计数 +1
        if _live["now"] > _live["peak"]:    # 如果超过历史峰值
            _live["peak"] = _live["now"]    # 更新峰值（后面打印 summary 要用）

        self.username = "bench_" + uuid.uuid4().hex[:10]
        #   每个 VU 一个唯一用户名。uuid 前 10 位足够唯一，又不会把数据库撑大
        self.password = "Bench@12345"       # 满足 schemas/auth.py 里 min_length=8
        self.token = ""                     # 登录后存这里

        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/register", json=payload,
                              name="/auth/register [准备]", catch_response=True) as r:
        #   name= 是"统计归类名"。不写的话 Locust 按真实 URL 聚合，
        #   而 /kg/ask?ingredient=土豆&condition=糖尿病 每个请求 URL 都不一样
        #   → 统计表出现几十行、每行一次请求，没法看。写死一个 name 就聚成一类
        #   catch_response=True 才能手动判定成功/失败
            if r.status_code == 409:        # 409 = 用户名已存在
                pass                        # 不算失败（网络重试可能撞上）
            elif r.status_code not in (200, 201):
                r.failure(f"准备阶段注册失败 HTTP {r.status_code}")   # 手动标记失败

        with self.client.post("/auth/login", json=payload,
                              name="/auth/login [准备]", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"准备阶段登录失败 HTTP {r.status_code}")
            else:
                self.token = r.json().get("access_token", "")   # 拿到 token 存起来

    def on_stop(self):                      # 离场时
        _live["now"] -= 1                   # 在线计数 -1（保持峰值统计准确）

    def _headers(self):                     # 统一生成请求头
        return {"Authorization": f"Bearer {self.token}"}   # 受保护接口都要它，无 token 直接 401
```

**为什么每个 VU 都注册自己的账号，而不是共用一个？**

1. 用户名有唯一约束，共用会在并发注册时互相撞；
2. 真实场景本来就是不同的人登录不同的账号；
3. **附带好处**：登录场景压的是"多个不同账号的密码校验"，比同一个账号反复校验更接近真实的 CPU 负载（bcrypt 有内存硬开销，不能被"缓存命中"稀释）。

### 8.4 代码逐行：三个压测场景

```python
    @task(3)                                # 权重 3：10 次动作里大约 3 次选这个
    def scenario_login(self):
        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/login", json=payload, name="/auth/login",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"登录失败 HTTP {r.status_code}")

    @task(2)                                # 权重 2：最少的。因为对话是最重的链路
    def scenario_chat(self):
        payload = {
            "message": random.choice(MESSAGE_POOL),             # 从池子里随机挑一句
            "thread_id": "bench_" + uuid.uuid4().hex[:8],       # 每次新会话，避免历史串味
            "user_id": None,                                    # 传 null = 按访客处理，不查用户画像（少一次 DB 查询）
        }
        with self.client.post("/chat/stream", json=payload, name="/chat/stream",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"对话失败 HTTP {r.status_code}")
            else:
                # 🔴 不要检查 "data:" 这种 SSE 帧头！
                #    本项目 /chat/stream 虽然 Content-Type 写了 text/event-stream，
                #    但 coordinator 里是直接 `yield content`（纯文本），没有 data: 前缀。
                #    压测 v1 在这里判过 "data:"，结果 100% 请求被判失败、失败率冲到 10%+，
                #    白白浪费一轮压测。这里只判断"有没有内容吐出来"
                if not (r.text or "").strip():
                    r.failure("对话返回空正文（链路没有产出内容）")

    @task(5)                                # 权重 5：最多的。它最轻，用来顶出"架构极限 QPS"
    def scenario_recommend(self):
        ingredient = random.choice(INGREDIENT_POOL)
        condition = random.choice(CONDITION_POOL)
        with self.client.get("/kg/ask", params={"ingredient": ingredient, "condition": condition},
                             name="/kg/ask", headers=self._headers(), catch_response=True,
                             timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"图谱问答失败 HTTP {r.status_code}")
```

**为什么权重是 3 / 2 / 5 而不是平均分配？**

- **登录 3**：要让 bcrypt 反复做密码校验（`BCRYPT_ROUNDS=12`，CPU 密集），量出"CPU 被密码哈希吃掉多少"。真实生产里登录也是 CPU 瓶颈大户。
- **对话 2**（最低）：这是全项目最重的一条链路，一次请求串五个节点，还碰本地向量检索和知识图谱。它决定的是"用户感知的响应时间"，不是"系统吞吐"。
- **图谱 5**（最高）：它最轻，用它把"架构本身的极限 QPS"顶出来。

**对话和图谱两个数字放一起看才有意义**：一个测上限，一个测真实体验。

### 8.5 代码逐行：跑完自动打印汇总

```python
_live = {"now": 0, "peak": 0}               # 自己数在线数：进场 +1、离场 -1，记住过程最大值
#   为什么不用 environment.runner.user_count：退出时 runner 已被回收，只能读到 0
#   为什么不用 events.user_started：locust 2.32 里根本没有这个事件名，
#   写错一个字母就是 AttributeError，整个文件加载失败、压测根本起不来


def _rps(entry) -> float:
    """算这个场景的实际吞吐量（请求/秒）"""
    span = float(getattr(entry, "last_request_timestamp", 0) or 0) - float(getattr(entry, "start_time", 0) or 0)
    #      locust 2.32 的 StatsEntry 上没有 total_rps（老版本才有），也没有 total_time。
    #      只有 start_time 和 last_request_timestamp（都是 time.time() 的秒级浮点），
    #      所以 RPS 只能自己算：请求数 ÷ 这批请求跨越的秒数
    if span <= 0:                           # 除以 0 保护
        return 0.0
    return entry.num_requests / span        # 请求总数 ÷ 首尾时间窗


@events.quitting.add_listener               # 注册到"压测进程退出"这个事件上
def _print_bench_summary(environment, **_kwargs):
    try:                                    # 🔴 整个函数体必须包在 try 里
        _print_bench_summary_inner(environment)
    except Exception as exc:                # 兜住一切异常
        print("")
        print("=" * 96)
        print(f"BENCH SUMMARY 生成失败：{type(exc).__name__}: {exc}")
        print("（压测数据本身没丢，看同目录下的 *_stats.csv 即可）")
        print("=" * 96)
    #   locust 对事件监听器里抛出的异常只是记一条日志，**不会**让压测失败。
    #   于是表现是"压测跑完了、CSV 也生成了，但屏幕上什么都没有"，
    #   人只会怀疑是不是自己命令敲错了。阶段 10 开发时就因为写了一个不存在的属性，
    #   连续三轮压测白跑。包一层 try，任何字段名变化都会变成屏幕上一行报错，而不是静默消失


def _print_bench_summary_inner(environment):
    stats = environment.stats               # 拿统计对象
    host = str(environment.host or "")      # 拿目标地址
    target = host.rsplit(":", 1)[-1].strip("/") or "unknown"
    #      "http://127.0.0.1:9002" → 按最后一个冒号切开 → "9002"

    scenarios = (                           # 只统计这三个被测场景
        ("/auth/login", "POST"),            # (显示名, HTTP 方法)
        ("/chat/stream", "POST"),
        ("/kg/ask", "GET"),
    )

    for name, method in scenarios:
        entry = stats.get(name, method)     # 🔴 必须同时给"名字 + 方法"
        #    只传一个参数会返回空的 Entry（num_requests=0），表里场景行会全部消失
        if entry.num_requests == 0:
            print(f"{name:<16}{'（本轮未执行）':>9}")
            continue
        fail_rate = entry.num_failures / entry.num_requests * 100
        print(f"{name:<16}{entry.num_requests:>9}..."  # 格式化对齐打印
              f"{entry.get_response_time_percentile(0.99):>9.0f}"   # P99
              f"{_rps(entry):>8.1f}")                                # RPS
```

### 8.6 已经踩过的两个坑（你别再踩）

| 坑 | 现象 | 原因 |
|---|---|---|
| `stats.get(name)` 少传 method | 所有场景显示"本轮未执行" | Locust 的统计是按 (name, method) 双键存的 |
| 用了 locust 2.32 里不存在的属性 | 屏幕上没有 summary，压测"看起来跑完了" | 事件监听器里的异常被静默吞掉 |

---

## 九、逐行解释：scripts/run_bench.sh

### 9.1 这一段在做什么

把"对 2 个目标 × 4 个并发档各跑一轮 Locust"这件很啰嗦的事收成一条命令，并保证每轮的前置条件一致（清配额、检查服务活着）。

### 9.2 代码逐行

```bash
set -euo pipefail                           # 严格模式：任何一条命令失败就退出（避免带着错误继续跑）
#   -e 出错即退出；-u 用了未定义变量就报错；-o pipefail 管道里任何一段失败整条算失败

TARGET_SCOPE="${1:-all}"                    # 第 1 个参数，默认 all（monolith + gateway 都压）
USERS_LIST="${2:-20}"                       # 第 2 个参数，默认单档 20 并发
RUN_SECONDS="${3:-60}"                      # 第 3 个参数，默认每档 60 秒

cd "$(dirname "$0")/.."                     # 切到脚本所在目录的上一级 = 项目根目录
#   这样不管你从哪个目录调用这个脚本，路径都对

PY="${PY:-./.venv3/Scripts/python.exe}"     # 解释器，允许用环境变量覆盖
#   🔴 绝不能写裸 python：Windows 上会先命中 Anaconda 3.6，读 UTF-8 配置按 GBK 解，直接 UnicodeDecodeError

if [ ! -f "$PY" ]; then                     # 🔴 这一步检查不能省
  echo "[中止] 找不到虚拟环境解释器: $PY"
  exit 1
fi
#   少了它，"解释器路径不存在"这条错误会被后面的管道整个吞掉：
#   屏幕上只看到"目标=monolith 并发=5"然后一行结果都没有、reports 目录空着，
#   人会以为是自己哪里写错了，实际上压测压根没启动

REPORT_DIR="reports/bench_$(date +%Y%m%d_%H%M%S)"   # 按时间戳分目录，避免覆盖上一轮
mkdir -p "$REPORT_DIR"

declare -A HOSTS=(                          # 关联数组：目标名 → 地址
  [monolith]="http://127.0.0.1:9002"        # 单体
  [gateway]="http://127.0.0.1:9100"         # 经 Kong 网关
)
ORDER=(monolith gateway)                    # 固定顺序，压测顺序一致才不会互相干扰

for p in 9002 9121 9122 9123 9124; do       # 前置检查：5 个服务必须先活着
  if ! curl -s -m 3 "http://127.0.0.1:$p/health" > /dev/null; then
    echo "[中止] 端口 $p 不通。按操作手册先把 5 个服务起好再压测。"
    exit 1
  fi
done

docker exec ai_chief_redis redis-cli --scan --pattern "quota:*" 2>/dev/null | while read -r k; do
  [ -n "$k" ] && docker exec ai_chief_redis redis-cli DEL "$k" > /dev/null
done
#   清当天配额：free 套餐 chat_daily 上限 50 次，压测几十秒就打满，
#   之后所有 chat 请求返回 429，报告变成"一堆 429"，看不出真实容量

IFS=',' read -r -a USER_ARRAY <<< "$USERS_LIST"   # 把 "10,20,40,60" 拆成数组

for target in "${ORDER[@]}"; do
  for users in "${USER_ARRAY[@]}"; do
    spawn=$(( users / 3 ))                  # 爬坡速率 = 并发数 ÷ 3
    [ "$spawn" -lt 1 ] && spawn=1           # 至少 1
    #   为什么不是"一秒全上"：一秒全上时头几秒全是冷启动（连接池新建、Milvus/Neo4j 重连），
    #   这些慢请求会把平均值和 P99 整体拉高，测出来的不是"稳态容量"。
    #   留 3 秒爬坡，在 45 秒的一轮里只占 7%，影响可忽略

    "$PY" -m locust -f "$LOCUSTFILE" \
      --headless \                          # 不开网页界面，命令行跑（脚本里必须加）
      --host "$host" \                      # 打哪个地址
      --users "$users" \                    # 多少并发
      --spawn-rate "$spawn" \               # 每秒起几个用户
      --run-time "${RUN_SECONDS}s" \        # 跑多久
      --csv "$csv" \                        # 输出 CSV 前缀
      --csv-full-history \                  # 额外输出时间序列 CSV（找拐点用）
      --only-summary                        # 只打印汇总表，不打每秒的实时刷新
    #   🔴 这里故意不接 `| grep` 过滤：一接管道，locust 自己报的任何错都会被过滤掉，
    #   只剩一行安静的分隔线，排查时完全看不出发生了什么。乱一点但可追溯
  done
done
```

### 9.3 为什么参数是"档位列表"而不是单个并发数

要回答"错误率拐点在哪"，就必须一路加压直到 P99 明显变差或出现失败。一档一档跑，才能把拐点画出来。**只跑一档只能得到"某个并发下还行"，写不进报告**。

---

## 十、逐行解释：scripts/locust_report.py

### 10.1 这一段在做什么

把 8 个 CSV 汇总成三张表 + 一份 Markdown 报告。

### 10.2 代码逐行：解析 CSV

```python
SCENARIOS = (                               # 场景定义：(CSV 里的 Name, HTTP 方法, 中文标签)
    ("/auth/login", "POST", "登录"),
    ("/chat/stream", "POST", "对话"),
    ("/kg/ask", "GET", "图谱问答"),
)
#   只收这三个；名字里带 " [准备]" 后缀的是进场开销，不是被测场景

FAIL_RATE_THRESHOLD = 1.0                   # 劣化判定：错误率超过 1%
P99_THRESHOLD_MS = 1000.0                   # 或者 P99 超过 1000 毫秒


def _to_float(value: str) -> float:         # 安全转 float
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0                          # 空串/脏数据一律当 0，不让报告崩掉


def parse_stats_csv(path: Path) -> dict:
    """解析一个 Locust stats CSV"""
    result = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):      # DictReader 按第一行的列名做键
            name = (row.get("Name") or "").strip()
            if not name or name.endswith("[准备]"):   # 空名字或准备阶段的请求，跳过
                continue
            req = _to_int(row.get("Request Count", "0"))
            fail = _to_int(row.get("Failure Count", "0"))
            result[name] = {
                "requests": req,
                "failures": fail,
                "fail_rate": (fail / req * 100) if req else 0.0,   # 除零保护
                "p99_ms": _to_float(row.get("99%", "0")),          # P99 就在 "99%" 这一列
                "rps": _to_float(row.get("Requests/s", "0")),      # 🔴 直接用它，别自己再算一遍
            }
    return result
```

> 🔴 **`Requests/s` 这一列是聚合口径的每秒请求数**。报告里的 QPS 直接用它，**不要**自己再用"请求数 ÷ 时长"算一遍——两个口径不一样，混用会让数字对不上。

Locust 2.32 真实写出的列名（照抄，别凭记忆改）：

```
Type, Name, Request Count, Failure Count, Median Response Time,
Average Response Time, Min Response Time, Max Response Time,
Average Content Size, Requests/s, Failures/s, 50%, 66%, 75%, 80%,
90%, 95%, 98%, 99%, 99.9%, 99.99%, 100%
```

### 10.3 代码逐行：生成对比表

```python
def build_comparison_table(rounds: list) -> list:
    by_users = {}                           # 按并发数分组
    for r in rounds:
        by_users.setdefault(r["users"], {})[r["target"]] = r

    rows = []
    for users in sorted(by_users):
        pair = by_users[users]
        if "monolith" not in pair or "gateway" not in pair:
            continue                        # 🔴 某一档缺一边就不进表
        #   避免出现"网关有数据、单体是空"的半截对比，那种表放进报告最容易误导人
        mono = pair["monolith"]["stats"]
        gw = pair["gateway"]["stats"]
        for name, _method, label in SCENARIOS:
            if name not in mono or name not in gw:
                continue
            m, g = mono[name], gw[name]
            delta = ((g["p99_ms"] - m["p99_ms"]) / m["p99_ms"] * 100) if m["p99_ms"] else None
            #       相对差 = (网关 - 单体) ÷ 单体 × 100；单体为 0 时留空（不能除零）
            rows.append({...})
    return rows
```

### 10.4 代码逐行：找拐点

```python
def find_knee(knee_rows: list, target: str):
    """找某个目标"开始劣化"的第一档并发；全程不劣化返回 None"""
    rows = [r for r in knee_rows if r["target"] == target]
    rows.sort(key=lambda r: r["users"])     # 按并发从小到大
    for r in rows:
        if r["degraded"]:                   # 错误率 > 1% 或 P99 > 1000ms
            return r["users"]               # 返回第一档劣化的并发数
    return None                             # 全程不劣化 = 还没摸到上限
```

> `None` 本身也是结论：**"压到最高档都还没到拐点"**，说明这台机器上还没摸到真实上限（要继续加压才会爆）。

### 10.5 代码逐行：为什么结论用"中位数"而不是"最大值"

```python
        per_scene = {}                      # 按场景收集各档的 P99 增幅
        for c in comparison:
            if c["delta_p99_pct"] is not None:
                per_scene.setdefault(c["label"], []).append(c["delta_p99_pct"])
        ranked = sorted(
            ((label, _median(vals)) for label, vals in per_scene.items() if _median(vals) is not None),
            key=lambda kv: kv[1], reverse=True,     # 按中位数从大到小排
        )
```

**为什么用中位数？** 某个并发档的 P99 可能被一次 GC、一次冷连接、一次限流重试拉高。取最大值会把这种偶发噪声当成"网关开销最大的场景"写进结论，结论就错了。

**实测里真发生过**：20 并发的 `/kg/ask` 出现过一次 310ms 的偶发尖刺（增幅 +1967%），而 40 并发同样场景只有 21ms。如果取最大值，结论会变成"网关让图谱查询慢了 20 倍"——完全是错的。取各档增幅的中位数（+51% 是对话场景）才代表常态。

### 10.6 代码逐行：渲染 Markdown（一个真实的坑）

```python
def render_markdown(rounds, comparison, knee, report_dir) -> str:
    out = []                                # 用列表收集每一行
    out.append("# AI 私厨 v3.0 · 阶段 10 性能压测报告")   # 🔴 每行都不带结尾换行符
    out.append("")
    out.append("| 目标 | 并发 | 总请求 | ... |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in knee:
        out.append(f"| {r['target']} | {r['users']} | ... |")
    return "\n".join(out) + "\n"            # 🔴 最后统一用 join 拼
```

> 🔴 **每一行都不要带 `\n`，最后统一 `"\n".join(out)`**。两条写法混着用（有的行带 `\n` 有的不带）就会出现"整张表挤成一行"，在渲染器里显示成一条永远滚不完的长表格，完全没法读。**这个 bug 在阶段 10 真的发生过**。

---

## 十一、逐行解释：docker/Dockerfile.svc

### 11.1 这一段在做什么

定义生产镜像：怎么装依赖、拷什么代码、用什么命令起、怎么判断活着。

### 11.2 代码逐行

```dockerfile
FROM docker.m.daocloud.io/library/python:3.13-slim
#   🔴 为什么写 DaoCloud 完整地址而不是官方 `python:3.13-slim`：
#   本机 Docker Desktop 配的 Registry Mirrors（USTC / 163 / 百度）当前全部连不上，
#   写官方地址会直接失败：failed to do request: Head "https://docker.mirrors.ustc.edu.cn/v2/...": EOF
#   DaoCloud 是项目 docker-compose.v3.yml 里一直在用的源，本地已有缓存

WORKDIR /app                                # 后续所有相对路径都基于 /app

ENV PYTHONUTF8=1 \                          # 容器默认 ASCII，中文日志一打印就 UnicodeEncodeError
    PYTHONDONTWRITEBYTECODE=1 \             # 不生成 .pyc，镜像小一点
    PIP_NO_CACHE_DIR=1 \                    # pip 不缓存下载包，镜像小一点
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple   # 国内源，不然拉依赖十几分钟

#   🔴 这里不装 curl（很多教程会 apt-get install curl，那是给自己挖坑）：
#   ① 容器内访问 deb.debian.org 常年 502/DNS 失败，一旦 apt 装不上，整条 build 当场失败；
#   ② slim 镜像自带 Python，用 urllib 做健康检查完全够用

COPY requirements.txt ./requirements.txt            # 🔴 分两行写
COPY docker/requirements.prod.txt ./requirements.prod.txt
#   `COPY a b ./x` 这种"多源到单目标"的写法，目标不是目录时会直接报 must be a directory

RUN pip install --no-cache-dir -r requirements.prod.txt   # 装依赖（含 gunicorn）
#   为什么要先拷依赖清单、再装依赖、最后拷代码：
#   Docker 按层缓存。这样"改代码重新构建"时，装依赖那一层能用缓存，不用每次重装

COPY app_my ./app_my                        # 拷业务代码（顺序不能反：依赖在前、代码在后）
COPY services ./services
COPY main.py ./main.py

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app        # 把 /app 的所有权给 appuser
USER appuser                                # 之后的所有指令都用这个用户跑（非 root）

ENV APP_MODULE=services.user.main:app \     # 默认跑哪个服务（docker run / compose 里覆盖）
    WEB_WORKERS=2 \                         # 默认几个 worker
    WEB_PORT=9121 \                         # 默认监听端口
    WEB_TIMEOUT=120                         # 默认超时（对话是长连接，必须够长）

EXPOSE 9121                                 # 声明端口（只是文档作用，真正映射靠 -p / ports:）

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('WEB_PORT','9121')+'/health',timeout=4).read()" || exit 1
#   每 30 秒探一次自己的 /health，连续 3 次失败才标记 unhealthy
#   用 Python urllib 而不是 curl：slim 镜像里没有 curl（我们没装）
#   urlopen 对连接失败/非 2xx 都会抛异常 → python 非 0 退出 → Docker 判 unhealthy
#   start_period=40s 是启动宽限期：服务启动要连数据库、建连接池，
#   不设的话启动慢一点就被判 unhealthy，compose 会不停重启它

CMD gunicorn "${APP_MODULE}" \
      -k uvicorn.workers.UvicornWorker \    # worker 类：必须是 ASGI 的，否则异步全堵死
      --workers "${WEB_WORKERS}" \          # worker 数量
      --bind "0.0.0.0:${WEB_PORT}" \        # 监听地址（容器内必须 0.0.0.0，不能 127.0.0.1）
      --timeout "${WEB_TIMEOUT}" \          # 单请求超时（对话流式要 120s）
      --graceful-timeout 30 \               # 优雅退出：收到停止信号后给 30 秒处理完手上的请求
      --access-logfile - \                  # 访问日志打到标准输出（docker logs 能看到）
      --error-logfile -                     # 错误日志同上
#   🔴 用 shell 形式（不是 exec 形式的 JSON 数组）写 CMD，
#   因为要展开 ${APP_MODULE} 这些环境变量；JSON 形式不做变量替换
```

### 11.3 生产镜像 vs 本机开发，五处不同

| 项 | 本机开发 | 生产容器 | 为什么 |
|---|---|---|---|
| 服务器 | `uvicorn main:app`（单进程） | `gunicorn` 管多个 worker | 多核利用 + worker 挂了自动拉起 |
| worker 类 | 无（就是 uvicorn） | `UvicornWorker` | 服务是 ASGI（异步），用同步 worker 会把异步堵死，`/chat/stream` 直接卡成串行 |
| 健康检查 | 无 | `HEALTHCHECK` | 没有它，容器"起来了但应用没起来"时 `docker ps` 显示 Up，只有用户报障才发现 |
| 运行用户 | 你的 Windows 用户 | `appuser`（uid 1000） | 镜像被拖库时，root 权限等于把整台机器交出去 |
| 日志 | 终端直接看 | `--access-logfile -` 打到标准输出 | 容器日志要能被 `docker logs` / Loki 采集 |

### 11.4 为什么 gunicorn 不能在本机试

gunicorn 依赖 `fcntl` 和 `os.fork`，**这两个 Windows 都没有**。在 Windows 里 `import gunicorn` 会直接：

```
ModuleNotFoundError: No module named 'fcntl'
```

**这是正常的，不是装错了。** 它只能跑在 Linux 容器里——这也正是"生产镜像"和"本机开发"必须分开的原因。

---

## 十二、逐行解释：docker/docker-compose.prod.yml

### 12.1 这一段在做什么

用容器起 4 个应用服务 + Kong 网关，每个都挂健康检查、资源上限、日志轮转。

### 12.2 代码逐行：锚点复用

```yaml
name: ai_chief_prod                         # 项目名，容器名和网络都基于它

x-svc-common: &svc-common                   # 🔴 定义锚点：以 x- 开头的键 compose 不会当成服务
  build:
    context: ..                             # 构建上下文 = 项目根目录（相对本 compose 文件所在目录）
    dockerfile: docker/Dockerfile.svc
  env_file:
    - ../.env                               # 读项目根目录的 .env（JWT_SECRET、API Key 都在里面）
  restart: unless-stopped                   # 崩了自动拉起；手动 stop 就不起来（不跟人工操作抢）
  extra_hosts:
    - "host.docker.internal:host-gateway"   # 🔴 让容器能访问宿主机
  #   DB / Redis / Neo4j / Milvus 都跑在宿主机端口上（5433 / 6380 / 7687 / 19530）。
  #   没有这一行，容器里的 127.0.0.1 指的是它自己，连数据库一律 Connection refused
  logging:
    driver: json-file
    options:
      max-size: "10m"                       # 单个日志超 10MB 就切新文件
      max-file: "3"                         # 最多留 3 个 → 总共封顶 30MB
  #   不设的话，一个跑几周的容器日志能把系统盘写满
  mem_limit: 768m                           # 内存上限：一个服务内存泄漏时不至于拖死整台机器
  cpus: 1.0                                 # CPU 上限

services:
  svc-user:
    <<: *svc-common                         # 🔴 把锚点的内容合并进来（YAML 合并键语法）
    container_name: ai_chief_prod_user
    environment:
      APP_MODULE: services.user.main:app    # 同一个镜像靠这个变量复用给 4 个服务
      WEB_PORT: "9121"
      WEB_WORKERS: "2"                      # 2 worker：登录是 bcrypt（CPU 密集），多核才有收益
      MOCK_LLM: "false"                     # 🔴 生产绝不能开 mock
```

**为什么用锚点？** 4 个服务的配置 90% 相同。不用锚点就得复制粘贴 4 遍，改一处要改 4 处，迟早漏改。

### 12.3 四个服务的 worker 数为什么不一样

| 服务 | worker 数 | 理由 |
|---|---|---|
| `svc-user` | 2 | 登录是 bcrypt **CPU 密集**，多核才有收益，但也别太多（CPU 就那么多核） |
| `svc-recognizer` | 2 | 主要调 LLM，IO 为主 |
| `svc-recommender` | 3 | 图谱 + 向量检索是 **IO 密集**，多开 worker 能把"等待"的时间重叠掉 |
| `svc-chat` | 3 | 同上，且要跨服务调用前三个，等待更多 |

> 这就是"**CPU 密集 vs IO 密集**"的实际应用：CPU 密集的 worker 数 ≈ CPU 核数；IO 密集的可以多于核数，因为大部分时间在等。

### 12.4 chat 服务的两个关键配置

```yaml
      SPLIT_MODE: "remote"                  # 🔴 生产必须 remote
      #   chat 服务要跨服务调用前三个服务。local 模式会退化成"在自己进程里跑全部节点"，等于白拆
      WEB_TIMEOUT: "120"                    # 对话是流式长连接，gunicorn 默认 30s 超时会把它掐断
```

> 🔴 `SPLIT_MODE` **不在 `config.py` 里**，它是 `app_my/agents/coordinator.py` 用 `os.getenv("SPLIT_MODE", "local")` 直接读的环境变量。默认值是 `local`（单体行为）。压测时给 9124 设 `remote` 才是"拆开"的状态。

### 12.5 Kong 网关部分

```yaml
  kong:
    image: docker.m.daocloud.io/library/kong:3.7
    #   🔴 写国内源完整地址 + 本地已缓存的版本号（3.7）
    #   官方 kong:3.9-ubuntu 在本机会去 Docker Hub 拉，而三个 Registry Mirrors 都连不上，
    #   结果是 compose up 卡在 "pulling kong" 最后失败
    environment:
      KONG_DATABASE: "off"                  # DB-less：配置全在 yaml 里，不额外起 Postgres
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      KONG_PROXY_LISTEN: "0.0.0.0:9100"     # 用户入口
      KONG_ADMIN_LISTEN: "0.0.0.0:9101"     # 管理口（容器内）
    volumes:
      - ./kong/kong.yml:/etc/kong/kong.yml:ro   # ro = 只读挂载，容器改不了配置
    ports:
      - "9100:9100"                         # 网关入口（和开发时同一个端口）
      - "9105:9101"                         # 管理口映射到 9105（避开 9101 已被 worker metrics 占用）
```

> 🔴 **DB-less 模式的关键特性**：Admin API 是**只读**的。改限流只能改 `kong.yml` 然后**重启容器**。操作手册 13.4 里那句 `docker restart ai_chief_kong` 就是因为这个。

---

## 十三、逐行解释：.gitee/workflows/pipeline.yml

### 13.1 这一段在做什么

定义云端流水线：代码 push 到 master/main 就自动跑测试和构建。

### 13.2 代码逐行

```yaml
version: '1.0'                              # Gitee Go 的流水线格式版本

name: ai-chief-ci                           # 唯一标识（英文、无空格）
displayName: 'AI私厨 v3.0 持续集成'          # Gitee 页面上显示的名字

triggers:
  push:
    - matchType: PRECISE                    # PRECISE = 精确匹配分支（不是前缀匹配）
      branch: master
    - matchType: PRECISE
      branch: main
#   只有 push 到这两个分支才触发。开发分支不触发，省 CI 资源

stages:
  - stage:
      name: test-stage
      displayName: '单元测试'
      failFast: false                       # false = 有 step 失败也继续跑完剩下的
      #   方便一次看全所有错误，不用改一个跑一次
      steps:
        - step: build@python                # Gitee Go 提供的 Python 构建环境
          name: run-pytest
          displayName: '安装依赖并跑单测'
          inputs:
            pythonVersion: '3.13'
            goals: |                        # | 表示后面的多行字符串原样保留换行
              set -e                        # 🔴 任何一条命令失败就立刻让这个 step 失败
              #   不加的话 pip 装失败也会继续往下跑，最后 pytest 报一堆莫名错误，很难定位
              python -V
              python -m pip install --upgrade pip
              pip install -r requirements.txt
              python -m pytest tests/unit -q --no-header -p no:cacheprovider
              #   🔴 只跑 tests/unit：integration 下的用例需要后端服务真的起着，
              #   CI 容器里没有后端也没有数据库，跑必然 ConnectionError

  - stage:
      name: build-stage
      displayName: '配置校验与镜像构建'
      failFast: true                        # true = 失败就停（配置都解析不了就没必要继续构建）
      steps:
        - step: build@python
          name: verify-config
          inputs:
            pythonVersion: '3.13'
            goals: |
              set -e
              pip install pyyaml
              python -c "import yaml;yaml.safe_load(open('docker/docker-compose.prod.yml',encoding='utf-8'));print('compose OK')"
              python -m py_compile benchmarks/locustfile.py scripts/locust_report.py
              #   py_compile 只检查语法，不执行代码——在 CI 里做"会不会写错"的快速筛查
              python -c "import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm; print('import OK')"
              #   冒烟：确认核心模块能被导入（少一个依赖包这里就炸）

        - step: build@docker
          name: build-image
          displayName: '构建生产镜像'
          inputs:
            dockerFileName: docker/Dockerfile.svc
            dockerImageName: ai-chief-svc
            dockerImageTag: 'stage10'
```

### 13.3 必须先说清楚的一件事

🔴 **云端 CI 的 YAML 没法在你本机实跑**。它只在 Gitee 服务器上生效，取决于云端怎么解析这份文件、云端环境里装了什么。

所以本阶段额外给了 `scripts/ci_local.sh` / `.ps1`：把流水线里的每条命令在你本机按顺序跑一遍。它能证明的是"**这些命令本身是通的**"，不能保证"云端一定接受这份 YAML 的语法"。

真要确认，只能 push 到 Gitee 看构建记录。

---

## 十四、逐行解释：scripts/ci_local.sh

### 14.1 这一段在做什么

把流水线的命令在本机跑一遍，让"CI 挂了才发现"变成"提交前就知道"。

### 14.2 代码逐行

```bash
set -euo pipefail                           # 严格模式

cd "$(dirname "$0")/.."                     # 切到项目根目录

PY="${PY:-./.venv3/Scripts/python.exe}"     # 解释器，允许覆盖
if [ ! -f "$PY" ]; then
  echo "[中止] 找不到虚拟环境解释器: $PY"
  exit 1
fi

FAILED=0                                    # 失败计数
run_step() {                                # 小工具函数：跑一条命令，记录成败
  local title="$1"; shift                   # 第 1 个参数是标题，剩下的是要执行的命令
  echo ""
  echo "--------------------------------------------------------------"
  echo " 步骤: $title"
  echo "--------------------------------------------------------------"
  if "$@"; then                             # 执行剩下的参数（就是那条命令）
    echo "[PASS] $title"
  else
    echo "[FAIL] $title"
    FAILED=$((FAILED + 1))                  # 计数 +1，但不退出
  fi
  #   为什么不失败就退出：想一次跑完全部步骤，最后看完整的 FAIL 清单
}

run_step "Python 版本（CI 用的是 3.13）" "$PY" -V

run_step "检查关键依赖是否已安装" "$PY" -c "
import importlib.util, sys
need = ['fastapi', 'uvicorn', 'sqlalchemy', 'redis', 'pytest', 'httpx', 'yaml', 'pydantic_settings']
missing = [m for m in need if importlib.util.find_spec(m) is None]
#          find_spec 只检查"能不能找到"，不真的 import —— 快，且不会触发副作用
if missing:
    print('缺失依赖:', missing)
    sys.exit(1)                             # 非 0 退出 → run_step 记 FAIL
print('关键依赖齐全:', len(need), '个')
"
#   🔴 和流水线的区别：流水线里是 `pip install -r requirements.txt`（每次全新环境都要装）
#   这里改成"检查关键依赖在不在" —— 本机早就装好了，没必要每次跑都重装一遍
#   （本项目依赖装一次要 5~6 分钟）

run_step "跑单元测试（tests/unit）" "$PY" -m pytest tests/unit -q --no-header -p no:cacheprovider

run_step "校验生产编排" "$PY" -c "
import yaml
d = yaml.safe_load(open('docker/docker-compose.prod.yml', encoding='utf-8'))
assert 'services' in d, 'compose 文件里没有 services'
print('生产编排解析通过，共', len(d['services']), '个服务:', list(d['services']))
"

run_step "校验压测脚本语法" "$PY" -m py_compile benchmarks/locustfile.py scripts/locust_report.py

run_step "冒烟：核心模块能被导入" "$PY" -c "
import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm
print('核心模块 import OK（含阶段10新增的 mock_llm）')
"

exit "$FAILED"                              # 退出码 = 失败数。0 = 全过，可直接用于 CI 判断
```

---

## 十五、逐行解释：scripts/verify_stage10.py

### 15.1 这一段在做什么

回答"阶段 10 到底做完没有"。它和 pytest 的分工：

- **pytest** —— 测"代码逻辑对不对"（141 个用例）
- **本脚本** —— 测"该有的东西在不在、能不能跑起来"（文件、配置、容器、端口、报告）

两者都绿，才算收官。

### 15.2 代码逐行

```python
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#   __file__ = .../scripts/verify_stage10.py → dirname 一次 = scripts/ → dirname 两次 = 项目根
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
#   🔴 为什么需要这三行：直接 `python scripts\verify_stage10.py` 时，
#   Python 只把 scripts\ 当作模块搜索路径，于是 `import app_my...` 会报
#   ModuleNotFoundError: No module named 'app_my'

PASS, FAIL = "OK  ", "FAIL"
_results: list = []                         # 收集所有结果，最后统一统计

def check(label: str, ok: bool, detail: str = "") -> bool:
    """记录一条检查结果并打印"""
    _results.append((PASS if ok else FAIL, label, detail))
    print("  %s %-46s %s" % (PASS if ok else FAIL, label, detail))
    #   %-46s = 左对齐占 46 个字符宽，让输出对齐成表格
    return ok


def check_files() -> None:
    """① 交付文件是否都在"""
    expected = {
        "app_my/core/mock_llm.py": "对话模型打桩器",
        ...
    }
    for rel, desc in expected.items():
        p = Path(_ROOT) / rel
        ok = p.is_file() and p.stat().st_size > 0    # 🔴 不只看存在，还看不是空文件
        check(rel, ok, f"{desc}" + ("" if ok else "（缺失或为空）"))


def check_mock_wiring() -> None:
    """② 打桩是否真的接上了 —— 不能只看文件在不在"""
    from app_my.core.config import settings
    check("MOCK_LLM 默认是关闭的", settings.MOCK_LLM is False, ...)
    #   默认必须是关的，否则正常开发全是假数据

    from app_my.core import model_router
    src = Path(model_router.__file__).read_text(encoding="utf-8")
    check("ainvoke_routed 里有 MOCK_LLM 分支", "MOCK_LLM" in src, ...)
    #   为什么用"读源码找字符串"而不是 import 后检查：
    #   打桩分支在函数体里，没法从外部观测。读源码是最直接的证据

    from app_my.knowledge.embedding import MOCK_DIMENSION
    from app_my.knowledge.milvus_store import DIMENSION
    check("打桩向量维度与 Milvus 集合一致", MOCK_DIMENSION == DIMENSION, ...)
    #   这两个常量必须相等，否则检索报维度不匹配

    import asyncio
    from app_my.core.mock_llm import ainvoke_mock
    from app_my.agents.recognizer import parse_json_payload
    data = parse_json_payload(asyncio.run(ainvoke_mock("extract", [])).content)
    n = len(data.get("ingredients") or [])
    check("extract 打桩能被识别节点解析", n >= 1, f"解析出 {n} 种食材")
    #   🔴 这是最关键的一条：打桩输出必须能被下游真的解析。
    #   解析出 0 种食材 → 后面推荐/营养节点全部空转 → 测出来的 QPS 是"什么都没干"的 QPS


def check_services() -> None:
    """③ 五个服务是否都健康"""
    for port, name in ((9002, "单体"), (9121, "user"), (9122, "recognizer"),
                       (9123, "recommender"), (9124, "chat")):
        r = requests.get(f"http://127.0.0.1:{port}/health", timeout=3)
        ok = r.status_code == 200


def check_prod_compose() -> None:
    """④ 生产编排能否被 Docker 解析"""
    proc = subprocess.run(["docker", "compose", "-f", str(compose), "config"],
                          capture_output=True, text=True, timeout=60, ...)
    check("docker compose config 通过", proc.returncode == 0, ...)
    #   🔴 为什么还要调 docker 命令：YAML 合法 ≠ compose 合法。
    #   PyYAML 只能证明语法对，证明不了 `build.context` 路径对、字段名拼对


def check_bench(bench_dir: str) -> None:
    """⑤ 压测产物与报告"""
    mono = {f.name.split("_u")[1].split("_")[0] for f in stats_files if f.name.startswith("monolith")}
    #   从文件名里反解出并发档位：monolith_u20_stats.csv → "20"
    report = d / "压测报告.md"
    text = report.read_text(encoding="utf-8")
    check("报告表格分行正常", any(line.startswith("| 目标 |") for line in text.splitlines()), ...)
    #   🔴 专门防"表格挤成一行"那个 bug。如果 table 挤成一行，startswith 就匹配不到
```

---

## 十六、PowerShell 版脚本的翻译要点

`run_bench.ps1` 和 `ci_local.ps1` 是 `.sh` 版本的逐行翻译。这里只讲**翻译时改了什么、为什么改**，因为这正是 PowerShell 5.1 最容易出错的地方。

### 16.1 `nohup cmd &` → `Start-Process`

```powershell
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--port","9002" `
    -NoNewWindow -RedirectStandardOutput "logs\bench_9002.log" -RedirectStandardError "logs\bench_9002.err.log"
```

- `-ArgumentList` 用**逗号分隔**的参数数组，不能像 bash 那样靠反斜杠续行（反斜杠续行是 PS 6+ 才有的）；
- `-NoNewWindow` = 不开新窗口（不加会弹出黑框）；
- `-RedirectStandardOutput` / `-RedirectStandardError` = 重定向输出到文件（PS 5.1 的 `*` 重定向操作符是 PS 6+ 才有的）。

### 16.2 `grep` → `Select-String`

```powershell
Select-String -Path docker\kong\kong.yml -Pattern "minute:" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
```

`$_` 是当前管道对象，`$_.LineNumber` 是行号，`$_.Line` 是那一行内容。

### 16.3 多行 Python 用 here-string

```powershell
& $PY -c @"
import importlib.util, sys
need = ['fastapi','uvicorn']
print('ok')
"@
```

🔴 **结尾的 `"@` 必须顶格**（行首不能有空格），否则 PowerShell 会一直等输入、卡住不返回。

### 16.4 判断外部命令的退出码用 `$LASTEXITCODE`

```powershell
& $PY -m pytest tests/unit -q
if ($LASTEXITCODE -ne 0) { ... }
```

🔴 **不能用 `$?`** —— `$?` 判断的是 PowerShell 自己语句的成功与否，对外部程序不可靠。

### 16.5 环境变量必须手动清理

```powershell
$env:MOCK_LLM = "true"
# ... 启动进程 ...
Remove-Item Env:MOCK_LLM       # 🔴 不清理的话，后面在这个窗口起的任何进程都会继承
```

bash 里 `VAR=x cmd` 只影响那一条命令；PowerShell 里 `$env:VAR="x"` 会**一直留在窗口里**。

### 16.6 `&&` 不存在

```powershell
# bash:  cmd1 && cmd2
# PS5.1:
cmd1; if ($?) { cmd2 }
```

### 16.7 完整的替换速查表

见《操作手册》附录 C。

---

## 十七、面试追问预案

按"最可能被问到"排序。每个问题给一句标准答案 + 追问怎么接。

### Q1："你这个压测的 QPS 是谁的 QPS？"

**标准答案**：我自己的架构的。我用 `MOCK_LLM` 开关把大模型调用换成了固定耗时（50ms）的假模型，所以响应时间里不含厂商的网络往返和排队。否则同一套代码连跑两次，数字能差一倍。

**追问**："那 50ms 是怎么定的？"
→ 真实快模型（qwen3.7-flash 关思考）2 秒内出报告，我取 50ms 是**有意压低**，好让架构自身的开销占主导。如果设 0，会量出一个漂亮但不真实的 QPS，上线后第一波流量就被真实耗时打脸。

### Q2："P99 为什么比平均值重要？"

**标准答案**：平均值会被大量快请求稀释。P99 是"最倒霉的 1% 用户等多久"，它才反映真实体验。我的报告里单体在 60 并发时平均值只有 231ms，但 P99 是 3900ms——**只看平均值会完全看不出已经崩了**。

### Q3："拐点是怎么判定的？"

**标准答案**：脚本自动判定，口径是"错误率 > 1% **或** P99 > 1000ms"，两个条件满足任一即算这一档开始劣化。我跑了 10/20/40/60 四个档，单体在 60 并发触发，微服务最高档仍未触发。

**追问**："微服务没到拐点说明什么？"
→ 说明这台机器上还没摸到它的真实上限，要继续加压（80/120 并发）才会爆。这本身也是结论：**微服务的容量上限至少比单体高一个档位**。

### Q4："拆分的收益具体是多少？"

**标准答案**：60 并发下登录场景 P99 从 3000ms 降到 560ms，**降低 81%**（约 5.8 倍）。定位到瓶颈是单进程内 bcrypt 密码哈希的 CPU 争抢，拆分后被分摊到多个进程。

**追问**："代价呢？"
→ 对话场景网关开销中位数 +51%（多一跳网络）。50% 的额外开销换 60 并发下不崩，值不值要按业务量判断。**我会把代价也说出来**——只讲收益不讲代价的方案不可信。

### Q5："你这个 +1967% 是怎么回事？"（针对 20 并发图谱那一行）

**标准答案**：那是单轮偶发尖刺（冷连接/GC），不是常态。所以我用**各档增幅的中位数**下结论，中位数是 +51%。压测报告必须做这一步，否则结论会被一次 GC 带偏。

> 这题是加分题。能主动说明"我剔除了噪声"比只报数字强得多。

### Q6："为什么打桩点选在 model_router 而不是模型工厂？"

**标准答案**：因为档位（lite/standard）不等于任务（extract/report/vision）。同一个 lite 档，"抽食材"要返回 JSON、"生成报告"要返回自然语言——从 tier 推不出该给什么格式。而 `ainvoke_routed` 是全项目唯一还在调 LLM 的地方，在这里加早返回分支，一行业务代码都不用改。

### Q7："向量打桩为什么用 md5 而不是内置 hash()？"

**标准答案**：Python 默认开启哈希随机化（`PYTHONHASHSEED`），同一个字符串在不同进程里 `hash()` 结果不一样。用它会导致每次重启服务，同一个查询的检索结果都在变，压测报告的"命中率"就没有可比性了。所以用 `hashlib.md5` 做种子。

**追问**："为什么还要 L2 归一化？"
→ Milvus 集合用 COSINE 度量。归一化成单位向量后点积就等于余弦值，分数落在 [-1, 1]，和真实 embedding 的分布一致，报告里的分数才读得懂。

### Q8："gunicorn 为什么不能在 Windows 上跑？"

**标准答案**：它依赖 `fcntl` 和 `os.fork`，这两个 Windows 没有。所以它只能跑在 Linux 容器里——这也正是"生产镜像"和"本机开发"必须分开的原因。我在本机只装它（打进镜像用），从不启动它。

### Q9："为什么 worker 数每个服务不一样？"

**标准答案**：因为负载类型不同。`svc-user` 的登录是 bcrypt **CPU 密集**，worker 数 ≈ CPU 核数（2）；`svc-recommender` 的图谱+向量检索是 **IO 密集**，大部分时间在等，可以开多一些（3）把等待时间重叠掉。一刀切设成同一个数是常见的错误做法。

### Q10："CI 流水线你验证过吗？"

**标准答案**：云端 YAML 没法在本机实跑，所以我写了 `ci_local.sh`，把流水线里的每条命令在本机按顺序跑一遍。它能证明"这些命令本身是通的"，不能保证"云端一定接受这份 YAML 的语法"——真要确认只能 push 看构建记录。**我不会说"我验证过 CI"**，那是不诚实的。

### Q11："容器为什么用非 root？"

**标准答案**：镜像被攻破时，root 权限等于把整台机器交出去。用 uid 1000 的 `appuser` 跑，能把损失限制在这个用户能碰到的范围内。我在验收里专门加了一条 `docker exec ... id` 来确认它生效——**配置写了不代表生效**，要验证。

### Q12："健康检查为什么用 Python 不用 curl？"

**标准答案**：因为镜像里没装 curl。很多教程会写 `apt-get install curl`，但容器内访问 `deb.debian.org` 常年 502/DNS 失败，一旦装不上整条 `docker build` 当场失败。slim 镜像自带 Python，用 `urllib.request.urlopen` 做一次 HTTP GET 完全够用，多装一个二进制换一份网络依赖不划算。

---

**说明手册结束。** 配合《操作手册》（照着做）和《理解手册》（大白话 + 图解）一起看。
