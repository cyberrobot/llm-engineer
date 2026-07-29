from abc import ABC, abstractmethod

from assistant.domain.website_document import WebsiteDocument


class WebsiteLoaderError(RuntimeError):
    """Base error exposed by the website-loading application boundary."""


class InvalidWebsiteUrl(WebsiteLoaderError, ValueError):
    """Raised when a URL is malformed, unsupported, or unsafe to request."""


class WebsiteLoadError(WebsiteLoaderError):
    """Raised when the root website document cannot be loaded."""


class WebsiteTimeoutError(WebsiteLoadError):
    """Raised when loading the root website document times out."""


class WebsiteHTTPStatusError(WebsiteLoadError):
    """Raised with stable HTTP metadata when the root source rejects retrieval."""

    def __init__(
        self,
        status_code: int,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__("Website root page returned an unsuccessful status.")
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class WebsiteLoader(ABC):
    """Application port for retrieving raw documents from a website."""

    @abstractmethod
    def load(self, url: str) -> list[WebsiteDocument]:
        """Load raw HTML documents reachable from the supplied root URL."""
