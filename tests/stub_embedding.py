"""Deterministic embedding client for tests."""


class StubEmbeddingClient:
    """Return fixed-size fake embeddings without calling Voyage."""

    def __init__(self, dimensions: int = 1024) -> None:
        """Store embedding width.

        Args:
            dimensions: Vector length to generate.
        """
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Build deterministic vectors for each text.

        Args:
            texts: Input documents.

        Returns:
            One vector per text.
        """
        embeddings: list[list[float]] = []
        for index, text in enumerate(texts):
            vector = [0.0] * self.dimensions
            vector[0] = float(index + 1)
            vector[1] = float(len(text))
            embeddings.append(vector)
        return embeddings
