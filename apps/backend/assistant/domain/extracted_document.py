from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Meaningful semantic content extracted from one raw website page."""

    source_url: str
    title: str | None
    headings: list[str]
    text: str
    retrieved_at: datetime
