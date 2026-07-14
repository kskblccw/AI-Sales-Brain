"""
product_tools.py — 商品搜索、库存查询、RAG 知识库检索工具
"""

from langchain_core.tools import tool

from database import search_products_db, get_product_by_id
from rag import search_product_knowledge


@tool
def search_products(keyword: str) -> str:
    """
    根据关键词搜索商品，返回匹配的商品列表。
    当用户想找某种商品、询问「有没有XX」「推荐XX」时使用。

    Args:
        keyword: 搜索关键词，如「耳机」「手机」「扫地机器人」
    """
    products = search_products_db(keyword, limit=5)
    if not products:
        return f"未找到与「{keyword}」相关的商品。建议尝试其他关键词，或咨询人工客服。"

    lines = [f"搜索「{keyword}」找到 {len(products)} 个商品："]
    for p in products:
        stock_info = "有货" if p.stock > 0 else "暂时缺货"
        lines.append(
            f"\n  [{p.id}] {p.name}"
            f"\n      价格：¥{p.price:.2f} | 库存：{stock_info}({p.stock}件)"
            f"\n      分类：{p.category}"
            f"\n      简介：{p.description[:80]}..."
        )

    return "\n".join(lines)


@tool
def get_product_detail(product_id: int) -> str:
    """
    获取某个商品的详细信息（规格参数、价格、库存等）。
    当用户对某商品感兴趣、询问「XX怎么样」「详细介绍一下XX」时使用。

    Args:
        product_id: 商品ID（数字编号）
    """
    product = get_product_by_id(product_id)
    if not product:
        return f"未找到商品 ID 为 {product_id} 的商品。"

    specs = product.specs or {}
    specs_text = "\n".join(f"  - {k}：{v}" for k, v in specs.items())

    return f"""
商品名称：{product.name}
商品ID：{product.id}
分类：{product.category}
价格：¥{product.price:.2f}
库存：{product.stock} 件（{'有货' if product.stock > 0 else '缺货'}）

商品描述：
{product.description}

规格参数：
{specs_text or '暂无详细参数'}
""".strip()


@tool
def check_stock(product_id: int) -> str:
    """
    查询某商品的实时库存。
    当用户询问「XX还有货吗」「XX的库存多少」时使用。

    Args:
        product_id: 商品ID
    """
    product = get_product_by_id(product_id)
    if not product:
        return f"未找到商品 {product_id}。"

    if product.stock > 50:
        level = "充足"
    elif product.stock > 10:
        level = "紧张"
    elif product.stock > 0:
        level = "仅剩少量"
    else:
        level = "已售罄"

    return f"商品「{product.name}」当前库存：{product.stock} 件（库存{level}）"


@tool
def search_product_knowledge_tool(query: str) -> str:
    """
    在商品知识库中搜索详细信息（使用指南、选购建议、保养知识、售后政策等）。
    当用户询问商品的使用方法、对比选购、保养维护、保修政策等需要深入知识的问题时使用。

    Args:
        query: 搜索关键词或问题，如「降噪耳机怎么选」「牛排怎么烹饪」
    """
    return search_product_knowledge(query)


PRODUCT_TOOLS = [search_products, get_product_detail, check_stock, search_product_knowledge_tool]
