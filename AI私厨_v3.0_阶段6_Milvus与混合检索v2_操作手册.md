# AI 私厨 v3.0 阶段 6 操作手册 — Milvus 向量库 + 三路混合检索 v2

> **阶段定位**：向量检索从 PGVector（数据库插件）升级到 Milvus（检索专用向量数据库），并把混合检索从"向量 + BM25 两路"升级为"**向量 50% + BM25 30% + 图谱 20%** 三路加权融合"，最后用对比实验拿出 v1 vs v2 的效果数字。对应原方案阶段 8。
>
> **本手册性质**：照着做——步骤 / 命令 / 验证 / 排错一站到底。**代码为什么这么写**见配套《说明手册》，本手册不重复解释。
>
> 🔴 **前置硬条件：阶段 5 必须已收官**（PgBouncer + 多级缓存已合并 master，pytest 基线 75 passed）。本阶段的检索路径跑在阶段 5 的缓存装饰器之上。
>
> 🟡 本阶段**新增 1 个 Python 依赖**（pymilvus）、**新增 3 个容器**（etcd / minio / milvus，内存增量约 3~4GB——16GB 机器可承受，但**做完实验可以停掉**，见避坑提示）。

---

## 目录

- [一、阶段目标](#一阶段目标)
- [二、简历叙事（照写）](#二简历叙事照写)
- [三、范围 & 与原方案差异（颜色标注）](#三范围--与原方案差异颜色标注)
- [四、端口与基础设施](#四端口与基础设施)
- [五、文件清单（创建 / 修改）](#五文件清单创建--修改)
- [六、准备（切分支、基线）](#六准备切分支基线)
- [七、子模块 1：Milvus 全家桶容器（etcd + minio + milvus）](#七子模块-1milvus-全家桶容器etcd--minio--milvus)
- [八、子模块 2：依赖与配置（pymilvus + config + .env）](#八子模块-2依赖与配置pymilvus--config--env)
- [九、子模块 3：Milvus 封装（knowledge/milvus_store.py）](#九子模块-3milvus-封装knowledgemilvus_storepy)
- [十、子模块 4：导入脚本（import_recipes_milvus.py）](#十子模块-4导入脚本import_recipes_milvuspy)
- [十一、子模块 5：图谱检索信号（core/kg.py 新增两个函数）](#十一子模块-5图谱检索信号corekgpy-新增两个函数)
- [十二、子模块 6：三路混合检索（retriever.py 升级 hybrid_search_v2）](#十二子模块-6三路混合检索retrieverpy-升级-hybrid_search_v2)
- [十三、子模块 7：灰度接线（recipe_rag_tool.py + Feature Flag）](#十三子模块-7灰度接线recipe_rag_toolpy--feature-flag)
- [十四、子模块 8：效果对比实验（retrieval_compare.py）](#十四子模块-8效果对比实验retrieval_comparepy)
- [十五、子模块 9：单元测试（8 个新测试）](#十五子模块-9单元测试8-个新测试)
- [十六、子模块 10：验证脚本与提测](#十六子模块-10验证脚本与提测)
- [十七、提交 Gitee 与 PR 描述](#十七提交-gitee-与-pr-描述)
- [十八、常见错误对照表](#十八常见错误对照表)
- [十九、避坑提示](#十九避坑提示)
- [二十、本阶段防呆自检清单](#二十本阶段防呆自检清单)

---

## 一、阶段目标

1. **向量库专用化**：菜谱向量从 PGVector（PostgreSQL 的插件，和业务表挤一个库）迁到 Milvus（为"十亿级向量检索"而生的专用数据库）；PGVector **保留为自动回退**——Milvus 挂了检索不中断。
2. **检索升级为三路**：向量管语义、BM25 管关键词、**图谱管结构化命中**（查询里出现"西兰花"，图谱知道哪些菜真含西兰花）——按 50/30/20 加权融合，某一路缺席时权重按比例自动重分配。
3. **灰度发布**：新旧检索路径用阶段 4 的 Feature Flag（`hybrid_v2`）切换——改一个开关立即生效，出问题改回去，这是"灰度发布"在个人项目里最真实的落地。
4. **效果可量化**：同一测试问题集上跑 v1 vs v2 对比实验，输出 MRR@5 / Hit@5——简历数字有出处。

**验收标准**：

- Milvus 里导入 60 条菜谱向量，真实搜索返回相关结果；
- `hybrid_v2` flag 打开后，`local_recipe_search` 走三路融合（日志可见 vector/bm25/kg 三路命中数）；关掉走 v1；
- 停掉 Milvus 容器，检索依然工作（自动回退 PGVector，日志有降级 warning）；
- `retrieval_compare.py` 输出 v1 vs v2 的 MRR@5 / Hit@5 对比表；
- pytest 基线 75 → 83 passed（新增 8 个单测）。

---

## 二、简历叙事（照写）

> 在 AI 私厨 v3.0 中将向量检索从 **PGVector 单机插件升级为 Milvus 专用向量库**（HNSW 索引 + COSINE 度量，1024 维），并设计**三路混合检索**：向量语义（50%）+ BM25 关键词（30%）+ 知识图谱结构化命中（20%）加权 RRF 融合，**单路故障时权重按比例自动重分配**（Milvus 不可用自动回退 PGVector、Neo4j 不可用自动退化为两路）。新旧检索经 **Feature Flag 按租户哈希分桶灰度**切换。对比实验（10 组真实查询）显示 MRR@5 提升 **X%**、Hit@5 提升 **Y%**（X/Y 用自己的实验数字填，阶段 10 汇总）。

---

## 三、范围 & 与原方案差异（颜色标注）

| 项 | 原方案（v3.0 十阶段表） | 本阶段做法 | 标签 |
|---|---|---|---|
| Milvus 容器 | 阶段 6（原方案 8） | standalone 模式（etcd+minio+milvus 三容器） | 🟢新增 |
| 三路融合 | 向量+BM25+图谱加权 | 权重 50/30/20，**缺席路权重按比例重分配**（原方案没写缺一路怎么办） | 🟢新增 |
| 融合算法 | 加权 | **RRF 变体**（weight/(60+rank)），与 v1 的 1/(i+1) 思路同族但更平滑 | 🔵修改 |
| PGVector 去留 | 原方案未提 | **保留为自动回退**——Milvus 挂了检索不断，简历可讲"降级链路" | 🟣补充 |
| 灰度发布 | 阶段 9 Feature Flag | 直接复用阶段 4 已落地的 flag 框架切 `hybrid_v2` | 🔵修改 |
| 检索效果评估 | 提到对比 | 落地为 10 组查询 + MRR@5/Hit@5 指标的对比脚本 | 🟣补充 |
| scripts/verify_stage6.py | — | 🔵 **覆盖 v2.0 遗留同名脚本**（内容是 v2 的 trace 验证，git 历史里永远可找回） | 🔵修改 |
| Embedding 模型 | — | 不动（qwen text-embedding，1024 维）——只换存储与检索，不动向量的来源 | 🟡提醒 |

---

## 四、端口与基础设施

| 组件 | 端口 | 说明 |
|---|---|---|
| Milvus | **19530**（gRPC 主端口） | 🟢 新增，应用连它 |
| Milvus 健康口 | **9191** → 容器 9091 | 🟢 新增，curl /healthz |
| MinIO 控制台 | **9111** → 容器 9001 | 🟢 新增（可选，浏览器看对象存储） |
| MinIO API | 容器内 9000（**不映射宿主机**） | 只有 milvus 容器用它 |
| etcd | 容器内 2379（**不映射宿主机**） | 只有 milvus 容器用它 |
| 后端 / PG / Redis / PgBouncer / Neo4j | 9002 / 5433 / 6380 / 9432 / 7474+7687 | 沿用 |

> 🟡 为什么 minio/etcd 不映射到宿主机：它们只被 milvus 容器在 docker 网络内部访问，应用和人都用不着——**不暴露就不占用宿主机端口，也不多开攻击面**（9111 控制台是可选的观察窗口）。
> 🟡 内存：etcd ~50MB + minio ~200MB + milvus ~2-3GB。机器吃紧时实验完 `docker compose -f docker/docker-compose.v3.yml stop milvus etcd minio`（数据卷保留，下次 start 秒恢复）——**检索会自动回退 PGVector，服务不中断**。

```
检索链路（本阶段之后）：

用户查询 ──► recipe_rag_tool.local_recipe_search
              │
              ├─ Feature Flag: hybrid_v2 ── off ──► v1：hybrid_search（PGVector+BM25 两路）
              │                              on
              ▼
        hybrid_search_v2（三路）
              ├─ 向量路（50%）：Milvus HNSW 检索 ──✕不可用──► 回退 PGVector
              ├─ BM25 路（30%）：进程内索引（阶段 5 已缓存）
              └─ 图谱路（20%）：查询→食材→两跳→菜谱 ──✕不可用──► 权重重分配（50%:30% → 62.5%:37.5%）
              ▼
        RRF 加权融合 → 前 k 条 →（阶段 5 缓存）
```

---

## 五、文件清单（创建 / 修改）

### 🟢 新建（7 个）

```
app_my/knowledge/milvus_store.py          Milvus 客户端封装（建集合/导入/检索/降级）
scripts/import_recipes_milvus.py          菜谱向量导入 Milvus（幂等）
scripts/retrieval_compare.py              v1 vs v2 效果对比实验（MRR@5/Hit@5）
scripts/verify_stage6.py                  v3 阶段 6 分步验证（覆盖 v2.0 遗留同名脚本）
scripts/stage6_check.ps1 / .sh            提测脚本（双终端）
tests/unit/test_hybrid_v2.py              融合与匹配单测（8 个）
```

### 🔵 修改（4 个）

```
docker/docker-compose.v3.yml              新增 etcd / minio / milvus 三个服务 + 三个卷
requirements.txt                          追加 pymilvus==2.4.15
app_my/core/config.py                     新增 MILVUS_URI / MILVUS_COLLECTION
app_my/core/kg.py                         新增 _ingredient_names / match_recipes_from_query
app_my/knowledge/retriever.py             新增 hybrid_search_v2（v1 函数原样保留）
app_my/tools/recipe_rag_tool.py           检索入口接 Feature Flag 灰度
scripts/import_recipes.py                 失效缓存时把 rag2 前缀一起清
```

---

## 六、准备（切分支、基线）

**操作 1：确认阶段 5 已合并**

```bash
cd F:/pycharm_aiprogram/ai_chief
git branch --show-current                 # master
git log --oneline -3                      # 最新是 feat(v3-stage5)
git checkout -b feat/v3-stage6
```

**操作 2：基线测试**

```bash
uv run pytest -q
```

**验证**：`75 passed`。

**操作 3：起现有容器**（Milvus 全家稍后加）：

```bash
docker compose -f docker/docker-compose.v3.yml up -d
```

---

## 七、子模块 1：Milvus 全家桶容器（etcd + minio + milvus）

### 7.1 修改 `docker/docker-compose.v3.yml`

在 `pgbouncer:` 服务块后面、`volumes:` 顶级声明前面加入（三个服务）：

```yaml
  etcd:
    image: docker.m.daocloud.io/quay.io/coreos/etcd:v3.5.14   # DaoCloud 源
    container_name: ai_chief_etcd                             # Milvus 的"元数据账本"
    restart: unless-stopped
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision                     # 按"版本号"自动压缩旧数据
      ETCD_AUTO_COMPACTION_RETENTION: "1000"                  # 保留最近 1000 个版本
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"                  # 后端存储配额 4GB
      ETCD_SNAPSHOT_COUNT: "50000"                            # 每 5 万次写做一次快照
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    volumes:
      - ai_chief_etcddata:/etcd                               # 元数据持久化（重启不丢）

  minio:
    image: docker.m.daocloud.io/minio/minio:RELEASE.2023-03-20T20-16-18Z
    container_name: ai_chief_minio                            # Milvus 的"向量文件仓库"
    restart: unless-stopped
    environment:
      MINIO_ROOT_USER: minioadmin                             # 本地默认账密（浏览器控制台也用它）
      MINIO_ROOT_PASSWORD: minioadmin
    command: minio server /minio_data --console-address ":9001"
    ports:
      - "9111:9001"                                           # 只暴露控制台；数据端口 9000 仅容器内用
    volumes:
      - ai_chief_miniodata:/minio_data                        # 向量数据文件持久化

  milvus:
    image: docker.m.daocloud.io/milvusdb/milvus:v2.4.17       # standalone 单机模式
    container_name: ai_chief_milvus
    restart: unless-stopped
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379                               # 去哪读元数据
      MINIO_ADDRESS: minio:9000                               # 去哪存数据文件
    ports:
      - "19530:19530"                                         # gRPC：应用检索用
      - "9191:9091"                                           # HTTP：健康检查/指标
    depends_on:
      - etcd
      - minio
    volumes:
      - ai_chief_milvusdata:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      timeout: 20s
      retries: 5
      start_period: 90s                                       # Milvus 启动慢，给足 90 秒再判健康
```

`volumes:` 顶级声明追加三个：

```yaml
volumes:
  ai_chief_pgdata:
  ai_chief_redisdata:
  ai_chief_neo4jdata:
  ai_chief_etcddata:      # v3阶段6 新增
  ai_chief_miniodata:     # v3阶段6 新增
  ai_chief_milvusdata:    # v3阶段6 新增
```

### 7.2 启动并验证

```bash
docker compose -f docker/docker-compose.v3.yml up -d etcd minio milvus
docker compose -f docker/docker-compose.v3.yml ps
```

**验证 1**：三个新容器状态 `Up`；milvus 的健康检查在 90 秒宽限期后变 `(healthy)`。

**验证 2**：健康接口：

```bash
curl http://127.0.0.1:9191/healthz
```

**验证**：返回 `OK`。

> 🔴 首次拉镜像约 1GB+（三个镜像合计），DaoCloud 源一般 2~5 分钟；拉不动看第十八节错误表。

---

## 八、子模块 2：依赖与配置（pymilvus + config + .env）

### 8.1 安装依赖

```bash
uv add "pymilvus==2.4.15"
```

（`uv add` 会同时写入 pyproject.toml 与 uv.lock；如果项目的依赖清单以 requirements.txt 为准，就再执行 `uv pip freeze | grep -i pymilvus >> requirements.txt` 手工核对追加的一行是 `pymilvus==2.4.15`。）

**验证**：

```bash
uv run python -c "import pymilvus; print(pymilvus.__version__)"
```

**验证**：输出 `2.4.15`。

### 8.2 修改 `app_my/core/config.py`

在 `NEO4J_PASSWORD` 那行后面追加：

```python
    # ============================================================
    # Milvus 向量库（v3阶段6 新增；默认值与 docker-compose 里的容器一致）
    # ============================================================
    MILVUS_URI: str = "http://localhost:19530"     # gRPC over HTTP 端口
    MILVUS_COLLECTION: str = "recipes_v2"          # 集合名（v2 区别于 PGVector 的 recipes）
```

### 8.3 `.env`（可选）

默认值已与容器一致，**不加也能跑**；要显式管理就加两行：

```bash
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=recipes_v2
```

---

## 九、子模块 3：Milvus 封装（knowledge/milvus_store.py）

新建 `app_my/knowledge/milvus_store.py`：

```python
# app_my/knowledge/milvus_store.py —— 阶段 6（v3.0）：Milvus 向量库封装
"""
检索专用向量数据库的访问层。

设计原则（与 core/kg.py 同一哲学）：
1. 增强不是依赖：Milvus 挂了/没装 pymilvus，所有函数返回空/False，
   检索自动回退 PGVector（v1 路径），主流程永远不断。
2. 查询收口：所有 Milvus API 调用收在本模块，业务代码不认识 pymilvus。

集合结构（recipes_v2）：
    recipe_id  VARCHAR(16)  主键——菜谱 ID（如 R001），重导 upsert 按它覆盖
    text       VARCHAR(8192) 原文——与 PGVector 存的同一份菜谱文本
    vector     FLOAT_VECTOR(1024)  embedding 模型输出的 1024 维向量
    metadata   JSON         元数据（菜名/标签/热量…，检索结果直接带出）
索引：HNSW + COSINE（为什么选它见说明手册）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app_my.core.config import settings
from app_my.core.logging import logger

DIMENSION = 1024          # 必须与 embedding 模型的 dimensions 一致，不一致建表就报错

_client = None            # MilvusClient 单例（惰性创建）
_client_failed = False    # 连接失败标记：失败一次本进程不再重试（和 kg 模块同款）


def get_client():
    """惰性创建 MilvusClient 单例；不可用返回 None（调用方走回退路径）"""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    try:
        from pymilvus import MilvusClient   # 函数内导入：没装 pymilvus 时 import 本模块不报错

        _client = MilvusClient(uri=settings.MILVUS_URI)
        logger.info(f"milvus: 已连接 {settings.MILVUS_URI}")
        return _client
    except Exception as exc:
        _client_failed = True
        logger.warning(f"milvus: 不可用（{type(exc).__name__}: {exc}），向量检索回退 PGVector")
        return None


def milvus_available() -> bool:
    """Milvus 当前是否可用（retriever 用它决定走向量库还是回退）"""
    return get_client() is not None


def ensure_collection() -> bool:
    """确保集合存在（不存在就按 schema+索引建一个）；幂等"""
    client = get_client()
    if client is None:
        return False
    name = settings.MILVUS_COLLECTION
    try:
        if client.has_collection(name):
            return True                      # 已存在：直接用（幂等）
        from pymilvus import DataType

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("recipe_id", DataType.VARCHAR, is_primary=True, max_length=16)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIMENSION)
        schema.add_field("metadata", DataType.JSON)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",              # 分层可导航小世界图：高精度、低延迟
            metric_type="COSINE",           # 余弦相似度（embedding 的标准度量）
            params={"M": 16, "efConstruction": 200},
        )
        client.create_collection(collection_name=name, schema=schema, index_params=index_params)
        logger.info(f"milvus: 已创建集合 {name}（dim={DIMENSION}, HNSW/COSINE）")
        return True
    except Exception as exc:
        logger.warning(f"milvus: 建集合失败: {exc}")
        return False


def upsert_recipes(rows: List[Dict[str, Any]]) -> int:
    """
    按 recipe_id 批量写入（存在即覆盖）。
    rows 每行：{"recipe_id", "text", "vector", "metadata"}
    返回成功写入条数；失败返回 0（导入脚本据此判定要不要终止）。
    """
    client = get_client()
    if client is None or not rows:
        return 0
    try:
        result = client.upsert(collection_name=settings.MILVUS_COLLECTION, data=rows)
        return result.get("upsert_count", len(rows)) if isinstance(result, dict) else len(rows)
    except Exception as exc:
        logger.warning(f"milvus: 写入失败: {exc}")
        return 0


def clear_collection() -> bool:
    """删掉整个集合（重导前的清场；下次 ensure_collection 会重建）"""
    client = get_client()
    if client is None:
        return False
    try:
        if client.has_collection(settings.MILVUS_COLLECTION):
            client.drop_collection(settings.MILVUS_COLLECTION)
            logger.info(f"milvus: 已删除集合 {settings.MILVUS_COLLECTION}（重导前清场）")
        return True
    except Exception as exc:
        logger.warning(f"milvus: 删除集合失败: {exc}")
        return False


def vector_search(query_vector: List[float], k: int = 10) -> List[Dict[str, Any]]:
    """
    向量近邻检索。
    返回 [{"recipe_id", "content", "metadata", "score"}]（score=余弦相似度，越大越相似）；
    不可用/出错返回空列表（触发上层回退）。
    """
    client = get_client()
    if client is None:
        return []
    try:
        results = client.search(
            collection_name=settings.MILVUS_COLLECTION,
            data=[query_vector],            # 批量查询传多个向量，这里一次查一个
            limit=k,                        # 每个查询向量取前 k 个近邻
            output_fields=["text", "metadata"],   # 命中时一并带回这两个字段
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        )
        hits: List[Dict[str, Any]] = []
        for hit in results[0]:              # results[0] = 第一个查询向量的命中列表
            entity = hit.get("entity", {}) or {}
            hits.append({
                "recipe_id": hit.get("id"),
                "content": entity.get("text", ""),
                "metadata": entity.get("metadata", {}) or {},
                "score": hit.get("distance"),   # COSINE 度量下 distance 即相似度
            })
        return hits
    except Exception as exc:
        logger.warning(f"milvus: 检索失败（回退 PGVector）: {exc}")
        return []


def collection_row_count() -> int:
    """集合内向量条数（验证导入是否成功用）"""
    client = get_client()
    if client is None:
        return 0
    try:
        stats = client.get_collection_stats(settings.MILVUS_COLLECTION)
        return int(stats.get("row_count", 0))
    except Exception:
        return 0
```

**验证**（连接 + 建空集合冒烟）：

```bash
uv run python -c "
from app_my.knowledge.milvus_store import ensure_collection, milvus_available, collection_row_count
print('Milvus 可用:', milvus_available())
print('建集合:', ensure_collection())
print('当前行数:', collection_row_count(), '（刚建好应为 0）')
"
```

**验证**：三个输出 `True / True / 0`。

---

## 十、子模块 4：导入脚本（import_recipes_milvus.py）

新建 `scripts/import_recipes_milvus.py`：

```python
# scripts/import_recipes_milvus.py
"""
阶段 6：把菜谱向量导入 Milvus（幂等：先删集合再重建再写入）。

用法（项目根目录执行）：
    uv run python scripts/import_recipes_milvus.py

流程：读 recipes.json → 清场 → 分批向量化（每批 10 条）→ upsert → 冒烟检索。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
from app_my.knowledge.embedding import embed_texts
from app_my.knowledge.milvus_store import (
    clear_collection, collection_row_count, ensure_collection, upsert_recipes, vector_search,
)

BATCH_SIZE = 10  # DashScope embedding 单次最多 10 条文本


def main() -> None:
    recipes = load_recipes()
    print(f"[1/5] 读取种子数据：{len(recipes)} 条菜谱")

    print("[2/5] 清场（删旧集合，幂等设计）")
    if not clear_collection():
        print("      清场失败：Milvus 不可用？先确认容器已启动")
        sys.exit(1)

    print("[3/5] 建集合（schema + HNSW 索引）")
    if not ensure_collection():
        sys.exit(1)

    print("[4/5] 分批向量化并写入（每批 10 条，调用 embedding 接口，请稍等）...")
    t0 = time.time()
    total = 0
    for i in range(0, len(recipes), BATCH_SIZE):
        batch = recipes[i : i + BATCH_SIZE]
        texts = [recipe_to_text(r) for r in batch]
        vectors = embed_texts(texts)              # 真实调用 DashScope，一次最多 10 条
        rows = [
            {
                "recipe_id": r["recipe_id"],      # 主键：重跑脚本 = 按 id 覆盖（幂等的另一重保险）
                "text": t,
                "vector": v,
                "metadata": recipe_to_metadata(r),
            }
            for r, t, v in zip(batch, texts, vectors)
        ]
        n = upsert_recipes(rows)
        total += n
        print(f"      已写入 {i + len(batch)}/{len(recipes)}（本批 {n} 条）")
    print(f"[5/5] 写入完成：{total} 条，耗时 {time.time() - t0:.1f} 秒")

    print(f"集合行数核对：{collection_row_count()}（应等于 {total}）")

    # 冒烟：一句真实查询跑一遍三件套（向量化 → Milvus 检索）
    from app_my.knowledge.embedding import embed_query
    hits = vector_search(embed_query("鸡胸肉 减脂"), k=3)
    print("冒烟检索 '鸡胸肉 减脂' 前 3 条 ->")
    for h in hits:
        print("  -", h["metadata"].get("name"), "| score:", round(h["score"], 4))

    # 数据变了：把两条检索路径的缓存一起失效（rag=v1 路径，rag2=v2 路径）
    from app_my.core.cache import invalidate_prefix
    invalidate_prefix("rag")
    invalidate_prefix("rag2")
    print("[缓存] rag / rag2 前缀已失效")


if __name__ == "__main__":
    main()
```

**操作与验证**：

```bash
uv run python scripts/import_recipes_milvus.py
```

**验证**：走完 5 步；`集合行数核对：60`；冒烟检索前 3 条都是鸡胸肉/减脂相关菜（R017 / R018 / R021 / R024 一类），score 是 0~1 的相似度。

---

## 十一、子模块 5：图谱检索信号（core/kg.py 新增两个函数）

在 `app_my/core/kg.py` 的 `kg_stats()` 函数**之前**（文件尾部区域）追加：

```python
# ============================================================
# 查询 3：文本 → 食材命中 → 菜谱（v3阶段6 混合检索的第三路）
# ============================================================

from functools import lru_cache


@lru_cache(maxsize=1)
def _ingredient_names() -> List[str]:
    """全图食材名列表（建一次进程内复用；重建图谱后重启后端生效）"""
    rows = _run("MATCH (i:Ingredient) RETURN i.name AS name")
    return [r["name"] for r in rows]


def reset_ingredient_cache() -> None:
    """重建图谱后调用：清掉食材名缓存，下次查询重新加载"""
    _ingredient_names.cache_clear()


def match_recipes_from_query(query: str, limit: int = 10) -> List[str]:
    """
    混合检索的第三路（图谱信号）：查询文本 → 命中的食材 → 两跳到菜谱。

    与向量/BM25 的本质区别：图谱返回的是"图上有边的事实"——
    查询里有"西兰花"，返回的菜谱一定真含西兰花（IN_RECIPE 边存在），
    不靠相似度猜测，没有幻觉。

    返回按"命中食材数"降序的 recipe_id 列表；图谱不可用/没命中返回空列表
    （上层会把它当成"这一路缺席"，权重自动重分配）。
    """
    names = _ingredient_names()
    if not names:
        return []
    # 子串匹配：查询"香煎鸡胸肉配西兰花"能命中食材"鸡胸肉"（分词不必精确）
    matched = [n for n in names if n and n in query]
    if not matched:
        return []
    rows = _run(
        """
        MATCH (i:Ingredient)-[:IN_RECIPE]->(rc:Recipe)
        WHERE i.name IN $names
        RETURN rc.recipe_id AS rid, count(DISTINCT i) AS hits
        ORDER BY hits DESC
        LIMIT $limit
        """,
        names=matched,
        limit=limit,
    )
    logger.info(f"kg: 查询命中食材 {matched} -> 图谱路返回 {len(rows)} 道菜")
    return [r["rid"] for r in rows]
```

> 🟡 `from functools import lru_cache` 放在函数区中间不优雅但**零风险**（Python 允许任意位置 import）；想整洁也可以挪到文件头部 import 区。

**验证**：

```bash
uv run python -c "
from app_my.core.kg import match_recipes_from_query
print(match_recipes_from_query('鸡胸肉 西兰花 减脂'))
print(match_recipes_from_query('土豆'))
print(match_recipes_from_query('今天天气怎么样'))
"
```

**验证**：第一行含 R017（香煎鸡胸肉配西兰花）等 id；第二行含 R010/R011（地三鲜/酸辣土豆丝）；第三行 `[]`（没有食材命中——图谱路缺席，这正是降级设计要的情形）。

---

## 十二、子模块 6：三路混合检索（retriever.py 升级 hybrid_search_v2）

在 `app_my/knowledge/retriever.py` **文件末尾追加**（v1 的 `hybrid_search` 原样保留，灰度开关切换）：

```python
# ============================================================
# v3 阶段 6：三路混合检索 v2（向量 50% + BM25 30% + 图谱 20%）
# ============================================================

from app_my.core import kg as kg_module
from app_my.core.cache import cached as _cached_dec      # 别名避免与 v1 的 import 重复
from app_my.knowledge.embedding import embed_query
from app_my.knowledge.milvus_store import vector_search as _milvus_search
from app_my.knowledge.data_loader import load_recipes as _load_recipes_for_index

# 三路默认权重（和=1）；单路缺席时按剩余比例重分配
HYBRID_V2_WEIGHTS = {"vector": 0.5, "bm25": 0.3, "kg": 0.2}
RRF_K = 60         # RRF 平滑常数：rank r 的得分 = weight/(60+r)，头部差距被适度压平


@lru_cache(maxsize=1)
def _recipe_index_v2() -> Dict[str, dict]:
    """recipe_id -> 原始菜谱（第三路可能召回前两路没有的菜，用它补全信息）"""
    return {r["recipe_id"]: r for r in _load_recipes_for_index()}


def _vector_path(query: str, n: int) -> List[str]:
    """第一路：Milvus 向量检索（不可用自动回退 PGVector），返回 recipe_id 排名列表"""
    hits = _milvus_search(embed_query(query), k=n)
    if hits:                                              # Milvus 正常返回
        return [h["recipe_id"] for h in hits]
    # 回退：PGVector 走 v1 的两路函数拿向量结果（日志会提示 milvus 降级）
    store = get_vector_store()
    if hasattr(store, "as_retriever"):
        vh = store.as_retriever(search_kwargs={"k": n}).invoke(query)
    else:
        vh = store.similarity_search(query, k=n)
    return [h.metadata.get("recipe_id") for h in vh if h.metadata.get("recipe_id")]


def _bm25_path(query: str, n: int) -> List[str]:
    """第二路：BM25 关键词检索（阶段 5 已把索引缓存进进程），返回 recipe_id 排名列表"""
    hits = _build_bm25(n).invoke(query)
    return [h.metadata.get("recipe_id") for h in hits if h.metadata.get("recipe_id")]


def _kg_path(query: str, n: int) -> List[str]:
    """第三路：图谱结构化命中（不可用/无命中返回空 -> 上层重分配权重）"""
    return kg_module.match_recipes_from_query(query, limit=n)


def _fuse(rankings: Dict[str, List[str]], weights: Dict[str, float]) -> List[tuple]:
    """
    三路排名加权融合（RRF 变体）：
        score(doc) = Σ 路径权重 / (RRF_K + 该路径内的名次)
    任何一路为空 = 缺席：把它的权重按比例分给剩余两路（0.5:0.3 -> 0.625:0.375）。
    """
    active = {p: ids for p, ids in rankings.items() if ids}
    if not active:
        return []
    if len(active) < len(weights):                        # 有路缺席：权重重分配
        total = sum(weights[p] for p in active)
        weights = {p: (weights[p] / total) if total else 0 for p in weights}
    scores: Dict[str, float] = {}
    for path, ids in active.items():
        for rank, rid in enumerate(ids):
            scores[rid] = scores.get(rid, 0.0) + weights[path] / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


@_cached_dec(prefix="rag2", ttl=300, null_ttl=30)        # v3阶段6：v2 路径独立缓存前缀
def hybrid_search_v2(query: str, k: int = 5,
                     weights: Dict[str, float] = None) -> List[Dict]:
    """
    三路混合检索 v2：向量 50% + BM25 30% + 图谱 20%。

    与 v1（hybrid_search）的三点不同：
    1. 三路而非两路——图谱路是"事实命中"不是"相似度猜测"；
    2. 融合键是 recipe_id 而非文本——三路的输出天然对齐（文本做键会被空格/标点差异坑）；
    3. 权重重分配——Milvus/Neo4j 任何一个挂了，剩下的路按原比例接管，检索不停摆。
    """
    w = weights or HYBRID_V2_WEIGHTS
    n = k * 2                                             # 每路先取 2k 个候选再融合

    rankings = {
        "vector": _vector_path(query, n),
        "bm25": _bm25_path(query, n),
        "kg": _kg_path(query, n),
    }
    logger.info(f"hybrid_v2: 三路命中 vector={len(rankings['vector'])} "
                f"bm25={len(rankings['bm25'])} kg={len(rankings['kg'])}")

    fused = _fuse(rankings, dict(w))[:k]

    # recipe_id -> (content, metadata)：优先用向量/BM25 命中带的元数据，没有就查菜谱索引
    meta_pool: Dict[str, Dict] = {}
    for rid, _ in fused:
        base = _recipe_index_v2().get(rid)
        if base:
            meta_pool[rid] = {"content": recipe_to_text(base), "metadata": recipe_to_metadata(base)}

    return [
        {"recipe_id": rid, "content": meta_pool[rid]["content"],
         "metadata": meta_pool[rid]["metadata"], "score": round(score, 4)}
        for rid, score in fused if rid in meta_pool
    ]
```

> 🟡 文件顶部已有的 import（`lru_cache`、`cached`、`Dict/List` 等）都不用动——新增代码用的 `cached` 起了别名 `_cached_dec`、`load_recipes` 起了别名，是为了**避免和文件上半部 v1 代码的 import 冲突**；你直接照抄追加即可。
> 🟡 注意 v2 返回结构多了 `recipe_id` 字段、`content` 来自原始菜谱文本——`recipe_rag_tool` 的补全逻辑对两种结构都兼容（下一节）。

**验证**：

```bash
uv run python -c "
from app_my.knowledge.retriever import hybrid_search_v2
for h in hybrid_search_v2('鸡胸肉 西兰花 减脂', k=3):
    print(h['recipe_id'], h['metadata'].get('name'), '| score:', h['score'])
"
```

**验证**：返回 3 条，R017（香煎鸡胸肉配西兰花）应排最前（三路全命中：向量相似 + BM25 关键词 + 图谱结构命中）。

---

## 十三、子模块 7：灰度接线（recipe_rag_tool.py + Feature Flag）

### 13.1 修改 `app_my/tools/recipe_rag_tool.py`

**改动一**：文件顶部的 import 区，在 `from app_my.knowledge.retriever import hybrid_search` 下面加一行：

```python
from app_my.knowledge.retriever import hybrid_search_v2   # v3阶段6：三路混合检索
```

**改动二**：`local_recipe_search` 函数**整体替换**为：

```python
def _hybrid_v2_enabled() -> bool:
    """读 Feature Flag（阶段 4 落地）；flag 不存在/异常 = 关（走 v1，稳定优先）"""
    try:
        from app_my.core.feature_flag import is_feature_enabled
        return bool(is_feature_enabled("hybrid_v2"))
    except Exception:
        return False


def local_recipe_search(query: str, k: int = 5) -> List[dict]:
    """
    检索主逻辑（纯函数，方便单测；工具函数 search_local_recipes 只是它的壳）

    流程：
        （Feature Flag 选择 v1 / v2 检索路径）
        hybrid_search / hybrid_search_v2
        → 逐条按 recipe_id 补全 → normalize_recipe 统一结构
    """
    if _hybrid_v2_enabled():
        hits = hybrid_search_v2(query, k=k)     # v3阶段6：三路（向量50+BM25 30+图谱20）
    else:
        hits = hybrid_search(query, k=k)        # v1：两路（向量+BM25）
    index = _recipe_index()
    results: List[dict] = []
    for hit in hits:
        meta = hit.get("metadata", {}) or {}
        rid = meta.get("recipe_id") or hit.get("recipe_id")   # v2 的结构把 recipe_id 放在顶层
        base = index.get(rid) if rid else None
        merged = {**meta, **(base or {})}
        results.append(normalize_recipe(merged, score=hit.get("score")))
    logger.info(f"recipe_rag_tool: query='{query}' 命中 {len(results)} 条 "
                f"（路径={'v2三路' if _hybrid_v2_enabled() else 'v1两路'}）")
    return results
```

### 13.2 打开灰度开关（用阶段 4 的管理接口）

```bash
# 登录拿 admin token 后（owner/admin 角色才行）：
curl -s -X POST http://127.0.0.1:9002/admin/feature-flags \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "hybrid_v2", "enabled": true, "rollout_percent": 100}'
```

> 🟡 flag 接口的字段名以阶段 4 操作手册 14 节的 `/admin/feature-flags` 定义为准；`rollout_percent` 从 5 → 50 → 100 的过程就是真实的灰度发布节奏。
> 🟡 flag 有 60 秒内存缓存（阶段 4 的设计）——改完最多等一分钟生效；后端日志出现 `路径=v2三路` 就是切换成功。

**验证**（重启后端后，登录态下发一条消息，看后端日志）：

```bash
# 后端日志应出现：
# recipe_rag_tool: query='...' 命中 5 条（路径=v2三路）
# hybrid_v2: 三路命中 vector=10 bm25=10 kg=2
```

**验证降级链路**（可选但强烈建议，这是面试的亮点素材）：

```bash
docker compose -f docker/docker-compose.v3.yml stop milvus
# 等一分钟（flag/连接缓存过期），再发一条消息
# 日志应出现：milvus: 不可用（...），向量检索回退 PGVector —— 且消息正常返回
docker compose -f docker/docker-compose.v3.yml start milvus
```

---

## 十四、子模块 8：效果对比实验（retrieval_compare.py）

新建 `scripts/retrieval_compare.py`：

```python
# scripts/retrieval_compare.py
"""
阶段 6：v1（两路）vs v2（三路）检索效果对比实验——简历数字的唯一来源。

测什么：同一批真实查询，两版检索的 MRR@5 与 Hit@5。
    MRR@5  平均倒数排名：第一条相关结果排第 1 名得 1 分、第 2 名得 0.5 分……
           越接近 1 表示"最想要的菜排得越靠前"
    Hit@5  前 5 条里至少出现一条相关菜的比例（0~1）

测试集：10 组查询，每组标注"哪些菜谱算相关"（依据食材/标签人工标注）。
公平性：两版走同一进程、同一 embedding、同一数据；缓存先失效。

用法（项目根目录，Milvus/Neo4j 容器已启动）：
    uv run python scripts/retrieval_compare.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 测试集：query -> 相关菜谱 id 集合（依据 recipes.json 的食材与标签人工标注）
TEST_SET = [
    ("减脂餐 鸡胸肉", ["R017", "R018", "R024", "R021"]),
    ("西兰花 虾仁 低卡", ["R023", "R017"]),
    ("豆腐 汤羹 减脂", ["R026", "R032", "R031"]),
    ("快手 早餐", ["R043", "R025", "R042", "R037"]),
    ("川菜 麻辣 下饭", ["R003", "R004", "R005", "R058"]),
    ("孩子爱吃 酸甜", ["R007", "R008", "R022"]),
    ("高蛋白 清淡 宴客", ["R019", "R059", "R020", "R055"]),
    ("土豆 素菜 快手", ["R011", "R010"]),
    ("汤羹 滋补 秋冬", ["R034", "R029", "R032"]),
    ("低卡 素菜 凉菜", ["R044", "R045", "R012"]),
]


def mrr_at_k(result_ids, relevant, k=5):
    """平均倒数排名（单查询）：前 k 里第一条相关的名次 r -> 1/r；没有相关 -> 0"""
    for rank, rid in enumerate(result_ids[:k], start=1):
        if rid in relevant:
            return 1.0 / rank
    return 0.0


def hit_at_k(result_ids, relevant, k=5):
    """前 k 里出现至少一条相关菜 -> 1，否则 0"""
    return 1.0 if any(rid in relevant for rid in result_ids[:k]) else 0.0


def evaluate(search_fn, label):
    """对整个测试集跑一遍 search_fn，输出两指标"""
    from app_my.core.cache import invalidate_prefix
    invalidate_prefix("rag")
    invalidate_prefix("rag2")
    mrr_total, hit_total = 0.0, 0.0
    rows = []
    for query, relevant in TEST_SET:
        hits = search_fn(query, k=5)
        ids = [h.get("recipe_id") or h.get("metadata", {}).get("recipe_id") for h in hits]
        mrr_total += mrr_at_k(ids, relevant)
        hit_total += hit_at_k(ids, relevant)
        rows.append((query, ids[:3], round(mrr_at_k(ids, relevant), 3)))
    n = len(TEST_SET)
    print(f"\n===== {label} =====")
    for q, top3, m in rows:
        print(f"  {q:<14} top3={top3}  单查询MRR={m}")
    print(f"  >> MRR@5 = {mrr_total / n:.3f}    Hit@5 = {hit_total / n:.3f}")
    return mrr_total / n, hit_total / n


def main():
    from app_my.knowledge.retriever import hybrid_search, hybrid_search_v2

    print("=" * 62)
    print("阶段 6 检索效果对比实验（v1 两路 vs v2 三路）")
    print("=" * 62)

    mrr1, hit1 = evaluate(hybrid_search, "v1（PGVector 向量 + BM25，两路）")
    mrr2, hit2 = evaluate(hybrid_search_v2, "v2（Milvus 向量 + BM25 + 图谱，三路）")

    print("\n" + "=" * 62)
    print(f"MRR@5:  v1={mrr1:.3f}  v2={mrr2:.3f}  变化={mrr2 - mrr1:+.3f}"
          f"（{(mrr2 - mrr1) / mrr1 * 100:+.1f}%）" if mrr1 else "")
    print(f"Hit@5:  v1={hit1:.3f}  v2={hit2:.3f}  变化={hit2 - hit1:+.3f}"
          f"（{(hit2 - hit1) / hit1 * 100:+.1f}%）" if hit1 else "")
    print("（把这两行数字记下来，收官文档和简历叙事要用；照抄实测值，不要改）")


if __name__ == "__main__":
    main()
```

**操作与验证**：

```bash
uv run python scripts/retrieval_compare.py
```

**验证**：输出两张明细表 + 最终对比行。🟡 v1 与 v2 的具体数字以你机器实测为准；如果 v2 某些查询反而变差，把该查询和两版 top3 记下来——这是**真实的实验观察**，收官文档里"哪些场景三路更优、哪些场景权重该调"的分析比一味"全面变好"更有说服力。

---

## 十五、子模块 9：单元测试（8 个新测试）

新建 `tests/unit/test_hybrid_v2.py`：

```python
# tests/unit/test_hybrid_v2.py —— 阶段 6：三路融合与图谱匹配单测（不依赖 Milvus/Neo4j）
"""
覆盖点：
- _fuse：三路全命中 / 单路缺席权重重分配 / 双路缺席 / 全空
- _fuse：RRF 分数单调（排名越前贡献越大）
- match_recipes_from_query：子串命中 / 无命中返回空 / 图谱不可用返回空
- HYBRID_V2_WEIGHTS：三路权重和为 1
"""
from unittest.mock import patch

import pytest

from app_my.core import kg as kg_module
from app_my.knowledge.retriever import HYBRID_V2_WEIGHTS, _fuse


W = {"vector": 0.5, "bm25": 0.3, "kg": 0.2}


def test_fuse_three_paths():
    r = _fuse({"vector": ["r1", "r2"], "bm25": ["r2", "r4"], "kg": ["r1"]}, dict(W))
    ids = [i for i, _ in r]
    assert set(ids) == {"r1", "r2", "r4"}
    assert ids[0] in ("r1", "r2")          # 双命中的两道菜霸占前二


def test_fuse_kg_missing_redistributes():
    # kg 缺席：0.5:0.3 -> 0.625:0.375，向量权重仍高于 BM25
    r = _fuse({"vector": ["a"], "bm25": ["b"]}, dict(W))
    assert r[0][0] == "a"
    scores = dict(r)
    assert scores["a"] > scores["b"]


def test_fuse_single_path():
    r = _fuse({"vector": ["x", "y"]}, dict(W))
    assert [i for i, _ in r] == ["x", "y"]  # 单路兜底按原顺序


def test_fuse_all_empty():
    assert _fuse({"vector": [], "bm25": [], "kg": []}, dict(W)) == []


def test_fuse_rank_monotonic():
    r = _fuse({"vector": ["a", "b", "c"]}, dict(W))
    scores = [s for _, s in r]
    assert scores == sorted(scores, reverse=True)


def test_weights_sum_to_one():
    assert abs(sum(HYBRID_V2_WEIGHTS.values()) - 1.0) < 1e-9


def test_kg_match_substring(monkeypatch):
    monkeypatch.setattr(kg_module, "_ingredient_names", lambda: ["鸡胸肉", "西兰花", "豆腐"])
    fake_rows = [{"rid": "R017", "hits": 2}, {"rid": "R018", "hits": 1}]
    monkeypatch.setattr(kg_module, "_run", lambda cypher, **kw: fake_rows)
    assert kg_module.match_recipes_from_query("香煎鸡胸肉配西兰花") == ["R017", "R018"]


def test_kg_match_no_hit(monkeypatch):
    monkeypatch.setattr(kg_module, "_ingredient_names", lambda: ["鸡胸肉"])
    assert kg_module.match_recipes_from_query("今天天气怎么样") == []
```

> 🟡 `_run` 的 mock 用 `lambda cypher, **kw: fake_rows`：`match_recipes_from_query` 内部调 `_run(cypher, names=..., limit=...)`，关键字参数用 `**kw` 接住即可。

**验证**：

```bash
uv run pytest -q
```

**验证**：`83 passed`（75 基线 + 8 新增）。

---

## 十六、子模块 10：验证脚本与提测

### 16.1 新建 `scripts/verify_stage6.py`（🔵 覆盖 v2.0 遗留同名脚本）

```python
# scripts/verify_stage6.py
"""
v3 阶段 6 分步验证脚本（Milvus + 三路混合检索）。
（本文件覆盖了 v2.0 时代的同名脚本——内容是 trace 验证，git 历史里可找回。）

用法（项目根目录执行）：
    uv run python scripts/verify_stage6.py <子命令>

子命令：
    deps     容器状态（milvus/etcd/minio + 老三样）
    conn     pymilvus 连接 + 集合存在 + 行数
    search   一句真实查询跑 Milvus 向量检索
    kg       图谱路：食材命中 -> 菜谱
    hybrid   hybrid_search_v2 三路融合出结果
    flag     hybrid_v2 flag 状态
    all      以上全部（提测用）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list = []


def report(name, ok, detail=""):
    print(("[OK]  " if ok else "[FAIL]") + f" {name}" + (f"  ->  {detail}" if detail else ""))
    RESULTS.append(ok)
    return ok


def check_deps():
    import subprocess
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                         capture_output=True, text=True).stdout.splitlines()
    for c in ("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer",
              "ai_chief_neo4j", "ai_chief_etcd", "ai_chief_minio", "ai_chief_milvus"):
        report(f"容器 {c} 运行中", c in out, "" if c in out else "docker compose -f docker/docker-compose.v3.yml up -d")


def check_conn():
    try:
        from app_my.knowledge.milvus_store import (
            collection_row_count, ensure_collection, milvus_available,
        )
        if not report("Milvus 可连接", milvus_available()):
            return
        ensure_collection()
        n = collection_row_count()
        report("集合 recipes_v2 有数据", n > 0, f"行数 {n}（0 = 先跑 import_recipes_milvus.py）")
    except Exception as e:
        report("Milvus 连接检查失败", False, f"{type(e).__name__}: {e}")


def check_search():
    try:
        from app_my.knowledge.embedding import embed_query
        from app_my.knowledge.milvus_store import vector_search
        hits = vector_search(embed_query("鸡胸肉 减脂"), k=3)
        report("Milvus 向量检索返回结果", len(hits) > 0,
               "; ".join(h["metadata"].get("name", "?") for h in hits[:3]))
    except Exception as e:
        report("Milvus 检索失败", False, f"{type(e).__name__}: {e}")


def check_kg():
    try:
        from app_my.core.kg import match_recipes_from_query
        ids = match_recipes_from_query("鸡胸肉 西兰花")
        report("图谱路命中菜谱", len(ids) > 0, str(ids[:5]))
        empty = match_recipes_from_query("完全无关的查询词组")
        report("无关查询返回空（缺席即降级）", empty == [])
    except Exception as e:
        report("图谱路检查失败", False, f"{type(e).__name__}: {e}")


def check_hybrid():
    try:
        from app_my.knowledge.retriever import hybrid_search_v2
        hits = hybrid_search_v2("鸡胸肉 西兰花 减脂", k=3)
        ok = len(hits) > 0 and all("recipe_id" in h for h in hits)
        report("三路混合检索出结果", ok,
               "; ".join(f"{h['recipe_id']}({h['metadata'].get('name')})" for h in hits))
    except Exception as e:
        report("混合检索失败", False, f"{type(e).__name__}: {e}")


def check_flag():
    try:
        from app_my.core.feature_flag import is_feature_enabled
        v = is_feature_enabled("hybrid_v2")
        report("hybrid_v2 flag 可读取", True, f"当前={'开（v2三路）' if v else '关（v1两路）'}")
    except Exception as e:
        report("feature_flag 模块不可用", False, f"{type(e).__name__}: {e}（阶段 4 做完了吗？）")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    checks = {"deps": check_deps, "conn": check_conn, "search": check_search,
              "kg": check_kg, "hybrid": check_hybrid, "flag": check_flag}
    if cmd == "all":
        for fn in checks.values():
            fn()
    else:
        checks[cmd]()
    print()
    print(f"结果：{sum(RESULTS)} 通过 / {len(RESULTS) - sum(RESULTS)} 失败")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
```

### 16.2 提测脚本 `scripts/stage6_check.sh`（Git Bash）

```bash
#!/bin/bash
# v3 阶段 6 提测脚本（Git Bash 用）
# 前置：① 全部容器已启动（含 milvus 全家桶）  ② main.py 已启动（9002）  ③ Milvus 已导入数据
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"

echo "=== 阶段 6 提测开始 ==="

echo "--- 1/4 单元测试 ---"
"$PY" -m pytest -q
RC=$?
if [ $RC -ne 0 ]; then echo "[FAIL] 单测未全绿"; exit $RC; fi

echo "--- 2/4 容器状态 ---"
for c in ai_chief_pgvector ai_chief_redis ai_chief_pgbouncer ai_chief_neo4j ai_chief_etcd ai_chief_minio ai_chief_milvus; do
  if docker ps --format '{{.Names}}' | grep -q "^$c$"; then
    echo "[OK]   容器 $c 运行中"
  else
    echo "[FAIL] 容器 $c 未运行：docker compose -f docker/docker-compose.v3.yml up -d"
    exit 1
  fi
done

echo "--- 3/4 全量验证 ---"
"$PY" scripts/verify_stage6.py deps
"$PY" scripts/verify_stage6.py conn
"$PY" scripts/verify_stage6.py search
"$PY" scripts/verify_stage6.py kg
"$PY" scripts/verify_stage6.py hybrid
"$PY" scripts/verify_stage6.py flag

echo "--- 4/4 对比实验 ---"
"$PY" scripts/retrieval_compare.py

echo ""
echo "阶段 6 提测全部通过（对比数字已输出，记进收官文档）"
```

### 16.3 提测脚本 `scripts/stage6_check.ps1`（PowerShell 5.1，UTF-8 BOM 保存）

```powershell
# v3 阶段 6 提测脚本（PowerShell 5.1 用，UTF-8 BOM）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\stage6_check.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$Py = ".venv\Scripts\python.exe"

Write-Host "=== 阶段 6 提测开始 ===" -ForegroundColor Cyan

Write-Host "--- 1/4 单元测试 ---"
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 单测未全绿" -ForegroundColor Red; exit 1 }

Write-Host "--- 2/4 容器状态 ---"
foreach ($c in @("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer",
                 "ai_chief_neo4j", "ai_chief_etcd", "ai_chief_minio", "ai_chief_milvus")) {
    $running = docker ps --format '{{.Names}}' | Select-String -SimpleMatch $c
    if ($running) {
        Write-Host "[OK]   容器 $c 运行中" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] 容器 $c 未运行" -ForegroundColor Red
        exit 1
    }
}

Write-Host "--- 3/4 全量验证 ---"
& $Py scripts\verify_stage6.py deps
& $Py scripts\verify_stage6.py conn
& $Py scripts\verify_stage6.py search
& $Py scripts\verify_stage6.py kg
& $Py scripts\verify_stage6.py hybrid
& $Py scripts\verify_stage6.py flag

Write-Host "--- 4/4 对比实验 ---"
& $Py scripts\retrieval_compare.py

Write-Host ""
Write-Host "阶段 6 提测全部通过" -ForegroundColor Green
```

**验证**：`bash scripts/stage6_check.sh` 末行输出通过；对比实验的两行指标数字记录下来。

---

## 十七、提交 Gitee 与 PR 描述

**操作 1：提交**

```bash
git add docker/docker-compose.v3.yml app_my/knowledge/milvus_store.py \
        app_my/knowledge/retriever.py app_my/core/config.py app_my/core/kg.py \
        app_my/tools/recipe_rag_tool.py scripts/import_recipes_milvus.py \
        scripts/retrieval_compare.py scripts/verify_stage6.py \
        scripts/stage6_check.ps1 scripts/stage6_check.sh \
        tests/unit/test_hybrid_v2.py requirements.txt pyproject.toml uv.lock

git commit -m "feat(v3-stage6): Milvus向量库+三路混合检索v2——向量50/BM25 30/图谱20加权RRF融合+单路故障权重重分配+FeatureFlag灰度"
git push -u origin feat/v3-stage6
```

**操作 2：Gitee 建 PR**（`feat/v3-stage6` → `master`）。

**操作 3：PR 描述（直接复制）**

```markdown
## 阶段 6：Milvus 向量库 + 三路混合检索 v2

### 改了什么

#### 基础设施
- 新增 Milvus standalone 三容器（milvus + etcd 元数据 + minio 对象存储）
  - 端口：19530（gRPC）/ 9191（健康）/ 9111（MinIO 控制台，可选）
  - HNSW 索引（M=16, efConstruction=200）+ COSINE 度量，1024 维
- 新增依赖 pymilvus==2.4.15

#### 检索升级（retriever.hybrid_search_v2）
- 三路信号：Milvus 向量（50%）+ BM25（30%）+ 知识图谱结构化命中（20%）
- 融合算法：RRF 变体 score=Σ w/(60+rank)，融合键为 recipe_id
- 单路故障自动降级：Milvus 挂 -> 回退 PGVector；Neo4j 挂 -> 权重按比例
  重分配（0.5:0.3 -> 0.625:0.375）；检索链路永远不断
- 图谱路（kg.match_recipes_from_query）：查询文本子串命中食材 ->
  IN_RECIPE 两跳 -> 按命中食材数排序（结构化事实命中，非相似度猜测）

#### 灰度发布
- 复用阶段 4 Feature Flag：hybrid_v2 开=v2 三路，关=v1 两路（PGVector）
- 60s 缓存内自动生效，出问题秒级回滚

#### 效果实验（scripts/retrieval_compare.py，10 组真实查询）
- MRR@5：v1=___ v2=___（变化 ___%）
- Hit@5：v1=___ v2=___（变化 ___%）
- 数字为本机实测；个别查询 v2 变差的分析见收官文档

#### 测试
- 新增 8 个单测（融合数学 + 权重重分配 + 图谱路匹配），75 -> 83 passed
- verify_stage6.py 覆盖 v2.0 遗留同名脚本（trace 验证，git 历史可找回）

#### 不在本 PR 的内容
- Milvus 集群/分布式模式（个人项目无此规模需求，简历不写假规模）
- 重排序模型（cross-encoder）——留作可选优化
- embedding 模型更换（不动向量的来源，只动存储与检索）
```

---

## 十八、常见错误对照表

| 现象 | 大概率原因 | 修法 |
|---|---|---|
| `milvus` 容器健康检查一直 `starting` / `unhealthy` | 启动慢（90 秒宽限期内没就绪）或内存不足 | 再等 1~2 分钟；`docker logs ai_chief_milvus --tail 50` 看报错；`docker stats` 看内存——不够就先停掉 v2.0 的旧容器腾内存 |
| 拉镜像 `manifest unknown` / 超时 | DaoCloud 没同步该 tag / 网络抖动 | 重试一次；etcd 换 `docker.m.daocloud.io/quay.io/coreos/etcd:v3.5.16`；minio 换更新的 RELEASE tag；还不行换 `docker.1ms.run` 等其它国内源 |
| pymilvus 连接报 `Connection refused` | milvus 容器没起 / 端口没映射 | `docker ps` + `docker port ai_chief_milvus` 应有 `19530/tcp -> 0.0.0.0:19530` |
| `ensure_collection` 报 `dimension mismatch` | DIMENSION 与 embedding 实际维度不一致 | 核对 embedding.py 的 `dimensions=1024`；改了维度要删集合重导 |
| 导入脚本每批都报错 `upsert failed` | metadata 里有 Milvus 不认的类型 | metadata 已由 recipe_to_metadata 转成纯 JSON 类型（tags 转逗号串）；若自己改过 schema 检查类型 |
| 检索返回 `[]` 且日志有 `milvus: 不可用` | 容器停了 / pymilvus 没装 | 这是**设计内降级**：回退 PGVector 照常检索；想恢复就 start 容器 |
| `hybrid_search_v2` 报 `ImportError: No module named 'app_my.knowledge.milvus_store'` | 文件没建 / 建错目录 | 确认在 `app_my/knowledge/` 下，文件名一字不差 |
| flag 打开后日志还是 `路径=v1两路` | flag 的 60 秒内存缓存没过期 | 等一分钟再试；或重启后端；或看阶段 4 flag 的缓存设计说明 |
| `_hybrid_v2_enabled` 抛异常静默回 v1 | 阶段 4 feature_flag 模块没落盘 | 🔴 先完成阶段 4；本阶段的灰度依赖它 |
| retrieval_compare 里 v1 的 `metadata` 取不到 recipe_id | v1 返回结构本来就带 `metadata.recipe_id` | 脚本已兼容两种结构（`h.get("recipe_id") or h.get("metadata",{}).get("recipe_id")`）；报 None 检查 PGVector 里导入的数据是否完整（重跑 import_recipes.py） |
| pytest `test_kg_match_substring` 失败 | `_ingredient_names` 的 lru_cache 有旧值 | 测试用 monkeypatch 替换整个函数，不受缓存影响；失败先看替身签名是否一致（无参 lambda） |
| 内存吃紧、电脑卡 | Milvus 全家 + Neo4j + PG + Redis 同时跑 | `docker compose -f docker/docker-compose.v3.yml stop milvus etcd minio`（数据卷保留，检索自动回退） |

---

## 十九、避坑提示

🟡 **Milvus 三容器是"全家桶"不是"三个独立选择"**：standalone 模式里 etcd 存元数据（有哪些集合/索引）、minio 存向量数据文件（段文件）。少任何一个 milvus 都起不来。`depends_on` 只保证启动顺序，不保证健康——milvus 的 healthcheck `start_period: 90s` 就是为此。

🟡 **DIMENSION 必须和 embedding 模型对齐**：`embedding.py` 里 `dimensions=1024`，`milvus_store.py` 的 `DIMENSION = 1024`——将来换 embedding 模型要**两处一起改**，且改完必须删集合重导（旧向量维度对不上）。

🟡 **融合键用 recipe_id 不用文本**：v1 用 `page_content` 文本做融合键，两路的文本只要有空格差异就对不上号。v2 三路的输出天然都有 recipe_id——用 id 做键是结构对齐，不是字符串碰运气。

🟡 **RRF_K=60 是经验值不是玄学**：分母越大，"第 1 名和第 2 名"的得分差距越小（1/61 vs 1/62），多路命中越容易反超单路冠军——这正好符合"三路都说好 > 一路说极好"的直觉。业界标准实现（Elasticsearch 的 RRF）也用 60。

🟡 **权重 50/30/20 是起点不是真理**：本阶段拍的默认值，压测和实验后可调（改 `HYBRID_V2_WEIGHTS` 一处即可）。改动要拿对比实验数据说话——"调权重前后的 MRR 变化"本身就是收官文档的好素材。

🟡 **图谱路的子串匹配足够用**：`n in query` 让"香煎鸡胸肉配西兰花"命中"鸡胸肉"。不用上分词器——图谱路要的是**精确命中**不是模糊匹配，模糊是向量路的工作。

🔴 **不要把 PGVector 的导入和表删了**：它是回退路径的底座。Milvus 与 PGVector 双份数据是"高可用"的代价，60 条菜谱 double 一份毫无压力。

🔴 **不要在生产代码里 hardcode `hybrid_v2` 的开关状态**：必须走 Feature Flag——硬编码的切换要改代码重启，flag 的切换是一分钟内生效的运维动作，这正是阶段 4 建旗子的意义。

🔴 **别用 Milvus 的 FLAT 索引"省事"**：FLAT 是暴力扫描，60 条无所谓、6000 条就是全表扫。HNSW 的建索引成本一次性付出，检索延迟数量级地低——简历上"HNSW"是真实调过参的词（M/efConstruction/ef 三个参数见说明手册）。

---

## 二十、本阶段防呆自检清单

- [ ] 阶段 5 已合并，基线 75 passed（第六节）
- [ ] 七个容器全部运行（pgvector/redis/pgbouncer/neo4j/etcd/minio/milvus）
- [ ] `curl http://127.0.0.1:9191/healthz` 返回 OK
- [ ] `import_recipes_milvus.py` 跑完，集合行数 = 60，冒烟检索有结果
- [ ] `match_recipes_from_query('鸡胸肉')` 返回非空、无关查询返回空
- [ ] `hybrid_search_v2('鸡胸肉 西兰花 减脂')` R017 排最前
- [ ] `hybrid_v2` flag 打开后，后端日志出现 `路径=v2三路`
- [ ] 停 milvus 容器 → 检索依然工作（回退日志出现）→ 重启恢复
- [ ] `retrieval_compare.py` 两行对比数字已记录
- [ ] pytest 83 passed
- [ ] 提交信息格式 `feat(v3-stage6): ...`，PR 已建

---

> **下一步**：全部打勾后告诉 AI"阶段 6 完成"，等待交付《阶段 6 最终完整版》+《阶段 6 问题与解决记录》两份收官文件；之后按总纲进入阶段 7（Prometheus + Grafana 全栈监控）。
>
> 🟡 阶段 4 / 5 / 6 三份收官文件（含问题记录）请在你完成对应阶段操作后逐个领取——AI 在你执行期间记录的问题越完整，收官文档越有价值。
