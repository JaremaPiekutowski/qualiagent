"""Document and query embedding clients."""

import logging
from typing import Protocol, cast

import voyageai

from qualiagent.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingClient(Protocol):
    """Interface for turning texts into embedding vectors."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts.

        Args:
            texts: Plain-text documents.

        Returns:
            One embedding vector per input text.
        """
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query.

        Args:
            text: Query text.

        Returns:
            Query embedding vector.
        """
        ...


class VoyageEmbeddingClient:
    """Voyage AI client used for document and query embeddings."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Create a Voyage client.

        Args:
            settings: Optional settings override; defaults to env settings.
        """
        self.settings = settings or get_settings()
        # voyageai stubs do not export Client in the package type info.
        self.client = voyageai.Client(api_key=self.settings.voyage_api_key)  # type: ignore[attr-defined]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with Voyage in configured batch sizes.

        Args:
            texts: Plain-text documents.

        Returns:
            Embedding vectors aligned with ``texts``.
        """
        if not texts:
            return []

        embeddings: list[list[float]] = []
        batch_size = self.settings.voyage_batch_size
        total_batches = (len(texts) + batch_size - 1) // batch_size
        for batch_index, start in enumerate(range(0, len(texts), batch_size), start=1):
            batch = texts[start : start + batch_size]
            logger.info(
                "Voyage batch %s/%s (%s texts, model=%s)",
                batch_index,
                total_batches,
                len(batch),
                self.settings.voyage_model,
            )
            result = self.client.embed(
                batch,
                model=self.settings.voyage_model,
                input_type="document",
            )
            embeddings.extend(cast(list[list[float]], result.embeddings))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        """Embed one query with Voyage ``input_type=query``.

        Args:
            text: Query text.

        Returns:
            Query embedding vector.
        """
        result = self.client.embed(
            [text],
            model=self.settings.voyage_model,
            input_type="query",
        )
        embeddings = cast(list[list[float]], result.embeddings)
        return embeddings[0]


def embed_texts(
    texts: list[str],
    client: EmbeddingClient | None = None,
) -> list[list[float]]:
    """Embed texts with the given client or the default Voyage client.

    Args:
        texts: Plain-text documents.
        client: Optional embedding client (useful in tests).

    Returns:
        Embedding vectors aligned with ``texts``.
    """
    embedding_client = client or VoyageEmbeddingClient()
    return embedding_client.embed_documents(texts)
