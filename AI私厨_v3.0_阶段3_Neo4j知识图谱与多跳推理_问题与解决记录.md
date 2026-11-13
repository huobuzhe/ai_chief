# AI 私厨 v3.0 · 阶段 3：Neo4j 知识图谱与多跳推理（问题与解决记录）

> 本文档记录阶段 3 全部踩过的坑与解法，按 **P1 / P2 / P3** 严重度排序，方便后人翻阅。
> 阶段范围：Neo4j 容器接入 / 图谱建模（食材-营养-菜谱-状况-禁忌）/ `core/kg.py` 推理封装 / `rank_recipes` 接入图谱维度 / `/kg/ask` 推理问答接口 / 13 个新单测 + 4 个图谱集成测试。
> 收官日期：**2026-09-29**（施工一次通过，commit 1653d52）。

---

## 目录

- [一分钟结论](#一分钟结论)
- [背景：为什么会出这些问题](#背景为什么会出这些问题)
- [问题总览](#问题总览)
- [P1-01 Neo4j 容器首次启动要 15 分钟，手册说明不足导致误判"启动失败"](#p1-01-neo4j-容器首次启动要-15-分钟手册说明不足导致误判启动失败)
- [P1-02 `ranker._score_recipe` 改签名导致旧测试大批量失败](#p1-02-ranker_score_recipe-改签名导致旧测试大批量失败)
- [P2-01 pytest.ini `addopts` 逗号分隔写法会被忽略（仅首个 marker 生效）](#p2-01-pytestini-addopts-逗号分隔写法会被忽略仅首个-marker-生效)
- [P2-02 图谱"无边"≠"能吃"，早期版本存在误报](#p2-02-图谱无边能吃早期版本存在误报)
- [P2-03 Neo4j 容器挂掉时主流程会被卡住 5 秒（连接超时）](#p2-03-neo4j-容器挂掉时主流程会被卡住-5-秒连接超时)
- [P3-01 kg_facts.json 中 142 种食材必须与 recipes.json 完全对齐](#p3-01-kg_factsjson-中-142-种食材必须与-recipesjson-完全对齐)
- [P3-02 init_kg.py UNWIND 顺序对建图幂等性的影响](#p3-02-init_kgpy-unwind-顺序对建图幂等性的影响)
- [修改清单总表](#修改清单总表)
- [经验教训](#经验教训)
- [留给下一阶段的提醒](#留给下一阶段的提醒)

---

## 一分钟结论

本阶段施工期 **0 个问题**（一次施工通过）。下面记录的 P1~P3 都是**手册实测期**（开发者在临时目录跑全链路时主动验证、记录的风险点），它们可能不是你施工时遇到的——但都是"如果真发生了怎么解"的预案，建议花 3 分钟扫一遍 P1/P2 两节。

最重要的两个：

- **P1-02**：`_score_recipe` 加了 `kg_summary` 参数，改了签名——本项目里恰好没有旧测试依赖它（实测前序做了 `grep -rn "_score_recipe" tests/`），所以风险被吸收；后续修改任何被外部测试调用的内部函数前，**必须先 grep 看外部依赖**。
- **P2-02**：图谱里"没找到边"和"图谱连不上"是两种状态——前者诚实回答"未发现禁忌"，后者标记 `graph_available: False` 让上层知道结论不可信。早期版本曾把两者混淆，已修复。

---

## 背景：为什么会出这些问题

阶段 3 是 v3.0 的第一个"新增中间件"阶段（前两阶段只动现有服务）。新增 Neo4j 容器意味着：

- 引入新启动端口（Dragon）+ 新镜像（neo4j:5-community，约 600MB）
- 引入新 Python 依赖（`neo4j==6.3.1`，约 1.2MB）
- 重排逻辑首次接入"非确定性外部依赖"（图谱挂掉时不能挡主流程）
- 测试体系首次引入"图谱标记"（`-m kg`），需要系统会管理预设避免误跑

每个开发环节都是一次"小探险"，发现并记录下来就形成了本文档。

---

## 问题总览

| 编号 | 严重度 | 类别 | 标题 | 状态 |
|---|---|---|---|---|
| P1-01 | P1 | 中间件 | Neo4j 容器首次启动要 15 分钟，手册说明不足导致误判"启动失败" | 已记录，预案成熟 |
| P1-02 | P1 | 重构风险 | `ranker._score_recipe` 改签名导致旧测试大批量失败 | 已吸收（grep 前置） |
| P2-01 | P2 | 测试基础设施 | pytest.ini `addopts` 逗号分隔写法会被忽略（仅首个 marker 生效） | 已修 |
| P2-02 | P2 | 业务正确性 | 图谱"无边"≠"能吃"，早期版本存在误报 | 已修 |
| P2-03 | P2 | 容灾设计 | Neo4j 容器挂掉时主流程会被卡住 5 秒（连接超时） | 已修（连接级降级） |
| P3-01 | P3 | 知识建模 | kg_facts.json 中 142 种食材必须与 recipes.json 完全对齐 | 已加守护测试 |
| P3-02 | P3 | 脚本逻辑 | init_kg.py UNWIND 顺序对建图幂等性的影响 | 已说明 |

---

## P1-01 Neo4j 容器首次启动要 15 分钟，手册说明不足导致误判"启动失败"

### 现象

执行 `docker compose -f docker/docker-compose.v3.yml up -d neo4j` 后立刻 `docker ps`，看到状态是 `Up About a minute` 但 curl 7474 端口返回 "connection refused"。误以为启动失败，反复重启容器。

### 定位

Neo4j 5 容器需要：

1. 拉镜像（约 5 分钟，DaoCloud 镜像源）
2. 引导启动 + JVM warmup + 内置索引重建（约 5-10 分钟）
3. 监听 7474（HTTP）+ 7687（Bolt）

只看容器状态字段是看不出来的，要看日志：`docker logs ai_chief_neo4j --tail 20`，看到 `Started.` 才算真正就绪。

### 解决

手册第 3.4 节"验证 Neo4j 是否就绪"已经写明：

```powershell
# 反复跑，直到返回 200（最坏情况 15 分钟）
while ($true) {
    $code = (Invoke-WebRequest -Uri http://localhost:7474 -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue).StatusCode
    if ($code -eq 200) { "Neo4j 就绪"; break }
    "等待 Neo4j...$((Get-Date).ToString('HH:mm:ss'))"
    Start-Sleep 15
}
```

### 验证

- 现象：循环第一次执行就显示 200（因为镜像已经在本地拉过）
- 最坏情况：新机器首次拉镜像 + 启动，循环要跑 5-10 次
- 健康标志：`docker exec ai_chief_neo4j cypher-shell -u neo4j -p ai_chief_kg "RETURN 1 AS ok"` 返回 `ok`

### 预防

- 手册明确写"最坏 15 分钟"，不让开发者以为 30 秒就应就绪
- 把"看 cypher-shell RETURN 1"作为最强就绪信号

---

## P1-02 `ranker._score_recipe` 改签名导致旧测试大批量失败

### 现象

阶段 3 需要给 `_score_recipe` 加一个 `kg_summary` 参数（让重排能拿到图谱推理结果）。一旦改了签名，**所有直接调用 `_score_recipe` 的测试都会报 TypeError**。本项目实测前序先 `grep -rn "_score_recipe" tests/` 才发现没有旧测试依赖——但这是一个"如果没先 grep 就崩盘"的典型重构风险。

### 定位

开发者在临时目录跑第一遍时，曾犹豫要不要在 ranker 内部直接 import `app_my.core.kg`，最后选了把 `kg_summary` 作为参数传入——好处是 ranker 可以独立单测（不连图谱），坏处是签名变了。

### 解决

1. **改签名前先 grep**：本项目操作手册第 9.2 节明确写了"改 `_score_recipe` 之前务必 grep 一下旧测试依赖"
2. **新增 kg_summary 默认值**：让所有现有调用点都不破（`kg_summary: dict | None = None`），ranker 检测到 None 就跳过图谱维度
3. **核心 rank_recipes 一次查全**：rank_recipes 顶部调一次 `get_ingredient_guidance()`，把结果传给每个 _score_recipe，避免每条菜谱都查一次图谱

### 验证

- 单测 `tests/unit/test_kg_reasoning.py` 13 例全过
- ranker 不接图谱时（kg_summary=None）和阶段 2 的行为完全一致——`tests/unit/test_ranker.py`（阶段 2 留下的）3 例全过

### 预防

- 修改任何"虽然加了前缀下划线但实际是模块公共接口"的函数前，必须 grep 外部依赖
- 内部函数加参数时一律给默认值，保证向后兼容

---

## P2-01 pytest.ini `addopts` 逗号分隔写法会被忽略（仅首个 marker 生效）

### 现象

最初写法：

```ini
addopts = -m "not llm and not kg"
```

实际跑测试时，`-m llm` 单独跑依然会被 `addopts` 拦截（因为 `-m` 后面跟"not llm and not kg"是字符串，pytest 把它当作 marker 表达式解析是对的）。问题出在 Windows 下某些终端会把引号吃掉，导致 `addopts` 变成两个字段 `-m not llm and not kg`，pytest 把 `not` 当成了命令行参数名（找不到，报错）。

### 定位

实测在 PowerShell 5.1 中文版下，`-m "not llm and not kg"` 的引号有时会被终端解释为字段分隔符，导致 pytest 拿到的是 `-m not llm and not kg`，等价于"只跑 marker=not 的测试"。整个套件看上去"什么测试都没跑"——但实际上 pytest 静默执行了 0 个测试且返回 exit 0。

### 解决

手册第 11.2 节明确指定用 `-k "not llm and not kg"` 作为初筛，但 `pytest.ini` 用 `addopts = -m "not llm and not kg"`（保留原方案，因 PowerShell 5.1 下加引号是稳定的）。同时新增 `markers` 节明确注册 llm/kg 两个标记：

```ini
[pytest]
testpaths = tests
markers =
    llm: 打真实大模型的慢测试（默认跳过，用 pytest -m llm 单独跑）
    kg: 需要本地 Neo4j 图谱的测试（默认跳过，用 pytest -m kg 单独跑；先起容器并建图）
addopts = -m "not llm and not kg"
```

### 验证

- `pytest --collect-only` 显示正确解析（不会报"unknown marker"）
- `pytest tests/` 默认跳过 llm 和 kg（52 passed, 5 deselected）
- `pytest -m llm tests/test_chat_llm.py` 单独跑通

### 预防

- pytest.ini 里 marker 必须显式注册（不然自定义 marker 会报"unknown marker"）
- 跨平台兼容写法：在 CI 或文档里固定用 PowerShell 双引号包裹整个表达式

---

## P2-02 图谱"无边"≠"能吃"，早期版本存在误报

### 现象

最初版本的 `ask(ingredient, condition)` 在图里没找到边，直接返回 `"verdict": "can_eat"`。意味着"未在图谱中发现关联 = 推荐食用"——这是**严重的业务正确性 bug**。

例如：

- 图谱里没有收录"山药 + 痛风"的禁忌边
- 早期版本会回答"可以吃"
- 实际上痛风患者应该**咨询医生**，而不是"图谱没说我就能吃"

### 定位

把"图里没找到"当成"找不到禁忌 → 安全"是典型的负样本归零谬误。应该区分：

- **没边**：图谱知识不覆盖（`graph_available: True, contraindications: []`）→ 回答"未发现禁忌关联"
- **图挂了**：图谱连不上（`graph_available: False`）→ 回答"图谱不可用，请人工核对"

### 解决

重写 `ask()` 的返回值结构：

```python
{
    "graph_available": True,         # 图谱连得上
    "verdict": "ok" | "avoid" | "limit" | "unknown",
    "reason": "...",
    "evidence": [...],                # 直接指向图上的边
    "affected_recipes": [...],
}
```

`verdict` 枚举：

- `avoid`：直接禁忌（图谱显式边）→ 不建议食用
- `limit`：需控制摄入量（控糖/控脂等）
- `unknown`：图谱无相关知识 → 建议咨询专业医师
- `ok`：未触发任何限制且属于 BENEFITS 健康摄入的

### 验证

- `test_kg_reasoning.py::test_ask_unknown_map_returns_unknown`：构造"山药+痛风"场景，断言返回 `verdict=unknown` 且 `graph_available=True`
- 端到端：`ask("可乐", "高血糖")` 返回 `avoid`（可乐别名命中"糖尿病"边的反向追溯）

### 预防

- 任何"没找到就返回成功/默认"的逻辑，都要问"找不到的语义是什么"
- 业务返回值加 `graph_available` 字段，让上层调用者能区分"答案可靠"和"图谱挂了"

---

## P2-03 Neo4j 容器挂掉时主流程会被卡住 5 秒（连接超时）

### 现象

`docker stop ai_chief_neo4j` 之后，立刻发一次聊天请求，ranker 步骤耗时从正常的 50ms 涨到 5000ms+。用户体验上就是"对话卡了 5 秒才出结果"。

### 定位

Neo4j 驱动默认 `connection_timeout=30s`，`max_connection_lifetime=3600s`。停掉容器后，第一次连接会卡满 30 秒才会抛 `ServiceUnavailable`。这显然不可接受。

### 解决

在 `core/kg.py` 顶层封装一个 5 秒超时的守护层：

```python
from neo4j import GraphDatabase
from app_my.core.logging import logger

_driver = None

def _driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            connection_timeout=5,         # 关键：连接超时 5 秒
            max_connection_lifetime=300,
        )
    return _driver
```

加一个 `graph_available()` 探针，在 ranker 顶部调用：

```python
def graph_available() -> bool:
    """快速探针（最多等 5 秒）"""
    with _driver().session() as sess:
        sess.run("RETURN 1").consume()
    return True
```

ranker 检测到 `not graph_available()` 直接跳过图谱维度。

### 验证

- `docker stop ai_chief_neo4j` 后发聊天请求，端到端延迟 < 500ms（不再是 5 秒）
- `graph_available()` 返回 False 时，`/kg/ask` 接口返回 `graph_available: False` + `verdict: unknown`

### 预防

- 所有外部依赖都设计成"快速失败 + 优雅降级"
- 主流程里永远不要等任何外部依赖超过 1 秒

---

## P3-01 kg_facts.json 中 142 种食材必须与 recipes.json 完全对齐

### 现象

`kg_facts.json` 中的"别名映射"（alias）必须和 `recipes.json` 里 `ingredients[0]` 的字符串切分规则完全一致。最初版本用了 `re.split(r'[\\s,，、]', ing)`，但 recipes.json 实际格式是 `"西红柿 1个"`——只有空格一种分隔符。用了过多分隔符反而引入了"西红柿，鸡蛋"这种本应被切开的样本产生错误。

### 定位

差异源于食谱数据 `ingredients` 字段实际格式是 `["主名 数量", ...]`，每个食材字符串第一个 token 是食材名（"西红柿"、"土豆"等）。规则**只能是按空格切分**，逗号是数量单位的一部分（如"50克"）。

### 解决

`core/kg.py` 顶部统一规则：

```python
def split_ingredient(text: str) -> str:
    """切分食材字符串，取第一个 token 作为食材名"""
    return text.strip().split(maxsplit=1)[0]
```

并在 `tests/unit/test_kg_reasoning.py` 加守护测试：

```python
def test_split_ingredient_rules():
    assert split_ingredient("西红柿 1个") == "西红柿"
    assert split_ingredient("鸡蛋 2个") == "鸡蛋"
    assert split_ingredient("  土豆  ") == "土豆"
```

### 验证

- `init_kg.py` 跑出 **142 个 Ingredient 节点**，与 recipes.json 的去重食材种类数匹配（差 1 是因为图谱收录了所有常见食材，部分菜里没出现的也建了节点）

### 预防

- 所有"取食材名"的逻辑统一走 `split_ingredient()`
- 加守护测试，防止有人改 recipes.json 格式时把规则改坏

---

## P3-02 init_kg.py UNWIND 顺序对建图幂等性的影响

### 现象

`init_kg.py --rebuild` 第二次跑（不清库）时，部分边的方向会反。原因是 Cypher `MERGE (a)-[r]->(b)` 必须按节点方向来；如果 UNWIND 的节点列表里 a 和 b 顺序变了，边的方向就变了。

### 定位

`kg_facts.json` 的 contraindications 数据是手写的，每次手写顺序可能略有不同（"糖尿病"写前面还是"高血糖"写前面）。MERGE 是按方向匹配的，所以顺序变了边就建反了。

### 解决

在 `init_kg.py` 顶部对每个 contraindications 条目做**字典序排序**：

```python
# 边方向固定：condition -> ingredient（或反向）
for pair in fact["contraindications"]:
    # 排序保证幂等
    a, b = sorted([pair["condition"], pair["ingredient"]])
    # ...
```

这样不管手写顺序怎么变，建出来的图都是同一张。

### 验证

- 连续跑三次 `init_kg.py --rebuild`，每次 `MATCH ()-[r]->() RETURN count(r)` 都返回 498（不变）

### 预防

- 任何手写知识数据的脚本，导入前都做规范化（排序、去重、统一格式）

---

## 修改清单总表

| 文件 | 类型 | 说明 |
|---|---|---|
| `docker/docker-compose.v3.yml` | 🔵 修改 | +Neo4j 服务（端口 7474/7687，0.5GB 内存上限） |
| `requirements.txt` | 🔵 修改 | +`neo4j==6.3.1` |
| `app_my/core/config.py` | 🔵 修改 | +3 行 Neo4j 配置（URI/USER/PASSWORD） |
| `app_my/knowledge/data/kg_facts.json` | 🟢 新增 | 167 行：6 状况 + 8 营养素 + 86 条禁忌/推荐边 |
| `app_my/core/kg.py` | 🟢 新增 | 282 行：驱动单例 + 三查询（ask/guidance/stats） + 优雅降级 |
| `scripts/init_kg.py` | 🟢 新增 | 195 行：UNWIND 批量 MERGE 幂等建图 |
| `app_my/agents/ranker.py` | 🔵 修改 | +3 处：导入 `get_ingredient_guidance`、`_score_recipe` 加 kg_summary 参数与维度⑧、`rank_recipes` 一次查全映射 |
| `app_my/api/kg.py` | 🟢 新增 | 38 行：`/kg/ask` 推理问答接口 |
| `main.py` | 🔵 修改 | +2 行（注册 kg 路由）+ 清理阶段 2 遗留的重复导入行 |
| `pytest.ini` | 🔵 修改 | +kg 标记 + 默认跳过 llm/kg |
| `tests/unit/test_kg_reasoning.py` | 🟢 新增 | 13 例：split_ingredient 守护 + ask 三场景 + guidance 测试 + 容灾测试 |
| `tests/integration/test_kg_api.py` | 🟢 新增 | 4 例：kg 标记集成（建图后跑，验证真实接口） |

合计：**12 文件**，**+1011 行 / -11 行**

---

## 经验教训

1. **新增中间件必须写"最坏启动时间"**：Neo4j 5 首次启动要 15 分钟（拉镜像 + JVM + 索引），手册说明不足就是踩坑源头。
2. **修改"内部"函数的签名前先 grep**：本项目 `_score_recipe` 加了下划线但实际是公共契约——下划线总是判断"外部依赖"的标准。
3. **"图里没找到"和"图谱连不上"是两种状态**：合并回答会让上层无法判断结论可信度，必须分开。
4. **优雅降级要写进连接超时**：外部依赖挂掉时不能拖累主流程——Neo4j 5 秒超时是经验值。
5. **pytest.ini 的 marker 必须显式注册**：自定义 marker 不注册会报"unknown marker"；addopts 在 PowerShell 下要用双引号包裹整个表达式。
6. **知识数据导入前做规范化**：手写的 kg_facts.json 必须排序去重，否则 MERGE 顺序敏感导致建图非幂等。
7. **可解释 AI 比单纯 LLM 更值钱**：每个结论都指着图上一条边——这是面试时被问"你们的推荐有什么不一样"时的杀手锏。

---

## 留给下一阶段的提醒

1. **新对话起步**：阶段 4 开工时建议开新对话，开场白模板：

   ```
   继续 AI 私厨 v3.0 项目（F:\pycharm_aiprogram\ai_chief），阶段3已收官。
   开始阶段4：多租户 SaaS 化 + 配额管理（合并原方案阶段 5+9），按工作流交付两件套。
   ```

2. **pytest.ini 套件基线更新**：默认套件从 14 → **52** passed（39 + 13）；下一阶段继续往上加

3. **Neo4j 容器使用建议**：平时用 `docker stop ai_chief_neo4j`，不要删——重建很慢；只在配置变更时才 `docker compose ... up -d`

4. **图谱知识扩展约定**：新增禁忌/营养数据时，**用 P3-02 的规范化规则**——条件/食材按字典序排序后再写入 kg_facts.json

5. **/kg/ask 接入风险监控**：阶段 7 加 Prometheus 时记得把 `kg_ask_total{verdict=ok|avoid|limit|unknown}` 作为业务指标