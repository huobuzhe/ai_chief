# app_my/knowledge/milvus_store.py —— 阶段 6（v3.0）：Milvus 向量库封装
"""
检索专用向量数据库的访问层。

设计原则（与 core/kg.py 同一哲学）：
1. 增强不是依赖：Milvus 挂了/没装 pymilvus，所有函数返回空/False，
   检索自动回退 PGVector（v1 路径），主流程永远不断。
2. 查询收口：所有 Milvus API 调用收在本模块，业务代码不认识 pymilvus。

集合结构（recipes_v2）：
    recipe_id  VARCHAR(16)  主键——菜谱 ID（如 R001），重导 upsert 按它覆盖
    text       VARCHAR(8192) 原文——与 PGVector 存的同一份菜谱文本
    vector     FLOAT_VECTOR(1024)  embedding 模型输出的 1024 维向量
    metadata   JSON         元数据（菜名/标签/热量…，检索结果直接带出）
索引：HNSW + COSINE（为什么选它见说明手册）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app_my.core.config import settings
from app_my.core.logging import logger

DIMENSION = 1024          # 必须与 embedding 模型的 dimensions 一致，不一致建表就报错

_client = None            # MilvusClient 单例（惰性创建）
_client_failed = False    # 连接失败标记：失败一次本进程不再重试（和 kg 模块同款）


def get_client():
    """惰性创建 MilvusClient 单例；不可用返回 None（调用方走回退路径）"""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    try:
        from pymilvus import MilvusClient   # 函数内导入：没装 pymilvus 时 import 本模块不报错

        _client = MilvusClient(uri=settings.MILVUS_URI)
        logger.info(f"milvus: 已连接 {settings.MILVUS_URI}")
        return _client
    except Exception as exc:
        _client_failed = True
        logger.warning(f"milvus: 不可用（{type(exc).__name__}: {exc}），向量检索回退 PGVector")
        return None


def milvus_available() -> bool:
    """Milvus 当前是否可用（retriever 用它决定走向量库还是回退）"""
    return get_client() is not None


def ensure_collection() -> bool:
    """确保集合存在（不存在就按 schema+索引建一个）；幂等"""
    client = get_client()
    if client is None:
        return False
    name = settings.MILVUS_COLLECTION
    try:
        if client.has_collection(name):
            return True                      # 已存在：直接用（幂等）
        from pymilvus import DataType

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("recipe_id", DataType.VARCHAR, is_primary=True, max_length=16)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIMENSION)
        schema.add_field("metadata", DataType.JSON)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",              # 分层可导航小世界图：高精度、低延迟
            metric_type="COSINE",           # 余弦相似度（embedding 的标准度量）
            params={"M": 16, "efConstruction": 200},
        )
        client.create_collection(collection_name=name, schema=schema, index_params=index_params)
        logger.info(f"milvus: 已创建集合 {name}（dim={DIMENSION}, HNSW/COSINE）")
        return True
    except Exception as exc:
        logger.warning(f"milvus: 建集合失败: {exc}")
        return False


def upsert_recipes(rows: List[Dict[str, Any]]) -> int:
    """
    按 recipe_id 批量写入（存在即覆盖）。
    rows 每行：{"recipe_id", "text", "vector", "metadata"}
    返回成功写入条数；失败返回 0（导入脚本据此判定要不要终止）。
    """
    client = get_client()
    if client is None or not rows:
        return 0
    try:
        result = client.upsert(collection_name=settings.MILVUS_COLLECTION, data=rows)
        return result.get("upsert_count", len(rows)) if isinstance(result, dict) else len(rows)
    except Exception as exc:
        logger.warning(f"milvus: 写入失败: {exc}")
        return 0


def clear_collection() -> bool:
    """删掉整个集合（重导前的清场；下次 ensure_collection 会重建）"""
    client = get_client()
    if client is None:
        return False
    try:
        if client.has_collection(settings.MILVUS_COLLECTION):
            client.drop_collection(settings.MILVUS_COLLECTION)
            logger.info(f"milvus: 已删除集合 {settings.MILVUS_COLLECTION}（重导前清场）")
        return True
    except Exception as exc:
        logger.warning(f"milvus: 删除集合失败: {exc}")
        return False


def vector_search(query_vector: List[float], k: int = 10) -> List[Dict[str, Any]]:
    """
    向量近邻检索。
    返回 [{"recipe_id", "content", "metadata", "score"}]（score=余弦相似度，越大越相似）；
    不可用/出错返回空列表（触发上层回退）。
    """
    client = get_client()
    if client is None:
        return []
    try:
        results = client.search(
            collection_name=settings.MILVUS_COLLECTION,
            data=[query_vector],            # 批量查询传多个向量，这里一次查一个
            limit=k,                        # 每个查询向量取前 k 个近邻
            output_fields=["text", "metadata"],   # 命中时一并带回这两个字段
            search_params={"metric_type": "COSINE", "params": {"ef": 64}},
        )
        hits: List[Dict[str, Any]] = []
        for hit in results[0]:              # results[0] = 第一个查询向量的命中列表
            entity = hit.get("entity", {}) or {}
            hits.append({
                "recipe_id": hit.get("id"),
                "content": entity.get("text", ""),
                "metadata": entity.get("metadata", {}) or {},
                "score": hit.get("distance"),   # COSINE 度量下 distance 即相似度
            })
        return hits
    except Exception as exc:
        logger.warning(f"milvus: 检索失败（回退 PGVector）: {exc}")
        return []


def collection_row_count() -> int:
    """集合内向量条数（验证导入是否成功用）"""
    client = get_client()
    if client is None:
        return 0
    try:
        stats = client.get_collection_stats(settings.MILVUS_COLLECTION)
        return int(stats.get("row_count", 0))
    except Exception:
        return 0