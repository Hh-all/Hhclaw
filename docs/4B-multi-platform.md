# 4B 多平台接入设计（QQ + 微信）

> 优先级：QQ > 微信 > Telegram（后置）
> 状态：开发基线，落定后进入 4B 开发

## 0. 总览

```
                        ┌─────────────────────────────────┐
                        │        ClawPy（WSL，Python）      │
                        │  ┌───────────────────────────┐  │
                        │  │   连接注册表 Connection      │  │
                        │  │   Registry + 投递函数抽象    │  │
                        │  └───────────────────────────┘  │
                        │         /onebot/ws 端点          │
                        │         /bridge/ 端点            │
                        └───────┬──────────────────┬──────┘
                                │ OneBot 11 (WS)   │ localhost HTTP
                    ┌───────────┴───────┐   ┌──────┴───────────────┐
                    │ NapCat Docker ×N   │   │ 微信桥接脚本(Windows原生) │
                    │ (每实例 = 1个QQ号)  │   │ wechatferry hook       │
                    └───────────────────┘   └──────────────────────┘
```

关键差异（决定部署拓扑）：

- **QQ 能与 ClawPy 同机**：NapCat 跑 Docker（WSL 的 Docker），与 ClawPy 同机，走 OneBot 11 反向 WebSocket。
- **微信必须拆 Windows 原生桥接进程**：wechatferry 注入 PE 格式 DLL，只能在原生 Windows 跑，ClawPy 在 WSL，两者走 localhost HTTP。

---

## 1. QQ 接入

### 1.1 底层引擎：NapCat

- 选型结论：**NapCat（NapCatQQ）**。
- 理由：社区最活跃、文档最全、协议变更响应快；Docker 部署与现有基础设施（Redis/Qdrant 均在 Docker）一致。
- 已否掉 go-cqhttp：2023 年官方停维护（issue #2471），其依赖的 Android 协议 + sign-server 已被官方封死，基本不可用。
- 备选：Lagrange.Core（无头，15MB，最轻量）作为降级/省资源方案，不主动采用。

### 1.2 事件订阅方式（OneBot 11）

NapCat 实现 OneBot 11 协议，三种通信模式：

| 模式 | 方向 | 评价 |
|------|------|------|
| 正向 WebSocket | ClawPy 主动连 bot 6700 端口 | 不选 |
| **反向 WebSocket** | **bot 主动连 ClawPy 的 `/onebot/ws`** | **选定，ClawPy 只维护一个 WS 服务** |
| HTTP POST | bot 把事件 POST 到 `/onebot/event` | 备用 |

事件按 `post_type` 分四类：`message`（消息）、`notice`（进群/退群/戳一戳）、`request`（加好友/群申请）、`meta_event`（心跳）。阶段 4B 只订阅 `message` + `meta_event.heartbeat`（心跳当存活探针），其余忽略。

### 1.3 消息格式转换

OneBot 消息是分段数组，每段带 `type`：

```json
[
  {"type": "text",  "data": {"text": "帮我查"}},
  {"type": "at",    "data": {"qq": "12345"}},
  {"type": "image", "data": {"url": "..."}}
]
```

转 ClawPy 内部消息模型（说明书第 4 章）：

- `text` 段 → 拼接为 `text` 字段。
- `at` 段 → 判断是否 @ 自己（决定应不应答）+ 提取被 @ 人。
- `image` / `file` 段 → 提取 url → 下载到本地 → 转附件字段。
- 反向发送：ClawPy 统一消息 → 按内容拆 `text` / `image` 段 → 调 `/send_msg` API。

### 1.4 部署方式

- NapCat 官方 Docker 镜像（内置无头 NTQQ），一条 `docker run` 起，走国内加速器。
- 两条硬限制：
  1. **不能同时登 PC 版 QQ**（会挤下线）。
  2. **每 30 天需重新扫码登录一次**。

### 1.5 多账号场景（补充点 1）

**硬约束：一个 NapCat 实例 = 一个 QQ 号。** 不存在「单实例多账号」，这是 NapCat/OneBot 的本质（一个进程持有一份 NTQQ 登录态）。

结论：**多账号 = 多容器（多实例）**，每号一个 NapCat 容器，各自反向 WS 连到 ClawPy 的同一个 `/onebot/ws` 端点。

账号区分机制：

- OneBot 握手/事件里带 `self_id`（bot 自己的 QQ 号），ClawPy 用它作为连接的唯一 key，注册进连接注册表。
- **内部 user_id 两级化**：多账号下，`user_id` 必须带上 bot 账号维度，否则两个号各自的「张三」会串记忆。

```
user_id = f"{bot_self_id}:{peer_qq}"   # 例: "10001:88888"
```

影响面：记忆系统（说明书第 6 章）按 user_id 隔离，多账号不能串记忆；连接注册表、投递函数都要以 `bot_self_id` 作为一级维度。

个人助手量级：个人号 + 测试号 = 2 个容器，量级小，无需复杂编排。

---

## 2. 微信接入

### 2.1 选型：wechatferry（Windows Hook）

微信无官方 bot API，三条路只有一条现实可行：

| 方案 | 协议 | 现状 |
|------|------|------|
| itchat | Web | 2017 后注册号基本墙死，排除 |
| **wechatferry** | **Windows Hook（注入 DLL）** | **选定** |
| WeChatPadPro | iPad 协议（Docker） | 备用，风控略低但部署重 |

关键约束：

- 只能跑**原生 Windows**（PE 格式 DLL，WSL 跑不了）。
- 只支持微信 **3.9.x**，4.x 不支持，需用降级版微信。

### 2.2 收消息 + 被动回复流程

```
微信进程 --(DLL hook)--> wcferry 回调 --> 桥接脚本(Windows原生)
                                          │
                                          ├─ 白名单过滤(只应答目标群/好友)
                                          ├─ 转 ClawPy 统一消息模型
                                          └─ localhost HTTP 发给 ClawPy
ClawPy 回复 --> 桥接脚本 --> wcferry 发送接口 --> 微信被动回复
```

要点：**只被动回复，不主动群发**（风控最低）；桥接脚本跑 Windows 原生，ClawPy 跑 WSL，两者 localhost 通信。

### 2.3 异常处理（补充点 2）

分三层，自愈边界清晰：

**层级 1：桥接脚本进程崩溃 → Windows 侧自动拉起，ClawPy 无需介入**

- 用 Windows 任务计划程序（Task Scheduler）或 NSSM 守护桥接脚本，进程退出即自动重启。
- ClawPy 不直接拉起 Windows 侧进程（跨系统，做不到也不该做）。

**层级 2：微信进程崩溃 / 掉线 / hook 失效 → 桥接脚本检测 + 尝试重启**

- wechatferry 的 hook 断开会触发回调/异常，桥接脚本捕获后尝试重启微信进程。
- 若登录态失效需要重新扫码，桥接脚本无法代扫 → **告警用户人工介入**（这是微信接入的固有上限，不是 bug）。

**层级 3：ClawPy 侧心跳监测 → 感知失联 + 降级**

- 桥接脚本每 30s 向 ClawPy 发 `POST /bridge/heartbeat`。
- ClawPy 超过 90s 未收到心跳 → 将该连接标记 `offline`，投递函数静默/丢弃（个人助手场景不缓存），记日志，**不阻塞其他平台**（QQ 照常）。
- 桥接自愈后重新注册连接 → 恢复 `online`。

设计咬合：这正好落在说明书方案 C 的「连接注册表 + 投递函数抽象」上——投递函数内部封装断线重试；桥接失联时投递返回失败，ClawPy 标记连接离线，与 QQ 连接同等对待。

### 2.4 风控策略

微信打击 bot 的核心是「识别非人类行为」：

1. **小号跑**，别用主号。
2. **限频 + 随机延迟**：回复前加 0.5~2 秒抖动，不秒回。
3. **只被动、不主动**：不主动加人/群发，主动动作是最高危信号。
4. **降级号别升微信**：升 4.x 就得重新降。
5. **目标群白名单**：只在指定群应答，不全局自动回复。
6. **紧急停止开关**：桥接脚本留一键停，账号异常立即停。

---

## 3. 连接注册表与投递函数（统一抽象）

两个平台、多个账号，最终都归入同一个抽象：

| 连接 | 标识 key | 投递函数封装 |
|------|---------|-------------|
| NapCat 实例 ×N | `bot_self_id` | OneBot `/send_msg` API 调用 |
| 微信桥接 ×1 | `bridge_id` | localhost HTTP → wcferry 发送接口 |

- ClawPy 的 Agent 执行器只认「连接 key + 消息内容」，不碰「怎么投」。
- 多账号、多平台、断线重连、静默降级，全部藏在各投递函数内部。
- 未来加 Telegram（后置），只需再注册一个「Telegram 投递函数」，Agent 执行器零改动。

---

## 4. 排期待办

- [ ] 补 NapCat Docker 镜像选型与登录态持久化方案（30 天重登的自动化程度）
- [ ] 补微信桥接脚本的 wcferry 版本锁定（与降级版微信版本匹配）
- [ ] 阶段 4B 开发：先 QQ（NapCat + OneBot 反向 WS + 连接注册表），后微信（桥接脚本）
- [ ] Telegram 后置，仅预留连接注册表接口，不实现
