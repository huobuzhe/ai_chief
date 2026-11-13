# AI 私厨 v3.0 · 阶段 2：多模型智能路由 + Token 计费（新增内容说明手册）

> **本手册定位**：全项目**唯一一处逐行代码解释**——讲清楚阶段 2 的每一行"在做什么、为什么这么写"。操作步骤请看操作手册（照着做），本手册只负责"看懂为什么"，两者绝不重复。
> 风格约定：代码行尾加简洁中文注释；解释表不加序号；不编造真实数据示例。

---

## 目录

- [一、本阶段在做什么（一句话与全景图）](#一本阶段在做什么一句话与全景图)
- [二、为什么要路由：一张价目表引发的架构](#二为什么要路由一张价目表引发的架构)
- [三、思考模式：本阶段实测挖出的最大一笔节省](#三思考模式本阶段实测挖出的最大一笔节省)
- [四、config.py 新增两行解释](#四configpy-新增两行解释)
- [五、models.py 分档工厂逐行解释](#五modelspy-分档工厂逐行解释)
- [六、model_router.py 逐行解释（本阶段核心）](#六model_routerpy-逐行解释本阶段核心)
- [七、token_billing.py 逐行解释（记账中心）](#七token_billingpy-逐行解释记账中心)
- [八、api/billing.py 与 main.py 改动解释](#八apibillingpy-与-mainpy-改动解释)
- [九、recognizer.py / output.py 的三处改动解释](#九recognizerpy--outputpy-的三处改动解释)
- [十、三个测试文件解释](#十三个测试文件解释)
- [十一、route_compare.py 实验设计解释](#十一route_comparepy-实验设计解释)
- [十二、常见疑问](#十二常见疑问)

---

## 一、本阶段在做什么（一句话与全景图）

**一句话**：让系统学会"看菜下饭"——简单任务用便宜模型、复杂任务用好模型，每一次调用的花费自动记账，省了多少一目了然。

```text
                         ┌──────────────────────────────────────────┐
                         │            智能路由 model_router          │
   识别节点(抽食材) ──►  │  extract + 复杂度判别 ──► lite(qwen-flash) │ ──► 便宜
                         │                        └► standard(plus) │ ──► 复杂输入升档
   输出节点(写报告) ──►  │  report（恒 standard） ──► standard(plus)  │ ──► 质量优先
   识别节点(看图)   ──►  │  vision（固定）        ──► omni 视觉模型   │ ──► 不适用档位
                         └──────────────┬───────────────────────────┘
                                        │ 每次调用结束自动挂账
                                        ▼
                         ┌──────────────────────────────────────────┐
                         │          Token 计费 token_billing         │
                         │  进程内账本(保底) + Redis 账本(重启不丢)    │
                         │  按官方刊例价折算成元 → /billing/stats     │
                         └──────────────────────────────────────────┘
```

改造前后的对比（对业务节点来说只改了一行调用）：

```text
改造前：response = await get_chat_model().ainvoke(消息)          # 所有任务一个模型
改造后：response = await ainvoke_routed("任务类型", 消息, text)    # 路由选档+自动记账+失败降级
```

---

## 二、为什么要路由：一张价目表引发的架构

阶段 2 开工时先做了一件不起眼但最重要的事：**查官方价目表**（阿里云帮助中心《AI 服务计费（按量付费）》，2026-09 查询值）：

| 模型 | 输入（元/千token） | 输出（元/千token） | 定位 |
|---|---|---|---|
| qwen3.7-flash | 0.00024 | 0.00096 | 轻量档：便宜 |
| qwen3.7-plus | 0.0024 | 0.0096 | 标准档：**输入输出都是 flash 的 10 倍价** |
| qwen3.7-max | 0.0144 | 0.0432 | 旗舰档：plus 的 6 倍价 |

10 倍的价差意味着：如果"从一句话里抽食材"这种 flash 就能干好的活也走 plus，钱就白花了 90%。反过来，"把营养分析、菜谱排序、用户画像整合成一份贴心报告"是直接给用户看的门面活，值得花 plus 的钱。

**路由的本质 = 让每一分钱花在刀刃上，并且这件事可以被计费系统量化验证。**

> 🟡 注意价目表是"分层计价"的（比如 flash 输入超过 32K token 后单价变高），我们单次输入远小于 32K，所以实际总落第一档——但计费代码必须把分层逻辑写对，不能只算第一档，这是对"工程正确性"的尊重。

---

## 三、思考模式：本阶段实测挖出的最大一笔节省

这是计划外的收获，也是本阶段最有面试价值的一页。

**现象**：阶段 2 代码写完跑真实对话测试，报告生成耗时 58 秒（原来 v2.0 只要几秒），首字节延迟超标。

**定位**：直接调用模型看返回的 `usage` 字段，发现里面有一项 `output_token_details: {"reasoning": 147}`——qwen3.7 系列**默认开启"深度思考"模式**，模型会先生成一大段用户看不见的思考文字，再输出正式回答。

**为什么这是大问题（三个角度）**：

```text
成本：思考 token 按【输出价】计费——实测抽取任务 225 个输出 token 里 147 个是思考，
     等于 65% 的输出费用买了"看不见的过程"
延迟：报告生成从 2 秒级被拖到 58 秒（思考占大头）
必要：抽取食材、整合报告都是"指令型任务"，提示词已经把格式和规则说得清清楚楚，
     模型不需要"想"，照做就行
```

**解决**：给模型工厂加 `extra_body={"enable_thinking": False}`（DashScope 的 OpenAI 兼容参数）。实测效果：plus 生成报告 58 秒 → 2 秒级；抽取的 reasoning token 归零；流式对话端到端 79 秒 → 15.7 秒。

**为什么不干脆留着思考模式给复杂任务？** 因为我们的两个 LLM 任务（抽食材、写报告）都是指令明确的活，实测关掉后结果质量没有可感知差异。真遇到需要推理的任务（比如阶段 3 的图谱多跳推理），再按任务单独开——**这是一个"默认关、按需开"的决策，而不是一刀切**。

---

## 四、config.py 新增两行解释

```python
    MODEL_LITE: str = "qwen3.7-flash"       # 🟢 v3阶段2 新增：轻量档（简单任务，成本优先）
    MODEL_STANDARD: str = "qwen3.7-plus"    # 🟢 v3阶段2 新增：标准档（复杂任务，质量优先）
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `MODEL_LITE: str = "qwen3.7-flash"` | 声明轻量档模型名，默认 flash | 抽到配置中心：以后模型升级（比如换成下一代 flash）只改这一行或 .env，不用动代码 |
| `MODEL_STANDARD: str = "qwen3.7-plus"` | 声明标准档模型名，默认 plus | 和上面同源同理；两个档位名是"角色名"，具体用哪个模型是"演员"，角色和演员解耦 |
| 默认值直接写在字段上 | 不配 .env 也能跑 | 延续 DASHSCOPE_API_KEY 的设计哲学：导入不报错，真正调用前才校验 |

> 🟡 两个新配置**不需要改 .env**——默认值就是我们要的模型。想换模型时在 .env 加 `MODEL_STANDARD=qwen3.7-max` 这类一行即可覆盖（pydantic-settings 的规则：.env 优先于代码默认值）。

---

## 五、models.py 分档工厂逐行解释

新增部分（接在 `get_vision_model` 后面）：

```python
# ============================================================
# 阶段 2（v3.0）新增：分档模型工厂——智能路由的"弹药库"
# lite 档 = qwen3.7-flash（便宜 10 倍，抽食材等简单任务）
# standard 档 = qwen3.7-plus（质量好，报告等复杂任务）
# ============================================================

@lru_cache()
def get_lite_model():
    return init_chat_model(                                    # 惰性创建：第一次调用才实例化
        model=settings.MODEL_LITE,                             # 从配置读模型名（默认 qwen3.7-flash）
        model_provider="openai",                               # 走 OpenAI 兼容协议对接百炼
        base_url=settings.DASHSCOPE_BASE_URL,                  # 百炼的兼容模式入口地址
        api_key=settings.DASHSCOPE_API_KEY,                    # 密钥从配置注入，不写死在代码里
        extra_body={"enable_thinking": False},                 # 关闭思考模式（见第三章的实测故事）
    )


@lru_cache()
def get_standard_model():
    return init_chat_model(                                    # 结构和 lite 完全对称，只有档位不同
        model=settings.MODEL_STANDARD,                         # 默认 qwen3.7-plus
        model_provider="openai",
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
        extra_body={"enable_thinking": False},                 # 报告生成同样关思考（58秒→2秒的修复）
    )


def get_model_for_tier(tier: str):
    factories = {                                              # 档位名 → 工厂函数 的映射表
        "lite": get_lite_model,
        "standard": get_standard_model,
        "vision": get_vision_model,                            # 视觉模型复用阶段 3 已有的工厂
    }
    if tier not in factories:
        raise ValueError(f"未知模型档位: {tier}（可选: {list(factories)}）")   # 漏配立刻报错，绝不静默
    return factories[tier]()
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `@lru_cache()` | 同一档位全进程只实例化一次 | 建模型对象有开销（配置解析、连接准备），对话一次要调好几次模型，不能每次都新建 |
| `extra_body={"enable_thinking": False}` | 往请求体里塞一个非标准参数 | OpenAI SDK 的 `extra_body` 专门用来传"OpenAI 没有但服务商有"的参数；百炼用它控制思考模式 |
| `get_model_for_tier` 用映射表 | 档位名 → 模型实例 | 路由器只认档位不认模型名，加新档位只需在表里加一行 |
| 未知档位抛 ValueError | 快速失败 | 路由层写错任务类型属于代码 bug，bug 要在第一次调用就炸出来，静默降级会把错误藏到线上 |

`reset_model_cache` 相应加了两行（清空新档位的单例缓存），供测试使用：

```python
def reset_model_cache():
    get_chat_model.cache_clear()             # 旧工厂也保留清理（兼容历史调用）
    get_vision_model.cache_clear()
    get_lite_model.cache_clear()             # 阶段 2：新档位一并清理
    get_standard_model.cache_clear()
```

> 🟡 旧的 `get_chat_model` **没有删除**——阶段 2 之后业务节点不再直接用它，但它仍是"能用的最简调用方式"，留着作为后备和对照。

---

## 六、model_router.py 逐行解释（本阶段核心）

### 6.1 复杂度判别（纯规则，零成本）

```python
_COMPLEX_KEYWORDS = (                        # 复杂任务的信号词元组：命中任意一个就是复杂任务
    "详细", "分析", "为什么", "怎么搭配", "营养方案", "减脂计划", "增肌计划",
    "控糖", "忌口", "过敏", "热量差", "卡路里", "搭配建议",
)
_INGREDIENT_SEP_RE = re.compile(r"[、,，;；/和与还有及]")   # 食材罗列的分隔符正则（中英文都认）


def classify_complexity(text: str) -> str:
    if not text:                             # 空输入
        return "simple"                      # 空文本无从判复杂，按简单处理（调用方本来也不会拿它调模型）
    if len(text) > 120:                      # 规则一：超过 120 字
        return "complex"                     # 长文本信息量大，轻量模型容易漏抽
    if any(kw in text for kw in _COMPLEX_KEYWORDS):   # 规则二：命中信号词
        return "complex"                     # 出现"详细/分析/控糖"说明用户要的是深度处理
    if len(_INGREDIENT_SEP_RE.split(text)) >= 6:      # 规则三：分隔符粗数 >= 6 段
        return "complex"                     # 清单越长越需要稳定的模型（漏一项都是错）
    return "simple"                          # 以上都没命中：简单任务
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 元组 `_COMPLEX_KEYWORDS` | 信号词清单 | 词表是最可解释的规则：谁都能看懂"为什么这句话被判复杂"，加词也只是一行 |
| 正则 `[、,，;；/和与还有及]` | 数食材个数 | 不追求精确分词——只需要"粗数罗列了多少项"，够用就好 |
| 三条规则按顺序短路 | 长度 → 关键词 → 数量 | 便宜的判断放前面（len 最快），命中即返回，不浪费 |
| 返回字符串 "simple"/"complex" | 而不是布尔 | 字符串可读性好，日志里一眼看懂；以后加"medium"档也不用改调用方类型 |

**为什么用规则而不是再调一次大模型来判复杂度？** 判别本身就花钱（一次小调用也是钱）、增加延迟（多一跳网络），而且判别结果自己也不可靠。规则引擎零成本零延迟、可单测、可解释——**能用确定性规则解决的事，不要用概率性的模型**。

### 6.2 路由决策

```python
def route(task: str, text: str = "") -> str:
    if task == "vision":
        return "vision"                      # 识图固定走视觉模型，档位概念不适用
    if task == "report":
        return "standard"                    # 报告直接给用户看，质量优先于成本，恒标准档
    if task == "extract":
        return "standard" if classify_complexity(text) == "complex" else "lite"   # 唯一分流的任务
    logger.warning("router: 未知任务类型 %s，按 standard 处理", task)   # 防御：写错任务名不至于崩
    return "standard"
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `route(task, text)` 返回档位名 | 而不是模型名 | 路由层只管"该用哪一档"，"这一档对应哪个模型"是 models.py 的职责——各管各的 |
| extract 是唯一分流的 | report 恒 standard | 报告是质量敏感的门面活；抽取是量大面广的基础活，分流它收益最大 |
| 未知任务兜底 standard | 宁可贵不可错 | 未知任务往往是新代码接进来，走强模型至少能答对 |

### 6.3 ainvoke_routed：业务节点唯一需要认识的函数

```python
async def ainvoke_routed(task: str, messages, text: str = ""):
    tier = route(task, text)                 # ① 决定档位
    model = get_model_for_tier(tier)         # ② 拿模型实例（单例）
    callbacks = [BillingCallbackHandler()]   # ③ 挂计费回调（见下一章）
    try:
        response = await model.ainvoke(messages, config={"callbacks": callbacks})   # ④ 正常调用
        logger.info("router: task=%s tier=%s -> %s", task, tier, getattr(model, "model_name", tier))   # ⑤ 留痕
        return response
    except Exception as exc:
        if tier in ("lite", "vision"):       # ⑥ 最便宜档失败没得降，抛给调用方走它的兜底
            raise
        logger.warning(                      # ⑦ 降级前记日志：出了事能查到"何时降的级"
            "router: %s 档调用失败（%s: %s），自动降级 lite 重试",
            tier, type(exc).__name__, exc,
        )
        lite = get_model_for_tier("lite")    # ⑧ 换 lite 再试一次
        return await lite.ainvoke(messages, config={"callbacks": callbacks})   # 降级调用同样记账
```

| 步骤 | 在做什么 | 为什么这么写 |
|---|---|---|
| ①②③④⑤ | 路由 → 取模型 → 挂账 → 调用 → 日志 | 五件事收口在一个函数里，业务节点一行代码全享受 |
| ⑥ lite/vision 失败直接 raise | 没有更便宜的退路 | output 节点自己还有纯代码兜底报告，这里的异常会被它接住 |
| ⑧ standard 失败自动降 lite | 降级链 | plus 限流/抖动时，flash 大概率还能服务——"降级"是成本治理里用户无感的那一面 |
| 降级调用同样挂 callbacks | 失败重试也要记账 | 不记账就会漏统计，成本页的数字对不上总账 |

---

## 七、token_billing.py 逐行解释（记账中心）

### 7.1 价目表

```python
PRICE_TABLE: Dict[str, List[tuple]] = {
    "qwen3.7-flash": [
        (32, 0.00024, 0.00096),              # 输入 <= 32K token：第一档（我们的调用都落这档）
        (256, 0.00072, 0.00288),             # 32K ~ 256K：第二档
        (float("inf"), 0.00144, 0.00576),    # 256K 以上：第三档
    ],
    "qwen3.7-plus": [
        (256, 0.0024, 0.0096),               # 我们单次输入远小于 256K，实际总落这档
        (float("inf"), 0.0072, 0.0288),
    ],
    "qwen3.7-max": [
        (float("inf"), 0.0144, 0.0432),
    ],
}
UNPRICED = "unpriced"                        # 价目表里没有的模型的标记
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 每个模型一个列表，元素是三元组 | (输入上限, 输入价, 输出价) | 阿里云是分层计价，表结构直接照着官方规则建模，不简化失真 |
| `float("inf")` 兜底档 | 永远能命中 | 保证任何输入长度都能算出价，不会走到"没档可配"的分支 |
| 价格放代码不放 .env | 常量性质 | 刊例价是供应商定的客观事实，不是部署环境变量；改价是代码变更，要走 git 留痕 |

### 7.2 记账函数与双写

```python
_memory_book: Dict[str, Dict[str, int]] = {}     # 进程内保底账本：重启就空，但零依赖


def record(model: str, input_tokens: int, output_tokens: int, ok: bool = True) -> None:
    if not model:
        model = "unknown"                     # 防御：模型名缺失也别记到奇怪的地方
    book = _memory_book.setdefault(           # ① 进程内账本：永远写
        model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0}
    )
    if ok:
        book["calls"] += 1                    # 成功调用：次数 + 两个 token 数
        book["input_tokens"] += int(input_tokens or 0)
        book["output_tokens"] += int(output_tokens or 0)
    else:
        book["errors"] += 1                   # 失败调用：只记错误数（失败也可能计费，要可见）
    try:
        from app_my.core.redis_client import get_redis, redis_available   # ② Redis 账本：尽力写
        if redis_available():
            r = get_redis()
            key = f"{_REDIS_PREFIX}:{model}"  # 键形如 billing:v1:qwen3.7-flash
            if ok:
                r.hincrby(key, "calls", 1)    # HINCRBY 原子自增：并发记账不打架
                r.hincrby(key, "input_tokens", int(input_tokens or 0))
                r.hincrby(key, "output_tokens", int(output_tokens or 0))
            else:
                r.hincrby(key, "errors", 1)
    except Exception as exc:
        logger.warning("billing: Redis 记账失败（不影响业务）: %s", exc)   # 记账永远不能拖垮对话
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 双写（内存 + Redis） | 两条腿走路 | 内存版零依赖（单测用），Redis 版跨重启累计（生产用）——Redis 挂了退内存，功能降级不失效 |
| 函数内 import redis | 惰性导入 | 记账模块被 import 时不触发 Redis 连接，和 models.py 的惰性哲学一致 |
| `HINCRBY` | 原子自增 | 多个请求并发记账时不需要加锁，Redis 单线程保证不丢账 |
| `except` 整段兜住 | 记账失败只记日志 | 记账是旁路功能，它出问题不能影响主对话——这是"可观测性组件"的通用素养 |

### 7.3 计费回调（自动记账的机关）

```python
class BillingCallbackHandler(BaseCallbackHandler):
    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        try:
            generation = response.generations[0][0]     # 取第一代第一条（我们一次只调一个模型）
            message = getattr(generation, "message", None)   # Chat 模型的返回里带着消息对象
            if message is None:
                return
            usage = getattr(message, "usage_metadata", None) or {}   # 官方返回的真实 token 数
            input_t = usage.get("input_tokens", 0)
            output_t = usage.get("output_tokens", 0)
            meta = getattr(message, "response_metadata", None) or {}
            model = meta.get("model_name") or meta.get("model") or "unknown"   # 真实命中的模型名
            if input_t or output_t:
                record(model, input_t, output_t)        # 有数才记（空调用记了也是脏数据）
        except Exception as exc:
            logger.warning("billing: 记账异常（已忽略）: %s", exc)

    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        try:
            record("error", 0, 0, ok=False)             # 失败也记账：错误在成本页可见
        except Exception:
            pass
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `on_llm_end` | LangChain 的钩子：每次模型调用正常结束时自动触发 | 不用改业务代码，挂上回调就自动记账——这就是"自动"两个字的实现 |
| 读 `usage_metadata` | 服务商返回的真实 token 用量 | 官方数字最准，比任何本地估算都可靠；拿不到就记 0，不猜 |
| 读 `response_metadata.model_name` | 本次真实调用的模型名 | 降级发生后，实际用的可能是 lite——账要记在真实模型头上，不能记在"想调用的模型"头上 |
| 整个方法包 try/except | 结构异常不外抛 | 模型返回结构千奇百怪（尤其非 chat 格式），记账器必须比数据更皮实 |

### 7.4 成本估算与统计

```python
def estimate_cost_cny(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    tiers = PRICE_TABLE.get(model)
    if not tiers:
        return None                            # 价目表没有：返回 None（诚实：宁缺毋假）
    for limit, in_price, out_price in tiers:   # 从便宜档往下找第一个命中的
        if input_tokens <= limit * 1000:       # 上限单位是"千token"，乘回 1000 再比
            return input_tokens / 1000 * in_price + output_tokens / 1000 * out_price
    return None
```

`get_billing_stats()` 生成统计时算了三个关键数字（省钱口径）：

```text
baseline = 所有已计价调用【假设全走 plus】的费用   —— "不差钱"基线
actual   = 当前实际发生的费用（lite 部分很便宜）    —— 路由后的真实成本
saved %  = (baseline - actual) / baseline        —— 智能路由省了多少钱
```

> 🟡 为什么 baseline 选 plus 而不是 v2.0 的 flash？因为 v3.0 的定位是"报告要升级到 plus 的质量"，公平的对比是"同样用 plus 的质量，路由帮你省了多少"。全 flash（v2.0 现状）作为另一个参照系放在实验脚本里对比（见第十一章）。

---

## 八、api/billing.py 与 main.py 改动解释

```python
# app_my/api/billing.py（整文件新增）
router = APIRouter()                                  # 标准 FastAPI 路由器

@router.get("/stats")
async def billing_stats():
    return get_billing_stats()                        # 直接把统计字典作为 JSON 返回
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 一个 GET 接口 | 查询成本统计 | 只读接口，简单到不需要请求参数和校验 |
| 不做白名单放行 | 默认走 JWT 鉴权 | AuthMiddleware 的规则是"不在白名单就要 token"——成本数据属于经营信息，必须登录才能看 |

main.py 的两行改动：

```python
from app_my.api import oss, chat, auth, user, billing   # 新增 billing 导入
app.include_router(billing.router, prefix="/billing", tags=["成本统计(v3阶段2)"])   # 注册路由
```

---

## 九、recognizer.py / output.py 的三处改动解释

业务节点的改动刻意做到最小——每处只是"换个函数名 + 多传一个参数"：

```python
# recognizer.py 导入区
from app_my.core.model_router import ainvoke_routed   # 🔵 原来导入 get_chat_model/get_vision_model

# 看图分支
response = await ainvoke_routed("vision", [SystemMessage(content=IMAGE_SYS), message])
# 原来是：await get_vision_model().ainvoke([...])

# 文字抽取分支
response = await ainvoke_routed(
    "extract",
    [SystemMessage(content=TEXT_SYS), HumanMessage(content=prompt)],
    text=text,                       # 把用户原文传给路由，供复杂度判别用
)
# 原来是：await get_chat_model().ainvoke([...])

# output.py 报告生成
response = await ainvoke_routed("report", [SystemMessage(content=OUTPUT_SYS), HumanMessage(content=prompt)], text=user_text)
# 原来是：await get_chat_model().ainvoke([...])
```

| 改动点 | 在做什么 | 为什么这么写 |
|---|---|---|
| 换成 `ainvoke_routed` | 路由+计费+降级一站完成 | 节点代码不感知"哪个模型在干活"，只声明"我在做什么类型的任务" |
| extract 传 `text=text` | 给复杂度判别提供原文 | 路由规则需要看用户输入才能判简单复杂 |
| output 传 `text=user_text` | 同上（报告恒 standard，传了备将来用） | 保持两个节点调用形状一致，少一种"特例" |

原有的 try/except、JSON 容错解析、兜底报告逻辑**一行没动**——路由失败抛出的异常依然会被 output 节点自己的 except 接住走兜底报告，两层保险叠加。

---

## 十、三个测试文件解释

| 文件 | 测什么 | 为什么这么测 |
|---|---|---|
| `tests/unit/test_model_router.py`（13 例） | 复杂度三规则、路由映射、价目表数学 | 规则引擎的全部价值在"可单测"——不打模型就能证明分流逻辑正确 |
| `tests/unit/test_token_billing.py`（10 例） | 记账累计、回调记账、假返回不崩、统计口径与省钱百分比 | 用手工构造的假模型返回（带 usage_metadata 的 AIMessage）测回调，不需要花钱调真模型 |
| `tests/integration/test_billing_api.py`（2 例） | 接口鉴权 401、登录后返回结构完整 | 集成层只验证"接口活着且守规矩"，数字本身可能是 0（还没人对话过），只验字段不验值 |

计费单测里有一个值得记住的坑：

```python
@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    import app_my.core.redis_client as redis_client        # 必须patch【源模块】
    tb._memory_book.clear()
    monkeypatch.setattr(redis_client, "redis_available", lambda: False)
```

> 🔴 为什么 patch 的是 `redis_client` 而不是 `token_billing`？因为 token_billing 的 `record()` 里是**函数内局部 import**——每次调用时才从源模块拿 `redis_available`。如果你 patch billing 模块自己的引用，局部 import 拿到的还是没被 patch 的原函数，测试就会"看似隔离、实际在写真 Redis"。这是本阶段实测踩过的坑（第一版单测就这么挂的：期望记 2 笔，Redis 里历史数据凑成了 5 笔）。

---

## 十一、route_compare.py 实验设计解释

验收要求"省多少"必须是**实测数字**，所以写了一个对照实验脚本，设计逻辑：

```text
同一批场景（6 个：短输入/罗列输入/信号词输入/长输入）
   │
   ├─ 策略A all-flash ：所有调用走 qwen3.7-flash   ← v2.0 现状（成本基线）
   ├─ 策略B all-plus  ：所有调用走 qwen3.7-plus    ← 不差钱基线（质量基线）
   └─ 策略C routed    ：智能路由分流               ← 本阶段的方案
   │
   每个场景 x 每种策略 = 2 次真实调用（抽取 + 报告，用的是生产同款提示词）
   产出：token 数（真实）、费用（价目表折算）、平均延迟（实测）
```

| 设计点 | 为什么 |
|---|---|
| 用生产的 `TEXT_SYS`/`OUTPUT_SYS` 提示词 | 实验结果才能外推到生产——自造提示词测出来的省钱比例不算数 |
| 报告提示词用 recipes.json 里的真实菜谱 | 让 plus 的生成负载接近真实（提示词长度影响 token 数） |
| 脚本自带本地记账（LocalBilling） | 实验数据和生产账本隔离：跑一百次实验也不污染 /billing/stats |
| 三策略而不是两策略 | 光说"省多少"容易被质疑"你比的是啥"；三策略同时回答"比 v2 贵了多少（买质量）"和"比全 plus 省了多少（路由收益）" |

---

## 十二、常见疑问

**Q1：路由判别会不会误判？比如把复杂任务判成简单，质量下降？**
会存在边界案例，但风险被两层兜住：① 误判只发生在 extract 任务（report 恒 standard）；② extract 判复杂的三条规则都是"宁可判复杂"的保守取向（信号词表里都是明确的质量敏感词）。真漏判了，flash 的抽取实测也是准的——规则的目的是分流成本大头，不是追求完美分类。

**Q2：计费数据能撑多久？Redis 会不会越长越大？**
每个模型只占一个 hash 键、四个字段，增长的是数值不是键数量——一年也长不出多少字节。要做"按天/按租户拆账"是阶段 9（多租户）的事，届时把键从 `billing:v1:{model}` 扩成 `billing:v1:{tenant}:{model}` 即可，这就是版本号 v1 留在键名里的原因。

**Q3：为什么视觉模型不定价、不参与省钱比例？**
qwen3.8-omni 的官方刊例结构和文本模型不同（按时长/多模态 token 混合计费），没有公开可比的千 token 单价。乱填一个数就是编数据——宁可标注 `unpriced`，token 照记、费用显示 null。**诚实是成本治理的第一原则。**

**Q4：降级（plus 失败换 flash）会不会让用户感觉报告质量忽好忽坏？**
会有一点，但这是设计过的取舍：降级只在 plus 调用失败（限流/网络）时触发，概率低；且降级报告（flash 写）仍远好于兜底报告（纯代码拼的模板）。质量排序：plus 正常 > 降级 flash > 纯代码兜底 > 报错。

**Q5：思考模式关了，会不会影响以后更复杂的任务？**
只关了这两个工厂（lite/standard）的默认行为。阶段 3 图谱推理如果需要思考，可以给那个任务单独建一个"开思考"的模型实例——决策是"默认关、按需开"，不是永久封死。
