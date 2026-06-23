"""Centralized logging configuration."""

import logging
import logging.handlers
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_LOG_DIR = Path(__file__).parent.parent.parent / "logs"

_LANGCHAIN_NAMESPACES = (
    "langchain",
    "langchain_core",
    "langchain_google_genai",
    "langgraph",
)


class LogConfig:
    """Configures the root logger and vends named loggers for the application.

    Ensures the root logger is configured exactly once regardless of how many
    modules call :meth:`get_logger`. Writes to both the console and a
    daily-rotating log file under ``<project_root>/logs/app.log``.
    """

    def __init__(self) -> None:
        self._configured = False

    def _configure_root(self) -> None:
        """Attach console and file handlers to the root logger exactly once."""
        if self._configured:
            return
        formatter = logging.Formatter(_LOG_FORMAT)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            _LOG_DIR / "app.log",
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(console_handler)
            root.addHandler(file_handler)
        root.setLevel(logging.INFO)
        self._configured = True

    def configure_langchain_logging(
        self, verbose: bool = False, debug: bool = False
    ) -> None:
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
        self._configure_root()
        if not verbose and not debug:
            return
        level = logging.DEBUG if debug else logging.INFO
        for ns in _LANGCHAIN_NAMESPACES:
            logging.getLogger(ns).setLevel(level)

    def get_logger(self, name: str) -> logging.Logger:
        """Return a module logger configured with the shared format and level.

        Args:
            name: Typically ``__name__`` of the calling module.

        Returns:
            A ``logging.Logger`` ready for use.
        """
        self._configure_root()
        return logging.getLogger(name)


config = LogConfig()
