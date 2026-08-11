from contextlib import suppress
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest

from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.infrastructure.repositories.document_ingestion_job import (
    PostgresDocumentIngestionJobRepository,
)
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from operations.application.administration import AuditQueryService
from operations.domain.administration import AuditFilters, AuditResult, MaintenanceState
from operations.infrastructure.audit import PostgresOperationsAuditStore
from operations.infrastructure.jobs import IngestionJobOperationsStore
from operations.infrastructure.runtime import PostgresRuntimeStateStore


def require_database() -> None:
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def test_postgres_runtime_audit_filters_and_existing_job_repository_persist():
    require_database()
    init_db()
    now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    runtime = PostgresRuntimeStateStore()
    audit = AuditQueryService(PostgresOperationsAuditStore())
    original_maintenance = runtime.get_maintenance()
    audit_ids = []
    document_id = str(uuid4())
    resource = f"integration:{uuid4()}"
    job = DocumentIngestionJob.create(document_id, job_id=uuid4(), created_at=now)

    try:
        maintenance = runtime.set_maintenance(
            MaintenanceState(True, None, now, "integration-operator")
        )
        first = audit.record(
            actor="integration-operator",
            action="cache.clear",
            resource=resource,
            result=AuditResult.success,
            request_id=str(uuid4()),
            correlation_id=str(uuid4()),
            duration_ms=4,
            metadata={"safe": "visible", "password": "must-not-persist"},
            timestamp=now - timedelta(minutes=2),
        )
        second = audit.record(
            actor="other-operator",
            action="maintenance.update",
            resource=resource,
            result=AuditResult.failure,
            request_id=str(uuid4()),
            correlation_id=str(uuid4()),
            duration_ms=5,
            timestamp=now - timedelta(minutes=1),
        )
        third = audit.record(
            actor="integration-operator",
            action="maintenance.update",
            resource=resource,
            result=AuditResult.success,
            request_id=str(uuid4()),
            correlation_id=str(uuid4()),
            duration_ms=6,
            timestamp=now,
        )
        audit_ids.extend((first.id, second.id, third.id))
        started = audit.start(
            actor="integration-operator",
            action="cache.region.clear",
            resource=f"{resource}:started",
            request_id=str(uuid4()),
            correlation_id=str(uuid4()),
        )
        audit_ids.append(started.id)

        with get_connection() as connection:
            connection.execute(
                "INSERT INTO documents (id,doc_type,assistant_id) VALUES (%s,'test',%s)",
                (document_id, str(REDMOOR_ASSISTANT_ID)),
            )
        repository = PostgresDocumentIngestionJobRepository()
        repository.create(job)

        assert PostgresRuntimeStateStore().get_maintenance() == maintenance
        assert PostgresOperationsAuditStore().get(started.id).result is AuditResult.started
        completed = audit.finish(started, result=AuditResult.success, duration_ms=7)
        assert PostgresOperationsAuditStore().get(started.id) == completed

        page = audit.list(AuditFilters(resource=resource), limit=2, offset=0)
        assert page.total == 3
        assert [entry.id for entry in page.items] == [third.id, second.id]
        assert audit.list(AuditFilters(resource=resource), limit=2, offset=2).items == (first,)
        assert (
            audit.list(
                AuditFilters(user="integration-operator", resource=resource), limit=10, offset=0
            ).total
            == 2
        )
        assert (
            audit.list(
                AuditFilters(action="maintenance.update", resource=resource), limit=10, offset=0
            ).total
            == 2
        )
        assert audit.list(
            AuditFilters(result=AuditResult.failure, resource=resource), limit=10, offset=0
        ).items == (second,)
        assert audit.list(
            AuditFilters(
                resource=resource,
                date_from=now - timedelta(seconds=90),
                date_to=now,
            ),
            limit=10,
            offset=0,
        ).items == (third, second)
        assert audit.get(first.id).metadata == {
            "safe": "visible",
            "password": "[REDACTED]",
        }

        job_store = IngestionJobOperationsStore(repository)
        assert job_store.get(job.id).status == "queued"
        assert job.id in {item.id for item in job_store.list(limit=10, offset=0).items}
    finally:
        with suppress(Exception):
            runtime.set_maintenance(original_maintenance)
        if audit_ids:
            with suppress(Exception), get_connection() as connection:
                connection.execute(
                    "DELETE FROM operations_audit_logs WHERE id = ANY(%s)", (audit_ids,)
                )
        with suppress(Exception), get_connection() as connection:
            connection.execute("DELETE FROM document_ingestion_jobs WHERE id=%s", (str(job.id),))
            connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
