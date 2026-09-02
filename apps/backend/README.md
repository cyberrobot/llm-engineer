# Backend

Administrator lifecycle operations for direct-text and single-page URL knowledge are documented in
[`docs/knowledge-source-management.md`](docs/knowledge-source-management.md).

Assistant behaviour drafts, explicit publishing, authenticated preview, concurrency, and prompt
security are documented in [Assistant behaviour](docs/assistant-behaviour.md).

FastAPI backend for the AI Discovery Assistant.

Operational ingestion retention, reconciliation, dry-run commands, scheduling guidance, and
failure recovery are documented in the
[ingestion maintenance runbook](docs/ingestion-maintenance-runbook.md).

Administrator login, bootstrap, cookie-session security, and the frontend integration contract are
documented in [administrator authentication](docs/administrator-authentication.md).

Cache control, administrative audit browsing, maintenance mode, background-job visibility, and
operational summaries are documented in
[operations administration](docs/operations-administration.md).

Authenticated administrators can manage assistants at `/admin/assistants`. Creation defaults to
`inactive` and `private`; slugs are immutable and globally unique. Updates require the `updated_at`
value returned as `concurrency_token`, and stale updates return a conflict. Deletion is restricted to
unused assistants and never cascades assistant knowledge; the seeded Redmoor assistant cannot be
deleted. The API provides list (`GET`), detail (`GET /{id}`), create (`POST`), partial update
(`PATCH /{id}`), and delete (`DELETE /{id}`); every route requires an administrator cookie session,
and writes additionally require a configured trusted `Origin`. Stable error codes include
`assistant_not_found`, `assistant_slug_conflict`, `assistant_update_conflict`,
`protected_assistant`, `assistant_has_dependencies`, and `invalid_request`. Creation has no generic
idempotency-key mechanism: database slug uniqueness provides deterministic replay conflict handling.
Public chat remains available only for assistants that are both active and public, while authenticated
knowledge-source administration remains available regardless of assistant status or visibility and
status/visibility changes do not mutate knowledge-source state.

Administrator-only evaluation dataset discovery, synchronous execution, server-managed report
history, and baseline comparison are documented in
[evaluation administration](docs/evaluation-administration.md).

The deployment-gated public widget chat request, grounding, error, and SSE contracts are documented
in [public assistant chat](docs/public-assistant-chat.md).

## Run locally

Install dependencies from `requirements.txt`, copy `.env.example` to `.env`, and run:

```sh
python -m uvicorn main:app --reload
```

The canonical application entry point is `main:app`.

## AI configuration

Assistant chat uses the provider selected entirely through environment variables:

- `AI_PROVIDER`: provider identifier; currently `openai` (default)
- `OPENAI_API_KEY`: required when Assistant chat is called
- `OPENAI_MODEL`: model identifier (default: `gpt-5.5`)
- `AI_REQUEST_TIMEOUT`: request timeout in seconds (default: `30`)
- `AI_MAX_RETRIES`: OpenAI SDK retry limit for transient failures (default: `2`)

Assistant chat retrieves relevant knowledge before generation. With `DATABASE_URL` configured,
retrieval uses the existing pgvector `chunks` and `documents` tables. Without a database it uses
the small manually curated seed fixture in `assistant/infrastructure/seed_knowledge.py`.

The OpenAI client is created lazily, so health endpoints and non-AI workflows can start
without provider credentials. Missing or invalid AI configuration is returned as a service
availability error when chat is requested.

## Website content processing

Raw `WebsiteDocument` values from the website loader are transformed entirely in memory:

```text
WebsiteDocument -> HTML extraction -> text normalisation -> semantic chunking
                -> ContentProcessingResult
```

The extractor prefers `main`, `article`, `role="main"`, recognised content containers, and then
the document body. Scripts, styles, embedded content, hidden elements, navigation, footers, and
conservatively recognised overlays or cookie controls are excluded. Its canonical representation
is Markdown-like plain text: headings use `#` markers, paragraphs use blank-line boundaries, list
items keep ordered or unordered markers, block quotes use `>`, and simple table cells are separated
with ` | `. This representation is deterministic and contains no HTML-parser objects.

The cleaner applies Unicode NFC normalisation, removes zero-width and control characters,
normalises whitespace, preserves semantic line boundaries, and removes only adjacent duplicate
lines. The SHA-256 document content hash is calculated from the final cleaned text.

Chunking is character-based; it does not report character counts as tokens. It prefers section and
paragraph boundaries, then uses the existing sentence segmenter, with word and hard character
splits only as fallbacks. Chunk order, hashes, UUIDs, and heading-path metadata are deterministic.
Overlap copies at most the configured number of characters from the prior base chunk, trims to a
word boundary when possible, never copies a full prior chunk, and never makes a chunk exceed the
configured size. The minimum chunk size is a best-effort constraint across the full ordered chunk
sequence: short chunks are merged or redistributed at a nearby boundary when size limits permit,
and otherwise retained without dropping content. A whole document shorter than that minimum
remains one useful chunk rather than being discarded. Merges retain the earliest heading path.

The loader's explicit `WebsiteDocument.title` takes precedence over Open Graph title, Twitter title,
HTML `title`, and the first meaningful `h1`, in that order. Blank, excessive, and known boilerplate
titles are ignored. Class and ID boilerplate matching is deliberately limited to specific controls
such as cookie banners, consent dialogs, modal overlays, social-sharing controls, breadcrumbs, and
sidebar navigation; broad terms such as `social` or `share` do not remove legitimate page content.

Configuration is environment-driven:

- `INGESTION_CHUNK_SIZE_CHARACTERS` (default `1200`)
- `INGESTION_CHUNK_OVERLAP_CHARACTERS` (default `150`)
- `INGESTION_MIN_CHUNK_SIZE_CHARACTERS` (default `100`)
- `INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS` (default `50`)

`WebsiteLoader` returns `list[WebsiteDocument]`, and processing accepts that collection as a
`Sequence[WebsiteDocument]`; there is no separate crawl-result wrapper. Pages with no extracted
body, too little cleaned content, or an explicitly recoverable page-level processing failure are
skipped with a structured warning while other pages continue. Unexpected extractor, cleaner, or
chunker failures abort processing as a chained `ContentProcessingError` and are logged only with a
safe source origin and stage metadata. If no page creates a chunk, the service raises
`NoProcessableContentError` carrying the aggregate result and warnings.

Current extraction is intentionally conservative and does not render JavaScript or learn
cross-page boilerplate. The processing layer itself makes no OpenAI, database, vector-store, or
retrieval calls.

## Knowledge persistence

`KnowledgePersistenceService` accepts a `ContentProcessingResult` and stores its website documents
and chunks in the existing `documents` and `chunks` tables queried by pgvector retrieval:

```text
ContentProcessingResult -> duplicate check -> batch embeddings
                        -> atomic document/chunk write -> existing retrieval
```

Website documents are identified by their normalized source URL and retain the deterministic
document and chunk hashes produced by content processing. A unique partial index on assistant and
document source URL prevents duplicate website records within one assistant without preventing the
same source from belonging to another assistant. Unique
document/sequence and document/chunk-hash indexes reinforce chunk idempotency. Source URL, title,
heading path, access roles, and the fixed 1536-dimensional vector are stored alongside the existing
retrieval fields.

An identical document hash is a no-op: no chunks are rewritten and no embeddings are requested.
Changed documents use a document-level replacement strategy. All replacement embeddings are
generated in configurable batches before the database write; the document metadata update, old
chunk deletion, and new chunk insertion then occur in one transaction. This deliberately favors a
small, reliable transaction boundary over chunk-level vector reuse. PostgreSQL advisory transaction
locks serialize writes for the same source URL, while database uniqueness constraints prevent
concurrent duplicate documents or chunks. Provider and database failures are mapped to application
errors, and failed writes roll back without partial knowledge.

Configuration:

- `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`)
- `EMBEDDING_BATCH_SIZE` (default `100`)
- `DATABASE_CONNECT_TIMEOUT_SECONDS` (default `5`)
- `DATABASE_OPERATION_TIMEOUT_SECONDS` (default `30`)

The vector dimension remains a single canonical backend value matching the existing pgvector
schema. Persistence logs counts and timing but never chunk text, vectors, provider responses, or
credentials.

`POST /assistant/knowledge/ingestions` runs the complete synchronous ingestion workflow using the
existing dependency-injected components:

```text
create pending job -> mark running -> load website -> process content
                   -> persist knowledge -> mark completed
```

The job records discovered and processed document counts plus chunks created by persistence. An
unchanged rerun therefore completes with zero newly created chunks while retaining the existing
indexed knowledge and avoiding duplicate embedding requests. Loader, processing, or persistence
failures transition the running job to failed and return a generic application error without
exposing upstream, provider, or database exceptions. Pipeline logs include stage and total timings,
counts, job identifiers, and at most the source origin; they never include URL paths, queries,
fragments, raw HTML, cleaned text, chunk contents, or embeddings.

Job-state writes are reconciled by reloading the job after an ambiguous repository error. A write
that committed before raising is accepted only when the durable state matches the intended running
or completed transition. If the final completion write did not commit, the durable running job is
marked failed where possible; already committed knowledge is not rolled back or embedded again. A
later unchanged ingestion safely reuses that knowledge through the normal persistence idempotency
rules.

The endpoint intentionally remains synchronous. Background workers, scheduling, and whole-job
retries are outside this workflow.

## HTTP security boundaries

The intentional anonymous Assistant boundary is
`POST /public/assistants/{assistant_slug}/chat`. The legacy `/assistant/chat`, `/chunks`, and
raw-text `/ingest` routes are not mounted.

`POST /rag-chat` and `GET /audit-logs` remain temporary legacy dependencies of `apps/rag-ui`, but
both now require the existing administrator cookie session and administrator role. Retrieval roles
are derived from that trusted identity and a client role hint may only narrow the server-permitted
set. Both routes bound caller-controlled input, return safe unexpected errors, and disable response
caching. They remain candidates for removal and must be retired together with RAG UI. Their
consumer-specific behavior is recorded in
[`docs/legacy-rag-contract.md`](docs/legacy-rag-contract.md); new consumers must not adopt it.

`POST /ingest/upload` remains a supported machine-to-machine integration protected by the existing
ingestion `X-API-Key`; credential validation occurs before upload persistence or ingestion work.

## Document ingestion jobs

### Uploaded-file integrity and exact-content deduplication

PDF upload preflight calculates a SHA-256 fingerprint from the exact stored bytes before opening a
database transaction or creating an ingestion job:

```text
store source -> stream SHA-256 -> search within access-role scope -> classify content
             -> reuse, skip, or create ingestion job -> run pipeline only when required
```

The fingerprint is a lowercase 64-character digest plus the exact byte count from the same streaming
read. The service reads in bounded chunks, supports empty content deterministically (the upload API
continues to reject empty PDFs), rewinds seekable caller-owned streams to their original position, and
does not close them. Filename and MIME type are retained as audit/display metadata but do not
participate in content identity. Upload filenames are reduced to their basename before persistence.

Fingerprint fields are nullable on `documents`, because legacy documents remain readable and are not
backfilled by schema migration. New uploaded-file rows store `checksum_algorithm`, `checksum`,
`file_size_bytes`, `mime_type`, and a timezone-aware `checksum_calculated_at`. This application has no
tenant or soft-delete model; its relevant visibility boundary is the canonical sorted `access_roles`
set. The unique fingerprint index therefore covers
`access_roles + checksum_algorithm + checksum + file_size_bytes`. Identical bytes in a different role
scope create an independent document and reveal no canonical identifier from the other scope. The
current document model has no archive state, so every persisted, accessible document with a fingerprint
is eligible as canonical content.

Upload responses distinguish `NEW_CONTENT`, `DUPLICATE_CONTENT`, `MODIFIED_CONTENT`, and
`FORCED_REINDEX`. New content returns `202` with one queued ingestion job. A completed identical upload
returns `200`, the canonical document and completed job, and `ingestion_required=false`. A queued or
running match returns its active job with `ingestion_in_progress=true`; it never creates a second active
job. Failed or cancelled matches retain their terminal history and create a new queued recovery job on
the canonical document. `force_reindex=true` is opt-in, reuses the canonical document, and creates a new
queued job once no job is active. A request may supply `document_id` to identify an established logical
source; different bytes then update that document's source fingerprint and enqueue a
`MODIFIED_CONTENT` job. Filename alone is never treated as stable source identity.

Request idempotency remains separate from byte identity. A small `ingestion_file_requests` receipt row
records checksum, force intent, and the returned decision even when a duplicate creates no job. Replaying
the same key returns the original result; reusing it with different bytes or force intent returns the
existing `idempotency_key_conflict`. The key and raw checksum are not exposed by the API.

PostgreSQL uniqueness is the final concurrent-insert safeguard. The scoped fingerprint index permits
one canonical document, and a partial job index permits one queued/running fingerprinted-file job per
document. A losing transaction reloads the winner and returns the canonical active/duplicate decision
instead of a server error. The partial job predicate excludes legacy jobs without `request_checksum`,
so migration does not rewrite their lifecycle. Database work is limited to short lookup/insert/update
transactions; hashing never holds a database transaction open.

The upload endpoint performs preflight and job creation without parsing or embedding in the HTTP
request. The current pipeline reconstructs website sources from `documents.source_url`; PDF parsing is
not yet a pipeline step, so workers deliberately leave upload-only jobs queued rather than claiming
and failing them. PDF execution and stored-source lifecycle are follow-up work.

Document ingestion requests have a persistent job record under `document_ingestion_jobs`. A document
must already exist before its job is created. `POST /ingestion/jobs` commits a queued job and returns
`202 Accepted`; database polling is the durable dispatch mechanism. The compatibility
`POST /ingestion/jobs/{job_id}/run` endpoint remains available, while normal execution is owned by the
separate worker through this explicit sequence:

```text
PARSE -> CHUNK -> EMBED -> PERSIST
```

The runner loads the current job, rejects terminal or inconsistent state, marks a queued job running,
sets `current_step` before each attempt, and returns a structured result. It records safe failure codes
and messages and always moves a terminal execution failure out of `running`. Full exceptions remain in
server logs; raw source content, chunks, embeddings, credentials, and stack traces are not returned.

Jobs begin in `queued` and may later move through `running` to `completed` or `failed`; `queued` and
`running` jobs may also become `cancelled`. Terminal jobs cannot transition, change their current step,
or increment their retry count. `current_step` is the step being attempted. The nullable
`last_completed_step` is written only after a configured durable boundary succeeds, and completion
clears `current_step` while retaining `last_completed_step=persist`.

The orchestration loop is:

```text
load job -> determine next durable stage -> execute step -> commit checkpoint -> continue
         -> classify failure -> persist retry state -> wait -> retry the same step
         -> complete or persist safe terminal failure
```

### Transactional final persistence

`KnowledgePersistenceService` owns the single database transaction for the pipeline's final
`PERSIST` step. Parsing, chunking, and embedding generation finish before this transaction opens.
The step builds an immutable `PersistIngestionResult` command containing the ingestion-job and
document identities, explicit `NEW`, `REINDEX`, or `RECOVERY` intent, the prepared document/chunk
graph, and a stable command hash. The transaction then writes document metadata, chunk text,
database-backed pgvector embeddings, chunk metadata and access roles, ingestion-job links, and the
committed-result receipt together:

```text
pipeline prepares complete indexed data -> begin database transaction
-> lock ingestion job -> write document representation -> write chunks and embeddings
-> record committed result -> commit -> advance PERSIST checkpoint
```

The schema retains the existing direct replacement model rather than adding document-version
history. Re-indexing takes a document-scoped advisory transaction lock, deletes the old chunks and
inserts the complete replacement in the same PostgreSQL transaction. PostgreSQL rollback therefore
restores the prior indexed document and chunk set if any later write, flush, activation-link update,
or result-record insert fails. A successful commit leaves one chunk set under the document; existing
document/sequence and document/content-hash unique indexes remain the active-representation
safeguards.

`ingestion_persistence_results` stores one committed receipt per ingestion job. Its primary key and
foreign keys ensure one job cannot create two committed results, while `documents.last_ingestion_job_id`
and `chunks.ingestion_job_id` identify the active database representation produced by that job.
Retries lock the job and inspect its receipt before writing. An exact command-hash match is treated
as an already successful ambiguous commit; a different command for the same job fails as an
inconsistent state instead of inserting duplicates. Transient connection, deadlock, integrity,
validation, conflict, and consistency failures are mapped to safe typed persistence errors for the
existing retry classifier.

```text
write fails -> rollback transaction -> keep previous representation
-> discard the failed connection/session -> do not advance checkpoint
-> classify for retry or terminal handling
```

The migration leaves legacy indexed documents and chunks queryable with nullable ingestion-job
links; only new pipeline commits require a durable receipt. It is reversible and performs no
external I/O. Embeddings are vector columns on `chunks`, so every persisted embedding participates
in the same PostgreSQL transaction. There is no external vector-store write in this path and no
distributed-transaction limitation. Operational claiming/leases, observability expansion, cleanup,
and worker orchestration remain deferred to PRs 9F-9H.

The existing website loader, content processor, embedding preparation, and atomic knowledge repository
are composed as concrete steps. Parsing is read-only, cleaning/chunking is deterministic for a fixed
source snapshot, embedding preparation has no writes, and final persistence is protected by stable
document/chunk identifiers, unique constraints, a per-source database lock, and content-hash no-ops.

Website HTML, processed chunks, and prepared vectors are not stored in the job row. Because the current
loader keeps no durable source snapshot and a remote website can change between runs, the production
website pipeline deliberately uses `PERSIST` as its only cross-process checkpoint. An interruption
before persistence restarts at `PARSE`; an interruption after atomic persistence safely re-enters the
idempotent persistence boundary before the final checkpoint when necessary. The runner supports finer
checkpoints for source types whose prior outputs are durable or deterministically reconstructable, but
the website wiring does not claim unsafe `PARSE`, `CHUNK`, or `EMBED` resumability.

The API provides:

- `POST /ingestion/jobs` with a `document_id` JSON field
- `GET /ingestion/jobs/{job_id}`
- `GET /ingestion/jobs` with `limit`, `offset`, `status`, and `document_id` filters
- `POST /ingestion/jobs/{job_id}/run` as the existing synchronous compatibility path

Creation returns `202 Accepted`. The optional, case-sensitive `Idempotency-Key` request header is trimmed
and limited to 255 characters. Repeating the same key and document returns the original job with `202`;
reusing the key for another document returns `409 Conflict`. A partial unique database index makes this
safe under concurrent requests. The key is intentionally omitted from API responses.

### Synchronous retry and recovery

Retries execute synchronously inside the current `run` request and are scoped to the incomplete step;
the runner never restarts a completed checkpoint or automatically reruns a terminal failed job. The
ingestion classifier follows wrapped typed causes and defaults unknown exceptions to permanent. Network
errors, timeouts, HTTP 429/502/503/504, provider unavailability, PostgreSQL operational failures, and
deadlocks are retryable. Invalid URLs/input, provider credentials/configuration, other HTTP responses,
database constraints, deterministic step failures, and unexpected exceptions fail immediately. Raw
exception text is logged internally but never persisted or returned.

`INGESTION_RETRY_MAX_ATTEMPTS` is the total executions allowed for one step, including attempt 1. The
job-level `retry_count` is cumulative across all steps and counts only subsequent attempts: a first
failure leaves it at zero, scheduling attempt 2 changes it to one. `current_step_attempt_count` records
the scheduled/executing attempt for the current step and resets on step advance; `last_attempted_at`
records when that state was persisted. The retry count and next attempt number are committed before
backoff, so a new runner retains consumed attempts after interruption. Because a process cannot know
whether an interrupted external request completed, replay still depends on the existing deterministic
parse/chunk operations, stable UUID5 document and chunk identifiers, uniqueness constraints, content
hash no-ops, and atomic per-document replacement. Provider calls may be repeated, but prepared vectors
are not persisted until the idempotent persistence step.

Backoff uses Tenacity's exponential wait primitive. Defaults are 3 maximum attempts, 1 second initial
delay, multiplier 2, 30 second maximum delay, and full jitter enabled. Without jitter, retries wait
1, 2, 4, 8 seconds up to the cap. A valid provider `Retry-After` is treated as a minimum: the effective
delay is `max(local backoff, provider delay)`, capped by the configured maximum. No sleep occurs before
attempt 1 or after exhaustion, and repository calls commit before sleeping, so no database transaction
is held through backoff or provider work.

Example:

```text
EMBED attempt 1 -> rate limited -> persist retry_count=1 -> wait 1 second
EMBED attempt 2 -> provider unavailable -> persist retry_count=2 -> wait 2 seconds
EMBED attempt 3 -> success -> persist checkpoint -> continue to PERSIST
```

This pipeline still does not add progress percentages, delayed scheduling, manual retry endpoints,
or cancellation commands.
Durable source snapshots are required before finer website checkpoints are enabled. Transactional
persistence is complete; deeper observability and operational cleanup remain deferred to PRs 9G-9H.

### Background ingestion worker

The ingestion-job table is both the authoritative lifecycle record and the PostgreSQL-backed durable
queue. No broker is involved. The API commits a `queued` row before returning, so a worker can always
discover it even if the API process exits immediately:

```text
API creates QUEUED job -> worker claims job -> RUNNING -> heartbeat renews lease
-> pipeline resumes from checkpoint -> COMPLETED or FAILED
```

Each claim is one short transaction. It selects the oldest eligible website job by
`created_at ASC, id ASC` using `FOR UPDATE SKIP LOCKED`, changes `queued` to `running`, assigns
`worker_id`, sets `claimed_at`, `last_heartbeat_at`, and `lease_expires_at`, increments
`claim_version`, and commits before pipeline work begins. Independent connections are used for
claims, heartbeats, and pipeline operations. Multiple processes therefore skip locked work rather
than blocking or executing the same valid claim.

The lease defaults to 60 seconds and is renewed every 20 seconds. Heartbeats require the current
`worker_id`, `claim_version`, running status, and an unexpired lease. Pipeline lifecycle and retry
writes use the same worker/version fence. A stale process cannot complete, fail, or extend a job
after another worker recovers it. Terminal updates clear live ownership. A legacy or crashed
`running` job with no lease, or an expired lease, is recoverable without resetting `started_at`,
checkpoints, or attempt counts:

```text
worker crashes -> heartbeat stops -> lease expires -> another worker increments claim_version
-> pipeline reconstructs from durable state -> idempotent PERSIST completes once
```

This is at-least-once delivery plus exclusive leased execution and an idempotent pipeline, producing
an effectively-once committed representation; it is not exactly-once execution.

Run locally from `apps/backend` in separate terminals:

```sh
python -m uvicorn main:app --reload
python -m assistant.workers.ingestion
```

The same Docker image runs both processes. Configure the web service with the existing `uvicorn`
command and a separate Railway worker service with:

```sh
python -m assistant.workers.ingestion
```

Both services share `DATABASE_URL`, AI/provider settings, and ingestion settings. Start with one
worker replica and `INGESTION_WORKER_CONCURRENCY=1`; replicas and per-process concurrency may be
increased safely, with at least one database connection available per active pipeline plus heartbeat
and polling connections. The process handles SIGTERM/SIGINT by stopping new claims, waiting up to
`INGESTION_WORKER_SHUTDOWN_GRACE_SECONDS`, and then stopping heartbeats for unfinished jobs so their
leases can expire. Deployment liveness is the worker process exit state; a database readiness probe
can run `python -m assistant.workers.ingestion --health-check`. Use an on-failure restart policy.

Worker settings and defaults:

- `INGESTION_WORKER_ENABLED=true`
- `INGESTION_WORKER_POLL_INTERVAL_SECONDS=1`
- `INGESTION_WORKER_LEASE_SECONDS=60`
- `INGESTION_WORKER_HEARTBEAT_INTERVAL_SECONDS=20`
- `INGESTION_WORKER_CONCURRENCY=1`
- `INGESTION_WORKER_SHUTDOWN_GRACE_SECONDS=30`
- `INGESTION_WORKER_ID` optional; otherwise hostname, PID, and a startup UUID form the identity

PR 9H remains responsible for cleanup and retention operations. Queue priorities, scheduled jobs,
replay UI, progress streaming, and automatic scaling are intentionally not included.

## Production operations

Set `APP_ENV=production` in deployed environments. Startup validates every ingestion limit,
including HTTP and AI timeouts, crawl and response limits, chunk/overlap relationships, embedding
batch size, retry limits, upload size, and database timeouts. Production startup additionally
requires `DATABASE_URL` and `OPENAI_API_KEY`; invalid configuration prevents the application from
accepting traffic. Recommended starting values are the defaults in `.env.example`, adjusted only
after observing real crawl sizes and provider latency.

### Administrative operations API foundation

`GET /admin/operations` is the protected root of the operations administration API. It advertises
the read-only `health` capability. Configuration visibility, metrics, audit-log browsing, cache
administration, privileged actions, and dashboard aggregation are not implemented.

Administrative routes use the API's existing opaque `X-API-Key` authentication convention. Set
`ADMIN_API_KEY` to enable an administrative caller. When that value is absent or blank, the route
remains registered for API-contract stability but fails closed with `401 Unauthorized` for every
credential. A valid non-administrative API key is authenticated but receives `403 Forbidden`.
Credentials and authorization headers are never included in responses or structured logs.

Authorization has two extension levels:

- `operations:read` permits inspection-only operations and protects the router by default.
- `operations:execute` is additionally required by future state-changing operations.

The configured administrative key currently receives both permissions. Future execute endpoints
must opt in to the execute dependency; the distinction does not itself add any state-changing route.
Responses may reuse the UTC `generated_at` metadata contract and an optional request identifier when
a trusted request-context facility is available.

External operations are bounded:

- website requests and their preliminary DNS resolution use `INGESTION_TIMEOUT_SECONDS`;
  connection establishment uses HTTPX retries capped by `INGESTION_HTTP_RETRIES`, while ingestion
  orchestration retries only classified transient failures such as HTTP 429/502/503/504. Each
  request connects to an address that passed public-network validation while retaining the original
  hostname for TLS SNI and the HTTP `Host` header.
- OpenAI requests use `AI_REQUEST_TIMEOUT`; ingestion embedding calls disable SDK retries so the
  durable ingestion retry policy owns attempts and backoff without compounding them, while other AI
  workflows retain the SDK policy capped by `AI_MAX_RETRIES`
- PostgreSQL connections use `DATABASE_CONNECT_TIMEOUT_SECONDS`, while statements use
  `DATABASE_OPERATION_TIMEOUT_SECONDS`. A transient persistence retry reuses already prepared
  embeddings rather than calling the embedding provider again.

The provider and website HTTP clients are process singletons and are closed during graceful FastAPI
shutdown. Database repositories use context-managed connections and cursors, and persistence keeps
document replacement in one transaction.

### Health checks

The public probes intentionally have separate contracts:

- `GET /health/live` always returns `200 {"status":"alive"}` after FastAPI startup has completed.
  It performs no database, Redis, filesystem, or OpenAI work and is suitable for process/container
  restart decisions.
- `GET /health/ready` returns `200 {"status":"ready"}` when all required checks pass and
  `503 {"status":"not_ready"}` otherwise. It never names a failed dependency.
- `GET /health` remains a backward-compatible readiness-style route, returning the established
  `200 {"status":"healthy"}` success payload or a minimal `503` failure payload. New deployments
  should use the explicitly named probes.
- `GET /assistant/health` retains its existing assistant-specific production validation contract.

`GET /admin/operations/health` requires administrative read access and returns `generated_at`, the
aggregate status, and safe per-check status, required/optional classification, latency, timestamp,
and stable error code. A completed diagnostic request returns HTTP `200` even if the aggregate is
`degraded` or `unhealthy`; those values describe dependencies, not failure of the diagnostic API.
Missing or invalid credentials return `401`, while an authenticated principal without
`operations:read` receives `403`. Raw exceptions, hostnames, connection strings, and credentials are
never returned.

PostgreSQL is registered as required when `DATABASE_URL` is configured; its check validates both
connectivity and availability of the `vector` extension. Writable upload storage is always required
for readiness. Redis is registered as an optional cache check unless `DISABLE_CACHE=true`, so its
failure degrades detailed diagnostics but does not make readiness fail. OpenAI is a
configuration-only optional diagnostic: it verifies that a credential is configured without
constructing a client or making a completion, embedding, or other remote request. Independent checks
run concurrently and each is bounded by
`HEALTH_CHECK_TIMEOUT_SECONDS` (default `2`, valid range greater than zero through `10` seconds).
No health result caching is used. Uvicorn completes the FastAPI lifespan startup—including validated
configuration and configured database initialization—before serving routes, which is the readiness
initialization guarantee.

For a platform with separate probe settings, use `/health/live` for liveness and `/health/ready` for
traffic readiness. Railway exposes a single health-check path, so configure `/health/ready`; this
prevents a deployment with an unavailable required PostgreSQL dependency from receiving traffic.

The worker's readiness command remains `python -m assistant.workers.ingestion --health-check`.
Queue backlog is an operational signal, not a reason to restart a healthy API or worker.

### Ingestion progress and APIs

The `document_ingestion_jobs` row remains authoritative. `GET /ingestion/jobs/{id}` adds
`queued_at`, completed and total step counts, `progress_percent`, queue-wait, processing and total
durations, and a safe structured failure. The ordered pipeline is PARSE, CHUNK, EMBED, PERSIST.
Progress is `round(completed_step_count / total_step_count * 100)`, capped to 0–100; queued jobs are
0 and completed jobs are always 100. A running step does not add partial credit, retries do not add
progress, and failed jobs retain their last committed checkpoint. Production currently checkpoints
PERSIST because earlier website inputs are transient, so API progress is intentionally coarse rather
than claiming unrecoverable intermediate state.

Durations are derived on read and clamped at zero: queue wait is `started_at - queued_at`, processing
is terminal `completed_at - started_at` or active `now - started_at`, and total is terminal
`completed_at - queued_at` or active `now - queued_at`. They are milliseconds and no real-time value
is repeatedly persisted.

`GET /ingestion/jobs` is bounded to 100 records and supports offset pagination plus `status`,
`document_id`, `created_from`, `created_to`, and `failed_step`; ordering is `created_at DESC, id DESC`.
`GET /ingestion/jobs/{id}/steps` returns safe attempt history. These routes require `X-API-Key` using
`INGEST_API_KEY`/`ADMIN_API_KEY`. The repository has no end-user/tenant identity model, so this is an
admin boundary, not per-user ownership. `GET /internal/ingestion/status` uses the same key and reports
queued/running/recoverable counts, oldest queued age, and workers inferred from active unexpired
leases. It does not claim to count idle workers.

Each logical step attempt has a unique `(ingestion_job_id, step, attempt_number)`. The first attempt
is 1 and a retry or recovered execution gets the next number. Terminal results cannot overwrite one
another. Recovery marks an unfinished history row `interrupted` without inventing a completion time,
then starts a new attempt. Start and terminal records add two small database writes per executed
attempt. Final duration uses the process monotonic clock; UTC wall timestamps provide chronology.

```text
QUEUED -> PARSE running -> PARSE completed -> CHUNK running -> CHUNK completed
-> EMBED retrying -> EMBED completed -> PERSIST completed -> COMPLETED

durable lifecycle transition -> structured event -> metrics update
-> logs -> API reflects committed state
```

### Logging

Application logs are newline-delimited JSON written to standard error. Ingestion lifecycle records
include the ingestion job ID, stage, page/document/chunk counts, embedding count, and website,
processing, persistence, embedding, and total durations. Logs use an explicit field allow-list and
never serialize HTML, cleaned document or chunk text, vectors, provider payloads, credentials, or
exception messages. Exception type and stage remain available for diagnosis without exposing
internal details to API clients. Every JSON record has an `event`; request work also has a validated
or generated `request_id`, returned as `X-Request-ID`. Worker activity uses `ingestion_job_id`/`job_id`,
`document_id`, safe `worker_id`, and `claim_version` for correlation. Step events include
`ingestion_step_attempt_started`, `ingestion_step_attempt_completed`,
`ingestion_step_attempt_failed`, `ingestion_step_retry_scheduled`, and retry exhaustion/success.
Successful heartbeats are DEBUG to bound log volume. Full checksums, filenames, document/chunk text,
embeddings, raw provider bodies, credentials, and exception messages are not allow-listed.

### Metrics

The application registers these low-cardinality instruments in the standard `prometheus_client`
default registry, exposed at `GET /metrics`:

- histograms: `ingestion_duration_seconds`,
  `ingestion_website_loading_duration_seconds`, `ingestion_processing_duration_seconds`,
  `ingestion_persistence_duration_seconds`, and `ingestion_embedding_duration_seconds`
- counters: `ingestion_success_total`, `ingestion_failure_total`,
  `ingestion_pages_processed_total`, `ingestion_pages_skipped_total`,
  `ingestion_documents_persisted_total`, `ingestion_chunks_persisted_total`, and
  `ingestion_embeddings_generated_total`
- job/worker counters: `ingestion_jobs_created_total`, `ingestion_jobs_claimed_total`,
  `ingestion_jobs_completed_total`, `ingestion_jobs_failed_total`,
  `ingestion_jobs_recovered_total`, `ingestion_step_attempts_total`,
  `ingestion_step_retries_total`, `ingestion_persistence_rollbacks_total`,
  `ingestion_duplicates_total`, `ingestion_pipeline_skipped_total`,
  `ingestion_forced_reindex_total`, and `worker_lease_losses_total`
- database-derived gauges refreshed by the internal status query: `ingestion_jobs_queued`,
  `ingestion_jobs_running`, `ingestion_recoverable_jobs`, and
  `ingestion_oldest_queued_age_seconds`, plus `ingestion_workers_active` inferred from live leases
- job/worker histograms: `ingestion_queue_wait_seconds`,
  `ingestion_job_processing_duration_seconds`, `ingestion_total_duration_seconds`,
  `ingestion_step_duration_seconds`, and `worker_job_execution_duration_seconds`

Labels are limited to bounded `step` and `failure_category` values (plus Prometheus histogram bucket
labels). They deliberately exclude URLs, job/document/worker IDs, filenames, checksums, tenant data,
content, and exception messages. Counters are emitted after authoritative state writes. As with most
in-process Prometheus counters, a process crash between commit and increment can under-count; gauges
are derived from database state and remain authoritative for current queue state. Export failures
are non-fatal and do not consume ingestion retries.

No OpenTelemetry dependency or established trace exporter exists, so PR 9G does not introduce a
second tracing stack. Logs, durable attempt history, metrics, and request/job correlation provide the
current observability path.

### Dashboard and alert recommendations

A minimal dashboard should graph queued/running jobs, oldest queued age, completion/failure rate,
queue wait and total duration, duration by step, retries by step/failure category, recoveries, lease
losses, persistence rollbacks, and deduplicated/skipped submissions. Persistence and deduplication
retain their existing metrics/logs; they are not relabelled with job IDs.

Configure environment-specific alerts for: oldest queued age above the service objective; queued
work with no recent claims; elevated terminal failure rate; recovery or lease-loss spikes; retry
exhaustion; p95 total duration; and persistence rollback rate. Backlog and latency alerts must not be
wired to liveness restarts. Thresholds belong in deployment monitoring configuration, not code.

### Troubleshooting and limitations

- A startup error names the invalid environment variable; correct it before restarting.
- A production health `503` intentionally hides connection details. Check the structured server log,
  database reachability, the `vector` extension, upload-directory permissions, and provider values.
- A failed ingestion remains safe to retry. Unchanged content does not regenerate embeddings or
  duplicate documents, chunks, or vectors. A concurrent writer is serialized per source URL.
- Website crawling is synchronous, same-origin, non-JavaScript, and bounded by the configured page
  and response limits. Traces, a dashboard UI, alert delivery, streaming progress, worker registry,
  queue scheduling, cancellation, cleanup, and retention remain out of scope. Cleanup/retention and
  reconciliation of old observability history are intentionally deferred to PR 9H.

## Validate

```sh
python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```

PostgreSQL/pgvector persistence verification can remain optional for local unit-only work. Set
`KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED=true` when running
`tests/test_knowledge_persistence_integration.py` in CI or release verification; in that mode a
missing `DATABASE_URL` or unavailable PostgreSQL service fails the suite instead of skipping it.

## Assistant-scoped knowledge

Knowledge is partitioned by the persistent `Assistant` domain entity. The built-in initial
assistant has the stable slug `redmoor`, active status, and public visibility. Status and
visibility are independent persisted values; low-level retrieval does not interpret either as
an authorization policy.

The database bootstrap creates Redmoor idempotently and backfills existing documents and chunks
to it without changing their identifiers or content. Every new document and chunk requires an
assistant ID. Chunk writes are protected by a composite document/assistant foreign key, and
assistant deletion is restricted while knowledge still references it.

Documents also have an independent `retrieval_state` (`enabled` or `disabled`). Both pgvector and
hybrid retrieval filter candidates inside SQL by assistant ID and include only enabled documents.
Application ingestion and existing chat entry points explicitly bind to the built-in Redmoor ID;
new internal persistence or retrieval callers must supply an assistant scope rather than querying
the global knowledge base.
