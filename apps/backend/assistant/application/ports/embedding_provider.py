from typing import Protocol


class EmbeddingProvider(Protocol):
    """Provider-neutral batch embedding boundary used by persistence."""

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        """Return one vector for each input text, preserving input order."""
