# 临时探针脚本：验证 WebSocket 能否穿过 Kong 网关
import asyncio
import sys

import websockets


async def probe(url: str):
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            await ws.send("ping")
            reply = await asyncio.wait_for(ws.recv(), timeout=15)
            return f"OK  {url} -> {reply}"
    except Exception as e:
        return f"FAIL {url} -> {type(e).__name__}: {e}"


async def main():
    token = sys.argv[1]
    targets = [
        f"ws://127.0.0.1:9124/ws/notifications?token={token}",   # 直连 chat 服务
        f"ws://127.0.0.1:9100/ws/notifications?token={token}",   # 经 Kong 网关
    ]
    for t in targets:
        print(await probe(t))


asyncio.run(main())
