"""
faq_agent.py — FAQ 常见问题专员子图

职责：FAQ 知识库检索，回答配送/支付/会员/政策等常见问题
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import make_llm
from tools.faq_tools import FAQ_TOOLS
from tools.auth_tools import AUTH_TOOLS

_AGENT_TOOLS = FAQ_TOOLS + AUTH_TOOLS


class FAQAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_faq_agent() -> StateGraph:
    """构建 FAQ 专员子图"""
    llm = make_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(_AGENT_TOOLS)
    tool_node = ToolNode(_AGENT_TOOLS)

    SYSTEM_PROMPT = """你是电商FAQ专员兼默认接待员，解答配送/支付/会员/售后政策等通用问题。

工具：search_faq(问题) / get_faq_categories() / get_current_user_phone()

规则：
- 任何问题先搜FAQ，用自己的话整理回复，禁止编造政策
- 寒暄→友好问候+引导用户说出需求
- FAQ无答案→告知未收录，建议转人工；超范围→引导描述需求，系统自动转接
"""

    def agent_node(state: FAQAgentState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages, config)
        return {"messages": [response]}

    builder = StateGraph(FAQAgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()
