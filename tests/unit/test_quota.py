# tests/unit/test_quota.py
"""配额模块单测（无需真实 Redis 时，monkeypatch get_redis）"""
import pytest

from app_my.core import quota


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}

    def incrby(self, key, n):
        self.store[key] = self.store.get(key, 0) + n
        return self.store[key]

    def expire(self, key, ttl):
        pass

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(quota, "get_redis", lambda: fr)
    return fr


def test_incr_and_get(fake_redis):
    quota.incr_usage(1, "chat_daily", 3)
    assert quota.get_usage(1, "chat_daily") == 3


def test_check_quota_under(fake_redis):
    ok, _, lim = quota.check_quota(1, "free", "chat_daily")
    assert ok is True
    assert lim == 50


def test_check_quota_over(fake_redis):
    for _ in range(50):
        quota.incr_usage(2, "chat_daily")
    ok, used, lim = quota.check_quota(2, "free", "chat_daily")
    assert ok is False
    assert used == 50
    assert lim == 50


def test_get_limit_unknown(fake_redis):
    assert quota.get_limit("unknown_plan", "chat_daily") == 50  # fallback to free


def test_reset(fake_redis):
    quota.incr_usage(3, "chat_daily", 10)
    quota.reset_usage(3, "chat_daily")
    assert quota.get_usage(3, "chat_daily") == 0