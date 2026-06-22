"""Tests for app.config.log_config."""

import logging

from app.config.log_config import config as log_config


def test_returns_named_logger():
    """get_logger returns a logging.Logger carrying the requested name."""
    logger = log_config.get_logger("test.module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_same_name_returns_same_instance():
    """Logging caches loggers by name, so repeated calls return one instance."""
    assert log_config.get_logger("dup") is log_config.get_logger("dup")


def test_logging_call_does_not_raise():
    """A configured logger can emit without raising."""
    log_config.get_logger("emit").info("hello %s", "world")
