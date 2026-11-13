#!/usr/bin/env python
# =============================================================================
# scripts/locust_report.py —— 阶段 10 压测结果汇总器
# =============================================================================
# 这个脚本干什么：
#   把 run_bench.sh 跑出来的一堆 CSV（每轮一个 *_stats.csv）汇总成
#   ① 同并发下「单体 vs 网关」对比表
#   ② 「并发数 → 吞吐量 / P99 / 失败率」的拐点曲线表
#   ③ 一份 Markdown 报告文件（可以直接贴进简历/项目文档）
#
# 为什么不直接看 Locust 自带表格：
#   Locust 一次只给一轮的结果，而且 `[准备]` 的注册/登录请求混在里面。
#   要回答"拆分到底值不值"、"错误率在哪个并发开始爆"这两个问题，
#   必须把多轮结果放在一起横向比——那就是这个脚本的活。
#
# 怎么用：
#   ./.venv3/Scripts/python.exe scripts/locust_report.py --dir reports/bench_20261020_143000
#   ./.venv3/Scripts/python.exe scripts/locust_report.py --dir reports/xxx --out reports/xxx/压测报告.md
#
# 依赖：只用 Python 标准库（csv / argparse / pathlib），不装任何新东西。
# =============================================================================
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# 压测场景定义：显示名 → CSV 里的 Name
# 只收这三个；名字里带 " [准备]" 后缀的（注册 / 首次登录）是每个虚拟用户的进场开销，
# 不是被测场景，混进来会把平均响应时间和成功率都带偏。
SCENARIOS = (
    ("/auth/login", "POST", "登录"),
    ("/chat/stream", "POST", "对话"),
    ("/kg/ask", "GET", "图谱问答"),
)

TARGET_LABEL = {
    "monolith": "单体（9002 直连）",
    "gateway": "微服务（9100 经 Kong 网关）",
}

# 拐点判定阈值：满足任意一条就算"这一档开始劣化"
FAIL_RATE_THRESHOLD = 1.0     # 错误率超过 1%
P99_THRESHOLD_MS = 1000.0     # 或者 P99 超过 1000 毫秒


def _to_float(value: str) -> float:
    """把 CSV 里的字符串安全转成 float（空串/脏数据一律当 0，不让报告崩掉）。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_stats_csv(path: Path) -> dict:
    """
    解析一个 Locust stats CSV，返回 {场景名: {指标}}。

    Locust 2.32 写出的列名（照抄自真实文件，不要凭记忆改）：
        Type, Name, Request Count, Failure Count, Median Response Time,
        Average Response Time, Min Response Time, Max Response Time,
        Average Content Size, Requests/s, Failures/s, 50%, 66%, 75%, 80%,
        90%, 95%, 98%, 99%, 99.9%, 99.99%, 100%
    注意 "Requests/s" 这一列是**聚合口径**的每秒请求数，
    报告里的 QPS 直接用它，不要自己再用 请求数÷时长 算一遍（口径不一样）。
    """
    result = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("Name") or "").strip()
            if not name or name.endswith("[准备]"):
                continue
            req = _to_int(row.get("Request Count", "0"))
            fail = _to_int(row.get("Failure Count", "0"))
            result[name] = {
                "requests": req,
                "failures": fail,
                "fail_rate": (fail / req * 100) if req else 0.0,
                "avg_ms": _to_float(row.get("Average Response Time", "0")),
                "p50_ms": _to_float(row.get("50%", "0")),
                "p95_ms": _to_float(row.get("95%", "0")),
                "p99_ms": _to_float(row.get("99%", "0")),
                "max_ms": _to_float(row.get("Max Response Time", "0")),
                "rps": _to_float(row.get("Requests/s", "0")),
            }
    return result


def load_rounds(report_dir: Path) -> list:
    """
    扫目录，把所有 `<target>_u<并发数>_stats.csv` 收成一轮压测记录。

    返回的每个元素：
        {"target": "monolith", "users": 20, "stats": {...}, "csv": 文件路径}
    """
    pattern = re.compile(r"^(?P<target>[a-z]+)_u(?P<users>\d+)_stats\.csv$")
    rounds = []
    for csv_path in sorted(report_dir.glob("*_stats.csv")):
        m = pattern.match(csv_path.name)
        if not m:
            continue
        stats = parse_stats_csv(csv_path)
        if not stats:
            print(f"[跳过] {csv_path.name} 里没有可用的场景数据", file=sys.stderr)
            continue
        rounds.append({
            "target": m.group("target"),
            "users": int(m.group("users")),
            "stats": stats,
            "csv": csv_path,
        })
    # 排序：先按并发数，再按目标，保证同一并发的单体/网关挨在一起
    rounds.sort(key=lambda r: (r["users"], r["target"]))
    return rounds


def _aggregated(stats: dict) -> dict:
    """
    取汇总行。

    Locust 会写一行 Name="Aggregated"（Type="Aggregated"），
    它把这一轮所有请求合在一起算，是报告里"总 QPS / 总失败率"的来源。
    """
    return stats.get("Aggregated", {})


def build_comparison_table(rounds: list) -> list:
    """
    生成「同一并发下，单体 vs 网关」逐场景对比表。

    只对比两边都跑过的并发档位——某一档缺一边就不进表，
    避免出现"网关有数据、单体是空"的半截对比（那种表放进报告最容易误导人）。
    """
    by_users = {}
    for r in rounds:
        by_users.setdefault(r["users"], {})[r["target"]] = r

    rows = []
    for users in sorted(by_users):
        pair = by_users[users]
        if "monolith" not in pair or "gateway" not in pair:
            continue
        mono = pair["monolith"]["stats"]
        gw = pair["gateway"]["stats"]
        for name, _method, label in SCENARIOS:
            if name not in mono or name not in gw:
                continue
            m, g = mono[name], gw[name]
            # P99 的相对差：(网关 - 单体) / 单体。单体为 0 时不算百分比，直接留空。
            delta = ((g["p99_ms"] - m["p99_ms"]) / m["p99_ms"] * 100) if m["p99_ms"] else None
            rows.append({
                "users": users,
                "label": label,
                "name": name,
                "mono_rps": m["rps"],
                "gw_rps": g["rps"],
                "mono_p99": m["p99_ms"],
                "gw_p99": g["p99_ms"],
                "delta_p99_pct": delta,
                "mono_fail": m["fail_rate"],
                "gw_fail": g["fail_rate"],
            })
    return rows


def build_knee_table(rounds: list) -> list:
    """生成「并发档位 → 总吞吐 / 总 P99 / 总失败率」的拐点表。"""
    rows = []
    for r in rounds:
        agg = _aggregated(r["stats"])
        if not agg:
            continue
        degraded = agg["fail_rate"] > FAIL_RATE_THRESHOLD or agg["p99_ms"] > P99_THRESHOLD_MS
        rows.append({
            "target": r["target"],
            "users": r["users"],
            "requests": agg["requests"],
            "failures": agg["failures"],
            "fail_rate": agg["fail_rate"],
            "rps": agg["rps"],
            "avg_ms": agg["avg_ms"],
            "p95_ms": agg["p95_ms"],
            "p99_ms": agg["p99_ms"],
            "max_ms": agg["max_ms"],
            "degraded": degraded,
        })
    return rows


def find_knee(knee_rows: list, target: str):
    """
    找某个目标"开始劣化"的第一档并发；全程不劣化则返回 None。

    判定口径（和报告里写的口径必须一致）：
        失败率 > 1%  或  P99 > 1000ms
    返回 None 表示"压到最高档都还没到拐点"——这本身也是结论，
    说明这台机器上还没摸到真实上限（要继续加压才会爆）。
    """
    rows = [r for r in knee_rows if r["target"] == target]
    rows.sort(key=lambda r: r["users"])
    for r in rows:
        if r["degraded"]:
            return r["users"]
    return None


def _median(values: list):
    """取中位数。空列表返回 None（调用方要自己处理，不能直接除）。"""
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    # 奇数个取中间那个；偶数个取中间两个的平均
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def render_markdown(rounds: list, comparison: list, knee: list, report_dir: Path) -> str:
    """
    把三张表渲染成一份 Markdown 报告。

    🔴 这里每一行都**不带**结尾换行符，最后统一用 "\\n".join() 拼起来。
    两条写法混着用（有的行带 \\n 有的不带）就会出现"整张表挤成一行"，
    在渲染器里显示成一条永远滚不完的长表格，完全没法读。
    """
    out = []
    out.append("# AI 私厨 v3.0 · 阶段 10 性能压测报告")
    out.append("")
    out.append(f"> 数据来源：`{report_dir}` 下的 Locust CSV（本机实跑）")
    out.append("> 口径说明：LLM 调用为 **Mock 模式**（`MOCK_LLM=true`），"
               "测的是本项目架构本身的容量，不含外部大模型服务的耗时。")

    out.append("")
    out.append("## 一、总览：并发 → 容量与劣化")
    out.append("")
    out.append("| 目标 | 并发 | 总请求 | 失败 | 失败率 | 总QPS | 平均ms | P95ms | P99ms | 已劣化 |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    knee_mono = find_knee(knee, "monolith")
    knee_gw = find_knee(knee, "gateway")
    for r in knee:
        out.append(
            f"| {TARGET_LABEL.get(r['target'], r['target'])} | {r['users']} | {r['requests']} | "
            f"{r['failures']} | {r['fail_rate']:.2f}% | {r['rps']:.1f} | {r['avg_ms']:.0f} | "
            f"{r['p95_ms']:.0f} | {r['p99_ms']:.0f} | {'是' if r['degraded'] else ''} |"
        )

    out.append("")
    out.append("## 二、单体 vs 微服务（同一并发、同一脚本）")
    out.append("")
    out.append("| 并发 | 场景 | 单体QPS | 网关QPS | 单体P99ms | 网关P99ms | 网关P99增幅 | 单体失败率 | 网关失败率 |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for c in comparison:
        delta = f"{c['delta_p99_pct']:+.0f}%" if c["delta_p99_pct"] is not None else "—"
        out.append(
            f"| {c['users']} | {c['label']}（{c['name']}） | {c['mono_rps']:.2f} | {c['gw_rps']:.2f} | "
            f"{c['mono_p99']:.0f} | {c['gw_p99']:.0f} | {delta} | "
            f"{c['mono_fail']:.2f}% | {c['gw_fail']:.2f}% |"
        )

    out.append("")
    out.append("## 三、结论（脚本自动判定，口径见下）")
    out.append("")
    out.append(f"- 劣化判定口径：错误率 > {FAIL_RATE_THRESHOLD}% **或** P99 > {P99_THRESHOLD_MS:.0f} ms")
    out.append(f"- 单体架构拐点：**{f'{knee_mono} 并发' if knee_mono else '未触及（最高档仍达标）'}**")
    out.append(f"- 微服务架构拐点：**{f'{knee_gw} 并发' if knee_gw else '未触及（最高档仍达标）'}**")

    if comparison:
        # 为什么用中位数而不是直接取最大值：
        #   某个并发档的 P99 可能被一次 GC / 一次冷连接 / 一次限流重试拉高，
        #   取最大会把这种偶发噪声当成"网关开销最大的场景"写进结论，
        #   结论就错了（实测里 20 并发的 /kg/ask 就出现过一次 310ms 的偶发尖刺，
        #   而 40 并发同样场景只有 21ms）。取各档增幅的中位数才代表常态。
        per_scene = {}
        for c in comparison:
            if c["delta_p99_pct"] is not None:
                per_scene.setdefault(c["label"], []).append(c["delta_p99_pct"])
        ranked = sorted(
            ((label, _median(vals)) for label, vals in per_scene.items() if _median(vals) is not None),
            key=lambda kv: kv[1], reverse=True,
        )
        if ranked:
            worst_label, worst_val = ranked[0]
            best_label, best_val = ranked[-1]
            out.append(f"- 网关开销中位数最大的场景：**{worst_label}**（各档中位数 {worst_val:+.0f}%）")
            out.append(f"- 网关开销中位数最小的场景：**{best_label}**（各档中位数 {best_val:+.0f}%）")

    out.append("")
    out.append("---")
    out.append("")
    out.append("### 复现方式")
    out.append("")
    out.append("```bash")
    out.append('bash scripts/run_bench.sh all "10,20,40,60" 45')
    out.append(".venv3/Scripts/python.exe scripts/locust_report.py --dir <输出目录>")
    out.append("```")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 10 压测结果汇总器")
    parser.add_argument("--dir", required=True, help="run_bench.sh 的输出目录（含 *_stats.csv）")
    parser.add_argument("--out", default="", help="把 Markdown 报告写到哪个文件；不给就打印到屏幕")
    args = parser.parse_args()

    report_dir = Path(args.dir)
    if not report_dir.is_dir():
        print(f"[错误] 目录不存在: {report_dir}", file=sys.stderr)
        return 1

    rounds = load_rounds(report_dir)
    if not rounds:
        print(f"[错误] {report_dir} 里没找到任何 *_stats.csv。"
              f"先跑 bash scripts/run_bench.sh 生成压测结果。", file=sys.stderr)
        return 1

    comparison = build_comparison_table(rounds)
    knee = build_knee_table(rounds)
    markdown = render_markdown(rounds, comparison, knee, report_dir)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"[完成] 报告已写入 {out_path}")
        print(f"       共解析 {len(rounds)} 轮压测、{len(comparison)} 行对比、{len(knee)} 行拐点数据")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())