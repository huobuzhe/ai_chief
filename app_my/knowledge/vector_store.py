# app_my/knowledge/vector_store.py
"""
向量库封装。
- get_vector_store()        : 按 DATABASE_URL 自动选 PGVector（正餐）或内存库（兜底）
- clear_recipe_collection() : 清空 recipes 集合旧数据（幂等导入用）
"""
from typing import Any, Dict, List

from sqlalchemy import create_engine, text
from langchain_core.documents import Document
from langchain_postgres import PGVector

from app_my.core.config import settings
from app_my.core.logging import logger
from app_my.knowledge.embedding import get_embedding_model

RECIPE_COLLECTION = "recipes"   # 向量库里的"集合名"，类似一张逻辑表


def get_pg_engine():
    """PostgreSQL 同步引擎（阶段 1 方案 H3 修订：统一 psycopg2 同步栈）"""
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def get_vector_store():
    """按配置自动分支：postgresql -> PGVector；否则内存兜底（仅本地调试）"""
    url = settings.DATABASE_URL
    if url.startswith("postgresql"):
        return PGVector(
            connection=get_pg_engine(),          # 传引擎，PGVector 自己建表
            collection_name=RECIPE_COLLECTION,   # 集合名
            embeddings=get_embedding_model(),    # 配套的向量化模型
            use_jsonb=True,                      # 元数据用 JSONB 存储，可按字段过滤
        )
    logger.warning("DATABASE_URL 不是 postgresql，使用内存向量库（仅本地调试，重启即失）")
    return _InMemoryVectorStore()


def clear_recipe_collection() -> int:
    """
    清空 recipes 集合的全部旧向量，返回删除行数。
    作用：让导入脚本可以放心重复执行（幂等）。
    """
    engine = get_pg_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "DELETE FROM langchain_pg_embedding "
                "WHERE collection_id = "
                "(SELECT uuid FROM langchain_pg_collection WHERE name = :n)"
            ),
            {"n": RECIPE_COLLECTION},
        )
        return result.rowcount


class _InMemoryVectorStore:
    """开发用内存向量库（SQLite 模式兜底，生产必须用 PGVector）"""

    def __init__(self):
        self.docs: List[Document] = []
        self._index_built = False

    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]] = None):
        from app_my.knowledge.embedding import embed_texts
        embeddings = embed_texts(texts)
        for i, (t, emb) in enumerate(zip(texts, embeddings)):
            meta = metadatas[i] if metadatas else {}
            self.docs.append(Document(page_content=t, metadata={**meta, "_embedding": emb}))
        self._index_built = True

    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        import numpy as np
        from app_my.knowledge.embedding import embed_query
        if not self.docs:
            return []
        q = np.array(embed_query(query))
        sims = []
        for doc in self.docs:
            d = np.array(doc.metadata["_embedding"])
            # 余弦相似度：两个向量方向越接近，值越接近 1
            sim = float(np.dot(q, d) / (np.linalg.norm(q) * np.linalg.norm(d) + 1e-9))
            sims.append((sim, doc))
        sims.sort(key=lambda x: -x[0])
        return [d for _, d in sims[:k]]