"""
deploy_graph.py — LangGraph Cloud 部署入口

LangGraph Cloud 自动提供 PostgresSaver 和 PostgreSQL 存储，
因此这里编译图时不传 checkpointer，由平台注入。

本地开发用 `langgraph dev` 会自动使用本地 PostgresSaver。
"""

from graph import build_csr_graph

# 云部署入口：平台自动注入 checkpointer
# 本地 dev 时 langgraph dev 会挂载本地 PostgresSaver
graph = build_csr_graph(checkpointer=None)
