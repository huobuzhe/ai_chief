"""
阶段 7 验证脚本：5 个容器 + /metrics 端点 + 指标存在性
用法：
  python scripts/verify_stage7.py all         # 跑全部子检查
  python scripts/verify_stage7.py containers  # 只查 5 个容器在跑
  python scripts/verify_stage7.py metrics     # 只查 /metrics 端点
  python scripts/verify_stage7.py prometheus  # 只查 Prometheus 在抓后端
"""
import json
import sys
import time
from urllib import request as urlreq, error as urlerr


def report(name, ok, detail=""):
    flag = "[OK]  " if ok else "[FAIL]"
    print(f"{flag} {name:<40} {detail}")
    return 1 if ok else 0


def http_get(url, timeout=10):
    try:
        with urlreq.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def check_containers():
    n_ok = 0
    for svc, url, expected in [
        ("prometheus",    "http://127.0.0.1:9090/-/ready", 'Prometheus Server is Ready.'),
        ("grafana",       "http://127.0.0.1:3300/api/health", '"database": "ok"'),
        ("alertmanager",  "http://127.0.0.1:9093/-/ready", "OK"),
        ("loki",         "http://127.0.0.1:3100/ready",   "ready"),
    ]:
        code, body = http_get(url)
        ok = code == 200 and expected in body
        n_ok += report(f"{svc} 健康", ok, f"code={code} body={body[:60]}")
    # promtail 不暴露 HTTP 端口健康检查——查容器日志
    return n_ok, 4, 0


def check_metrics():
    n_ok = 0
    code, body = http_get("http://127.0.0.1:9002/metrics")
    if code != 200:
        return report("/metrics 端点", False, f"code={code}"), 0, 1
    n_ok += report("/metrics 端点", True, f"len={len(body)} bytes")
    for metric in ["http_requests_total", "http_request_duration_seconds",
                   "llm_tokens_total", "llm_cost_cny_total"]:
        ok = metric in body
        n_ok += report(f"指标 {metric} 存在", ok)
    return n_ok, 5, 0


def check_prometheus():
    code, body = http_get("http://127.0.0.1:9090/api/v1/targets")
    if code != 200:
        return report("Prometheus /targets", False, f"code={code}"), 0, 1
    try:
        data = json.loads(body)
        targets = data["data"]["activeTargets"]
        backend = [t for t in targets if t["labels"].get("job") == "ai_chief_backend"]
        if not backend:
            return report("Prometheus 抓后端", False, "未找到 ai_chief_backend job"), 0, 1
        health = backend[0]["health"]
        n_ok = report("Prometheus 抓后端 (ai_chief_backend)", health == "up", f"health={health}")
        # 告警规则数
        rules_code, rules_body = http_get("http://127.0.0.1:9090/api/v1/rules")
        rules_count = len(json.loads(rules_body)["data"]["groups"][0]["rules"]) if rules_code == 200 else 0
        n_ok += report("告警规则加载", rules_count == 4, f"rules_count={rules_count}")
        return n_ok, 2, 0
    except Exception as exc:
        return report("解析 /targets 失败", False, str(exc)), 0, 1


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "all":
        checks = [check_containers, check_metrics, check_prometheus]
    elif sys.argv[1] == "containers":
        checks = [check_containers]
    elif sys.argv[1] == "metrics":
        checks = [check_metrics]
    elif sys.argv[1] == "prometheus":
        checks = [check_prometheus]
    else:
        print(f"未知子命令: {sys.argv[1]}")
        return 2

    all_ok, all_total = 0, 0
    for fn in checks:
        ok, total, _ = fn()
        all_ok += ok
        all_total += total
    print(f"\n结果：{all_ok} 通过 / {all_total - all_ok} 失败")
    return 0 if all_ok == all_total else 1


if __name__ == "__main__":
    sys.exit(main())