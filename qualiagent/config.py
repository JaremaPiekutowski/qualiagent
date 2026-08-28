"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for database, embeddings, and logging."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    voyage_api_key: str
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    chunk_size_characters: int = 1200
    chunk_overlap_characters: int = 200
    voyage_model: str = "voyage-3"
    voyage_embedding_dimensions: int = 1024
    voyage_batch_size: int = 128
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    retrieval_top_k: int = 8
    rrf_constant: int = 60
    web_search_max_uses: int = 3
    reports_directory: str = "reports"
    use_postgres_checkpointer: bool = True
    interrupt_before_write: bool = True
    admin_username: str = "admin"
    admin_password: str = "admin"
    admin_secret_key: str = "change-me-qualiagent-admin"

    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins.

        Returns:
            List of allowed frontend origins.
        """
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Returns:
        Settings loaded from the environment and ``.env``.
    """
    return Settings()  # type: ignore[call-arg]
