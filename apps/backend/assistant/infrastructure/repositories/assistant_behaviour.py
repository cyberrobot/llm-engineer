import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from assistant.domain.assistant_behaviour import (
    AssistantBehaviourRevision,
    AssistantBehaviourState,
    default_behaviour_revision,
)
from assistant.domain.assistant_behaviour_repository import (
    AssistantBehaviourNotFound,
    AssistantBehaviourPublishConflict,
    AssistantBehaviourRepository,
    AssistantBehaviourUpdateConflict,
)
from assistant.domain.assistant_repository import AssistantNotFound, AssistantRepository
from infrastructure.database.connection import get_connection


@dataclass(frozen=True, slots=True)
class _BehaviourStateRow:
    assistant_id: UUID
    draft_revision: int
    published_revision: int | None
    published_at: datetime | None
    version: int
    updated_at: datetime


class _AssistantBehaviourInvariantError(RuntimeError):
    pass


class PostgresAssistantBehaviourRepository(AssistantBehaviourRepository):
    def __init__(self, connection_factory: Callable[[], Any] = get_connection) -> None:
        self._connection_factory = connection_factory

    def get_state(self, assistant_id: UUID) -> AssistantBehaviourState:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            state = self._read_state(cursor, assistant_id)
        return state

    def get_published(self, assistant_id: UUID) -> AssistantBehaviourRevision:
        state = self.get_state(assistant_id)
        if state.published is None:
            raise AssistantBehaviourNotFound("Assistant has no published behaviour.")
        return state.published

    def save_draft(
        self,
        assistant_id: UUID,
        *,
        expected_token: str,
        instructions: str,
        welcome_message: str,
        input_placeholder: str,
        suggested_questions: tuple[str, ...],
        at: datetime,
    ) -> AssistantBehaviourState:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            state = self._read_state(cursor, assistant_id, lock=True)
            if expected_token != state.concurrency_token:
                raise AssistantBehaviourUpdateConflict(
                    "Assistant behaviour was updated concurrently."
                )
            candidate = AssistantBehaviourRevision(
                assistant_id,
                state.draft.revision + 1,
                instructions,
                welcome_message,
                input_placeholder,
                suggested_questions,
                at,
            )
            if candidate.same_content_as(state.draft):
                return state
            cursor.execute(
                """INSERT INTO assistant_behaviour_revisions
                   (assistant_id,revision,instructions,welcome_message,input_placeholder,
                    suggested_questions,created_at)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                (
                    str(assistant_id),
                    candidate.revision,
                    candidate.instructions,
                    candidate.welcome_message,
                    candidate.input_placeholder,
                    json.dumps(candidate.suggested_questions, ensure_ascii=False),
                    candidate.created_at,
                ),
            )
            cursor.execute(
                """UPDATE assistant_behaviour_states
                   SET draft_revision=%s,version=version+1,updated_at=%s
                   WHERE assistant_id=%s""",
                (candidate.revision, at, str(assistant_id)),
            )
            return self._read_state(cursor, assistant_id)

    def publish(
        self,
        assistant_id: UUID,
        *,
        expected_token: str,
        draft_revision: int,
        at: datetime,
    ) -> AssistantBehaviourState:
        with self._connection_factory() as connection, connection.cursor() as cursor:
            state = self._read_state(cursor, assistant_id, lock=True)
            if (
                state.draft.revision == draft_revision
                and state.published is not None
                and state.published.revision == draft_revision
            ):
                return state
            if expected_token != state.concurrency_token or state.draft.revision != draft_revision:
                raise AssistantBehaviourPublishConflict(
                    "The requested draft is no longer the current saved draft."
                )
            cursor.execute(
                """UPDATE assistant_behaviour_states
                   SET published_revision=%s,published_at=%s,version=version+1,updated_at=%s
                   WHERE assistant_id=%s""",
                (draft_revision, at, at, str(assistant_id)),
            )
            return self._read_state(cursor, assistant_id)

    @staticmethod
    def _read_state_row(cursor: Any, assistant_id: UUID, *, lock: bool) -> _BehaviourStateRow:
        cursor.execute(
            """SELECT s.assistant_id,s.draft_revision,s.published_revision,s.published_at,
                      s.version,s.updated_at
               FROM assistant_behaviour_states s
               WHERE s.assistant_id=%s"""
            + (" FOR UPDATE" if lock else ""),
            (str(assistant_id),),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute("SELECT 1 FROM assistants WHERE id=%s", (str(assistant_id),))
            if cursor.fetchone() is None:
                raise AssistantNotFound("Assistant not found.")
            raise AssistantBehaviourNotFound("Assistant behaviour was not initialized.")
        return _BehaviourStateRow(
            UUID(str(row[0])),
            int(row[1]),
            int(row[2]) if row[2] is not None else None,
            row[3],
            int(row[4]),
            row[5],
        )

    @staticmethod
    def _read_revision(
        cursor: Any, assistant_id: UUID, revision: int
    ) -> AssistantBehaviourRevision:
        cursor.execute(
            """SELECT instructions,welcome_message,input_placeholder,
                      suggested_questions,created_at
               FROM assistant_behaviour_revisions
               WHERE assistant_id=%s AND revision=%s""",
            (str(assistant_id), revision),
        )
        row = cursor.fetchone()
        if row is None:
            raise _AssistantBehaviourInvariantError(
                "Assistant behaviour state references a missing immutable revision "
                f"(assistant_id={assistant_id}, revision={revision})."
            )
        return AssistantBehaviourRevision(
            assistant_id,
            revision,
            str(row[0]),
            str(row[1]),
            str(row[2]),
            tuple(row[3]),
            row[4],
        )

    @classmethod
    def _hydrate_state(cls, cursor: Any, state_row: _BehaviourStateRow) -> AssistantBehaviourState:
        draft = cls._read_revision(cursor, state_row.assistant_id, state_row.draft_revision)
        published = (
            cls._read_revision(cursor, state_row.assistant_id, state_row.published_revision)
            if state_row.published_revision is not None
            else None
        )
        return AssistantBehaviourState(
            state_row.assistant_id,
            draft,
            published,
            state_row.published_at,
            state_row.version,
            state_row.updated_at,
        )

    @classmethod
    def _read_state(
        cls, cursor: Any, assistant_id: UUID, *, lock: bool = False
    ) -> AssistantBehaviourState:
        state_row = cls._read_state_row(cursor, assistant_id, lock=lock)
        return cls._hydrate_state(cursor, state_row)


class InMemoryAssistantBehaviourRepository(AssistantBehaviourRepository):
    def __init__(self, assistants: AssistantRepository) -> None:
        self._assistants = assistants
        self._states: dict[UUID, AssistantBehaviourState] = {}

    def _state(self, assistant_id: UUID) -> AssistantBehaviourState:
        self._assistants.get_by_id(assistant_id)
        if assistant_id not in self._states:
            assistant = self._assistants.get_by_id(assistant_id)
            revision = default_behaviour_revision(assistant_id, created_at=assistant.created_at)
            self._states[assistant_id] = AssistantBehaviourState(
                assistant_id, revision, revision, assistant.created_at, 1, assistant.created_at
            )
        return self._states[assistant_id]

    def get_state(self, assistant_id: UUID) -> AssistantBehaviourState:
        return self._state(assistant_id)

    def get_published(self, assistant_id: UUID) -> AssistantBehaviourRevision:
        published = self._state(assistant_id).published
        if published is None:
            raise AssistantBehaviourNotFound("Assistant has no published behaviour.")
        return published

    def save_draft(
        self,
        assistant_id: UUID,
        *,
        expected_token: str,
        instructions: str,
        welcome_message: str,
        input_placeholder: str,
        suggested_questions: tuple[str, ...],
        at: datetime,
    ) -> AssistantBehaviourState:
        state = self._state(assistant_id)
        if expected_token != state.concurrency_token:
            raise AssistantBehaviourUpdateConflict("Assistant behaviour was updated concurrently.")
        candidate = AssistantBehaviourRevision(
            assistant_id,
            state.draft.revision + 1,
            instructions,
            welcome_message,
            input_placeholder,
            suggested_questions,
            at,
        )
        if candidate.same_content_as(state.draft):
            return state
        result = AssistantBehaviourState(
            assistant_id, candidate, state.published, state.published_at, state.version + 1, at
        )
        self._states[assistant_id] = result
        return result

    def publish(
        self,
        assistant_id: UUID,
        *,
        expected_token: str,
        draft_revision: int,
        at: datetime,
    ) -> AssistantBehaviourState:
        state = self._state(assistant_id)
        if state.published is not None and (
            state.draft.revision == draft_revision == state.published.revision
        ):
            return state
        if expected_token != state.concurrency_token or state.draft.revision != draft_revision:
            raise AssistantBehaviourPublishConflict(
                "The requested draft is no longer the current saved draft."
            )
        result = AssistantBehaviourState(
            assistant_id, state.draft, state.draft, at, state.version + 1, at
        )
        self._states[assistant_id] = result
        return result
