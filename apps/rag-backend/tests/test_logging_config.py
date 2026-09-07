import json
import logging

from logging_config import JsonFormatter, RequestIdFilter, request_id_context


def test_log_records_receive_effective_request_id_without_sensitive_context():
    token = request_id_context.set("12345678-1234-5678-1234-567812345678")
    try:
        record = logging.LogRecord(
            "rag_backend", logging.ERROR, __file__, 1, "failed", (), None
        )
        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "12345678-1234-5678-1234-567812345678"
        assert record.msg == "failed"
    finally:
        request_id_context.reset(token)


def test_json_formatter_emits_only_allowlisted_operational_fields():
    record = logging.LogRecord(
        "rag_backend", logging.ERROR, __file__, 1, "retrieval_failed", (), None
    )
    record.request_id = "request-1"
    record.failure_category = "database_connectivity"
    record.question = "sensitive question"
    record.database_url = "postgresql://secret"

    payload = json.loads(JsonFormatter().format(record))

    assert payload == {
        "event": "retrieval_failed",
        "failure_category": "database_connectivity",
        "level": "ERROR",
        "request_id": "request-1",
        "service": "rag-backend",
    }
