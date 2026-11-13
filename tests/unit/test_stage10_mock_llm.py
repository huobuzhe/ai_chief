# tests/unit/test_stage10_mock_llm.py —— v3 阶段 10：LLM 打桩器（纯内存，不依赖服务）
"""
为什么要有这几个用例：

    压测报告里的每个数字都建立在"LLM 被成功打桩"这个前提上。
    一旦打桩失效（比如格式改了、开关没生效），压测就会静悄悄地
    变成"在压测厂商的服务器"——数字照样出来，但全是错的，而且看不出来。

    所以把"打桩后的输出是否符合下游消费者的格式要求"固化成测试，
    是这个阶段最有价值的一道保险。

覆盖点：
    1. extract 打桩出来的内容，识别节点真的能解析出食材（不是空清单）
    2. report 打桩出来的内容非空（否则输出节点会判定失败、降级走兜底报告）
    3. 未知 task 也能返回（防御式，不 KeyError）
    4. embedding 打桩：确定性、维度正确、已归一化
    5. MOCK_LLM 开关打开时，统一入口 ainvoke_routed 真的走打桩分支

注意：和项目其它用例一致，用 asyncio.run() 在同步用例里跑协程，
      不额外引入 pytest-asyncio 配置。
"""
import asyncio
import math

import pytest

from app_my.agents.recognizer import parse_json_payload
# 🔴 这两个名字分属两个文件，别从错的那个 import：
#    ainvoke_mock      → app_my/core/mock_llm.py       （对话模型的打桩入口）
#    _mock_embedding / MOCK_DIMENSION → app_my/knowledge/embedding.py（向量打桩 + 维度常量）
#    从错的模块 import 会直接 ImportError，报错信息还会误导成"忘了定义这个常量"。
from app_my.core.mock_llm import ainvoke_mock
from app_my.knowledge.embedding import MOCK_DIMENSION, _mock_embedding


# ---------------- 1. 识别节点的打桩格式 ----------------
def test_mock_extract_能被识别节点解析出食材():
    """
    打桩的 extract 响应必须能被 parse_json_payload 抠出 JSON，且食材非空。

    为什么这条最关键：解析失败时 parse_json_payload 返回 {}（它故意不抛异常），
    于是识别节点拿到 0 种食材 → 营养/推荐/重排节点全部跳过 →
    整条链路变成"空转"。压测照样跑得飞快、QPS 漂亮，
    但测的是"什么都不干"的 QPS，报告里的数字全是假的。
    """
    response = asyncio.run(ainvoke_mock("extract", []))
    data = parse_json_payload(response.content)
    assert "ingredients" in data, "打桩响应里解析不出 ingredients 字段"
    assert len(data["ingredients"]) >= 1, "食材清单为空，链路会空转"


def test_mock_vision_和extract一样给JSON():
    """多模态分支虽然不真看图，但输出契约必须和文字分支一致。"""
    response = asyncio.run(ainvoke_mock("vision", []))
    data = parse_json_payload(response.content)
    assert len(data.get("ingredients", [])) >= 1


# ---------------- 2. 输出节点的打桩格式 ----------------
def test_mock_report_返回非空文本():
    """
    输出节点会把"空内容"当成失败，转而生成兜底报告。

    那样压测到的是兜底路径（纯字符串拼接，快得离谱），
    真实的模型调用耗时根本没被测到。
    """
    response = asyncio.run(ainvoke_mock("report", []))
    assert isinstance(response.content, str)
    assert response.content.strip(), "report 打桩返回了空文本，会触发兜底分支"


# ---------------- 3. 未知任务不炸 ----------------
def test_mock_未知task_兜底为报告文本而不报错():
    """防御式：万一以后新增任务名忘了配表，也要能跑，只是内容不对。"""
    response = asyncio.run(ainvoke_mock("some-new-task", []))
    assert response.content.strip()


# ---------------- 4. embedding 打桩 ----------------
def test_mock_embedding_同一文本两次结果完全一致():
    """
    确定性是压测可比的前提。

    这里如果用了 Python 内置的 hash() 当种子，跨进程结果会变
    （PYTHONHASHSEED 随机化），同一个查询每次检索到的菜谱都不一样，
    两轮压测就没有可比性了。用 md5 做种子就是为了锁死这一点。
    """
    a = _mock_embedding("土豆 糖尿病")
    b = _mock_embedding("土豆 糖尿病")
    assert a == b


def test_mock_embedding_不同文本给出不同向量():
    """反过来，不同输入必须给出不同向量，否则检索永远命中同一批结果。"""
    assert _mock_embedding("土豆") != _mock_embedding("牛肉")


def test_mock_embedding_维度与Milvus集合一致且已归一化():
    """
    维度对不上，pymilvus 检索时直接抛 vector dimension mismatch；
    零向量则会让余弦相似度的分母为 0。两个都是"压测跑一半全 500"的元凶。
    """
    vec = _mock_embedding("随便一段文本")
    assert len(vec) == MOCK_DIMENSION == 1024, "维度必须和 milvus_store.DIMENSION 一致"
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-6, f"向量未归一化，模长={norm}"


# ---------------- 5. 开关是否真的接通 ----------------
def test_ainvoke_routed_在开关打开时走打桩分支(monkeypatch):
    """
    验证 MOCK_LLM=true 时统一入口不碰网络、直接返回打桩内容。

    这是"开关有没有接对"的唯一证据：
    开关没接上（比如判断写在了 get_model_for_tier 里而调用方绕过了它），
    前面 4 个用例照样全绿，但压测会真调大模型—— деньги 和延迟都失控。
    """
    from app_my.core import model_router
    from app_my.core.config import settings

    monkeypatch.setattr(settings, "MOCK_LLM", True, raising=False)
    response = asyncio.run(model_router.ainvoke_routed("extract", [], text="测试输入"))
    data = parse_json_payload(response.content)
    assert len(data.get("ingredients", [])) >= 1, "开关打开后 ainvoke_routed 仍没走打桩"