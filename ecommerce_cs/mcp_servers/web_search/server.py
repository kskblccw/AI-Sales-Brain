"""
web_search MCP Server -- 网页搜索工具

基于 DuckDuckGo Instant Answer API（无需 API Key），
当 FAQ Agent 本地知识库查不到时，用此工具搜索网页获取答案。

启动：
    python -m mcp_servers.web_search.server

独立测试：
    import asyncio
    from mcp_servers.web_search.server import web_search, fetch_page
    asyncio.run(web_search("Python LangGraph tutorial"))

工具：
    web_search(query)   -- 搜索网页，返回摘要列表
    fetch_page(url)     -- 抓取网页正文
"""

import json
import asyncio
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _log(call: str, **kwargs):
    from datetime import datetime
    entry = {"timestamp": datetime.now().isoformat(), "call": call, **kwargs}
    with open(LOG_DIR / "search.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ═══════════════════════════════════════════════════════════
# 核心函数（可独立 import，不依赖 mcp 包）
# ═══════════════════════════════════════════════════════════

async def web_search(query: str, max_results: int = 5) -> dict:
    """
    搜索网页。使用 DuckDuckGo Instant Answer API，免费无需 Key。

    Args:
        query: 搜索关键词
        max_results: 返回条数（最多 10）
    """
    import urllib.parse
    import httpx

    try:
        # DuckDuckGo Instant Answer API
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()

        results = []

        # Abstract
        if data.get("AbstractText"):
            results.append({
                "title": data.get("AbstractSource", "DuckDuckGo"),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "snippet": topic["Text"],
                    "url": topic.get("FirstURL", ""),
                })

        _log("web_search", query=query, results=len(results))
        return {
            "query": query,
            "total": len(results),
            "results": results[:max_results],
        }
    except Exception as e:
        _log("web_search_error", query=query, error=str(e))
        return {"query": query, "total": 0, "results": [], "error": str(e)}


async def fetch_page(url: str) -> dict:
    """
    抓取网页正文（提取纯文本，去除 HTML 标签）。

    Args:
        url: 网页 URL
    """
    import httpx
    import re

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; EcommerceCS/1.0)"
            })
            html = resp.text

        # 简易提取：去掉 script/style 标签 + HTML 标签
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        _log("fetch_page", url=url, length=len(text))
        return {
            "url": url,
            "length": len(text),
            "content": text[:3000],  # 截断到 3000 字
        }
    except Exception as e:
        _log("fetch_page_error", url=url, error=str(e))
        return {"url": url, "length": 0, "content": "", "error": str(e)}


# ═══════════════════════════════════════════════════════════
# MCP Server 模式（pip install mcp 后可用）
# ═══════════════════════════════════════════════════════════

def _register_mcp():
    try:
        from mcp.server import Server
    except ImportError:
        return None

    server = Server("web-search")

    server.tool()(web_search)
    server.tool()(fetch_page)

    @server.resource("search://history")
    async def search_history() -> str:
        f = LOG_DIR / "search.jsonl"
        if not f.exists():
            return json.dumps([])
        with open(f, encoding="utf-8") as fp:
            return json.dumps([json.loads(line) for line in fp.readlines()[-20:]], ensure_ascii=False)

    return server


if __name__ == "__main__":
    server = _register_mcp()
    if server is None:
        print("mcp 包未安装。作为独立模块测试：")
        async def test():
            r = await web_search("Python LangGraph 电商客服")
            print(f"搜索 '{r['query']}': {r['total']} 条结果")
            for i, item in enumerate(r["results"]):
                print(f"  [{i+1}] {item['snippet'][:80]}...")

            if r["results"]:
                url = r["results"][0]["url"]
                if url:
                    print(f"\n抓取: {url}")
                    p = await fetch_page(url)
                    print(f"  内容长度: {p['length']} 字")
                    print(f"  预览: {p['content'][:100]}...")
        asyncio.run(test())
    else:
        async def mcp_main():
            from mcp.server.stdio import stdio_server
            async with stdio_server() as (reader, writer):
                await server.run(reader, writer, server.create_initialization_options())
        asyncio.run(mcp_main())
