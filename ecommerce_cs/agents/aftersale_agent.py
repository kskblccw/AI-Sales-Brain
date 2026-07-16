"""
aftersale_agent.py — 售后专员子图

职责：退换货政策咨询、售后申请创建、工单状态查询
流程：先查订单列表 → 用户选单 → 确认详情 → 提交工单 → 人工审核
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import make_llm
from tools.aftersale_tools import AFTERSALE_TOOLS
from tools.auth_tools import AUTH_TOOLS
from tools.order_tools import list_my_orders, query_order

_AGENT_TOOLS = AFTERSALE_TOOLS + AUTH_TOOLS + [list_my_orders, query_order]


class AfterSaleAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_aftersale_agent() -> StateGraph:
    """构建售后专员子图"""
    llm = make_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(_AGENT_TOOLS)
    tool_node = ToolNode(_AGENT_TOOLS)

    SYSTEM_PROMPT = """你是电商售后专员。简洁专业，不要每句都提用户画像细节。

工具：list_my_orders() / query_order(订单号) / check_return_policy() / create_return_request(订单号,原因,类型) / query_return_status(工单号) / get_current_user_phone()

流程：
1. 用户要退货/换货/退款→先调 list_my_orders 列出订单
2. 用户确认订单后→调 create_return_request 提交
3. 只咨询政策→调 check_return_policy；投诉→致歉+转人工
禁止：不查订单直接要订单号、未调工具前承诺退款金额、推测用户身份/爱好
"""

    def agent_node(state: AfterSaleAgentState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages, config)
        return {"messages": [response]}

    builder = StateGraph(AfterSaleAgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()
