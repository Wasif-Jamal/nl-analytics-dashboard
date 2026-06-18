"""Application bootstrap / app factory.

Builds the FastAPI application: initializes the database (creates tables and
loads the source CSV once) and returns the configured app. ``app/main.py``
exposes the result as the ASGI entry point for Uvicorn.
"""

from fastapi import FastAPI

from app.config.log_config import get_logger
from app.utils.database_initializer import DatabaseInitializer

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Initialize the database, then build and return the FastAPI app."""
    logger.info("Bootstrapping application — initializing database")
    DatabaseInitializer().initialize()

    app = FastAPI(title="Natural Language Analytics Dashboard API")
    # Routers from app.routes (chat_routes, health) are included here as they land.
    return app
