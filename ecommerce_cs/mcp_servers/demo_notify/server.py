"""
demo_notify -- 演示版通知服务（双模：独立模块 + MCP Server）

模式 1 - 独立模块（不需要安装 mcp 包）：
    from mcp_servers.demo_notify.server import send_dingtalk, create_ticket
    result = await send_dingtalk("138xxx", "消息内容")

模式 2 - MCP Server（需要 pip install mcp）：
    python -m mcp_servers.demo_notify.server

所有通知写入 mcp_servers/demo_notify/logs/ 目录下的 JSONL 文件。
"""

import json
import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _write_log(channel: str, recipient: str, message: str, **meta):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "channel": channel,
        "recipient": recipient,
        "message": message,
        **meta,
    }
    log_file = LOG_DIR / f"{channel}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ═══════════════════════════════════════════════════════════════
# 核心函数（可直接 import 使用，不依赖 mcp 包）
# ═══════════════════════════════════════════════════════════════

async def send_dingtalk(user_id: str, message: str, title: str = "") -> dict:
    """发送钉钉消息（演示版：写入日志）"""
    e = _write_log("dingtalk", user_id, message, title=title)
    return {"success": True, "channel": "dingtalk", "recipient": user_id,
            "timestamp": e["timestamp"]}


async def send_email(to: str, subject: str, body: str) -> dict:
    """发送邮件（演示版：写入日志）"""
    e = _write_log("email", to, body, subject=subject)
    return {"success": True, "channel": "email", "recipient": to,
            "timestamp": e["timestamp"]}


async def create_ticket(title: str, priority: str = "normal", assignee: str = "") -> dict:
    """创建工单（演示版：写入日志）"""
    e = _write_log("ticket", assignee or "unassigned", title, priority=priority)
    ticket_id = f"TK-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {"success": True, "ticket_id": ticket_id, "priority": priority,
            "assignee": assignee or "unassigned", "timestamp": e["timestamp"]}


async def list_recent_notifications(channel: str = "", limit: int = 10) -> dict:
    """查看最近通知"""
    results = []
    channels = [channel] if channel else ["dingtalk", "email", "ticket"]
    for ch in channels:
        log_file = LOG_DIR / f"{ch}.jsonl"
        if not log_file.exists():
            continue
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f.readlines()[-limit:]:
                results.append(json.loads(line))
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"total": len(results), "notifications": results[:limit]}


# ═══════════════════════════════════════════════════════════════
# MCP Server 模式（pip install mcp 后可用）
# ═══════════════════════════════════════════════════════════════

def _register_mcp():
    """注册为 MCP Server -- 仅在 mcp 包可用时调用"""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
    except ImportError:
        return None

    server = Server("demo-notify")

    # 将已有函数注册为 MCP tools
    server.tool()(send_dingtalk)
    server.tool()(send_email)
    server.tool()(create_ticket)
    server.tool()(list_recent_notifications)

    @server.resource("notify://stats")
    async def get_stats() -> str:
        stats = {}
        for ch in ["dingtalk", "email", "ticket"]:
            f = LOG_DIR / f"{ch}.jsonl"
            stats[ch] = sum(1 for _ in open(f, encoding="utf-8")) if f.exists() else 0
        return json.dumps(stats, ensure_ascii=False)

    return server


# ── MCP 入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    server = _register_mcp()
    if server is None:
        print("mcp 包未安装。作为独立模块测试：")
        import asyncio
        async def test():
            r = await send_dingtalk("13800001001", "测试消息：用户张伟发起售后")
            print(f"demo-notify: {r}")
            r2 = await create_ticket("测试工单", "high", "客服001")
            print(f"demo-notify: {r2}")
            r3 = await list_recent_notifications()
            print(f"demo-notify: {len(r3['notifications'])} 条记录")
            print(f"日志目录: {LOG_DIR}")
        asyncio.run(test())
    else:
        import asyncio
        async def mcp_main():
            from mcp.server.stdio import stdio_server
            async with stdio_server() as (reader, writer):
                await server.run(reader, writer, server.create_initialization_options())
        asyncio.run(mcp_main())
