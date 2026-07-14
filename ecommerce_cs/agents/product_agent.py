"""
product_agent.py — 商品咨询专员子图

职责：商品搜索、详情查看、库存查询、RAG 商品知识检索
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import make_llm
from tools.product_tools import PRODUCT_TOOLS


class ProductAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_product_agent() -> StateGraph:
    """构建商品咨询专员子图"""
    llm = make_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(PRODUCT_TOOLS)
    tool_node = ToolNode(PRODUCT_TOOLS)

    SYSTEM_PROMPT = """你是一个电商客服的商品咨询专员。你的职责是帮用户了解商品信息和选购。

你可以：
- 搜索商品（search_products）
- 查看商品详情和规格（get_product_detail）
- 查询商品库存（check_stock）
- 搜索商品知识库——含使用指南、选购建议、保养知识等（search_product_knowledge_tool）

工作规范：
1. 先调用工具搜索/查询，只调用一次工具即可
2. 搜不到商品时告知用户并建议更换关键词，回复末尾加 [DONE]
3. 查到时整理结果（含价格/库存），回复末尾加 [DONE]
4. 对深入问题务必调用 search_product_knowledge_tool，回复末尾加 [DONE]
"""

    def agent_node(state: ProductAgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    builder = StateGraph(ProductAgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()
