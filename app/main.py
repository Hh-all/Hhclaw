"""Hhclaw 入口：FastAPI + WebSocket 接入层。

阶段 2A：短期记忆（Redis）+ 长期记忆检索（Qdrant+BGE）+ 显式记忆写入。
启动顺序遵循《详细设计说明书》第 3 章。
"""
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import config
from . import memory
from . import skills
from . import scheduler
from . import multiagent
from . import qqbot
from .agent import run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("hhclaw")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config.AGICTO_API_KEY:
        logger.warning("AGICTO_API_KEY 未设置，LLM 调用将失败")
    logger.info("Hhclaw 启动：model=%s base_url=%s", config.MODEL, config.AGICTO_BASE_URL)
    scheduler.start_heartbeat(registry)
    qqbot_task = asyncio.create_task(qqbot.run_qqbot())
    yield
    qqbot_task.cancel()
    scheduler.stop_heartbeat()
    logger.info("Hhclaw 关闭")


app = FastAPI(title="Hhclaw", lifespan=lifespan)

# 连接注册表（阶段 0 存 WebSocket 对象；接入多平台时升级为投递函数抽象）
registry: dict[str, WebSocket] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "model": config.MODEL}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    session_id = ws.query_params.get("session_id") or str(uuid.uuid4())
    registry[session_id] = ws
    logger.info("连接建立 session=%s", session_id)
    try:
        while True:
            text = await ws.receive_text()
            msg = {
                "session_id": session_id,
                "platform": "web",
                "text": text,
                "async_mode": False,
                "task_id": str(uuid.uuid4()),
            }
            if not text.strip():
                continue
            if len(text) > config.MAX_MESSAGE_LEN:
                await ws.send_text(
                    json.dumps({"type": "error", "content": "消息过长"}, ensure_ascii=False)
                )
                continue
            await handle_message(session_id, msg, ws)
    except WebSocketDisconnect:
        logger.info("连接断开 session=%s", session_id)
    finally:
        registry.pop(session_id, None)
        # 会话结束钩子：异步抽取长期记忆（不阻塞连接关闭）
        asyncio.create_task(memory.extract_and_save(session_id))


async def handle_message(session_id: str, msg: dict, ws: WebSocket):
    """阶段 2A 处理：长期记忆检索 + 短期记忆（Redis）+ Agent ReAct 循环。"""
    user_text = msg["text"]

    async def emit(event: dict):
        await ws.send_text(json.dumps(event, ensure_ascii=False))

    # 1. 显式记忆检测（用户说「记住X」）
    if await memory.maybe_remember(user_text):
        await emit({"type": "status", "content": "已记住"})

    # 2. 检索长期记忆（熔断降级，异常返回空）
    memories = await memory.search_memory(user_text)

    # 3. 取短期历史 + 摘要
    history = await memory.get_history(session_id)
    summaries = await memory.get_summaries(session_id)

    # 4. 拼 system prompt（含摘要 + 长期记忆）
    system_prompt = config.SYSTEM_PROMPT
    if summaries:
        system_prompt += "\n\n【本次会话的早期摘要】\n" + "\n".join(f"- {s}" for s in summaries)
    if memories:
        system_prompt += "\n\n【关于用户，你已知的（来自长期记忆）】\n" + "\n".join(
            f"- {m}" for m in memories
        )
    # 技能路由（关键词粗筛 + 注入命中技能正文）
    skill_text = skills.render_skills(skills.route_skills(user_text))
    if skill_text:
        system_prompt += skill_text

    # 5. 拼 messages（system + 历史 + 当前 user）
    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": user_text})

    # 6. 写 user 消息到短期记忆
    await memory.append_message(session_id, "user", user_text)

    # 7. 每 SUMMARY_EVERY 轮触发一次摘要（异步，不阻塞回复）
    if len(history) + 1 >= config.SUMMARY_EVERY * 2:
        asyncio.create_task(memory.summarize_session(session_id))

    await emit({"type": "thinking", "content": "思考中"})

    full = ""

    async def collect(event: dict):
        nonlocal full
        if event["type"] == "token":
            full += event["content"]
        await emit(event)

    try:
        # 主 Agent 判断是否需要拆解（多 Agent）
        subtasks = await multiagent.plan_subtasks(user_text)
        if subtasks:
            await emit({"type": "status", "content": f"已拆解为 {len(subtasks)} 个子任务，并发执行"})
            results = await multiagent.dispatch_subtasks(subtasks, emit)
            full = await multiagent.summarize(user_text, results, emit)
        else:
            await run_agent(messages, collect)
    except Exception as e:
        logger.exception("Agent 执行失败 session=%s", session_id)
        await emit({"type": "error", "content": f"调用失败：{str(e) or type(e).__name__}"})

    if full:
        await memory.append_message(session_id, "assistant", full)
    await emit({"type": "done", "content": ""})
