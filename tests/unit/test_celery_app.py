# tests/unit/test_celery_app.py  —— v3 阶段 8：Celery 配置与任务执行（不依赖 worker）
"""
覆盖点：
1. broker / result backend 真的落在 Redis 6380 的 db1 / db2（与业务 db0 隔离）；
2. 三条队列 high/default/low 声明齐全；
3. 三个任务名都注册了，且路由到正确队列；
4. eager 模式下营养任务真跑通、返回真实营养数字；
5. 参数不合法时任务真失败、并且 FAILURE 指标 +1。
"""
import pytest

from app_my.core.worker_metrics import CELERY_TASK_FAILURES
from app_my.worker.celery_app import celery_app

NUTRITION = "tasks.generate_nutrition_report"
REINDEX = "tasks.reindex_milvus"
KG = "tasks.rebuild_kg_graph"


@pytest.fixture()
def eager():
    """把 Celery 切到"调用即本地执行"模式，跑完恢复原值（不影响其它用例）"""
    old = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = old


@pytest.fixture()
def eager_non_propagating():
    """
    eager + 不抛异常的组合，专门用来验证"失败路径"。

    为什么失败用例必须关掉 task_eager_propagates：
        Celery 在 eager 模式下如果开着 propagate，异常会立刻原样抛出（方便测试断言异常），
        但代价是"跳过" on_failure 通知这条链（源码 trace.py 的 on_error 里 `if propagate: raise`）。
        要看到 FAILURE 指标和通知，就得关掉 propagate，让 Celery 走正常的失败处理流程。
    """
    old_eager = celery_app.conf.task_always_eager
    old_prop = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield
    celery_app.conf.task_always_eager = old_eager
    celery_app.conf.task_eager_propagates = old_prop


def test_broker_and_backend_are_isolated_redis_dbs():
    """broker 用 db1、backend 用 db2 —— 与业务缓存的 db0 分开"""
    assert celery_app.conf.broker_url == "redis://localhost:6380/1"
    assert celery_app.conf.result_backend == "redis://localhost:6380/2"


def test_three_queues_declared():
    """三条分级队列必须在"""
    names = {q.name for q in celery_app.conf.task_queues}
    assert names == {"high", "default", "low"}


def test_tasks_registered_and_routed():
    """三个任务已注册，且路由到各自队列"""
    for name in (NUTRITION, REINDEX, KG):
        assert name in celery_app.tasks, f"{name} 未注册"
    assert celery_app.conf.task_routes[REINDEX] == {"queue": "high"}
    assert celery_app.conf.task_routes[KG] == {"queue": "default"}
    assert celery_app.conf.task_routes[NUTRITION] == {"queue": "low"}


def test_serializer_is_json():
    """任务参数/结果必须是 JSON 序列化（安全：不用 pickle）"""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_nutrition_task_runs_eager_and_returns_real_numbers(eager):
    """营养任务在本地同步跑一遍：返回结构完整、数字是真实计算值"""
    from app_my.worker.tasks.nutrition import generate_nutrition_report

    r = generate_nutrition_report.delay(ingredients=["鸡胸肉 200克", "西兰花 1颗"], tenant_id=1, user_id=1)
    assert r.state == "SUCCESS"
    data = r.get()
    assert data["ingredients"] == ["鸡胸肉 200克", "西兰花 1颗"]
    assert data["coverage"] == 1.0                       # 两个食材都命中营养库
    assert data["total_estimated"]["calories"] > 0       # 热量算出来了
    assert "千卡" in data["summary"]


def test_nutrition_task_fails_on_empty_ingredients(eager_non_propagating, monkeypatch):
    """空食材 → 任务状态 FAILURE、失败指标 +1、且发出 FAILURE 通知（带正确的 tenant）"""
    from app_my.worker import base
    from app_my.worker.tasks.nutrition import generate_nutrition_report

    captured = []
    monkeypatch.setattr(base, "publish_task_event", lambda payload: (captured.append(payload), 1)[1])

    before = CELERY_TASK_FAILURES.labels(task=NUTRITION)._value.get()
    r = generate_nutrition_report.delay(ingredients=[], tenant_id=3, user_id=5)
    after = CELERY_TASK_FAILURES.labels(task=NUTRITION)._value.get()

    assert r.state == "FAILURE"                       # 状态是失败
    assert after - before == 1.0                      # 失败计数 +1
    assert captured[-1]["status"] == "FAILURE"        # 发了 FAILURE 通知
    assert captured[-1]["tenant_id"] == 3             # 通知带对了租户（推给谁）
    assert "ValueError" in captured[-1]["error"]      # 错误摘要有内容