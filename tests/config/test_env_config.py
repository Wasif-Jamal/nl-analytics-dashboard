"""Tests for app.config.env_config."""

from app.config.env_config import Settings, settings


def test_default_paths():
    """The module-level settings expose the documented defaults."""
    assert settings.database_url == "sqlite:///data/superstore.db"
    assert settings.csv_path == "data/database.csv"


def test_env_overrides(monkeypatch):
    """Environment variables override the defaults when settings are built."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///custom.db")
    monkeypatch.setenv("CSV_PATH", "other/data.csv")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    reloaded = Settings()

    assert reloaded.database_url == "sqlite:///custom.db"
    assert reloaded.csv_path == "other/data.csv"
    assert reloaded.google_api_key == "test-key"
