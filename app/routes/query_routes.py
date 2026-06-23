"""FastAPI query router — execute-query endpoint.

``QueryRouter`` exposes ``POST /api/query`` and delegates entirely to
``QueryService``. Validates that the submitted SQL is a read-only SELECT before
execution. No business logic beyond validation lives here (AGENTS.md §5).
"""

from fastapi import APIRouter, HTTPException

from app.config.log_config import config as log_config
from app.schemas.requests import QueryRequest
from app.schemas.responses import QueryResponse
from app.services.sql_service import QueryService
from app.utils.validators import validate_select_only

logger = log_config.get_logger(__name__)


class QueryRouter:
    """Class-based router that wraps the ``/api/query`` endpoint.

    Accepts ``QueryService`` via constructor injection so the route handler
    stays dependency-free and fully testable without spinning up the full app.

    Attributes:
        router: The FastAPI ``APIRouter`` to include in the application.
    """

    def __init__(self, query_service: QueryService) -> None:
        """Register the execute-query route against the injected service.

        Args:
            query_service: The singleton ``QueryService`` built at startup.
        """
        self._query_service = query_service
        self.router = APIRouter(prefix="/api", tags=["query"])
        self.router.add_api_route(
            "/query",
            self.execute_query,
            methods=["POST"],
            response_model=QueryResponse,
        )

    async def execute_query(self, request: QueryRequest) -> QueryResponse:
        """Validate and execute a SELECT query, returning its result set.

        Rejects non-SELECT SQL with HTTP 400 before delegating to the service.
        No business logic beyond validation lives in this handler.

        Args:
            request: The validated ``QueryRequest`` payload containing the SQL.

        Returns:
            A ``QueryResponse`` with columns, rows, and row count.

        Raises:
            HTTPException: 400 if the SQL fails read-only validation.
        """
        logger.info("POST /api/query sql_length=%d", len(request.sql))
        if not validate_select_only(request.sql):
            logger.warning("POST /api/query rejected non-SELECT SQL")
            raise HTTPException(
                status_code=400, detail="Generated query could not be validated."
            )
        result = self._query_service.run_query(request.sql)
        return QueryResponse(
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
        )
