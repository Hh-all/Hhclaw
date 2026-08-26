"""心跳调度：APScheduler 定时自主唤醒。见说明书第 11.3 节。

心跳任务与用户消息任务统一走 Agent（点 5 封口），
区别仅在于投递通道：有活跃连接则推送，否则静默写日志。
"""
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import config
from .agent import run_agent

logger = logging.getLogger("hhclaw")

scheduler = AsyncIOScheduler()


def start_heartbeat(registry):
    """启动心跳调度（若启用）。registry 为活跃连接表，用于投递结果。"""
    if not config.HEARTBEAT_ENABLED:
        logger.info("心跳未启用")
        return
    scheduler.add_job(
        _run_heartbeat,
        "interval",
        seconds=config.HEARTBEAT_INTERVAL,
        args=[registry],
        id="heartbeat",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("心跳已启动：每 %d 秒一次", config.HEARTBEAT_INTERVAL)


def stop_heartbeat():
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def _run_heartbeat(registry):
    logger.info("心跳触发")
    messages = [
        {"role": "system", "content": config.SYSTEM_PROMPT},
        {"role": "user", "content": config.HEARTBEAT_PROMPT},
    ]
    full = ""

    async def emit(event):
        nonlocal full
        if event["type"] == "token":
            full += event["content"]

    try:
        await run_agent(messages, emit)
    except Exception as e:
        logger.exception("心跳执行失败")
        full = f"心跳执行失败：{e}"

    text = full.strip()
    if registry:
        payload = json.dumps({"type": "heartbeat", "content": text}, ensure_ascii=False)
        for ws in list(registry.values()):
            try:
                await ws.send_text(payload)
            except Exception:
                pass
    else:
        logger.info("心跳结果（无活跃连接）：%s", text[:200])
