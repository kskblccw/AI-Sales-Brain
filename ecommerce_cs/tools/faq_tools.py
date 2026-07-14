"""
faq_tools.py — FAQ 常见问题检索工具
"""

from langchain_core.tools import tool

from database import search_faqs_db, get_faq_categories_sync


@tool
def search_faq(query: str) -> str:
    """
    在FAQ知识库中搜索常见问题答案。
    当用户询问配送、支付、会员、退换货政策等常见问题时使用。

    Args:
        query: 问题关键词，如「配送时间」「怎么退货」「会员权益」
    """
    faqs = search_faqs_db(query, limit=5)
    if not faqs:
        return f"FAQ 库中暂未收录关于「{query}」的问题。建议联系人工客服获取帮助。"

    lines = [f"关于「{query}」的常见问题："]
    for f in faqs:
        lines.append(f"\n  Q: {f.question}")
        lines.append(f"  A: {f.answer}")
        lines.append(f"  [分类：{f.category}]")

    return "\n".join(lines)


@tool
def get_faq_categories() -> str:
    """获取FAQ知识库中的所有问题分类列表。"""
    categories = get_faq_categories_sync()
    return "FAQ 问题分类：" + "、".join(categories)


FAQ_TOOLS = [search_faq, get_faq_categories]
