"""SQLite configuration: SQLAlchemy engine and session management.

Builds the engine from :data:`app.config.env_config.settings` and exposes a
session factory. Contains no business logic.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.env_config import settings
from app.config.log_config import get_logger

logger = get_logger(__name__)

# check_same_thread=False so the engine is usable across FastAPI worker threads.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)
logger.info("SQLAlchemy engine created for %s", engine.url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield a database session, closing it afterwards (FastAPI dependency)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
