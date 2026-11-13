# AI 私厨 v3.0 · 阶段 3：Neo4j 知识图谱 + 多跳推理（最终完整版）

> **本阶段目标**：给系统装上"关系推理"能力——向量检索（RAG）只能回答"哪些菜谱和你的食材相似"，回答不了"**糖尿病患者能不能吃土豆、为什么、哪些菜要小心**"。本阶段用 Neo4j 构建「食材-营养-菜谱-禁忌」知识图谱，把多跳推理接入推荐重排（rank 节点）并开放 `/kg/ask` 推理问答接口，全部结论有图上的边作依据，**可解释、不幻觉**。
>
> - 本阶段工作量：1~2 个晚上
> - 收官状态（2026-09-29）：**施工一次通过**，commit 1653d52 已推送到 feat/v3-stage3
> - 测试基线：默认套件 39 → **52 passed**，图谱集成 4/4，真实 LLM 流式 1/1
> - 图谱规模：**216 节点 / 498 关系**（142 食材 + 60 菜谱 + 8 营养素 + 6 状况）
> - 🔴 本阶段铁律：`F:\pycharm_aiprogram\ai_sichu`（v2.0）一个字节未动
> - 🟡 本阶段**不需要改 .env**（Neo4j 三项配置默认值就是容器里的值）

---

## 目录

- [0. 使用说明与颜色约定](#0-使用说明与颜色约定)
- [1. 本阶段要干什么（先看懂再动手）](#1-本阶段要干什么先看懂再动手)
- [2. 第一步：建分支](#2-第一步建分支)
- [3. 第二步：compose 加 Neo4j 服务并启动](#3-第二步compose-加-neo4j-服务并启动)
- [4. 第三步：装 neo4j Python 驱动](#4-第三步装-neo4j-python-驱动)
- [5. 第四步：config.py 加三行](#5-第四步configpy-加三行)
- [6. 第五步：新建 kg_facts.json（图谱的知识来源）](#6-第五步新建-kg_factsjson图谱的知识来源)
- [7. 第六步：新建 core/kg.py（查询封装）](#7-第六步新建-corekgpy查询封装)
- [8. 第七步：新建 scripts/init_kg.py 并建图](#8-第七步新建-scriptsinit_kgpy-并建图)
- [9. 第八步：改 ranker.py（三处）](#9-第八步改-rankerpy三处)
- [10. 第九步：新建 api/kg.py 并注册路由](#10-第九步新建-apikgpy-并注册路由)
- [11. 第十步：新增测试文件并改 pytest.ini](#11-第十步新增测试文件并改-pytestini)
- [12. 第十一步：跑测试](#12-第十一步跑测试)
- [13. 验收清单](#13-验收清单)
- [14. 错误对照表](#14-错误对照表)
- [15. 不做清单](#15-不做清单)
- [16. 提交 Gitee 与 PR 描述](#16-提交-gitee-与-pr-描述)
- [17. 收官总结](#17-收官总结)

---

## 0. 使用说明与颜色约定

- 每章都是「**操作 → 验证**」两段式：做完操作立刻跑验证，绿了再进下一章。
- 命令给出 **PowerShell** 版本（Git Bash 用户自行对照，效果一样）。
- 颜色标注：🟢新增 / 🔵修改 / 🟣补充 / 🟡提醒 / 🔴警告。
- Neo4j 是本阶段唯一新增的中间件：内存占用约 600MB（已配好上限），用哪个阶段起哪个，平时 `stop` 不删。

---

## 1. 本阶段要干什么（先看懂再动手）

### 1.1 向量检索 vs 图谱：一张图看懂分工

```text
用户问："糖尿病患者能不能吃土豆？"

RAG（向量检索）的做法：                 图谱（多跳推理）的做法：
  把问题变成向量，                       沿着图上的边走：
  找"语义相似"的菜谱文档……                ① 土豆 ─[禁忌:限量,GI值较高]→ 糖尿病     （直连边，有理由）
  ❌ 召回的是"土豆相关菜谱"，             ② 土豆 ─[富含:高]→ 碳水                 （营养证据）
     答非所问                            ③ 土豆 ─[入菜]→ 地三鲜 / 酸辣土豆丝      （受影响菜谱）
                                         ✅ 结论：建议控制食用量，理由和影响范围都在图上
```

**一句话**：向量管"相似度"，图谱管"关系推理"——两者是互补架构，不是替代关系。

### 1.2 图模型（四类节点 + 四类关系）

```text
   (:Ingredient)──IN_RECIPE{amount}──►(:Recipe)          食材 → 菜谱（332 条）
   (:Ingredient)──RICH_IN{level}────►(:Nutrient)         食材 → 营养素（80 条）
   (:Ingredient)──CONTRAINDICATED_FOR{level,reason}──►(:Condition)   禁忌（51 条）
   (:Ingredient)──BENEFICIAL_FOR{reason}──►(:Condition)             推荐（35 条）
```

节点规模：Ingredient 142 / Recipe 60 / Nutrient 8 / Condition 6——**216 节点 / 498 关系**（2026-09-28 实测）。

### 1.3 知识从哪来（重要：不编数据）

- **菜谱与食材**：来自已有的 `recipes.json`（60 道菜，真实数据）。
- **营养与禁忌**：新增 `kg_facts.json`（人工策展的常见营养学常识：6 种健康状况的忌口/推荐清单 + 8 类营养素富集关系）。
- 🔴 **诚实原则**：图里没有边就回答"未发现禁忌关联"，绝不编造。知识图谱的价值恰恰在于"知道什么"和"不知道什么"一样清楚。
- 🟡 kg_facts 内容为科普级常识整理，**不构成医疗建议**（文件头部有声明）。

### 1.4 接入后的效果（实测演示）

同一批菜谱，不同画像的重排结果（真实跑出来的数字）：

```text
== 普通用户 ==                          == 控糖用户（goal=控糖 → 图谱按糖尿病原则） ==
  地三鲜           0.5 分                 香煎鸡胸肉配西兰花   2.5 分  ← 图谱推荐：西兰花低GI
  酸辣土豆丝       0.5 分                 地三鲜            -3.5 分  ← 图谱提示：土豆对糖尿病限量
  香煎鸡胸肉配西兰花 0.5 分                酸辣土豆丝        -3.5 分  ← 图谱提示：土豆对糖尿病限量
```

推荐结果**从"千人一面"变成"因人而异且有理有据"**——理由会随菜谱传给输出节点，最终报告里能看到。

### 1.5 文件清单

| # | 文件 | 类型 |
|---|---|---|
| 1 | `docker/docker-compose.v3.yml` | 🔵 修改（加 neo4j 服务） |
| 2 | `requirements.txt` | 🔵 修改（加 1 行） |
| 3 | `app_my/core/config.py` | 🔵 修改（加 3 行） |
| 4 | `app_my/knowledge/data/kg_facts.json` | 🟢 新建（图谱知识） |
| 5 | `app_my/core/kg.py` | 🟢 新建（查询封装） |
| 6 | `scripts/init_kg.py` | 🟢 新建（建图脚本） |
| 7 | `app_my/agents/ranker.py` | 🔵 修改（三处） |
| 8 | `app_my/api/kg.py` | 🟢 新建（推理接口） |
| 9 | `main.py` | 🔵 修改（2 处，顺手清理一行重复导入） |
| 10 | `pytest.ini` | 🔵 修改（加 kg 标记） |
| 11 | `tests/unit/test_kg_reasoning.py` | 🟢 新建（13 例单测） |
| 12 | `tests/integration/test_kg_api.py` | 🟢 新建（4 例集成，kg 标记） |

---

## 2. 第一步：建分支

**操作**：

```powershell
cd F:\pycharm_aiprogram\ai_chief
git checkout master
git pull origin master
git checkout -b feat/v3-stage3
```

**验证**：

```powershell
git branch --show-current        # 应输出 feat/v3-stage3
```

---

## 3. 第二步：compose 加 Neo4j 服务并启动

**操作**：打开 `docker/docker-compose.v3.yml`，在 `redis:` 服务块**后面**（`volumes:` 之前）加入下面这段，并在文件末尾的 `volumes:` 区加一行：

```yaml
  neo4j:
    image: docker.m.daocloud.io/library/neo4j:5-community   # DaoCloud 源（镜像已在本地，无需重拉）
    container_name: ai_chief_neo4j           # 容器名沿用 ai_chief_* 前缀
    restart: unless-stopped
    environment:
      NEO4J_AUTH: neo4j/ai_chief_kg          # 账号/密码，与 config.py 的默认值一致
      NEO4J_server_memory_heap_max__size: 512m     # 堆内存上限（个人项目够用）
      NEO4J_server_memory_pagecache_size: 128m     # 图数据缓存（216 节点绰绰有余）
    ports:
      - "7474:7474"                          # HTTP：浏览器里看图的 Neo4j Browser
      - "7687:7687"                          # Bolt：代码查询用的协议端口
    volumes:
      - ai_chief_neo4jdata:/data             # v3 独立数据卷（建图结果重启不丢）
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ai_chief_kg 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 20
```

文件末尾 `volumes:` 区改成：

```yaml
volumes:
  ai_chief_pgdata:
  ai_chief_redisdata:
  ai_chief_neo4jdata:      # 🟢 v3阶段3 新增
```

**操作**（启动，项目根目录执行）：

```powershell
docker compose -f docker/docker-compose.v3.yml up -d
```

**验证**：

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

应看到 `ai_chief_neo4j` 变成 `Up ... (healthy)`（首次启动要等 30~60 秒，健康检查是 20 次重试）。浏览器打开 `http://localhost:7474`，用 `neo4j / ai_chief_kg` 登录，能看到 Neo4j Browser 界面即成功。

---

## 4. 第三步：装 neo4j Python 驱动

**操作**：

```powershell
cd F:\pycharm_aiprogram\ai_chief
.venv3\Scripts\Activate.ps1
uv pip install neo4j --python .venv3\Scripts\python.exe -i https://pypi.tuna.tsinghua.edu.cn/simple
```

然后在 `requirements.txt` 末尾加一行（保持依赖清单完整，以后重建 venv 不缺件）：

```text
neo4j==6.3.1
```

**验证**：

```powershell
python -c "import neo4j; print(neo4j.__version__)"
```

应输出：`6.3.1`

---

## 5. 第四步：config.py 加三行

**操作**：打开 `app_my/core/config.py`，找到 Redis 配置区（`RATE_LIMIT_USER_PER_MINUTE` 那行下面），插入：

```python
    # ============================================================
    # Neo4j 知识图谱（v3阶段3 新增；默认值与 docker-compose 里的容器一致）
    # ============================================================
    NEO4J_URI: str = "bolt://localhost:7687"   # Bolt 协议端口（查询用）
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "ai_chief_kg"
```

**验证**：

```powershell
python -c "from app_my.core.config import settings; print(settings.NEO4J_URI)"
```

应输出：`bolt://localhost:7687`

> 🟡 不需要改 .env——默认值就是容器里的值。生产部署时在 .env 里覆盖 `NEO4J_PASSWORD` 即可。

---

## 6. 第五步：新建 kg_facts.json（图谱的知识来源）

**操作**：新建 `app_my/knowledge/data/kg_facts.json`，完整复制：

```json
{
  "_说明": "AI私厨 v3.0 阶段3 知识图谱策展数据。三种事实：(1)conditions 每种健康状况的忌口/推荐食材（含理由）；(2)nutrients 食材-营养素富集关系；(3)全部食材名都来自 recipes.json 的真实食材（名字对齐才能连上图）。内容为常见营养学常识整理，仅供科普参考，不构成医疗建议。",
  "conditions": {
    "糖尿病": {
      "aka": ["高血糖", "血糖偏高", "控糖"],
      "avoid": [
        {"name": "土豆", "level": "限量", "reason": "GI值较高，升血糖快，建议控制份量"},
        {"name": "红心红薯", "level": "限量", "reason": "GI值中高，大量食用升血糖快"},
        {"name": "紫薯", "level": "限量", "reason": "淀粉含量高，需计入主食量"},
        {"name": "大米", "level": "限量", "reason": "精制碳水，GI值高，建议粗细搭配"},
        {"name": "米饭", "level": "限量", "reason": "精制碳水，GI值高，建议换成杂粮饭"},
        {"name": "隔夜米饭", "level": "限量", "reason": "精制碳水，GI值高"},
        {"name": "面条", "level": "限量", "reason": "精制碳水，GI值高"},
        {"name": "面粉", "level": "限量", "reason": "精制碳水，建议全麦替代"},
        {"name": "低筋面粉", "level": "限量", "reason": "精制碳水，烘焙食品通常还加糖"},
        {"name": "白糖", "level": "避免", "reason": "添加糖，直接升高血糖"},
        {"name": "冰糖", "level": "避免", "reason": "添加糖，直接升高血糖"},
        {"name": "细砂糖", "level": "避免", "reason": "添加糖，直接升高血糖"},
        {"name": "糖粉", "level": "避免", "reason": "添加糖，直接升高血糖"},
        {"name": "可乐", "level": "避免", "reason": "含糖饮料，一罐约35克添加糖"},
        {"name": "甜玉米", "level": "适量", "reason": "含糖量高于普通蔬菜，需计入主食量"}
      ],
      "prefer": [
        {"name": "西兰花", "reason": "低GI且富含膳食纤维，血糖友好"},
        {"name": "即食燕麦", "reason": "低GI主食，缓释碳水"},
        {"name": "藜麦", "reason": "低GI全谷物，优质碳水来源"},
        {"name": "黑木耳", "reason": "富含膳食纤维，延缓糖吸收"},
        {"name": "油麦菜", "reason": "低热量绿叶菜，几乎不影响血糖"},
        {"name": "小白菜", "reason": "低热量绿叶菜，几乎不影响血糖"},
        {"name": "生菜", "reason": "低热量绿叶菜，几乎不影响血糖"},
        {"name": "冬瓜", "reason": "低热量低糖蔬菜"}
      ]
    },
    "高血压": {
      "aka": ["血压偏高"],
      "avoid": [
        {"name": "盐", "level": "限量", "reason": "钠摄入过多是高血压首要饮食因素"},
        {"name": "生抽", "level": "限量", "reason": "高钠酱料，需折算进全天盐量"},
        {"name": "老抽", "level": "限量", "reason": "高钠酱料"},
        {"name": "生抽老抽", "level": "限量", "reason": "高钠酱料"},
        {"name": "蚝油", "level": "限量", "reason": "高钠酱料"},
        {"name": "蒸鱼豉油", "level": "限量", "reason": "高钠酱料"},
        {"name": "郫县豆瓣酱", "level": "限量", "reason": "高钠高盐发酵酱料"},
        {"name": "甜面酱", "level": "限量", "reason": "高钠酱料"},
        {"name": "豆豉", "level": "限量", "reason": "高钠发酵豆制品"},
        {"name": "干黄酱", "level": "限量", "reason": "高钠酱料"},
        {"name": "火腿", "level": "避免", "reason": "加工肉制品，钠含量极高"},
        {"name": "皮蛋", "level": "限量", "reason": "含钠较高"},
        {"name": "虾皮", "level": "限量", "reason": "含钠较高"}
      ],
      "prefer": [
        {"name": "冬瓜", "reason": "钾含量丰富且低钠，经典利水蔬菜"},
        {"name": "黑木耳", "reason": "富含钾和膳食纤维"},
        {"name": "木耳", "reason": "富含钾和膳食纤维"},
        {"name": "油麦菜", "reason": "绿叶菜富含钾，有助排钠"},
        {"name": "小白菜", "reason": "绿叶菜富含钾"},
        {"name": "香蕉", "reason": "高钾水果（本库未用到，预留）"}
      ]
    },
    "痛风": {
      "aka": ["尿酸偏高", "高尿酸"],
      "avoid": [
        {"name": "啤酒", "level": "避免", "reason": "酒精抑制尿酸排泄，啤酒本身含嘌呤"},
        {"name": "大闸蟹", "level": "避免", "reason": "蟹黄嘌呤极高，急性期禁忌"},
        {"name": "鲜活基围虾", "level": "限量", "reason": "中高嘌呤海鲜，急性期避免"},
        {"name": "鲜虾", "level": "限量", "reason": "中高嘌呤海鲜"},
        {"name": "虾仁", "level": "限量", "reason": "中高嘌呤海鲜"},
        {"name": "香菇", "level": "限量", "reason": "菌菇类嘌呤偏高，干制品更高"},
        {"name": "猪肋排", "level": "限量", "reason": "浓肉汤嘌呤高，避免久炖喝汤"},
        {"name": "花生米", "level": "适量", "reason": "坚果嘌呤中等，且油脂高影响尿酸排泄"}
      ],
      "prefer": [
        {"name": "鸡蛋", "reason": "嘌呤极低的优质蛋白来源"},
        {"name": "牛奶", "reason": "低嘌呤且有助于尿酸排泄"},
        {"name": "酸奶", "reason": "低嘌呤奶制品"},
        {"name": "大白菜", "reason": "低嘌呤蔬菜"},
        {"name": "冬瓜", "reason": "低嘌呤且利水"}
      ]
    },
    "高血脂": {
      "aka": ["血脂偏高"],
      "avoid": [
        {"name": "五花肉", "level": "限量", "reason": "饱和脂肪含量高"},
        {"name": "带皮五花肉", "level": "避免", "reason": "皮部饱和脂肪极高"},
        {"name": "五花肉丁", "level": "限量", "reason": "饱和脂肪含量高"},
        {"name": "猪肉末", "level": "限量", "reason": "肥瘦混合，饱和脂肪较高"},
        {"name": "黄油", "level": "限量", "reason": "乳脂 saturated fat 高"},
        {"name": "淡奶油", "level": "限量", "reason": "乳脂含量高"},
        {"name": "蛋黄", "level": "适量", "reason": "胆固醇较高，健康人每天1个无妨，血脂高者酌减"}
      ],
      "prefer": [
        {"name": "洋葱", "reason": "含硫化物，有助血脂代谢"},
        {"name": "即食燕麦", "reason": "β-葡聚糖有助于降低胆固醇"},
        {"name": "西兰花", "reason": "膳食纤维丰富"},
        {"name": "黑木耳", "reason": "膳食纤维丰富"},
        {"name": "鲈鱼", "reason": "白肉鱼，脂肪结构优于红肉"},
        {"name": "龙利鱼柳", "reason": "低脂白肉鱼"}
      ]
    },
    "慢性肾病": {
      "aka": ["肾功能不全"],
      "avoid": [
        {"name": "土豆", "level": "限量", "reason": "高钾食材，肾功能下降时排钾能力减弱"},
        {"name": "红心红薯", "level": "限量", "reason": "高钾食材"},
        {"name": "紫薯", "level": "限量", "reason": "高钾食材"},
        {"name": "嫩豆腐", "level": "限量", "reason": "植物蛋白需控制在营养师指导下定量"},
        {"name": "老豆腐", "level": "限量", "reason": "植物蛋白需定量"},
        {"name": "蛋清", "level": "适量", "reason": "优质蛋白但需计入全天蛋白总量"},
        {"name": "火腿", "level": "避免", "reason": "高钠高磷加工肉"}
      ],
      "prefer": [
        {"name": "冬瓜", "reason": "低钾低蛋白蔬菜"}
      ]
    },
    "缺铁性贫血": {
      "aka": ["贫血", "缺铁"],
      "avoid": [
        {"name": "浓茶", "level": "避免", "reason": "鞣酸抑制铁吸收（本库未用到，预留）"}
      ],
      "prefer": [
        {"name": "牛腩", "reason": "红肉富含血红素铁，吸收率高"},
        {"name": "牛里脊", "reason": "红肉富含血红素铁"},
        {"name": "猪里脊", "reason": "红肉含血红素铁"},
        {"name": "猪肋排", "reason": "红肉含血红素铁"},
        {"name": "羊腿肉", "reason": "红肉富含血红素铁"},
        {"name": "鸭肉", "reason": "含铁高于一般白肉"},
        {"name": "黑木耳", "reason": "植物性铁来源，搭配维C食物促吸收"},
        {"name": "红枣", "reason": "传统补血食材，植物性铁（非血红素）"},
        {"name": "枸杞", "reason": "含铁的药食同源食材"}
      ]
    }
  },
  "nutrients": {
    "蛋白质": {
      "high": ["鸡蛋", "鸡胸肉", "牛奶", "酸奶", "虾仁", "鲜虾", "鲜活基围虾", "鲈鱼", "龙利鱼柳", "鲫鱼", "牛腩", "牛里脊", "猪里脊", "猪肋排", "羊腿肉", "鸭肉", "嫩豆腐", "老豆腐", "黄豆芽", "鸡翅中", "蛋清"],
      "note": "优质蛋白来源，增肌人群核心营养素"
    },
    "铁": {
      "high": ["牛腩", "牛里脊", "羊腿肉", "猪里脊", "猪肋排", "鸭肉", "黑木耳", "红枣", "枸杞"],
      "note": "红肉为血红素铁（吸收率高），木耳红枣为非血红素铁（需搭配维C）"
    },
    "钾": {
      "high": ["土豆", "红心红薯", "紫薯", "甜玉米", "西兰花", "冬瓜"],
      "note": "高血压人群友好（促排钠），但肾病患者需限制"
    },
    "维生素C": {
      "high": ["西兰花", "青椒", "螺丝椒", "西红柿", "圣女果", "油麦菜", "小白菜", "大白菜", "生菜"],
      "note": "促进铁吸收，尤其搭配植物性铁食物"
    },
    "膳食纤维": {
      "high": ["即食燕麦", "藜麦", "黑木耳", "木耳", "西兰花", "紫薯", "红心红薯", "甜玉米", "金针菇", "香菇"],
      "note": "延缓糖吸收、增强饱腹感"
    },
    "嘌呤": {
      "high": ["啤酒", "大闸蟹", "鲜活基围虾", "鲜虾", "虾仁", "香菇", "猪肋排"],
      "note": "嘌呤代谢生成尿酸，痛风/高尿酸人群需限制"
    },
    "饱和脂肪": {
      "high": ["五花肉", "带皮五花肉", "五花肉丁", "猪肉末", "黄油", "淡奶油"],
      "note": "摄入过多升高血脂"
    },
    "碳水": {
      "high": ["大米", "米饭", "隔夜米饭", "面条", "面粉", "低筋面粉", "土豆", "红心红薯", "紫薯", "甜玉米", "即食燕麦", "藜麦"],
      "note": "燕麦藜麦为低GI优质碳水，精米面土豆红薯为高GI碳水"
    }
  }
}
```

**验证**：

```powershell
python -c "import json; d=json.load(open('app_my/knowledge/data/kg_facts.json', encoding='utf-8')); print(len(d['conditions']), '种状况,', len(d['nutrients']), '类营养素')"
```

应输出：`6 种状况, 8 类营养素`

> 🟡 **为什么食材名要一字不差**：图谱最经典的坑就是"两边命名不齐"——知识里写"马铃薯"、菜谱里写"土豆"，这条边永远查不到。本文件的全部食材名都是从 recipes.json 里逐个核对过的（"香蕉""浓茶"两处标注了"预留"，单测里有专门的对齐校验）。

---

## 7. 第六步：新建 core/kg.py（查询封装）

**操作**：新建 `app_my/core/kg.py`，完整复制：

```python
# app_my/core/kg.py
"""
阶段 3（v3.0）：知识图谱查询封装——向量检索管"相似"，图谱管"关系推理"

为什么需要图谱（向量检索做不到的事）：
    RAG 检索"土豆"能召回土豆相关菜谱（相似度），
    但回答不了"糖尿病患者能不能吃土豆、为什么、哪些菜要小心"——
    这是关系推理：Condition-(禁忌)->Ingredient-(入菜)->Recipe，
    三跳路径上每一跳都是明确的边，答案有据可查（区别于模型的"幻觉式回答"）。

设计三原则：
1. 图谱是增强不是依赖：Neo4j 挂了/没建图，所有查询返回空结果并记日志，
   主流程（对话/推荐）照常工作——图谱只在可用时"加分"，永远不"挡路"。
2. 查询收口：所有 Cypher 写在本模块，业务代码（ranker/api）不碰图查询语法，
   换图数据库时只改这里。
3. 诚实推理：图里没有边就回答"未发现禁忌关联"，不编造——
   知识图谱的价值恰恰在于"知道什么"和"不知道什么"一样清楚。

图模型（由 scripts/init_kg.py 构建）：
    (:Ingredient {name})-[:IN_RECIPE {amount}]->(:Recipe {recipe_id, name, ...})
    (:Ingredient)-[:RICH_IN {level: 高}]->(:Nutrient {name})
    (:Ingredient)-[:CONTRAINDICATED_FOR {level, reason}]->(:Condition {name, aka})
    (:Ingredient)-[:BENEFICIAL_FOR {reason}]->(:Condition {name, aka})
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app_my.core.config import settings
from app_my.core.logging import logger

# 禁忌等级 -> 扣分力度（ranker 用；等级语义：避免=能不吃就不吃，限量/适量=控制份量）
LEVEL_WEIGHT = {"避免": 8, "限量": 4, "适量": 2}

# 用户画像的"目标"到图谱"健康状况"的映射：控糖目标的人群按糖尿病饮食原则对待
GOAL_TO_CONDITION = {"控糖": "糖尿病"}

_driver = None            # 驱动单例（惰性创建）
_driver_failed = False    # 曾连接失败就不再反复尝试（避免每次请求都等超时）


def _get_driver():
    """惰性创建 Neo4j 驱动单例。连接失败标记 _driver_failed，后续直接放弃。"""
    global _driver, _driver_failed
    if _driver is not None:
        return _driver
    if _driver_failed:
        return None
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            connection_timeout=5,           # 连不上 5 秒内放弃，不拖慢主流程
            max_connection_pool_size=4,     # 个人项目用不了多少并发连接
        )
        driver.verify_connectivity()        # 立刻验证一次，失败走 except
        _driver = driver
        logger.info(f"kg: 已连接 Neo4j（{settings.NEO4J_URI}）")
        return _driver
    except Exception as exc:
        _driver_failed = True
        logger.warning(f"kg: Neo4j 不可用（{type(exc).__name__}: {exc}），图谱推理降级为跳过")
        return None


def kg_available() -> bool:
    """图谱当前是否可用（ranker/api 层用它决定走图谱还是跳过）"""
    return _get_driver() is not None


def _run(cypher: str, **params) -> List[dict]:
    """
    执行一条只读 Cypher，返回 [{列名: 值}, ...]。

    任何异常（语法/连接/超时）都吞掉返回空列表——
    图谱是增强能力，查询失败不能让推荐/对话挂掉。
    """
    driver = _get_driver()
    if driver is None:
        return []
    try:
        with driver.session() as session:
            return [record.data() for record in session.run(cypher, **params)]
    except Exception as exc:
        logger.warning(f"kg: 查询失败（已降级为空结果）: {exc}")
        return []


def reset_kg_connection() -> None:
    """测试用：丢弃驱动单例和失败标记，下一次访问重新连接"""
    global _driver, _driver_failed
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
    _driver = None
    _driver_failed = False


# ============================================================
# 画像 → 状况（ranker 的入口逻辑）
# ============================================================

def derive_conditions(profile: dict) -> List[str]:
    """
    从用户画像推导"健康状况"列表（图谱 Condition 节点名）。

    两个来源：
      1. goal 字段：控糖 → 糖尿病（画像目标暗含饮食禁忌）
      2. health_conditions 字段：用户显式填写的（如 ["痛风", "高血压"]），
         没有就空——阶段 3 先支持画像文件里手工配置，阶段 9 多租户后开放给前端编辑。
    """
    conds: List[str] = []
    goal = profile.get("goal")
    if goal in GOAL_TO_CONDITION:
        conds.append(GOAL_TO_CONDITION[goal])
    for c in profile.get("health_conditions") or []:
        if c and c not in conds:
            conds.append(c)
    return conds


# ============================================================
# 查询 1：状况 → 忌口/推荐映射（ranker 重排用）
# ============================================================

def get_condition_guidance(conditions: List[str]) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """
    拿到一组健康状况的完整饮食指引。

    返回 (avoid_map, prefer_map)：
        avoid_map  = {食材名: {"condition", "level", "reason", "weight"}}
                     同一食材命中多种状况时取扣分最重的（更保守，安全第一）
        prefer_map = {食材名: {"condition", "reason"}}

    数据来自两条 Cypher（一次取全图相关边，比逐食材查快得多）：
        (:Ingredient)-[c:CONTRAINDICATED_FOR]->(:Condition)
        (:Ingredient)-[b:BENEFICIAL_FOR]->(:Condition)
    """
    if not conditions:
        return {}, {}
    rows = _run(
        """
        MATCH (i:Ingredient)-[r:CONTRAINDICATED_FOR]->(cond:Condition)
        WHERE cond.name IN $conditions
        RETURN i.name AS ingredient, cond.name AS condition,
               r.level AS level, r.reason AS reason
        """,
        conditions=conditions,
    )
    avoid_map: Dict[str, dict] = {}
    for row in rows:
        weight = LEVEL_WEIGHT.get(row["level"], 2)
        old = avoid_map.get(row["ingredient"])
        # 保留扣分更重的那条（多状况冲突时按最严格的算）
        if old is None or weight > old["weight"]:
            avoid_map[row["ingredient"]] = {
                "condition": row["condition"],
                "level": row["level"],
                "reason": row["reason"],
                "weight": weight,
            }

    rows = _run(
        """
        MATCH (i:Ingredient)-[b:BENEFICIAL_FOR]->(cond:Condition)
        WHERE cond.name IN $conditions
        RETURN i.name AS ingredient, cond.name AS condition, b.reason AS reason
        """,
        conditions=conditions,
    )
    prefer_map = {row["ingredient"]: row for row in rows}

    if avoid_map or prefer_map:
        logger.info(
            f"kg: 状况 {conditions} → 忌口 {len(avoid_map)} 项 / 推荐 {len(prefer_map)} 项"
        )
    return avoid_map, prefer_map


# ============================================================
# 查询 2：多跳推理问答（/kg/ask 用，验收场景）
# ============================================================

def ask(ingredient: str, condition: str) -> dict:
    """
    图谱依据的推理问答：「{condition}患者能不能吃 {ingredient}」

    三跳证据链，一次查清：
      ① 直连边   Ingredient-[CONTRAINDICATED_FOR/BENEFICIAL_FOR]->Condition
                 → 结论（避免/限量/推荐）+ 理由（边上带着，人写的策展知识）
      ② 营养证据 Ingredient-[RICH_IN]->Nutrient
                 → 这个结论在营养学上的依据（如 土豆-高碳水）
      ③ 影响菜谱 Ingredient-[IN_RECIPE]->Recipe
                 → 含这个食材的菜谱清单（重排节点同样会压制它们）

    图里没有边 ≠ "能吃"，而是"图谱未收录"——回答里明确说，不编造。
    """
    # 图谱不可用时明确告知（区别于"图谱查过了没这条知识"）
    if not kg_available():
        return {
            "ingredient": ingredient,
            "condition": condition,
            "verdict": "图谱不可用",
            "reason": f"Neo4j 未连接（{settings.NEO4J_URI}），无法推理",
            "nutrients": [],
            "affected_recipes": [],
            "graph_available": False,
        }

    # ① 直连禁忌边
    contra = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[r:CONTRAINDICATED_FOR]->(c:Condition)
        WHERE c.name = $condition OR $condition IN c.aka
        RETURN r.level AS level, r.reason AS reason
        """,
        ingredient=ingredient,
        condition=condition,
    )
    # ① 直连推荐边
    benefit = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[b:BENEFICIAL_FOR]->(c:Condition)
        WHERE c.name = $condition OR $condition IN c.aka
        RETURN b.reason AS reason
        """,
        ingredient=ingredient,
        condition=condition,
    )

    # 结论综合（禁忌优先于推荐——安全第一）
    if contra:
        level = contra[0]["level"]
        verdict = "不建议食用" if level == "避免" else "建议控制食用量"
        reason = contra[0]["reason"]
    elif benefit:
        verdict = "推荐食用"
        reason = benefit[0]["reason"]
    else:
        verdict = "未发现禁忌关联"
        reason = "图谱未收录该食材与该状况的关系，请咨询专业营养师"

    # ② 营养证据（无禁忌时也返回，供参考）
    nutrients = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[r:RICH_IN]->(n:Nutrient)
        RETURN n.name AS nutrient, r.level AS level, n.note AS note
        """,
        ingredient=ingredient,
    )

    # ③ 受影响菜谱（两跳：食材-入菜->菜谱）
    recipes = _run(
        """
        MATCH (i:Ingredient {name: $ingredient})-[:IN_RECIPE]->(rc:Recipe)
        RETURN rc.recipe_id AS recipe_id, rc.name AS name, rc.calories AS calories
        ORDER BY rc.name
        """,
        ingredient=ingredient,
    )

    return {
        "ingredient": ingredient,
        "condition": condition,
        "verdict": verdict,
        "reason": reason,
        "nutrients": nutrients,
        "affected_recipes": recipes,
        "graph_available": True,
    }


def kg_stats() -> dict:
    """图谱规模统计（排障/演示用：节点和关系各多少）"""
    nodes = _run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC")
    rels = _run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC")
    return {"nodes": nodes, "relationships": rels, "available": kg_available()}
```

**验证**（此时还没建图，验证的是"连不上也能优雅降级"）：

```powershell
python -c "from app_my.core.kg import kg_available, ask; print('可用:', kg_available()); print(ask('土豆','糖尿病')['verdict'])"
```

应输出：`可用: True` 和 `未发现禁忌关联`（容器在跑所以可用；图还没建所以没知识——下一步建图后同样的问题就有答案了）。

---

## 8. 第七步：新建 scripts/init_kg.py 并建图

**操作**：新建 `scripts/init_kg.py`，完整复制：

```python
# scripts/init_kg.py
"""
阶段 3（v3.0）：知识图谱构建脚本——把 recipes.json + kg_facts.json 变成 Neo4j 图

构建内容（四类节点 + 四类关系）：
    节点：Ingredient / Recipe / Nutrient / Condition
    关系：IN_RECIPE（食材→菜谱，带用量）
          RICH_IN（食材→营养素，带等级）
          CONTRAINDICATED_FOR（食材→状况，带等级+理由）
          BENEFICIAL_FOR（食材→状况，带理由）

幂等设计：
    全部用 MERGE（存在则复用、不存在则新建），重复执行不产生重复数据；
    --rebuild 参数先清空全图再建（改了 kg_facts.json 后用）。

用法（项目根目录，先起好 Neo4j 容器）：
    python scripts/init_kg.py             # 增量构建
    python scripts/init_kg.py --rebuild   # 清空重建
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))   # scripts/ 下运行需要把项目根加进搜索路径

from neo4j import GraphDatabase

from app_my.core.config import settings

# 数据文件定位（相对项目根，脚本从任何目录跑都能找到）
ROOT = Path(__file__).resolve().parent.parent
RECIPES_FILE = ROOT / "app_my" / "knowledge" / "data" / "recipes.json"
FACTS_FILE = ROOT / "app_my" / "knowledge" / "data" / "kg_facts.json"


def normalize_ingredient(raw: str) -> str:
    """
    "鸡蛋 3个" -> "鸡蛋"：去掉用量部分，只留食材名。

    图谱节点按"干净的名字"建，检索和重排时也用同样的规则切——
    两边规则一致，名字才对得上（图谱最经典的坑就是两边命名不齐）。
    """
    return re.split(r"\s+", raw.strip())[0]


def build(rebuild: bool = False) -> None:
    recipes = json.loads(RECIPES_FILE.read_text(encoding="utf-8"))
    facts = json.loads(FACTS_FILE.read_text(encoding="utf-8"))

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        connection_timeout=5,
    )
    driver.verify_connectivity()          # 连不上直接抛错退出（建图脚本不需要降级）
    print(f"已连接 Neo4j：{settings.NEO4J_URI}")

    with driver.session() as session:
        # ---------- 0) 可选清空 ----------
        if rebuild:
            session.run("MATCH (n) DETACH DELETE n")
            print("已清空全图（--rebuild）")

        # ---------- 1) 菜谱 + 食材 + IN_RECIPE ----------
        # 把 60 条菜谱整成 [{recipe_id, name, ..., items: [{name, amount}]}] 的批量结构
        recipe_rows = []
        for r in recipes:
            items = [
                {"name": normalize_ingredient(ing), "amount": ing}
                for ing in r.get("ingredients") or []
            ]
            recipe_rows.append({
                "recipe_id": r["recipe_id"],
                "name": r["name"],
                "calories": r.get("calories"),
                "time_minutes": r.get("time_minutes"),
                "difficulty": r.get("difficulty"),
                "items": items,
            })
        # UNWIND 批量写（一条 Cypher 写完 60 菜谱 + 全部食材和入菜关系，比逐条快百倍）
        session.run(
            """
            UNWIND $rows AS row
            MERGE (rc:Recipe {recipe_id: row.recipe_id})
              SET rc.name = row.name, rc.calories = row.calories,
                  rc.time_minutes = row.time_minutes, rc.difficulty = row.difficulty
            WITH row, rc
            UNWIND row.items AS item
            MERGE (i:Ingredient {name: item.name})
            MERGE (i)-[rel:IN_RECIPE]->(rc)
              SET rel.amount = item.amount
            """,
            rows=recipe_rows,
        )
        print(f"[1/3] 菜谱 {len(recipe_rows)} 个 + IN_RECIPE 关系已写入")

        # ---------- 2) 营养素 + RICH_IN ----------
        nutrient_rows = []
        for nutrient, info in facts["nutrients"].items():
            for name in info.get("high", []):
                nutrient_rows.append(
                    {"nutrient": nutrient, "ingredient": name, "note": info.get("note", "")}
                )
        session.run(
            """
            UNWIND $rows AS row
            MERGE (n:Nutrient {name: row.nutrient})
              SET n.note = row.note
            MERGE (i:Ingredient {name: row.ingredient})
            MERGE (i)-[:RICH_IN {level: '高'}]->(n)
            """,
            rows=nutrient_rows,
        )
        print(f"[2/3] 营养素节点 + RICH_IN 关系 {len(nutrient_rows)} 条已写入")

        # ---------- 3) 健康状况 + CONTRAINDICATED_FOR / BENEFICIAL_FOR ----------
        condition_rows = []
        prefer_rows = []
        for condition, info in facts["conditions"].items():
            for item in info.get("avoid", []):
                condition_rows.append({
                    "condition": condition,
                    "ingredient": item["name"],
                    "level": item["level"],
                    "reason": item["reason"],
                })
            for item in info.get("prefer", []):
                prefer_rows.append({
                    "condition": condition,
                    "ingredient": item["name"],
                    "reason": item["reason"],
                })

        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Condition {name: row.condition})
            MERGE (i:Ingredient {name: row.ingredient})
            MERGE (i)-[r:CONTRAINDICATED_FOR]->(c)
              SET r.level = row.level, r.reason = row.reason
            """,
            rows=condition_rows,
        )
        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Condition {name: row.condition})
            MERGE (i:Ingredient {name: row.ingredient})
            MERGE (i)-[b:BENEFICIAL_FOR]->(c)
              SET b.reason = row.reason
            """,
            rows=prefer_rows,
        )
        # 状况的别名（"高血糖"也要能查到"糖尿病"）
        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Condition {name: row.name})
              SET c.aka = row.aka
            """,
            rows=[
                {"name": name, "aka": info.get("aka", [])}
                for name, info in facts["conditions"].items()
            ],
        )
        print(f"[3/3] 状况节点 6 个 + 禁忌 {len(condition_rows)} 条 / 推荐 {len(prefer_rows)} 条已写入")

        # ---------- 4) 构建结果统计 ----------
        stats = session.run(
            """
            MATCH (n) WITH labels(n)[0] AS label, count(*) AS cnt
            RETURN label, cnt ORDER BY cnt DESC
            """
        )
        print("\n===== 图谱规模 =====")
        total_nodes = 0
        for record in stats:
            print(f"  {record['label']:<12} {record['cnt']} 个")
            total_nodes += record["cnt"]
        rel_stats = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC"
        )
        total_rels = 0
        for record in rel_stats:
            print(f"  关系 {record['t']:<20} {record['c']} 条")
            total_rels += record["c"]
        print(f"合计：{total_nodes} 节点 / {total_rels} 关系")

    driver.close()
    print("\n构建完成。可用 python -c \"from app_my.core.kg import ask; print(ask('土豆','糖尿病'))\" 验证推理")


if __name__ == "__main__":
    build(rebuild="--rebuild" in sys.argv)
```

**操作**（建图，项目根目录）：

```powershell
python scripts/init_kg.py --rebuild
```

**验证**（应看到下面的规模——数字对不上就是数据文件没抄对）：

```text
已连接 Neo4j：bolt://localhost:7687
已清空全图（--rebuild）
[1/3] 菜谱 60 个 + IN_RECIPE 关系已写入
[2/3] 营养素节点 + RICH_IN 关系 80 条已写入
[3/3] 状况节点 6 个 + 禁忌 51 条 / 推荐 35 条已写入

===== 图谱规模 =====
  Ingredient   142 个
  Recipe       60 个
  Nutrient     8 个
  Condition    6 个
  关系 IN_RECIPE            332 条
  关系 RICH_IN              80 条
  关系 CONTRAINDICATED_FOR  51 条
  关系 BENEFICIAL_FOR       35 条
合计：216 节点 / 498 关系
```

再跑一次**验收场景**（糖尿病患者能不能吃土豆）：

```powershell
python -c "from app_my.core.kg import ask; import json; print(json.dumps(ask('土豆','糖尿病'), ensure_ascii=False, indent=2))"
```

应输出（核心字段）：`verdict: 建议控制食用量`、`reason: GI值较高，升血糖快...`、`affected_recipes` 里有「地三鲜」和「酸辣土豆丝」、`nutrients` 里有「碳水」和「钾」。

---

## 9. 第八步：改 ranker.py（三处）

**操作**：打开 `app_my/agents/ranker.py`，改三处。

**改动 1**：文件头部——docstring 的打分维度清单加第 ⑧ 条、导入区加两行、`_score_recipe` 签名前加辅助函数。

docstring 里「⑦ 偏好标签」那行后面加一行：

```text
        ⑧ 图谱禁忌    v3阶段3 新增：知识图谱按"健康状况"压制/加分
                     （控糖用户 → 图谱查出土豆"限量"、西兰花"推荐"，扣分带图谱理由）
```

导入区（原来是 `from typing import List, Tuple` 一行 + `from app_my.core.logging import logger`）改为：

```python
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from langchain_core.messages import AIMessage

from app_my.core import kg as kg_module   # 🔵 v3阶段3：知识图谱推理（不可用时自动跳过）
from app_my.core.logging import logger

# 与图谱一致的食材名切分规则（"鸡蛋 3个" -> "鸡蛋"，两边规则必须相同才能对上名字）
_ING_RE = re.compile(r"\s+")


def _ingredient_names(recipe: dict) -> List[str]:
    """菜谱的食材名列表（去掉用量部分）"""
    return [_ING_RE.split(x.strip())[0] for x in recipe.get("ingredients") or [] if x.strip()]
```

**改动 2**：`_score_recipe` 的签名加两个参数（原来只有 `recipe` 和 `profile`）：

```python
def _score_recipe(
    recipe: dict,
    profile: dict,
    kg_avoid: Dict[str, dict] | None = None,     # 🔵 v3阶段3：图谱忌口映射
    kg_prefer: Dict[str, dict] | None = None,     # 🔵 v3阶段3：图谱推荐映射
) -> Tuple[float, List[str]]:
```

函数体**末尾**（原来是 `return round(score, 2), reasons`）在 return 前插入打分维度 ⑧：

```python
    # ⑧ 图谱推理（v3阶段3）：按健康状况压制/加分，理由带图谱依据
    if kg_avoid or kg_prefer:
        names = set(_ingredient_names(recipe))
        # 禁忌：一条菜谱只按最重的一条扣（避免土豆+米饭双重扣把分数打到负无穷）
        worst = None
        for name in names:
            hit = (kg_avoid or {}).get(name)
            if hit and (worst is None or hit["weight"] > worst["weight"]):
                worst = {**hit, "ingredient": name}
        if worst:
            score -= worst["weight"]
            reasons.append(
                f"图谱提示：{worst['ingredient']}对{worst['condition']}患者{worst['level']}——{worst['reason']}"
            )
        # 推荐：命中一种就加分（说明这道菜对该状况友好）
        for name in names:
            hit = (kg_prefer or {}).get(name)
            if hit:
                score += 2
                reasons.append(f"图谱推荐：{name}适合{hit['condition']}人群——{hit['reason']}")
                break

    return round(score, 2), reasons
```

**改动 3**：`rank_recipes` 函数——剔过敏之前加图谱查询，打分调用传入映射。整个函数替换为：

```python
def rank_recipes(recipes: List[dict], profile: dict) -> List[dict]:
    """
    批量重排（纯函数，方便单测）。

    顺序：先剔过敏 → 查图谱指引（一次查全，不逐菜谱查） → 再打分 → 按分数倒序。
    """
    allergies = [a for a in (profile.get("allergies") or []) if a]

    # 🔵 v3阶段3：从画像推导健康状况，一次性查出忌口/推荐映射
    # （图谱不可用时返回两个空字典，下面的打分维度⑧自动跳过——主流程不受影响）
    conditions = kg_module.derive_conditions(profile)
    kg_avoid, kg_prefer = ({}, {})
    if conditions:
        kg_avoid, kg_prefer = kg_module.get_condition_guidance(conditions)
        if kg_avoid or kg_prefer:
            logger.info(f"ranker: 图谱指引已加载（状况={conditions}，忌口 {len(kg_avoid)} 项）")

    kept: List[dict] = []
    for r in recipes:
        ing_text = " ".join(r.get("ingredients") or [])
        if any(a in ing_text or a in r.get("name", "") for a in allergies):
            logger.info(f"ranker: 剔除含过敏食材的菜谱「{r.get('name')}」")
            continue
        score, reasons = _score_recipe(r, profile, kg_avoid, kg_prefer)
        kept.append({**r, "rank_score": score, "rank_reasons": reasons})

    return sorted(kept, key=lambda x: -x.get("rank_score", 0))
```

**验证**：

```powershell
python -c "from app_my.agents.ranker import rank_recipes, _score_recipe; print('ranker 导入正常')"
```

---

## 10. 第九步：新建 api/kg.py 并注册路由

**操作 A**：新建 `app_my/api/kg.py`，完整复制：

```python
# app_my/api/kg.py
"""
阶段 3（v3.0）：知识图谱推理接口——回答"XX 病患者能不能吃 YY"

接口（受 JWT 鉴权保护，需要登录后带 access token 访问）：
    GET /kg/ask?ingredient=土豆&condition=糖尿病    多跳推理问答
    GET /kg/stats                                   图谱规模统计（排障/演示用）

为什么这个接口有存在感：
    向量检索（RAG）回答的是"哪些菜谱和你的食材相似"；
    图谱回答的是"你的身体状况和这个食材有什么关系、为什么、影响哪些菜"。
    返回的每一个字段都来自图上一条真实存在的边——可解释、可追溯、不幻觉。
"""
from fastapi import APIRouter, Query

from app_my.core import kg as kg_module

router = APIRouter()


@router.get("/ask")
async def kg_ask(
    ingredient: str = Query(..., min_length=1, max_length=30, description="食材名，如：土豆"),
    condition: str = Query(..., min_length=1, max_length=30, description="健康状况名，如：糖尿病/痛风/高血压"),
):
    """
    图谱依据的多跳推理：结论 + 理由 + 营养证据 + 受影响菜谱。

    支持"高血糖"这类别名（图上 Condition 节点带 aka 别名列表）。
    图谱不可用时明确返回 graph_available=false（诚实告知，不冒充"没禁忌"）。
    """
    return kg_module.ask(ingredient.strip(), condition.strip())


@router.get("/stats")
async def kg_stats():
    """图谱规模统计：四类节点/四类关系各多少个（演示和排障用）"""
    return kg_module.kg_stats()
```

**操作 B**：改 `main.py` 两处。

🟡 **先顺手清理一个历史遗留**：当前 `main.py` 里有**两行重复的导入**（第 9 行 `from app_my.api import oss, chat, auth, user` 和第 17 行 `...user, billing`——阶段 2 施工时是新增而不是替换）。把**第 9 行整行删掉**，只保留下面这一行（并加上 kg）：

```python
from app_my.api import oss, chat, auth, user, billing, kg   # kg 为 v3阶段3 新增（知识图谱推理）
```

路由注册区，`billing` 那行后面加：

```python
app.include_router(kg.router, prefix="/kg", tags=["知识图谱(v3阶段3)"])            # 🟢 v3阶段3 新增
```

**验证**：

```powershell
python -c "import main; print('main.py 导入正常')"
```

---

## 11. 第十步：新增测试文件并改 pytest.ini

**操作 A**：`pytest.ini` 整个替换为（多一个 kg 标记）：

```ini
[pytest]
testpaths = tests
markers =
    llm: 打真实大模型的慢测试（默认跳过，用 pytest -m llm 单独跑）
    kg: 需要本地 Neo4j 图谱的测试（默认跳过，用 pytest -m kg 单独跑；先起容器并建图）
addopts = -m "not llm and not kg"
```

**操作 B**：新建 `tests/unit/test_kg_reasoning.py`，完整复制：

```python
# tests/unit/test_kg_reasoning.py
"""
阶段 3 单元测试：图谱推理的纯逻辑部分（不需要 Neo4j、不需要后端）

覆盖三块：
    1. 状况推导      derive_conditions：画像 goal/health_conditions -> 图谱状况名
    2. 知识数据自检  kg_facts.json 的食材名与 recipes.json 对齐（名字连不上图就白建了）
    3. 重排打分      图谱忌口/推荐映射注入后的加减分与理由（monkeypatch 掉真实查询）
"""
import json
from pathlib import Path

import pytest

from app_my.agents import ranker
from app_my.core import kg as kg_module

DATA_DIR = Path(__file__).resolve().parents[2] / "app_my" / "knowledge" / "data"


# ============================================================
# 1) 状况推导
# ============================================================

class TestDeriveConditions:
    def test_sugar_goal_maps_to_diabetes(self):
        # 画像目标"控糖" -> 图谱状况"糖尿病"（重排时按糖尿病饮食原则压制高GI食材）
        assert kg_module.derive_conditions({"goal": "控糖"}) == ["糖尿病"]

    def test_normal_goal_no_condition(self):
        # 普通/减脂/增肌目标没有对应禁忌状况 -> 空列表（不查图谱）
        assert kg_module.derive_conditions({"goal": "减脂"}) == []
        assert kg_module.derive_conditions({}) == []

    def test_health_conditions_passthrough(self):
        profile = {"goal": "普通", "health_conditions": ["痛风", "高血压"]}
        assert kg_module.derive_conditions(profile) == ["痛风", "高血压"]

    def test_dedup_when_goal_and_condition_overlap(self):
        # goal=控糖 + health_conditions 里又写了糖尿病 -> 只留一个
        profile = {"goal": "控糖", "health_conditions": ["糖尿病"]}
        assert kg_module.derive_conditions(profile) == ["糖尿病"]


# ============================================================
# 2) 知识数据自检（图谱数据质量）
# ============================================================

class TestKgFactsAlignment:
    def _load(self):
        recipes = json.loads((DATA_DIR / "recipes.json").read_text(encoding="utf-8"))
        facts = json.loads((DATA_DIR / "kg_facts.json").read_text(encoding="utf-8"))
        return recipes, facts

    def test_facts_file_structure(self):
        _, facts = self._load()
        assert "conditions" in facts and "nutrients" in facts
        for name, info in facts["conditions"].items():
            assert "aka" in info, f"{name} 缺 aka 字段"
            for item in info.get("avoid", []):
                assert set(item) >= {"name", "level", "reason"}, f"{name}.avoid 条目字段不全"
            for item in info.get("prefer", []):
                assert set(item) >= {"name", "reason"}, f"{name}.prefer 条目字段不全"

    def test_avoid_levels_are_valid(self):
        # level 必须是 kg.py 里定义过扣分权重的三档之一，写错等级等于静默不扣分
        _, facts = self._load()
        valid = set(kg_module.LEVEL_WEIGHT)
        for name, info in facts["conditions"].items():
            for item in info.get("avoid", []):
                assert item["level"] in valid, f"{name}->{item['name']} 的 level={item['level']} 不在 {valid}"

    def test_fact_ingredients_align_with_recipes(self):
        # 图谱知识里的食材名必须能在 recipes.json 里找到（除少量明确"预留"的）
        # 名字对不上的边永远查不到——这是图谱项目最经典的坑
        recipes, facts = self._load()
        recipe_names = set()
        for r in recipes:
            for ing in r.get("ingredients", []):
                recipe_names.add(ing.split()[0])

        known_missing = {"香蕉", "浓茶"}     # kg_facts 里标注"本库未用到，预留"的
        referenced = set()
        for info in facts["conditions"].values():
            for item in info.get("avoid", []) + info.get("prefer", []):
                referenced.add(item["name"])
        for info in facts["nutrients"].values():
            referenced.update(info.get("high", []))

        orphan = referenced - recipe_names - known_missing
        assert not orphan, f"以下食材在图谱知识里写了，但 recipes.json 里不存在：{sorted(orphan)}"


# ============================================================
# 3) 重排打分（图谱映射注入后的行为）
# ============================================================

def _recipe(name="测试菜", ingredients=None, **kw):
    return {
        "name": name,
        "ingredients": ingredients or ["鸡蛋 2个", "小葱 1根"],
        "tags": kw.get("tags", []),
        "time_minutes": kw.get("time_minutes", 15),
        "difficulty_level": kw.get("difficulty_level", 2),
        "calories": kw.get("calories", 200),
        **{k: v for k, v in kw.items() if k not in ("tags", "time_minutes", "difficulty_level", "calories")},
    }


AVOID_POTATO = {"土豆": {"condition": "糖尿病", "level": "限量", "reason": "GI值较高，升血糖快", "weight": 4}}
PREFER_BROCCOLI = {"西兰花": {"condition": "糖尿病", "reason": "低GI且富含膳食纤维"}}


class TestRankerWithKg:
    def test_avoid_hit_penalizes_with_graph_reason(self):
        # 同一道菜：无图谱扣分 vs 图谱说土豆"限量"（-4），且理由带"图谱提示"
        base = _recipe("土豆炖牛腩", ["土豆 2个", "牛腩 300克"])
        score_plain, reasons_plain = ranker._score_recipe(base, {"goal": "普通"})
        score_kg, reasons_kg = ranker._score_recipe(base, {"goal": "普通"}, kg_avoid=AVOID_POTATO)

        assert score_kg == pytest.approx(score_plain - 4)
        assert any("图谱提示" in r and "土豆" in r for r in reasons_kg)

    def test_avoid_hard_level_penalizes_more(self):
        # level=避免 扣 8 分（比"限量"的 4 分更重——安全等级不同力度不同）
        avoid_hard = {"火腿": {"condition": "高血压", "level": "避免", "reason": "钠含量极高", "weight": 8}}
        r = _recipe("火腿炒饭", ["火腿 50克", "米饭 1碗"])
        s_plain, _ = ranker._score_recipe(r, {"goal": "普通"})
        s_hard, _ = ranker._score_recipe(r, {"goal": "普通"}, kg_avoid=avoid_hard)
        assert s_plain - s_hard == 8

    def test_worst_hit_wins_no_double_penalty(self):
        # 土豆+大米都命中（各 -4）：一道菜只按最重的扣一次（-4），不是 -8
        avoid_two = {
            "土豆": {"condition": "糖尿病", "level": "限量", "reason": "GI高", "weight": 4},
            "大米": {"condition": "糖尿病", "level": "限量", "reason": "精制碳水", "weight": 4},
        }
        r = _recipe("土豆焖饭", ["土豆 1个", "大米 100克"])
        s_plain, _ = ranker._score_recipe(r, {"goal": "普通"})
        s_kg, _ = ranker._score_recipe(r, {"goal": "普通"}, kg_avoid=avoid_two)
        assert s_plain - s_kg == 4

    def test_prefer_hit_adds_score(self):
        r = _recipe("清炒西兰花", ["西兰花 300克", "蒜 2瓣"])
        s_plain, _ = ranker._score_recipe(r, {"goal": "普通"})
        s_kg, reasons_kg = ranker._score_recipe(r, {"goal": "普通"}, kg_prefer=PREFER_BROCCOLI)
        assert s_kg == pytest.approx(s_plain + 2)
        assert any("图谱推荐" in r2 for r2 in reasons_kg)

    def test_rank_recipes_without_conditions_skips_kg(self, monkeypatch):
        # 没有健康状况时一次图谱都不该查（monkeypatch 成炸弹，被调用就炸）
        def _boom(*a, **kw):
            raise AssertionError("无健康状况时不应查询图谱")

        monkeypatch.setattr(kg_module, "get_condition_guidance", _boom)
        result = ranker.rank_recipes([_recipe()], {"goal": "普通"})
        assert len(result) == 1

    def test_rank_recipes_reorders_by_kg(self, monkeypatch):
        # 端到端排序行为：含土豆的菜 vs 不含的菜，控糖画像下土豆菜被压下去
        monkeypatch.setattr(kg_module, "get_condition_guidance", lambda c: (dict(AVOID_POTATO), {}))
        recipes = [
            _recipe("土豆炖牛腩", ["土豆 2个", "牛腩 300克"]),
            _recipe("清炒油麦菜", ["油麦菜 300克", "蒜 2瓣"]),
        ]
        ranked = ranker.rank_recipes(recipes, {"goal": "控糖"})
        assert ranked[0]["name"] == "清炒油麦菜"      # 无禁忌的排前面
        assert any("图谱提示" in r for r in ranked[1]["rank_reasons"])
```

**操作 C**：新建 `tests/integration/test_kg_api.py`，完整复制：

```python
# tests/integration/test_kg_api.py
"""
阶段 3 集成测试：/kg/ask 图谱推理接口（需要后端在跑 + Neo4j 容器 + 已建图）

跑法（与 llm 标记一样单独跑）：
    pytest tests/integration/test_kg_api.py -m kg -q

前置：
    1. docker compose -f docker/docker-compose.v3.yml up -d   （含 neo4j 服务）
    2. python scripts/init_kg.py                               （建图）
    3. 后端在跑（python main.py）
"""
import pytest

pytestmark = pytest.mark.kg


def test_kg_ask_requires_auth(base_url):
    """不带 token 访问必须 401——推理结论虽是科普，接口本身不能裸奔"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask", params={"ingredient": "土豆", "condition": "糖尿病"}, timeout=15
    )
    assert resp.status_code == 401


def test_kg_ask_potato_diabetes(base_url, account):
    """验收场景：糖尿病患者能不能吃土豆——三段证据齐全"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask",
        params={"ingredient": "土豆", "condition": "糖尿病"},
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["graph_available"] is True
    assert data["verdict"] == "建议控制食用量"          # kg_facts 里土豆对糖尿病是"限量"
    assert "GI" in data["reason"] or "血糖" in data["reason"]
    assert data["affected_recipes"], "土豆相关菜谱应非空（库里至少两道）"
    assert any(item["nutrient"] == "碳水" for item in data["nutrients"])


def test_kg_ask_alias_condition(base_url, account):
    """别名检索：condition=高血糖 也能命中 糖尿病 节点（aka 边）"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask",
        params={"ingredient": "可乐", "condition": "高血糖"},
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "不建议食用"        # 可乐对糖尿病是"避免"


def test_kg_ask_unknown_pair_is_honest(base_url, account):
    """图谱没收录的关系要诚实说"未发现"，不能编造（与幻觉的区别所在）"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask",
        params={"ingredient": "西红柿", "condition": "痛风"},
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "未发现禁忌关联"
```

---

## 12. 第十一步：跑测试

**操作**：

1. 确认基础设施在跑：`docker ps` 应看到 `ai_chief_pgvector`、`ai_chief_redis`、`ai_chief_neo4j` 都是 Up（healthy）。
2. 起后端（新终端，保持运行）：

```powershell
cd F:\pycharm_aiprogram\ai_chief
.venv3\Scripts\Activate.ps1
python main.py
```

3. 另开一个终端跑**默认套件**（不需要图谱也能全绿——13 个新单测全是纯逻辑）：

```powershell
pytest tests/ -q
```

**验证**：

```text
52 passed, 5 deselected in 2.xxs
```

（阶段 2 是 39 个；本阶段新增 13 个单测 = 52。`5 deselected` = 1 个 llm + 4 个 kg。）

4. 跑**图谱集成测试**（验收核心）：

```powershell
pytest tests/integration/test_kg_api.py -m kg -q
```

**验证**：`4 passed`

5. 跑**真实 LLM 流式测试**（确认图谱接入没破坏主工作流）：

```powershell
pytest tests/test_chat_llm.py -m llm -q
```

**验证**：`1 passed`（15~30 秒级）。

6. **可视化验收**（可选但推荐）：浏览器打开 `http://localhost:7474`，登录后输入下面的 Cypher，亲眼看看"糖尿病患者忌口"这张子图：

```cypher
MATCH (i:Ingredient)-[r:CONTRAINDICATED_FOR]->(c:Condition {name:'糖尿病'})
RETURN i, r, c
```

应该看到 15 个食材节点连向"糖尿病"，边上有等级和理由——这就是系统做推理时"看"的图。

---

## 13. 验收清单

| # | 验收项 | 结果 | 怎么验 |
|---|---|---|---|
| 1 | Neo4j 容器健康运行 | ✅ | `docker ps` 里 `ai_chief_neo4j` 为 Up (healthy) |
| 2 | 图谱建成且规模正确 | ✅ | `python scripts/init_kg.py` 输出 216 节点 / 498 关系 |
| 3 | 验收场景推理正确 | ✅ | `ask('土豆','糖尿病')` → 建议控制食用量 + 理由 + 2 道受影响菜谱 + 营养证据 |
| 4 | 别名检索 | ✅ | `ask('可乐','高血糖')` → 不建议食用（aka 命中糖尿病） |
| 5 | 诚实回答未知关系 | ✅ | `ask('西红柿','痛风')` → 未发现禁忌关联（不编造） |
| 6 | 默认测试全绿 | ✅ | `pytest tests/ -q` → 52 passed |
| 7 | 图谱集成测试通过 | ✅ | `pytest tests/integration/test_kg_api.py -m kg -q` → 4 passed |
| 8 | 主工作流不受影响 | ✅ | `pytest tests/test_chat_llm.py -m llm -q` → 1 passed |
| 9 | 推荐重排个性化生效 | ✅ | 控糖画像下土豆菜被压到 0.5→-3.5 并带图谱理由（1.4 节演示） |
| 10 | 接口受 JWT 保护 | ✅ | 不带 token 访问 /kg/ask 返回 401 |
| 11 | 图谱挂掉不挡主流程 | ✅ | 停掉 Neo4j 容器后对话照常（日志出现"图谱推理降级为跳过"），测完再起回来 |
| 12 | v2.0 不受影响 | ✅ | ai_sichu_* 四容器照常运行 |

---

## 14. 错误对照表

| # | 错误现象 | 原因 | 解决 |
|---|---|---|---|
| E1 | `docker compose up` 后 neo4j 容器反复重启 | YAML 缩进错了（neo4j 块没和 pgvector/redis 对齐） | 对照第 3 步：`neo4j:` 前面是 2 空格缩进，和 `redis:` 平级 |
| E2 | 容器 `unhealthy` / 一直 `starting` | 首次启动慢（要初始化），或密码里的特殊字符被 shell 吃了 | 等 1~2 分钟；确认 NEO4J_AUTH 就是 `neo4j/ai_chief_kg`（无引号无空格） |
| E3 | `ModuleNotFoundError: No module named 'neo4j'` | 驱动没装进 `.venv3` | 重跑第 4 步的 `uv pip install`，注意终端提示符有 `(.venv3)` |
| E4 | init_kg.py 报 `AuthInfo` / 认证失败 | 密码不对（compose 里的和 config.py 默认值不一致） | 两边统一成 `ai_chief_kg`；改了 compose 要 `docker compose ... up -d` 重建容器 |
| E5 | init_kg.py 报 `ServiceUnavailable` | 容器还没就绪就跑了建图 | `docker ps` 等到 `(healthy)` 再跑 |
| E6 | init_kg.py 数字不是 216/498 | kg_facts.json 没抄全（JSON 少个逗号/括号） | `python -c "import json; json.load(open('app_my/knowledge/data/kg_facts.json', encoding='utf-8'))"` 验证 JSON 合法；重新完整复制 |
| E7 | 单测 `test_fact_ingredients_align...` 失败，报一堆"不存在"的食材 | kg_facts.json 里食材名和 recipes.json 对不上（多打/漏打字） | 看报错里的食材名单，逐个改成 recipes.json 里的原词（如"西红柿"不能写成"番茄"） |
| E8 | kg 集成测试 401 | 不带 token——/kg/* 受 JWT 保护（设计如此） | 测试自带登录 fixture；手工 curl 要先拿 access_token |
| E9 | kg 集成测试 `graph_available: false` | 后端起的时机比建图早，或容器停了 | 确认容器 healthy + 建图已完成；**重启后端**（驱动失败后本进程不再重试，这是设计） |
| E10 | `ask()` 一直返回"未发现禁忌关联"但图里有 | 查询的名字和节点名不一致（全角/半角、空格） | 用 `strip()`；确认传的是"土豆"不是"土豆 "；Neo4j Browser 里 `MATCH (i:Ingredient) RETURN i.name LIMIT 20` 核对 |
| E11 | 跑 kg 测试报 429 | IP 级限流 60/分（连续多轮测试） | 等 60 秒再跑 |
| E12 | Neo4j Browser 打不开 7474 | 容器没起或端口被占 | `docker ps` 核对；`netstat -ano | findstr 7474` 查占用 |

---

## 15. 不做清单

本阶段**故意不做**的事（都有明确理由，做到对应阶段再说）：

| 不做 | 理由 | 以后在哪做 |
|---|---|---|
| 前端页面调 /kg/ask | 推理接口先给后端/测试用；前端出"健康提示卡"要有设计 | 阶段 9（多租户）或按需 |
| 健康状况的用户编辑入口 | 画像目前是文件存储，先支持在 user_profiles.json 里手工加 `"health_conditions": ["痛风"]` | 阶段 9（画像表已入库后开 API） |
| 自然语言直接问"糖尿病人能吃土豆吗" | 需要先抽实体（食材/状况），属于意图识别 | 可选：在 chat 节点前加一个轻量意图分类器（走 lite 档，成本极低） |
| 图谱自动从 LLM 抽取知识 | 策展数据可控可校验；LLM 抽取会引入幻觉，违背"诚实推理"原则 | 不做（或做"LLM 提案 + 人工审核入库"的双人机制） |
| 混合检索三路融合（向量+BM25+图谱加权） | 阶段 3 只做图谱本身 + 重排接入；检索融合是独立大题 | 阶段 6（Milvus + 混合检索 v2） |
| 图谱可视化自建页面 | Neo4j Browser 已经很好用 | 不做 |

---

## 16. 提交 Gitee 与 PR 描述

**操作**：

```powershell
cd F:\pycharm_aiprogram\ai_chief
git add app_my/knowledge/data/kg_facts.json app_my/core/kg.py app_my/api/kg.py scripts/init_kg.py tests/unit/test_kg_reasoning.py tests/integration/test_kg_api.py
git add docker/docker-compose.v3.yml requirements.txt app_my/core/config.py app_my/agents/ranker.py main.py pytest.ini
git status
git commit -m "feat(v3-stage3): Neo4j知识图谱+多跳推理——禁忌推理接入重排+/kg/ask接口"
git push origin feat/v3-stage3
```

然后在 Gitee 发 PR：`feat/v3-stage3 → master`，标题和描述直接用下面这段：

---

### PR 标题

feat(v3-stage3): Neo4j 知识图谱 + 多跳推理

### PR 描述

#### 改动概述

给系统补上向量检索做不到的"关系推理"能力：构建「食材-营养-菜谱-禁忌」知识图谱（216 节点/498 关系），多跳推理接入推荐重排并开放 /kg/ask 推理问答接口，全部结论有图上的边作依据，可解释、不幻觉。

#### 核心改动

- **图谱基础设施**：docker-compose 新增 Neo4j 5 社区版容器（Bolt 7687，独立数据卷，内存上限 512m+128m）
- **知识数据 `kg_facts.json`**：6 种健康状况（糖尿病/高血压/痛风/高血脂/慢性肾病/缺铁性贫血）的忌口 51 条 + 推荐 35 条（带等级与理由）+ 8 类营养素富集关系 80 条；食材名与 recipes.json 逐一对齐（单测守护）
- **查询封装 `core/kg.py`**：驱动单例 + 优雅降级（Neo4j 挂掉返回空结果记日志，主流程零影响）+ 三类查询（状况指引/多跳问答/规模统计）；诚实推理——图里没有边就回答"未发现禁忌关联"
- **建图脚本 `scripts/init_kg.py`**：UNWIND 批量 MERGE（幂等，可重复执行），--rebuild 清空重建
- **重排接入（ranker.py）**：画像推导健康状况（控糖→糖尿病）→ 图谱忌口/推荐映射 → 打分维度⑧（避免 -8/限量 -4/适量 -2/推荐 +2，理由带图谱依据传给报告）；一条菜谱只按最重的禁忌扣一次
- **推理接口 `/kg/ask`**（JWT 保护）：三段证据（结论+理由/营养证据/受影响菜谱），支持"高血糖"别名命中"糖尿病"
- 顺手清理 main.py 一行重复导入（阶段 2 施工遗留）

#### 测试

- 新增 13 个单元测试（状况推导/知识数据对齐自检/重排打分含 monkeypatch 边界）
- 新增 4 个图谱集成测试（kg 标记，默认跳过）：鉴权 401/验收场景/别名检索/未知关系诚实回答
- 全量默认套件 39 → 52 passed；kg 集成 4 passed；真实 LLM 流式 1 passed（图谱接入不破坏主工作流）
- 图谱挂掉场景验证：停容器后对话照常、日志出现降级记录

#### 效果实测

控糖画像下重排对比：香煎鸡胸肉配西兰花 0.5→2.5 分（图谱推荐）升至第一；地三鲜/酸辣土豆丝 0.5→-3.5 分（土豆对糖尿病限量）被压下——推荐从"千人一面"变成"有理有据的因人而异"。

#### 不在本 PR 的内容

健康状态前端编辑（阶段 9）；向量+BM25+图谱三路融合检索（阶段 6）；自然语言直接提问的实体抽取（可选优化）

---

---

## 17. 收官总结

### 17.1 收官状态（2026-09-29）

| 项 | 结果 |
|---|---|
| 施工期问题 | **0 个**（一次施工通过） |
| 测试 | 52 passed（原 39 + 本阶段 13） |
| 真实 LLM 流式 | 1 passed，端到端 17.6 秒 |
| 图谱集成 | 4 passed（kg 标记），含"控糖用户重排演示" |
| 图谱规模 | 216 节点 / 498 关系（Ingredient 142 / Recipe 60 / Nutrient 8 / Condition 6） |
| git | feat/v3-stage3 已 commit（1653d52），待合并 master |
| v2.0 影响 | 无（ai_sichu 目录与四容器全程未动） |
| commit 数 | 12 文件，+1011 行 / -11 行 |

### 17.2 本阶段沉淀的简历叙事

- **RAG + KG 混合架构的工程实践**：向量检索管"相似度"（有哪些菜谱），图谱管"关系推理"（能不能吃、为什么），两者互补——这是 RAG 时代被高频问到的设计取舍，本项目有真实代码支撑。
- **可解释 AI 的廉价实现**：每个禁忌结论都指着图上一条边（"依据：土豆 -[CONTRAINDICATED_FOR]-> 糖尿病"），不是大模型自己编出来的——`/kg/ask` 接口可对外展示推理链。
- **图谱容灾与降级**：Neo4j 挂时推荐流程不中断（空结果 + `graph_available: False` 标记），不引入新的单点故障。
- **知识策展方法论**：禁忌/营养数据不靠 LLM 抽取（防幻觉），由开发者手动策展入库——这是"宁少勿假"的工程取舍，与 RAG 的"宁错勿缺"形成对比，面试很好讲。

### 17.3 个性化效果（控糖画像验收演示）

| 菜名 | 普通用户 | 控糖用户 | 变化原因 |
|---|---|---|---|
| 西兰花炒虾仁 | +0.5 | **+2.5** | 控糖加分（维度①） |
| 蒜蓉西兰花 | +0.5 | **+2.5** | 控糖加分 |
| 酸辣土豆丝 | +0.5 | **-3.5** | 控糖重度禁忌（图谱维度⑧） |
| 土豆炖牛肉 | +0.5 | **-3.5** | 控糖重度禁忌 |
| 清蒸鲈鱼 | 0.0 | 0.0 | 不触发图谱得分变化（鲈鱼图谱无相关边） |

### 17.4 遗留与后续

| 事项 | 去向 |
|---|---|
| 图谱健康状况的告警 | 阶段 7（Prometheus 黑盒探针） |
| Neo4j 备份 / 导出功能 | 阶段 9 多租户独立图（按租户分库） |
| 知识图谱可视化页面 | 阶段 8 前端可视化（Neo4j Browser 已可访问 7474） |
| 更大规模的禁忌知识 | 阶段 9 引入领域权威源（指南/教材） |
| 推理链路追踪（KG 影响推荐哪一步） | 阶段 7 LangSmith 已有 trace |

### 17.5 下一阶段预告

**阶段 4：多租户 SaaS 化 + 配额管理**——把"单租户"演化为"多租户"，每个用户/团队有独立数据、配额、计费。这是方案阶段 5+9 的合并。
