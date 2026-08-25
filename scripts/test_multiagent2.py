"""阶段 4C 补充测试：复杂任务拆解，子 Agent 用工具真正干成活并汇总。"""
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
    async with websockets.connect("ws://127.0.0.1:8000/ws?session_id=ma_test2") as ws:
        await chat(ws, "帮我全面检查系统状态：磁盘空间、内存使用情况、当前主要进程，分别说明")


asyncio.run(main())
