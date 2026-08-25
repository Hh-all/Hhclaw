"""手写 ReAct 循环：调 LLM -> 执行工具 -> 回填 -> 循环，直到出最终答案或撞终止条件。

终止条件（见说明书第 5 章）：
- 最多 MAX_ITERATIONS 次工具调用轮次
- 总执行时间 MAX_TIME 秒
- 工具连续失败 MAX_CONSECUTIVE_FAILURES 次即放弃
"""
import json
import time

from . import config
from .llm import stream_chat
from .tools import TOOL_SCHEMAS, execute_tool


def preview(text: str, max_len: int = 200) -> str:
    """工具结果预览，避免把超长结果整段推给前端。"""
    text = text.strip()
    return text[:max_len] + "..." if len(text) > max_len else text


async def run_agent(messages: list[dict], emit) -> str:
    """运行 ReAct 循环。

    messages: 完整消息历史（含 system prompt）。本函数会在内部 append
              assistant/tool 中间消息，但不会持久化（由调用方决定）。
    emit: 异步回调，签名 emit(event: dict)，用于推送流式事件。
    返回：最终 assistant 文本（出错时为空串，错误已通过 emit 推送）。
    """
    start = time.monotonic()
    consecutive_failures = 0

    for _ in range(config.MAX_ITERATIONS):
        if time.monotonic() - start > config.MAX_TIME:
            await emit({"type": "error", "content": "执行超时，已中止"})
            return ""

        tool_calls = []
        text = ""
        async for event in stream_chat(messages, tools=TOOL_SCHEMAS):
            if event["type"] == "token":
                text += event["content"]
                await emit({"type": "token", "content": event["content"]})
            elif event["type"] == "tool_call":
                tool_calls.append(event)

        if not tool_calls:
            return text

        messages.append(
            {
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            await emit({"type": "tool_start", "content": f"正在执行 {tc['name']}"})
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            result = await execute_tool(tc["name"], args)
            if result.startswith(("错误", "拒绝")):
                consecutive_failures += 1
            else:
                consecutive_failures = 0
            if consecutive_failures >= config.MAX_CONSECUTIVE_FAILURES:
                await emit(
                    {"type": "error", "content": f"工具连续失败 {consecutive_failures} 次，已放弃"}
                )
                return ""
            await emit({"type": "status", "content": preview(result)})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    await emit({"type": "error", "content": "任务太复杂，请简化（迭代次数超限）"})
    return ""
