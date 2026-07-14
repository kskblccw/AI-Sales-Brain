"""
order_agent.py — 订单查询专员子图

职责：订单查询、物流跟踪、用户订单列表
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import make_llm
from tools.order_tools import ORDER_TOOLS


class OrderAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_order_agent() -> StateGraph:
    """构建订单专员子图"""
    llm = make_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(ORDER_TOOLS)
    tool_node = ToolNode(ORDER_TOOLS)

    SYSTEM_PROMPT = """你是一个电商客服的订单查询专员。你的职责是帮助用户查询订单相关信息。

你可以：
- 查询指定订单号的详情（query_order）
- 查询订单物流状态（track_shipment）
- 查看用户所有订单列表（list_my_orders）

工作规范：
1. 先理解用户需求，选择合适的工具，只调用一次工具即可
2. 需要手机号时，礼貌询问用户，回复末尾加 [DONE]
3. 查不到订单时，告知用户并建议核对订单号，回复末尾加 [DONE]
4. 查询成功时整理结果给用户，回复末尾加 [DONE]
5. 如果用户需要退换货，引导联系售后专员，回复末尾加 [DONE]
"""

    def agent_node(state: OrderAgentState) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    builder = StateGraph(OrderAgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()
