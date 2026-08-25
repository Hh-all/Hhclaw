"""补充验证：全新 session（无短期历史）问名字，答案只能来自 Qdrant 长期记忆。"""
import asyncio
import json

import websockets


async def chat(ws, text):
    print(f"=== 用户: {text} ===")
    await ws.send(text)
    full = ""
    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=90)
        obj = json.loads(msg)
        t = obj["type"]
        if t == "token":
            full += obj["content"]
        elif t == "done":
            break
        elif t == "error":
            print(f"[error] {obj['content']}")
            break
    print(f"[回复] {full[:200]}")


async def main():
    # 全新 session，无任何短期历史，只能靠 Qdrant 长期记忆检索
    async with websockets.connect("ws://127.0.0.1:8000/ws?session_id=brand_new_session_999") as ws:
        await chat(ws, "我叫什么名字？")


asyncio.run(main())
