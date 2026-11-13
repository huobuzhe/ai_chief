# AI 私厨 v3.0 · 阶段 10 说明手册
## 看懂为什么：逐行代码解释 + 专业名词

> **这份手册和《操作手册》的分工**：
> - **操作手册 = 照着做**：建什么文件、粘贴什么内容、跑什么命令、看到什么算成功。
> - **说明手册 = 看懂为什么**（本文件）：每一行代码在做什么、为什么这么写、每个参数什么意思。
>
> **全项目只有这一处做逐行代码解释**，操作手册里不再重复。
>
> **代码里的注释规则**：每段代码我都在**行尾加了中文注释**解释该行作用，**注释不加序号**，方便你直接照抄落盘。
> 代码块下面再用"这一段在做什么 / 为什么要这么写"讲一遍设计理由。

---

## 目录

- [一、这一阶段到底在干什么](#一这一阶段到底在干什么)
- [二、章节顺序对照表](#二章节顺序对照表)
- [三、专业名词解释表](#三专业名词解释表)
- [四、逐行解释：app_my/core/mock_llm.py](#四逐行解释app_mycoremock_llmpy)
- [五、逐行解释：app_my/core/config.py（改动）](#五逐行解释app_mycoreconfigpy改动)
- [六、逐行解释：app_my/core/model_router.py（改动）](#六逐行解释app_mycoremodel_routerpy改动)
- [七、逐行解释：app_my/knowledge/embedding.py（改动）](#七逐行解释app_myknowledgeembeddingpy改动)
- [八、逐行解释：benchmarks/locustfile.py](#八逐行解释benchmarkslocustfilepy)
- [九、逐行解释：scripts/run_bench.sh](#九逐行解释scriptsrun_benchsh)
- [十、逐行解释：scripts/locust_report.py](#十逐行解释scriptslocust_reportpy)
- [十一、逐行解释：docker/Dockerfile.svc](#十一逐行解释dockerdockerfilesvc)
- [十二、逐行解释：docker/docker-compose.prod.yml](#十二逐行解释dockerdocker-composeprodyml)
- [十三、逐行解释：.gitee/workflows/pipeline.yml](#十三逐行解释giteeworkflowspipelineyml)
- [十四、逐行解释：scripts/ci_local.sh](#十四逐行解释scriptsci_localsh)
- [十五、逐行解释：scripts/verify_stage10.py](#十五逐行解释scriptsverify_stage10py)
- [十六、PowerShell 版脚本的翻译要点](#十六powershell-版脚本的翻译要点)
- [十七、面试追问预案](#十七面试追问预案)

---

## 一、这一阶段到底在干什么

一句话：**回答"微服务拆分到底值不值"，并把答案变成可复现的数字；顺带把项目从"能跑"升级成"能交付"。**

拆成四块：

```
① 打桩（Mock）  →  让压测测的是"我的架构"，不是"大模型厂商的服务器"
② 压测（Locust）→  同一份脚本打两个架构，跑出 P99 / QPS / 拐点
③ 生产部署      →  gunicorn 多 worker + 容器健康检查 + 非 root + 资源上限
④ CI/CD         →  提交即跑单测与校验，附本地等价脚本保证"提交前就知道"
```

**为什么必须先做①再做②**：压测的原始数据（响应时间）里混着外部大模型调用的耗时。那个耗时随厂商负载剧烈波动，两次跑能差一倍。不摘掉它，你得到的数字是"DashScope 今天的网速"，不是"你的架构能扛多少并发"。面试官一问"这个 QPS 是谁的 QPS"就答不上来。

---

## 二、章节顺序对照表

说明手册的章节顺序**镜像操作手册的执行顺序**，方便你两边对照着看。

| 操作手册节 | 做了什么 | 本手册对应章节 |
|---|---|---|
| §7.1 | 新建 `mock_llm.py` | [四](#四逐行解释app_mycoremock_llmpy) |
| §7.2 | 改 `config.py` 加开关 | [五](#五逐行解释app_mycoreconfigpy改动) |
| §7.3 | 改 `model_router.py` 接上打桩 | [六](#六逐行解释app_mycoremodel_routerpy改动) |
| §7.4 | 改 `embedding.py` 打桩 | [七](#七逐行解释app_myknowledgeembeddingpy改动) |
| §8.1 | 新建 `locustfile.py` | [八](#八逐行解释benchmarkslocustfilepy) |
| §9.1 | 新建 `run_bench.sh` | [九](#九逐行解释scriptsrun_benchsh) |
| §9.3 | 新建 `locust_report.py` | [十](#十逐行解释scriptslocust_reportpy) |
| §10.2 | 新建 `Dockerfile.svc` | [十一](#十一逐行解释dockerdockerfilesvc) |
| §10.3 | 新建 `docker-compose.prod.yml` | [十二](#十二逐行解释dockerdocker-composeprodyml) |
| §11.1 | 新建 `pipeline.yml` | [十三](#十三逐行解释giteeworkflowspipelineyml) |
| §11.2 | 新建 `ci_local.sh` | [十四](#十四逐行解释scriptsci_localsh) |
| §12.1 | 新建 `verify_stage10.py` | [十五](#十五逐行解释scriptsverify_stage10py) |
| §9.2 / §11.3 | 两个 `.ps1` 脚本 | [十六](#十六powershell-版脚本的翻译要点) |

---

## 三、专业名词解释表

本阶段新出现的名词，按"你在哪一步会遇到它"排序。

| 名词 | 一句话解释 | 在本项目里具体指什么 |
|---|---|---|
| **压测（Load Test / Benchmark）** | 用程序模拟很多用户同时访问，量出系统能扛多少、什么时候开始变慢 | Locust 起 10/20/40/60 个虚拟用户打你的接口 |
| **并发数（Concurrency）** | 同一时刻有多少个"用户"在发请求 | `--users 60` = 60 个虚拟用户同时在打 |
| **QPS / RPS / 吞吐** | 每秒处理多少个请求（Queries/Requests Per Second） | 报告里"总QPS"那一列 |
| **P99 / P95 / P50** | 百分位响应时间。P99 = 把最慢的 1% 请求算进来时的耗时 | **P99 比平均值重要得多**——平均值会被大量快请求稀释，P99 才反映"最倒霉的用户等多久" |
| **平均值（avg / mean）** | 所有请求耗时的算术平均 | 参考价值最低，只看它会被误导 |
| **拐点（Knee / 性能拐点）** | 并发加到某一档，响应时间突然明显变差的那个点 | 单体在 60 并发时 P99 从 290ms 跳到 3900ms |
| **劣化（Degradation）** | 性能明显变差的状态 | 本项目判定口径：错误率 > 1% **或** P99 > 1000ms |
| **打桩 / Mock** | 用一个"假的、行为固定的"替身换掉真实依赖 | `MOCK_LLM=true` 时把大模型换成返回固定文本的假模型 |
| **测试替身（Test Double）** | Mock 的学名，泛指测试时替换真实对象的假东西 | LangChain 的 `GenericFakeChatModel` |
| **热路径（Hot Path）** | 每次请求都会走到的代码路径 | `/chat/stream` 里"识别→营养→推荐→重排→出报告"整条链 |
| **bcrypt** | 一种**故意很慢**的密码哈希算法（慢是为了防暴力破解） | 登录慢就慢在它身上，占 CPU |
| **CPU 密集型 vs IO 密集型** | CPU 密集 = 一直在算（bcrypt）；IO 密集 = 一直在等（查数据库、等网络） | 登录=CPU密集；图谱查询=IO密集。**两者的最优 worker 数不同** |
| **worker（工作进程）** | 真正处理请求的进程。多 worker = 多个进程并行 | gunicorn 起 2~3 个 UvicornWorker |
| **gunicorn** | 生产级 Python 应用服务器，管多个 worker，worker 挂了自动拉起 | **不支持 Windows**（缺 `fcntl`），只能在 Linux 容器里跑 |
| **ASGI / WSGI** | Python Web 应用的两种接口规范。ASGI 支持异步和长连接（WebSocket、SSE）；WSGI 只支持同步 | 我们的服务是 FastAPI（ASGI），所以 worker 类必须选 `UvicornWorker` |
| **UvicornWorker** | gunicorn 的一种 worker 类型，内部跑 uvicorn（ASGI 服务器） | `-k uvicorn.workers.UvicornWorker` |
| **Docker 层缓存（Layer Cache）** | Docker 按 Dockerfile 的每一行缓存一层，没变的行直接用缓存 | 所以"先拷依赖清单装依赖，再拷代码" |
| **健康检查（HEALTHCHECK）** | 容器自己定期探一下"我的应用还活着吗" | 每 30 秒打一次自己的 `/health` |
| **start_period** | 健康检查的"启动宽限期"，这段时间内的失败不算数 | 设 40s，否则服务启动慢一点就被判 unhealthy 然后被反复重启 |
| **非 root 运行** | 容器里用普通用户（uid 1000）跑应用，不用管理员 | 容器被攻破时把损失限制在这个用户能碰到的范围 |
| **日志轮转（Log Rotation）** | 日志文件超过一定大小就切新文件、保留有限个 | `max-size: 10m` + `max-file: "3"` = 最多 30MB |
| **资源上限（mem_limit / cpus）** | 限制单个容器最多能用多少内存和 CPU | 一个服务内存泄漏时不至于拖死整台机器 |
| **CI / CD** | 持续集成 / 持续部署。代码一提交就自动跑测试、构建 | Gitee Go 流水线 |
| **流水线（Pipeline）** | CI 里的一组有序步骤 | 本项目的 `test-stage` → `build-stage` |
| **YAML 锚点（Anchor）** | YAML 里给一段内容起个名字，后面用 `<<: *名字` 复用 | `x-svc-common: &svc-common` 让 4 个服务共用一套配置 |
| **DB-less 模式** | Kong 不用数据库，配置全写在一个 yaml 文件里 | 改配置必须**重启容器**才生效（Admin API 是只读的） |
| **率限制（Rate Limiting）** | 限制单位时间内的请求次数 | Kong 插件 120/min；中间件 60/min、20/min |
| **配额（Quota）** | 按套餐限制总量，比如免费用户一天 50 次对话 | Redis 里 `quota:<租户>:<指标>:<日期>` 计数 |
| **L2 归一化** | 把一个向量的长度缩成 1（每个分量除以模长） | 打桩向量的模长必须 = 1.0 |
| **余弦相似度（COSINE）** | 用两个向量的夹角衡量相似度，忽略长度 | Milvus 集合用的度量方式 |
| **PYTHONHASHSEED** | Python 的哈希随机化开关，默认开启，导致内置 `hash()` 每次进程结果不同 | 所以打桩种子必须用 `hashlib.md5`，不能用 `hash()` |
| **SSE（Server-Sent Events）** | 服务端流式推送的一种协议，格式是 `data: xxx\n\n` | 🔴 本项目 `/chat/stream` **只是** Content-Type 写了 `text/event-stream`，实际是纯文本，没有 `data:` 前缀 |
| **DB-less Kong Admin API** | Kong 在 DB-less 模式下的管理接口，只读 | 改限流只能改 yaml + 重启 |

---

## 四、逐行解释：app_my/core/mock_llm.py

### 4.1 这一段在做什么

提供一个"假的大模型"。打开开关后，所有走 `model_router.ainvoke_routed()` 的调用都会拿到一份**格式正确、耗时固定**的假回复，完全不联网。

### 4.2 代码逐行

```python
from __future__ import annotations          # 让 Python 3.9 也能写 list[dict] 这种新式类型标注

import asyncio                              # 异步 sleep 用，模拟模型耗时
from typing import Iterator, List           # 类型标注用的两个泛型

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
#                                            LangChain 官方提供的"假对话模型"，支持 invoke/ainvoke/stream/astream 四种调用方式
from langchain_core.messages import AIMessage, BaseMessage
#                                            AIMessage = 模型回复消息；BaseMessage = 所有消息的基类

# ---- 按任务类型准备的假响应 ----
_MOCK_INGREDIENT_JSON = (                   # 给"识别食材"任务用的假回复，必须能被 parse_json_payload 抠出 JSON
    '```json\n'                             # 故意包一层 markdown 代码围栏，和真实模型常见的输出格式一致
    '{"ingredients": ['                     # 食材列表，字段名必须和下游 recognizer 期待的一致
    '{"name": "西兰花", "freshness": 9, "amount": "约300g", "usable": true},'
    #                                        freshness=新鲜度 1~10；usable=是否可用
    '{"name": "鸡胸肉", "freshness": 8, "amount": "约200g", "usable": true},'
    '{"name": "鸡蛋", "freshness": 9, "amount": "2个", "usable": true}'
    '], "warnings": []}\n'                  # warnings 空数组，避免下游取这个键时 KeyError
    '```'
)

_MOCK_REPORT_TEXT = (                       # 给"生成报告"任务用的假回复，只要求非空文本
    "【压测模式固定回复】根据您提供的食材，建议采用「白灼西兰花 + 香煎鸡胸肉 + 番茄炒蛋」"
    "三菜一汤的搭配：西兰花提供膳食纤维，鸡胸肉补充优质蛋白，鸡蛋补充卵磷脂。"
    "总热量约 620 kcal，蛋白质 48g，脂肪 22g，碳水 55g，适合控糖人群。"
    "（本段为 MOCK_LLM 模式的固定压测响应，不代表真实模型输出。）"
    #                                        末尾这句声明很重要：万一哪天忘了关开关，看到它能立刻反应过来
)

MOCK_LATENCY_SEC = 0.05                     # 假模型的固定耗时 50ms（为什么不是 0，见 4.3）

_MOCK_TEXT_BY_TASK = {                      # task 名 → 假响应内容；键名必须和 model_router.route() 认识的任务名一致
    "extract": _MOCK_INGREDIENT_JSON,       # 识别节点（文字输入）
    "vision": _MOCK_INGREDIENT_JSON,        # 识别节点（图片输入），mock 时不真的看图
    "report": _MOCK_REPORT_TEXT,            # 输出节点（生成菜谱报告）
}


def _cycling(messages: List[BaseMessage]) -> Iterator[AIMessage]:
    """把固定响应"无限循环"成迭代器"""
    while True:                             # 无限循环，永远不 StopIteration
        for m in messages:                  # 把传入的消息列表一条条吐出来
            yield m                         # yield = 每次调用取一条，不一次性返回


def mock_model(text: str = _MOCK_REPORT_TEXT) -> GenericFakeChatModel:
    """造一个秒回固定文本的假对话模型"""
    return GenericFakeChatModel(messages=_cycling([AIMessage(content=text)]))
    #      messages 参数要求传"迭代器"，不是单条消息；所以要把 AIMessage 包进 _cycling


async def ainvoke_mock(task: str, messages) -> AIMessage:
    """按任务类型返回格式正确的假响应"""
    if MOCK_LATENCY_SEC:                    # 如果配了耗时（None 或 0 就跳过）
        await asyncio.sleep(MOCK_LATENCY_SEC)   # 异步等待，不阻塞事件循环
    return AIMessage(content=_MOCK_TEXT_BY_TASK.get(task, _MOCK_REPORT_TEXT))
    #      .get(task, 默认) —— 遇到不认识的任务名就退回报告文本，避免 KeyError 让请求 500
```

### 4.3 三个"为什么必须这么写"

**① 为什么 `_cycling` 要无限循环？**

`GenericFakeChatModel` 的 `messages` 参数要求是一个**迭代器**，它每次被调用就 `next()` 取一条。压测会打几百上千次请求。如果只给一条，第二次调用就抛 `StopIteration` → 被当成"模型调用失败" → output 节点降级走兜底报告、recognizer 重试一次。**P99 全被重试逻辑污染，数据不可信**。

**② 为什么假模型还要"故意慢 50ms"，而不是 0 耗时？**

如果 `MOCK_LATENCY_SEC = 0`，压测会量出一个漂亮得不真实的 QPS——瓶颈完全落在数据库/图谱/HTTP 框架上，而 LLM 那一环"白送"。真实业务里 LLM 是每请求必经的一环，压测报告必须给它留个位置，否则上线后第一波流量就被真实耗时打脸。

50ms 是"快模型返回一段固定文本"的量级（阶段 2 实测 qwen3.7-flash 关思考模式 2 秒内出报告，这里取 50ms 是**有意压低**，好让架构自身的开销占主导）。

**③ 为什么打桩点选在 `model_router.ainvoke_routed` 而不是 `models.py` 的工厂函数？**

因为**档位（lite/standard）不等于任务（extract/report/vision）**。同一个 lite 档，"抽食材"要返回 JSON、"生成报告"要返回自然语言——从 tier 推不出该给什么格式。只有 `ainvoke_routed` 才知道 `task`。

而且 `ainvoke_routed` 是全项目**唯一**还在调 LLM 的地方（旧的 `get_chat_model().ainvoke(...)` 早已被改走这里）。在这里加一个早返回分支，**一行业务代码都不用改**，关掉开关立刻恢复。

---

## 五、逐行解释：app_my/core/config.py（改动）

### 5.1 这一段在做什么

加两个配置项：一个总开关、一个标注用的名字。

### 5.2 代码逐行

```python
    # ============================================================
    # 性能压测（v3 阶段 10 新增）
    # ============================================================
    MOCK_LLM: bool = False                  # 压测总开关。默认 False —— 正常开发/跑测试绝不能受影响
    BENCH_TARGET_NAME: str = "monolith"     # 只用于日志标注，不影响业务（真正打哪个地址由 locust --host 决定）
```

### 5.3 为什么默认必须是 `False`

这不是随便定的。如果默认 `True`：

- 你平时开发时，所有对话都返回同一段假菜谱；
- 跑集成测试时全绿但毫无意义；
- **最可怕的是你查不出原因**——代码没报错，接口也返回 200，只是内容永远是那一段。

所以：**压测才临时用环境变量打开，平时必须是关的。**

### 5.4 为什么用环境变量而不是改 `.env`

`.env` 是长期配置，改了容易忘记改回来。环境变量只在那一条命令里生效：

```bash
MOCK_LLM=true ./.venv3/Scripts/python.exe -m uvicorn main:app --port 9002
```

这条命令一结束，开关就消失了。关掉终端更是彻底清干净。

> 🔴 **唯一的例外是 PowerShell**：`PS$env:MOCK_LLM="true"` 设置后会**一直留在那个窗口里**，后面启动的所有进程都会继承。所以操作手册 17.2 里专门写了 `Remove-Item Env:MOCK_LLM` 来清理。

---

## 六、逐行解释：app_my/core/model_router.py（改动）

### 6.1 这一段在做什么

在"所有 LLM 调用的唯一出口"上加一个早返回分支。

### 6.2 代码逐行

```python
from app_my.core.config import settings     # 新增：要读 MOCK_LLM 开关，得先能拿到 settings

async def ainvoke_routed(task: str, messages, text: str = ""):
    """路由 + 调用 + 计费 + 降级，一站式完成"""
    # ---------- 压测打桩分支 ----------
    if settings.MOCK_LLM:                   # 开关打开？
        from app_my.core.mock_llm import ainvoke_mock
        #   为什么在函数里 import 而不是文件顶部：生产环境不该 import 测试替身，
        #   写在函数里就只有开关打开时才会加载，正常路径零开销
        response = await ainvoke_mock(task, messages)
        #          await —— ainvoke_mock 是异步函数（里面要 asyncio.sleep）
        logger.info("router: MOCK_LLM 命中，task=%s 直接返回固定响应", task)
        #          留一条日志，方便你事后确认"到底走没走打桩"
        return response                     # 直接返回，后面的 route/model/计费全都不执行

    tier = route(task, text)                # 原逻辑：决定用哪一档模型（lite / standard）
    model = get_model_for_tier(tier)        # 原逻辑：按档位拿到模型实例
    callbacks = [BillingCallbackHandler()]  # 原逻辑：挂计费回调，调用结束自动记 token 账
```

### 6.3 三个关键设计

**① 为什么必须放在函数最前面？**

放在"任何网络调用之前"。只要它前面有一行 `route()` 或 `get_model_for_tier()`，那行就可能触发网络或读配置，打桩的意义就打折了。

**② 为什么不挂 `BillingCallbackHandler`？**

mock 没有真实 token 消耗，自然不该记账。如果挂了，压测会把**假用量写进账单表**，把阶段 2 建立的计费数据污染掉——而且这种污染是"看起来正常的数字"，很难发现。

**③ 参数怎么传？**

- `task`：原样透传，让 mock 知道该返回 JSON 还是自然语言；
- `messages`：**原样透传但不读它**。mock 的意义是"不管你问了什么，都给一个格式正确的固定答案"。真去读 prompt 反而会让 mock 行为不可预测。

---

## 七、逐行解释：app_my/knowledge/embedding.py（改动）

### 7.1 这一段在做什么

把"文本转向量"也打桩。这是**最容易漏掉的一个外部依赖**——它不在 `model_router` 的出口上，但 chat 场景每次请求都要向量化一次用户问题。

### 7.2 代码逐行

```python
import hashlib                              # 算 md5，用作随机数种子
import math                                 # 算平方根（模长）
import random                               # 生成伪随机向量

MOCK_DIMENSION = 1024                       # 必须和 Milvus 集合的 DIMENSION 一致，否则检索报维度不匹配


def _mock_embedding(text: str) -> List[float]:
    """给一段文本算一个稳定的假向量，不联网"""
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    #      md5(text) → 十六进制串 → 取前 8 位 → 按 16 进制转成整数
    #      为什么用 md5 而不是内置 hash()：Python 默认开启哈希随机化（PYTHONHASHSEED），
    #      同一个字符串在不同进程里 hash() 结果不一样。用它会导致每次重启服务，
    #      同一个查询的检索结果都在变，压测报告的"命中率"就没有可比性了
    rng = random.Random(seed)               # 用独立 Random 实例，别碰全局 random 状态（否则影响别的代码）
    vec = [rng.uniform(-1.0, 1.0) for _ in range(MOCK_DIMENSION)]
    #      生成 1024 个 [-1, 1) 之间的随机数，组成一个向量
    norm = math.sqrt(sum(v * v for v in vec))   # 算模长（勾股定理推广到多维）
    return [v / norm for v in vec]              # 每个分量除以模长 → 单位向量（L2 归一化）


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量向量化"""
    if settings.MOCK_LLM:                       # 开关打开
        return [_mock_embedding(t) for t in texts]   # 每条文本算一个假向量，不联网
    return get_embedding_model().embed_documents(texts)  # 原逻辑：真调 DashScope


def embed_query(text: str) -> List[float]:
    """单条向量化（用户查询用）"""
    if settings.MOCK_LLM:                       # 同上
        return _mock_embedding(text)
    return get_embedding_model().embed_query(text)
```

### 7.3 两个必须做对的地方（做错了数据就不可信）

**① 种子必须用 `hashlib.md5`，不能用内置 `hash()`**

Python 3 默认开启哈希随机化（`PYTHONHASHSEED`），同一个字符串在**不同进程**里 `hash()` 的结果不一样。用它会导致：每次重启服务，同一个查询的检索结果都在变——压测报告里"推荐命中率"这类数字就没有可比性了。

验证方法（操作手册 7.4）：连跑两次同一个查询，输出必须一字不差。

**② 必须做 L2 归一化**

Milvus 集合用的是 **COSINE（余弦相似度）** 度量。余弦相似度在数学上会自动除以模长，但全零向量会让分母为 0。归一化成单位向量后，点积就等于余弦值，检索分数落在 `[-1, 1]`，和真实 embedding 的分布一致，报告里的分数才读得懂。

验证方法：模长必须 = 1.0。

**③ 维度必须是 1024**

和 `app_my/knowledge/milvus_store.py` 里的 `DIMENSION` 一致。打桩时如果维度对不上，`pymilvus` 会在检索时直接抛 `vector dimension mismatch`，表现为**所有 chat 请求 500**。所以这个数字不是随手填的。

---

## 八、逐行解释：benchmarks/locustfile.py

### 8.1 这一段在做什么

定义"虚拟用户长什么样、做什么动作"。同一个文件打到两个不同的地址，就能对比两个架构。

### 8.2 代码逐行：参数区

```python
INGREDIENT_POOL = ["土豆", "西红柿", "鸡蛋", "鸡胸肉", "西兰花",
                   "牛肉", "豆腐", "虾", "黄瓜", "茄子",]
#   图谱问答的"食材"入参池。故意用多个取值而不是固定一个：
#   /kg/ask 上挂了阶段 5 的 10 分钟缓存，只压一个固定组合的话，
#   第一个请求之后全命中缓存，测出来的是"Redis 返回"的 QPS，反映不出 Neo4j 的能力。
#   10 种食材 × 3 种病症 = 30 种组合，缓存命中率才接近真实使用

CONDITION_POOL = ["糖尿病", "痛风", "高血压"]     # 图谱问答的"病症"入参池

MESSAGE_POOL = [
    "我手里有西红柿、鸡蛋和土豆，能做什么菜？",
    "帮我分析一下这些食材的营养搭配",
    "推荐三个适合控糖的菜谱",
    "中午随便吃点啥",
    "鸡胸肉和西兰花怎么做好吃，详细说一下做法",
    "我减脂期，这些食材怎么搭配",
]
#   对话输入池。刻意混合了长短句和"详细/分析"这类信号词，
#   让阶段 2 的智能路由真的在 lite/standard 档之间切换（压测要覆盖真实分支，不是只压一条路）

WAIT_MIN = float(os.getenv("BENCH_WAIT_MIN", "1"))    # 虚拟用户两次请求之间的最短停顿（秒）
WAIT_MAX = float(os.getenv("BENCH_WAIT_MAX", "2"))    # 最长停顿。取 1~2s 而不是 0，模拟真人节奏
#   设 0 是"闭压力测"——会把服务打满，只适合找极限，不适合测稳态容量

HTTP_TIMEOUT = float(os.getenv("BENCH_TIMEOUT", "60"))  # 请求超时 60 秒
#   设长一点是为了"宁可慢也别算成失败"——超时会被 Locust 记成错误，虚高错误率最难看
```

### 8.3 代码逐行：虚拟用户类

```python
class BenchUser(HttpUser):                  # 继承 Locust 的 HttpUser = 会用 HTTP 发请求的虚拟用户
    wait_time = between(WAIT_MIN, WAIT_MAX) # 两个动作之间随机等 1~2 秒

    def on_start(self):                     # 每个虚拟用户"进场"时跑一次
        _live["now"] += 1                   # 在线计数 +1
        if _live["now"] > _live["peak"]:    # 如果超过历史峰值
            _live["peak"] = _live["now"]    # 更新峰值（后面打印 summary 要用）

        self.username = "bench_" + uuid.uuid4().hex[:10]
        #   每个 VU 一个唯一用户名。uuid 前 10 位足够唯一，又不会把数据库撑大
        self.password = "Bench@12345"       # 满足 schemas/auth.py 里 min_length=8
        self.token = ""                     # 登录后存这里

        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/register", json=payload,
                              name="/auth/register [准备]", catch_response=True) as r:
        #   name= 是"统计归类名"。不写的话 Locust 按真实 URL 聚合，
        #   而 /kg/ask?ingredient=土豆&condition=糖尿病 每个请求 URL 都不一样
        #   → 统计表出现几十行、每行一次请求，没法看。写死一个 name 就聚成一类
        #   catch_response=True 才能手动判定成功/失败
            if r.status_code == 409:        # 409 = 用户名已存在
                pass                        # 不算失败（网络重试可能撞上）
            elif r.status_code not in (200, 201):
                r.failure(f"准备阶段注册失败 HTTP {r.status_code}")   # 手动标记失败

        with self.client.post("/auth/login", json=payload,
                              name="/auth/login [准备]", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"准备阶段登录失败 HTTP {r.status_code}")
            else:
                self.token = r.json().get("access_token", "")   # 拿到 token 存起来

    def on_stop(self):                      # 离场时
        _live["now"] -= 1                   # 在线计数 -1（保持峰值统计准确）

    def _headers(self):                     # 统一生成请求头
        return {"Authorization": f"Bearer {self.token}"}   # 受保护接口都要它，无 token 直接 401
```

**为什么每个 VU 都注册自己的账号，而不是共用一个？**

1. 用户名有唯一约束，共用会在并发注册时互相撞；
2. 真实场景本来就是不同的人登录不同的账号；
3. **附带好处**：登录场景压的是"多个不同账号的密码校验"，比同一个账号反复校验更接近真实的 CPU 负载（bcrypt 有内存硬开销，不能被"缓存命中"稀释）。

### 8.4 代码逐行：三个压测场景

```python
    @task(3)                                # 权重 3：10 次动作里大约 3 次选这个
    def scenario_login(self):
        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/login", json=payload, name="/auth/login",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"登录失败 HTTP {r.status_code}")

    @task(2)                                # 权重 2：最少的。因为对话是最重的链路
    def scenario_chat(self):
        payload = {
            "message": random.choice(MESSAGE_POOL),             # 从池子里随机挑一句
            "thread_id": "bench_" + uuid.uuid4().hex[:8],       # 每次新会话，避免历史串味
            "user_id": None,                                    # 传 null = 按访客处理，不查用户画像（少一次 DB 查询）
        }
        with self.client.post("/chat/stream", json=payload, name="/chat/stream",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"对话失败 HTTP {r.status_code}")
            else:
                # 🔴 不要检查 "data:" 这种 SSE 帧头！
                #    本项目 /chat/stream 虽然 Content-Type 写了 text/event-stream，
                #    但 coordinator 里是直接 `yield content`（纯文本），没有 data: 前缀。
                #    压测 v1 在这里判过 "data:"，结果 100% 请求被判失败、失败率冲到 10%+，
                #    白白浪费一轮压测。这里只判断"有没有内容吐出来"
                if not (r.text or "").strip():
                    r.failure("对话返回空正文（链路没有产出内容）")

    @task(5)                                # 权重 5：最多的。它最轻，用来顶出"架构极限 QPS"
    def scenario_recommend(self):
        ingredient = random.choice(INGREDIENT_POOL)
        condition = random.choice(CONDITION_POOL)
        with self.client.get("/kg/ask", params={"ingredient": ingredient, "condition": condition},
                             name="/kg/ask", headers=self._headers(), catch_response=True,
                             timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"图谱问答失败 HTTP {r.status_code}")
```

**为什么权重是 3 / 2 / 5 而不是平均分配？**

- **登录 3**：要让 bcrypt 反复做密码校验（`BCRYPT_ROUNDS=12`，CPU 密集），量出"CPU 被密码哈希吃掉多少"。真实生产里登录也是 CPU 瓶颈大户。
- **对话 2**（最低）：这是全项目最重的一条链路，一次请求串五个节点，还碰本地向量检索和知识图谱。它决定的是"用户感知的响应时间"，不是"系统吞吐"。
- **图谱 5**（最高）：它最轻，用它把"架构本身的极限 QPS"顶出来。

**对话和图谱两个数字放一起看才有意义**：一个测上限，一个测真实体验。

### 8.5 代码逐行：跑完自动打印汇总

```python
_live = {"now": 0, "peak": 0}               # 自己数在线数：进场 +1、离场 -1，记住过程最大值
#   为什么不用 environment.runner.user_count：退出时 runner 已被回收，只能读到 0
#   为什么不用 events.user_started：locust 2.32 里根本没有这个事件名，
#   写错一个字母就是 AttributeError，整个文件加载失败、压测根本起不来


def _rps(entry) -> float:
    """算这个场景的实际吞吐量（请求/秒）"""
    span = float(getattr(entry, "last_request_timestamp", 0) or 0) - float(getattr(entry, "start_time", 0) or 0)
    #      locust 2.32 的 StatsEntry 上没有 total_rps（老版本才有），也没有 total_time。
    #      只有 start_time 和 last_request_timestamp（都是 time.time() 的秒级浮点），
    #      所以 RPS 只能自己算：请求数 ÷ 这批请求跨越的秒数
    if span <= 0:                           # 除以 0 保护
        return 0.0
    return entry.num_requests / span        # 请求总数 ÷ 首尾时间窗


@events.quitting.add_listener               # 注册到"压测进程退出"这个事件上
def _print_bench_summary(environment, **_kwargs):
    try:                                    # 🔴 整个函数体必须包在 try 里
        _print_bench_summary_inner(environment)
    except Exception as exc:                # 兜住一切异常
        print("")
        print("=" * 96)
        print(f"BENCH SUMMARY 生成失败：{type(exc).__name__}: {exc}")
        print("（压测数据本身没丢，看同目录下的 *_stats.csv 即可）")
        print("=" * 96)
    #   locust 对事件监听器里抛出的异常只是记一条日志，**不会**让压测失败。
    #   于是表现是"压测跑完了、CSV 也生成了，但屏幕上什么都没有"，
    #   人只会怀疑是不是自己命令敲错了。阶段 10 开发时就因为写了一个不存在的属性，
    #   连续三轮压测白跑。包一层 try，任何字段名变化都会变成屏幕上一行报错，而不是静默消失


def _print_bench_summary_inner(environment):
    stats = environment.stats               # 拿统计对象
    host = str(environment.host or "")      # 拿目标地址
    target = host.rsplit(":", 1)[-1].strip("/") or "unknown"
    #      "http://127.0.0.1:9002" → 按最后一个冒号切开 → "9002"

    scenarios = (                           # 只统计这三个被测场景
        ("/auth/login", "POST"),            # (显示名, HTTP 方法)
        ("/chat/stream", "POST"),
        ("/kg/ask", "GET"),
    )

    for name, method in scenarios:
        entry = stats.get(name, method)     # 🔴 必须同时给"名字 + 方法"
        #    只传一个参数会返回空的 Entry（num_requests=0），表里场景行会全部消失
        if entry.num_requests == 0:
            print(f"{name:<16}{'（本轮未执行）':>9}")
            continue
        fail_rate = entry.num_failures / entry.num_requests * 100
        print(f"{name:<16}{entry.num_requests:>9}..."  # 格式化对齐打印
              f"{entry.get_response_time_percentile(0.99):>9.0f}"   # P99
              f"{_rps(entry):>8.1f}")                                # RPS
```

### 8.6 已经踩过的两个坑（你别再踩）

| 坑 | 现象 | 原因 |
|---|---|---|
| `stats.get(name)` 少传 method | 所有场景显示"本轮未执行" | Locust 的统计是按 (name, method) 双键存的 |
| 用了 locust 2.32 里不存在的属性 | 屏幕上没有 summary，压测"看起来跑完了" | 事件监听器里的异常被静默吞掉 |

---

## 九、逐行解释：scripts/run_bench.sh

### 9.1 这一段在做什么

把"对 2 个目标 × 4 个并发档各跑一轮 Locust"这件很啰嗦的事收成一条命令，并保证每轮的前置条件一致（清配额、检查服务活着）。

### 9.2 代码逐行

```bash
set -euo pipefail                           # 严格模式：任何一条命令失败就退出（避免带着错误继续跑）
#   -e 出错即退出；-u 用了未定义变量就报错；-o pipefail 管道里任何一段失败整条算失败

TARGET_SCOPE="${1:-all}"                    # 第 1 个参数，默认 all（monolith + gateway 都压）
USERS_LIST="${2:-20}"                       # 第 2 个参数，默认单档 20 并发
RUN_SECONDS="${3:-60}"                      # 第 3 个参数，默认每档 60 秒

cd "$(dirname "$0")/.."                     # 切到脚本所在目录的上一级 = 项目根目录
#   这样不管你从哪个目录调用这个脚本，路径都对

PY="${PY:-./.venv3/Scripts/python.exe}"     # 解释器，允许用环境变量覆盖
#   🔴 绝不能写裸 python：Windows 上会先命中 Anaconda 3.6，读 UTF-8 配置按 GBK 解，直接 UnicodeDecodeError

if [ ! -f "$PY" ]; then                     # 🔴 这一步检查不能省
  echo "[中止] 找不到虚拟环境解释器: $PY"
  exit 1
fi
#   少了它，"解释器路径不存在"这条错误会被后面的管道整个吞掉：
#   屏幕上只看到"目标=monolith 并发=5"然后一行结果都没有、reports 目录空着，
#   人会以为是自己哪里写错了，实际上压测压根没启动

REPORT_DIR="reports/bench_$(date +%Y%m%d_%H%M%S)"   # 按时间戳分目录，避免覆盖上一轮
mkdir -p "$REPORT_DIR"

declare -A HOSTS=(                          # 关联数组：目标名 → 地址
  [monolith]="http://127.0.0.1:9002"        # 单体
  [gateway]="http://127.0.0.1:9100"         # 经 Kong 网关
)
ORDER=(monolith gateway)                    # 固定顺序，压测顺序一致才不会互相干扰

for p in 9002 9121 9122 9123 9124; do       # 前置检查：5 个服务必须先活着
  if ! curl -s -m 3 "http://127.0.0.1:$p/health" > /dev/null; then
    echo "[中止] 端口 $p 不通。按操作手册先把 5 个服务起好再压测。"
    exit 1
  fi
done

docker exec ai_chief_redis redis-cli --scan --pattern "quota:*" 2>/dev/null | while read -r k; do
  [ -n "$k" ] && docker exec ai_chief_redis redis-cli DEL "$k" > /dev/null
done
#   清当天配额：free 套餐 chat_daily 上限 50 次，压测几十秒就打满，
#   之后所有 chat 请求返回 429，报告变成"一堆 429"，看不出真实容量

IFS=',' read -r -a USER_ARRAY <<< "$USERS_LIST"   # 把 "10,20,40,60" 拆成数组

for target in "${ORDER[@]}"; do
  for users in "${USER_ARRAY[@]}"; do
    spawn=$(( users / 3 ))                  # 爬坡速率 = 并发数 ÷ 3
    [ "$spawn" -lt 1 ] && spawn=1           # 至少 1
    #   为什么不是"一秒全上"：一秒全上时头几秒全是冷启动（连接池新建、Milvus/Neo4j 重连），
    #   这些慢请求会把平均值和 P99 整体拉高，测出来的不是"稳态容量"。
    #   留 3 秒爬坡，在 45 秒的一轮里只占 7%，影响可忽略

    "$PY" -m locust -f "$LOCUSTFILE" \
      --headless \                          # 不开网页界面，命令行跑（脚本里必须加）
      --host "$host" \                      # 打哪个地址
      --users "$users" \                    # 多少并发
      --spawn-rate "$spawn" \               # 每秒起几个用户
      --run-time "${RUN_SECONDS}s" \        # 跑多久
      --csv "$csv" \                        # 输出 CSV 前缀
      --csv-full-history \                  # 额外输出时间序列 CSV（找拐点用）
      --only-summary                        # 只打印汇总表，不打每秒的实时刷新
    #   🔴 这里故意不接 `| grep` 过滤：一接管道，locust 自己报的任何错都会被过滤掉，
    #   只剩一行安静的分隔线，排查时完全看不出发生了什么。乱一点但可追溯
  done
done
```

### 9.3 为什么参数是"档位列表"而不是单个并发数

要回答"错误率拐点在哪"，就必须一路加压直到 P99 明显变差或出现失败。一档一档跑，才能把拐点画出来。**只跑一档只能得到"某个并发下还行"，写不进报告**。

---

## 十、逐行解释：scripts/locust_report.py

### 10.1 这一段在做什么

把 8 个 CSV 汇总成三张表 + 一份 Markdown 报告。

### 10.2 代码逐行：解析 CSV

```python
SCENARIOS = (                               # 场景定义：(CSV 里的 Name, HTTP 方法, 中文标签)
    ("/auth/login", "POST", "登录"),
    ("/chat/stream", "POST", "对话"),
    ("/kg/ask", "GET", "图谱问答"),
)
#   只收这三个；名字里带 " [准备]" 后缀的是进场开销，不是被测场景

FAIL_RATE_THRESHOLD = 1.0                   # 劣化判定：错误率超过 1%
P99_THRESHOLD_MS = 1000.0                   # 或者 P99 超过 1000 毫秒


def _to_float(value: str) -> float:         # 安全转 float
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0                          # 空串/脏数据一律当 0，不让报告崩掉


def parse_stats_csv(path: Path) -> dict:
    """解析一个 Locust stats CSV"""
    result = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):      # DictReader 按第一行的列名做键
            name = (row.get("Name") or "").strip()
            if not name or name.endswith("[准备]"):   # 空名字或准备阶段的请求，跳过
                continue
            req = _to_int(row.get("Request Count", "0"))
            fail = _to_int(row.get("Failure Count", "0"))
            result[name] = {
                "requests": req,
                "failures": fail,
                "fail_rate": (fail / req * 100) if req else 0.0,   # 除零保护
                "p99_ms": _to_float(row.get("99%", "0")),          # P99 就在 "99%" 这一列
                "rps": _to_float(row.get("Requests/s", "0")),      # 🔴 直接用它，别自己再算一遍
            }
    return result
```

> 🔴 **`Requests/s` 这一列是聚合口径的每秒请求数**。报告里的 QPS 直接用它，**不要**自己再用"请求数 ÷ 时长"算一遍——两个口径不一样，混用会让数字对不上。

Locust 2.32 真实写出的列名（照抄，别凭记忆改）：

```
Type, Name, Request Count, Failure Count, Median Response Time,
Average Response Time, Min Response Time, Max Response Time,
Average Content Size, Requests/s, Failures/s, 50%, 66%, 75%, 80%,
90%, 95%, 98%, 99%, 99.9%, 99.99%, 100%
```

### 10.3 代码逐行：生成对比表

```python
def build_comparison_table(rounds: list) -> list:
    by_users = {}                           # 按并发数分组
    for r in rounds:
        by_users.setdefault(r["users"], {})[r["target"]] = r

    rows = []
    for users in sorted(by_users):
        pair = by_users[users]
        if "monolith" not in pair or "gateway" not in pair:
            continue                        # 🔴 某一档缺一边就不进表
        #   避免出现"网关有数据、单体是空"的半截对比，那种表放进报告最容易误导人
        mono = pair["monolith"]["stats"]
        gw = pair["gateway"]["stats"]
        for name, _method, label in SCENARIOS:
            if name not in mono or name not in gw:
                continue
            m, g = mono[name], gw[name]
            delta = ((g["p99_ms"] - m["p99_ms"]) / m["p99_ms"] * 100) if m["p99_ms"] else None
            #       相对差 = (网关 - 单体) ÷ 单体 × 100；单体为 0 时留空（不能除零）
            rows.append({...})
    return rows
```

### 10.4 代码逐行：找拐点

```python
def find_knee(knee_rows: list, target: str):
    """找某个目标"开始劣化"的第一档并发；全程不劣化返回 None"""
    rows = [r for r in knee_rows if r["target"] == target]
    rows.sort(key=lambda r: r["users"])     # 按并发从小到大
    for r in rows:
        if r["degraded"]:                   # 错误率 > 1% 或 P99 > 1000ms
            return r["users"]               # 返回第一档劣化的并发数
    return None                             # 全程不劣化 = 还没摸到上限
```

> `None` 本身也是结论：**"压到最高档都还没到拐点"**，说明这台机器上还没摸到真实上限（要继续加压才会爆）。

### 10.5 代码逐行：为什么结论用"中位数"而不是"最大值"

```python
        per_scene = {}                      # 按场景收集各档的 P99 增幅
        for c in comparison:
            if c["delta_p99_pct"] is not None:
                per_scene.setdefault(c["label"], []).append(c["delta_p99_pct"])
        ranked = sorted(
            ((label, _median(vals)) for label, vals in per_scene.items() if _median(vals) is not None),
            key=lambda kv: kv[1], reverse=True,     # 按中位数从大到小排
        )
```

**为什么用中位数？** 某个并发档的 P99 可能被一次 GC、一次冷连接、一次限流重试拉高。取最大值会把这种偶发噪声当成"网关开销最大的场景"写进结论，结论就错了。

**实测里真发生过**：20 并发的 `/kg/ask` 出现过一次 310ms 的偶发尖刺（增幅 +1967%），而 40 并发同样场景只有 21ms。如果取最大值，结论会变成"网关让图谱查询慢了 20 倍"——完全是错的。取各档增幅的中位数（+51% 是对话场景）才代表常态。

### 10.6 代码逐行：渲染 Markdown（一个真实的坑）

```python
def render_markdown(rounds, comparison, knee, report_dir) -> str:
    out = []                                # 用列表收集每一行
    out.append("# AI 私厨 v3.0 · 阶段 10 性能压测报告")   # 🔴 每行都不带结尾换行符
    out.append("")
    out.append("| 目标 | 并发 | 总请求 | ... |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in knee:
        out.append(f"| {r['target']} | {r['users']} | ... |")
    return "\n".join(out) + "\n"            # 🔴 最后统一用 join 拼
```

> 🔴 **每一行都不要带 `\n`，最后统一 `"\n".join(out)`**。两条写法混着用（有的行带 `\n` 有的不带）就会出现"整张表挤成一行"，在渲染器里显示成一条永远滚不完的长表格，完全没法读。**这个 bug 在阶段 10 真的发生过**。

---

## 十一、逐行解释：docker/Dockerfile.svc

### 11.1 这一段在做什么

定义生产镜像：怎么装依赖、拷什么代码、用什么命令起、怎么判断活着。

### 11.2 代码逐行

```dockerfile
FROM docker.m.daocloud.io/library/python:3.13-slim
#   🔴 为什么写 DaoCloud 完整地址而不是官方 `python:3.13-slim`：
#   本机 Docker Desktop 配的 Registry Mirrors（USTC / 163 / 百度）当前全部连不上，
#   写官方地址会直接失败：failed to do request: Head "https://docker.mirrors.ustc.edu.cn/v2/...": EOF
#   DaoCloud 是项目 docker-compose.v3.yml 里一直在用的源，本地已有缓存

WORKDIR /app                                # 后续所有相对路径都基于 /app

ENV PYTHONUTF8=1 \                          # 容器默认 ASCII，中文日志一打印就 UnicodeEncodeError
    PYTHONDONTWRITEBYTECODE=1 \             # 不生成 .pyc，镜像小一点
    PIP_NO_CACHE_DIR=1 \                    # pip 不缓存下载包，镜像小一点
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple   # 国内源，不然拉依赖十几分钟

#   🔴 这里不装 curl（很多教程会 apt-get install curl，那是给自己挖坑）：
#   ① 容器内访问 deb.debian.org 常年 502/DNS 失败，一旦 apt 装不上，整条 build 当场失败；
#   ② slim 镜像自带 Python，用 urllib 做健康检查完全够用

COPY requirements.txt ./requirements.txt            # 🔴 分两行写
COPY docker/requirements.prod.txt ./requirements.prod.txt
#   `COPY a b ./x` 这种"多源到单目标"的写法，目标不是目录时会直接报 must be a directory

RUN pip install --no-cache-dir -r requirements.prod.txt   # 装依赖（含 gunicorn）
#   为什么要先拷依赖清单、再装依赖、最后拷代码：
#   Docker 按层缓存。这样"改代码重新构建"时，装依赖那一层能用缓存，不用每次重装

COPY app_my ./app_my                        # 拷业务代码（顺序不能反：依赖在前、代码在后）
COPY services ./services
COPY main.py ./main.py

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app        # 把 /app 的所有权给 appuser
USER appuser                                # 之后的所有指令都用这个用户跑（非 root）

ENV APP_MODULE=services.user.main:app \     # 默认跑哪个服务（docker run / compose 里覆盖）
    WEB_WORKERS=2 \                         # 默认几个 worker
    WEB_PORT=9121 \                         # 默认监听端口
    WEB_TIMEOUT=120                         # 默认超时（对话是长连接，必须够长）

EXPOSE 9121                                 # 声明端口（只是文档作用，真正映射靠 -p / ports:）

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('WEB_PORT','9121')+'/health',timeout=4).read()" || exit 1
#   每 30 秒探一次自己的 /health，连续 3 次失败才标记 unhealthy
#   用 Python urllib 而不是 curl：slim 镜像里没有 curl（我们没装）
#   urlopen 对连接失败/非 2xx 都会抛异常 → python 非 0 退出 → Docker 判 unhealthy
#   start_period=40s 是启动宽限期：服务启动要连数据库、建连接池，
#   不设的话启动慢一点就被判 unhealthy，compose 会不停重启它

CMD gunicorn "${APP_MODULE}" \
      -k uvicorn.workers.UvicornWorker \    # worker 类：必须是 ASGI 的，否则异步全堵死
      --workers "${WEB_WORKERS}" \          # worker 数量
      --bind "0.0.0.0:${WEB_PORT}" \        # 监听地址（容器内必须 0.0.0.0，不能 127.0.0.1）
      --timeout "${WEB_TIMEOUT}" \          # 单请求超时（对话流式要 120s）
      --graceful-timeout 30 \               # 优雅退出：收到停止信号后给 30 秒处理完手上的请求
      --access-logfile - \                  # 访问日志打到标准输出（docker logs 能看到）
      --error-logfile -                     # 错误日志同上
#   🔴 用 shell 形式（不是 exec 形式的 JSON 数组）写 CMD，
#   因为要展开 ${APP_MODULE} 这些环境变量；JSON 形式不做变量替换
```

### 11.3 生产镜像 vs 本机开发，五处不同

| 项 | 本机开发 | 生产容器 | 为什么 |
|---|---|---|---|
| 服务器 | `uvicorn main:app`（单进程） | `gunicorn` 管多个 worker | 多核利用 + worker 挂了自动拉起 |
| worker 类 | 无（就是 uvicorn） | `UvicornWorker` | 服务是 ASGI（异步），用同步 worker 会把异步堵死，`/chat/stream` 直接卡成串行 |
| 健康检查 | 无 | `HEALTHCHECK` | 没有它，容器"起来了但应用没起来"时 `docker ps` 显示 Up，只有用户报障才发现 |
| 运行用户 | 你的 Windows 用户 | `appuser`（uid 1000） | 镜像被拖库时，root 权限等于把整台机器交出去 |
| 日志 | 终端直接看 | `--access-logfile -` 打到标准输出 | 容器日志要能被 `docker logs` / Loki 采集 |

### 11.4 为什么 gunicorn 不能在本机试

gunicorn 依赖 `fcntl` 和 `os.fork`，**这两个 Windows 都没有**。在 Windows 里 `import gunicorn` 会直接：

```
ModuleNotFoundError: No module named 'fcntl'
```

**这是正常的，不是装错了。** 它只能跑在 Linux 容器里——这也正是"生产镜像"和"本机开发"必须分开的原因。

---

## 十二、逐行解释：docker/docker-compose.prod.yml

### 12.1 这一段在做什么

用容器起 4 个应用服务 + Kong 网关，每个都挂健康检查、资源上限、日志轮转。

### 12.2 代码逐行：锚点复用

```yaml
name: ai_chief_prod                         # 项目名，容器名和网络都基于它

x-svc-common: &svc-common                   # 🔴 定义锚点：以 x- 开头的键 compose 不会当成服务
  build:
    context: ..                             # 构建上下文 = 项目根目录（相对本 compose 文件所在目录）
    dockerfile: docker/Dockerfile.svc
  env_file:
    - ../.env                               # 读项目根目录的 .env（JWT_SECRET、API Key 都在里面）
  restart: unless-stopped                   # 崩了自动拉起；手动 stop 就不起来（不跟人工操作抢）
  extra_hosts:
    - "host.docker.internal:host-gateway"   # 🔴 让容器能访问宿主机
  #   DB / Redis / Neo4j / Milvus 都跑在宿主机端口上（5433 / 6380 / 7687 / 19530）。
  #   没有这一行，容器里的 127.0.0.1 指的是它自己，连数据库一律 Connection refused
  logging:
    driver: json-file
    options:
      max-size: "10m"                       # 单个日志超 10MB 就切新文件
      max-file: "3"                         # 最多留 3 个 → 总共封顶 30MB
  #   不设的话，一个跑几周的容器日志能把系统盘写满
  mem_limit: 768m                           # 内存上限：一个服务内存泄漏时不至于拖死整台机器
  cpus: 1.0                                 # CPU 上限

services:
  svc-user:
    <<: *svc-common                         # 🔴 把锚点的内容合并进来（YAML 合并键语法）
    container_name: ai_chief_prod_user
    environment:
      APP_MODULE: services.user.main:app    # 同一个镜像靠这个变量复用给 4 个服务
      WEB_PORT: "9121"
      WEB_WORKERS: "2"                      # 2 worker：登录是 bcrypt（CPU 密集），多核才有收益
      MOCK_LLM: "false"                     # 🔴 生产绝不能开 mock
```

**为什么用锚点？** 4 个服务的配置 90% 相同。不用锚点就得复制粘贴 4 遍，改一处要改 4 处，迟早漏改。

### 12.3 四个服务的 worker 数为什么不一样

| 服务 | worker 数 | 理由 |
|---|---|---|
| `svc-user` | 2 | 登录是 bcrypt **CPU 密集**，多核才有收益，但也别太多（CPU 就那么多核） |
| `svc-recognizer` | 2 | 主要调 LLM，IO 为主 |
| `svc-recommender` | 3 | 图谱 + 向量检索是 **IO 密集**，多开 worker 能把"等待"的时间重叠掉 |
| `svc-chat` | 3 | 同上，且要跨服务调用前三个，等待更多 |

> 这就是"**CPU 密集 vs IO 密集**"的实际应用：CPU 密集的 worker 数 ≈ CPU 核数；IO 密集的可以多于核数，因为大部分时间在等。

### 12.4 chat 服务的两个关键配置

```yaml
      SPLIT_MODE: "remote"                  # 🔴 生产必须 remote
      #   chat 服务要跨服务调用前三个服务。local 模式会退化成"在自己进程里跑全部节点"，等于白拆
      WEB_TIMEOUT: "120"                    # 对话是流式长连接，gunicorn 默认 30s 超时会把它掐断
```

> 🔴 `SPLIT_MODE` **不在 `config.py` 里**，它是 `app_my/agents/coordinator.py` 用 `os.getenv("SPLIT_MODE", "local")` 直接读的环境变量。默认值是 `local`（单体行为）。压测时给 9124 设 `remote` 才是"拆开"的状态。

### 12.5 Kong 网关部分

```yaml
  kong:
    image: docker.m.daocloud.io/library/kong:3.7
    #   🔴 写国内源完整地址 + 本地已缓存的版本号（3.7）
    #   官方 kong:3.9-ubuntu 在本机会去 Docker Hub 拉，而三个 Registry Mirrors 都连不上，
    #   结果是 compose up 卡在 "pulling kong" 最后失败
    environment:
      KONG_DATABASE: "off"                  # DB-less：配置全在 yaml 里，不额外起 Postgres
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      KONG_PROXY_LISTEN: "0.0.0.0:9100"     # 用户入口
      KONG_ADMIN_LISTEN: "0.0.0.0:9101"     # 管理口（容器内）
    volumes:
      - ./kong/kong.yml:/etc/kong/kong.yml:ro   # ro = 只读挂载，容器改不了配置
    ports:
      - "9100:9100"                         # 网关入口（和开发时同一个端口）
      - "9105:9101"                         # 管理口映射到 9105（避开 9101 已被 worker metrics 占用）
```

> 🔴 **DB-less 模式的关键特性**：Admin API 是**只读**的。改限流只能改 `kong.yml` 然后**重启容器**。操作手册 13.4 里那句 `docker restart ai_chief_kong` 就是因为这个。

---

## 十三、逐行解释：.gitee/workflows/pipeline.yml

### 13.1 这一段在做什么

定义云端流水线：代码 push 到 master/main 就自动跑测试和构建。

### 13.2 代码逐行

```yaml
version: '1.0'                              # Gitee Go 的流水线格式版本

name: ai-chief-ci                           # 唯一标识（英文、无空格）
displayName: 'AI私厨 v3.0 持续集成'          # Gitee 页面上显示的名字

triggers:
  push:
    - matchType: PRECISE                    # PRECISE = 精确匹配分支（不是前缀匹配）
      branch: master
    - matchType: PRECISE
      branch: main
#   只有 push 到这两个分支才触发。开发分支不触发，省 CI 资源

stages:
  - stage:
      name: test-stage
      displayName: '单元测试'
      failFast: false                       # false = 有 step 失败也继续跑完剩下的
      #   方便一次看全所有错误，不用改一个跑一次
      steps:
        - step: build@python                # Gitee Go 提供的 Python 构建环境
          name: run-pytest
          displayName: '安装依赖并跑单测'
          inputs:
            pythonVersion: '3.13'
            goals: |                        # | 表示后面的多行字符串原样保留换行
              set -e                        # 🔴 任何一条命令失败就立刻让这个 step 失败
              #   不加的话 pip 装失败也会继续往下跑，最后 pytest 报一堆莫名错误，很难定位
              python -V
              python -m pip install --upgrade pip
              pip install -r requirements.txt
              python -m pytest tests/unit -q --no-header -p no:cacheprovider
              #   🔴 只跑 tests/unit：integration 下的用例需要后端服务真的起着，
              #   CI 容器里没有后端也没有数据库，跑必然 ConnectionError

  - stage:
      name: build-stage
      displayName: '配置校验与镜像构建'
      failFast: true                        # true = 失败就停（配置都解析不了就没必要继续构建）
      steps:
        - step: build@python
          name: verify-config
          inputs:
            pythonVersion: '3.13'
            goals: |
              set -e
              pip install pyyaml
              python -c "import yaml;yaml.safe_load(open('docker/docker-compose.prod.yml',encoding='utf-8'));print('compose OK')"
              python -m py_compile benchmarks/locustfile.py scripts/locust_report.py
              #   py_compile 只检查语法，不执行代码——在 CI 里做"会不会写错"的快速筛查
              python -c "import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm; print('import OK')"
              #   冒烟：确认核心模块能被导入（少一个依赖包这里就炸）

        - step: build@docker
          name: build-image
          displayName: '构建生产镜像'
          inputs:
            dockerFileName: docker/Dockerfile.svc
            dockerImageName: ai-chief-svc
            dockerImageTag: 'stage10'
```

### 13.3 必须先说清楚的一件事

🔴 **云端 CI 的 YAML 没法在你本机实跑**。它只在 Gitee 服务器上生效，取决于云端怎么解析这份文件、云端环境里装了什么。

所以本阶段额外给了 `scripts/ci_local.sh` / `.ps1`：把流水线里的每条命令在你本机按顺序跑一遍。它能证明的是"**这些命令本身是通的**"，不能保证"云端一定接受这份 YAML 的语法"。

真要确认，只能 push 到 Gitee 看构建记录。

---

## 十四、逐行解释：scripts/ci_local.sh

### 14.1 这一段在做什么

把流水线的命令在本机跑一遍，让"CI 挂了才发现"变成"提交前就知道"。

### 14.2 代码逐行

```bash
set -euo pipefail                           # 严格模式

cd "$(dirname "$0")/.."                     # 切到项目根目录

PY="${PY:-./.venv3/Scripts/python.exe}"     # 解释器，允许覆盖
if [ ! -f "$PY" ]; then
  echo "[中止] 找不到虚拟环境解释器: $PY"
  exit 1
fi

FAILED=0                                    # 失败计数
run_step() {                                # 小工具函数：跑一条命令，记录成败
  local title="$1"; shift                   # 第 1 个参数是标题，剩下的是要执行的命令
  echo ""
  echo "--------------------------------------------------------------"
  echo " 步骤: $title"
  echo "--------------------------------------------------------------"
  if "$@"; then                             # 执行剩下的参数（就是那条命令）
    echo "[PASS] $title"
  else
    echo "[FAIL] $title"
    FAILED=$((FAILED + 1))                  # 计数 +1，但不退出
  fi
  #   为什么不失败就退出：想一次跑完全部步骤，最后看完整的 FAIL 清单
}

run_step "Python 版本（CI 用的是 3.13）" "$PY" -V

run_step "检查关键依赖是否已安装" "$PY" -c "
import importlib.util, sys
need = ['fastapi', 'uvicorn', 'sqlalchemy', 'redis', 'pytest', 'httpx', 'yaml', 'pydantic_settings']
missing = [m for m in need if importlib.util.find_spec(m) is None]
#          find_spec 只检查"能不能找到"，不真的 import —— 快，且不会触发副作用
if missing:
    print('缺失依赖:', missing)
    sys.exit(1)                             # 非 0 退出 → run_step 记 FAIL
print('关键依赖齐全:', len(need), '个')
"
#   🔴 和流水线的区别：流水线里是 `pip install -r requirements.txt`（每次全新环境都要装）
#   这里改成"检查关键依赖在不在" —— 本机早就装好了，没必要每次跑都重装一遍
#   （本项目依赖装一次要 5~6 分钟）

run_step "跑单元测试（tests/unit）" "$PY" -m pytest tests/unit -q --no-header -p no:cacheprovider

run_step "校验生产编排" "$PY" -c "
import yaml
d = yaml.safe_load(open('docker/docker-compose.prod.yml', encoding='utf-8'))
assert 'services' in d, 'compose 文件里没有 services'
print('生产编排解析通过，共', len(d['services']), '个服务:', list(d['services']))
"

run_step "校验压测脚本语法" "$PY" -m py_compile benchmarks/locustfile.py scripts/locust_report.py

run_step "冒烟：核心模块能被导入" "$PY" -c "
import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm
print('核心模块 import OK（含阶段10新增的 mock_llm）')
"

exit "$FAILED"                              # 退出码 = 失败数。0 = 全过，可直接用于 CI 判断
```

---

## 十五、逐行解释：scripts/verify_stage10.py

### 15.1 这一段在做什么

回答"阶段 10 到底做完没有"。它和 pytest 的分工：

- **pytest** —— 测"代码逻辑对不对"（141 个用例）
- **本脚本** —— 测"该有的东西在不在、能不能跑起来"（文件、配置、容器、端口、报告）

两者都绿，才算收官。

### 15.2 代码逐行

```python
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#   __file__ = .../scripts/verify_stage10.py → dirname 一次 = scripts/ → dirname 两次 = 项目根
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
#   🔴 为什么需要这三行：直接 `python scripts\verify_stage10.py` 时，
#   Python 只把 scripts\ 当作模块搜索路径，于是 `import app_my...` 会报
#   ModuleNotFoundError: No module named 'app_my'

PASS, FAIL = "OK  ", "FAIL"
_results: list = []                         # 收集所有结果，最后统一统计

def check(label: str, ok: bool, detail: str = "") -> bool:
    """记录一条检查结果并打印"""
    _results.append((PASS if ok else FAIL, label, detail))
    print("  %s %-46s %s" % (PASS if ok else FAIL, label, detail))
    #   %-46s = 左对齐占 46 个字符宽，让输出对齐成表格
    return ok


def check_files() -> None:
    """① 交付文件是否都在"""
    expected = {
        "app_my/core/mock_llm.py": "对话模型打桩器",
        ...
    }
    for rel, desc in expected.items():
        p = Path(_ROOT) / rel
        ok = p.is_file() and p.stat().st_size > 0    # 🔴 不只看存在，还看不是空文件
        check(rel, ok, f"{desc}" + ("" if ok else "（缺失或为空）"))


def check_mock_wiring() -> None:
    """② 打桩是否真的接上了 —— 不能只看文件在不在"""
    from app_my.core.config import settings
    check("MOCK_LLM 默认是关闭的", settings.MOCK_LLM is False, ...)
    #   默认必须是关的，否则正常开发全是假数据

    from app_my.core import model_router
    src = Path(model_router.__file__).read_text(encoding="utf-8")
    check("ainvoke_routed 里有 MOCK_LLM 分支", "MOCK_LLM" in src, ...)
    #   为什么用"读源码找字符串"而不是 import 后检查：
    #   打桩分支在函数体里，没法从外部观测。读源码是最直接的证据

    from app_my.knowledge.embedding import MOCK_DIMENSION
    from app_my.knowledge.milvus_store import DIMENSION
    check("打桩向量维度与 Milvus 集合一致", MOCK_DIMENSION == DIMENSION, ...)
    #   这两个常量必须相等，否则检索报维度不匹配

    import asyncio
    from app_my.core.mock_llm import ainvoke_mock
    from app_my.agents.recognizer import parse_json_payload
    data = parse_json_payload(asyncio.run(ainvoke_mock("extract", [])).content)
    n = len(data.get("ingredients") or [])
    check("extract 打桩能被识别节点解析", n >= 1, f"解析出 {n} 种食材")
    #   🔴 这是最关键的一条：打桩输出必须能被下游真的解析。
    #   解析出 0 种食材 → 后面推荐/营养节点全部空转 → 测出来的 QPS 是"什么都没干"的 QPS


def check_services() -> None:
    """③ 五个服务是否都健康"""
    for port, name in ((9002, "单体"), (9121, "user"), (9122, "recognizer"),
                       (9123, "recommender"), (9124, "chat")):
        r = requests.get(f"http://127.0.0.1:{port}/health", timeout=3)
        ok = r.status_code == 200


def check_prod_compose() -> None:
    """④ 生产编排能否被 Docker 解析"""
    proc = subprocess.run(["docker", "compose", "-f", str(compose), "config"],
                          capture_output=True, text=True, timeout=60, ...)
    check("docker compose config 通过", proc.returncode == 0, ...)
    #   🔴 为什么还要调 docker 命令：YAML 合法 ≠ compose 合法。
    #   PyYAML 只能证明语法对，证明不了 `build.context` 路径对、字段名拼对


def check_bench(bench_dir: str) -> None:
    """⑤ 压测产物与报告"""
    mono = {f.name.split("_u")[1].split("_")[0] for f in stats_files if f.name.startswith("monolith")}
    #   从文件名里反解出并发档位：monolith_u20_stats.csv → "20"
    report = d / "压测报告.md"
    text = report.read_text(encoding="utf-8")
    check("报告表格分行正常", any(line.startswith("| 目标 |") for line in text.splitlines()), ...)
    #   🔴 专门防"表格挤成一行"那个 bug。如果 table 挤成一行，startswith 就匹配不到
```

---

## 十六、PowerShell 版脚本的翻译要点

`run_bench.ps1` 和 `ci_local.ps1` 是 `.sh` 版本的逐行翻译。这里只讲**翻译时改了什么、为什么改**，因为这正是 PowerShell 5.1 最容易出错的地方。

### 16.1 `nohup cmd &` → `Start-Process`

```powershell
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--port","9002" `
    -NoNewWindow -RedirectStandardOutput "logs\bench_9002.log" -RedirectStandardError "logs\bench_9002.err.log"
```

- `-ArgumentList` 用**逗号分隔**的参数数组，不能像 bash 那样靠反斜杠续行（反斜杠续行是 PS 6+ 才有的）；
- `-NoNewWindow` = 不开新窗口（不加会弹出黑框）；
- `-RedirectStandardOutput` / `-RedirectStandardError` = 重定向输出到文件（PS 5.1 的 `*` 重定向操作符是 PS 6+ 才有的）。

### 16.2 `grep` → `Select-String`

```powershell
Select-String -Path docker\kong\kong.yml -Pattern "minute:" | ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
```

`$_` 是当前管道对象，`$_.LineNumber` 是行号，`$_.Line` 是那一行内容。

### 16.3 多行 Python 用 here-string

```powershell
& $PY -c @"
import importlib.util, sys
need = ['fastapi','uvicorn']
print('ok')
"@
```

🔴 **结尾的 `"@` 必须顶格**（行首不能有空格），否则 PowerShell 会一直等输入、卡住不返回。

### 16.4 判断外部命令的退出码用 `$LASTEXITCODE`

```powershell
& $PY -m pytest tests/unit -q
if ($LASTEXITCODE -ne 0) { ... }
```

🔴 **不能用 `$?`** —— `$?` 判断的是 PowerShell 自己语句的成功与否，对外部程序不可靠。

### 16.5 环境变量必须手动清理

```powershell
$env:MOCK_LLM = "true"
# ... 启动进程 ...
Remove-Item Env:MOCK_LLM       # 🔴 不清理的话，后面在这个窗口起的任何进程都会继承
```

bash 里 `VAR=x cmd` 只影响那一条命令；PowerShell 里 `$env:VAR="x"` 会**一直留在窗口里**。

### 16.6 `&&` 不存在

```powershell
# bash:  cmd1 && cmd2
# PS5.1:
cmd1; if ($?) { cmd2 }
```

### 16.7 完整的替换速查表

见《操作手册》附录 C。

---

## 十七、面试追问预案

按"最可能被问到"排序。每个问题给一句标准答案 + 追问怎么接。

### Q1："你这个压测的 QPS 是谁的 QPS？"

**标准答案**：我自己的架构的。我用 `MOCK_LLM` 开关把大模型调用换成了固定耗时（50ms）的假模型，所以响应时间里不含厂商的网络往返和排队。否则同一套代码连跑两次，数字能差一倍。

**追问**："那 50ms 是怎么定的？"
→ 真实快模型（qwen3.7-flash 关思考）2 秒内出报告，我取 50ms 是**有意压低**，好让架构自身的开销占主导。如果设 0，会量出一个漂亮但不真实的 QPS，上线后第一波流量就被真实耗时打脸。

### Q2："P99 为什么比平均值重要？"

**标准答案**：平均值会被大量快请求稀释。P99 是"最倒霉的 1% 用户等多久"，它才反映真实体验。我的报告里单体在 60 并发时平均值只有 231ms，但 P99 是 3900ms——**只看平均值会完全看不出已经崩了**。

### Q3："拐点是怎么判定的？"

**标准答案**：脚本自动判定，口径是"错误率 > 1% **或** P99 > 1000ms"，两个条件满足任一即算这一档开始劣化。我跑了 10/20/40/60 四个档，单体在 60 并发触发，微服务最高档仍未触发。

**追问**："微服务没到拐点说明什么？"
→ 说明这台机器上还没摸到它的真实上限，要继续加压（80/120 并发）才会爆。这本身也是结论：**微服务的容量上限至少比单体高一个档位**。

### Q4："拆分的收益具体是多少？"

**标准答案**：60 并发下登录场景 P99 从 3000ms 降到 560ms，**降低 81%**（约 5.8 倍）。定位到瓶颈是单进程内 bcrypt 密码哈希的 CPU 争抢，拆分后被分摊到多个进程。

**追问**："代价呢？"
→ 对话场景网关开销中位数 +51%（多一跳网络）。50% 的额外开销换 60 并发下不崩，值不值要按业务量判断。**我会把代价也说出来**——只讲收益不讲代价的方案不可信。

### Q5："你这个 +1967% 是怎么回事？"（针对 20 并发图谱那一行）

**标准答案**：那是单轮偶发尖刺（冷连接/GC），不是常态。所以我用**各档增幅的中位数**下结论，中位数是 +51%。压测报告必须做这一步，否则结论会被一次 GC 带偏。

> 这题是加分题。能主动说明"我剔除了噪声"比只报数字强得多。

### Q6："为什么打桩点选在 model_router 而不是模型工厂？"

**标准答案**：因为档位（lite/standard）不等于任务（extract/report/vision）。同一个 lite 档，"抽食材"要返回 JSON、"生成报告"要返回自然语言——从 tier 推不出该给什么格式。而 `ainvoke_routed` 是全项目唯一还在调 LLM 的地方，在这里加早返回分支，一行业务代码都不用改。

### Q7："向量打桩为什么用 md5 而不是内置 hash()？"

**标准答案**：Python 默认开启哈希随机化（`PYTHONHASHSEED`），同一个字符串在不同进程里 `hash()` 结果不一样。用它会导致每次重启服务，同一个查询的检索结果都在变，压测报告的"命中率"就没有可比性了。所以用 `hashlib.md5` 做种子。

**追问**："为什么还要 L2 归一化？"
→ Milvus 集合用 COSINE 度量。归一化成单位向量后点积就等于余弦值，分数落在 [-1, 1]，和真实 embedding 的分布一致，报告里的分数才读得懂。

### Q8："gunicorn 为什么不能在 Windows 上跑？"

**标准答案**：它依赖 `fcntl` 和 `os.fork`，这两个 Windows 没有。所以它只能跑在 Linux 容器里——这也正是"生产镜像"和"本机开发"必须分开的原因。我在本机只装它（打进镜像用），从不启动它。

### Q9："为什么 worker 数每个服务不一样？"

**标准答案**：因为负载类型不同。`svc-user` 的登录是 bcrypt **CPU 密集**，worker 数 ≈ CPU 核数（2）；`svc-recommender` 的图谱+向量检索是 **IO 密集**，大部分时间在等，可以开多一些（3）把等待时间重叠掉。一刀切设成同一个数是常见的错误做法。

### Q10："CI 流水线你验证过吗？"

**标准答案**：云端 YAML 没法在本机实跑，所以我写了 `ci_local.sh`，把流水线里的每条命令在本机按顺序跑一遍。它能证明"这些命令本身是通的"，不能保证"云端一定接受这份 YAML 的语法"——真要确认只能 push 看构建记录。**我不会说"我验证过 CI"**，那是不诚实的。

### Q11："容器为什么用非 root？"

**标准答案**：镜像被攻破时，root 权限等于把整台机器交出去。用 uid 1000 的 `appuser` 跑，能把损失限制在这个用户能碰到的范围内。我在验收里专门加了一条 `docker exec ... id` 来确认它生效——**配置写了不代表生效**，要验证。

### Q12："健康检查为什么用 Python 不用 curl？"

**标准答案**：因为镜像里没装 curl。很多教程会写 `apt-get install curl`，但容器内访问 `deb.debian.org` 常年 502/DNS 失败，一旦装不上整条 `docker build` 当场失败。slim 镜像自带 Python，用 `urllib.request.urlopen` 做一次 HTTP GET 完全够用，多装一个二进制换一份网络依赖不划算。

---

**说明手册结束。** 配合《操作手册》（照着做）和《理解手册》（大白话 + 图解）一起看。
