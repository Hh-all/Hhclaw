"""记忆系统：短期（Redis）+ 长期（Qdrant + BGE）。见说明书第 6 章三层漏斗。

阶段 2A 实现：短期记忆 + 长期记忆检索 + 显式「记住X」写入。
熔断降级：任何依赖服务异常都静默降级（返回空/False），不阻塞主流程。
"""
import json
import time
import uuid

import httpx
import redis.asyncio as redis

from . import config
from .llm import stream_chat

# 短期记忆 Redis 客户端
_redis = redis.from_url(config.REDIS_URL, decode_responses=True)

# ============ 短期记忆（Redis List，20 轮环形） ============

def _history_key(session_id: str) -> str:
    return f"clawpy:session:{session_id}:history"


async def get_history(session_id: str) -> list[dict]:
    """取会话历史（最近 MAX_HISTORY 轮，按时间顺序）。"""
    try:
        raw = await _redis.lrange(_history_key(session_id), 0, -1)
        return [json.loads(x) for x in raw]
    except Exception:
        return []


async def append_message(session_id: str, role: str, content: str):
    """追加一条消息，保持最近 MAX_HISTORY 轮（每轮 user+assistant 共 2 条）。"""
    try:
        key = _history_key(session_id)
        await _redis.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
        await _redis.ltrim(key, -config.MAX_HISTORY * 2, -1)
    except Exception:
        pass


# ============ 长期记忆（Qdrant + BGE） ============

async def embed(texts: list[str]) -> list[list[float]]:
    """BGE 嵌入，返回向量列表。"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{config.BGE_URL}/embed", json={"inputs": texts})
        r.raise_for_status()
        return r.json()


async def _ensure_collection(client: httpx.AsyncClient):
    """确保长期记忆 collection 存在，不存在则创建（512 维 Cosine）。"""
    url = f"{config.QDRANT_URL}/collections/{config.MEMORY_COLLECTION}"
    r = await client.get(url)
    if r.status_code == 404:
        await client.put(
            url,
            json={"vectors": {"size": config.BGE_DIM, "distance": "Cosine"}},
        )


async def search_memory(query: str, top_k: int | None = None) -> list[str]:
    """检索长期记忆，返回相关事实文本列表。任何异常返回空列表（熔断降级）。"""
    top_k = top_k or config.MEMORY_TOP_K
    if not query.strip():
        return []
    try:
        vec = (await embed([query]))[0]
    except Exception:
        return []
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await _ensure_collection(client)
            r = await client.post(
                f"{config.QDRANT_URL}/collections/{config.MEMORY_COLLECTION}/points/search",
                json={"vector": vec, "limit": top_k, "with_payload": True},
            )
            if r.status_code != 200:
                return []
            data = r.json()
            return [
                item["payload"]["text"]
                for item in data.get("result", [])
                if item.get("payload", {}).get("text")
            ]
        except Exception:
            return []


async def save_memory(text: str, fact_type: str = "knowledge") -> bool:
    """写入长期记忆。失败返回 False（不抛出）。"""
    text = text.strip()
    if not text:
        return False
    try:
        vec = (await embed([text]))[0]
    except Exception:
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await _ensure_collection(client)
            await client.put(
                f"{config.QDRANT_URL}/collections/{config.MEMORY_COLLECTION}/points",
                json={
                    "points": [
                        {
                            "id": str(uuid.uuid4()),
                            "vector": vec,
                            "payload": {
                                "text": text,
                                "fact_type": fact_type,
                                "user_id": config.USER_ID,
                                "timestamp": int(time.time()),
                            },
                        }
                    ]
                },
            )
            return True
        except Exception:
            return False


async def maybe_remember(text: str) -> bool:
    """检测用户是否显式要求记住某事，是则写入长期记忆。返回是否命中。"""
    prefixes = ("记住", "记一下", "记着", "别忘了", "帮我记住", "请记住", "记好")
    for prefix in prefixes:
        if text.startswith(prefix):
            content = text[len(prefix):].strip()
            if content:
                return await save_memory(content)
    return False


# ============ 摘要层 + 会话结束自动抽取（阶段 2B） ============

def _summary_key(session_id: str) -> str:
    return f"clawpy:session:{session_id}:summary"


async def get_summaries(session_id: str) -> list[str]:
    """取会话摘要（最近 SUMMARY_KEEP 条）。"""
    try:
        return await _redis.lrange(_summary_key(session_id), 0, -1)
    except Exception:
        return []


async def summarize_session(session_id: str):
    """对当前会话历史做一次 LLM 摘要，追加到 summary。"""
    history = await get_history(session_id)
    if len(history) < 6:  # 至少 3 轮才摘要
        return
    text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in history)
    messages = [
        {"role": "system", "content": "你是对话摘要器。把下面这段对话压缩成 2-3 句话的摘要，保留关键事实、结论和用户意图。"},
        {"role": "user", "content": text},
    ]
    summary = ""
    try:
        async for event in stream_chat(messages):
            if event["type"] == "token":
                summary += event["content"]
    except Exception:
        return
    summary = summary.strip()
    if summary:
        try:
            await _redis.rpush(_summary_key(session_id), summary)
            await _redis.ltrim(_summary_key(session_id), -config.SUMMARY_KEEP, -1)
        except Exception:
            pass


async def extract_and_save(session_id: str):
    """会话结束时，从历史抽取可复用事实写入长期记忆（异步，不阻塞）。"""
    history = await get_history(session_id)
    if len(history) < 4:  # 太短不抽取
        return
    text = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history)
    messages = [
        {"role": "system", "content": "你是记忆抽取器。从对话中抽取用户的长期有效事实（姓名、偏好、个人信息、重要结论），每条一行，只输出事实本身，不要编号或解释。没有可抽取的就输出空。"},
        {"role": "user", "content": text},
    ]
    result = ""
    try:
        async for event in stream_chat(messages):
            if event["type"] == "token":
                result += event["content"]
    except Exception:
        return
    for line in result.strip().splitlines():
        line = line.strip().strip("-•*0123456789.、 ").strip()
        if line and len(line) > 2:
            await save_memory(line)
