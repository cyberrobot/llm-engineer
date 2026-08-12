PR 13E — Admin Dashboard & Operations UI

Repository state

Expected branch:

feature/13e-admin-dashboard-operations-ui

Base branch:

main

Worktree:

Frontend

Dependencies:

* PR 13A — Admin Application Foundation
* PR 13B — Admin Assistant Management Foundation
* PR 13C — Assistant Knowledge & Retrieval Configuration
* PR 13D — Behaviour, Prompts, Publishing & Preview
* PR 11H — Operations/Admin API expansion required for dashboard functionality
* Existing administrator authentication and session infrastructure
* Existing Operations/Admin backend foundation and contracts

PR 11H must be merged before implementation begins.

The backend implementation is authoritative for endpoint paths, request models, response models, permissions, error codes, pagination and mutation semantics.

Read first

* AGENTS.md
* docs/architecture/repository-map.md
* docs/architecture/dependency-rules.md
* apps/admin/
* apps/admin/package.json
* apps/admin/src/App.tsx
* apps/admin/src/api/
* Existing admin authentication/session handling
* Existing Assistant, Knowledge Source and Behaviour admin pages
* Existing admin Storybook configuration and stories
* Existing admin tests and test utilities
* apps/backend/operations/
* apps/backend/operations/api/router.py
* apps/backend/operations/api/administration_router.py
* apps/backend/operations/api/models.py
* Focused backend tests covering Operations/Admin endpoints
* PR 11H task/spec and implementation

Before making changes, inspect the actual merged repository state.

Do not infer API contracts from this specification when the backend implementation provides an authoritative answer.

Primary change area

* apps/admin/src/
* Admin routing/navigation
* Dashboard page
* Operations pages/components
* Admin API client
* Operations API response validation
* Operations query/mutation state
* Admin tests
* Admin Storybook stories
* apps/admin/README.md where necessary

Canonical implementation examples

Use the existing admin application as the canonical frontend implementation.

In particular, reuse established patterns for:

* authenticated API requests
* administrator session-expiry handling
* runtime response validation
* TanStack Query or the repository’s existing query/cache solution
* loading states
* empty states
* retryable failures
* safe API error rendering
* pagination
* confirmation dialogs
* mutation pending states
* focus restoration
* accessible forms and tables
* responsive page layouts
* Storybook stories
* MSW/network-boundary tests
* Vitest and React Testing Library
* navigation and page-header composition

Do not introduce a second frontend architecture for operations functionality.

Prefer existing libraries already used by apps/admin instead of custom implementations.

Relevant symbols

Codex must verify exact names before implementation.

Expected concepts include:

* admin router
* authenticated admin shell
* primary navigation
* admin API client
* shared authenticated request function
* API error model
* session-expiry handling
* dashboard route
* operations route
* query client
* mutation handling
* confirmation dialog
* loading/error/empty-state components
* pagination controls
* administrator permissions or capabilities if exposed

Expected backend concepts include:

* /admin/operations
* /admin/operations/summary
* /admin/operations/health
* /admin/operations/cache
* /admin/operations/cache/clear
* /admin/operations/cache/regions/{region}/clear
* /admin/operations/cache/key
* /admin/operations/maintenance
* /admin/operations/audit
* /admin/operations/audit/{entry_id}
* /admin/operations/jobs
* /admin/operations/jobs/{job_id}

These paths reflect the current repository implementation but Codex must verify the final PR 11H contract before coding.

Do not invent:

* endpoint paths
* permissions
* cache region names
* job states
* health states
* audit fields
* maintenance semantics
* pagination semantics
* error codes
* mutation responses

Expected change surface

Expected work includes:

* Replace the Dashboard placeholder with a functional operational dashboard.
* Add an Operations section to the authenticated admin navigation where suitable.
* Add typed Operations/Admin API methods.
* Add runtime validation of Operations/Admin responses.
* Implement operational summary presentation.
* Implement health/dependency status presentation.
* Implement cache inspection and administration.
* Implement maintenance-mode visibility and control.
* Implement operational job browsing and detail.
* Implement administrative audit-log browsing and detail.
* Add confirmation and safety controls around destructive or production-affecting actions.
* Integrate operations requests with existing authentication/session handling.
* Add responsive and accessible UI states.
* Add deterministic Storybook stories.
* Add API, component and workflow tests.
* Update admin documentation.

Excluded areas

Do not implement or refactor:

* backend Operations/Admin functionality
* backend authentication or authorization
* Assistant management
* Assistant behaviour editing
* Assistant publishing
* Assistant preview
* Knowledge Source management
* ingestion orchestration
* job execution or retry infrastructure
* audit persistence
* cache implementation
* maintenance-mode enforcement
* monitoring infrastructure
* Prometheus/Grafana dashboards
* log aggregation
* alerting
* infrastructure deployment controls
* arbitrary database administration
* shell/terminal access
* arbitrary Redis access
* arbitrary cache-key browsing
* queue administration unless explicitly exposed by PR 11H
* manual job execution or cancellation unless explicitly exposed by PR 11H
* feature flags unless explicitly exposed by PR 11H
* user/administrator account management
* public Assistant widget changes
* unrelated apps/rag-ui changes
* a new general-purpose design system
* custom charting, table, pagination, form, modal, query-cache or validation frameworks where the project already has a suitable maintained dependency
* automatic polling at aggressive intervals
* fake operational data
* client-side authorization treated as a security boundary

Do not modify backend production code to make the frontend easier to implement.

If PR 11H and the frontend requirements materially disagree, report the backend contract mismatch instead of silently changing backend behaviour.

Unknowns Codex must verify

Before implementation, verify:

* exact operations API paths and HTTP methods
* exact response schemas
* exact administrative error codes
* whether read and execute permissions differ
* how insufficient operation permissions are represented
* whether the logged-in administrator response exposes permissions/capabilities
* whether the Operations root capability list should drive UI availability
* health status enum values
* health-check/dependency response structure
* operational-summary response structure
* cache-region statistics available to the frontend
* whether cache invalidation supports global, region and individual-key mutations
* maintenance-mode fields and validation rules
* whether the maintenance message is optional
* whether disabling maintenance requires preserving or clearing its message
* audit pagination and filtering parameters
* audit result values
* audit detail fields safe to render
* job pagination and filtering parameters
* supported operational job states
* whether job error details are already sanitized for administrator display
* whether job detail includes type/source/assistant metadata
* whether operations endpoints expose request/correlation identifiers
* existing frontend date/time formatting utilities
* existing table/pagination components
* existing confirmation-dialog conventions
* existing responsive navigation conventions
* existing query invalidation conventions after mutations
* whether automatic refresh/polling is already implemented elsewhere
* whether Storybook uses MSW for API-backed page states

⸻

Objective

Implement the administrator Dashboard and Operations UI using the backend Operations/Admin capabilities supplied by PR 11H.

The existing Dashboard placeholder must become a useful production operations overview that allows an authenticated administrator to understand the current state of the application without direct access to the backend, database, cache or infrastructure.

The frontend must provide safe administrator workflows for:

* operational summary
* application and dependency health
* maintenance mode
* cache administration
* background-job visibility
* administrative audit history

The UI must distinguish clearly between passive inspection and production-affecting actions.

Destructive or operationally significant actions must require deliberate administrator interaction and must never occur automatically.

All Operations/Admin API communication must pass through the existing authenticated admin API boundary.

The backend remains the source of truth for authorization, state and validation.

Current architecture

apps/admin is the existing authenticated administrator application.

PR 13A established:

Admin pages
    ↓
Admin API client
    ↓
Backend

Later PRs extended that application with Assistant management, Knowledge Source management and Assistant behaviour/publishing workflows.

This PR must extend the same application rather than introducing a separate operations application.

The backend Operations/Admin API provides an authenticated operations namespace.

The current architecture exposes capabilities including:

Operations
├── Summary
├── Health
├── Cache
├── Maintenance
├── Audit
└── Jobs

Read and production-affecting operations may have different backend authorization requirements.

Frontend visibility can improve usability, but hiding a control is not authorization. Every privileged operation remains protected by the backend.

The Dashboard should primarily consume the aggregate operational summary rather than reconstructing equivalent information through multiple unrelated requests when the backend already supplies the summary.

Detailed pages may then load the corresponding authoritative endpoint.

Required implementation

1. Replace the Dashboard placeholder

Replace the existing admin Dashboard placeholder with a production operations overview.

The Dashboard must load the authoritative Operations Summary endpoint.

Present, where supplied by the backend:

* overall health
* maintenance state
* cache summary
* running jobs
* failed jobs
* administrative activity/audit count

Use compact summary cards or equivalent components that work at desktop and mobile widths.

Each meaningful summary item should link to its corresponding detailed Operations view where one exists.

The dashboard must support:

* loading state
* populated state
* degraded/unhealthy state
* maintenance-enabled state
* zero-activity state
* retryable network/server failure
* unauthenticated/session-expired handling
* permission-denied handling
* malformed successful response handling

Do not show fake trends, percentages or historical comparisons that the backend does not provide.

Do not infer system health from the HTTP status code alone when the backend health payload contains the authoritative state.

2. Add Operations navigation and routing

Extend the existing authenticated admin navigation with an Operations destination.

Use the existing route hierarchy.

Expected route structure:

/admin
/admin/operations
/admin/operations/health
/admin/operations/cache
/admin/operations/jobs
/admin/operations/jobs/:jobId
/admin/operations/audit
/admin/operations/audit/:entryId
/admin/operations/maintenance

If the existing application does not use the /admin prefix, preserve the established hierarchy rather than introducing a new one.

The /admin/operations page may act as the operations overview or redirect to the Dashboard/summary view according to the existing navigation model.

Do not duplicate the same operational summary in multiple incompatible forms.

Navigation must:

* expose only real implemented capabilities
* provide visible active-route state
* remain keyboard accessible
* work at narrow/mobile widths
* preserve existing Assistant and Knowledge Source navigation
* not break deep links or refresh behaviour

3. Extend the Admin API boundary

Add Operations/Admin methods to the existing admin API client.

Expected capabilities include:

* get operations capabilities/root
* get operations summary
* get health details
* list cache regions
* clear all cache regions
* clear a cache region
* invalidate a cache key
* get maintenance state
* update maintenance state
* list audit entries
* get audit entry
* list operational jobs
* get operational job

Use the exact merged backend contract.

All requests must:

* use the configured backend base URL
* include the existing HTTP-only administrator session
* use the shared authenticated request mechanism
* preserve AbortSignal support where applicable
* validate successful response structures
* map backend failures into safe frontend-owned errors
* preserve existing session-expiry behaviour
* avoid logging response bodies or sensitive values

Do not call fetch directly from pages or components.

Do not add automatic mutation retries.

Do not automatically retry cache invalidation or maintenance changes because an ambiguous network failure may mean the server already applied the action.

Read-only requests may follow the application’s existing bounded retry conventions.

4. Operations capabilities and permissions

If PR 11H exposes explicit capabilities or permission information, use it to improve the UI.

The frontend may:

* hide unavailable sections
* disable unavailable actions
* explain that an administrator lacks permission

However:

* backend authorization remains authoritative
* the frontend must still handle 403
* stale capability data must never cause privileged behaviour to be assumed
* a permission failure must not destroy currently displayed read-only state unnecessarily

If read access exists but execute access does not, operations pages should remain useful in read-only mode.

Do not infer roles or permission names that the backend does not expose.

5. Health view

Implement a detailed Health page using the authoritative health endpoint.

Present:

* overall health state
* generation/check timestamp where supplied
* individual dependency/check results
* safe diagnostic messages supplied for administrator display

Health states must have accessible text labels and not rely on colour alone.

Clearly distinguish:

* healthy
* degraded
* unhealthy
* unknown/unavailable

Do not expose raw exceptions, connection strings, credentials or infrastructure secrets.

A successful HTTP response containing a degraded or unhealthy health payload must be rendered as degraded/unhealthy rather than treated as a request error.

Provide manual refresh.

Do not introduce high-frequency polling.

If automatic refresh is already an established admin convention, use a conservative interval and pause or suppress it when the page is not active where the existing query library supports this naturally.

6. Cache administration

Implement a Cache page using the backend cache administration contract.

Display registered cache regions and the statistics actually exposed by the backend.

Possible fields may include:

* region name
* item count
* hit/miss statistics
* availability/state

Render only fields that exist in the final backend response.

Support the backend-provided actions:

* clear all caches
* clear one cache region
* invalidate one cache key

Production-affecting cache actions must require deliberate confirmation.

For clearing all caches, the confirmation must make the scope unmistakable.

For region clearing, identify the affected region in the confirmation.

Individual cache-key invalidation must:

* require a region
* require a key
* use backend validation
* avoid echoing sensitive key content into logs
* not retain submitted cache keys in browser persistence

While a cache mutation is pending:

* prevent duplicate submission
* prevent accidental repeated execution
* expose an accessible pending state

After confirmed success:

* refresh/invalidate relevant cache queries
* show a concise success message
* restore focus sensibly

On failure:

* retain safe existing data where possible
* show the mapped backend error
* avoid claiming the mutation did not happen when the network outcome is ambiguous

Do not implement arbitrary cache browsing or expose cache values.

7. Maintenance mode

Implement a Maintenance page or focused section using the backend maintenance API.

Display the current authoritative state.

Where supported, show:

* enabled/disabled state
* maintenance message
* who changed it
* last-updated time

Render only actual backend fields.

Allow authorized administrators to enable or disable maintenance according to the backend contract.

Enabling maintenance is operationally significant and must require confirmation.

The confirmation must clearly explain that public-facing requests may become unavailable according to backend maintenance semantics.

Disabling maintenance must also be deliberate but does not require exaggerated warning copy.

Prevent duplicate submissions while pending.

After successful mutation:

* replace cached state with the authoritative response or invalidate/reload it
* update Dashboard summary state
* announce the change accessibly

If the request fails after submission with an unknown network outcome, do not confidently state that maintenance mode remains unchanged. Require an authoritative refresh before another mutation where necessary.

Do not duplicate backend maintenance enforcement in the frontend.

8. Operational jobs

Implement an operational Jobs page.

Display the backend-supported job information, expected to include fields such as:

* job identifier
* status
* created time
* started time
* completed time
* duration
* retry count
* execution node
* safe last error

Render only actual response fields.

Support backend-provided filtering, expected at minimum to include job status if present.

Support bounded pagination using the server contract.

Use URLs/query parameters for filters where this matches the application’s existing patterns so views remain navigable and refreshable.

Status presentation must:

* use text as well as visual treatment
* support every backend-defined state
* gracefully reject malformed/unknown states

Add a Job Detail page where the backend exposes job detail.

Do not implement:

* retry
* cancellation
* deletion
* execution
* queue manipulation

unless PR 11H explicitly exposes those actions.

Error details must be displayed exactly within the safety level intended by the backend. Do not render raw backend stack traces or unvalidated arbitrary HTML.

9. Administrative audit log

Implement an Audit page using the administrator audit API.

Display a paginated list containing the backend-supported summary fields, expected to include:

* timestamp
* administrator/user
* action
* resource
* result

Support backend-provided filters, expected to include some combination of:

* user
* action
* resource
* result
* from date/time
* to date/time

Use the exact API query contract.

Filters must:

* remain deterministic
* reset pagination appropriately when changed
* reject obviously invalid date ranges before submission where practical
* still rely on backend validation as authoritative

Do not fetch an unbounded audit history.

Add an Audit Detail route/page using the backend detail endpoint.

Where supplied and safe, show:

* actor
* action
* resource
* result
* timestamp
* duration
* request ID
* correlation ID
* structured metadata

Render structured metadata defensively.

Do not interpret arbitrary metadata as HTML.

Do not expose values the backend intentionally omits.

Audit detail must handle deleted/missing entries safely.

10. Query state and refresh behaviour

Use the existing query/cache library and conventions.

Read-only operational data may be cached briefly where appropriate.

Operational data must not remain misleadingly stale after mutations.

At minimum:

* maintenance updates invalidate maintenance and summary state
* cache mutations invalidate cache and summary state
* administrative actions that generate audit entries should invalidate audit summary/list state where appropriate

Do not invalidate unrelated Assistant or Knowledge Source queries.

Avoid global cache resets.

Provide manual refresh where the administrator reasonably expects current production state.

Do not implement WebSockets, server-sent events or new real-time infrastructure in this PR.

11. Error handling

Use the existing admin safe-error architecture.

Distinguish where the backend permits:

* authentication required
* permission denied
* invalid request
* missing cache region
* missing cache key
* missing audit record
* missing operational job
* unavailable operations dependency
* network failure
* server failure
* malformed successful response

Never show:

* raw backend exception strings
* stack traces
* cookies
* session identifiers
* credentials
* database connection details
* Redis connection details
* arbitrary response bodies

Operations pages should retain previously loaded safe data during transient refetch failures where the existing query architecture supports this.

A failed background refresh should not replace valid displayed data with an empty screen unnecessarily.

12. Destructive-action safety

Production-affecting operations require deliberate interaction.

At minimum, confirmations are required for:

* clear all caches
* clear cache region
* maintenance-mode activation

Use the existing confirmation-dialog pattern.

Confirmations must:

* name the action
* identify its scope
* describe its immediate effect concisely
* provide Cancel
* provide an explicit action button
* place focus appropriately
* return focus sensibly after cancellation
* prevent duplicate confirmation while pending

Do not use browser window.confirm if the admin application already has an accessible dialog abstraction.

Do not introduce typed phrases such as DELETE unless the operation’s risk genuinely justifies it and such a convention already exists in the application.

13. Accessibility and responsive behaviour

All new pages must follow the accessibility requirements already established by the admin application.

Requirements include:

* semantic headings
* keyboard-accessible controls
* associated form labels
* accessible table/list alternatives at narrow widths
* visible focus
* status communicated with text rather than colour alone
* appropriate live announcements for mutation success/failure
* correctly labelled confirmation dialogs
* no core horizontal overflow
* readable timestamps and identifiers
* sensible focus after route changes and mutations

Large operational tables must remain usable on smaller screens.

Prefer responsive layouts over shrinking text or forcing the entire application horizontally.

14. Storybook

Add deterministic stories for the important reusable operations states.

Expected stories include:

* Dashboard healthy
* Dashboard degraded
* Dashboard maintenance enabled
* Dashboard loading
* Dashboard error
* Health healthy
* Health degraded/unhealthy
* Cache populated
* Cache clear confirmation
* Maintenance enabled
* Maintenance disabled
* Jobs populated
* Jobs empty
* Audit populated
* Audit empty
* Operations read-only/permission-limited state where supported

Use fixed fictional values.

Do not connect Storybook to a live backend.

Reuse existing Storybook/MSW conventions.

15. Documentation

Update apps/admin/README.md where necessary to cover:

* Dashboard and Operations routes
* backend PR 11H dependency
* required administrator permissions
* available operational capabilities
* production-affecting actions
* local development
* relevant test commands
* Storybook coverage
* limitations and explicitly unsupported operations

Do not document credentials, cache keys or sensitive infrastructure details.

Acceptance criteria

* PR 13E replaces the existing Dashboard placeholder with a functional operational dashboard.
* Dashboard data comes from the authoritative Operations Summary API.
* Dashboard renders health, maintenance, cache, job and audit information only where supplied by the backend.
* Operations navigation integrates with the existing authenticated admin shell.
* Existing Assistants, Knowledge Sources and Behaviour routes remain functional.
* All Operations/Admin HTTP requests pass through the existing admin API boundary.
* No operations page or component performs direct fetch calls.
* All successful Operations/Admin responses are runtime validated before use.
* Authentication/session-expiry behaviour remains consistent with the existing admin application.
* Backend 403 responses are handled safely and do not rely on client-side authorization.
* Read-only administrators remain able to inspect permitted data when execute permission is unavailable, if supported by PR 11H.
* Health details correctly distinguish healthy, degraded and unhealthy backend states.
* A degraded/unhealthy health payload returned with HTTP 200 is rendered as system state rather than an HTTP failure.
* Cache regions can be inspected using the backend contract.
* Clear-all cache requires explicit confirmation.
* Clear-region requires explicit confirmation identifying the region.
* Cache-key invalidation uses backend validation and does not persist submitted keys.
* Duplicate cache mutation submissions are prevented.
* Maintenance state is read from the backend.
* Authorized administrators can update maintenance state according to the backend contract.
* Enabling maintenance requires explicit confirmation.
* Maintenance mutations update/invalidate Dashboard state.
* Operational jobs support server-backed bounded pagination.
* Supported job filtering uses the backend contract.
* Job detail handles missing jobs safely.
* Audit browsing uses bounded server-side pagination.
* Supported audit filters are implemented without inventing query parameters.
* Audit detail renders only validated and safe backend fields.
* Invalid audit date ranges are handled safely.
* Mutation success refreshes only relevant query state.
* Mutations are never automatically retried.
* Ambiguous network failures do not falsely claim that a production mutation failed to execute.
* Operational status is never conveyed by colour alone.
* New pages remain keyboard usable.
* New pages remain usable at narrow/mobile widths.
* Confirmation dialogs have correct accessible focus behaviour.
* Loading, empty, error, permission-denied and populated states are implemented where relevant.
* Deterministic Storybook stories cover representative Operations states.
* No raw backend errors, stack traces, credentials, cookies or infrastructure secrets are displayed or logged.
* No arbitrary cache values are exposed.
* No unsupported job execution, retry, cancellation or queue controls are introduced.
* No backend production code is changed.
* Existing public Assistant widget behaviour remains unchanged.
* Existing admin Assistant, Knowledge Source and Behaviour workflows remain unchanged.
* Admin lint passes.
* Admin type checking passes.
* Admin tests pass.
* Admin production build succeeds.
* Admin Storybook build succeeds.
* git diff --check passes.
* apps/admin/README.md accurately documents Operations functionality and limitations.

Tests to add or update

Add tests beside the existing admin test locations using the repository’s established Vitest, React Testing Library, userEvent and MSW patterns.

Cover the API boundary for:

* operations root/capabilities
* summary
* health
* cache listing
* clear-all cache
* clear-region cache
* cache-key invalidation
* maintenance read/update
* audit list/detail
* job list/detail
* query parameter encoding
* pagination
* credentialed requests
* cancellation
* response validation
* malformed successful responses
* safe administrative error mapping
* session expiry
* permission denied
* unavailable dependency errors
* mutation requests not being automatically retried

Cover Dashboard behaviour for:

* loading
* healthy summary
* degraded/unhealthy summary
* maintenance-enabled summary
* zero jobs/audit activity
* safe navigation to detailed views
* network/server failure
* permission failure
* session expiry
* malformed response

Cover Health for:

* healthy dependencies
* degraded dependencies
* unhealthy dependencies
* manual refresh
* HTTP 200 with unhealthy payload
* failed refresh retaining previously loaded safe data where supported

Cover Cache for:

* populated regions
* empty regions
* global clear confirmation
* region clear confirmation
* cancellation
* successful invalidation
* missing region
* missing key
* invalid key form
* duplicate submission prevention
* ambiguous mutation network failure
* relevant query invalidation
* keyboard/focus behaviour

Cover Maintenance for:

* enabled state
* disabled state
* enable confirmation
* disable workflow
* backend validation
* pending state
* duplicate submission prevention
* ambiguous mutation failure
* Dashboard/summary invalidation
* permission denied

Cover Jobs for:

* populated list
* empty list
* each supported status
* status filtering
* pagination
* detail navigation
* missing job
* safe last-error rendering
* unknown/malformed status rejection

Cover Audit for:

* populated list
* empty list
* pagination
* filters
* filter reset
* invalid date range
* detail navigation
* detail metadata
* missing entry
* safe rendering of metadata
* request/correlation IDs where present

Cover routing and navigation for:

* Operations navigation entry
* active navigation state
* direct deep links
* not-found behaviour
* existing admin routes remaining intact
* session restoration on an Operations deep link

Add/update Storybook coverage for the representative deterministic states defined above.

Verification commands

Run the exact scripts supported by the repository after inspecting current package scripts.

Expected commands:

npm ci
npm run lint:admin
npm run typecheck --workspace @ai-discovery-assistant/admin
npm run test:admin
npm run build:admin
npm run build-storybook --workspace @ai-discovery-assistant/admin
git diff --check

Also run focused admin tests during implementation, for example:

npm test --workspace @ai-discovery-assistant/admin -- src/api/adminApi.test.ts
npm test --workspace @ai-discovery-assistant/admin -- src/App.test.tsx

If Operations functionality is split into dedicated test files, run those focused files as well.

Do not consider the task complete until the full admin test suite, production build and Storybook build pass.
