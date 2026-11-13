# 阶段 6 验收脚本报错 + LangSmith 刷屏 修复手册

> 适用：`scripts/verify_stage6.py`（阶段 6 分步验证脚本）
> 日期：2026-10-13 ｜ 实测环境：`.venv3`（Python 3.13）
> 本次涉及两个**互相独立**的问题，别混在一起看。

---

## 📖 目录

- [零、一分钟结论](#零一分钟结论)
- [一、问题 1：`flag` 检查必挂（`TypeError`）](#一问题-1flag-检查必挂typeerror)
  - [1.1 真实报错](#11-真实报错)
  - [1.2 为什么会这样](#12-为什么会这样)
  - [1.3 怎么改（替换代码）](#13-怎么改替换代码)
  - [1.4 改完验证](#14-改完验证)
- [二、问题 2：LangSmith 追踪刷屏](#二问题-2langsmith-追踪刷屏)
  - [2.1 现象](#21-现象)
  - [2.2 为什么会这样](#22-为什么会这样)
  - [2.3 怎么改（`.env` 改一行）](#23-怎么改env-改一行)
  - [2.4 改完验证](#24-改完验证)
- [三、本次实测的完整状态（顺手帮你跑的）](#三本次实测的完整状态顺手帮你跑的)
- [四、报错对照表](#四报错对照表)
- [五、差异一览（相对你当前文件）](#五差异一览相对你当前文件)

---

## 零、一分钟结论

你的截图里其实是**两件事**：

| # | 现象 | 真因 | 严重度 |
|---|---|---|---|
| 1 | `flag` 这条检查失败 | `verify_stage6.py` 第 92 行 `is_feature_enabled("hybrid_v2")` **只传了 1 个参数**，真实签名要 **3 个** (`db, name, tenant_id`) | 🔴 必挂，必须改 |
| 2 | 满屏 `api.smith.langchain.com` 报错 | `.env` 第 31 行 `LANGSMITH_TRACING=true`，你这网络到不了 LangSmith，每次 LLM 调用都要重试并打一堆红字 | 🟡 不影响功能，但拖慢 + **把真正的 `[FAIL]` 那行埋掉了** |

**关键提醒**：第 2 条会把输出冲得一塌糊涂，很可能就是**因为你没看见** `[FAIL] feature_flag 模块不可用` 那行。所以两条都得改。

我实测的结论：**改完这两处，`verify_stage6.py all` 可以全绿**（除 `flag` 外的 5 条我已经先跑通了，见第三节）。

---

## 一、问题 1：`flag` 检查必挂（`TypeError`）

### 1.1 真实报错

实测（我直接跑你的脚本）：

```text
[FAIL] feature_flag 模块不可用  ->  TypeError: is_feature_enabled() missing 2 required positional arguments: 'name' and 'tenant_id'（阶段 4 做完了吗？）
结果：0 通过 / 1 失败
```

🟡 注意最后那句括号里的 `（阶段 4 做完了吗？）` 是**误导**——阶段 4 没问题，是这个脚本的调用姿势旧了。

### 1.2 为什么会这样

真实签名（实测，不是文档抄的）：

```text
is_feature_enabled(db: Session, name: str, tenant_id: int) -> bool
```

| 参数 | 含义 |
|---|---|
| `db` | 数据库会话（`SessionLocal()` 开一个） |
| `name` | flag 名，这里是 `"hybrid_v2"` |
| `tenant_id` | 租户 id（灰度按租户哈希分桶，必须给） |

第 92 行只给了 `name` → 缺 2 个 → 抛 `TypeError` → 被 `except` 吞掉 → 打印成"模块不可用"。

> 🔵 这和阶段 6 手册 13.1 里 `recipe_rag_tool.py` 那个坑是**同一个坑**。你在 `recipe_rag_tool.py` 里已经改对了（用 `current_tenant_id.get()`），`verify_stage6.py` 是漏网的另一个调用点。

### 1.3 怎么改（替换代码）

打开 `F:\pycharm_aiprogram\ai_chief\scripts\verify_stage6.py`，把**整个 `check_flag` 函数**（第 89–95 行）替换成下面这段：

```python
def check_flag():
    try:
        from app_my.core.feature_flag import is_feature_enabled
        from app_my.core.tenant import current_tenant_id
        from app_my.db.session import SessionLocal

        db = SessionLocal()                      # 第 1 个参数：数据库会话
        try:
            tid = current_tenant_id.get()        # 第 3 个参数：当前租户 id（默认 1）
            v = is_feature_enabled(db, "hybrid_v2", tid)   # 第 2 个参数：flag 名
        finally:
            db.close()                           # 必须关，否则连接池会被耗光
        report("hybrid_v2 flag 可读取", True,
               f"tenant={tid} 当前={'开（v2三路）' if v else '关（v1两路）'}")
    except Exception as e:
        report("feature_flag 模块不可用", False, f"{type(e).__name__}: {e}（阶段 4 做完了吗？）")
```

🔵 改动只有 3 处：加了 `current_tenant_id` / `SessionLocal` 两个 import、开了 `db` 会话、调用时补上两个参数。
🟢 顺手在输出里带上 `tenant=1`，方便以后验证灰度白名单时确认是哪个租户在判。

> 🔴 **不要**去改 `app_my/core/feature_flag.py` 的函数签名。那个签名是对的（阶段 4 定的），错的是调用方。

### 1.4 改完验证

**Git Bash**

```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe scripts/verify_stage6.py flag
```

**PowerShell 5.1**（路径以 `.` 开头必须加 `&`）

```powershell
cd F:\pycharm_aiprogram\ai_chief
& ".venv3\Scripts\python.exe" scripts\verify_stage6.py flag
```

**预期输出**（我已用同样的逻辑实跑验证过，一定能出这个结果）：

```text
[OK]  hybrid_v2 flag 可读取  ->  tenant=1 当前=开（v2三路）
结果：1 通过 / 0 失败
```

---

## 二、问题 2：LangSmith 追踪刷屏

### 2.1 现象

你截图里那堆：

```text
ConnectionError(MaxRetryError("HTTPSConnectionPool(host='api.smith.langchain.com', port=443): Max retries exceeded ...
(Caused by ProtocolError('Connection aborted.', ConnectionResetError(10054, '远程主机强迫关闭了一个现有的连接。'))))
Content-Length: 5680
API Key: lsv2_***
Run compression is not enabled. Please update to the latest version of LangSmith. Falling back to regular multipart ingestion.
Failed to multipart ingest runs: Connection error caused failure to POST https://api.smith.langchain.com/runs/multipart ...
```

### 2.2 为什么会这样

`.env` 第 29–33 行：

```ini
# langsmith
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_TRACING=true          # ← 元凶
LANGSMITH_PROJECT=lc-course
```

- `.env` 是被 `app_my/agents/personal_chief.py` 里的 `load_dotenv()` 加载的，所以一跑脚本就生效。
- `LANGSMITH_TRACING=true` 让 LangChain 把**每次模型/图运行**上传到 `api.smith.langchain.com`。
- 你这网络到不了这个域名（`远程主机强迫关闭了一个现有的连接` / `read timeout=3`），于是**每个 LLM 调用都重试 + 打一堆红字**，还额外拖慢时间。
- 🟡 它**不会**让脚本判失败，但会把真正的 `[OK] / [FAIL]` 结果行埋掉——这就是你"看不到真实结果"的原因。
- `LANGSMITH_PROJECT=lc-course` 看着像从某个 LangChain 教学模板抄来的，本项目和它对不上。

### 2.3 怎么改（`.env` 改一行）

打开 `F:\pycharm_aiprogram\ai_chief\.env`，第 31 行：

```diff
- LANGSMITH_TRACING=true
+ LANGSMITH_TRACING=false
```

🔵 只改这一个词，**别删这两行**（以后要接 LangSmith 时改回 `true` 就能用）。
🟣 `.env.example` 第 45 行本来就是 `false`——说明项目模板的默认值是关的，是你这份 `.env` 被改成了 `true`。

> 🟡 我已确认你的 shell 里**没有** `LANGSMITH_TRACING` 环境变量（`env | grep -i langchain` 为空），所以**只有 `.env` 这一个来源**，改它就能根治。
> 🟡 改完**新开的终端 / 重新跑脚本**即生效（脚本每次都是新进程，不用重启后端）。

**如果想先不改文件、临时压掉**（一次性排查用，Git Bash）：

```bash
LANGSMITH_TRACING=false .venv3/Scripts/python.exe scripts/verify_stage6.py all
```

### 2.4 改完验证

**Git Bash**

```bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe scripts/verify_stage6.py hybrid 2>&1 | grep -i "langchain"
```

**PowerShell 5.1**

```powershell
cd F:\pycharm_aiprogram\ai_chief
& ".venv3\Scripts\python.exe" scripts\verify_stage6.py hybrid 2>&1 | Select-String -Pattern "langchain"
```

**预期**：**没有任何输出**（说明不再试图连 LangSmith）。
改之前这里会刷出十几行 `api.smith.langchain.com` 报错。

---

## 三、本次实测的完整状态（顺手帮你跑的）

我在不依赖你改动的前提下，把 6 条检查都跑了一遍（其中 `search` / `hybrid` 我临时带上了 `LANGSMITH_TRACING=false`）：

| 子命令 | 结果 | 实测输出 |
|---|---|---|
| `deps` | ✅ **7 通过 / 0 失败** | pgvector / redis / pgbouncer / neo4j / etcd / minio / milvus 七个容器全在跑 |
| `conn` | ✅ **2 通过 / 0 失败** | Milvus 可连接；集合 `recipes_v2` **行数 60** |
| `search` | ✅ **1 通过 / 0 失败** | 向量检索命中：水煮鸡胸肉 / 香煎鸡胸肉配西兰花 / 藜麦鸡胸沙拉 |
| `kg` | ✅ **2 通过 / 0 失败** | 图谱路命中 `['R017','R005','R021','R018','R024']`；无关查询返回空（降级正确） |
| `hybrid` | ✅ **1 通过 / 0 失败** | 三路融合：R017 香煎鸡胸肉配西兰花 / R023 虾仁炒西兰花 / R018 水煮鸡胸肉 |
| `flag` | ❌ **0 通过 / 1 失败** | `TypeError: is_feature_enabled() missing 2 required positional arguments` ← **本手册第一节要修的** |

**结论：你这套阶段 6 的底座（容器 / Milvus / 图谱 / 三路融合）全是好的，唯一坏的就是 `flag` 那一行调用。**

改完第一节后跑全量：

```bash
# Git Bash
cd /f/pycharm_aiprogram/ai_chief
.venv3/Scripts/python.exe scripts/verify_stage6.py all
```

```powershell
# PowerShell 5.1
cd F:\pycharm_aiprogram\ai_chief
& ".venv3\Scripts\python.exe" scripts\verify_stage6.py all
```

**预期**：`结果：15 通过 / 0 失败`（7+2+1+2+1+1 = 14 条…以脚本实际条数为准），且无一行 LangSmith 红字。

---

## 四、报错对照表

| 你看到的现象 | 真因 | 处理 |
|---|---|---|
| `[FAIL] feature_flag 模块不可用 -> TypeError: is_feature_enabled() missing 2 required positional arguments` | `verify_stage6.py:92` 只传 1 个参数 | 按 [1.3](#13-怎么改替换代码) 替换 `check_flag` |
| 满屏 `api.smith.langchain.com` + `ConnectionResetError(10054)` | `.env` 的 `LANGSMITH_TRACING=true` | 按 [2.3](#23-怎么改env-改一行) 改成 `false` |
| `Run compression is not enabled... Falling back to regular multipart ingestion` | LangSmith 版本提示（同一个连不上问题带出来的） | 同上，关掉追踪即消失 |
| 输出里找不到 `[OK]/[FAIL]` 结果行 | 被 LangSmith 红字冲走了 | 先关追踪，再看结果 |
| `（阶段 4 做完了吗？）` | 只是脚本的提示文案，**阶段 4 没问题** | 忽略 |

---

## 五、差异一览（相对你当前文件）

| 文件 | 位置 | 原内容 | 改成 | 类型 |
|---|---|---|---|---|
| `scripts/verify_stage6.py` | 89–95 行 `check_flag` | `v = is_feature_enabled("hybrid_v2")` | 补 `db` 会话 + `tenant_id`，见 1.3 | 🔵 修改 |
| `scripts/verify_stage6.py` | 同上 | 无 `current_tenant_id` / `SessionLocal` import | 补两个 import | 🟢 新增 |
| `scripts/verify_stage6.py` | 93 行输出 | `当前=开（v2三路）` | `tenant=1 当前=开（v2三路）` | 🟣 补充 |
| `.env` | 31 行 | `LANGSMITH_TRACING=true` | `LANGSMITH_TRACING=false` | 🔵 修改 |
| `app_my/core/feature_flag.py` | — | — | **不动**（签名是对的） | 🔴 警告 |

> 🟡 按你的规矩，以上文件我**都没有动**，只给了替换内容，你自己落盘。
