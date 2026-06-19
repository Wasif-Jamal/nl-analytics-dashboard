"""Repository for executing read-only SQL queries.

Thin data-access layer: executes already-validated ``SELECT`` statements and
returns a :class:`~app.schemas.sql_result.QueryResult`. Contains no business
logic — query generation and validation happen upstream (SQL agent). SQLAlchemy
errors are allowed to propagate so the caller can classify them.
"""

import pandas as pd
from sqlalchemy import Engine, text

from app.config.db_config import engine
from app.config.log_config import get_logger
from app.schemas.sql_result import QueryResult

logger = get_logger(__name__)


class QueryRepository:
    """Executes read-only SQL against the database and returns ``QueryResult``."""

    def __init__(self, db_engine: Engine = engine) -> None:
        """Store the SQLAlchemy engine (defaults to the shared app engine)."""
        self._engine = db_engine

    def execute_select(self, sql: str) -> QueryResult:
        """Execute a validated ``SELECT`` statement and return its result.

        Args:
            sql: A read-only ``SELECT`` query, already validated upstream.

        Returns:
            A :class:`QueryResult` wrapping the result DataFrame, its column
            names, and the row count (an empty DataFrame yields ``row_count=0``).
        """
        logger.info("Executing query")
        with self._engine.connect() as connection:
            dataframe = pd.read_sql(text(sql), connection)
        return QueryResult(
            dataframe=dataframe,
            columns=list(dataframe.columns),
            row_count=len(dataframe),
        )
