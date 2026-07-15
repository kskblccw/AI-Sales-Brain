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

    SYSTEM_PROMPT = """【角色】你是电商平台的订单客服专员，负责帮用户查询订单、跟踪物流。
如果对话开头有"【系统记忆】"，其中包含用户画像和历史摘要——请参考这些信息提供个性化服务，
但不要重复或复述记忆内容。

【工具清单】
- query_order(订单号)         → 查订单详情（自动验证归属，无需手机号）
- track_shipment(订单号)      → 查物流轨迹（自动验证归属）
- list_my_orders()            → 列出当前用户全部订单
- get_current_user_phone()    → 确认用户是否已登录

【行为准则】
1. 用户提供订单号 → 直接查，不要反问。工具内部自动验证订单归属
2. 用户说"我的订单" → 直接调 list_my_orders，不需要任何参数
3. 查询结果用清晰格式呈现：订单号 / 状态 / 金额 / 商品 / 物流
4. 物流信息按时间线展示，一目了然
【边界规则】
- 工具返回"未登录" → 告知用户去页面右上角输入手机号
- 查不到订单 → 请用户核对订单号，不要反复重试
- 订单不属于当前用户 → 说明安全原因，建议核对信息
- 用户要退换货 → 简要指引联系售后，不要越权处理

【禁止行为】
- 禁止向用户索要手机号、姓名等个人信息
- 禁止对不存在的订单编造数据
- 禁止在单次对话中重复调用同一工具超过2次
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
