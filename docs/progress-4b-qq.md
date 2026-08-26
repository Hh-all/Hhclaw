# QQ 接入进度记录（阶段 4B）

> 更新日期：2026-08-25（下次继续时先读这个文件）

## 当前状态

- 目标：ClawPy 阶段 4B 多平台接入，QQ 优先（NapCat 方案）
- 进度卡点：**等用户在 Windows 侧扫码登录 NapCat**（这是唯一阻塞项）
- 文件位置：`D:\hermes_work_place\napcat\`

## 今天完成的

1. 方案讨论 + 拍板：**NapCat Windows 原生**（QQ 和微信架构统一为「Windows 协议端 + WSL ClawPy + localhost」）
2. 下载 NapCat.Shell.zip（29MB，手动版）+ OneKey.zip（1MB，一键版）到 `D:\hermes_work_place\napcat\`
3. 解压确认结构，读懂了 NapCat 的启动方式（launcher.bat / NapCatInstaller.exe）

## 关键决策与踩坑记录（重要，别重蹈覆辙）

1. **go-cqhttp 已死**：2023 停维护，Android 协议被官方封死，排除。
2. **Lagrange 排除**：官方签名服务拉闸（实测 `Signer server NotFound`），登录需要第三方 NTQQ sign server（要 TG 群找，不稳定）。已下载的 36MB Lagrange 作废。
3. **NapCat Docker 排除**：镜像 1-2GB，docker.1ms.run 加速器回源慢（60s 才 1 层），Docker Hub 直连被 VPN 阻断。
4. **最终方案 NapCat Windows 原生**：内置签名（不依赖外部 sign server），Shell 仅 28MB，GitHub 直连可下。
5. **版本匹配坑**：NapCat 是 hook QQ NT 方案，版本必须匹配。NapCat v4.18.19 支持 QQ `40768~55230`（9.9.26~9.9.32），官方最新 9.9.33 可能太新。→ 因此推荐 **OneKey 一键版**（内置匹配版本 QQ NT）。

## 明天要做的（下一步，按顺序）

1. **用户在 Windows 侧操作**（扫码只能用户来）：
   - 打开 `D:\hermes_work_place\napcat\onekey_extract\`
   - 双击 `NapCatInstaller.exe`，等它自动下载 QQ NT + NapCat（几百 MB）
   - 进生成的 NapCat 目录，双击 `napcat.bat`，手机 QQ 扫码登录（勾选「下次登录无需确认」）
2. 用户扫完码后，我验证 **ClawPy 的 `/onebot/ws` 端点能否收到 NapCat 连接**
3. 配反向 WS：`ws://localhost:8000/onebot/ws`
4. 写 ClawPy 侧 `/onebot/ws` 端点代码（阶段 4B 第 2 步，目前还没写，因为用户要求先验证连接链路）

## 环境备忘

- ClawPy 跑 WSL，端口 **8000**（`app/main.py`，FastAPI + uvicorn）
- 反向 WS 目标：`ws://localhost:8000/onebot/ws`
- NapCat WebUI 端口：6099（配反向 WS 用）
- 30 天重登是硬约束，登录态持久化方案待跑通后定
- 相关设计文档：`docs/4B-multi-platform.md`（QQ + 微信接入设计基线）
