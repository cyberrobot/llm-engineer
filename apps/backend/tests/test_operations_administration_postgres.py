from contextlib import suppress
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.infrastructure.repositories.document_ingestion_job import (
    PostgresDocumentIngestionJobRepository,
)
from core.config import DATABASE_URL
from infrastructure.database.connection import get_connection, init_db
from infrastructure.database.migrations.operations_administration import upgrade
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


def test_operations_migration_upgrades_provisional_constraints_once_without_losing_data():
    require_database()
    schema = f"operations_administration_{uuid4().hex}"
    audit_id = uuid4()

    try:
        with get_connection() as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            connection.execute("""
                CREATE TABLE operations_runtime_state (
                    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                    maintenance_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    maintenance_message TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_by TEXT,
                    CONSTRAINT operations_runtime_state_check
                        CHECK (NOT maintenance_enabled OR maintenance_message IS NOT NULL)
                )
            """)
            connection.execute(
                """INSERT INTO operations_runtime_state
                   (singleton,maintenance_enabled,maintenance_message,updated_by)
                   VALUES (TRUE,FALSE,NULL,'existing-operator')"""
            )
            connection.execute("""
                CREATE TABLE operations_audit_logs (
                    id UUID PRIMARY KEY,
                    timestamp TIMESTAMPTZ NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    result TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    duration_ms BIGINT NOT NULL CHECK (duration_ms >= 0),
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    CONSTRAINT operations_audit_logs_result_check
                        CHECK (result IN ('SUCCESS', 'FAILURE'))
                )
            """)
            connection.execute(
                """INSERT INTO operations_audit_logs
                   (id,timestamp,actor,action,resource,result,request_id,correlation_id,
                    duration_ms,metadata)
                   VALUES (%s,NOW(),'existing-operator','cache.clear','cache','SUCCESS',
                           'request','correlation',3,'{}'::jsonb)""",
                (audit_id,),
            )

            with connection.cursor() as cursor:
                upgrade(cursor)
                upgrade(cursor)

            definition = connection.execute(
                """SELECT pg_get_constraintdef(oid) FROM pg_constraint
                   WHERE conname='operations_audit_logs_result_check'
                     AND conrelid='operations_audit_logs'::regclass"""
            ).fetchone()[0]
            obsolete_runtime_constraints = connection.execute(
                """SELECT count(*) FROM pg_constraint
                   WHERE conname='operations_runtime_state_check'
                     AND conrelid='operations_runtime_state'::regclass"""
            ).fetchone()[0]
            stored_audit = connection.execute(
                "SELECT actor,result FROM operations_audit_logs WHERE id=%s", (audit_id,)
            ).fetchone()
            stored_runtime = connection.execute(
                """SELECT maintenance_enabled,maintenance_message,updated_by
                   FROM operations_runtime_state WHERE singleton=TRUE"""
            ).fetchone()

        assert "STARTED" in definition
        assert obsolete_runtime_constraints == 0
        assert stored_audit == ("existing-operator", "SUCCESS")
        assert stored_runtime == (False, None, "existing-operator")
    finally:
        with suppress(Exception), get_connection() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
