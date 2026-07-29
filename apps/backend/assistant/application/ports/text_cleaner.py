from abc import ABC, abstractmethod

from assistant.domain.clean_document import CleanDocument
from assistant.domain.extracted_document import ExtractedDocument


class TextCleaner(ABC):
    """Application boundary for deterministic text normalisation."""

    @abstractmethod
    def clean(self, document: ExtractedDocument) -> CleanDocument | None:
        """Return clean content, or ``None`` when too little useful text remains."""
