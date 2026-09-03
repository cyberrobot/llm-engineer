# PR 2 — Secure the RAG UI Boundary

## Repository state

Expected branch:

`2-secure-rag-ui-boundary`

Base branch:

`main`

Worktree:

Create a fresh worktree/feature branch from the latest `origin/main`.

Dependencies:

- PR 1A — Legacy Public API Security Hardening is merged.
- PR 1B — Freeze the Legacy RAG Contract is merged.
- The temporary RAG UI still consumes:
  - `POST /rag-chat`
  - `GET /audit-logs`
- `apps/rag-ui` remains the active in-repository consumer of those routes.
- The supported anonymous Assistant endpoint remains:
  - `POST /public/assistants/{assistant_slug}/chat`
- Existing administrator authentication/session infrastructure should be reused where practical.
- An identity-aware/private reverse proxy may satisfy the outer RAG UI protection requirement if one is already available, but backend authorization requirements and automated protection tests still apply.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/1a-legacy-public-api-security-hardening.md`
- `.codex/tasks/1b-freeze-legacy-rag-contract.md`
- `apps/backend/docs/legacy-rag-contract.md`
- `README.md`
- `apps/backend/README.md`
- `apps/backend/docs/operations-administration.md`

### Primary change area

Backend security boundary:

- `apps/backend/assistant/api/rag.py`
- `apps/backend/assistant/api/audit.py`
- `apps/backend/assistant/application/rag_chat.py`
- existing administrator authentication/authorization dependencies and middleware
- request/body-size middleware or equivalent HTTP boundary infrastructure
- audit/debug response handling
- backend configuration only where required for bounded limits

RAG UI integration:

- `apps/rag-ui/src/services/getRagChat.ts`
- `apps/rag-ui/src/services/getAuditLogs.ts`
- RAG UI deployment/proxy configuration where repository-managed
- RAG UI authentication/session integration only as required to traverse the protected boundary

Tests:

- `apps/backend/tests/test_legacy_rag_contract.py`
- `apps/backend/tests/test_legacy_api_security.py`
- `apps/backend/tests/test_rag_chat.py`
- `apps/backend/tests/test_audit.py`
- administrator authentication/API tests
- RAG UI tests where request authentication behaviour changes

### Canonical implementation examples

Use the repository's existing administrator security mechanisms rather than introducing a parallel authentication model.

Inspect and follow established patterns from:

- administrator API authentication dependencies
- administrator authorization tests
- `apps/backend/tests/test_operations_administration_api.py`
- `apps/backend/tests/test_legacy_api_security.py`
- `apps/backend/tests/test_legacy_rag_contract.py`
- existing middleware for correlation, maintenance, CORS and rate limiting

### Relevant symbols

Verify exact current names before implementation.

Expected relevant concepts include:

- `assistant.api.rag.RagChatRequest`
- `assistant.api.rag.rag_chat_endpoint`
- `assistant.api.audit.get_logs`
- `assistant.application.rag_chat.rag_chat`
- `assistant.infrastructure.audit.get_audit_logs`
- administrator authentication/session dependencies
- role/claim extraction from the authenticated principal
- `getRagChat`
- `getAuditLogs`

### Expected change surface

Expected:

- protect the RAG UI and its backend API boundary
- authenticate callers before allowing RAG debug functionality
- derive retrieval permissions from authenticated server-side identity
- stop treating JSON `user_role` as an authoritative authorization claim
- authorize access to `/audit-logs`
- establish a safe maximum `audit-logs.limit`
- establish message-size limits
- establish request-body-size limits
- replace raw backend exception text with stable non-sensitive API errors
- apply `Cache-Control: no-store` to audit/debug-sensitive responses
- add negative authorization and cross-role retrieval tests
- update the frozen PR 1B contract tests where security behaviour intentionally changes
- preserve the functional RAG UI experience for authorized users

Infrastructure-managed access control is acceptable for protecting the browser UI itself when an existing identity-aware/private proxy is available. Its effectiveness must be represented by executable repository configuration or automated verification rather than documentation alone.

### Excluded areas

Do not:

- redesign the RAG retrieval algorithm
- redesign ranking, reranking, embeddings or chunk persistence
- change the supported anonymous public Assistant endpoint
- expose `/rag-chat` or `/audit-logs` as supported public APIs
- add arbitrary client-selected roles as an authorization mechanism
- trust `user_role` merely because it matches a known role name
- introduce a second independent administrator identity system when the existing one can protect this boundary
- expose authentication/session tokens in client logs, audit rows or error messages
- leak stack traces, database details, provider errors, prompt content, retrieved document text or credentials through error responses
- make audit history cacheable by shared/browser caches
- introduce unbounded pagination or unbounded audit-log retrieval
- weaken PR 1A's protection or removal of retired legacy endpoints
- modify public Assistant authorization semantics as part of this PR
- redesign the RAG UI beyond what is necessary to access the protected API

### Unknowns Codex must verify

Before implementation, verify:

1. The exact authentication/session mechanism currently used by administrator APIs.
2. Whether the existing administrator session can be reused directly by `apps/rag-ui`.
3. Whether the deployed environment already provides an identity-aware/private proxy suitable for protecting the RAG UI route.
4. Whether that proxy injects any identity claims and, if so, whether the backend currently has a trustworthy mechanism for validating them.
5. The current role model used for chunk access and the source of truth linking authenticated principals to permitted document/access roles.
6. Whether administrators should receive all RAG roles or only explicitly assigned roles. Do not infer this silently; preserve the repository's existing authorization model.
7. Every backend location where `user_role` currently influences retrieval, caching, auditing or evaluation.
8. Whether cache keys currently include the user-selected role and whether they must instead incorporate server-derived authorization context.
9. The current behaviour of `/audit-logs?limit=...`, including default, zero, negative and excessively large values.
10. Existing request-size/body-size middleware and any reverse-proxy size limits already configured.
11. The current largest legitimate RAG message/request size used by the application so the new bound is practical.
12. Every endpoint or response containing audit/debug information requiring `Cache-Control: no-store`.
13. Every raw exception path currently capable of returning internal exception text.
14. Whether the browser client currently sends credentials with API requests and whether same-origin deployment can be used to avoid exposing tokens to frontend JavaScript.
15. Which PR 1B characterization tests must deliberately change because anonymous access, arbitrary role selection, error exposure and unbounded limits are no longer valid behaviour.

---

## Objective

Secure the temporary RAG UI and its backend boundary before the same insecure access model is reproduced elsewhere.

The RAG UI is an internal/debugging surface. It must no longer rely on anonymous access or client-supplied authorization claims.

After this PR:

- only authenticated/authorized users can use the protected RAG UI boundary
- `/audit-logs` is not anonymously readable
- access roles used for retrieval are derived from trusted server-side identity
- a caller cannot cause retrieval using a role they do not possess
- audit retrieval is bounded
- excessively large messages or request bodies are rejected predictably
- backend exception details do not leak through HTTP responses
- audit/debug responses are marked non-cacheable
- authorized users can continue using the RAG UI normally

The supported anonymous customer-facing boundary remains:

`POST /public/assistants/{assistant_slug}/chat`

---

## Current architecture

`apps/rag-ui` currently depends on two temporary legacy endpoints:

- `POST /rag-chat`
- `GET /audit-logs`

PR 1B freezes their current behaviour before this intentional security migration.

### RAG chat

The current RAG UI submits a JSON object containing:

- `message`
- `user_role`

Historically, `user_role` has been accepted from the browser and used as retrieval context.

That is not an authorization boundary.

A caller able to submit arbitrary JSON must not be able to obtain additional document chunks merely by changing:

```json
{
  "user_role": "some-more-privileged-role"
}
```

Authorization context must instead originate from a trusted authenticated principal and be computed server-side.

### Audit history

`GET /audit-logs` exposes RAG debugging information including questions, replies, metrics, retrieval/debug information and chunk-related data.

It is currently part of the temporary RAG UI contract but must not remain anonymously accessible.

### Internal/debug nature

These routes exist to support the RAG UI and are not the supported anonymous Assistant API.

Security should therefore favour a protected internal/admin boundary rather than preserving anonymous compatibility.

---

## Required implementation

### 1. Protect the RAG UI boundary

Require authenticated access to the internal RAG experience.

Preferred order:

1. reuse the existing administrator session/authentication mechanism; or
2. use an already-available identity-aware/private proxy where that is the established deployment architecture.

Do not create a bespoke authentication mechanism solely for the RAG UI unless repository architecture makes reuse impossible.

If proxy protection is used:

- repository-managed configuration must clearly protect the UI
- bypassing the browser UI must not leave sensitive backend APIs anonymously accessible
- protection must be testable
- trusted identity information must be validated before being used for authorization

The API must not assume that hiding the frontend URL protects backend routes.

### 2. Authenticate the RAG API routes

`POST /rag-chat` and `GET /audit-logs` must require the intended authenticated identity or equivalent trusted internal boundary.

Anonymous requests must fail without invoking:

- retrieval
- LLM orchestration
- audit retrieval
- sensitive database work

Use the repository's established authentication failure contract.

Do not reveal whether sensitive audit records or restricted chunks exist to unauthorized callers.

### 3. Derive permitted roles server-side

Remove the browser-provided `user_role` value as an authoritative permission source.

The server must determine the caller's effective retrieval authorization from trusted identity/session information.

The effective access-role set must be derived before retrieval.

If the UI retains a role selector for debugging purposes, it may only select from the intersection of:

- roles requested by the UI, and
- roles the authenticated caller actually possesses.

A client-provided value must never expand authorization.

It is acceptable to remove the request-side role selector entirely if the authenticated identity already determines the complete retrieval context.

### 4. Prevent cross-role retrieval

Every retrieval path used by `/rag-chat` must enforce the server-derived role set.

Tests must demonstrate that a caller possessing role A cannot retrieve role-B-only content by:

- supplying `user_role=B`
- altering request JSON
- omitting the role
- supplying multiple/unknown role values where accepted by parsing
- manipulating cached results
- repeating a request previously made by a more privileged user

Authorization must hold regardless of frontend behaviour.

### 5. Review cache authorization boundaries

Inspect RAG caching for authorization-sensitive keys.

A response generated under one authorization context must not be served to a caller with a different or narrower authorization context.

Where cached RAG results depend on permitted roles, include the normalized server-derived authorization context in the cache key or otherwise guarantee equivalent isolation.

Add a regression test where practical.

### 6. Authorize `/audit-logs`

`GET /audit-logs` must require explicit authorization suitable for internal/admin debugging information.

Authentication alone is insufficient if the existing administrator security model distinguishes permissions.

Use the closest existing administrator permission/capability.

If the repository currently has only an administrator/non-administrator distinction, require administrator authorization rather than inventing a new RBAC model solely for this PR.

Unauthorized callers must not receive partial audit data.

### 7. Bound `audit-logs.limit`

Define an explicit maximum audit-log page/result size.

Requirements:

- preserve a sensible existing default
- valid values within range are honoured
- requests above the maximum are rejected or capped consistently
- zero and negative values have explicit validated behaviour
- malformed values produce normal validation errors
- persistence never receives an unbounded user-controlled limit

Prefer explicit API validation over relying on database behaviour.

Keep the maximum configurable only if the repository already uses configuration for comparable bounds; otherwise use an appropriately named application constant.

### 8. Add message-size limits

Set a maximum accepted RAG message size.

Validate it at the API schema/boundary before expensive retrieval or LLM work begins.

Oversized messages must receive a stable client error.

Do not silently truncate user input.

The limit must be:

- explicit
- tested at boundary and boundary+1
- large enough for legitimate current RAG UI use
- documented in the relevant API/internal documentation

### 9. Add request-body-size limits

Protect the HTTP boundary from excessively large request bodies independently of the `message` field validation.

Use existing server/middleware/proxy facilities where appropriate.

A request exceeding the configured maximum must be rejected before application orchestration.

Ensure the body-size protection applies consistently to the protected RAG API and cannot be bypassed simply through additional unknown JSON fields.

Do not depend solely on browser behaviour.

### 10. Replace raw exception text

Review `/rag-chat`, `/audit-logs` and directly associated security/error paths for exception responses that expose raw internal exception text.

Externally visible errors must use stable, non-sensitive responses.

For unexpected server failures, prefer a generic contract such as:

```json
{
  "detail": "Internal server error"
}
```

or the repository's established equivalent.

Internal logs may retain actionable exception context, subject to existing logging/redaction standards.

Do not include in HTTP responses:

- exception messages
- stack traces
- SQL/database errors
- filesystem paths
- provider payloads
- API credentials
- prompts
- retrieved confidential text

Tests must use a deliberately sensitive-looking fictional exception string and prove it is absent from the response.

### 11. Mark audit/debug responses `no-store`

Responses containing audit or sensitive debugging information must include:

`Cache-Control: no-store`

At minimum this applies to successful `/audit-logs` responses.

Inspect `/rag-chat` debug-oriented responses and any other directly affected route. Apply `no-store` wherever the response contains information that should not persist in browser/intermediary caches.

Do not overwrite stronger compatible security headers already supplied by infrastructure.

### 12. Keep the RAG UI functional

Update `apps/rag-ui` only as required to cross the newly protected boundary.

Prefer same-origin cookie/session behaviour where supported.

Do not place administrator credentials or long-lived secrets in:

- browser source
- build-time public environment variables
- local storage
- query strings

The normal authorized flow must continue to support:

- submitting a RAG question
- rendering the answer
- rendering sources/evaluation data currently used by the UI
- loading audit/debug history for authorized users

Unauthorized UI behaviour should fail clearly without displaying sensitive backend detail.

### 13. Update the frozen legacy contract intentionally

PR 1B captured the pre-hardening contract.

Update those tests and documentation only where this PR deliberately changes security behaviour.

The following PR 1B behaviours are expected to change:

- anonymous `/rag-chat` access
- anonymous `/audit-logs` access
- arbitrary client-selected role authority
- raw exception exposure where present
- effectively unbounded audit limits where present

Preserve unrelated frozen behaviour unless required by this security change, including:

- response fields consumed by the RAG UI
- normal successful answer rendering
- audit ordering
- retrieval/evaluation semantics
- rate limiting unless technically superseded by an established authenticated equivalent
- supported public Assistant behaviour

### 14. Document the protected boundary

Update `apps/backend/docs/legacy-rag-contract.md` or the nearest replacement documentation.

Document:

- the RAG UI is an authenticated internal/debug surface
- the authentication mechanism used
- `/rag-chat` authorization expectations
- `/audit-logs` authorization expectations
- server-derived retrieval roles
- the rule against trusting client-provided authorization claims
- audit limit default and maximum
- message/request-size limits
- non-sensitive error behaviour
- `Cache-Control: no-store`
- the supported anonymous Assistant endpoint for public consumers

If an identity-aware proxy is used, document where its configuration lives and how backend/API bypass is prevented.

---

## Acceptance criteria

- [ ] The RAG UI is accessible only through the intended authenticated/private boundary.
- [ ] `POST /rag-chat` cannot be used anonymously.
- [ ] `GET /audit-logs` cannot be used anonymously.
- [ ] Unauthorized callers cannot obtain audit-history contents.
- [ ] `/audit-logs` requires the intended administrator/debug authorization.
- [ ] Retrieval roles are derived from trusted server-side identity.
- [ ] Client JSON cannot grant the caller an additional retrieval role.
- [ ] A caller possessing only role A cannot obtain role-B-only chunks.
- [ ] Forging the historical `user_role` field does not bypass authorization.
- [ ] Omitting or manipulating the client-side role field cannot broaden access.
- [ ] Cached responses cannot cross authorization-role boundaries.
- [ ] `audit-logs.limit` has an explicit maximum.
- [ ] Excessive, malformed, zero and negative audit limits have deterministic validated behaviour.
- [ ] Persistence never receives an unbounded caller-controlled audit limit.
- [ ] RAG messages have an explicit maximum size.
- [ ] The largest valid message is accepted.
- [ ] A message one unit above the maximum is rejected before RAG orchestration.
- [ ] HTTP request bodies have an explicit maximum size.
- [ ] Oversized request bodies are rejected before application processing.
- [ ] Raw unexpected exception text is not returned to callers.
- [ ] Sensitive-looking fictional exception contents are absent from HTTP responses.
- [ ] Internal failures use stable, non-sensitive error responses.
- [ ] `/audit-logs` responses include `Cache-Control: no-store`.
- [ ] Other directly affected debug-sensitive responses use `no-store` where appropriate.
- [ ] Authentication/authorization failures do not reveal restricted data.
- [ ] Cross-role tests exercise the real HTTP/application authorization boundary rather than only mocking frontend behaviour.
- [ ] RAG UI authenticated users can still submit questions successfully.
- [ ] RAG UI authenticated users with the required authorization can still view audit/debug history.
- [ ] Existing RAG answer/source/evaluation behaviour remains compatible unless explicitly changed by this task.
- [ ] The supported `/public/assistants/{assistant_slug}/chat` anonymous boundary is unchanged.
- [ ] Retired legacy endpoints protected/removed by PR 1A remain absent.
- [ ] PR 1B tests and documentation are updated to reflect only the intended security migration.
- [ ] If an identity-aware/private proxy provides UI protection, automated verification proves that the protection cannot be bypassed through the deployed route/configuration.

---

## Tests to add or update

Backend HTTP/security tests should cover:

- anonymous `/rag-chat` request
- authenticated authorized `/rag-chat` request
- authenticated caller with role A requesting role A
- authenticated caller with role A attempting role B
- forged `user_role`
- omitted `user_role`
- unknown role
- cached answer generated under a more privileged role followed by a less privileged caller
- anonymous `/audit-logs`
- authenticated but unauthorized `/audit-logs`
- authorized `/audit-logs`
- audit default limit
- audit maximum limit
- maximum + 1
- zero
- negative
- malformed limit
- very large limit
- maximum-size RAG message
- oversized RAG message
- maximum HTTP request body
- oversized HTTP request body
- unexpected RAG exception with sensitive-looking fictional text
- unexpected audit exception with sensitive-looking fictional text where applicable
- `Cache-Control: no-store` on audit/debug responses
- public Assistant endpoint remains unaffected

Update:

- `apps/backend/tests/test_legacy_rag_contract.py`
- `apps/backend/tests/test_legacy_api_security.py`
- `apps/backend/tests/test_rag_chat.py`
- `apps/backend/tests/test_audit.py`
- existing administrator authorization test modules as appropriate

Add focused modules if doing so makes the security contract clearer, for example:

- `apps/backend/tests/test_rag_ui_security.py`

RAG UI tests should cover only behaviour changed by the protected integration:

- authenticated requests use the established session/private boundary correctly
- authorization failures are handled without leaking server detail
- normal RAG submission still works
- authorized audit history still loads

If protection is provided by repository-managed proxy/infrastructure configuration, add the closest available configuration/unit/integration verification proving:

- the RAG UI route is protected
- direct API access is not left anonymously exposed
- trusted identity cannot be forged through arbitrary client headers

---

## Verification commands

```bash
# Confirm branch and scope.
git status -sb
git log -1 --oneline origin/main
git diff --check origin/main...HEAD

# Backend focused security/contract verification.
cd apps/backend
../../venv/bin/python -m pytest -q -o "addopts=" --strict-markers \
  tests/test_legacy_rag_contract.py \
  tests/test_legacy_api_security.py \
  tests/test_rag_chat.py \
  tests/test_audit.py \
  tests/test_operations_administration_api.py
cd ../..

# Run any new focused RAG security test module explicitly.
# Example, if created:
cd apps/backend
../../venv/bin/python -m pytest -q -o "addopts=" --strict-markers \
  tests/test_rag_ui_security.py
cd ../..

# Broader backend verification.
npm run test:api
venv/bin/ruff check apps/backend
venv/bin/ruff format --check apps/backend

# RAG UI verification.
npm run build --workspace @ai-discovery-assistant/rag-ui

# Run the repository-established RAG UI test command if one exists.
# Do not invent or claim a passing lint gate where the selected base has
# documented pre-existing lint failures; record any unchanged baseline issue.

# Confirm public Assistant and retired legacy-route security suites remain green
# through the broader API test command above.
```

If implementation adds or changes repository-managed proxy/deployment configuration, also run the existing validation command for that configuration and include it in this section before the PR is considered complete.
