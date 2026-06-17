"""Tests for app.config.llm_config."""

from unittest.mock import patch

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.llm_config import LlmConfig


def test_get_llm_returns_chat_google_generative_ai():
    """get_llm() returns a ChatGoogleGenerativeAI instance."""
    with patch("app.config.llm_config.settings") as mock_settings:
        mock_settings.llm_model = "gemini-2.0-flash"
        mock_settings.llm_temperature = 0.0
        mock_settings.google_api_key = "test-key"
        llm = LlmConfig().get_llm()
    assert isinstance(llm, ChatGoogleGenerativeAI)


def test_get_llm_uses_settings_model():
    """The model name from settings is reflected in the LLM client."""
    with patch("app.config.llm_config.settings") as mock_settings:
        mock_settings.llm_model = "gemini-2.0-flash"
        mock_settings.llm_temperature = 0.0
        mock_settings.google_api_key = "test-key"
        llm = LlmConfig().get_llm()
    assert "gemini-2.0-flash" in llm.model
