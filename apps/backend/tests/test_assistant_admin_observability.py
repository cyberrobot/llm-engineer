from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from assistant.application import assistant_admin_service as module
from assistant.application.assistant_admin_service import (
    AssistantAdministrationService,
    ProtectedAssistantDeletion,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import (
    AssistantConcurrentUpdate,
    AssistantDeletionBlocked,
    AssistantNotFound,
    DuplicateAssistantSlug,
)
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
ID = UUID("11111111-1111-4111-8111-111111111111")


class CapturingOperations:
    def __init__(self, *, fail: bool = False) -> None:
        self.labels_seen: list[dict[str, str]] = []
        self.fail = fail

    def labels(self, **labels):
        if self.fail:
            raise RuntimeError("metrics unavailable")
        self.labels_seen.append(labels)
        return self

    def inc(self) -> None:
        return None


def _service(repository=None, *, clock=NOW) -> AssistantAdministrationService:
    return AssistantAdministrationService(
        repository or InMemoryAssistantRepository(()), clock=lambda: clock, id_factory=lambda: ID
    )


def test_lifecycle_metrics_and_logs_have_bounded_safe_fields(monkeypatch, caplog) -> None:
    operations = CapturingOperations()
    monkeypatch.setattr(module.assistant_administration_metrics, "operations", operations)
    repository = InMemoryAssistantRepository(())
    subject = _service(repository)
    with caplog.at_level("INFO"):
        created = subject.create_assistant(slug="safe-slug", name="Sensitive assistant name")
        updated = _service(repository, clock=NOW + timedelta(seconds=1)).update_assistant(
            created.id,
            concurrency_token=created.updated_at,
            status=AssistantStatus.active,
            visibility=AssistantVisibility.public,
        )
        _service(repository, clock=NOW + timedelta(seconds=2)).update_assistant(
            created.id, concurrency_token=updated.updated_at, status=AssistantStatus.inactive
        )
        subject.delete_assistant(created.id)

    assert operations.labels_seen == [
        {"operation": "create", "outcome": "success"},
        {"operation": "update", "outcome": "success"},
        {"operation": "update", "outcome": "success"},
        {"operation": "delete", "outcome": "success"},
    ]
    events = {record.message for record in caplog.records}
    assert {
        "assistant_created",
        "assistant_updated",
        "assistant_activated",
        "assistant_deactivated",
        "assistant_visibility_changed",
        "assistant_deleted",
    } <= events
    serialized = " ".join(str(record.__dict__) for record in caplog.records)
    for secret in (
        "Sensitive assistant name",
        "cookie",
        "session token",
        "authorization",
        "document content",
        "chunk text",
        "embedding",
    ):
        assert secret not in serialized


@pytest.mark.parametrize(
    ("operation", "error", "outcome"),
    [
        ("create", DuplicateAssistantSlug("duplicate"), "conflict"),
        ("create", RuntimeError("failure"), "failure"),
        ("update", AssistantConcurrentUpdate("stale"), "conflict"),
        ("update", AssistantNotFound("missing"), "not_found"),
        ("update", RuntimeError("failure"), "failure"),
        ("delete", AssistantDeletionBlocked("blocked"), "conflict"),
        ("delete", AssistantNotFound("missing"), "not_found"),
        ("delete", RuntimeError("failure"), "failure"),
    ],
)
def test_repository_outcomes_emit_expected_metric(monkeypatch, operation, error, outcome) -> None:
    operations = CapturingOperations()
    monkeypatch.setattr(module.assistant_administration_metrics, "operations", operations)

    class Repository(InMemoryAssistantRepository):
        def create(self, assistant):
            if operation == "create":
                raise error
            return super().create(assistant)

        def update(self, assistant, *, expected_updated_at):
            if operation == "update":
                raise error
            return super().update(assistant, expected_updated_at=expected_updated_at)

        def delete(self, assistant_id):
            if operation == "delete":
                raise error
            return super().delete(assistant_id)

    repository = Repository(())
    subject = _service(repository)
    created = None
    if operation != "create":
        created = subject.create_assistant(slug="safe", name="Safe")
        operations.labels_seen.clear()

    def call() -> None:
        if operation == "create":
            subject.create_assistant(slug="safe", name="Safe")
        elif operation == "update":
            assert created is not None
            subject.update_assistant(
                created.id, concurrency_token=created.updated_at, name="Updated"
            )
        else:
            assert created is not None
            subject.delete_assistant(created.id)

    with pytest.raises(type(error)):
        call()
    assert operations.labels_seen == [{"operation": operation, "outcome": outcome}]


def test_protected_delete_and_detail_not_found_are_measured(monkeypatch) -> None:
    operations = CapturingOperations()
    monkeypatch.setattr(module.assistant_administration_metrics, "operations", operations)
    subject = _service()
    with pytest.raises(ProtectedAssistantDeletion):
        subject.delete_assistant(REDMOOR_ASSISTANT_ID)
    with pytest.raises(AssistantNotFound):
        subject.get_assistant(ID)
    assert operations.labels_seen == [
        {"operation": "delete", "outcome": "conflict"},
        {"operation": "detail", "outcome": "not_found"},
    ]


def test_metric_and_logging_failures_never_replace_business_result(monkeypatch) -> None:
    monkeypatch.setattr(
        module.assistant_administration_metrics, "operations", CapturingOperations(fail=True)
    )
    monkeypatch.setattr(
        module.logger,
        "info",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("logging unavailable")),
    )
    assert _service().create_assistant(slug="safe", name="Safe").slug == "safe"

    class FailingRepository(InMemoryAssistantRepository):
        def create(self, assistant):
            raise DuplicateAssistantSlug("authoritative conflict")

    with pytest.raises(DuplicateAssistantSlug, match="authoritative conflict"):
        _service(FailingRepository(())).create_assistant(slug="safe", name="Safe")
