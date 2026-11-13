# AI 私厨 v3.0 · 阶段 3：Neo4j 知识图谱 + 多跳推理（新增内容说明手册）

> **本手册定位**：全项目**唯一一处逐行代码解释**——讲清楚阶段 3 的每一行"在做什么、为什么这么写"。操作步骤请看操作手册（照着做），本手册只负责"看懂为什么"，两者绝不重复。
> 风格约定：代码行尾加简洁中文注释；解释表不加序号；不编造真实数据示例。

---

## 目录

- [一、本阶段在做什么（一句话与全景图）](#一本阶段在做什么一句话与全景图)
- [二、为什么是图数据库：三种数据形态的分工](#二为什么是图数据库三种数据形态的分工)
- [三、图模型设计：节点和关系是怎么定下来的](#三图模型设计节点和关系是怎么定下来的)
- [四、kg_facts.json：策展知识与数据对齐](#四kg_factsjson策展知识与数据对齐)
- [五、core/kg.py：驱动单例与优雅降级](#五corekgpy驱动单例与优雅降级)
- [六、core/kg.py：三个查询函数逐行解释](#六corekgpy三个查询函数逐行解释)
- [七、init_kg.py：UNWIND 批量建图逐行解释](#七init_kgpyunwind-批量建图逐行解释)
- [八、ranker.py 三处改动逐行解释](#八rankerpy-三处改动逐行解释)
- [九、api/kg.py 与 main.py 改动解释](#九apikgpy-与-mainpy-改动解释)
- [十、测试设计解释：13 个单测在守护什么](#十测试设计解释13-个单测在守护什么)
- [十一、Cypher 语法速查（本阶段用到的）](#十一cypher-语法速查本阶段用到的)
- [十二、常见疑问](#十二常见疑问)

---

## 一、本阶段在做什么（一句话与全景图）

**一句话**：向量检索管"相似"（哪些菜谱像你要的），图谱管"关系"（你的身体和这个食材之间发生了什么）——本阶段把后一半补上，且每个结论都能指着图上一条边说"依据在这"。

```text
                        ┌─────────────────────────────────────────────────┐
                        │            Neo4j 知识图谱（216 节点/498 关系）      │
                        │                                                 │
   recipes.json ──建图──►│  (:Recipe)◄──IN_RECIPE──(:Ingredient)           │
   kg_facts.json ─建图──►│                            │                    │
                        │              CONTRAINDICATED_FOR ──►(:Condition) │
                        │              BENEFICIAL_FOR    ──►(:Condition)   │
                        │              RICH_IN           ──►(:Nutrient)    │
                        └───────────────┬─────────────────┬────────────────┘
                                        │                 │
                          一次查全忌口/推荐映射          多跳推理问答
                                        ▼                 ▼
                        ┌──────────────────────┐  ┌──────────────────────┐
                        │ ranker 重排节点        │  │ /kg/ask 接口          │
                        │ 打分维度⑧：           │  │ 结论+理由+营养证据     │
                        │ 忌口扣分/推荐加分      │  │ +受影响菜谱           │
                        │ 理由传给最终报告       │  │ （JWT 保护）           │
                        └──────────────────────┘  └──────────────────────┘
```

对用户可感知的变化：控糖用户的推荐结果里，土豆菜被压下去、西兰花菜升上来，而且报告里的理由写着"图谱提示：土豆对糖尿病患者限量——GI值较高"。

---

## 二、为什么是图数据库：三种数据形态的分工

本阶段之后，项目里同时存在三种存储，各管一件事：

| 存储 | 擅长 | 本项目用它管 | 典型查询 |
|---|---|---|---|
| PostgreSQL（关系型） | 结构化事务数据 | 用户、画像、token | `WHERE user_id = ?` |
| PGVector（向量） | 相似度检索 | 菜谱语义召回 | "和鸡胸肉相关的菜谱" |
| Neo4j（图） | 关系推理 | 食材-营养-禁忌-菜谱 | "糖尿病患者忌口的食材有哪些、影响哪些菜" |

为什么"糖尿病患者不能吃什么"不适合用 SQL 或向量做：

```text
SQL 的做法：要为每种状况建一张忌口表，查"哪些菜受影响"要 JOIN 三层，
           关系种类一多（以后加"食物相克""药物相互作用"），JOIN 深度跟着涨，写不动
向量的做法：把"糖尿病忌口"文档切块做嵌入，检索回来的是"相似的文档片段"，
           没有精确的"关系"概念，也无法保证穷举（漏一条就是漏一条）
图的做法：  忌口就是一条边、入菜就是一条边，"受影响菜谱"= 沿两条边走两跳，
           加新关系类型 = 加一种边，老查询一个字不用改
```

**核心洞察**：图数据库的价值不在"存"，在于**查询关系时成本恒定**——两跳三跳都是 `MATCH` 一句话，不用拼 JOIN。

---

## 三、图模型设计：节点和关系是怎么定下来的

先看最终结果，再讲为什么：

```text
节点（4 类）                          关系（4 类）
─────────────                        ─────────────
(:Ingredient {name})                 (:Ingredient)-[:IN_RECIPE {amount}]->(:Recipe)
(:Recipe {recipe_id,name,calories…}) (:Ingredient)-[:RICH_IN {level}]->(:Nutrient)
(:Nutrient {name,note})              (:Ingredient)-[:CONTRAINDICATED_FOR {level,reason}]->(:Condition)
(:Condition {name,aka})              (:Ingredient)-[:BENEFICIAL_FOR {reason}]->(:Condition)
```

| 设计决策 | 在做什么 | 为什么这么写 |
|---|---|---|
| 节点只放"名词"，关系放"动词" | Ingredient/Recipe/Nutrient/Condition 都是实体 | 图建模第一原则：节点是东西，边是关系——"土豆**禁忌于**糖尿病"里土豆和糖尿病是名词、禁忌是动词 |
| 属性挂在**关系**上（level/reason） | 禁忌边带等级和理由 | "限量"是这条**关系**的属性，不是土豆的属性（土豆对痛风没关系，对糖尿病才限量）——挂在节点上就错了 |
| Recipe 节点带 calories 等业务属性 | 菜谱的热量/时长直接放节点 | 排障和演示时一条 Cypher 能取全；食谱详情仍以 recipes.json 为准（图不存 steps 全文，避免双写漂移） |
| Condition 带 aka 别名数组 | "高血糖"挂在"糖尿病"节点上 | 用户嘴里的说法和医学名词不一致；别名放节点，查询时 `WHERE c.name=$x OR $x IN c.aka` 一句兼容 |
| 没有把 tags 建成节点 | 菜谱标签留在 JSON | 本阶段的推理用不到标签关系；**不建用不上的边**是图建模的克制原则（每类边都要回答"哪个查询在用它"） |

> 🟡 一个反直觉的点：图的"设计"主要发生在**边**上。节点是谁几乎一目了然，真正决定这个图能回答什么问题的，是你允许哪些边存在。

---

## 四、kg_facts.json：策展知识与数据对齐

### 4.1 为什么知识是"人写的 JSON"而不是"LLM 抽的"

| 方案 | 优点 | 致命缺点 |
|---|---|---|
| LLM 自动抽取知识建图 | 快、覆盖广 | 会产生幻觉边——"土豆禁忌于感冒"这种错边混进去，用户按错误结论忌口，比没有图谱更糟 |
| 人工策展 JSON（本阶段做法） | 每条边可校验、可追责 | 慢、覆盖有限 |

推理系统的**可信度上限 = 知识源的可信度**。本阶段选择小而准：6 种常见状况、86 条带理由的边，全部对齐菜谱库真实食材。覆盖有限没关系——没收录的关系系统会**诚实说"未发现"**，这比错答好。

### 4.2 数据结构（三种字段，机器可校验）

```json
"糖尿病": {
  "aka": ["高血糖", "血糖偏高", "控糖"],          // 别名：用户搜索的口语说法
  "avoid": [
    {"name": "土豆", "level": "限量", "reason": "GI值较高，升血糖快，建议控制份量"}
  ],
  "prefer": [
    {"name": "西兰花", "reason": "低GI且富含膳食纤维，血糖友好"}
  ]
}
```

| 字段 | 在做什么 | 为什么这么写 |
|---|---|---|
| `aka` 数组 | 收录"高血糖"等口语别名 | 建图时写进 Condition 节点，查询侧一句 `IN c.aka` 兼容所有说法 |
| `level` 三档（避免/限量/适量） | 禁忌的严重程度 | 对应 kg.py 里的扣分权重 8/4/2——**"不能吃"和"少吃点"必须区分**，一刀切扣分会把推荐列表搞成空白 |
| `reason` 人话理由 | 每条禁忌必须带解释 | 理由会流到用户的报告里："为什么不建议"和"不建议"同样重要；没理由的知识不允许入库 |
| `nutrients` 的 `high` 数组 | 食材→营养素富集关系 | 是"营养证据"查询的数据源（土豆-高碳水，支撑"GI高"的结论） |

### 4.3 最容易踩的坑：名字对齐

图谱项目最经典的失败模式：知识里写"番茄"，菜谱里是"西红柿"——**这条边建了也永远查不到**。三道防线：

```text
① 人工核对：kg_facts 里每个食材名都从 recipes.json 里逐个复制
② 单测守护：test_fact_ingredients_align_with_recipes 会把"孤儿食材"全部揪出来
③ 同一切分规则：建图和查询都用 re.split(r"\s+") 取第一个词（"鸡蛋 3个"→"鸡蛋"）
```

其中 ② 是关键——以后任何人往 kg_facts.json 加条目，抄错名字立刻测试报红，不用等线上查不到才发现。

---

## 五、core/kg.py：驱动单例与优雅降级

### 5.1 模块级状态（两个全局变量）

```python
_driver = None            # 驱动单例（惰性创建）
_driver_failed = False    # 曾连接失败就不再反复尝试（避免每次请求都等超时）
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `_driver = None` | 驱动单例的"还没创建"标记 | 建连接有开销（TCP 握手+鉴权），全局建一次复用——和 `get_chat_model` 的 lru_cache 单例是同一个思想 |
| `_driver_failed = False` | 失败标记 | 🔑 本模块最重要的设计：**连接失败一次后，本进程余生不再尝试**。否则每次用户对话都要白等 5 秒超时——降级必须降得干脆 |

### 5.2 连接函数逐行解释

```python
def _get_driver():
    """惰性创建 Neo4j 驱动单例。连接失败标记 _driver_failed，后续直接放弃。"""
    global _driver, _driver_failed          # 声明要改模块级变量（Python 不声明只能读）
    if _driver is not None:                 # 已有单例：直接返回（快路径）
        return _driver
    if _driver_failed:                      # 之前失败过：直接放弃（第二快路径）
        return None
    try:
        from neo4j import GraphDatabase     # 函数内局部导入：没装 neo4j 包时，import 本模块不报错

        driver = GraphDatabase.driver(
            settings.NEO4J_URI,             # bolt://localhost:7687，Bolt 是 Neo4j 的二进制查询协议
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            connection_timeout=5,           # 连不上 5 秒内放弃，不拖慢主流程
            max_connection_pool_size=4,     # 个人项目用不了多少并发连接
        )
        driver.verify_connectivity()        # 立刻验证一次，失败走 except（惰性连接可能到真查询才炸，提前炸好处理）
        _driver = driver                    # 成功：记住单例
        logger.info(f"kg: 已连接 Neo4j（{settings.NEO4J_URI}）")
        return _driver
    except Exception as exc:
        _driver_failed = True               # 失败：标记后本进程不再重试
        logger.warning(f"kg: Neo4j 不可用（{type(exc).__name__}: {exc}），图谱推理降级为跳过")
        return None
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 局部 `from neo4j import ...` | 驱动的导入放在函数里 | 单测/无驱动环境 import kg 模块不炸（和 token_billing 局部导入 redis 同款思路） |
| `connection_timeout=5` | 限制连接等待 | 图谱是增强能力，配额给到 5 秒封顶——**增强组件不能拖垮主链路** |
| `verify_connectivity()` | 创建后立刻验活 | driver 对象创建成功 ≠ 连得上（驱动是惰性连接的）；在这里炸，走统一的 except 分支 |

### 5.3 统一查询入口

```python
def _run(cypher: str, **params) -> List[dict]:
    driver = _get_driver()                  # 拿单例（可能是 None）
    if driver is None:
        return []                           # 图不可用 → 空结果（调用方拿到空 map 就跳过图谱逻辑）
    try:
        with driver.session() as session:   # with：用完自动归还连接（session 是"一次对话"，轻量对象）
            return [record.data() for record in session.run(cypher, **params)]
    except Exception as exc:
        logger.warning(f"kg: 查询失败（已降级为空结果）: {exc}")
        return []                           # 语法错/超时/连接断 → 空结果，绝不让异常冒泡到业务层
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `session.run(cypher, **params)` | 参数化查询 | 🔑 **永不字符串拼接 Cypher**——`$conditions` 占位符防注入，和 SQL 参数化同一原则 |
| `record.data()` | 记录转字典 | Neo4j 返回的 Record 对象转成纯 Python 字典，业务层不用认识 Neo4j 类型 |
| 两处 `return []` | 统一降级出口 | 上游（ranker/api）只判断"空不空"，不需要知道"是没知识还是没连上" |

---

## 六、core/kg.py：三个查询函数逐行解释

### 6.1 derive_conditions：画像 → 状况

```python
GOAL_TO_CONDITION = {"控糖": "糖尿病"}       # 画像目标到图谱状况的映射表

def derive_conditions(profile: dict) -> List[str]:
    conds: List[str] = []
    goal = profile.get("goal")
    if goal in GOAL_TO_CONDITION:            # 来源一：目标暗含的饮食原则
        conds.append(GOAL_TO_CONDITION[goal])
    for c in profile.get("health_conditions") or []:   # 来源二：显式填写的状况
        if c and c not in conds:             # 去空串 + 去重（控糖+糖尿病只留一个）
            conds.append(c)
    return conds
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 用**映射表**而不是 if-else | "控糖"→"糖尿病" | 以后加"护肝→脂肪肝"只改一行表；分支逻辑永远比数据表难维护 |
| 减脂/增肌不映射 | 只有控糖有对应状况 | 减脂增肌是"目标偏好"（用原有打分维度①处理），不是"禁忌"——不混入图谱概念 |
| 返回空列表 = 不查图 | 普通用户零图谱开销 | 后面 ranker 用 `if conditions:` 短路，普通用户一次图查询都不会发生 |

### 6.2 get_condition_guidance：状况 → 忌口/推荐映射（重排的数据源）

```python
rows = _run(
    """
    MATCH (i:Ingredient)-[r:CONTRAINDICATED_FOR]->(cond:Condition)
    WHERE cond.name IN $conditions
    RETURN i.name AS ingredient, cond.name AS condition,
           r.level AS level, r.reason AS reason
    """,
    conditions=conditions,
)
```

读法（人话翻译）：**"找出所有食材 i，使得 i 到给定状况的【禁忌】边存在，把食材名/状况名/等级/理由还给我。"** 一条查询把一种状况的全部忌口拿完。

```python
avoid_map: Dict[str, dict] = {}
for row in rows:
    weight = LEVEL_WEIGHT.get(row["level"], 2)      # 等级换扣分权重；没见过的等级按最轻的算
    old = avoid_map.get(row["ingredient"])
    if old is None or weight > old["weight"]:       # 同一食材命中多状况 → 保留更重的那条
        avoid_map[row["ingredient"]] = { ... }
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 一次查全再在 Python 里合并 | 不逐食材查询 | "土豆+糖尿病""土豆+慢性肾病"分开查要 N×M 次往返；图数据库一次往返拿全部，本地合并更便宜 |
| `weight > old["weight"]` 才覆盖 | 冲突取更重 | 土豆对糖尿病"限量"(-4)、对肾病也"限量"(-4)，但假设某食材一边"避免"一边"适量"——**安全第一，按最严的算** |
| 返回字典而非列表 | `{食材: 详情}` | 重排时是"拿食材名查详情"的场景，字典 O(1)，列表要遍历 |

### 6.3 ask：多跳推理问答（/kg/ask 的内核）

函数一上来先做一件事：

```python
if not kg_available():
    return { ..., "verdict": "图谱不可用", "graph_available": False, ... }
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `graph_available` 字段 | 区分三种状态 | "连不上"（graph_available=false）≠"查过了没这条知识"（未发现禁忌）≠"有禁忌"——三种状态对调用方语义完全不同，混在一起就是不诚实 |

三条查询对应三跳证据链：

```python
# ① 直连边（一跳）：结论和理由
MATCH (i:Ingredient {name: $ingredient})-[r:CONTRAINDICATED_FOR]->(c:Condition)
WHERE c.name = $condition OR $condition IN c.aka     # 支持别名："高血糖"命中"糖尿病"
RETURN r.level AS level, r.reason AS reason

# ② 营养证据（一跳）：结论的营养学支撑
MATCH (i:Ingredient {name: $ingredient})-[r:RICH_IN]->(n:Nutrient)
RETURN n.name AS nutrient, r.level AS level, n.note AS note

# ③ 受影响菜谱（两跳）：从食材出发沿"入菜"边走
MATCH (i:Ingredient {name: $ingredient})-[:IN_RECIPE]->(rc:Recipe)
RETURN rc.recipe_id AS recipe_id, rc.name AS name, rc.calories AS calories
```

| 查询 | 在做什么 | 为什么这么写 |
|---|---|---|
| ① 用 `WHERE ... OR ... IN c.aka` | 名字或别名都命中 | 用户输入是自由的，节点上的 aka 数组兜住口语说法 |
| ② 无禁忌也返回营养 | 证据独立于结论 | "西红柿对痛风未发现禁忌 + 西红柿富含维C"——营养事实本身有价值 |
| ③ 只走两跳，不展开 | 拿菜谱清单就停 | 多跳不是越深越好：第 3 跳（菜谱→其它食材）对回答这个问题没有增益，**深度服务于问题** |

结论综合的优先级：

```python
if contra:                          # 有禁忌边：禁忌优先
    verdict = "不建议食用" if level == "避免" else "建议控制食用量"
elif benefit:                       # 无禁忌有推荐边
    verdict = "推荐食用"
else:                               # 什么边都没有
    verdict = "未发现禁忌关联"       # 🔑 不说"可以吃"，说"没查到"——未收录≠安全
```

**禁忌优先于推荐**：如果一个食材对某状况既有推荐边又有禁忌边（策展失误或特殊情况），按禁忌算——推理系统的错误应当偏向"过度谨慎"而不是"过度许可"。

---

## 七、init_kg.py：UNWIND 批量建图逐行解释

### 7.1 名字归一化（建图的第一颗扣子）

```python
def normalize_ingredient(raw: str) -> str:
    return re.split(r"\s+", raw.strip())[0]     # "鸡蛋 3个" -> "鸡蛋"
```

和 kg.py 查询侧、ranker.py 打分侧用的是**同一个正则**——三处规则一致，名字才对得上。这颗扣子扣错，整张图白建。

### 7.2 UNWIND 批量写（为什么不是 for 循环逐条写）

```python
session.run(
    """
    UNWIND $rows AS row          // 把传入的列表"展开"成逐行：60 条数据变 60 个 row
    MERGE (rc:Recipe {recipe_id: row.recipe_id})
      SET rc.name = row.name, ...
    WITH row, rc                 // 把 row 和刚 MERGE 的 rc 一起带进下一段
    UNWIND row.items AS item     // 再展开：每个菜谱的食材清单逐个 item
    MERGE (i:Ingredient {name: item.name})
    MERGE (i)-[rel:IN_RECIPE]->(rc)
      SET rel.amount = item.amount
    """,
    rows=recipe_rows,
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `UNWIND $rows` | 列表参数展开成行 | 一次网络往返写 60 菜谱 + 332 条入菜关系；逐条跑要 392 次往返——**差两个数量级** |
| `MERGE` 而非 `CREATE` | 存在则复用，不存在才建 | **幂等**：脚本重复跑不产生重复数据；改了 kg_facts 再跑一遍就是增量更新 |
| `MERGE (i:Ingredient {name: ...})` | 按名字 MERGE | MERGE 依据花括号里的属性——名字是食材的唯一键，同一食材在 24 道菜里出现也只有一个节点 |
| `SET rc.name = ...` | MERGE 后补属性 | MERGE 只保证节点存在，属性要 SET 补（MERGE 上的旧节点也会被刷新成最新数据） |
| `WITH row, rc` | 管道里传递变量 | Cypher 的链式查询：上一段的变量默认不自动带下一段，要显式 WITH |

### 7.3 为什么建图脚本不做降级

```python
driver.verify_connectivity()      # 连不上直接抛错退出
```

和 kg.py 的"吞掉一切异常"相反——建图是**运维动作**不是在线服务：连不上就该大声失败让人来修，静默降级反而把错误埋进"图怎么建完了少数据"的迷雾里。**降级策略要分场景：在线查询降级保可用，离线构建快败保正确。**

### 7.4 --rebuild 的清空语句

```cypher
MATCH (n) DETACH DELETE n        // 删所有节点，DETACH = 先断开它们的关系再删
```

不带 DETACH 直接 DELETE 会因为"还有关系连着"而失败——Neo4j 不允许删除有关系牵着的节点。

---

## 八、ranker.py 三处改动逐行解释

### 8.1 导入区与辅助函数

```python
from app_my.core import kg as kg_module   # 导入整个模块而非 from kg import xxx
_ING_RE = re.compile(r"\s+")              # 预编译正则（模块加载时编译一次）

def _ingredient_names(recipe: dict) -> List[str]:
    return [_ING_RE.split(x.strip())[0] for x in recipe.get("ingredients") or [] if x.strip()]
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `import kg as kg_module` | 按模块导入 | 单测要 `monkeypatch.setattr(kg_module, "get_condition_guidance", ...)`——按名导入的引用 patch 不掉（阶段 2 E4 的教训：**patch 要打在使用现场**） |
| `_ING_RE` 预编译 | 正则只编译一次 | 和建图/查询侧同一颗"扣子"，三处共用同一规则 |

### 8.2 rank_recipes：一次查全，不逐菜谱查

```python
conditions = kg_module.derive_conditions(profile)      # 画像 → 状况（普通用户返回 []）
kg_avoid, kg_prefer = ({}, {})
if conditions:                                         # 有状况才查图（短路：普通用户零开销）
    kg_avoid, kg_prefer = kg_module.get_condition_guidance(conditions)
...
score, reasons = _score_recipe(r, profile, kg_avoid, kg_prefer)   # 映射透传给打分函数
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 图谱查询放在 for 循环**外面** | 一次查全 | 60 道菜逐道查图 = 60 次往返；先查全映射，循环里只做字典查找 O(1)——**把 I/O 和计算分开** |
| `kg_avoid, kg_prefer = ({}, {})` 先置空 | 图谱不可用的兜底 | get_condition_guidance 内部降级返回空 map，这里不判空直接往下走——打分维度⑧对空 map 自动跳过 |

### 8.3 打分维度⑧：图谱扣分/加分

```python
if kg_avoid or kg_prefer:                    # 两个 map 都空 = 整段跳过（普通用户/图谱挂了）
    names = set(_ingredient_names(recipe))   # 本道菜的全部食材名（集合，去重）

    worst = None                             # 找"最重的一条禁忌"
    for name in names:
        hit = (kg_avoid or {}).get(name)
        if hit and (worst is None or hit["weight"] > worst["weight"]):
            worst = {**hit, "ingredient": name}
    if worst:
        score -= worst["weight"]             # 避免-8 / 限量-4 / 适量-2
        reasons.append(f"图谱提示：{worst['ingredient']}对{worst['condition']}患者{worst['level']}——{worst['reason']}")

    for name in names:
        hit = (kg_prefer or {}).get(name)
        if hit:
            score += 2
            reasons.append(f"图谱推荐：{name}适合{hit['condition']}人群——{hit['reason']}")
            break                            # 命中一种就够（说明这道菜对该状况友好）
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 禁忌取"最重一条"而非累加 | 一道菜只扣一次 | "土豆焖饭"里土豆+大米都命中，累加扣 -8 会把分数打到没有区分度（全是负分）；**扣分是信号不是惩罚**，够把排序压下去就行 |
| 推荐也只加一次（break） | 对称设计 | 禁忌一条就压、推荐一条就抬——加减分都是"改变相对排序"的手段，不追求精确计分 |
| 理由文本带"图谱提示/推荐"前缀 | 可解释性 | 这个字符串会流进最终报告，用户看到的每条建议都能溯源到图上的一条边 |
| 扣分权重 8/4/2 和"过敏剔除(-∞)"拉开层次 | 软硬约束分级 | 过敏是硬约束直接剔除；禁忌是软约束降权——土豆对糖尿病是"限量"不是"过敏"，处理力度必须不同 |

---

## 九、api/kg.py 与 main.py 改动解释

```python
@router.get("/ask")
async def kg_ask(
    ingredient: str = Query(..., min_length=1, max_length=30, description="食材名，如：土豆"),
    condition: str = Query(..., min_length=1, max_length=30, description="健康状况名，如：糖尿病/痛风/高血压"),
):
    return kg_module.ask(ingredient.strip(), condition.strip())
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `Query(..., min_length=1, max_length=30)` | 必填 + 长度限制 | 空字符串和超长输入在入口就挡掉（422），不用等图查询才发现问题 |
| `.strip()` | 去首尾空格 | "土豆 "查不到节点——用户从浏览器地址栏粘贴参数时最常见的隐形坑 |
| 接口层**零业务逻辑** | 直接转发 kg.ask | 推理逻辑全在 core 层，接口只是壳——和 billing 接口同款分层：将来加缓存/限流，接口层加，core 不动 |

`/kg/*` 没有加任何鉴权代码却自动受 JWT 保护——因为 `AuthMiddleware` 的默认策略是"**白名单之外全拦截**"（默认拒绝，显式放行），新增路径天生安全。这是阶段 4 那版中间件设计埋下的红利。

main.py 的改动只有两行（import + include_router），外加清理了阶段 2 施工遗留的一行重复导入（无害但不整洁）。

---

## 十、测试设计解释：13 个单测在守护什么

| 测试组 | 个数 | 守护的不变量 |
|---|---|---|
| TestDeriveConditions | 4 | 画像→状况的映射规则：控糖映射、普通不映射、显式状况透传、重叠去重 |
| TestKgFactsAlignment | 3 | **知识数据质量**：结构完整、level 必须是三档之一（写错等级=静默不扣分）、食材名与菜谱库对齐 |
| TestRankerWithKg | 6 | **打分行为**：限量 -4 带理由、避免 -8 更重、双重命中只扣一次、推荐 +2、无状况零查询、端到端排序翻转 |

三个值得说的设计：

```python
def test_rank_recipes_without_conditions_skips_kg(self, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("无健康状况时不应查询图谱")   # 被调用就当失败

    monkeypatch.setattr(kg_module, "get_condition_guidance", _boom)
    ranker.rank_recipes([_recipe()], {"goal": "普通"})
```

| 设计 | 在做什么 | 为什么这么写 |
|---|---|---|
| "炸弹" monkeypatch | 把图谱查询换成"一调用就炸" | 普通的 mock 只能验证"调了什么"，炸弹能验证"**没调**"——普通用户的性能承诺（零图谱开销）靠它守护 |
| `monkeypatch.setattr(kg_module, ...)` | patch 源模块 | ranker 里是 `kg_module.get_condition_guidance(...)` 按模块取的，patch 模块属性才拦得住（阶段 2 P3 教训的第三次应用） |
| 集成测试单独 `kg` 标记 | 与 llm 标记同款机制 | 图谱测试依赖容器+建图（环境三件套），不满足时默认套件照常全绿——**环境依赖测试永远不该拖累日常回归** |

---

## 十一、Cypher 语法速查（本阶段用到的）

```text
(n:Label)                  节点模式：变量 n、标签 Label（类似"类型"）
(n {name: '土豆'})          按属性匹配节点
(n)-[r:REL]->(m)           关系模式：方向必须画出来（图是有向图！）
MATCH ... WHERE ... RETURN  与 SQL 对应：FROM ... WHERE ... SELECT
$参数名                     占位参数（防注入，等价 SQL 的 %s）
IN                         集合成员判断（支持节点属性数组：$x IN c.aka）
UNWIND $rows AS row        把列表参数展开成行（批量的核心）
MERGE (n:Label {key: v})   存在则匹配，不存在则创建（幂等写入）
SET n.prop = value         设置属性（MERGE 后补属性用）
WITH a, b                  管道传递变量到下一段（Cypher 的"分号"）
DETACH DELETE n            先断关系再删节点
labels(n)[0]               节点的第一个标签（统计用）
type(r)                    关系的类型名（统计用）
```

> 🟡 方向很重要：本阶段建的边是 `(:Ingredient)-[:IN_RECIPE]->(:Recipe)`（食材指向菜谱）。查询反着写 `(rc)-[:IN_RECIPE]->(i)` 查不到任何东西——图查询的方向必须和建模一致。

---

## 十二、常见疑问

**Q1：为什么选 Neo4j 而不是 PostgreSQL 里建两张表存关系？**
答：对当前 500 条关系，PG 完全够。但图的查询会变深："痛风患者忌口的食材、参与的高分菜谱、那些菜谱里还有什么替代食材"——图上三跳一句 MATCH；SQL 要三层自连接。选型不是为今天的数据量，是为**关系查询的复杂度增长方式**。另外 Neo4j Browser 的可视化（验收第 12 条）对调试知识数据的帮助立竿见影。

**Q2：图谱挂了推荐会变差吗？**
答：会退回"无图谱"版本（v2.0 的行为），不会挂掉、不会变错——降级路径是"少一路加分项"，主流程的其他 7 个打分维度照常。这正是"增强不是依赖"设计原则的含义。可以亲手验证：`docker stop ai_chief_neo4j` 后对话照常，日志出现"图谱推理降级为跳过"。

**Q3：为什么不把 kg_facts 直接写进 Neo4j，还要过一道 JSON 文件？**
答：JSON 是**知识源**（source of truth），图是**查询加速结构**。知识放在人可读可 review 的文件里，改知识=改 JSON+重跑建图；图永远是可丢弃可重建的（--rebuild）。反过来把知识直接录进图，图就成了不可再生的一次性资产——改一条禁忌要进图改，没法 diff、没法 review。

**Q4：这不就是一张硬编码的表吗，跟 if-else 写死有什么区别？**
答：区别在三层。① 数据与逻辑分离：禁忌数据在 JSON/图里，扣分逻辑在 kg.py 里——加一种新状况（如"脂肪肝"）不改一行代码；② 一份数据两处消费：重排打分和 /kg/ask 问答读的是同一张图，天然一致；③ 多跳能力：单点查询（土豆对糖尿病）只是入门，"忌口食材→受影响菜谱→替代推荐"的链式推理才是图的不可替代性，if-else 写到第二层就会失控。

**Q5：面试官问"你的图谱多大"会不会显得太小？**
答：216 节点/498 关系确实不大——但简历叙事的重点从来不是规模，是**架构**："向量管相似、图谱管关系推理的互补架构 + 图谱不可用时的优雅降级 + 知识与逻辑分离 + 数据对齐的单测守护"。这四个点每个都能深聊十分钟。真要扩量，kg_facts 加满 6 种状况×50 食材就是几千条边——但**宁可小而准，不可大而错**，这本身就是可讲的工程判断。

**Q6：enable_thinking 那个坑（阶段 2）跟本阶段有关系吗？**
答：有——图谱推理恰恰是"**不需要思考模式**"的反例之外的正面案例：多跳推理我们做在**图上**（确定性遍历）而不是让 LLM"想"，所以又快又可解释。什么时候值得给 LLM 开思考模式？开放性规划类任务（如"给我排一周的控糖食谱"）——那可能是未来阶段的事。
