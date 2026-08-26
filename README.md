# Hhclaw

个人专属 AI 助手（OpenClaw 升级版），全 Python 技术栈，本地运行。

> 一个常驻本地的 Python 进程：聊天界面 / QQ 当遥控器，LLM 当大脑，工具当手脚，向量记忆当长期记忆，SKILL.md 当技能库，定时器当闹钟。

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
┌───────────────────────────────────────────────────────┐
│  接入层：WebChat(单文件HTML) · QQ官方机器人 · 微信(后置) │
└──────────────────────────┬────────────────────────────┘
                           │ WebSocket / QQ官方WebSocket网关
┌──────────────────────────▼────────────────────────────┐
│  Agent 执行器：主 Agent 拆解 + 子 Agent 并发（多Agent）  │
│  工具层：文件 / Shell / HTTP（四层安全壳）               │
└────────┬──────────────────────────┬───────────────────┘
         │ 读写                      │ 加载
┌────────▼──────────┐        ┌──────▼──────────────┐
│ 记忆系统           │        │ 技能库 SKILL.md      │
│ 短期Redis/摘要     │        │ frontmatter+路由     │
│ 长期Qdrant+BGE    │        └─────────────────────┘
└───────────────────┘
          ▲
┌─────────┴──────────┐
│ 心跳调度 APScheduler │
└────────────────────┘
```

## 核心特性

| 能力 | 实现 |
|---|---|
| 流式聊天 | FastAPI + WebSocket，打字机效果 |
| QQ 官方机器人 | 腾讯 QQ 开放平台官方 WebSocket 网关接入（合规、无封号风险），支持单聊 + 群聊 @ |
| 工具调用 | 文件 / Shell / HTTP，四层安全壳（结构化调用 + 白名单 + 路径校验 + 超时） |
| 三层记忆 | Redis 短期（20 轮）→ 摘要层（每 10 轮）→ Qdrant 长期（BGE 向量检索） |
| 技能库 | SKILL.md frontmatter + 关键词路由（中文顺序匹配） |
| 心跳调度 | APScheduler 定时自主唤醒 |
| 多 Agent | 主 Agent 拆解 + 子 Agent 并发（dispatch 接口，可换 LangGraph） |

## 快速开始

```bash
cd /mnt/d/hermes_work_place/clawpy
export AGICTO_API_KEY=<你的LLM key>        # LLM 接入（OpenAI 兼容接口）
export QQ_APP_ID=<你的QQ机器人AppID>        # QQ 官方机器人（可选）
export QQ_APP_SECRET=<你的QQ机器人AppSecret> # QQ 官方机器人（可选）
uv sync                                    # 安装依赖
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 http://localhost:8000 即可用 WebChat 对话。

依赖服务（记忆系统需要）：

- Redis（`:6378`）
- Qdrant（`:16333`，原 6333 被 Windows portproxy 占用，换端口）
- BGE 嵌入服务（`:18081`，bge-small-zh-v1.5）

> 心跳默认关闭，需要时 `HHCLAW_HEARTBEAT_ENABLED=true` + `HHCLAW_HEARTBEAT_INTERVAL` 开启。

## QQ 官方机器人接入

通过腾讯 QQ 开放平台（q.qq.com）的官方机器人 API 接入，走 WebSocket 网关，合规稳定，无需 hook 逆向。

### 开通流程

1. 登录 [q.qq.com](https://q.qq.com) → 个人主体注册（邮箱 + 实名）
2. 创建机器人，拿到 **AppID** 和 **AppSecret**
3. 开发设置里把「事件订阅方式」选为 **WebSocket**
4. 配置沙箱（沙箱单聊 QQ 号 = 你自己的号），沙箱环境无需审核和公网 IP 即可测试

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `QQ_APP_ID` | 空 | 机器人 AppID |
| `QQ_APP_SECRET` | 空 | 机器人 AppSecret |
| `QQ_API_BASE` | `https://sandbox.api.sgroup.qq.com` | 沙箱环境；正式环境用 `https://api.sgroup.qq.com` |
| `QQ_INTENTS` | `1<<25`（33554432） | 订阅事件：单聊 C2C_MESSAGE_CREATE + 群聊 GROUP_AT_MESSAGE_CREATE |

### 工作原理

ClawPy 作为客户端主动连 QQ 官方 WebSocket 网关：拿 access_token → 连网关 → Identify 鉴权 → 收消息事件 → Agent 处理 → 通过 HTTP API 发消息回 QQ。群聊里需 @ 机器人才应答。

## 技术栈

Python 3.11 · FastAPI · WebSocket · 手写 ReAct 循环 · Redis · Qdrant · BGE · APScheduler · httpx · websockets · Playwright（截图）

## 项目结构

```
clawpy/
├── app/
│   ├── main.py        # 接入层（WebChat WebSocket）+ 消息处理编排
│   ├── qqbot.py       # QQ 官方机器人接入（WebSocket 网关 + 心跳 + 收发）
│   ├── agent.py       # ReAct 循环（含终止条件）
│   ├── tools.py       # 工具层 + 四层安全壳
│   ├── memory.py      # 三层记忆（Redis + Qdrant/BGE）
│   ├── skills.py      # SKILL.md 技能路由
│   ├── multiagent.py  # 多 Agent 协作
│   ├── scheduler.py   # 心跳调度
│   ├── llm.py         # LLM 流式调用
│   └── config.py      # 配置（环境变量）
├── skills/            # 技能库
├── static/index.html  # 单文件前端（亮色、零 CDN）
├── docs/screenshots/  # README 截图
└── scripts/           # 测试 + 截图脚本
```

## 开发历史（git log）

```
2ab1acc  重命名项目 ClawPy → Hhclaw
4956e5e  阶段4B  QQ 接入改为官方机器人平台（替代 NapCat 逆向）
15fdd6b  阶段4B  多平台接入设计
73d49a5  阶段4C  多 Agent 协作
7551bed  阶段4A  心跳调度
1c22598  阶段3   技能库
d474b2c  阶段2B  摘要层 + 会话结束自动抽取
1dcca54  阶段2A  记忆系统
ed7254e  阶段0+1A 闭环 + 工具层 + 安全壳
```

完整设计文档见桌面《专属AI助手_详细设计说明书.md》。
