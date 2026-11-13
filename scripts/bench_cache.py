# scripts/bench_cache.py
"""
阶段 5：缓存开 vs 关 的同机对比压测——简历数字的唯一来源。

测什么：local_recipe_search（真实生产路径：embedding 调用 + PG 查询 + 融合 + 补全）
怎么测：
    off 轮：关掉缓存，连打 10 次（每次真实穿透，花 embedding 额度约 10 次）
    on  轮：打开缓存，先打 1 次填充缓存，再连打 200 次（全命中）
输出：两轮各自的 QPS、平均延迟、命中率——数字全部来自你的机器

用法（项目根目录，后端无需启动）：
    uv run python scripts/bench_cache.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_my.core import cache as cache_mod
from app_my.core.cache import cache_stats_reset, cache_stats, invalidate_prefix

QUERY = "鸡胸肉 西兰花 减脂"      # 一个有代表性的真实查询
OFF_N = 10                         # 关缓存轮次（每次都打 embedding 接口，别设太大）
ON_N = 200                         # 开缓存轮次（纯内存命中，可以多打）


def run_round(n: int) -> tuple:
    cache_stats_reset()
    t0 = time.perf_counter()
    for _ in range(n):
        from app_my.tools.recipe_rag_tool import local_recipe_search
        local_recipe_search(QUERY, k=5)
    cost = time.perf_counter() - t0
    s = cache_stats()
    return cost, n / cost, s


def main() -> None:
    from app_my.tools.recipe_rag_tool import local_recipe_search

    print("=" * 60)
    print("阶段 5 缓存压测（结果填进简历/收官文档）")
    print("=" * 60)

    # --- 轮 1：缓存关（真实穿透：embedding + PG + BM25 融合 + 补全）---
    cache_mod.settings.__class__.CACHE_ENABLED = False
    invalidate_prefix("rag")
    cost_off, qps_off, _ = run_round(OFF_N)
    print(f"\n[关] {OFF_N} 次真实穿透：{cost_off:.1f}s，QPS={qps_off:.2f}，"
          f"平均 {cost_off / OFF_N * 1000:.0f} ms/次")

    # --- 轮 2：缓存开（先填一次，再测命中性能）---
    cache_mod.settings.__class__.CACHE_ENABLED = True
    invalidate_prefix("rag")
    local_recipe_search(QUERY, k=5)          # 填充缓存（这次算 miss）
    cost_on, qps_on, s = run_round(ON_N)
    print(f"[开] {ON_N} 次缓存命中：{cost_on:.2f}s，QPS={qps_on:.1f}，"
          f"平均 {cost_on / ON_N * 1000:.2f} ms/次")
    print(f"     命中统计：L1={s['l1_hits']} L2={s['l2_hits']} 穿透={s['misses']}"
          f" 命中率={s['hit_rate'] * 100:.1f}%")

    print("\n" + "-" * 60)
    print(f"结论：QPS 提升 {qps_on / qps_off:.0f} 倍，"
          f"单次延迟 {cost_off / OFF_N * 1000:.0f}ms -> {cost_on / ON_N * 1000:.2f}ms")
    print("（把这两个数字记下来，收官文档要用）")


if __name__ == "__main__":
    main()