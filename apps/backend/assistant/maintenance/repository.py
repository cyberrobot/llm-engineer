from __future__ import annotations

import heapq
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

import psycopg

from assistant.maintenance.ingestion import (
    BatchResult,
    Cursor,
    IngestionMaintenanceSettings,
    MaintenanceCategory,
    MaintenanceError,
    MaintenanceFinding,
)
from core.config import get_upload_dir
from infrastructure.database.connection import get_connection

logger = logging.getLogger(__name__)
_UPLOAD_NAME = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.pdf$",
    re.IGNORECASE,
)


class PostgresIngestionMaintenanceRepository:
    """Short-transaction, revalidating maintenance operations for the current schema."""

    def __init__(
        self,
        connection_factory: Callable[[], Any] = get_connection,
        *,
        upload_dir: Path | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._configured_upload_dir = upload_dir or get_upload_dir()
        self._upload_dir = self._configured_upload_dir.resolve()
        self._lock_connections: dict[MaintenanceCategory, Any] = {}
        self._lock_guard = RLock()

    def acquire_lock(self, category: MaintenanceCategory, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while True:
            connection = self._connection_factory()
            try:
                acquired = bool(
                    connection.execute(
                        "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
                        (f"ingestion-maintenance:{category.value}",),
                    ).fetchone()[0]
                )
                connection.commit()
                if acquired:
                    with self._lock_guard:
                        self._lock_connections[category] = connection
                    return True
            except Exception:
                connection.close()
                raise
            connection.close()
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))

    def release_lock(self, category: MaintenanceCategory) -> None:
        with self._lock_guard:
            connection = self._lock_connections.pop(category, None)
        if connection is None:
            return
        try:
            connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (f"ingestion-maintenance:{category.value}",),
            )
            connection.commit()
        finally:
            connection.close()

    def process_batch(
        self,
        category: MaintenanceCategory,
        *,
        settings: IngestionMaintenanceSettings,
        now: datetime,
        dry_run: bool,
        cursor: Cursor | None,
    ) -> BatchResult:
        category_value = category.value
        if category_value == MaintenanceCategory.terminal_job_retention.value:
            return self._cleanup_terminal_jobs(settings, now, dry_run, cursor)
        if category_value == MaintenanceCategory.step_history_retention.value:
            return self._cleanup_step_history(settings, now, dry_run, cursor)
        if category_value == MaintenanceCategory.orphan_chunk_cleanup.value:
            return self._cleanup_orphan_chunks(settings, dry_run, cursor)
        if category_value == MaintenanceCategory.temporary_source_cleanup.value:
            return self._cleanup_temporary_sources(settings, now, dry_run, cursor)
        if category_value == MaintenanceCategory.expired_lease_recovery.value:
            return self._reconcile_jobs(settings, now, dry_run, cursor, committed_only=False)
        if category_value == MaintenanceCategory.inconsistent_state_reconciliation.value:
            return self._reconcile_jobs(settings, now, dry_run, cursor, committed_only=True)
        if category_value in {
            MaintenanceCategory.orphan_representation_cleanup.value,
            MaintenanceCategory.superseded_representation_retention.value,
        }:
            return BatchResult(stopped_reason="not_applicable_current_schema")
        raise ValueError(f"Unsupported maintenance category: {category.value}")

    @staticmethod
    def _cursor_clause(
        cursor: Cursor | None, timestamp_column: str, identifier_column: str
    ) -> tuple[str, tuple[Any, ...]]:
        if cursor is None:
            return "", ()
        return f"AND ({timestamp_column}, {identifier_column}::text) > (%s, %s)", cursor

    def _cleanup_terminal_jobs(
        self,
        settings: IngestionMaintenanceSettings,
        now: datetime,
        dry_run: bool,
        cursor: Cursor | None,
    ) -> BatchResult:
        cutoffs = settings.job_cutoffs(now)
        cursor_sql, cursor_parameters = self._cursor_clause(cursor, "jobs.completed_at", "jobs.id")
        eligible = f"""
            FROM document_ingestion_jobs AS jobs
            WHERE (
                (jobs.status = 'completed' AND jobs.completed_at <= %s)
                OR (jobs.status = 'failed' AND jobs.completed_at <= %s)
                OR (jobs.status = 'cancelled' AND jobs.completed_at <= %s)
            )
              AND jobs.worker_id IS NULL
              AND (jobs.lease_expires_at IS NULL OR jobs.lease_expires_at <= %s)
              AND NOT EXISTS (
                  SELECT 1 FROM ingestion_step_executions AS attempts
                  WHERE attempts.ingestion_job_id = jobs.id
                    AND attempts.status IN ('running', 'interrupted')
              )
              AND NOT EXISTS (
                  SELECT 1 FROM documents
                  WHERE documents.last_ingestion_job_id = jobs.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM chunks WHERE chunks.ingestion_job_id = jobs.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM ingestion_file_requests AS requests
                  WHERE requests.ingestion_job_id = jobs.id
              )
              {cursor_sql}
        """
        parameters = (
            cutoffs["completed"],
            cutoffs["failed"],
            cutoffs["cancelled"],
            now,
            *cursor_parameters,
            settings.batch_size,
        )
        try:
            with self._connection_factory() as connection:
                if dry_run:
                    rows = connection.execute(
                        f"""SELECT jobs.id, jobs.completed_at {eligible}
                            ORDER BY jobs.completed_at, jobs.id LIMIT %s""",
                        parameters,
                    ).fetchall()
                else:
                    rows = connection.execute(
                        f"""
                        WITH candidates AS (
                            SELECT jobs.id, jobs.completed_at {eligible}
                            ORDER BY jobs.completed_at, jobs.id
                            LIMIT %s FOR UPDATE OF jobs SKIP LOCKED
                        ), deleted_results AS (
                            DELETE FROM ingestion_persistence_results AS results
                            USING candidates
                            WHERE results.ingestion_job_id = candidates.id
                        )
                        DELETE FROM document_ingestion_jobs AS jobs
                        USING candidates
                        WHERE jobs.id = candidates.id
                        RETURNING jobs.id, candidates.completed_at
                        """,
                        parameters,
                    ).fetchall()
        except psycopg.Error as exc:
            raise RuntimeError("Terminal ingestion-job cleanup failed.") from exc
        return self._deleted_batch(rows, dry_run=dry_run)

    def _cleanup_step_history(
        self,
        settings: IngestionMaintenanceSettings,
        now: datetime,
        dry_run: bool,
        cursor: Cursor | None,
    ) -> BatchResult:
        cutoff = now - timedelta(days=settings.step_history_retention_days)
        cursor_sql, cursor_parameters = self._cursor_clause(
            cursor, "attempts.completed_at", "attempts.id"
        )
        eligible = f"""
            FROM ingestion_step_executions AS attempts
            JOIN document_ingestion_jobs AS jobs ON jobs.id = attempts.ingestion_job_id
            WHERE jobs.status IN ('completed', 'failed', 'cancelled')
              AND jobs.completed_at IS NOT NULL
              AND attempts.status IN ('completed', 'failed')
              AND attempts.completed_at <= %s
              {cursor_sql}
        """
        parameters = (cutoff, *cursor_parameters, settings.batch_size)
        try:
            with self._connection_factory() as connection:
                if dry_run:
                    rows = connection.execute(
                        f"""SELECT attempts.id, attempts.completed_at {eligible}
                            ORDER BY attempts.completed_at, attempts.id LIMIT %s""",
                        parameters,
                    ).fetchall()
                else:
                    rows = connection.execute(
                        f"""
                        WITH candidates AS (
                            SELECT attempts.id, attempts.completed_at {eligible}
                            ORDER BY attempts.completed_at, attempts.id
                            LIMIT %s FOR UPDATE OF attempts SKIP LOCKED
                        )
                        DELETE FROM ingestion_step_executions AS attempts
                        USING candidates
                        WHERE attempts.id = candidates.id
                        RETURNING attempts.id, candidates.completed_at
                        """,
                        parameters,
                    ).fetchall()
        except psycopg.Error as exc:
            raise RuntimeError("Ingestion step-history cleanup failed.") from exc
        return self._deleted_batch(rows, dry_run=dry_run)

    def _cleanup_orphan_chunks(
        self,
        settings: IngestionMaintenanceSettings,
        dry_run: bool,
        cursor: Cursor | None,
    ) -> BatchResult:
        cursor_sql, cursor_parameters = self._cursor_clause(
            cursor, "chunks.created_at", "chunks.id"
        )
        eligible = f"""
            FROM chunks
            WHERE NOT EXISTS (SELECT 1 FROM documents WHERE documents.id = chunks.doc_id)
              {cursor_sql}
        """
        parameters = (*cursor_parameters, settings.batch_size)
        try:
            with self._connection_factory() as connection:
                if dry_run:
                    rows = connection.execute(
                        f"""SELECT chunks.id, chunks.created_at {eligible}
                            ORDER BY chunks.created_at, chunks.id LIMIT %s""",
                        parameters,
                    ).fetchall()
                else:
                    rows = connection.execute(
                        f"""
                        WITH candidates AS (
                            SELECT chunks.id, chunks.created_at {eligible}
                            ORDER BY chunks.created_at, chunks.id
                            LIMIT %s FOR UPDATE OF chunks SKIP LOCKED
                        )
                        DELETE FROM chunks USING candidates
                        WHERE chunks.id = candidates.id
                          AND NOT EXISTS (
                              SELECT 1 FROM documents WHERE documents.id = chunks.doc_id
                          )
                        RETURNING chunks.id, candidates.created_at
                        """,
                        parameters,
                    ).fetchall()
        except psycopg.Error as exc:
            raise RuntimeError("Orphan chunk cleanup failed.") from exc
        return self._deleted_batch(rows, dry_run=dry_run)

    @staticmethod
    def _deleted_batch(rows: list[Any], *, dry_run: bool) -> BatchResult:
        if not rows:
            return BatchResult()
        timestamp = rows[-1][1]
        identifier = str(rows[-1][0])
        return BatchResult(
            candidates_found=len(rows),
            records_deleted=0 if dry_run else len(rows),
            records_skipped=len(rows) if dry_run else 0,
            next_cursor=(timestamp, identifier),
        )

    def _cleanup_temporary_sources(
        self,
        settings: IngestionMaintenanceSettings,
        now: datetime,
        dry_run: bool,
        cursor: Cursor | None,
    ) -> BatchResult:
        cutoff = now - timedelta(hours=settings.temporary_source_retention_hours)
        candidates = heapq.nsmallest(
            settings.batch_size,
            self._temporary_source_candidates(cutoff, cursor),
            key=lambda item: (item[0], item[1].name),
        )
        if not candidates:
            return BatchResult()
        deleted = 0
        skipped = 0
        errors: list[MaintenanceError] = []
        for _modified_at, path in candidates:
            if self._upload_path_is_referenced(path):
                skipped += 1
                continue
            if dry_run:
                skipped += 1
                continue
            try:
                self._delete_managed_upload(path)
                deleted += 1
            except OSError:
                skipped += 1
                errors.append(
                    MaintenanceError(
                        "ingestion_maintenance_storage_delete_failed", "upload", path.name
                    )
                )
        last_modified, last_path = candidates[-1]
        return BatchResult(
            candidates_found=len(candidates),
            records_deleted=deleted,
            records_skipped=skipped,
            errors=errors,
            next_cursor=(last_modified, last_path.name),
        )

    def _temporary_source_candidates(self, cutoff: datetime, cursor: Cursor | None):
        if not self._upload_dir.exists():
            return
        with os.scandir(self._upload_dir) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False) or not _UPLOAD_NAME.fullmatch(
                    entry.name
                ):
                    continue
                modified_at = datetime.fromtimestamp(
                    entry.stat(follow_symlinks=False).st_mtime, timezone.utc
                )
                if modified_at > cutoff:
                    continue
                if cursor is not None and (modified_at, entry.name) <= cursor:
                    continue
                path = Path(entry.path).resolve()
                if path.parent == self._upload_dir:
                    yield modified_at, path

    def _upload_path_is_referenced(self, path: Path) -> bool:
        try:
            with self._connection_factory() as connection:
                row = connection.execute(
                    "SELECT 1 FROM documents WHERE upload_path IN (%s, %s) LIMIT 1",
                    (str(path), str(self._configured_upload_dir / path.name)),
                ).fetchone()
                return row is not None
        except psycopg.Error as exc:
            raise RuntimeError("Temporary-source reference validation failed.") from exc

    def _delete_managed_upload(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved.parent != self._upload_dir or not _UPLOAD_NAME.fullmatch(resolved.name):
            raise OSError("Unsafe upload path")
        resolved.unlink(missing_ok=True)

    def _reconcile_jobs(
        self,
        settings: IngestionMaintenanceSettings,
        now: datetime,
        dry_run: bool,
        cursor: Cursor | None,
        *,
        committed_only: bool,
    ) -> BatchResult:
        stale_before = now - timedelta(seconds=settings.stale_job_grace_seconds)
        cursor_sql, cursor_parameters = self._cursor_clause(cursor, "jobs.updated_at", "jobs.id")
        committed_sql = (
            "AND EXISTS (SELECT 1 FROM ingestion_persistence_results r WHERE r.ingestion_job_id = jobs.id)"
            if committed_only
            else ""
        )
        try:
            with self._connection_factory() as connection:
                rows = connection.execute(
                    f"""
                    SELECT jobs.id, jobs.status, jobs.document_id, jobs.current_step,
                           jobs.last_completed_step, jobs.retry_count, jobs.updated_at,
                           jobs.worker_id, jobs.lease_expires_at, documents.source_url,
                           documents.upload_path
                    FROM document_ingestion_jobs AS jobs
                    JOIN documents ON documents.id = jobs.document_id
                    WHERE (
                        (jobs.status = 'queued' AND (
                            jobs.worker_id IS NOT NULL OR jobs.claimed_at IS NOT NULL
                            OR jobs.lease_expires_at IS NOT NULL OR jobs.last_heartbeat_at IS NOT NULL
                        ))
                        OR (jobs.status IN ('completed', 'failed', 'cancelled') AND (
                            jobs.worker_id IS NOT NULL OR jobs.claimed_at IS NOT NULL
                            OR jobs.lease_expires_at IS NOT NULL OR jobs.last_heartbeat_at IS NOT NULL
                        ))
                        OR (jobs.status = 'running' AND (
                            jobs.lease_expires_at <= %s
                            OR (jobs.lease_expires_at IS NULL AND jobs.updated_at <= %s)
                        ))
                    )
                    {committed_sql}
                    {cursor_sql}
                    ORDER BY jobs.updated_at, jobs.id
                    LIMIT %s FOR UPDATE OF jobs SKIP LOCKED
                    """,
                    (stale_before, stale_before, *cursor_parameters, settings.batch_size),
                ).fetchall()
                if not rows:
                    return BatchResult()
                repaired = 0
                skipped = 0
                findings: list[MaintenanceFinding] = []
                for row in rows:
                    action, finding = self._reconciliation_action(connection, row)
                    if finding is not None:
                        findings.append(finding)
                        skipped += 1
                        continue
                    if dry_run:
                        skipped += 1
                        continue
                    repaired += self._apply_reconciliation(
                        connection, row, action, now, stale_before
                    )
        except psycopg.Error as exc:
            raise RuntimeError("Stale ingestion-job reconciliation failed.") from exc
        return BatchResult(
            candidates_found=len(rows),
            records_repaired=repaired,
            records_skipped=skipped,
            manual_review_count=len(findings),
            findings=findings,
            next_cursor=(rows[-1][6], str(rows[-1][0])),
        )

    def _reconciliation_action(
        self, connection: Any, row: Any
    ) -> tuple[str, MaintenanceFinding | None]:
        job_id, status, document_id = str(row[0]), str(row[1]), str(row[2])
        if status in {"queued", "completed", "failed", "cancelled"}:
            return "clear_ownership", None
        committed = connection.execute(
            """
            SELECT results.document_id, results.result, documents.last_ingestion_job_id,
                   (SELECT count(*) FROM chunks
                    WHERE chunks.doc_id = results.document_id
                      AND chunks.ingestion_job_id = results.ingestion_job_id),
                   (SELECT count(*) FROM chunks WHERE chunks.doc_id = results.document_id)
            FROM ingestion_persistence_results AS results
            JOIN documents ON documents.id = results.document_id
            WHERE results.ingestion_job_id = %s
            """,
            (job_id,),
        ).fetchone()
        if committed is not None:
            result = committed[1]
            expected_chunks = int(result.get("chunks_received", -1))
            exact = (
                str(committed[0]) == document_id
                and str(committed[2]) == job_id
                and int(committed[3]) == int(committed[4]) == expected_chunks
            )
            if exact:
                return "complete_committed", None
            return "manual_review", MaintenanceFinding(
                "ingestion_job",
                job_id,
                "committed_result_not_active_or_incomplete",
                "verify the active document pointer and committed chunk set",
            )
        if not self._checkpoint_is_consistent(row[3], row[4]):
            return "manual_review", MaintenanceFinding(
                "ingestion_job",
                job_id,
                "ingestion_maintenance_invalid_checkpoint",
                "inspect persisted step history before choosing a recovery state",
            )
        source_url, upload_path = row[9], row[10]
        if source_url is not None:
            return "reset_queued", None
        if upload_path is not None and self._safe_source_exists(str(upload_path)):
            return "reset_queued", None
        return "manual_review", MaintenanceFinding(
            "ingestion_job",
            job_id,
            "ingestion_maintenance_source_missing",
            "restore the source or mark failed after confirming recovery is impossible",
        )

    @staticmethod
    def _checkpoint_is_consistent(current_step: str | None, completed_step: str | None) -> bool:
        order = {None: -1, "parse": 0, "chunk": 1, "embed": 2, "persist": 3}
        return (
            current_step in order
            and completed_step in order
            and order[current_step] >= order[completed_step]
        )

    def _safe_source_exists(self, value: str) -> bool:
        try:
            path = Path(value).resolve()
            return path.parent == self._upload_dir and path.is_file() and not path.is_symlink()
        except OSError:
            return False

    @staticmethod
    def _apply_reconciliation(
        connection: Any,
        row: Any,
        action: str,
        now: datetime,
        stale_before: datetime,
    ) -> int:
        job_id = str(row[0])
        if action == "complete_committed":
            result = connection.execute(
                """
                UPDATE document_ingestion_jobs
                SET status = 'completed', current_step = NULL, last_completed_step = 'persist',
                    current_step_attempt_count = 0, last_attempted_at = NULL,
                    failure_code = NULL, failure_message = NULL, completed_at = %s,
                    worker_id = NULL, claimed_at = NULL, lease_expires_at = NULL,
                    last_heartbeat_at = NULL, claim_version = claim_version + 1, updated_at = %s
                WHERE id = %s AND status = 'running'
                  AND (
                      lease_expires_at <= %s
                      OR (lease_expires_at IS NULL AND updated_at <= %s)
                  )
                """,
                (now, now, job_id, stale_before, stale_before),
            )
            return result.rowcount
        if action == "reset_queued":
            result = connection.execute(
                """
                UPDATE document_ingestion_jobs
                SET status = 'queued', started_at = NULL, completed_at = NULL,
                    failure_code = NULL, failure_message = NULL,
                    worker_id = NULL, claimed_at = NULL, lease_expires_at = NULL,
                    last_heartbeat_at = NULL, claim_version = claim_version + 1, updated_at = %s
                WHERE id = %s AND status = 'running'
                  AND (
                      lease_expires_at <= %s
                      OR (lease_expires_at IS NULL AND updated_at <= %s)
                  )
                """,
                (now, job_id, stale_before, stale_before),
            )
            return result.rowcount
        result = connection.execute(
            """
            UPDATE document_ingestion_jobs
            SET worker_id = NULL, claimed_at = NULL, lease_expires_at = NULL,
                last_heartbeat_at = NULL, claim_version = claim_version + 1, updated_at = %s
            WHERE id = %s AND status = %s
            """,
            (now, job_id, str(row[1])),
        )
        return result.rowcount
