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
    """查询退换货和售后政策。当用户询问「退货政策」「怎么退款」「售后规则」时使用。"""
    return """
【退换货政策】

1. 退货规则：
   - 7天无理由退货：商品完好、不影响二次销售（吊牌/包装完整）
   - 质量问题退货：15天内支持换货或退货，运费由平台承担
   - 生鲜食品不支持无理由退货

2. 换货规则：
   - 质量问题：15天内联系客服申请换货
   - 尺码不合适：7天内可申请换货（保持商品完好）

3. 退款规则：
   - 退货签收后1-3个工作日质检
   - 质检通过后立即退款，按原支付方式返还
   - 支付宝/微信：即时到账 | 银行卡：1-3个工作日

4. 不适用无理由退货：
   - 生鲜食品、个人护理、定制商品、虚拟商品、已拆封软件

5. 售后热线：400-888-8888（每天9:00-22:00）
""".strip()


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

售后申请已提交！
申请编号：{req.return_no} | 订单号：{order_no}
售后类型：{return_type} | 原因：{reason}
当前状态：待审核

客服将在1-2个工作日内完成审核。此申请需人工审核确认后方可生效。
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
