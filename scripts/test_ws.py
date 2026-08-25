"""阶段 0 端到端测试：WebSocket 连接 -> 发消息 -> 收流式回复。"""
import asyncio
import json

import httpx
import websockets


async def main():
    # 1. health + 首页
    async with httpx.AsyncClient() as c:
        r = await c.get("http://127.0.0.1:8000/health")
        print("health:", r.status_code, r.json())

    # 2. WebSocket 端到端
    async with websockets.connect("ws://127.0.0.1:8000/ws") as ws:
        await ws.send("你好，用一句话介绍你自己")
        events = []
        full = ""
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=90)
            obj = json.loads(msg)
            t = obj["type"]
            events.append(t)
            if t == "token":
                full += obj["content"]
            elif t == "done":
                print("收到 done，共", len(events), "个事件")
                break
            elif t == "error":
                print("ERROR:", obj["content"])
                break
        print("事件序列:", events[:6], "..." if len(events) > 6 else "")
        print("LLM 回复:", full[:200])


asyncio.run(main())
