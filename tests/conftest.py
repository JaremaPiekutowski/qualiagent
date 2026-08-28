"""Shared pytest fixtures."""

from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from qualiagent.config import Settings, get_settings
from tests.stub_embedding import StubEmbeddingClient

EmbeddingClientFactory = Callable[..., StubEmbeddingClient]


@pytest.fixture
def session() -> Generator[Session]:
    """Yield a database session rolled back after the test."""
    database_url = get_settings().database_url
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    database_session = factory()
    try:
        yield database_session
        database_session.rollback()
    finally:
        database_session.close()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return test settings without reading Voyage from the environment."""
    return Settings(
        database_url="postgresql+psycopg://unused:unused@127.0.0.1:5432/unused",
        voyage_api_key="test-key",
        chunk_size_characters=200,
        chunk_overlap_characters=40,
        voyage_embedding_dimensions=1024,
        reports_directory=str(tmp_path / "reports"),
        interrupt_before_write=False,
        use_postgres_checkpointer=False,
    )


@pytest.fixture
def make_embedding_client() -> EmbeddingClientFactory:
    """Return a factory that builds stub embedding clients.

    Returns:
        Callable ``make_embedding_client(dimensions=1024)``.
    """

    def factory(dimensions: int = 1024) -> StubEmbeddingClient:
        return StubEmbeddingClient(dimensions=dimensions)

    return factory


@pytest.fixture
def embedding_client(
    make_embedding_client: EmbeddingClientFactory,
    settings: Settings,
) -> StubEmbeddingClient:
    """Return a stub client sized to the test embedding dimensions."""
    return make_embedding_client(dimensions=settings.voyage_embedding_dimensions)
