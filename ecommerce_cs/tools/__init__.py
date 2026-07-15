"""工具包 — 收集所有子 Agent 所需的工具"""

from tools.order_tools import ORDER_TOOLS
from tools.product_tools import PRODUCT_TOOLS
from tools.aftersale_tools import AFTERSALE_TOOLS
from tools.faq_tools import FAQ_TOOLS
from tools.auth_tools import AUTH_TOOLS

# 所有 Agent 共享的身份验证工具
SHARED_TOOLS = AUTH_TOOLS

# 按 Agent 分组的工具集（各 Agent 额外带 SHARED_TOOLS）
AGENT_TOOLS = {
    "order": SHARED_TOOLS + ORDER_TOOLS,
    "product": SHARED_TOOLS + PRODUCT_TOOLS,
    "aftersale": SHARED_TOOLS + AFTERSALE_TOOLS,
    "faq": SHARED_TOOLS + FAQ_TOOLS,
}

# 全部工具
ALL_TOOLS = SHARED_TOOLS + ORDER_TOOLS + PRODUCT_TOOLS + AFTERSALE_TOOLS + FAQ_TOOLS
