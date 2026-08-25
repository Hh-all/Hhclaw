"""阶段 2B 测试：会话结束自动抽取长期记忆。"""
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
    print(f"[回复] {full[:150]}")


async def main():
    sid = "session_2b_test"
    # 第一段会话：陈述事实（不显式说「记住」）
    async with websockets.connect(f"ws://127.0.0.1:8000/ws?session_id={sid}") as ws:
        await chat(ws, "我最近在杭州工作，做的是大模型应用开发")
        await chat(ws, "好的，了解了")
    print("\n=== 连接已断开，等待异步抽取完成... ===")
    await asyncio.sleep(10)
    # 全新 session，验证自动抽取的事实能否被检索到
    async with websockets.connect("ws://127.0.0.1:8000/ws?session_id=brand_new_2b") as ws:
        await chat(ws, "我在哪个城市工作？做什么方向？")


asyncio.run(main())
