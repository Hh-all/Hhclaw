"""阶段 4A 测试：心跳调度（连接后等待 heartbeat 消息）。"""
import asyncio
import json

import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws?session_id=heartbeat_test") as ws:
        print("连接已建立，等待心跳触发（间隔 30 秒）...")
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=70)
                obj = json.loads(msg)
                if obj["type"] == "heartbeat":
                    print("\n收到心跳消息:")
                    print(obj["content"][:300])
                    break
        except asyncio.TimeoutError:
            print("70 秒内未收到心跳")


asyncio.run(main())
