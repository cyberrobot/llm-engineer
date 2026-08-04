from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from assistant.application.assistant_admin_service import (
    AssistantAdministrationService,
    EmptyAssistantUpdate,
    ProtectedAssistantDeletion,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import AssistantConcurrentUpdate, DuplicateAssistantSlug
from assistant.infrastructure.repositories.assistant import InMemoryAssistantRepository

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
