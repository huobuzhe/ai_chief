# scripts/verify_stage5.py
"""
阶段 5 分步验证脚本（手册各章"验证"统一走它，避免 PowerShell 粘贴引号被吃）。

用法（项目根目录执行）：
    uv run python scripts/verify_stage5.py <子命令>

子命令：
    deps      容器状态（pgvector/redis/pgbouncer）
    pgb       通过 9432 完成真实 SQL + SHOW POOLS 看池子
    routing   双引擎构建 + SELECT/INSERT 分流正确
    cache     三件套逻辑（命中/并发单飞/空值/抖动）
    api       /cache/stats 接口（需后端已启动 + 能登录）
    all       以上全部（提测用）
"""
import sys
import threading
import time
import urllib.request
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[OK]  " if ok else "[FAIL]"
    msg = f"{tag} {name}" + (f"  ->  {detail}" if detail else "")
    print(msg)
    RESULTS.append(ok)
    return ok


def check_deps() -> None:
    import subprocess
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    ).stdout
    for c in ("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer"):
        report(f"容器 {c} 运行中", c in out.splitlines(), "" if c in out.splitlines()
               else "docker compose -f docker/docker-compose.v3.yml up -d")


def check_pgb() -> None:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost", port=9432, dbname="ai_sichu",
            user="ai_sichu", password="ai_sichu", connect_timeout=5,
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        report("通过 9432(PgBouncer) 执行 SELECT 1", cur.fetchone()[0] == 1)
        cur.execute("SELECT count(*) FROM users")
        report("经 PgBouncer 查 users 表", True, f"行数 {cur.fetchone()[0]}")
        conn.close()

        admin = psycopg2.connect(
            host="localhost", port=9432, dbname="pgbouncer",
            user="ai_sichu", password="ai_sichu", connect_timeout=5,
        )
        admin.autocommit = True   # =========【新增】关闭事务，不发送BEGIN
        cur = admin.cursor()
        cur.execute("SHOW POOLS")
        rows = cur.fetchall()
        report("SHOW POOLS 可用（连接池观测）", len(rows) > 0, str(rows[:1]))
        admin.close()
    except Exception as e:
        report("PgBouncer 连接失败", False, f"{type(e).__name__}: {e}")


def check_routing() -> None:
    try:
        from sqlalchemy import text
        from app_my.db.session import read_engine, write_engine, engine, SessionLocal
        report("双引擎已构建", True,
               f"write={write_engine.url.render_as_string(hide_password=False).split('@')[1]}")
        db = SessionLocal()
        val = db.execute(text("SELECT 1")).scalar()
        db.close()
        report("RoutingSession 经 PgBouncer 查询", val == 1)
        report("engine 兼容别名仍指向写引擎", engine is write_engine)
    except Exception as e:
        report("路由检查失败", False, f"{type(e).__name__}: {e}")


def check_cache() -> None:
    try:
        from app_my.core import cache as cache_mod
        from app_my.core.cache import cached, cache_stats

        calls = {"n": 0}

        @cached(prefix="verify", ttl=60)
        def slow(q):
            calls["n"] += 1
            time.sleep(0.2)
            return [q]

        slow("x")
        slow("x")
        report("缓存命中（数据源只执行 1 次）", calls["n"] == 1)

        calls["n"] = 0

        def worker():
            slow("y")

        threads = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        report("singleflight：8 并发只穿透 1 次", calls["n"] == 1)

        ttls = {cache_mod._jitter_ttl(100) for _ in range(200)}
        report("TTL 抖动在 ±10% 内", 90 <= min(ttls) and max(ttls) <= 110)

        s = cache_stats()
        report("统计可读（含命中率）", "hit_rate" in s, str(s))
    except Exception as e:
        report("缓存检查失败", False, f"{type(e).__name__}: {e}")


def check_api() -> None:
    base = "http://127.0.0.1:9002"
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=3) as resp:
            report("后端存活", json.loads(resp.read()).get("status") == "ok")

        req = urllib.request.Request(
            f"{base}/cache/stats",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzNyIsInR5cGUiOiJhY2Nlc3MiLCJqdGkiOiI1NDA1YzM0NTkxMGU0ZTYxYTM4MTRjM2EyZGRmYmI0MSIsImlhdCI6MTc5MTgwMDMzMywiZXhwIjoxNzkxODAyMTMzLCJ0ZW5hbnRfaWQiOjE2LCJ0ZW5hbnRfcm9sZSI6Im93bmVyIiwidGVuYW50X3BsYW4iOiJmcmVlIn0.0D7QwEVAM08nqouI9TQjvhku6NoigSETtF4Zdrw0j8Q"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read())
            report("/cache/stats 可访问", "hit_rate" in body)
        except urllib.error.HTTPError as e:
            report("/cache/stats 可访问", False,
                   f"HTTP {e.code}（401=先登录换 token 填进脚本）")
    except Exception as e:
        report("API 检查失败", False, f"{type(e).__name__}: {e}")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    checks = {
        "deps": check_deps, "pgb": check_pgb, "routing": check_routing,
        "cache": check_cache, "api": check_api,
    }
    if cmd == "all":
        for fn in checks.values():
            fn()
    else:
        checks[cmd]()
    print()
    print(f"结果：{sum(RESULTS)} 通过 / {len(RESULTS) - sum(RESULTS)} 失败")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())