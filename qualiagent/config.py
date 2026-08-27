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
    chunk_size_characters: int = 1200
    chunk_overlap_characters: int = 200
    voyage_model: str = "voyage-3"
    voyage_embedding_dimensions: int = 1024
    voyage_batch_size: int = 128
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Returns:
        Settings loaded from the environment and ``.env``.
    """
    return Settings()  # type: ignore[call-arg]
