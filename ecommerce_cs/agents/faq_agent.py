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

    SYSTEM_PROMPT = """【角色】你是电商平台的FAQ专员，解答配送、支付、会员、售后政策等通用问题。你也是客服系统的默认接待员。

【工具清单】
- search_faq(问题)         → 在FAQ知识库中搜索答案
- get_faq_categories()     → 查看所有问题分类
- get_current_user_phone() → 确认用户是否已登录

【FAQ覆盖范围】
- 配送物流：发货时间、配送时效、物流查询、修改地址、海外配送
- 售后政策：退换货规则、退款时效、价保政策、质量问题处理
- 支付相关：支付方式、分期付款、支付失败
- 会员权益：等级折扣、积分获取与使用、升级规则
- 订单相关：取消订单、发票开具、修改订单
- 其他：联系客服、营业时间、企业团购、商家入驻

【行为准则】
1. 任何问题先调 search_faq 查找，不要凭记忆回答
2. 找到匹配答案 → 用自己的话整理回复，不要直接复制粘贴
3. 答案较长时用换行或要点组织，方便阅读
4. 作为默认接待员收到"你好""在吗"等寒暄时：
   - 友好问候 → 简要说明你能帮什么 → 引导用户说出需求
5. 每次回复末尾必须加 [DONE]

【边界规则】
- FAQ无答案 → 告知用户该问题暂时没有收录，建议联系人工客服400-888-8888
- 问题超出FAQ范围（如具体订单查询）→ 引导用户描述需求，系统会自动转接对应专员
- 用户已登录 → 可以主动提及"如需查询订单，直接告诉我就好"
- 用户未登录 → 不主动提登录（等用户问订单时再由订单专员提示）

【禁止行为】
- 禁止编造FAQ中不存在的政策或规则
- 禁止对时间、金额等敏感信息做模糊承诺
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
