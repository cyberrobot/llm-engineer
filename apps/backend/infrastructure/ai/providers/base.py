from abc import ABC, abstractmethod
from collections.abc import Iterator


class AIProvider(ABC):
    """Provider-neutral interface used by Assistant application services."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable provider identifier."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the configured model identifier for observability."""

    @abstractmethod
    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        """Generate a text response from provider-neutral prompt strings."""

    def generate_embedding(self, *, text: str) -> list[float]:
        """Generate an embedding without exposing a provider-specific API.

        The default keeps existing provider adapters source-compatible. Providers used
        by retrieval should override it.
        """
        return []

    def stream_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float = 0.2,
        timeout_seconds: float | None = None,
    ) -> Iterator[str]:
        """Stream text while keeping older provider adapters source-compatible."""
        del max_output_tokens, temperature, timeout_seconds
        response = self.generate_response(system_prompt=system_prompt, user_prompt=user_prompt)
        if response:
            yield response

    def generate_embeddings(self, *, texts: list[str]) -> list[list[float]]:
        """Generate embeddings in input order while preserving adapter compatibility."""
        return [self.generate_embedding(text=text) for text in texts]
