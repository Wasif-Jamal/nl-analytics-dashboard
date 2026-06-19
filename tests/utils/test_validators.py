"""Tests for app.utils.validators.validate_select_only.

Covers spec scenarios under the ``read-only-validation`` requirement: SELECT and
CTE pass; write/DDL statements, lowercase variants, mixed multi-statement input,
and unparseable SQL are all rejected.
"""

import pytest

from app.utils.validators import validate_select_only


def test_plain_select_passes():
    """A plain SELECT is read-only."""
    assert validate_select_only("SELECT customer_id FROM customers") is True


def test_cte_select_passes():
    """A CTE that ultimately selects is read-only (parses to a Select)."""
    sql = "WITH c AS (SELECT sales FROM order_items) SELECT SUM(sales) FROM c"
    assert validate_select_only(sql) is True


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO customers VALUES ('X', 'Y', 'Consumer')",
        "UPDATE customers SET segment = 'Consumer'",
        "DELETE FROM customers",
        "DROP TABLE customers",
        "ALTER TABLE customers ADD COLUMN x TEXT",
        "TRUNCATE TABLE customers",
    ],
)
def test_write_and_ddl_statements_blocked(sql: str):
    """Each write/DDL statement type is rejected."""
    assert validate_select_only(sql) is False


def test_lowercase_write_blocked():
    """Validation is case-insensitive (AST-based), so lowercase writes are blocked."""
    assert validate_select_only("insert into customers values ('a','b','c')") is False


def test_multi_statement_with_non_select_blocked():
    """A SELECT followed by a DDL statement is rejected as a whole."""
    assert validate_select_only("SELECT 1; DROP TABLE customers") is False


def test_malformed_sql_blocked():
    """Unparseable SQL fails closed (returns False)."""
    assert validate_select_only("SELEKT bad sql ;;") is False
