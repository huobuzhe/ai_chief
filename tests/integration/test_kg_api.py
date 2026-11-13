# tests/integration/test_kg_api.py
"""
阶段 3 集成测试：/kg/ask 图谱推理接口（需要后端在跑 + Neo4j 容器 + 已建图）

跑法（与 llm 标记一样单独跑）：
    pytest tests/integration/test_kg_api.py -m kg -q

前置：
    1. docker compose -f docker/docker-compose.v3.yml up -d   （含 neo4j 服务）
    2. python scripts/init_kg.py                               （建图）
    3. 后端在跑（python main.py）
"""
import pytest

pytestmark = pytest.mark.kg


def test_kg_ask_requires_auth(base_url):
    """不带 token 访问必须 401——推理结论虽是科普，接口本身不能裸奔"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask", params={"ingredient": "土豆", "condition": "糖尿病"}, timeout=15
    )
    assert resp.status_code == 401


def test_kg_ask_potato_diabetes(base_url, account):
    """验收场景：糖尿病患者能不能吃土豆——三段证据齐全"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask",
        params={"ingredient": "土豆", "condition": "糖尿病"},
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["graph_available"] is True
    assert data["verdict"] == "建议控制食用量"          # kg_facts 里土豆对糖尿病是"限量"
    assert "GI" in data["reason"] or "血糖" in data["reason"]
    assert data["affected_recipes"], "土豆相关菜谱应非空（库里至少两道）"
    assert any(item["nutrient"] == "碳水" for item in data["nutrients"])


def test_kg_ask_alias_condition(base_url, account):
    """别名检索：condition=高血糖 也能命中 糖尿病 节点（aka 边）"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask",
        params={"ingredient": "可乐", "condition": "高血糖"},
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "不建议食用"        # 可乐对糖尿病是"避免"


def test_kg_ask_unknown_pair_is_honest(base_url, account):
    """图谱没收录的关系要诚实说"未发现"，不能编造（与幻觉的区别所在）"""
    import requests

    resp = requests.get(
        f"{base_url}/kg/ask",
        params={"ingredient": "西红柿", "condition": "痛风"},
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "未发现禁忌关联"