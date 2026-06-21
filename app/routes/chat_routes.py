"""FastAPI chat router — submit-question endpoint.

``ChatRouter`` exposes ``POST /api/chat`` and delegates entirely to
``ChatService``. No business logic lives here (SDS §9.3 / AGENTS.md §5).
The router is instantiated with a ``ChatService`` dependency in
``app.starter.create_app()`` and registered on the ``FastAPI`` application.
"""

from fastapi import APIRouter

from app.config.log_config import get_logger
from app.schemas.requests import AnalyticsRequest
from app.schemas.responses import AnalyticsResponse
from app.services.chat_service import ChatService

logger = get_logger(__name__)


class ChatRouter:
    """Class-based router that wraps the ``/api/chat`` endpoint.

    Accepts ``ChatService`` via constructor injection so the route handler
    stays dependency-free and fully testable without spinning up the full app.

    Attributes:
        router: The FastAPI ``APIRouter`` to include in the application.
    """

    def __init__(self, chat_service: ChatService) -> None:
        """Register the submit-question route against the injected service.

        Args:
            chat_service: The singleton ``ChatService`` built at startup.
        """
        self._chat_service = chat_service
        self.router = APIRouter(prefix="/api", tags=["chat"])
        self.router.add_api_route(
            "/chat",
            self.submit_question,
            methods=["POST"],
            response_model=AnalyticsResponse,
        )

    async def submit_question(self, request: AnalyticsRequest) -> AnalyticsResponse:
        """Accept a question and return the analytics response.

        Delegates entirely to ``ChatService.ask()``; contains no business logic.

        Args:
            request: The validated ``AnalyticsRequest`` payload.

        Returns:
            The ``AnalyticsResponse`` produced by the Chat Service.
        """
        logger.info("POST /api/chat session=%s", request.session_uuid)
        return await self._chat_service.ask(request)
