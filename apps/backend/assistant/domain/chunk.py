from dataclasses import dataclass

from assistant.domain.document import KnowledgeDocument


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """A ranked passage retrieved from a knowledge document."""

    id: str
    document: KnowledgeDocument
    content: str
    score: float
