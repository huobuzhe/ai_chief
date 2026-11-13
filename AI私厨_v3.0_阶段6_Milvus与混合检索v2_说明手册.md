# AI 私厨 v3.0 · 阶段 6：Milvus 向量库 + 三路混合检索 v2（新增内容说明手册）

> **本手册定位**：全项目**唯一一处逐行代码解释**——讲清楚阶段 6 的每一行"在做什么、为什么这么写、每个参数什么意思"。操作步骤请看操作手册（照着做），本手册只负责"看懂为什么"，两者绝不重复。
> 风格约定：代码行尾加简洁中文注释；解释表不加序号；不编造真实数据示例。
> 🟢 本手册配套的**融合数学与图谱匹配逻辑已在临时目录实测**（8 项断言全过）；Milvus 容器交互部分（建集合/导入/检索）在你机器上由 `verify_stage6.py` 验证。

---

## 目录

- [一、本阶段在做什么（一句话与全景图）](#一本阶段在做什么一句话与全景图)
- [二、新出现的专业名词（先看这张表再读代码）](#二新出现的专业名词先看这张表再读代码)
- [三、为什么向量库要"专用化"：PGVector vs Milvus](#三为什么向量库要专用化pgvector-vs-milvus)
- [四、Milvus 三容器的分工（etcd / minio / milvus 本体）](#四milvus-三容器的分工etcd--minio--milvus-本体)
- [五、docker-compose 三段逐行解释](#五docker-compose-三段逐行解释)
- [六、milvus_store.py 逐行解释（schema 与索引参数详解）](#六milvus_storepy-逐行解释schema-与索引参数详解)
- [七、import_recipes_milvus.py 逐行解释](#七import_recipes_milvuspy-逐行解释)
- [八、kg.py 图谱路两个函数逐行解释](#八kgpy-图谱路两个函数逐行解释)
- [九、retriever.py 三路融合逐行解释（含权重重分配数学）](#九retrieverpy-三路融合逐行解释含权重重分配数学)
- [十、灰度接线：Feature Flag 怎么切的](#十灰度接线feature-flag-怎么切的)
- [十一、retrieval_compare.py：MRR / Hit 指标逐行解释](#十一retrieval_comparepy-mrr--hit-指标逐行解释)
- [十二、测试设计解释](#十二测试设计解释)
- [十三、常见疑问](#十三常见疑问)

---

## 一、本阶段在做什么（一句话与全景图）

**一句话**：检索从"两路相似度比赛"（向量 + 关键词）升级为"两路相似度 + 一路结构化事实"的三路合议——每一路只知道自己擅长的那一面，融合层负责听三家之言排出最终名次；同时向量库搬到 Milvus，检索引擎与业务数据库分家。

```text
                 用户查询 "鸡胸肉 西兰花 减脂"
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
   向量路（50%）      BM25 路（30%）      图谱路（20%）
   "语义像不像"       "关键词中没中"      "图上有没有这条边"
   Milvus HNSW        进程内索引          Neo4j 两跳
   R017 R018 R024 …   R017 R023 R011 …    R017 R023 …
        └─────────────────┼──────────────────┘
                          ▼
              RRF 加权融合 score = Σ w/(60+rank)
              （单路缺席 → 权重按比例重分配）
                          ▼
              前 k 条 → 补全菜谱 → 阶段5缓存 → 重排节点
```

为什么需要第三路——用一个真实例子感受：

```text
查询："西兰花 减脂"
向量路：找"语义上像'西兰花减脂'的文本"——可能召回紫薯燕麦杯（都带"减脂"味儿）
BM25 路：找"包含'西兰花'三个字的文本"——命中所有提过西兰花的菜
图谱路：沿图上的边走——西兰花-(IN_RECIPE)->香煎鸡胸肉配西兰花、虾仁炒西兰花
        这是"数据库里白纸黑字的入菜关系"，不是猜测
```

---

## 二、新出现的专业名词（先看这张表再读代码）

| 名词 | 人话解释 | 在本阶段的角色 |
|---|---|---|
| **向量数据库** | 专门存"向量 + 元数据"并提供"近邻搜索"的数据库——不像 SQL 按“值相等”查，而按"方向相近"查 | Milvus 是这个品类的代表 |
| **维度（dimension）** | 一个向量的数字个数。本项目 embedding 输出 1024 维 = 每条菜谱文本变成 1024 个浮点数 | schema 里的 `dim=1024`，必须与 embedding 模型一致 |
| **余弦相似度（COSINE）** | 两个向量夹角的余弦值：方向越一致越接近 1，正交为 0——只看方向不看长度 | 度量"语义像不像"的标准尺子；`metric_type="COSINE"` |
| **HNSW 索引** | Hierarchical Navigable Small World：把向量组织成"多层跳表式图"——顶层稀疏好赶路、底层稠密好精找，检索像"高速转乡道" | Milvus 集合的索引类型（替代暴力扫描 FLAT） |
| **M / efConstruction** | HNSW 的两个建索引参数：M=每个节点连多少条边（图更稠密→更准但更占内存）；efConstruction=建图时候选队列长度（越大建得越精细、越慢） | `params={"M": 16, "efConstruction": 200}` |
| **ef（检索参数）** | 检索时候选队列长度——越大越准越慢。**建索引调质量，检索调速度，两者独立** | `search_params={"params": {"ef": 64}}` |
| **集合（Collection）** | Milvus 里"表"的叫法：schema（字段）+ 索引 + 数据三位一体 | `recipes_v2` |
| **主键 / upsert** | 主键唯一标识一行；upsert = 存在就更新、不存在就插入（按主键幂等） | `recipe_id` 当主键，重跑导入=覆盖不重复 |
| **gRPC** | Google 的高性能二进制 RPC 协议（HTTP/2 之上），比 JSON-over-HTTP 快 | Milvus 的 19530 端口就是 gRPC |
| **etcd** | 分布式键值存储：强一致的小字典，集群的"共识账本" | Milvus 用它记元数据（有哪些集合/索引/段） |
| **MinIO** | 开源对象存储：兼容 S3 协议的"文件仓库" | Milvus 用它存向量数据文件（段文件） |
| **段（Segment）** | Milvus 内部把数据切成一段段的存储单元（内存段/磁盘段），后台自动合并 | 说明"为什么 Milvus 需要 minio"——段文件落盘的地方 |
| **BM25** | 关键词相关性打分算法（TF-IDF 的进化版：词频饱和 + 文档长度归一） | 第二路（阶段 2 就有，复习） |
| **RRF（Reciprocal Rank Fusion）** | 倒数排名融合：不看分数只看名次，第 r 名贡献 1/(k+r)——多来源排名合并的标准算法，对"各家分数量纲不同"免疫 | 本阶段的融合内核（变体：加路权重） |
| **MRR@k** | Mean Reciprocal Rank：每个查询"第一条相关结果的名次倒数"取平均——衡量"最想要的排多前" | 对比实验指标 |
| **Hit@k** | 前 k 条里至少出现一条相关的查询占比——衡量"想找的有没有出现" | 对比实验指标 |
| **召回（recall）** | 检索把该找回来的东西找回来多少（相对"精确"是排得对不对） | 三路各自就是三种召回策略 |
| **灰度发布** | 新功能先放给一小部分流量，观察没问题再逐步放大 | Feature Flag `hybrid_v2` 从 5%→50%→100% |
| **降级 / fallback** | 组件不可用时切换到备用方案继续服务（而不是报错停摆） | Milvus 挂→PGVector；Neo4j 挂→两路融合 |

---

## 三、为什么向量库要"专用化"：PGVector vs Milvus

| 维度 | PGVector（阶段 1~5 在用） | Milvus（本阶段引入） |
|---|---|---|
| 本质 | PostgreSQL 的一个扩展插件 | 独立的向量数据库 |
| 检索时和谁抢资源 | 和用户表、账单表、审计表挤同一个 PG 的 CPU/内存/连接 | 独立进程独立资源 |
| 索引 | HNSW/IVF 都支持，但要和 OLTP 查询共存 | 为 ANN（近似最近邻）而生，段管理/缓存/压缩全为检索优化 |
| 规模天花板 | 百万级开始吃力（单表、单库） | 十亿级（分布式架构预留） |
| 运维 | 零额外组件（跟 PG 一起备份） | 多三个容器（etcd/minio/milvus） |

**本项目的真实选型逻辑**（面试照这个讲，诚实且有层次）：

```text
60 条菜谱，PGVector 明明够用，为什么还迁 Milvus？
1. 学习与简历维度：PGVector→Milvus 的迁移是"知道什么时候该换专用组件"的完整演练；
   反向的"为什么不用 ES/不用 Faiss 裸库"也能答（见第十三节 Q1）。
2. 架构维度：向量检索是 CPU 密集型，业务查询是 IO 密集型——资源画像不同的负载
   分开部署，是"微服务拆分依据"（阶段 8）的预演。
3. 风险维度：保留 PGVector 回退，迁移零风险——两套并存本身就是高可用设计。
```

> 🟡 诚实红线：**不写"支撑亿级向量"**——60 条数据写亿级就是给面试官递刀。写"完成 PGVector→Milvus 架构迁移，设计降级回退链路"——每个词都有代码对应。

---

## 四、Milvus 三容器的分工（etcd / minio / milvus 本体）

Milvus standalone 是个"三口之家"，各自管一摊：

```text
┌────────────────────────────────────────────────────┐
│                ai_chief_milvus (本体)                │
│   检索引擎：gRPC:19530 对外；算 HNSW、管内存段       │
│        │ 元数据："有哪些集合/索引/段"                │
│        ▼                                             │
│   ai_chief_etcd —— 共识账本（强一致 KV）             │
│        │ 数据文件：段文件（向量本体）落盘            │
│        ▼                                             │
│   ai_chief_minio —— 对象存储（S3 兼容文件仓库）      │
└────────────────────────────────────────────────────┘
```

| 容器 | 管什么 | 类比 |
|---|---|---|
| etcd | 元数据账本：集合定义、索引状态、段清单——**改一次写一次，量小但绝不能错** | 图书馆的"馆藏目录系统" |
| minio | 数据文件仓库：向量本体的段文件——**量大、追加写、顺序读** | 图书馆的"书库本身" |
| milvus | 干活的引擎：接受检索请求、走 HNSW 图、把结果还给你 | 图书馆的"管理员+检索台" |

**为什么账本和书库要分开**（存储分裂的通用理由）：元数据要强一致（少一条集合定义整个库就乱），数据要高吞吐（GB 级文件追加）——两类访问模式对存储引擎的要求截然相反，塞进一个组件就会两头不讨好。这个"目录与书库分离"的思想在 Kafka（Controller/日志）、数据库（WAL/数据文件）里反复出现。

---

## 五、docker-compose 三段逐行解释

### 5.1 etcd 段

```yaml
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
      ETCD_SNAPSHOT_COUNT: "50000"
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `AUTO_COMPACTION_MODE/RETENTION` | 自动压缩：etcd 每次修改都留历史版本，按"版本号"压缩、保留最近 1000 版 | 元数据频繁小改，不留压缩会无限膨胀 |
| `QUOTA_BACKEND_BYTES` | 后端存储配额 4GB | 超配额 etcd 进入维护模式拒写——提前给足 |
| `SNAPSHOT_COUNT` | 每 5 万次写做一次磁盘快照 | 快照之间的变更靠 WAL 日志恢复 |
| `advertise-client-urls=http://etcd:2379` | 对外宣告的访问地址用的是**服务名** | milvus 容器拿这个名字找它（docker 内部 DNS）；写 localhost 别的容器就找错人了 |
| `listen-client-urls http://0.0.0.0:2379` | 实际监听所有网卡 | 容器场景固定写法（不写 0.0.0.0 服务名解析了也连不进） |

### 5.2 minio 段

```yaml
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: minio server /minio_data --console-address ":9001"
    ports:
      - "9111:9001"
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `MINIO_ROOT_USER/PASSWORD` | 账密 | minioadmin/minioadmin 是本地开发默认值；**不映射数据端口 9000 到宿主机**——只有 milvus 在用它，少一个暴露面 |
| `--console-address ":9001"` | 管理控制台端口 | 显式声明它才固定（否则随机）；映射 9111 供浏览器选看 |
| 数据端口 9000 不映射 | API 端口只在容器网络内 | 宿主机 9000 已被前端开发服务器占用（端口规划表），而且人也不需要访问它 |

### 5.3 milvus 段

```yaml
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
      - "9191:9091"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      timeout: 20s
      retries: 5
      start_period: 90s
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `milvus run standalone` | 单机模式（另有 distributed 分布式） | 个人项目单机足矣；简历不写假集群 |
| `ETCD_ENDPOINTS / MINIO_ADDRESS` | 告诉 milvus 两个伙伴在哪 | 全部用服务名（docker 网络 DNS） |
| `19530` | gRPC 主端口 | pymilvus 连的就是它 |
| `9091 → 9191` | HTTP 健康检查/指标口 | `curl :9191/healthz` 是"活着吗"的最简探测 |
| `start_period: 90s` | 宽限期：启动后 90 秒内健康检查失败**不算数** | Milvus 启动要拉起索引、恢复段——直接判死会反复重启 |

---

## 六、milvus_store.py 逐行解释（schema 与索引参数详解）

### 6.1 单例与降级（与 kg.py 同款骨架）

```python
_client = None            # MilvusClient 单例（惰性创建）
_client_failed = False    # 连接失败标记：失败一次本进程不再重试

def get_client():
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    try:
        from pymilvus import MilvusClient
        _client = MilvusClient(uri=settings.MILVUS_URI)
        return _client
    except Exception as exc:
        _client_failed = True
        logger.warning(f"milvus: 不可用（...），向量检索回退 PGVector")
        return None
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `MilvusClient(uri=...)` | 创建客户端（此时**还没真正连**，首个操作才建连） | 与 redis-py 同为惰性连接设计 |
| 失败标记 | 一次失败终身降级 | 检索路径上每条请求多等一个连接超时不值得——降级哲学三连（kg / cache L2 / milvus）现在凑齐了 |
| `import` 在函数内 | 没装 pymilvus 时本模块照样可导入 | 依赖缺失 ≠ 系统瘫痪，只是这一路缺席 |

### 6.2 schema：集合的"字段设计图"

```python
schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
schema.add_field("recipe_id", DataType.VARCHAR, is_primary=True, max_length=16)
schema.add_field("text",      DataType.VARCHAR, max_length=8192)
schema.add_field("vector",    DataType.FLOAT_VECTOR, dim=DIMENSION)
schema.add_field("metadata",  DataType.JSON)
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `auto_id=False` | 主键由**我们**提供（R001...），不是数据库自增 | 菜谱 id 天然存在；自增 id 会导致重导时同一道菜存两份 |
| `enable_dynamic_field=False` | 关掉"动态字段"（行内可随意加字段） | schema 严格=数据干净；动态字段是排查地狱 |
| `recipe_id VARCHAR(16) is_primary` | 字符串主键 | 融合层需要它做键；主键还让 upsert 幂等成为可能 |
| `text VARCHAR(8192)` | 原文回显字段 | 检索命中时直接带回原文（PGVector 时代也是这么存的），8192 字符对一条菜谱文本绰绰有余 |
| `vector FLOAT_VECTOR dim=1024` | 向量本体 | dim 必须 = embedding 的 dimensions；**不一致建表就报错**（好事，fail-fast） |
| `metadata JSON` | 结构化元数据 | JSONB 思想在 Milvus 的对应物：菜名/标签/热量整体存取，还能按字段标量过滤 |

### 6.3 索引：HNSW 的三个旋钮

```python
index_params = client.prepare_index_params()
index_params.add_index(
    field_name="vector",
    index_type="HNSW",
    metric_type="COSINE",
    params={"M": 16, "efConstruction": 200},
)
```

| 参数 | 含义 | 调大 / 调小 |
|---|---|---|
| `index_type="HNSW"` | 多层图索引：顶层稀疏"高速公路"，底层稠密"精找" | 对比 FLAT（暴力扫描，100% 准但 O(n)）和 IVF（先分簇再搜簇，快但边界召回低）——HNSW 是"准与快"的工程平衡点，也是各家向量库默认主力 |
| `metric_type="COSINE"` | 距离怎么算 | L2（欧氏距离）受向量长度影响；COSINE 只看方向——文本语义的标准选择 |
| `M=16` | 图上每个节点连 16 条边 | 调大：更准、内存涨（每条边都占内存）；调小：省内存、容易"迷路"漏召回。16 是官方推荐甜点 |
| `efConstruction=200` | **建索引**时候选队列长度 | 调大：建图质量高、建得慢（一次性成本）；调小：快糙。200 是质量与时间的平衡 |

> 🔑 **efConstruction（建）与 ef（查）的区别**——面试高频追问：efConstruction 在**写入时**决定图的质量（一次性付出）；ef 在**检索时**决定走图的探索广度（每次查询都付出）。本项目建图用 200 求质量，检索用 ef=64 求延迟——两个旋钮独立调，这正是 HNSW 的精髓。

### 6.4 upsert 与检索

```python
result = client.upsert(collection_name=..., data=rows)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `upsert` | 按 recipe_id 覆盖写 | 幂等导入的第二重保险（第一重是导入前 drop 集合）——就算 drop 失败了半路重跑，也不会出重复行 |

```python
results = client.search(
    collection_name=settings.MILVUS_COLLECTION,
    data=[query_vector],
    limit=k,
    output_fields=["text", "metadata"],
    search_params={"metric_type": "COSINE", "params": {"ef": 64}},
)
for hit in results[0]:
    entity = hit.get("entity", {}) or {}
    hits.append({
        "recipe_id": hit.get("id"),
        "content": entity.get("text", ""),
        "metadata": entity.get("metadata", {}) or {},
        "score": hit.get("distance"),
    })
```

| 参数 | 含义 | 取值理由 |
|---|---|---|
| `data=[query_vector]` | 查询向量**装在列表里** | 接口支持一次查多个（批量），单查也要装列表——`results[0]` 取第一个向量的结果就是为此 |
| `limit=k` | 每个查询向量取前 k 近邻 | 对应 SQL 的 LIMIT |
| `output_fields` | 命中时一并带回的字段 | 不声明就只有 id 和距离，还得二次查询——一次拿全 |
| `search_params.ef=64` | 检索时候选队列 | 建图 200 求质量、检索 64 求速度；调到 200 更准但更慢——**这是本阶段最值得亲手试的调参实验** |
| `hit["distance"]` | 命中"距离" | COSINE 度量下它就是相似度（越大越像，1 为满）——字段名叫 distance 只是接口惯例 |

---

## 七、import_recipes_milvus.py 逐行解释

```python
BATCH_SIZE = 10  # DashScope embedding 单次最多 10 条文本

for i in range(0, len(recipes), BATCH_SIZE):
    batch = recipes[i : i + BATCH_SIZE]
    texts = [recipe_to_text(r) for r in batch]
    vectors = embed_texts(texts)
    rows = [
        {
            "recipe_id": r["recipe_id"],
            "text": t,
            "vector": v,
            "metadata": recipe_to_metadata(r),
        }
        for r, t, v in zip(batch, texts, vectors)
    ]
    n = upsert_recipes(rows)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `range(0, len, 10)` 切片循环 | 60 条按 10 条一批 | DashScope 的 embedding 接口**单次最多 10 条**（v2.0 时代踩过并记录的坑，这里沿用） |
| `texts` 先算再 `vectors` | 文本列表 → 向量列表 | `embed_texts` 内部自动按 10 条分批发 HTTP——外层切片其实与它对齐，双保险 |
| `zip(batch, texts, vectors)` | 三条等长列表并排走 | 菜谱、文本、向量按下标配对——zip 是"多列表对齐"的标准姿势 |
| `invalidate_prefix("rag")` + `("rag2")` 收尾 | 两条检索路径的缓存都失效 | v1 缓存前缀是 rag、v2 是 rag2——**新增检索路径时新增缓存前缀**，失效钩子必须同步覆盖 |

幂等的三重设计（重跑脚本永远安全）：drop 集合（清场）→ 重建 schema → upsert 按主键覆盖。**幂等是导入脚本的第一美德**——数据脚本跑一半挂了，修完直接重跑，不用担心"跑出两份数据"。

---

## 八、kg.py 图谱路两个函数逐行解释

### 8.1 食材名缓存

```python
@lru_cache(maxsize=1)
def _ingredient_names() -> List[str]:
    rows = _run("MATCH (i:Ingredient) RETURN i.name AS name")
    return [r["name"] for r in rows]

def reset_ingredient_cache() -> None:
    _ingredient_names.cache_clear()
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `lru_cache(maxsize=1)` | 全图食材名只查一次 | 每次 `MATCH (i:Ingredient)` 都是一次 Neo4j 往返；食材名集合几乎不变——**"几乎不变的读"正是缓存的标准靶子**（阶段 5 知识的复用） |
| `cache_clear()` 暴露出来 | 重建图谱后的手动刷新入口 | lru_cache 不带 TTL（进程生命周期），重建图谱后要么调它、要么重启后端——手册和注释里都写明了 |

### 8.2 图谱路主函数

```python
def match_recipes_from_query(query: str, limit: int = 10) -> List[str]:
    names = _ingredient_names()
    if not names:
        return []
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
    return [r["rid"] for r in rows]
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `matched = [n for n in names if n in query]` | 食材名**子串**匹配查询文本 | "香煎鸡胸肉配西兰花"不用分词就能命中"鸡胸肉"——图谱路要的是**事实命中**，宁可少而准（模糊交给向量路） |
| 两处提前 `return []` | 没食材可匹配就退出 | 空返回在上层=「这一路缺席」信号，触发权重重分配——**返回空不是失败，是诚实的弃权** |
| `count(DISTINCT i)` | 每道菜命中了**几种**食材 | 命中两种（鸡胸肉+西兰花）的菜排一种（只有西兰花）前面——**证据越多越可信** |
| `ORDER BY hits DESC LIMIT $limit` | 数据库内排序截断 | 排序下推给 Neo4j，Python 只收 final 名单——"能下推的过滤排序就下推" |
| 参数化 `$names/$limit` | 永不拼接 Cypher | 防注入，与 SQL 参数化同一原则（阶段 3 老规矩） |

读法（人话翻译这条 Cypher）：**"对每个食材 i，沿它的【入菜】边走一步到菜谱 rc；只看名字在给定名单里的食材；按菜谱分组数命中了几种食材，降序取前 limit 个。"** 一条查询两跳完成，这就是图数据库查询关系"成本恒定"的体现。

---

## 九、retriever.py 三路融合逐行解释（含权重重分配数学）

### 9.1 三路各自的取数函数

```python
def _vector_path(query: str, n: int) -> List[str]:
    hits = _milvus_search(embed_query(query), k=n)
    if hits:
        return [h["recipe_id"] for h in hits]
    store = get_vector_store()                        # 回退：PGVector
    if hasattr(store, "as_retriever"):
        vh = store.as_retriever(search_kwargs={"k": n}).invoke(query)
    else:
        vh = store.similarity_search(query, k=n)
    return [h.metadata.get("recipe_id") for h in vh if h.metadata.get("recipe_id")]
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 先 Milvous 后 PGVector | 主路 Milvus，**空结果触发回退** | milvus_store 的降级设计返回空列表——这里把"空"翻译成"走备用路"。回退路径直接复用 v1 已验证的调用代码，不重写 |
| `n = k * 2`（调用方传的） | 每路先取两倍候选 | 融合是"淘汰赛"：候选多一些，融合后截回 k 才有挑选余地 |

```python
def _bm25_path(query: str, n: int) -> List[str]:
    hits = _build_bm25(n).invoke(query)
    return [h.metadata.get("recipe_id") for h in hits if h.metadata.get("recipe_id")]

def _kg_path(query: str, n: int) -> List[str]:
    return kg_module.match_recipes_from_query(query, limit=n)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `_build_bm25(n)` | 阶段 5 缓存的 BM25 索引 | `@lru_cache` 让索引只在第一次建——三路里最便宜的一路 |
| `_kg_path` 只是转发 | 图谱逻辑收在 kg.py | 查询收口原则：retriever 不写 Cypher（换图数据库只改 kg 模块） |

### 9.2 融合核心 _fuse（本阶段的数学心脏）

```python
def _fuse(rankings: Dict[str, List[str]], weights: Dict[str, float]) -> List[tuple]:
    active = {p: ids for p, ids in rankings.items() if ids}
    if not active:
        return []
    if len(active) < len(weights):
        total = sum(weights[p] for p in active)
        weights = {p: (weights[p] / total) if total else 0 for p in weights}
    scores: Dict[str, float] = {}
    for path, ids in active.items():
        for rank, rid in enumerate(ids):
            scores[rid] = scores.get(rid, 0.0) + weights[path] / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `active` 字典过滤 | 空路直接除名 | 把"缺席"从特殊情况变成普通情况——后面的重分配自然成立 |
| `weights[p] / total` | **权重重分配** | 数学：剩余路的权重除以剩余总权重=按原比例放大到和为 1。0.5:0.3 缺 0.2 → 0.5/0.8 : 0.3/0.8 = 0.625 : 0.375——**比例关系保持不变**，这是"公平"的数学定义 |
| `weights[path] / (RRF_K + rank + 1)` | RRF 变体得分 | 分母 60+名次：第 1 名 1/61、第 2 名 1/62——名次间的差距被压得很平。**好处**：多路合议容易胜过单路冠军（两路都排第 3 > 一路第 1 + 一路查无此菜）；且对"各家分数量纲不同"完全免疫（只看名次） |
| `scores.get(rid, 0.0) +` | 同一菜谱跨路**累加** | 这就是"合议"：三路都说好的菜分数叠起来 |
| `sorted(..., key=lambda x: -x[1])` | 按分数降序 | 融合最终裁决 |

**为什么不用 1/(rank+1)（v1 的算法）**：v1 里第 1 名 1.0、第 2 名 0.5——头部差距太大，"一路的冠军"几乎锁死榜首；RRF 的 60 平滑让"多路合议"真正起作用。v1 保留原算法没改——**对比实验比的就是这两套融合策略**（顺带比了向量库迁移），这正是实验设计的干净之处（一次只换该换的，v1 完全不动）。

### 9.3 主函数 hybrid_search_v2

```python
@_cached_dec(prefix="rag2", ttl=300, null_ttl=30)
def hybrid_search_v2(query: str, k: int = 5, weights=None) -> List[Dict]:
    w = weights or HYBRID_V2_WEIGHTS
    n = k * 2
    rankings = {"vector": _vector_path(query, n), "bm25": _bm25_path(query, n),
                "kg": _kg_path(query, n)}
    fused = _fuse(rankings, dict(w))[:k]

    meta_pool: Dict[str, Dict] = {}
    for rid, _ in fused:
        base = _recipe_index_v2().get(rid)
        if base:
            meta_pool[rid] = {"content": recipe_to_text(base),
                              "metadata": recipe_to_metadata(base)}
    return [...]
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `@cached(prefix="rag2")` | v2 有**自己的缓存前缀** | 与 v1 的 rag 隔离：切 flag 时不会互相污染缓存；失效钩子两个前缀都清 |
| `weights=None` 形参 | 权重可注入 | 单测注入假权重验证数学；将来做"权重调参实验"不用改代码 |
| `dict(w)` 拷贝一份 | 防止重分配污染全局 | `_fuse` 内部改 weights——传引用会把模块级默认权重改坏（不可变数据习惯：**要改先拷**） |
| `meta_pool` 从原始 JSON 补全 | 图谱路可能召回前两路没有的菜 | 三路候选集不相等是常态——`_recipe_index_v2()` 是全量菜谱索引，兜住所有路的输出 |
| 返回结构带 `recipe_id` | 与 v1 结构的**唯一差异点** | 消费方 `recipe_rag_tool` 已做兼容（`meta.get(...) or hit.get(...)`）；向后兼容的演进模式 |

---

## 十、灰度接线：Feature Flag 怎么切的

```python
def _hybrid_v2_enabled() -> bool:
    try:
        from app_my.core.feature_flag import is_feature_enabled
        return bool(is_feature_enabled("hybrid_v2"))
    except Exception:
        return False

def local_recipe_search(query: str, k: int = 5) -> List[dict]:
    if _hybrid_v2_enabled():
        hits = hybrid_search_v2(query, k=k)
    else:
        hits = hybrid_search(query, k=k)
    ...
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `try/except` 包住 flag 读取 | flag 模块异常=关 | **新功能的默认姿态是关**——灰度的意义就是"出问题=回到旧路"，异常时选 v1 与此一致 |
| 在 `local_recipe_search`（唯一入口）分流 | 一个 if 切换全链路 | 三个消费点（推荐节点/工具调用/对比脚本）都经这里——**入口收口，改一处生效** |
| flag 有 60 秒内存缓存（阶段 4 设计） | 改开关不必重启 | 运维动作（改 flag）与发布动作（重启进程）分离——这就是灰度发布和"改代码上线"的本质区别 |

灰度节奏（阶段 4 的 rollout_percent）在检索场景的真实含义：5% 流量走 v2 时，95% 用户完全无感；观察日志（三路命中数、延迟）没问题再放大——**个人项目也能走完这个仪式**，面试讲灰度时你有一手亲历细节。

---

## 十一、retrieval_compare.py：MRR / Hit 指标逐行解释

### 11.1 两个指标的人话定义

```python
def mrr_at_k(result_ids, relevant, k=5):
    for rank, rid in enumerate(result_ids[:k], start=1):
        if rid in relevant:
            return 1.0 / rank
    return 0.0
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `enumerate(..., start=1)` | 名次从 1 数起 | 给人看的名次从 1 开始，代码里 0 基容易把人绕晕 |
| 第一条相关结果返回 `1/rank` | 倒数排名 | 相关结果排第 1 → 1.0 分；排第 2 → 0.5；排第 5 → 0.2；**没出现 → 0**——"最想要的排多前"的单调度量 |
| 找到第一条就 return | 只看第一条相关的名次 | MRR 的定义就是"第一条相关结果的排名倒数"——第二条在哪不影响这个指标（那是另一个指标 nDCG 的事） |

```python
def hit_at_k(result_ids, relevant, k=5):
    return 1.0 if any(rid in relevant for rid in result_ids[:k]) else 0.0
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `any(...)` 一票通过 | 前 5 里有 relevant 就得 1 | 比 MRR 宽容：只问"有没有"，不问"第几"——两个指标一严一宽正好互补 |

**为什么选这两个指标而不是"准确率"**：检索是排名问题不是分类问题——"前 5 条里 3 条相关"没法用准确率表达（分母是谁？）。MRR/Hit@k 是信息检索的标准评估语言，面试用它交流零歧义。

### 11.2 实验的公平性设计

| 设计 | 防的是什么偏差 |
|---|---|
| 两版同进程、同 embedding、同数据 | 环境差异（网络快慢、缓存冷热）污染对比 |
| `invalidate_prefix("rag")` + `("rag2")` 开跑前清缓存 | 阶段 5 的缓存把"第一次查询的旧结果"喂给实验 |
| 直接调 `hybrid_search / hybrid_search_v2` | 绕过 flag——比较的是**算法本身**，不是"flag 今天开着没有" |
| 10 组查询固定写死在 TEST_SET | 可重复：任何时候重跑，同一批问题、同一批期望——**能复现的实验才算实验** |

> 🟡 测试集的期望标注（`relevant`）是**人工判断**："减脂餐 鸡胸肉"→ 相关=带减脂/高蛋白标签或主料是鸡胸肉的菜。标注标准写在脚本注释里——评估的ground truth 怎么来的，面试被问就照实说"按食材与标签人工标注的 10 组查询"。

---

## 十二、测试设计解释

| 测试 | 守护的断言 | 对应的故障场景 |
|---|---|---|
| `test_fuse_three_paths` | 双命中的菜霸占前二 | 融合根本没生效（各路结果被某一路覆盖） |
| `test_fuse_kg_missing_redistributes` | kg 缺席时向量权重仍高于 BM25 | 重分配算错（比例关系被破坏） |
| `test_fuse_single_path` | 单路时按原顺序返回 | 极端情况下融合把顺序搞乱 |
| `test_fuse_all_empty` | 全空返回空列表 | 空输入炸异常（None 迭代错） |
| `test_fuse_rank_monotonic` | 同路内名次单调 | RRF 公式抄错（分母丢了或加了） |
| `test_weights_sum_to_one` | 三路权重和为 1 | 改权重时手滑（0.5+0.3+0.2≠1 会静默地放大某一路） |
| `test_kg_match_substring` | 子串命中 + 排序正确 | 图谱路匹配逻辑错（精确匹配漏掉长菜名） |
| `test_kg_match_no_hit` | 无命中返回空 | 空结果误报（缺席信号失灵→降级链路断） |

**测试为什么不需要起 Milvus/Neo4j**：单测只测**纯逻辑**（数学与匹配），不测客户端与真实服务的交互——后者由 verify_stage6.py 的 conn/search/kg 子命令在你机器上验。**"逻辑用单测、集成用验证脚本"** 的分层，让测试套件在任何机器（哪怕没装 docker）都全绿。

`test_kg_match_substring` 的 mock 手法值得学一眼：

```python
monkeypatch.setattr(kg_module, "_ingredient_names", lambda: ["鸡胸肉", "西兰花", "豆腐"])
monkeypatch.setattr(kg_module, "_run", lambda cypher, **kw: fake_rows)
```

替身是一个**无参 lambda**（顶替 `_ingredient_names`）和一个**吞掉所有关键字参数的 lambda**（顶替 `_run`——它会被传 `names=`/`limit=`）。monkeypatch 的本质就是"运行时把模块属性换掉、测试结束自动还原"。

---

## 十三、常见疑问

**Q1：为什么不用 Elasticsearch（BM25+向量一体）？**
A：ES 一件套确实能做三路里的两路。不选它的理由：① JVM 全家桶内存开销对这个项目过重；② 第三路（图谱）反正要 Neo4j，三件套拆成"三个专用组件"比"一个大型综合组件+一个图库"边界更清晰——**组件按业务能力分工**（向量归向量、关键词归关键词、关系归图）是微服务化（阶段 8）的同一思想。

**Q2：Milvus 都上了，PGVector 为什么不删？**
A：它是回退路径的底座。"高可用"不是"多买个云服务"，而是**任何单点挂掉时链路自动降级继续服务**——停掉 Milvus 容器检索不断，这个演示比任何架构图都有说服力。60 条数据双写一份的成本趋近于零。

**Q3：三路权重 50/30/20 怎么定的？**
A：工程起手式：向量是语义主力给一半；BM25 补关键词精确命中给三成；图谱是"事实校准"信号给两成。**重点是可调**（`HYBRID_V2_WEIGHTS` 一处改）且**可验证**（retrieval_compare 跑前后对比）——"拍初值→实验→用数据修正"本身就是面试可以讲的方法论。

**Q4：图谱路为什么不给"禁忌"信号扣分？检索阶段不算禁忌吗？**
A：职责分层。检索（retrieval）的职责是**召回**——把候选找齐；禁忌扣分是**重排**（ranker，阶段 3 的打分维度⑧）的职责。检索阶段掺业务规则，会让"召回率"和"个性化"搅在一起没法独立评估——这正是检索系统和推荐系统的经典分层（recall → rank → re-rank）。

**Q5：hybrid_search_v2 的缓存会不会把"切换 flag"变得不干净？**
A：不会串——v1/v2 缓存前缀隔离（rag/rag2），切 flag 后各读各的。唯一的细节是：切换后一分钟内 L1 里还留着旧路径的结果（没过期），但这本来就是缓存语义（TTL 内容忍旧值）。

**Q6：为什么 Milvus 的 metadata 用 JSON 不用多个标量字段？**
A：菜谱元数据字段多且可能演进（将来加"菜系标签向量"）。Milvus 的 JSON 字段整体存取、还支持 JSON 内路径的标量过滤——字段schema 不用跟着数据演进改。等真的有高频过滤字段（比如按 cuisine 过滤）再"提升"成独立标量字段+scalar index，这是 schema 演进的正确次序。

**Q7：导入脚本为什么 drop 整个集合再重建，而不是增量 upsert？**
A：60 条全量数据的场景，"drop+重建"是最简单且必然正确的幂等方案：不用写 diff 逻辑、不用担心残留脏数据。增量 upsert 适合"日常少量追加"；**全量重导适合"数据集整体换代"**——识别自己处于哪种场景，比记住两个名词更重要。

**Q8：MRR 提升多少算"值得写进简历"？**
A：数字大小不是关键，**出处和过程才是**。哪怕 +8%，只要能讲清"10 组查询、两版同环境对比、MRR/Hit 两个指标、哪类查询提升明显（含图谱信号的）、哪类反而变差、为什么"——这比一个没有过程的大数字可信十倍。简历真实性原则（总纲第七节）在检索效果上同样适用。

---

> **配套阅读**：操作手册讲"照着做"，本手册讲"为什么"。阶段 7（Prometheus + Grafana）开工后，本手册的三路命中日志（`vector=10 bm25=10 kg=2`）会成为监控指标的数据来源——检索延迟、三路命中分布都会进 Grafana 仪表盘。
