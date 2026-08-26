PR 13G — Admin Operations UI

Repository state

Expected branch:

feature/13g-admin-operations-ui

Base branch:

Latest main.

Worktree:

Frontend worktree.

Dependencies:

- PR 13A — Admin Application Foundation
- PR 11H — Admin Operations API Expansion for Dashboard
- PR 13F — Admin Dashboard Operational Summary
- Existing administrator authentication/session infrastructure
- Existing Admin API client and runtime response-validation patterns
- Existing Operations/Admin backend implementation

PR 13F owns the read-only /admin Dashboard and its aggregate Operations Summary integration.

This task must not rebuild, replace, or duplicate the Dashboard. It implements the detailed Operations frontend that the Dashboard can link into.

The backend Operations API is already implemented and is authoritative. Do not create dashboard-specific or frontend-specific backend endpoints.

Read first

- AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/11h-admin-operations-dashboard-api.md
- .codex/tasks/13e-admin-dashboard-operations-ui.md
- .codex/tasks/13f-admin-dashboard-operational-summary.md
- apps/admin/src/App.tsx
- apps/admin/src/components/AdminShell.tsx
- apps/admin/src/api/adminApi.ts
- apps/admin/src/api/adminApi.test.ts
- apps/admin/src/features/dashboard/
- apps/admin/src/App.test.tsx
- apps/admin/src/styles.css
- apps/backend/operations/api/router.py
- apps/backend/operations/api/administration_router.py
- apps/backend/operations/api/models.py
- focused backend tests covering Operations/Admin endpoints

Before implementing, inspect the merged repository and backend tests. Backend implementation is authoritative for paths, schemas, validation, permissions, error codes, pagination, and mutation semantics.

Primary change area

- apps/admin/src/App.tsx
- apps/admin/src/components/AdminShell.tsx
- apps/admin/src/api/adminApi.ts
- apps/admin/src/api/adminApi.test.ts
- apps/admin/src/features/operations/
- apps/admin/src/App.test.tsx
- apps/admin/src/styles.css
- Operations Storybook stories
- apps/admin/README.md where useful

Canonical implementation examples

Reuse the existing Admin application patterns for:

- authenticated cookie-based requests
- AbortSignal
- AdminApiError
- strict runtime response validation
- session expiry
- loading, empty and retry states
- responsive page layouts
- accessible forms and buttons
- focus management
- pagination
- deterministic Storybook stories
- Vitest
- React Testing Library

Use the existing Dashboard implementation as the closest Operations-specific frontend example for authenticated Operations requests and error handling.

Do not introduce:

- another HTTP client
- another state-management framework
- another validation framework
- a new design system
- custom table/pagination infrastructure when existing application patterns are sufficient
- a charting dependency

Relevant symbols

Frontend:

- App
- Protected
- AdminShell
- FullPageStatus
- AdminApi
- createAdminApi
- AdminApiError
- request
- successfulJson
- getOperationsSummary
- DashboardPage

Backend:

- OperationsRootResponse
- OperationsHealthResponse
- CacheRegionsResponse
- CacheRegionResponse
- ActionSuccessResponse
- MaintenanceResponse
- MaintenanceUpdateRequest
- AuditEntryResponse
- AuditPageResponse
- AuditDetailResponse
- OperationalJobResponse
- OperationalJobsResponse
- AdministrativeErrorCode
- require_operations_read
- require_operations_execute

Expected change surface

Implement a detailed Operations domain inside apps/admin.

Expected frontend routes:

/admin/operations
/admin/operations/health
/admin/operations/cache
/admin/operations/maintenance
/admin/operations/jobs
/admin/operations/jobs/:jobId
/admin/operations/audit
/admin/operations/audit/:entryId

Small shared Admin component changes are allowed where they genuinely reduce duplication.

Backend production changes are not expected.

Excluded areas

- Reimplementation of the /admin Dashboard
- New backend Operations endpoints
- Changes to backend Operations domain behaviour
- Backend authentication or authorization changes
- Assistant management
- Knowledge Source management
- Assistant behaviour, publishing or preview
- ingestion execution controls
- job retry, cancellation, deletion or execution
- arbitrary queue manipulation
- arbitrary Redis access
- arbitrary cache-value browsing
- database administration
- shell or terminal access
- monitoring infrastructure
- Prometheus/Grafana
- log aggregation
- alert configuration
- deployment controls
- fake operational data
- historical operational charts
- client-side authorization as a security boundary
- aggressive polling
- unrelated frontend refactoring

Unknowns Codex must verify

Before making changes, verify against the merged backend implementation and its tests:

- exact Operations root response
- exact health response and dependency-check schema
- exact cache response fields and nullable statistics
- exact maintenance response fields
- maintenance message validation and disable semantics
- exact action success response
- administrative error codes
- cache region-name validation
- cache-key validation
- audit result values
- audit filter parameters
- audit date-filter serialization
- audit pagination semantics
- audit-detail metadata constraints
- operational job status values
- operational job pagination/filter semantics
- whether all job last_error values are already safe for administrator display
- behaviour when a requested audit entry or job does not exist
- whether read and execute permissions differ for the authenticated administrator
- whether /admin/operations capabilities expose execute permissions or only available domains
- whether frontend auth state contains any permission information
- existing confirmation-dialog conventions
- existing pagination conventions
- existing date/time and duration formatting utilities
- whether Dashboard cards currently link or are intended to link into Operations routes

Do not infer permission semantics that are not represented by the backend.

⸻

Objective

Implement the detailed administrator Operations frontend using the existing /admin/operations backend API.

The result must give an authenticated administrator safe access to:

- detailed health diagnostics
- cache inspection and administration
- maintenance-mode inspection and control
- operational job browsing and detail
- administrative audit browsing and detail

The Operations frontend must consume the existing authoritative Operations API.

It must not reconstruct backend state from unrelated APIs and must not introduce frontend-specific backend calls.

Read-only inspection and production-affecting actions must be visually and behaviourally distinct.

Destructive or operationally significant mutations must always require deliberate administrator confirmation.

Current architecture

The Admin frontend currently has an authenticated application shell and routes for:

/admin
/admin/assistants
/admin/knowledge-sources

PR 13F supplies the /admin Dashboard through:

GET /admin/operations/summary

The existing Admin API client already owns:

Admin component
↓
AdminApi
↓
shared authenticated request()
↓
/admin/\*

The detailed Operations backend already exists.

Its current namespace includes:

/admin/operations
├── GET /
├── GET /summary
├── GET /health
├── GET /cache
├── POST /cache/clear
├── POST /cache/regions/{region}/clear
├── POST /cache/key
├── GET /maintenance
├── PUT /maintenance
├── GET /jobs
├── GET /jobs/{job_id}
├── GET /audit
└── GET /audit/{entry_id}

Operations read access is enforced by the backend namespace.

Production-affecting mutations additionally require backend Operations execute authorization.

The frontend may improve usability based on capabilities it actually receives, but backend authorization remains authoritative.

Required implementation

1. Add Operations navigation and routing

Add an Operations destination to the authenticated Admin navigation.

Implement:

/admin/operations
/admin/operations/health
/admin/operations/cache
/admin/operations/maintenance
/admin/operations/jobs
/admin/operations/jobs/:jobId
/admin/operations/audit
/admin/operations/audit/:entryId

/admin/operations must provide a lightweight Operations landing page rather than duplicating the Dashboard.

It should provide navigation to the detailed operational areas available from the Operations API.

Use:

GET /admin/operations

where useful to verify available backend capabilities.

Preserve:

- Dashboard navigation
- Assistants navigation
- Knowledge Sources navigation
- logout
- protected-route behaviour
- active navigation state
- deep links
- refresh behaviour
- not-found handling

Navigation and page titles must work for nested Operations routes.

2. Extend the Admin API client

Extend the existing AdminApi; do not call fetch directly from Operations components.

Add typed methods corresponding to the backend contract, including:

getOperations()
getOperationsHealth()
listCacheRegions()
clearCache()
clearCacheRegion()
invalidateCacheKey()
getMaintenance()
updateMaintenance()
listOperationalJobs()
getOperationalJob()
listAuditEntries()
getAuditEntry()

Use the exact merged backend paths and HTTP methods.

Every request must:

- use the configured API base URL
- use the existing credentialed request function
- preserve administrator cookies
- preserve AbortSignal
- map backend failures through AdminApiError
- preserve existing 401 session-expiry behaviour
- safely handle 403
- validate every successful response at runtime
- reject malformed successful responses as invalid_response
- avoid logging response bodies or sensitive submitted values

Convert backend snake_case into the frontend’s established camelCase models at the API boundary.

Do not automatically retry mutations.

3. Strict Operations response validation

Runtime validation must cover the complete API response structures.

Do not silently:

- coerce malformed fields
- replace missing values with zero
- ignore unexpected fields where exact response validation is already the Admin convention
- treat unknown enum/status values as valid
- invent timestamps or identifiers

Validate, where applicable:

- UUID identifiers
- aware/parseable timestamps
- non-negative counts
- non-negative durations
- nullable fields
- pagination bounds
- health enums
- job statuses
- audit result values
- cache statistics
- action-success responses
- request/correlation identifiers

Malformed 2xx responses must not be rendered as valid operational state.

4. Operations landing page

Implement /admin/operations as a detailed-operations entry point.

Expose implemented sections such as:

- Health
- Cache
- Maintenance
- Jobs
- Audit

Do not reproduce the full Dashboard summary.

Where the Operations root response supplies capabilities, use them to determine which real Operations sections are advertised.

Do not invent capabilities.

If a capability is unavailable, do not render a link that leads to unsupported functionality.

A capabilities response is a usability aid, not an authorization boundary.

5. Health diagnostics

Implement /admin/operations/health using:

GET /admin/operations/health

Render:

- overall health state
- generated/check time
- each backend-provided dependency/check result
- safe diagnostic information supplied by the backend

Support all backend-defined states.

At minimum distinguish visibly:

- healthy
- degraded
- unhealthy
- unknown

Do not rely on colour alone.

A successful HTTP request containing a degraded or unhealthy payload is still a successful diagnostic request and must render the reported state rather than a generic request-error screen.

Provide manual refresh.

Do not add aggressive polling.

Do not expose:

- raw exceptions
- credentials
- connection strings
- arbitrary infrastructure internals not supplied by the contract

6. Cache inspection

Implement /admin/operations/cache.

Load:

GET /admin/operations/cache

Render every registered region and only the statistics supplied by the backend.

Current response fields include:

- name
- entries
- estimated memory bytes
- hit count
- miss count
- hit ratio

Nullable statistics must display an explicit unavailable state rather than being converted to zero.

Do not expose cache values.

Do not implement arbitrary cache browsing.

7. Cache administration

Support the existing cache mutation endpoints:

POST /admin/operations/cache/clear
POST /admin/operations/cache/regions/{region}/clear
POST /admin/operations/cache/key

Clear all cache regions

Require explicit confirmation.

The confirmation must clearly state that all registered cache regions will be cleared.

Prevent duplicate submission while pending.

Clear one region

Require explicit confirmation identifying the region.

Do not allow the user to accidentally execute against a different region from the one shown in the confirmation.

Invalidate one key

Require:

- region
- cache key

Respect backend region/key validation.

Do not:

- persist cache keys in browser storage
- include submitted cache keys in frontend logs
- display arbitrary cache values

After confirmed success:

- refresh relevant cache state
- display an accessible success acknowledgement
- prevent accidental duplicate execution

On an ambiguous network failure after submission, do not claim that the operation definitely failed or definitely did not happen.

Require authoritative refresh where necessary before encouraging another mutation.

8. Maintenance mode

Implement /admin/operations/maintenance.

Load the current state from:

GET /admin/operations/maintenance

Render the backend-supported fields:

- enabled
- message
- updated time
- updated by

Support updates through:

PUT /admin/operations/maintenance

Use the exact backend request model.

Enabling maintenance

Require confirmation before execution.

The confirmation must clearly identify that this changes production-facing application behaviour.

Disabling maintenance

Require deliberate administrator interaction and a pending state.

It need not use unnecessarily alarming wording.

After a successful update:

- replace or reload the authoritative maintenance state
- ensure subsequent Dashboard data can refresh naturally
- announce the result accessibly

On an ambiguous network failure after submission:

- do not state confidently that maintenance mode remains unchanged
- require an authoritative refresh before another mutation where necessary

Do not duplicate maintenance enforcement in the frontend.

9. Operational jobs list

Implement /admin/operations/jobs.

Use:

GET /admin/operations/jobs

Render backend-supported fields including:

- job ID
- job type
- status
- created time
- started time
- completed time
- duration
- retry count
- execution node
- safe last error

Support backend pagination.

Support the backend status filter where exposed.

Current backend status values must be verified before implementation and handled exhaustively.

Filters should be represented in the URL query string where consistent with existing Admin navigation so the page remains refreshable and shareable.

Changing filters must reset pagination appropriately.

Do not fetch all jobs into the browser and paginate client-side.

Do not implement:

- retry
- cancellation
- deletion
- manual execution
- queue manipulation

10. Operational job detail

Implement:

/admin/operations/jobs/:jobId

using:

GET /admin/operations/jobs/{job_id}

Render the authoritative job detail.

Handle:

- valid job
- missing job
- malformed response
- permission failure
- network/server failure
- session expiry

Do not render untrusted strings as HTML.

Do not expose raw stack traces unless the backend contract explicitly guarantees the corresponding field as administrator-safe display content.

11. Audit log list

Implement /admin/operations/audit.

Use:

GET /admin/operations/audit

Render the backend-supported summary fields:

- timestamp
- user
- action
- resource
- result

Support backend pagination.

Support the backend-provided filters:

- user
- action
- resource
- result
- date from
- date to

Use the exact backend query parameter names and serialization.

Filter state should use URL query parameters where consistent with existing Admin patterns.

Changing filters must reset pagination.

Reject an obviously inverted local date range before sending it where practical, while retaining backend validation as authoritative.

Never fetch an unbounded audit history.

12. Audit detail

Implement:

/admin/operations/audit/:entryId

using:

GET /admin/operations/audit/{entry_id}

Render the authoritative fields, including where supplied:

- timestamp
- actor/user
- action
- resource
- result
- duration
- request ID
- correlation ID
- structured metadata

Render metadata defensively as data.

Do not interpret arbitrary metadata as HTML.

Do not expose anything omitted by the backend.

Handle missing/deleted entries safely.

13. Mutation safety

Operations mutations affect production state.

For every mutation:

- no execution on initial render
- no execution on confirmation-dialog open
- require deliberate final user action
- disable duplicate submission while pending
- do not automatically retry
- preserve safe existing read-only data on failure
- map 401 through existing session expiry
- render 403 as a permission failure
- distinguish definitive backend rejection from ambiguous network outcomes
- refresh authoritative state after successful execution

Confirmation text must identify the action and scope.

A generic reusable confirmation such as Are you sure? is insufficient for destructive Operations actions.

14. Error and loading states

Every Operations page must support:

- loading
- populated
- legitimate empty state
- retryable network/server failure
- permission denied
- unauthenticated/session expired
- malformed successful response

Loading states must not display invented operational zeroes.

A 403 must not be presented as an empty or healthy state.

A malformed 2xx response must become invalid_response.

Where existing valid data is available during a failed refresh, retain it where the existing Admin architecture supports that safely.

15. Accessibility

Operations UI must:

- use correct heading hierarchy
- expose text labels for operational states
- not rely on colour alone
- have keyboard-operable controls
- use labelled form controls
- expose mutation pending states accessibly
- move or restore focus sensibly around confirmation interactions
- provide meaningful button names
- keep tables or alternative layouts usable at narrow widths
- avoid horizontal page scrolling where practical

16. Dashboard integration

PR 13F remains the owner of /admin.

Do not replace its single-summary-request architecture.

Where Dashboard summary cards logically correspond to detailed Operations pages, small navigation-link additions are permitted.

Examples:

health → /admin/operations/health
cache → /admin/operations/cache
jobs → /admin/operations/jobs
audit → /admin/operations/audit
maintenance → /admin/operations/maintenance

Do not make the Dashboard fetch detailed Operations endpoints.

The dependency direction must remain:

Dashboard
↓
GET /admin/operations/summary
Detailed Operations pages
↓
corresponding /admin/operations/\* endpoint

Acceptance criteria

- Operations is present in authenticated Admin navigation.
- /admin/operations provides a real detailed-operations entry point without duplicating the Dashboard.
- Health, Cache, Maintenance, Jobs and Audit routes are implemented.
- Job and Audit detail routes are implemented.
- Existing Dashboard, Assistant and Knowledge Source routes remain functional.
- All Operations requests pass through the existing AdminApi.
- Components do not call fetch directly.
- The frontend uses existing /admin/operations/\* APIs rather than introducing backend endpoints.
- Successful Operations responses are runtime validated before presentation.
- Malformed 2xx responses result in invalid_response.
- 401 uses the existing session-expiry flow.
- 403 produces an explicit permission state rather than a healthy/empty state.
- Health renders backend-reported degraded and unhealthy states correctly even when HTTP status is 200.
- Cache regions and nullable statistics render accurately.
- Clearing all cache regions requires explicit scope-specific confirmation.
- Clearing one cache region requires confirmation naming that region.
- Cache-key invalidation requires a region and key and does not persist keys locally.
- Maintenance state is read from the authoritative backend endpoint.
- Maintenance changes require deliberate confirmation and cannot double-submit.
- Operational jobs use server pagination and supported status filtering.
- No job retry/cancel/delete/execute controls are introduced.
- Audit history uses server pagination.
- Backend-supported audit filters work and changing them resets pagination.
- Invalid local audit date ranges are handled safely.
- Audit metadata is rendered as data, never arbitrary HTML.
- Operational mutations are never automatically retried.
- Ambiguous mutation network failures do not falsely claim that no state change occurred.
- Successful mutations cause the corresponding authoritative data to refresh.
- Loading states do not display invented zeroes.
- Empty states are visibly different from failures.
- Status presentation does not rely on colour alone.
- Operations routes work at narrow and desktop widths.
- Existing Admin route, authentication, logout and not-found behaviour does not regress.
- PR 13F remains the owner of Dashboard summary behaviour.
- Backend production code is unchanged.

Tests to add or update

Admin API tests

Extend:

apps/admin/src/api/adminApi.test.ts

Cover:

- Operations root request and exact validation
- health request
- healthy/degraded/unhealthy/unknown responses
- malformed health responses
- cache list
- nullable cache statistics
- malformed cache responses
- clear-all request
- clear-region request and URL encoding
- invalidate-key request body
- action-success response validation
- maintenance read
- maintenance update request/response
- jobs pagination
- job status filtering
- job detail
- audit pagination
- audit filters
- audit date serialization
- audit detail
- 400/401/403/404/409/422/5xx mapping as applicable
- malformed JSON
- malformed 2xx payloads
- network failures
- AbortSignal cancellation

Operations component/page tests

Add focused tests under:

apps/admin/src/features/operations/

Cover:

- Operations landing/capabilities
- unavailable capability handling
- health states
- dependency/check rendering
- manual health refresh
- cache statistics
- cache empty state
- clear-all confirmation
- clear-region confirmation
- cache-key validation/submission
- duplicate mutation prevention
- mutation success
- mutation backend failure
- ambiguous mutation network failure
- maintenance enabled/disabled states
- maintenance confirmation
- jobs list
- jobs empty state
- jobs filtering
- jobs pagination
- job detail
- audit list
- audit filtering
- audit pagination
- invalid audit date range
- audit detail
- metadata defensive rendering
- missing job/audit detail
- permission failures
- session expiry
- malformed successful responses
- retry states

Routing tests

Update:

apps/admin/src/App.test.tsx

Cover:

- Operations navigation
- active Operations navigation for nested routes
- /admin/operations
- /admin/operations/health
- /admin/operations/cache
- /admin/operations/maintenance
- /admin/operations/jobs
- /admin/operations/jobs/:jobId
- /admin/operations/audit
- /admin/operations/audit/:entryId
- direct deep links
- protected routes
- logout regression
- Dashboard regression
- Assistant routes regression
- Knowledge Source routes regression
- not-found regression

Storybook

Add deterministic stories for important states including:

- Operations landing
- healthy/degraded health
- cache populated/empty
- maintenance enabled
- jobs populated/empty
- audit populated/empty
- permission failure
- destructive-action confirmation

Stories must not require a live backend.

Verification commands

cd apps/admin
npm test
npm run lint
npm run typecheck
npm run build
npm run build-storybook

Run focused Operations API and component tests first, followed by the full Admin verification suite.

Backend production files must remain unchanged.
