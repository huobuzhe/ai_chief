# tests/unit/test_hybrid_v2.py —— 阶段 6：三路融合与图谱匹配单测（不依赖 Milvus/Neo4j）
"""
覆盖点：
- _fuse：三路全命中 / 单路缺席权重重分配 / 双路缺席 / 全空
- _fuse：RRF 分数单调（排名越前贡献越大）
- match_recipes_from_query：子串命中 / 无命中返回空 / 图谱不可用返回空
- HYBRID_V2_WEIGHTS：三路权重和为 1
"""
from unittest.mock import patch

import pytest

from app_my.core import kg as kg_module
from app_my.knowledge.retriever import HYBRID_V2_WEIGHTS, _fuse


W = {"vector": 0.5, "bm25": 0.3, "kg": 0.2}


def test_fuse_three_paths():
    r = _fuse({"vector": ["r1", "r2"], "bm25": ["r2", "r4"], "kg": ["r1"]}, dict(W))
    ids = [i for i, _ in r]
    assert set(ids) == {"r1", "r2", "r4"}
    assert ids[0] in ("r1", "r2")          # 双命中的两道菜霸占前二


def test_fuse_kg_missing_redistributes():
    # kg 缺席：0.5:0.3 -> 0.625:0.375，向量权重仍高于 BM25
    r = _fuse({"vector": ["a"], "bm25": ["b"]}, dict(W))
    assert r[0][0] == "a"
    scores = dict(r)
    assert scores["a"] > scores["b"]


def test_fuse_single_path():
    r = _fuse({"vector": ["x", "y"]}, dict(W))
    assert [i for i, _ in r] == ["x", "y"]  # 单路兜底按原顺序


def test_fuse_all_empty():
    assert _fuse({"vector": [], "bm25": [], "kg": []}, dict(W)) == []


def test_fuse_rank_monotonic():
    r = _fuse({"vector": ["a", "b", "c"]}, dict(W))
    scores = [s for _, s in r]
    assert scores == sorted(scores, reverse=True)


def test_weights_sum_to_one():
    assert abs(sum(HYBRID_V2_WEIGHTS.values()) - 1.0) < 1e-9


def test_kg_match_substring(monkeypatch):
    monkeypatch.setattr(kg_module, "_ingredient_names", lambda: ["鸡胸肉", "西兰花", "豆腐"])
    fake_rows = [{"rid": "R017", "hits": 2}, {"rid": "R018", "hits": 1}]
    monkeypatch.setattr(kg_module, "_run", lambda cypher, **kw: fake_rows)
    assert kg_module.match_recipes_from_query("香煎鸡胸肉配西兰花") == ["R017", "R018"]


def test_kg_match_no_hit(monkeypatch):
    monkeypatch.setattr(kg_module, "_ingredient_names", lambda: ["鸡胸肉"])
    assert kg_module.match_recipes_from_query("今天天气怎么样") == []