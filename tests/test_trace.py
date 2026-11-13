# test_trace.py - 可观测性测试（阶段 7）：trace_id 生成与透传
import requests


def test_trace_id_generated(base_url):
    """每个响应都自动带 X-Trace-Id 头（阶段 6 可观测性）"""
    resp = requests.get(f"{base_url}/health", timeout=10)
    assert resp.status_code == 200
    assert resp.headers.get("x-trace-id"), "响应头缺少 X-Trace-Id"


def test_trace_id_passthrough(base_url):
    """上游传入的 X-Trace-Id 应原样透传：跨服务串联链路"""
    resp = requests.get(f"{base_url}/health", headers={"X-Trace-Id": "pytest-trace-001"}, timeout=10)
    assert resp.headers.get("x-trace-id") == "pytest-trace-001"


def test_trace_id_unique_per_request(base_url):
    """两次请求的 trace_id 不能相同"""
    r1 = requests.get(f"{base_url}/health", timeout=10)
    r2 = requests.get(f"{base_url}/health", timeout=10)
    assert r1.headers["x-trace-id"] != r2.headers["x-trace-id"]