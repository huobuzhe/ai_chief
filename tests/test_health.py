# test_health.py - 健康检查冒烟测试（阶段 7）
import requests


def test_health_ok(base_url):
    """GET /health 返回 200 且 status=ok：服务活着、路由挂载正常"""
    resp = requests.get(f"{base_url}/health", timeout=10)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"