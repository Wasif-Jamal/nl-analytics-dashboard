"""Centralized logging configuration.

Provides :func:`get_logger`, the single sanctioned way to obtain a logger
across the application. Modules must use this rather than ``print`` or
ad-hoc logging setup.
"""

import logging

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def _configure_root() -> None:
    """Attach a stream handler and level to the root logger exactly once."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger configured with the shared format and level.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A ``logging.Logger`` ready for use.
    """
    _configure_root()
    return logging.getLogger(name)
