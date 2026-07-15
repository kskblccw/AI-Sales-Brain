"""
order_tools.py — 订单查询、物流跟踪工具

手机号从 config.configurable.user_phone 静默获取，不暴露给 LLM。
"""

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from database import find_order_by_no, find_orders_by_user, find_user_by_phone


def _get_phone(config: RunnableConfig) -> str:
    return (config or {}).get("configurable", {}).get("user_phone", "")


@tool
def query_order(order_no: str, config: RunnableConfig = None) -> str:
    """
    根据订单号查询订单详情（含金额、状态、物流和商品明细）。
    当用户询问某个具体订单时使用。会自动验证订单是否属于当前用户。

    Args:
        order_no: 订单编号，格式如 ORD202607150001
    """
    phone = _get_phone(config)
    if not phone:
        return "您还未登录。请先在前端右上角输入手机号完成登录，我才能帮您查询订单。"

    order = find_order_by_no(order_no)
    if not order:
        return f"未找到订单 {order_no}。请确认订单号是否正确。"

    # 验证归属
    user = find_user_by_phone(phone)
    if not user or order.user_id != user.id:
        return f"订单 {order_no} 不属于您（{phone}），请确认订单号。"

    items_text = "\n".join(
        f"  - {item.product.name} x {item.quantity}（¥{item.unit_price}）"
        for item in order.items
    )

    return f"""
订单号：{order.order_no}
状态：{order.status.value}
下单时间：{order.created_at.strftime('%Y-%m-%d %H:%M')}
收货地址：{order.address}
物流单号：{order.tracking_no or '暂未发货'}
商品明细：
{items_text}
订单总额：¥{order.total:.2f}
""".strip()


@tool
def track_shipment(order_no: str, config: RunnableConfig = None) -> str:
    """
    查询订单的物流追踪信息。当用户询问「我的快递到哪了」「物流状态」时使用。
    会自动验证订单是否属于当前用户。

    Args:
        order_no: 订单编号
    """
    phone = _get_phone(config)
    if not phone:
        return "您还未登录。请先在前端右上角输入手机号完成登录。"

    order = find_order_by_no(order_no)
    if not order:
        return f"未找到订单 {order_no}。"

    user = find_user_by_phone(phone)
    if not user or order.user_id != user.id:
        return f"订单 {order_no} 不属于您，请确认订单号。"

    if not order.tracking_no:
        return f"订单 {order_no} 暂未发货，当前状态：{order.status.value}。"

    import random
    statuses = ["快递员已揽收", "到达分拣中心", "运输中", "到达目的地分拣中心", "快递员派送中", "已签收"]
    current_idx = random.randint(2, len(statuses) - 1) if order.status.value == "已发货" else len(statuses) - 1

    carriers = {"SF": "顺丰速运", "YT": "圆通速递", "ZTO": "中通快递", "JD": "京东物流", "DB": "德邦快递"}
    carrier_name = "快递"
    for k, v in carriers.items():
        if k in order.tracking_no:
            carrier_name = v
            break

    from datetime import datetime, timedelta
    lines = [f"物流单号：{order.tracking_no}（{carrier_name}）"]
    for i in range(current_idx + 1):
        t = datetime.now() - timedelta(hours=(current_idx - i) * random.randint(2, 12))
        lines.append(f"  [{t.strftime('%m-%d %H:%M')}] {statuses[i]}")
    lines.append(f"\n当前状态：{statuses[current_idx]}")
    return "\n".join(lines)


@tool
def list_my_orders(config: RunnableConfig = None) -> str:
    """
    查询当前登录用户的所有订单列表。
    当用户询问「我的订单」「帮我查一下我的订单」时使用。
    无需参数，自动识别当前用户身份。
    """
    phone = _get_phone(config)
    if not phone:
        return "您还未登录。请先在前端右上角输入手机号完成登录，我才能帮您查询订单。"

    user = find_user_by_phone(phone)
    if not user:
        return f"未找到手机号 {phone} 对应的用户，请联系人工客服。"

    orders = find_orders_by_user(user.id)
    if not orders:
        return f"用户 {user.name} 暂无订单记录。"

    lines = [f"用户 {user.name} 的订单列表（共 {len(orders)} 单）："]
    for order in orders:
        items_summary = "、".join(
            f"{item.product.name}x{item.quantity}"
            for item in order.items
        )
        lines.append(
            f"  [{order.status.value}] {order.order_no} — ¥{order.total:.2f}"
            f" — {items_summary} — {order.created_at.strftime('%m-%d')}"
        )

    return "\n".join(lines)


@tool
def modify_shipping_address(order_no: str, new_address: str, config: RunnableConfig = None) -> str:
    """
    修改订单的收货地址。仅未发货的订单可修改。
    当用户要求"改地址""修改收货地址""换地址"时使用。会自动验证订单归属。

    Args:
        order_no: 订单编号
        new_address: 新的收货地址（完整地址）
    """
    phone = _get_phone(config)
    if not phone:
        return "您还未登录。请先在前端右上角输入手机号完成登录。"

    user = find_user_by_phone(phone)
    if not user:
        return f"未找到手机号 {phone} 对应的用户。"

    order = find_order_by_no(order_no)
    if not order:
        return f"未找到订单 {order_no}。请确认订单号。"

    if order.user_id != user.id:
        return f"订单 {order_no} 不属于您，请确认订单号。"

    if order.status.value in ("已完成", "已取消"):
        return f"订单 {order_no} 当前状态为「{order.status.value}」，无法修改地址。"

    if order.status.value == "已发货":
        return f"订单 {order_no} 已发货，无法修改地址。建议联系快递公司转寄或联系人工客服 400-888-8888。"

    from database import update_order_address_sync
    import random
    from datetime import datetime

    old_address = order.address
    ok = update_order_address_sync(order.id, new_address)
    if not ok:
        return f"修改地址失败，请稍后重试或联系人工客服。"

    addr_no = f"ADDR{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10, 99)}"

    return f"""
身份验证通过（{user.name}）

申请编号：{addr_no} | 订单号：{order_no}
操作类型：地址修改
旧地址：{old_address}
新地址：{new_address}

⚠️ 请在确认弹窗中点击"确认"以提交地址修改。
""".strip()


ORDER_TOOLS = [query_order, track_shipment, list_my_orders, modify_shipping_address]
