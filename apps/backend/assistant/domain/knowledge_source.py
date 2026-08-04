import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import UUID, uuid4

from assistant.domain.assistant import DocumentRetrievalState

MAX_DIRECT_TEXT_CHARACTERS = 100_000


def normalize_knowledge_source_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Knowledge source URL is malformed.") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Knowledge source URL must be absolute HTTP or HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Knowledge source URL must not contain credentials.")
    host = parsed.hostname.lower().encode("idna").decode("ascii")
    default_port = 80 if scheme == "http" else 443
    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if port in {None, default_port} else f"{display_host}:{port}"
    return urlunsplit(SplitResult(scheme, netloc, parsed.path or "/", parsed.query, ""))


class KnowledgeSourceType(str, Enum):
    direct_text = "direct_text"
    url = "url"


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    id: UUID
    assistant_id: UUID
    source_type: KnowledgeSourceType
    name: str
    retrieval_state: DocumentRetrievalState
    direct_text: str | None
    url: str | None
    document_id: str
    content_version: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("Knowledge source name must not be empty.")
        if self.id.int == 0 or self.assistant_id.int == 0:
            raise ValueError("Knowledge source identifiers must not be nil.")
        if not self.document_id.strip():
            raise ValueError("Knowledge source requires a canonical document.")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Knowledge source timestamps must be timezone-aware.")
        if self.updated_at < self.created_at:
            raise ValueError("Knowledge source update cannot precede creation.")
        if self.source_type is KnowledgeSourceType.direct_text:
            if self.url is not None or self.direct_text is None or not self.direct_text.strip():
                raise ValueError("A direct-text source requires only non-empty direct_text.")
            if len(self.direct_text) > MAX_DIRECT_TEXT_CHARACTERS:
                raise ValueError("Direct text exceeds the configured maximum length.")
        elif self.direct_text is not None or self.url is None:
            raise ValueError("A URL source requires only a URL.")
        elif normalize_knowledge_source_url(self.url) != self.url or urlsplit(self.url).fragment:
            raise ValueError("Knowledge source URL must be normalized and fragment-free.")

    @classmethod
    def create(
        cls,
        *,
        assistant_id: UUID,
        source_type: KnowledgeSourceType,
        name: str,
        direct_text: str | None = None,
        url: str | None = None,
        source_id: UUID | None = None,
        now: datetime | None = None,
    ) -> "KnowledgeSource":
        identifier = source_id or uuid4()
        timestamp = now or datetime.now(timezone.utc)
        if url is not None and urlsplit(url).fragment:
            raise ValueError("Knowledge source URL must not contain a fragment.")
        normalized_url = normalize_knowledge_source_url(url) if url is not None else None
        payload = direct_text if source_type is KnowledgeSourceType.direct_text else normalized_url
        version = hashlib.sha256((payload or "").encode("utf-8")).hexdigest()
        return cls(
            id=identifier,
            assistant_id=assistant_id,
            source_type=source_type,
            name=name.strip(),
            retrieval_state=DocumentRetrievalState.enabled,
            direct_text=direct_text,
            url=normalized_url,
            document_id=str(uuid4()),
            content_version=version,
            created_at=timestamp,
            updated_at=timestamp,
        )
