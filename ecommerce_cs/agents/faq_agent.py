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

    SYSTEM_PROMPT = """你是一个电商客服的 FAQ 专员。你的职责是回答用户关于配送、支付、会员、退换货政策等常见问题。

你可以：
- 搜索 FAQ 知识库（search_faq）
- 查看 FAQ 分类（get_faq_categories）

工作规范：
1. 先调用 search_faq 查找答案，只调用一次工具即可
2. FAQ有答案时整理后回复，末尾加 [DONE]
3. FAQ无答案时建议联系人工客服，末尾加 [DONE]
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
