"""阶段 4C 测试：主 Agent 拆解 + 子 Agent 并发 + 汇总。"""
import asyncio
import json

import websockets


async def chat(ws, text):
    print(f"\n=== 用户: {text} ===")
    await ws.send(text)
    full = ""
    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=180)
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
    print(f"  [回复] {full[:500]}")


async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws?session_id=ma_test") as ws:
        # 简单任务（应不拆解，走单 Agent）
        await chat(ws, "你好，用一句话介绍你自己")
        # 复杂任务（应拆解并发执行）
        await chat(ws, "分析 Hhclaw 项目的三个维度：代码结构、主要依赖、安全设计，每个维度分别说明")


asyncio.run(main())
