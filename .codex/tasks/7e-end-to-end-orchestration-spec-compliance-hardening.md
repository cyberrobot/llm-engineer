# PR 7E follow-up — End-to-end ingestion orchestration specification compliance

## Repository state

Expected branch: a fresh feature branch created from the latest `origin/main`

Base branch: `origin/main`

Worktree: repository worktree for the new branch

Dependencies: PRs 7A–7E, including the synchronous website-ingestion workflow and the established
PR 7D knowledge-persistence behavior, must already be present on `origin/main`

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- The authoritative **PR 7E — End-to-End Knowledge Ingestion Orchestration** specification
- `apps/backend/README.md`, especially the synchronous ingestion and knowledge-persistence sections

### Primary change area

- `apps/backend/assistant/application/ingestion_service.py`
- `apps/backend/tests/test_ingestion_workflow.py`
- Focused application-service tests under `apps/backend/tests/`

### Canonical implementation examples

- `apps/backend/assistant/domain/ingestion_job.py`
- `apps/backend/assistant/infrastructure/repositories/ingestion_job.py`
- `apps/backend/assistant/application/knowledge_persistence_service.py`
- `apps/backend/assistant/application/retrieval_service.py`
- `apps/backend/assistant/application/chat.py`
- `apps/backend/assistant/api/knowledge.py`
- `apps/backend/core/exceptions.py`
- Existing deterministic ingestion fixtures under
  `apps/backend/tests/fixtures/content_processing/`

### Relevant symbols

- `IngestionService.start_ingestion`
- `IngestionService._fail_job`
- `IngestionJob.create`
- `IngestionJob.start`
- `IngestionJob.complete`
- `IngestionJob.fail`
- `IngestionJobRepository.create`
- `IngestionJobRepository.update`
- `IngestionJobRepository.get`
- `KnowledgePersistenceService.prepare`
- `KnowledgePersistenceService.persist_prepared`
- `RetrievalService.retrieve`
- `ChatService.chat`
- `IngestionFailedError`

### Expected change surface

- Small orchestration changes that reconcile durable job state when a job-repository write fails
- A small existing-utility-based URL sanitization change for structured ingestion logs
- Focused lifecycle failure tests
- Changed-content ingestion, retrieval, and chat-compatibility integration coverage
- Minimal documentation clarification if recovery behavior becomes externally or operationally
  observable

### Excluded areas

- Website crawling, extraction, cleaning, chunking, embedding, or retrieval algorithm changes
- Knowledge-persistence repository behavior or the PR 7D replacement strategy
- Database schema changes unless inspection proves the current schema cannot represent the required
  lifecycle outcome
- New job states, parallel ingestion models, repository frameworks, or exception hierarchies
- Background workers, queues, scheduling, cancellation APIs, progress streaming, or dead-letter
  handling
- New retry policies or changes to retry classification, limits, or backoff
- Authentication, tenancy, administrator APIs, frontend work, or unrelated production hardening
- Broad refactoring of `IngestionService`

### Unknowns Codex must verify

- Whether repository `create()` and `update()` failures can be ambiguous after a successful database
  commit, and how the existing repository/connection contract exposes that outcome
- Whether reloading the job by ID is sufficient to reconcile an ambiguous write without introducing
  a repository API change
- Whether a completion-update failure can be recovered using a preserved running-state job or a
  freshly reloaded durable job while keeping domain transition rules intact
- Which existing URL parsing or normalization utility can produce a safe origin/domain without
  logging credentials, paths, query strings, or fragments
- The repository-defined command that makes PostgreSQL/pgvector integration prerequisites mandatory
  rather than silently skipped
- The smallest existing fake AI provider that can prove `ChatService` receives the newly ingested
  retrieval context without making a live provider call

---

## Objective

Close the remaining PR 7E specification gaps without redesigning the synchronous ingestion workflow.

The completed change must:

1. leave every created ingestion job in a truthful, retrievable lifecycle state when job-state
   persistence fails;
2. avoid exposing complete source URLs or sensitive URL components in structured logs;
3. prove complete-workflow idempotency for both unchanged and changed website content; and
4. prove newly ingested knowledge flows through the existing retrieval and chat contracts.

## Current architecture

`POST /assistant/knowledge/ingestions` validates the URL and calls
`IngestionService.start_ingestion()`. The service creates and persists a pending `IngestionJob`, marks
and persists it as running, invokes the existing website loader, content processor, embedding
preparation, and transactional knowledge persistence, then marks and persists the job as completed.
Stage failures use the domain `fail()` transition, attempt to persist a safe failure message, log the
underlying exception, and surface `IngestionFailedError` through the established API handler.

Two job-state write boundaries are currently inconsistent:

- job creation and the running-state update share one exception handler, so a successful create
  followed by a failed update can leave a durable pending job;
- after knowledge commits, `job.complete()` mutates the only in-memory job before the completed-state
  update. If that update fails, durable state remains running, while the in-memory object can no
  longer transition to failed.

The existing workflow test proves unchanged-content idempotency and direct retrieval. It does not
exercise changed-content replacement through the complete HTTP workflow or feed retrieved knowledge
through `ChatService`.

## Required implementation

### 1. Reconcile initialization failures after job creation

Keep pending-job creation and running-state persistence as separate, observable boundaries.

- If pending-job creation definitely fails and no row exists, return the established safe
  application error and do not invent a job record.
- If `create()` raises with an ambiguous outcome, reload by the generated job ID before deciding
  whether a durable job exists.
- If the job exists but the transition to running cannot be persisted, transition the current or
  reloaded non-terminal job to failed and attempt to persist a safe initialization failure.
- Preserve the original repository failure as the primary exception cause.
- If failure-state persistence also fails, log both failures with safe job/stage identifiers and
  return the established safe API error. Do not claim that a failed state was stored.
- Do not bypass `IngestionJob.start()` or `IngestionJob.fail()` by assigning lifecycle fields.
- Do not run website loading or any downstream stage unless the running state was confirmed durable.

### 2. Reconcile completed-state persistence failures

Knowledge persistence must remain committed before a job can be reported completed, and the service
must not leave a recoverable durable job silently running after a final job-state write failure.

- Preserve or reload the last confirmed durable running representation before attempting the
  completed transition.
- Apply `complete(...)` to a separate candidate or otherwise retain a valid domain object that can
  still transition from running to failed if the completion update does not commit.
- If the completion update raises, reload the job to resolve an ambiguous commit:
  - if durable state is already completed with the expected counters, treat the operation as
    completed and return that durable job;
  - if durable state remains pending or running, transition it through the domain model to failed
    with a safe completion-state persistence message and persist that failure where possible;
  - if durable state is missing or inconsistent, log the inconsistency and return the established
    safe application error without fabricating success.
- Preserve the original completion-update exception as the primary cause when the operation cannot
  be reconciled as successful.
- Log any reload or failure-state persistence error separately without exposing SQL, connection
  details, document content, or credentials.
- Do not roll back or repeat already committed knowledge merely to repair the job record.
- Document that a failed terminal job can coexist with committed idempotent knowledge when the final
  job-state update fails; a later unchanged ingestion must remain safe.

### 3. Keep failure mapping and transaction boundaries stable

- Continue returning the existing `IngestionFailedError` mapping and compatible API response.
- Continue storing stage-specific safe failure descriptions rather than raw exception text.
- Do not place website loading, processing, or embedding generation inside a database transaction.
- Do not add a transaction spanning the job repository and knowledge repository.
- Do not catch `BaseException`; cancellation and process termination must continue to propagate
  according to existing runtime behavior.
- Do not change retry policy as part of this work.

### 4. Sanitize ingestion source logging

Replace the complete `source_url` log field with an established safe representation.

- Prefer an existing validated URL/normalization helper.
- The logged value may contain the normalized scheme and hostname, or only the hostname/domain.
- It must not contain user information, path segments, query parameters, fragments, or raw percent-
  encoded equivalents of those values.
- Keep the ingestion job ID and stage fields.
- Do not alter the URL supplied to `WebsiteLoader` or the URL persisted as the business source.
- Add a regression test using a valid URL whose path, query, and fragment contain sentinel secrets;
  assert none appears in captured logs.

### 5. Prove unchanged and changed-content behavior end to end

Extend the controlled HTTP workflow tests using existing HTML fixtures, real extraction/cleaning/
chunking, deterministic embeddings, real PostgreSQL knowledge repositories, pgvector retrieval, and
no live network or AI provider.

For unchanged content:

- two HTTP ingestion requests may produce two completed ingestion jobs;
- exactly one logical document and one active chunk representation remain;
- the second run creates no chunks or vectors and generates no additional embeddings;
- retrieval continues returning the original content and correct source metadata.

For changed content at the same URL:

- make the mocked HTTP transport return a second deterministic fixture for the later ingestion;
- assert the job completes and persistence follows the established PR 7D replacement behavior;
- assert the stored document representation is updated without a duplicate logical document;
- assert obsolete chunks and vectors are absent from active storage/retrieval;
- assert newly changed content is retrievable with the same correct source URL and expected title;
- assert embedding calls occur only for content that the established persistence service determines
  requires embeddings.

Do not reproduce content hashing or duplicate detection in orchestration or test-only production
code.

### 6. Prove chat compatibility

After the database-backed changed-content ingestion succeeds:

- construct the existing `RetrievalService` over the real pgvector-backed retrieval path;
- construct `ChatService` with that retrieval service and an existing deterministic fake AI
  provider;
- submit a normal `ChatRequest` whose answer depends on the changed fixture content;
- assert the provider receives a prompt containing the relevant newly ingested context;
- assert the response maps the expected source reference through existing schemas;
- assert stale content is absent from the prompt and response sources;
- do not call a live completion or embedding provider and do not change prompt behavior.

### 7. Complete lifecycle failure coverage

Add deterministic application-service tests for failures at all required job-repository boundaries:

- pending-job creation before any row is stored;
- ambiguous pending-job creation where the repository stores then raises;
- running-state update after pending creation;
- failed-state persistence after a pipeline failure;
- completed-state update before commit;
- ambiguous completed-state update where the repository stores then raises;
- failure-state persistence while reconciling a failed completed-state update.

Use a narrowly scoped stateful test repository or connection/cursor wrapper that models whether each
operation failed before or after durable storage. Do not add production flags, timing races, sleeps,
or mocks that bypass the service behavior being tested.

For every case, assert:

- the exact downstream components that did or did not execute;
- the final retrievable job state, when a row exists;
- safe error text and absence of raw repository details;
- the primary exception cause;
- no false completed response;
- whether committed knowledge is present, according to the failure boundary.

## Acceptance criteria

- [ ] A failed running-state update never starts website loading and does not leave a known durable
      job silently pending when a failed state can be persisted.
- [ ] A failed completed-state update is reconciled against durable state and never leaves the API
      claiming an unverified completion.
- [ ] An update that committed and then raised is recognized through a repository reload rather than
      incorrectly overwriting a completed job with failure.
- [ ] Secondary reload or failed-state persistence errors are logged while the original failure
      remains the primary cause.
- [ ] Lifecycle fields are changed only through existing domain methods.
- [ ] Knowledge persistence remains outside job repository transactions and is not repeated during
      completion-state reconciliation.
- [ ] The existing ingestion endpoint, response schema, status codes, and safe exception mapping
      remain backward compatible.
- [ ] Structured ingestion logs contain no source path, query, fragment, credentials, raw content,
      chunks, embeddings, or provider/database secrets.
- [ ] Two unchanged full-workflow ingestions leave one logical active knowledge representation and
      perform no unnecessary second embedding generation.
- [ ] A changed-content full-workflow ingestion replaces stale active chunks and makes only the new
      content retrievable.
- [ ] `ChatService` consumes the newly ingested retrieval context and returns the expected existing
      source contract without prompt or schema changes.
- [ ] No new runtime dependency, migration, background worker behavior, or retry policy is added
      unless inspection proves it unavoidable and the deviation is documented.
- [ ] Backend documentation accurately describes final-state reconciliation and synchronous
      ingestion limitations.
- [ ] All required focused and broader backend checks pass without silently skipping required
      PostgreSQL/pgvector coverage.

## Tests to add or update

- Add focused `IngestionService` lifecycle tests in a new
  `apps/backend/tests/test_ingestion_service.py` or the nearest existing application-service test
  module.
- Update `apps/backend/tests/test_ingestion_workflow.py` with:
  - unchanged-content database-backed idempotency assertions;
  - same-URL changed-content replacement and stale-retrieval assertions;
  - chat prompt/context and source-mapping compatibility;
  - source URL log-sanitization coverage where the real orchestration log is exercised.
- Update API tests only if needed to assert the established safe response for repository-boundary
  failures and that a failed job remains fetchable when its failure state was persisted.
- Reuse the existing required-database helper and deterministic embedding fixtures. When the
  documented required mode is enabled, unavailable PostgreSQL, pgvector, or migrations must fail
  rather than skip.

## Verification commands

Run commands from the repository root unless the backend documentation requires otherwise.

```bash
# Focused lifecycle and workflow regression coverage
venv/bin/python -m pytest -q -o "addopts=" --strict-markers \
  apps/backend/tests/test_ingestion_service.py \
  apps/backend/tests/test_ingestion_api.py \
  apps/backend/tests/test_ingestion_workflow.py

# Required PostgreSQL/pgvector workflow evidence
KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED=true \
venv/bin/python -m pytest -q -o "addopts=" --strict-markers \
  apps/backend/tests/test_ingestion_workflow.py \
  apps/backend/tests/test_knowledge_persistence_integration.py

# Broader backend suite
npm run test:api

# Repository-defined static validation; confirm exact commands in current manifests/docs
venv/bin/python -m ruff check apps/backend
venv/bin/python -m ruff format --check apps/backend
venv/bin/python -m mypy apps/backend

# Startup and OpenAPI contract checks
cd apps/backend
../../venv/bin/python -c "from main import app; assert app.openapi()"
```

If an exact lint, formatting, typing, startup, migration, or generated-contract command differs in
the current repository, use the repository-defined command and record both the discovered command
and its result. Do not claim validation passed when a dependency is missing or a required database
suite skipped.
