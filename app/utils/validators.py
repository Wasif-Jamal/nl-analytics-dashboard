"""Read-only SQL validation for the SQL pipeline.

Provides :func:`validate_select_only`, the guard that ``validate_sql`` and
``execute_sql`` (defense-in-depth) apply before any generated SQL reaches the
database (FRS §9, AGENTS.md §9).
Validation is AST-based via ``sqlglot`` — never string/regex matching — so CTEs,
subqueries, and multi-statement input are classified correctly.
"""

import sqlglot
from sqlglot import exp

from app.config.log_config import config as log_config

logger = log_config.get_logger(__name__)


def validate_select_only(sql: str) -> bool:
    """Return whether ``sql`` is a read-only query (``SELECT`` statements only).

    Parses ``sql`` with the SQLite dialect and requires every top-level statement
    to be a ``SELECT`` (a CTE parses to a ``Select`` wrapping its ``WITH`` clause,
    so it passes). Any write/DDL statement (``INSERT``/``UPDATE``/``DELETE``/
    ``DROP``/``ALTER``/``TRUNCATE``), a mix containing one, an empty statement, or
    unparseable SQL all fail.

    Args:
        sql: The candidate SQL string.

    Returns:
        True if the SQL is exclusively ``SELECT``; False otherwise.
    """
    try:
        statements = sqlglot.parse(sql, dialect="sqlite")
    except sqlglot.errors.ParseError:
        logger.warning("SQL validation failed: could not parse statement")
        return False

    real_statements = [stmt for stmt in statements if stmt is not None]
    if not real_statements:
        logger.warning("SQL validation failed: no statement found")
        return False

    if all(isinstance(stmt, exp.Select) for stmt in real_statements):
        logger.debug("SQL validation passed: %d statement(s)", len(real_statements))
        return True

    logger.warning("SQL validation failed: non-SELECT statement detected")
    return False
