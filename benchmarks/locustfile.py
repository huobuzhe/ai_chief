# benchmarks/locustfile.py
"""
阶段 10：AI 私厨 v3.0 性能压测脚本（Locust）

这个脚本干什么
--------------
    同一份脚本、打到两个不同的目标，用来说明一件事：
    「微服务拆分 + 网关」到底带来了什么（或者没带来什么）。
        目标 A（单体）：--host http://127.0.0.1:9002   ← 阶段 8 之前的单体，所有接口在一个进程里
        目标 B（微服务）：--host http://127.0.0.1:9100  ← 阶段 9 拆成 4 个服务 + Kong 网关入口
    两个目标跑同一份脚本、同样并发，得到两张数据表，
    差值就是"拆分的代价与收益"——阶段 7 手册里欠着的那个"拆分前后 P99/QPS 对比"。

三个压测场景（都是真实接口，字段与 app_my/schemas 里的 Pydantic 模型一一对应）
--------------------------------------------------------------------------------
    login       POST /auth/login          登录。慢在 bcrypt 校验（BCRYPT_ROUNDS=12，CPU 密集），
                                             典型场景：用户反复登录、切账号
    chat        POST /chat/stream         流式对话。最重的一条链路：
                                             识别 → 营养 → 推荐（本地 RAG + 图谱）→ 重排 → 出报告
    recommend   GET  /kg/ask              图谱多跳推理。轻量但真实碰 Neo4j，
                                             还能顺带量出阶段 5 缓存的命中率影响

跑之前必须满足的条件（不满足的话，测出来的数字是废的）
------------------------------------------------------
    ① 服务端 MOCK_LLM=true        不打真实大模型，见 app_my/core/mock_llm.py
    ② 服务端限流阈值调高          RATE_LIMIT_PER_MINUTE / RATE_LIMIT_USER_PER_MINUTE
                                  默认 60/min、20/min，压测会直接吃到 429
    ③ 清掉当天配额计数            free 套餐 chat_daily 上限 50 次，压测几十秒就打满
    ④ Kong 网关限流调高（只压目标 B 时）  chat 默认 120/min = 2 QPS
    这四条在本阶段操作手册里都有对应步骤与验证命令。

用法（完整命令见操作手册，这里只给最常敲的两条）
------------------------------------------------
    # 压单体（Git Bash）
    MOCK_LLM=true RATE_LIMIT_PER_MINUTE=1000000 RATE_LIMIT_USER_PER_MINUTE=1000000 \
      ./.venv3/Scripts/python.exe -m uvicorn main:app --port 9002

    ./.venv3/Scripts/python.exe -m locust -f benchmarks/locustfile.py \
      --headless --host http://127.0.0.1:9002 --users 20 --spawn-rate 5 \
      --run-time 90s --csv reports/bench_monolith
"""
import os
import random
import uuid

from locust import HttpUser, between, events, task

# ============================================================
# 1. 压测参数（都可以用环境变量覆盖，不用改代码）
# ============================================================

# 图谱问答的两个入参池。故意用"多个取值"而不是固定一个：
# /kg/ask 上挂了阶段 5 的 10 分钟缓存（cached(ttl=600)），只压一个固定组合的话，
# 第一个请求之后全命中缓存，测出来的 QPS 是"Redis 返回"的 QPS，
# 根本反映不出 Neo4j 的能力。用 10×3=30 种组合，缓存命中率才接近真实使用。
INGREDIENT_POOL = [
    "土豆", "西红柿", "鸡蛋", "鸡胸肉", "西兰花",
    "牛肉", "豆腐", "虾", "黄瓜", "茄子",
]
CONDITION_POOL = ["糖尿病", "痛风", "高血压"]

# 对话场景的用户输入池。刻意混合了长短句和"详细/分析"这类信号词，
# 让阶段 2 的智能路由真的在 lite/standard 档之间切换（压测要覆盖真实分支，不是只压一条路）。
MESSAGE_POOL = [
    "我手里有西红柿、鸡蛋和土豆，能做什么菜？",
    "帮我分析一下这些食材的营养搭配",
    "推荐三个适合控糖的菜谱",
    "中午随便吃点啥",
    "鸡胸肉和西兰花怎么做好吃，详细说一下做法",
    "我减脂期，这些食材怎么搭配",
]

# 虚拟用户等待时间（秒）。取 1~2s 而不是 0，
# 模拟真人"看完上一条再发下一条"的节奏；设 0 是闭压力测（会把服务打满，只适合找极限）。
WAIT_MIN = float(os.getenv("BENCH_WAIT_MIN", "1"))
WAIT_MAX = float(os.getenv("BENCH_WAIT_MAX", "2"))

# 请求超时。chat 走完整链路（含本地 RAG 和图谱查询），默认 60s 足够，
# 但设长一点是为了"宁可慢也别算成失败"——超时会被 Locust 记成错误，虚高错误率最难看。
HTTP_TIMEOUT = float(os.getenv("BENCH_TIMEOUT", "60"))


# ============================================================
# 2. 虚拟用户
# ============================================================
class BenchUser(HttpUser):
    """
    一个虚拟用户 = 一个虚拟的人。

    on_start 在"这个人刚进场"时跑一次：注册一个专属账号并登录，拿到 token。
    为什么每人都注册而不是共用一个账号：
        · 用户名有唯一约束，共用会在并发注册时互相撞
        · 真实场景本来就是不同的人登录不同的账号
        · 附带好处：登录场景压的是"多个不同账号的密码校验"，
          比同一个账号反复校验更接近真实的 CPU 负载（bcrypt 有内存硬开销，不能被"缓存命中"稀释）
    """

    # 两次请求之间的停顿。所有 User 类都能通过这个属性调整施压节奏。
    wait_time = between(WAIT_MIN, WAIT_MAX)

    def on_start(self):
        """进场准备：注册 + 登录，拿到后面所有请求要用的 token。"""
        _live["now"] += 1
        if _live["now"] > _live["peak"]:
            _live["peak"] = _live["now"]

        # 每个 VU 一个唯一用户名。uuid 前 8 位足够唯一，又不会把数据库撑大。
        self.username = "bench_" + uuid.uuid4().hex[:10]
        self.password = "Bench@12345"          # 满足 schemas/auth.py 里 min_length=8
        self.token = ""

        # name= 是"统计归类名"。不写的话 Locust 会按真实 URL 聚合，
        # 而 /kg/ask?ingredient=土豆&condition=糖尿病 每个请求的 URL 都不一样
        # → 统计表里会出现几十行、每行一次请求，没法看。写死一个 name 就聚成一类。
        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/register", json=payload,
                              name="/auth/register [准备]", catch_response=True) as r:
            # 409 = 用户名已存在（同一用户名基本不可能，但网络重试可能撞上）→ 不算失败
            if r.status_code == 409:
                pass
            elif r.status_code not in (200, 201):
                r.failure(f"准备阶段注册失败 HTTP {r.status_code}")

        with self.client.post("/auth/login", json=payload,
                              name="/auth/login [准备]", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"准备阶段登录失败 HTTP {r.status_code}")
            else:
                self.token = r.json().get("access_token", "")

    def on_stop(self):
        """离场：把在线计数减回来（保持峰值统计准确）。"""
        _live["now"] -= 1

    def _headers(self):
        """统一带上 Authorization 头。所有受保护接口都要它（无 token 直接 401）。"""
        return {"Authorization": f"Bearer {self.token}"}

    # ---------------- 场景 1：登录 ----------------
    @task(3)
    def scenario_login(self):
        """
        压 POST /auth/login。

        权重 3：这个场景故意用**已注册好的本账号**再登录一次，
        目的是让 bcrypt 反复做密码校验（BCRYPT_ROUNDS=12，CPU 密集型），
        从而量出"CPU 被密码哈希吃掉多少"。真实生产里登录也是 CPU 瓶颈大户。
        """
        payload = {"username": self.username, "password": self.password}
        with self.client.post("/auth/login", json=payload, name="/auth/login",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                # 401 在这里就是限流/配额打满了，属于压测配置问题，要在报告里写清楚而不是当"业务错误"
                r.failure(f"登录失败 HTTP {r.status_code}")

    # ---------------- 场景 2：对话（完整链路） ----------------
    @task(2)
    def scenario_chat(self):
        """
        压 POST /chat/stream（流式对话）。

        为什么权重最低（2）：这是全项目最重的一条链路，一次请求要串五个节点，
        还碰本地向量检索和知识图谱。它决定的是"用户感知到的响应时间"，
        不是"系统吞吐"。两种指标都要，就靠它 + recommend 两个场景互补。
        """
        payload = {
            "message": random.choice(MESSAGE_POOL),
            "thread_id": "bench_" + uuid.uuid4().hex[:8],   # 每次新会话，避免历史串味
            "user_id": None,          # 传 null = 按访客处理，不查用户画像（少一次 DB 查询）
        }
        with self.client.post("/chat/stream", json=payload, name="/chat/stream",
                              headers=self._headers(), catch_response=True,
                              timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"对话失败 HTTP {r.status_code}")
            else:
                # 🔴 不要检查 "data:" 这种 SSE 帧头！本项目的 /chat/stream 虽然
                # Content-Type 写的是 text/event-stream，但 coordinator 里是直接
                # `yield content`（纯文本），并没有按 SSE 协议包一层 data: 前缀。
                # 压测 v1 的脚本在这里判过 "data:"，结果 100% 请求被判失败、
                # 失败率直接冲到 10%+，白白浪费一轮压测。
                # 这里只判断"有没有内容吐出来"，这才是链路通没通的真实信号。
                if not (r.text or "").strip():
                    r.failure("对话返回空正文（链路没有产出内容）")

    # ---------------- 场景 3：图谱推荐 ----------------
    @task(5)
    def scenario_recommend(self):
        """
        压 GET /kg/ask（知识图谱多跳推理）。

        权重最高（5）：它最轻，用它把"架构本身的极限 QPS"顶出来。
        对话场景的 QPS 受 LLM 和 RAG 拖累，不能代表架构吞吐，
        这两个数字放一起看才有意义（一个测上限，一个测真实体验）。
        """
        ingredient = random.choice(INGREDIENT_POOL)
        condition = random.choice(CONDITION_POOL)
        with self.client.get("/kg/ask", params={"ingredient": ingredient, "condition": condition},
                             name="/kg/ask", headers=self._headers(), catch_response=True,
                             timeout=HTTP_TIMEOUT) as r:
            if r.status_code != 200:
                r.failure(f"图谱问答失败 HTTP {r.status_code}")


# ============================================================
# 3. 跑完自动打印一张"场景 × 目标"对照表
# ============================================================
# 为什么要自己打印一遍，而不直接看 Locust 自带表格：
#   ① 自带表格里 `[准备]` 的请求（注册/首次登录）混在里面，会把成功率拉低
#   ② 压测完真正要写进报告的是"P99 和失败数"两个数，自带表要人眼找
#   ③ 打印时带上目标名，复制进报告时不会搞不清这张表是哪一轮的

# 峰值并发数。locust 2.32 的 StatsEntry 上**没有** num_users 属性，
# 退出时 runner 也已经被回收（读 environment.runner.user_count 只会拿到 0），
# 所以自己数一遍：每个虚拟用户进场 +1、离场 -1，记住过程中的最大值。
#
# 为什么不在 on_start 里用 event 钩子去记：
#   locust 的事件名没有 events.user_started（只有 init/start/stop/quitting/request 等），
#   写错一个字母就是 AttributeError，整个文件加载失败、压测根本起不来。
#   而且 on_start 是同步执行的（locust 用 gevent 协作式调度，不会在这里被打断），
#   所以加减计数不存在竞态，最朴素的做法反而最稳。
_live = {"now": 0, "peak": 0}


def _rps(entry) -> float:
    """
    算这个场景的实际吞吐量（请求/秒）。

    🔴 locust 2.32 的 StatsEntry 上没有 total_rps 属性了（老版本才有），
    也没有 total_time。只有 total_response_time（耗时总和，毫秒）、
    start_time 和 last_request_timestamp（都是 time.time() 的秒级浮点）。
    所以 RPS 只能自己按"请求数 ÷ 这批请求跨越的秒数"算：
        第一次请求记下 start_time，最后一次请求的时间是 last_request_timestamp。
    注意分母用 last - start 而不是整轮时长：
    虚拟用户是陆续发请求的，首尾之间才是真实有请求的时间窗。
    """
    span = float(getattr(entry, "last_request_timestamp", 0) or 0) - float(getattr(entry, "start_time", 0) or 0)
    if span <= 0:
        return 0.0
    return entry.num_requests / span


@events.quitting.add_listener
def _print_bench_summary(environment, **_kwargs):
    """压测进程退出时触发，把关键指标打成一排，方便直接粘进报告。"""
    # 🔴 整个函数体必须包在 try 里。locust 对事件监听器里抛出的异常只是记一条日志，
    #    **不会**让压测失败——于是表现是"压测跑完了、CSV 也生成了，但屏幕上什么都没有"，
    #    人只会怀疑是不是自己命令敲错了。
    #    阶段 10 开发时就因为写了一个 locust 2.32 里不存在的属性，连续三轮压测白跑。
    #    包一层 try，任何字段名变化都会变成屏幕上的一行报错，而不是静默消失。
    try:
        _print_bench_summary_inner(environment)
    except Exception as exc:                       # noqa: BLE001 —— 这里就是要兜住一切
        print("")
        print("=" * 96)
        print(f"BENCH SUMMARY 生成失败：{type(exc).__name__}: {exc}")
        print("（压测数据本身没丢，看同目录下的 *_stats.csv 即可；这条报错请反馈以修脚本）")
        print("=" * 96)


def _print_bench_summary_inner(environment):
    stats = environment.stats
    host = str(environment.host or "")
    target = host.rsplit(":", 1)[-1].strip("/") or "unknown"

    # 🔴 取单条统计必须同时给"显示名 + HTTP 方法"：stats.get(name, method)。
    #    只传一个参数会返回空的 Entry（num_requests=0），表里场景行会全部消失。
    #    名字里带 " [准备]" 后缀的（注册/首次登录）是每个 VU 的进场开销，不是被测场景，不列进表。
    scenarios = (
        ("/auth/login", "POST"),
        ("/chat/stream", "POST"),
        ("/kg/ask", "GET"),
    )

    print("")
    print("=" * 96)
    peak = _live["peak"]
    print(f"BENCH SUMMARY  target=:{target}  peak_users={peak}"
          f"  total={stats.total.num_requests}  failures={stats.total.num_failures}")
    print("-" * 96)
    print(f"{'场景':<16}{'请求数':>9}{'失败':>7}{'失败率':>9}{'平均ms':>10}{'P50ms':>9}{'P95ms':>9}{'P99ms':>9}{'RPS':>8}")
    print("-" * 96)

    for name, method in scenarios:
        entry = stats.get(name, method)
        if entry.num_requests == 0:
            print(f"{name:<16}{'（本轮未执行）':>9}")
            continue
        fail_rate = entry.num_failures / entry.num_requests * 100
        print(f"{name:<16}{entry.num_requests:>9}{entry.num_failures:>7}{fail_rate:>8.1f}%"
              f"{entry.avg_response_time:>10.0f}"
              f"{entry.get_response_time_percentile(0.50):>9.0f}"
              f"{entry.get_response_time_percentile(0.95):>9.0f}"
              f"{entry.get_response_time_percentile(0.99):>9.0f}"
              f"{_rps(entry):>8.1f}")

    total = stats.total
    if total.num_requests:
        print("-" * 96)
        print(f"{'TOTAL':<16}{total.num_requests:>9}{total.num_failures:>7}"
              f"{total.num_failures / total.num_requests * 100:>8.1f}%"
              f"{total.avg_response_time:>10.0f}"
              f"{total.get_response_time_percentile(0.50):>9.0f}"
              f"{total.get_response_time_percentile(0.95):>9.0f}"
              f"{total.get_response_time_percentile(0.99):>9.0f}"
              f"{_rps(total):>8.1f}")
    print("=" * 96)