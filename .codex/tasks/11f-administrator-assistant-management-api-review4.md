PR 11F CI Fix — Isolate Expected Foreign-Key Failure in PostgreSQL Test

Repository state

Expected branch:

feature/11f-administrator-assistant-management-api

Base branch:

main

Pull request:

#62 — PR 11F — Add Administrator Assistant Management API

Use the existing backend worktree containing PR #62.

Do not create a new branch.

Do not change production assistant-management behaviour unless repository inspection proves the test exposed a real implementation defect.

Before editing:

- confirm the current branch is feature/11f-administrator-assistant-management-api;
- confirm the branch contains the latest PR #62 changes;
- inspect the failing GitHub Actions run;
- inspect the complete failing test;
- preserve all existing passing behaviour;
- avoid unrelated refactoring.

Read first

- AGENTS.md
- apps/backend/AGENTS.md
- apps/backend/tests/test_assistant_admin_repository_postgres_integration.py
- apps/backend/assistant/infrastructure/repositories/assistant.py
- apps/backend/infrastructure/database/connection.py or the canonical connection helper;
- existing PostgreSQL tests that use expected database exceptions;
- existing tests that use savepoints or nested transactions.

⸻

Failure summary

GitHub Actions reports one backend failure:

FAILED tests/test_assistant_admin_repository_postgres_integration.py::test_indirect_ingestion_records_are_covered_by_document_parent_dependency

Suite result:

1 failed, 970 passed

The test:

1. deletes the parent document;
2. confirms the associated ingestion job was cascade-deleted;
3. intentionally inserts an ingestion step for the now-missing job;
4. expects a PostgreSQL ForeignKeyViolation;
5. then attempts to delete the assistant.

The expected ForeignKeyViolation is caught by pytest.raises inside the same connection context that performed the document deletion.

PostgreSQL marks the transaction as aborted after the constraint violation. Because the exception is consumed inside the context block, the connection context manager later attempts to finish the failed transaction. The earlier document deletion is rolled back.

The assistant therefore still owns a document, and the production repository correctly raises:

AssistantDeletionBlocked: Assistant has dependent records.

This is a test transaction-boundary defect, not evidence that production deletion behaviour is incorrect.

⸻

Objective

Fix the failing PostgreSQL integration test by isolating the deliberately invalid insert from the transaction that removes the document and ingestion job.

The corrected test must prove all of the following:

- a document blocks assistant deletion;
- ingestion jobs and step executions are indirectly protected through the document parent;
- deleting the document cascades to its ingestion job;
- an ingestion step cannot exist without its ingestion job;
- the expected foreign-key failure does not roll back the successful document deletion;
- the assistant can be deleted after all dependencies are gone.

⸻

Required change

Update:

apps/backend/tests/test_assistant_admin_repository_postgres_integration.py

Target test:

test_indirect_ingestion_records_are_covered_by_document_parent_dependency

Required transaction structure

Separate the successful cleanup transaction from the intentionally failing transaction.

Use this sequence:

1. Open a database connection.
2. Delete the document.
3. Verify the ingestion job count is zero.
4. Exit the connection context so the deletion commits.
5. Open a new database connection for the deliberately invalid ingestion-step insert.
6. Assert that insert raises psycopg.errors.ForeignKeyViolation.
7. Allow that second transaction to roll back independently.
8. Call repository.delete(target.id).
9. Verify the assistant no longer exists.

Preferred shape:

with get_connection() as connection:
connection.execute(
"DELETE FROM documents WHERE id=%s",
(document_id,),
)
assert connection.execute(
"SELECT count(\*) FROM document_ingestion_jobs WHERE id=%s",
(job_id,),
).fetchone() == (0,)
with pytest.raises(psycopg.errors.ForeignKeyViolation):
with get_connection() as connection:
connection.execute(
"""
INSERT INTO ingestion_step_executions
(ingestion_job_id, step, attempt_number, status, started_at)
VALUES (%s, 'parse', 1, 'running', NOW())
""",
(job_id,),
)
repository.delete(target.id)
with pytest.raises(AssistantNotFound):
repository.get_by_id(target.id)

Use repository formatting and SQL style conventions.

Alternative

A nested transaction or savepoint may be used if the repository already has a clear established pattern:

with get_connection() as connection:
connection.execute(...)
with pytest.raises(psycopg.errors.ForeignKeyViolation):
with connection.transaction():
connection.execute(...)

Prefer the separate-connection approach unless savepoints are already the canonical test convention.

Do not manually issue ROLLBACK inside the production connection helper unless existing tests already require that pattern.

⸻

Test quality requirements

The corrected test must explicitly prove committed state before deleting the assistant.

After deleting the document, assert using a fresh connection:

with get_connection() as connection:
assert connection.execute(
"SELECT count(_) FROM documents WHERE id=%s",
(document_id,),
).fetchone() == (0,)
assert connection.execute(
"SELECT count(_) FROM document_ingestion_jobs WHERE id=%s",
(job_id,),
).fetchone() == (0,)

This prevents the test from passing while relying on uncommitted state.

After repository.delete(target.id), assert:

with pytest.raises(AssistantNotFound):
repository.get_by_id(target.id)

Retain cleanup in finally, and ensure cleanup remains safe when:

- setup fails;
- the document was already deleted;
- the assistant was already deleted;
- the expected foreign-key assertion fails.

Use DELETE ... WHERE operations that are harmless when no row exists.

⸻

Do not change

Do not change:

- PostgresAssistantRepository.delete;
- dependency queries;
- foreign-key definitions;
- cascade rules;
- application service behaviour;
- API behaviour;
- assistant deletion error mapping;
- knowledge-source behaviour;
- ingestion production code.

The current failure does not justify a production code change.

Do not weaken the test by removing the foreign-key assertion.

Do not remove the final successful assistant-deletion assertion.

Do not mark the test as skipped or xfail.

⸻

Acceptance criteria

- The expected foreign-key violation runs in an isolated transaction.
- The document deletion commits before the invalid insert is attempted.
- The associated ingestion job is confirmed deleted.
- The invalid ingestion-step insert still raises ForeignKeyViolation.
- The expected database error does not roll back the document deletion.
- Assistant deletion succeeds after dependencies are removed.
- A subsequent assistant lookup raises AssistantNotFound.
- Existing concurrency, rollback and dependency tests remain unchanged and pass.
- No production code is modified.
- No test is skipped or weakened.
- The full backend suite passes.
- The required knowledge-source PostgreSQL CI step runs after the main suite passes.

⸻

Verification commands

Run the failing test first:

cd apps/backend
DATABASE_URL="<postgresql-test-database>" \
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
python -m pytest \
 tests/test_assistant_admin_repository_postgres_integration.py::test_indirect_ingestion_records_are_covered_by_document_parent_dependency \
 -q

Run the complete assistant repository integration file:

DATABASE_URL="<postgresql-test-database>" \
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
python -m pytest \
 tests/test_assistant_admin_repository_postgres_integration.py \
 -q

Run the relevant PR 11F tests:

DATABASE_URL="<postgresql-test-database>" \
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
python -m pytest \
 tests/test_assistant_admin_api.py \
 tests/test_assistant_admin_api_postgres_integration.py \
 tests/test_assistant_admin_observability.py \
 tests/test_assistant_admin_repository_postgres_integration.py \
 tests/test_assistant_admin_service.py \
 tests/test_assistant_repository.py \
 tests/test_knowledge_source_api_postgres_integration.py \
 tests/test_public_chat.py \
 -q

Run the complete backend suite:

DATABASE_URL="<postgresql-test-database>" \
ASSISTANT_ADMIN_POSTGRES_REQUIRED=true \
KNOWLEDGE_SOURCE_POSTGRES_REQUIRED=true \
python -m pytest -q

Also run:

git diff --check

Use the repository’s actual Python executable or virtual environment path if different.

⸻

Completion report

Report:

- exact file changed;
- exact transaction-boundary change;
- exact commands run;
- pass, fail and skip counts;
- result of the previously failing test;
- result of the full backend suite;
- whether the required knowledge-source PostgreSQL step ran;
- confirmation that no production code was changed;
- any remaining CI failure.

Do not commit, push, merge or create another pull request.
