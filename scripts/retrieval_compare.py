# scripts/retrieval_compare.py
"""
阶段 6：v1（两路）vs v2（三路）检索效果对比实验——简历数字的唯一来源。

测什么：同一批真实查询，两版检索的 MRR@5 与 Hit@5。
    MRR@5  平均倒数排名：第一条相关结果排第 1 名得 1 分、第 2 名得 0.5 分……
           越接近 1 表示"最想要的菜排得越靠前"
    Hit@5  前 5 条里至少出现一条相关菜的比例（0~1）

测试集：10 组查询，每组标注"哪些菜谱算相关"（依据食材/标签人工标注）。
公平性：两版走同一进程、同一 embedding、同一数据；缓存先失效。

用法（项目根目录，Milvus/Neo4j 容器已启动）：
    uv run python scripts/retrieval_compare.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 测试集：query -> 相关菜谱 id 集合（依据 recipes.json 的食材与标签人工标注）
TEST_SET = [
    ("减脂餐 鸡胸肉", ["R017", "R018", "R024", "R021"]),
    ("西兰花 虾仁 低卡", ["R023", "R017"]),
    ("豆腐 汤羹 减脂", ["R026", "R032", "R031"]),
    ("快手 早餐", ["R043", "R025", "R042", "R037"]),
    ("川菜 麻辣 下饭", ["R003", "R004", "R005", "R058"]),
    ("孩子爱吃 酸甜", ["R007", "R008", "R022"]),
    ("高蛋白 清淡 宴客", ["R019", "R059", "R020", "R055"]),
    ("土豆 素菜 快手", ["R011", "R010"]),
    ("汤羹 滋补 秋冬", ["R034", "R029", "R032"]),
    ("低卡 素菜 凉菜", ["R044", "R045", "R012"]),
]


def mrr_at_k(result_ids, relevant, k=5):
    """平均倒数排名（单查询）：前 k 里第一条相关的名次 r -> 1/r；没有相关 -> 0"""
    for rank, rid in enumerate(result_ids[:k], start=1):
        if rid in relevant:
            return 1.0 / rank
    return 0.0


def hit_at_k(result_ids, relevant, k=5):
    """前 k 里出现至少一条相关菜 -> 1，否则 0"""
    return 1.0 if any(rid in relevant for rid in result_ids[:k]) else 0.0


def evaluate(search_fn, label):
    """对整个测试集跑一遍 search_fn，输出两指标"""
    from app_my.core.cache import invalidate_prefix
    invalidate_prefix("rag")
    invalidate_prefix("rag2")
    mrr_total, hit_total = 0.0, 0.0
    rows = []
    for query, relevant in TEST_SET:
        hits = search_fn(query, k=5)
        ids = [h.get("recipe_id") or h.get("metadata", {}).get("recipe_id") for h in hits]
        mrr_total += mrr_at_k(ids, relevant)
        hit_total += hit_at_k(ids, relevant)
        rows.append((query, ids[:3], round(mrr_at_k(ids, relevant), 3)))
    n = len(TEST_SET)
    print(f"\n===== {label} =====")
    for q, top3, m in rows:
        print(f"  {q:<14} top3={top3}  单查询MRR={m}")
    print(f"  >> MRR@5 = {mrr_total / n:.3f}    Hit@5 = {hit_total / n:.3f}")
    return mrr_total / n, hit_total / n


def main():
    from app_my.knowledge.retriever import hybrid_search, hybrid_search_v2

    print("=" * 62)
    print("阶段 6 检索效果对比实验（v1 两路 vs v2 三路）")
    print("=" * 62)

    mrr1, hit1 = evaluate(hybrid_search, "v1（PGVector 向量 + BM25，两路）")
    mrr2, hit2 = evaluate(hybrid_search_v2, "v2（Milvus 向量 + BM25 + 图谱，三路）")

    print("\n" + "=" * 62)
    print(f"MRR@5:  v1={mrr1:.3f}  v2={mrr2:.3f}  变化={mrr2 - mrr1:+.3f}"
          f"（{(mrr2 - mrr1) / mrr1 * 100:+.1f}%）" if mrr1 else "")
    print(f"Hit@5:  v1={hit1:.3f}  v2={hit2:.3f}  变化={hit2 - hit1:+.3f}"
          f"（{(hit2 - hit1) / hit1 * 100:+.1f}%）" if hit1 else "")
    print("（把这两行数字记下来，收官文档和简历叙事要用；照抄实测值，不要改）")


if __name__ == "__main__":
    main()