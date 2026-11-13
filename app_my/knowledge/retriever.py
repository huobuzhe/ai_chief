# app_my/knowledge/retriever.py
"""
混合检索（Hybrid Search）：
- 向量检索：懂语义（"减脂" 能联想到 "低卡、高蛋白"）
- BM25 检索：懂关键词（菜名、食材的精确命中）
- 两者按 alpha 加权融合，兼顾"懂意思"和"答得准"


v3 阶段 5 升级：
- BM25 索引进程内复用（lru_cache）——之前每次检索都重建一遍索引，纯浪费
- hybrid_search 挂多级缓存——同样的问题不再打 embedding 接口和数据库
"""
from typing import Dict, List

import jieba
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from app_my.core.logging import logger
from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
from app_my.knowledge.vector_store import get_vector_store


from functools import lru_cache
from app_my.core.cache import cached



@lru_cache(maxsize=4)                      # 5,k 取值很少变，缓存几个规格就够
def _build_bm25(k: int) -> BM25Retriever:
    """用种子数据构建 BM25 索引，jieba 中文分词5,（建好一次进程内复用）"""
    recipes = load_recipes()
    docs = [
        Document(page_content=recipe_to_text(r), metadata=recipe_to_metadata(r))
        for r in recipes
    ]
    return BM25Retriever.from_documents(
        docs,
        k=k,
        preprocess_func=jieba.lcut,   #  中文分词：把"鸡胸肉减脂"切成 ["鸡胸","肉","减脂"]
    )

@cached(prefix="rag", ttl=300, null_ttl=30)   #  v3阶段5：三级缓存 + 三件套防护
def hybrid_search(query: str, k: int = 5, alpha: float = 0.7) -> List[Dict]:
    """
    混合检索：向量结果占 alpha 权重，BM25 占 (1-alpha)。

    参数：
        query : 用户的问题，如 "鸡胸肉 减脂"
        k     : 最终返回前 k 条
        alpha : 融合权重，0.7 = 向量 70% + 关键词 30%
    返回：
        [{"content": 原文, "metadata": 菜谱元数据, "score": 融合分}, ...]
    """
    store = get_vector_store()

    # --- 第 1 路：向量检索（PGVector 走标准接口；内存库走自定义接口）---
    if hasattr(store, "as_retriever"):
        retriever = store.as_retriever(search_kwargs={"k": k * 2})
        vector_hits = retriever.invoke(query)
    elif hasattr(store, "similarity_search"):
        vector_hits = store.similarity_search(query, k=k * 2)
    else:
        logger.error("Vector store 不支持任何已知检索接口")
        return []

    # --- 第 2 路：BM25 关键词检索 ---
    bm25 = _build_bm25(k * 2)
    bm25_hits = bm25.invoke(query)

    # --- 融合：倒数排名归一化（RRF 思路）---
    # 排名第 1 得 1.0 分，第 2 得 0.5 分，第 3 得 0.33 分……
    # 两路各按权重相加，同一道菜两路都命中会得高分
    def normalize(hits):
        return {h.page_content: 1.0 / (i + 1) for i, h in enumerate(hits)}

    vec_scores = normalize(vector_hits)
    bm_scores = normalize(bm25_hits)

    combined: Dict[str, float] = {}
    for content, s in vec_scores.items():
        combined[content] = alpha * s
    for content, s in bm_scores.items():
        combined[content] = combined.get(content, 0.0) + (1 - alpha) * s

    sorted_items = sorted(combined.items(), key=lambda x: -x[1])[:k]

    # --- 取回 metadata 组装结果 ---
    all_hits = list(vector_hits) + list(bm25_hits)
    result = []
    for content, score in sorted_items:
        for h in all_hits:
            if h.page_content == content:
                result.append(
                    {"content": content, "metadata": h.metadata, "score": round(score, 4)}
                )
                break
    return result


# ============================================================
# v3 阶段 6：三路混合检索 v2（向量 50% + BM25 30% + 图谱 20%）
# ============================================================

from app_my.core import kg as kg_module
from app_my.core.cache import cached as _cached_dec      # 别名避免与 v1 的 import 重复
from app_my.knowledge.embedding import embed_query
from app_my.knowledge.milvus_store import vector_search as _milvus_search
from app_my.knowledge.data_loader import load_recipes as _load_recipes_for_index

# 三路默认权重（和=1）；单路缺席时按剩余比例重分配
HYBRID_V2_WEIGHTS = {"vector": 0.5, "bm25": 0.3, "kg": 0.2}
RRF_K = 60         # RRF 平滑常数：rank r 的得分 = weight/(60+r)，头部差距被适度压平


@lru_cache(maxsize=1)
def _recipe_index_v2() -> Dict[str, dict]:
    """recipe_id -> 原始菜谱（第三路可能召回前两路没有的菜，用它补全信息）"""
    return {r["recipe_id"]: r for r in _load_recipes_for_index()}


def _vector_path(query: str, n: int) -> List[str]:
    """第一路：Milvus 向量检索（不可用自动回退 PGVector），返回 recipe_id 排名列表"""
    hits = _milvus_search(embed_query(query), k=n)
    if hits:                                              # Milvus 正常返回
        return [h["recipe_id"] for h in hits]
    # 回退：PGVector 走 v1 的两路函数拿向量结果（日志会提示 milvus 降级）
    store = get_vector_store()
    if hasattr(store, "as_retriever"):
        vh = store.as_retriever(search_kwargs={"k": n}).invoke(query)
    else:
        vh = store.similarity_search(query, k=n)
    return [h.metadata.get("recipe_id") for h in vh if h.metadata.get("recipe_id")]


def _bm25_path(query: str, n: int) -> List[str]:
    """第二路：BM25 关键词检索（阶段 5 已把索引缓存进进程），返回 recipe_id 排名列表"""
    hits = _build_bm25(n).invoke(query)
    return [h.metadata.get("recipe_id") for h in hits if h.metadata.get("recipe_id")]


def _kg_path(query: str, n: int) -> List[str]:
    """第三路：图谱结构化命中（不可用/无命中返回空 -> 上层重分配权重）"""
    return kg_module.match_recipes_from_query(query, limit=n)


def _fuse(rankings: Dict[str, List[str]], weights: Dict[str, float]) -> List[tuple]:
    """
    三路排名加权融合（RRF 变体）：
        score(doc) = Σ 路径权重 / (RRF_K + 该路径内的名次)
    任何一路为空 = 缺席：把它的权重按比例分给剩余两路（0.5:0.3 -> 0.625:0.375）。
    """
    active = {p: ids for p, ids in rankings.items() if ids}
    if not active:
        return []
    if len(active) < len(weights):                        # 有路缺席：权重重分配
        total = sum(weights[p] for p in active)
        weights = {p: (weights[p] / total) if total else 0 for p in weights}
    scores: Dict[str, float] = {}
    for path, ids in active.items():
        for rank, rid in enumerate(ids):
            scores[rid] = scores.get(rid, 0.0) + weights[path] / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


@_cached_dec(prefix="rag2", ttl=300, null_ttl=30)        # v3阶段6：v2 路径独立缓存前缀
def hybrid_search_v2(query: str, k: int = 5,
                     weights: Dict[str, float] = None) -> List[Dict]:
    """
    三路混合检索 v2：向量 50% + BM25 30% + 图谱 20%。

    与 v1（hybrid_search）的三点不同：
    1. 三路而非两路——图谱路是"事实命中"不是"相似度猜测"；
    2. 融合键是 recipe_id 而非文本——三路的输出天然对齐（文本做键会被空格/标点差异坑）；
    3. 权重重分配——Milvus/Neo4j 任何一个挂了，剩下的路按原比例接管，检索不停摆。
    """
    w = weights or HYBRID_V2_WEIGHTS
    n = k * 2                                             # 每路先取 2k 个候选再融合

    rankings = {
        "vector": _vector_path(query, n),
        "bm25": _bm25_path(query, n),
        "kg": _kg_path(query, n),
    }
    logger.info(f"hybrid_v2: 三路命中 vector={len(rankings['vector'])} "
                f"bm25={len(rankings['bm25'])} kg={len(rankings['kg'])}")

    fused = _fuse(rankings, dict(w))[:k]

    # recipe_id -> (content, metadata)：优先用向量/BM25 命中带的元数据，没有就查菜谱索引
    meta_pool: Dict[str, Dict] = {}
    for rid, _ in fused:
        base = _recipe_index_v2().get(rid)
        if base:
            meta_pool[rid] = {"content": recipe_to_text(base), "metadata": recipe_to_metadata(base)}

    return [
        {"recipe_id": rid, "content": meta_pool[rid]["content"],
         "metadata": meta_pool[rid]["metadata"], "score": round(score, 4)}
        for rid, score in fused if rid in meta_pool
    ]