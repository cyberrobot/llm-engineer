# Backend

FastAPI backend for the AI Discovery Assistant.

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
configured size. The minimum chunk size is honoured where the available content can satisfy it;
a whole document shorter than that minimum remains one useful chunk rather than being discarded.

Configuration is environment-driven:

- `INGESTION_CHUNK_SIZE_CHARACTERS` (default `1200`)
- `INGESTION_CHUNK_OVERLAP_CHARACTERS` (default `150`)
- `INGESTION_MIN_CHUNK_SIZE_CHARACTERS` (default `100`)
- `INGESTION_MIN_DOCUMENT_LENGTH_CHARACTERS` (default `50`)

Pages with no extracted body, too little cleaned content, or a recoverable page-level processing
failure are skipped with a structured warning while other pages continue. If no page creates a
chunk, the service raises `NoProcessableContentError` carrying the aggregate result and warnings.

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
document and chunk hashes produced by content processing. A unique partial index on document source
URL prevents duplicate website records without affecting existing uploaded documents. Unique
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
counts, and job identifiers, but never raw HTML, cleaned text, chunk contents, or embeddings.

The endpoint intentionally remains synchronous. Background workers, scheduling, and whole-job
retries are outside this workflow.

## Document ingestion jobs

Document ingestion requests have a persistent job record under `document_ingestion_jobs`. A document
must already exist before its job is created. `POST /ingestion/jobs/{job_id}/run` executes the job
synchronously in the current API process through this explicit sequence:

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
         -> complete or persist safe failure
```

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
- `POST /ingestion/jobs/{job_id}/run` for synchronous execution

Creation returns `201 Created`. The optional, case-sensitive `Idempotency-Key` request header is trimmed
and limited to 255 characters. Repeating the same key and document returns the original job with `201`;
reusing the key for another document returns `409 Conflict`. A partial unique database index makes this
safe under concurrent requests. The key is intentionally omitted from API responses.

This pipeline does not add progress percentages, queues, workers, automatic retries, retry backoff,
distributed claiming, cancellation commands, or asynchronous execution. Retry policy is deferred to
PR 9C. Durable source snapshots are required before finer website checkpoints are enabled. Distributed
job claiming and worker leases remain deferred to PR 9F; a concurrent process can still begin the same
non-terminal job.

## Production operations

Set `APP_ENV=production` in deployed environments. Startup validates every ingestion limit,
including HTTP and AI timeouts, crawl and response limits, chunk/overlap relationships, embedding
batch size, retry limits, upload size, and database timeouts. Production startup additionally
requires `DATABASE_URL` and `OPENAI_API_KEY`; invalid configuration prevents the application from
accepting traffic. Recommended starting values are the defaults in `.env.example`, adjusted only
after observing real crawl sizes and provider latency.

External operations are bounded:

- website requests use `INGESTION_TIMEOUT_SECONDS` and retry connection failures at most
  `INGESTION_HTTP_RETRIES` times (default `2`); validation failures, HTTP responses, malformed HTML,
  and unsupported content are not retried
- OpenAI requests use `AI_REQUEST_TIMEOUT` and the SDK's maintained transient-failure policy capped
  by `AI_MAX_RETRIES`; application validation and configuration failures are never retried
- PostgreSQL connections use `DATABASE_CONNECT_TIMEOUT_SECONDS`, while statements use
  `DATABASE_OPERATION_TIMEOUT_SECONDS`

The provider and website HTTP clients are process singletons and are closed during graceful FastAPI
shutdown. Database repositories use context-managed connections and cursors, and persistence keeps
document replacement in one transaction.

### Health checks

`GET /health` and `GET /assistant/health` keep their existing successful response contracts. With
`APP_ENV=production`, both act as readiness checks and return `503` with a generic message when a
required dependency is unavailable. They validate configuration, upload-storage writability,
database connectivity, and availability of PostgreSQL's `vector` extension. Embedding readiness is
validated without making a billable provider request: the configured provider, API credential,
model, timeout, and retry settings are checked at startup and health-check time.

Use a process-level liveness probe when a deployment needs to distinguish liveness from readiness;
these existing endpoints intentionally report dependency readiness in production.

### Logging

Application logs are newline-delimited JSON written to standard error. Ingestion lifecycle records
include the ingestion job ID, stage, page/document/chunk counts, embedding count, and website,
processing, persistence, embedding, and total durations. Logs use an explicit field allow-list and
never serialize HTML, cleaned document or chunk text, vectors, provider payloads, credentials, or
exception messages. Exception type and stage remain available for diagnosis without exposing
internal details to API clients.

### Metrics

The application registers these low-cardinality instruments in the standard `prometheus_client`
default registry for collection by the deployment's existing Python/ASGI Prometheus exporter:

- histograms: `ingestion_duration_seconds`,
  `ingestion_website_loading_duration_seconds`, `ingestion_processing_duration_seconds`,
  `ingestion_persistence_duration_seconds`, and `ingestion_embedding_duration_seconds`
- counters: `ingestion_success_total`, `ingestion_failure_total`,
  `ingestion_pages_processed_total`, `ingestion_pages_skipped_total`,
  `ingestion_documents_persisted_total`, `ingestion_chunks_persisted_total`, and
  `ingestion_embeddings_generated_total`

No metrics route is added here because API endpoint expansion is outside this hardening change.
Deployments should expose the default registry through their existing metrics sidecar or ASGI
instrumentation. Metric labels deliberately exclude URLs, job IDs, content, and other unbounded or
sensitive values.

### Troubleshooting and limitations

- A startup error names the invalid environment variable; correct it before restarting.
- A production health `503` intentionally hides connection details. Check the structured server log,
  database reachability, the `vector` extension, upload-directory permissions, and provider values.
- A failed ingestion remains safe to retry. Unchanged content does not regenerate embeddings or
  duplicate documents, chunks, or vectors. A concurrent writer is serialized per source URL.
- Website crawling is synchronous, same-origin, non-JavaScript, and bounded by the configured page
  and response limits. Queues, scheduling, distributed workers, and dashboards remain out of scope.

## Validate

```sh
python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```
