# test_security_unit.py - 纯单元测试（阶段 7）：不依赖后端服务
"""
直接测 security.py 的函数：哈希/验密、token 签发/校验。
单元测试跑得快，不需要起服务、不消耗限流配额。
"""
from app_my.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    """哈希后能验对，错密码验不过；哈希值每次都不同（带随机盐）"""
    h1 = hash_password("my-secret-123")
    h2 = hash_password("my-secret-123")
    assert h1 != h2, "同一密码两次哈希应不同（盐随机）"
    assert verify_password("my-secret-123", h1)
    assert not verify_password("wrong-password", h1)


def test_token_roundtrip():
    """签发 access token 后能解出正确的 sub 和 type"""
    token = create_access_token(42)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["type"] == "access"


def test_token_types_distinguished():
    """access 和 refresh 的 type 字段必须可区分"""
    access = decode_token(create_access_token(1))
    refresh = decode_token(create_refresh_token(1))
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"


def test_token_invalid_signature():
    """乱写的字符串解不出 payload：decode_token 返回 None 而不是抛异常"""
    assert decode_token("not-a-jwt-token") is None