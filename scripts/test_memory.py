"""阶段 2A 测试：显式记忆写入 + 长期记忆检索 + 短期记忆跨连接保留。"""
import asyncio
import json

import websockets


async def chat(ws, text):
    print(f"\n=== 用户: {text} ===")
    await ws.send(text)
    full = ""
    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=90)
        obj = json.loads(msg)
        t = obj["type"]
        if t == "status":
            print(f"  [status] {obj['content'][:80]}")
        elif t == "token":
            full += obj["content"]
        elif t == "done":
            break
        elif t == "error":
            print(f"  [error] {obj['content']}")
            break
    print(f"  [回复] {full[:300]}")


async def main():
    sid = "test_session_001"
    async with websockets.connect(f"ws://127.0.0.1:8000/ws?session_id={sid}") as ws:
        await chat(ws, "记住我的名字叫黄河，我喜欢喝美式咖啡")
        await chat(ws, "你还记得我叫什么名字、喜欢喝什么吗？")
    print("\n=== 断开重连（同 session_id，验证短期记忆跨连接）===")
    async with websockets.connect(f"ws://127.0.0.1:8000/ws?session_id={sid}") as ws:
        await chat(ws, "我们刚才聊了什么？简单复述一下")


asyncio.run(main())
