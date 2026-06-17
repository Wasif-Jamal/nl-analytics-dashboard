"""SQLAlchemy model for the ``order_items`` table."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrderItem(Base):
    """A single order line (one per CSV Row ID) — the fact table.

    Links an order to a product and holds the per-line measures.
    """

    __tablename__ = "order_items"

    row_id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"))
    sales: Mapped[float]
    quantity: Mapped[int]
    discount: Mapped[float]
    profit: Mapped[float]
