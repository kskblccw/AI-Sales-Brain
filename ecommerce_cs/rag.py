"""
rag.py — RAG 模块：商品知识库构建、Chroma 向量存储、检索器

- build_product_knowledge_base(): 构建 Chroma 向量索引（首次运行调用）
- get_product_retriever(): 获取检索器（自动加载已有索引）
"""

import os
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma

from config import make_embeddings, CHROMA_PERSIST_DIR
from database import Product, _load_products_async


# ── 构建商品知识文档 ───────────────────────────────────────────────────────────
PRODUCT_KNOWLEDGE_TEMPLATES = {
    "手机数码": """
【{name}】商品使用指南
{description}

规格参数：
{specs_text}

选购建议：
- 适合人群：对数码产品有较高要求的用户
- 使用场景：日常通讯、拍照摄影、移动办公、影音娱乐
- 注意事项：建议配合官方保护壳和屏幕膜使用，避免跌落和进水

售后服务：
- 支持7天无理由退货（未激活）
- 主机保修1年，配件保修6个月
- 官方授权维修点全国联保
""",
    "电脑办公": """
【{name}】办公设备详情
{description}

技术规格：
{specs_text}

使用场景：
- 适合人群：职场白领、程序员、设计师、学生
- 应用场景：日常办公、编程开发、图形设计、远程会议
- 保养提示：定期清洁键盘和屏幕，避免在潮湿环境中使用

售后保障：
- 7天无理由退货
- 主机保修2年，配件保修1年
- 全国联保，支持上门维修服务
""",
    "家用电器": """
【{name}】家用电器使用说明
{description}

产品参数：
{specs_text}

安装与使用：
- 安装方式：建议由专业人员安装（空调/净水器等）
- 使用技巧：按照说明书操作，定期清洁滤网/尘盒等耗材
- 安全提示：使用前确认电压匹配，勿让儿童单独操作

售后政策：
- 7天无理由退货（未拆封）
- 整机保修1-3年（视产品而定）
- 24小时售后热线：400-888-8888
""",
    "服饰鞋包": """
【{name}】时尚单品介绍
{description}

商品参数：
{specs_text}

穿搭与保养：
- 搭配建议：可根据个人风格搭配，经典款百搭不出错
- 清洗方式：建议按标签说明清洗，深色衣物首次请单独洗涤
- 存放方法：鞋子建议使用鞋撑保持形状，包包不使用时填充存放

退换说明：
- 支持7天无理由退货（吊牌完好、未穿着使用）
- 鞋子请在干净地面试穿
- 退换货请保持原包装完整
""",
    "食品生鲜": """
【{name}】食品详情
{description}

产品信息：
{specs_text}

食用与储存：
- 食用方法：坚果/牛奶开袋即食，牛排需解冻后烹饪至全熟
- 储存方式：请按包装说明存放，生鲜食品收到后请立即冷藏/冷冻
- 保质期限：请留意包装上的生产日期和保质期，开封后尽快食用

售后说明：
- 生鲜食品不支持7天无理由退货
- 如有质量问题（变质/破损/错发），签收后24小时内联系客服
- 核实后全额退款或重新补发
""",
}


async def _load_products() -> list:
    """从数据库加载所有商品"""
    return await _load_products_async()


def _build_documents(products: list) -> list[Document]:
    """为每个商品生成知识文档"""
    documents = []

    for p in products:
        specs = p.specs or {}
        specs_text = "\n".join(f"- {k}：{v}" for k, v in specs.items())

        template = PRODUCT_KNOWLEDGE_TEMPLATES.get(
            p.category, PRODUCT_KNOWLEDGE_TEMPLATES["手机数码"]
        )

        content = template.format(
            name=p.name,
            description=p.description,
            specs_text=specs_text or "暂无详细参数",
        )

        documents.append(Document(
            page_content=content,
            metadata={
                "product_id": p.id,
                "product_name": p.name,
                "category": p.category,
                "price": p.price,
                "stock": p.stock,
            },
        ))

    return documents


def build_product_knowledge_base(force: bool = False) -> Chroma:
    """
    构建 Chroma 商品知识库

    Args:
        force: 是否强制重建

    Returns:
        Chroma 向量存储实例
    """
    persist_path = Path(CHROMA_PERSIST_DIR)

    if persist_path.exists() and not force and any(persist_path.iterdir()):
        print(f"Chroma 索引已存在：{CHROMA_PERSIST_DIR}")
        return Chroma(
            persist_directory=CHROMA_PERSIST_DIR,
            embedding_function=make_embeddings(),
        )

    print("正在构建商品知识库...")

    # 加载商品数据（同步方式）
    import asyncio
    products = asyncio.run(_load_products())
    print(f"加载 {len(products)} 个商品")

    # 生成文档
    documents = _build_documents(products)
    print(f"生成 {len(documents)} 篇知识文档")

    # 文本切分
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    print(f"切分为 {len(chunks)} 个文本块")

    # 构建 Chroma 索引
    embeddings = make_embeddings()
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_PERSIST_DIR,
    )
    print(f"Chroma 索引已保存到：{CHROMA_PERSIST_DIR}")

    return vectorstore


def get_product_retriever(k: int = 3):
    """
    获取商品知识库检索器

    Args:
        k: 返回top-k文档

    Returns:
        配置好的检索器（langchain retriever）
    """
    persist_path = Path(CHROMA_PERSIST_DIR)

    if not persist_path.exists() or not any(persist_path.iterdir()):
        raise FileNotFoundError(
            f"Chroma 索引不存在：{CHROMA_PERSIST_DIR}\n请先运行 build_product_knowledge_base()"
        )

    embeddings = make_embeddings()
    vectorstore = Chroma(
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=embeddings,
    )

    return vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


def search_product_knowledge(query: str, k: int = 3) -> str:
    """
    搜索商品知识库（供 @tool 直接调用）

    Args:
        query: 搜索查询
        k: 返回结果数

    Returns:
        格式化的搜索结果文本
    """
    retriever = get_product_retriever(k=k)
    docs = retriever.invoke(query)

    if not docs:
        return f"未找到关于「{query}」的相关商品知识。"

    lines = []
    for i, doc in enumerate(docs, 1):
        name = doc.metadata.get("product_name", "未知商品")
        category = doc.metadata.get("category", "")
        price = doc.metadata.get("price", 0)
        stock = doc.metadata.get("stock", 0)
        content = doc.page_content[:300]

        lines.append(
            f"[{i}] {name}（{category}，¥{price}，库存{stock}）\n{content}"
        )

    return "\n\n---\n\n".join(lines)


# ── 模块加载时自动初始化 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    build_product_knowledge_base(force=True)
    print("\n测试检索：")
    result = search_product_knowledge("降噪耳机推荐")
    print(result)
