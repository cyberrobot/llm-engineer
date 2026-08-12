# Operations administration

The operations module owns production runtime administration independently from assistant editing,
retrieval, ingestion execution, and publishing. All routes are under `/admin/operations` and require
the `X-API-Key` administrator credential. Read routes require `operations:read`; state-changing
routes additionally require `operations:execute`.

## Capabilities

- `GET /admin/operations/cache` lists registered cache regions. Statistics that the backing cache
  cannot provide cheaply are `null`; the API does not scan keys merely to fabricate counts.
- `POST /admin/operations/cache/clear`,
  `POST /admin/operations/cache/regions/{region}/clear`, and
  `POST /admin/operations/cache/key` invalidate only registered namespaces. They never flush a
  shared Redis database.
- `GET|PUT /admin/operations/maintenance` reads or changes maintenance mode. Enabling maintenance
  accepts an optional operator-facing message. Public assistant traffic returns a generic
  `503 maintenance_mode` response while administrator routes, liveness, health, and readiness
  probes remain reachable. The public response retains CORS and request-correlation headers and
  never includes the configured operator message. Readiness reports `not_ready` while maintenance
  is enabled; liveness remains `alive`.
  Maintenance is enforced centrally for the published
  `/public/assistants/{assistant_slug}/chat` route and the existing unauthenticated
  `/assistant/chat` and `/rag-chat` routes. `/assistant/health`, `/admin/auth/**`,
  `/admin/operations/**`, and the health probes remain reachable so operators can authenticate,
  diagnose the service, and disable maintenance.
- `GET /admin/operations/jobs` and `GET /admin/operations/jobs/{id}` provide a read-only projection
  of existing background ingestion jobs. Pagination uses `limit` (1–200) and a zero-based `offset`;
  list filtering accepts the established job statuses.
- `GET /admin/operations/audit` browses administrative action records newest first. It accepts
  exact `user`, `action`, `resource`, and `result` filters, inclusive `date_from`/`date_to` values,
  `limit` (1–200), and `offset`. `GET /admin/operations/audit/{id}` includes request/correlation IDs,
  duration, outcome, and redacted safe metadata.
- `GET /admin/operations/summary` aggregates health, maintenance, cache-region count, running/failed
  job counts, and today's administrative audit count from the owning services. It also returns a
  server-generated UTC `generated_at` timestamp and dashboard aggregates for Assistants, Knowledge
  Sources, and ingestion. Existing summary fields remain unchanged.

The additive dashboard sections have this shape:

```json
{
  "generated_at": "2026-08-11T10:00:00Z",
  "assistants": {"total": 3, "published": 2},
  "knowledge_sources": {"total": 7, "enabled": 5, "failed": null},
  "ingestion": {
    "queued": 4,
    "running": 1,
    "recoverable": 1,
    "failed": 2,
    "oldest_queued_age_seconds": 90.0,
    "workers_observed": 1
  }
}
```

`assistants.published` counts Assistants with an authoritative published behaviour revision. It is
not inferred from Assistant status or visibility. Knowledge Sources currently have only
enabled/disabled retrieval lifecycle state, so `knowledge_sources.failed` is `null`; the API does
not infer a source failure from an ingestion job or silently report an unsupported count as zero.

The ingestion section reuses the established operational-status query. `recoverable` counts running
jobs whose lease is absent or expired. `workers_observed` counts distinct worker identifiers on
running jobs with a lease beyond the summary timestamp; it is an observation of current leased work,
not a registry of all deployed workers. `oldest_queued_age_seconds` is calculated against the same
server timestamp returned as `generated_at`. `failed` counts authoritative failed ingestion jobs.

## State, safety, and errors

Production and staging deployments with `DATABASE_URL` store maintenance state and administrative
audit records in PostgreSQL. This shared state keeps maintenance behaviour consistent across
application instances and process restarts. Development and test processes use the same service
interfaces with process-local stores. The schema is created by the normal database initialization
path and includes timestamp plus supported-filter indexes for audit pagination.

Whole-cache clearing, region clearing, and maintenance updates are idempotent. Invalidating a
specific absent key returns `cache_key_not_found`. Before an authenticated state-changing action is
attempted, a durable `STARTED` audit intent is written; it is then updated to `SUCCESS` or `FAILURE`.
If completion recording fails, the durable intent remains available for investigation. Audit
metadata uses an explicit safe-field allowlist, and cache keys, maintenance messages, credentials,
cookies, authorization values, private configuration, and request payloads are not copied into
audit records. Browsing also reapplies redaction to protect older records.

Job visibility is a read-only projection over the established document-ingestion job repository;
it does not query the table through a parallel operations repository or add mutation capabilities.
Only the existing safe failure code is exposed, not the persisted failure message. Job responses
also expose the safe `job_type` discriminator (`ingestion`) without provider or execution details.

Mutating responses include `request_id` and `correlation_id`. This service currently uses the
validated request ID as the correlation ID so logs, responses, and audit records share one stable
identifier.

Errors use the standard administrative envelope:

```json
{
  "detail": {
    "code": "cache_region_not_found",
    "message": "The cache region was not found."
  }
}
```

Stable codes include `admin_authentication_required`, `admin_permission_denied`,
`invalid_admin_request`, `cache_region_not_found`, `cache_key_not_found`,
`audit_entry_not_found`, `operational_job_not_found`, and `dependency_unavailable`. Responses never
include implementation exceptions, credentials, request payloads, or provider responses.

## Repository-state constraints

The repository has no concrete feature-flag or mutable runtime-flag abstraction and no known flag
consumers. PR 10C therefore does not invent a standalone feature-flag platform or expose synthetic
flags. A future real flag provider can be integrated when a domain-owned flag exists.

The current prerequisite branch provides health, readiness, dependency diagnostics, and Prometheus
metrics, but it does not expose the runtime-configuration visibility described by the PR 10B task.
PR 10C leaves that prerequisite mismatch explicit instead of recreating unrelated PR 10B scope.
