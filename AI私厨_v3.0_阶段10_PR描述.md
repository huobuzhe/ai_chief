# PR 描述 · 阶段 10：性能压测 + CI/CD + 生产级部署

> 直接复制下方「PR 正文」粘贴到 Gitee/GitHub 的 PR 描述框即可。
> 分支：`feat/v3-stage10` → `main`｜提交：`49371f8`（+ 补交文档，见文末提醒）

---

## PR 标题

```
feat(v3-stage10): Locust 性能压测 + Gitee Go CI/CD + 生产级部署（gunicorn 多 worker / 非 root / 资源上限）
```

---

## PR 正文

### 一句话

用 Locust 在 Mock LLM 模式下测出**单体 60 并发出现拐点（P99 3900ms）、微服务同档仅 530ms**，把阶段 9 的微服务拆分从"架构上更优雅"变成"**有数据支撑的性能收益**"；同时补齐生产级部署与 CI/CD。

### 背景

阶段 9 把单体拆成了 4 个微服务 + Kong 网关，但"拆了到底值不值"只有架构论证、没有数据。本阶段补上这块：在**隔离掉外部大模型耗时**（Mock LLM 打桩）的前提下，测两种架构各自的容量与拐点，并顺带把"能上线"这件事做实（生产镜像 + 编排 + 流水线）。

### 做了什么

**① 压测：让测量可信**
- `app_my/core/mock_llm.py` + `model_router.py` 加 `MOCK_LLM` 开关：唯一的 LLM 出口处打桩，假响应按 task 分派（extract/vision 返回可解析的 JSON，report 返回非空文本），并**故意保留 50ms 时延**——让 LLM 这一环在报告里仍有位置，不测出"漂亮得不真实"的 QPS
- `knowledge/embedding.py` 加假 embedding：md5 做种子保证**跨进程确定性**，L2 归一化保证模长 1.0、维度与 Milvus 的 1024 一致
- `benchmarks/locustfile.py`：3 个场景（登录/对话/图谱问答，权重 3/2/5），图谱入参用 10 食材 × 3 病症 = 30 种组合绕开 10 分钟缓存，峰值并发自建计数（locust 2.32 的 `StatsEntry` 没有 `num_users`）
- `scripts/run_bench.sh/.ps1` 编排多目标 × 多并发档；`scripts/locust_report.py` 汇总成对比表 + 拐点表 + Markdown 报告

**② 生产级部署**
- `docker/Dockerfile.svc`：gunicorn + `UvicornWorker`（ASGI，不能用同步 worker）、非 root 用户、`HEALTHCHECK` 用 Python urllib（不装 curl，避免 apt 源 502 让整个 build 失败）、`PYTHONUTF8=1`
- `docker/docker-compose.prod.yml`：4 服务 + Kong，日志轮转（10m × 3）、`mem_limit 768m` / `cpus 1.0`
- `docker/env.prod-override`：容器视角连接串覆盖层（`.env` 的 localhost 在容器里指自己，必须改 `host.docker.internal`）

**③ CI/CD**
- `.gitee/workflows/pipeline.yml`：两阶段——单测（只跑 `tests/unit`，集成测试要后端服务，CI 里跑不通）+ 编排校验/镜像构建
- `scripts/ci_local.sh/.ps1`：把流水线每条命令在本机跑一遍（云端 YAML 本机跑不了，这样能提前发现命令级错误）

**④ 验收**
- `scripts/verify_stage10.py`：33 项（交付文件 / 打桩接线 / 5 个服务健康 / 生产编排 / 压测产物）

### 实测结果

| 项 | 结果 |
|---|---|
| 单测 | `tests/unit` **124 → 141 passed**（+8 打桩 +9 报告）；全量 **157 passed / 7 deselected** |
| 验收脚本 | `verify_stage10.py` **33 项全部 OK** |
| 压测 | 8 轮（单体 + 网关 × 10/20/40/60 并发），**失败率全部 0.00%** |
| 拐点 | 单体 **60 并发**（P99 3900ms，判定劣化）；微服务同档 P99 **530ms** 未触及拐点 |
| 拆分收益 | 登录场景 60 并发 P99 **2700ms → 390ms（-86%）**；对话场景网关开销中位数 +29%，图谱问答 -7% |
| 生产部署 | 5 容器全 `Up (healthy)`；走 Kong 9100 端到端：401 ✓ / token 299 字符 ✓ / 图谱真实推理 ✓ / 对话真实 LLM ✓ |
| CI 本地验证 | `bash scripts/ci_local.sh` **6 步全部 PASS** |

### 影响面 / 风险

- **默认关闭**：`MOCK_LLM` 默认 `False`，不打桩时行为与阶段 9 完全一致；压测才显式开
- **不改动既有接口**：本阶段未改任何 API 契约，新增的都是独立脚本与配置文件
- **基础设施沿用**：生产编排不含数据库/Redis/Neo4j/Milvus，沿用 `docker-compose.v3.yml` 那批容器（容器经 `host.docker.internal` 访问）
- **已知限制**：`run_bench.ps1` / `ci_local.ps1` 只做了静态语法验证 + 关键路径核对，完整压测是用 `run_bench.sh` 在 Git Bash 跑的

### Self-check

- [x] `pytest tests/unit` = 141 passed；全量 157 passed
- [x] `scripts/verify_stage10.py` 33 项 OK
- [x] `bash scripts/ci_local.sh` 6 步 PASS
- [x] 生产镜像构建成功，`docker compose config` 退出码 0
- [x] 压测临时调高的 Kong 限流已恢复（600/300/300/120）
- [x] `MOCK_LLM` 已关闭（对话返回真实模型输出）
- [x] 压测残留账号已清理（549 个 `bench_*`）
- [ ] ⚠️ 补交文档：三份手册 + 压测报告（见下）

---

## ⚠️ 提交前请补这一步（否则 PR 里没有文档）

> 🟡 本节的命令是**简版**（只有 Git Bash、不含 `pr_stage10.md`）。完整双终端版（含把 PR 正文写成仓库根目录的 `pr_stage10.md`、一起提交推送）见《操作手册》**§21 写 PR 描述（入库与推送）**，推荐直接照 §21 执行。

`.gitignore` 第 10 行的 `*.md` 把所有 Markdown 都忽略了，`git status` 看着干净，其实**三份手册和压测报告从未入库**（全仓库历史只提交过 `README.md`）。

**Git Bash：**

```bash
git add -f "AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md" \
         "AI私厨_v3.0_阶段10_说明手册_性能压测与CI-CD.md" \
         "AI私厨_v3.0_阶段10_理解手册_性能压测与CI-CD.md" \
         "AI私厨_v3.0_阶段10_最终完整版.md" \
         "AI私厨_v3.0_阶段10_问题与解决记录.md" \
         "AI私厨_v3.0_阶段10_PR描述.md" \
         "reports/bench_20261021_171618/压测报告.md"
git commit -m "docs(v3-stage10): 补交阶段10手册、压测报告与问题记录"
```

**PowerShell 5.1：**

```powershell
git add -f "AI私厨_v3.0_阶段10_操作手册_性能压测与CI-CD.md"
git add -f "AI私厨_v3.0_阶段10_说明手册_性能压测与CI-CD.md"
git add -f "AI私厨_v3.0_阶段10_理解手册_性能压测与CI-CD.md"
git add -f "AI私厨_v3.0_阶段10_最终完整版.md"
git add -f "AI私厨_v3.0_阶段10_问题与解决记录.md"
git add -f "AI私厨_v3.0_阶段10_PR描述.md"
git add -f "reports/bench_20261021_171618/压测报告.md"
git commit -m "docs(v3-stage10): 补交阶段10手册、压测报告与问题记录"
```

**顺手建议一并修掉**（不然下个阶段还会再漏一次）：把 `.gitignore` 第 10 行的 `*.md` 改成 `tmp/*.md`，并清掉第 52~54 行的 NUL 字节（PowerShell 追加留下的 UTF-16LE 残迹，导致 git 把 `.gitignore` 当二进制、`git diff` 显示 `Binary files differ`）。命令见《最终完整版》第二章。
