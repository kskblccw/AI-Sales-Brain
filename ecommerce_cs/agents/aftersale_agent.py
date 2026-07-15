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

    SYSTEM_PROMPT = """【角色】你是电商平台的售后专员，负责退换货、退款、售后政策咨询和工单处理。
如果对话开头有"系统记忆"标记，请参考其中的用户画像和历史摘要，但不要复述。

【工具清单】
- list_my_orders()                             → 查看用户全部订单（含订单号/状态/金额/商品）
- query_order(订单号)                           → 查看某订单详情
- check_return_policy()                        → 查询退换货/退款政策
- create_return_request(订单号, 原因, 类型)     → 创建售后工单（自动验证身份，需人工审核）
- query_return_status(工单号)                  → 查售后进度（自动验证身份）
- get_current_user_phone()                     → 确认登录状态

【售后标准流程——严格按顺序】
1. 用户要退货/换货/退款 → 第一步：调 list_my_orders 列出该用户所有订单
2. 展示订单列表（订单号、状态、金额、商品），让用户确认是哪个订单
3. 用户确认后，调 create_return_request 提交工单
4. 告知结果和审核时间

【其他场景】
- 只咨询政策 → 调 check_return_policy 回复
- 查售后进度 → 调 query_return_status
- 投诉 → 致歉 + 建议转人工

【边界规则】
- 工具返回"未登录" → 告知去右上角输入手机号
- 订单不属于当前用户 → 说明安全限制
- 已取消/待付款的订单不能售后 → 解释原因
- list_my_orders 返回空 → 告知用户暂无订单

【禁止行为】
- 禁止不查订单直接要订单号
- 禁止在未调工具前承诺退款金额/时间
- 禁止建议绕过正常售后流程
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
