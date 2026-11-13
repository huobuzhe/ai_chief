# tests/integration/test_billing_api.py
"""
阶段 2 集成测试：/billing/stats 成本统计接口（需要后端在跑）
- 接口必须受 JWT 保护：不带 token 401
- 登录后返回完整的三段结构：totals / models / routing
"""
import requests


def test_billing_stats_requires_auth(base_url):
    """不带 token 访问必须 401——成本数据不能裸奔"""
    resp = requests.get(f"{base_url}/billing/stats", timeout=15)
    assert resp.status_code == 401


def test_billing_stats_shape(base_url, account):
    """带 token 访问：返回结构完整（数字可能是 0，但字段必须在）"""
    resp = requests.get(
        f"{base_url}/billing/stats",
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "totals" in data
    assert "models" in data
    assert "routing" in data
    for field in ("calls", "input_tokens", "output_tokens", "errors", "estimated_cost_cny"):
        assert field in data["totals"]
    for field in ("all_standard_baseline_cny", "actual_cost_cny", "saved_percent"):
        assert field in data["routing"]