1A — Legacy/Public API Security Boundary Hardening

Repository state

Expected branch:

feature/1a-legacy-public-api-security-hardening

Base branch:

main

Worktree:

Create a fresh worktree/feature branch from the latest origin/main.

Dependencies:

- Existing administrator authentication and authorization under apps/backend/admin_auth/
- Existing administrative API boundary under /api/admin/\*\*
- Existing operations administration API, including /api/admin/operations/audit
- Existing supported anonymous assistant boundary:
  - POST /public/assistants/{assistant_slug}/chat
- Existing public-chat abuse protection, request limits, origin handling and maintenance-mode integration

Read first

- AGENTS.md
- apps/backend/AGENTS.md
- packages/assistant-widget/AGENTS.md if widget cleanup is required
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- apps/backend/docs/public-assistant-chat.md
- apps/backend/docs/administrator-authentication.md
- apps/backend/docs/operations-administration.md

Primary change area

Backend API exposure and security boundaries:

- apps/backend/assistant/api/routes.py
- apps/backend/assistant/api/ingest.py
- apps/backend/assistant/api/audit.py
- apps/backend/assistant/api/rag.py
- apps/backend/assistant/api/chat.py
- apps/backend/operations/infrastructure/maintenance.py

Potential consumer cleanup:

- apps/rag-ui/src/services/
- packages/assistant-widget/src/api/
- packages/assistant-widget/src/publicChatClient.ts
- affected tests and documentation

Canonical implementation examples

Use existing security boundaries rather than introducing another authentication mechanism.

Administrator authentication/authorization:

- apps/backend/admin_auth/dependencies.py
  - require_authenticated_administrator
  - require_administrator_role
  - established administrator session-cookie authentication

Administrative API examples:

- apps/backend/assistant/api/assistant_admin.py
- apps/backend/assistant/api/knowledge_sources.py
- apps/backend/operations/api/administration_router.py

Supported anonymous chat:

- apps/backend/assistant/api/public_chat.py
- apps/backend/assistant/application/public_chat.py
- apps/backend/assistant/application/public_chat_protection.py
- packages/assistant-widget/src/publicChatClient.ts

Relevant symbols

Legacy/public endpoints:

- POST /ingest
- GET /chunks
- GET /audit-logs
- POST /rag-chat
- POST /assistant/chat

Related endpoint requiring review:

- POST /ingest/upload

Existing supported anonymous endpoint:

- POST /public/assistants/{assistant_slug}/chat

Relevant backend symbols:

- assistant.api.ingest.ingest
- assistant.api.ingest.upload_pdf
- assistant.api.ingest.get_chunks
- assistant.api.audit.get_logs
- assistant.api.rag.rag_chat_endpoint
- assistant.api.chat.chat
- assistant.api.routes.router
- admin_auth.dependencies.require_authenticated_administrator
- admin_auth.dependencies.require_administrator_role
- MaintenanceModeMiddleware.\_LEGACY_PUBLIC_ASSISTANT_PATHS

Known consumers/references requiring verification:

- apps/rag-ui/src/services/getAuditLogs.ts
- apps/rag-ui/src/services/getRagChat.ts
- packages/assistant-widget/src/api/assistant.ts
- generated/static API schema references under packages/assistant-widget/src/api/types/
- backend tests
- README/backend documentation
- operations maintenance tests

Expected change surface

Expected:

- assistant API route registration
- deletion or protection of legacy HTTP handlers
- administrator authorization dependencies where a legacy capability genuinely remains necessary
- removal of obsolete browser clients and API-schema references where routes disappear
- maintenance middleware cleanup
- backend API regression/security tests
- focused frontend/widget tests if obsolete clients are removed
- public API documentation cleanup

Possible but only when existing consumers prove it necessary:

- migration of a genuinely supported internal capability to an authenticated /api/admin/\*\* endpoint

No database migration should be required.

Excluded areas

Do not:

- redesign public assistant chat
- replace the existing administrator authentication system
- introduce another API-key, JWT, bearer-token or custom authorization mechanism when the administrator session boundary already applies
- treat CORS, Origin validation, maintenance mode or rate limiting as authentication
- merely add stronger rate limits to the exposed legacy endpoints
- change retrieval, RAG ranking, embeddings or prompt behaviour
- redesign ingestion processing
- redesign the Admin UI
- alter Assistant or Knowledge Source persistence models
- expose /chunks through a newly invented public/debug API
- expose raw audit data through another unauthenticated compatibility endpoint
- add permanent compatibility aliases for endpoints being deliberately retired
- preserve insecure behaviour simply because an old test expects it

Unknowns Codex must verify

Before changing production code, trace the current consumers of every affected endpoint.

Verify:

1. Whether any production-supported consumer still calls:
   - /ingest
   - /chunks
   - /audit-logs
   - /rag-chat
   - /assistant/chat
2. Whether apps/rag-ui remains a supported runtime application or is an internal/development legacy UI.
3. Whether packages/assistant-widget/src/api/assistant.ts or its exports are reachable through the supported package surface. The current public widget transport should use publicChatClient.ts and /public/assistants/{assistant_slug}/chat.
4. Whether /ingest/upload remains a supported integration. It currently has a dedicated X-API-Key check while /ingest does not. Do not accidentally weaken /ingest/upload while restructuring the router.
5. Whether the newer Assistant/Knowledge Source ingestion APIs already replace /ingest sufficiently for the raw endpoint to be deleted.
6. Whether any documentation, generated OpenAPI types, test fixtures, load tests or operational middleware still assume /assistant/chat or /rag-chat are public.
7. Whether any endpoint being retained as administrative functionality already has an equivalent /api/admin/\*\* contract. Prefer that canonical contract over protecting and perpetuating an obsolete alias.

⸻

Objective

Close the remaining legacy/public API security holes so that the backend has one deliberate anonymous assistant-chat boundary:

POST /public/assistants/{assistant_slug}/chat

No legacy endpoint may remain anonymously callable merely because it historically existed or has a rate limit.

The following routes must be removed or placed behind explicit server-side authentication and authorization:

POST /ingest
GET /chunks
GET /audit-logs
POST /rag-chat
POST /assistant/chat

Prefer deletion where the capability has already been replaced.

Where a capability genuinely remains necessary for administrators or internal operations, expose it through the existing authenticated administrative boundary and enforce the established administrator authorization dependency.

Rate limiting is defence-in-depth only. It is not a substitute for authentication or authorization.

⸻

Current architecture

The repository now has three materially different HTTP security boundaries.

Public assistant boundary

POST /public/assistants/{assistant_slug}/chat is intentionally anonymous.

It already owns the protections required for anonymous use, including:

- explicit public-route semantics
- assistant-specific lookup
- origin restrictions
- request-size limits
- public-chat throttling
- concurrency protection
- timeout handling
- safe errors
- SSE streaming
- maintenance-mode handling

This is the supported anonymous assistant endpoint.

Administrative boundary

The backend has an administrator authentication system based on opaque administrator sessions and reusable authorization dependencies.

Administrative Assistant, Knowledge Source and Operations APIs already use this model.

Operational audit browsing also has a canonical administrative API under:

/api/admin/operations/audit

Legacy boundary

Several older Assistant/RAG endpoints remain mounted directly by assistant/api/routes.py.

Current code exposes:

POST /ingest
GET /chunks
GET /audit-logs
POST /rag-chat
POST /assistant/chat

These routes predate the newer public/admin boundaries.

Their security is inconsistent:

- /ingest has a rate limit but no authentication.
- /chunks has neither authentication nor authorization.
- /audit-logs has a rate limit but no authentication.
- /rag-chat has a rate limit but no authentication.
- /assistant/chat has no authentication boundary.
- /ingest/upload has a separate legacy API-key check and therefore needs explicit review when restructuring the ingestion router.

The maintenance middleware further confirms the historical status of /assistant/chat and /rag-chat by maintaining a \_LEGACY_PUBLIC_ASSISTANT_PATHS collection containing both routes.

The published widget also contains legacy /assistant/chat client/schema code alongside the newer public-chat client and therefore requires consumer cleanup verification.

⸻

Required implementation

1. Establish an explicit route disposition

Codex must classify every affected endpoint as one of:

REMOVE
ADMIN_ONLY

There must be no third state equivalent to “public but rate-limited.”

Record the final disposition in the implementation/PR description.

Prefer REMOVE when there is already a canonical replacement or no supported consumer remains.

2. Remove /assistant/chat

POST /assistant/chat must no longer be an anonymous alternative to the supported public Assistant endpoint.

The preferred implementation is removal.

Remove:

- route registration
- obsolete handler code when no longer used
- obsolete tests that assert public availability
- obsolete widget/client references
- generated API type dependencies that exist only for this route
- documentation describing it as supported
- maintenance-mode special casing for the legacy route

Do not redirect or alias /assistant/chat to the public endpoint.

The public endpoint is Assistant-specific and has materially different security and streaming semantics. A compatibility alias would preserve an unintended public surface.

After this PR:

POST /assistant/chat

must resolve as an unavailable route, normally 404/405 according to FastAPI routing semantics.

3. Remove or make /rag-chat administrator-only

POST /rag-chat must not remain anonymously callable.

First verify whether apps/rag-ui remains a supported consumer.

If the RAG UI is obsolete or development-only and no supported consumer requires the route:

- remove /rag-chat
- remove its legacy browser service
- remove obsolete documentation and tests
- remove it from maintenance middleware

If a supported internal capability still requires RAG chat:

- do not keep it as an anonymous endpoint
- move/expose the capability through an appropriate authenticated administrative API
- use the existing administrator session and authorization system
- update the supported internal client accordingly
- remove the legacy /rag-chat route

Do not protect the existing public path solely with a new rate limit.

Do not accept a caller-supplied user_role as authorization.

4. Remove /audit-logs

GET /audit-logs must be removed unless Codex proves it exposes information not available through the canonical administrative audit APIs.

The repository already provides administrative audit browsing under the operations API.

Prefer migrating consumers to:

/api/admin/operations/audit

rather than preserving /audit-logs.

Remove/update:

- legacy route
- apps/rag-ui/src/services/getAuditLogs.ts where applicable
- tests
- README references
- API documentation

No unauthenticated compatibility alias is allowed.

5. Remove /chunks

GET /chunks directly exposes retrieval/knowledge internals and must not remain public.

Preferred implementation:

- remove the HTTP endpoint completely
- preserve the underlying application/service functionality only if other backend code legitimately uses it

Do not create an authenticated replacement unless an actual supported administrator workflow requires raw chunk browsing.

If such a workflow is genuinely required, it must be a separately designed /api/admin/\*\* capability using existing administrator authorization, not a retained /chunks compatibility endpoint.

6. Close /ingest

POST /ingest currently allows raw ingestion without authentication.

It must no longer be public.

Codex must verify whether the modern Knowledge Source/ingestion workflow has superseded this endpoint.

Preferred outcome:

POST /ingest -> removed

If a genuine supported administrator workflow still depends on equivalent raw-text ingestion:

- place that capability behind the existing administrator authentication/authorization boundary
- use an /api/admin/\*\* route
- do not retain anonymous /ingest
- do not invent another API key solely for this endpoint

Preserve application-layer ingestion services when still used elsewhere.

Removing an obsolete transport endpoint must not remove valid ingestion-domain functionality required by current Knowledge Source ingestion.

7. Review /ingest/upload as part of the router security boundary

POST /ingest/upload is not the same defect as /ingest: it currently requires X-API-Key.

Do not accidentally make it anonymous while changing ingest.py.

Codex must determine whether it remains a supported integration.

If retained:

- its authentication requirement must remain explicit
- tests must prove missing and invalid credentials are rejected before ingestion side effects occur
- the PR must document why this legacy credential boundary remains necessary

If it has been superseded and has no supported consumer:

- remove it alongside the obsolete ingestion transport

Do not broaden this PR into redesigning file ingestion.

8. Reuse existing administrator authorization

Any capability retained as administrator-only must use established backend authorization.

Do not create:

- a new static admin token
- a new X-Admin-Key
- another JWT implementation
- another session mechanism
- client-side authorization
- an Origin-only security boundary

Authentication and role authorization must be enforced server-side.

Denied requests must perform no underlying read/write/provider operation.

9. Keep the supported anonymous public route anonymous

This PR must not accidentally protect:

POST /public/assistants/{assistant_slug}/chat

with administrator authentication.

Its explicit anonymous security contract must remain intact.

Preserve its existing:

- public-chat protections
- assistant resolution
- origin policy
- request limits
- rate/concurrency controls
- maintenance handling
- SSE contract
- error mapping

The result is deliberate separation:

/public/** -> explicitly anonymous where designed
/api/admin/** -> authenticated/authorized
legacy endpoints -> removed

10. Clean up route composition

Update apps/backend/assistant/api/routes.py so removed legacy routers are no longer mounted.

Delete obsolete API modules when they have no remaining responsibility.

Do not leave unreachable dead controllers or unused router imports.

11. Clean up maintenance middleware

MaintenanceModeMiddleware currently includes:

\_LEGACY_PUBLIC_ASSISTANT_PATHS = frozenset({"/assistant/chat", "/rag-chat"})

Once those routes are removed from the anonymous surface, remove this legacy special casing.

Maintenance mode should continue handling the supported public Assistant route:

/public/assistants/{assistant_slug}/chat

Do not classify administrator-only routes as public runtime traffic.

12. Clean up client contracts

Search all applications/packages for references to removed endpoints.

In particular verify:

apps/rag-ui/src/services/getAuditLogs.ts
apps/rag-ui/src/services/getRagChat.ts
packages/assistant-widget/src/api/assistant.ts
packages/assistant-widget/src/api/types/schema.ts

Remove obsolete clients when nothing supported consumes them.

Do not export or ship a public package client capable of calling a retired /assistant/chat endpoint.

The published widget must continue using the supported public-chat client.

13. Clean up OpenAPI and documentation

Removed routes must disappear from the generated OpenAPI contract.

Update references in:

- repository README
- backend README
- backend API docs
- widget documentation
- examples/load tests where relevant

Documentation must clearly identify:

POST /public/assistants/{assistant_slug}/chat

as the supported anonymous chat contract.

Do not document removed endpoints as deprecated-but-still-callable unless such a compatibility period has been explicitly required. It has not been required by this task.

14. Do not substitute rate limiting for authorization

Existing rate limits may remain on authenticated/admin endpoints as defence-in-depth when useful.

However, the following does not satisfy this PR:

@limiter.limit(...)
def legacy_endpoint(...):
...

unless explicit authentication and authorization is also enforced.

A regression test must make this requirement observable.

⸻

Acceptance criteria

- POST /assistant/chat is no longer anonymously callable.
- The preferred result is that /assistant/chat is removed entirely and absent from OpenAPI.
- POST /rag-chat is either removed or replaced by an explicitly authenticated administrator capability.
- GET /audit-logs is removed in favour of the existing administrative audit API unless a distinct supported requirement is demonstrated.
- GET /chunks is removed from the unauthenticated API surface.
- POST /ingest is removed from the unauthenticated API surface.
- No affected endpoint is considered secured merely because it has rate limiting.
- Any retained privileged capability uses the repository’s established server-side authentication and authorization system.
- Anonymous requests to administrator-only replacements receive the repository-standard authentication failure.
- Authenticated users without the required administrator permission receive the repository-standard authorization failure.
- Authentication/authorization failure occurs before ingestion, retrieval, provider invocation, audit retrieval or other protected side effects.
- /ingest/upload does not become less secure as a side effect of restructuring.
- If /ingest/upload remains, missing or invalid credentials continue to fail before ingestion work occurs.
- POST /public/assistants/{assistant_slug}/chat remains intentionally anonymous.
- Public chat retains its existing request-size, origin, throttling, concurrency, timeout, streaming and maintenance behaviour.
- The public widget no longer calls /assistant/chat.
- Supported widget chat continues to use /public/assistants/{assistant_slug}/chat.
- Removed legacy routes are absent from generated OpenAPI.
- No supported frontend/client references a removed endpoint.
- Maintenance middleware no longer carries obsolete /assistant/chat or /rag-chat public-route special cases after those routes are retired.
- Existing canonical /api/admin/\*\* functionality is not duplicated by new compatibility endpoints.
- No new authentication library or parallel security mechanism is introduced without a demonstrated requirement.
- No database schema change is introduced.
- Existing Assistant management, Knowledge Source management, public chat and operations administration functionality remains passing.
- Documentation describes the final security boundaries accurately.

Tests to add or update

Add a focused security-regression test module, for example:

apps/backend/tests/test_legacy_api_security.py

Cover the final disposition of every target route.

Removed routes

For every route classified REMOVE, verify it is no longer present in the application’s route/OpenAPI surface.

At minimum cover:

POST /assistant/chat
POST /rag-chat
GET /audit-logs
GET /chunks
POST /ingest

according to the final verified disposition.

Prefer OpenAPI/route-table assertions plus HTTP behaviour so a later accidental remount is caught.

Administrator-only capabilities

For any capability classified ADMIN_ONLY, test:

- no administrator session
- invalid session
- expired session where existing fixtures support it
- authenticated non-administrator
- authenticated administrator
- denied requests cause no protected side effect

Reuse existing administrator-authentication fixtures and patterns.

Public chat regression

Update/run:

apps/backend/tests/test_public_chat.py
apps/backend/tests/test_public_chat_protection.py

Verify that the supported public route remains anonymous and protected by its existing public controls.

Ingestion regression

Update relevant tests under:

apps/backend/tests/test_ingest_upload.py
apps/backend/tests/test_ingestion_api.py
apps/backend/tests/test_ingestion_jobs_api.py

as required by the actual route disposition.

If /ingest/upload remains, explicitly test:

- missing API key
- invalid API key
- valid API key
- rejected requests produce no ingestion side effects

Operations regression

Run/update:

apps/backend/tests/test_operations_administration_api.py

Ensure the canonical authenticated audit endpoint remains functional.

Update maintenance-mode tests so only the supported public Assistant route is treated as anonymous Assistant traffic.

Widget/client regression

If obsolete widget client code is removed, update/run:

packages/assistant-widget/src/publicChatClient.test.ts
packages/assistant-widget/src/AssistantWidget.public.test.tsx
packages/assistant-widget/src/api/assistant.test.ts

Remove the legacy test where the corresponding client is deleted rather than rewriting it to preserve the obsolete endpoint.

Verify the package does not emit /assistant/chat as its chat URL.

RAG UI regression

If apps/rag-ui is affected, update its service/component tests so there are no remaining calls to removed unauthenticated endpoints.

Do not weaken tests merely to accommodate route removal.

Verification commands

Run from the repository root.

# Confirm prohibited legacy route references have been eliminated or are

# intentionally confined to regression tests/documentation explaining removal.

rg -n '"/(assistant/chat|rag-chat|audit-logs|chunks|ingest)"|`/(assistant/chat|rag-chat|audit-logs|chunks|ingest)`' \
 apps packages README.md docs || true

# Focused backend security regression.

cd apps/backend
pytest tests/test_legacy_api_security.py -q

# Public boundary regression.

pytest tests/test_public_chat.py tests/test_public_chat_protection.py -q

# Admin authentication/operations regression.

pytest \
 tests/test_admin_authentication_api.py \
 tests/test_operations_administration_api.py \
 -q

# Ingestion regression where affected.

pytest \
 tests/test_ingest_upload.py \
 tests/test_ingestion_api.py \
 tests/test_ingestion_jobs_api.py \
 -q
cd ../..

# Broader backend API suite.

npm run test:api

# Widget checks when widget/client files changed.

npm test --workspace @redmoor/assistant-widget
npm run lint --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget

# RAG UI checks when its legacy services are changed.

npm run lint --workspace @ai-discovery-assistant/rag-ui
npm run build --workspace @ai-discovery-assistant/rag-ui

# Repository-wide affected tests.

npm test

Before completion, inspect generated OpenAPI or the registered FastAPI route set and explicitly verify that every route classified REMOVE is absent.

The completion report must include the final endpoint matrix, for example:

Endpoint Final boundary
POST /assistant/chat REMOVED
POST /rag-chat REMOVED
GET /audit-logs REMOVED
GET /chunks REMOVED
POST /ingest REMOVED
POST /ingest/upload RETAINED + explicit auth / REMOVED
POST /public/assistants/{slug}/chat PUBLIC
/api/admin/\*\* ADMIN AUTHENTICATED

Do not mark the task complete until every legacy endpoint has an explicit, tested security disposition.
