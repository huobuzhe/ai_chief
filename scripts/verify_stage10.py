# scripts/verify_stage10.py —— v3 阶段 10 验收脚本
#
# 这个脚本干什么：
#     一句话回答"阶段 10 到底做完没有"。它按交付物逐条检查，最后给一个总的
#     OK / FAIL 结论。不合格就打印缺什么、去哪补。
#
#     它和 pytest 的分工：
#         pytest     —— 测"代码逻辑对不对"（阶段 9 有 124 个，本阶段新增 17 个）
#         本脚本     —— 测"该有的东西在不在、能不能跑起来"（文件、配置、容器、端口、报告）
#     两者都绿，才算这个阶段收官。
#
# 用法（在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#     .\.venv3\Scripts\python.exe scripts\verify_stage10.py
#     .\.venv3\Scripts\python.exe scripts\verify_stage10.py --bench-dir reports/bench_20261020_143045
#
# 退出码：0 = 全过；1 = 有 FAIL。可直接用于 CI 判断。
import argparse
import os
import subprocess
import sys
from pathlib import Path

# 把项目根目录塞进 sys.path。
# 为什么需要：直接 `python scripts\verify_stage10.py` 时，Python 只把 scripts\ 当作模块搜索路径，
# 于是 `import app_my...` 会报 ModuleNotFoundError: No module named 'app_my'。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

PASS, FAIL = "OK  ", "FAIL"
_results: list = []          # [(标记, 说明, 细节)]


def check(label: str, ok: bool, detail: str = "") -> bool:
    """记录一条检查结果并打印。全程收集，最后统一统计，不中途退出。"""
    _results.append((PASS if ok else FAIL, label, detail))
    print("  %s %-46s %s" % (PASS if ok else FAIL, label, detail))
    return ok


# ============================================================
# ① 交付文件是否都在
# ============================================================
def check_files() -> None:
    print("\n[1] 交付文件")
    expected = {
        # LLM 打桩（阶段 10 新增的业务代码）
        "app_my/core/mock_llm.py": "对话模型打桩器",
        "app_my/knowledge/embedding.py": "向量打桩（含 MOCK_DIMENSION）",
        "app_my/core/config.py": "MOCK_LLM 配置开关",
        "app_my/core/model_router.py": "统一入口的打桩早返回分支",
        # 压测
        "benchmarks/locustfile.py": "压测脚本（三场景）",
        "scripts/run_bench.sh": "压测编排（Git Bash）",
        "scripts/locust_report.py": "压测结果汇总器",
        # 生产部署
        "docker/Dockerfile.svc": "生产镜像定义",
        "docker/requirements.prod.txt": "生产依赖（含 gunicorn）",
        "docker/docker-compose.prod.yml": "生产编排（4 服务 + 网关）",
        # CI/CD
        ".gitee/workflows/pipeline.yml": "Gitee Go 流水线",
        # 测试
        "tests/unit/test_stage10_mock_llm.py": "打桩单元测试",
        "tests/unit/test_stage10_bench_report.py": "汇总器单元测试",
    }
    for rel, desc in expected.items():
        p = Path(_ROOT) / rel
        ok = p.is_file() and p.stat().st_size > 0
        check(rel, ok, f"{desc}" + ("" if ok else f"（缺失或为空）"))


# ============================================================
# ② 打桩代码是否真的接上了（不能只看文件在不在）
# ============================================================
def check_mock_wiring() -> None:
    print("\n[2] LLM 打桩接线")
    # 2.1 配置项存在且默认关闭（默认必须是关的，否则正常跑测试会误伤）
    try:
        from app_my.core.config import settings
        check("config 里有 MOCK_LLM 配置", hasattr(settings, "MOCK_LLM"),
              f"当前值={getattr(settings, 'MOCK_LLM', 'N/A')}")
        check("MOCK_LLM 默认是关闭的", settings.MOCK_LLM is False,
              "压测才临时打开；默认开着会让普通请求全部返回假数据")
    except Exception as exc:
        check("能读取 settings", False, f"{type(exc).__name__}: {exc}")

    # 2.2 统一入口里真的有打桩分支
    try:
        from app_my.core import model_router
        src = Path(model_router.__file__).read_text(encoding="utf-8")
        check("ainvoke_routed 里有 MOCK_LLM 分支", "MOCK_LLM" in src,
              "打桩必须挂在唯一出口上，否则绕过去了照样真调模型")
        check("打桩分支不挂计费回调", "ainvoke_mock" in src,
              "mock 没有真 token，不该记账")
    except Exception as exc:
        check("能导入 model_router", False, f"{type(exc).__name__}: {exc}")

    # 2.3 embedding 打桩：维度必须是 1024（和 Milvus 集合一致）
    try:
        from app_my.knowledge.embedding import MOCK_DIMENSION
        from app_my.knowledge.milvus_store import DIMENSION
        check("打桩向量维度与 Milvus 集合一致",
              MOCK_DIMENSION == DIMENSION,
              f"打桩={MOCK_DIMENSION} Milvus={DIMENSION}")
    except Exception as exc:
        check("能读取向量维度常量", False, f"{type(exc).__name__}: {exc}")

    # 2.4 打桩输出真的能被下游解析（这是压测数据可信的前提）
    try:
        import asyncio
        from app_my.core.mock_llm import ainvoke_mock
        from app_my.agents.recognizer import parse_json_payload
        data = parse_json_payload(asyncio.run(ainvoke_mock("extract", [])).content)
        n = len(data.get("ingredients") or [])
        check("extract 打桩能被识别节点解析", n >= 1, f"解析出 {n} 种食材（0 会导致链路空转）")
    except Exception as exc:
        check("打桩输出可被解析", False, f"{type(exc).__name__}: {exc}")


# ============================================================
# ③ 五个服务是否都健康
# ============================================================
def check_services() -> None:
    print("\n[3] 服务健康")
    try:
        import requests
    except ImportError:
        check("requests 可用", False, "装一下：pip install requests")
        return
    for port, name in ((9002, "单体"), (9121, "user"), (9122, "recognizer"),
                       (9123, "recommender"), (9124, "chat")):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=3)
            ok = r.status_code == 200
            detail = f"{name}" + (f" → {r.json().get('status')}" if ok else f" HTTP {r.status_code}")
        except Exception:
            ok, detail = False, f"{name} 连不上（端口 {port}）"
        check(f"端口 {port} 健康", ok, detail)


# ============================================================
# ④ 生产编排能否被 Docker 解析
# ============================================================
def check_prod_compose() -> None:
    print("\n[4] 生产编排与 CI 配置")
    # 4.1 先用 PyYAML 兜一层（不依赖 docker 命令）
    try:
        import yaml
        for rel in ("docker/docker-compose.prod.yml", ".gitee/workflows/pipeline.yml"):
            p = Path(_ROOT) / rel
            try:
                yaml.safe_load(p.read_text(encoding="utf-8"))
                check(f"{rel} YAML 可解析", True)
            except Exception as exc:
                check(f"{rel} YAML 可解析", False, f"{type(exc).__name__}: {exc}")
    except ImportError:
        check("PyYAML 可用", False, "装一下：pip install pyyaml")

    # 4.2 compose 必须能被 docker 自己解析（YAML 合法 ≠ compose 合法）
    compose = Path(_ROOT) / "docker" / "docker-compose.prod.yml"
    if compose.is_file():
        try:
            proc = subprocess.run(
                ["docker", "compose", "-f", str(compose), "config"],
                capture_output=True, text=True, timeout=60, cwd=str(Path(_ROOT) / "docker"),
            )
            check("docker compose config 通过", proc.returncode == 0,
                  "" if proc.returncode == 0 else (proc.stderr or proc.stdout)[:120])
        except FileNotFoundError:
            check("docker 命令可用", False, "没装 Docker 或不在 PATH 里")
        except subprocess.TimeoutExpired:
            check("docker compose config 通过", False, "超时")

    # 4.3 compose 里必须真的定义了 4 个服务 + 网关
    try:
        import yaml
        data = yaml.safe_load(compose.read_text(encoding="utf-8"))
        svcs = set(data.get("services", {}))
        need = {"svc-user", "svc-recognizer", "svc-recommender", "svc-chat", "kong"}
        check("compose 含 4 个服务 + 网关", need <= svcs,
              f"实际={sorted(svcs)}" if not need <= svcs else "")
    except Exception as exc:
        check("能读取 compose 结构", False, f"{type(exc).__name__}: {exc}")


# ============================================================
# ⑤ 压测产物与报告
# ============================================================
def check_bench(bench_dir: str) -> None:
    print("\n[5] 压测产物")
    if not bench_dir:
        print("  --   （跳过：没指定 --bench-dir。跑完 bash scripts/run_bench.sh 后可加这个参数复查）")
        return
    d = Path(bench_dir)
    if not d.is_absolute():
        d = Path(_ROOT) / d
    if not d.is_dir():
        check("压测输出目录存在", False, f"{d} 不存在")
        return

    stats_files = sorted(d.glob("*_stats.csv"))
    check("存在压测结果 CSV", len(stats_files) > 0, f"找到 {len(stats_files)} 个")

    # 单体和网关的档位必须一致，否则对比表出不来
    mono = {f.name.split("_u")[1].split("_")[0] for f in stats_files if f.name.startswith("monolith")}
    gw = {f.name.split("_u")[1].split("_")[0] for f in stats_files if f.name.startswith("gateway")}
    check("单体与网关都跑了压测", bool(mono) and bool(gw),
          f"单体档位={sorted(mono)} 网关档位={sorted(gw)}")

    report = d / "压测报告.md"
    if check("压测报告已生成", report.is_file(), str(report.name) if report.is_file() else "缺失"):
        text = report.read_text(encoding="utf-8")
        # 表格必须一行一行渲染，不能挤成一行
        check("报告表格分行正常", any(line.startswith("| 目标 |") for line in text.splitlines()),
              "如果这里挂了，多半是拼接时漏了换行")
        check("报告含拐点结论", "拐点" in text)


# ============================================================
# 汇总
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 10 验收")
    parser.add_argument("--bench-dir", default="", help="run_bench.sh 的输出目录")
    args = parser.parse_args()

    print("=" * 78)
    print(" AI 私厨 v3.0 · 阶段 10 验收")
    print("=" * 78)

    check_files()
    check_mock_wiring()
    check_services()
    check_prod_compose()
    check_bench(args.bench_dir)

    failed = [r for r in _results if r[0] == FAIL]
    print("\n" + "=" * 78)
    if failed:
        print(" 验收未通过：%d / %d 项失败" % (len(failed), len(_results)))
        for _tag, label, detail in failed:
            print("   - %s  %s" % (label, detail))
        print("=" * 78)
        return 1
    print(" 验收通过：%d 项全部 OK" % len(_results))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())