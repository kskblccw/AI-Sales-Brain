"""
order_agent.py — 订单处理专员子图

职责：订单查询、物流跟踪、用户订单列表
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import make_llm
from tools.order_tools import ORDER_TOOLS
from tools.auth_tools import AUTH_TOOLS

_AGENT_TOOLS = ORDER_TOOLS + AUTH_TOOLS


class OrderAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_order_agent() -> StateGraph:
    """构建订单专员子图"""
    llm = make_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(_AGENT_TOOLS)
    tool_node = ToolNode(_AGENT_TOOLS)

    SYSTEM_PROMPT = """你是电商订单客服。简洁专业，不要每句都提用户画像。

工具：query_order(订单号) / track_shipment(订单号) / list_my_orders() / modify_shipping_address(订单号,新地址) / get_current_user_phone()

规则：
- 用户给订单号→直接查；说"我的订单"→调 list_my_orders
- 结果清晰列出：订单号/状态/金额/商品/物流
- 改地址→调 modify_shipping_address，仅待发货订单可改
- 未登录→引导去右上角输手机号；查不到→请核对
- 禁止编造数据、禁止推测用户身份/爱好/生活场景
"""

    def agent_node(state: OrderAgentState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages, config)
        return {"messages": [response]}

    builder = StateGraph(OrderAgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()
