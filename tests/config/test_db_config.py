"""Tests for app.config.db_config."""

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config.db_config import SessionLocal, engine, get_session


def test_engine_is_sqlite():
    """The shared engine is a SQLite engine."""
    assert isinstance(engine, Engine)
    assert engine.url.get_backend_name() == "sqlite"


def test_sessionlocal_is_bound_to_engine():
    """Sessions produced by SessionLocal are bound to the shared engine."""
    session = SessionLocal()
    try:
        assert session.bind is engine
    finally:
        session.close()


def test_get_session_yields_a_session_and_closes():
    """get_session yields a Session and closes it when the generator ends."""
    generator = get_session()
    session = next(generator)
    assert isinstance(session, Session)
    generator.close()  # triggers the finally/close branch
