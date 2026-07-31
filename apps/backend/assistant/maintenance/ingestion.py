from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Protocol

from core.logging import configure_logging
from core.metrics import IngestionMaintenanceMetrics, ingestion_maintenance_metrics

logger = logging.getLogger(__name__)
MAINTENANCE_POLICY_VERSION = "9h-v1"


class MaintenanceCategory(str, Enum):
    terminal_job_retention = "TERMINAL_JOB_RETENTION"
    step_history_retention = "STEP_HISTORY_RETENTION"
    expired_lease_recovery = "EXPIRED_LEASE_RECOVERY"
    orphan_representation_cleanup = "ORPHAN_REPRESENTATION_CLEANUP"
    orphan_chunk_cleanup = "ORPHAN_CHUNK_CLEANUP"
    temporary_source_cleanup = "TEMPORARY_SOURCE_CLEANUP"
    inconsistent_state_reconciliation = "INCONSISTENT_STATE_RECONCILIATION"
    superseded_representation_retention = "SUPERSEDED_REPRESENTATION_RETENTION"


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Maintenance timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class IngestionMaintenanceSettings:
    completed_job_retention_days: int = 90
    failed_job_retention_days: int = 180
    cancelled_job_retention_days: int = 90
    step_history_retention_days: int = 90
    superseded_representation_retention_days: int = 30
    temporary_source_retention_hours: int = 24
    batch_size: int = 100
    max_batches: int = 20
    lock_timeout_seconds: float = 5
    stale_job_grace_seconds: int = 300
    execution_identity: str = "local-cli"

    def __post_init__(self) -> None:
        non_negative = (
            "completed_job_retention_days",
            "failed_job_retention_days",
            "cancelled_job_retention_days",
            "step_history_retention_days",
            "superseded_representation_retention_days",
            "temporary_source_retention_hours",
            "lock_timeout_seconds",
            "stale_job_grace_seconds",
        )
        for field_name in non_negative:
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name.upper()} must not be negative")
        for field_name in ("batch_size", "max_batches"):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name.upper()} must be greater than zero")
        if self.temporary_source_retention_hours == 0:
            raise ValueError("TEMPORARY_SOURCE_RETENTION_HOURS must be greater than zero")
        if not self.execution_identity.strip():
            raise ValueError("EXECUTION_IDENTITY must not be empty")

    def job_cutoffs(self, now: datetime) -> dict[str, datetime]:
        current = _require_aware(now)
        return {
            "completed": current - timedelta(days=self.completed_job_retention_days),
            "failed": current - timedelta(days=self.failed_job_retention_days),
            "cancelled": current - timedelta(days=self.cancelled_job_retention_days),
        }


Cursor = tuple[datetime, str]


@dataclass(frozen=True)
class MaintenanceError:
    code: str
    record_type: str | None = None
    record_id: str | None = None


@dataclass(frozen=True)
class MaintenanceFinding:
    record_type: str
    record_id: str
    reason_code: str
    recommended_action: str


@dataclass
class BatchResult:
    candidates_found: int = 0
    records_deleted: int = 0
    records_repaired: int = 0
    records_skipped: int = 0
    manual_review_count: int = 0
    errors: list[MaintenanceError] = field(default_factory=list)
    findings: list[MaintenanceFinding] = field(default_factory=list)
    next_cursor: Cursor | None = None
    stopped_reason: str | None = None


@dataclass
class MaintenanceResult:
    maintenance_category: MaintenanceCategory
    dry_run: bool
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int = 0
    batches_processed: int = 0
    candidates_found: int = 0
    records_changed: int = 0
    records_deleted: int = 0
    records_archived: int = 0
    records_repaired: int = 0
    records_skipped: int = 0
    manual_review_count: int = 0
    errors: list[MaintenanceError] = field(default_factory=list)
    findings: list[MaintenanceFinding] = field(default_factory=list)
    lock_acquired: bool = False
    stopped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["maintenance_category"] = self.maintenance_category.value
        for key in ("started_at", "completed_at"):
            if value[key] is not None:
                value[key] = value[key].isoformat()
        return value


class MaintenanceRepository(Protocol):
    def acquire_lock(self, category: MaintenanceCategory, timeout_seconds: float) -> bool: ...

    def release_lock(self, category: MaintenanceCategory) -> None: ...

    def process_batch(
        self,
        category: MaintenanceCategory,
        *,
        settings: IngestionMaintenanceSettings,
        now: datetime,
        dry_run: bool,
        cursor: Cursor | None,
    ) -> BatchResult: ...


class IngestionMaintenanceService:
    RUN_ALL_ORDER = (
        MaintenanceCategory.expired_lease_recovery,
        MaintenanceCategory.inconsistent_state_reconciliation,
        MaintenanceCategory.temporary_source_cleanup,
        MaintenanceCategory.step_history_retention,
        MaintenanceCategory.terminal_job_retention,
        MaintenanceCategory.superseded_representation_retention,
        MaintenanceCategory.orphan_representation_cleanup,
        MaintenanceCategory.orphan_chunk_cleanup,
    )

    def __init__(
        self,
        repository: MaintenanceRepository,
        *,
        settings: IngestionMaintenanceSettings | None = None,
        clock: Callable[[], datetime] | None = None,
        metrics: IngestionMaintenanceMetrics = ingestion_maintenance_metrics,
    ) -> None:
        self._repository = repository
        self._settings = settings or get_ingestion_maintenance_settings()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._metrics = metrics

    def run(self, category: MaintenanceCategory, *, dry_run: bool) -> MaintenanceResult:
        started_at = _require_aware(self._clock())
        result = MaintenanceResult(category, dry_run=dry_run, started_at=started_at)
        logger.info(
            "ingestion_maintenance_started",
            extra={
                "maintenance_category": category.value,
                "dry_run": dry_run,
                "execution_identity": self._settings.execution_identity,
                "maintenance_policy_version": MAINTENANCE_POLICY_VERSION,
                "batch_size": self._settings.batch_size,
                "max_batches": self._settings.max_batches,
            },
        )
        try:
            result.lock_acquired = self._repository.acquire_lock(
                category, self._settings.lock_timeout_seconds
            )
            if not result.lock_acquired:
                result.stopped_reason = "lock_unavailable"
                logger.warning(
                    "ingestion_maintenance_lock_unavailable",
                    extra={"maintenance_category": category.value, "dry_run": dry_run},
                )
            else:
                logger.info(
                    "ingestion_maintenance_lock_acquired",
                    extra={"maintenance_category": category.value, "dry_run": dry_run},
                )
                self._process_locked(result, started_at)
        except Exception:
            result.errors.append(MaintenanceError("ingestion_maintenance_process_failed"))
            result.stopped_reason = "process_error"
            logger.exception(
                "ingestion_maintenance_failed",
                extra={"maintenance_category": category.value, "dry_run": dry_run},
            )
        finally:
            if result.lock_acquired:
                try:
                    self._repository.release_lock(category)
                except Exception:
                    result.errors.append(
                        MaintenanceError("ingestion_maintenance_lock_release_failed")
                    )
                    result.stopped_reason = "process_error"
        return self._finish(result)

    def _process_locked(self, result: MaintenanceResult, started_at: datetime) -> None:
        category = result.maintenance_category
        cursor: Cursor | None = None
        for batch_number in range(1, self._settings.max_batches + 1):
            batch_started_at = time.monotonic()
            batch = self._repository.process_batch(
                category,
                settings=self._settings,
                now=started_at,
                dry_run=result.dry_run,
                cursor=cursor,
            )
            try:
                self._metrics.record_batch(
                    category.value, max(0, time.monotonic() - batch_started_at)
                )
            except Exception:
                logger.warning(
                    "ingestion_telemetry_export_failed",
                    extra={"maintenance_category": category.value, "reason": "batch_duration"},
                )
            if batch.stopped_reason is not None:
                result.stopped_reason = batch.stopped_reason
            if batch.candidates_found == 0:
                result.stopped_reason = result.stopped_reason or "no_candidates"
                break
            result.batches_processed += 1
            result.candidates_found += batch.candidates_found
            result.records_deleted += batch.records_deleted
            result.records_repaired += batch.records_repaired
            result.records_skipped += batch.records_skipped
            result.manual_review_count += batch.manual_review_count
            result.errors.extend(batch.errors)
            result.findings.extend(batch.findings)
            self._log_batch_findings(result, batch)
            cursor = batch.next_cursor
            logger.info(
                "ingestion_maintenance_batch_completed",
                extra={
                    "maintenance_category": category.value,
                    "dry_run": result.dry_run,
                    "batch_number": batch_number,
                    "candidates_found": batch.candidates_found,
                    "records_deleted": batch.records_deleted,
                    "records_repaired": batch.records_repaired,
                },
            )
            if (
                batch.stopped_reason is not None
                or batch.candidates_found < self._settings.batch_size
            ):
                result.stopped_reason = batch.stopped_reason or "batch_exhausted"
                break
        else:
            result.stopped_reason = "max_batches_reached"

    @staticmethod
    def _log_batch_findings(result: MaintenanceResult, batch: BatchResult) -> None:
        category = result.maintenance_category
        for finding in batch.findings:
            logger.warning(
                "ingestion_maintenance_manual_review_required",
                extra={
                    "maintenance_category": category.value,
                    "dry_run": result.dry_run,
                    "record_type": finding.record_type,
                    "record_id": finding.record_id,
                    "reason_code": finding.reason_code,
                },
            )
        for error in batch.errors:
            logger.error(
                error.code,
                extra={
                    "maintenance_category": category.value,
                    "dry_run": result.dry_run,
                    "record_type": error.record_type,
                    "record_id": error.record_id,
                    "reason_code": error.code,
                },
            )

    def run_all(self, *, dry_run: bool) -> list[MaintenanceResult]:
        return [self.run(category, dry_run=dry_run) for category in self.RUN_ALL_ORDER]

    def _finish(self, result: MaintenanceResult) -> MaintenanceResult:
        result.completed_at = _require_aware(self._clock())
        if result.started_at is not None:
            result.duration_ms = max(
                0, int((result.completed_at - result.started_at).total_seconds() * 1_000)
            )
        result.records_changed = (
            result.records_deleted + result.records_archived + result.records_repaired
        )
        outcome = (
            "error"
            if result.errors
            else "lock_unavailable"
            if not result.lock_acquired
            else "success"
        )
        try:
            self._metrics.record_result(result, outcome=outcome)
        except Exception:
            logger.warning(
                "ingestion_telemetry_export_failed",
                extra={"maintenance_category": result.maintenance_category.value},
            )
        logger.info(
            "ingestion_maintenance_completed",
            extra={
                "maintenance_category": result.maintenance_category.value,
                "dry_run": result.dry_run,
                "duration_ms": result.duration_ms,
                "result": outcome,
                "records_deleted": result.records_deleted,
                "records_repaired": result.records_repaired,
                "records_skipped": result.records_skipped,
                "manual_review_count": result.manual_review_count,
            },
        )
        return result


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def get_ingestion_maintenance_settings() -> IngestionMaintenanceSettings:
    return IngestionMaintenanceSettings(
        completed_job_retention_days=_env_int("INGESTION_COMPLETED_JOB_RETENTION_DAYS", 90),
        failed_job_retention_days=_env_int("INGESTION_FAILED_JOB_RETENTION_DAYS", 180),
        cancelled_job_retention_days=_env_int("INGESTION_CANCELLED_JOB_RETENTION_DAYS", 90),
        step_history_retention_days=_env_int("INGESTION_STEP_HISTORY_RETENTION_DAYS", 90),
        superseded_representation_retention_days=_env_int(
            "INGESTION_SUPERSEDED_REPRESENTATION_RETENTION_DAYS", 30
        ),
        temporary_source_retention_hours=_env_int("INGESTION_TEMPORARY_SOURCE_RETENTION_HOURS", 24),
        batch_size=_env_int("INGESTION_MAINTENANCE_BATCH_SIZE", 100),
        max_batches=_env_int("INGESTION_MAINTENANCE_MAX_BATCHES", 20),
        lock_timeout_seconds=_env_float("INGESTION_MAINTENANCE_LOCK_TIMEOUT_SECONDS", 5),
        stale_job_grace_seconds=_env_int("INGESTION_MAINTENANCE_STALE_JOB_GRACE_SECONDS", 300),
        execution_identity=os.getenv(
            "INGESTION_MAINTENANCE_EXECUTION_IDENTITY", socket.gethostname()
        ).strip(),
    )


COMMAND_CATEGORIES = {
    "cleanup-jobs": MaintenanceCategory.terminal_job_retention,
    "cleanup-step-history": MaintenanceCategory.step_history_retention,
    "cleanup-superseded-representations": (MaintenanceCategory.superseded_representation_retention),
    "cleanup-orphans": MaintenanceCategory.orphan_chunk_cleanup,
    "cleanup-temp-sources": MaintenanceCategory.temporary_source_cleanup,
    "reconcile-stale-jobs": MaintenanceCategory.expired_lease_recovery,
    "repair-committed-jobs": MaintenanceCategory.inconsistent_state_reconciliation,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe ingestion operational maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("report", *COMMAND_CATEGORIES, "run-all"):
        child = subparsers.add_parser(command)
        mode = child.add_mutually_exclusive_group()
        mode.add_argument("--execute", action="store_true", help="Perform approved mutations")
        mode.add_argument("--dry-run", action="store_true", help="Report without mutation")
        child.add_argument("--json", action="store_true", help="Print structured JSON")
    return parser


def build_service() -> IngestionMaintenanceService:
    from assistant.maintenance.repository import PostgresIngestionMaintenanceRepository

    return IngestionMaintenanceService(PostgresIngestionMaintenanceRepository())


def _print_results(results: Sequence[MaintenanceResult], *, structured: bool) -> None:
    values = [result.to_dict() for result in results]
    if structured:
        print(json.dumps(values[0] if len(values) == 1 else values, separators=(",", ":")))
        return
    for result in results:
        print(
            f"{result.maintenance_category.value}: dry_run={str(result.dry_run).lower()} "
            f"candidates={result.candidates_found} changed={result.records_changed} "
            f"manual_review={result.manual_review_count} stopped={result.stopped_reason}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    dry_run = not args.execute
    try:
        service = build_service()
        if args.command in {"report", "run-all"}:
            results = service.run_all(dry_run=True if args.command == "report" else dry_run)
        elif args.command == "cleanup-orphans":
            results = [
                service.run(MaintenanceCategory.orphan_representation_cleanup, dry_run=dry_run),
                service.run(MaintenanceCategory.orphan_chunk_cleanup, dry_run=dry_run),
            ]
        else:
            results = [service.run(COMMAND_CATEGORIES[args.command], dry_run=dry_run)]
    except (RuntimeError, ValueError):
        logger.exception("ingestion_maintenance_failed")
        return 2
    _print_results(results, structured=args.json)
    return 1 if any(result.errors for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
