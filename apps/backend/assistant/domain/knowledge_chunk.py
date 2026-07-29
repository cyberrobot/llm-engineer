from dataclasses import dataclass
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from assistant.domain.clean_document import CleanDocument


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """An ordered, deterministic passage produced from cleaned website content."""

    id: UUID
    source_url: str
    title: str | None
    sequence: int
    text: str
    content_hash: str
    document_content_hash: str
    heading_path: tuple[str, ...]
    character_count: int

    @classmethod
    def create(
        cls,
        *,
        document: CleanDocument,
        sequence: int,
        text: str,
        heading_path: tuple[str, ...] = (),
    ) -> "KnowledgeChunk":
        content = text.strip()
        if sequence < 0:
            raise ValueError("Knowledge chunk sequence must not be negative.")
        if not content:
            raise ValueError("Knowledge chunk text must not be empty.")
        identity = "\0".join([document.source_url, document.content_hash, str(sequence), content])
        content_hash = sha256(identity.encode("utf-8")).hexdigest()
        return cls(
            id=uuid5(NAMESPACE_URL, content_hash),
            source_url=document.source_url,
            title=document.title,
            sequence=sequence,
            text=content,
            content_hash=content_hash,
            document_content_hash=document.content_hash,
            heading_path=heading_path,
            character_count=len(content),
        )
