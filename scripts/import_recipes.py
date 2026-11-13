# scripts/import_recipes.py
"""
阶段 2：把种子菜谱（app_my/knowledge/data/recipes.json）导入 PGVector 向量库。

用法（项目根目录执行）：
    uv run python scripts/import_recipes.py

特性：
- 幂等：每次运行前清空 recipes 集合的旧向量，重复执行结果一致
- 分批：每批 10 条调用一次 embedding 接口（DashScope 单次上限 10 条）
"""
import sys
import time
from pathlib import Path

# 保证从任意目录运行都能 import app_my（scripts/ 不在 sys.path 默认搜索路径里）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
from app_my.knowledge.vector_store import clear_recipe_collection, get_vector_store

BATCH_SIZE = 10  # DashScope embedding 单次最多 10 条文本


def main() -> None:
    recipes = load_recipes()
    print(f"[1/4] 读取种子数据：{len(recipes)} 条菜谱")

    store = get_vector_store()
    print("[2/4] 清空旧向量（幂等设计，可放心重复执行）")
    deleted = clear_recipe_collection()
    print(f"      清除旧记录 {deleted} 行")

    print("[3/4] 分批导入中（每批 10 条，需调用 embedding 接口，请稍等）...")
    t0 = time.time()
    total = 0
    for i in range(0, len(recipes), BATCH_SIZE):
        batch = recipes[i : i + BATCH_SIZE]
        store.add_texts(
            texts=[recipe_to_text(r) for r in batch],
            metadatas=[recipe_to_metadata(r) for r in batch],
        )
        total += len(batch)
        print(f"      已导入 {total}/{len(recipes)}")
    print(f"[4/4] 导入完成，耗时 {time.time() - t0:.1f} 秒")

    # 冒烟验证：直接向量检索一句话
    print("冒烟验证：similarity_search('鸡胸肉 减脂') 前 3 条 ->")
    hits = store.similarity_search("鸡胸肉 减脂", k=3)
    for h in hits:
        print("  -", h.metadata.get("name"), "| 标签:", h.metadata.get("tags"))

        # v3阶段5：导入完成 = 数据变了，主动让 rag 缓存失效（下次检索重新加载）
    from app_my.core.cache import invalidate_prefix
    n = invalidate_prefix("rag")
    print(f"[缓存] 已失效 rag 前缀缓存（L1 清除 {n} 条），下次检索自动加载新数据")

if __name__ == "__main__":
    main()
