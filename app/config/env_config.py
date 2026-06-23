"""Application settings and environment configuration.

Centralizes environment variable loading via ``pydantic-settings``. Import the
module-level :data:`settings` singleton; never read ``os.environ`` directly.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, loaded from the environment / ``.env``.

    Attributes:
        database_url: SQLAlchemy URL for the SQLite database.
        csv_path: Path to the source CSV loaded into the database at startup.
        google_api_key: API key for the Google GenAI (Gemini) provider.
        llm_model: Gemini model identifier (default ``gemini-2.0-flash``).
        llm_temperature: Sampling temperature for the LLM (default 0.0 for determinism).
        sql_retry_limit: Max self-correction attempts for the SQL agent (default 3,
            capped at 10 to bound token consumption).
        langchain_verbose: Enable LangChain verbose mode (inputs/outputs per chain step).
        langchain_debug: Enable LangChain debug mode (full message payloads and tool calls).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/superstore.db"
    csv_path: str = "data/database.csv"
    google_api_key: str | None = None
    llm_model: str = "gemini-2.0-flash"
    llm_temperature: float = 0.0
    sql_retry_limit: int = Field(default=3, ge=1, le=10)
    api_base_url: str = "http://localhost:8000"
    langchain_verbose: bool = False
    langchain_debug: bool = False


settings = Settings()
