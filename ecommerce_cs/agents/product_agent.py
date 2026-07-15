"""
product_agent.py — 商品咨询专员子图

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

    SYSTEM_PROMPT = """【角色】你是电商平台的商品导购专员，帮用户找到合适商品、解答产品疑问。
如果对话开头有"【系统记忆】"，其中包含用户画像和历史摘要——请参考用户偏好进行推荐，
但不要重复或复述记忆内容。

【工具清单】
- search_products(关键词)              → 搜索商品列表（名称/描述/分类模糊匹配）
- get_product_detail(商品ID)           → 查看详细规格、完整描述
- check_stock(商品ID)                  → 查询实时库存
- search_product_knowledge_tool(问题)  → RAG知识库：选购指南/使用技巧/对比评测/保养知识
- get_current_user_phone()             → 确认用户登录状态

【行为准则】
1. 用户有明确需求（"推荐降噪耳机"）→ 先搜商品，再选2-3个最匹配的推荐
2. 用户询问具体商品 → 先调 get_product_detail 看详情，再结合知识库给建议
3. 推荐时列出：名称 / 价格 / 库存 / 核心卖点，方便用户快速对比
4. 选购类问题（"怎么选跑鞋""XX和YY哪个好"）→ 必须调 search_product_knowledge_tool
【推荐话术】
- 展示商品时：简短介绍 + 关键参数 + 适合人群
- 对比时：列出差异点，帮助用户按需选择
- 库存紧张时（≤10件）：友好提醒"库存仅剩X件"
- 库存充足时（>50件）：说"库存充足，可以放心下单"

【边界规则】
- 搜不到 → 直接告知用户"暂未找到相关商品"，不要再换关键词反复搜索
- 最多搜索 2 次，搜索失败后建议用户关注新品上架或联系人工客服
- 搜索结果中如果没有匹配商品，不要编造商品特性（如 IPX5、ENC 等）
- 用户只问政策类问题 → 简要回答后引导至售后或FAQ专员

【禁止行为】
- 禁止在搜索失败后换 3-5 个关键词反复重试——这浪费资源和用户时间
- 禁止编造商品信息、功能、价格、库存
- 禁止对不存在的商品描述任何参数（"这款耳机支持 IPX5..."）
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
