Update Existing PR #60 — Complete PR 11B.1 Hardening

Repository state

Branch

feature/11b1-knowledge-source-hardening

Pull Request

PR #60 — Knowledge Source Management Hardening

This task updates the existing PR.

Do not create a new branch.

Do not create a new PR.

The objective is to complete the outstanding work identified during the engineering review so that PR #60 fully satisfies the original hardening specification.

⸻

Before writing code

First inspect the current implementation in the branch.

Read:

- AGENTS.md
- apps/backend/AGENTS.md
- .codex/tasks/11b1-knowledge-source-hardening.md

Compare the current implementation against the specification before making any changes.

Do not reimplement work that already exists.

Only implement the remaining missing behaviour.

⸻

Current review findings

PR #60 already correctly implements:

- Assistant-scoped creation idempotency.
- Assistant-aware request hashing.
- Transaction-safe re-ingestion.
- Dedicated re-ingestion idempotency receipts.
- Direct URL repository lookup.
- One-to-one document ownership.
- Formal website-loader contract.
- Improved direct-text formatting.
- Structured logging.
- Metrics.

These areas require no architectural redesign.

Focus exclusively on the remaining gaps below.

⸻

Remaining work

1. Safe migration for existing databases

The migration currently creates the unique active-ingestion index directly.

If an upgraded database already contains multiple queued or running jobs for one document, migration can fail unexpectedly.

Before creating the unique index:

- detect duplicate active jobs
- implement the repository-approved migration policy

Preferred:

Fail the migration deliberately with a clear diagnostic explaining which document(s) violate the invariant.

Do not allow PostgreSQL to fail with an unexplained unique-index creation error.

Do not silently delete or modify ingestion jobs unless an existing repository policy already defines how duplicates should be reconciled.

Document the migration behaviour.

⸻

2. Replace SQL-string migration tests

Current migration tests only inspect generated SQL.

Replace or supplement them with genuine PostgreSQL migration tests.

Required coverage:

- fresh upgrade
- repeat upgrade
- downgrade
- re-upgrade
- duplicate active-job handling
- constraint enforcement

These tests must execute against a disposable PostgreSQL database using existing repository conventions.

⸻

3. Repository integration tests

Add repository tests covering:

Creation

- direct text
- URL

Assistant isolation

- lookup
- idempotency replay
- duplicate URL lookup

Re-ingestion

- replay
- conflict
- active job reuse
- terminal job creation

Deletion

- active job rejection
- successful deletion
- cross-assistant protection

Rollback

Verify transactions roll back completely after forced failures.

Use real PostgreSQL where practical.

⸻

4. API integration tests

Expand API coverage.

Required cases:

Authentication

- unauthenticated
- invalid session
- trusted-origin protection

Creation

- direct text
- URL
- replay
- idempotency conflict

Re-ingestion

- replay
- conflict

Knowledge source

- list
- detail
- enable
- disable
- delete

Cross-assistant access must continue returning the established not-found contract.

The administrator API contract must remain unchanged.

⸻

5. Concurrency tests

Add deterministic concurrency tests for:

Concurrent URL creation

Verify:

- one source
- one document
- one active job

Concurrent re-ingestion

Verify:

- one active job
- deterministic replay
- no database unique violation escapes

Avoid timing-based sleeps where possible.

⸻

6. Retrieval-state authority

The implementation appears correct but is not currently proven.

Add an integration test demonstrating:

1. ingest enabled source
2. disable source
3. complete ingestion
4. verify retrieval remains disabled
5. re-enable
6. verify retrieval resumes without re-indexing

Only change production code if this test exposes a defect.

⸻

7. Logging and metrics verification

Add tests confirming:

Structured logs never contain:

- direct text
- HTML
- chunks
- embeddings
- cookies
- provider payloads

Verify metrics increment only for successful externally observable lifecycle events.

⸻

Do not change

Do not modify:

- public assistant API
- administrator API contract
- ingestion architecture
- worker model
- queues
- embeddings
- retrieval implementation
- document schema (unless required by migration safety)
- widget code
- frontend
- authentication model

Avoid unrelated refactoring.

⸻

Deliverables

Update the existing PR with:

- migration safety improvements
- PostgreSQL migration tests
- repository integration tests
- API integration tests
- concurrency tests
- rollback tests
- retrieval-state integration test
- logging tests
- metrics tests
- documentation updates where required

Do not create a follow-up PR.

⸻

Acceptance criteria

The existing PR is complete when:

- duplicate active-job migration behaviour is explicit and tested
- PostgreSQL migration tests exist
- repository integration tests exist
- API integration tests exist
- deterministic concurrency tests exist
- rollback behaviour is verified
- retrieval-state authority is demonstrated
- logging is verified safe
- metrics are verified
- all backend tests pass
- Ruff passes
- mypy passes

⸻

Final verification

Before finishing:

- Run the complete backend test suite.
- Run all newly added focused tests.
- Update the PR description only if validation differs from reality.
- Push additional commits to the existing branch.
- Do not create a new branch or a new pull request.
