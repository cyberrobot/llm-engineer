from datetime import datetime, timezone

from assistant.maintenance.ingestion import (
    BatchResult,
    IngestionMaintenanceService,
    IngestionMaintenanceSettings,
    MaintenanceCategory,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self, batches, *, lock_acquired=True):
        self.batches = list(batches)
        self.lock_acquired = lock_acquired
        self.calls = []
        self.released = []

    def acquire_lock(self, category, timeout_seconds):
        self.calls.append(("lock", category, timeout_seconds))
        return self.lock_acquired

    def release_lock(self, category):
        self.released.append(category)

    def process_batch(self, category, *, settings, now, dry_run, cursor):
        self.calls.append(("batch", category, dry_run, cursor))
        return self.batches.pop(0) if self.batches else BatchResult()


class FailingRepository(FakeRepository):
    def process_batch(self, category, *, settings, now, dry_run, cursor):
        raise RuntimeError("fictional database failure")


def test_dry_run_uses_real_batch_selection_without_mutation_and_is_bounded():
    repository = FakeRepository(
        [
            BatchResult(candidates_found=2, records_skipped=2, next_cursor=(NOW, "2")),
            BatchResult(candidates_found=2, records_skipped=2, next_cursor=(NOW, "4")),
        ]
    )
    service = IngestionMaintenanceService(
        repository,
        settings=IngestionMaintenanceSettings(batch_size=2, max_batches=2),
        clock=lambda: NOW,
    )

    result = service.run(MaintenanceCategory.terminal_job_retention, dry_run=True)

    assert result.dry_run is True
    assert result.batches_processed == 2
    assert result.candidates_found == 4
    assert result.records_changed == 0
    assert result.records_skipped == 4
    assert result.stopped_reason == "max_batches_reached"
    assert repository.released == [MaintenanceCategory.terminal_job_retention]


def test_execute_reports_actual_changes_and_repeated_empty_run_converges():
    repository = FakeRepository([BatchResult(candidates_found=1, records_deleted=1), BatchResult()])
    service = IngestionMaintenanceService(
        repository,
        settings=IngestionMaintenanceSettings(batch_size=1),
        clock=lambda: NOW,
    )

    result = service.run(MaintenanceCategory.step_history_retention, dry_run=False)

    assert result.records_deleted == 1
    assert result.records_changed == 1
    assert result.stopped_reason == "no_candidates"

    second = service.run(MaintenanceCategory.step_history_retention, dry_run=False)
    assert second.candidates_found == 0
    assert second.records_changed == 0


def test_no_destructive_work_occurs_when_same_category_lock_is_unavailable():
    repository = FakeRepository([], lock_acquired=False)
    service = IngestionMaintenanceService(repository, clock=lambda: NOW)

    result = service.run(MaintenanceCategory.terminal_job_retention, dry_run=False)

    assert result.lock_acquired is False
    assert result.stopped_reason == "lock_unavailable"
    assert not [call for call in repository.calls if call[0] == "batch"]
    assert repository.released == []


def test_batch_failure_reports_no_partial_success_and_releases_lock():
    repository = FailingRepository([])
    service = IngestionMaintenanceService(repository, clock=lambda: NOW)

    result = service.run(MaintenanceCategory.terminal_job_retention, dry_run=False)

    assert result.records_changed == 0
    assert [error.code for error in result.errors] == ["ingestion_maintenance_process_failed"]
    assert result.stopped_reason == "process_error"
    assert repository.released == [MaintenanceCategory.terminal_job_retention]


def test_current_schema_representation_categories_are_explicit_non_destructive_boundaries():
    repository = FakeRepository([BatchResult(stopped_reason="not_applicable_current_schema")])
    service = IngestionMaintenanceService(repository, clock=lambda: NOW)

    result = service.run(MaintenanceCategory.superseded_representation_retention, dry_run=False)

    assert result.records_changed == 0
    assert result.stopped_reason == "not_applicable_current_schema"
