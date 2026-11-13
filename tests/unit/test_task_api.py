# tests/unit/test_task_api.py  —— v3 阶段 8：任务提交/查询接口
"""
覆盖点：
1. 不登录取不到任务接口（401）；
2. 三个提交接口都返回 task_id + 正确的队列名（high/default/low）；
3. 营养报告参数校验（空列表 → 422）；
4. GET /tasks/{id} 能正确翻译 SUCCESS / FAILURE 两种状态。

手法说明：这里把"任务对象的 .delay"换成假的，只验证接口契约，
    不真的投递任务（真投递的验证在 test_celery_app.py 的 eager 用例里做）。
    monkeypatch 的目标是 "app_my.api.tasks.reindex_milvus" —— 也就是 api 模块里
    那三个 import 进来的名字，替换它们等于换掉接口看到的任务对象。
"""
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app_my.core.security import create_access_token
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers():
    token = create_access_token(subject=1, tenant_id=1, tenant_role="owner", tenant_plan="free")
    return {"Authorization": f"Bearer {token}"}


def _stub_task(task_id: str):
    """假任务对象：只有一个 .delay()，返回带 id 的东西，模拟 Celery 投递后的返回"""
    class _Stub:
        def delay(self, **kwargs):
            return SimpleNamespace(id=task_id)
    return _Stub()


def test_submit_requires_auth(client):
    r = client.post("/tasks/nutrition-report", json={"ingredients": ["鸡蛋 2个"]})
    assert r.status_code == 401


def test_submit_nutrition_report(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app_my.api.tasks.generate_nutrition_report", _stub_task("fake-nutrition-001"))
    r = client.post("/tasks/nutrition-report", json={"ingredients": ["鸡蛋 2个"]}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == "fake-nutrition-001"
    assert body["name"] == "tasks.generate_nutrition_report"
    assert body["queue"] == "low"
    assert body["status"] == "PENDING"


def test_submit_nutrition_report_rejects_empty_list(client, auth_headers):
    r = client.post("/tasks/nutrition-report", json={"ingredients": []}, headers=auth_headers)
    assert r.status_code == 422          # Pydantic min_length=1 拦住了


def test_submit_reindex_uses_high_queue(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app_my.api.tasks.reindex_milvus", _stub_task("fake-reindex-002"))
    r = client.post("/tasks/reindex-milvus", json={"rebuild": False}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["queue"] == "high"


def test_submit_rebuild_kg_uses_default_queue(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app_my.api.tasks.rebuild_kg_graph", _stub_task("fake-kg-003"))
    r = client.post("/tasks/rebuild-kg", json={"rebuild": False}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["queue"] == "default"


def test_get_task_status_success(client, auth_headers, monkeypatch):
    class _FakeResult:
        status = "SUCCESS"
        result = {"rows": 60, "row_count": 60}

        def successful(self):
            return True

        def failed(self):
            return False

    monkeypatch.setattr("app_my.api.tasks.AsyncResult", lambda task_id, app=None: _FakeResult())
    r = client.get("/tasks/whatever", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "SUCCESS"
    assert r.json()["result"]["rows"] == 60


def test_get_task_status_failure(client, auth_headers, monkeypatch):
    class _FakeResult:
        status = "FAILURE"
        result = RuntimeError("Milvus 不可用：清场失败")

        def successful(self):
            return False

        def failed(self):
            return True

    monkeypatch.setattr("app_my.api.tasks.AsyncResult", lambda task_id, app=None: _FakeResult())
    r = client.get("/tasks/whatever", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "FAILURE"
    assert "Milvus" in r.json()["error"]


def test_get_task_status_requires_auth(client):
    """查任务状态同样要登录"""
    r = client.get("/tasks/whatever")
    assert r.status_code == 401