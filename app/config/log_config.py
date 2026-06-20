"""Centralized logging configuration.

Provides :func:`get_logger`, the single sanctioned way to obtain a logger
across the application. Modules must use this rather than ``print`` or
ad-hoc logging setup.
"""

import logging

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False

# Third-party namespaces whose Python log level is lowered when verbose/debug is on.
_LANGCHAIN_NAMESPACES = (
    "langchain",
    "langchain_core",
    "langchain_google_genai",
    "langgraph",
)


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


def configure_langchain_logging(verbose: bool = False, debug: bool = False) -> None:
    """Lower the Python log level for LangChain/LangGraph namespaces.

    ``set_verbose`` and ``set_debug`` gate LangChain's callback-based stdout
    output, but internal agent/tool messages in ``langchain*`` and ``langgraph*``
    packages are emitted via Python's ``logging`` module at DEBUG level.  Without
    this call the root logger's INFO gate silences them.

    Call this once at startup after reading env settings.

    Args:
        verbose: When True, sets LangChain/LangGraph loggers to INFO so
            chain-step inputs/outputs appear in the shared log stream.
        debug: When True, sets them to DEBUG so full message payloads and
            tool call/response details are shown.
    """
    _configure_root()
    if not verbose and not debug:
        return
    level = logging.DEBUG if debug else logging.INFO
    for ns in _LANGCHAIN_NAMESPACES:
        logging.getLogger(ns).setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger configured with the shared format and level.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A ``logging.Logger`` ready for use.
    """
    _configure_root()
    return logging.getLogger(name)
