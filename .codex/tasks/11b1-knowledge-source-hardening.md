PR 11B.1 — Knowledge Source Management Hardening

Repository state

Expected branch

feature/11b1-knowledge-source-hardening

Base branch

main

Worktree

Backend worktree.

This PR is a corrective follow-up to PR 11B — Redmoor Knowledge Source Management. It must not introduce new end-user functionality. The objective is to complete the behavioural guarantees that were defined for PR 11B but were only partially implemented.

Before making any changes, verify that the following are already present:

- PR 9 ingestion infrastructure
- PR 10 operational foundations
- PR 11A Assistant Domain and Knowledge Scoping
- PR 11B Knowledge Source Management
- PR 11C Public Assistant Chat API
- PR 11D Public API Protection
- PR 11E Administrator Authentication

If any prerequisite is missing, stop immediately and report the repository-state mismatch rather than recreating infrastructure inside this PR.

⸻

Read first

Read the following before implementation:

- AGENTS.md
- apps/backend/AGENTS.md
- apps/backend/README.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- apps/backend/docs/knowledge-source-management.md

Inspect the existing implementation rather than assuming symbol names.

⸻

Objective

PR 11B introduced the administrator-facing Knowledge Source abstraction and integrated it into the ingestion pipeline.

The implementation is functionally correct but several architectural guarantees from the original specification remain incomplete.

This PR hardens the implementation so that it satisfies production-level requirements around:

- assistant isolation
- idempotency
- concurrency
- safe deletion
- deterministic behaviour
- observability
- integration testing

No new public functionality should be added.

The administrator API surface must remain unchanged.

⸻

Scope

This PR must address the following issues.

⸻

1. Assistant-scoped idempotency

The current implementation stores and resolves creation idempotency keys globally.

That allows identical requests against different assistants to potentially resolve to the same stored knowledge source.

Although Redmoor currently contains only one seeded assistant, the architecture explicitly supports multiple assistants and therefore assistant isolation must be enforced correctly.

Required implementation

Creation idempotency must become assistant scoped.

A lookup must uniquely identify:

- assistant
- idempotency key

rather than only the key.

Any unique indexes supporting idempotency should be updated accordingly.

Replay detection must only consider knowledge sources belonging to the same assistant.

A request replayed against another assistant must behave as a completely new request.

The request hash should also include assistant identity so that replay validation cannot accidentally match a different assistant.

No API behaviour should change.

⸻

2. Transaction-safe re-ingestion

The existing implementation performs:

1. check for active job
2. create job

in separate operations.

Concurrent requests can therefore race.

The specification required exactly one active ingestion job.

Required implementation

Move active-job detection and creation into one repository transaction.

The implementation must guarantee:

- one active queued/running job per source
- concurrent callers receive the winning job
- duplicate jobs are never created
- raw database unique violations are never exposed

Use existing PostgreSQL transactional patterns already present elsewhere in the repository.

Do not introduce distributed locking.

Do not introduce another queue.

Do not introduce background schedulers.

⸻

3. Correct idempotent re-ingestion

Creation already supports an idempotency key.

Re-ingestion must support the same behaviour.

When an idempotency key is replayed:

- identical request returns original queued/running job
- conflicting request returns established conflict response

The implementation must be deterministic.

⸻

4. One-to-one document ownership

The current schema allows multiple knowledge sources to reference the same document.

Deletion removes the document.

If shared ownership ever occurred this could cascade into deletion of unrelated knowledge sources.

Even if application code currently creates unique documents, the schema should enforce the intended invariant.

Required implementation

Choose one of the following approaches.

Preferred:

Enforce one-to-one ownership by:

- unique constraint
- repository validation
- migration
- tests

Alternative:

If shared ownership is intentional, deletion must explicitly reject removal whenever multiple sources reference the document.

The implementation should clearly document whichever invariant is chosen.

⸻

5. Replace list scan conflict resolution

Current duplicate URL detection loads up to one hundred knowledge sources before searching in memory.

This is not deterministic once an assistant owns more than one hundred sources.

Required implementation

Add repository support for:

- lookup by assistant
- normalized URL

Resolve duplicate URL conflicts directly.

Never perform paging purely to resolve uniqueness conflicts.

⸻

6. Retrieval-state concurrency guarantee

The original specification required administrator retrieval-state changes to remain authoritative even when ingestion completes simultaneously.

The implementation updates document retrieval state correctly but does not demonstrate that ingestion cannot overwrite administrator intent.

Required implementation

Review the transactional persistence boundary.

Verify that persistence never restores an outdated retrieval state.

If necessary:

- extend persistence
- preserve administrator retrieval state
- prevent stale worker updates

No behavioural regression to ingestion should occur.

⸻

7. Worker integration verification

The current direct-text support reconstructs synthetic HTML before content processing.

Review whether this remains the smallest adapter compatible with the existing processing pipeline.

If paragraph structure is unnecessarily degraded while processing direct text, improve the adapter without introducing another processing pipeline.

Maintain:

- deterministic chunking
- safe HTML escaping
- durable reconstruction

Do not duplicate parsing logic.

⸻

8. Website loader contract

The ingestion pipeline currently checks for:

load_single_page()

using runtime inspection.

Replace this with a proper interface contract.

All implementations of the website loader should expose the same capability through the application port.

Avoid runtime feature detection.

⸻

9. Structured logging

Add structured logs for:

- source creation
- duplicate detection
- replay
- re-ingestion
- retrieval-state update
- deletion
- active ingestion rejection

Logs must not include:

- direct text
- embeddings
- chunk contents
- administrator cookies
- provider payloads

Low-cardinality identifiers only.

⸻

10. Metrics

Reuse the existing observability framework.

Add metrics for:

- knowledge source creation
- successful re-ingestion
- replay
- duplicate URL rejection
- deletion
- retrieval enable
- retrieval disable

Do not introduce another metrics library.

⸻

11. PostgreSQL integration tests

Replace migration-only string assertions with genuine database verification.

Tests must demonstrate:

- migration upgrade
- migration downgrade
- repeatable upgrade
- constraint enforcement
- assistant isolation
- URL uniqueness
- retrieval-state values
- one-to-one document ownership

Use disposable PostgreSQL databases following existing repository conventions.

⸻

12. Repository tests

Add repository integration tests covering:

- creation
- retrieval
- pagination
- duplicate URL handling
- deletion
- active ingestion protection
- idempotent replay
- assistant isolation

Verify transaction rollback behaviour.

⸻

13. API tests

Extend API coverage.

Include:

Create

- direct text
- URL

Validation

- malformed URL
- credentials
- fragments
- oversized direct text
- invalid assistant

Authentication

- unauthenticated
- forbidden administrator
- trusted origin

Behaviour

- replay
- duplicate URL
- retrieval update
- delete
- re-ingest

Verify response contracts remain unchanged.

⸻

14. Concurrency tests

Add deterministic tests covering:

- simultaneous creation
- simultaneous re-ingestion
- duplicate URL races
- retrieval-state update while ingestion completes

The tests should demonstrate that only one canonical outcome exists.

⸻

15. Regression tests

Ensure no regression to:

- public assistant chat
- assistant scoping
- ingestion pipeline
- retry behaviour
- transactional persistence

Existing tests should continue to pass.

⸻

Non-goals

Do not implement:

- admin UI
- widget changes
- crawling
- sitemap ingestion
- scheduled refresh
- source editing
- file uploads
- PDFs
- analytics
- citations
- evaluation framework
- new worker architecture
- new queues
- new vector stores

⸻

Acceptance criteria

The PR is complete when:

- assistant-scoped idempotency is enforced
- re-ingestion is transaction-safe
- only one active ingestion job can exist
- duplicate URL handling is deterministic
- document ownership is explicitly enforced
- retrieval state remains authoritative during ingestion
- website loader exposes a formal single-page contract
- structured logs are emitted
- metrics are recorded
- PostgreSQL migration tests are implemented
- repository tests are comprehensive
- API tests are comprehensive
- concurrency behaviour is verified
- all existing backend tests pass
- Ruff passes
- mypy passes

⸻

Deliverables

Expected changes include:

- repository updates
- migration updates
- repository transaction improvements
- service-layer hardening
- website loader interface improvements
- ingestion persistence adjustments (if required)
- structured logging
- metrics
- API tests
- PostgreSQL integration tests
- repository tests
- concurrency tests
- documentation updates

Focus on strengthening correctness rather than expanding functionality. Every behavioural guarantee introduced by this PR should be demonstrated by automated tests.
