"""SQLAlchemy model for the ``orders`` table."""

import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Order(Base):
    """An order header (one per Order ID).

    Carries order/shipment attributes shared by all of its line items —
    dates, ship mode, the customer, and the ship-to geography (Region etc.).
    """

    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(primary_key=True)
    order_date: Mapped[datetime.date]
    ship_date: Mapped[datetime.date]
    ship_mode: Mapped[str]
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    country: Mapped[str]
    city: Mapped[str]
    state: Mapped[str]
    postal_code: Mapped[str]
    region: Mapped[str]
