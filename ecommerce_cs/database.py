"""
database.py — PostgreSQL 异步连接 + SQLAlchemy ORM 模型 + CRUD 工具函数

表结构：
  User           — 用户
  Product        — 商品
  Order          — 订单
  OrderItem      — 订单明细
  ReturnRequest  — 退换货申请
  FAQ            — 常见问题
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import enum

from config import DB_URL, DB_URL_SYNC


# ── 枚举 ────────────────────────────────────────────────────────────────────────
class OrderStatus(str, enum.Enum):
    PENDING = "待付款"
    SHIPPED = "已发货"
    COMPLETED = "已完成"
    CANCELLED = "已取消"


class ReturnType(str, enum.Enum):
    RETURN = "退货"
    EXCHANGE = "换货"
    REFUND = "退款"


class ReturnStatus(str, enum.Enum):
    PENDING = "待审核"
    APPROVED = "已通过"
    REJECTED = "已拒绝"
    COMPLETED = "已完成"


# ── ORM 基类 ────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── 模型定义 ────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    orders = relationship("Order", back_populates="user", lazy="selectin")
    returns = relationship("ReturnRequest", back_populates="user", lazy="selectin")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    specs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False
    )
    total: Mapped[float] = mapped_column(Float, nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    tracking_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", lazy="selectin")


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    type: Mapped[ReturnType] = mapped_column(SAEnum(ReturnType), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReturnStatus] = mapped_column(
        SAEnum(ReturnStatus), default=ReturnStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    order = relationship("Order", lazy="selectin")
    user = relationship("User", back_populates="returns")


class FAQ(Base):
    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(300), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)


# ── 异步引擎 & 会话工厂 ─────────────────────────────────────────────────────────
# ── 异步引擎（供 FastAPI 用）───────────────────────────────────────────────────
async_engine = create_async_engine(DB_URL, echo=False, pool_size=10, max_overflow=5)
async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)


# ── 同步引擎（供 @tool 函数用，LangChain 工具是同步的）────────────────────────
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.orm import Session as SyncSession, sessionmaker as sync_sessionmaker

sync_engine = create_sync_engine(DB_URL_SYNC, echo=False, pool_size=5, max_overflow=5)
SyncSessionFactory = sync_sessionmaker(sync_engine, expire_on_commit=False)


async def init_db():
    """创建所有表"""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库表已创建。")


# ── 同步 CRUD 函数（供 tools/ 层 @tool 直接调用）────────────────────────────

def find_user_by_phone(phone: str) -> Optional[User]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()


def find_orders_by_user(user_id: int) -> List[Order]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())


def find_order_by_no(order_no: str) -> Optional[Order]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(select(Order).where(Order.order_no == order_no))
        return result.scalar_one_or_none()


def search_products_db(keyword: str, limit: int = 5) -> List[Product]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(
            select(Product)
            .where(
                Product.name.ilike(f"%{keyword}%")
                | Product.description.ilike(f"%{keyword}%")
                | Product.category.ilike(f"%{keyword}%")
            )
            .limit(limit)
        )
        return list(result.scalars().all())


def get_product_by_id(product_id: int) -> Optional[Product]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()


def search_faqs_db(query: str, limit: int = 5) -> List[FAQ]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(
            select(FAQ)
            .where(
                FAQ.question.ilike(f"%{query}%")
                | FAQ.answer.ilike(f"%{query}%")
                | FAQ.category.ilike(f"%{query}%")
            )
            .limit(limit)
        )
        return list(result.scalars().all())


def get_faq_categories_sync() -> List[str]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(select(FAQ.category).distinct())
        return list(result.scalars().all())


def create_return_request_sync(
    order_id: int, user_id: int, return_type: str, reason: str
) -> ReturnRequest:
    with SyncSessionFactory() as db:
        import random
        req = ReturnRequest(
            return_no=f"RTN{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(10, 99)}",
            order_id=order_id,
            user_id=user_id,
            type=ReturnType(return_type),
            reason=reason,
            status=ReturnStatus.PENDING,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req


def find_return_by_no(return_no: str) -> Optional[ReturnRequest]:
    with SyncSessionFactory() as db:
        from sqlalchemy import select
        result = db.execute(
            select(ReturnRequest).where(ReturnRequest.return_no == return_no)
        )
        return result.scalar_one_or_none()


# ── 异步 CRUD 函数（供 rag.py / FastAPI 后台任务使用）─────────────────────

async def _load_products_async() -> List[Product]:
    async with async_session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(select(Product))
        return list(result.scalars().all())
