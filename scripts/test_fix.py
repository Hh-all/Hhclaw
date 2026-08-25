"""验证方案 A 修复：越界读文件应被拦截，正常功能应保留。"""
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
        if t == "tool_start":
            print(f"  [tool_start] {obj['content']}")
        elif t == "status":
            print(f"  [status] {obj['content'][:100]}")
        elif t == "token":
            full += obj["content"]
        elif t == "done":
            break
        elif t == "error":
            print(f"  [error] {obj['content']}")
            break
    print(f"  [回复] {full[:200]}")


async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws") as ws:
        await chat(ws, "读一下 /etc/passwd 文件的内容")
        await chat(ws, "读一下 hello.txt 的内容")
        await chat(ws, "用 free 命令看看内存")


asyncio.run(main())
