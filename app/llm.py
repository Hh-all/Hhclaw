"""LLM 流式调用：OpenAI 兼容接口，支持 function calling。

yield 事件 dict：
  {"type": "token", "content": str}                     # 文本增量
  {"type": "tool_call", "id": str, "name": str, "arguments": str}  # 完整工具调用
"""
import json

import httpx

from . import config

# token 用量统计（供 /api/status 监控面板展示）
TOKEN_USAGE = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "calls": 0,
}


async def stream_chat(messages: list[dict], tools: list[dict] | None = None, model: str | None = None):
    url = f"{config.AGICTO_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.AGICTO_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or config.MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            tool_acc: dict[int, dict] = {}  # index -> {"id","name","arguments"}
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                if not data:
                    continue
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                # 捕获 usage（流式里 usage 出现在带 finish_reason 的最后一帧，只出现一次）
                usage = obj.get("usage")
                if usage:
                    TOKEN_USAGE["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    TOKEN_USAGE["completion_tokens"] += usage.get("completion_tokens", 0)
                    TOKEN_USAGE["total_tokens"] += usage.get("total_tokens", 0)
                    TOKEN_USAGE["calls"] += 1
                choice = obj["choices"][0]
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if content:
                    yield {"type": "token", "content": content}
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    acc = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        acc["name"] = fn["name"]
                    if fn.get("arguments"):
                        acc["arguments"] += fn["arguments"]
                if choice.get("finish_reason") == "tool_calls":
                    for idx in sorted(tool_acc):
                        acc = tool_acc[idx]
                        yield {
                            "type": "tool_call",
                            "id": acc["id"],
                            "name": acc["name"],
                            "arguments": acc["arguments"],
                        }
