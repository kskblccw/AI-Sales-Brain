"""
kb_server.py — 知识库管理系统（端口 8001，与主服务隔离）

启动：python kb_server.py
API:  http://localhost:8001/docs
UI:   http://localhost:8001
"""

import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import make_embeddings, CHROMA_PERSIST_DIR
from rag import build_product_knowledge_base, search_product_knowledge

# ── FastAPI ──────────────────────────────────────────────────────────────────
app = FastAPI(title="知识库管理系统", version="1.0")

static_dir = Path(__file__).parent / "kb_static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (static_dir / "index.html").read_text(encoding="utf-8")


# ── Chroma 连接（通过 langchain_community 包装器，避免 chromadb 直接 import 的 otel 冲突）──
from langchain_community.vectorstores import Chroma as LCChroma

_vectorstore: LCChroma = None


def _get_vectorstore() -> LCChroma:
    """获取 Chroma vectorstore（懒加载）"""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = LCChroma(
            persist_directory=CHROMA_PERSIST_DIR,
            embedding_function=make_embeddings(),
        )
    return _vectorstore


def _get_collection():
    """通过 langchain 获取底层 chroma collection（用于 CRUD）"""
    vs = _get_vectorstore()
    return vs._collection


# ── Pydantic 模型 ───────────────────────────────────────────────────────────
class DocCreate(BaseModel):
    content: str = Field(..., description="文档内容", min_length=1)
    category: str = Field(default="通用", description="分类标签")
    product_name: str = Field(default="", description="关联商品名")
    doc_type: str = Field(default="custom", description="文档类型")


class DocUpdate(BaseModel):
    content: Optional[str] = Field(None, description="文档内容")
    category: Optional[str] = Field(None, description="分类标签")
    product_name: Optional[str] = Field(None, description="关联商品名")
    doc_type: Optional[str] = Field(None, description="文档类型")


class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


# ── CRUD API ────────────────────────────────────────────────────────────────
@app.get("/api/documents")
async def list_documents(
    category: str = Query(default="", description="按分类过滤"),
    doc_type: str = Query(default="", description="按类型过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """分页列出所有知识库文档"""
    coll = _get_collection()
    result = coll.get(include=["metadatas", "documents"])

    docs = []
    for i in range(len(result["ids"])):
        meta = result["metadatas"][i] or {}
        # 应用过滤
        if category and meta.get("category", "") != category:
            continue
        if doc_type and meta.get("doc_type", "") != doc_type:
            continue
        docs.append({
            "id": result["ids"][i],
            "content": (result["documents"][i] or "")[:200] + (
                "..." if len(result["documents"][i] or "") > 200 else ""
            ),
            "content_full": result["documents"][i] or "",
            "metadata": meta,
        })

    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size

    return JSONResponse({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": docs[start:end],
    })


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    """获取单个文档详情"""
    coll = _get_collection()
    result = coll.get(ids=[doc_id], include=["metadatas", "documents"])

    if not result["ids"]:
        raise HTTPException(status_code=404, detail="文档不存在")

    return JSONResponse({
        "id": result["ids"][0],
        "content": result["documents"][0] or "",
        "metadata": result["metadatas"][0] or {},
    })


@app.post("/api/documents")
async def create_document(doc: DocCreate):
    """新增知识库文档（长文档自动切分，每个 chunk 独立嵌入）"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=80,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )

    # 切分长文档
    if len(doc.content) > 600:
        chunks = splitter.split_text(doc.content)
    else:
        chunks = [doc.content]

    # 批量生成嵌入
    emb = make_embeddings()
    vectors = emb.embed_documents(chunks)

    # 每个 chunk 作为独立条目（共享元数据，ID 加后缀）
    doc_id_prefix = str(uuid.uuid4())
    coll = _get_collection()
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        coll.add(
            ids=[f"{doc_id_prefix}_{i}"],
            documents=[chunk],
            metadatas=[{
                "category": doc.category,
                "product_name": doc.product_name,
                "doc_type": doc.doc_type,
                "parent_id": doc_id_prefix,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }],
            embeddings=[vec],
        )

    return JSONResponse({
        "id": doc_id_prefix,
        "chunks": len(chunks),
        "message": f"文档已添加（{len(chunks)} 个片段）",
    }, status_code=201)


@app.put("/api/documents/{doc_id}")
async def update_document(doc_id: str, doc: DocUpdate):
    """更新文档（内容和/或元数据）"""
    coll = _get_collection()
    existing = coll.get(ids=[doc_id])

    if not existing["ids"]:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 合并更新
    new_content = doc.content if doc.content is not None else existing["documents"][0]
    new_meta = {**existing["metadatas"][0]}
    if doc.category is not None:
        new_meta["category"] = doc.category
    if doc.product_name is not None:
        new_meta["product_name"] = doc.product_name
    if doc.doc_type is not None:
        new_meta["doc_type"] = doc.doc_type

    # 如果内容变了，重新生成 embedding
    emb = make_embeddings()
    new_vector = emb.embed_query(new_content[:1000])

    coll.update(
        ids=[doc_id],
        documents=[new_content],
        metadatas=[new_meta],
        embeddings=[new_vector],
    )

    return JSONResponse({"id": doc_id, "message": "文档已更新"})


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档"""
    coll = _get_collection()
    coll.delete(ids=[doc_id])
    return JSONResponse({"id": doc_id, "message": "文档已删除"})


@app.delete("/api/documents")
async def batch_delete(ids: str = Query(..., description="逗号分隔的ID列表")):
    """批量删除文档"""
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    coll = _get_collection()
    coll.delete(ids=id_list)
    return JSONResponse({"deleted": len(id_list), "message": f"已删除 {len(id_list)} 个文档"})


# ── 搜索 ────────────────────────────────────────────────────────────────────
@app.post("/api/search")
async def search_docs(q: SearchQuery):
    """语义搜索知识库"""
    result = search_product_knowledge(q.query, k=q.top_k)
    return JSONResponse({"query": q.query, "results": result})


@app.get("/api/search")
async def search_docs_get(q: str = Query(..., min_length=1), top_k: int = 5):
    """GET 方式搜索"""
    result = search_product_knowledge(q, k=top_k)
    return JSONResponse({"query": q, "results": result})


# ── 分类和类型统计 ──────────────────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    """获取知识库统计信息"""
    coll = _get_collection()
    result = coll.get(include=["metadatas"])

    categories = {}
    doc_types = {}
    for meta in (result["metadatas"] or []):
        cat = (meta or {}).get("category", "未知")
        dt = (meta or {}).get("doc_type", "未知")
        categories[cat] = categories.get(cat, 0) + 1
        doc_types[dt] = doc_types.get(dt, 0) + 1

    return JSONResponse({
        "total": len(result["ids"]),
        "categories": categories,
        "doc_types": doc_types,
    })


# ── 重建索引 ────────────────────────────────────────────────────────────────
@app.post("/api/rebuild")
async def rebuild_index():
    """从数据库重新构建整个知识库（耗时操作）"""
    try:
        build_product_knowledge_base(force=True)
        # 刷新 vectorstore 缓存引用
        global _vectorstore
        _vectorstore = None
        return JSONResponse({"message": "知识库重建完成"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重建失败: {e}")


# ── 启动 ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import sys

    print("\n" + "=" * 60)
    print("  知识库管理系统")
    print("  API:  http://localhost:8001/docs")
    print("  UI:   http://localhost:8001")
    print("=" * 60 + "\n")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    uvicorn.run(app, host="0.0.0.0", port=port)
