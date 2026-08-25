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
