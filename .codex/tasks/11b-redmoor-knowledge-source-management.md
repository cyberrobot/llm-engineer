# PR 11B — Redmoor Knowledge Source Management

## Repository state

Expected branch:

`feature/11b-redmoor-knowledge-source-management`

Base branch:

`main`

Worktree:

Backend worktree. Start from a clean worktree created from the latest `origin/main`. Do not implement this task in the frontend worktree and do not include unrelated frontend, widget-package, release, or administration-shell changes.

Dependencies:

- PR 11A — Assistant Domain and Knowledge Scoping must already be present on `main`.
- PR 11E — Administrator Authentication API must already be present on `main`.
- PR 11C — Public Assistant Chat API must already be present on `main`.
- PR 11D — Public API Protection must already be present on `main`.
- The existing ingestion job, worker, retry, transactional persistence, progress, observability, and maintenance foundations from PR 9 must remain the only production ingestion machinery.
- Stop and report a repository-state mismatch if the assistant-scoped document model, administrator session dependency, or durable ingestion job infrastructure is missing. Do not recreate those foundations inside this PR.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `apps/backend/README.md`
- `apps/backend/docs/administrator-authentication.md`
- `apps/backend/docs/public-assistant-chat.md`
- The nearest README or module documentation for assistant ingestion, document persistence, and administrator API routing.

### Primary change area

- `apps/backend/assistant/domain/`
- `apps/backend/assistant/application/`
- `apps/backend/assistant/application/ports/`
- `apps/backend/assistant/api/`
- `apps/backend/assistant/schemas/`
- `apps/backend/assistant/infrastructure/`
- `apps/backend/infrastructure/database/migrations/`
- Focused backend tests under `apps/backend/tests/`
- Backend API documentation under `apps/backend/docs/`

### Canonical implementation examples

Inspect and reuse the current implementations rather than relying on names in this task:

- `apps/backend/assistant/domain/assistant.py` for assistant identity, status, visibility, and `DocumentRetrievalState`.
- The assistant and document repository implementations introduced by PR 11A for assistant ownership filters and PostgreSQL mapping.
- The ingestion job domain, repository, runner, worker, and transactional persistence code from PR 9.
- The existing website loader and processing service for URL extraction, normalization, chunking, and persistence.
- The existing document-scoped vector retrieval queries for enforcing assistant identity and retrieval state.
- The PR 11E administrator authentication route dependency and structured authentication error contract.
- Existing list/detail endpoint conventions, pagination schemas, dependency factories, router registration, OpenAPI configuration, logging, metrics, migration registration, and PostgreSQL integration tests.

### Relevant symbols

Codex must locate the current symbols before implementation. Expected concepts include:

- `Assistant`, `AssistantStatus`, `REDMOOR_ASSISTANT_ID`
- `DocumentRetrievalState`
- The document domain model and assistant-scoped document repository
- The ingestion job model, status and source reconstruction rules
- `KnowledgePersistenceService`
- Website loading and content-processing services
- Administrator current-session/current-user dependency
- Assistant API router and dependency wiring
- Database migration registry and migration test helpers

Names may differ. Extend the current owning abstractions instead of creating similarly named replacements.

### Expected change surface

The implementation is expected to add or update:

- A first-class knowledge-source domain model and stable enums.
- A repository port and PostgreSQL implementation for knowledge-source persistence.
- A reversible database migration and migration registration.
- Application services for create, list, detail, update retrieval state, re-ingest, and delete.
- Protected administrator HTTP endpoints and request/response schemas.
- Composition/dependency wiring and OpenAPI registration.
- Integration with existing documents and durable ingestion jobs.
- Behaviour-focused unit, API, migration, repository, and PostgreSQL integration tests.
- Backend documentation describing contracts, lifecycle, idempotency, deletion and operational behaviour.

### Excluded areas

Do not implement:

- The admin React application or PR 13A.
- Public widget or public-chat contract changes.
- Multi-page crawling, sitemap ingestion, JavaScript rendering, scheduled refresh, webhooks, bulk import, file upload UI, PDF execution, or cloud storage.
- Assistant creation/editing APIs beyond resolving the existing Redmoor assistant.
- Citations, grounding display, analytics dashboards, evaluation UI, source previews, content editing history, version rollback, source grouping, tags, search, or arbitrary metadata.
- A second worker, queue, retry framework, embedding path, vector store, document table, or ingestion orchestration system.
- Hard deletion of an assistant.
- New third-party dependencies unless an existing repository dependency cannot satisfy a clearly demonstrated requirement.

### Unknowns Codex must verify

Before changing code, verify and record in the completion report:

1. The exact document fields that represent source URL, source type, assistant ownership, retrieval state, and latest ingestion linkage.
2. Whether the current URL loader fetches one page or follows links. For this PR, URL sources must ingest exactly one requested page; disable or bypass crawling through existing configuration rather than forking the loader.
3. Whether the ingestion worker can reconstruct direct-text input durably. If not, add the smallest durable source-payload representation owned by the knowledge source and an adapter into the existing pipeline. Do not rely on in-memory request data after returning `202`.
4. Whether existing document rows can represent direct text safely without fake public URLs. Do not invent externally meaningful URLs solely to satisfy a legacy field.
5. The existing administrator role model. Use the current authenticated administrator policy; do not add a new role system.
6. Existing deletion conventions and foreign-key behaviour. Choose constraints deliberately and test them.
7. Whether retrieval-state filtering already excludes disabled documents. Extend the canonical query if required; do not filter only in the API.
8. The established API prefix and route naming conventions. The route examples below describe behaviour; align paths with current router structure if the repository uses a consistent alternative.

---

## Objective

Add a protected Redmoor knowledge-source management API that lets an authenticated administrator create and manage direct-text and single-page URL sources for the existing Redmoor assistant.

A knowledge source is the administrator-facing lifecycle record. It owns source identity, source configuration, retrieval availability and operational status, while the existing document, ingestion-job, processing, embedding, persistence and retrieval components remain authoritative for indexed knowledge.

The completed change must support:

- Creating a direct-text source and queueing durable ingestion.
- Creating a single-page URL source and queueing durable ingestion.
- Listing and reading source state, including latest ingestion information.
- Re-ingesting an existing source without creating a duplicate source.
- Enabling or disabling retrieval without deleting indexed content.
- Safely deleting a source and its owned indexed representation when no ingestion is active.
- Strict Redmoor-assistant scoping and administrator authentication.
- Deterministic, idempotent and concurrency-safe behaviour.

## Current architecture

PR 11A introduced a stable Redmoor assistant identity and assistant-scoped documents, chunks, persistence and retrieval. Documents already carry a retrieval state, and public chat retrieves only knowledge belonging to the requested assistant.

The ingestion architecture uses durable PostgreSQL job rows. Normal execution is owned by the existing worker, with explicit parse, chunk, embed and transactional persist stages. Retries, leases, checkpoints, deduplication, progress, structured failures and operational maintenance already exist. Final knowledge persistence atomically replaces a document’s chunks and embeddings and records the committed ingestion result.

PR 11E provides administrator accounts and cookie-session authentication. Knowledge management must use that server-side authentication boundary. Public chat protection is unrelated and must not be reused as administrator authorization.

The missing layer is an administrator-facing source abstraction. Raw document and job records are implementation details and do not provide a coherent API for creating source material, toggling availability, re-ingesting it or deleting it safely.

## Required implementation

### 1. Knowledge-source domain

Add a domain entity with, at minimum:

- Stable UUID identifier.
- Owning assistant UUID.
- Stable source type: `direct_text` or `url`.
- Administrator-facing name/title.
- Retrieval state using the existing enabled/disabled semantics.
- Source-specific configuration:
  - Direct text: durable UTF-8 text.
  - URL: normalized absolute `http` or `https` URL.
- Linked canonical document identifier, nullable only before a document is established if required by the existing workflow.
- Created and updated timezone-aware timestamps.
- Optional deleted state only if the repository already uses soft deletion. Otherwise implement guarded hard deletion.
- A stable representation/version marker or content hash where needed to detect stale ingestion results.

Validate business invariants in the domain or owning request boundary. Reject empty names, empty or whitespace-only direct text, unsupported URL schemes, credentials embedded in URLs, fragments where they are not meaningful, extra source payload fields, and contradictory type/payload combinations. Apply an explicit bounded maximum to direct text using an existing configuration pattern; document the limit.

Do not expose direct text in list responses, logs, metrics or errors. Detail responses may return the configured text because the endpoint is administrator-protected, but must not return chunks, embeddings or provider payloads.

### 2. Persistence and migration

Add a dedicated knowledge-source table rather than overloading document rows with administrator lifecycle concerns. Link each source to exactly one assistant and at most one canonical document. Enforce assistant ownership with foreign keys and repository predicates.

Add database guarantees for:

- One source ID.
- Valid stable source-type and retrieval-state values.
- Required source payload according to type, using application validation plus safe database constraints where practical.
- A source cannot link to a document owned by another assistant. If PostgreSQL cannot express this through a simple foreign key, enforce it transactionally in the repository and cover the race with locking or a suitable composite constraint.
- Normalized URL uniqueness within the same assistant for active URL sources.
- No accidental cross-assistant uniqueness.
- Deterministic indexes for assistant-scoped pagination and lookup.

Migration must preserve all current data, perform no provider/network work, be reversible, and be idempotent according to existing migration conventions. Do not fabricate knowledge-source rows for legacy documents unless there is a clear, lossless mapping. Legacy documents must remain queryable.

### 3. Creation and ingestion

Expose protected administrator creation endpoints under the current admin/assistant API convention. A suitable contract is:

- `POST /admin/assistants/{assistant_id}/knowledge-sources`
- `GET /admin/assistants/{assistant_id}/knowledge-sources`
- `GET /admin/assistants/{assistant_id}/knowledge-sources/{source_id}`
- `POST /admin/assistants/{assistant_id}/knowledge-sources/{source_id}/reingestions`
- `PATCH /admin/assistants/{assistant_id}/knowledge-sources/{source_id}`
- `DELETE /admin/assistants/{assistant_id}/knowledge-sources/{source_id}`

Use current conventions if paths differ, but preserve these resources and behaviours.

Creation must atomically establish the source, canonical document and queued ingestion job, or establish no partial business state. Slow URL fetching, parsing and provider calls must not occur inside the request transaction. Return `202 Accepted` with the source and queued job summary.

Direct text must be stored durably before returning. The existing worker must reconstruct the exact source version from persisted data. URL ingestion must fetch exactly the configured page through the established loader protections and timeout/error mapping.

Support the existing case-sensitive `Idempotency-Key` convention if available. Replaying the same key and semantically identical creation request must return the original source/job result. Reusing the key with different content must return the established conflict response. Concurrent creation of the same normalized URL must return the winning canonical source rather than creating duplicates or leaking an integrity error.

### 4. Listing and detail

List sources only for the route assistant. Use deterministic ordering, preferably newest first with ID as a tie-breaker, and established bounded pagination.

Each summary should include:

- Source ID, assistant ID, type, name and retrieval state.
- URL for URL sources; omit direct-text content.
- Created and updated timestamps.
- Canonical document ID when available.
- Derived operational status.
- Latest ingestion job summary: ID, status, progress/current step where already supported, created/started/completed timestamps and safe failure code/message.

Do not duplicate job-state logic in schemas. Compose current source and ingestion repositories through an application service.

Unknown assistant and unknown source must use existing not-found contracts without revealing cross-assistant existence. Invalid pagination must return structured validation errors.

### 5. Enable and disable retrieval

Allow a protected partial update containing only retrieval state in this PR. Reject unsupported mutable fields rather than silently ignoring them.

Disabling must update the source and canonical document retrieval state atomically so existing chunks remain stored but are immediately excluded by every production retrieval path. Enabling restores retrieval of the currently committed representation without forcing re-ingestion.

Repeated enable or disable requests are successful no-ops with stable state. Retrieval-state updates must remain safe against concurrent ingestion completion: a stale worker must not re-enable a source that an administrator disabled while ingestion was running. The source’s current retrieval state must be authoritative at final persistence.

### 6. Re-ingestion

Re-ingestion creates a new durable job for the same source and canonical document. It must not create a new knowledge source.

If a queued or running job already exists for the source, return that active job and indicate reuse rather than creating another. If the latest job completed or failed, create one new queued job using the source’s current persisted payload/version. Apply the existing idempotency-key contract where supported.

For direct text, ensure the job is bound to the intended persisted content version. For URL sources, re-ingestion fetches the URL again and may replace indexed knowledge when content changed. Existing transactional persistence must retain the previous usable representation if the new ingestion fails.

### 7. Safe deletion

Deletion must require an authenticated administrator and exact assistant/source ownership.

Reject deletion with `409 Conflict` when a queued or running ingestion job exists. Do not attempt implicit cancellation in this PR.

For a deletable source, remove the knowledge source, canonical document, chunks/embeddings and source-owned terminal ingestion history according to existing retention and foreign-key conventions in one bounded database transaction. Do not delete shared or cross-assistant records. If the existing model permits a document to be referenced by more than one business source, detect that condition and fail closed rather than cascading.

A successful delete returns `204 No Content`. Repeating deletion follows the project’s established not-found semantics. Test rollback by forcing a failure during dependent deletion and verifying that the source and indexed representation remain intact.

### 8. Security, errors and observability

All endpoints require the existing administrator cookie session. Test missing, invalid and expired sessions. Do not accept public API tokens or operations API keys as substitutes.

Use safe structured errors for validation, not found, conflict, active ingestion, provider/infrastructure unavailability and unexpected failures. Never return raw database/provider exceptions or fetched page contents.

Add structured logs and low-cardinality metrics through existing systems for source creation, ingestion request, retrieval-state update and deletion. Include safe source/assistant/job identifiers, result and duration. Never log direct text, fetched HTML, chunks, embeddings, session cookies, credentials or full URLs containing sensitive query values.

### 9. Documentation

Add a backend document for knowledge-source management and link it from `apps/backend/README.md`. Document request/response examples, authentication, supported source types, single-page URL scope, lifecycle, retrieval disable semantics, idempotency, active-job reuse, deletion conflicts, failure behaviour and current limitations.

## Acceptance criteria

- [ ] Authenticated administrators can create a direct-text Redmoor source and receive a durable queued ingestion job.
- [ ] Authenticated administrators can create a single-page URL source; ingestion does not crawl linked pages.
- [ ] Creation, source persistence, document linkage and job creation cannot leave partial state.
- [ ] Direct text is durable and worker-reconstructable after the API process restarts.
- [ ] List and detail responses are assistant-scoped, deterministic, paginated and include latest safe ingestion state.
- [ ] Direct-text bodies are omitted from list responses and all logs/metrics.
- [ ] Disabling a source immediately excludes its existing chunks from public retrieval without deleting them.
- [ ] Enabling restores the committed representation without re-embedding.
- [ ] Concurrent ingestion completion cannot override an administrator’s disabled state.
- [ ] Re-ingestion reuses an active job and creates at most one new queued job after terminal completion.
- [ ] URL uniqueness and idempotency are safe under concurrent requests.
- [ ] Cross-assistant access returns the established not-found response and produces no side effects.
- [ ] Deletion is blocked while ingestion is queued or running.
- [ ] Successful deletion removes only the source-owned knowledge representation and returns `204`.
- [ ] Failed deletion rolls back fully.
- [ ] Missing, invalid and expired administrator sessions are rejected through the existing auth contract.
- [ ] Migration upgrade/downgrade succeeds against a disposable PostgreSQL database and preserves legacy documents.
- [ ] Existing public chat, ingestion, worker, maintenance and evaluation behaviour remains backward compatible.
- [ ] OpenAPI and backend documentation accurately describe the implemented contract.

## Tests to add or update

Add focused tests in existing locations; follow repository naming conventions rather than creating unnecessary test hierarchies.

Required coverage:

- Domain validation for both source types, timestamps, identifiers, payload combinations, direct-text bounds and URL normalization.
- Repository create/get/list/update/delete and assistant isolation using real PostgreSQL.
- Migration upgrade, constraints, indexes, downgrade and legacy-data preservation.
- API authentication and authorization for every endpoint.
- Creation happy paths, malformed inputs, unsupported schemes, embedded URL credentials, empty text, extra fields and unknown assistants.
- Idempotent replay, idempotency conflict, duplicate URL creation and concurrent winner recovery.
- Durable direct-text reconstruction through the real worker/pipeline boundary with external embedding/provider boundaries faked only where necessary.
- Single-page URL ingestion with a controlled loader fixture proving no linked-page crawl.
- Pagination boundaries and deterministic ordering.
- Latest-job projection for queued, running, completed and failed jobs.
- Retrieval enable/disable verified through the real production retrieval service, not just response fields.
- Disable-versus-ingestion-completion race.
- Re-ingestion active-job reuse, terminal-job replacement and unchanged-content no-op persistence.
- Deletion conflict, successful cascade/explicit cleanup, cross-assistant denial and forced rollback.
- Safe errors and confirmation that sensitive text/content is absent from logs and serialized list responses.
- Regression coverage for existing public chat and ingestion API behaviour.

Where practical, write the behaviour test first and confirm it fails for the expected missing behaviour before implementing production code.

## Verification commands

Run from the repository root unless the existing backend documentation requires otherwise. Replace focused test filenames with the actual files created.

```bash
git status -sb

# Focused knowledge-source tests
cd apps/backend
venv/bin/python -m pytest -q \
  tests/test_knowledge_source_domain.py \
  tests/test_knowledge_source_repository.py \
  tests/test_knowledge_source_api.py \
  tests/test_knowledge_source_ingestion.py \
  tests/test_knowledge_source_migration.py

# Existing affected regression suites
venv/bin/python -m pytest -q \
  tests/test_assistant_domain.py \
  tests/test_assistant_repository.py \
  tests/test_ingestion_api.py \
  tests/test_ingestion_workflow.py \
  tests/test_public_chat.py \
  tests/test_admin_auth_api.py

# Full backend suite against the repository-supported disposable PostgreSQL setup
venv/bin/python -m pytest -q

# Static validation
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/mypy .

# Return to repository root and run the defined backend entry point
cd ../..
npm run test:api

git diff --check
git status -sb
```

If the repository uses different virtual-environment or test-database commands, use its documented equivalents and report the exact commands. Do not claim PostgreSQL concurrency, migration, worker reconstruction or rollback behaviour is verified if those tests were skipped.
