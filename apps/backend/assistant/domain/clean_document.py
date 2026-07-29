from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CleanDocument:
    """Deterministically normalised website content ready for chunking."""

    source_url: str
    title: str | None
    text: str
    content_hash: str
    retrieved_at: datetime
