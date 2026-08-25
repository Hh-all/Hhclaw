"""工具层：文件 / Shell / HTTP 工具 + 安全壳（四层安全壳的前三层）。

安全模型（见说明书第 7、8 章）：
1. 结构化调用：LLM 经 function calling 输出 {command, args[], ...}，subprocess list 形式 shell=False，物理免疫命令注入。
2. 命令白名单：默认拒绝，只读命令放开参数，危险命令人工确认（阶段 1A 先做只读白名单 + 危险参数拦截）。
3. 路径校验：resolve 真实路径后锁在工作区根内，防 ../ 与符号链接逃逸。
"""
import asyncio
from pathlib import Path

import httpx

from . import config

# ============ 第一层：结构化调用（工具 schema，供 LLM function calling） ============

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作区内文件的文本内容，返回内容（大文件会截断）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径，相对或绝对（必须位于工作区内）"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将文本内容写入工作区内的文件（覆盖写）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（工作区内）"},
                    "content": {"type": "string", "description": "要写入的完整文本内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出工作区内某个目录的文件列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径（工作区内），默认工作区根"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exec_shell",
            "description": "执行纯系统状态查询命令（白名单内，如 df/ps/uname/free/ping），查看系统运行状态，不能读写文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "命令名，必须为白名单内命令"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "命令参数列表，可选",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "发起 HTTP GET 请求获取外部资源（网页、公开 API）。阶段 1A 仅支持 GET。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整的 http/https URL"},
                },
                "required": ["url"],
            },
        },
    },
]

# ============ 第二层：命令白名单（默认拒绝） ============

READONLY_COMMANDS = {
    "df", "ps", "pwd", "uname", "free", "ping", "which",
    "uptime", "hostname", "date", "whoami",
}

# ============ 第三层：路径校验（resolve + 工作区根） ============

def resolve_workspace_path(path: str) -> Path:
    """把用户给的路径解析成真实路径，并校验在工作区根内，防 ../ 与软链逃逸。"""
    root = Path(config.WORKSPACE_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    if not str(p).startswith(str(root) + "/") and str(p) != str(root):
        raise PermissionError(f"路径越界：{path} 不在工作区 {root} 内")
    return p


# ============ 工具实现 ============

async def read_file(path: str) -> str:
    try:
        p = resolve_workspace_path(path)
    except PermissionError as e:
        return f"拒绝：{e}"
    if not p.is_file():
        return f"错误：文件不存在 {path}"
    try:
        data = await asyncio.to_thread(p.read_text, encoding="utf-8", errors="replace")
    except Exception as e:
        return f"错误：读取失败 {e}"
    max_len = 50000
    if len(data) > max_len:
        return data[:max_len] + f"\n...(文件共 {len(data)} 字符，已截断)"
    return data


async def write_file(path: str, content: str) -> str:
    try:
        p = resolve_workspace_path(path)
    except PermissionError as e:
        return f"拒绝：{e}"
    try:
        await asyncio.to_thread(p.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_text, content, encoding="utf-8")
    except Exception as e:
        return f"错误：写入失败 {e}"
    return f"已写入 {p}"


async def list_dir(path: str = ".") -> str:
    try:
        p = resolve_workspace_path(path)
    except PermissionError as e:
        return f"拒绝：{e}"
    if not p.is_dir():
        return f"错误：目录不存在 {path}"
    try:
        entries = await asyncio.to_thread(sorted, p.iterdir(), key=lambda x: (x.is_file(), x.name))
    except Exception as e:
        return f"错误：列目录失败 {e}"
    if not entries:
        return "(空目录)"
    lines = []
    for e in entries:
        kind = "dir " if e.is_dir() else "file"
        lines.append(f"{kind}  {e.name}")
    return "\n".join(lines)


async def exec_shell(command: str, args: list = None) -> str:
    args = args or []
    if command not in READONLY_COMMANDS:
        return f"拒绝：命令 '{command}' 不在白名单内（仅限系统状态查询命令）"
    cmd = [command] + [str(a) for a in args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=config.WORKSPACE_ROOT,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=config.SHELL_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            return f"错误：命令超时（{config.SHELL_TIMEOUT} 秒）"
        result = out.decode("utf-8", errors="replace")
        if err:
            result += "\n[stderr] " + err.decode("utf-8", errors="replace")
        return result[:50000] if result.strip() else "(无输出)"
    except Exception as e:
        return f"错误：执行失败 {e}"


async def http_request(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return "拒绝：URL 必须以 http:// 或 https:// 开头"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            content = r.text
            return content[:20000] if len(content) > 20000 else content
    except Exception as e:
        return f"错误：请求失败 {e}"


# 工具分发表
TOOL_HANDLERS = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "exec_shell": exec_shell,
    "http_request": http_request,
}


async def execute_tool(name: str, arguments: dict) -> str:
    """按 name 分发执行工具，返回结果文本。"""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"错误：未知工具 {name}"
    try:
        return await handler(**arguments)
    except TypeError as e:
        return f"错误：参数不匹配 {e}"
