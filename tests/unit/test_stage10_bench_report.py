# tests/unit/test_stage10_bench_report.py —— v3 阶段 10：压测结果汇总器（纯内存，不依赖服务）
"""
为什么要有这几个用例：

    locust_report.py 是"把 CSV 变成结论"的那一环。它会做三件容易出错的事：
        ① 解析 CSV（列名一个字都不能错，Locust 升级改列名就会静默解析成 0）
        ② 过滤掉 [准备] 请求（漏过滤会把进场开销混进平均响应时间）
        ③ 判定拐点（阈值口径写错，报告结论就是错的）

    这些错都不会让程序崩溃——它照样输出一张看起来很正常的表格，
    只是数字是错的。所以只能靠测试守住。

覆盖点：
    1. 解析：数值正确、[准备] 被排除、脏数据不炸
    2. 拐点：超过阈值才判劣化，没超判定为"未触及"
    3. 渲染：Markdown 每行独立成行（曾经因为漏换行整张表挤成一行）
    4. 对比表：缺一边的数据就不出对比（不出半截表）

注意：导入用 `from scripts.xxx import`——scripts/ 下有 __init__.py，
      项目根目录在 pytest 的 sys.path 里，可以直接当包导入。
"""
from scripts.locust_report import (
    build_comparison_table,
    build_knee_table,
    find_knee,
    load_rounds,
    parse_stats_csv,
    render_markdown,
)

# 仿 Locust 2.32 真实输出的 CSV 表头（22 列，列名照抄真实文件）
CSV_HEADER = (
    "Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,"
    "Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,"
    "50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%"
)

# 表头列数。所有造数据的函数都必须产出这么多列——
# 🔴 少一列不会报错，只会让整行**整体前移**：Name 读进 Type、请求数读进 Name，
#    最后每个字段都是 0 / None，而程序一声不吭。这个常量就是用来防这个的。
COLUMN_COUNT = 22


def _row(name, count, fail, avg, p99, rps, method="POST"):
    """
    拼一行"具体接口"的数据。前 19 列有用，后面补 0。

    列顺序（严格对齐表头）：
        Type, Name, 请求数, 失败数, Median, Average, Min, Max, 内容大小,
        Requests/s, Failures/s, 50%, 66%, 75%, 80%, 90%, 95%, 98%, 99%, ...
    """
    cells = [
        method,          # Type
        name,            # Name
        count,           # Request Count
        fail,            # Failure Count
        0,               # Median Response Time
        avg,             # Average Response Time
        0,               # Min
        0,               # Max
        0,               # Average Content Size
        rps,             # Requests/s
        0,               # Failures/s
        0, 0, 0, 0, 0, 0, 0,   # 50% 66% 75% 80% 90% 95% 98%
        p99,             # 99%
        0, 0, 0,         # 99.9% 99.99% 100%
    ]
    assert len(cells) == COLUMN_COUNT, f"造数据列数错了：{len(cells)} != {COLUMN_COUNT}"
    return ",".join(str(c) for c in cells)


def _agg_row(count, fail, avg, p99, rps):
    """
    拼汇总行。真实文件里它的 **Type 列是空的**（行首就是逗号）：
        `,Aggregated,24,0,130.0,...`
    """
    cells = [
        "",              # Type —— 空
        "Aggregated",    # Name
        count,
        fail,
        0,               # Median
        avg,             # Average
        0,               # Min
        0,               # Max
        0,               # 内容大小
        rps,             # Requests/s
        0,               # Failures/s
        0, 0, 0, 0, 0, 0, 0,
        p99,             # 99%
        0, 0, 0,
    ]
    assert len(cells) == COLUMN_COUNT, f"汇总行列数错了：{len(cells)} != {COLUMN_COUNT}"
    return ",".join(str(c) for c in cells)


SAMPLE_CSV = "\n".join([
    CSV_HEADER,
    _row("/auth/login", 100, 0, 200, 300, 2.0),
    _row("/auth/login [准备]", 20, 0, 300, 400, 0.4),     # 必须被过滤掉
    _row("/kg/ask", 300, 0, 10, 20, 6.0, method="GET"),
    _agg_row(420, 0, 120, 350, 8.4),
])


# ---------------- 0. 自检：表头列数与造数据一致 ----------------
def test_样本数据列数与表头一致():
    """
    这条测试保护的是"测试自己造的数据"。
    如果表头将来变了（Locust 升级）而造数据的函数没跟着变，
    下面所有断言都会以"取到 0"的形式失败，看起来像被测代码有 bug，
    实际是测试数据错了——这条能一眼把责任分清楚。
    """
    assert len(CSV_HEADER.split(",")) == COLUMN_COUNT
    assert len(SAMPLE_CSV.splitlines()[1].split(",")) == COLUMN_COUNT


# ---------------- 1. 解析 ----------------
def test_parse_stats_csv_数值正确(tmp_path):
    f = tmp_path / "monolith_u20_stats.csv"
    f.write_text(SAMPLE_CSV, encoding="utf-8")
    stats = parse_stats_csv(f)

    assert "/auth/login" in stats
    assert stats["/auth/login"]["requests"] == 100
    assert stats["/auth/login"]["p99_ms"] == 300
    assert stats["/auth/login"]["rps"] == 2.0


def test_parse_stats_csv_过滤准备请求(tmp_path):
    """[准备] 是虚拟用户进场时的注册/登录，不是被测场景，混进来会拉高平均值。"""
    f = tmp_path / "monolith_u20_stats.csv"
    f.write_text(SAMPLE_CSV, encoding="utf-8")
    stats = parse_stats_csv(f)

    assert "/auth/login [准备]" not in stats
    # 反证：确保它不是因为"整行没解析"而不在，而是被规则过滤了
    assert "/auth/login" in stats


def test_parse_stats_csv_脏数据不崩溃(tmp_path):
    """空值 / 非数字不应该让汇总器挂掉（CI 里挂掉就整条流水线红）。"""
    f = tmp_path / "monolith_u20_stats.csv"
    f.write_text(CSV_HEADER + "\n" + "GET,/kg/ask,,,n/a,,,,,,,,,,,,,,,,,,", encoding="utf-8")
    stats = parse_stats_csv(f)

    assert stats["/kg/ask"]["requests"] == 0
    assert stats["/kg/ask"]["fail_rate"] == 0.0


# ---------------- 2. 拐点判定 ----------------
def _make_rounds(tmp_path, rows):
    """造一个压测结果目录：rows = [(文件名, CSV内容)]"""
    for name, content in rows:
        (tmp_path / name).write_text(content, encoding="utf-8")
    return load_rounds(tmp_path)


def test_find_knee_超过P99阈值才算劣化(tmp_path):
    # 10 并发 P99=200（健康）；40 并发 P99=1500（>1000 阈值，劣化）
    rows = [
        ("monolith_u10_stats.csv", CSV_HEADER + "\n" + _agg_row(100, 0, 100, 200, 5.0)),
        ("monolith_u40_stats.csv", CSV_HEADER + "\n" + _agg_row(400, 0, 800, 1500, 20.0)),
    ]
    rounds = _make_rounds(tmp_path, rows)
    knee = build_knee_table(rounds)
    assert find_knee(knee, "monolith") == 40


def test_find_knee_全程健康时返回None(tmp_path):
    """没到拐点也是一种结论：说明这台机器上还没摸到真实上限。"""
    rows = [
        ("gateway_u10_stats.csv", CSV_HEADER + "\n" + _agg_row(100, 0, 100, 200, 5.0)),
    ]
    rounds = _make_rounds(tmp_path, rows)
    knee = build_knee_table(rounds)
    assert find_knee(knee, "gateway") is None


def test_find_knee_错误率超标也判劣化(tmp_path):
    """错误率 > 1% 同样算劣化（两条口径是"或"的关系）。"""
    rows = [
        ("monolith_u30_stats.csv", CSV_HEADER + "\n" + _agg_row(100, 5, 100, 300, 5.0)),
    ]
    rounds = _make_rounds(tmp_path, rows)
    knee = build_knee_table(rounds)
    assert find_knee(knee, "monolith") == 30


# ---------------- 3. 渲染 ----------------
def test_render_markdown_每行独立成行(tmp_path):
    """
    曾经因为拼接时丢了换行，整张表格挤在一行里，
    在渲染器里变成一条永远滚不完的长表格，完全没法读。
    """
    rows = [
        ("monolith_u20_stats.csv", SAMPLE_CSV),
        ("gateway_u20_stats.csv", SAMPLE_CSV),
    ]
    rounds = _make_rounds(tmp_path, rows)
    md = render_markdown(rounds, build_comparison_table(rounds), build_knee_table(rounds), tmp_path)

    lines = md.splitlines()
    assert "## 一、总览：并发 → 容量与劣化" in lines
    # 表头必须整行独立存在（用 startswith 判断，因为后面还有很多列）
    assert any(line.startswith("| 目标 |") for line in lines)
    assert any("单体" in line and line.startswith("| ") for line in lines)


# ---------------- 4. 对比表只在两边都有数据时生成 ----------------
def test_build_comparison_table_缺一边就不出对比(tmp_path):
    """
    只有网关数据、没有单体数据时不能生成半截对比表——
    那种表放进报告最容易误导人（读者会以为单体是 0）。
    """
    rows = [("gateway_u20_stats.csv", SAMPLE_CSV)]
    rounds = _make_rounds(tmp_path, rows)
    assert build_comparison_table(rounds) == []