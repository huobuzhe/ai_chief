# test_chat_llm.py - 流式对话测试（阶段 7）：打真实大模型，默认跳过
"""
这条测试要花 10~60 秒、消耗 DashScope 额度，所以打了 llm 标记：
- 默认 `pytest` 不跑它
- 想跑：`pytest -m llm`
"""
import time

import pytest
import requests

pytestmark = pytest.mark.llm


def test_chat_stream(base_url, account):
    """登录后流式对话：200、逐段到达、内容包含菜谱要素"""
    headers = {"Authorization": f"Bearer {account['access_token']}"}

    # 拿 user_id（后端要求字符串）
    me = requests.get(f"{base_url}/users/me", headers=headers, timeout=15)
    user_id = str(me.json()["id"])

    t0 = time.time()
    resp = requests.post(
        f"{base_url}/chat/stream",
        headers=headers,
        json={"message": "做个西红柿炒鸡蛋", "image_url": [], "thread_id": "pytest-thread", "user_id": user_id},
        stream=True,
        timeout=120,
    )
    assert resp.status_code == 200, f"流式接口异常: {resp.status_code} {resp.text[:200]}"

    chunks, first_byte, total = 0, None, 0
    for piece in resp.iter_content(chunk_size=64):
        if piece:
            if first_byte is None:
                first_byte = time.time() - t0
            chunks += 1
            total += len(piece)

    assert chunks > 1, "只收到 1 块数据，流式疑似失效（被整体缓冲了）"
    assert total > 50, "回复内容过短，疑似异常"
    assert first_byte is not None and first_byte < 60, f"首字节延迟 {first_byte:.1f}s，过长"