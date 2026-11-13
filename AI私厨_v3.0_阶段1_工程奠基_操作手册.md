# AI 私厨 v3.0 · 阶段 1：工程奠基（操作手册）

> **本阶段目标**：在 `F:\pycharm_aiprogram\ai_chief` 建立 v3.0 独立工程——git 克隆保留全部历史、关联 Gitee 新仓库、重建虚拟环境、独立基础设施（pgvector 5433 + redis 6380）、pytest 基线 14 全绿。完成后 **v2.0 和 v3.0 两个项目可以同时运行、互不影响**。
>
> - 预计工作量：一个晚上（1~2 小时）
> - 你要做的：**一条克隆命令 + 重建环境 + 复制改配置 + 新建 1 个 compose 文件 + 改 2 个文件各 1 行**
> - 🔴 本阶段铁律：**`F:\pycharm_aiprogram\ai_sichu`（v2.0）一个字节都不动**——它已冻结为可随时演示的真实项目
> - 本手册所有命令均已在 2026-09-26 本机实测验证（克隆完整性、端口空闲、镜像就绪均已核对）

---

## 目录

- [0. 使用说明与颜色约定](#0-使用说明与颜色约定)
- [1. 本阶段要干什么（先看懂再动手）](#1-本阶段要干什么先看懂再动手)
- [2. 第一步：Gitee 新建空仓库 ai_chief](#2-第一步gitee-新建空仓库-ai_chief)
- [3. 第二步：本地克隆出新目录](#3-第二步本地克隆出新目录)
- [4. 第三步：关联新 Gitee 仓库](#4-第三步关联新-gitee-仓库)
- [5. 第四步：重建虚拟环境](#5-第四步重建虚拟环境)
- [6. 第五步：复制并修改 .env](#6-第五步复制并修改-env)
- [7. 第六步：新建 docker-compose.v3.yml](#7-第六步新建-docker-composev3yml)
- [8. 第七步：起 v3.0 独立基础设施](#8-第七步起-v30-独立基础设施)
- [9. 第八步：起后端并导入菜谱知识库](#9-第八步起后端并导入菜谱知识库)
- [10. 第九步：两处基线适配（各改 1 行）](#10-第九步两处基线适配各改-1-行)
- [11. 第十步：pytest 基线验证](#11-第十步pytest-基线验证)
- [12. 双项目并存验证](#12-双项目并存验证)
- [13. 验收清单](#13-验收清单)
- [14. 错误对照表](#14-错误对照表)
- [15. 不做清单](#15-不做清单)
- [16. 提交 Gitee 与 PR 描述](#16-提交-gitee-与-pr-描述)

---

## 0. 使用说明与颜色约定

- 每章都是「**操作 → 验证**」两段式：做完操作立刻跑验证，绿了再进下一章。
- 命令给出 **PowerShell** 和 **Git Bash** 两个版本，效果一样。
- 颜色标注（与整体规划文档的差异）：🟢新增 / 🔵修改 / 🟣补充 / 🟡提醒 / 🔴警告。

---

## 1. 本阶段要干什么（先看懂再动手）

### 1.1 迁移全景图

```text
F:\pycharm_aiprogram\
├── ai_sichu\     ← v2.0：冻结不动，随时可跑（端口 8002/5432/6379）
└── ai_chief\     ← v3.0：本阶段新建（端口 9002/5433/6380）✨
```

### 1.2 为什么是「git 克隆」而不是「复制文件夹」

| 方式 | 结果 |
|---|---|
| ❌ 资源管理器复制文件夹 | 会把几 GB 的 .venv 垃圾带过去（且里面全是旧目录的绝对路径，复制过去也用不了）；.git、.env 一起带，容易误推密钥 |
| ✅ `git clone` 本地仓库 | 代码、历史、tag 全保留；.venv/.env 自动排除（.gitignore 的功劳）；干净且可控 |

### 1.3 本阶段改动的文件清单（总共 3 个）

| # | 文件 | 改动 |
|---|---|---|
| 1 | `docker/docker-compose.v3.yml` | 🟢 新建（v3 独立基础设施） |
| 2 | `tests/conftest.py` | 🔵 改 1 行（测试目标 8002 → 9002） |
| 3 | `frontend/js/api.js` | 🔵 改 1 行（前端端口判断适配 9000/9002） |

外加 `.env`（不进 git，不算代码改动）。

---

## 2. 第一步：Gitee 新建空仓库 ai_chief

**操作**：

1. 浏览器打开 https://gitee.com/projects/new（需登录）
2. 仓库名填：`ai_chief`
3. 🔴 **不要勾选**任何初始化选项（"使用 Readme 文件初始化"、"设置开源"等一律不勾）——必须是**空仓库**，否则推送时历史对不上
4. 私有/公开：选**私有**（以后想开源再改）

**验证**：新建后页面显示空仓库提示（"Git 全局设置…"之类的引导文字），地址为 `https://gitee.com/huobuzhe/ai_chief.git`。

---

## 3. 第二步：本地克隆出新目录

🟡 前提：v2.0 的所有改动都已提交（阶段 7 PR !6 已合并，master = 86edb6a，已确认）。

**操作**（PowerShell 或 Git Bash 都行）：

```powershell
# PowerShell
cd F:\pycharm_aiprogram
git clone F:\pycharm_aiprogram\ai_sichu F:\pycharm_aiprogram\ai_chief
```

```bash
# Git Bash
cd /f/pycharm_aiprogram
git clone /f/pycharm_aiprogram/ai_sichu /f/pycharm_aiprogram/ai_chief
```

**验证**：

```bash
cd F:\pycharm_aiprogram\ai_chief
git log --oneline -3        # 应看到 !6 阶段7 提交（86edb6a 开头）
git tag                     # 应输出 v1.0.0
ls                          # 应有 main.py、app_my、frontend、tests、docker、requirements.txt 等
```

🟡 顺手核对（已实测，你复验一遍更安心）：

```bash
# 确认 .env 和 .venv 没被带过来（应该都提示不存在）
ls .env .venv
```

预期：`No such file or directory` —— 这是**正确**的，后面第五、六步补上。

---

## 4. 第三步：关联新 Gitee 仓库

克隆出来的目录，remote 还指向旧仓库（ai_sichu）。要把它改到新仓库。

**操作**：

```bash
cd F:\pycharm_aiprogram\ai_chief
git remote -v                              # 先看：origin 现在指向 ai_sichu.git
git remote set-url origin https://gitee.com/huobuzhe/ai_chief.git
git remote -v                              # 再看：origin 已指向 ai_chief.git
git push -u origin master                  # 把全部历史推到新仓库
```

**验证**：

1. 命令行输出推送进度，最后 `* [new branch] master -> master`
2. 打开 `https://gitee.com/huobuzhe/ai_chief`，能看到所有提交历史和 `v1.0.0` 标签

```bash
git push origin v1.0.0                     # 标签单独推一下
```

🟡 如果推送时提示登录，用你的 Gitee 账号密码或令牌即可（和 v2.0 推送方式一样）。

---

## 5. 第四步：重建虚拟环境

**操作**：

```powershell
# PowerShell
cd F:\pycharm_aiprogram\ai_chief
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

```bash
# Git Bash
cd /f/pycharm_aiprogram/ai_chief
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

🟡 `requirements.txt` 是阶段 6 用 `pip freeze` 锁定的 107 个包，装出来和 v2.0 环境完全一致；清华源速度快。

**验证**：

```bash
.venv/Scripts/python.exe -m pytest --version     # 应输出 pytest 9.1.1
.venv/Scripts/python.exe -c "import fastapi, jose, psycopg2, redis; print('依赖 OK')"
```

---

## 6. 第五步：复制并修改 .env

**操作 1：从 v2.0 复制**

```powershell
# PowerShell
copy F:\pycharm_aiprogram\ai_sichu\.env F:\pycharm_aiprogram\ai_chief\.env
```

```bash
# Git Bash
cp /f/pycharm_aiprogram/ai_sichu/.env /f/pycharm_aiprogram/ai_chief/.env
```

**操作 2：打开新目录里的 `.env`，做 4 处修改**：

| # | 键 | 改成 | 说明 |
|---|---|---|---|
| 1 | `DATABASE_URL` | `postgresql+psycopg2://ai_sichu:ai_sichu@localhost:5433/ai_sichu` | 🔵 端口 5432→**5433**（v3 独立数据库） |
| 2 | `CORS_ORIGINS` | `["http://localhost:9000","http://127.0.0.1:9000","http://127.0.0.1:9002","null"]` | 🔵 前端 9000、后端 9002 |
| 3 | 新增一行 `PORT=9002` | 加在文件开头附近 | 🟢 v3 后端端口（config.py 里有这个默认值 8002，.env 里显式写明更清晰） |
| 4 | 新增一行 `REDIS_URL=redis://localhost:6380/0` | 加在 PORT 下一行 | 🟢 v3 独立 Redis（config.py 默认 6379，必须覆盖） |

其余键（DASHSCOPE_API_KEY、TAVILY_API_KEY、JWT_SECRET、OSS 等）**原样保留，不要动**。

🔴 **JWT_SECRET 引号老坑提醒**：保持 v2.0 原样即可（compose 的 env_file 会自动去引号；永远不要用 `docker run --env-file` 起容器）。

**验证**：

```bash
cd /f/pycharm_aiprogram/ai_chief
grep -E "^(PORT|DATABASE_URL|REDIS_URL|CORS_ORIGINS)" .env
```

应输出（值与你设置的一致）：

```text
PORT=9002
DATABASE_URL=postgresql+psycopg2://ai_sichu:ai_sichu@localhost:5433/ai_sichu
REDIS_URL=redis://localhost:6380/0
CORS_ORIGINS=["http://localhost:9000","http://127.0.0.1:9000","http://127.0.0.1:9002","null"]
```

🟡 顺手确认 `.env` 没被 git 跟踪（.gitignore 已排除，双保险）：

```bash
git status          # 不应出现 .env
git ls-files | grep .env    # 应无输出
```

---

## 7. 第六步：新建 docker-compose.v3.yml

**操作**：在 `F:\pycharm_aiprogram\ai_chief\docker\` 目录下新建文件 `docker-compose.v3.yml`，完整复制：

```yaml
# AI 私厨 v3.0 - 独立基础设施（阶段 1）
# 只起 pgvector + redis 两个容器，与 v2.0 的容器彻底隔离：
#   - 不同容器名（ai_chief_* vs ai_sichu_*）
#   - 不同宿主机端口（5433/6380 vs 5432/6379）
#   - 不同数据卷（ai_chief_* vs ai_sichu_*）
# 用法（在项目根目录执行）：
#   起容器：docker compose -f docker/docker-compose.v3.yml up -d
#   看状态：docker compose -f docker/docker-compose.v3.yml ps
#   停止：  docker compose -f docker/docker-compose.v3.yml stop
#   删除（数据卷保留）：docker compose -f docker/docker-compose.v3.yml down

services:
  pgvector:
    # 与 v2.0 同一个镜像（本地已有，无需重新拉取）
    image: registry.cn-hangzhou.aliyuncs.com/fastgpt/pgvector:v0.7.0
    container_name: ai_chief_pgvector          # 容器名与 v2.0 区分开
    restart: unless-stopped
    environment:
      POSTGRES_USER: ai_sichu                  # 库名/账号沿用 v2.0，代码零改动
      POSTGRES_PASSWORD: ai_sichu
      POSTGRES_DB: ai_sichu
    ports:
      - "5433:5432"                            # 宿主机 5433 -> 容器内 5432
    volumes:
      - ai_chief_pgdata:/var/lib/postgresql/data   # v3 独立数据卷
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ai_sichu -d ai_sichu"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: docker.m.daocloud.io/library/redis:7-alpine   # DaoCloud 源，本地已有
    container_name: ai_chief_redis            # 容器名与 v2.0 区分开
    restart: unless-stopped
    ports:
      - "6380:6379"                            # 宿主机 6380 -> 容器内 6379
    volumes:
      - ai_chief_redisdata:/data               # v3 独立数据卷
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  ai_chief_pgdata:
  ai_chief_redisdata:
```

**验证**：

```bash
wc -c docker/docker-compose.v3.yml    # 应约 2000 字节（不是 0 就行）
```

---

## 8. 第七步：起 v3.0 独立基础设施

**操作**（在项目根目录）：

```bash
docker compose -f docker/docker-compose.v3.yml up -d
```

**验证**：

```bash
docker compose -f docker/docker-compose.v3.yml ps
```

应看到两个容器，STATUS 都是 `Up ... (healthy)`：

```text
NAME                STATUS
ai_chief_pgvector   Up 10 seconds (healthy)
ai_chief_redis      Up 10 seconds (healthy)
```

🟡 再确认 v2.0 的容器没受影响（应该原样在跑）：

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

应同时看到 6 个容器：`ai_sichu_*` 4 个（v2.0）+ `ai_chief_*` 2 个（v3.0）。

---

## 9. 第八步：起后端并导入菜谱知识库

**操作 1：起 v3.0 后端**

```powershell
# PowerShell（新开一个终端，保持运行）
cd F:\pycharm_aiprogram\ai_chief
.venv\Scripts\python.exe main.py
```

🟡 启动日志里应看到 `监听: http://0.0.0.0:9002`——端口是 9002 就对了（`.env` 里 `PORT=9002` 生效）。`init_db()` 会自动在新库里建 users 表。

**验证 1**：

```bash
curl http://127.0.0.1:9002/health
# 应输出 {"status":"ok"}
```

**操作 2：导入菜谱知识库**（新开一个终端）：

```bash
cd /f/pycharm_aiprogram/ai_chief
.venv/Scripts/python.exe scripts/import_recipes.py
```

🟡 recipes.json 在 git 里（克隆已带入），导入脚本会把 60 条菜谱向量化写入 v3 的独立 pgvector（5433）。

**验证 2**：导入脚本输出无报错（看到处理条数即成功）。想更稳可起后端问一句菜谱问题验证检索（可选）。

---

## 10. 第九步：两处基线适配（各改 1 行）

### 10.1 改 tests/conftest.py（1 行）

**操作**：打开 `tests/conftest.py`，找到这一行：

```python
    return os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8002")
```

改成：

```python
    return os.environ.get("TEST_BASE_URL", "http://127.0.0.1:9002")   # v3.0 后端端口改为 9002
```

### 10.2 改 frontend/js/api.js（1 行）

**操作**：打开 `frontend/js/api.js`，找到这一行（第 6 行附近）：

```javascript
const API_BASE = location.port === '8000' ? 'http://127.0.0.1:8002' : '';   // 开发模式直连后端，部署模式同源
```

改成：

```javascript
const API_BASE = location.port === '9000' ? 'http://127.0.0.1:9002' : '';   // v3.0 开发模式：前端9000直连后端9002，部署模式同源
```

🟡 localStorage 的键名（`ai_sichu.*`）**不用改**——浏览器里两个项目不会同时开同一个端口，token 互不干扰。

**验证**：两个文件保存后，看编辑器标签页圆点消失（落盘自检），或：

```bash
grep -n "9002" tests/conftest.py frontend/js/api.js
# 两行都能搜到 9002 即已改对
```

---

## 11. 第十步：pytest 基线验证

🟡 前提：v3.0 后端（9002）保持运行中。

**操作**（在项目根目录）：

```powershell
# PowerShell
.venv\Scripts\python.exe -m pytest -v
```

**预期输出**：

```text
tests/test_auth.py::test_register_conflict PASSED [  7%]
...（中间省略）...
tests/test_trace.py::test_trace_id_unique_per_request PASSED [100%]

====================== 14 passed, 1 deselected in ~2s =======================
```

**再验证测试用户清理**（打到 v3 的 5433 库）：

```bash
.venv/Scripts/python.exe -c "
import psycopg2
conn = psycopg2.connect('postgresql://ai_sichu:ai_sichu@localhost:5433/ai_sichu')
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM users WHERE username LIKE 'pytest_%'\")
print('v3 库残留 pytest 用户:', cur.fetchone()[0])
conn.close()"
```

应输出 `v3 库残留 pytest 用户: 0`。

🟡 前端也顺手验一下（可选但推荐）：

```bash
cd /f/pycharm_aiprogram/ai_chief/frontend
python -m http.server 9000
```

浏览器打开 `http://127.0.0.1:9000`，注册新用户 → 登录 → 发消息 → 流式正常显示。

---

## 12. 双项目并存验证

**操作**：此刻保持 v3.0 后端运行，再确认 v2.0 也能跑。

🟡 如果 v2.0 的部署栈（8001 入口）还在跑（第七步验证过容器都健康），直接浏览器打开 `http://127.0.0.1:8001`，登录 v2.0 发消息应一切正常。

**最终验证**（三个地址同时活着 = 阶段 1 目标达成）：

| 地址 | 项目 | 应有结果 |
|---|---|---|
| `http://127.0.0.1:9002/health` | v3.0 后端 | `{"status":"ok"}` |
| `http://127.0.0.1:8001` | v2.0 部署栈（nginx） | 页面正常、可对话 |
| `http://127.0.0.1:9000` | v3.0 前端 | 页面正常、可对话 |

---

## 13. 验收清单

| # | 验收项 | 结果 | 验证方式 |
|---|---|---|---|
| 1 | Gitee 新仓库 ai_chief 已建，历史与 tag 已推 | ✅ | gitee.com/huobuzhe/ai_chief 可见全部提交 |
| 2 | v2.0 目录零改动 | ✅ | `ai_sichu` 里 `git status` 干净、四容器照常运行 |
| 3 | v3.0 venv 重建，pytest 9.1.1 可用 | ✅ | `pytest --version` |
| 4 | .env 端口三件套（9002/5433/6380）就位 | ✅ | grep 验证四行 |
| 5 | v3 独立容器 healthy | ✅ | `docker compose -f docker/docker-compose.v3.yml ps` |
| 6 | v3.0 后端 9002 可访问 | ✅ | `curl :9002/health` |
| 7 | 菜谱知识库已导入 v3 库 | ✅ | import_recipes.py 无报错 |
| 8 | pytest 基线 14 passed | ✅ | `pytest -v` |
| 9 | 测试用户 0 残留 | ✅ | 清理验证输出 0 |
| 10 | 双项目同时运行互不影响 | ✅ | 第 12 章三地址验证 |

---

## 14. 错误对照表

| # | 错误现象 | 原因 | 解决 |
|---|---|---|---|
| E1 | `clone` 报 `destination path already exists` | ai_chief 目录已存在（之前试过复制） | 删掉半成品目录再克隆：`rm -rf F:\pycharm_aiprogram\ai_chief` |
| E2 | `git push` 报 `not the same project` / 历史不符 | Gitee 建仓库时勾了初始化（Readme） | 删掉 Gitee 仓库重建**空仓库**（不勾任何初始化） |
| E3 | `pip install` 卡住/超时 | 默认源走国外 | 确认命令带 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| E4 | 起容器报 `port is already allocated`（5433/6380） | 端口被其他程序占了 | `netstat -ano \| findstr :5433` 找到占用进程；本机已实测空闲，若遇到大概率是新装软件 |
| E5 | 后端起在 8002 而不是 9002 | .env 没加 PORT 或没保存 | 检查 .env 第一条 PORT=9002；改完 .env 必须重启后端（@lru_cache） |
| E6 | 后端报 `connection refused ... 5433` | v3 容器没起 / 还没 healthy | `docker compose -f docker/docker-compose.v3.yml up -d`，等 healthy 再起后端 |
| E7 | pytest 大面积 `ConnectionError` | v3 后端没起（9002） | 新终端起 `.venv\Scripts\python.exe main.py` 保持运行 |
| E8 | pytest 报 `ModuleNotFoundError: app_my` | 不在项目根目录跑 | `cd F:\pycharm_aiprogram\ai_chief` 再跑 |
| E9 | pytest 大量 429 | 1 分钟连跑 4 轮以上 | 等 60 秒再跑（v3 是全新 Redis，计数从 0 开始，正常单轮不会撞） |
| E10 | 前端 9000 页面打不开/接口 501 | api.js 端口判断没改 / 前端服务器没起 | 核对第 10.2 节那一行；`python -m http.server 9000` 要在 frontend 目录里跑 |
| E11 | 导入菜谱报错连不上 5432 | .env 的 DATABASE_URL 没改 | 核对第 6 步修改 1；改 .env 后重跑 |
| E12 | v2.0 的容器挂了 | （不应该发生）误操作了 v2.0 的 compose | `cd F:\pycharm_aiprogram\ai_sichu && docker compose -f docker/docker-compose.yml up -d` 拉回 |

---

## 15. 不做清单

- **不动 v2.0 目录的任何文件**（包括它的 .env、容器、数据）。
- **不迁移 v2.0 数据库里的历史数据**（用户/对话记录留在 v2.0；v3.0 从空库开始，只导菜谱知识库）——企业级实践里新版本环境本来就从干净数据开始。
- **不在本阶段改任何业务代码**（conftest.py 与 api.js 各 1 行属基线适配，不算业务改动）。
- **不删 Gitee 旧仓库 ai_sichu**（v2.0 的云端归档）。
- **不提前装 Neo4j/RabbitMQ/Milvus**——用到哪个阶段起哪个容器（整体规划第五节）。

---

## 16. 提交 Gitee 与 PR 描述

**操作**：

```bash
cd F:\pycharm_aiprogram\ai_chief
git checkout -b feat/v3-stage1
git add docker/docker-compose.v3.yml tests/conftest.py frontend/js/api.js
git status
git commit -m "feat(v3-stage1): 工程奠基——v3独立基础设施(5433/6380)+端口9xxx基线适配"
git push -u origin feat/v3-stage1
```

🟡 然后顺手打基线标签（合并 PR 之后做）：

```bash
git checkout master
git pull origin master
git tag v3.0.0-base
git push origin v3.0.0-base
```

**PR 描述**（在 Gitee 建 `feat/v3-stage1` → `master` 的 PR 时粘贴）：

```text
## v3.0 阶段 1：工程奠基（新目录 + 独立基础设施 + 基线守护）

### 背景与目标
v2.0（ai_sichu）已收官冻结。v3.0 在新目录 ai_chief 启动，目标是
与 v2.0 完全隔离、双项目可同时运行。本阶段通过 git 本地克隆保留
v1→v2 全部演进历史，建立 v3.0 独立基础设施。

### 变更内容
- 新增 docker/docker-compose.v3.yml：v3 独立 pgvector(5433) + redis(6380)，
  独立容器名与数据卷，与 v2.0 容器互不影响
- tests/conftest.py：测试目标端口适配 8002 → 9002
- frontend/js/api.js：前端开发端口适配（9000 → 直连后端 9002）
- .env 端口三件套：PORT=9002 / DATABASE_URL@5433 / REDIS_URL@6380（不进 git）

### 验证
1. v3 独立容器 2 个 healthy，v2.0 四容器不受影响
2. v3.0 后端 9002 /health 正常，菜谱知识库导入成功
3. pytest 基线 14 passed，测试用户残留 0
4. 双项目同时运行：127.0.0.1:9002(v3) 与 127.0.0.1:8001(v2) 均正常

### 工程意义
- 环境隔离：端口段规划（v2 用 8xxx/5432/6379，v3 用 9xxx/5433/6380）
- 基线守护：v3.0 的每次架构演进从"14 个测试全绿"出发
- 历史保留：git 克隆携带 v1.0.0 tag 与全部提交记录
```

---

> 配套文档：《AI私厨_v3.0_阶段1_工程奠基_说明手册.md》（本阶段逐行详解，全项目唯一一处逐行代码解释）
> 实测证据：2026-09-26 已在本机完整验证克隆迁移路径（关键文件 12/12 齐全、历史与 tag 完整、.env/.venv 正确排除、9000/9002/5433/6380 端口空闲、镜像本地就绪）
