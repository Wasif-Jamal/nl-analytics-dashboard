"""Database initialization and one-time CSV load.

On startup this creates the schema (from the SQLAlchemy models) and loads the
source CSV (``settings.csv_path``) into the normalized tables exactly once —
only when the database is empty. The wide, denormalized Superstore CSV is split
into ``customers``, ``products``, ``orders``, and ``order_items``.
"""

import pandas as pd
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config.db_config import engine
from app.config.env_config import settings
from app.config.log_config import get_logger
from app.models import Base, Customer, Order, OrderItem, Product

logger = get_logger(__name__)

# CSV column -> model field, per normalized table.
_CUSTOMER_COLS = {
    "Customer ID": "customer_id",
    "Customer Name": "customer_name",
    "Segment": "segment",
}
_PRODUCT_COLS = {
    "Product ID": "product_id",
    "Category": "category",
    "Sub-Category": "sub_category",
    "Product Name": "product_name",
}
_ORDER_COLS = {
    "Order ID": "order_id",
    "Order Date": "order_date",
    "Ship Date": "ship_date",
    "Ship Mode": "ship_mode",
    "Customer ID": "customer_id",
    "Country": "country",
    "City": "city",
    "State": "state",
    "Postal Code": "postal_code",
    "Region": "region",
}
_ORDER_ITEM_COLS = {
    "Row ID": "row_id",
    "Order ID": "order_id",
    "Product ID": "product_id",
    "Sales": "sales",
    "Quantity": "quantity",
    "Discount": "discount",
    "Profit": "profit",
}


class DatabaseInitializer:
    """Creates the schema and loads the source CSV once, if the DB is empty."""

    def __init__(self, db_engine: Engine = engine, csv_path: str | None = None) -> None:
        """Configure the initializer.

        Args:
            db_engine: SQLAlchemy engine to create tables / load data against.
            csv_path: Override for the source CSV path (defaults to settings).
        """
        self._engine = db_engine
        self._session_factory = sessionmaker(
            bind=db_engine, autoflush=False, expire_on_commit=False
        )
        self._csv_path = csv_path or settings.csv_path

    def initialize(self) -> None:
        """Create tables, then load the CSV only when no data is present."""
        Base.metadata.create_all(self._engine)
        with self._session_factory() as session:
            if session.scalar(select(OrderItem).limit(1)) is not None:
                logger.info("Database already populated — skipping CSV load")
                return
            logger.info("Empty database detected — loading %s", self._csv_path)
            self._load_csv(session)

    def _load_csv(self, session: Session) -> None:
        """Read, normalize, and insert the CSV into the four tables."""
        frame = self._read_csv()

        customers = (
            frame[list(_CUSTOMER_COLS)]
            .drop_duplicates("Customer ID")
            .rename(columns=_CUSTOMER_COLS)
        )
        products = (
            frame[list(_PRODUCT_COLS)]
            .drop_duplicates("Product ID")
            .rename(columns=_PRODUCT_COLS)
        )
        orders = (
            frame[list(_ORDER_COLS)]
            .drop_duplicates("Order ID")
            .rename(columns=_ORDER_COLS)
        )
        order_items = frame[list(_ORDER_ITEM_COLS)].rename(columns=_ORDER_ITEM_COLS)

        # Insert dimensions before facts so foreign keys resolve.
        session.bulk_insert_mappings(Customer, customers.to_dict("records"))
        session.bulk_insert_mappings(Product, products.to_dict("records"))
        session.bulk_insert_mappings(Order, orders.to_dict("records"))
        session.bulk_insert_mappings(OrderItem, order_items.to_dict("records"))
        session.commit()

        logger.info(
            "Loaded %d customers, %d products, %d orders, %d order items",
            len(customers),
            len(products),
            len(orders),
            len(order_items),
        )

    def _read_csv(self) -> pd.DataFrame:
        """Read the CSV with correct dtypes and parsed dates."""
        frame = pd.read_csv(
            self._csv_path,
            dtype={"Postal Code": str},
            encoding="latin-1",
        )
        # Superstore dates are M/D/YYYY; store as Python dates.
        frame["Order Date"] = pd.to_datetime(
            frame["Order Date"], format="%m/%d/%Y"
        ).dt.date
        frame["Ship Date"] = pd.to_datetime(
            frame["Ship Date"], format="%m/%d/%Y"
        ).dt.date
        return frame
