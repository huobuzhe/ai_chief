# AI 私厨 v3.0 · 阶段 2：多模型智能路由 + Token 计费（问题与解决记录）

> **阶段状态**：已收官（2026-09-28）。施工一次通过（**施工期问题 0 个**，历史第二次）；本记录整理的全部是**手册实测期**（AI 在临时目录验证代码时）发现并已在交付手册中修复的问题——按项目惯例留档，方便面试时讲"踩过的坑"。

---

## 目录

- [一、一分钟结论](#一一分钟结论)
- [二、背景](#二背景)
- [三、问题总览](#三问题总览)
- [四、问题详情](#四问题详情)
  - [P1：报告生成要 58 秒，流式对话 79 秒首字节超时（qwen3.7 默认开思考模式）](#p1报告生成要-58-秒流式对话-79-秒首字节超时qwen37-默认开思考模式)
  - [P2：抽取任务 65% 的输出 token 是"思考"，白花钱](#p2抽取任务-65-的输出-token-是思考白花钱)
  - [P3：Token 计费单测"账对不上"——monkeypatch 打错了模块](#p3token-计费单测账对不上monkeypatch-打错了模块)
  - [P4：对比实验脚本从 scripts/ 目录跑不起来](#p4对比实验脚本从-scripts-目录跑不起来)
  - [P5：flash 输出 token 反而比 plus 多 40%（实测发现，非 Bug）](#p5flash-输出-token-反而比-plus-多-40实测发现非-bug)
- [五、修改清单总表](#五修改清单总表)
- [六、经验教训](#六经验教训)

---

## 一、一分钟结论

阶段 2（智能路由 + Token 计费）一次施工通过，39 例测试全绿、真实 LLM 流式 15.7 秒、对比实验跑出真实省钱数字（路由比全 plus 基线省 5.1%，日常对话账本省 23.2%）。

本阶段最大的收获不是路由本身，而是**实测挖出的"思考模式"大坑**：qwen3.7 系列默认开启深度思考，思考 token 按输出价计费（一单抽取任务 65% 的输出 token 是思考），还把报告生成拖到 58 秒。一行 `extra_body={"enable_thinking": False}` 同时修好了延迟和成本——这类"只有跑过真实数据才知道"的问题，正是本阶段价值所在。

## 二、背景

- v3.0 阶段 2 合并了原方案的阶段 4（多模型路由）+ 阶段 16（成本治理），因为"选哪个模型"和"花了多少钱"本质是同一件事的两面。
- 交付物：`model_router.py`（规则路由 + 降级链）、`token_billing.py`（回调自动记账 + 刊例价折算）、`/billing/stats` 接口、23 个新测试、`route_compare.py` 对比实验。
- 所有代码在 `C:\tmp\stage2_build` 临时目录实测（后端 9003 + Redis 15 号库隔离），项目目录零改动，验证通过后才写入手册。

## 三、问题总览

| # | 问题 | 严重度 | 发现期 | 状态 |
|---|---|---|---|---|
| P1 | 思考模式默认开启：报告 58s / 流式 79s 超时 | 🔴 高（验收阻塞） | 手册实测期 | ✅ 已修复 |
| P2 | 思考 token 按输出价计费，抽取任务 65% 白花 | 🔴 高（成本） | 手册实测期 | ✅ 已修复 |
| P3 | 计费单测读到 Redis 历史账，账对不上 | 🟡 中（测试可靠性） | 手册实测期 | ✅ 已修复 |
| P4 | 实验脚本从 scripts/ 跑报 ModuleNotFoundError | 🟡 中 | 手册实测期 | ✅ 已修复 |
| P5 | flash 输出 token 比 plus 多 40%（啰嗦） | 🟣 发现（非 Bug） | 手册实测期 | ✅ 已写入文档 |

> 施工期问题：**0 个**——用户按手册一次通过，未提出任何报错。

## 四、问题详情

### P1：报告生成要 58 秒，流式对话 79 秒首字节超时（qwen3.7 默认开思考模式）

**现象**：
- 真实 LLM 流式测试（`tests/test_chat_llm.py -m llm`）失败，断言"首字节延迟 < 60 秒"被击穿。
- 后端日志显示 `output` 节点调用 `qwen3.7-plus` 生成报告耗时 58 秒；整条流式链路端到端 79 秒。
- 抽取节点（flash）单独调用却只要 3.7 秒——同为 qwen3.7 系列，速度差 15 倍，不合常理。

**定位**：
1. 先排除网络/限流：flash 同期调用正常，说明链路没问题，是 plus 这个调用本身慢。
2. 直接用脚本裸调 plus 并打印 `usage_metadata`，发现返回里有 `output_token_details: {'reasoning': 147}`——**"reasoning token"就是思考 token，qwen3.7 系列默认开启深度思考模式**，模型先默默"想"一大段再答题。
3. 用 `extra_body={"enable_thinking": False}` 关闭后再测：plus 同样的任务 1.3 秒完成，reasoning token 归零。实锤。

**解决**：`models.py` 的两个分档工厂（`get_lite_model` / `get_standard_model`）统一加：

```python
extra_body={"enable_thinking": False},   # 关闭思考模式（v3阶段2 实测修复）
```

`route_compare.py` 实验脚本里也加了同样的参数（与生产一致，保证实验数字可比）。

**验证**：重启后端后重跑：

```text
pytest tests/test_chat_llm.py -m llm -q  →  1 passed
流式端到端：79 秒 → 15.7 秒；plus 生成报告：58 秒 → 2 秒级
```

**预防**：
- 以后接入任何 qwen3.x 系列新模型，第一件事先看 `usage_metadata.output_token_details` 里有没有 reasoning——有就评估这个任务需不需要思考，不需要就关。
- 思考模式不是坏东西：复杂推理任务（比如多约束规划）值得开；但"抽食材""套模板写报告"这类指令型任务纯属浪费。按任务开关，而不是全局一刀切。

### P2：抽取任务 65% 的输出 token 是"思考"，白花钱

**现象**：P1 排查过程中的连带发现——flash 抽取任务一次返回 225 个输出 token，其中 **147 个是思考 token**（占 65%）。思考 token 按输出价计费，等于一单多花了近两倍的钱，而抽取结果完全不需要思考。

**定位**：与 P1 同源（默认思考模式），但危害维度不同——P1 是延迟问题，P2 是成本问题。这个发现让"关闭思考模式"从性能优化升级成了**成本治理动作**，写进了本阶段的设计文档。

**解决**：同 P1（同一行代码修两个问题）。

**验证**：关闭后 `output_token_details` 里 reasoning 归零，抽取结果与开启时一致（食材识别完全正确）。

**预防**：Token 计费系统（`token_billing.py`）记录的是官方返回的真实 usage，天然能暴露这类"隐形消耗"——以后做成本分析时优先看 `output_token_details` 拆分，而不是只看总数。

### P3：Token 计费单测"账对不上"——monkeypatch 打错了模块

**现象**：23 个新增单测里 1 个失败，断言形如 `assert 5 == 2`——账本里混进了不属于本测试的历史数据。

**定位**：
- `token_billing.record()` / `_read_book()` 内部用的是**函数内局部 import**：`from app_my.core.redis_client import get_redis, redis_available`。
- 单测 fixture 里我最初 patch 的是 `tb`（billing 模块）里的 `redis_available` 引用——但局部 import 每次调用时都从**源模块** `redis_client` 现取，patch billing 模块的引用拦不住真正的源头，导致单测读到了 Redis 里的真实历史账。

**解决**：fixture 改为 patch 源模块：

```python
import app_my.core.redis_client as redis_client
monkeypatch.setattr(redis_client, "redis_available", lambda: False)
```

**验证**：重跑 `pytest tests/unit -q` → 23/23 全绿。

**预防**：
- **monkeypatch 铁律：patch 要打在"使用发生的现场"**。函数内局部 import 的场景，现场就是源模块——patch 消费方模块没用。
- 这个坑已写进操作手册错误对照表 E4，单测代码里也留了注释说明为什么必须 patch 源模块。

### P4：对比实验脚本从 scripts/ 目录跑不起来

**现象**：`python scripts/route_compare.py` 报 `ModuleNotFoundError: No module named 'app_my'`。

**定位**：Python 的模块搜索路径（sys.path）以**脚本所在目录**为起点——从项目根目录执行 `python scripts/route_compare.py` 时，起点是 `scripts/`，找不到项目根下的 `app_my` 包。v2.0 的 `verify_stage6.py` 早就踩过并修过这个坑。

**解决**：脚本开头加两行（与 v2.0 的 `verify_stage6.py` 同款方案）：

```python
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))   # 把项目根目录加入搜索路径
```

**验证**：项目根目录执行 `python scripts/route_compare.py` 正常运行，完成 36 次真实调用。

**预防**：以后所有放 `scripts/` 下的脚本都自带这两行——已经是项目惯例，写代码时直接抄同款。

### P5：flash 输出 token 反而比 plus 多 40%（实测发现，非 Bug）

**现象**：对比实验结果反直觉——flash 平均延迟（25.9s）比 plus（22.5s）还慢，输出 token 21753 个比 plus 的 15496 个**多 40%**。

**定位**：这不是 Bug，是模型行为差异：**flash 比 plus 啰嗦**。轻量模型倾向于写更长的文字来弥补能力差距，字数一多，延迟和 token 都上去了。单价便宜 10 倍但字数多 40%，实际省钱比例低于单价差（实验里只省 5.1%，而不是理想的 90%）。

**解决**：不需要改代码——把它当作**实验的核心发现**写进了手册 12 章"怎么读这个数字"：路由省的是"能省的部分"，不是硬砍质量；省钱比例取决于流量结构（日常短对话 simple 占比高，账本显示省 23.2%）。

**验证**：数字可复现（对比实验脚本随时可重跑）；/billing/stats 真实账本与之互相印证。

**预防/启发**：
- **别只看刊例价做决策**——模型行为差异（输出长度、风格）会吃掉单价差，必须实测。
- 这也是面试的好素材：能讲出"flash 单价便宜 10 倍但我们实测只省 5.1%，因为轻量模型更啰嗦"，比背概念有说服力得多。

## 五、修改清单总表

| 文件 | 改动 | 对应问题 |
|---|---|---|
| `app_my/core/models.py` | 两个分档工厂加 `extra_body={"enable_thinking": False}` | P1、P2 |
| `scripts/route_compare.py` | 脚本开头加 `sys.path.insert` 项目根 | P4 |
| `tests/unit/test_token_billing.py` | `_isolated` fixture 改为 patch `redis_client` 源模块 | P3 |
| 操作手册 12 章 | 新增"怎么读这个数字"三问解读 | P5 |
| 操作手册 14 章 | 错误对照表 E2/E3/E4 记录三个坑的速查版 | P3、P4、P1 |

> 以上修改全部发生在**手册成稿之前**（临时目录实测期），用户拿到的手册已是修复后版本，因此施工期 0 问题。

## 六、经验教训

1. **新模型接入先看 usage 细节**：`usage_metadata.output_token_details` 里的 reasoning token 是隐形成本+隐形延迟的双重杀手，一行参数解决，但不去实测永远不会发现。
2. **monkeypatch 打"使用现场"，不打"导入现场"**：局部 import 的场景 patch 源模块，这个教训适用于所有 Python 项目。
3. **scripts/ 下脚本自带 sys.path 修正**：项目惯例第三次出现（v2 verify_stage6 → v3 route_compare），已成肌肉记忆。
4. **实验的价值在反直觉的发现**：flash 更啰嗦、省钱比例取决于流量结构——这些"做了实验才知道"的细节，是简历和面试里最经得起追问的部分。
5. **一次施工通过的经验**：代码在临时目录全链路实测（含真实 LLM 调用和 36 次实验）再交付手册，问题在到达用户之前就被消灭——这是阶段 6 以来第二次实现"施工期 0 问题"，值得坚持。
