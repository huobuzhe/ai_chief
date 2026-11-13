# tests/unit/test_feature_flag.py
"""Feature Flag 单测：直接调 _load_flag + is_feature_enabled"""
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app_my.db.base import Base
from app_my.db.models.feature_flag import FeatureFlag
from app_my.core.feature_flag import is_feature_enabled, invalidate_cache


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _make(s, name, enabled=True, pct=0, wl=None):
    f = FeatureFlag(name=name, enabled=enabled, rollout_pct=pct, whitelist_tenants=json.dumps(wl or []))
    s.add(f)
    s.commit()
    invalidate_cache(None)
    return f


def test_disabled(db):
    _make(db, "x", enabled=False, pct=100)
    assert is_feature_enabled(db, "x", 1) is False


def test_whitelist(db):
    _make(db, "x", enabled=True, pct=0, wl=[1, 2])
    assert is_feature_enabled(db, "x", 1) is True
    assert is_feature_enabled(db, "x", 999) is False


def test_rollout_pct_0(db):
    _make(db, "x", enabled=True, pct=0)
    assert is_feature_enabled(db, "x", 1) is False


def test_rollout_pct_100(db):
    _make(db, "x", enabled=True, pct=100)
    assert is_feature_enabled(db, "x", 1) is True


def test_missing_flag(db):
    assert is_feature_enabled(db, "no_such_flag", 1) is False