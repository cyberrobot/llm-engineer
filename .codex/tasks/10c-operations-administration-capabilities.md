PR 10C — Remaining Operations and Administration Capabilities

Repository state

Expected branch:

feature/10c-operations-admin-capabilities

Base branch:

Latest main containing the completed PR 10A/10B operations foundation and the completed 11G assistant behaviour/publishing work.

Worktree:

Backend worktree.

Dependencies:

- PR 10A — Operations Domain and Administration API Foundation
- PR 10B — Health, Readiness, Diagnostics, Runtime Configuration and Metrics
- PR 11E — Administrator Authentication API
- PR 11G — Assistant Behaviour, Publishing and Preview
- Existing ingestion/job infrastructure where operational job visibility requires it

Assume 11G is fully implemented before this task begins.

Read first

- AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- Existing operations/admin implementation introduced by PR 10A and PR 10B
- Existing administrator authentication/authorization implementation
- Existing audit infrastructure
- Existing cache abstraction and cache implementations
- Existing ingestion/background-job models and repositories
- Existing assistant publishing implementation from 11G

Before making changes, inspect the current repository rather than assuming paths, class names, endpoint prefixes, persistence models, or abstractions.

Primary change area

Backend operations/admin domain and its HTTP API.

Expected responsibilities include:

- cache administration
- audit-log browsing
- maintenance-mode administration
- runtime feature flags, if the repository architecture supports mutable flags
- operational background-job visibility
- aggregate operations summary
- safe administrative actions and audit integration

Keep the implementation inside the existing operations/admin architectural boundary introduced by PR 10A.

Canonical implementation examples

Use existing repository implementations as canonical patterns rather than introducing parallel conventions.

In particular, follow existing patterns for:

- admin authorization
- router/controller registration
- dependency injection
- service interfaces
- Pydantic/request-response models
- pagination contracts
- error responses
- audit-event recording
- database/repository access
- structured logging
- correlation/request identifiers
- test structure
- configuration handling

Prefer established libraries and existing repository abstractions where suitable. Do not introduce custom framework-level functionality where the project already has an appropriate implementation or dependency.

Relevant symbols

Codex must identify the actual symbols before implementation.

Expected relevant concepts include:

- operations module/router
- admin authorization dependency
- admin response/error models
- audit repository/service
- cache abstraction/provider
- ingestion/background-job repository
- health/readiness services
- runtime configuration service
- request/correlation ID infrastructure
- administrator identity/session model
- assistant public API routing

Do not create duplicate abstractions if equivalent symbols already exist.

Expected change surface

Expected changes are primarily within:

- operations/admin domain
- operations/admin API schemas
- operations/admin routes/controllers
- operations service interfaces and implementations
- dependency injection/module registration
- audit query infrastructure
- maintenance-state infrastructure
- cache administration adapters
- operational job-query adapters
- relevant persistence/migrations only where genuinely required
- backend tests

Small changes to common middleware or the public assistant request path are permitted only where necessary to enforce maintenance mode centrally.

Excluded areas

Do not implement or refactor:

- assistant behaviour editing
- assistant publishing
- assistant preview
- assistant frontend/admin UI
- knowledge extraction
- chunking
- embedding generation
- vector persistence
- ingestion orchestration
- new background-job execution
- queue infrastructure
- authentication/session implementation
- health/readiness functionality already completed by PR 10B
- metrics functionality already completed by PR 10B
- unrelated repository cleanup

Do not alter existing assistant, ingestion, retrieval, publishing, or authentication contracts unless strictly necessary to satisfy an explicit requirement below.

Avoid regressions in concurrently implemented or already completed work.

Unknowns Codex must verify

Before implementation, verify:

- the exact admin operations API prefix
- which PR 10B capabilities already exist
- whether cache administration abstractions already expose statistics/invalidation
- whether audit records already contain the metadata required for browsing
- whether an audit query API already exists
- whether maintenance-mode infrastructure already exists
- whether the application supports mutable runtime configuration
- whether a feature-flag abstraction already exists
- whether adding runtime feature flags is architecturally appropriate
- how background/ingestion jobs are currently represented and persisted
- whether there is more than one job type worth exposing operationally
- whether correlation IDs and request IDs already exist
- whether administrative actions are automatically audited
- how pagination is implemented elsewhere
- whether audit tables have suitable indexes for the required filtering
- how readiness semantics should interact with maintenance mode
- which public endpoints should be blocked during maintenance
- whether 11G introduces published-version entities or processes relevant to operational visibility

If repository state conflicts materially with this specification, do not silently recreate missing earlier work. Report the mismatch and implement only what can safely be added on top of the actual prerequisite architecture.

⸻

Objective

Complete the remaining production operations and administration backend capabilities on top of the PR 10A/10B foundation.

The completed operations/admin domain must provide authenticated administrators with production-safe APIs for:

- cache inspection and invalidation
- audit-log browsing
- maintenance-mode control
- operational feature-flag management where supported by the architecture
- background-job visibility
- aggregate operational status
- safe, auditable administrative mutations

The result should allow normal production support and administration without requiring direct database, cache, or process access.

This PR must extend the existing operations architecture rather than create a second administration subsystem.

Current architecture

PR 10A establishes the operations/admin bounded area, including the administrative API namespace, authorization enforcement, common response/error contracts, action metadata, registration and dependency wiring.

PR 10B provides the passive production-observability functionality such as:

- health
- readiness
- diagnostics
- runtime configuration visibility
- operational metrics

Administrator authentication is provided separately by the existing admin-auth work.

11G is assumed complete and provides the current assistant behaviour/publishing implementation. PR 10C must not duplicate or redesign that functionality.

Existing cache, audit, ingestion/job, request-context and application-service infrastructure should be reused wherever possible.

PR 10C completes the active administration side of the operations domain:

Operations / Administration
├── Health existing
├── Readiness existing
├── Diagnostics existing
├── Runtime Configuration existing
├── Metrics existing
├── Cache Administration PR 10C
├── Audit Browsing PR 10C
├── Maintenance Mode PR 10C
├── Feature Flags PR 10C, where supported
├── Job Visibility PR 10C
└── Operations Summary PR 10C

Required implementation

Cache administration

Provide administrator-only cache inspection and invalidation through the existing operations API namespace.

Expose the equivalent of:

GET /api/admin/operations/cache
POST /api/admin/operations/cache/clear
POST /api/admin/operations/cache/regions/{region}/clear
POST /api/admin/operations/cache/key

Use the repository’s actual established route conventions if they differ.

Cache inspection should expose information the underlying cache implementation can determine safely, such as:

- cache/region name
- entry count
- hit count
- miss count
- hit ratio
- estimated memory usage

Do not fabricate unavailable statistics.

Where a statistic cannot be obtained efficiently or reliably, represent it using the repository’s established optional/null convention.

Do not expose:

- passwords
- connection strings
- raw Redis credentials
- internal infrastructure addresses unnecessarily
- arbitrary cache contents
- implementation-specific objects

Cache invalidation must operate through an abstraction rather than coupling HTTP routes directly to Redis or another concrete cache implementation.

Support:

- clearing all administratively clearable cache data
- clearing a named cache region where regions exist
- invalidating a specific supported key

Validate region/key input.

A nonexistent or unsupported region/key must use the project’s standard admin error contract.

Do not add expensive keyspace scans to normal administrative requests if the underlying cache implementation cannot support them safely.

Audit-log browsing

Provide administrator-only, read-only access to operational audit records.

Expose list and detail operations using the repository’s API conventions.

Equivalent endpoints:

GET /api/admin/operations/audit
GET /api/admin/operations/audit/{audit_id}

The list endpoint must:

- order newest first by default
- use the established pagination contract
- return deterministic ordering
- avoid unbounded queries

Support filters where the persisted audit model supports them, including:

- actor/user
- action
- resource/target
- outcome/result
- date/time range

Do not create fake queryability for fields that are not actually persisted.

If additional persistence fields are genuinely required to meet these requirements, add them through the established migration process while preserving existing records.

Audit detail should expose safe operational metadata where available, such as:

- audit ID
- timestamp
- actor
- action
- target/resource
- result/outcome
- request ID
- correlation ID
- execution duration
- safe structured metadata

Sensitive values must not be returned.

Redact or exclude:

- credentials
- tokens
- session secrets
- passwords
- authorization headers
- private configuration
- unrestricted request/response payloads containing sensitive data

Audit browsing itself must remain read-only.

Maintenance mode

Introduce centrally managed maintenance-mode state.

Provide administrator APIs equivalent to:

GET /api/admin/operations/maintenance
PUT /api/admin/operations/maintenance

The update request should support at minimum:

{
"enabled": true,
"message": "Scheduled maintenance"
}

Use existing repository schemas/conventions where appropriate.

Maintenance state must be evaluated centrally rather than by scattering checks throughout every endpoint implementation.

When maintenance mode is enabled:

- normal public assistant functionality must reject new public requests with the project’s defined maintenance response
- administrator APIs must remain accessible
- health must remain accessible
- operations APIs must remain accessible
- authentication required for administrators must remain functional
- existing administrator sessions must remain valid

Do not block the very endpoints required to diagnose or disable maintenance mode.

Determine from the existing readiness semantics whether readiness should:

- become non-ready during maintenance, or
- remain technically ready while exposing maintenance state separately

Use the behaviour most consistent with the existing architecture and tests, and document the decision in code/tests.

Do not change health semantics merely to make maintenance easier to implement.

If a maintenance message is exposed publicly, ensure it is plain configured text and cannot expose internal operational information.

Maintenance persistence

Maintenance mode must have well-defined behaviour across process restarts.

Inspect the existing architecture and choose the established persistence/configuration mechanism.

Do not introduce process-local state if the application is designed to run multiple instances and doing so would produce inconsistent maintenance state between nodes.

If persistent/shared state is required, use an existing suitable persistence or cache abstraction rather than building a new coordination mechanism unnecessarily.

Feature flags

First verify whether the repository already has a feature-flag or mutable-runtime-configuration abstraction.

If one exists, extend it with administrator visibility/control.

Equivalent API:

GET /api/admin/operations/feature-flags
PUT /api/admin/operations/feature-flags/{name}

A feature flag representation should contain at least:

{
"name": "some_feature",
"enabled": true
}

Feature flag resolution must be centralised.

Do not introduce arbitrary string-based feature checks throughout business-domain code.

Flags should support defined defaults.

Unknown flags must not silently create new runtime functionality unless that behaviour is explicitly part of the existing architecture.

If the repository has no runtime feature-flag concept and introducing one would create an unrelated platform subsystem, do not invent a large custom feature-flag framework solely for PR 10C.

In that case:

1. implement the smallest architecture-consistent capability required by existing known flags, or
2. report the repository-state mismatch if no concrete feature flags exist to administer.

Prefer an established library/provider if the repository already depends on one.

Background-job visibility

Expose read-only operational visibility into existing persisted background/ingestion jobs.

Do not implement:

- a new job runner
- queues
- workers
- retry execution
- cancellation
- orchestration
- ingestion logic

Equivalent endpoints:

GET /api/admin/operations/jobs
GET /api/admin/operations/jobs/{job_id}

Use existing job repositories and domain models.

Expose fields that actually exist and are operationally useful, such as:

- ID
- job type
- status
- created time
- started time
- completed time
- duration
- retry/attempt count
- safe last-error information

Only expose execution-node information if the current job infrastructure records it.

Do not invent missing values.

The job list must:

- be paginated
- use deterministic ordering
- avoid loading complete job history into memory
- allow status/type filtering where supported efficiently

Error information returned to administrators must still avoid exposing secrets or raw internal payloads unnecessarily.

Operations summary

Provide an administrator-only aggregate summary endpoint.

Equivalent endpoint:

GET /api/admin/operations/summary

The response should aggregate already available operational services rather than reimplement their logic.

It should expose a concise overview useful to the operations/admin frontend, including applicable values such as:

{
"health": "healthy",
"maintenance": false,
"cache": {
"regions": 4
},
"jobs": {
"running": 2,
"failed": 0
},
"audit": {
"today": 153
}
}

The exact contract must follow existing project schema conventions.

The summary service must delegate to appropriate operations/query services.

Do not duplicate:

- health calculations
- metrics calculations
- cache statistics logic
- audit query logic
- job state logic

Avoid N+1 database/cache operations.

Where aggregate counts can be obtained directly from repositories, use aggregate queries rather than materialising complete record sets.

Safe administrative actions

All mutating operations introduced by PR 10C must:

- require administrator authorization
- validate input
- use standard response/error contracts
- emit structured logs where appropriate
- create an audit record through the established audit mechanism
- preserve request/correlation identifiers
- avoid leaking implementation details
- fail safely

Applicable operations include:

- maintenance-state changes
- cache invalidation
- feature-flag changes

Administrative mutations must not bypass existing service/domain boundaries merely because the caller is an administrator.

Audit integration

Administrative mutations introduced by this PR must produce audit information sufficient to determine:

- actor
- action
- target
- timestamp
- result
- request ID where available
- correlation ID where available
- duration where supported by the existing audit architecture

Record failures as well as successful administrative actions where consistent with the existing audit mechanism.

Do not record secrets or sensitive payloads.

Avoid creating duplicate audit records if middleware or an existing admin-action mechanism already audits the request.

Idempotency

Administrative state-setting operations must be idempotent where their semantics permit it.

At minimum:

- enabling maintenance when already enabled must succeed without corrupting state
- disabling maintenance when already disabled must succeed
- setting a feature flag to its existing value must succeed
- clearing a cache or cache region repeatedly must remain safe

Repeated requests must result in the same final operational state.

Do not attempt artificial exactly-once semantics for cache clearing.

Audit records may still record separate administrator requests, provided they accurately represent what happened and do not trigger duplicate domain side effects.

Authorization

Every PR 10C administration endpoint must use the existing reusable administrator authorization mechanism.

Do not implement a second role/authentication check.

Verify:

- unauthenticated caller → rejected
- authenticated non-admin caller → rejected where that distinction exists
- administrator → permitted

Public maintenance responses must not expose any administrator-only information.

Dependency injection and module registration

Register all new services through the existing backend DI/module mechanism.

Expected concepts may include:

- cache administration service
- audit query service
- maintenance service
- feature flag service
- job operations/query service
- operations summary service

Use interfaces/protocols where that is already the architectural convention.

Do not add abstraction layers purely for ceremony if the existing operations architecture uses concrete injected services.

Database and indexing

Add persistence/migrations only where required by actual repository gaps.

If audit browsing requires database filtering, verify that commonly used filters/orderings can execute efficiently.

Add appropriate indexes where justified, particularly around:

- audit timestamp ordering
- actor/action filtering where used
- job status
- job creation timestamps

Do not add speculative indexes unrelated to actual queries introduced by this PR.

Migrations must follow project conventions and remain compatible with existing data.

Error handling

Use the common administration error contract introduced by the operations foundation.

Handle cases including, where applicable:

- unknown cache region
- invalid cache key request
- unknown feature flag
- unknown audit record
- unknown job
- malformed maintenance request
- unsupported administrative operation
- infrastructure/service failure

Do not return stack traces or raw infrastructure exceptions.

Logging

Use existing structured logging.

Log significant administrative state changes such as:

- maintenance enabled/disabled
- cache invalidation
- feature flag changes
- failed administrative operations

Avoid redundant logging when equivalent structured audit data already provides the necessary event history.

Never log:

- credentials
- session tokens
- authorization headers
- connection strings
- sensitive cached payloads

Backwards compatibility

Existing public and administrative contracts must continue to work.

Do not regress:

- assistant APIs
- assistant publishing APIs
- assistant preview
- ingestion APIs
- retrieval APIs
- authentication/session APIs
- health/readiness APIs
- metrics APIs
- runtime configuration APIs

11G behaviour/publishing functionality must remain unchanged unless a minimal integration change is required for maintenance-mode enforcement.

Acceptance criteria

- Existing PR 10A/10B operations architecture is reused rather than replaced.
- All new administrative endpoints use the existing admin authorization mechanism.
- Administrators can inspect available cache metadata without exposing cached application data.
- Administrators can safely invalidate supported cache keys/regions.
- Unsupported cache operations fail using the standard administration error contract.
- Cache administration does not depend directly on a concrete Redis/cache implementation from the HTTP layer.
- Audit records can be listed using bounded pagination.
- Audit records are returned newest first with deterministic ordering.
- Supported audit filters operate at the persistence/query layer rather than filtering complete result sets in memory.
- Individual audit records can be retrieved by ID.
- Audit APIs do not expose secrets or sensitive payloads.
- Maintenance mode can be inspected, enabled and disabled by an administrator.
- Public assistant requests are rejected appropriately while maintenance mode is enabled.
- Administrator and operations endpoints remain available while maintenance mode is enabled.
- Health remains available during maintenance.
- Readiness/maintenance interaction has explicit, tested semantics.
- Maintenance state behaves correctly for the application’s deployment model and does not accidentally become node-local where shared state is required.
- Repeating the same maintenance-state request is safe.
- Existing feature-flag infrastructure is reused if present.
- Feature flags are centrally resolved rather than checked through scattered arbitrary strings.
- Unknown feature flags fail safely instead of silently creating unrecognised behaviour.
- No unnecessary custom feature-flag platform is created if the repository has no concrete requirement for one.
- Existing persisted jobs can be listed through an admin operations endpoint.
- Job listing is paginated and deterministically ordered.
- Existing jobs can be retrieved by ID.
- Job visibility is read-only and does not introduce execution, retry, cancellation or queue functionality.
- Missing optional job/cache metrics are represented honestly rather than fabricated.
- Operations summary returns a concise aggregate view of current operational state.
- Operations summary delegates to existing services/query abstractions instead of duplicating their logic.
- Operations summary avoids N+1 queries and unnecessary full-table/full-cache scans.
- Administrative mutations produce appropriate audit records.
- Administrative audit events preserve existing request/correlation identifiers where available.
- Sensitive values are excluded from logs and audit metadata.
- Cache clear operations are safely repeatable.
- Feature-flag updates to the current value are idempotent.
- Existing health, readiness, metrics and runtime-configuration functionality continues to pass its tests.
- Existing 11G assistant behaviour/publishing/preview functionality is not regressed.
- Existing assistant, retrieval, ingestion and authentication APIs remain backward compatible.
- No unrelated business-domain functionality is introduced into the operations module.
- All new unit and integration tests pass.
- Existing backend test suite passes.
- Backend linting/type-checking/static-analysis checks pass.

Tests to add or update

Add tests in the existing backend test locations matching repository conventions.

Cache administration

Test:

- administrator can inspect cache metadata
- anonymous request is rejected
- non-admin request is rejected where applicable
- administrator can clear supported cache
- administrator can clear supported region
- administrator can invalidate supported key
- invalid/unknown region is handled correctly
- repeated clear is safe
- unavailable statistics are represented correctly
- no cache payloads/secrets are exposed

Audit browsing

Test:

- administrator can list audit records
- newest-first deterministic ordering
- pagination
- filtering by supported actor/action/resource/outcome values
- date-range filtering
- audit detail lookup
- unknown audit ID
- sensitive metadata redaction
- anonymous/non-admin rejection

Prefer repository/database-backed query tests for filter behaviour rather than mocking the filtering logic entirely.

Maintenance mode

Test:

- initial/current state retrieval
- enable maintenance
- disable maintenance
- repeated enable
- repeated disable
- optional maintenance message
- public assistant request while disabled
- public assistant request while enabled
- admin API access while enabled
- health while enabled
- readiness behaviour while enabled
- persistence/shared-state behaviour appropriate to deployment architecture
- mutation audit event

Feature flags

Where feature-flag administration is applicable, test:

- list known flags
- enable known flag
- disable known flag
- repeated update to same state
- unknown flag
- default resolution
- mutation audit event
- authorization

Job visibility

Test:

- list existing jobs
- pagination
- deterministic ordering
- supported status/type filters
- retrieve job by ID
- unknown job
- safe error information
- authorization
- no mutation capability introduced

Reuse existing ingestion/background-job fixtures where possible.

Operations summary

Test aggregation of:

- health
- maintenance
- cache overview
- job counts
- audit summary

Verify that:

- existing services are delegated to
- failed/partial dependencies use the intended operations error/degraded-state semantics
- aggregate queries do not require loading complete job/audit tables

Administrative auditing

Verify that mutating operations record:

- actor
- action
- target
- result
- request/correlation identifiers where available

Verify sensitive request values are not persisted.

Regression tests

Run and preserve existing tests covering:

- PR 10A operations foundation
- PR 10B health/readiness/metrics/runtime configuration
- admin authentication
- assistant public APIs
- assistant publishing and preview from 11G
- ingestion jobs
- retrieval

Verification commands

Before running commands, inspect pyproject.toml, package scripts, Makefile, CI workflows and AGENTS.md and use the repository’s canonical commands.

At minimum run the backend equivalents of:

# Backend formatting/linting

ruff check apps/backend

# Backend type checking, if configured

mypy apps/backend

# Operations/admin tests

pytest apps/backend/tests -k "operations or admin or maintenance or cache or audit"

# Job/ingestion regression tests

pytest apps/backend/tests -k "ingestion or job"

# Assistant/publishing regression tests

pytest apps/backend/tests -k "assistant or publish or preview"

# Complete backend test suite

pytest apps/backend/tests

Do not blindly introduce these commands into CI if the repository uses different canonical commands.

Codex must finish by reporting:

1. files changed
2. operations capabilities implemented
3. any specification requirements that were already satisfied
4. any requirements intentionally not implemented because the repository architecture did not support them
5. migrations added, if any
6. tests added or updated
7. exact verification commands run
8. test/lint/type-check results
9. any remaining repository-state mismatch or follow-up work
