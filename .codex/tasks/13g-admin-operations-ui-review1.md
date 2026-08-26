PR 13G Review 1 — Admin Operations UI Corrections

Repository state

Expected branch:

feature/13g-admin-operations-ui

Base branch:

Latest main.

Worktree:

Frontend worktree.

Dependencies:

- .codex/tasks/13g-admin-operations-ui.md
- PR #81 — Admin Operations UI
- Existing administrator authentication/session infrastructure
- Existing Operations/Admin backend implementation
- PR 13F — Admin Dashboard Operational Summary

This is a review-fix task for PR #81.

Do not create a new feature branch.

Implement the corrections on the existing:

feature/13g-admin-operations-ui

branch.

Read first

- AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/13g-admin-operations-ui.md
- .agents/skills/gh-review-pr/SKILL.md
- apps/admin/src/api/adminApi.ts
- apps/admin/src/api/adminApi.test.ts
- apps/admin/src/features/operations/Operations.tsx
- apps/admin/src/features/operations/Operations.test.tsx
- apps/admin/src/App.test.tsx
- apps/backend/operations/api/router.py
- apps/backend/operations/api/administration_router.py
- apps/backend/operations/api/models.py
- apps/backend/operations/domain/health.py
- focused backend Operations API tests

Inspect the actual PR #81 branch state before making changes.

The backend implementation remains authoritative for response serialization, nullable/omitted fields, enum values, error semantics, pagination and mutation behaviour.

Primary change area

- apps/admin/src/api/adminApi.ts
- apps/admin/src/api/adminApi.test.ts
- apps/admin/src/features/operations/Operations.test.tsx
- apps/admin/src/App.test.tsx only where additional routing/session regression coverage is needed
- Operations Storybook stories only where needed to reproduce valid backend response states

Canonical implementation examples

Preserve the architecture already introduced by PR #81:

Operations component
↓
AdminApi
↓
shared authenticated request()
↓
/admin/operations/\*

Continue using:

- existing AdminApiError
- existing shared authenticated request function
- existing runtime validation helpers
- AbortSignal
- existing auth/session-expiry flow
- Vitest
- React Testing Library
- existing Storybook patterns

Do not weaken validation generally to fix one contract mismatch.

The correct solution is to make validation accurately reflect the authoritative backend serialization contract.

Relevant symbols

Frontend:

- createAdminApi
- AdminApi
- AdminApiError
- getOperationsHealth
- operationsHealthFrom
- DependencyHealth
- DependencyHealthCode
- OperationsHealthDetail
- OperationsHealthPage
- useLoad
- LoadState
- ConfirmationDialog

Backend:

- get_operations_health
- OperationsHealthResponse
- DependencyHealthResult
- HealthStatus
- HealthErrorCode

Expected change surface

This task is narrowly scoped to review corrections for PR #81.

Expected changes include:

- fixing the valid Operations Health response rejection
- adding regression coverage for omitted optional health fields
- filling the highest-value missing Operations workflow tests identified in review
- running and recording the complete required Admin verification suite

Backend production changes are not expected.

Excluded areas

Do not:

- redesign the Operations UI
- recreate PR 13G
- change Operations endpoint paths
- modify backend production behaviour to accommodate the frontend validator
- loosen all Operations runtime validation
- add new Operations backend endpoints
- add job execution/retry/cancellation
- add arbitrary cache browsing
- change Dashboard summary architecture
- refactor unrelated Admin features
- introduce new HTTP/state/validation frameworks
- add automatic mutation retries
- introduce aggressive polling

Unknowns Codex must verify

Before implementation, verify:

- the exact JSON emitted by GET /admin/operations/health
- interaction between FastAPI response_model_exclude_none=True and nullable nested DependencyHealthResult.code
- whether any other Operations endpoints use response_model_exclude_none=True
- whether other frontend Operations validators incorrectly require fields that the backend legitimately omits
- whether omitted optional response fields should normalize to null or remain optional in the frontend model
- existing tests for healthy dependency checks where code=None
- exact current PR #81 test/lint/typecheck/build status
- whether all verification commands are available from apps/admin/package.json

If another valid-backend-response / frontend-validator mismatch is discovered while auditing response_model_exclude_none behaviour, fix it only when it is part of the existing PR 13G Operations contract and add a focused regression test.

⸻

Objective

Correct PR #81 so the detailed Admin Operations UI interoperates with the authoritative backend contract and has sufficient regression and verification evidence for approval.

The immediate production defect is:

/admin/operations/health

renders:

The backend returned an invalid response. No operational state has been inferred.

for a valid backend Health response.

The frontend runtime validator currently requires every dependency check to contain the exact key:

code

even though the backend defines:

code: HealthErrorCode | None = None

and the health endpoint uses:

response_model_exclude_none=True

Therefore a healthy dependency whose code is None can legitimately serialize without a code property.

The frontend must accept that valid representation while preserving strict validation for malformed responses.

This task must also address the missing regression/verification evidence found during the PR #81 review.

Current architecture

PR #81 implements:

/admin/operations
/admin/operations/health
/admin/operations/cache
/admin/operations/maintenance
/admin/operations/jobs
/admin/operations/jobs/:jobId
/admin/operations/audit
/admin/operations/audit/:entryId

Operations requests correctly flow through the existing Admin API boundary.

The Health client currently performs strict response validation through:

getOperationsHealth()
↓
operationsHealthFrom()

The validator expects each dependency check to contain exactly:

name
status
required
latency_ms
code
checked_at

However, the backend route is configured to exclude None fields from serialization.

A healthy backend dependency can therefore validly emit:

{
"name": "postgres",
"status": "healthy",
"required": true,
"latency_ms": 5,
"checked_at": "2026-08-26T10:00:00Z"
}

rather than:

{
"name": "postgres",
"status": "healthy",
"required": true,
"latency_ms": 5,
"code": null,
"checked_at": "2026-08-26T10:00:00Z"
}

The current frontend rejects the first representation as invalid_response.

That is a frontend contract bug.

⸻

Required implementation

1. Fix Operations Health optional code validation

Update operationsHealthFrom() so a dependency health check accepts both valid backend representations:

{
"code": null
}

and an omitted:

code

property.

Continue rejecting:

- unknown extra fields
- unsupported health states
- unsupported diagnostic codes
- non-string diagnostic codes
- malformed timestamps
- invalid latency
- missing required fields
- invalid dependency names

Do not replace exact response validation with loose property access.

A valid dependency check must still have exactly the required fields plus the optional code field.

Equivalent valid key sets are therefore:

name
status
required
latency_ms
checked_at

or:

name
status
required
latency_ms
code
checked_at

Normalize an omitted or null backend code into the existing frontend representation:

code: null

This keeps consumers simple and avoids introducing undefined as another frontend state.

2. Add a regression test reproducing the real backend response

Extend:

apps/admin/src/api/adminApi.test.ts

Add an explicit successful Health response where a healthy dependency check does not contain code at all.

For example:

{
"generated_at": "2026-08-26T10:00:00Z",
"status": "healthy",
"checks": [
{
"name": "postgres",
"status": "healthy",
"required": true,
"latency_ms": 5,
"checked_at": "2026-08-26T10:00:00Z"
}
]
}

Assert that:

api.getOperationsHealth()

resolves successfully and maps the dependency to:

{
code: null
}

Also retain/add tests proving that:

- explicit code: null remains valid
- a valid non-null backend diagnostic code remains valid
- an unknown code is rejected
- an unexpected additional property is rejected
- another required field being omitted still produces invalid_response

The regression test must model actual backend serialization rather than an idealized mock.

3. Verify other Operations validators against omitted nullable fields

Audit the other PR #81 Operations response validators against the exact backend router/model serialization rules.

Specifically inspect:

- Operations root
- Health
- Cache
- Maintenance
- Jobs
- Audit

Do not assume all nullable Pydantic fields are serialized identically.

If an endpoint uses response exclusion that legitimately omits a nullable field and the frontend currently rejects that response:

- update that validator narrowly
- normalize the omitted value consistently
- add a regression test

Do not make speculative changes where the backend always emits the field.

4. Complete critical cache mutation test coverage

Add focused component tests for the existing cache workflows that were not sufficiently evidenced during review.

At minimum verify:

Clear all caches

- opening the confirmation does not perform the mutation
- confirmation copy clearly identifies all registered regions
- final confirmation executes exactly one mutation
- duplicate submission is prevented
- successful mutation triggers authoritative refresh

Definitive backend mutation failure

For a non-network backend failure:

- existing read-only cache state remains visible where appropriate
- a safe error is presented
- the UI does not claim success
- the administrator can deliberately retry where safe

Permission denied

For cache mutation 403:

- render an explicit permission failure
- do not render a success state
- do not treat it as an ambiguous network outcome

5. Complete maintenance failure/ambiguity test coverage

Add focused tests covering:

- network failure after maintenance submission produces an explicit unknown-outcome state
- another maintenance mutation remains blocked until authoritative refresh
- authoritative refresh clears the ambiguity state
- definitive backend failure does not claim that maintenance changed
- mutation 403 is presented as permission denied
- 401 triggers the existing administrator session-expiry flow

Do not add automatic mutation retries.

6. Complete Operations session-expiry regression coverage

Add component-level evidence that an Operations read request returning:

401 / unauthenticated

uses:

auth.sessionExpired()

and returns to the existing login/session restoration flow.

Cover at least one detailed Operations read route.

The API-level error mapping test alone is insufficient to prove the page/session integration.

7. Add malformed-response UI regression coverage

Add at least one focused detailed-Operations page test where the underlying API reports:

AdminApiError('invalid_response')

and verify that the page renders the safe invalid-response state rather than:

- stale invented data
- an empty healthy state
- zero operational values
- an unhandled exception

The Health page is an appropriate candidate because this task fixes its validation defect.

8. Complete Audit interaction coverage

Add focused UI tests for:

- applying valid audit filters
- URL query parameter update
- backend API receiving the expected filters
- changing filters resetting offset to zero
- audit next/previous pagination updating server offset
- populated Audit Detail rendering

Continue to verify that an inverted date range is rejected locally without issuing a new filtered request.

9. Complete Job Detail positive coverage

Add a focused Job Detail test for a valid job response.

Verify presentation of the existing backend-supported fields, including:

- ID
- type
- status
- created time
- started time
- completed time
- duration
- retry count
- execution node
- last error where present

Keep the existing not-found test.

10. Preserve mutation ambiguity semantics

Do not regress PR #81’s existing ambiguity handling.

For production-affecting Operations actions, a transport/network failure after submission may mean the backend applied the mutation.

The frontend must continue to:

- avoid automatically retrying
- avoid saying the action definitely failed
- block accidental repeated execution where the authoritative state is unknown
- require authoritative refresh before another mutation where necessary

Tests must distinguish:

definitive backend rejection

from:

unknown network outcome

11. Preserve strict API validation

The Health correction must not turn the Admin API into permissive parsing.

Every Operations validator must continue to reject malformed successful responses.

Where a field is optional because of serialization behaviour:

- explicitly define the accepted key combinations
- validate the field when present
- normalize it deliberately

Do not use:

value.code ?? null

without first validating that the absence/presence itself conforms to the backend contract.

12. Run the complete verification suite

PR #81 previously reported:

Not run (not requested)

That is insufficient for approval.

Run all verification commands required by PR 13G.

Do not report the task complete unless every command has been run.

If a command fails:

- fix failures introduced or exposed by this PR
- rerun the failing focused command
- rerun the complete required suite before completion

⸻

Acceptance criteria

- /admin/operations/health successfully renders a valid healthy backend response where dependency code=None is omitted from JSON.
- A dependency check with explicit code: null remains valid.
- A dependency check with a supported non-null diagnostic code remains valid.
- An unsupported diagnostic code still produces invalid_response.
- Unexpected health-check properties still produce invalid_response.
- Missing required health-check fields still produce invalid_response.
- Omitted backend code normalizes to frontend code: null.
- The Health fix does not weaken strict validation for unrelated fields.
- Other Operations validators have been checked against actual backend nullable-field serialization.
- Any additional discovered legitimate omission mismatch is fixed with focused regression coverage.
- Clear-all cache confirmation is tested through actual final mutation execution.
- Cache mutations cannot double-submit.
- Cache definitive failures are distinguished from ambiguous network outcomes.
- Cache 403 produces an explicit permission state.
- Maintenance network ambiguity is tested.
- Maintenance ambiguity blocks another mutation until authoritative refresh.
- Maintenance definitive failure does not claim success.
- Maintenance 403 produces an explicit permission state.
- Operations mutation/read 401 uses the existing session-expiry behaviour.
- At least one detailed Operations page has component-level malformed-response coverage.
- Valid Audit filters are tested end-to-end through URL/query API parameters.
- Changing Audit filters resets pagination.
- Audit pagination interaction is tested.
- Populated Audit Detail is tested.
- Populated Job Detail is tested.
- Existing not-found Job/Audit behaviour continues to pass.
- No Operations mutation is automatically retried.
- Existing Dashboard, Assistant and Knowledge Source behaviour does not regress.
- Backend production code is unchanged.
- All required Admin tests pass.
- Admin lint passes.
- Admin typecheck passes.
- Admin production build passes.
- Admin Storybook build passes.

Tests to add or update

apps/admin/src/api/adminApi.test.ts

Add/update coverage for:

- healthy Health check with omitted code
- healthy Health check with explicit code: null
- degraded/unhealthy Health check with valid code
- unknown diagnostic code
- unexpected health-check field
- missing required health-check field
- any other verified nullable-field serialization mismatch
- existing Operations failure mapping remains intact

apps/admin/src/features/operations/Operations.test.tsx

Add/update coverage for:

- valid Health page after omitted code
- malformed-response UI state
- clear-all cache confirmation and success
- cache duplicate-submission protection
- cache definitive backend failure
- cache 403
- maintenance ambiguous network outcome
- maintenance authoritative refresh after ambiguity
- maintenance definitive backend failure
- maintenance 403
- component-level 401 session expiry
- valid audit filters
- audit filter offset reset
- audit pagination
- populated Audit Detail
- populated Job Detail

Preserve existing tests for:

- capability-driven Operations landing
- all health states
- nullable cache statistics
- clear-region confirmation
- key invalidation confirmation
- cache network ambiguity
- maintenance confirmation
- jobs server filtering/pagination
- missing Job
- permission failure
- inverted audit dates
- defensive audit metadata rendering
- missing Audit entry

apps/admin/src/App.test.tsx

Update only where needed for:

- detailed Operations session-expiry regression
- existing protected Operations deep links
- existing route regression coverage

Do not duplicate lower-level component tests unnecessarily.

Verification commands

Run focused tests first:

cd apps/admin
npm test -- src/api/adminApi.test.ts
npm test -- src/features/operations/Operations.test.tsx
npm test -- src/App.test.tsx

Then run the complete required verification suite:

cd apps/admin
npm test
npm run lint
npm run typecheck
npm run build
npm run build-storybook

All commands must pass before PR #81 is considered ready for another specification review.
