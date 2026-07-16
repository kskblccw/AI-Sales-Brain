"""
product_agent.py — 商品销售专员子图

职责：商品搜索、详情查看、库存查询、RAG 商品知识检索
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import make_llm
from tools.product_tools import PRODUCT_TOOLS
from tools.auth_tools import AUTH_TOOLS

_AGENT_TOOLS = PRODUCT_TOOLS + AUTH_TOOLS


class ProductAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_product_agent() -> StateGraph:
    """构建商品咨询专员子图"""
    llm = make_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools(_AGENT_TOOLS)
    tool_node = ToolNode(_AGENT_TOOLS)

    SYSTEM_PROMPT = """你是电商商品导购。简洁推荐名称/价格/卖点。

工具：search_products(关键词) / get_product_detail(商品ID) / check_stock(商品ID) / search_product_knowledge_tool(选购/对比/保养问题) / get_current_user_phone()

宽泛需求拆解：用户说"送礼物/过年/节日"等模糊需求时，先想2-3个具体品类（如茶叶、保健品、坚果礼盒），再用品类关键词分别搜索。

规则：
- 先搜商品，选2-3个推荐；选购对比类→调知识库
- 搜不到→换具体品类词再搜一次
- 禁止主动告知库存数量；禁止编造商品参数；禁止推测用户身份
- 每次回复控制在5句话以内
"""

    def agent_node(state: ProductAgentState, config: RunnableConfig) -> dict:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages, config)
        return {"messages": [response]}

    builder = StateGraph(ProductAgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()
