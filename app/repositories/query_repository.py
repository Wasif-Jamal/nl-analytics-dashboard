"""Repository for executing read-only SQL queries.

Thin data-access layer: executes already-validated ``SELECT`` statements and
returns a :class:`~app.schemas.sql_result.QueryResult`. Contains no business
logic — query generation and validation happen upstream (SQL agent). SQLAlchemy
errors are allowed to propagate so the caller can classify them.
"""

from sqlalchemy import Engine, text

from app.config.db_config import config as db_config
from app.config.log_config import config as log_config
from app.schemas.sql_result import QueryResult

logger = log_config.get_logger(__name__)


class QueryRepository:
    """Executes read-only SQL against the database and returns ``QueryResult``."""

    def __init__(self, db_engine: Engine = db_config.engine) -> None:
        """Store the SQLAlchemy engine (defaults to the shared app engine)."""
        self._engine = db_engine

    def execute_select(self, sql: str) -> QueryResult:
        """Execute a validated ``SELECT`` statement and return its result.

        Args:
            sql: A read-only ``SELECT`` query, already validated upstream.

        Returns:
            A :class:`QueryResult` with rows as ``list[dict]``, column names,
            and the row count (an empty result yields ``row_count=0``).
        """
        logger.info("Executing query (%d chars)", len(sql))
        with self._engine.connect() as connection:
            cursor = connection.execute(text(sql))
            columns = list(cursor.keys())
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        result = QueryResult(rows=rows, columns=columns, row_count=len(rows))
        logger.info(
            "Query complete: %d row(s), columns=%s", result.row_count, result.columns
        )
        return result
