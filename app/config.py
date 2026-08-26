"""ClawPy 配置。阶段 0：环境变量 + 默认值，不引入 config.yaml（避免多余依赖）。"""
import os

# LLM 接入（OpenAI 兼容接口）
AGICTO_API_KEY = os.getenv("AGICTO_API_KEY", "")
AGICTO_BASE_URL = os.getenv("AGICTO_BASE_URL", "https://api.agicto.cn/v1")
MODEL = os.getenv("CLAWPY_MODEL", "deepseek-v4-flash")

SYSTEM_PROMPT = os.getenv(
    "CLAWPY_SYSTEM_PROMPT",
    "你是 ClawPy，一个运行在本地的个人 AI 助手。回答简洁、直接、有用，用中文。",
)

# 会话历史轮数上限（阶段 0 内存版，阶段 2 换 Redis）
MAX_HISTORY = int(os.getenv("CLAWPY_MAX_HISTORY", "20"))

# 单条消息最大长度（字符）
MAX_MESSAGE_LEN = int(os.getenv("CLAWPY_MAX_MESSAGE_LEN", "8000"))

# Agent 工具层沙箱根（阶段 0 预留，阶段 1 启用）。与项目代码目录隔离。
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "/mnt/d/workspace")

# Agent ReAct 循环终止条件（阶段 1 起用，见说明书第 5 章）
MAX_ITERATIONS = int(os.getenv("CLAWPY_MAX_ITERATIONS", "5"))
MAX_TIME = float(os.getenv("CLAWPY_MAX_TIME", "60"))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("CLAWPY_MAX_CONSECUTIVE_FAILURES", "2"))
SHELL_TIMEOUT = float(os.getenv("CLAWPY_SHELL_TIMEOUT", "30"))

# 记忆系统（阶段 2 起用，见说明书第 6 章）
# 注意：Qdrant/BGE 因 portproxy 冲突临时用新端口，删 portproxy 后改回 6333/8081
REDIS_URL = os.getenv("CLAWPY_REDIS_URL", "redis://localhost:6378")
QDRANT_URL = os.getenv("CLAWPY_QDRANT_URL", "http://localhost:16333")
BGE_URL = os.getenv("CLAWPY_BGE_URL", "http://localhost:18081")
BGE_DIM = int(os.getenv("CLAWPY_BGE_DIM", "512"))
MEMORY_COLLECTION = os.getenv("CLAWPY_MEMORY_COLLECTION", "clawpy_memory")
MEMORY_TOP_K = int(os.getenv("CLAWPY_MEMORY_TOP_K", "5"))
USER_ID = os.getenv("CLAWPY_USER_ID", "default")

# 摘要层（阶段 2B 起用）
SUMMARY_EVERY = int(os.getenv("CLAWPY_SUMMARY_EVERY", "10"))  # 每 N 轮触发摘要
SUMMARY_KEEP = int(os.getenv("CLAWPY_SUMMARY_KEEP", "3"))     # 保留最近 N 条摘要

# 心跳调度（阶段 4A 起用，见说明书第 11.3 节）
HEARTBEAT_ENABLED = os.getenv("CLAWPY_HEARTBEAT_ENABLED", "false").lower() == "true"
HEARTBEAT_INTERVAL = int(os.getenv("CLAWPY_HEARTBEAT_INTERVAL", "3600"))  # 秒，默认 1 小时
HEARTBEAT_PROMPT = os.getenv(
    "CLAWPY_HEARTBEAT_PROMPT", "检查一下当前系统状态（磁盘、内存），简要汇报"
)

# QQ 官方机器人（阶段 4B，WebSocket 网关接入，见 docs/4B-multi-platform.md）
QQ_APP_ID = os.getenv("QQ_APP_ID", "")
QQ_APP_SECRET = os.getenv("QQ_APP_SECRET", "")
# 沙箱环境 sandbox.api.sgroup.qq.com（不受 IP 白名单限制）；正式 api.sgroup.qq.com
QQ_API_BASE = os.getenv("QQ_API_BASE", "https://sandbox.api.sgroup.qq.com")
QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
# GROUP_AND_C2C_EVENT = 1<<25：单聊 C2C_MESSAGE_CREATE + 群聊 GROUP_AT_MESSAGE_CREATE
QQ_INTENTS = int(os.getenv("QQ_INTENTS", str(1 << 25)))
