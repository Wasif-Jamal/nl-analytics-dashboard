"""SQLAlchemy model for the ``products`` table."""

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Product(Base):
    """A product. Derived from the Product ID/Category/Sub-Category/Name CSV columns."""

    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(primary_key=True)
    category: Mapped[str]
    sub_category: Mapped[str]
    product_name: Mapped[str]
