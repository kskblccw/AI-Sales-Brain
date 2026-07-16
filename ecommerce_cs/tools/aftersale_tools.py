"""
aftersale_tools.py — 退换货、售后工单工具

手机号从 config 静默获取，LLM 不传也不"看到"。
"""

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from database import (
    find_order_by_no, find_user_by_phone, find_return_by_no,
    create_return_request_sync,
)


def _get_phone(config: RunnableConfig) -> str:
    return (config or {}).get("configurable", {}).get("user_phone", "")


@tool
def check_return_policy() -> str:
    """
    查询退换货和售后政策。当用户询问「退货政策」「怎么退款」「售后规则」时使用。
    从 RAG 知识库中检索最新政策，始终与知识库保持同步。
    """
    from rag import search_product_knowledge
    result = search_product_knowledge("退换货政策 退款规则 售后政策 换货流程", k=3)
    if result and "未找到" not in result:
        return result
    return "暂未找到售后政策信息，请联系人工客服 400-888-8888。"


@tool
def create_return_request(
    order_no: str, reason: str, return_type: str = "退货",
    config: RunnableConfig = None,
) -> str:
    """
    为当前用户创建退换货/退款申请工单。自动验证身份，无需传入手机号。
    当用户明确表示要退货、换货或退款时使用。

    Args:
        order_no: 需要售后的订单号
        reason: 退换货原因，如「质量问题」「不想要了」「发错货」「尺码不合适」
        return_type: 售后类型，可选「退货」/「换货」/「退款」，默认「退货」
    """
    phone = _get_phone(config)
    if not phone:
        return "您还未登录，无法创建售后申请。请先在前端右上角输入手机号完成登录。"

    # 1. 验证用户身份
    user = find_user_by_phone(phone)
    if not user:
        return f"未找到手机号 {phone} 对应的用户，请联系人工客服。"

    # 2. 查订单
    order = find_order_by_no(order_no)
    if not order:
        return f"未找到订单 {order_no}。请确认订单号。"

    # 3. 验证归属
    if order.user_id != user.id:
        return (
            f"身份验证失败！订单 {order_no} 不属于您（{user.name}）。"
            f"请核对订单号，如有疑问请联系人工客服。"
        )

    # 4. 检查订单状态
    if order.status.value in ("待付款", "已取消"):
        return f"订单 {order_no} 当前状态为「{order.status.value}」，无法申请售后。"

    # 5. 验证售后类型
    valid_types = ["退货", "换货", "退款"]
    if return_type not in valid_types:
        return f"不支持的售后类型：{return_type}。可选：{'/'.join(valid_types)}"

    # 6. 创建
    req = create_return_request_sync(
        order_id=order.id, user_id=user.id,
        return_type=return_type, reason=reason,
    )

    return f"""
身份验证通过（{user.name}）

申请编号：{req.return_no} | 订单号：{order_no}
售后类型：{return_type} | 原因：{reason}

⚠️ 请在确认弹窗中点击"确认"以提交此售后申请。
""".strip()


@tool
def query_return_status(return_no: str, config: RunnableConfig = None) -> str:
    """
    查询退换货工单的处理状态。自动验证身份。
    当用户询问「我的退货进度」「售后处理好了吗」时使用。

    Args:
        return_no: 售后申请编号
    """
    phone = _get_phone(config)
    if not phone:
        return "您还未登录。请先在前端右上角输入手机号完成登录。"

    user = find_user_by_phone(phone)
    if not user:
        return f"未找到手机号 {phone} 对应的用户。"

    req = find_return_by_no(return_no)
    if not req:
        return f"未找到售后申请 {return_no}。请确认编号。"

    if req.user_id != user.id:
        return f"售后申请 {return_no} 不属于您（{user.name}），请核对编号。"

    return f"""
身份验证通过（{user.name}）

售后申请编号：{req.return_no} | 关联订单：{req.order.order_no}
售后类型：{req.type.value} | 原因：{req.reason}
当前状态：{req.status.value}
提交时间：{req.created_at.strftime('%Y-%m-%d %H:%M')}

{'客服已处理完毕。' if req.status.value in ('已通过', '已拒绝', '已完成') else '仍在处理中，请耐心等待。'}
""".strip()


AFTERSALE_TOOLS = [check_return_policy, create_return_request, query_return_status]
