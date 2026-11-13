# test_auth.py - 鉴权接口集成测试（阶段 7）
"""
覆盖阶段 4 的核心安全行为：
注册成功/重名、登录成功/密码错、token 校验、refresh 旋转、logout 拉黑
整个模块共享一个账号（conftest 的 account 夹具），总请求数控制在 10 个以内，
不会触发 IP 级 60/分限流。
"""
import requests


def test_register_conflict(base_url, account):
    """同一用户名再注册应 409：唯一性约束生效"""
    resp = requests.post(
        f"{base_url}/auth/register",
        json={"username": account["username"], "password": "whatever-123", "email": ""},
        timeout=15,
    )
    assert resp.status_code == 409


def test_login_wrong_password(base_url, account):
    """密码错应 401，且提示不区分到底是用户不存在还是密码错"""
    resp = requests.post(
        f"{base_url}/auth/login",
        json={"username": account["username"], "password": "wrong-password"},
        timeout=15,
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户名或密码错误"


def test_me_with_token(base_url, account):
    """带 access token 访问 /users/me 返回 200 和正确用户名"""
    resp = requests.get(
        f"{base_url}/users/me",
        headers={"Authorization": f"Bearer {account['access_token']}"},
        timeout=15,
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == account["username"]


def test_me_without_token(base_url):
    """不带 token 访问 /users/me 应 401：门禁在起作用"""
    resp = requests.get(f"{base_url}/users/me", timeout=15)
    assert resp.status_code == 401


def test_refresh_rotation(base_url, account):
    """refresh 换新对成功；旧 refresh 再用一次应 401：旋转+一次性生效"""
    resp = requests.post(
        f"{base_url}/auth/refresh",
        json={"refresh_token": account["refresh_token"]},
        timeout=15,
    )
    assert resp.status_code == 200
    new_pair = resp.json()
    assert new_pair["access_token"] != account["access_token"]

    # 旧 refresh 已经被拉黑，重放必须失败
    replay = requests.post(
        f"{base_url}/auth/refresh",
        json={"refresh_token": account["refresh_token"]},
        timeout=15,
    )
    assert replay.status_code == 401


def test_logout_blacklist(base_url, account):
    """logout 后原 access token 立即失效：黑名单生效"""
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    resp = requests.post(f"{base_url}/auth/logout", headers=headers, timeout=15)
    assert resp.status_code == 200

    # 同一枚 token 再访问受保护接口必须 401
    after = requests.get(f"{base_url}/users/me", headers=headers, timeout=15)
    assert after.status_code == 401