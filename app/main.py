"""ClawPy 入口：FastAPI + WebSocket 接入层（阶段 0 最小闭环）。

阶段 0 范围：网页发消息 -> LLM 流式回复。无工具、无记忆、无技能。
启动顺序遵循《详细设计说明书》第 3 章（阶段 0 仅加载配置 + 启动接入层）。
"""
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from . import config
from .agent import run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("clawpy")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动顺序（阶段 0：无 Redis/Qdrant/SKILL/心跳，仅加载配置 + 接入层）
    if not config.AGICTO_API_KEY:
        logger.warning("AGICTO_API_KEY 未设置，LLM 调用将失败")
    logger.info("ClawPy 启动：model=%s base_url=%s", config.MODEL, config.AGICTO_BASE_URL)
    yield
    logger.info("ClawPy 关闭")


app = FastAPI(title="ClawPy", lifespan=lifespan)

# 连接注册表（阶段 0 存 WebSocket 对象；接入多平台时升级为投递函数抽象）
registry: dict[str, WebSocket] = {}
# 会话历史（阶段 0 内存版；阶段 2 换 Redis）
session_history: dict[str, list[dict]] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "model": config.MODEL}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    session_id = str(uuid.uuid4())
    registry[session_id] = ws
    session_history[session_id] = []
    logger.info("连接建立 session=%s", session_id)
    try:
        while True:
            text = await ws.receive_text()
            # 统一消息模型（预留 async_mode / task_id，见说明书第 4 章）
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
            # 阶段 0 会话内天然串行（while 循环 await 处理完才收下一条）
            await handle_message(session_id, msg, ws)
    except WebSocketDisconnect:
        logger.info("连接断开 session=%s", session_id)
    finally:
        registry.pop(session_id, None)
        session_history.pop(session_id, None)


async def handle_message(session_id: str, msg: dict, ws: WebSocket):
    """阶段 1 处理：Agent ReAct 循环（含工具）。"""
    history = session_history[session_id]
    history.append({"role": "user", "content": msg["text"]})
    messages = [{"role": "system", "content": config.SYSTEM_PROMPT}] + history[
        -config.MAX_HISTORY:
    ]

    async def emit(event: dict):
        await ws.send_text(json.dumps(event, ensure_ascii=False))

    await emit({"type": "thinking", "content": "思考中"})

    full = ""

    async def collect(event: dict):
        nonlocal full
        if event["type"] == "token":
            full += event["content"]
        await emit(event)

    try:
        await run_agent(messages, collect)
    except Exception as e:
        logger.exception("Agent 执行失败 session=%s", session_id)
        await emit({"type": "error", "content": f"调用失败：{str(e) or type(e).__name__}"})

    if full:
        history.append({"role": "assistant", "content": full})
    await emit({"type": "done", "content": ""})
