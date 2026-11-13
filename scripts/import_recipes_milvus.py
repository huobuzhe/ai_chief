# scripts/import_recipes_milvus.py
"""
阶段 6：把菜谱向量导入 Milvus（幂等：先删集合再重建再写入）。

用法（项目根目录执行）：
    uv run python scripts/import_recipes_milvus.py

流程：读 recipes.json → 清场 → 分批向量化（每批 10 条）→ upsert → 冒烟检索。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
from app_my.knowledge.embedding import embed_texts
from app_my.knowledge.milvus_store import (
    clear_collection, collection_row_count, ensure_collection, upsert_recipes, vector_search,
)

BATCH_SIZE = 10  # DashScope embedding 单次最多 10 条文本


def main() -> None:
    recipes = load_recipes()
    print(f"[1/5] 读取种子数据：{len(recipes)} 条菜谱")

    print("[2/5] 清场（删旧集合，幂等设计）")
    if not clear_collection():
        print("      清场失败：Milvus 不可用？先确认容器已启动")
        sys.exit(1)

    print("[3/5] 建集合（schema + HNSW 索引）")
    if not ensure_collection():
        sys.exit(1)

    print("[4/5] 分批向量化并写入（每批 10 条，调用 embedding 接口，请稍等）...")
    t0 = time.time()
    total = 0
    for i in range(0, len(recipes), BATCH_SIZE):
        batch = recipes[i : i + BATCH_SIZE]
        texts = [recipe_to_text(r) for r in batch]
        vectors = embed_texts(texts)              # 真实调用 DashScope，一次最多 10 条
        rows = [
            {
                "recipe_id": r["recipe_id"],      # 主键：重跑脚本 = 按 id 覆盖（幂等的另一重保险）
                "text": t,
                "vector": v,
                "metadata": recipe_to_metadata(r),
            }
            for r, t, v in zip(batch, texts, vectors)
        ]
        n = upsert_recipes(rows)
        total += n
        print(f"      已写入 {i + len(batch)}/{len(recipes)}（本批 {n} 条）")
    print(f"[5/5] 写入完成：{total} 条，耗时 {time.time() - t0:.1f} 秒")

    print(f"集合行数核对：{collection_row_count()}（应等于 {total}）")

    # 冒烟：一句真实查询跑一遍三件套（向量化 → Milvus 检索）
    from app_my.knowledge.embedding import embed_query
    hits = vector_search(embed_query("鸡胸肉 减脂"), k=3)
    print("冒烟检索 '鸡胸肉 减脂' 前 3 条 ->")
    for h in hits:
        print("  -", h["metadata"].get("name"), "| score:", round(h["score"], 4))

    # 数据变了：把两条检索路径的缓存一起失效（rag=v1 路径，rag2=v2 路径）
    from app_my.core.cache import invalidate_prefix
    invalidate_prefix("rag")
    invalidate_prefix("rag2")
    print("[缓存] rag / rag2 前缀已失效")


if __name__ == "__main__":
    main()