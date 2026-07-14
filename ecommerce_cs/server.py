"""
server.py — FastAPI 后端 + SSE 流式端点

启动方式：
    python server.py
    uvicorn server:app --reload --port 8000
"""

import json
import uuid
import asyncio
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage

from graph import build_csr_graph, CSRState
from rag import build_product_knowledge_base

# ── FastAPI 应用 ────────────────────────────────────────────────────────────────
app = FastAPI(title="电商智能客服系统", version="1.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回聊天界面"""
    return (static_dir / "index.html").read_text(encoding="utf-8")


# ── 全局图实例（共享 MemorySaver，支持多会话）─────────────────────────────────
_csr_graph = build_csr_graph()


# ── 非流式对话 ──────────────────────────────────────────────────────────────────
@app.post("/api/chat/{session_id}")
async def chat_non_stream(session_id: str, request: Request):
    """非流式对话接口"""
    body = await request.json()
    question = body.get("message", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="消息不能为空")

    config = {"configurable": {"thread_id": session_id}}

    result = _csr_graph.invoke(
        {
            "messages": [HumanMessage(content=question)],
            "intent": "",
            "iteration_count": 0,
            "next_agent": "",
        },
        config=config,
    )

    answer = result["messages"][-1].content

    # 检查是否有人工审核待处理
    state = _csr_graph.get_state(config)
    pending = None
    if state.tasks:
        interrupts = state.tasks[0].interrupts
        if interrupts:
            pending = interrupts[0].value

    return JSONResponse({
        "answer": answer,
        "pending_approval": pending,
    })


# ── SSE 流式对话 ────────────────────────────────────────────────────────────────
@app.get("/api/chat/{session_id}/stream")
async def chat_stream(session_id: str, message: str = ""):
    """SSE 流式对话接口"""
    if not message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    async def event_generator() -> AsyncGenerator[str, None]:
        config = {"configurable": {"thread_id": session_id}}

        try:
            async for event in _csr_graph.astream_events(
                {
                    "messages": [HumanMessage(content=message)],
                    "intent": "",
                    "iteration_count": 0,
                    "next_agent": "",
                },
                config=config,
                version="v2",
            ):
                kind = event.get("event", "")
                name = event.get("name", "")

                # 节点开始
                if kind == "on_chain_start" and name in (
                    "intent_classifier", "supervisor",
                    "order_agent", "product_agent", "aftersale_agent", "faq_agent",
                    "human_approval", "human_handoff",
                ):
                    node_labels = {
                        "intent_classifier": "🔍 正在分析您的问题...",
                        "supervisor": "🤔 正在决定如何处理...",
                        "order_agent": "📦 正在查询订单信息...",
                        "product_agent": "🛍️ 正在为您查找商品...",
                        "aftersale_agent": "🔧 正在处理售后请求...",
                        "faq_agent": "📋 正在搜索常见问题...",
                        "human_approval": "👤 等待人工审核...",
                        "human_handoff": "📞 正在转接人工客服...",
                    }
                    label = node_labels.get(name, f"⏳ {name}")
                    yield {
                        "event": "status",
                        "data": json.dumps({"type": "status", "node": name, "label": label}, ensure_ascii=False),
                    }
                    await asyncio.sleep(0.01)

                # LLM token 流式输出
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", None)
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield {
                            "event": "token",
                            "data": json.dumps({"type": "token", "content": chunk.content}, ensure_ascii=False),
                        }

            # 检查是否有人工审核待处理
            state = _csr_graph.get_state(config)
            if state.tasks:
                interrupts = state.tasks[0].interrupts
                if interrupts:
                    pending_data = interrupts[0].value
                    yield {
                        "event": "approval_required",
                        "data": json.dumps({"type": "approval_required", "data": pending_data}, ensure_ascii=False, default=str),
                    }

            yield {"event": "done", "data": json.dumps({"type": "done"})}

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


# ── 人工审核接口 ────────────────────────────────────────────────────────────────
@app.post("/api/human/approve/{session_id}")
async def approve_action(session_id: str):
    """批准待审核操作"""
    config = {"configurable": {"thread_id": session_id}}

    state = _csr_graph.get_state(config)
    if not state.tasks or not state.tasks[0].interrupts:
        raise HTTPException(status_code=400, detail="该会话没有待审核的操作")

    from langgraph.types import Command
    result = _csr_graph.invoke(Command(resume="approve"), config=config)

    return JSONResponse({
        "result": "approved",
        "answer": result["messages"][-1].content if result.get("messages") else "审核完成",
    })


@app.post("/api/human/reject/{session_id}")
async def reject_action(session_id: str):
    """拒绝待审核操作"""
    config = {"configurable": {"thread_id": session_id}}

    state = _csr_graph.get_state(config)
    if not state.tasks or not state.tasks[0].interrupts:
        raise HTTPException(status_code=400, detail="该会话没有待审核的操作")

    from langgraph.types import Command
    result = _csr_graph.invoke(Command(resume="reject"), config=config)

    return JSONResponse({
        "result": "rejected",
        "answer": result["messages"][-1].content if result.get("messages") else "审核完成",
    })


@app.get("/api/human/pending/{session_id}")
async def check_pending(session_id: str):
    """检查是否有待审核操作"""
    config = {"configurable": {"thread_id": session_id}}
    state = _csr_graph.get_state(config)

    pending = None
    if state.tasks:
        interrupts = state.tasks[0].interrupts
        if interrupts:
            pending = interrupts[0].value

    return JSONResponse({"has_pending": pending is not None, "data": pending})


# ── 健康检查 ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "电商智能客服系统"}


# ── 启动 ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import sys

    # 初始化 RAG 知识库（如果需要）
    try:
        build_product_knowledge_base()
    except Exception as e:
        print(f"[警告] RAG 知识库初始化失败（数据库可能尚未初始化）：{e}")
        print("请先运行 python seed_data.py 初始化数据")

    print("\n" + "=" * 60)
    print("  电商智能客服系统启动中...")
    print("   API 文档: http://localhost:8000/docs")
    print("   聊天界面: http://localhost:8000")
    print("=" * 60 + "\n")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="0.0.0.0", port=port)
