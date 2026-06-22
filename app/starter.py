"""Application bootstrap / app factory.

Builds the FastAPI application: initializes the database, constructs the
analytics workflow (``AnalyticsGraph``) and ``ChatService`` as startup
singletons, registers the API routers, and returns the configured app.
``app/main.py`` exposes the result as the ASGI entry point for Uvicorn.
"""

from fastapi import FastAPI

from app.config.llm_config import config as llm_config
from app.config.log_config import config as log_config
from app.orchestration.graph import AnalyticsGraph
from app.routes.chat_routes import ChatRouter
from app.routes.health import router as health_router
from app.routes.query_routes import QueryRouter
from app.services.chat_service import ChatService
from app.services.sql_service import QueryService
from app.utils.database_initializer import DatabaseInitializer

logger = log_config.get_logger(__name__)


def create_app() -> FastAPI:
    """Initialize the database, build the workflow singleton, and return the app.

    Startup sequence:
    1. ``DatabaseInitializer`` creates tables and loads the CSV once.
    2. ``QueryService`` is built and passed to ``QueryRouter`` (``POST /api/query``).
    3. ``AnalyticsGraph`` is compiled once (expensive; shared for all requests).
    4. ``ChatService`` wraps the graph (manages session history).
    5. All API routers are registered on the ``FastAPI`` application.

    Returns:
        The fully configured ``FastAPI`` ASGI application.
    """
    logger.info("Bootstrapping application — initializing database")
    DatabaseInitializer().initialize()

    app = FastAPI(title="Natural Language Analytics Dashboard API")

    logger.info("Creating QueryService")
    query_service = QueryService()
    logger.info("Initializing LLM")
    llm = llm_config.get_llm()
    logger.info("Building analytics supervisor graph")
    graph = AnalyticsGraph(llm).build()
    logger.info("Creating ChatService")
    chat_service = ChatService(graph)

    app.include_router(QueryRouter(query_service).router)
    app.include_router(ChatRouter(chat_service).router)
    app.include_router(health_router)

    logger.info("Application startup complete — ready to serve requests")
    return app
