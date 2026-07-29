from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WebsiteDocument:
    """Raw HTML and retrieval metadata for one website page."""

    url: str
    status_code: int
    content_type: str
    html: str
    title: str | None
    retrieved_at: datetime
