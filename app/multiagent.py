"""多 Agent 协作：主 Agent 拆解 + 子 Agent 并发执行 + 汇总。

核心设计：
- 「并发执行子 Agent」抽象为 dispatch_subtasks 接口（当前 asyncio.gather 实现）。
  将来出现真正的图需求（循环/条件分支/失败重试）时，只需替换此接口实现为
  LangGraph，上层调用代码一行不改。
- 子 Agent 上下文隔离：每个子 Agent 独立 ReAct 循环，不共享主 Agent 状态。
"""
import asyncio
import json

from .llm import stream_chat
from .agent import run_agent


# ============ 接口抽象（后门） ============

async def dispatch_subtasks(subtasks: list[dict], emit=None) -> list[str]:
    """并发执行子任务，返回结果列表（与 subtasks 顺序一致）。

    子任务格式：{"goal": str}
    当前实现：asyncio.gather（线性 DAG 够用）。
    未来换 LangGraph：替换此函数内部实现，保持签名与返回不变。
    """
    async def _run_one(idx: int, subtask: dict) -> str:
        if emit:
            await emit({"type": "status", "content": f"子任务 {idx + 1}/{len(subtasks)} 执行中"})
        return await run_subagent(subtask["goal"])

    return await asyncio.gather(*(_run_one(i, t) for i, t in enumerate(subtasks)))


async def run_subagent(goal: str) -> str:
    """子 Agent：独立 ReAct 循环执行单个子任务，返回结果文本。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是 Hhclaw 的子 Agent，负责完成一个具体的子任务。"
                "专注于给定目标，可使用工具（文件/Shell/HTTP），完成后返回简洁、准确的结果。"
            ),
        },
        {"role": "user", "content": goal},
    ]
    result = ""

    async def emit(event):
        nonlocal result
        if event["type"] == "token":
            result += event["content"]

    try:
        await run_agent(messages, emit)
    except Exception as e:
        result = f"子任务执行失败：{e}"
    return result.strip()


# ============ 主 Agent（判断 + 拆解 + 汇总） ============

async def plan_subtasks(user_text: str) -> list[dict] | None:
    """主 Agent 判断任务是否需要拆解。需要则返回子任务列表，否则返回 None。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是任务规划器。判断用户请求是否需要拆解成多个并行子任务。\n"
                "- 简单任务（一句话能答、单步操作、闲聊）不需要拆解，返回 {\"split\": false}。\n"
                "- 复杂任务（需要多方面研究/分析/查询，且这些方面相互独立、可并行）拆解成 2-5 个子任务，"
                "每个子任务是一句明确的执行目标，返回 {\"split\": true, \"subtasks\": [\"子任务1\", \"子任务2\", ...]}。\n"
                "只返回 JSON，不要输出其他内容。"
            ),
        },
        {"role": "user", "content": user_text},
    ]
    text = ""
    async for event in stream_chat(messages):
        if event["type"] == "token":
            text += event["content"]
    try:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not data.get("split"):
        return None
    subtasks = data.get("subtasks", [])
    if not subtasks:
        return None
    return [{"goal": s} for s in subtasks[:5]]


async def summarize(user_text: str, results: list[str], emit) -> str:
    """主 Agent 汇总各子任务结果，流式生成最终回复。"""
    messages = [
        {
            "role": "system",
            "content": "你是 Hhclaw 的主 Agent。把多个子任务的结果汇总成一份连贯、完整、对用户有用的回复。",
        },
        {
            "role": "user",
            "content": (
                f"用户请求：{user_text}\n\n各子任务结果：\n"
                + "\n\n---\n\n".join(f"[子任务 {i + 1}]\n{r}" for i, r in enumerate(results))
            ),
        },
    ]
    full = ""
    async for event in stream_chat(messages):
        if event["type"] == "token":
            full += event["content"]
        await emit(event)
    return full
