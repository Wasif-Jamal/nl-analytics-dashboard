"""Tests for app.utils.database_initializer.DatabaseInitializer.

Exercises the normalized CSV load: row counts, de-duplication, dtype/date
handling, foreign-key integrity, and one-time (idempotent) loading. Each test
runs against an isolated temp engine (see ``tests/conftest.py``).
"""

import datetime

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.models import Order
from app.repositories.query_repository import QueryRepository
from app.utils.database_initializer import DatabaseInitializer
from tests.conftest import EXPECTED_COUNTS


def _counts(engine: Engine) -> dict[str, int]:
    """Return row counts per table using the query repository."""
    repo = QueryRepository(db_engine=engine)
    return {
        table: int(
            repo.execute_select(f"SELECT COUNT(*) AS n FROM {table}").rows[0]["n"]
        )
        for table in EXPECTED_COUNTS
    }


def test_loads_normalized_counts(initialized_engine: Engine):
    """The CSV is split into the four tables with the expected row counts."""
    assert _counts(initialized_engine) == EXPECTED_COUNTS


def test_dedup_keeps_one_row_per_key(initialized_engine: Engine):
    """Repeated product/customer keys collapse to a single dimension row."""
    repo = QueryRepository(db_engine=initialized_engine)
    products = repo.execute_select(
        "SELECT product_id FROM products WHERE product_id = 'FUR-BO-1'"
    )
    customers = repo.execute_select(
        "SELECT customer_id FROM customers WHERE customer_id = 'CG-1'"
    )
    assert products.row_count == 1
    assert customers.row_count == 1


def test_postal_code_leading_zero_preserved(initialized_engine: Engine):
    """Postal codes are stored as strings (leading zeros intact)."""
    repo = QueryRepository(db_engine=initialized_engine)
    row = repo.execute_select(
        "SELECT postal_code FROM orders WHERE order_id = 'CA-2016-2'"
    )
    assert row.rows[0]["postal_code"] == "06010"


def test_dates_stored_as_dates(initialized_engine: Engine):
    """Order/ship dates are parsed and stored as real date values."""
    session = sessionmaker(bind=initialized_engine)()
    try:
        order = session.get(Order, "CA-2016-1")
        assert order.order_date == datetime.date(2016, 11, 8)
        assert order.ship_date == datetime.date(2016, 11, 11)
    finally:
        session.close()


def test_foreign_key_integrity(initialized_engine: Engine):
    """Every order item references an existing order and product."""
    repo = QueryRepository(db_engine=initialized_engine)
    orphan_orders = repo.execute_select(
        "SELECT COUNT(*) AS n FROM order_items oi "
        "LEFT JOIN orders o ON oi.order_id = o.order_id WHERE o.order_id IS NULL"
    )
    orphan_products = repo.execute_select(
        "SELECT COUNT(*) AS n FROM order_items oi "
        "LEFT JOIN products p ON oi.product_id = p.product_id WHERE p.product_id IS NULL"
    )
    assert int(orphan_orders.rows[0]["n"]) == 0
    assert int(orphan_products.rows[0]["n"]) == 0


def test_load_is_idempotent(initialized_engine: Engine, sample_csv: str):
    """Re-initializing an already-populated database does not duplicate rows."""
    DatabaseInitializer(db_engine=initialized_engine, csv_path=sample_csv).initialize()
    assert _counts(initialized_engine) == EXPECTED_COUNTS
