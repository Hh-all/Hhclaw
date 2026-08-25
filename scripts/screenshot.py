"""README 截图脚本：Playwright 驱动 Windows Edge，截取 ClawPy 对话界面。"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

SHOTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


async def send_and_wait(page, text: str, timeout: int = 30000):
    """发送消息并等待回复完成（input 重新可用）。"""
    await page.fill("#input", text)
    await page.press("#input", "Enter")
    await page.wait_for_function("!document.getElementById('input').disabled", timeout=timeout)
    await page.wait_for_timeout(800)


async def main():
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        # 连接手动启动的 Chrome headless（CDP 端口 9222，走 WSL interop）
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = await browser.new_page(viewport={"width": 1000, "height": 720})
        await page.goto("http://localhost:8000", wait_until="networkidle")
        await page.wait_for_timeout(800)

        # 1. 首页
        await page.screenshot(path=str(SHOTS_DIR / "01-home.png"))

        # 2. 工具调用
        await send_and_wait(page, "帮我看看 D 盘还剩多少空间")
        await page.screenshot(path=str(SHOTS_DIR / "02-tool.png"))

        # 3. 记忆
        await send_and_wait(page, "记住我叫黄河，喜欢喝美式咖啡")
        await send_and_wait(page, "我叫什么名字？")
        await page.screenshot(path=str(SHOTS_DIR / "03-memory.png"))

        # 4. 多 Agent
        await send_and_wait(page, "帮我全面检查系统状态：磁盘、内存、主要进程，分别说明", timeout=90000)
        await page.screenshot(path=str(SHOTS_DIR / "04-multiagent.png"))

        await browser.close()
        print("截图完成，输出目录:", SHOTS_DIR)


asyncio.run(main())
