# conftest.py - pytest 全局夹具（阶段 7）
"""
两个夹具：
- base_url：被测后端地址，默认本机 8002，可用环境变量 TEST_BASE_URL 覆盖
- account：模块级共享账号，注册+登录一次，同模块多个测试复用（省限流配额），
  测试结束自动从数据库删除测试用户
"""
import os
import time
import uuid

import psycopg2
import pytest
import requests


def _database_dsn():
    """从项目配置里取数据库连接串，转成 psycopg2 能用的格式"""
    from app_my.core.config import settings
    url = settings.DATABASE_URL
    # SQLAlchemy 驱动前缀去掉：postgresql+psycopg2:// -> postgresql://
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return url


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("TEST_BASE_URL", "http://127.0.0.1:9002")


@pytest.fixture(scope="module")
def account(base_url):
    """注册一个临时用户并登录拿 token；用例结束后删库清理"""
    username = f"pytest_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    password = "pytest-pass-123"
    requests.post(
        f"{base_url}/auth/register",
        json={"username": username, "password": password, "email": f"{username}@test.local"},
        timeout=15,
    ).raise_for_status()
    resp = requests.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()
    yield {
        "username": username,
        "password": password,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }
    # 清理：直接删数据库里的测试用户（幂等，删不到也不报错）
    conn = psycopg2.connect(_database_dsn())
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username LIKE 'pytest_%'")
    finally:
        conn.close()