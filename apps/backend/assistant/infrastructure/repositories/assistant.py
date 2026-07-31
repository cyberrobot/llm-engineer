from collections.abc import Callable
from typing import Any
from uuid import UUID

from assistant.domain.assistant import Assistant, AssistantStatus, AssistantVisibility
from assistant.domain.assistant_repository import AssistantNotFound, AssistantRepository
from infrastructure.database.connection import get_connection


class PostgresAssistantRepository(AssistantRepository):
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def get_by_id(self, assistant_id: UUID) -> Assistant:
        return self._get(str(assistant_id), by_slug=False)

    def get_by_slug(self, slug: str) -> Assistant:
        normalized = slug.strip()
        if not normalized:
            raise AssistantNotFound("Assistant not found.")
        return self._get(normalized, by_slug=True)

    def _get(self, value: str, *, by_slug: bool) -> Assistant:
        query = (
            """SELECT id, slug, name, status, visibility, created_at, updated_at
               FROM assistants WHERE slug = %s"""
            if by_slug
            else """SELECT id, slug, name, status, visibility, created_at, updated_at
                     FROM assistants WHERE id = %s"""
        )
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, (value,))
            row = cursor.fetchone()
        if row is None:
            raise AssistantNotFound("Assistant not found.")
        return Assistant(
            id=UUID(str(row[0])),
            slug=str(row[1]),
            name=str(row[2]),
            status=AssistantStatus(row[3]),
            visibility=AssistantVisibility(row[4]),
            created_at=row[5],
            updated_at=row[6],
        )
