# tests/integration/test_quota_enforcement.py
"""配额超限集成测试（默认跳过）"""
import pytest

pytestmark = pytest.mark.quota


def test_chat_quota_exceed_returns_429():
    pytest.skip("需手动验证：scripts/verify_stage4.py 已覆盖")