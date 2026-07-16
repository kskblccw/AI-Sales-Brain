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
from memory import (
    build_context_injection, _user_id_from_phone,
)
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
    user_phone: str        # 当前用户手机号（元数据）
    summary: str           # 历史对话摘要（压缩后）
    user_profile_json: str # 用户画像 JSON（压缩后）
    approval_decision: str # 人工审核决策：approve / reject / ""
    approval_meta: str     # 审核元数据 JSON（如回滚信息）


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

# ── 安全打印（Windows console 兼容）───────────────────────────────────────────
def _safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs, flush=True)
    except UnicodeEncodeError:
        try:
            # 尝试用 UTF-8 绕过 console 编码限制
            import sys
            for a in args:
                if isinstance(a, str):
                    sys.stdout.buffer.write(a.encode("utf-8") + b"\n")
                else:
                    print(a, flush=True)
        except Exception:
            safe_args = [a.encode("ascii", "replace").decode("ascii") if isinstance(a, str) else a for a in args]
            print(*safe_args, flush=True)


# ── 正则规则预路由 ──────────────────────────────────────────────────────────────
# 80% 高频问题直接命中，跳过 LLM 意图分类，省 token + 秒级响应
import re

ROUTE_RULES = [
    # order: 订单、物流、快递、改地址（"下单"太宽泛，仅限"帮我下单/我要下单"）
    ("order", re.compile(
        r"订单|物流|快递|发货|运单|到哪|送到了|没收到|还没到|查一下.*单|我的.*单|买了.*东西|我要下单|帮我下单|改.*地址|修改.*地址"
    )),
    # aftersale: 退货、换货、退款、投诉（去掉"有.*问题"太宽泛）
    ("aftersale", re.compile(
        r"退货|换货|退款|退钱|售后|退.*款|换.*码|换.*大|换.*小|质量.*问题|坏.*了|投诉|差评"
    )),
    # product: 搜索、推荐、价格、有没有卖
    ("product", re.compile(
        r"推荐|有没有|多少钱|价格|怎么.*卖|有卖|买.*什么|选.*哪|对比|哪个.*好|介绍.*一下|怎么选|适合.*吗|值得.*买"
    )),
    # faq: 支付/配送/会员/积分/营业时间等通用问题 + 寒暄
    ("faq", re.compile(
        r"支付|花呗|分期|会员|积分|营业时间|企业.*购|发票|配送.*时效|几天.*到|多久.*发货|怎么.*买|怎么.*选|如何.*购买|优惠券|学生.*优惠|退.*政策|售后.*政策|退款.*时间|隐私|账.*安全|自提|几天.*收|你好|在吗|谢谢|感谢|再见|拜拜"
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
    Supervisor：第1轮用 LLM 路由，第2轮起自动 FINISH
    不再依赖 LLM 输出的 [DONE] 文本标记（防注入），改用系统级状态判断
    """
    iteration = state.get("iteration_count", 0) + 1
    intent = state.get("intent", "")

    # 安全检查：超过上限强制结束
    if iteration > 3:
        _safe_print(f"[Supervisor] 第{iteration}轮 -> FINISH (安全上限)")
        return {"next_agent": "FINISH", "iteration_count": iteration}

    # 第1轮：用 LLM 决定路由（基于意图 + 用户消息）
    if iteration == 1:
        recent_msgs = state["messages"][-3:] if len(state["messages"]) > 3 else state["messages"]
        context = "\n".join(
            f"[{m.__class__.__name__}] {str(m.content)[:200]}" for m in recent_msgs
        )

        prompt = f"""根据用户消息决定路由。意图={intent}。

可用：order(订单/物流) product(商品/推荐) aftersale(退货/退款) faq(配送/支付/会员等通用) human(转人工客服) FINISH(结束)

对话：
{context}

只输出一个标签（小写英文）："""

        response = llm.invoke([HumanMessage(content=prompt)])
        decision = response.content.strip()

        if decision not in AGENT_NAMES + ["FINISH", "human"]:
            decision = intent if intent in AGENT_NAMES else "faq"

        _safe_print(f"[Supervisor] 第1轮 → {decision}")
        return {"next_agent": decision, "iteration_count": iteration}

    # 第2轮+：子 Agent 已完成 ReAct 循环，自动结束
    _safe_print(f"[Supervisor] 第{iteration}轮 -> FINISH (子Agent已完成)")
    return {"next_agent": "FINISH", "iteration_count": iteration}


# ── 记忆系统节点 ────────────────────────────────────────────────────────────────
def prepare_context_node(state: CSRState) -> dict:
    """
    每轮对话开始时：从 DB 注入当前用户的历史摘要 + 用户画像。
    同时清除旧的 [系统记忆] 消息，确保不同用户的记忆不会混合。
    """
    phone = state.get("user_phone", "")

    if not phone:
        return {}

    user_id = _user_id_from_phone(phone)
    injection = build_context_injection(user_id)

    # 移除所有旧的 [系统记忆] 消息（可能是其他用户或旧轮次残留）
    from langchain_core.messages import RemoveMessage
    old_memory_ids = [
        m.id for m in state.get("messages", [])
        if isinstance(m, SystemMessage) and m.content and "[系统记忆]" in str(m.content)
    ]

    if not injection:
        # 没有可注入的记忆，只清除旧记忆
        return {"messages": [RemoveMessage(id=mid) for mid in old_memory_ids]} if old_memory_ids else {}

    msg = SystemMessage(content=f"[系统记忆]\n{injection}\n\n请根据以上用户画像和历史摘要提供个性化服务。")
    result = {"messages": [msg]}
    if old_memory_ids:
        result["messages"] = [RemoveMessage(id=mid) for mid in old_memory_ids] + result["messages"]

    return result


# ── 子Agent调用节点 ─────────────────────────────────────────────────────────────
def _invoke_subgraph(name: str, state: CSRState, config: RunnableConfig) -> dict:
    """通用子图调用：返回全部消息（含 ToolMessage），上层自行取最后一条展示"""
    _safe_print(f"[{name}] 开始处理...")
    try:
        result = _subgraphs[name].invoke({"messages": state["messages"]}, config)
        msgs = result.get("messages", [])
        if not msgs:
            _safe_print(f"[{name}] 子图返回空消息，使用兜底回复")
            return {"messages": [AIMessage(content=f"{name}专员暂时无法处理您的请求，请稍后重试或联系人工客服。")]}
        _safe_print(f"[{name}] 完成: {str(msgs[-1].content)[:80]}...")
        return {"messages": msgs}
    except Exception as e:
        _safe_print(f"[{name}] 异常: {e}")
        return {"messages": [AIMessage(content="抱歉，系统处理您的请求时遇到问题，请稍后重试。如需紧急帮助请拨打 400-888-8888。")]}


def _has_approval_marker(msgs: list) -> str:
    """搜全部消息（含 ToolMessage），检测是否包含需要确认的操作"""
    for m in msgs:
        content = str(getattr(m, "content", ""))
        if "申请编号" in content:
            return content
    return ""


def call_order_agent(state: CSRState, config: RunnableConfig) -> dict:
    result = _invoke_subgraph("order", state, config)
    msgs = result["messages"]
    last_msg = msgs[-1]

    trigger = _has_approval_marker(msgs)
    if trigger:
        _safe_print("[Order Agent] 敏感操作需确认，路由至 human_approval")
        import re, json as _json
        meta = {}
        m = re.search(r"订单号：(\w+)", trigger)
        if m:
            meta["order_no"] = m.group(1)
        m = re.search(r"旧地址：(.+?)(?:\n|$)", trigger)
        if m:
            meta["old_address"] = m.group(1).strip()
        return {
            "messages": [last_msg],
            "next_agent": "human_approval",
            "approval_meta": _json.dumps(meta, ensure_ascii=False) if meta else "",
        }

    return {"messages": [last_msg]}


def call_product_agent(state: CSRState, config: RunnableConfig) -> dict:
    result = _invoke_subgraph("product", state, config)
    return {"messages": [result["messages"][-1]]}


def call_aftersale_agent(state: CSRState, config: RunnableConfig) -> dict:
    result = _invoke_subgraph("aftersale", state, config)
    msgs = result["messages"]
    last_msg = msgs[-1]

    if _has_approval_marker(msgs):
        _safe_print("[AfterSale Agent] 售后工单已创建，触发确认流程")
        return {
            "messages": [last_msg],
            "next_agent": "human_approval",
        }

    return {"messages": [last_msg]}


def call_faq_agent(state: CSRState, config: RunnableConfig) -> dict:
    result = _invoke_subgraph("faq", state, config)
    return {"messages": [result["messages"][-1]]}


# ── 用户确认节点 ────────────────────────────────────────────────────────────────
def human_approval_node(state: CSRState) -> dict:
    """
    用户确认节点：interrupt() 暂停 → 前端弹窗 → 用户点确认/取消 → resume
    """
    import json as _json

    last_msg = state["messages"][-1].content if state["messages"] else ""
    meta_raw = state.get("approval_meta", "")

    decision = interrupt({
        "type": "user_confirm",
        "message": "请确认此操作",
        "details": str(last_msg)[:500],
    })

    meta = {}
    if meta_raw:
        try:
            meta = _json.loads(meta_raw)
        except _json.JSONDecodeError:
            pass

    is_address = "地址" in str(last_msg) or bool(meta.get("order_no"))

    if decision == "approve":
        if is_address:
            response = "✅ 已确认，收货地址已更新。"
        else:
            response = ("✅ 售后申请已提交！请按提示将商品寄回，"
                        "我们收到后将在1-3个工作日内完成处理。")
    else:
        if is_address:
            old_addr = meta.get("old_address", "")
            order_no = meta.get("order_no", "")
            if old_addr and order_no:
                from database import find_order_by_no, update_order_address_sync
                order = find_order_by_no(order_no)
                if order:
                    update_order_address_sync(order.id, old_addr)
            response = "已取消，地址未修改。"
        else:
            response = "已取消，售后申请未提交。如需帮助请联系客服 400-888-8888。"

    return {"messages": [AIMessage(content=response)], "approval_meta": ""}


# ── 转人工节点 ──────────────────────────────────────────────────────────────────
def human_handoff_node(state: CSRState) -> dict:
    _safe_print("[Human Handoff] 转接人工客服...")
    response = (
        "正在为您转接人工客服，请稍候...\n\n"
        "人工客服将在工作时间内（每天9:00-22:00）尽快为您服务。"
        "您也可以拨打客服热线 400-888-8888。"
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
        return "human"
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
    builder.add_node("prepare_context", prepare_context_node)
    builder.add_node("intent_classifier", intent_classifier_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("order_agent", call_order_agent)
    builder.add_node("product_agent", call_product_agent)
    builder.add_node("aftersale_agent", call_aftersale_agent)
    builder.add_node("faq_agent", call_faq_agent)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("human_handoff", human_handoff_node)

    # 连接边：START → pre_router → prepare_context → [命中→supervisor | 未命中→LLM→supervisor]
    builder.add_edge(START, "pre_router")
    builder.add_edge("pre_router", "prepare_context")
    builder.add_conditional_edges("prepare_context", route_after_pre, {
        "supervisor": "supervisor",
        "intent_classifier": "intent_classifier",
    })
    builder.add_edge("intent_classifier", "supervisor")

    # Supervisor 路由（FINISH 直达 END，压缩摘要由后台 API 异步处理）
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

    # 人工节点 → 直接结束（压缩摘要由后台 API 异步处理）
    builder.add_edge("human_approval", END)
    builder.add_edge("human_handoff", END)

    # 编译
    if checkpointer is None:
        return builder.compile()
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
            "user_phone": "", "summary": "", "user_profile_json": "",
            "approval_decision": "", "approval_meta": "",
        },
        config=config,
    )
    return result["messages"][-1].content
