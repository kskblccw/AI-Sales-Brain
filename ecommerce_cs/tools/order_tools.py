"""
order_tools.py — 订单查询、物流跟踪工具
"""

from langchain_core.tools import tool

from database import find_order_by_no, find_orders_by_user, find_user_by_phone


@tool
def query_order(order_no: str) -> str:
    """
    根据订单号查询订单详情（含金额、状态、物流和商品明细）。
    当用户询问某个具体订单的详情时使用。

    Args:
        order_no: 订单编号，格式如 ORD202401010001
    """
    order = find_order_by_no(order_no)
    if not order:
        return f"未找到订单 {order_no}。请确认订单号是否正确。"

    items_text = "\n".join(
        f"  - {item.product.name} × {item.quantity}（¥{item.unit_price}）"
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
def track_shipment(order_no: str) -> str:
    """
    查询订单的物流追踪信息。
    当用户询问「我的快递到哪了」「物流状态」时使用。

    Args:
        order_no: 订单编号
    """
    order = find_order_by_no(order_no)
    if not order:
        return f"未找到订单 {order_no}。"

    if not order.tracking_no:
        return f"订单 {order_no} 暂未发货，当前状态：{order.status.value}。"

    # 模拟物流轨迹（真实场景接入快递100等API）
    import random
    statuses = [
        "快递员已揽收",
        "到达分拣中心",
        "运输中",
        "到达目的地分拣中心",
        "快递员派送中",
        "已签收",
    ]
    current_idx = random.randint(2, len(statuses) - 1) if order.status.value == "已发货" else len(statuses) - 1

    lines = [f"物流单号：{order.tracking_no}（{'顺丰速运' if 'SF' in order.tracking_no else '中通快递' if 'ZTO' in order.tracking_no else '圆通速递' if 'YTO' in order.tracking_no else '韵达快递' if 'YD' in order.tracking_no else '京东物流'}）"]
    from datetime import datetime, timedelta
    for i in range(current_idx + 1):
        time = datetime.now() - timedelta(hours=(current_idx - i) * random.randint(2, 12))
        lines.append(f"  [{time.strftime('%m-%d %H:%M')}] {statuses[i]}")

    lines.append(f"\n当前状态：{statuses[current_idx]}")
    return "\n".join(lines)


@tool
def list_my_orders(phone: str) -> str:
    """
    查询某用户的所有订单列表。
    当用户询问「我的订单」「帮我查一下我的订单」时使用。

    Args:
        phone: 用户手机号
    """
    user = find_user_by_phone(phone)
    if not user:
        return f"未找到手机号为 {phone} 的用户。请确认手机号是否正确。"

    orders = find_orders_by_user(user.id)
    if not orders:
        return f"用户 {user.name}（{phone}）暂无订单记录。"

    lines = [f"用户 {user.name} 的订单列表（共 {len(orders)} 单）："]
    for order in orders:
        items_summary = "、".join(
            f"{item.product.name}×{item.quantity}"
            for item in order.items
        )
        lines.append(
            f"  [{order.status.value}] {order.order_no} — ¥{order.total:.2f}"
            f" — {items_summary} — {order.created_at.strftime('%m-%d')}"
        )

    return "\n".join(lines)


ORDER_TOOLS = [query_order, track_shipment, list_my_orders]
