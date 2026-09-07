import json
import logging
from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    """Emit low-cardinality operational events as one JSON object per line."""

    _fields = (
        "operation",
        "path",
        "status_code",
        "duration_ms",
        "failure_category",
        "dependency",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "service": "rag-backend",
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for field in self._fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def initialize_logging() -> logging.Logger:
    logger = logging.getLogger("rag_backend")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(RequestIdFilter())
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
