import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

STRUCTURED_FIELDS = {
    "chunks_created",
    "chunks_received",
    "database_duration_ms",
    "documents_created",
    "documents_discovered",
    "documents_processed",
    "documents_persisted",
    "documents_received",
    "documents_skipped",
    "documents_unchanged",
    "documents_updated",
    "duration_ms",
    "duration_seconds",
    "embedding_duration_ms",
    "embeddings_generated",
    "ingestion_job_id",
    "page_url",
    "pages_loaded",
    "pages_skipped",
    "persistence_duration_ms",
    "processing_duration_ms",
    "provider",
    "reason",
    "root_url",
    "source_url",
    "stage",
    "status_code",
    "success",
    "total_duration_ms",
    "website_loading_duration_ms",
}


class JsonFormatter(logging.Formatter):
    """Emit allow-listed operational fields while excluding content and secrets."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in STRUCTURED_FIELDS:
            if hasattr(record, field):
                value = getattr(record, field)
                payload[field] = _redact_url(value) if field.endswith("url") else value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _redact_url(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<invalid-url>"
    if not parts.scheme or not parts.netloc:
        return value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
