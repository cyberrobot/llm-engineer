from dataclasses import dataclass

from assistant.domain.chunk import KnowledgeChunk


@dataclass(frozen=True, slots=True)
class Citation:
    """A response reference derived from a retrieved chunk."""

    document_id: str
    title: str
    chunk_id: str
    source_uri: str | None = None

    @classmethod
    def from_chunk(cls, chunk: KnowledgeChunk) -> "Citation":
        return cls(
            document_id=chunk.document.id,
            title=chunk.document.title,
            chunk_id=chunk.id,
            source_uri=chunk.document.source_uri,
        )
