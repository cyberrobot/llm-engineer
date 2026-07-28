from abc import ABC, abstractmethod


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
