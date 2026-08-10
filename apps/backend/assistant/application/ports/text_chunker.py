from abc import ABC, abstractmethod

from assistant.domain.clean_document import CleanDocument
from assistant.domain.knowledge_chunk import KnowledgeChunk


class TextChunker(ABC):
    """Application boundary for ordered, deterministic text chunking."""

    @abstractmethod
    def chunk(self, document: CleanDocument) -> list[KnowledgeChunk]:
        """Return ordered chunks, or raise a declared recoverable page-level chunking error."""
