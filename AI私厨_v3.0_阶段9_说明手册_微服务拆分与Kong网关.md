# AI 私厨 v3.0 · 阶段 9 说明手册

> **本手册不重复操作手册的"照着做"内容**——命令、步骤、验证都在操作手册里。
> 本手册回答的是"**为什么这么写 / 这段是干什么的 / 参数是什么意思**"。
>
> 章节顺序**严格镜像**操作手册（§1→§25），每节末尾附"代码读懂 → 操作命令"的对应小表。
> 阅读时建议与操作手册**左右对照**。

---

## 📑 目录（可点击锚点）

- [0. 全局地图：阶段 9 的代码长什么样](#0-全局地图阶段-9-的代码长什么样)
- [1. 顺序对照表（镜像操作手册）](#1-顺序对照表镜像操作手册)
- [术语表（按出现顺序，至少 16 项）](#术语表按出现顺序至少-16-项)
- [2. 第 3 章 共享内核的整体设计](#2-第-3-章-共享内核的整体设计)
- [3. services/common/breaker.py 逐行解释](#3-servicescommonbreakerpy-逐行解释)
- [4. services/common/client.py 逐行解释](#4-servicescommonclientpy-逐行解释)
- [5. services/common/context.py 逐行解释](#5-servicescommoncontextpy-逐行解释)
- [6. services/common/app_factory.py 逐行解释](#6-servicescommonappfactorypy-逐行解释)
- [7. 第 4 章 四个服务的入口 main.py](#7-第-4-章-四个服务的入口-mainpy)
- [8. 第 5 章 coordinator 的本地 / 远程切换](#8-第-5-章-coordinator-的本地--远程切换)
- [9. 第 6 章 22 个单元测试的设计思路](#9-第-6-章-22-个单元测试的设计思路)
- [10. 第 7 章 Kong 声明式配置 kong.yml](#10-第-7-章-kong-声明式配置-kongyml)
- [11. 第 8 章 docker-compose 加 Kong service](#11-第-8-章-docker-compose-加-kong-service)
- [12. 第 9 章 起服务 + 中间件顺序](#12-第-9-章-起服务--中间件顺序)
- [13. 第 14-16 章 故障隔离与熔断原理](#13-第-14-16-章-故障隔离与熔断原理)
- [14. 第 17-18 章 Prometheus 抓取 + 对比基线](#14-第-17-18-章-prometheus-抓取--对比基线)
- [15. 第 21 章 PR 描述的写作思路](#15-第-21-章-pr-描述的写作思路)

---

## 0. 全局地图：阶段 9 的代码长什么样

阶段 9 引入的变更：**新增 `services/` 四服务 + 共享内核**，**只修改一个老文件** `app_my/agents/coordinator.py`（加节点表参数），**新增 Kong 配置 + compose 一段 + 3 个测试文件 + 1 个探测脚本**。

```
ai_chief/
├── app_my/                             ← 老单体代码原样当"共享内核"（一行不改，除了下面这一个文件）
│   ├── agents/
│   │   └── coordinator.py              ← ✏️ 唯一被修改的老文件：build_workflow(nodes=None) 支持换节点表
│   ├── api/                            ← 路由模块被四个服务分别"借走"挂载
│   └── middleware/ core/ db/ ws/       ← 中间件/配置/DB/WS 全部复用
├── services/                           ← 🆕 本阶段新增
│   ├── common/                         ← 共享内核（四个服务都从这里装配）
│   │   ├── breaker.py                  ← 熔断器（closed/open/half_open 状态机）
│   │   ├── client.py                   ← ServiceClient：httpx + 重试 + 熔断 + 头透传
│   │   ├── context.py                  ← contextvars 存上游 JWT（跨服务透传用）
│   │   └── app_factory.py              ← 服务工厂：中间件栈 + /health + 路由装配
│   ├── user/main.py                    ← 9121：auth/users/tenants/admin/billing/cache
│   ├── recognizer/main.py              ← 9122：/internal/nodes/{recognize,nutrition} + /oss
│   ├── recommender/main.py             ← 9123：/internal/nodes/{recommend,rank} + /kg
│   └── chat/
│       ├── main.py                     ← 9124：/chat /tasks /ws（唯一开 quota+capture_auth 的服务）
│       └── graph_remote.py             ← 🆕 远程节点表：SPLIT_MODE=remote 时识别/营养/推荐/重排走 HTTP
├── docker/
│   ├── kong/kong.yml                   ← 🆕 Kong 声明式配置（DB-less）
│   └── docker-compose.v3.yml           ← ✏️ 只加 kong 一段
├── scripts/ws_probe.py                 ← 🆕 WebSocket 穿透网关探测
└── tests/unit/
    ├── test_circuit_breaker.py         ← 🆕 8 用例
    ├── test_service_client.py          ← 🆕 7 用例（MockTransport 离线）
    └── test_service_apps.py            ← 🆕 7 用例（装配 + 中间件顺序钉死）
```

> ⚠️ 勘误（2026-10-19）：不存在 `app_my/agents/coordinator_local.py`、`app_my/agents/graph_remote.py`；
> 远程节点表在 **`services/chat/graph_remote.py`**。项目里也没有 `app_my/api/memory.py`。

### 服务职责一句话

| 服务 | 端口 | 业务 | 对外最频繁的调用 |
| --- | --- | --- | --- |
| user | 9121 | 认证 / 用户 / 租户 / 计费 / 配额 / 管理端 / KG 写 / OSS | `/auth/login`, `/users/me`, `/billing/*` |
| recognizer | 9122 | 食材识别 + 营养计算 | chat → `POST /internal/nodes/recognize` |
| recommender | 9123 | 推荐 + 重排 + KG 读 | chat → `POST /internal/nodes/recommend` |
| chat | 9124 | 对话编排 + WS + 对话历史 | 浏览器 → `POST /chat/stream`, WS `/ws/notifications` |
| Kong | 9100 / 9105 | 路由 + CORS + 限流 + trace 透传 | 浏览器 → 上述任一 |

> **用户视角的入口永远是 `9100`**。`9121-9124` 是内部端口，仅运维和单元测试用。

---

## 1. 顺序对照表（镜像操作手册）

> 这一表是 §1-§25 的章节顺序。每一行告诉你"操作步骤做了什么"、"代码为什么要这么写"。

| 操作手册节 | 对应说明章 | 代码视角 | 一句话 |
| --- | --- | --- | --- |
| §0 30 秒核对 | §术语表 | — | 为什么这些前置项是必须的 |
| §1 拉分支 | — | — | 暂不涉及代码 |
| §2 建目录 | — | — | 暂不涉及代码 |
| §3 写共享内核 | §3-6 | services/common/* | 4 个文件的逐行解释 |
| §4 写 4 个 main.py | §7 | services/{user,recognizer,recommender,chat}/main.py | 路由装配的边界 |
| §5 改 coordinator | §8 | coordinator.py / services/chat/graph_remote.py | 怎么"按变量切两套图" |
| §6 写 22 测试 | §9 | tests/unit/test_*.py | 怎么"无外部真服务"也能全跑 |
| §7 写 kong.yml | §10 | docker/kong/kong.yml | 5 条 route 怎么对应 4 服务（/admin 含在 r-user，无独立 r-admin） |
| §8 docker-compose 加 Kong | §11 | docker/docker-compose.v3.yml | host.docker.internal 是什么 |
| §9 起服务 | §12 | 中间件顺序 | add_middleware 为什么是这样 |
| §10 /metrics 验证 | §12 | MetricsMiddleware | 为什么必须在 Auth 外 |
| §11 端到端业务流 | §术语表 | - | token / user_id 流过哪些环节 |
| §12 限流 / trace 头 | §10 | kong.yml plugins 段 | 哪些 header 是谁加的 |
| §13 WS 穿透 | §10 | r-chat-ws route | WS 在 Kong 怎么路由 |
| §14-16 故障 / 熔断 | §13 | breaker.py + client.py | 状态机怎么转的 |
| §17 Prometheus | §14 | prometheus.yml | scrape interval 与 relabel |
| §18 对比基线 | §14 | - | 怎么写出有说服力的数字 |
| §19 拷回项目 | — | - | 落盘清单 |
| §20 回归 | §9 | - | 怎么解读测试结果 |
| §21 提交 PR | §15 | - | PR 描述怎么写 |
| §22 错误对照 | §术语表 | - | 现象 → 真因 |
| §23 避坑 | — | - | 经验沉淀 |
| §24 自检 | — | - | 双终端双跑 |
| §25 PS 速查 | — | - | PowerShell 5.1 等价 |

---

## 术语表（按出现顺序，至少 16 项）

| 术语 | 一句话解释 |
| --- | --- |
| **微服务（Microservice）** | 一个应用按业务边界拆成的若干独立进程。每个服务有自己的部署、扩容、失败模式。 |
| **FastAPI** | Python 的一个 web 框架，基于 Starlette + Pydantic。本工程当前所有 HTTP 层都用它。 |
| **uvicorn** | ASGI 服务器，是真正跑 FastAPI 应用的进程。开发期 `uvicorn main:app` 启动的就是它。 |
| **DB-less 模式（Kong）** | Kong 没有数据库，所有配置写在一个 YAML 文件里；容器启动就立刻生效，不用 migrations。 |
| **CORS** | 浏览器安全规则：JS 默认不能读跨域响应。Kong 装的 cors 插件负责回复一个 `Access-Control-Allow-Origin` 头给浏览器。 |
| **Correlation ID / Trace ID** | 一次请求在多个服务之间穿行的全局唯一 ID（一般是 UUID）；出问题时报这串 ID 就能串起整条链路日志。 |
| **限流（Rate Limiting）** | 防止某一个客户端疯狂打接口。后端可以做，但 Kong 在网关层做更省资源。 |
| **JWT（JSON Web Token）** | 用户登录后拿到的一个字符串，里面有 `user_id` 等信息。后端验证它就知道"是谁"。 |
| **熔断器（Circuit Breaker）** | 一种故障隔离模式：当下游连续失败时，先在本进程内直接返回失败，省下重试延迟；过一会再放一次试探。 |
| **半开探测（half-open）** | 熔断器开一段时间后，让下一次请求打过去看看；如果通就合闸，不通就保持开。 |
| **指数退避（Exponential Backoff）** | 重试的间隔每次翻倍：0.2s → 0.4s → 0.8s。这样能避免下游刚恢复就被"重试风暴"打死。 |
| **HL（High-Level）/ LL（Low-Level）** | 中文文档里有时出现的别名——HL = "高层业务"、LL = "底层基础设施"，本工程对应 mock 数据层。 |
| **httpx** | Python 的一个 HTTP 客户端（同步 + 异步都支持）；和 requests 长得像，但能用在 async 函数里。 |
| **LangGraph / StateGraph** | LangChain 团队的状态机框架；本工程用 `app_my/agents/coordinator.py` 里的 `StateGraph(ChefState)` 描述识别→营养→推荐→重排→输出。 |
| **Pydantic 模型** | 用类语法定义"字段名+类型"，自动校验 JSON body。本工程 `BaseModel` 子类。 |
| **ASGI / ASGI 中间件** | ASGI 是 Python 异步 web 标准；中间件是一个能"在请求被路由前/后做点什么"的函数链。Starlette / FastAPI 都按这条链处理。 |
| **Bind Mount** | Docker 把宿主机的某个文件**直接**挂进容器，而不是拷一份；改宿主机文件容器立刻看到。配置 / 日志常用。 |
| **host.docker.internal** | Docker Desktop 提供的一个特殊主机名，等价于"宿主机的内网 IP"。Linux 主机需要加 `--add-host=host.docker.internal:host-gateway`。 |
| **OpenAPI** | FastAPI 自动生成的一个 API 描述文件（JSON/YAML）。可视化工具（Swagger UI / Kong / 客户端 SDK）都读它。 |
| **Prometheus / Scrape / Target** | 一个开源监控系统。"Scrape" 是它定期去目标 URL `GET /metrics` 拉指标的动作；目标就是"被拉的那个服务"。 |
| **NDJSON（Newline-Delimited JSON）** | 流式响应的最简格式：每行一个合法的 JSON 对象。本工程 `/chat/stream` 用这种。 |

---

## 2. 第 3 章 共享内核的整体设计

`services/common/` 4 个文件分别完成"四件底层辅助"：

| 文件 | 职责 | 对应设计模式 |
| --- | --- | --- |
| `breaker.py` | 单服务维度的状态机 | 熔断器模式 |
| `client.py` | 跨服务 HTTP 客户端（含熔断调用） | 客户端门面 |
| `context.py` | 当前请求上下文（trace_id） | ThreadLocal / ContextVars |
| `app_factory.py` | 装配一个完整的 FastAPI 实例 | 工厂模式 |

**为什么是"共享内核"？** 4 个服务都重复用到 `CircuitBreaker` 和 `ServiceClient`，抽到 `common/` 是 DRY；服务之间**没有**业务耦合，只是底层工具代码共享，符合"微服务 + 共享内核"标准模式。

### 数据旅程（一段对话从用户到回复）

```
1. 浏览器 → Kong(9100) /chat/stream   携带 JWT、message
2. Kong → chat(9124) /chat/stream     Kong 不鉴权（AuthMiddleware 做）
3. AuthMiddleware 验证 JWT、写入 request.state.user_id
4. QuotaMiddleware 按 user_id 限流 / 扣 quota
5. TenantMiddleware 解析 tenant_id 写入 request.state
6. CaptureAuthMiddleware 把 Authorization 头存 scope.state 以备下游用
7. /chat/stream 调用 chat_coordinator
8. coordinator（remote 模式）→ get_coordinator_agent()
9. 内部图按顺序调用：
   - recognize_node  → ServiceClient("recognizer").post(...)
                     → recognizer(9122) /internal/nodes/recognize
                     → 返回识别到的食材
   - recommend_node  → ServiceClient("recommender").post(...)
                     → recommender(9123) /internal/nodes/recommend
   - rank_node       → ServiceClient("recommender").post(...)
                     → /internal/nodes/rank
10. 每个内部 HTTP 调用都被 breaker 守护；失败重试 + 熔断
11. chat 把所有结果合流 → 返回给 Kong → 转发给浏览器
12. Prometheus 定时 GET /chat:9124/metrics 抓指标（每服务一个 job）
```

---

## 3. `services/common/breaker.py` 逐行解释

> 🔴 勘误（2026-10-19）：以实测版为准。核心类 `CircuitBreaker`（`threading.Lock` 保护的状态机）+ 全局注册表（`get_breaker` 按名取单例、`all_snapshots` 给 /health 用）。注意：跨服务调用异常叫 `CircuitOpenError`（熔断器抛）；`ServiceCallError` 在 `client.py` 里（调用失败抛），**不要混**。

#### 文件全文（行尾即注释）

```python
# services/common/breaker.py
"""
熔断器（Circuit Breaker）—— 微服务里"防止一个服务挂掉拖垮调用方"的保护开关

生活化比喻：就像家里的电闸。
    正常（CLOSED）   ：电流正常通过，请求照发。
    跳闸（OPEN）     ：连续烧坏几个电器后，电闸自动跳掉，直接拒绝请求，不再往故障服务上砸。
    试探（HALF_OPEN）：等了一会儿，放一个请求过去试试，通了就合闸，不通继续跳着。

为什么必须有它：
    微服务里 A 调 B，B 挂了 → A 的每次请求都要等超时（比如 5 秒）才失败 →
    用户请求全堵在 A 上 → A 的连接池耗尽 → A 也挂 → 一路传染（雪崩）。
    熔断器的作用是"快速失败"：B 已经确定不行了，A 立刻返回降级结果，不再等。

三个可调参数：
    failure_threshold  连续失败几次才跳闸（默认 3）
    recovery_timeout   跳闸后等多久才允许试探（默认 30 秒）
    half_open_max_calls 试探期最多放几个请求过去（默认 1）
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Dict


class BreakerState(str, Enum):
    """熔断器的三种状态。用 str 继承是为了能直接进 JSON/日志。"""
    CLOSED = "closed"        # 正常放行
    OPEN = "open"            # 跳闸，直接拒绝
    HALF_OPEN = "half_open"  # 试探期，放少量请求


class CircuitOpenError(RuntimeError):
    """熔断器处于 OPEN 时抛出的异常，调用方要 catch 它并走降级逻辑。"""


class CircuitBreaker:
    """
    一个"按服务名"独立的熔断器实例。

    线程安全：用 threading.Lock 保护状态读写。
    （uvicorn 单进程里也可能有多线程跑同步代码，加锁最稳妥）
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = BreakerState.CLOSED
        self._failures = 0           # 连续失败计数（成功一次就清零）
        self._opened_at = 0.0        # 跳闸时刻（time.time() 的时间戳）
        self._half_open_calls = 0    # 试探期已经放过去几个请求
        self._last_error = ""        # 最近一次失败原因，便于排错

    # ------------------------------------------------------------------ 状态查询
    @property
    def state(self) -> BreakerState:
        """当前状态。注意：OPEN 状态下如果已经过了恢复时间，会自动降级成 HALF_OPEN。"""
        with self._lock:
            return self._current_state_unlocked()

    def _current_state_unlocked(self) -> BreakerState:
        """内部方法：调用前必须已持有锁。OPEN 超时自动转 HALF_OPEN。"""
        if self._state == BreakerState.OPEN:
            if time.time() - self._opened_at >= self.recovery_timeout:
                self._state = BreakerState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    # ------------------------------------------------------------------ 调用前闸门
    def before_call(self) -> None:
        """
        发请求之前调用。如果处于 OPEN（还没到试探时间），直接抛 CircuitOpenError。

        这一抛很关键：它让调用方"立刻失败"，而不是陪着故障服务耗掉整个超时时间。
        """
        with self._lock:
            state = self._current_state_unlocked()
            if state == BreakerState.OPEN:
                raise CircuitOpenError(
                    f"[{self.name}] 熔断器已跳闸，剩余恢复时间 "
                    f"{max(0.0, self.recovery_timeout - (time.time() - self._opened_at)):.1f}s"
                )
            if state == BreakerState.HALF_OPEN:
                # 试探期有名额限制：超过名额的请求继续拒绝，避免刚有点希望就被打垮
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitOpenError(f"[{self.name}] 试探名额已用完，稍后再试")
                self._half_open_calls += 1

    # ------------------------------------------------------------------ 结果回写
    def record_success(self) -> None:
        """调用成功：连续失败计数清零；如果是试探期，说明服务恢复了，直接合闸。"""
        with self._lock:
            self._failures = 0
            self._last_error = ""
            self._half_open_calls = 0
            self._state = BreakerState.CLOSED

    def record_failure(self, reason: str = "") -> None:
        """调用失败：连续失败计数 +1；达到阈值就跳闸。"""
        with self._lock:
            self._failures += 1
            self._last_error = reason
            if self._state == BreakerState.HALF_OPEN:
                # 试探失败 → 立刻重新跳闸，并把恢复计时器重置（再等一轮）
                self._trip_unlocked()
            elif self._failures >= self.failure_threshold:
                self._trip_unlocked()

    def _trip_unlocked(self) -> None:
        """内部方法：置为 OPEN 并记录跳闸时刻。"""
        self._state = BreakerState.OPEN
        self._opened_at = time.time()
        self._half_open_calls = 0

    # ------------------------------------------------------------------ 观测 / 测试辅助
    def snapshot(self) -> Dict[str, object]:
        """把内部状态导出成字典，给 /health 和指标用。"""
        with self._lock:
            state = self._current_state_unlocked()
            return {
                "name": self.name,
                "state": state.value,
                "failures": self._failures,
                "threshold": self.failure_threshold,
                "last_error": self._last_error,
                "recover_in": (
                    round(max(0.0, self.recovery_timeout - (time.time() - self._opened_at)), 1)
                    if state == BreakerState.OPEN else 0.0
                ),
            }

    def reset(self) -> None:
        """恢复到出厂状态。单测里每个用例跑之前都要调一次，避免用例互相污染。"""
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failures = 0
            self._opened_at = 0.0
            self._half_open_calls = 0
            self._last_error = ""


# 全局注册表：所有熔断器按"服务名"登记在这里，方便 /health 一次性列出全部状态
_REGISTRY: Dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = threading.Lock()


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    """取（必要时创建）某个服务的熔断器。同名只会有一个实例。"""
    with _REGISTRY_LOCK:
        if name not in _REGISTRY:
            _REGISTRY[name] = CircuitBreaker(name, **kwargs)
        return _REGISTRY[name]


def all_snapshots() -> Dict[str, Dict[str, object]]:
    """导出全部熔断器的状态快照，供 /health 展示。"""
    with _REGISTRY_LOCK:
        return {name: b.snapshot() for name, b in _REGISTRY.items()}


def reset_all() -> None:
    """清空注册表（仅测试用）。"""
    with _REGISTRY_LOCK:
        _REGISTRY.clear()
```

### 三个要点

1. **`_current_state_unlocked()` 里"OPEN 超时自动降 HALF_OPEN"**：状态不是靠定时器切的，而是**每次读状态时顺手判断**——过了 `recovery_timeout` 就地改状态。这样不用起后台线程，代码简单且线程安全。
2. **`before_call()` 的两个闸门**：OPEN（没到试探时间）直接抛 `CircuitOpenError`（快速失败的价值就在这一抛）；HALF_OPEN 有 `half_open_max_calls` 个名额，超名额照样拒（保护刚恢复的服务）。
3. **`record_failure()` 在 HALF_OPEN 下试探失败 → 立刻重新跳闸并重置计时**——这就是实测里"第 4 次请求 16s（熔断 fast-fail）→ 等 35s → 恢复"的机制来源。

---

## 4. `services/common/client.py` 逐行解释

> 🔴 勘误（2026-10-19）：实测版 API 是 `get_client(name)`（按名取单例）+ `ServiceClient.request()`。没有 `make_clients`、没有 `set_trace_id`。trace_id 从 `app_my.core.logging.trace_id_var`（阶段 7 的 contextvars）自动取。

#### 文件全文（行尾即注释）

```python
# services/common/client.py
"""
服务间调用客户端（ServiceClient）—— 微服务之间唯一的"电话机"

它把四件事打包在一起，业务代码只管 client.post(...)，不用关心细节：
    ① HTTP 传输     ：用 httpx.AsyncClient（异步，不阻塞事件循环）
    ② 自动重试      ：网络抖动/对方 5xx 时按"指数退避"重试几次
    ③ 熔断保护      ：对方连续挂了就跳闸，立刻失败，不再陪它耗超时
    ④ 上下文透传    ：把 trace_id / tenant_id / user_id 放进请求头带过去

为什么要透传上下文：
    一次用户请求会穿过 "Kong → chat → recommender" 三个进程。
    如果不把 trace_id 带过去，三个进程各写各的日志，出问题时你根本没法把
    同一次请求的三段日志串起来看 —— 这就是"链路追踪"要解决的头号问题。
"""
from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Dict, Optional

import httpx

from services.common import breaker as breaker_mod

# 请求头名字，全项目统一（Kong 和各服务都用这三个）
HEADER_TRACE = "X-Trace-Id"
HEADER_TENANT = "X-Tenant-Id"
HEADER_USER = "X-User-Id"

# 这几类 HTTP 状态码才重试：429 是被限流（等一下再来），5xx 是对方出错。
# 4xx（401/403/404/422）是"请求本身有问题"，重试一万次也一样，不重试。
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ServiceCallError(RuntimeError):
    """服务调用最终失败时抛出。调用方 catch 它做降级。"""


def _current_trace_id() -> str:
    """
    取当前协程上下文里的 trace_id。

    为什么用 contextvars 而不是参数传递：
    trace_id 是"贯穿全链路的环境变量"，如果每个函数都加一个 trace_id 参数，
    从接口层到最深的工具函数要改几十个签名。contextvars 是 Python 官方给的
    "协程版全局变量"，在 await 链里自动传递，不需要改任何函数签名。
    """
    try:
        from app_my.core.logging import trace_id_var
        value = trace_id_var.get()
        return value if value and value != "-" else ""
    except Exception:
        return ""


def _upstream_token() -> str:
    """取上游请求带过来的 JWT（由 TokenCaptureMiddleware 存进 contextvars）。"""
    try:
        from services.common.context import get_upstream_token
        return get_upstream_token()
    except Exception:
        return ""


class ServiceClient:
    """
    针对某一个下游服务的客户端。一个下游服务一个实例（内部复用同一个连接池）。
    """

    def __init__(
        self,
        name: str,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
        retries: int = 2,
        backoff: float = 0.2,
        transport: Optional[Any] = None,
        **breaker_kwargs,
    ) -> None:
        """
        transport：可选的 httpx 传输层。正常运行时不传（走真实网络）；
        单元测试时传 httpx.MockTransport，就能在完全离线的情况下
        精确模拟"对方返回 503""连接超时"等各种故障，验证重试和熔断逻辑。
        """
        self.name = name
        self._transport = transport
        self.base_url = (base_url or os.getenv(
            f"SERVICE_{name.upper()}_URL", f"http://127.0.0.1:{_default_port(name)}"
        )).rstrip("/")
        self.timeout = timeout
        self.retries = retries          # 首次失败后再试几次（不含第一次）
        self.backoff = backoff          # 退避基数：第 n 次等待 backoff * 2^(n-1) 秒
        self.breaker = breaker_mod.get_breaker(name, **breaker_kwargs)
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ 连接管理
    def _ensure_client(self) -> httpx.AsyncClient:
        """
        懒创建 httpx.AsyncClient。

        为什么不每次请求 new 一个：
        AsyncClient 内部持有连接池，复用它能省掉反复 TCP 握手 + TLS 的开销。
        但也不能在 __init__ 里创建 —— 那时可能还没有事件循环。
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 2.0)),
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        """关闭连接池。服务关闭时调用，否则会有连接泄漏警告。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------ 对外方法
    async def post(self, path: str, payload: Optional[Dict[str, Any]] = None,
                   **kwargs) -> Dict[str, Any]:
        """POST JSON。返回对方响应的 JSON 字典。"""
        return await self.request("POST", path, json=payload, **kwargs)

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None,
                  **kwargs) -> Dict[str, Any]:
        """GET。返回对方响应的 JSON 字典。"""
        return await self.request("GET", path, params=params, **kwargs)

    async def request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        trace_id: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发请求的核心方法：熔断闸门 → 重试循环 → 回写熔断状态。

        参数：
            method     HTTP 方法（"GET" / "POST"）
            path       路径，如 "/internal/nodes/recommend"
            json       POST 的请求体（字典）
            params     GET 的查询参数（字典）
            tenant_id  要透传的租户 ID（不传就不带这个头）
            user_id    要透传的用户 ID
            trace_id   要透传的链路 ID（不传就自动从 contextvars 里取）
            auth_token 要透传的 JWT（形如 "Bearer xxx"）。
                       因为鉴权下沉在各服务内（Kong 不鉴权），跨服务调用必须把
                       用户的 token 原样带过去，否则对方 AuthMiddleware 直接 401。
                       不传时会自动从 contextvars 里取上游抓到的 token。
        """
        # ---- ① 熔断闸门：已跳闸就直接抛，不再发请求 ----
        self.breaker.before_call()

        headers: Dict[str, str] = {}
        tid = trace_id or _current_trace_id()
        if tid:
            headers[HEADER_TRACE] = tid
        if tenant_id is not None:
            headers[HEADER_TENANT] = str(tenant_id)
        if user_id is not None:
            headers[HEADER_USER] = str(user_id)

        token = auth_token or _upstream_token()
        if token:
            headers["Authorization"] = token

        last_error = ""
        client = self._ensure_client()

        # ---- ② 重试循环：第 0 次是正常请求，之后才是重试 ----
        for attempt in range(self.retries + 1):
            try:
                resp = await client.request(method, path, json=json, params=params, headers=headers)

                if resp.status_code in RETRYABLE_STATUS:
                    # 对方明确说"我现在不行"，算一次失败，可以重试
                    last_error = f"HTTP {resp.status_code}"
                    raise httpx.HTTPStatusError(last_error, request=resp.request, response=resp)

                if resp.status_code >= 400:
                    # 4xx 不重试：请求本身有问题，重试没意义。直接算成功"送达"，
                    # 让熔断知道对方还活着（它只是拒绝了我们的请求）。
                    self.breaker.record_success()
                    raise ServiceCallError(
                        f"[{self.name}] {method} {path} 返回 {resp.status_code}: {resp.text[:200]}"
                    )

                self.breaker.record_success()
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text}

            except breaker_mod.CircuitOpenError:
                raise                      # 熔断的错不重试，直接往上抛
            except ServiceCallError:
                raise                      # 4xx 的错不重试
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt >= self.retries:
                    break
                # 指数退避 + 抖动：0.2s → 0.4s → 0.8s…再加 ±20% 随机，
                # 避免"所有调用方同一时刻一起重试"把刚恢复的服务再次打垮（惊群）。
                delay = self.backoff * (2 ** attempt) * (1 + random.uniform(-0.2, 0.2))
                await asyncio.sleep(max(delay, 0.01))

        # ---- ③ 所有重试都失败：记一次熔断失败，再抛给调用方降级 ----
        self.breaker.record_failure(last_error)
        raise ServiceCallError(
            f"[{self.name}] {method} {path} 失败（重试 {self.retries} 次后）：{last_error}"
        )

    # ------------------------------------------------------------------ 观测
    def breaker_snapshot(self) -> Dict[str, object]:
        """导出这个下游服务当前熔断器的状态。"""
        return self.breaker.snapshot()


def _default_port(name: str) -> int:
    """各服务的默认端口（与 docker/kong/kong.yml 保持一致）。"""
    return {"user": 9121, "recognizer": 9122, "recommender": 9123, "chat": 9124}.get(name, 9002)


def get_client(name: str, **kwargs) -> ServiceClient:
    """
    取（必要时创建）某个下游服务的客户端。

    做成全局缓存的原因和熔断器一样：一个进程里对同一个下游只该有一个连接池。
    """
    global _CLIENTS
    if name not in _CLIENTS:
        _CLIENTS[name] = ServiceClient(name, **kwargs)
    return _CLIENTS[name]


_CLIENTS: Dict[str, ServiceClient] = {}


async def aclose_all() -> None:
    """关闭所有客户端的连接池（服务关闭时调用）。"""
    for c in _CLIENTS.values():
        await c.aclose()
    _CLIENTS.clear()
```

### 四个要点

1. **重试循环里 4xx 与 5xx 分家**：`RETRYABLE_STATUS = {429, 500, 502, 503, 504}` 才重试；4xx 直接 `record_success()`（对方活着，只是拒绝我们）后抛 `ServiceCallError`——这保证了"请求写错"不会把熔断器打跳闸。
2. **一次 `post()` 只记 1 次熔断失败**：重试是内部循环，3 次 HTTP 失败 → 1 次调用失败。熔断阈值衡量的是"调用级故障"，不是"请求数"。
3. **指数退避 + ±20% 抖动**：`backoff * 2**attempt * (1 + uniform(-0.2, 0.2))`，防止所有调用方同一瞬间一起重试（惊群）把刚恢复的服务再次打垮。
4. **`transport` 参数**：正常运行不传（走真实网络）；单测传 `httpx.MockTransport`，离线精确模拟 503/连接失败——§6 的 7 个客户端用例全靠它。

---

## 5. `services/common/context.py` 逐行解释

> 🔴 勘误（2026-10-19）：实测版存的是**上游 JWT**，不是 trace_id（trace_id 复用阶段 7 的 `app_my.core.logging.trace_id_var`，不重复造）。

#### 文件全文（行尾即注释）

```python
# services/common/context.py
"""
跨服务调用的"上下文小仓库"—— 存放那些没法通过函数参数传递、但又必须带过去的东西

为什么单独一个文件：
    LangGraph 的节点函数签名被框架定死了：`async def node(state: dict) -> dict`。
    我们想在节点里发 HTTP 请求调用别的服务，就得带上用户的 JWT，
    但签名里塞不进去。contextvars 是 Python 官方为这种场景准备的方案：
    它在"协程上下文"里存值，await 链上任何深度都能读到，且不同请求之间互不干扰。

    类比：普通全局变量是"整栋楼共用一个白板"（并发时会串台）；
    contextvars 是"每个人手里一块自己的小白板"（各自独立，还能带进电梯）。
"""
from __future__ import annotations

import contextvars
from typing import Optional

# 上游请求带过来的原始 Authorization 头（形如 "Bearer eyJhbGci..."）
_upstream_token: contextvars.ContextVar[str] = contextvars.ContextVar(
    "upstream_token", default=""
)


def set_upstream_token(token: str) -> None:
    """在请求入口处把 token 存进来。"""
    _upstream_token.set(token or "")


def get_upstream_token() -> str:
    """在任意深度（包括 LangGraph 节点里）把 token 读出来。"""
    return _upstream_token.get() or ""


def auth_header() -> dict:
    """
    直接产出可以塞进 httpx 的请求头字典。
    没有 token 时返回空字典，避免发出一个值为空的 Authorization 头（对方会解析失败）。
    """
    token = get_upstream_token()
    return {"Authorization": token} if token else {}
```

### 为什么需要它

LangGraph 节点签名被框架钉死为 `async def node(state) -> dict`，用户的 JWT 塞不进参数。`contextvars` 相当于"每个请求自己的一块小白板"：`TokenCaptureMiddleware` 在入口 `set_upstream_token()` 存一笔，节点深处 `auth_header()` 取出来用，不同请求互不串台。

---

## 6. `services/common/app_factory.py` 逐行解释

> 🔴 勘误（2026-10-19）：项目里**没有** `app_my/middleware/cors.py`（CORS 用 `fastapi.middleware.cors` 自带的）、没有 `app_my/middleware/tracing.py`（是 `app_my/middleware/trace.py`）、`MetricsMiddleware` 在 `app_my/middleware/metrics.py`（不在 core 里）。本文件还**新定义了两个中间件**：`TenantVarMiddleware`（把租户写进 contextvars）和 `TokenCaptureMiddleware`（把 JWT 写进 contextvars）。

#### 文件全文（行尾即注释）

```python
# services/common/app_factory.py
"""
服务工厂（create_service_app）—— 四个微服务的"统一装配线"

为什么要有它：
    拆成四个服务后，如果每个服务的 main.py 都抄一遍"加中间件 + 加健康检查 + 加指标端点"，
    很快就会抄歪：某个服务忘了加鉴权、另一个服务的 /metrics 被 401 挡住……
    工厂函数把这套装配固定成一份代码，四个服务共享，顺序只可能错一次。

🔴 本文件最关键的知识点：Starlette 的中间件"洋葱顺序"
    Starlette 规则：**后 add_middleware 的，包在更外层**。
    所以下面代码是"倒着写"的：越靠上的 add 语句，请求越晚经过它（越靠里）。
    请求实际经过顺序（外 → 内）：
        CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
              → UserLimit → RateLimit → (Quota) → 路由
    响应返回时反过来走一遍（内 → 外）。

    🔴 两条不能违反的顺序约束：
    1. MetricsMiddleware 必须 add 在 AuthMiddleware **之前**（这样它才更靠外），
       否则 /metrics 会先被 Auth 拦下返回 401，Prometheus 永远抓不到数据。
    2. CORS 必须最后 add（最外层），否则内层限流吐出的 429 响应不带跨域头，
       浏览器前端只能看到"网络错误"，根本不知道自己是被限流了。
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import List, Optional, Sequence, Tuple

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app_my.core.config import settings
from app_my.core.logging import logger, setup_logging
from app_my.core.tenant import current_tenant_id
from app_my.middleware.auth import AuthMiddleware
from app_my.middleware.metrics import MetricsMiddleware
from app_my.middleware.quota import QuotaMiddleware
from app_my.middleware.rate_limit import RateLimitMiddleware, UserRateLimitMiddleware
from app_my.middleware.tenant import TenantContextMiddleware
from app_my.middleware.trace import TraceIdMiddleware


# ---------------------------------------------------------------- 两个本阶段新增的小中间件
class TenantVarMiddleware(BaseHTTPMiddleware):
    """
    把 request.state.tenant_id 写进 contextvars（current_tenant_id）。

    为什么必须新写一个：
    现有的 TenantContextMiddleware 只写 request.state，**不写 contextvars**。
    单体时代没问题——因为 app_my/agents/coordinator.py 里手动 set 了一次。
    但拆成微服务后，recommender 进程里跑的 recommend_node 深处会调
    local_recipe_search()，它靠 current_tenant_id 做灰度判定；
    这个进程里没人 set，就会一直用默认值 1 —— 灰度/租户隔离静默失效。

    🔴 这是本次拆分最容易漏、且最难查的一个点：
    不报错、不崩溃，只是"租户 B 用成了租户 A 的配置"。
    """

    async def dispatch(self, request: Request, call_next):
        tenant_id = getattr(request.state, "tenant_id", None)
        # 没有租户（未登录 / 内部探测）就保留默认值，不强行写 0
        token = current_tenant_id.set(tenant_id if tenant_id is not None else 1)
        try:
            return await call_next(request)
        finally:
            # 必须 reset：不然同一个线程处理下一个请求时会读到上一个租户（连接池复用场景）
            current_tenant_id.reset(token)


class TokenCaptureMiddleware(BaseHTTPMiddleware):
    """
    把原始 Authorization 头存进 contextvars，供"跨服务调用"时透传。

    为什么需要：chat 服务要去调 recommender 服务，而 recommender 也有 AuthMiddleware
    （鉴权下沉在各自服务内，Kong 不做鉴权）。所以 chat 必须把用户的 JWT 原样带过去，
    否则对方直接 401。

    为什么用 contextvars 而不是一层层传参：
    LangGraph 的节点函数签名是固定的 `async def node(state: dict) -> dict`，
    没法额外塞一个 token 参数。contextvars 让我们"绕开签名"把值带进去。
    """

    async def dispatch(self, request: Request, call_next):
        from services.common.context import set_upstream_token
        set_upstream_token(request.headers.get("authorization", ""))
        return await call_next(request)


# ---------------------------------------------------------------- 工厂函数
def create_service_app(
    service_name: str,
    routers: Sequence[Tuple[APIRouter, str, List[str]]] = (),
    *,
    enable_auth: bool = True,
    enable_quota: bool = False,
    capture_auth: bool = False,
    cors_origins: Optional[List[str]] = None,
    startup_tasks: Sequence[Callable[[], Coroutine]] = (),
) -> FastAPI:
    """
    造一个"装配好"的 FastAPI 服务实例。

    参数：
        service_name   服务名（user / recognizer / recommender / chat），进 /health 和日志
        routers        要挂的路由，每个元素是 (router, prefix, tags) 三元组
        enable_auth    是否挂 JWT 鉴权中间件（四个服务都要 True）
        enable_quota   是否挂租户配额中间件（只有 chat 服务要 True，因为它管 /chat/stream）
        capture_auth   是否捕获 Authorization 头用于跨服务透传（只有 chat 服务要 True）
        cors_origins   允许的跨域来源；不传就用 settings.CORS_ORIGINS
        startup_tasks  要常驻运行的后台协程工厂（如 chat 服务的 Redis 订阅中继）。
                       传进来的是"函数"而不是"协程对象"，因为协程对象只能被 await 一次；
                       传函数才能在每个进程里重新创建。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging()
        logger.info("服务 [%s] 启动中 ...", service_name)

        # 拉起常驻后台协程（如 WS 通知中继），并把句柄存起来以便关闭时取消
        tasks = [asyncio.create_task(factory(), name=f"{service_name}-bg-{i}")
                 for i, factory in enumerate(startup_tasks)]
        if tasks:
            logger.info("服务 [%s] 已启动 %d 个后台协程", service_name, len(tasks))

        yield

        logger.info("服务 [%s] 关闭", service_name)
        # 先取消后台协程再收尾，否则事件循环关闭时会报
        # "Task was destroyed but it is pending!"
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        # 关闭跨服务调用客户端的连接池，否则进程退出会有 "unclosed connector" 警告
        try:
            from services.common.client import aclose_all
            await aclose_all()
        except Exception:
            pass

    app = FastAPI(
        title=f"{settings.APP_NAME} · {service_name}服务",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # ============ 中间件（🔴 倒着 add：越靠上的越靠里）============
    if capture_auth:
        app.add_middleware(TokenCaptureMiddleware)      # 最里层：先把 token 抓到手

    if enable_quota:
        app.add_middleware(QuotaMiddleware)             # 租户配额（只有 chat 用）

    app.add_middleware(RateLimitMiddleware)             # 4. IP 级限流
    app.add_middleware(UserRateLimitMiddleware)         # 3. 用户级限流
    app.add_middleware(TenantVarMiddleware)             # 2.6 写 contextvars（本阶段新增）
    app.add_middleware(TenantContextMiddleware)         # 2.5 租户上下文
    if enable_auth:
        app.add_middleware(AuthMiddleware)              # 2. JWT 鉴权
    app.add_middleware(MetricsMiddleware)               # 1.5 指标埋点 + /metrics（必须在 Auth 之外）
    app.add_middleware(TraceIdMiddleware)               # 1. TraceID
    app.add_middleware(                                 # 0. CORS（最后 add → 最外层）
        CORSMiddleware,
        allow_origins=cors_origins or settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ============ 路由 ============
    for router, prefix, tags in routers:
        app.include_router(router, prefix=prefix, tags=tags)

    # ============ 通用端点：每个服务都有，方便 Kong 探活与排错 ============
    @app.get("/")
    async def root():
        return {"service": service_name, "version": settings.APP_VERSION, "status": "running"}

    @app.get("/health")
    async def health():
        """
        健康检查。除了返回 ok，还带上"我依赖的下游服务熔断器状态"——
        排障时一眼就能看出 chat 是不是把 recommender 熔断了。
        """
        from services.common.breaker import all_snapshots
        return {
            "status": "ok",
            "service": service_name,
            "version": settings.APP_VERSION,
            "breakers": all_snapshots(),
        }

    return app
```

### 中间件顺序为什么这样？

实测确认（别凭印象）：Starlette 的 `add_middleware()` 是 `user_middleware.insert(0, ...)`——
**user_middleware 列表"外层在前"**，所以"后 add 的更靠外层"。请求实际穿过顺序（外 → 内）：

```
CORS → TraceID → Metrics → Auth → TenantContext → TenantVar
      → UserLimit → RateLimit → (Quota) → (TokenCapture) → 路由
```

两条铁约束（§6.3 的测试把它们钉死了）：
1. **Metrics 在 Auth 之外**（add 顺序上 Metrics 先 add）——否则 `/metrics` 被 401 挡住，Prometheus 永远抓不到；
2. **CORS 最后 add（最外层）**——否则内层限流的 429 不带跨域头，浏览器只看到"网络错误"。

---

## 7. 第 4 章 四个服务的入口 `main.py`

> 🔴 勘误（2026-10-19）：路由归属以实测版为准——`/kg` 归 recommender、`/oss` 归 recognizer、`/cache` 归 user、`/tasks`+`/ws` 归 chat；**不存在 `/memory` 路由**。

### 7.1 `services/user/main.py`

```python
# services/user/main.py
"""
user 服务（端口 9121）—— 管"人"和"组织"的一切

职责边界（为什么这些路由放一起）：
    认证（auth）、用户资料（user）、租户（tenant）、管理端（admin）、成本统计（billing）
    这五组路由的共同点是：**它们只碰 PostgreSQL 和 Redis，不碰大模型**。
    这是拆分的第一条依据——资源画像相同的功能放一起，扩容时可以单独加机器，
    不用为了给"对话"扩容而连带把"登录"也复制一份。

它不做什么：不调大模型、不碰 Milvus、不碰 Neo4j。
"""
from services.common.app_factory import create_service_app

# 复用单体时代已经写好的路由模块：拆分是"换入口"，不是"重写业务"
from app_my.api import auth, user, cache
from app_my.api import tenant as tenant_api
from app_my.api import admin as admin_api
from app_my.api import billing

app = create_service_app(
    "user",
    routers=[
        (auth.router, "/auth", ["认证"]),
        (user.router, "/users", ["用户"]),
        (tenant_api.router, "/tenants", ["租户管理"]),
        (admin_api.router, "/admin", ["管理端"]),
        (billing.router, "/billing", ["成本统计"]),
        (cache.router, "/cache", ["缓存观测"]),
    ],
    enable_auth=True,      # 有自己的 JWT 鉴权（Kong 不鉴权，鉴权下沉在各自服务）
    enable_quota=False,    # 配额只管 /chat/stream，那是 chat 服务的事
    capture_auth=False,    # user 服务不往下调别的服务，不用透传 token
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.user.main:app", host="0.0.0.0", port=9121, reload=False)
```

> 要点：user 服务**只碰 PostgreSQL 和 Redis，不碰大模型**。资源画像相同的功能放一起，扩容时不用连坐。

### 7.2 `services/recognizer/main.py`

```python
# services/recognizer/main.py
"""
recognizer 服务（端口 9122）—— 把"用户说了什么 / 拍了什么"变成结构化食材清单

拆出来的理由（拆分依据第二条：故障半径）：
    识别节点要调**多模态大模型**（看图），是所有节点里最慢、最贵、最容易超时的一环。
    它单独成一个服务，好处很实在：
      · 它超时/报错时，只影响"识别"，chat 服务还能用上一轮结果继续跑；
      · 它慢的时候可以单独加实例（比如 2 个 recognizer + 1 个 chat）；
      · 改识别模型不用重启整个应用。

对外只有两个"内部接口"（/internal/ 前缀，约定只给服务间调用）：
    POST /internal/nodes/recognize   文字/图片 → 食材清单
    POST /internal/nodes/nutrition   食材清单 → 营养估算

🔴 为什么要重新包一层 HTTP 接口，而不是直接把 state 整个传过来：
    LangGraph 的 state 里有 messages 字段，里面装的是 LangChain 的
    HumanMessage / AIMessage **对象**，不是 JSON。直接 json.dumps 会报
    "Object of type HumanMessage is not JSON serializable"。
    所以这里定了一套"只传必要字段"的窄接口：进 JSON、出 JSON。
"""
from typing import List, Optional

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app_my.agents.nutritionist import nutrition_node
from app_my.agents.recognizer import recognize_node
from app_my.api import oss
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


# ----------------------------------------------------------------- 接口的数据契约
class RecognizeIn(BaseModel):
    """识别接口的入参。"""
    text: str = Field(default="", description="用户输入的文字（图片模式下可作补充提示）")
    image_url: List[str] = Field(default_factory=list, description="图片 URL 列表，空数组=走文字抽取")


class NutritionIn(BaseModel):
    """营养接口的入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="上一步识别出的食材清单")


def _summary_of(node_output: dict) -> str:
    """
    从节点返回值里抽出那条 AIMessage 的文本，作为 summary 返回。

    节点返回形如 {"nutrition": {...}, "messages": [AIMessage("...")]}；
    messages 是 LangChain 对象不能进 JSON，所以这里提前把它转成纯字符串。
    """
    msgs = node_output.get("messages") or []
    if msgs:
        return getattr(msgs[-1], "content", "") or ""
    return ""


router = APIRouter()


@router.post("/internal/nodes/recognize")
async def http_recognize(body: RecognizeIn):
    """
    把 recognize_node 包成 HTTP 接口。

    做法：造一个"最小可用的 state" → 调原来的节点函数 → 把结果转成纯 JSON。
    这样**一个字的业务逻辑都没重写**，只是加了一层协议转换。
    """
    state = {
        "messages": [HumanMessage(content=body.text)],   # 节点只读最后一条消息的 content
        "image_url": body.image_url or [],
    }
    out = await recognize_node(state)
    logger.info("recognizer.http: 识别完成，%d 种食材", len(out.get("ingredients") or []))
    return {
        "ingredients": out.get("ingredients") or [],
        "summary": _summary_of(out),
    }


@router.post("/internal/nodes/nutrition")
async def http_nutrition(body: NutritionIn):
    """把 nutrition_node 包成 HTTP 接口。"""
    state = {"ingredients": body.ingredients or []}
    out = await nutrition_node(state)
    return {
        "nutrition": out.get("nutrition") or {},
        "summary": _summary_of(out),
    }


app = create_service_app(
    "recognizer",
    routers=[
        (router, "", ["识别内部接口"]),
        (oss.router, "/oss", ["阿里云OSS"]),   # 图片要先上传才能识别，归识别域
    ],
    enable_auth=True,      # 一样要鉴权：Kong 不做鉴权，靠各服务自己守门
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recognizer.main:app", host="0.0.0.0", port=9122, reload=False)
```

> 要点：**窄接口**（进 JSON 出 JSON）。LangGraph 的 state 里有 `HumanMessage/AIMessage` 对象，直接 json.dumps 会报 not serializable，所以 HTTP 层只传必要字段，`_summary_of` 把 AIMessage 转纯字符串。

### 7.3 `services/recommender/main.py`

```python
# services/recommender/main.py
"""
recommender 服务（端口 9123）—— 管"找菜谱"和"排菜谱"，以及知识图谱

拆出来的理由（拆分依据第三条：数据所有权）：
    Milvus 向量库和 Neo4j 图谱**只被这一个服务访问**。
    拆分前 chat 进程里也连着这两个库，现在它们成了 recommender 的"私有数据"，
    别的服务想查菜谱，只能走 HTTP 来问它 —— 这就是微服务的"数据所有权"原则。

对外接口：
    POST /internal/nodes/recommend   食材清单 → 候选菜谱（未排序）
    POST /internal/nodes/rank        候选菜谱 + 用户画像 → 排好序的菜谱
    GET  /kg/ask                     知识图谱问答（阶段 3 的路由，原样搬过来）
    GET  /kg/stats                   图谱规模统计

🔴 本服务最需要注意的一点（也是本次拆分最容易踩的坑）：
    local_recipe_search() 内部会读 current_tenant_id 这个 contextvars 变量做灰度判定。
    单体时代是 coordinator 手动 set 的；现在它跑在 recommender 自己的进程里，
    没人 set 就会一直用默认值 1 —— 表现为"灰度开关对所有租户一起生效/失效"，
    而且**不报错**。
    解决办法在 services/common/app_factory.py 的 TenantVarMiddleware：
    每个请求进来时把 request.state.tenant_id 写进 contextvars。
"""
from typing import List

from fastapi import APIRouter
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from app_my.agents.ranker import rank_node
from app_my.agents.recommender import recommend_node
from app_my.api import kg
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


class RecommendIn(BaseModel):
    """推荐接口入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="识别出的食材清单")


class RankIn(BaseModel):
    """重排接口入参。"""
    recipes: List[dict] = Field(default_factory=list, description="候选菜谱（推荐节点的产出）")
    user_profile: dict = Field(default_factory=dict, description="用户画像（目标/忌口/过敏/偏好）")


def _summary_of(node_output: dict) -> str:
    """把节点返回里的 AIMessage 转成纯字符串（LangChain 对象不能进 JSON）。"""
    msgs = node_output.get("messages") or []
    return getattr(msgs[-1], "content", "") if msgs else ""


router = APIRouter()


@router.post("/internal/nodes/recommend")
async def http_recommend(body: RecommendIn):
    """把 recommend_node 包成 HTTP 接口。"""
    out = await recommend_node({"ingredients": body.ingredients or []})
    recipes = out.get("recipes") or []
    logger.info("recommender.http: 检索到 %d 条候选菜谱", len(recipes))
    return {"recipes": recipes, "summary": _summary_of(out)}


@router.post("/internal/nodes/rank")
async def http_rank(body: RankIn):
    """把 rank_node 包成 HTTP 接口。"""
    out = await rank_node({
        "recipes": body.recipes or [],
        "user_profile": body.user_profile or {},
    })
    ranked = out.get("ranked_recipes") or []
    logger.info("recommender.http: 重排完成，%d 条", len(ranked))
    return {"ranked_recipes": ranked, "summary": _summary_of(out)}


app = create_service_app(
    "recommender",
    routers=[
        (router, "", ["推荐内部接口"]),
        (kg.router, "/kg", ["知识图谱"]),
    ],
    enable_auth=True,
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recommender.main:app", host="0.0.0.0", port=9123, reload=False)
```

> 要点：Milvus / Neo4j 只被这个服务访问——"数据所有权"原则。`/kg` 挂在这里（不在 chat）。

### 7.4 `services/chat/main.py`

```python
# services/chat/main.py
"""
chat 服务（端口 9124）—— 用户真正"说话"的入口，也是唯一会去调别的服务的地方

它承担三件事：
    1. /chat/stream   流式对话（LangGraph 编排，可能跨服务调 recognizer / recommender）
    2. /ws/notifications  WebSocket 实时推送（阶段 8）
    3. /tasks/*       长任务提交与查询（阶段 8）

它是本阶段唯一打开了两个"额外开关"的服务：
    enable_quota=True   因为 /chat/stream 要按租户配额限流（QuotaMiddleware 只认这个路径）
    capture_auth=True   因为它要跨服务调用，必须把用户的 JWT 抓下来透传给下游
    startup_tasks       因为 WS 通知中继（订阅 Redis 频道）必须常驻在 chat 进程里
"""
import os

from app_my.api import chat
from app_my.api import tasks as tasks_api
from app_my.ws import gateway as ws_gateway
from app_my.ws.relay import run_relay

from services.common.app_factory import create_service_app


# 读一次运行模式，写进启动日志，方便排错时一眼确认
SPLIT_MODE = os.getenv("SPLIT_MODE", "local").strip().lower()


app = create_service_app(
    "chat",
    routers=[
        (chat.router, "/chat", ["AI对话"]),
        (tasks_api.router, "/tasks", ["异步任务"]),
        (ws_gateway.router, "/ws", ["WebSocket"]),
    ],
    enable_auth=True,
    enable_quota=True,     # 只有 chat 需要：QuotaMiddleware 拦截 /chat/stream 做租户配额
    capture_auth=True,     # 只有 chat 需要：把 JWT 存进 contextvars 以便透传给下游
    startup_tasks=[run_relay],   # WS 通知中继常驻协程
)


@app.get("/mode")
async def mode():
    """运维小端点：一眼看出这个 chat 进程现在是本地模式还是远程模式。"""
    return {
        "service": "chat",
        "split_mode": SPLIT_MODE,
        "remote_nodes": SPLIT_MODE == "remote",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.chat.main:app", host="0.0.0.0", port=9124, reload=False)
```

> 要点：chat 是唯一打开三个开关的服务——`enable_quota`（管 /chat/stream 配额）、`capture_auth`（抓 JWT 透传给下游）、`startup_tasks=[run_relay]`（WS 通知中继常驻）。`/mode` 是运维小端点，一眼看出当前是 local 还是 remote。

---

## 8. 第 5 章 coordinator 的本地 / 远程切换

### 8.1 设计动机

拆微服务后，LangGraph 图里的 4 个节点要改走 HTTP。但图**形状**不该变、本地模式还得留（单测不开外部服务、压测对照）。实测方案是把"图的形状"和"节点怎么实现"解耦：

| 文件 | 职责 |
| --- | --- |
| `coordinator.py`（修改） | `build_workflow(nodes=None)`：不传 nodes = 本地函数直调（原行为）；传了 = 用传入的节点表注册图 |
| `coordinator.py` 里的 `_resolve_nodes()` | 读 `SPLIT_MODE`：remote 时返回 `services.chat.graph_remote.remote_nodes()` |
| `services/chat/graph_remote.py`（新增） | 4 个远程节点 + `remote_nodes()` 节点表（output 仍用本地实现） |

**没有 `coordinator_local.py`**——连边代码只有一份，不需要抽两份（勘误：旧手册的抽离方案作废）。

### 8.2 关键代码

coordinator 的修改（整段替换锚点见操作手册 §5.1）：

```python
def build_workflow(nodes=None):
    """
    组装并编译工作流。

    add_edge 的两种写法：
        add_edge("recognize", "nutrition")         一次只接一个下游 → 顺序执行
        add_edge(["nutrition", "recommend"], "rank") 多个起点汇聚到同一节点 → 等待全部完成再走

    v3阶段9 新增参数 nodes：
        传 None（默认）→ 用本地节点，行为和阶段 8 之前完全一致（单体模式）。
        传一张"节点名 → 函数"的表 → 用这张表注册节点（微服务模式下换成 HTTP 版节点）。
        这样"图的形状"和"节点怎么实现"就解耦了：拆不拆微服务，连边代码一行都不用改。
    """
    if nodes is None:
        nodes = {
            "recognize": recognize_node,
            "nutrition": nutrition_node,
            "recommend": recommend_node,
            "rank": rank_node,
            "output": output_node,
        }

    workflow = StateGraph(ChefState)

    # ① 注册节点（名字 → 函数）
    for name, fn in nodes.items():
        workflow.add_node(name, fn)

    # ② 连边（数据流向）
    workflow.add_edge(START, "recognize")
    workflow.add_edge("recognize", "nutrition")        # 识别 → 营养（并行分支 1）
    workflow.add_edge("recognize", "recommend")        # 识别 → 推荐（并行分支 2）
    workflow.add_edge(["nutrition", "recommend"], "rank")   # fan-in：两支都完成才重排
    workflow.add_edge("rank", "output")
    workflow.add_edge("output", END)

    return workflow.compile()


# 惰性单例：编译图有开销，但也不能在 import 时就编译（否则单测/无密钥环境会受影响）
_agent = None


def _resolve_nodes():
    """
    按环境变量 SPLIT_MODE 决定节点用本地版还是远程版（v3阶段9 新增）。

        SPLIT_MODE=local（默认）  → 全部节点在本进程内跑（单体行为，拆分前/对照组用）
        SPLIT_MODE=remote        → 识别/营养/推荐/重排改走 HTTP 调各自的服务

    为什么要做成环境变量而不是硬改代码：
    阶段 9 的验收项之一是"用阶段 7 的指标给出拆分前后对比"——
    同一个代码库，改一个环境变量就能在"单体"和"微服务"两种形态间切换，
    压测才有可比性（否则你得维护两套代码）。
    """
    import os
    if os.getenv("SPLIT_MODE", "local").strip().lower() == "remote":
        from services.chat.graph_remote import remote_nodes
        logger.info("coordinator: SPLIT_MODE=remote，识别/营养/推荐/重排改走 HTTP 调用")
        return remote_nodes()
    return None


def get_coordinator_agent():
    """取（必要时创建）编译后的工作流单例"""
    global _agent
    if _agent is None:
        logger.info("coordinator: 首次编译 StateGraph")
        _agent = build_workflow(nodes=_resolve_nodes())
    return _agent


def reset_coordinator_agent() -> None:
    """测试用：丢掉单例，下次重新编译"""
    global _agent
    _agent = None
```

远程节点表全文：

```python
# services/chat/graph_remote.py
"""
远程节点（remote nodes）—— 把"本地函数调用"换成"HTTP 调用别的服务"

一句话理解：
    单体时代，LangGraph 的 recognize 节点 = 直接 `await recognize_node(state)`（进程内函数调用）。
    拆成微服务后，同一个节点 = `await client.post("/internal/nodes/recognize", ...)`（跨进程 HTTP）。
    **图的形状一点没变**（还是 识别→营养/推荐→重排→输出），变的只是节点内部怎么干活。

🔴 本文件的灵魂：降级（degradation）
    每个远程节点都用 try/except 包住。远程服务挂了（连接失败 / 熔断跳闸 / 5xx），
    节点**不抛异常**，而是返回一个"空但合法"的结果 + 一条说明消息。
    为什么：
        LangGraph 里一个节点抛异常，整条工作流就崩了，用户看到 500。
        但"推荐服务挂了"其实不该让"营养估算"也一起完蛋——
        降级后用户拿到的是"营养报告完整、菜谱部分暂时不可用"，体验好得多，
        这正是"故障隔离"要的效果。
    这也就是验收项「杀掉单个服务，其余功能不受影响」的实现方式。
"""
from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import AIMessage

from app_my.agents.output import output_node
from app_my.agents.recognizer import message_content_to_text
from app_my.core.logging import logger
from app_my.core.tenant import current_tenant_id
from services.common.client import get_client


def _user_text(state: dict) -> str:
    """从 state 里取用户最后一句话的纯文本（支持多模态 content 是 list 的情况）。"""
    messages = state.get("messages") or []
    if not messages:
        return ""
    return message_content_to_text(messages[-1].content)


def _ai(content: str) -> List[AIMessage]:
    """包一条 AIMessage —— 图要求节点返回 messages，用来记录过程。"""
    return [AIMessage(content=content)]


# ------------------------------------------------------------------ ① 识别节点（远程）
async def recognize_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做食材识别。"""
    tenant_id = current_tenant_id.get()
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/recognize",
            {"text": _user_text(state), "image_url": state.get("image_url") or []},
            tenant_id=tenant_id,
        )
        return {
            "ingredients": data.get("ingredients") or [],
            "messages": _ai(data.get("summary") or "[识别] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recognize 失败，已降级：%s", exc)
        return {"ingredients": [], "messages": _ai(f"[识别] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ② 营养节点（远程）
async def nutrition_node_remote(state: dict) -> dict:
    """调 recognizer 服务（9122）做营养估算（营养和识别同域，都在 recognizer）。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"nutrition": {}, "messages": _ai("[营养] 无食材，跳过")}
    try:
        data = await get_client("recognizer").post(
            "/internal/nodes/nutrition",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "nutrition": data.get("nutrition") or {},
            "messages": _ai(data.get("summary") or "[营养] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.nutrition 失败，已降级：%s", exc)
        return {"nutrition": {}, "messages": _ai(f"[营养] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ③ 推荐节点（远程）
async def recommend_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）检索候选菜谱。"""
    tenant_id = current_tenant_id.get()
    ingredients = state.get("ingredients") or []
    if not ingredients:
        return {"recipes": [], "messages": _ai("[推荐] 无食材，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/recommend",
            {"ingredients": ingredients},
            tenant_id=tenant_id,
        )
        return {
            "recipes": data.get("recipes") or [],
            "messages": _ai(data.get("summary") or "[推荐] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.recommend 失败，已降级：%s", exc)
        # 降级：没有菜谱，但工作流继续往下走（营养部分仍然完整）
        return {"recipes": [], "messages": _ai(f"[推荐] 服务不可用，已跳过：{exc}")}


# ------------------------------------------------------------------ ④ 重排节点（远程）
async def rank_node_remote(state: dict) -> dict:
    """调 recommender 服务（9123）做个性化重排。"""
    tenant_id = current_tenant_id.get()
    recipes = state.get("recipes") or []
    if not recipes:
        return {"ranked_recipes": [], "messages": _ai("[重排] 无候选菜谱，跳过")}
    try:
        data = await get_client("recommender").post(
            "/internal/nodes/rank",
            {"recipes": recipes, "user_profile": state.get("user_profile") or {}},
            tenant_id=tenant_id,
        )
        return {
            "ranked_recipes": data.get("ranked_recipes") or [],
            "messages": _ai(data.get("summary") or "[重排] 远程节点返回空结果"),
        }
    except Exception as exc:
        logger.error("remote.rank 失败，已降级：%s", exc)
        return {"ranked_recipes": [], "messages": _ai(f"[重排] 服务不可用，已跳过：{exc}")}


def remote_nodes() -> Dict[str, object]:
    """
    返回"远程版"的节点表。

    注意 output 仍然是**本地**的：
    它是纯文本拼装，不调外部资源，没有必要再跨一次网络（多一跳 = 多一个故障点）。
    这也体现了一条拆分原则：**不是所有东西都要拆，只拆有独立资源/故障特征的**。
    """
    return {
        "recognize": recognize_node_remote,
        "nutrition": nutrition_node_remote,
        "recommend": recommend_node_remote,
        "rank": rank_node_remote,
        "output": output_node,
    }
```

### 8.3 降级策略（故障隔离的实现方式）

每个远程节点都 `try/except` 包住：服务挂了**不抛异常**，返回"空但合法"的结果 + 一条说明消息。一个节点抛异常整条工作流就 500 了；降级后用户拿到"营养报告完整、菜谱部分暂不可用"。这就是操作手册 §14 实测"杀掉 recommender，chat 仍返回完整报告"的代码来源。

---

## 9. 第 6 章 22 个单元测试的设计思路

> 🔴 勘误：实测计数 **8 + 7 + 7 = 22 passed**（不是 27）。测试文件全文以操作手册 §6 为准（API 与旧版不同，别混用）。

### 9.1 test_circuit_breaker（8 用例）

纯内存状态机测试：CLOSED 不误跳 → 到阈值跳 OPEN → OPEN 抛 `CircuitOpenError` → 超时自动 HALF_OPEN → 试探成功合闸 / 试探失败重新跳闸 → snapshot 字段齐全 → 注册表单例。技巧：不真等 30 秒，直接 `_opened_at = time.time() - 999` 把时钟往前拨。

### 9.2 test_service_client（7 用例）

全部挂 `httpx.MockTransport`，离线验证：200 原样返回 → 503×2 后 200（重试救回，发了 3 次）→ 一直 503（抛 `ServiceCallError` 且**一次 post 只记 1 次熔断失败**，跳闸后第 2 次调用 0 次请求）→ 4xx 不重试不记失败 → trace/tenant/auth 三头透传 → `auth_token` 缺省时从 contextvars 自动取 → 连接错误也跳闸。

### 9.3 test_service_apps（7 用例）

**装配结构断言**（不发请求）：四服务都能构建且有 `/health` → 路由归属符合拆分表（`/kg` 在 recommender、`/oss` 在 recognizer…）→ 🔴 `test_metrics_outside_auth`：实测确认 `user_middleware` **外层在前**，所以断言 `Metrics.index < Auth.index` → `test_cors_outermost`：CORS 必须在索引 0 → `test_middleware_order_reads_correctly`：把 chat 整个洋葱顺序钉死成 10 项清单 → `/health` 返回体带 service+breakers → chat 独享 quota/token-capture 两个开关。

> 为什么用测试钉顺序：中间件顺序坏了是"静默失效"——接口全正常，只有 Grafana 空了。只有直接断言装配结构才防得住。

---

## 10. 第 7 章 Kong 声明式配置 `kong.yml`

> 🔴 勘误（2026-10-19）：以实测版为准。全文见操作手册 §7.2，这里讲结构。

### 10.1 services 段（4 个，路由内嵌）

实测版把 route **写在 service 里面**（而不是顶层 routes 段引用 service）——两种写法 Kong 都认，内嵌更紧凑：

| service | 上游 | routes | 限流 |
| --- | --- | --- | --- |
| svc-user | host.docker.internal:9121 | `/auth /users /tenants /admin /billing /cache` | 600/min |
| svc-recognizer | host.docker.internal:9122 | `/oss`（⚠️ `/internal/nodes/*` 故意不暴露到网关） | 300/min |
| svc-recommender | host.docker.internal:9123 | `/kg` | 300/min |
| svc-chat | host.docker.internal:9124 | `/chat /tasks` + `/ws`（WS 单独一条 route） | 120/min |

### 10.2 plugins 段（全局只有一个）

实测版全局插件只有 **correlation-id**：`header_name: X-Trace-Id`（不是 X-Kong-Trace-Id）+ `echo_downstream: true`。后端 `TraceIdMiddleware` 会**沿用**这个 ID，于是 Kong / user / chat / recognizer 四段日志能用同一个 ID 串起来。CORS 由各服务自己的 CORSMiddleware 管（不重复配）；限流按服务挂（见上表）。

### 10.3 三个最容易写错的地方

1. `strip_path: false`——四个服务自己带前缀，Kong 再吃掉前缀就 404；
2. `host.docker.internal`——写 127.0.0.1 会连到 Kong 容器自己，表现为 502；
3. **不要写 `protocols: ["websocket"]`**——Kong 3.x 已移除该值，整个配置解析直接失败；WS 就是普通 http + Upgrade 头自动升级。

---

## 11. 第 8 章 docker-compose 加 Kong service

```yaml
  kong:
    image: docker.1panel.live/library/kong:3.7          # 国内镜像源（Docker Hub 直连易 EOF）
    container_name: ai_chief_kong
    restart: unless-stopped
    environment:
      KONG_DATABASE: "off"                              # 🔴 DB-less 开关，少了它会去找 Postgres
      KONG_DECLARATIVE_CONFIG: /etc/kong/kong.yml
      KONG_PROXY_LISTEN: 0.0.0.0:8000                   # 容器内听 8000（Kong 默认端口）
      KONG_ADMIN_LISTEN: 0.0.0.0:8001                   # Admin API 默认只听 127.0.0.1，改成 0.0.0.0 才能宿主机访问
      KONG_PROXY_ACCESS_LOG: /dev/stdout                # 日志进 stdout，阶段 7 的 Promtail 直接复用
      KONG_ADMIN_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_ERROR_LOG: /dev/stderr
      KONG_NGINX_WORKER_PROCESSES: "1"                  # 单机开发 1 个 worker 足够（默认按核数起，费内存）
    ports:
      - "9100:8000"   # 宿主 9100 → 容器 8000：统一入口
      - "9105:8001"   # 宿主 9105 → 容器 8001：Admin API（DB-less 下只读，查路由表用）
    volumes:
      - ./kong/kong.yml:/etc/kong/kong.yml:ro           # 🔴 挂单个文件；必须"先写文件再起容器"
    extra_hosts:
      - "host.docker.internal:host-gateway"             # 让 Kong 容器内能解析到宿主机上的四个服务
```

> 勘误（2026-10-19）：实测版没有 healthcheck 段——`kong health` 在 DB-less 下意义不大，用 Admin API（9105）探活代替。

### `host.docker.internal` 这块 Docker Desktop 的细节

| OS | 是否默认支持 | 怎么打开 |
| --- | --- | --- |
| macOS（Intel/M1） | ✅ 默认支持 | — |
| Windows Docker Desktop | ✅ 默认支持 | — |
| Linux Docker CE | ❌ 默认不支持 | 加 `--add-host=host.docker.internal:host-gateway` |

Compose 里等价写 `extra_hosts: ["host.docker.internal:host-gateway"]`。

---

## 12. 第 9 章 起服务 + 中间件顺序

> 服务启动的流水线：uvicorn 进程 → import app → 中间件栈构建 → lifespan 进入 → 路由注册 → 监听端口。

### 12.1 中间件顺序与"洋葱"

```
请求 →  CORS            （最外层：所有响应都带跨域头，429 也不例外）
     →  TraceId         （创建或继承 X-Trace-Id）
     →  Metrics         （所有响应记指标；/metrics 端点在这里暴露）
     →  Auth            （JWT 校验，写 user_id 进 state）
     →  TenantContext   （解析租户写 state）
     →  TenantVar       （🆕 把租户写进 contextvars，供检索工具读）
     →  UserRateLimit   （用户级限流）
     →  RateLimit       （IP 级限流）
     →  Quota           （仅 chat：租户配额）
     →  TokenCapture    （仅 chat：把 JWT 存进 contextvars 供跨服务透传）
     →  路由处理函数 → 响应原路返回（内 → 外）
```

> **记住（实测确认，别凭印象）**：`add_middleware()` 是 `user_middleware.insert(0, ...)`——
> **列表"外层在前"**，所以**后调用**的 add 是**最外层**。代码里是"倒着写"的：
> TokenCapture 最先 add（最里层），CORS 最后 add（最外层）。§9.3 的 `test_middleware_order_reads_correctly` 把这个 10 层顺序钉死了。

### 12.2 Prometheus /metrics 为什么不被 401 挡？

因为 Metrics 挂在 Auth 的**外层**（工厂里 `add_middleware(MetricsMiddleware)` 写在 `add_middleware(AuthMiddleware)` 之后）：

```
请求 GET /metrics →
  CORS → TraceId → Metrics（✅ 在这里就被接住，根本走不到 Auth）
       → /metrics 端点返回 Prometheus 文本，200
```

双保险：AuthMiddleware 自身的白名单里也有 `/metrics`，就算顺序将来被人改坏，Auth 也不会拦它。但**顺序断言测试（§9.3）才是第一道防线**——别依赖白名单兜底。

---

## 13. 第 14-16 章 故障隔离与熔断原理

### 13.1 完整状态机

```
                  累计失败 >= threshold
       closed ───────────────────────────► open
         ▲                                  │
         │                                  │ 超过 recovery_timeout
         │  next request 试探成功             ▼
         └──────────────────────────── half_open ── 试探失败 ──► open
```

- **closed** —— 正常。failures 累计，达阈值跳闸。
- **open** —— 闸门开，所有请求 fast-fail（503），不再发。
- **half_open** —— 放一次试探；成功 → closed，失败 → 重新 open 计时。

### 13.2 重试 vs 熔断：互不替代的关系

| 角色 | 重试 | 熔断 |
| --- | --- | --- |
| 目标 | 应付**临时抖动**（网络 1s 内恢复） | 应付**持续故障**（下游宕机 1h） |
| 实现 | for attempt in range(retries+1) | breaker.before_call() |
| 影响 | 每次调用多耗 0.2s/0.4s/0.8s 时间 | 跳闸后调用 **0 秒** 返回 |
| 关联 | 失败时 **同时** 记 breaker | — |

> **常见错误**：只做重试不做熔断。后果是下游宕机时，5000 RPS 的请求会把每请求的 retries（×2 次）全打过去，重试风暴打死整个系统。

---

## 14. 第 17-18 章 Prometheus 抓取 + 对比基线

### 14.1 Prometheus scrape_config 加 target

```yaml
  - job_name: "ms-user"
    static_configs:
      - targets: ["host.docker.internal:9121"]
        labels:
          service: "user"
          stage: "9"
```

- `job_name` 是 Prometheus 内部的"作业名"
- `targets` 是它每 15s 去访问的 `<ip>:<port>/metrics`
- `labels` 是给所有该 job 拉回的指标贴的元数据，方便 Grafana 按 `service=chat` 过滤

### 14.2 对比基线怎么跑有说服力？

| 维度 | 单体（保留对照组） | 4 服务 + Kong |
| --- | --- | --- |
| **平均 /chat/stream 耗时** | 19.8s | 19.8s |
| **P99** | 24.0s | 26.0s |
| **+ 内网 HTTP 开销** | — | +2s |
| **故障隔离** | kill -9 整个 9002 | kill -9 仅 recommender → 降级 |
| **横向扩展** | 顶满 1 进程 | 每服务独立 N× |
| **Prometheus target** | 1 个 | 4 个，可画 `service=chat` 的单独曲线 |

**叙事要写**："耗时几乎没退化（+2s，约 10%），换来（故障隔离 / 独立扩缩 / 独立观测）三件用户侧的硬性收益。"——这是面试里最有冲击力的对比。

---

## 15. 第 21 章 PR 描述的写作思路

PR 描述不是报告，是**给读者"5 分钟看完你说服了你"**的机会。结构建议：

### 15.1 标准骨架

```markdown
## 阶段 N：标题（一行总结最大价值）

### 🎯 目标
- 3-5 条具体目标，每条动词开头：拆 4 服务 / 接 Kong / 实现熔断

### 📦 改动清单
- **新增** ……
- **改动** ……
- **删除** ……（应当尽量少）

### ✅ 测试
- 命令 + 期望结果

### 🚀 端到端实测
- 表格：场景 × 结果

### 📈 关键数字
- 至少 2 个对比数字

### ⚠️ 注意事项
- 写不为人知的坑 / 决策记录
```

### 15.2 容易踩的坑

1. **写"代码风格改进"**——不算里程碑，包含的话 PR 审稿会问"那为什么是这阶段"。改了不该改的就打回。
2. **改动清单不分类**——"5 个文件"不如"新增 4 / 改动 3 / 删除 0"清晰。
3. **测试只写 `pytest passed`** 不写命令——别人在你机器上跑不起来。
4. **端到端实测写 `通过了`**——表格化，**每个场景**一行。
5. **不写"未来作业"**——把下一阶段要做的列出来，让团队知道"这是路线图下一站"。

---

## 写到这里就齐活

说明手册讲完**所有 6 大件事**的底层原理：

1. **共享内核**（`services/common/`）——4 文件的协作
2. **服务入口**（`services/{user,recognizer,recommender,chat}/main.py`）——路由按业务切分
3. **coordinator 重构**（`coordinator.py` 加节点表参数 + `services/chat/graph_remote.py`）——按 SPLIT_MODE 切图
4. **22 个单元测试**（`tests/unit/test_*.py`，8+7+7）——MockTransport 不真发请求
5. **Kong 配置 + Compose + Prometheus**——网关与抓取
6. **故障隔离 / 熔断 / 对比基线**——可量化的成果

剩下操作手册里没有的细节：**让代码跑起来后，再读本节一次**，会发现每个"为什么这么写"在你的机器上**就是这样落地**的。
