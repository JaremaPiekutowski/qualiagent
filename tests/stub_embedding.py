"""Deterministic embedding client for tests."""

import math
import re


class StubEmbeddingClient:
    """Build content-based fake embeddings without calling Voyage."""

    def __init__(self, dimensions: int = 1024) -> None:
        """Store embedding width.

        Args:
            dimensions: Vector length to generate.
        """
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents with a deterministic bag-of-tokens vector.

        Args:
            texts: Input documents.

        Returns:
            One vector per text.
        """
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Embed a query with the same scheme as documents.

        Args:
            text: Query text.

        Returns:
            Normalized embedding vector.
        """
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
        if not tokens:
            vector[0] = 1.0
            return vector

        for token in tokens:
            index = hash(token) % self.dimensions
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
