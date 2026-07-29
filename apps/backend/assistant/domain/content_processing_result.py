from dataclasses import dataclass

from assistant.domain.knowledge_chunk import KnowledgeChunk


@dataclass(frozen=True, slots=True)
class ProcessingWarning:
    source_url: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ContentProcessingResult:
    documents_received: int
    documents_processed: int
    documents_skipped: int
    chunks_created: int
    chunks: list[KnowledgeChunk]
    warnings: list[ProcessingWarning]
    duration_ms: int
