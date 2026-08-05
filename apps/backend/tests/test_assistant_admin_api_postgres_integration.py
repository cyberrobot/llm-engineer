import os
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.assistant_admin import router as assistant_router
from assistant.api.dependencies import (
    get_assistant_administration_service,
    get_knowledge_source_service,
)
from assistant.api.knowledge_sources import router as knowledge_source_router
from assistant.application.assistant_admin_service import AssistantAdministrationService
from assistant.application.knowledge_source_service import KnowledgeSourceService
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository
from assistant.infrastructure.repositories.knowledge_source import PostgresKnowledgeSourceRepository
from core.config import DATABASE_URL
from core.exceptions import register_exception_handlers
from infrastructure.database.connection import get_connection, init_db


def _require_database() -> None:
    if not DATABASE_URL:
        pytest.fail("DATABASE_URL is required for assistant administrator PostgreSQL tests")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if os.getenv("ASSISTANT_ADMIN_POSTGRES_REQUIRED") == "true":
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def test_api_concurrency_token_survives_postgres_json_round_trip() -> None:
    _require_database()
    init_db()
    repository = PostgresAssistantRepository()
    service = AssistantAdministrationService(repository)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(assistant_router)
    app.dependency_overrides[get_assistant_administration_service] = lambda: service
    app.dependency_overrides[require_administrator_role] = lambda: object()
    app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    client = TestClient(app)
    slug = f"api-token-{uuid4().hex}"
    assistant_id = None
    try:
        created = client.post("/admin/assistants", json={"slug": slug, "name": "Original"})
        assert created.status_code == 201
        assistant_id = created.json()["id"]

        detail = client.get(f"/admin/assistants/{assistant_id}")
        assert detail.status_code == 200
        first_token = detail.json()["concurrency_token"]

        updated = client.patch(
            f"/admin/assistants/{assistant_id}",
            json={"concurrency_token": first_token, "name": "Persisted"},
        )
        assert updated.status_code == 200
        second_token = updated.json()["concurrency_token"]
        assert second_token != first_token

        stale = client.patch(
            f"/admin/assistants/{assistant_id}",
            json={"concurrency_token": first_token, "name": "Must not persist"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "assistant_update_conflict"
        final = client.get(f"/admin/assistants/{assistant_id}")
        assert final.status_code == 200
        assert final.json()["name"] == "Persisted"
        assert final.json()["concurrency_token"] == second_token
    finally:
        if assistant_id is not None:
            with get_connection() as connection:
                connection.execute("DELETE FROM assistants WHERE id=%s", (assistant_id,))


def test_api_detail_tracks_real_knowledge_source_dependency(monkeypatch) -> None:
    _require_database()
    monkeypatch.setenv("ADMIN_TRUSTED_ORIGINS", "http://localhost:5173")
    init_db()
    assistant_repository = PostgresAssistantRepository()
    assistant_service = AssistantAdministrationService(assistant_repository)
    knowledge_source_service = KnowledgeSourceService(
        PostgresKnowledgeSourceRepository(), assistant_repository
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(assistant_router)
    app.include_router(knowledge_source_router)
    app.dependency_overrides[get_assistant_administration_service] = lambda: assistant_service
    app.dependency_overrides[get_knowledge_source_service] = lambda: knowledge_source_service
    app.dependency_overrides[require_administrator_role] = lambda: object()
    app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    client = TestClient(app)
    origin = {"Origin": "http://localhost:5173"}
    assistant_id = source_id = document_id = None
    try:
        created = client.post(
            "/admin/assistants",
            json={"slug": f"api-dependency-{uuid4().hex}", "name": "Dependency detail"},
        )
        assert created.status_code == 201
        assistant_id = created.json()["id"]

        detail = client.get(f"/admin/assistants/{assistant_id}")
        assert detail.status_code == 200
        assert detail.json()["knowledge_source_count"] == 0
        assert detail.json()["deletion_allowed"] is True

        source_base = f"/admin/assistants/{assistant_id}/knowledge-sources"
        source = client.post(
            source_base,
            headers=origin,
            json={
                "source_type": "direct_text",
                "name": "Deletion dependency",
                "direct_text": "A real source blocks deletion.",
            },
        )
        assert source.status_code == 202
        source_id = source.json()["id"]
        document_id = source.json()["document_id"]

        blocked_detail = client.get(f"/admin/assistants/{assistant_id}")
        assert blocked_detail.status_code == 200
        assert blocked_detail.json()["knowledge_source_count"] == 1
        assert blocked_detail.json()["deletion_allowed"] is False
        blocked_delete = client.delete(f"/admin/assistants/{assistant_id}")
        assert blocked_delete.status_code == 409
        assert blocked_delete.json()["detail"]["code"] == "assistant_has_dependencies"

        with get_connection() as connection:
            connection.execute(
                "UPDATE document_ingestion_jobs "
                "SET status='completed', started_at=NOW(), completed_at=NOW(), updated_at=NOW() "
                "WHERE document_id=%s",
                (document_id,),
            )
        removed = client.delete(f"{source_base}/{source_id}", headers=origin)
        assert removed.status_code == 204
        source_id = document_id = None

        unblocked_detail = client.get(f"/admin/assistants/{assistant_id}")
        assert unblocked_detail.status_code == 200
        assert unblocked_detail.json()["knowledge_source_count"] == 0
        assert unblocked_detail.json()["deletion_allowed"] is True
        deleted = client.delete(f"/admin/assistants/{assistant_id}")
        assert deleted.status_code == 204
        assistant_id = None
    finally:
        if document_id is not None:
            with get_connection() as connection:
                connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
        if assistant_id is not None:
            with get_connection() as connection:
                connection.execute("DELETE FROM assistants WHERE id=%s", (assistant_id,))
