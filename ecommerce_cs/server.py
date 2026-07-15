"""
server.py — FastAPI 后端 + SSE 流式端点

启动方式：
    python server.py
    uvicorn server:app --reload --port 8000
"""

import json
import asyncio
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage

from graph import build_csr_graph
from rag import build_product_knowledge_base

# ── FastAPI 应用 ────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _csr_graph
    from config import get_checkpointer
    _csr_graph = build_csr_graph(checkpointer=get_checkpointer())
    print("[Startup] PostgresSaver ready")
    yield

app = FastAPI(title="电商智能客服系统", version="1.0", lifespan=lifespan)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回聊天界面"""
    return (static_dir / "index.html").read_text(encoding="utf-8")


# ── 全局图实例（启动时用同步 PostgresSaver 初始化）─────────────────────────
_csr_graph = None
# session_id → phone（服务端内存，不写 State）
_session_phones: dict[str, str] = {}
# phone → {session_ids}（反向索引，用于按用户过滤会话列表）
_phone_sessions: dict[str, set[str]] = {}


def _bind_phone(session_id: str, phone: str):
    """绑定 session 到 phone，建立双向映射"""
    _session_phones[session_id] = phone
    _phone_sessions.setdefault(phone, set()).add(session_id)


def _get_config(session_id: str, phone_hint: str = "") -> dict:
    phone = _session_phones.get(session_id, "")
    # 兜底：前端把手机号存在 sessionStorage，请求时带上
    if not phone and phone_hint and len(phone_hint) == 11 and phone_hint.isdigit():
        _bind_phone(session_id, phone_hint)
        phone = phone_hint
    return {"configurable": {"thread_id": session_id, "user_phone": phone}}


def _make_initial_state(message: str, session_id: str) -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "intent": "", "iteration_count": 0, "next_agent": "",
        "user_phone": _session_phones.get(session_id, ""),
    }




# ── 用户登录 ────────────────────────────────────────────────────────────────────
@app.post("/api/login/{session_id}")
async def login(session_id: str, request: Request):
    """前端提交手机号，后端验证并绑定到 session"""
    body = await request.json()
    phone = body.get("phone", "").strip()
    if not phone or len(phone) != 11 or not phone.isdigit():
        raise HTTPException(status_code=400, detail="请输入有效的11位手机号")

    from database import find_user_by_phone
    user = find_user_by_phone(phone)
    if not user:
        raise HTTPException(status_code=404, detail=f"未找到手机号 {phone} 对应的用户")

    _bind_phone(session_id, phone)
    return JSONResponse({
        "logged_in": True,
        "phone": phone,
        "user_name": user.name,
    })


@app.get("/api/login/{session_id}")
async def get_login_status(session_id: str):
    """查询当前 session 的登录状态"""
    phone = _session_phones.get(session_id, "")
    if not phone:
        return JSONResponse({"logged_in": False, "phone": "", "user_name": ""})
    from database import find_user_by_phone
    user = find_user_by_phone(phone)
    return JSONResponse({
        "logged_in": True,
        "phone": phone,
        "user_name": user.name if user else "",
    })


# ── 非流式对话 ──────────────────────────────────────────────────────────────────
@app.post("/api/chat/{session_id}")
async def chat_non_stream(session_id: str, request: Request):
    """非流式对话接口"""
    body = await request.json()
    question = body.get("message", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="消息不能为空")

    config = _get_config(session_id)
    initial_state = _make_initial_state(question, session_id)

    def _invoke():
        return _csr_graph.invoke(initial_state, config=config)

    result = await asyncio.to_thread(_invoke)
    answer = result["messages"][-1].content

    state = _csr_graph.get_state(config)
    pending = None
    if state and state.tasks:
        interrupts = state.tasks[0].interrupts
        if interrupts:
            pending = interrupts[0].value

    return JSONResponse({
        "answer": answer,
        "pending_approval": pending,
    })


# ── SSE 流式对话 ────────────────────────────────────────────────────────────────
@app.get("/api/chat/{session_id}/stream")
async def chat_stream(session_id: str, message: str = "", phone: str = ""):
    """SSE 流式对话接口"""
    if not message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    async def event_generator():
        import queue, threading

        config = _get_config(session_id, phone_hint=phone)
        initial_state = _make_initial_state(message, session_id)
        # 兜底：如果 phone 参数带了但 _session_phones 是新的，更新 initial_state
        if phone and not initial_state.get("user_phone"):
            initial_state["user_phone"] = phone

        node_names = {
            "intent_classifier": "正在分析您的问题...",
            "supervisor": "正在决定如何处理...",
            "order_agent": "正在查询订单信息...",
            "product_agent": "正在为您查找商品...",
            "aftersale_agent": "正在处理售后请求...",
            "faq_agent": "正在搜索常见问题...",
            "human_approval": "等待人工审核...",
            "human_handoff": "正在转接人工客服...",
        }

        q = queue.Queue()
        error_holder = []

        def run_graph():
            try:
                for step in _csr_graph.stream(initial_state, config=config, stream_mode="updates"):
                    q.put(("step", step))
                # 完成后检查人工审核
                state = _csr_graph.get_state(config)
                pending = None
                if state and state.tasks:
                    interrupts = state.tasks[0].interrupts
                    if interrupts:
                        pending = interrupts[0].value
                q.put(("done", pending))
            except Exception as e:
                error_holder.append(e)
                q.put(("error", str(e)))

        thread = threading.Thread(target=run_graph, daemon=True)
        thread.start()

        try:
            while True:
                item = await asyncio.to_thread(q.get)
                kind, data = item

                if kind == "step":
                    for node_name, node_output in data.items():
                        label = node_names.get(node_name, node_name)
                        yield {"event": "status", "data": json.dumps(
                            {"type": "status", "node": node_name, "label": label}, ensure_ascii=False)}
                        if "messages" in node_output:
                            last_msg = node_output["messages"][-1]
                            if hasattr(last_msg, "content") and last_msg.content:
                                yield {"event": "token", "data": json.dumps(
                                    {"type": "token", "content": str(last_msg.content)}, ensure_ascii=False)}

                elif kind == "done":
                    if data:  # pending approval
                        yield {"event": "approval_required", "data": json.dumps(
                            {"type": "approval_required", "data": data}, ensure_ascii=False, default=str)}
                    yield {"event": "done", "data": json.dumps({"type": "done"})}
                    break

                elif kind == "error":
                    yield {"event": "error", "data": json.dumps(
                        {"type": "error", "message": data[:200]}, ensure_ascii=False)}
                    break

        except Exception as e:
            import traceback
            print(f"\n{'='*40}\n[STREAM ERROR] {traceback.format_exc()}\n{'='*40}", flush=True)
            yield {"event": "error", "data": json.dumps(
                {"type": "error", "message": str(e)[:200]}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


# ── 人工审核接口 ────────────────────────────────────────────────────────────────
@app.post("/api/human/approve/{session_id}")
async def approve_action(session_id: str):
    """批准待审核操作"""
    config = _get_config(session_id)

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
    config = _get_config(session_id)

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
    config = _get_config(session_id)
    state = _csr_graph.get_state(config)

    pending = None
    if state and state.tasks:
        interrupts = state.tasks[0].interrupts
        if interrupts:
            pending = interrupts[0].value

    return JSONResponse({"has_pending": pending is not None, "data": pending})


# ── 会话管理 ────────────────────────────────────────────────────────────────────
@app.delete("/api/chat/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话的所有 checkpoint 数据"""
    from config import get_checkpointer_pool
    pool = get_checkpointer_pool()
    with pool.connection() as conn:
        conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (session_id,))
        conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (session_id,))
        conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", (session_id,))
    return JSONResponse({"deleted": session_id})
@app.get("/api/sessions")
async def list_sessions(phone: str = ""):
    """列出当前用户的会话 ID（按 phone 过滤，未登录返回空）"""
    if not phone:
        return JSONResponse([])

    # 获取该 phone 关联的所有 session_id
    user_sessions = _phone_sessions.get(phone, set())
    if not user_sessions:
        return JSONResponse([])

    # 只返回在 checkpoints 表中确实存在的 session
    from config import get_checkpointer_pool
    pool = get_checkpointer_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id = ANY(%s) ORDER BY thread_id",
            (list(user_sessions),)
        ).fetchall()
    return JSONResponse([r[0] for r in rows])


@app.get("/api/chat/{session_id}/history")
async def get_history(session_id: str):
    """获取指定会话的聊天记录"""
    config = _get_config(session_id)
    state = _csr_graph.get_state(config)

    messages = []
    if state.values:
        for msg in state.values.get("messages", []):
            msg_data = {"role": "unknown", "content": ""}
            msg_type = getattr(msg, "type", "")
            if msg_type == "human":
                msg_data["role"] = "user"
            elif msg_type == "ai":
                msg_data["role"] = "assistant"
            elif msg_type == "system":
                msg_data["role"] = "system"
            msg_data["content"] = str(getattr(msg, "content", ""))
            messages.append(msg_data)

    return JSONResponse({"session_id": session_id, "messages": messages})


@app.get("/api/debug/checkpoints")
async def debug_checkpoints():
    """调试端点：直接查看 checkpoints 表中的所有 thread_id"""
    from config import get_checkpointer_pool
    pool = get_checkpointer_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT thread_id, checkpoint_id, "
            "length(checkpoint::text) as size "
            "FROM checkpoints ORDER BY thread_id, checkpoint_id"
        ).fetchall()
    result = {}
    for r in rows:
        tid = r["thread_id"]
        if tid not in result:
            result[tid] = []
        result[tid].append({"checkpoint_id": r["checkpoint_id"], "size": r["size"]})
    return JSONResponse({"threads": len(result), "detail": result})


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
