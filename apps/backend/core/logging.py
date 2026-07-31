import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from core.correlation import request_id_context

STRUCTURED_FIELDS = {
    "batch_number",
    "batch_size",
    "candidates_found",
    "attempt_number",
    "chunks_created",
    "checksum_algorithm",
    "content_status",
    "chunks_received",
    "chunk_count",
    "database_duration_ms",
    "documents_created",
    "documents_discovered",
    "documents_processed",
    "documents_persisted",
    "documents_received",
    "documents_skipped",
    "documents_unchanged",
    "documents_updated",
    "file_size_bytes",
    "duration_ms",
    "duration_seconds",
    "dry_run",
    "delay_seconds",
    "embedding_duration_ms",
    "embeddings_generated",
    "embedding_count",
    "execution_identity",
    "ingestion_job_id",
    "job_id",
    "worker_id",
    "claim_version",
    "lease_expires_at",
    "document_id",
    "failure_code",
    "failure_category",
    "page_url",
    "pages_loaded",
    "pages_skipped",
    "access_level",
    "operation_id",
    "operation_type",
    "principal_id",
    "request_id",
    "persistence_duration_ms",
    "persistence_mode",
    "processing_duration_ms",
    "provider",
    "maximum_attempts",
    "maintenance_category",
    "maintenance_policy_version",
    "manual_review_count",
    "max_batches",
    "reason",
    "reason_code",
    "record_id",
    "record_type",
    "records_deleted",
    "records_repaired",
    "records_skipped",
    "result",
    "root_url",
    "source_url",
    "stage",
    "status_code",
    "success",
    "retryable",
    "retry_count",
    "security_scope_id",
    "step",
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
            "event": record.getMessage(),
        }
        for field in STRUCTURED_FIELDS:
            if hasattr(record, field):
                value = getattr(record, field)
                payload[field] = _redact_url(value) if field.endswith("url") else value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(",", ":"))


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_context.get()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationFilter())
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
