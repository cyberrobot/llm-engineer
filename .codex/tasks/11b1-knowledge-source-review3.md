Update Existing PR #60 — Complete Remaining Knowledge Source Hardening Requirements

Repository state

Existing branch

feature/11b1-knowledge-source-hardening

Existing pull request

PR #60 — Knowledge Source Management Hardening

This task updates the existing branch and pull request.

Do not:

- Create a new branch.
- Create a new pull request.
- Rebase the work onto a separate feature branch.
- Reimplement changes already present in PR #60.
- Expand the administrator API or introduce new end-user functionality.

The objective is to complete the small number of requirements that remain outstanding after the latest review of PR #60.

Prerequisites

Before changing code, confirm the current branch already contains:

- Assistant-scoped creation idempotency.
- Assistant-aware creation request hashes.
- Transaction-safe re-ingestion.
- Re-ingestion idempotency receipts.
- Direct assistant-and-URL repository lookup.
- One-to-one Knowledge Source and Document ownership.
- The one-active-ingestion-job database constraint.
- Migration diagnostics for pre-existing duplicate active jobs.
- Formal load_single_page() support in the website-loader port.
- Structured knowledge-source lifecycle logs.
- Knowledge-source metrics.
- Current repository, API, migration and concurrency tests.

If any of these are absent, stop and report the repository-state mismatch rather than silently rebuilding PR 11B.1.

Read first

Read:

- AGENTS.md
- apps/backend/AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/11b1-knowledge-source-hardening.md
- .codex/tasks/11b1-knowledge-source-review2.md
- apps/backend/docs/knowledge-source-management.md

Inspect the current PR diff and current test implementation before writing code.

Objective

Complete the remaining production-hardening evidence for Knowledge Source Management.

The current implementation is broadly correct. This task is primarily about proving the remaining persistence, retrieval, rollback and migration guarantees through realistic integration tests and making only the smallest production changes exposed by those tests.

The required outcomes are:

1. Prove retrieval state remains authoritative through real ingestion persistence.
2. Prove production retrieval honours disable and enable transitions.
3. Add re-ingestion transaction rollback coverage.
4. Add deletion rollback coverage where meaningful.
5. Complete the PostgreSQL database-constraint matrix.
6. Ensure required PostgreSQL tests execute in CI and cannot silently skip.
7. Keep the existing administrator API unchanged.

⸻

1. Replace the incomplete retrieval-state test

The current test directly marks an ingestion job as completed by updating the job row.

That does not exercise the final persistence boundary and does not prove that newly persisted chunks remain excluded from production retrieval.

Replace or supplement that test with a real integration test.

Required scenario

The test must use the production knowledge persistence and retrieval boundaries as far as existing test fixtures permit.

Perform this sequence:

1. Create a direct-text or URL knowledge source with retrieval enabled.
2. Persist an initial indexed representation using the real transactional persistence service.
3. Confirm the production retrieval service can return one or more chunks for that source.
4. Prepare a second ingestion representation for the same source and document.
5. Disable the Knowledge Source through KnowledgeSourceService.update().
6. Execute the real final persistence operation for the second ingestion.
7. Reload both:
   - Knowledge Source.
   - Canonical Document.
8. Confirm both remain disabled.
9. Query through the production retrieval service.
10. Confirm no chunks from that document are returned.
11. Re-enable the source through the production service.
12. Query through the production retrieval service again.
13. Confirm the already committed chunks are returned.
14. Confirm re-enabling did not:

- Create another ingestion job.
- Invoke the embedding provider.
- Rewrite the chunk representation.

Rules

Do not simulate persistence by only updating job status.

Do not test retrieval by only reading documents.retrieval_state.

Use the canonical production retrieval filtering path.

Mock only true external boundaries such as the embedding provider. Use realistic prepared embeddings and persistence commands through existing fixtures or adapters.

If the test exposes that final persistence overwrites retrieval state, fix the persistence implementation so the latest administrator-owned state remains authoritative.

Do not add retrieval state copied from stale ingestion context to final writes.

⸻

2. Re-ingestion rollback test

The re-ingestion transaction performs multiple durable effects:

- It may insert a new ingestion job.
- It may insert an idempotency receipt.
- It may reuse an existing active job.

Add a PostgreSQL integration test proving a failure between job creation and receipt completion rolls back all new work.

Required scenario

1. Create a Knowledge Source.
2. Complete its initial job so no active job exists.
3. Start a repository re-ingestion transaction.
4. Insert or schedule the new job using the production transaction method.
5. Force a controlled failure before the re-ingestion receipt is committed.
6. Exit the transaction with an exception.
7. Reload database state.

Verify:

- No new ingestion job remains.
- No knowledge_source_reingestion_requests row remains.
- The Knowledge Source is unchanged.
- The previous terminal job remains unchanged.
- A subsequent legitimate re-ingestion succeeds.

Test design

Prefer a controlled database failure, test-only repository fault injection at a database boundary, or a transaction-scoped constraint failure.

Do not mock the transaction object itself.

Do not change production semantics solely to make the test easy.

If a small injectable repository hook is necessary, keep it private, narrowly scoped and consistent with existing repository test conventions.

⸻

3. Deletion rollback coverage

The delete implementation relies on a document delete and database cascades.

Add a test proving the delete transaction is atomic.

Required scenario

Seed:

- Knowledge Source.
- Canonical Document.
- At least one terminal ingestion job.
- At least one persisted chunk.
- Any source-owned receipt rows that should cascade.

Force a failure within the same transaction after deletion work begins but before commit.

After rollback, verify all seeded records still exist and remain correctly linked.

The test must verify:

- Knowledge Source exists.
- Document exists.
- Chunks exist.
- Terminal ingestion history exists.
- Re-ingestion receipts remain consistent.
- Retrieval state is unchanged.

If the implementation performs deletion through one indivisible SQL statement and there is no realistic point for a controlled mid-operation failure, document that constraint clearly and instead verify rollback by executing deletion inside an outer transaction and deliberately raising before commit.

Do not add multi-stage deletion merely to manufacture a test point.

⸻

4. Complete PostgreSQL constraint coverage

Expand the real PostgreSQL migration tests so they directly exercise the database constraints introduced by PR 11B and PR 11B.1.

Creation idempotency

Verify:

- Duplicate creation_idempotency_key within one assistant is rejected.
- The same key in two different assistants is allowed.

URL uniqueness

Verify:

- Duplicate normalized URL within one assistant is rejected.
- The same normalized URL in two different assistants is allowed.

Retrieval state

Verify invalid retrieval-state values are rejected.

Valid values must remain:

- enabled
- disabled

Source payload constraints

Verify PostgreSQL rejects:

- A direct_text source with no direct text.
- A direct_text source with a URL.
- A URL source with direct text.
- A URL source with no normalized URL.
- An empty or whitespace-only name.
- An invalid content-version hash.

Document ownership

Verify two Knowledge Sources cannot reference the same document.

Active ingestion jobs

Verify:

- Two queued/running jobs for one document are rejected after migration.
- One active job plus multiple completed, failed or cancelled jobs is allowed.
- Multiple terminal jobs for one document are allowed.

Re-ingestion receipts

Verify:

- The same idempotency key is rejected for two receipts within one assistant.
- The same key is allowed across assistants.
- Invalid source, assistant or ingestion-job references are rejected.
- Receipt deletion behaviour follows documented foreign-key rules.

Use savepoints around expected constraint failures so the full test transaction remains usable.

⸻

5. Improve concurrency test determinism

The current concurrency tests use ThreadPoolExecutor, but they do not deliberately align both operations at the critical transaction boundary.

Strengthen the tests using an existing repository concurrency pattern or a controlled barrier.

Concurrent source creation

Ensure both requests reach the create transaction before either completes.

Verify:

- One Knowledge Source.
- One Document.
- One active ingestion job.
- Both callers receive the same canonical result.
- No raw UniqueViolation escapes.

Concurrent re-ingestion

Ensure both requests attempt to re-ingest after the previous active job is terminal.

Verify:

- One new active job.
- Both callers receive the same job.
- Exactly one caller receives a newly-created outcome.
- The other receives a reused outcome.
- One idempotency receipt exists for a shared key.
- No transaction or database exception escapes.

Do not rely only on arbitrary sleeps.

Use barriers, controlled locks, events or explicit connection coordination.

⸻

6. Add at least one database-backed API integration test

The existing API tests mock KnowledgeSourceService. Keep those tests for transport mapping, but add at least one full-stack API integration test using:

- The real FastAPI route.
- Real authentication dependency or a realistic authenticated dependency override.
- Real Knowledge Source service.
- Real PostgreSQL repository.
- Real transaction behaviour.
- Fake only true external provider boundaries.

Required flow

Through HTTP:

1. Create a direct-text source.
2. List sources.
3. Read source detail.
4. Disable retrieval.
5. Re-enable retrieval.
6. Attempt deletion while a job is active and receive 409.
7. Complete the job.
8. Delete successfully.
9. Confirm a later detail request returns 404.

Also verify:

- Direct text is absent from list output.
- Direct text is present in protected detail output.
- Mutating requests require trusted origin.
- The resulting database records match the response.

Clean up all generated rows.

⸻

7. Verify observability outcomes more precisely

Extend current observability tests where necessary.

Verify each intended lifecycle result increments exactly one relevant counter:

- Creation.
- Creation replay.
- Duplicate URL reuse.
- Re-ingestion created.
- Re-ingestion replay.
- Retrieval enabled.
- Retrieval disabled.
- Deletion.
- Active-ingestion deletion rejection, if a dedicated metric exists.

Verify failed or rolled-back operations do not increment success counters.

Capture structured logs and verify they do not contain:

- Direct-text source body.
- Full URL query strings if they may contain sensitive values.
- HTML.
- Chunk text.
- Embeddings.
- Cookies.
- Administrator tokens.
- Raw database errors.
- Provider payloads.

The log records should contain safe identifiers and outcome fields only.

⸻

8. Make PostgreSQL tests mandatory in CI

The integration tests currently skip when DATABASE_URL is unavailable.

That may remain acceptable for an individual developer’s local environment, but PR validation must not pass while the required PostgreSQL tests are skipped.

Inspect the existing GitHub Actions workflow.

Ensure the backend test job:

- Starts a PostgreSQL instance compatible with the application schema.
- Enables pgvector if required by the broader backend suite.
- Exposes DATABASE_URL.
- Runs the knowledge-source PostgreSQL tests.
- Fails if those tests skip due to missing database configuration.

Use the repository’s existing CI database conventions if present.

Do not introduce a second CI test architecture.

A suitable approach is a small test helper that fails rather than skips when a CI environment variable is set, while preserving optional local skips. Reuse an existing repository pattern if one exists.

Document the exact CI behaviour.

⸻

9. Migration diagnostic bounds

The migration currently aggregates every document ID with duplicate active jobs into one error string.

Bound the diagnostic to avoid oversized migration failures.

The failure should report:

- Total number of affected documents.
- A deterministic sample of the first limited number of document IDs, such as 20.
- An indication when additional IDs are omitted.
- The existing remediation hint.

Do not log or expose source content or URLs.

Add a migration test with more duplicate documents than the display limit.

Verify:

- The total count is accurate.
- The displayed IDs are deterministic.
- The error remains bounded.
- The active-job index is not created.

⸻

Documentation

Update apps/backend/docs/knowledge-source-management.md only where required.

Document:

- Retrieval state remains administrator-controlled across re-ingestion.
- Re-enabling retrieval does not trigger re-ingestion.
- Active-job uniqueness and migration failure behaviour.
- Required operational repair before retrying a failed migration.
- PostgreSQL-backed concurrency guarantees.
- CI verification expectations, if operationally relevant.

Do not claim test coverage or guarantees that are not implemented.

⸻

Non-goals

Do not implement:

- New administrator endpoints.
- Source content editing.
- Multi-page crawling.
- Scheduled refresh.
- PDF or file ingestion.
- Bulk import.
- New workers.
- New queues.
- New retrieval engines.
- New vector stores.
- Frontend changes.
- Authentication redesign.
- General ingestion refactoring.
- Unrelated migration cleanup.

⸻

Acceptance criteria

PR #60 is complete when:

- The retrieval-state test uses real persistence and production retrieval.
- Disabled sources remain excluded after a real ingestion commit.
- Re-enabling restores existing chunks without re-ingestion.
- Re-ingestion transaction rollback is proven.
- Deletion transaction rollback is proven.
- The complete PostgreSQL constraint matrix is tested.
- Concurrent create and re-ingest tests are deterministically coordinated.
- At least one database-backed API lifecycle test exists.
- Success metrics do not increment on rollback or failure.
- Structured logs contain no source content or credentials.
- Duplicate-active-job migration diagnostics are bounded.
- Required PostgreSQL tests execute in GitHub Actions without skipping.
- Existing public chat, ingestion, retry and persistence behaviour remains unchanged.
- All backend tests pass.
- Ruff passes.
- mypy passes.
- The PR description lists only validation commands that actually passed.

⸻

Verification commands

Run from the repository root unless repository documentation requires otherwise.

git status -sb
cd apps/backend

# Focused hardening tests

venv/bin/python -m pytest -q \
 tests/test_knowledge_source_postgres_migration.py \
 tests/test_knowledge_source_repository_postgres_integration.py \
 tests/test_knowledge_source_api.py \
 tests/test_knowledge_source_observability.py \
 tests/test_ingestion_pipeline_steps.py

# Add actual filenames if retrieval, rollback or full-stack API tests are split out

venv/bin/python -m pytest -q \
 tests/test_knowledge_source_retrieval_state.py \
 tests/test_knowledge_source_transaction_rollback.py \
 tests/test_knowledge_source_api_postgres_integration.py

# Affected regressions

venv/bin/python -m pytest -q \
 tests/test_ingestion_workflow.py \
 tests/test_ingestion_persistence.py \
 tests/test_assistant_repository.py \
 tests/test_public_chat.py \
 tests/test_admin_auth_api.py

# Full backend validation

venv/bin/python -m pytest -q
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/mypy .
cd ../..
npm run test:api
git diff --check
git status -sb

Inspect the test output and confirm the required PostgreSQL tests ran rather than skipped.

Push the changes to feature/11b1-knowledge-source-hardening so they update PR #60.

Do not create another branch or pull request.
