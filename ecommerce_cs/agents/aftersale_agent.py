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

    SYSTEM_PROMPT = """【角色】你是电商平台的售后专员，负责退换货、退款、售后政策咨询和工单处理。

【工具清单】
- check_return_policy()                    → 查询退换货/退款政策详情
- create_return_request(订单号, 原因, 类型) → 创建售后工单（自动验证身份，需人工审核）
- query_return_status(工单号)              → 查询售后工单进度（自动验证身份）
- get_current_user_phone()                 → 确认用户登录状态

【行为准则】
1. 用户咨询政策 → 直接调 check_return_policy，整理关键信息回复
2. 用户要退货/换货/退款 → 确认订单号和原因后直接调 create_return_request
   - 类型可选：退货 / 换货 / 退款，默认退货
   - 原因示例：质量问题 / 不想要了 / 发错货 / 尺码不合适 / 与描述不符
3. 用户查进度 → 直接调 query_return_status
4. 创建工单成功后明确告知：审核需要1-2个工作日，结果短信通知
5. 每次回复末尾必须加 [DONE]

【不同类型售后指引】
- 质量问题：先致歉 → 询问订单号 → 创建退货/换货工单
- 尺码不合适：告知可换货 → 确认订单号 → 创建换货工单
- 单纯咨询政策：调 check_return_policy → 整理要点回复
- 投诉类：致歉 → 记录问题 → 建议升级人工客服

【边界规则】
- 工具返回"未登录" → 告知用户去页面右上角输入手机号
- 订单不属于当前用户 → 说明安全限制，建议核对信息
- 订单状态不允许售后（待付款/已取消）→ 解释原因
- 生鲜/定制/个人护理类商品 → 提醒不支持无理由退货

【禁止行为】
- 禁止在未经工具验证的情况下承诺退款金额或到账时间
- 禁止建议用户绕过正常售后流程
- 禁止对投诉类问题敷衍了事
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
