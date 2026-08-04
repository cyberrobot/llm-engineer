from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from assistant.application.assistant_admin_service import (
    AssistantAdministrationService,
    EmptyAssistantUpdate,
    ProtectedAssistantDeletion,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import (
    AssistantConcurrentUpdate,
    AssistantDeletionBlocked,
    DuplicateAssistantSlug,
)
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository
from core.metrics import assistant_administration_metrics

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
ID = UUID("11111111-1111-4111-8111-111111111111")


def service(repository=None, now=NOW):
    return AssistantAdministrationService(
        repository or InMemoryAssistantRepository(()), clock=lambda: now, id_factory=lambda: ID
    )


def test_create_defaults_to_inactive_private_and_normalizes_name():
    created = service().create_assistant(slug="legal-review", name="  Legal ✓  ")
    assert (created.status, created.visibility, created.name) == (
        AssistantStatus.inactive,
        AssistantVisibility.private,
        "Legal ✓",
    )


def test_duplicate_slug_is_deterministic():
    subject = service()
    subject.create_assistant(slug="legal-review", name="Legal")
    with pytest.raises(DuplicateAssistantSlug):
        subject.create_assistant(slug="legal-review", name="Other")


def test_partial_update_uses_timestamp_compare_and_set():
    repository = InMemoryAssistantRepository(())
    subject = service(repository)
    created = subject.create_assistant(slug="legal-review", name="Legal")
    updated = service(repository, NOW + timedelta(seconds=1)).update_assistant(
        created.id, concurrency_token=created.updated_at, status=AssistantStatus.active
    )
    assert updated.status is AssistantStatus.active
    with pytest.raises(AssistantConcurrentUpdate):
        service(repository, NOW + timedelta(seconds=2)).update_assistant(
            created.id, concurrency_token=created.updated_at, visibility=AssistantVisibility.public
        )


def test_empty_update_and_redmoor_deletion_are_rejected():
    with pytest.raises(EmptyAssistantUpdate):
        service().update_assistant(ID, concurrency_token=NOW)
    with pytest.raises(ProtectedAssistantDeletion):
        service().delete_assistant(REDMOOR_ASSISTANT_ID)


def test_unused_assistant_can_be_deleted():
    subject = service()
    created = subject.create_assistant(slug="temporary", name="Temporary")
    subject.delete_assistant(created.id)
    assert subject.list_assistants(limit=10, offset=0)[1] == 0


def _metric(operation: str, outcome: str) -> float:
    return assistant_administration_metrics.operations.labels(
        operation=operation, outcome=outcome
    )._value.get()


def test_only_expected_create_and_update_conflicts_are_classified_as_conflicts():
    subject = service()
    subject.create_assistant(slug="legal-review", name="Legal")
    create_before = _metric("create", "conflict")
    with pytest.raises(DuplicateAssistantSlug):
        subject.create_assistant(slug="legal-review", name="Other")
    assert _metric("create", "conflict") == create_before + 1

    update_before = _metric("update", "conflict")
    with pytest.raises(AssistantConcurrentUpdate):
        subject.update_assistant(
            ID,
            concurrency_token=NOW - timedelta(seconds=1),
            status=AssistantStatus.active,
        )
    assert _metric("update", "conflict") == update_before + 1


def test_unexpected_repository_failure_is_not_mislabeled_as_conflict():
    class FailingRepository(InMemoryAssistantRepository):
        def create(self, assistant):
            raise RuntimeError("database unavailable")

    conflict_before = _metric("create", "conflict")
    failure_before = _metric("create", "failure")
    with pytest.raises(RuntimeError, match="database unavailable"):
        service(FailingRepository(())).create_assistant(slug="legal", name="Legal")
    assert _metric("create", "conflict") == conflict_before
    assert _metric("create", "failure") == failure_before + 1


def test_blocked_delete_emits_bounded_metric_and_safe_log(caplog):
    class DependentRepository(InMemoryAssistantRepository):
        def delete(self, assistant_id):
            raise AssistantDeletionBlocked("blocked")

    before = _metric("delete", "conflict")
    with caplog.at_level("INFO"):
        with pytest.raises(AssistantDeletionBlocked):
            service(DependentRepository(())).delete_assistant(ID)
    assert _metric("delete", "conflict") == before + 1
    record = next(
        record for record in caplog.records if record.message == "assistant_deletion_blocked"
    )
    assert record.assistant_id == str(ID)
    assert record.outcome_code == "dependencies"
    assert "cookie" not in record.__dict__
    assert "token" not in record.__dict__
    assert "assistant_name" not in record.__dict__


def test_telemetry_failures_do_not_change_successful_result(monkeypatch):
    class BrokenMetrics:
        def labels(self, **_labels):
            raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(assistant_administration_metrics, "operations", BrokenMetrics())
    created = service().create_assistant(slug="safe", name="Safe")
    assert created.slug == "safe"
