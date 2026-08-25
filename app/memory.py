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
