"""Repository for executing read-only SQL queries.

Thin data-access layer: executes already-validated ``SELECT`` statements and
returns results as a pandas DataFrame. Contains no business logic — query
generation and validation happen upstream (SQL agent / validation node).
"""

import pandas as pd
from sqlalchemy import Engine, text

from app.config.db_config import engine
from app.config.log_config import get_logger

logger = get_logger(__name__)


class QueryRepository:
    """Executes read-only SQL against the database and returns DataFrames."""

    def __init__(self, db_engine: Engine = engine) -> None:
        """Store the SQLAlchemy engine (defaults to the shared app engine)."""
        self._engine = db_engine

    def execute_select(self, sql: str) -> pd.DataFrame:
        """Execute a validated ``SELECT`` statement and return the rows.

        Args:
            sql: A read-only ``SELECT`` query, already validated upstream.

        Returns:
            A DataFrame of the result set (empty if no rows match).
        """
        logger.info("Executing query")
        with self._engine.connect() as connection:
            return pd.read_sql(text(sql), connection)
