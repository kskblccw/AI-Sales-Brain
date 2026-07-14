"""工具包 — 收集所有子 Agent 所需的工具"""

from tools.order_tools import ORDER_TOOLS
from tools.product_tools import PRODUCT_TOOLS
from tools.aftersale_tools import AFTERSALE_TOOLS
from tools.faq_tools import FAQ_TOOLS

# 按 Agent 分组的工具集
AGENT_TOOLS = {
    "order": ORDER_TOOLS,
    "product": PRODUCT_TOOLS,
    "aftersale": AFTERSALE_TOOLS,
    "faq": FAQ_TOOLS,
}

# 全部工具（供 supervisor 使用）
ALL_TOOLS = ORDER_TOOLS + PRODUCT_TOOLS + AFTERSALE_TOOLS + FAQ_TOOLS
