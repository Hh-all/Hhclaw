# ClawPy

个人专属 AI 助手（OpenClaw 升级版），全 Python 技术栈，本地运行。

> 一个常驻本地的 Python 进程：聊天界面当遥控器，LLM 当大脑，工具当手脚，向量记忆当长期记忆，SKILL.md 当技能库，定时器当闹钟。

## 截图一览（均为真实运行截图）

### 首页

![首页](docs/screenshots/01-home.png)

### 工具调用

问一句「帮我看看 D 盘还剩多少空间」，Agent 自动调用 shell 工具执行 `df`，并把原始输出转成易读的结论：

![工具调用](docs/screenshots/02-tool.png)

### 记忆

「记住我叫黄河」之后，下次会话（哪怕是全新会话）再问「我叫什么」，它能从向量记忆里检索出来：

![记忆](docs/screenshots/03-memory.png)

### 多 Agent 协作

复杂任务「全面检查系统状态（磁盘/内存/进程）」被主 Agent 拆成 3 个子任务并发执行，再汇总成一份报告：

![多 Agent](docs/screenshots/04-multiagent.png)

## 架构

```
┌─────────────────────────────────────────────────────┐
│  接入层：WebChat(单文件HTML) · Telegram/微信(后置)    │
└────────────────────────┬────────────────────────────┘
                         │ WebSocket
┌────────────────────────▼────────────────────────────┐
│  Agent 执行器：主 Agent 拆解 + 子 Agent 并发（多Agent）│
│  工具层：文件 / Shell / HTTP（四层安全壳）             │
└──────┬──────────────────────────┬───────────────────┘
       │ 读写                      │ 加载
┌──────▼──────────┐        ┌──────▼──────────────┐
│ 记忆系统         │        │ 技能库 SKILL.md      │
│ 短期Redis/摘要   │        │ frontmatter+路由     │
│ 长期Qdrant+BGE  │        └─────────────────────┘
└─────────────────┘
        ▲
┌───────┴──────────┐
│ 心跳调度 APScheduler │
└──────────────────┘
```

## 核心特性

| 能力 | 实现 |
|---|---|
| 流式聊天 | FastAPI + WebSocket，打字机效果 |
| 工具调用 | 文件 / Shell / HTTP，四层安全壳（结构化调用 + 白名单 + 路径校验 + 超时） |
| 三层记忆 | Redis 短期（20 轮）→ 摘要层（每 10 轮）→ Qdrant 长期（BGE 向量检索） |
| 技能库 | SKILL.md frontmatter + 关键词路由（中文顺序匹配） |
| 心跳调度 | APScheduler 定时自主唤醒 |
| 多 Agent | 主 Agent 拆解 + 子 Agent 并发（dispatch 接口，可换 LangGraph） |

## 快速开始

```bash
cd /mnt/d/hermes_work_place/clawpy
export AGICTO_API_KEY=<你的key>          # LLM 接入
uv sync                                  # 安装依赖
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 http://localhost:8000

依赖服务（记忆系统需要）：

- Redis（`:6378`）
- Qdrant（`:16333`，原 6333 被 Windows portproxy 占用，换端口）
- BGE 嵌入服务（`:18081`，bge-small-zh-v1.5）

> 心跳默认关闭，需要时 `CLAWPY_HEARTBEAT_ENABLED=true` + `CLAWPY_HEARTBEAT_INTERVAL` 开启。

## 技术栈

Python 3.11 · FastAPI · WebSocket · LangChain 思路（手写 ReAct）· Redis · Qdrant · BGE · APScheduler · Playwright（截图）

## 项目结构

```
clawpy/
├── app/
│   ├── main.py        # 接入层 + 消息处理编排
│   ├── agent.py       # ReAct 循环（含终止条件）
│   ├── tools.py       # 工具层 + 四层安全壳
│   ├── memory.py      # 三层记忆（Redis + Qdrant/BGE）
│   ├── skills.py      # SKILL.md 技能路由
│   ├── multiagent.py  # 多 Agent 协作
│   ├── scheduler.py   # 心跳调度
│   ├── llm.py         # LLM 流式调用
│   └── config.py      # 配置
├── skills/            # 技能库
├── static/index.html  # 单文件前端（亮色、零 CDN）
├── docs/screenshots/  # README 截图
└── scripts/           # 测试 + 截图脚本
```

## 开发历史（git log）

```
73d49a5  阶段4C  多 Agent 协作
7551bed  阶段4A  心跳调度
1c22598  阶段3   技能库
d474b2c  阶段2B  摘要层 + 会话结束自动抽取
1dcca54  阶段2A  记忆系统
ed7254e  阶段0+1A 闭环 + 工具层 + 安全壳
```

完整设计文档见桌面《专属AI助手_详细设计说明书.md》。
