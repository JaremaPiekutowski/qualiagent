"""FastAPI dependency providers."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from qualiagent.database import SessionLocal
from qualiagent.ingest.embedding import EmbeddingClient, VoyageEmbeddingClient
from qualiagent.language_model import AnthropicLanguageModelClient, LanguageModelClient


def get_db() -> Generator[Session]:
    """Yield a request-scoped database session.

    Commits on success and rolls back on error.

    Yields:
        An open SQLAlchemy ``Session``.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_embedding_client() -> EmbeddingClient:
    """Return the default Voyage embedding client.

    Returns:
        Client used when ingesting uploaded sources.
    """
    return VoyageEmbeddingClient()


def get_language_model() -> LanguageModelClient:
    """Return the default Anthropic language model client.

    Returns:
        Client used by analysis graph nodes.
    """
    return AnthropicLanguageModelClient()
