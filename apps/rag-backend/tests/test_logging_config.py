import logging

from logging_config import RequestIdFilter, request_id_context


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
