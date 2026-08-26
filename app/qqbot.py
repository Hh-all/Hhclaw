"""QQ 官方机器人接入（WebSocket 网关）。

阶段 4B：Hhclaw 作为客户端主动连 QQ 官方 WebSocket 网关，
收 C2C 单聊 / 群聊 @ 事件，走 Agent 循环后通过 HTTP API 发消息。
协议见 bot.q.qq.com 官方文档，流程：token → gateway → Hello → Identify → Ready → 心跳+收事件。
"""
import asyncio
import json
import logging
import time

import httpx
import websockets

from . import config
from . import memory
from . import skills
from . import multiagent
from .agent import run_agent

logger = logging.getLogger("hhclaw.qqbot")

# access_token 缓存（有效期 7200 秒，提前 60 秒刷新）
_token: str = ""
_token_expire_at: float = 0.0

# 最新事件序列号 s（心跳时携带，Resume 用）
_latest_seq = None

# 消息去重（相同 msg_id 可能重复推送）
_seen_msg_ids: set = set()
_SEEN_MAX = 1000


async def get_access_token() -> str:
    """获取 access_token，带缓存，临近过期自动刷新。"""
    global _token, _token_expire_at
    if _token and time.time() < _token_expire_at - 60:
        return _token
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            config.QQ_TOKEN_URL,
            json={"appId": config.QQ_APP_ID, "clientSecret": config.QQ_APP_SECRET},
        )
        resp.raise_for_status()
        data = resp.json()
        _token = data["access_token"]
        _token_expire_at = time.time() + int(data.get("expires_in", 7200))
        logger.info("QQ access_token 已获取，有效期 %ss", data.get("expires_in", 7200))
    return _token


async def get_gateway_url(token: str) -> str:
    """获取 WebSocket 网关地址。"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{config.QQ_API_BASE}/gateway",
            headers={"Authorization": f"QQBot {token}"},
        )
        resp.raise_for_status()
        return resp.json()["url"]


async def send_message(token: str, target_type: str, target_id: str, text: str):
    """发消息。target_type: 'user'（单聊）| 'group'（群聊）。"""
    if target_type == "user":
        url = f"{config.QQ_API_BASE}/v2/users/{target_id}/messages"
    else:
        url = f"{config.QQ_API_BASE}/v2/groups/{target_id}/messages"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            json={"content": text, "msg_type": 0},
            headers={"Authorization": f"QQBot {token}"},
        )
        if resp.status_code != 200:
            logger.warning(
                "QQ 发消息失败 target=%s：%s %s", target_id, resp.status_code, resp.text[:200]
            )
        return resp


def _dedup(msg_id: str) -> bool:
    """消息去重，返回 True 表示已处理过。"""
    if not msg_id:
        return False
    if msg_id in _seen_msg_ids:
        return True
    _seen_msg_ids.add(msg_id)
    if len(_seen_msg_ids) > _SEEN_MAX:
        _seen_msg_ids.clear()
    return False


async def handle_qq_message(peer_type: str, peer_id: str, content: str, msg_id: str):
    """处理一条 QQ 消息：记忆检索 + Agent 循环 + 整条回复。"""
    if _dedup(msg_id):
        return
    user_text = content.strip()
    if not user_text:
        return

    session_id = f"qq:{peer_type}:{peer_id}"
    token = await get_access_token()

    if await memory.maybe_remember(user_text):
        await send_message(token, peer_type, peer_id, "已记住")

    memories = await memory.search_memory(user_text)
    history = await memory.get_history(session_id)
    summaries = await memory.get_summaries(session_id)

    system_prompt = config.SYSTEM_PROMPT
    if summaries:
        system_prompt += "\n\n【本次会话的早期摘要】\n" + "\n".join(f"- {s}" for s in summaries)
    if memories:
        system_prompt += "\n\n【关于用户，你已知的（来自长期记忆）】\n" + "\n".join(
            f"- {m}" for m in memories
        )
    skill_text = skills.render_skills(skills.route_skills(user_text))
    if skill_text:
        system_prompt += skill_text

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": user_text})

    await memory.append_message(session_id, "user", user_text)
    if len(history) + 1 >= config.SUMMARY_EVERY * 2:
        asyncio.create_task(memory.summarize_session(session_id))

    full = ""

    async def collect(event: dict):
        nonlocal full
        if event["type"] == "token":
            full += event["content"]

    async def noop(event: dict):
        return None

    try:
        subtasks = await multiagent.plan_subtasks(user_text)
        if subtasks:
            results = await multiagent.dispatch_subtasks(subtasks, noop)
            full = await multiagent.summarize(user_text, results, noop)
        else:
            await run_agent(messages, collect)
    except Exception as e:
        logger.exception("QQ Agent 执行失败 session=%s", session_id)
        full = f"调用失败：{str(e) or type(e).__name__}"

    if full:
        await memory.append_message(session_id, "assistant", full)
    await send_message(token, peer_type, peer_id, full or "（无回复）")


def _handle_dispatch(event: dict):
    """解析并分发 Dispatch 事件（单聊 + 群聊 @）。"""
    t = event.get("t")
    d = event.get("d", {})
    if t == "C2C_MESSAGE_CREATE":
        author = d.get("author", {})
        user_openid = author.get("user_openid", "")
        content = d.get("content", "")
        msg_id = d.get("id", "")
        if user_openid and content:
            asyncio.create_task(handle_qq_message("user", user_openid, content, msg_id))
    elif t == "GROUP_AT_MESSAGE_CREATE":
        group_openid = d.get("group_openid", "")
        content = d.get("content", "")
        msg_id = d.get("id", "")
        if group_openid and content:
            asyncio.create_task(handle_qq_message("group", group_openid, content, msg_id))


async def run_qqbot():
    """QQ 机器人主循环：连网关 → 鉴权 → 心跳 + 收事件，断线重连。"""
    if not config.QQ_APP_ID or not config.QQ_APP_SECRET:
        logger.warning("QQ_APP_ID / QQ_APP_SECRET 未配置，QQ 机器人不启动")
        return

    while True:
        try:
            token = await get_access_token()
            ws_url = await get_gateway_url(token)
            logger.info("QQ 连接网关：%s", ws_url)
            async with websockets.connect(ws_url, ping_interval=None) as ws:
                hello = json.loads(await ws.recv())
                heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000
                logger.info("QQ 网关已连接，心跳周期 %.0fs", heartbeat_interval)

                await ws.send(json.dumps({
                    "op": 2,
                    "d": {
                        "token": f"QQBot {token}",
                        "intents": config.QQ_INTENTS,
                        "shard": [0, 1],
                        "properties": {},
                    },
                }))

                global _latest_seq
                heartbeat_task = asyncio.create_task(_heartbeat(ws, heartbeat_interval))
                async for raw in ws:
                    event = json.loads(raw)
                    op = event.get("op")
                    if op == 0:
                        _latest_seq = event.get("s")
                        t = event.get("t")
                        if t == "READY":
                            logger.info(
                                "QQ 机器人已就绪 session_id=%s",
                                event.get("d", {}).get("session_id"),
                            )
                        else:
                            _handle_dispatch(event)
                    elif op == 9:
                        logger.error("QQ 鉴权失败（Invalid Session），检查 intents 权限")
                        raise ConnectionError("Invalid Session")
                    elif op == 7:
                        logger.warning("QQ 网关要求重连")
                        break
                heartbeat_task.cancel()
        except Exception as e:
            logger.exception("QQ 连接异常，10 秒后重连：%s", e)
            await asyncio.sleep(10)


async def _heartbeat(ws, interval: float):
    """定时发心跳，携带最新事件序列号。"""
    while True:
        await asyncio.sleep(interval)
        try:
            await ws.send(json.dumps({"op": 1, "d": _latest_seq}))
        except Exception:
            break
