from abc import ABC, abstractmethod

from assistant.domain.extracted_document import ExtractedDocument
from assistant.domain.website_document import WebsiteDocument


class ContentExtractor(ABC):
    """Application boundary for converting raw markup to semantic text."""

    @abstractmethod
    def extract(self, document: WebsiteDocument) -> ExtractedDocument | None:
        """Return extracted content, or ``None`` when the page has no meaningful body."""
