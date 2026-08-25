"""诊断：直接调 stream_chat，打印完整 traceback。"""
import asyncio
import traceback

from app import config
from app.llm import stream_chat


async def main():
    print("KEY 是否设置:", bool(config.AGICTO_API_KEY))
    print("KEY 前6位:", config.AGICTO_API_KEY[:6] + "..." if config.AGICTO_API_KEY else "空")
    print("BASE_URL:", config.AGICTO_BASE_URL)
    print("MODEL:", config.MODEL)
    try:
        msgs = [{"role": "user", "content": "你好，回复一个字"}]
        full = ""
        async for t in stream_chat(msgs):
            full += t
        print("OK, 回复:", full[:100])
    except Exception:
        traceback.print_exc()


asyncio.run(main())
