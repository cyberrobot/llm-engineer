import json
import logging

from prometheus_client import CollectorRegistry, generate_latest

from assistant.maintenance.ingestion import (
    MaintenanceCategory,
    MaintenanceError,
    MaintenanceFinding,
    MaintenanceResult,
)
from core.logging import JsonFormatter
from core.metrics import IngestionMaintenanceMetrics


def test_maintenance_metrics_use_only_bounded_category_result_and_reason_labels():
    registry = CollectorRegistry()
    metrics = IngestionMaintenanceMetrics(registry=registry)
    result = MaintenanceResult(
        MaintenanceCategory.terminal_job_retention,
        dry_run=False,
        records_deleted=2,
        records_repaired=1,
        records_skipped=3,
        duration_ms=250,
        errors=[MaintenanceError("database_unavailable", "ingestion_job", "sensitive-id")],
        findings=[
            MaintenanceFinding(
                "ingestion_job", "sensitive-id", "ambiguous_state", "inspect the record"
            )
        ],
    )

    metrics.record_batch(result.maintenance_category.value, 0.05)
    metrics.record_result(result, outcome="error")
    output = generate_latest(registry).decode()

    assert 'maintenance_category="TERMINAL_JOB_RETENTION"' in output
    assert 'result="error"' in output
    assert 'reason_code="database_unavailable"' in output
    assert 'reason_code="ambiguous_state"' in output
    assert "sensitive-id" not in output
    assert "record_type" not in output


def test_structured_maintenance_logs_exclude_content_embeddings_and_storage_urls():
    record = logging.LogRecord(
        "maintenance",
        logging.INFO,
        __file__,
        1,
        "ingestion_maintenance_completed",
        (),
        None,
    )
    record.maintenance_category = "TERMINAL_JOB_RETENTION"
    record.dry_run = True
    record.document_content = "secret source text"
    record.embedding = [0.1, 0.2]
    record.storage_url = "https://secret.example/path?token=secret"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["maintenance_category"] == "TERMINAL_JOB_RETENTION"
    assert payload["dry_run"] is True
    assert "document_content" not in payload
    assert "embedding" not in payload
    assert "storage_url" not in payload
    assert "secret" not in json.dumps(payload)
