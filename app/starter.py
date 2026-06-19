"""Application bootstrap / app factory.

Builds the FastAPI application: initializes the database, constructs the
analytics workflow (``AnalyticsGraph``) and ``ChatService`` as startup
singletons, registers the API routers, and returns the configured app.
``app/main.py`` exposes the result as the ASGI entry point for Uvicorn.
"""

from fastapi import FastAPI

from app.config.llm_config import get_llm
from app.config.log_config import get_logger
from app.orchestration.graph import AnalyticsGraph
from app.routes.chat_routes import ChatRouter
from app.routes.health import router as health_router
from app.services.chat_service import ChatService
from app.services.sql_service import QueryService
from app.utils.database_initializer import DatabaseInitializer

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Initialize the database, build the workflow singleton, and return the app.

    Startup sequence:
    1. ``DatabaseInitializer`` creates tables and loads the CSV once.
    2. ``AnalyticsGraph`` is compiled once (expensive; shared for all requests).
    3. ``ChatService`` wraps the graph (manages session history).
    4. Both API routers are registered on the ``FastAPI`` application.

    Returns:
        The fully configured ``FastAPI`` ASGI application.
    """
    logger.info("Bootstrapping application — initializing database")
    DatabaseInitializer().initialize()

    app = FastAPI(title="Natural Language Analytics Dashboard API")

    llm = get_llm()
    query_service = QueryService()
    graph = AnalyticsGraph(llm, query_service).build()
    chat_service = ChatService(graph)

    app.include_router(ChatRouter(chat_service).router)
    app.include_router(health_router)

    logger.info("Application startup complete")
    return app
