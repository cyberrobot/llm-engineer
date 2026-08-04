Update Existing PR #60 — Resolve Final Knowledge Source Hardening Failures

Repository state

Existing branch

feature/11b1-knowledge-source-hardening

Existing pull request

PR #60 — Knowledge Source Management Hardening

This task updates the existing branch and pull request.

Do not:

- Create a new branch.
- Create a new pull request.
- Reimplement completed hardening work.
- Expand the administrator API.
- Remove meaningful regression tests simply to make CI pass.
- Introduce unrelated ingestion architecture changes.

The objective is to resolve the final failures exposed by the latest PostgreSQL-backed CI run while preserving the intended Knowledge Source guarantees and existing ingestion behaviour.

Current PR state

The branch already contains:

- Assistant-scoped creation idempotency.
- Assistant-scoped re-ingestion receipts.
- Transaction-safe Knowledge Source re-ingestion.
- Direct normalized-URL conflict lookup.
- One-to-one Knowledge Source and Document ownership.
- Formal single-page website-loader contract.
- Direct-text formatting preservation.
- Structured lifecycle logging.
- Knowledge Source metrics.
- Real PostgreSQL migration tests.
- Database constraint tests.
- Repository integration tests.
- Re-ingestion rollback tests.
- Deletion rollback tests.
- Database-backed API tests.
- Real persistence and retrieval-state test structure.
- PostgreSQL and pgvector in GitHub Actions.
- Required PostgreSQL tests configured to fail rather than skip in CI.

Do not redesign or replace these completed areas.

Read first

Read:

- AGENTS.md
- apps/backend/AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/11b1-knowledge-source-hardening.md
- .codex/tasks/11b1-knowledge-source-review2.md
- .codex/tasks/11b1-knowledge-source-review3.md
- apps/backend/docs/knowledge-source-management.md
- The latest failing GitHub Actions output for PR #60.

Inspect the existing ingestion-job, persistence and Knowledge Source repository contracts before changing schema or tests.

Objective

Fix the final compatibility and test defects so that:

1. Knowledge Source re-ingestion remains concurrency-safe.
2. Existing non-Knowledge-Source ingestion behaviour is not restricted by an overly broad database invariant.
3. Concurrent URL creation is tested deterministically without breaking normal conflict-resolution reads.
4. Retrieval-state behaviour is verified through the real persistence and retrieval paths.
5. Test cleanup removes all dependent state correctly.
6. The complete backend and focused PostgreSQL suites pass.

⸻

1. Remove or correctly scope the global active-job uniqueness constraint

Current defect

The migration currently creates a partial unique index similar to:

CREATE UNIQUE INDEX knowledge_source_active_job_unique_idx
ON document_ingestion_jobs(document_id)
WHERE status IN ('queued', 'running');

This applies to all ingestion jobs for every document.

The hardening requirement is to prevent concurrent active re-ingestion jobs for a Knowledge Source. It is not valid to impose a new global ingestion invariant unless every existing ingestion workflow is intentionally changed to follow it.

The current global index breaks an existing persistence integration test that deliberately creates more than one active job to verify stale or competing persistence behaviour.

Required implementation

Use the smallest design that protects Knowledge Source re-ingestion without changing unrelated ingestion semantics.

Preferred solution

Remove the global unique index.

Rely on:

- SELECT ... FOR UPDATE of the Knowledge Source row.
- Active-job lookup inside the same repository transaction.
- Creation of a new job before releasing the row lock.
- Existing re-ingestion receipt serialization for idempotent requests.

Concurrent re-ingestion requests for the same Knowledge Source already serialize through the source-row lock. The second request must see and reuse the job created by the first transaction.

Alternative solution

Only use a database-level uniqueness mechanism if it can be explicitly scoped to Knowledge-Source-owned ingestion.

A valid alternative must:

- Not affect legacy or file-ingestion jobs.
- Not use an invalid cross-table predicate.
- Avoid denormalized state that can drift.
- Be justified by tests and documentation.
- Preserve current persistence conflict behaviour.

Do not add a broad document_ingestion_jobs(document_id) uniqueness constraint again.

Migration changes

If removing the global index:

- Drop it safely in upgrade() if it may already exist from an earlier draft deployment.
- Do not rely only on downgrade().
- Remove duplicate-active-job migration diagnostics that only existed to support the global index, unless they remain useful for a narrower invariant.
- Preserve all other Knowledge Source constraints and indexes.
- Ensure repeated upgrade remains idempotent.

Tests

Update migration tests to verify:

- The global active-job index does not exist after upgrade.
- Multiple active jobs remain allowed for ordinary non-Knowledge-Source documents.
- Knowledge Source re-ingestion still creates only one active job under concurrency through transaction locking.
- Existing ingestion persistence tests retain their original meaning and pass.

Do not weaken the existing test_pipeline_persistence_rolls_back_reindex_and_replays_one_committed_result scenario.

⸻

2. Fix deterministic concurrent URL creation test coordination

Current defect

The concurrency test wraps every repository connection acquisition in the same two-party barrier.

The first two transaction acquisitions coordinate correctly. However, after one request loses the uniqueness race, the service performs a normal find_by_url() lookup. That second connection acquisition reaches the same barrier with no matching caller and raises BrokenBarrierError.

This is a test harness defect, not expected production behaviour.

Required implementation

Coordinate only the first create transaction acquisition in each worker.

Suitable approaches include:

- A per-worker connection factory with a first_call flag.
- A small wrapper that waits on the barrier once, then delegates directly.
- A test-only repository subclass that pauses immediately before the first transactional insert.
- Explicit events around the transaction boundary.

Subsequent calls must use ordinary database connections, including:

- find_by_url()
- latest_job()
- Idempotency lookups
- Cleanup reads

Required assertions

The test must prove:

- Exactly one Knowledge Source exists.
- Exactly one canonical Document exists.
- Exactly one initial ingestion job exists.
- Both callers return the same source ID.
- Both callers return the same document ID.
- Both callers return the same job ID.
- One caller may report a fresh result and the other a reused result.
- No raw UniqueViolation, repository error or barrier error escapes.

Do not use arbitrary sleeps as the primary coordination mechanism.

⸻

3. Correct the retrieval result assertions

Current defect

The real retrieval-state integration test uses item.document_id, but the retrieval result is a KnowledgeChunk whose public contract exposes document association differently.

Required implementation

Inspect the current KnowledgeChunk domain model and production retrieval result contract.

Use the existing supported field, likely one of:

- item.document
- item.document.id
- item.doc_id
- Another established accessor

Do not add a new production property solely to satisfy this test unless that property is independently valuable and consistent with the domain model.

Preserve the full behaviour test

The corrected test must continue to prove:

1. Initial persisted chunks are retrievable.
2. A replacement representation can be prepared.
3. The source is disabled before replacement persistence commits.
4. The real persistence service commits the replacement.
5. Knowledge Source retrieval state remains disabled.
6. Document retrieval state remains disabled.
7. Production retrieval excludes the replacement chunks.
8. Re-enabling restores the already committed replacement chunks.
9. No additional ingestion job is created.
10. No embedding batch is regenerated.
11. Stored chunks and embeddings are not rewritten during enable.

Do not simplify the test back to direct database-field assertions only.

⸻

4. Fix integration-test cleanup ordering

Current defect

The retrieval-state test persists data that creates ingestion_persistence_results rows referencing the document.

The generic cleanup helper attempts to delete the document first, causing a foreign-key violation.

Some cleanup errors are currently suppressed, which can leave persistent test data behind and make later tests order-dependent.

Required implementation

Create or reuse a cleanup helper that deletes dependent integration-test data in the correct order.

Inspect current foreign-key behaviour before hard-coding order.

Likely dependent records include:

- knowledge_source_reingestion_requests
- ingestion_persistence_results
- ingestion_step_executions
- chunks
- document_ingestion_jobs
- knowledge_sources
- documents

Prefer deletion through the production Knowledge Source delete path when it correctly removes all owned records.

Where direct cleanup is required:

- Use one transaction.
- Delete only records associated with test-generated document/source IDs.
- Do not truncate shared tables.
- Do not suppress cleanup failures for complex persistence tests.
- Make failures visible so contaminated test state is detected.

Tests

Verify cleanup completes without foreign-key errors.

The test database must contain no rows for the generated source and document after cleanup.

⸻

5. Preserve Knowledge Source concurrency without the global index

After removing the global active-job constraint, re-run and strengthen the concurrent re-ingestion test.

Required sequence

1. Create a Knowledge Source.
2. Mark the initial job terminal.
3. Coordinate two re-ingestion calls at the source transaction boundary.
4. Allow one transaction to acquire the row lock and create the job.
5. Allow the second transaction to continue after the first commits.
6. Confirm the second transaction observes and reuses the active job.

Assertions

- One active queued/running job exists for the source document.
- Both responses reference the same job.
- One response is fresh.
- One response is reused.
- One receipt exists when a shared idempotency key is used.
- No raw database conflict escapes.
- A later request with the same key replays the same result.
- A conflicting key reuse returns the established idempotency conflict.

This test is the proof replacing the removed global unique index.

⸻

6. Update migration tests and documentation

Migration test updates

Remove assertions that require the global active-job index.

Retain and verify:

- Assistant-scoped creation-key uniqueness.
- Assistant-scoped URL uniqueness.
- One-to-one Knowledge Source and Document ownership.
- Source payload constraints.
- Retrieval-state constraints.
- Re-ingestion receipt constraints.
- Upgrade repeatability.
- Downgrade and re-upgrade.

If duplicate-active-job diagnostics are removed with the global index, remove obsolete diagnostic tests and documentation.

Do not retain dead migration code or tests for an invariant no longer enforced.

Documentation

Update apps/backend/docs/knowledge-source-management.md to state the actual concurrency guarantee:

- Knowledge Source re-ingestion is serialized by locking the Knowledge Source record.
- Concurrent callers reuse the active job created by the winning transaction.
- The shared ingestion-job table does not globally prohibit multiple active jobs for unrelated workflows.
- Idempotency receipts provide deterministic replay for keyed requests.

Do not claim database-wide one-active-job uniqueness.

⸻

7. CI requirements

The GitHub Actions PostgreSQL service and mandatory test configuration should remain.

After fixes, ensure:

- The main pytest step passes.
- The dedicated Knowledge Source PostgreSQL test step executes rather than being skipped due to an earlier failure.
- Required PostgreSQL tests cannot silently skip.
- Storybook tests remain unaffected.

Do not mark the PR ready while any required job is failing.

⸻

Non-goals

Do not:

- Redesign ingestion-job lifecycle globally.
- Remove existing persistence conflict tests.
- Add a new queue or locking service.
- Add distributed locks.
- Change public or administrator API response shapes.
- Add frontend work.
- Add crawling, file ingestion or scheduled refresh.
- Refactor unrelated repository code.
- Add a global one-active-job invariant under a different name.

⸻

Acceptance criteria

PR #60 is complete when:

- The global active-job unique index is removed or narrowly scoped without affecting unrelated ingestion.
- Existing persistence conflict tests pass unchanged in intent.
- Concurrent Knowledge Source re-ingestion still yields one active job.
- Concurrent URL creation returns one canonical source without barrier failures.
- The retrieval-state integration test uses the correct retrieval result contract.
- Real production retrieval excludes disabled replacement chunks.
- Re-enabling restores existing chunks without embedding or re-ingestion.
- Integration-test cleanup removes persistence results and all dependent rows safely.
- Migration tests reflect the final schema rather than obsolete draft invariants.
- Documentation accurately describes row-lock-based concurrency.
- Full backend pytest passes.
- Required PostgreSQL tests run and pass in CI.
- Ruff passes.
- Ruff format check passes.
- mypy passes.
- npm run test:api passes.
- GitHub Actions is green.

⸻

Verification commands

Run from the repository root unless the repository documentation specifies otherwise.

git status -sb
cd apps/backend

# Focused compatibility and hardening tests

venv/bin/python -m pytest -q \
 tests/test_knowledge_persistence_integration.py \
 tests/test_knowledge_source_postgres_migration.py \
 tests/test_knowledge_source_repository_postgres_integration.py \
 tests/test_knowledge_source_api_postgres_integration.py \
 tests/test_knowledge_source_observability.py

# Knowledge Source transport tests

venv/bin/python -m pytest -q \
 tests/test_knowledge_source_api.py \
 tests/test_knowledge_source_domain.py \
 tests/test_knowledge_source_migration.py \
 tests/test_ingestion_pipeline_steps.py

# Affected regressions

venv/bin/python -m pytest -q \
 tests/test_document_ingestion_job_postgres_integration.py \
 tests/test_ingestion_workflow.py \
 tests/test_ingestion_worker_postgres_integration.py \
 tests/test_public_chat.py \
 tests/test_assistant_repository.py

# Full backend validation

venv/bin/python -m pytest -q
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/mypy .
cd ../..
npm run test:api
git diff --check
git status -sb

When PostgreSQL is configured as required, confirm no Knowledge Source PostgreSQL tests are skipped.

Push fixes to:

feature/11b1-knowledge-source-hardening

Do not create another branch or pull request.

Update the existing PR description so its validation section reflects only commands and CI checks that actually passed.
