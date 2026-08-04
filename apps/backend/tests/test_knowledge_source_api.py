from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import (
    get_administrator_auth_service,
    require_administrator_role,
)
from admin_auth.service import AuthenticationRequired
from assistant.api.dependencies import get_knowledge_source_service
from assistant.api.knowledge_sources import router
from assistant.application.knowledge_source_service import (
    ActiveIngestionConflict,
    IdempotencyConflict,
    KnowledgeSourceNotFound,
    KnowledgeSourceView,
)
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, DocumentRetrievalState
from assistant.domain.document_ingestion_job import DocumentIngestionJob
from assistant.domain.knowledge_source import KnowledgeSource, KnowledgeSourceType
from core.exceptions import register_exception_handlers

ORIGIN = "http://localhost:5173"


def _view(source_type=KnowledgeSourceType.direct_text) -> KnowledgeSourceView:
    source = KnowledgeSource.create(
        assistant_id=REDMOOR_ASSISTANT_ID,
        source_type=source_type,
        name="Guide",
        direct_text="Fictional administrator guidance."
        if source_type is KnowledgeSourceType.direct_text
        else None,
        url="https://example.com/guide" if source_type is KnowledgeSourceType.url else None,
    )
    return KnowledgeSourceView(source, DocumentIngestionJob.create(source.document_id))


def _app(service: MagicMock, *, authenticated: bool = True) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_knowledge_source_service] = lambda: service
    if authenticated:
        app.dependency_overrides[require_administrator_role] = lambda: object()
    return app


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("ADMIN_TRUSTED_ORIGINS", ORIGIN)
    service = MagicMock()
    return TestClient(_app(service)), service


def test_knowledge_source_routes_require_authentication_and_reject_invalid_session(monkeypatch):
    monkeypatch.setenv("ADMIN_TRUSTED_ORIGINS", ORIGIN)
    service = MagicMock()
    app = _app(service, authenticated=False)
    authentication = MagicMock()
    authentication.authenticate.side_effect = AuthenticationRequired("invalid session")
    app.dependency_overrides[get_administrator_auth_service] = lambda: authentication
    client = TestClient(app)
    path = f"/admin/assistants/{REDMOOR_ASSISTANT_ID}/knowledge-sources"

    missing = client.get(path)
    client.cookies.set("redmoor_admin_session", "invalid-session")
    invalid = client.get(path)

    assert missing.status_code == invalid.status_code == 401
    assert missing.json()["detail"]["code"] == "authentication_required"
    assert invalid.json() == missing.json()
    service.list.assert_not_called()


def test_mutations_require_a_trusted_origin(api):
    client, service = api
    path = f"/admin/assistants/{REDMOOR_ASSISTANT_ID}/knowledge-sources"
    response = client.post(
        path,
        json={
            "source_type": "direct_text",
            "name": "Guide",
            "direct_text": "Fictional guidance.",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"
    service.create.assert_not_called()


def test_creation_direct_url_replay_and_idempotency_conflict_contract(api):
    client, service = api
    path = f"/admin/assistants/{REDMOOR_ASSISTANT_ID}/knowledge-sources"
    direct = _view()
    url = _view(KnowledgeSourceType.url)
    service.create.side_effect = [
        (direct, False),
        (url, False),
        (url, True),
        IdempotencyConflict("Idempotency key conflicts with another request."),
    ]

    created_direct = client.post(
        path,
        headers={"Origin": ORIGIN, "Idempotency-Key": "direct-key"},
        json={
            "source_type": "direct_text",
            "name": "Guide",
            "direct_text": direct.source.direct_text,
        },
    )
    created_url = client.post(
        path,
        headers={"Origin": ORIGIN, "Idempotency-Key": "url-key"},
        json={"source_type": "url", "name": "Guide", "url": url.source.url},
    )
    replay = client.post(
        path,
        headers={"Origin": ORIGIN, "Idempotency-Key": "url-key"},
        json={"source_type": "url", "name": "Guide", "url": url.source.url},
    )
    conflict = client.post(
        path,
        headers={"Origin": ORIGIN, "Idempotency-Key": "url-key"},
        json={"source_type": "url", "name": "Other", "url": "https://example.com/other"},
    )

    assert created_direct.status_code == created_url.status_code == replay.status_code == 202
    assert created_direct.json()["direct_text"] == direct.source.direct_text
    assert created_url.json()["url"] == url.source.url
    assert created_url.json()["active_job_reused"] is False
    assert replay.json()["id"] == str(url.source.id)
    assert replay.json()["active_job_reused"] is True
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_key_conflict"


def test_list_detail_enable_disable_delete_and_cross_assistant_contract(api):
    client, service = api
    view = _view()
    base = f"/admin/assistants/{REDMOOR_ASSISTANT_ID}/knowledge-sources"
    detail_path = f"{base}/{view.source.id}"
    service.list.return_value = ([view], 1)
    service.get.return_value = view
    service.update.return_value = view

    listed = client.get(base)
    detail = client.get(detail_path)
    disabled = client.patch(
        detail_path,
        headers={"Origin": ORIGIN},
        json={"retrieval_state": "disabled"},
    )
    enabled = client.patch(
        detail_path,
        headers={"Origin": ORIGIN},
        json={"retrieval_state": "enabled"},
    )
    deleted = client.delete(detail_path, headers={"Origin": ORIGIN})

    assert listed.status_code == detail.status_code == disabled.status_code == enabled.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["direct_text"] is None
    assert detail.json()["direct_text"] == view.source.direct_text
    assert deleted.status_code == 204
    assert service.update.call_args_list[0].args[2] is DocumentRetrievalState.disabled
    assert service.update.call_args_list[1].args[2] is DocumentRetrievalState.enabled

    service.get.side_effect = KnowledgeSourceNotFound()
    other_assistant = uuid4()
    hidden = client.get(f"/admin/assistants/{other_assistant}/knowledge-sources/{view.source.id}")
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "knowledge_source_not_found"


def test_reingestion_replay_conflict_and_active_deletion_contract(api):
    client, service = api
    view = _view()
    base = f"/admin/assistants/{REDMOOR_ASSISTANT_ID}/knowledge-sources/{view.source.id}"
    service.reingest.side_effect = [
        (view, False),
        (view, True),
        IdempotencyConflict("Idempotency key conflicts with another request."),
    ]

    queued = client.post(
        f"{base}/reingestions", headers={"Origin": ORIGIN, "Idempotency-Key": "refresh"}
    )
    replay = client.post(
        f"{base}/reingestions", headers={"Origin": ORIGIN, "Idempotency-Key": "refresh"}
    )
    conflict = client.post(
        f"{base}/reingestions", headers={"Origin": ORIGIN, "Idempotency-Key": "conflict"}
    )
    service.delete.side_effect = ActiveIngestionConflict()
    active_delete = client.delete(base, headers={"Origin": ORIGIN})

    assert queued.status_code == replay.status_code == 202
    assert queued.json()["active_job_reused"] is False
    assert replay.json()["active_job_reused"] is True
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_key_conflict"
    assert active_delete.status_code == 409
    assert active_delete.json()["detail"]["code"] == "active_ingestion"
