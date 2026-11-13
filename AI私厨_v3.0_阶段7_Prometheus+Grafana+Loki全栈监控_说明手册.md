# AI 私厨 v3.0 · 阶段 7：Prometheus + Grafana + Loki 全栈可观测（新增内容说明手册）

> **本手册定位**：全项目**唯一一处逐行代码解释**——讲清楚阶段 7 的每一行"在做什么、为什么这么写、每个参数什么意思"。操作步骤请看操作手册（照着做），本手册只负责"看懂为什么"，两者绝不重复。
> 风格约定：**代码行尾加简洁中文注释**（不加序号）；不编造真实数据示例。
> 🟢 本手册配套的**Prometheus 指标定义 + Loki 标签提取 + AlertManager 规则数学**已在临时目录实测（8 项断言全过）；5 个容器在你机器上由 `verify_stage7.py` 验证。

---

## 目录

> 🧭 **本手册章节已按《操作手册》的执行顺序重排**（先基础设施 → 再代码 → 再展示 → 再告警 → 最后测试），
> 每章开头都标了"对应操作手册第几节"，两份手册可以对照着读。

- [一、本阶段在做什么（一句话与全景图）](#一本阶段在做什么一句话与全景图)
- [二、新出现的专业名词（先看这张表再读代码）](#二新出现的专业名词先看这张表再读代码)
- [三、为什么是这套可观测栈：现状的三个真空](#三为什么是这套可观测栈现状的三个真空)
- [四、Prometheus 数据模型与抓取原理](#四prometheus-数据模型与抓取原理)
- [五、5 个容器与 6 个配置文件（含 Loki + Promtail）](#五5-个容器与-6-个配置文件含-loki--promtail) —— 对应操作手册**七、八节**
- [六、metrics.py 逐行解释](#六metricspy-逐行解释) —— 对应操作手册**第九节**
- [七、middleware/metrics.py 逐行解释](#七middlewaremetricspy-逐行解释) —— 对应操作手册**第十节**
- [八、token_billing 改造 与 main.py 接入](#八token_billing-改造-与-mainpy-接入) —— 对应操作手册**十一、十二节**
- [九、Grafana 仪表盘 JSON 字段含义](#九grafana-仪表盘-json-字段含义) —— 对应操作手册**第十三节**
- [十、AlertManager 规则数学与 PromQL 详解](#十alertmanager-规则数学与-promql-详解) —— 对应操作手册**第十四节**
- [十一、测试设计解释](#十一测试设计解释) —— 对应操作手册**第十五节**
- [十二、常见疑问](#十二常见疑问)
- [附录 A：本阶段一句话解决与价值](#附录-a本阶段一句话解决与价值)
- [附录 B：4 个仪表盘 JSON 逐面板解释（按面板说人话）](#附录-b4-个仪表盘-json-逐面板解释按面板说人话)

**顺序对照表**（两份手册怎么对应着读）：

| 执行顺序 | 操作手册 | 说明手册（本手册） |
|---|---|---|
| 1 | 七、5 个容器 / 八、6 个配置文件 | **五**、容器与配置文件 |
| 2 | 九、metrics.py | **六**、metrics.py 逐行 |
| 3 | 十、middleware/metrics.py | **七**、中间件逐行 |
| 4 | 十一、Token 成本接入 / 十二、main.py 接入 | **八**、token_billing 与 main.py |
| 5 | 十三、仪表盘 JSON | **九**、仪表盘 JSON |
| 6 | 十四、告警规则 | **十**、AlertManager 规则数学 |
| 7 | 十五、单元测试 | **十一**、测试设计 |

> 🟡 两份手册的**编号不必相同**——操作手册按"动手顺序"编号（多了一~六的准备章节），
> 说明手册按"理解顺序"编号。重要的是**章的先后次序一致**，上表已经逐条对齐。

---


## 一、本阶段在做什么（一句话与全景图）

**一句话**：在阶段 1~6 的代码里**插两根温度计**（`prometheus_client` 客户端 + Loki JSON 日志落档），再**装两块仪表盘**（Grafana 看 Prometheus 指标 + Loki 日志），最后**接一根电话线**（AlertManager 告警）——给阶段 8 微服务拆分装上"监控和告警"，拆完之后能立刻验证拆分收益。

```text
                       ┌─────────── 用户 / 运维 ───────────┐
                       │                                    │
                       ▼                                    ▼
                ┌─────────────┐                     ┌──────────────┐
                │   Grafana   │  拉模式抓指标        │ AlertManager │  规则触发
                │  统一面板   │◀─── Prometheus ◀─── │    .alert告警 │
                └──────┬──────┘                     └──────────────┘
                       │                                    ▲
                       │ LogQL 查日志                       │ 评估告警
                       ▼                                    │
                ┌─────────────┐                             │
                │   Promtail   │──日志推送──▶┌──────────┐    │
                │ (docker 读)  │             │   Loki   │    │
                └─────────────┘             └──────────┘    │
                       │                                       │
                       └─────── FastAPI 后端 ────────────────┘
                              MetricsMiddleware
                              ├─ QPS / 延迟 / 错误率
                              └─ token_billing → cost_inc
```

为什么需要仪表盘——用一个真实例子感受：

```text
事故现场："用户说对话报错了"
v3.0 阶段 7 之前：
  - 后端日志 grep → 找不到（INFO 只在 access log）
  - /chat/stream 5xx 看不出来（前端只接"网络异常）
  - 成本涨没涨不知道（billing 页要刷新看）

v3.0 阶段 7 之后：
  - Grafana 错误面板点开 → 看到 5xx 突增
  - 点 trace_id → Loki 直接定位到那条 ERROR 日志
  - AlertManager 已发告警 → "5xx 错误率超 5%"
  - 同时看 token 成本 → 没影响，所以是租户路由的问题
```

---


## 二、新出现的专业名词（先看这张表再读代码）

| 名词 | 人话解释 | 在本阶段的角色 |
|---|---|---|
| **可观测性（Observability）** | 不仅"知道出错了"，还能**"知道为什么出错、出在哪"**——靠**指标**（什么变了）、**日志**（具体哪一句）、**trace**（整条链路）三种数据 | 阶段 7 落指标 + 日志 + 告警；trace 用 LangSmith（云端）凑齐"三件套" |
| **指标（Metric）** | 数字随时间变化的曲线——`温度计`、`流量计` | Prometheus 抓到的 Counter / Histogram / Gauge |
| **日志（Log）** | 某时某刻发生的具体事件——`病历本` | Loki 存的 JSON 日志 |
| **追踪（Trace）** | 一条请求从进入到返回的完整路径——`出行轨迹` | LangSmith 云端 trace（已存在） |
| **Counter（计数器）** | 单调递增的数字——`汽车里程表`，**只能加不会减** | `http_requests_total` / `llm_tokens_total` / `llm_cost_cny_total` |
| **Gauge（仪表）** | 可增可减的瞬时值——`车速表`、`温度计` | `llm_quota_used_ratio`（租户配额使用率） |
| **Histogram（直方图）** | 把"数值的分布"切成桶——`按身高分组的统计`；每个桶是 Counter | `http_request_duration_seconds`（按耗时桶分组） |
| **分位数（Quantile）** | 一组数排好序后某位置的数——P99 = 排第 99% 位的数 | Histogram 配合 `histogram_quantile()` 函数算 P50/P95/P99 |
| **Label（标签）** | 给指标加"分组键"——key（什么键）/ val（"花哨"）。**标签基数不能爆**（key 总数有限） | 我们的 `method` / `status` / `tenant_id` / `path` 都是 label |
| **指标基数爆炸** | 当 label 的不同组合太多，Prometheus 内存炸——比如把 `用户_id` 当 label | 阶段 5 缓存 key 用 namespace、hash 不用 `user_id` 是同问题 |
| **Pull（拉模式）** | Prometheus 主动去"问"被监控方要指标——`海关查账` | 本阶段用这种；vs Pushgateway 的"被监控方主动推" |
| **PromQL** | Prometheus 的查询语言——SQL 时序风格的聚合 / 过滤 | `rate(http_requests_total[1m])` 这种 |
| **/metrics 端点** | 应用以 text/plain 文本格式暴露指标的 HTTP 接口 | 后端 `:9002/metrics` |
| **scrape_interval** | 多久拉一次——太短数据库压力大，太长曲线粗糙 | 本项目 `5s`（个人项目，资源够） |
| **scrape_timeout** | 单次拉取多久超期——后端慢就会 timeout | `3s`；太短会让 scrape 失败 |
| **label 高基数问题** | label 取值太多——比如把 `用户_id`（百万级）当 label | 状态码归 2xx/4xx/5xx、路径用 FastAPI route pattern 都是为了控基数 |
| **Grafana** | 指标的"显示大屏"——`仪表盘` | 把 Prometheus / Loki 的数据可视化 |
| **Provisioning** | Grafana 启动时自动加载配置——`自动导入仪表盘` | 阶段 7 用文件 provisioning，不用手动导入 |
| **Loki** | Grafana 实验室的日志存储——`专门存日志的数据库` | 与 Prometheus 同源，PromQL → LogQL |
| **LogQL** | Loki 的查询语言——像 grep + SQL | `{job="dashboard} |= "level=ERROR"` |
| **Promtail** | Loki 的"日志收集器"——`日志传送带` | 读 docker daemon 推送到 Loki |
| **AlertManager** | Prometheus 的"电话线"——触发后通知人 | 本项目写到文件 + 4 条规则 |
| **告警规则（Alert rule）** | PromQL 表达式 + 阈值 + 持续时间 → 满足就告警 | `alerts.yml` 里的 4 条规则 |
| **for 持续时间** | 规则触达后持续多久才真告警——避免抖动 | `for: 2m` = 触发后 2 分钟还成立才算 |
| **Webhook** | "告警来了一按按钮就发到指定 URL"的协议 | 企业微信 / 钉钉 / Slack 都用它接 |
| **silence（静默）** | 临时"关掉某条告警"——比如在做升级 | AlertManager UI 右侧栏 |
| **灰度发布（Canary）** | 新功能先放给一部分流量试——阶段 6 已讲 | 阶段 7 没直接用，面试时同概念 |
| **失败降级 / fallback** | 组件不可用时换备用方案——`备用轮胎` | metrics 上报失败不影响主记账（第十一节） |

---


## 三、为什么是这套可观测栈：现状的三个真空

阶段 6 收官后，系统的实际状况：

| 真空 | 表现 | 阶段 7 怎么补 |
|---|---|---|
| **指标真空** | QPS、延迟、错误率是"算出来的还是"估出来的——`压测时才知道几分钟前出过事` | Prometheus 抓 4 类核心指标，Grafana 实时看 |
| **日志真空** | 日志在 docker daemon 里 / 文件里——`找到时往往事故现场已被覆盖` | Loki + Promtail 自动入库存 7 天，Grafana 同界面查询 |
| **告警真空** | 出了事靠"用户投诉 / 自己看到"——`5xx 都过半小时才发现` | AlertManager 4 条规则，5xx/30 等到阈值就告警 |

**为什么 Prometheus 是默认选型**：

```text
+---------------------+-----------------+-----------------------+
|       维度          |    Prometheus    |     OpenTelemetry     |
+---------------------+-----------------+-----------------------+
| 拉 vs 推            | 拉（监控方主动） | 推（被监控方主动）    |
| 存储                | 本地 TSDB        | 后端转发（Jaeger等）   |
| 多维度查询          | PromQL（强）     | 需配合 trace 后端     |
| 生态                | CNCF 毕业项目     | CNCF 沙箱            |
| 适合                | 指标+告警        | 多语言 trace        |
+---------------------+-----------------+-----------------------+
```

本项目选 Prometheus：① 个人项目跑得动；③ Grafana 同源 Prometheus + Loki；③ 阶段 8 拆分后立刻能用上。

> 🟡 诚实红线：**不写"支撑亿级指标"**——本机单机 5 秒一次抓数据，撑不撑得住说"业务跑过 1 年"是诚实的。

---


## 四、Prometheus 数据模型与抓取原理

### 4.1 数据模型

```text
一个指标 = 一个 (metric_name + label_keys + tuples of label_values) + 一个数字 + 一个时间戳
```

举例：

```text
http_requests_total{method="GET", status="2xx", tenant_id="1", path="/health"} 1234 @ 1730000000000
```

意思是：在时间戳 `1730000000000`，`GET /health` 在第 1 个租户有 `1234` 次访问。

### 4.2 抓取原理

```text
Prometheus 服务器
   │
   │  HTTP GET http://host.docker.internal:9002/metrics
   │  (每 5s 一次)
   ▼
后端应用
   │
   │  generate_latest() → text/plain
   │
   ▼
Prometheus 解析 + 写 TSDB（时段数据库）
   │
   │  后台跑 alert rules
   ▼
触发 → AlertManager → 通知
```

**为什么是拉而不是推**：

| 拉（Pull） | 推（Push） |
|---|---|
| 监控方主动——`海关查账` | 被监控方主动——`主动报账` |
| **被监控方不需要知道 Prometheus 在哪** | 需要知道 + 配 endpoint |
| Prometheus 知道自己失败不成功 | 不知道上游接没接住 |
| 多副本切换方便 | 多副本端点要重新配 |

个人项目 + 容器编排优先 → 拉模式是默认选择。

---


## 五、5 个容器与 6 个配置文件（含 Loki + Promtail）

> 🧭 **本节对应《操作手册》第七节（5 个容器）+ 第八节（6 个配置文件）**。
> 操作手册负责「照着做」，本手册负责「看懂为什么」——下面先讲这 5 个容器各自干什么、彼此怎么连，再逐项解释配置。

### 5.0 先看清：5 个容器到底谁依赖谁

```text
                    ┌──────────────┐
                    │   Grafana    │  3300  ← 你用浏览器看的那块屏
                    │  （展示层）   │
                    └──────┬───────┘
                   读指标  │  读日志
              ┌───────────┴───────────┐
              ▼                       ▼
      ┌──────────────┐        ┌──────────────┐
      │  Prometheus  │ 9090   │     Loki     │ 3100
      │ （指标数据库）│        │ （日志数据库）│
      └──────┬───────┘        └──────▲───────┘
             │ 每 5 秒主动拉          │ 推送
             ▼                       │
      ┌──────────────┐        ┌──────┴───────┐
      │  后端 :9002  │        │   Promtail   │
      │  /metrics    │        │  （日志采集） │
      └──────────────┘        └──────▲───────┘
             │                       │ 读容器 stdout
             │ 告警规则命中          │
             ▼                       │
      ┌──────────────┐        ┌──────┴────────────────┐
      │ AlertManager │ 9093   │ /var/lib/docker/...   │
      │  （发通知）   │        │  *-json.log（含后端）  │
      └──────────────┘        └───────────────────────┘
```

**一句话记住**：指标走**拉**（Prometheus 主动来取），日志走**推**（Promtail 主动送去）。
这是两套完全相反的数据流向，也是很多新手搞混 Prometheus 和 Loki 的根源。

### 5.0.1 5 个容器各管什么（人话版）

| 容器 | 端口 | 一句人话 | 没有它会怎样 |
|---|---|---|---|
| **Prometheus** | 9090 | 指标数据库，每 5 秒去后端 `/metrics` **拉**一次，存成时间序列 | 指标没地方存，Grafana 一片空白 |
| **Grafana** | 3300 | 画图的屏，从 Prometheus 取指标、从 Loki 取日志，**只展示不存储** | 数据都有，但你看不见 |
| **AlertManager** | 9093 | 告警收发室：Prometheus 说"规则命中了"，它负责去重、分组、发通知 | 出问题没人知道 |
| **Loki** | 3100 | 日志数据库，按**标签**存日志（只索引标签，不索引正文 → 省资源） | 只能 `docker logs` 一条条翻 |
| **Promtail** | 无 | 采集器，盯着 Docker 的 `*-json.log`，有新日志就**推**给 Loki | Loki 里什么都没有 |

> 🟡 **Promtail 没有对外端口**——它是"只干活不露面"的角色，所以操作手册第八节步骤 12 验证端口时**不检查它**，
> 只看 `docker ps` 里是不是 `Up`。这是新手常问的"为什么 5 个容器只验 4 个端口"。

### 5.0.2 6 个配置文件谁读谁

| 配置文件 | 被谁读 | 作用 |
|---|---|---|
| `docker/prometheus/prometheus.yml` | Prometheus | 定义"去哪儿拉、多久拉一次" + 引用告警规则文件 |
| `docker/prometheus/alerts.yml` | Prometheus（被上者引用） | 4 条告警规则的判断条件（PromQL） |
| `docker/alertmanager/alertmanager.yml` | AlertManager | 告警来了怎么路由、怎么去重、发到哪 |
| `docker/loki/loki-config.yaml` | Loki | 日志存哪、存多久、用什么索引 |
| `docker/promtail/promtail-config.yaml` | Promtail | 从哪读日志、怎么打标签、推送给谁 |
| `docker/grafana/provisioning/**` | Grafana | 启动时**自动**建数据源 + 自动加载仪表盘（不用手动点） |

> 🟡 前 5 份配置在《操作手册》第八节里**每份都带了行尾中文注释**，照抄即可，本手册不重复。
> 下面 5.1~5.3 只挑**最容易搞混、也最容易配错**的 Loki + Promtail 展开讲——尤其是那个让 Loki 无限重启的
> `object_store` 字段（本项目真踩过）。

### 5.1 数据流

```text
FastAPI 后端
   │
   │  setup_logging() 设置 JSON formatter
   │
   ▼
stdout （每个容器一行 JSON）
   │
   │  Docker daemon 收容器 stdout
   │
   ▼
/var/lib/docker/containers/<container_id>/<container_id>-json.log
   │
   │  Promtail 读这个路径
   │
   ▼
Promtail pipeline_stages: docker:{} + json:{}
   │
   │  提取 container_name / level / logger / msg
   │  转成 Loki label
   │
   ▼
Loki 接收 → 存储到 /loki/chunks
   │
   │  LogQL 查询
   ▼
Grafana 面板显示
```

### 5.2 Promtail 配置关键字段

```yaml
scrape_configs:                                                          # 采集配置块
  - job_name: docker                                                      # job 名字 必填项
    static_configs:                                                       # 静态目标列表
      - targets: [localhost]                                              # 假目标——本身不连
        labels:                                                           # 全局 label
          job: docker                                                     # job 标签 用于查询
          __path__: /var/lib/docker/containers/*/*log                     # 文件路径——Loki 约定的反查
    pipeline_stages:                                                       # 处理流水线
      - docker: {}                                                        # 自动解析 docker JSON 字段
      - match:                                                            # 匹配条件
          selector: '{job="docker"}'                                      # 选择器：所有 docker job 的日志
          stages:                                                         # 子层流水线
            - json:                                                       # JSON 解析
                expressions:                                              # 输入字段映射
                  level: level                                            # JSON 里的 level 字段 → level label
                  logger: logger                                          # logger → logger label
                  msg: msg                                                # msg → msg label
                  trace_id: trace_id                                      # trace_id → trace_id label
            - labels:                                                    # 把提取的字段设为 label
                level:                                                    # level 作为 label 出现
                logger:                                                    # logger 作为 label
                trace_id:                                                  # trace_id 作为 label
```

| 字段 | 在做什么 | 为什么这么写 |
|---|---|---|
| `__path__` | Loki 用它定位日志文件——`特殊下划线变量` | Loki Promtail 的约定 |
| `docker: {}` | 自动把 docker JSON 的 container_name / image / tag 提出来 | 镜像配置不同——配置裸写会丢失容器标签 |
| `pipeline_stages` | 多阶段处理——`工厂流水线` | 每阶段一功能：解析 → 提取 → 转换 |
| `json: {expressions: {level: level}}` | 把 JSON 里的 `level` 字段提取出来 | 我们的 JSON formatter 已经在日志里放了 level |
| `labels: {level: ...}` | 把提取字段变 label | Loki label 是"索引字段"，不能多否则爆 |

### 5.3 Loki 配置关键字段

```yaml
auth_enabled: false                                                       # 关闭鉴权——本机使用 不开集群
schema_config:                                                            # 配置 schema
  configs:                                                                # TSDB schema
    - from: 2024-01-01                                                    # 起始日期
      store: tsdb                                                         # 存储引擎：tsdb 索引（v13 schema）
      index:                                                                # 索引配置
        prefix: index_                                                    # 索引文件名前缀
        period: 24h                                                       # 每个索引 24h 一个文件
```

| 字段 | 在做什么 | 为什么这么写 |
|---|---|---|
| `store: tsdb` | Loki 2.0+ 的新型存储引擎 | 旧版 boltdb 已停。官方推荐 tsdb |
| `period: 24h` | 索引文件按天切——`每天一个 index` | 查询时按时间范围扫对应 index |

---


## 六、metrics.py 逐行解释

### 6.1 指标对象定义（4 + 1 类）

```python
from prometheus_client import Counter, Histogram, Gauge, REGISTRY as _PROM_REGISTRY  # 官方库的 3 种核心指标 + 全局注册表
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `Counter(...)` | 定义一个**单调递增**的指标——`里程表` | QPS / Token / 成本都是"只增不减"的累计量——用 Counter |
| `Histogram(...)` | 定义一个**分布**——`身高分布直方图` | 延迟是连续值，要按桶（0.1s/0.5s/1s/...）分组计数 |
| `Gauge(...)` | 定义一个**可增可减**的瞬时值——`温度计` | 配额使用率可能升也可能降（续费后回 0%） |

```python
HTTP_REQUESTS = Counter(                                              # 定义"HTTP 请求总数"指标对象
    "http_requests_total",                                              # 指标名（暴露给 Prometheus 的字段名）
    "HTTP 请求总数（按 method / status / tenant_id / path 拆）",       # 帮助文本（Grafana 里 hover 显示）
    labelnames=("method", "status", "tenant_id", "path"),              # 4 个 label key：方法/标签（方法/状态/租户/路径）
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `labelnames=("method", "status", "tenant_id", "path")` | 4 个 label 维度——`多维度统计的"行键"` | 4 个 label 组合：可以同时看"哪条路径 / 哪个租户 / 哪种状态码"的请求数 |
| 用**元组**不是列表 | label 名不可变 | Prometheus 内部用 dict，name 元组是关键字参数，hash + 结构安全 |

```python
HTTP_DURATION = Histogram(                                            # 定义"HTTP 请求延迟"直方图
    "http_request_duration_seconds",                                  # 指标名（`_seconds` 后缀是 Prometheus 约定）
    "HTTP 请求延迟（秒）",                                            # 帮助文本
    labelnames=("method", "tenant_id", "path"),                       # 3 个 label（不含 status：延迟不按状态分）
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),  # 11 个桶边界（秒）
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `_seconds` 后缀 | Prometheus 命名约定——`知道这是时间单位` | `histogram_quantile()` 自动把桶转成秒 |
| `buckets=(0.005, ..., 10.0)` | 11 个桶边界——`5ms ~ 10s` | web 请求 90% 都在 100ms 内、99% 在 1s 内；**桶切得越细 P99 越准，桶越多内存越大**——11 个是甜点 |
| 3 个 label 而不是 4 个 | 不按 status 拆——`延迟和状态码关系不大` | 4xx/5xx 延迟本身按 path 区分已 OK，省一个 label 节省存储 |

```python
LLM_TOKENS = Counter(                                                  # 定义"LLM token 消耗总数"指标
    "llm_tokens_total",                                                # 指标名
    "LLM token 消耗总数（按 model / direction 拆）",                   # 帮助文本
    labelnames=("model", "direction"),                                 # 2 个 label：模型 / 方向（输入/输出）
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `direction` label | 拆 / input 或 output | 输出 token 单价比输入贵 4 倍——**不分开没法算成本** |

```python
LLM_COST = Counter(                                                     # 定义"LLM 成本累计"指标
    "llm_cost_cny_total",                                              # 指标名（`_cny` 后缀是约定）
    "LLM 调用成本累计（元）",                                          # 帮助文本
    labelnames=("model",),                                             # 1 个 label：模型
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 不用 `tenant_id` label | 阶段 7 暂不拆租户成本 | 阶段 9 多租户 SaaS 时再加——**别提前**"凡是要" |
| 用 Counter 不用 Gauge | 成本是累计的，不会退 | 续费 / 退款由 billing 系统管，metrics 只管"计账合计" |

```python
LLM_QUOTA_RATIO = Gauge(                                               # 定义"租户配额使用率"瞬时值
    "llm_quota_used_ratio",                                            # 指标名
    "租户 LLM 配额使用率（0~1）",                                      # 帮助文本
    labelnames=("tenant_id",),                                         # 1 个 label：租户
)
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| Gauge 不是 Counter | 续费后会下降——`已用比例`会降 | 用 Gauge 才能描述"瞬时值" |
| 值范围 0~1 | 比例统一口径 | Grafana 配置 Y 轴 max=1 直接显示 0~100% |

### 6.2 埋点 helper 函数

```python
def http_inc(method: str, path: str, status_code: int, tenant_id: str = "anon") -> None:  # HTTP 埋点：QPS Counter + Duration Histogram 一次性记录
    """HTTP 埋点：QPS Counter + Duration Histogram 一次性记录。
    用一个 helper 把 4 个 label 的拼装集中起来——避免中间件里重复 + 拼错。"""
    status_bucket = (                                                  # ✅ 准备状态码标签值——状态码归 2xx/4xx/5xx 三类
        "2xx" if 200 <= status_code < 300                              # ✅ 200~299 → "2xx"
        else "4xx" if 400 <= status_code < 500                         # ✅ 400~499 → "4xx"
        else "5xx" if 500 <= status_code < 600                         # ✅ 500~599 → "5xx"
        else str(status_code)                                          # ✅ 其它（3xx 重定向）→ 原值（极少出现）
    )
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `status_bucket = "2xx"/"4xx"/"5xx"` | 把上百种 status code 归三类 | label 基数必须控制在百级别——**直接用 `201`、`404`、`502` 会让 label 100+ 种** |
| 3xx 单独返原值 | 重定向不常见，但偶有 304、308 | 完整度——不漏报 |

```python
    tenant_label = str(tenant_id) if tenant_id is not None else "anon"  # 租户标签准备：None 变 "anon"
    HTTP_REQUESTS.labels(method=method, status=status_bucket, tenant_id=tenant_label, path=path).inc()  # QPS Counter 自增 1
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `str(tenant_id) if tenant_id is not None else "anon"` | 没登录 / 没租户是 "anon" | Prometheus label 必须是字符串；None 会变成字符串 `"None"`（脏数据）|
| `.labels(...).inc()` | 把 4 个 label 拼成 key 查 chart 后自增 | prometheus_client 的标准姿势——`labels()` 拿到 chart，`.inc()` 改 chart |
| 不用 `inc(1)` 的显式参数 | `inc()` 默认是 1 | 99% 的请求只增 1，少量自定 2/3/0.5 时才传参 |

```python
def tokens_inc(model: str, direction: str, amount: int) -> None:        # Token 埋点：input / output 增量
    """Token 埋点：input / output 增量。"""
    LLM_TOKENS.labels(model=model or "unknown", direction=direction).inc(amount)  # 计 tokens 数 + token 数
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `model or "unknown"` | 模型名为空归 "unknown" | label 不能是空串——空串在 Grafana 里展示丑 |
| `inc(amount)` | 加 amount 个（不是 1） | tokens 一次不是 1 个——可能 200、5000 |

```python
def cost_inc(model: str, cny: float) -> None:                           # 成本埋点：累计（元）
    """成本埋点：累计（元）。"""
    LLM_COST.labels(model=model or "unknown").inc(cny)                  # 计成本 + 成本
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `inc(cny)` | 加 `cny` 元（float） | 单次成本是个小数值——0.001、0.012 |

```python
def quota_set(tenant_id: int, ratio: float) -> None:                    # 配额埋点：设置租户当前使用率
    """配额埋点：设置租户当前使用率。"""
    LLM_QUOTA_RATIO.labels(tenant_id=str(tenant_id)).set(ratio)        # 设 Gauge + 刻度
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `.set(ratio)` 不是 `.inc(ratio)` | Gauge 用 `set` 设值 | Counter 是单调增；Gauge 是变动值——API 不同 |

---


## 七、middleware/metrics.py 逐行解释

### 7.1 入口 dispatch

```python
import time                                                              # 导入时间模块——用于 perf_counter 高精度计时
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest       # 从工具注册表导入：最新指标文本格式生成器
from starlette.middleware.base import BaseHTTPMiddleware                 # 异步中间件基类
from starlette.requests import Request                                  # 请求对象
from starlette.responses import PlainTextResponse, Response             # 文本响应 + 通用响应
from app_my.core.config import settings                                 # 环境变量读取配置
from app_my.core.logging import logger, trace_id_var                     # 日志 + trace_id 上下文变量
```

```python
class PrometheusMiddleware(BaseHTTPMiddleware):                          # 自定义 HTTP 埋点中间件
    """HTTP 埋点中间件 + 暴露 /metrics 端点"""

    async def dispatch(self, request: Request, call_next):              # dispatch 入口（每条请求都走这里）
        path = request.url.path                                         # 取请求路径
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `BaseHTTPMiddleware` | starlette 的标准中间件基类 | 与项目现有中间件（rate_limit / quota / tenant）同一框架 |

```python
        if path == settings.PROMETHEUS_METRICS_PATH:                    # 如果访问的是 /metrics 端点
            return PlainTextResponse(_build_metrics_text(), media_type=CONTENT_TYPE_LATEST)  # 返回 text/plain 格式的指标文本
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 早 return | /metrics 不参与计数 | 否则 self-scrape 会污染数据——HTTP_REQUESTS 里会出现 `/metrics` 巨量 |
| `PlainTextResponse` 不是 `JSONResponse` | Prometheus 要 text/plain | Prometheus 0.0.4 文本格式是 `key{label=value,]* value` |
| `CONTENT_TYPE_LATEST` | 固定常量 `"text/plain; version=0.0.4; charset=utf-8"` | Prometheus 期望这个 Content-Type——否则报错 |

```python
        route = request.scope.get("route")                              # 从请求 scope 取 trip pattern
        path_label = getattr(route, "path", path) if route else path    # 用 pattern 不用真实 URL——避免高基数
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `request.scope.get("route")` | FastAPI 路由匹配后写入的"路径模式" | `/users/{user_id}` 这种；真实 URL `/users/456` 会让 label 基数百万 |
| `getattr(route, "path", path) if route else path` | 三元组：`route=空` → 用真实 URL；`route.path` 拿不到 → 用真实 URL | 实际路径请求从 401 之前没进路由栈，route=None——key 用 raw URL 作 fallback |
| 路径模式 vs 真实 URL | 模式基数有限（项目几十条路由） vs URL 千万级 | **label 高基数是 Prometheus 头号坑**——基线用模式几十~百 |

```python
        start = time.perf_counter()                                     # 高精度计时起点
        try:                                                            # 异常路径计 try：保证路由抛异常也能埋点 500
            response: Response = await call_next(request)               # 走下一层中间件 / 业务处理
        except Exception:                                                            # 路由抛异常
            cost_ms = (time.perf_counter() - start) * 1000               # 算耗时（毫秒）
            _handle_inc(request, path_label, 500, cost_ms)              # 埋点 500
            raise                                                        # 🚀 重新抛异常（关键 — 否则异常被吞）
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `time.perf_counter()` | 最高精度计时器 | `time.time()` 受系统时间调整；`perf_counter` 是单调时钟 |
| 乘 1000 | perf_counter 是秒，毫秒需要 * 1000 | 历史代码用 ms 比较多——延续习惯 |
| try/finally 的设计 | 异常路径也要埋 500 | 否则 500 永远记不到——**和之前"route_handler.py"设计同款** |

```python
        cost_ms = (time.perf_counter() - start) * 1000                   # 算耗时（毫秒）
        _handle_inc(request, path_label, response.status_code, cost_ms) # 埋点正常响应
        return response                                                  # 返回响应给上层中间件
```

### 7.2 公共埋点函数

```python
def _handle_inc(request: Request, path_label: str, status_code: int, cost_ms: float) -> None:  # 统一埋点：QPS Counter + Duration Histogram
    """统一埋点：QPS Counter + Duration Histogram"""
    from app_my.core.metrics import HTTP_DURATION                          # 避免循环引用
    tenant_id = getattr(request.state, "tenant_id", None)                # 从请求 state 拿租户 ID
    http_inc(method=request.method, path=path_label, status_code=status_code, tenant_id=tenant_id)  # QPS 自增
    HTTP_DURATION.labels(method=request.method, path=path_label, tenant_id=str(tenant_id or "anon")).observe(cost_ms / 1000)  # Histogram 观察耗时
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| 函数内 import | 延迟 import | 中间件和 metrics 互相引用会循环——延迟到函数内 import 避免循环 |
| `request.state.tenant_id` | 从 TenantContextMiddleware 写入 | 阶段 4 已落地——本阶段只读不写 |
| `cost_ms / 1000` | 毫秒转秒 | Histogram 的 `_seconds` 后缀约定单位是秒 |
| `tenant_id or "anon"` | None 变 "anon" | label 不能 None |

### 7.3 指标文本生成

```python
def _build_metrics_text() -> bytes:                                       # 生成 Prometheus text 导出格式
    """生成 Prometheus text 导出格式"""
    try:                                                                  # try
        return generate_latest()                                          # 调用官方库生成指标文本
        # ⚠️ generate_latest() 会将所有注册的指标序列化为 Prometheus text 格式
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `generate_latest()` | 序列化为 Prometheus 0.0.4 文本 | 这是 prometheus_client 库的核心函数 |
| try 包住 | generate_latest 抛异常不致命 | metrics 端点失败要让业务不受影响——返回空文本 |

---


## 八、token_billing 改造 与 main.py 接入（逐行解释）

> 🧭 **本节对应《操作手册》第十一节（Token 成本指标接入）+ 第十二节（main.py 接入）**。
> 目录里原本就有这一章，但正文漏写了——这次补齐。

### 8.1 为什么埋点要写进 `record()` 而不是别处

阶段 2 做多模型路由时，你已经有一个"每调一次大模型就记一笔账"的函数 `record()`：

```python
def record(model, input_tokens, output_tokens, ok=True):
```

它是**所有 LLM 调用的唯一收口**——不管走哪个模型、哪个路由，最后都要调它。
所以阶段 7 要统计 token 和成本，**最省事又最不会漏**的做法，就是在 `record()` 末尾追加一段上报，
而不是在每个调用点各写一遍（那会漏、也会改出 bug）。

### 8.2 `record()` 末尾新增的这段，逐行看

```python
    # ③ 阶段 7：metrics 上报（不影响原记账逻辑；失败则吞掉）
    try:
        from app_my.core.metrics import tokens_inc, cost_inc
        if ok:
            tokens_inc(model, "input", int(input_tokens or 0))
            tokens_inc(model, "output", int(output_tokens or 0))
            cost = estimate_cost_cny(model, int(input_tokens or 0), int(output_tokens or 0))
            if cost is not None:
                cost_inc(model, cost)
    except Exception:
        pass
```

| 行 | 在做什么 | 为什么这么写 |
|---|---|---|
| `# ③` 注释 | 标明这是第③段（①进程内账本 ②Redis 账本 ③metrics） | 三段并列，一眼看出各管什么 |
| `try:` 包住整段 | **监控绝不能拖垮业务** | 这是可观测的铁律：埋点出 bug，宁可丢一个指标，也不能让聊天接口 500 |
| `from ... import` 写在**函数内部** | 避免循环引用 | `metrics.py` 不 import 业务模块，反过来业务模块在用到时才 import 它——谁也不在加载时依赖谁 |
| `if ok:` | 只统计成功的调用 | 失败的调用（ok=False）在 ① 里已计到 `errors`，这里不重复计 token |
| `tokens_inc(model, "input", ...)` | 给 `llm_tokens_total{model, direction}` 加 N | `direction` 分 input/output，是因为**输入输出单价不同**，仪表盘要分开看 |
| `estimate_cost_cny(...)` | 按价目表算这一笔多少钱 | 复用阶段 2 已有的计价函数，不重复造轮子 |
| `if cost is not None:` | 价目表里没这个模型时返回 None | 未知模型不报错、也不记成本，静默跳过 |
| `except Exception: pass` | 吞掉所有异常 | 极端保守：宁可指标少一条，也不让记账函数抛错 |

> 🟡 **`except: pass` 一般是坏习惯**，但在这里是**刻意的**：监控属于旁路系统，它的失败不应该影响主链路。
> 同一套思路也用在 `QuotaMiddleware` 的 `quota_set` 上。

### 8.3 `main.py` 接入：中间件顺序为什么是"反的"

FastAPI 有个反直觉的规则：**`add_middleware()` 后注册的，反而更靠外层**。

```text
请求进来 →  CORS → TraceId → Metrics → Auth → Tenant → 限流 → 配额 → 路由函数
           （最外）                                              （最里）
```

所以你在 `main.py` 里看到的代码顺序是**从里往外写**的：

```python
app.add_middleware(QuotaMiddleware)              # 5. 配额（最里层）
app.add_middleware(RateLimitMiddleware)          # 4. 全局/IP 级限流
app.add_middleware(UserRateLimitMiddleware)      # 3. 用户级限流
app.add_middleware(TenantContextMiddleware)      # 2.5 租户上下文
app.add_middleware(AuthMiddleware)               # 2. JWT 鉴权
app.add_middleware(MetricsMiddleware)            # 1.5 阶段 7：HTTP 埋点 + /metrics（必须在 Auth 之外）
app.add_middleware(TraceIdMiddleware)            # 1. TraceID
app.add_middleware(CORSMiddleware, ...)          # 0. CORS（最后加 -> 最外层）
```

🔴 **最关键的一条**：`MetricsMiddleware` 必须写在 `AuthMiddleware` **之后**（这样它更靠外）。

原因：`/metrics` **不是一个路由**，而是写在 `MetricsMiddleware.dispatch()` 里的一个判断——

```python
if path == settings.PROMETHEUS_METRICS_PATH:
    return PlainTextResponse(_build_metrics_text(), media_type=CONTENT_TYPE_LATEST)
```

如果 Metrics 在 Auth **内侧**，请求会**先**被 Auth 拦下返回 401，这段判断永远轮不到执行 —— Prometheus 就一直报 401。
（本项目真踩过这个坑，是手册早期版本把顺序写错了。）

### 8.4 那为什么又不放到最外层？

```text
CORS(最外) → TraceId → Metrics → Auth ...
```

- **不放在 CORS 之外**：浏览器发的 OPTIONS 预检请求会被记两次（预检 + 真实请求），指标虚高；
- **放在 Auth / 限流之外**：被 401 拒绝、被 429 限流的请求**也计入指标** —— 这正是我们想要的，
  否则"错误率面板"永远看不到鉴权失败和限流拒绝，**监控就瞎了一只眼**。

### 8.5 一个容易想不通的点：在外层怎么读到 `tenant_id`？

`tenant_id` 是**内层**的 `TenantContextMiddleware` 写进 `request.state` 的，外层怎么读得到？

因为 Starlette 的 `request.state` 实际存在 `scope["state"]` 里，**整条中间件链共享同一个 scope 对象**。
所以外层中间件在 `call_next()` 返回**之后**再读，就能拿到内层写过的值：

```python
tenant_id = getattr(request.state, "tenant_id", None)
```

> 🟡 注意时序：必须在 `await call_next(request)` **之后**读，之前读是 None（内层还没执行）。

## 九、Grafana 仪表盘 JSON 字段含义

### 9.1 顶层结构

```json
{
  "title": "AI Chief · HTTP 概览",                                        // 仪表盘标题
  "uid": "ai_chief_http",                                                 // 唯一 ID——URL 用
  "schemaVersion": 39,                                                  // 仪表盘 schema 版本
  "refresh": "5s",                                                       // 自动刷新间隔
  "time": {"from": "now-1h", "to": "now"},                              // 默认时间范围
  "panels": [...],                                                       // 面板数组
  "tags": ["ai_chief", "stage7"]                                          // 标签——左侧栏过滤用
}
```

### 9.2 Panel 通用结构

```json
{
  "title": "QPS by path",                                                 // 面板标题
  "type": "timeseries",                                                   // 面板类型（timeseries / logs / stat / table）
  "datasource": {"type": "prometheus", "uid": "prometheus"},              // 数据源引用
  "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},                          // 网格定位（24 列网格）
  "targets": [{"expr": "sum by (path) (rate(http_requests_total[1m]))", "refId": "A"}],  // PromQL 查询
  "fieldConfig": {"defaults": {"unit": "ms"}}                            // 字段格式化（如单位）
}
```

### 9.3 4 个仪表盘的 PromQL 详解

#### HTTP 概览

```json
{"expr": "sum by (path) (rate(http_requests_total[1m]))"}                 # 每秒请求数按路径拆
```

- `rate(metric[1m])`：1 分钟内每秒的平均增量（Prometheus 自动算）
- `sum by (path)`：按 path 聚合求和——`保留维度、压缩其它`

#### Token 成本

```json
{"expr": "sum by (direction) (rate(llm_tokens_total[5m])) * 60"}         # 每分钟 token 数按方向拆
```

- `rate(...) * 60`：rate 是"每秒"——乘 60 表达"每分钟"——面试常问
- `sum by (direction)`：按 input/output 分开——两个方向的 token 单价不同

#### 错误日志

```json
{"expr": "{job=\"docker\"} |= \"level=ERROR\""}                          # Loki LogQL：找 ERROR 日志
```

- `{job="docker"}`：标签选择器
- `|= "level=ERROR"`：日志内容过滤——`含 ERROR 字样`

---


## 十、AlertManager 规则数学与 PromQL 详解

### 10.1 4 条规则

```yaml
      # 1) 5xx 错误率 > 5% 持续 2 分钟
      - alert: HighErrorRate
        expr: sum(rate(http_requests_total{status=~"5xx"}[5m])) /
              sum(rate(http_requests_total[5m])) > 0.05
        for: 2m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `http_requests_total{status=~"5xx"}` | label 选择器 `status` 匹配 `5xx` | 状态码已归 2xx/4xx/5xx——这里精确匹配 5xx |
| `[5m]` | 5 分钟滑动窗口 | 太短抖动，太长反应慢——5 分钟是平衡 |
| `rate(...[5m])` | 5 分钟内的平均每秒增量 | rate 是 Prometheus 的"标准求导"函数 |
| `> 0.05` | 5xx 占比超 5% | 5% 是经验阈值——超过就是"问题在持续" |
| `for: 2m` | 持续 2 分钟才真告警 | 避免抖动——一次 5xx 是网络抖动，连续 2 分钟 5xx 才是真问题 |

```yaml
      # 2) P99 延迟 > 3 秒持续 5 分钟
      - alert: HighP99Latency
        expr: histogram_quantile(0.99, sum by (path, le) (rate(http_request_duration_seconds_bucket[5m]))) > 3
        for: 5m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `histogram_quantile(0.99, ...)` | 从 Histogram 桶里插值算出 P99 | Histogram 不直接存分位数——要算 |
| `sum by (path, le)` | 按 path + le（桶上界）聚合 | `le` 必留——histogram_quantile 需要桶边界 |
| `> 3` | P99 超过 3 秒 | 3s 是 web 体验的"能忍上限" |

```yaml
      # 3) Token 成本小时环比 ≥ 3 倍
      - alert: TokenCostSpike
        expr: (sum(rate(llm_cost_cny_total[1h])) * 3600) /
              (sum(rate(llm_cost_cny_total[1h] offset 1h)) * 3600 + 1) > 3
        for: 5m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| `rate(...[1h]) * 3600` | 1 小时平均每秒 * 3600 = 1 小时累计 | rate 是"每秒"，乘 3600 = 一小时值 |
| `offset 1h` | 上一小时的数据——`时间索引偏移` | 比较当前 vs 上一小时 |
| `+ 1` | 防除零——`空数据时除以 1` | 上一小时没数据时不能除零 |
| `> 3` | 3 倍以上才告警 | 1.5x 可能是正常波动；3x 一定是异常 |

```yaml
      # 4) 配额耗尽
      - alert: QuotaExhausted
        expr: llm_quota_used_ratio > 0.95
        for: 1m
```

| 代码 | 在做什么 | 为什么这么写 |
|---|---|---|
| Gauge 不需要 rate | 瞬时值直接比 | Gauge 是当前状态；Counter 才需要 rate |
| `> 0.95` | 95% 阈值 | 留 5% 缓冲——100% 才告警就来不及通知租户 |

---


## 十一、测试设计解释

### 11.1 8 个测试守护的断言

| 测试 | 守护的断言 | 对应的故障场景 |
|---|---|---|
| `test_http_inc_increments_counter` | 埋点 +1 | helper 写错（漏调 `.inc()` 或传错参数） |
| `test_http_inc_status_bucketing` | 4xx/5xx 归类正确 | 状态码分支写错（404 归到 5xx） |
| `test_http_inc_anon_tenant` | None → "anon" | None 变 "None"（脏数据） |
| `test_tokens_inc` | Token 增量 | tokens_inc 写错（方向混淆） |
| `test_cost_inc` | 成本累加 | cost_inc 传错单位（用了 `.inc(0.012)` 还是 `.inc(12)`） |
| `test_quota_set` | Gauge set | 用了 `.inc()` 而不是 `.set()`（Gauge API） |
| `test_metrics_endpoint_returns_prometheus_format` | /metrics 端点 200 + 含 4 指标 | 中间件没注册 / 路径配置错 |

| `test_metrics_endpoint_skips_self` | /metrics 端点不参与计数 | self-scrape 把 `/metrics` 也计进 HTTP_REQUESTS |

### 11.2 `_value.get()` 是私有 API

测试用 `Counter._value.get()` 读累计值——这 API prometheus_client 没承诺稳定。但**单测是黑盒**——只要我们的 helper 函数功能对，私有 API 怎么算都不影响业务。

为什么不用 `with` 块或 mock 库？

- `with` 块重置整个 REGISTRY，影响其它测试
- mock 库要用 `patch.object(REGISTRY, '_names_to_collectors', ...)`——复杂

权衡：`._value.get()` 简单可读，是测试 Prometheus 指标的标准做法。

---


## 十二、常见疑问

**Q1：为什么不直接用 prometheus-fastapi-instrumentator（自动埋点）？**
A：用户决策时确认"手工埋点"——理由：① 自动埋点没法不 star 减 tenant_id / path 标签；② 手工埋点粒度可控，可以选 path / 不选 path；③ 阶段 8 拆分多个服务，手动埋点代码可以直接复制。

**Q2：Loki 装不下替代为 ELK？**
A：用户决策时确认 Loki——理由：① Grafana 同源不用多装一个 Kibana；② Loki 内存约 25MB，ES 堆 16GB；③ 本项目日志量小（60 个请求量级），Loki 完全够。

**Q3：AlertManager 规则用 for: 2m 太长怎么办？**
A：生产 2m 是标准——避免抖动。**测试时改成 30s** 快速验证，验证完改回原值。

**Q4：为什么 trace 不在本阶段？**
A：用户决策时确认"沿用 LangSmith"——理由：① 阶段 4 落地 LangSmith，云端 trace 已有；② 个人项目加 Jaeger 内存开销大；④ 阶段 8 拆分多服务时如果发现 LangSmith 不够，再加 Jaeger——**不要提前"凡是要"**。

**Q5：状态码 304/308 这种重定向不常见，怎么处理？**
A：本阶段归类为 `"3xx"`（单独）。**真正不常见**——大多数路由都重定向给前端。出现重定向意味着资源缓存生效，反而是好兆头。

**Q6：仪表盘 JSON 错了怎么办？**
A：Grafana UI 会拒绝、不会崩。错误处理：① 看 `docker logs ai_chief_grafana`；② 用 `jq` 本地校验：`jq . docker/grafana/dashboards/http-overview.json`。

**Q7：Prometheus 抓取不到后端怎么办？**
A：① 看 `curl -s http://127.0.0.1:9090/api/v1/targets` → `health=down` 看 `lastError`；② 容器内 `host.docker.internal` 解不到 → Linux 加 `network_mode: host`；③ scrape_timeout 太短 → 改大到 10s。

**Q8：仪表盘能直接打开吗？**
A：Provisioning 启动时自动加载——docker logs 启动后 30s 内可见。**第一次启动慢**——Grafana 要初始化数据库。

**Q9：为什么 label 路径用 FastAPI route pattern 而不是真实 URL？**
A：高基数问题。`/users/1` `/users/2` `/users/3` ... 让 label 数量爆炸。FastAPI route pattern 是 `/users/{user_id}`——**单条 label 容纳所有用户**。

**Q10：为什么指标名带 `_total` 后缀？**
A：Prometheus 命名约定——Counter 必带 `_total`，表示"累计"；Gauge / Histogram 不带。

**Q11：测试怎么 mock metrics？**
A：本项目不用 test——helper 直接调 prometheus_client 内部 API。Prometheus 客户端是同步的、有内部锁——在 pytest 里跑没问题。**但底层的依赖（如 requests）需要 mock**。

---


## 附录 A：本阶段一句话解决与价值

```text
阶段 7 解决了什么？
  - QPS / 延迟 / 错误率 三个指标从"算出来的还是"变成"仪表盘上实时看"
  - 出事故从"边警状态"变成"实时响铃"
  - 错误排查从"grep docker logs"变成"面板点击 trace_id 看具体错误"
  - 阶段 8 拆分后能立刻验证"拆分前后指标对比"——为阶段 10 压测提供实时面板
```

面试官问"你怎样保证服务可用性"的话术：阶段 7 实测的 QPS 数字 + AlertManager 触发次数 + 人工制造 5xx 触发告警的演练过程——每个数字都有出处、每个环节都亲手验证过。

---


## 附录 B：4 个仪表盘 JSON 逐面板解释（按面板说人话）

> 本附录回答一个问题：**打开 Grafana 看到的那几个面板，每个到底在查什么、为什么要这么查。** 4 个 JSON 文件已落在 `docker/grafana/dashboards/`，你不需要手抄；这里解释每个字段。

### B.0 先说清楚"仪表盘是怎么被自动加载的"

```text
docker-compose 把两个目录挂进 grafana 容器：
  ./grafana/provisioning  ->  /etc/grafana/provisioning        （数据源 + 仪表盘"路标"）
  ./grafana/dashboards    ->  /var/lib/grafana/dashboards      （4 个 JSON 本体）

Grafana 启动时读 provisioning/datasources/datasources.yml  →  自动建好 Prometheus / Loki 两个数据源
Grafana 启动时读 provisioning/dashboards/dashboards.yml    →  知道"去 /var/lib/grafana/dashboards 找 *.json"
                                                            →  每 30s 扫一遍，有改动自动重载
```

🔴 **一个坑（本阶段已修）**：`datasources.yml` 里**必须显式写 `uid`**。如果只写 `name`，Grafana 给数据源随机生成 uid，而每个面板 JSON 里写死的是 `{"uid": "prometheus"}` / `{"uid": "loki"}`——对不上，**所有面板都会报 `Datasource prometheus was not found`**。所以要保证 `datasources.yml` 的两个 `uid` 与面板里的一字不差。

### B.1 数据源 uid 对照表

| 面板里写的 | 必须等于 datasources.yml 里的 | 类型 |
|---|---|---|
| `{"type": "prometheus", "uid": "prometheus"}` | `uid: prometheus` | Prometheus（指标） |
| `{"type": "loki", "uid": "loki"}` | `uid: loki` | Loki（日志） |

### B.2 `http-overview.json` —— HTTP 概览（4 个面板）

| 面板 | 类型 | PromQL | 在查什么（人话） |
|---|---|---|---|
| QPS by path | timeseries | `sum by (path) (rate(http_requests_total[1m]))` | 每秒有几次请求，按路由分开画。`rate([1m])`=取 1 分钟窗口，把"累计次数"换算成"每秒次数" |
| P50 / P99 by path | timeseries | `histogram_quantile(0.50|0.99, sum by (path, le) (rate(http_request_duration_seconds_bucket[1m]))) * 1000` | 延迟分位数。P99=最慢的 1% 请求有多慢。`*1000` 把秒换成毫秒。直方图指标名带 `_bucket`（Prometheus 自动生成的桶） |
| 5xx 错误率 | timeseries | `sum(rate(http_requests_total{status=~"5xx"}[5m])) / sum(rate(http_requests_total[5m]))` | 5xx 请求数 ÷ 总请求数 = 服务端错误占比。面板上画了黄线(1%)/红线(5%)阈值 |
| 4xx 错误率 by tenant | timeseries | `sum by (tenant_id) (rate(http_requests_total{status=~"4xx"}[5m])) / sum by (tenant_id) (rate(http_requests_total[5m]))` | 按租户看"客户端错误"比例——能看出哪个租户在疯狂传错参数 |

**标签怎么来的**：`http_requests_total` 的标签是 `method / status / tenant_id / path`（见 `metrics.py`）。`status` 已经被 `http_inc()` 归成 `2xx / 4xx / 5xx` 三档（不是原始 200/404/500），这样标签基数小、不会撑爆 Prometheus。

**为什么 `sum by (path)` 而不是 `sum by (path, method)`**：`by(...)` 决定"画几条线"。只按 path 拆，同一路由的 GET/POST 合成一条线，图更干净；要拆 method 时再加一个维度即可。

### B.3 `token-cost.json` —— Token 成本（4 个面板）

| 面板 | 类型 | PromQL | 在查什么（人话） |
|---|---|---|---|
| Tokens / min by direction | timeseries | `sum by (direction) (rate(llm_tokens_total[5m])) * 60` | 每分钟烧多少 token，按 input/output 分开。`rate` 是"每秒"，`*60` 才变"每分钟" |
| Cost (CNY/h) by model | timeseries | `sum by (model) (rate(llm_cost_cny_total[5m])) * 3600` | 每个模型每小时花多少元。`*3600` 把"每秒元"换成"每小时元" |
| Tokens / min by model | timeseries | `sum by (model) (rate(llm_tokens_total[5m])) * 60` | 每个模型每分钟烧多少 token——看哪个模型最费 |
| 配额使用率 by tenant | timeseries | `llm_quota_used_ratio` | Gauge 指标，每个租户当前用量 ÷ 配额（0~1）。>0.95 触发第 4 条告警 |

🔴 **一个必须记住的坑**：`rate(...)` 的结果单位是"每秒"，而人看报表习惯"每分钟 / 每小时"。`*60`、`*3600` 就是这层换算，面试常问"你面板上这个数为什么乘 60"。

🔴 **另一个坑（本阶段踩过并已修）**：早期草稿写过 `sum by (model) (rate(http_requests_total{path="/chat/stream"}[5m]))`——**错的**。`http_requests_total` 根本没有 `model` 标签，`sum by (model)` 会返回空序列（面板一片空白，也不报错，最难查）。正确做法是统计真正带 `model` 标签的 `llm_tokens_total`。**规律：`sum by (某标签)` 之前，先确认这个指标真的有这个标签**——用 `curl /metrics | grep 指标名` 看一眼标签就行。

### B.4 `error-logs.json` —— 错误日志（2 个面板）

| 面板 | 类型 | LogQL | 在查什么（人话） |
|---|---|---|---|
| ERROR 日志 | logs | `{job="docker"} \|= "ERROR"` | 从 Loki 实时拉"日志内容里含 ERROR 字样"的行 |
| WARN 日志 | logs | `{job="docker"} \|~ "(?i)WARN"` | 同上，含 WARN/Warning 的行（`~` 是正则，`(?i)` 忽略大小写） |

**LogQL 三个符号记牢**（对照上面）：
- `{job="docker"}`：**标签选择器**——先框出"哪批日志"，类似 SQL 的 `WHERE` 走索引
- `|=`：**行内含**（子串匹配，快）
- `|~`：**行内正则**（慢一点，胜在灵活）

`job="docker"` 这个标签来自 `promtail-config.yaml` 的 `scrape_configs.job_name: docker`；Promtail 抓 `/var/lib/docker/containers/*/*log` 时给每行打上它。

> 🟡 用 `|= "ERROR"` 而非 `|= "level=ERROR"`：前者只要求行里出现 `ERROR` 子串，不管日志是 `"level": "ERROR"`（JSON 冒号）还是 `level=ERROR`（logfmt 等号）都能命中，最稳。日志格式没统一前，别把过滤条件写死。

### B.5 `alerts.json` —— 告警统计（3 个面板）

| 面板 | 类型 | PromQL | 在查什么（人话） |
|---|---|---|---|
| 活跃告警数 | stat | `count(ALERTS{alertstate="firing"})` | 正在响铃的告警**有几条**（一个数字）；没告警时显示 0 |
| 告警明细 | table | `ALERTS` | 把每条告警的标签（alertname / severity / instance…）列成表格 |
| 告警状态时间线 | timeseries | `count by (alertstate) (ALERTS)` | firing / pending 各自的条数随时间变化 |

**`ALERTS` 是什么**：不是你自己埋的点，是 **Prometheus 内置生成的**一个特殊指标——只要 `alerts.yml` 里写了规则，Prometheus 就会持续输出每条规则的状态（`alertstate="firing"` / `"pending"`）。所以这个面板是"白捡的"，不用改任何业务代码。

**`count(...)` vs 直接 `ALERTS`**：直接查 `ALERTS` 会返回 N 条序列（每条告警一条），stat 面板不知道显示哪个；`count()` 把它压成一个标量数字，stat 面板才显示得出来。

### B.6 面板 JSON 里几个通用字段（每个面板都有）

| 字段 | 作用 | 常见取值 |
|---|---|---|
| `type` | 面板类型 | `timeseries`（折线）/ `logs`（日志流）/ `stat`（大数字）/ `table`（表格） |
| `datasource` | 用哪个数据源 | 见 B.1 |
| `gridPos` | 24 列网格里的位置 | `{"h":8,"w":12,"x":0,"y":0}` = 高 8 宽 12，第 0 列第 0 行 |
| `targets[].expr` | 查询语句 | PromQL（指标）或 LogQL（日志） |
| `targets[].legendFormat` | 图上每条线的名字 | `{{path}}` 取标签值填进去 |
| `fieldConfig.defaults.unit` | 数值单位 | `ms` / `percentunit`（0.05 显示成 5%）/ `currencyCNY` / `reqps` |
| `options.legend` | 图例样式 | `displayMode: table` + `calcs: ["mean","max"]` 显示均值/峰值 |
| `refresh` | 自动刷新间隔 | `5s` / `10s` |

> 🟡 **`gridPos` 的 x 只能在 0~12（因为 w=12）之间**：一排放两个 w=12 的面板，第二个的 x 必须是 12。写错 x 会重叠。满宽面板是 `w: 24`，x 只能是 0。

