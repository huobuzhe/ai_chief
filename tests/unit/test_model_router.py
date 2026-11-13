# tests/unit/test_model_router.py
"""
阶段 2 单元测试：智能路由的规则与成本计算（不打真实模型、不花钱）
"""
import pytest

from app_my.core.model_router import classify_complexity, route
from app_my.core.token_billing import estimate_cost_cny, PRICE_TABLE


# ============================================================
# 复杂度判别
# ============================================================

class TestClassifyComplexity:
    def test_short_simple(self):
        assert classify_complexity("我有鸡蛋和西红柿") == "simple"

    def test_empty_is_simple(self):
        assert classify_complexity("") == "simple"

    def test_long_text_is_complex(self):
        assert classify_complexity("今天" + "菜市场买了好多东西" * 15) == "complex"

    def test_keyword_is_complex(self):
        assert classify_complexity("帮我分析一下这餐的热量") == "complex"

    def test_many_ingredients_is_complex(self):
        assert classify_complexity("鸡蛋、西红柿、青椒、土豆、牛肉、豆腐") == "complex"

    def test_few_ingredients_still_simple(self):
        assert classify_complexity("鸡蛋、西红柿、青椒") == "simple"


# ============================================================
# 路由决策
# ============================================================

class TestRoute:
    def test_extract_simple_goes_lite(self):
        assert route("extract", "我有鸡蛋和西红柿") == "lite"

    def test_extract_complex_goes_standard(self):
        assert route("extract", "帮我详细分析这些食材的营养搭配") == "standard"

    def test_report_always_standard(self):
        assert route("report", "很简单的话") == "standard"

    def test_vision_fixed(self):
        assert route("vision") == "vision"

    def test_unknown_task_falls_to_standard(self):
        assert route("nonexistent-task") == "standard"


# ============================================================
# 成本计算（价目表数学）
# ============================================================

class TestEstimateCost:
    def test_flash_basic(self):
        # 1000 输入 + 1000 输出，落在 flash 第一档：0.00024 + 0.00096 = 0.0012 元
        cost = estimate_cost_cny("qwen3.7-flash", 1000, 1000)
        assert cost == pytest.approx(0.0012)

    def test_plus_is_ten_x(self):
        # 同样 token 走 plus：0.0024 + 0.0096 = 0.012 元，正好是 flash 的 10 倍
        cost = estimate_cost_cny("qwen3.7-plus", 1000, 1000)
        assert cost == pytest.approx(0.012)
        assert cost == pytest.approx(estimate_cost_cny("qwen3.7-flash", 1000, 1000) * 10)

    def test_unknown_model_returns_none(self):
        assert estimate_cost_cny("some-unknown-model", 1000, 1000) is None

    def test_flash_tier_boundary(self):
        # 33000 输入超过 32K，应落到第二档（0.00072/0.00288）
        cost = estimate_cost_cny("qwen3.7-flash", 33_000, 1000)
        assert cost == pytest.approx(33 * 0.00072 + 1 * 0.00288)

    def test_price_table_covers_key_models(self):
        for m in ("qwen3.7-flash", "qwen3.7-plus", "qwen3.7-max"):
            assert m in PRICE_TABLE