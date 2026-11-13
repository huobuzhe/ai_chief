# tests/unit/test_token_billing.py
"""
阶段 2 单元测试：Token 记账回调（不打真实模型、不碰 Redis）
"""
import pytest

import app_my.core.token_billing as tb
from app_my.core.token_billing import (
    BillingCallbackHandler,
    estimate_cost_cny,
    get_billing_stats,
    record,
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """每个测试自带隔离：清空内存账本 + 屏蔽 Redis（只测纯内存路径）。

    注意必须 patch redis_client 源模块里的 redis_available——
    token_billing 的 record/_read_book 都是函数内局部 import，
    patch billing 模块自己的引用拦不住它们。
    """
    import app_my.core.redis_client as redis_client

    tb._memory_book.clear()
    monkeypatch.setattr(redis_client, "redis_available", lambda: False)
    yield
    tb._memory_book.clear()


def _fake_response(model: str, input_tokens: int, output_tokens: int):
    """手工构造一个带 usage_metadata 的假 AIMessage/LLMResult，模拟模型返回"""
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    msg = AIMessage(content="ok")
    msg.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    msg.response_metadata = {"model_name": model}
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


class TestRecord:
    def test_record_accumulates(self):
        record("qwen3.7-flash", 100, 50)
        record("qwen3.7-flash", 200, 80)
        book = tb._memory_book["qwen3.7-flash"]
        assert book["calls"] == 2
        assert book["input_tokens"] == 300
        assert book["output_tokens"] == 130

    def test_record_error(self):
        record("qwen3.7-flash", 0, 0, ok=False)
        assert tb._memory_book["qwen3.7-flash"]["errors"] == 1


class TestCallbackHandler:
    def test_on_llm_end_records_usage(self):
        handler = BillingCallbackHandler()
        handler.on_llm_end(_fake_response("qwen3.7-plus", 500, 200))
        book = tb._memory_book["qwen3.7-plus"]
        assert book["calls"] == 1
        assert book["input_tokens"] == 500
        assert book["output_tokens"] == 200

    def test_on_llm_error_counts(self):
        handler = BillingCallbackHandler()
        handler.on_llm_error(RuntimeError("boom"))
        assert tb._memory_book["error"]["errors"] == 1

    def test_malformed_response_does_not_raise(self):
        handler = BillingCallbackHandler()
        handler.on_llm_end(None)          # 任何结构异常都不能抛出去影响业务
        assert tb._memory_book == {}


class TestStats:
    def test_stats_shape_and_savings(self):
        # lite 一笔 + standard 一笔：省钱比例应大于 0（flash 比 plus 便宜）
        record("qwen3.7-flash", 1000, 1000)
        record("qwen3.7-plus", 1000, 1000)
        stats = get_billing_stats()

        assert stats["totals"]["calls"] == 2
        assert set(stats["models"]) == {"qwen3.7-flash", "qwen3.7-plus"}
        # flash 那笔 0.0012 元，plus 那笔 0.012 元
        assert stats["models"]["qwen3.7-flash"]["estimated_cost_cny"] == pytest.approx(0.0012)
        assert stats["models"]["qwen3.7-plus"]["estimated_cost_cny"] == pytest.approx(0.012)
        # 全走 plus 的假想成本 = 0.012 + 0.012 = 0.024；实际 = 0.0132；省 45%
        assert stats["routing"]["all_standard_baseline_cny"] == pytest.approx(0.024)
        assert stats["routing"]["actual_cost_cny"] == pytest.approx(0.0132)
        assert stats["routing"]["saved_percent"] == pytest.approx(45.0)

    def test_unpriced_model_listed(self):
        record("qwen3.8-omni-flash-realtime", 800, 300)
        stats = get_billing_stats()
        assert "qwen3.8-omni-flash-realtime" in stats["unpriced_models"]
        assert stats["models"]["qwen3.8-omni-flash-realtime"]["estimated_cost_cny"] is None