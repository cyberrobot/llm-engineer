import json
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from assistant.domain.assistant import (
    REDMOOR_ASSISTANT_ID,
    REDMOOR_ASSISTANT_SLUG,
    Assistant,
    AssistantStatus,
    AssistantVisibility,
)
from assistant.domain.assistant_behaviour import (
    DEFAULT_ASSISTANT_INSTRUCTIONS,
    DEFAULT_INPUT_PLACEHOLDER,
    DEFAULT_SUGGESTED_QUESTIONS,
    DEFAULT_WELCOME_MESSAGE,
)
from assistant.domain.assistant_repository import (
    AssistantAggregate,
    AssistantConcurrentUpdate,
    AssistantDeletionBlocked,
    AssistantDependencySummary,
    AssistantNotFound,
    AssistantRepository,
    DuplicateAssistantSlug,
)
from infrastructure.database.connection import get_connection

ASSISTANT_SLUG_UNIQUE_CONSTRAINT = "assistants_slug_key"


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

    def create(self, assistant: Assistant) -> Assistant:
        try:
            with self._connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO assistants (id,slug,name,status,visibility,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(assistant.id),
                        assistant.slug,
                        assistant.name,
                        assistant.status.value,
                        assistant.visibility.value,
                        assistant.created_at,
                        assistant.updated_at,
                    ),
                )
                cursor.execute(
                    """INSERT INTO assistant_behaviour_revisions
                       (assistant_id,revision,instructions,welcome_message,input_placeholder,
                        suggested_questions,created_at)
                       VALUES (%s,1,%s,%s,%s,%s::jsonb,%s)""",
                    (
                        str(assistant.id),
                        DEFAULT_ASSISTANT_INSTRUCTIONS,
                        DEFAULT_WELCOME_MESSAGE,
                        DEFAULT_INPUT_PLACEHOLDER,
                        json.dumps(DEFAULT_SUGGESTED_QUESTIONS),
                        assistant.created_at,
                    ),
                )
                cursor.execute(
                    """INSERT INTO assistant_behaviour_states
                       (assistant_id,draft_revision,published_revision,published_at,version,updated_at)
                       VALUES (%s,1,1,%s,1,%s)""",
                    (str(assistant.id), assistant.created_at, assistant.created_at),
                )
        except Exception as exc:
            if (
                getattr(exc, "sqlstate", None) == "23505"
                and getattr(getattr(exc, "diag", None), "constraint_name", None)
                == ASSISTANT_SLUG_UNIQUE_CONSTRAINT
            ):
                raise DuplicateAssistantSlug("Assistant slug already exists.") from exc
            raise
        return assistant

    def aggregate_counts(self) -> AssistantAggregate:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT count(assistants.id),
                          count(assistant_behaviour_states.published_revision)
                   FROM assistants
                   LEFT JOIN assistant_behaviour_states
                     ON assistant_behaviour_states.assistant_id = assistants.id"""
            )
            row = cursor.fetchone()
            return AssistantAggregate(total=int(row[0]), published=int(row[1]))

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: AssistantStatus | None = None,
        visibility: AssistantVisibility | None = None,
    ) -> tuple[list[Assistant], int]:
        clauses: list[str] = []
        params: list[object] = []
        if status is not None:
            clauses.append("status=%s")
            params.append(status.value)
        if visibility is not None:
            clauses.append("visibility=%s")
            params.append(visibility.value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM assistants" + where, tuple(params))
            total = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id,slug,name,status,visibility,created_at,updated_at FROM assistants"
                + where
                + " ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s",
                (*params, limit, offset),
            )
            rows = cursor.fetchall()
        return [_assistant(row) for row in rows], total

    def update(self, assistant: Assistant, *, expected_updated_at: datetime) -> Assistant:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE assistants SET name=%s,status=%s,visibility=%s,updated_at=%s WHERE id=%s AND updated_at=%s",
                (
                    assistant.name,
                    assistant.status.value,
                    assistant.visibility.value,
                    assistant.updated_at,
                    str(assistant.id),
                    expected_updated_at,
                ),
            )
            if cursor.rowcount == 0:
                cursor.execute("SELECT 1 FROM assistants WHERE id=%s", (str(assistant.id),))
                if cursor.fetchone() is None:
                    raise AssistantNotFound("Assistant not found.")
                raise AssistantConcurrentUpdate("Assistant was updated concurrently.")
        return assistant

    def dependency_count(self, assistant_id: UUID) -> int:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM knowledge_sources WHERE assistant_id=%s", (str(assistant_id),)
            )
            return cursor.fetchone()[0]

    def has_dependencies(self, assistant_id: UUID) -> bool:
        return self.dependency_summary(assistant_id).has_dependencies

    def dependency_summary(self, assistant_id: UUID) -> AssistantDependencySummary:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT COUNT(*) FROM knowledge_sources WHERE assistant_id=%s), "
                "EXISTS(SELECT 1 FROM knowledge_sources WHERE assistant_id=%s "
                "UNION ALL SELECT 1 FROM documents WHERE assistant_id=%s "
                "UNION ALL SELECT 1 FROM chunks WHERE assistant_id=%s)",
                (str(assistant_id),) * 4,
            )
            row = cursor.fetchone()
            return AssistantDependencySummary(
                knowledge_source_count=int(row[0]), has_dependencies=bool(row[1])
            )

    def delete(self, assistant_id: UUID) -> None:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM assistants WHERE id=%s FOR UPDATE", (str(assistant_id),))
            if cursor.fetchone() is None:
                raise AssistantNotFound("Assistant not found.")
            # These are the only direct assistant ownership paths. Ingestion jobs,
            # execution history, persistence/file receipts, fingerprints, and managed
            # source metadata are necessarily anchored by a document or source.
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM knowledge_sources WHERE assistant_id=%s UNION ALL SELECT 1 FROM documents WHERE assistant_id=%s UNION ALL SELECT 1 FROM chunks WHERE assistant_id=%s)",
                (str(assistant_id),) * 3,
            )
            if cursor.fetchone()[0]:
                raise AssistantDeletionBlocked("Assistant has dependent records.")
            cursor.execute("DELETE FROM assistants WHERE id=%s", (str(assistant_id),))

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


def _assistant(row: tuple[Any, ...]) -> Assistant:
    return Assistant(
        UUID(str(row[0])),
        str(row[1]),
        str(row[2]),
        AssistantStatus(row[3]),
        AssistantVisibility(row[4]),
        row[5],
        row[6],
    )


class InMemoryAssistantRepository(AssistantRepository):
    """Deterministic local/test assistant lookup with production-equivalent semantics."""

    def __init__(self, assistants: Iterable[Assistant] | None = None) -> None:
        if assistants is None:
            created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
            assistants = (
                Assistant(
                    id=REDMOOR_ASSISTANT_ID,
                    slug=REDMOOR_ASSISTANT_SLUG,
                    name="Redmoor Assistant",
                    status=AssistantStatus.active,
                    visibility=AssistantVisibility.public,
                    created_at=created_at,
                    updated_at=created_at,
                ),
            )
        self._by_id = {assistant.id: assistant for assistant in assistants}
        self._by_slug = {assistant.slug: assistant for assistant in self._by_id.values()}

    def get_by_id(self, assistant_id: UUID) -> Assistant:
        try:
            return self._by_id[assistant_id]
        except KeyError as exc:
            raise AssistantNotFound("Assistant not found.") from exc

    def aggregate_counts(self) -> AssistantAggregate:
        # In-memory Assistants use the same canonical published default as
        # persistence, and no unpublish operation exists.
        total = len(self._by_id)
        return AssistantAggregate(total=total, published=total)

    def create(self, assistant: Assistant) -> Assistant:
        if assistant.slug in self._by_slug:
            raise DuplicateAssistantSlug("Assistant slug already exists.")
        if assistant.id in self._by_id:
            raise ValueError("Assistant ID already exists.")
        self._by_id[assistant.id] = assistant
        self._by_slug[assistant.slug] = assistant
        return assistant

    def list(
        self,
        *,
        limit: int,
        offset: int,
        status: AssistantStatus | None = None,
        visibility: AssistantVisibility | None = None,
    ) -> tuple[list[Assistant], int]:
        values = [
            a
            for a in self._by_id.values()
            if (status is None or a.status is status)
            and (visibility is None or a.visibility is visibility)
        ]
        values.sort(key=lambda a: (a.created_at, a.id), reverse=True)
        return values[offset : offset + limit], len(values)

    def update(self, assistant: Assistant, *, expected_updated_at: datetime) -> Assistant:
        current = self.get_by_id(assistant.id)
        if current.updated_at != expected_updated_at:
            raise AssistantConcurrentUpdate("Assistant was updated concurrently.")
        self._by_id[assistant.id] = assistant
        self._by_slug[assistant.slug] = assistant
        return assistant

    def dependency_count(self, assistant_id: UUID) -> int:
        return 0

    def has_dependencies(self, assistant_id: UUID) -> bool:
        return False

    def dependency_summary(self, assistant_id: UUID) -> AssistantDependencySummary:
        return AssistantDependencySummary(
            knowledge_source_count=self.dependency_count(assistant_id),
            has_dependencies=self.has_dependencies(assistant_id),
        )

    def delete(self, assistant_id: UUID) -> None:
        assistant = self.get_by_id(assistant_id)
        del self._by_id[assistant_id]
        del self._by_slug[assistant.slug]

    def get_by_slug(self, slug: str) -> Assistant:
        normalized = slug.strip()
        if not normalized:
            raise AssistantNotFound("Assistant not found.")
        try:
            return self._by_slug[normalized]
        except KeyError as exc:
            raise AssistantNotFound("Assistant not found.") from exc
