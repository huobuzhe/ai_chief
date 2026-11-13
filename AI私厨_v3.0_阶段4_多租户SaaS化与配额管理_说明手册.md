# AI 私厨 v3.0 阶段 4 说明手册 — 多租户 SaaS 化 + 配额管理

> **本手册性质**：看懂为什么——全项目**唯一**逐行代码解释处。每行代码讲"在做什么 / 为什么这么写 / 每个调用参数什么意思 / 每个函数为什么这么写"。
>
> **阅读方式**：先按《操作手册》把代码敲完（你已经有完整代码），再看本手册把"为什么"补齐。两份手册**不重复**——操作手册讲"步骤"，本手册讲"代码里每一行在做什么"。
>
> **注释约定**：本手册里的所有代码示例，行尾都用"#"或字符串注释**直接解释该行作用**，不加 1,2,3 序号，不编造"真实数据示例"（比如不说"假设张三的租户 ID 是 5"——直接说"占位值"）。

---

## 目录

- [1. 阶段全景](#一阶段全景)
- [2. 多租户方案选型](#二多租户方案选型)
- [3. 配额算法选型](#三配额算法选型)
- [4. 审计日志设计](#四审计日志设计)
- [5. Feature Flag（灰度）设计](#五feature-flag灰度设计)
- [6. 数据模型逐行解读](#六数据模型逐行解读)
  - [6.1 `app_my/db/models/tenant.py`](#61-app_mydbmodelstenantpytenants-表)
  - [6.2 `app_my/db/models/tenant_member.py`](#62-app_mydbmodelstenant_memberpytenant_members-表)
  - [6.3 `app_my/db/models/audit_log.py`](#63-app_mydbmodelsaudit_logpyaudit_logs-表)
  - [6.4 `app_my/db/models/feature_flag.py`](#64-app_mydbmodelsfeature_flagpyfeature_flags-表)
  - [6.5 `app_my/db/models/user.py` 的新增列](#65-app_mydbmodelsuserpy-的新增列default_tenant_id)
- [7. 核心模块逐行解读](#七核心模块逐行解读)
  - [7.1 `app_my/core/tenant.py`](#71-app_mycoretenantpy租户上下文)
  - [7.2 `app_my/core/quota.py`](#72-app_mycorequotapyredis-配额计数器)
  - [7.3 `app_my/core/audit.py`](#73-app_mycoreauditpy审计写入工具)
  - [7.4 `app_my/core/feature_flag.py`](#74-app_mycorefeature_flagpy灰度判定)
  - [7.5 `app_my/core/security.py` 的改动](#75-app_mycoresecuritypy-的改动jwt-携带-tenant-三元组)
- [8. 中间件逐行解读](#八中间件逐行解读)
  - [8.1 `app_my/middleware/tenant.py`](#81-app_mymiddlewaretenantpy注入租户上下文)
  - [8.2 `app_my/middleware/quota.py`](#82-app_mymiddlewarequotapychat-配额检查)
- [9. API 改造逐行解读](#九api-改造逐行解读)
  - [9.1 `app_my/api/auth.py` 改造](#91-app_myapiauthpy-改造注册建个人租户--switch-tenant)
  - [9.2 `app_my/api/chat.py` 改造](#92-app_myapichatpy-改造透传-tenant_id)
  - [9.3 `app_my/api/billing.py` 改造](#93-app_myapibillingpy-改造按租户统计)
  - [9.4 `app_my/api/kg.py` 改造](#94-app_myapikgpy-改造要求登录租户)
  - [9.5 `app_my/api/tenant.py`（新增）](#95-app_myapitenantpy新增租户管理接口)
  - [9.6 `app_my/api/admin.py`（新增）](#96-app_myapiadminpy新增管理端接口)
- [10. `main.py` 中间件链顺序](#十mainpy-中间件链顺序)
- [11. 测试逐行解读](#十一测试逐行解读)
- [12. 面试可能被追问的点](#十二面试可能被追问的点)

---

## 一、阶段全景

本阶段把系统从「一个用户一个数据库行」演化为「一个租户一批用户 + 独立数据 + 配额 + 审计 + 灰度」。四块能力各司其职：

- **多租户隔离**：每个 `chat` / `kg` / `billing` 查询自动绑定 `tenant_id`，靠中间件把身份注入 `request.state`，业务代码读 `request.state.tenant_id` 即可。
- **配额管理**：租户维度计数（对话次数/天、token/天、成员数），用 Redis O(1) 计数器，不给 PostgreSQL 加压力。
- **审计日志**：API 内显式调 `log_audit()` 写敏感操作（创建 / 移除 / 灰度变更），不靠中间件（中间件拿不到业务参数）。
- **Feature Flag**：按 `tenant_id` 哈希分桶，租户粒度灰度（个人项目不需要用户粒度——租户即用户）。

---

## 二、多租户方案选型

行业三种方案（来自阿里云栖、AWS、Salesforce 公开博客）：

| 方案 | 优点 | 缺点 |
|---|---|---|
| 共享库 + `tenant_id` 列 | 改造成本最低，迁移零成本，单机最佳 | 每张表都要带列，ORM 写起来啰嗦 |
| 共享库 + 独立 schema | 中等隔离（schema 级 DDL 权限） | ORM 切换 schema 复杂，跨 schema JOIN 性能差 |
| 独立库 | 最强隔离，合规友好 | 运维复杂（每租户一库），跨库聚合报表困难 |

**本项目选「共享库 + `tenant_id` 列」**：

理由 1：单机个人项目，运维越简单越好——独立库要做 100 份备份、配额路由，简历写出来反而不真实（面试会问"你有多少租户、为什么要分库"）。

理由 2：菜谱知识库是公共数据，不按租户拆——共享库天然适合。

理由 3：阶段 5 引入 PgBouncer 连接池治理，能挡掉共享库的"连接放大"问题。

**关键纪律**：`tenant_id` **必须从 JWT 解析**，不能从前端传参——这是数据隔离的命门。

---

## 三、配额算法选型

三种常见配额算法：

| 算法 | 优点 | 缺点 |
|---|---|---|
| 固定窗口（INCR + EXPIRE） | 实现最简单，O(1)，原子 | 边界处可能 2 倍突发（59 秒 + 60 秒两个窗口都满） |
| 滑动窗口（ZSET 时间戳） | 无边界突发 | Redis 内存放大（每个请求一个 ZSET 元素），TTL 清理复杂 |
| 令牌桶（Lua 脚本） | 平滑限流，可突增 | Lua 脚本维护成本高，调试难 |

**本项目选「固定窗口 + 分桶键（按 `YYYYMMDD`）」**：

理由 1：单次配额检查 O(1)，请求热路径上加锁/多 round-trip 都不可接受。

理由 2：跨天**自然分桶换键**，不需要定时任务清老键——`INCR` 的 key 带日期，昨天的 key 没人 INCR，30 天后自动从 Redis 淘汰（Redis 默认 maxmemory 策略 allkeys-lru）。

理由 3：2 倍边界突发的代价可接受——配额本来就有 2-3 倍冗余（free 给 50，实际日均 30，边界放大到 60 也不出事）。

**fail-open 策略**：Redis 挂了配额检查**放行**——配额是保护措施不是主链路；fail-closed 会让缓存故障把整个服务打死。详见 `quota.py` 注释。

---

## 四、审计日志设计

**为什么不放中间件**：中间件只能看到 path/method，看不到"邀请了谁""改了什么资源"——审计需要业务参数。

**为什么同步写而不是异步队列**：个人项目不需要担心审计写入打爆 DB——审计写入是单条 INSERT，本身有索引保护；引入异步队列反而让审计"非实时"，合规场景下不可接受。

**字段约定**：

- `tenant_id`：这条审计**属于哪个租户**——为空表示全局操作（如管理员创建 flag）。
- `actor_user_id`：谁做的——为空表示系统自动（如定时任务）。
- `action`：动作用英文点分（`tenant.create` / `tenant.invite` / `auth.switch_tenant` / `feature_flag.update`）。
- `resource_type + resource_id`：被操作的对象（`tenant` / `user` / `feature_flag` + 资源 ID 字符串）。
- `payload_json`：业务参数（邀请的角色、改的灰度比例等）—— JSON 字符串，方便扩展。

---

## 五、Feature Flag（灰度）设计

**为什么不用配置中心**：个人项目没有配置中心基础设施；直接读 DB + 内存缓存最简。

**分桶算法**：`md5(f"{tenant_id}:{flag_name}")` 取前 8 位十六进制转 int，模 100 得到 0~99 的桶号。

为什么不直接 `tenant_id % 100`：`%` 太规律——相邻租户 ID 全部进同一个桶；MD5 让"加新租户"的桶号尽量均匀。

为什么 flag 名参与 hash：不参与则不同 flag 同一租户的桶号一样——想给租户 A 开 flag1 也开 flag2 时桶号相同，**灰度要么都开要么都不开**；参与后两个 flag 互相独立。

**缓存策略**：60s 内存 TTL；改了 flag 主动 `invalidate_cache(name)` 让下一请求立刻读到新值。

---

## 六、数据模型逐行解读

### 6.1 `app_my/db/models/tenant.py`（tenants 表）

```python
# app_my/db/models/tenant.py
# 租户是一组用户 + 资源的边界；type 区分个人/团队；plan 区分套餐
from datetime import datetime, timezone  # timezone-aware 时间，3.12+ 强制要求
from typing import Optional  # Optional 让字段可空（owner_id 不为空这里就没用）
from sqlalchemy import DateTime, Integer, String  # 三种 SQLAlchemy 列类型
from sqlalchemy.orm import Mapped, mapped_column  # 1.23+ 类型注解式 ORM 写法
from app_my.db.base import Base  # 公共基类，SQLAlchemy 靠它收集所有表
def _utcnow() -> datetime:  # 统一的时间函数，3.12+ 强制 timezone.utc
def _utcnow(): datetime.now(timezone.utc)  # utcnow() 在 3.12+ 已废弃，改用 now(timezone.utc)
class Tenant(Base):  # 继承 Base，SQLAlchemy 会自动建表
    __tablename__ = "tenants"  # 表名，复数（团队习惯）
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 主键自增
    name: Mapped[str] = mapped_column(String(80), nullable=False)  # 租户名，80 字符以内
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="personal")  # personal/team
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="free")  # free/pro/enterprise
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 创建者；加索引按 owner 查
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)  # 建时间
    def __repr__(self) -> str:  # 调试输出，便于在日志里区分
        return f"<Tenant id={self.id} name={self.name!r} type={self.type}>"  # f-string 调试字符串，!r 加引号
```

### 6.2 `app_my/db/models/tenant_member.py`（tenant_members 表）

```python
# app_my/db/models/tenant_member.py
# 用户-租户 多对多 + 角色；每条记录是一个成员关系
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, UniqueConstraint  # UniqueConstraint 加复合唯一约束
from sqlalchemy.orm import Mapped, mapped_column
from app_my.db.base import Base
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
class TenantMember(Base):
    __tablename__ = "tenant_members"  # 表名
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),)  # 复合唯一约束：同一用户在同一租户只能有一条记录
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 自身成员
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 租户 ID；加索引按租户查
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 用户 ID；加索引按用户查
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")  # owner/admin/member
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)  # 加入时间
```

### 6.3 `app_my/db/models/audit_log.py`（audit_logs 表）

```python
# app_my/db/models/audit_log.py
# 审计日志：敏感操作留底；按 tenant_id+action_time 索引便于回放
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Integer, String, Text  # Text 类型存 JSON 字符串
from sqlalchemy.orm import Mapped, mapped_column
from app_my.db.base import Base
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # 可空：全局操作没有 tenant
    actor_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # 可空：系统任务
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 点分动作名（tenant.invite）；索引便于按动作统计
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 被操作对象类型（user/tenant/feature_flag）
    resource_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)  # 对象 ID（用 str 兼容 tenant_id / user_id / flag name）
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON 字符串存扩展字段
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)  # 时间索引便于时间范围查
```

### 6.4 `app_my/db/models/feature_flag.py`（feature_flags 表）

```python
# app_my/db/models/feature_flag.py
# Feature Flag 表：flag 名唯一；enabled 总开关 + rollout_pct 灰度比例 + whitelist 白名单
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app_my.db.base import Base
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)  # flag 名全局唯一
    enabled: Mapped[bool] = mapped_column(nullable=False, default=False)  # 总开关，False 时全员不开
    rollout_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0~100 灰度比例
    whitelist_tenants: Mapped[str] = mapped_column(Text, nullable=False, default="")  # JSON 字符串存白名单 tenant_id 数组
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")  # 给人看的说明
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)  # onupdate 写入时自动更新
```

### 6.5 `app_my/db/models/user.py` 的新增列（default_tenant_id）

```python
# 在 is_active 行下方插入；老 users 表兼容靠"应用层兜底"（见 13.1 节 register/login）
default_tenant_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
# 作用：每个用户的"默认租户"——登录时拿这个签 token，调用接口默认走这个租户
# 为什么 Optional：老用户没这列；应用层兜底逻辑见 register/login
# 为什么加索引：按 user_id 反查租户时用不到，但运维排查"某租户有哪些用户"会用到
```

---

## 七、核心模块逐行解读

### 7.1 `app_my/core/tenant.py`（租户上下文）

```python
# app_my/core/tenant.py
# 租户上下文：JWT 解析后注入 request.state 的最小数据单元
from dataclasses import dataclass  # 用 dataclass 而不是 Pydantic：只装数据，无校验需求
from typing import Optional
@dataclass
class TenantContext:  # 业务侧拿到这个对象就能直接 .tenant_id / .role / .is_admin
    tenant_id: int  # 租户 ID
    user_id: int  # 当前用户 ID（冗余存，方便调用方少查一次）
    role: str = "owner"  # 当前用户在该租户的角色；默认 owner 是兼容老 token
    plan: str = "free"  # 当前租户的套餐；影响配额上限
    @property
    def is_admin(self) -> bool:  # property 让调用方写 tenant.is_admin 比 tenant.role == "owner" 更语义化
        return self.role in ("owner", "admin")  # owner 和 admin 都是管理角色
ROLE_OWNER = "owner"  # 字符串常量，统一从这取
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"
def parse_role(role: str) -> str:
    # 防御式：把任意字符串归一化到合法角色；非法值降级为 member（不会让系统崩）
    if role in (ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER):
        return role  # 合法直接返回
    return ROLE_MEMBER  # 非法降级
```

### 7.2 `app_my/core/quota.py`（Redis 配额计数器）

```python
# app_my/core/quota.py
# 租户级配额：Redis 固定窗口计数器；O(1) 热路径上加锁/多 round-trip 都不可接受
from datetime import datetime, timezone  # 取按日的 key
from typing import Tuple  # 元组返回值类型注解
from app_my.core.logging import logger
from app_my.core.redis_client import get_redis  # 复用阶段 4 的全局 Redis 单例
def _today_key(tenant_id: int, metric: str) -> str:
    # 键格式带日期：跨天自动换键=自动清零；不需要定时任务清老 key
    day = datetime.now(timezone.utc).strftime("%Y%m%d")  # 今天的 UTC 日期字符串
    return f"quota:{tenant_id}:{metric}:{day}"  # 完整 key
def incr_usage(tenant_id: int, metric: str, by: int = 1) -> int:
    # 加 1（可指定 by），返回加完的值；返回 -1 表示 Redis 不可用（fail-open）
    key = _today_key(tenant_id, metric)  # 取今天这个 metric 的 key
    try:
        r = get_redis()  # 拿全局 Redis 客户端
        val = r.incrby(key, by)  # 原子 +by；redis-py 自动转 int 返回
        if val == by:  # 第一次 INCR 这个 key（说明键刚建）
            r.expire(key, 9000)  # 9000 秒兜底过期（≈2.5 小时，远小于跨天 24h）
        return int(val)  # 返回加完的值（int 化防止 redis-py 返回 bytes）
    except Exception as exc:
        # fail-open：Redis 挂了放行并记日志；配额是保护措施不是主链路
        logger.warning("配额计数失败（fail-open）: %s %s", type(exc).__name__, exc)
        return -1  # 特殊值表示"没计入"——接口层按 fail-open 放行
def get_usage(tenant_id: int, metric: str) -> int:
    # 查已用量；Redis 挂返回 0（不阻断 UI 显示）
    key = _today_key(tenant_id, metric)
    try:
        return int(get_redis().get(key) or 0)  # redis-py get 返回 None 或 str；or 0 防 None
    except Exception:
        return 0  # Redis 挂返回 0
def reset_usage(tenant_id: int, metric: str) -> None:
    # 手动重置（管理员手动调，或测试 fixture）；删 key 不是 set 0——删掉最干净
    try:
        get_redis().delete(_today_key(tenant_id, metric))
    except Exception as exc:
        logger.warning("配额重置失败: %s", exc)
# 配额档位：按 plan 决定上限；未知 plan 兜底到 free
QUOTAS = {
    "free":       {"chat_daily": 50,  "tokens_daily": 100_000,  "max_members": 1},
    # free：50 次对话/天（个人用够），10 万 token，1 个成员（个人租户不能邀请）
    "pro":        {"chat_daily": 500, "tokens_daily": 1_000_000, "max_members": 10},
    # pro：500 次/天，100 万 token，10 个成员
    "enterprise": {"chat_daily": 5000,"tokens_daily": 10_000_000,"max_members": 100},
    # enterprise：5000 次/天，1000 万 token，100 个成员
}
def get_limit(plan: str, metric: str) -> int:
    # 未知 plan 兜底 free（防御式：DB 里 plan 字段被污染不会让接口崩）
    return QUOTAS.get(plan, QUOTAS["free"]).get(metric, 0)
def check_quota(tenant_id: int, plan: str, metric: str) -> Tuple[bool, int, int]:
    # 三元组返回（bool, used, cap）：让接口层直接拼结构化错误
    limit = get_limit(plan, metric)
    if limit == 0:  # 这个 metric 未配置上限 = 不限
        return True, 0, 0
    used = get_usage(tenant_id, metric)  # 查已用量
    return used < limit, used, limit  # 元组：是否超限、已用、上限
```

### 7.3 `app_my/core/audit.py`（审计写入工具）

```python
# app_my/core/audit.py
# 审计写入：业务代码里显式调 log_audit() 写入敏感操作
from typing import Optional
from sqlalchemy.orm import Session
from app_my.db.models.audit_log import AuditLog  # 审计表模型
def log_audit(
    db: Session,  # SQLAlchemy 会话（调用方 FastAPI Depends 注入）
    *,
    # 关键字参数：避免调用方写错参数顺序；* 后面强制 keyword-only
    action: str,  # 点分动作名（tenant.create / tenant.invite / feature_flag.update）
    tenant_id: Optional[int] = None,  # 审计所属租户；None 表示全局操作
    actor_user_id: Optional[int] = None,  # 操作者；None 表示系统自动
    resource_type: Optional[str] = None,  # 被操作对象类型（user/tenant/feature_flag）
    resource_id: Optional[str] = None,  # 对象 ID（用 str 兼容多种 ID）
    payload: Optional[dict] = None,  # 业务参数 dict
) -> None:
    # 调用方负责 commit；本函数只 add；不自己 commit 是为了和业务事务绑定（邀请成功才提交审计）
    import json  # 函数内 import：避免循环依赖（models 导入本模块时 json 已就绪）
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else None  # JSON 字符串；ensure_ascii=False 保中文
    entry = AuditLog(  # 构造 AuditLog 模型实例
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_json=payload_json,
    )
    db.add(entry)  # 加到会话；调用方 commit 时落库
```

### 7.4 `app_my/core/feature_flag.py`（灰度判定）

```python
# app_my/core/feature_flag.py
# Feature Flag：按 tenant_id 哈希分桶的灰度判定
import hashlib  # MD5 用
import json  # 解析 whitelist JSON 字符串
from typing import Optional
from sqlalchemy.orm import Session
from app_my.core.logging import logger
from app_my.core.redis_client import get_redis  # 引入但本阶段不直接用——保留扩展位
from app_my.db.models.feature_flag import FeatureFlag  # flag 模型
# 60s 内存缓存：读多写少，加 TTL 避免每次查 DB
_CACHE: dict[str, tuple[float, dict]] = {}  # key:flag 名，value:(过期时间, flag dict)
_CACHE_TTL = 60.0  # 60 秒过期
def _load_flag(db: Session, name: str) -> Optional[dict]:
    # 从 DB 读一条 flag 转 dict；解析 whitelist JSON
    # name 是 unique 但不是主键，不能用 db.get（db.get 按主键查 id），必须显式 select
    from sqlalchemy import select
    row = db.scalar(select(FeatureFlag).where(FeatureFlag.name == name))
    if row is None:
        return None  # flag 不存在
    try:
        whitelist = json.loads(row.whitelist_tenants or "[]")  # 解析 JSON；空字符串按 [] 处理
    except json.JSONDecodeError:
        whitelist = []  # 解析失败按空名单
    return {
        "name": row.name,
        "enabled": row.enabled,
        "rollout_pct": row.rollout_pct,
        "whitelist": [int(x) for x in whitelist],  # 转 int 防 JSON 里写 "1" 字符串
    }
def _read_with_cache(db: Session, name: str) -> Optional[dict]:
    # 带 60s 缓存读 flag；过期重读 DB
    import time
    now = time.time()
    hit = _CACHE.get(name)
    if hit and now - hit[0] < _CACHE_TTL:  # 命中且没过期
        return hit[1]
    flag = _load_flag(db, name)
    if flag is not None:  # 写入缓存（包括 enabled=False 的 flag——避免反复查 DB）
        _CACHE[name] = (now, flag)
    return flag
def invalidate_cache(name: Optional[str] = None) -> None:
    # 主动失效缓存（管理员改 flag 后调一次）
    if name is None:
        _CACHE.clear()  # 清全部
    else:
        _CACHE.pop(name, None)  # 清单个；pop 不报错
def is_feature_enabled(db: Session, name: str, tenant_id: int) -> bool:
    # 判定某租户能否用某 flag；flag 不存在默认关闭（新功能保守做法）
    flag = _read_with_cache(db, name)
    if flag is None or not flag["enabled"]:  # 不存在或总开关关
        return False
    if tenant_id in flag["whitelist"]:  # 白名单命中
        return True
    # 哈希分桶：MD5(tenant_id + flag_name) 取前 8 位 → int → % 100 → 0~99
    h = hashlib.md5(f"{tenant_id}:{name}".encode()).hexdigest()
    bucket = int(h[:8], 16) % 100  # 0~99 的桶号
    return bucket < flag["rollout_pct"]  # 桶号小于灰度比例即在内
```

### 7.5 `app_my/core/security.py` 的改动（JWT 携带 tenant 三元组）

```python
# app_my/core/security.py
# 改 1：_create_token 加 extra_claims 参数
def _create_token(subject: Any, token_type: str, expires_minutes: int, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)
    payload = {  # payload 基础字段
        "sub": str(subject),
        "type": token_type,
        "jti": uuid4().hex,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:  # 有额外 claims 就 merge
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
# 改 2：create_access_token 加 tenant 三元组参数（keyword-only 防止位置错乱）
def create_access_token(subject: Any, *, tenant_id: Optional[int] = None, tenant_role: str = "owner", tenant_plan: str = "free") -> str:
    # tenant_id=None 时不写入 tenant claims——兼容老调用（/auth/refresh 不需要 tenant）
    return _create_token(
        subject,
        TOKEN_TYPE_ACCESS,
        settings.JWT_ACCESS_EXPIRE_MINUTES,
        extra_claims={
            "tenant_id": tenant_id,
            "tenant_role": tenant_role,
            "tenant_plan": tenant_plan,
        } if tenant_id is not None else None,
    )
# 改 3：refresh token 故意不携带 tenant——强制登录时再确定，避免 refresh 期间换租户引发歧义
def create_refresh_token(subject: Any) -> str:
    return _create_token(subject, TOKEN_TYPE_REFRESH, settings.JWT_REFRESH_EXPIRE_MINUTES)
```

---

## 八、中间件逐行解读

### 8.1 `app_my/middleware/tenant.py`（注入租户上下文）

```python
# app_my/middleware/tenant.py
# TenantContextMiddleware：在 Auth 之后从 token payload 组装并挂到 request.state.tenant
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app_my.core.tenant import TenantContext  # 数据单元
class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        payload = getattr(request.state, "token_payload", None)
        # AuthMiddleware 已经把 token payload 放进去了；这里直接读
        tenant_id = None  # 初值 None 兼容老调用
        role = "member"  # 角色默认 member（不假设 owner）
        plan = "free"  # 套餐默认 free（最保守）
        if payload is not None:  # 有 token 才解
            tid = payload.get("tenant_id")  # 从 JWT 读
            if isinstance(tid, int):  # 类型校验：老 token 没这个字段是 None
                tenant_id = tid
            role = payload.get("tenant_role", "owner")  # 默认 owner 是兼容老 token（个人租户）
            plan = payload.get("tenant_plan", "free")  # 默认 free
        user_id = getattr(request.state, "user_id", None)  # Auth 也注入了 user_id
        request.state.tenant_id = tenant_id  # 平铺字段——多数 API 只要这三个就够
        request.state.tenant_role = role
        request.state.tenant_plan = plan
        request.state.tenant = (  # 包装对象——少数 API 需要 is_admin 之类的属性
            TenantContext(tenant_id=tenant_id, user_id=user_id or 0, role=role, plan=plan)
            if tenant_id is not None and user_id is not None  # 必须二者齐全才组装
            else None  # 不齐全保持 None，API 层显式判断
        )
        return await call_next(request)  # 放行
```

### 8.2 `app_my/middleware/quota.py`（chat 配额检查）

```python
# app_my/middleware/quota.py
# QuotaMiddleware：对 /chat/stream 做租户级 chat_daily 配额检查
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from app_my.core.logging import logger
from app_my.core.quota import incr_usage, check_quota
# 哪些路径走配额：未来扩展配额维度时在这里加
QUOTA_PATHS = {"/chat/stream"}
class QuotaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in QUOTA_PATHS:  # 只挡这些路径
            tenant_id = getattr(request.state, "tenant_id", None)
            plan = getattr(request.state, "tenant_plan", "free")
            if tenant_id is not None:  # 有 tenant 才检查（匿名调用放行——前面 Auth 已经拦过）
                ok, used, cap = check_quota(tenant_id, plan, "chat_daily")  # 查配额
                if not ok:  # 超限
                    logger.warning("配额超限 tenant=%s used=%d limit=%d", tenant_id, used, cap)
                    return JSONResponse(  # 429 + 结构化错误
                        {
                            "detail": "租户对话配额已用完",
                            "metric": "chat_daily",
                            "used": used,
                            "limit": cap,
                            "upgrade_hint": "升级到 pro / enterprise 可提高配额",  # 引导升级
                        },
                        status_code=429,
                        headers={"Retry-After": "86400"},  # 告诉客户端 24h 后再试（=明天）
                    )
        response: Response = await call_next(request)  # 请求过了再 INCR
        if request.url.path in QUOTA_PATHS:
            tenant_id = getattr(request.state, "tenant_id", None)
            if tenant_id is not None:
                incr_usage(tenant_id, "chat_daily", 1)  # +1；包含失败的请求也算（避免恶意 429 探测）
        return response
```

---

## 九、API 改造逐行解读

### 9.1 `app_my/api/auth.py` 改造（注册建个人租户 + switch-tenant）

```python
# app_my/api/auth.py
# 顶部 import 加三行
from app_my.db.models.tenant import Tenant  # 注册时建个人租户
from app_my.db.models.tenant_member import TenantMember  # 关联成员
from app_my.core.audit import log_audit  # 写审计
# _token_pair 函数签名加 tenant 三元组
def _token_pair(user_id: int, tenant_id: int, tenant_role: str = "owner", tenant_plan: str = "free") -> TokenPair:
    return TokenPair(  # 构造响应 Pydantic 模型
        access_token=create_access_token(user_id, tenant_id=tenant_id, tenant_role=tenant_role, tenant_plan=tenant_plan),
        # access 带 tenant 三元组——业务接口用
        refresh_token=create_refresh_token(user_id),
        # refresh 不带——强制重新登录时确定
        expires_in=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,  # 秒
    )
# register 函数：在 db.refresh(user) 之前插入建租户逻辑
@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.username == data.username))
    if exists:
        raise HTTPException(status_code=409, detail="用户名已被注册")
    user = User(
        username=data.username,
        email=data.email or None,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.flush()  # flush 而非 commit：拿 user.id 但不 commit 事务——下面建租户要复用
    # 🟢 v3阶段4 新增：自动建个人租户
    tenant = Tenant(name=f"{user.username}-个人", type="personal", plan="free", owner_id=user.id)  # 命名加 "-个人" 防重名
    db.add(tenant)
    db.flush()  # 拿 tenant.id
    member = TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner")  # 加成员关系，owner 角色
    db.add(member)
    user.default_tenant_id = tenant.id  # 关联默认租户
    log_audit(db, action="tenant.create", tenant_id=tenant.id, actor_user_id=user.id,
              resource_type="tenant", resource_id=str(tenant.id), payload={"name": tenant.name, "type": "personal"})  # 写审计
    db.commit()  # 整体提交
    db.refresh(user)  # 重读拿默认值（id / created_at）
    return user
# login 函数：拿到 user 之后补 tenant 字段
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    # 🟢 v3阶段4 新增：兜底建租户（老用户迁移路径）
    tenant_id = user.default_tenant_id
    if tenant_id is None:  # 老用户没这字段
        tenant = Tenant(name=f"{user.username}-个人", type="personal", plan="free", owner_id=user.id)
        db.add(tenant)
        db.flush()
        db.add(TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner"))
        user.default_tenant_id = tenant.id
        db.commit()
        db.refresh(user)
        tenant_id = tenant.id  # 拿到新租户 ID
    role = "owner"  # 个人租户默认 owner
    plan = "free"  # 个人租户默认 free
    return _token_pair(user.id, tenant_id, role, plan)
# switch-tenant 接口（文件末尾）
@router.post("/switch-tenant")
def switch_tenant(request: Request, payload: dict, db: Session = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未认证")
    target_id = payload.get("tenant_id")
    if not isinstance(target_id, int):  # 类型校验防恶意 body
        raise HTTPException(status_code=400, detail="tenant_id 必须是整数")
    # 校验：必须是该租户成员
    member = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == target_id) & (TenantMember.user_id == user_id)
        )
    )
    if member is None:
        raise HTTPException(status_code=403, detail="你不是该租户的成员")
    tenant = db.get(Tenant, target_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    # 更新默认租户
    user = db.get(User, user_id)
    user.default_tenant_id = target_id
    log_audit(db, action="auth.switch_tenant", tenant_id=target_id, actor_user_id=user_id,
              resource_type="tenant", resource_id=str(target_id))  # 审计
    db.commit()
    return _token_pair(user_id, target_id, member.role, tenant.plan)  # 返回新 token
```

### 9.2 `app_my/api/chat.py` 改造（透传 tenant_id）

```python
# app_my/api/chat.py
from fastapi import APIRouter, Request
from app_my.schemas.chat import ChatRequest
from starlette.responses import StreamingResponse
from app_my.agents.coordinator import chat_coordinator
router = APIRouter()
@router.post("/stream")
async def chat_endpoint(request: Request, payload: ChatRequest):  # 把 Request 显式拿出来
    tenant_id = getattr(request.state, "tenant_id", None)  # 中间件已注入
    return StreamingResponse(
        chat_coordinator(
            text=payload.message,
            image_url=payload.image_url,
            thread_id=payload.thread_id,
            user_id=payload.user_id,
            tenant_id=tenant_id,  # 🟢 透传给 coordinator
        ),
        media_type="text/event-stream",
    )
```

### 9.3 `app_my/api/billing.py` 改造（按租户统计）

```python
# app_my/api/billing.py
from fastapi import APIRouter, Request
from app_my.core.token_billing import get_billing_stats
router = APIRouter()
@router.get("/stats")
async def billing_stats(request: Request):  # 加 Request 参数
    tenant_id = getattr(request.state, "tenant_id", None)  # 中间件已注入
    return get_billing_stats(tenant_id=tenant_id)  # 按租户统计；None 表示全量（兼容老调用）
```

### 9.4 `app_my/api/kg.py` 改造（要求登录租户）

```python
# app_my/api/kg.py
from fastapi import APIRouter, Query, Request, HTTPException
from app_my.core import kg as kg_module

router = APIRouter()

@router.get("/ask")
async def kg_ask(
    request: Request,
    ingredient: str = Query(..., min_length=1, max_length=30, description="食材名，如：土豆"),
    condition: str = Query(..., min_length=1, max_length=30, description="健康状况名，如：糖尿病/痛风/高血压"),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:  # 必须登录
        raise HTTPException(status_code=401, detail="需要登录租户才能调用")
    return kg_module.ask(ingredient.strip(), condition.strip())  # 原逻辑不变
```

### 9.5 `app_my/api/tenant.py`（新增租户管理接口）

```python
# app_my/api/tenant.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func  # func 给 count() 用
from sqlalchemy.orm import Session
from app_my.core.audit import log_audit
from app_my.core.quota import QUOTAS, get_usage  # 配额档位 + 已用量
from app_my.db.models.user import User
from app_my.db.models.tenant import Tenant
from app_my.db.models.tenant_member import TenantMember
from app_my.db.session import get_db
from app_my.schemas.tenant import (MemberInviteIn, MemberOut, QuotaOut, TenantCreateIn, TenantOut)
router = APIRouter()
def _user_role(db: Session, tenant_id: int, user_id: int) -> str | None:
    # 查用户在某租户的角色；返回 None 表示不是成员
    m = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == user_id)
        )
    )
    return m.role if m else None
@router.get("", response_model=List[TenantOut])
def list_my_tenants(request: Request, db: Session = Depends(get_db)):
    # 我的租户列表：JOIN tenant_members 查我作为成员的租户
    user_id = getattr(request.state, "user_id", None)
    rows = db.scalars(
        select(Tenant, TenantMember.role)
        .join(TenantMember, TenantMember.tenant_id == Tenant.id)
        .where(TenantMember.user_id == user_id)
    ).all()
    return [TenantOut(id=t.id, name=t.name, type=t.type, plan=t.plan, role=r) for (t, r) in rows]
@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(request: Request, payload: TenantCreateIn, db: Session = Depends(get_db)):
    # 创建团队租户（owner=当前用户）
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未认证")
    t = Tenant(name=payload.name, type="team", plan="free", owner_id=user_id)
    db.add(t)
    db.flush()  # 拿 id
    db.add(TenantMember(tenant_id=t.id, user_id=user_id, role="owner"))  # 加成员
    log_audit(db, action="tenant.create", tenant_id=t.id, actor_user_id=user_id,
              resource_type="tenant", resource_id=str(t.id), payload={"name": t.name, "type": "team"})
    db.commit()
    return TenantOut(id=t.id, name=t.name, type=t.type, plan=t.plan, role="owner")
@router.get("/{tenant_id}/quota", response_model=QuotaOut)
def get_quota(request: Request, tenant_id: int, db: Session = Depends(get_db)):
    # 配额用量：成员可看自己租户的（不限于 owner）
    user_id = getattr(request.state, "user_id", None)
    role = _user_role(db, tenant_id, user_id)
    if role is None:
        raise HTTPException(status_code=403, detail="不是该租户成员")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    plan = tenant.plan
    metrics = {m: {"used": get_usage(tenant_id, m), "limit": lim} for m, lim in QUOTAS.get(plan, QUOTAS["free"]).items()}
    return QuotaOut(plan=plan, metrics=metrics)
@router.post("/{tenant_id}/members", response_model=MemberOut, status_code=201)
def invite_member(request: Request, tenant_id: int, payload: MemberInviteIn, db: Session = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    role = _user_role(db, tenant_id, user_id)
    if role not in ("owner", "admin"):  # owner/admin 才能邀请
        raise HTTPException(status_code=403, detail="需要 owner 或 admin 权限")
    target = db.scalar(select(User).where(User.username == payload.username))
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 配额：成员上限
    tenant = db.get(Tenant, tenant_id)
    limit = QUOTAS.get(tenant.plan, QUOTAS["free"])["max_members"]
    n = db.scalar(select(func.count(TenantMember.id)).where(TenantMember.tenant_id == tenant_id)) or 0
    if n >= limit:
        raise HTTPException(status_code=429, detail=f"成员数已达上限 {limit}；升级套餐或移除成员")
    exists = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == target.id)
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="该用户已是成员")
    m = TenantMember(tenant_id=tenant_id, user_id=target.id, role=payload.role)
    db.add(m)
    log_audit(db, action="tenant.invite", tenant_id=tenant_id, actor_user_id=user_id,
              resource_type="user", resource_id=str(target.id), payload={"role": payload.role})
    db.commit()
    return MemberOut(user_id=target.id, username=target.username, role=m.role, joined_at=m.joined_at.isoformat())
@router.delete("/{tenant_id}/members/{member_user_id}", status_code=204)
def remove_member(request: Request, tenant_id: int, member_user_id: int, db: Session = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    role = _user_role(db, tenant_id, user_id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="需要 owner 或 admin 权限")
    if member_user_id == user_id:  # 不能移除自己
        raise HTTPException(status_code=400, detail="不能移除自己")
    m = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == member_user_id)
        )
    )
    if m is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    db.delete(m)
    log_audit(db, action="tenant.remove_member", tenant_id=tenant_id, actor_user_id=user_id,
              resource_type="user", resource_id=str(member_user_id))
    db.commit()
    return None
```

### 9.6 `app_my/api/admin.py`（新增管理端接口）

```python
# app_my/api/admin.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app_my.core.audit import log_audit
from app_my.core.feature_flag import invalidate_cache  # 改 flag 时清缓存
from app_my.db.models.audit_log import AuditLog
from app_my.db.models.feature_flag import FeatureFlag
from app_my.db.session import get_db
from app_my.schemas.admin import AuditLogOut, FeatureFlagOut, FeatureFlagUpdateIn
router = APIRouter()
def _require_admin(request: Request, db: Session, tenant_id: int):
    # admin 路由要求当前用户在该 tenant 是 owner 或 admin；403 防御
    from app_my.db.models.tenant_member import TenantMember
    user_id = getattr(request.state, "user_id", None)
    m = db.scalar(
        select(TenantMember).where(
            (TenantMember.tenant_id == tenant_id) & (TenantMember.user_id == user_id)
        )
    )
    if m is None or m.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="需要 owner 或 admin 权限")
    return user_id
@router.get("/audit/logs", response_model=List[AuditLogOut])
def list_audit_logs(request: Request, tenant_id: int, db: Session = Depends(get_db), limit: int = 50):
    _require_admin(request, db, tenant_id)  # 权限校验
    rows = db.scalars(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()
    return [AuditLogOut(...) for r in rows]  # 构造响应
@router.get("/feature-flags", response_model=List[FeatureFlagOut])
def list_flags(db: Session = Depends(get_db)):
    rows = db.scalars(select(FeatureFlag).order_by(FeatureFlag.name)).all()
    # 解析 whitelist JSON；fail 时降级 []
    return [...]
@router.post("/feature-flags/{name}", response_model=FeatureFlagOut)
def upsert_flag(name: str, payload: FeatureFlagUpdateIn, db: Session = Depends(get_db)):
    import json
    row = db.scalar(select(FeatureFlag).where(FeatureFlag.name == name))
    if row is None:  # 不存在则新建
        row = FeatureFlag(name=name)
        db.add(row)
    row.enabled = payload.enabled
    row.rollout_pct = payload.rollout_pct
    row.whitelist_tenants = json.dumps(payload.whitelist)  # 转 JSON 字符串
    row.description = payload.description
    db.commit()
    invalidate_cache(name)  # 清缓存让下一请求读新值
    log_audit(db, action="feature_flag.update", actor_user_id=None, resource_type="feature_flag", resource_id=name,
              payload={"enabled": payload.enabled, "rollout_pct": payload.rollout_pct})  # 全局操作 actor=None
    return FeatureFlagOut(...)
```

---

## 十、`main.py` 中间件链顺序

```python
# main.py
# Starlette 规则：后 add 的包在外层。本阶段中间件链（请求方向）：
# CORS → Trace → Auth → Tenant → UserLimit → RateLimit → Quota → 路由
app.add_middleware(QuotaMiddleware)                  # 5. 租户配额（最里层）
app.add_middleware(RateLimitMiddleware)              # 4. 全局 IP 限流
app.add_middleware(UserRateLimitMiddleware)          # 3. 用户级限流
app.add_middleware(TenantContextMiddleware)          # 2.5 租户上下文（v3阶段4 新增）
app.add_middleware(AuthMiddleware)                   # 2. JWT 鉴权
app.add_middleware(TraceIdMiddleware)                # 1. TraceID
app.add_middleware(CORSMiddleware, ...)              # 0. CORS 最外层
# 为什么 Tenant 在 Auth 之后：TenantContextMiddleware 需要读 token_payload；Auth 还没跑就没有
# 为什么 Quota 在最里层：配额是业务规则最里层——比用户/IP 限流更细
# 为什么 CORS 最外层：CORS 处理跨域预检，跨域 OPTIONS 请求不应该被限流/鉴权挡
```

---

## 十一、测试逐行解读

`tests/unit/test_quota.py`：

```python
# tests/unit/test_quota.py
# 用 FakeRedis monkeypatch get_redis——不依赖真实 Redis；CI 可跑
class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}  # 用普通 dict 模拟 Redis hash
    def incrby(self, key, n):
        self.store[key] = self.store.get(key, 0) + n  # 模拟 INCRBY
        return self.store[key]
    def expire(self, key, ttl):
        pass  # 测试里不验证过期
    def get(self, key):
        return self.store.get(key)  # 模拟 GET
    def delete(self, key):
        self.store.pop(key, None)  # 模拟 DEL
@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(quota, "get_redis", lambda: fr)  # monkeypatch 替换 get_redis 函数
    return fr
def test_incr_and_get(fake_redis):
    quota.incr_usage(1, "chat_daily", 3)  # 加 3
    assert quota.get_usage(1, "chat_daily") == 3  # 验证 3
def test_check_quota_under(fake_redis):
    ok, _, lim = quota.check_quota(1, "free", "chat_daily")
    assert ok is True  # 没超
    assert lim == 50  # free 上限 50
def test_check_quota_over(fake_redis):
    for _ in range(50):  # 加到 50
        quota.incr_usage(2, "chat_daily")
    ok, used, lim = quota.check_quota(2, "free", "chat_daily")
    assert ok is False  # 超了
    assert used == 50
    assert lim == 50
def test_get_limit_unknown(fake_redis):
    assert quota.get_limit("unknown_plan", "chat_daily") == 50  # 未知 plan 兜底 free
def test_reset(fake_redis):
    quota.incr_usage(3, "chat_daily", 10)
    quota.reset_usage(3, "chat_daily")  # 重置
    assert quota.get_usage(3, "chat_daily") == 0
```

`tests/unit/test_feature_flag.py`：

```python
# tests/unit/test_feature_flag.py
# 用内存 SQLite 跑——SQLAlchemy 通用，不需要 Postgres
@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")  # 内存数据库
    Base.metadata.create_all(engine)  # 建表
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
def _make(s, name, enabled=True, pct=0, wl=None):
    f = FeatureFlag(name=name, enabled=enabled, rollout_pct=pct, whitelist_tenants=json.dumps(wl or []))
    s.add(f)
    s.commit()
    invalidate_cache(None)  # 清缓存
    return f
def test_disabled(db):
    _make(db, "x", enabled=False, pct=100)  # enabled=False
    assert is_feature_enabled(db, "x", 1) is False  # 任何 tenant 都不开
def test_whitelist(db):
    _make(db, "x", enabled=True, pct=0, wl=[1, 2])  # 白名单 [1,2]
    assert is_feature_enabled(db, "x", 1) is True  # 白名单命中
    assert is_feature_enabled(db, "x", 999) is False  # 不在白名单 + pct=0
def test_rollout_pct_0(db):
    _make(db, "x", enabled=True, pct=0)
    assert is_feature_enabled(db, "x", 1) is False  # 0% 全员不开
def test_rollout_pct_100(db):
    _make(db, "x", enabled=True, pct=100)
    assert is_feature_enabled(db, "x", 1) is True  # 100% 全员开
def test_missing_flag(db):
    assert is_feature_enabled(db, "no_such_flag", 1) is False  # 不存在 = 关
```

---

## 十二、面试可能被追问的点

**Q1：多租户隔离的"共享库+列"方案会不会有性能问题？**

A：会——`tenant_id` 列必须加索引，每次查询都带 `WHERE tenant_id = ?`；如果某租户数据特别多，可能成为热点。本项目租户规模小（个人项目），性能 OK；商业化（千租户）要分库/分 schema。

**Q2：为什么配额用固定窗口不用滑动窗口？**

A：滑动窗口用 ZSET 存时间戳，内存放大 N 倍（每次请求一个元素）；固定窗口跨天自然换键无需清理。2 倍边界突发可接受（配额本身冗余）。算法选型见 §3。

**Q3：审计日志为什么 API 层显式调而不用中间件？**

A：中间件只能拿 path/method，拿不到"邀请了谁""改了什么资源"；审计需要业务参数。本项目审计字段需要 actor_user_id / resource_id / payload 这些只有 API 层才有的信息。

**Q4：Feature Flag 缓存 60s 太长怎么办？**

A：改 flag 后主动调 `invalidate_cache(name)`——缓存只在 invalidate 后第一次是数据进来，不是 60s 后才看到。60s 是兜底（管理员忘了 invalidate）。

**Q5：JWT 切换租户为什么不撤销旧 token？**

A：撤销会让"刚切换的 token 立刻失效"用户体验差——用户每切一次租户就要重新登录。JWT 30 分钟自然过期足够短，切换频率低，泄漏窗口可接受。

**Q6：为什么 `tenant_id` 不从前端传参？**

A：前端传参 = 用户可控 = 越权。`tenant_id` 必须从 JWT 解析（服务端拿 payload），前端只能传"我想切换到哪个租户"——再由 `/auth/switch-tenant` 校验"我是不是这个租户成员"，通过后服务端重新签发带新 tenant_id 的 token。这是数据隔离的命门。

**Q7：老用户怎么迁移？**

A：本项目用"应用层兜底"——`/auth/login` 时检查 `user.default_tenant_id`，空就建个人租户并绑定。比 ALTER TABLE 安全（不会在升级过程中让老用户在更新线上）。阶段 5 引入 PgBouncer 后会再写一段启动时批量迁移脚本（把 `default_tenant_id IS NULL` 的用户全部建租户）。

**Q8：配额超限 429 是怎么传给前端的？**

A：返回结构化 JSON `{detail, metric, used, limit, upgrade_hint}` + `Retry-After: 86400` 头；前端用 `response.status === 429` 判断，弹个 toast"今天对话次数用完了，明天再来 / 升级套餐"。这个约定比阶段 4 的限流（只带 Retry-After）信息密度更高。

---

> **配套阅读**：操作手册讲"照着做"，本手册讲"为什么"；阶段 5 开工后会以本手册为基线继续演进。