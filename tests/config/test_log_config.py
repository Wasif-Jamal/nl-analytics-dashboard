"""Tests for app.config.log_config."""

import logging

from app.config.log_config import get_logger


def test_returns_named_logger():
    """get_logger returns a logging.Logger carrying the requested name."""
    logger = get_logger("test.module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_same_name_returns_same_instance():
    """Logging caches loggers by name, so repeated calls return one instance."""
    assert get_logger("dup") is get_logger("dup")


def test_logging_call_does_not_raise():
    """A configured logger can emit without raising."""
    get_logger("emit").info("hello %s", "world")
