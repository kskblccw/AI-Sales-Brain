"""
config.py — 全局配置：LLM 工厂、Embeddings 工厂、路径常量

独立文件，不依赖 final/ 内任何模块。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent / ".env")

# ── DashScope 配置 ──────────────────────────────────────────────────────────
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "your_key_here")
DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# ── PostgreSQL 配置 ─────────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "ecommerce_cs")

from urllib.parse import quote_plus

DB_URL = f"postgresql+asyncpg://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DB_URL_SYNC = f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# LangGraph checkpointer 用 psycopg 3.x 连接字符串（不带 +asyncpg）
CHECKPOINT_URL = f"postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ── Chroma 配置 ─────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR = str(Path(__file__).parent / "chroma_db")

# ── LangGraph Checkpointer（同步 PostgresSaver，配合 asyncio.to_thread）─────
_checkpointer_pool = None
_checkpointer = None


def get_checkpointer_pool():
    """获取同步 ConnectionPool（单例）"""
    global _checkpointer_pool
    if _checkpointer_pool is None:
        from psycopg_pool import ConnectionPool
        _checkpointer_pool = ConnectionPool(
            CHECKPOINT_URL,
            min_size=2,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
    return _checkpointer_pool


def get_checkpointer():
    """获取 PostgresSaver（同步版）单例

    Windows 上 psycopg3 async 不兼容 ProactorEventLoop，
    因此使用同步版 PostgresSaver，在 FastAPI async 端点中
    通过 asyncio.to_thread() 调用 graph 的同步方法。
    """
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres import PostgresSaver
        _checkpointer = PostgresSaver(get_checkpointer_pool())
        _checkpointer.setup()
    return _checkpointer


# ── LLM 工厂 ────────────────────────────────────────────────────────────────
def make_llm(temperature: float = 0.3):
    """创建 ChatOpenAI 实例，对接 DashScope 兼容接口"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=temperature,
        base_url=DASHSCOPE_BASE_URL,
        api_key=DASHSCOPE_API_KEY,
    )


def make_embeddings():
    """创建 DashScope Embeddings 实例（用 httpx 直调 DashScope 原生 API）"""
    return DashScopeEmbeddings(model=EMBEDDING_MODEL, api_key=DASHSCOPE_API_KEY)


# ── 自定义 DashScope Embeddings ─────────────────────────────────────────────────
from typing import List
from langchain_core.embeddings import Embeddings


class DashScopeEmbeddings(Embeddings):
    """DashScope Text Embedding 封装，用 httpx 直接调用 DashScope 原生 API。

    OpenAI 兼容模式的 /v1/embeddings 在新版 openai 客户端下与 DashScope
    存在输入格式不兼容问题，因此直调 DashScope 原生 endpoint。
    """

    def __init__(self, model: str = "text-embedding-v3", api_key: str = ""):
        self.model = model
        self.api_key = api_key
        self._url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=30)
        return self._client

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        # 批量请求：一次 HTTP 调用处理全部文本
        resp = self.client.post(
            self._url,
            json={"model": self.model, "input": {"texts": texts}},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return [e["embedding"] for e in data["output"]["embeddings"]]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
