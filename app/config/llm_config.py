"""LLM client initialization for the Gemini provider.

Provides :func:`get_llm`, the single sanctioned way to obtain a configured
``ChatGoogleGenerativeAI`` instance. Import this function; never instantiate
the LLM directly in agent or node code.
"""

from langchain_core.globals import set_debug, set_verbose
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.env_config import settings
from app.config.log_config import get_logger

logger = get_logger(__name__)


class LlmConfig:
    """Factory for the application LLM client.

    Reads model and temperature from :data:`app.config.env_config.settings`
    so both can be overridden via environment variables without code changes.
    """

    def get_llm(self) -> ChatGoogleGenerativeAI:
        """Return a configured ChatGoogleGenerativeAI instance.

        Returns:
            A ``ChatGoogleGenerativeAI`` client ready for structured-output calls.
        """
        if settings.langchain_verbose:
            set_verbose(True)
            logger.info("LangChain verbose mode enabled")
        if settings.langchain_debug:
            set_debug(True)
            logger.info("LangChain debug mode enabled")
        logger.info(
            "Initializing LLM: model=%s temperature=%s",
            settings.llm_model,
            settings.llm_temperature,
        )
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            google_api_key=settings.google_api_key,
        )


_config = LlmConfig()


def get_llm() -> ChatGoogleGenerativeAI:
    """Return a configured LLM instance (module-level convenience wrapper).

    Returns:
        A ``ChatGoogleGenerativeAI`` client from the shared :class:`LlmConfig`.
    """
    return _config.get_llm()
