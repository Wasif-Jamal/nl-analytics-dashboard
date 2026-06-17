"""Tests for app.repositories.query_repository.QueryRepository."""

import pandas as pd
from sqlalchemy import Engine

from app.repositories.query_repository import QueryRepository


def test_execute_select_returns_dataframe(initialized_engine: Engine):
    """A SELECT returns a DataFrame with the expected rows and columns."""
    repo = QueryRepository(db_engine=initialized_engine)
    result = repo.execute_select("SELECT * FROM customers")
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    assert {"customer_id", "customer_name", "segment"} <= set(result.columns)


def test_aggregation_join_query(initialized_engine: Engine):
    """A grouped join over the fact/dimension tables aggregates correctly."""
    repo = QueryRepository(db_engine=initialized_engine)
    result = repo.execute_select(
        "SELECT o.region, ROUND(SUM(oi.sales), 2) AS revenue "
        "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id "
        "GROUP BY o.region"
    )
    revenue = dict(zip(result["region"], result["revenue"]))
    assert revenue["South"] == 1093.9  # 261.96 + 731.94 + 100.0
    assert revenue["East"] == 14.62


def test_empty_result_returns_empty_dataframe(initialized_engine: Engine):
    """A query matching no rows returns an empty DataFrame (columns intact)."""
    repo = QueryRepository(db_engine=initialized_engine)
    result = repo.execute_select(
        "SELECT * FROM customers WHERE customer_id = 'MISSING'"
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
    assert "customer_id" in result.columns
