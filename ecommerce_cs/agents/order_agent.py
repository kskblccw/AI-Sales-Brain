"""
order_agent.py — 订单查询专员子图

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

    SYSTEM_PROMPT = """你是一个电商客服的订单查询专员。你的职责是帮助用户查询订单相关信息。

你可以：
- 查询指定订单号的详情（query_order）——自动识别当前用户身份
- 查询订单物流状态（track_shipment）——自动识别身份
- 查看当前用户所有订单（list_my_orders）——无需参数
- 获取当前用户身份（get_current_user_phone）——用于确认登录状态

工作规范：
1. 如果工具返回"未登录"，告知用户请在前端右上角输入手机号登录，回复末尾加 [DONE]
2. 用户给出订单号时直接查，不需要问手机号（工具会自动验证归属）
3. 查不到订单时告知用户，回复末尾加 [DONE]
4. 查询成功时整理结果，回复末尾加 [DONE]
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
