# Knowledge-source management

Authenticated administrators manage Redmoor knowledge at
`/admin/assistants/{assistant_id}/knowledge-sources`. Read operations require the administrator
session cookie. Create, patch, re-ingest, and delete also require an exact trusted `Origin`, using
the same authentication and CSRF contract as the administrator authentication API.

Supported source types are `direct_text` (up to 100,000 Unicode characters) and `url`. URL values
must be absolute HTTP(S), contain no credentials, and are normalized without fragments. URL
ingestion fetches exactly the requested page after redirects; it does not follow page links.

```json
{"source_type":"direct_text","name":"Services","direct_text":"Redmoor provides..."}
```

Creation returns `202` with the source and its durable queued ingestion job. The source payload,
canonical document, and job are committed atomically, so a worker can reconstruct direct text after
an API restart. Lists are newest-first and omit direct text; protected detail responses include it.
URLs are unique within an assistant. `Idempotency-Key` is case-sensitive and may be used on create
and re-ingestion requests.

`PATCH` accepts only `retrieval_state` (`enabled` or `disabled`). Disabling retains chunks and
embeddings but immediately removes the document from production retrieval. Enabling restores the
committed representation without re-embedding. Re-ingestion preserves the source identity and
reuses a queued or running job; otherwise it queues a new job for the current persisted payload.

Deletion returns `409 active_ingestion` while a job is queued or running. Otherwise it removes the
source-owned document, chunks, embeddings, and terminal job history in one transaction, returning
`204`. Cross-assistant and missing resources use the same not-found response. Provider and database
details, fetched HTML, chunks, embeddings, direct text, cookies, and sensitive URL content are not
included in operational errors.

Current limitations include direct text and one HTML page only: no crawling, sitemaps, JavaScript
rendering, uploads, scheduling, previews, tags, or content history.
