"""SQLAlchemy model for the ``customers`` table."""

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Customer(Base):
    """A customer. Derived from the Customer ID/Name/Segment CSV columns."""

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(primary_key=True)
    customer_name: Mapped[str]
    segment: Mapped[str]
