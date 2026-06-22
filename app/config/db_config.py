"""SQLite configuration: SQLAlchemy engine and session management."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.env_config import settings
from app.config.log_config import config as log_config

logger = log_config.get_logger(__name__)


class DbConfig:
    """Builds the SQLAlchemy engine and session factory from application settings.

    Reads the database URL from :data:`app.config.env_config.settings`.
    Contains no business logic.
    """

    def __init__(self) -> None:
        # check_same_thread=False so the engine is usable across FastAPI worker threads.
        self.engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.session_local = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False
        )
        logger.info("SQLAlchemy engine created for %s", self.engine.url)

    def get_session(self) -> Iterator[Session]:
        """Yield a database session, closing it afterwards (FastAPI dependency)."""
        session = self.session_local()
        try:
            yield session
        finally:
            session.close()


config = DbConfig()
