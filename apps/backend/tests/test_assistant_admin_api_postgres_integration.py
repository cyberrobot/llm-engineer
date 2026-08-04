import os
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.assistant_admin import router
from assistant.api.dependencies import get_assistant_administration_service
from assistant.application.assistant_admin_service import AssistantAdministrationService
from assistant.infrastructure.repositories.assistant import PostgresAssistantRepository
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
    app.include_router(router)
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
