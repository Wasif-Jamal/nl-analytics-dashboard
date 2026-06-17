"""SQLAlchemy models package.

Re-exports the declarative ``Base`` and all model classes so that importing
``app.models`` registers every table on ``Base.metadata``.
"""

from app.models.base import Base
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product

__all__ = ["Base", "Customer", "Order", "OrderItem", "Product"]
