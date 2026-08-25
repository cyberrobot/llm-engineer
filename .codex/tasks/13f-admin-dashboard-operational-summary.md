# PR 13F — Admin Dashboard Operational Summary

## Repository state

Expected branch:

`feature/13f-admin-dashboard-operational-summary`

Base branch:

Latest `main`.

Worktree:

Frontend worktree.

Dependencies:

- PR 13A — Admin Application Foundation
- PR 11H — Admin Operations API Expansion for Dashboard
- Existing administrator authentication/session infrastructure
- Existing Admin API client and runtime response-validation patterns

PR 11H is merged on the selected base. Its backend contract is authoritative. This task is the
narrow P0 Dashboard extracted from PR 13E; detailed Operations pages and production-affecting
operations remain out of scope.

### Read first

- `AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/11h-admin-operations-dashboard-api.md`
- `.codex/tasks/13a-admin-application-foundation.md`
- `.codex/tasks/13e-admin-dashboard-operations-ui.md`
- `apps/admin/src/App.tsx`
- `apps/admin/src/components/AdminShell.tsx`
- `apps/admin/src/api/adminApi.ts`
- `apps/admin/src/api/adminApi.test.ts`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/styles.css`
- `apps/backend/operations/api/models.py`
- focused backend tests for `GET /admin/operations/summary`

### Primary change area

- `apps/admin/src/App.tsx`
- `apps/admin/src/api/adminApi.ts`
- `apps/admin/src/api/adminApi.test.ts`
- `apps/admin/src/features/dashboard/`
- `apps/admin/src/App.test.tsx`
- `apps/admin/src/styles.css`
- Dashboard Storybook stories and Admin documentation where useful

### Canonical implementation examples

Reuse the existing Admin application patterns for authenticated requests, cookie sessions,
`AbortSignal`, `AdminApiError`, runtime response validation, session expiry, loading and retry
states, accessible status text, responsive CSS, Storybook, Vitest, and React Testing Library.

Do not introduce another HTTP client, state manager, validation framework, design system, or
charting dependency.

### Relevant symbols

- `App`, `Protected`, `AdminShell`, `FullPageStatus`
- `AdminApi`, `createAdminApi`, `AdminApiError`, `request`, `successfulJson`
- `OperationsSummaryResponse`, `SummaryCacheResponse`, `SummaryJobsResponse`
- `SummaryAuditResponse`, `SummaryAssistantsResponse`, `SummaryKnowledgeSourcesResponse`
- `SummaryIngestionResponse`, `OperationsResponseMetadata`

### Expected change surface

Changes remain in the Admin frontend. Small shared Admin component changes are allowed only for
genuinely reusable presentation. Backend production changes are not expected.

### Excluded areas

- Backend Operations changes or new endpoints
- Operations detail, health dependency, cache administration, maintenance mutation, audit browsing,
  operational-job browsing, retry, cancellation, or ingestion controls
- Assistant, Knowledge Source, behaviour, publishing, preview, or public widget changes
- Prometheus/Grafana, aggressive polling, historical charts, fake trends/incidents, infrastructure
  diagnostics, and unrelated frontend refactoring

### Unknowns Codex verified

- The configured API base URL is combined with `/admin/operations/summary`; the application base URL
  already represents the backend origin and does not include `/api`.
- Successful summary responses intentionally omit `request_id` through FastAPI response-model
  exclusion, although the reusable backend metadata model permits it elsewhere.
- Required top-level fields are `generated_at`, `health`, `maintenance`, `cache`, `jobs`, `audit`,
  `assistants`, `knowledge_sources`, and `ingestion`.
- Health values are `healthy`, `degraded`, `unhealthy`, and `unknown`.
- `oldest_queued_age_seconds` is a required non-negative numeric value and zero is valid.
- `workers_observed` is a non-negative count; it does not guarantee currently online workers.
- `knowledge_sources.failed` is the only nullable dashboard aggregate and must remain unavailable
  when null.
- Existing authenticated feature requests call `auth.sessionExpired()` on `unauthenticated`.
- The application has shared full-page status treatment but no reusable dashboard/card or formatting
  utility. Existing feature CSS uses simple responsive cards and grids.
- Storybook uses deterministic component stories without a network mocking layer.

---

## Objective

Replace the `/admin` placeholder with an authenticated operational Dashboard backed exclusively by:

`GET /admin/operations/summary`

The Dashboard lets an administrator understand current service, content, ingestion, cache, job, and
attention state without loading or reconstructing aggregates from other endpoints.

## Current architecture

The protected Admin shell owns `/admin`, `/admin/assistants`, and `/admin/knowledge-sources`. The
Dashboard navigation destination already exists but is a placeholder. Components consume backend
data only through the injected `AdminApi`, whose shared request function owns credentials, safe error
mapping, and cancellation. PR 11H composes authoritative operations, Assistant, Knowledge Source,
and ingestion read models into the single summary endpoint.

## Required implementation

1. Extend `AdminApi` with `getOperationsSummary(signal?: AbortSignal)` and a frontend-owned typed
   `OperationsSummary` model. Keep backend snake_case at validation only and expose consistent
   frontend camelCase fields.
2. Request `/admin/operations/summary` through the shared credentialed request function. Preserve
   cancellation and existing 401, 403, network, server, and safe malformed-response handling.
3. Strictly validate the exact successful response: aware/parseable generated timestamp, allowed
   health value, boolean maintenance, exact nested keys, non-negative integer counts, non-negative
   finite queue age, and nullable failed Knowledge Source count only. Do not default malformed or
   missing values to zero.
4. Render the Dashboard at `/admin`, leaving the existing shell and navigation in place.
5. Show service health, maintenance enabled/disabled, and generated time with text that does not rely
   on colour.
6. Show Assistant total/published and Knowledge Source total/enabled/failed from summary data only.
   Present null failed Knowledge Sources as “Not reported”. Link these sections to existing routes.
7. Show ingestion queued/running/recoverable/failed, concise oldest queued duration, and “Workers
   observed”. Do not call workers online or infer a stuck queue threshold.
8. Show cache region count, running/failed operational jobs, and administrative actions today. Do not
   imply unsupported cache health, traffic, or incident semantics.
9. Derive an operational-attention list deterministically from degraded/unhealthy/unknown health,
   maintenance enabled, failed jobs, failed/recoverable ingestion, queued ingestion with no observed
   workers, and known failed Knowledge Sources. Render an explicit clear state when none apply.
10. Show intentional loading without false zeroes; for retryable and permission/malformed failures,
    show safe text and manual retry. A 401 expires the existing session. Manual refresh is sufficient;
    do not add polling.
11. Keep the layout usable without horizontal scrolling at narrow and desktop widths, with valid
    heading hierarchy, accessible status labels, and keyboard-operable links/buttons.
12. Preserve authentication, logout, active navigation, Assistant and Knowledge Source routes,
    deep links, and not-found behaviour.

## Acceptance criteria

- [ ] `/admin` renders an authenticated Dashboard, not the placeholder.
- [ ] Exactly one Operations Summary request supplies all Dashboard aggregates.
- [ ] The API method uses the configured base URL, cookies, cancellation, safe errors, and session
      semantics already owned by `AdminApi`.
- [ ] Populated, zero, null-failure, degraded/unhealthy, maintenance, and clear-attention states render
      accurately.
- [ ] Malformed 2xx payloads produce `invalid_response`, including invalid timestamps, enums, counts,
      queue age, nesting, missing keys, and unexpected fields.
- [ ] Loading never renders invented zero values.
- [ ] Retryable failures provide manual retry; 403 is not rendered as a healthy empty Dashboard; 401
      returns to the existing login flow.
- [ ] Oldest queue age is human-readable and zero remains valid.
- [ ] Status and attention semantics use visible text and do not rely on colour alone.
- [ ] Dashboard cards link only to existing Assistant and Knowledge Source pages where appropriate.
- [ ] The layout works at narrow widths without adding a charting or design-system dependency.
- [ ] Existing Admin routes and tests continue to pass; backend production code is unchanged.

## Tests to add or update

- Extend `apps/admin/src/api/adminApi.test.ts` for the exact request, populated/zero/null responses,
  strict validation, 401/403/5xx/network/malformed JSON, and cancellation.
- Add `apps/admin/src/features/dashboard/Dashboard.test.tsx` or focused equivalent tests for loading,
  populated/zero/degraded/maintenance states, formatting, attention derivation, clear state, retry,
  forbidden/malformed failures, session expiry, links, and absence of secondary aggregate requests.
- Update `apps/admin/src/App.test.tsx` for routing, protection, active Dashboard navigation, logout,
  existing routes, and not-found regression behaviour.
- Add deterministic Dashboard Storybook stories consistent with existing Admin conventions.

## Verification commands

```bash
cd apps/admin
npm test
npm run lint
npm run typecheck
npm run build
npm run build-storybook
```

Run focused API and Dashboard tests first, followed by the full Admin checks above.
