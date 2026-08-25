# ClawPy

个人专属 AI 助手（OpenClaw 升级版），全 Python 技术栈。

## 当前阶段：阶段 0（最小闭环）

- FastAPI + WebSocket + 单文件 HTML 前端（亮色、零 CDN）
- 网页发消息 -> LLM 流式回复
- 无工具、无记忆、无技能

## 运行

```bash
cd /mnt/d/hermes_work_place/clawpy
export AGICTO_API_KEY=<在此填入你的key>
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 http://localhost:8000

## 目录结构

```
clawpy/
├── app/
│   ├── main.py      # FastAPI 入口 + WebSocket 接入层
│   ├── config.py    # 配置（环境变量 + 默认值）
│   └── llm.py       # LLM 流式调用（httpx 直连 OpenAI 兼容接口）
├── static/
│   └── index.html   # 单文件前端
├── .env.example
└── README.md
```

## 架构设计

完整设计见桌面《专属AI助手_详细设计说明书.md》。

阶段 0 待后续接入：工具层（阶段 1）、记忆系统 Redis/Qdrant（阶段 2）、SKILL.md 技能库（阶段 3）、心跳 + 多平台 + 多 Agent（阶段 4）。
