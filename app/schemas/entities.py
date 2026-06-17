"""Pydantic contracts mirroring the database entities.

Typed, read-only representations of rows from the ``customers``, ``products``,
``orders``, and ``order_items`` tables. ``from_attributes`` is enabled so these
can be built directly from the SQLAlchemy model instances in ``app.models``.
"""

import datetime

from pydantic import BaseModel, ConfigDict


class CustomerSchema(BaseModel):
    """A customer row (mirrors ``app.models.customer.Customer``)."""

    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    customer_name: str
    segment: str


class ProductSchema(BaseModel):
    """A product row (mirrors ``app.models.product.Product``)."""

    model_config = ConfigDict(from_attributes=True)

    product_id: str
    category: str
    sub_category: str
    product_name: str


class OrderSchema(BaseModel):
    """An order header row (mirrors ``app.models.order.Order``)."""

    model_config = ConfigDict(from_attributes=True)

    order_id: str
    order_date: datetime.date
    ship_date: datetime.date
    ship_mode: str
    customer_id: str
    country: str
    city: str
    state: str
    postal_code: str
    region: str


class OrderItemSchema(BaseModel):
    """An order line row (mirrors ``app.models.order_item.OrderItem``)."""

    model_config = ConfigDict(from_attributes=True)

    row_id: int
    order_id: str
    product_id: str
    sales: float
    quantity: int
    discount: float
    profit: float
