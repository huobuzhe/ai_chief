# scripts/verify_stage8.py —— v3 阶段 8 验收脚本（两种模式）
#
#   模式一 routing：验证"任务分级路由"是否真的把三个任务送进 high / default / low
#                   —— 只需要 Redis 在跑，不需要 worker、不需要 API
#                   🔴 跑之前请先停掉 worker（否则任务被 worker 消费走，队列会是 0）
#
#   模式二 e2e    ：验证端到端链路：提交任务 → worker 执行 → Redis pub/sub → 中继 → WebSocket
#                   —— 需要 API(9002) + worker 都在跑
#
# 用法（在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#   .\.venv3\Scripts\python.exe scripts\verify_stage8.py routing
#   .\.venv3\Scripts\python.exe scripts\verify_stage8.py e2e
import asyncio
import json
import os
import sys

# 把项目根目录塞进 sys.path。
# 为什么需要：直接 `python scripts\verify_stage8.py` 时，Python 只把 scripts\ 当作模块搜索路径，
# 于是 `import app_my...` 会报 ModuleNotFoundError: No module named 'app_my'。
# 这两行把"脚本所在目录的上一级"（= 项目根）加进去，无论从哪个目录调用都能跑通。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

DEMO_INGREDIENTS = ["鸡蛋 100克", "西兰花 200克"]


# ============================================================ 模式一：分级路由
def mode_routing() -> int:
    import redis
    from app_my.worker.celery_app import celery_app
    from app_my.worker.tasks.graph import rebuild_kg_graph
    from app_my.worker.tasks.nutrition import generate_nutrition_report
    from app_my.worker.tasks.reindex import reindex_milvus

    print("=" * 66)
    print("模式一：任务分级路由验证")
    print("=" * 66)

    # ① 先看路由表：Celery 认为每个任务该去哪条队列
    print("\n[1] 路由表（celery_app.conf.task_routes）")
    expected = {
        "tasks.reindex_milvus": "high",
        "tasks.rebuild_kg_graph": "default",
        "tasks.generate_nutrition_report": "low",
    }
    for name, q in expected.items():
        route = celery_app.amqp.router.route({}, name)
        got = route.get("queue") and getattr(route["queue"], "name", route["queue"])
        flag = "OK " if got == q else "!! "
        print("    %s%-32s 期望=%-8s 实际=%s" % (flag, name, q, got))

    # ② 实测：清空 broker → 发三个任务 → 看三条队列各自的长度
    r = redis.Redis.from_url(celery_app.conf.broker_url, decode_responses=True)
    r.flushdb()
    print("\n[2] broker 已清空（%s）" % celery_app.conf.broker_url)

    reindex_milvus.delay(rebuild=True, tenant_id=1, user_id=1)
    rebuild_kg_graph.delay(rebuild=False, tenant_id=1, user_id=1)
    generate_nutrition_report.delay(ingredients=DEMO_INGREDIENTS, tenant_id=1, user_id=1)
    print("[3] 三个任务已发送（未启动 worker，消息暂存在 broker 里）")

    print("\n[4] 三条队列的待处理数（LLEN）：")
    lens = {}
    for q in ("high", "default", "low"):
        lens[q] = r.llen(q)
        print("    %-8s LLEN=%s" % (q, lens[q]))

    r.flushdb()
    print("\n[5] broker 已再次清空（避免残留消息干扰后面的 worker）")

    if lens == {"high": 1, "default": 1, "low": 1}:
        print("\n结果：[ok] 分级路由生效 —— 三个任务分别落到 high / default / low")
        return 0
    print("\n结果：[err] 路由不符合预期。若某条队列是 0，请确认 worker 是否已经停掉。")
    return 1


# ============================================================ 模式二：端到端
def mode_e2e(base_url: str = None) -> int:
    import time

    import websockets

    if not base_url:
        # 默认 9002（项目实际端口）；换端口时用环境变量覆盖，例如：
        #   set STAGE8_BASE_URL=http://127.0.0.1:9018
        base_url = os.environ.get("STAGE8_BASE_URL", "http://127.0.0.1:9002")

    print("=" * 66)
    print("模式二：端到端链路验证（API=%s）" % base_url)
    print("=" * 66)

    # 延迟导入：只有 e2e 模式才需要 requests / psycopg2
    import requests

    username = "stage8verify_%d" % int(time.time())
    password = "stage8-verify-123"

    print("\n[1] 注册 + 登录临时账号 %s ..." % username)
    r = requests.post(
        base_url + "/auth/register",
        json={"username": username, "password": password, "email": username + "@verify.local"},
        timeout=15,
    )
    print("    注册 HTTP %s" % r.status_code)
    if r.status_code not in (200, 201):
        print("    注册失败，响应：%s" % r.text[:300])
        return 1
    r = requests.post(
        base_url + "/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    print("    登录 HTTP %s，token 前缀 %s..." % (r.status_code, token[:20]))

    async def run_ws_case() -> int:
        ws_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = ws_base + "/ws/notifications?token=" + token
        got = []

        async with websockets.connect(ws_url) as ws:
            print("\n[2] WebSocket 握手成功（token 走 ?token= 查询参数）")

            await ws.send("ping")
            pong = await asyncio.wait_for(ws.recv(), timeout=5)
            print("[3] 心跳 ping → 服务端回：%s" % pong)

            headers = {"Authorization": "Bearer " + token}
            resp = requests.post(
                base_url + "/tasks/nutrition-report",
                json={"ingredients": DEMO_INGREDIENTS},
                headers=headers,
                timeout=15,
            )
            print("\n[4] 提交营养报告任务 HTTP %s" % resp.status_code)
            if resp.status_code != 200:
                print("    提交失败，响应：%s" % resp.text[:300])
                return 1
            sub = resp.json()
            task_id = sub["task_id"]
            print("    task_id=%s 队列=%s 状态=%s" % (task_id, sub["queue"], sub["status"]))

            print("\n[5] 等待 WebSocket 推送（最多 90 秒）...")
            deadline = time.time() + 90
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(deadline - time.time(), 0.1))
                except asyncio.TimeoutError:
                    print("    超时：没有收到推送（检查 worker 是否启动）")
                    break
                event = json.loads(raw)
                if event.get("type") != "task" or event.get("task_id") != task_id:
                    continue
                got.append(event["status"])
                print("    收到推送：status=%s" % event["status"])
                if event.get("result"):
                    print("        结果：%s" % json.dumps(event["result"], ensure_ascii=False))
                if event.get("error"):
                    print("        错误：%s" % event["error"])
                if event["status"] in ("SUCCESS", "FAILURE"):
                    break

            print("\n[6] 用 GET /tasks/{id} 复核状态")
            st = requests.get(base_url + "/tasks/" + task_id, headers=headers, timeout=15)
            print("    HTTP %s → %s" % (st.status_code, json.dumps(st.json(), ensure_ascii=False)[:400]))

        print("\n[7] 收到的事件序列：%s" % got)
        if got and got[0] == "STARTED" and got[-1] == "SUCCESS":
            print("\n结果：[ok] 端到端链路打通（提交 → 排队 → worker 执行 → 推送回客户端）")
            return 0
        print("\n结果：[err] 事件序列不符合预期（应为 STARTED → SUCCESS）")
        return 1

    code = asyncio.run(run_ws_case())

    # 清理临时账号，别在库里留垃圾
    try:
        import psycopg2

        from app_my.core.config import settings

        dsn = settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://", 1)
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (username,))
        conn.close()
        print("[8] 临时账号 %s 已删除" % username)
    except Exception as exc:  # 清理失败不影响验收结论
        print("[8] 临时账号清理失败（不影响结论）：%s" % exc)

    return code


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    mode = args[0] if args else ""
    if mode == "routing":
        return mode_routing()
    if mode == "e2e":
        return mode_e2e()
    print(__doc__)
    print("请指定模式：routing 或 e2e")
    return 2


if __name__ == "__main__":
    sys.exit(main())