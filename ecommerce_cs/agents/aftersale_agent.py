"""
aftersale_agent.py — 售后专员子图

职责：退换货政策咨询、售后申请创建、工单状态查询

注意：create_return_request 工具执行前需要人工确认（在父图中通过 interrupt_before 实现）
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

_AGENT_TOOLS = AFTERSALE_TOOLS + AUTH_TOOLS


class AfterSaleAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_aftersale_agent() -> StateGraph:
    """构建售后专员子图"""
    llm = make_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(_AGENT_TOOLS)
    tool_node = ToolNode(_AGENT_TOOLS)

    SYSTEM_PROMPT = """你是一个电商客服的售后专员。你的职责是帮助用户处理退换货和售后问题。

你可以：
- 查询退换货政策（check_return_policy）
- 创建退换货申请（create_return_request）——自动验证身份，需人工审核
- 查询售后工单状态（query_return_status）——自动验证身份
- 获取当前用户身份（get_current_user_phone）

工作规范：
1. 如果工具返回"未登录"，告知用户请在前端右上角输入手机号登录，回复末尾加 [DONE]
2. 创建售后申请前确认订单号和原因即可，不需要问手机号（工具自动验证）
3. 告知用户申请需人工审核，回复末尾加 [DONE]
4. 仅咨询政策时直接回答，回复末尾加 [DONE]
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
