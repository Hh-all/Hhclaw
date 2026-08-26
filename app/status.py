"""系统状态监控：/api/status 接口 + MCP 注册表。

借鉴 OpenClaw Dashboard 的监控思路：系统指标（CPU/内存/磁盘）+ 依赖服务健康 +
token 用量 + MCP 服务器方块。前端定时轮询本接口刷新监控面板。
"""
import asyncio
import shutil
import time

import httpx

from . import config
from . import llm
from . import memory

# 进程启动时间（算 uptime）
_START_TIME = time.time()

# MCP 服务器注册表：name -> {"name", "status", "info"}
# 未来 MCP 接入时调用 register_mcp() 注册，前端自动多一个方块。
MCP_SERVERS: dict[str, dict] = {}


def register_mcp(name: str, info: str = "", status: str = "running"):
    """注册一个 MCP 服务器。name 唯一标识；info 展示在方块里。"""
    MCP_SERVERS[name] = {"name": name, "status": status, "info": info}


def _read_cpu_times():
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
    idle = int(parts[3]) + int(parts[4])
    total = sum(int(x) for x in parts)
    return idle, total


async def get_cpu_percent() -> float:
    """CPU 使用率（两次采样差值）。"""
    idle1, total1 = _read_cpu_times()
    await asyncio.sleep(0.1)
    idle2, total2 = _read_cpu_times()
    idle_d = idle2 - idle1
    total_d = total2 - total1
    if total_d == 0:
        return 0.0
    return round((1 - idle_d / total_d) * 100, 1)


def get_memory() -> dict:
    """内存（读 /proc/meminfo，单位字节）。"""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, val = line.partition(":")
            info[key] = int(val.split()[0]) * 1024
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    return {
        "total": total,
        "used": total - available,
        "percent": round((total - available) / total * 100, 1) if total else 0.0,
    }


def get_disk() -> dict:
    """磁盘（D 盘，项目所在盘）。"""
    usage = shutil.disk_usage("/mnt/d")
    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": round(usage.used / usage.total * 100, 1),
    }


async def check_services() -> dict:
    """依赖服务健康检查（短超时，异常视为离线）。"""
    result = {}

    try:
        await asyncio.wait_for(memory._redis.ping(), timeout=2)
        result["redis"] = True
    except Exception:
        result["redis"] = False

    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{config.QDRANT_URL}/collections")
            result["qdrant"] = r.status_code == 200
    except Exception:
        result["qdrant"] = False

    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{config.BGE_URL}/health")
            result["bge"] = r.status_code == 200
    except Exception:
        result["bge"] = False

    result["llm"] = bool(config.AGICTO_API_KEY)
    return result


async def get_status() -> dict:
    """汇总状态（供 /api/status）。"""
    return {
        "system": {
            "cpu": await get_cpu_percent(),
            "memory": get_memory(),
            "disk": get_disk(),
        },
        "services": await check_services(),
        "tokens": dict(llm.TOKEN_USAGE),
        "mcp": list(MCP_SERVERS.values()),
        "uptime": int(time.time() - _START_TIME),
    }
