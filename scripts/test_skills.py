"""阶段 3 测试：技能路由 + 正文注入。"""
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
    print(f"[回复] {full[:400]}")


async def main():
    code = "def get_data(conn):\n    sql = 'SELECT * FROM users WHERE id=' + user_id\n    return conn.execute(sql)\n"
    async with websockets.connect("ws://127.0.0.1:8000/ws?session_id=skills_test") as ws:
        await chat(ws, "帮我审查一下这段代码：\n" + code)


asyncio.run(main())
