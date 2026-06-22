"""Tests for app.config.db_config."""

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config.db_config import config as db_config


def test_engine_is_sqlite():
    """The shared engine is a SQLite engine."""
    assert isinstance(db_config.engine, Engine)
    assert db_config.engine.url.get_backend_name() == "sqlite"


def test_sessionlocal_is_bound_to_engine():
    """Sessions produced by session_local are bound to the shared engine."""
    session = db_config.session_local()
    try:
        assert session.bind is db_config.engine
    finally:
        session.close()


def test_get_session_yields_a_session_and_closes():
    """get_session yields a Session and closes it when the generator ends."""
    generator = db_config.get_session()
    session = next(generator)
    assert isinstance(session, Session)
    generator.close()  # triggers the finally/close branch
