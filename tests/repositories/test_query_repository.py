"""Tests for app.repositories.query_repository.QueryRepository."""

import pandas as pd
from sqlalchemy import Engine

from app.repositories.query_repository import QueryRepository
from app.schemas.sql_result import QueryResult


def test_execute_select_returns_query_result(initialized_engine: Engine):
    """A SELECT returns a QueryResult wrapping the rows, columns, and count."""
    repo = QueryRepository(db_engine=initialized_engine)
    result = repo.execute_select("SELECT * FROM customers")
    assert isinstance(result, QueryResult)
    assert isinstance(result.dataframe, pd.DataFrame)
    assert result.row_count == 2
    assert result.columns == ["customer_id", "customer_name", "segment"]


def test_aggregation_join_query(initialized_engine: Engine):
    """A grouped join over the fact/dimension tables aggregates correctly."""
    repo = QueryRepository(db_engine=initialized_engine)
    result = repo.execute_select(
        "SELECT o.region, ROUND(SUM(oi.sales), 2) AS revenue "
        "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id "
        "GROUP BY o.region"
    )
    revenue = dict(zip(result.dataframe["region"], result.dataframe["revenue"]))
    assert revenue["South"] == 1093.9  # 261.96 + 731.94 + 100.0
    assert revenue["East"] == 14.62


def test_empty_result_returns_zero_rows(initialized_engine: Engine):
    """A query matching no rows yields row_count 0 with columns intact."""
    repo = QueryRepository(db_engine=initialized_engine)
    result = repo.execute_select(
        "SELECT * FROM customers WHERE customer_id = 'MISSING'"
    )
    assert isinstance(result, QueryResult)
    assert result.row_count == 0
    assert "customer_id" in result.columns
