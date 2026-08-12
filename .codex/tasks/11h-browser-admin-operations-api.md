PR 11H — Browser Administrator Operations API Integration

Repository state

Expected branch:

feature/11h-browser-admin-operations-api

Base branch:

main

Worktree:

Backend

Dependencies:

* PR 10A — Operations Domain and Administration API Foundation
* PR 10B — Health, Readiness, Diagnostics, Runtime Configuration and Metrics
* PR 10C — Remaining Operations and Administration Capabilities
* PR 11E — Administrator Authentication API
* PR 11F — Administrator Assistant Management API
* PR 11G — Assistant Behaviour, Publishing & Preview API
* Existing administrator HTTP-only cookie session infrastructure
* Existing Operations/Admin API under /admin/operations

This PR is the backend dependency required by frontend PR 13E — Admin Dashboard & Operations UI.

Read first

* AGENTS.md
* docs/architecture/repository-map.md
* docs/architecture/dependency-rules.md
* apps/backend/AGENTS.md
* apps/backend/admin_auth/
* apps/backend/admin_auth/dependencies.py
* apps/backend/admin_auth/routes.py
* apps/backend/admin_auth/api_models.py
* apps/backend/admin_auth/domain.py
* apps/backend/operations/
* apps/backend/operations/api/router.py
* apps/backend/operations/api/administration_router.py
* apps/backend/operations/api/dependencies.py
* apps/backend/operations/api/models.py
* apps/backend/operations/application/authorization.py
* apps/backend/operations/application/administration.py
* Existing Assistant administrator routes
* Existing Knowledge Source administrator routes
* Existing Assistant Behaviour administrator routes
* Existing administrator authentication tests
* Existing Operations API tests
* Existing trusted-origin / mutation tests

Before changing code, inspect the final merged implementations rather than assuming exact dependency names, middleware, router registration, error contracts or authentication semantics.

Primary change area

Backend authentication and authorization integration between:

* administrator HTTP-only cookie sessions
* Operations/Admin API authorization
* trusted-origin enforcement for browser mutations
* existing Operations read/execute permission model

Expected changes should remain concentrated in:

* apps/backend/operations/api/
* small reusable administrator-auth integration code where justified
* Operations API tests
* administrator-auth regression tests
* backend documentation

Canonical implementation examples

Use the existing administrator APIs as the canonical browser authentication pattern.

In particular, reuse established repository behaviour for:

* HTTP-only administrator session authentication
* active administrator validation
* administrator role enforcement
* trusted-origin validation
* CSRF protection
* safe 401 and 403 responses
* session expiry
* disabled administrator behaviour
* structured logging
* request/correlation identifiers
* audit actor identity
* FastAPI dependencies
* API error handling
* dependency injection
* tests

Preserve the existing Operations API-key authentication implementation for existing non-browser operational clients unless repository inspection proves it is unused and intentionally replaceable.

Do not create another session system, bearer-token system, frontend API key, CSRF token mechanism or parallel administrator identity model.

Relevant symbols

Codex must verify exact names before implementation.

Expected relevant symbols include:

* require_authenticated_administrator
* require_administrator_role
* require_trusted_admin_origin
* Administrator
* AdministratorRole
* administrator session cookie dependency
* ApiPrincipal
* OperationsPermission
* AdminAccessLevel
* authorize_operations_access
* get_authenticated_principal
* require_operations_read
* require_operations_execute
* Operations router
* Operations administration router
* Operations administrative error models
* audit actor identifier
* X-API-Key
* administrator HTTP-only session cookie

Do not duplicate equivalent dependencies.

Expected change surface

The required outcome is that /admin/operations/* can be safely consumed by the existing browser administrator application using its HTTP-only administrator session.

Expected changes include:

* Add administrator-session authentication support to the Operations API.
* Preserve existing API-key authentication compatibility.
* Map authenticated administrators into the existing Operations authorization model where appropriate.
* Require administrator authorization for browser Operations reads.
* Require administrator authorization plus trusted-origin protection for browser state-changing Operations requests.
* Preserve existing API-key read/execute permission semantics.
* Use the authenticated administrator identity as the audit actor for browser mutations.
* Preserve safe Operations error responses.
* Add regression tests for both browser-session and API-key callers.
* Document the two supported authentication modes.

Excluded areas

Do not implement or refactor:

* Operations Dashboard frontend
* apps/admin
* Administrator account management
* new administrator roles unless necessary to satisfy an explicit existing permission model
* login/logout/current-user semantics
* session storage
* password handling
* authentication throttling
* cache functionality
* cache storage implementation
* maintenance-state implementation
* audit persistence
* job persistence
* ingestion orchestration
* Assistant behaviour
* Assistant publishing
* Knowledge Source management
* health-check implementation
* operational summary calculations except where a genuine contract defect blocks frontend usage
* new Operations endpoints not required by PR 13E
* bearer tokens
* OAuth
* JWT authentication
* frontend-stored secrets
* API keys embedded in browser configuration
* a second RBAC framework
* arbitrary authorization refactors
* unrelated common middleware changes
* public Assistant API authentication

Do not remove X-API-Key support without explicit evidence that no existing operational client depends on it.

Unknowns Codex must verify

Before implementation, verify:

* whether any existing production or test client depends on X-API-Key Operations authentication
* whether Operations routes should support API key and administrator session simultaneously
* how FastAPI security dependencies currently behave when both credentials are absent
* whether an invalid API key should prevent fallback to a valid administrator cookie
* whether a stale/invalid administrator cookie should prevent fallback to a valid API key
* whether explicit dual credentials should be accepted or rejected
* whether all active administrators currently have equivalent Operations execute authority
* whether the single current AdministratorRole.administrator role makes a separate frontend read/execute role distinction unnecessary
* whether future role expansion is already anticipated elsewhere
* how existing administrator routes apply require_trusted_admin_origin
* which Operations HTTP methods mutate server state
* whether global router dependencies make conditional trusted-origin enforcement practical
* whether Operations administrative errors or admin-auth errors should be authoritative for Operations routes
* whether existing frontend admin code already maps either error family
* whether browser session expiry currently returns the error shape expected by the admin frontend
* whether disabled administrators are rejected by session authentication
* whether audit actor fields should use administrator ID, email or another existing canonical identifier
* whether API-key audit actors must remain unchanged
* whether Cache-Control: no-store should be applied to sensitive Operations responses
* whether current CORS configuration already permits credentialed requests from the admin origin
* whether OpenAPI can accurately represent both authentication modes

If repository state materially conflicts with this specification, do not redesign authentication silently. Report the mismatch and preserve existing security guarantees.

⸻

Objective

Allow the existing authenticated browser administrator application to safely consume the Operations/Admin API without exposing an administrative API key to frontend JavaScript.

The current Operations API authenticates operational callers through X-API-Key.

The existing administrator application authenticates users through an opaque HTTP-only cookie session.

These mechanisms currently form two separate authentication paths:

Existing operational client
        ↓
X-API-Key
        ↓
Operations API

and:

Admin browser
        ↓
HTTP-only administrator cookie
        ↓
Assistant / Knowledge / Behaviour admin APIs

Frontend PR 13E requires:

Admin browser
        ↓
HTTP-only administrator cookie
        ↓
Operations API

This PR must bridge those existing security models safely.

It must not require the browser to know, receive, store or transmit the backend ADMIN_API_KEY.

Existing API-key Operations clients must continue to function.

Current architecture

The Operations API is mounted under:

/admin/operations

and exposes functionality including:

* Operations root/capabilities
* health
* operational summary
* cache inspection
* cache clearing
* cache-key invalidation
* maintenance-mode inspection
* maintenance-mode mutation
* audit browsing
* audit detail
* operational-job browsing
* operational-job detail

The existing Operations authorization path builds an ApiPrincipal from an X-API-Key.

The configured administrative API key receives:

operations:read
operations:execute

permissions.

Operations routes then use the existing read/execute authorization model.

Separately, PR 11E introduced browser administrator authentication using an opaque HTTP-only cookie.

Existing browser-facing administrator endpoints already provide dependencies for:

* authenticating the current administrator
* enforcing administrator role
* rejecting untrusted mutation origins

The administrator domain currently exposes the administrator role through the authenticated session.

The browser administrator application deliberately has no access to the opaque cookie value and must never receive an administrative API key.

The missing architectural connection is therefore:

Administrator session
        ↓
Operations authorization principal

without weakening either security boundary.

Required implementation

1. Support administrator sessions on Operations read endpoints

Allow a valid administrator HTTP-only session to authenticate Operations read requests.

This must apply to the read-only Operations endpoints required by PR 13E, including the final merged equivalents of:

GET /admin/operations
GET /admin/operations/summary
GET /admin/operations/health
GET /admin/operations/cache
GET /admin/operations/maintenance
GET /admin/operations/audit
GET /admin/operations/audit/{entry_id}
GET /admin/operations/jobs
GET /admin/operations/jobs/{job_id}

Use the existing administrator authentication service.

Do not manually parse or validate session cookies inside Operations code.

Do not duplicate session lookup logic.

A valid active administrator must be able to make these requests using only the HTTP-only cookie.

No X-API-Key header should be required for browser-session callers.

2. Preserve API-key Operations authentication

Existing valid administrative API keys must continue to authenticate Operations requests.

Preserve:

* operations:read
* operations:execute
* current principal identifiers
* existing API-key rejection behaviour
* existing ingestion-key isolation
* existing audit attribution for API-key actions

Do not automatically grant Operations access to unrelated API keys.

In particular, an ingestion API key must not gain Operations access.

3. Introduce a unified Operations caller dependency

Refactor the Operations authentication boundary so authorization can receive either:

Administrative API key

or:

Authenticated administrator session

Prefer a small adapter around the existing ApiPrincipal / Operations authorization abstraction rather than adding browser-specific authorization checks throughout individual routes.

Expected conceptual flow:

Request
   ↓
Resolve Operations caller
   ├── valid Operations API key
   │       ↓
   │   ApiPrincipal
   │
   └── valid administrator session
           ↓
       Administrator
           ↓
       Operations ApiPrincipal
   ↓
Existing Operations authorization

The exact implementation may differ if repository inspection reveals a cleaner existing abstraction.

Do not couple Operations application/domain services to HTTP session types.

Authentication adaptation belongs at the API/security boundary.

4. Define deterministic credential precedence

Behaviour must be deterministic when requests contain:

* neither credential
* API key only
* administrator cookie only
* valid API key plus valid cookie
* invalid API key plus valid cookie
* valid API key plus invalid cookie
* invalid API key plus invalid cookie

Codex must inspect existing security conventions and choose the safest compatible behaviour.

The implementation must not accidentally permit authentication bypass through fallback semantics.

At minimum:

* no valid credential → 401
* valid administrator cookie → authenticated administrator caller
* valid Operations API key → authenticated API-key caller
* ingestion API key → no Operations access
* malformed credentials must never grant access

Add explicit tests for all supported combinations.

Document any credential precedence rule.

5. Map administrator identity into Operations authorization

Do not bypass the existing Operations authorization layer simply because the caller has an administrator cookie.

Adapt authenticated administrators into the Operations permission model.

The current administrator role is expected to be:

administrator

Codex must verify this.

If all current administrators are intentionally permitted to perform Operations actions, map the authenticated administrator to:

operations:read
operations:execute

at the API boundary.

If the repository already contains a more granular role/capability mechanism, use it instead.

Do not introduce speculative roles purely for PR 13E.

Keep the mapping explicit and testable so future roles can restrict Operations access without rewriting route logic.

6. Protect browser mutations against cross-site requests

Administrator cookie authentication creates a CSRF consideration because browsers attach cookies automatically.

All Operations mutations performed through an administrator session must reuse the existing trusted-admin-origin protection.

At minimum, inspect and protect the final merged equivalents of:

POST /admin/operations/cache/clear
POST /admin/operations/cache/regions/{region}/clear
POST /admin/operations/cache/key
PUT  /admin/operations/maintenance

Do not weaken the existing origin comparison.

Do not create an alternative origin allowlist.

Use the same configured trusted admin origins used by login/logout and existing browser administrator mutations.

A valid administrator session with an untrusted or missing required mutation origin must be rejected.

7. Preserve machine/API-key mutation compatibility

Trusted-origin browser protection must not accidentally break legitimate non-browser Operations API-key callers unless existing API-key policy already requires an Origin header.

If the request is authenticated exclusively through the administrative API key, preserve the existing API-key mutation contract.

The implementation therefore needs to distinguish the authenticated caller type at the API boundary.

Do not require browser Origin semantics from machine-to-machine callers unnecessarily.

8. Preserve backend authorization as the security boundary

Frontend PR 13E may hide or disable unavailable actions for usability.

This PR must ensure that such frontend behaviour is never relied upon for security.

Every Operations endpoint must continue to enforce its required backend access level.

Read endpoints must require Operations read authorization.

Production-affecting mutations must require Operations execute authorization.

Do not rely on:

* frontend routes
* hidden buttons
* JavaScript role checks
* client-provided permission values

for authorization.

9. Audit browser administrator mutations correctly

Operations mutations already produce administrative audit records.

For administrator-session callers, use a stable authenticated administrator identity as the actor.

Prefer an existing canonical identifier used by other admin audit events.

Codex must verify whether the repository convention should use:

* administrator UUID
* normalized administrator email
* another stable administrator identifier

Do not use:

* session token
* cookie value
* password
* arbitrary client-provided identity

For API-key callers, preserve the existing API-key principal identifier.

Audit entries must continue to avoid sensitive payload data.

In particular, cache keys must not be added to audit metadata unless an existing safe contract explicitly permits them.

10. Preserve safe API errors

Operations endpoints should continue to return deterministic safe error responses.

Browser-session integration must correctly distinguish:

* no authentication
* expired session
* disabled/revoked administrator
* insufficient permission
* untrusted mutation origin
* invalid Operations request
* unavailable dependency
* missing operational resource

Do not expose whether a submitted session token exists internally.

Do not expose raw authentication exceptions.

Do not expose backend API-key configuration.

Prefer preserving the Operations API error family for Operations routes unless the repository’s established admin integration requires otherwise.

Whatever contract is selected must be consistent across Operations routes and documented for PR 13E.

11. Session expiry behaviour

If an administrator session expires or is revoked:

* Operations requests must return the established unauthenticated response.
* No stale administrator identity may be used.
* No mutation may execute.
* The frontend must be able to converge to its existing logged-out state.

Do not refresh or recreate an administrator session from an Operations request.

Session lifecycle remains owned by the existing authentication service.

12. Disabled administrator behaviour

Verify that an administrator who becomes disabled cannot continue accessing Operations through an existing session.

Reuse existing administrator authentication semantics.

Do not add an Operations-specific administrator-status cache.

13. CORS compatibility

Verify that credentialed admin-browser requests to /admin/operations/* use the repository’s existing CORS configuration.

Do not add wildcard credentialed CORS.

Ensure:

* trusted admin frontend origin is explicitly allowed
* credentials remain enabled only according to existing configuration
* API-key machine clients remain unaffected

If existing CORS configuration already satisfies this requirement, add regression coverage rather than unnecessary production changes.

14. OpenAPI security documentation

Update Operations API documentation so it no longer falsely implies that X-API-Key is the only supported authentication mechanism.

Where practical with FastAPI/OpenAPI, document both:

* administrative API key
* administrator session cookie

Avoid large custom OpenAPI machinery solely for cosmetic documentation.

Runtime security correctness takes precedence over perfect generated UI representation.

15. Preserve existing Operations contracts

Do not change the established successful response models for:

* health
* summary
* cache
* maintenance
* audit
* jobs

unless repository validation identifies a concrete PR 13E blocker unrelated to authentication.

In particular, retain current Dashboard summary fields where present, including the backend-defined equivalents of:

* health
* maintenance
* cache
* jobs
* audit
* assistants
* knowledge sources
* ingestion

This PR is primarily an authentication/authorization integration PR.

Do not expand it into a second Operations feature PR.

16. Documentation

Update backend administrator/Operations documentation to explain:

* API-key Operations authentication
* browser administrator-session Operations authentication
* read versus execute authorization
* trusted-origin requirement for browser mutations
* API-key machine mutation compatibility
* audit attribution
* credential precedence where relevant
* frontend clients must never receive the administrative API key

Explicitly state that ADMIN_API_KEY or its equivalent is a server-side credential and must not be configured as a VITE_* or other browser environment variable.

Acceptance criteria

* A valid administrator HTTP-only session can access Operations read endpoints without an X-API-Key.
* Frontend PR 13E does not require the administrative API key.
* The administrative API key remains server-side only.
* Existing valid Operations API-key clients continue to work.
* Existing operations:read API-key semantics remain unchanged.
* Existing operations:execute API-key semantics remain unchanged.
* The ingestion API key cannot access Operations endpoints.
* Operations authentication supports administrator sessions through the existing authentication service.
* Session parsing/validation logic is not duplicated in Operations code.
* Administrator-session callers pass through the Operations authorization model rather than bypassing it.
* Active administrators receive only the Operations permissions intentionally mapped from their backend role.
* No speculative administrator role system is introduced.
* Browser cache-clear mutations require trusted-origin validation.
* Browser cache-region-clear mutations require trusted-origin validation.
* Browser cache-key invalidation requires trusted-origin validation.
* Browser maintenance mutations require trusted-origin validation.
* Untrusted browser mutation origins are rejected before the mutation executes.
* Existing API-key machine mutations are not broken by browser Origin requirements.
* Browser mutations use the authenticated administrator as the audit actor.
* API-key mutations preserve their existing audit identity.
* Cache keys, session values and API keys are not written to audit metadata or logs.
* Missing authentication returns a safe deterministic 401.
* Expired/revoked administrator sessions return the established unauthenticated response.
* Disabled administrators cannot access Operations through stale sessions.
* Permission failures return a safe deterministic 403.
* Credential precedence/fallback behaviour is deterministic and tested.
* Invalid API-key plus cookie combinations cannot accidentally bypass authentication.
* Operations successful response models remain backwards compatible.
* Operations health behaviour remains unchanged.
* Operations summary behaviour remains unchanged.
* Cache administration behaviour remains unchanged.
* Maintenance semantics remain unchanged.
* Audit-query behaviour remains unchanged.
* Operational-job behaviour remains unchanged.
* Existing admin Assistant APIs remain unchanged.
* Existing Knowledge Source admin APIs remain unchanged.
* Existing Behaviour/Preview APIs remain unchanged.
* Public Assistant APIs remain unchanged.
* Credentialed CORS remains restricted to configured trusted origins.
* Operations API documentation describes both supported authentication modes.
* Backend documentation explicitly forbids exposing the administrative API key to browser code.
* No new bearer-token or JWT system is introduced.
* No frontend changes are included.
* Ruff passes.
* Ruff formatting check passes.
* mypy passes.
* Focused Operations API tests pass.
* Administrator-auth regression tests pass.
* Full backend test suite passes.
* git diff --check passes.

Tests to add or update

Add or update focused Operations API tests covering administrator-session access.

Expected test locations include:

* existing Operations API test modules
* existing Operations administration tests
* existing administrator authentication API tests where integration coverage belongs
* trusted-origin/security regression tests

Cover read authentication for:

* valid administrator cookie
* expired administrator cookie
* revoked administrator cookie
* disabled administrator
* no credentials
* valid Operations API key
* invalid API key
* ingestion API key

Cover credential combinations for:

* valid API key only
* valid administrator cookie only
* valid API key + valid administrator cookie
* invalid API key + valid administrator cookie
* valid API key + invalid administrator cookie
* invalid API key + invalid administrator cookie
* no API key + no cookie

Assert the chosen precedence semantics explicitly.

Cover administrator-session read access to:

* Operations root/capabilities
* summary
* health
* cache regions
* maintenance state
* audit list
* audit detail
* jobs list
* job detail

Cover browser mutation authorization for:

* clear all caches
* clear cache region
* invalidate cache key
* enable maintenance
* disable maintenance

For each relevant mutation, cover:

* valid administrator session + trusted origin
* valid administrator session + untrusted origin
* valid administrator session + missing origin according to established policy
* expired session
* no session
* mutation is not executed on authorization/origin failure

Cover API-key mutation regression for:

* valid execute key without browser Origin
* read-only principal denied execute where testable
* unrelated ingestion key denied
* audit actor remains API-key principal

Cover administrator mutation audit behaviour for:

* stable administrator actor identity
* successful action
* failed action
* request/correlation identifiers
* safe metadata
* cache key not recorded
* session/API-key value not recorded

Cover error contracts for:

* unauthenticated
* permission denied
* untrusted origin
* missing operational resource
* malformed request
* unavailable dependency

Cover regressions ensuring:

* Operations successful response bodies have not changed unexpectedly
* existing API-key tests continue to pass
* existing administrator authentication tests continue to pass
* existing Assistant administrator APIs continue to authenticate with cookie sessions
* existing Knowledge Source APIs remain unaffected
* existing Behaviour APIs remain unaffected

Verification commands

Use the repository’s exact supported commands after inspecting current configuration.

Expected backend verification:

cd apps/backend
venv/bin/python -m pytest -q tests/test_operations_api.py
venv/bin/python -m pytest -q tests/test_operations_administration_api.py
venv/bin/python -m pytest -q tests/test_admin_authentication_api.py
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/mypy .
venv/bin/python -m pytest -q

If the actual Operations test filenames differ, run the equivalent focused modules.

From the repository root also run:

git diff --check

Do not consider the task complete if only cookie-session tests pass while existing API-key Operations tests regress.
