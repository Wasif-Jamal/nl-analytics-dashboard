"""SQL execution service.

``QueryService`` is the business-logic intermediary between the SQL agent's
``execute_sql`` tool and the data-access layer. It enforces the call chain
``execute_sql -> POST /api/query -> QueryService -> QueryRepository -> SQLite``
(SDS §9.2): the repository is never invoked directly by agents or routes.
This service stays independent of LangGraph.
"""

from app.config.log_config import config as log_config
from app.repositories.query_repository import QueryRepository
from app.schemas.sql_result import QueryResult

logger = log_config.get_logger(__name__)


class QueryService:
    """Runs validated read-only SQL by delegating to the repository."""

    def __init__(self, repository: QueryRepository | None = None) -> None:
        """Store the repository dependency (defaults to a new ``QueryRepository``).

        Args:
            repository: The data-access repository; injected for testability.
        """
        self._repository = repository or QueryRepository()

    def run_query(self, sql: str) -> QueryResult:
        """Execute an already-validated ``SELECT`` and return its result.

        Args:
            sql: A read-only ``SELECT`` query, validated upstream by the tool.

        Returns:
            The :class:`QueryResult` produced by the repository.
        """
        logger.info("Running validated query (%d chars) through repository", len(sql))
        return self._repository.execute_select(sql)
