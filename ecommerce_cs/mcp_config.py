"""
mcp_config.py -- MCP 客户端配置 + 工具注册

使用方式：
    from mcp_config import get_mcp_tools

    async def build_order_agent():
        mcp_tools = await get_mcp_tools()
        all_tools = LOCAL_TOOLS + mcp_tools
        ...

依赖：
    pip install langchain-mcp-adapters mcp
"""

import os
import asyncio
from typing import List

# ── MCP Server 配置 ──────────────────────────────────────────────────────────
# 每个 Server 通过 stdio 启动子进程，Client 自动管理生命周期

MCP_SERVERS = {
    "demo-notify": {
        "command": "python",
        "args": ["-m", "mcp_servers.demo_notify.server"],
        "cwd": os.path.dirname(os.path.abspath(__file__)),
    },
    "web-search": {
        "command": "python",
        "args": ["-m", "mcp_servers.web_search.server"],
        "cwd": os.path.dirname(os.path.abspath(__file__)),
    },
}

_mcp_client = None
_mcp_tools_cache: List = []


async def _init_mcp_client():
    """延迟初始化 MCP 客户端（首次调用时创建）"""
    global _mcp_client
    if _mcp_client is not None:
        return

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        _mcp_client = MultiServerMCPClient(MCP_SERVERS)
        print(f"[MCP] 已连接 {len(MCP_SERVERS)} 个 MCP Server: {list(MCP_SERVERS.keys())}")
    except ImportError:
        print("[MCP] langchain-mcp-adapters 未安装，跳过 MCP 工具加载")
        _mcp_client = False  # 标记为已尝试但不可用
    except Exception as e:
        print(f"[MCP] 初始化失败: {e}")
        _mcp_client = False


async def get_mcp_tools(refresh: bool = False) -> List:
    """
    获取所有 MCP Server 提供的工具列表

    Args:
        refresh: 强制刷新工具列表（默认使用缓存）
    """
    global _mcp_tools_cache

    await _init_mcp_client()
    if not _mcp_client:
        return []

    if _mcp_tools_cache and not refresh:
        return _mcp_tools_cache

    try:
        tools = _mcp_client.get_tools()
        _mcp_tools_cache = tools
        print(f"[MCP] 加载 {len(tools)} 个 MCP 工具: {[t.name for t in tools]}")
        return tools
    except Exception as e:
        print(f"[MCP] 获取工具列表失败: {e}")
        return []


async def refresh_mcp_tools():
    """强制刷新 MCP 工具列表（新增 Server 后调用）"""
    return await get_mcp_tools(refresh=True)


async def shutdown_mcp():
    """关闭所有 MCP 连接"""
    global _mcp_client, _mcp_tools_cache
    if _mcp_client and _mcp_client is not False:
        try:
            await _mcp_client.close()
        except Exception:
            pass
    _mcp_client = None
    _mcp_tools_cache = []
    print("[MCP] 已关闭所有连接")


# ── 同步包装（供 LangGraph 同步节点使用）───────────────────────────────────
def get_mcp_tools_sync() -> List:
    """同步获取 MCP 工具（内部使用 asyncio.run）"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(get_mcp_tools())

    # 在已有事件循环中运行
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as ex:
        return ex.submit(lambda: asyncio.run(get_mcp_tools())).result()


# ── LangChain Tool 包装（不依赖 mcp 包，直接调用 MCP 函数）───────────────
def get_langchain_mcp_tools() -> List:
    """
    将 MCP Server 中的函数包装为 LangChain @tool，供 Agent 直接使用。
    不需要安装 mcp 包，直接 import MCP Server 中的异步函数。

    返回 LangChain Tool 列表，可直接传给 llm.bind_tools()。
    """
    from langchain_core.tools import tool

    tools = []

    # ---- web_search 工具 ----
    @tool
    def mcp_web_search(query: str) -> str:
        """
        在互联网上搜索信息。当本地FAQ知识库中找不到答案时使用。
        搜索电商相关知识、产品评测、行业新闻等。

        Args:
            query: 搜索关键词
        """
        import asyncio
        from mcp_servers.web_search.server import web_search

        async def _run():
            r = await web_search(query, max_results=3)
            if r.get("error"):
                return f"搜索失败: {r['error']}"
            if not r["results"]:
                return f"未找到关于「{query}」的相关信息。"
            lines = [f"搜索「{query}」结果:"]
            for i, item in enumerate(r["results"], 1):
                lines.append(f"\n[{i}] {item['title']}\n{item['snippet'][:200]}")
            return "\n".join(lines)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_run())

        # 已有事件循环：在新线程中运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(asyncio.run, _run())
            return future.result()

    tools.append(mcp_web_search)

    # ---- 通知工具 ----
    @tool
    def mcp_create_ticket(title: str, priority: str = "normal") -> str:
        """
        创建客服工单。当用户问题需要人工跟进时使用。

        Args:
            title: 工单标题
            priority: 优先级（low/normal/high/urgent）
        """
        import asyncio
        from mcp_servers.demo_notify.server import create_ticket

        async def _run():
            r = await create_ticket(title, priority)
            return f"工单已创建: {r.get('ticket_id', 'UNKNOWN')}（优先级: {r.get('priority', 'normal')}）"

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_run())

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as ex:
            return ex.submit(asyncio.run, _run()).result()

    tools.append(mcp_create_ticket)

    return tools


# ── 独立测试入口 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def test():
        print("=" * 50)
        print("MCP 工具测试")
        print("=" * 50)

        # 测试 web_search
        print("\n[web_search] 搜索 'Python LangGraph 多智能体'...")
        from mcp_servers.web_search.server import web_search, fetch_page
        r = await web_search("Python LangGraph 多智能体", max_results=3)
        print(f"  找到 {r['total']} 条结果")
        for i, item in enumerate(r["results"]):
            print(f"  [{i+1}] {item['snippet'][:80]}...")

        # 测试 fetch_page
        if r["results"] and r["results"][0]["url"]:
            url = r["results"][0]["url"]
            print(f"\n[fetch_page] 抓取 {url[:60]}...")
            p = await fetch_page(url)
            print(f"  内容: {p['length']} 字, 预览: {p['content'][:100]}...")

        # 测试 LangChain 包装
        print("\n[LangChain Tool] 测试 mcp_web_search...")
        tools = get_langchain_mcp_tools()
        for t in tools:
            print(f"  {t.name}: {t.description[:60]}...")
        result = tools[0].invoke("电商退货政策")
        print(f"  返回: {result[:200]}...")

        print("\n所有测试通过")

    asyncio.run(test())
