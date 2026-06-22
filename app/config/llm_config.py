"""LLM client initialization for the Gemini provider."""

from langchain_core.globals import set_debug, set_verbose
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.env_config import settings
from app.config.log_config import config as log_config

logger = log_config.get_logger(__name__)


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
        log_config.configure_langchain_logging(
            verbose=settings.langchain_verbose,
            debug=settings.langchain_debug,
        )
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


config = LlmConfig()
