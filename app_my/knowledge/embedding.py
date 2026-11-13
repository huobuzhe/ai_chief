# app_my/knowledge/embedding.py
"""
文本向量化模块。
- get_embedding_model(): 惰性单例（lru_cache），第一次调用才创建
- embed_texts() : 批量文本 -> 向量列表（导入菜谱用）
- embed_query() : 单条文本 -> 向量（用户提问时用）
"""



import hashlib
import math
import random

from functools import lru_cache
from typing import List

from langchain_openai import OpenAIEmbeddings

from app_my.core.config import settings


# Milvus 集合的向量维度，必须与真实 embedding 模型输出一致（app_my/knowledge/milvus_store.py 里 DIMENSION = 1024）。
# 打桩时如果维度对不上，pymilvus 会在检索时直接抛 "vector dimension mismatch"，
# 表现为所有 chat 请求 500 —— 所以这个数字不是随手填的。
MOCK_DIMENSION = 1024

@lru_cache()
def get_embedding_model() -> OpenAIEmbeddings:
    """惰性 embedding 单例：全局只创建一次，且没用到时不联网"""
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,          # 默认 text-embedding-v3（.env 可改）
        openai_api_key=settings.DASHSCOPE_API_KEY,   # 阿里云百炼的 Key
        openai_api_base=settings.DASHSCOPE_BASE_URL, # 百炼的 OpenAI 兼容地址
        #dimensions=1024,                         # 输出 1024 维向量
        dimensions=MOCK_DIMENSION,                         # 输出 1024 维向量
        check_embedding_ctx_length=False,        # 🔵 非官方 OpenAI 服务必须关掉
        chunk_size=10,                           # 🔵 DashScope 单次最多 10 条
    )

def _mock_embedding(text: str) -> List[float]:
    """
    给一段文本算一个"稳定的假向量"，不联网。

    两个必须做对的地方，做错了压测数据就不可信：

    1）种子用 hashlib.md5，不能用内置 hash()
       Python 3 默认开启哈希随机化（PYTHONHASHSEED），同一个字符串在不同进程里
       hash() 的结果不一样。用内置 hash() 会导致每次重启服务，同一个查询的检索结果
       都在变——压测报告里"推荐命中率"这类数字就没有可比性了。

    2）必须做 L2 归一化
       Milvus 集合用的是 COSINE（余弦相似度）度量。余弦相似度在数学上会自动除以模长，
       但全零向量会让分母为 0。归一化成单位向量后，点积就等于余弦值，
       检索分数落在 [-1, 1]，和真实 embedding 的分布一致，报告里的分数才读得懂。
    """
    # md5 取前 8 位十六进制当整数种子：稳定、跨进程一致、分布够散
    seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)                  # 用独立 Random 实例，别碰全局 random 状态
    vec = [rng.uniform(-1.0, 1.0) for _ in range(MOCK_DIMENSION)]
    norm = math.sqrt(sum(v * v for v in vec))   # 算模长（勾股定理）
    return [v / norm for v in vec]              # 每个分量除以模长 → 单位向量


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量向量化（每 10 条一批自动发送）"""
    if settings.MOCK_LLM:
        return [_mock_embedding(t) for t in texts]
    return get_embedding_model().embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """单条向量化（用户查询用）"""
    if settings.MOCK_LLM:
        return _mock_embedding(text)
    return get_embedding_model().embed_query(text)

# def embed_texts(texts: List[str]) -> List[List[float]]:
#     """批量向量化（每 10 条一批自动发送）"""
#     return get_embedding_model().embed_documents(texts)


# def embed_query(text: str) -> List[float]:
#     """单条向量化（用户查询用）"""
#     return get_embedding_model().embed_query(text)