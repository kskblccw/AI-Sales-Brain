"""
graph.py — Supervisor 主图：意图识别 → 调度路由 → 子Agent执行 → 汇总响应

架构：
  START → intent_classifier → supervisor → order/product/aftersale/faq → supervisor → END
                                                                          ↓
                                                                   human_handoff
"""

from typing import TypedDict, Annotated, Literal
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from langchain_core.runnables import RunnableConfig
from config import make_llm
from agents.order_agent import build_order_agent
from agents.product_agent import build_product_agent
from agents.aftersale_agent import build_aftersale_agent
from agents.faq_agent import build_faq_agent


# ── State 定义 ──────────────────────────────────────────────────────────────────
class CSRState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str            # 用户意图：order/product/aftersale/faq/human
    iteration_count: int   # 子Agent调度轮数
    next_agent: str        # supervisor 决定的下一个Agent
    user_phone: str        # 当前用户手机号（元数据，不注入 LLM 上下文）


# 可用的子Agent列表
AGENT_NAMES = ["order", "product", "aftersale", "faq"]

# ── 预编译子图 ──────────────────────────────────────────────────────────────────
_subgraphs = {
    "order": build_order_agent(),
    "product": build_product_agent(),
    "aftersale": build_aftersale_agent(),
    "faq": build_faq_agent(),
}

llm = make_llm(temperature=0.3)

# ── 安全打印（Windows console GBK 兼容）───────────────────────────────────────
def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [a.encode("ascii", "replace").decode("ascii") if isinstance(a, str) else a for a in args]
        print(*safe_args, **kwargs)


# ── 正则规则预路由 ──────────────────────────────────────────────────────────────
# 80% 高频问题直接命中，跳过 LLM 意图分类，省 token + 秒级响应
import re

ROUTE_RULES = [
    # order: 订单、物流、快递
    ("order", re.compile(
        r"订单|物流|快递|发货|运单|到哪|送到了|没收到|还没到|查一下.*单|我的.*单|买了.*东西|下单"
    )),
    # aftersale: 退货、换货、退款、售后、投诉
    ("aftersale", re.compile(
        r"退货|换货|退款|售后|退钱|退.*款|换.*码|换.*大|换.*小|质量.*问题|坏.*了|有.*问题|投诉|差评|不.*满意"
    )),
    # product: 搜索、推荐、价格、有没有卖
    ("product", re.compile(
        r"推荐|有没有|多少钱|价格|怎么.*卖|有卖|买.*什么|选.*哪|对比|哪个.*好|介绍.*一下|怎么选|适合.*吗|值得.*买"
    )),
    # human: 转人工
    ("human", re.compile(r"转人工|人工客服|找.*人|投诉.*电话")),
]


def _pre_route(user_msg: str) -> str | None:
    """正则盲筛，返回匹配的 intent 或 None"""
    if not user_msg:
        return None
    msg = user_msg.strip()
    for intent, pattern in ROUTE_RULES:
        if pattern.search(msg):
            _safe_print(f"[PreRouter] regex match -> {intent}")
            return intent
    return None


# ── 预路由节点 ──────────────────────────────────────────────────────────────────
def pre_router_node(state: CSRState) -> dict:
    """关键词盲筛：命中直接返回意图，未命中交给 LLM"""
    user_msg = state["messages"][-1].content if state["messages"] else ""
    intent = _pre_route(str(user_msg))
    if intent:
        return {
            "intent": intent,
            "iteration_count": 0,
            "next_agent": intent,
        }
    # 未命中，标记需要 LLM
    return {"intent": "__llm__"}


def route_after_pre(state: CSRState) -> str:
    """预路由后的分岔：命中→supervisor，未命中→LLM分类器"""
    if state.get("intent") == "__llm__":
        return "intent_classifier"
    return "supervisor"


# ── 意图分类节点（LLM）──────────────────────────────────────────────────────────
def intent_classifier_node(state: CSRState) -> dict:
    """预路由未命中时才走这里，用 LLM 分析用户消息"""
    user_msg = state["messages"][-1].content if state["messages"] else ""

    prompt = f"""分析用户消息，输出意图标签。

标签：order(订单/物流) product(商品/推荐) aftersale(退货/退款/投诉) faq(政策/支付/会员/配送时效等通用问题) human(转人工)

用户消息：{user_msg}

只输出一个标签（小写英文）："""

    response = llm.invoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()

    if intent not in AGENT_NAMES + ["human"]:
        intent = "faq"

    _safe_print(f"[Intent Classifier] LLM -> {intent}")
    return {"intent": intent, "iteration_count": 0, "next_agent": intent}


# ── Supervisor 决策节点 ─────────────────────────────────────────────────────────
def supervisor_node(state: CSRState) -> dict:
    """
    LLM Supervisor：动态决定下一步路由
    - 根据意图和当前对话状态，决定调用哪个子Agent或结束
    """
    iteration = state.get("iteration_count", 0) + 1  # 每次调度递增
    intent = state.get("intent", "")

    # 获取最近的对话摘要
    recent_msgs = state["messages"][-4:] if len(state["messages"]) > 4 else state["messages"]
    context = "\n".join(
        f"[{m.__class__.__name__}] {m.content[:200]}" for m in recent_msgs
    )

    prompt = f"""你是一个电商客服的调度员。根据对话内容决定下一步行动。

可用专家：order（订单）、product（商品）、aftersale（售后）、faq（常见问题）
结束条件：用户问题已解决，或最后一条消息末尾有 [DONE] 标记

当前意图：{intent}
已调度轮数：{iteration}（最多5轮）

最近对话：
{context}

请仅输出以下之一：order / product / aftersale / faq / FINISH"""

    # 强制检查：最后一条 AI 消息有 [DONE] 或超过轮数上限 → 直接结束
    last_content = state["messages"][-1].content if state["messages"] else ""
    if "[DONE]" in str(last_content):
        _safe_print(f"[Supervisor] 第{iteration}轮 -> FINISH (检测到[DONE])")
        return {"next_agent": "FINISH", "iteration_count": iteration}
    if iteration > 5:
        _safe_print(f"[Supervisor] 第{iteration}轮 -> FINISH (超过轮数上限)")
        return {"next_agent": "FINISH", "iteration_count": iteration}

    response = llm.invoke([HumanMessage(content=prompt)])
    decision = response.content.strip()

    # 归一化：LLM 输出异常时回退到初始意图
    if decision not in AGENT_NAMES + ["FINISH"]:
        decision = intent if intent in AGENT_NAMES else "faq"

    _safe_print(f"[Supervisor] 第{iteration}轮 → {decision}")

    return {"next_agent": decision, "iteration_count": iteration}


# ── 子Agent调用节点 ─────────────────────────────────────────────────────────────
def call_order_agent(state: CSRState, config: RunnableConfig) -> dict:
    _safe_print("[Order Agent] 开始处理...")
    result = _subgraphs["order"].invoke({"messages": state["messages"]}, config)
    last_msg = result["messages"][-1]
    _safe_print(f"[Order Agent] 完成: {str(last_msg.content)[:80]}...")
    return {"messages": [last_msg]}


def call_product_agent(state: CSRState, config: RunnableConfig) -> dict:
    _safe_print("[Product Agent] 开始处理...")
    result = _subgraphs["product"].invoke({"messages": state["messages"]}, config)
    last_msg = result["messages"][-1]
    _safe_print(f"[Product Agent] 完成: {str(last_msg.content)[:80]}...")
    return {"messages": [last_msg]}


def call_aftersale_agent(state: CSRState, config: RunnableConfig) -> dict:
    _safe_print("[AfterSale Agent] 开始处理...")
    result = _subgraphs["aftersale"].invoke({"messages": state["messages"]}, config)
    last_msg = result["messages"][-1]
    _safe_print(f"[AfterSale Agent] 完成: {str(last_msg.content)[:80]}...")

    # 检查是否需要人工审核（售后申请创建）
    content = str(last_msg.content) if last_msg.content else ""
    if "需要人工审核" in content or "待审核" in content:
        _safe_print("[AfterSale Agent] 检测到待审核操作，触发人工确认流程")
        return {
            "messages": [last_msg],
            "next_agent": "human_approval",
        }

    return {"messages": [last_msg]}


def call_faq_agent(state: CSRState, config: RunnableConfig) -> dict:
    _safe_print("[FAQ Agent] 开始处理...")
    result = _subgraphs["faq"].invoke({"messages": state["messages"]}, config)
    last_msg = result["messages"][-1]
    _safe_print(f"[FAQ Agent] 完成: {str(last_msg.content)[:80]}...")
    return {"messages": [last_msg]}


# ── 人工审核节点 ────────────────────────────────────────────────────────────────
def human_approval_node(state: CSRState) -> dict:
    """
    人工审核节点：使用 interrupt() 暂停图执行，等待人工确认
    当人工通过 /api/human/approve 确认后，图继续执行
    """
    last_msg = state["messages"][-1].content if state["messages"] else ""

    # interrupt 会暂停图并向外传递审核信息
    approval_result = interrupt({
        "type": "human_approval",
        "message": "售后申请需要人工审核确认",
        "details": str(last_msg)[:500],
    })

    if approval_result == "approve":
        response = ("✅ 您的售后申请已通过人工审核！"
                    "请按提示将商品寄回，我们收到后将在1-3个工作日内完成处理。"
                    "如有疑问请随时联系我们。\n\n[DONE]")
    else:
        response = ("您的售后申请未通过审核。"
                    "如有疑问请联系人工客服 400-888-8888。\n\n[DONE]")

    return {"messages": [AIMessage(content=response)]}


# ── 转人工节点 ──────────────────────────────────────────────────────────────────
def human_handoff_node(state: CSRState) -> dict:
    _safe_print("[Human Handoff] 转接人工客服...")
    response = (
        "正在为您转接人工客服，请稍候...\n\n"
        "人工客服将在工作时间内（每天9:00-22:00）尽快为您服务。"
        "您也可以拨打客服热线 400-888-8888。\n\n[DONE]"
    )
    return {"messages": [AIMessage(content=response)]}


# ── 路由函数 ────────────────────────────────────────────────────────────────────
def route_by_next_agent(state: CSRState) -> str:
    """根据 supervisor 的 next_agent 决定路由"""
    agent = state.get("next_agent", "FINISH")
    if agent in AGENT_NAMES:
        return agent
    if agent == "human_approval":
        return "human_approval"
    if agent == "human":
        return "human_handoff"
    return "FINISH"


def route_after_agent(state: CSRState) -> str:
    """子Agent执行完成后，检查是否需要人工审核"""
    next_a = state.get("next_agent", "")
    if next_a == "human_approval":
        return "human_approval"
    return "supervisor"


# ── 构建主图 ────────────────────────────────────────────────────────────────────
def build_csr_graph(checkpointer=None):
    """
    构建电商客服 Supervisor 主图

    Args:
        checkpointer: 持久化器，None 则使用 MemorySaver
    """
    builder = StateGraph(CSRState)

    # 添加节点
    builder.add_node("pre_router", pre_router_node)
    builder.add_node("intent_classifier", intent_classifier_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("order_agent", call_order_agent)
    builder.add_node("product_agent", call_product_agent)
    builder.add_node("aftersale_agent", call_aftersale_agent)
    builder.add_node("faq_agent", call_faq_agent)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("human_handoff", human_handoff_node)

    # 连接边：START → pre_router → [命中→supervisor | 未命中→LLM分类器→supervisor]
    builder.add_edge(START, "pre_router")
    builder.add_conditional_edges("pre_router", route_after_pre, {
        "supervisor": "supervisor",
        "intent_classifier": "intent_classifier",
    })
    builder.add_edge("intent_classifier", "supervisor")

    # Supervisor 路由
    builder.add_conditional_edges(
        "supervisor",
        route_by_next_agent,
        {
            "order": "order_agent",
            "product": "product_agent",
            "aftersale": "aftersale_agent",
            "faq": "faq_agent",
            "human": "human_handoff",
            "human_approval": "human_approval",
            "FINISH": END,
        },
    )

    # 子Agent执行后回 Supervisor（或去人工审核）
    builder.add_conditional_edges(
        "order_agent",
        route_after_agent,
        {"supervisor": "supervisor", "human_approval": "human_approval"},
    )
    builder.add_conditional_edges(
        "product_agent",
        route_after_agent,
        {"supervisor": "supervisor", "human_approval": "human_approval"},
    )
    builder.add_conditional_edges(
        "aftersale_agent",
        route_after_agent,
        {"supervisor": "supervisor", "human_approval": "human_approval"},
    )
    builder.add_conditional_edges(
        "faq_agent",
        route_after_agent,
        {"supervisor": "supervisor", "human_approval": "human_approval"},
    )

    # 人工节点 → 结束
    builder.add_edge("human_approval", END)
    builder.add_edge("human_handoff", END)

    # 编译
    # - checkpointer=None（云部署）：LangGraph Cloud 自动注入 PostgresSaver
    # - checkpointer=实例（本地 server）：由调用方注入
    if checkpointer is None:
        return builder.compile()  # 云部署：平台注入 checkpointer
    return builder.compile(checkpointer=checkpointer)


# ── 便捷函数（用于调试和 eval.py）────────────────────────────────────────────
def chat(question: str, session_id: str = "default", checkpointer=None) -> str:
    """单次调用（调试用，需传入 checkpointer）"""
    graph = build_csr_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": session_id, "user_phone": ""}}
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=question)],
            "intent": "", "iteration_count": 0, "next_agent": "",
            "user_phone": "",
        },
        config=config,
    )
    return result["messages"][-1].content
