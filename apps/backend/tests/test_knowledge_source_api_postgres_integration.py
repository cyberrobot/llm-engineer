import os
from uuid import UUID

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role
from assistant.api.dependencies import get_knowledge_source_service
from assistant.api.knowledge_sources import router
from assistant.application.knowledge_source_service import KnowledgeSourceService
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository
from assistant.infrastructure.repositories.knowledge_source import PostgresKnowledgeSourceRepository
from core.config import DATABASE_URL
from core.exceptions import register_exception_handlers
from infrastructure.database.connection import get_connection, init_db

ORIGIN = "http://localhost:5173"


def _require_database() -> None:
    if not DATABASE_URL:
        if os.getenv("KNOWLEDGE_SOURCE_POSTGRES_REQUIRED") == "true":
            pytest.fail("DATABASE_URL is required for knowledge-source PostgreSQL tests")
        pytest.skip("DATABASE_URL is not configured")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as connection:
            connection.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        if os.getenv("KNOWLEDGE_SOURCE_POSTGRES_REQUIRED") == "true":
            pytest.fail(f"Required PostgreSQL test database is unavailable: {exc}")
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")


def test_database_backed_api_lifecycle(monkeypatch):
    _require_database()
    monkeypatch.setenv("ADMIN_TRUSTED_ORIGINS", ORIGIN)
    init_db()
    service = KnowledgeSourceService(
        PostgresKnowledgeSourceRepository(), PostgresAssistantRepository()
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_knowledge_source_service] = lambda: service
    app.dependency_overrides[require_administrator_role] = lambda: object()
    client = TestClient(app)
    base = f"/admin/assistants/{REDMOOR_ASSISTANT_ID}/knowledge-sources"
    document_id: str | None = None

    try:
        untrusted = client.post(
            base,
            json={
                "source_type": "direct_text",
                "name": "Database-backed guide",
                "direct_text": "Protected fictional database-backed guidance.",
            },
        )
        assert untrusted.status_code == 403

        created = client.post(
            base,
            headers={"Origin": ORIGIN},
            json={
                "source_type": "direct_text",
                "name": "Database-backed guide",
                "direct_text": "Protected fictional database-backed guidance.",
            },
        )
        assert created.status_code == 202
        payload = created.json()
        source_id = UUID(payload["id"])
        document_id = payload["document_id"]
        assert payload["direct_text"] == "Protected fictional database-backed guidance."

        listed = client.get(base)
        detailed = client.get(f"{base}/{source_id}")
        assert listed.status_code == detailed.status_code == 200
        assert (
            next(item for item in listed.json()["items"] if item["id"] == str(source_id))[
                "direct_text"
            ]
            is None
        )
        assert detailed.json()["direct_text"] == payload["direct_text"]

        for state in ("disabled", "enabled"):
            updated = client.patch(
                f"{base}/{source_id}",
                headers={"Origin": ORIGIN},
                json={"retrieval_state": state},
            )
            assert updated.status_code == 200
            assert updated.json()["retrieval_state"] == state

        active_delete = client.delete(f"{base}/{source_id}", headers={"Origin": ORIGIN})
        assert active_delete.status_code == 409
        assert active_delete.json()["detail"]["code"] == "active_ingestion"

        with get_connection() as connection:
            stored = connection.execute(
                """SELECT knowledge_sources.name, documents.retrieval_state
                   FROM knowledge_sources JOIN documents
                     ON documents.id = knowledge_sources.document_id
                   WHERE knowledge_sources.id = %s""",
                (str(source_id),),
            ).fetchone()
            assert stored == ("Database-backed guide", "enabled")
            connection.execute(
                """UPDATE document_ingestion_jobs
                   SET status='completed', started_at=NOW(), completed_at=NOW(), updated_at=NOW()
                   WHERE document_id=%s""",
                (document_id,),
            )

        deleted = client.delete(f"{base}/{source_id}", headers={"Origin": ORIGIN})
        missing = client.get(f"{base}/{source_id}")
        assert deleted.status_code == 204
        assert missing.status_code == 404
        with get_connection() as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM documents WHERE id=%s", (document_id,)
                ).fetchone()[0]
                == 0
            )
    finally:
        if document_id is not None:
            with get_connection() as connection:
                connection.execute(
                    "DELETE FROM ingestion_persistence_results WHERE document_id=%s",
                    (document_id,),
                )
                connection.execute("DELETE FROM documents WHERE id=%s", (document_id,))
