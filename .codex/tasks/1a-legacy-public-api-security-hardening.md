PR 1A — Legacy Public API Security Hardening

Repository state

Expected branch:

1a-legacy-public-api-security-hardening

Base branch:

main

Worktree:

Create a fresh worktree/feature branch from the latest origin/main.

Task specification:

.codex/tasks/1a-legacy-public-api-security-hardening.md

Dependencies:

- Existing administrator authentication and authorization under apps/backend/admin_auth/
- Existing administrative API boundary under /api/admin/\*\*
- Existing Operations administration API, including /api/admin/operations/audit
- Existing supported anonymous Assistant boundary:
  - POST /public/assistants/{assistant_slug}/chat
- Existing public-chat abuse protection, request limits, origin handling and maintenance-mode integration
- Existing apps/rag-ui functionality must remain working

Read first

- AGENTS.md
- apps/backend/AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- apps/backend/docs/public-assistant-chat.md
- apps/backend/docs/administrator-authentication.md
- apps/backend/docs/operations-administration.md

If changing packages/assistant-widget:

- packages/assistant-widget/AGENTS.md

Primary change area

Backend API exposure and security boundaries:

- apps/backend/assistant/api/routes.py
- apps/backend/assistant/api/ingest.py
- apps/backend/assistant/api/audit.py
- apps/backend/assistant/api/rag.py
- apps/backend/assistant/api/chat.py
- apps/backend/operations/infrastructure/maintenance.py

RAG UI migration where required:

- apps/rag-ui/src/services/getAuditLogs.ts
- apps/rag-ui/src/services/getRagChat.ts
- callers of those services
- relevant RAG UI tests

Potential widget cleanup:

- packages/assistant-widget/src/api/
- packages/assistant-widget/src/publicChatClient.ts
- relevant tests and generated API types

Canonical implementation examples

Administrator authentication/authorization:

- apps/backend/admin_auth/dependencies.py
  - require_authenticated_administrator
  - require_administrator_role
- existing authenticated /api/admin/\*\* routes

Administrative Operations API:

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

Supported anonymous endpoint:

- POST /public/assistants/{assistant_slug}/chat

Known consumers:

- apps/rag-ui/src/services/getAuditLogs.ts
- apps/rag-ui/src/services/getRagChat.ts
- packages/assistant-widget/src/api/assistant.ts

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

Expected change surface

Expected:

- remove unsupported legacy public routes
- migrate supported RAG UI calls away from insecure legacy endpoints
- introduce authenticated administrative RAG-chat transport only if needed to preserve rag-ui
- reuse the existing Operations audit API for RAG UI audit browsing
- administrator authentication/authorization dependencies
- route registration cleanup
- maintenance middleware cleanup
- backend regression/security tests
- RAG UI service and behavioural tests
- widget cleanup where obsolete /assistant/chat client code remains
- documentation/OpenAPI cleanup

No database migration should be required.

Excluded areas

Do not:

- break or remove apps/rag-ui
- remove RAG UI functionality as a shortcut for closing the backend endpoint
- require RAG UI to use the anonymous public Assistant API when its functionality is administrative/internal
- redesign RAG UI screens
- redesign retrieval, ranking, embeddings or prompts
- redesign ingestion orchestration
- redesign public Assistant chat
- replace the administrator authentication system
- create another API-key/JWT/session system for administrative browser access
- treat rate limiting, CORS, Origin validation or maintenance mode as authorization
- retain insecure endpoints simply for backward compatibility
- introduce database migrations
- alter Assistant or Knowledge Source persistence models

Unknowns Codex must verify

Before changing production code, trace current consumers of each affected endpoint.

Verify:

1. Every caller of:
   - /ingest
   - /chunks
   - /audit-logs
   - /rag-chat
   - /assistant/chat
2. Which RAG UI screens/functions consume:
   - getAuditLogs
   - getRagChat
3. The authentication model currently available to apps/rag-ui.
4. Whether RAG UI already has an authenticated API client/helper that can call /api/admin/\*\*.
5. Whether /api/admin/operations/audit provides all data required by the current RAG UI audit screen.
6. Whether /rag-chat has an authenticated equivalent already implemented under another route.
7. Whether packages/assistant-widget/src/api/assistant.ts is still reachable from the package public surface.
8. Whether /ingest/upload remains a supported integration and therefore must retain its existing credential boundary.
9. Whether /ingest and /chunks have any supported callers that cannot already use modern Knowledge Source or administrative APIs.

⸻

Objective

Close the remaining legacy/public API security holes without regressing apps/rag-ui.

The backend must have explicit and intentional HTTP security boundaries.

The supported anonymous Assistant boundary remains:

POST /public/assistants/{assistant_slug}/chat

The following legacy endpoints must no longer remain anonymously accessible:

POST /ingest
GET /chunks
GET /audit-logs
POST /rag-chat
POST /assistant/chat

Where a legacy endpoint is still required by apps/rag-ui, migrate that capability to an authenticated administrative API and update RAG UI to consume it in the same PR.

Do not solve this by adding more rate limiting.

Authentication and authorization must be explicit and enforced server-side.

⸻

Current architecture

Supported anonymous Assistant API

POST /public/assistants/{assistant_slug}/chat is the deliberate anonymous Assistant boundary.

It already owns:

- assistant-specific resolution
- origin restrictions
- request-size limits
- anonymous throttling
- concurrency controls
- timeout handling
- SSE streaming
- maintenance-mode behaviour
- safe public errors

It must remain anonymous.

Administrative API

The backend already provides authenticated administrative APIs through /api/admin/\*\*.

Administrator authentication uses the existing opaque administrator session model and reusable authentication/role dependencies.

Operations already exposes authenticated audit browsing through:

/api/admin/operations/audit

RAG UI

apps/rag-ui currently depends on legacy backend routes.

In particular:

apps/rag-ui/src/services/getAuditLogs.ts
-> GET /audit-logs
apps/rag-ui/src/services/getRagChat.ts
-> POST /rag-chat

These routes therefore cannot simply disappear without corresponding RAG UI migration.

RAG UI must remain functional after this PR.

Legacy API surface

The Assistant router still mounts older endpoints:

POST /ingest
GET /chunks
GET /audit-logs
POST /rag-chat
POST /assistant/chat

Current security is inconsistent:

- /ingest — rate limited, unauthenticated
- /chunks — unauthenticated
- /audit-logs — rate limited, unauthenticated
- /rag-chat — rate limited, unauthenticated
- /assistant/chat — unauthenticated
- /ingest/upload — separate X-API-Key authentication

Maintenance middleware also explicitly recognises /assistant/chat and /rag-chat as legacy public Assistant paths.

⸻

Required implementation

1. Define the final endpoint disposition

Every target route must finish this PR in one of these states:

REMOVED
ADMIN_REPLACEMENT

There must be no PUBLIC_LEGACY state.

Document the final matrix in the completion report.

2. Remove /assistant/chat

Remove:

POST /assistant/chat

It must not remain an alternative anonymous chat endpoint.

The supported public contract is:

POST /public/assistants/{assistant_slug}/chat

Remove obsolete:

- backend route registration
- controller code if unused
- OpenAPI contract
- package client references
- generated type references
- tests asserting /assistant/chat availability
- documentation
- maintenance middleware special casing

Do not redirect or alias it to the public Assistant endpoint.

3. Migrate RAG UI /rag-chat usage before removing the legacy route

apps/rag-ui must continue supporting its existing RAG-chat workflow.

Do not remove /rag-chat until its RAG UI consumer has a secure replacement.

If no authenticated equivalent currently exists, add the smallest suitable administrator endpoint, for example under the existing admin Assistant namespace:

POST /api/admin/assistant/rag-chat

or another existing admin namespace that matches repository conventions after inspection.

The exact path must follow existing backend routing conventions rather than this example blindly.

Requirements:

- administrator authentication required
- appropriate administrator authorization required
- reuse the existing RAG application/service logic
- do not duplicate retrieval or generation behaviour
- preserve the RAG UI response contract where practical
- do not trust caller-provided user_role as authorization
- update getRagChat.ts to call the authenticated endpoint
- ensure browser credentials/session behaviour follows existing admin-client conventions

Once RAG UI has migrated:

- remove public /rag-chat
- remove legacy middleware classification
- remove obsolete route tests/docs

4. Migrate RAG UI audit browsing to Operations API

Remove:

GET /audit-logs

RAG UI currently uses it and therefore must be migrated first.

Prefer the existing canonical endpoint:

GET /api/admin/operations/audit

Update:

apps/rag-ui/src/services/getAuditLogs.ts

to consume the authenticated Operations API.

Adapt response mapping inside the service boundary if the Operations response differs from the legacy RAG UI model.

Do not make UI components directly understand multiple backend representations.

Preserve existing user-visible audit browsing behaviour as far as the canonical API supports it.

If required fields are genuinely missing from the Operations endpoint, extend the existing administrative API only where necessary rather than restoring /audit-logs.

After migration:

- remove /audit-logs
- remove legacy route tests
- remove legacy documentation

5. Remove /chunks

Remove unauthenticated:

GET /chunks

Raw retrieval chunks are not a public API.

Preserve underlying application functionality if backend internals use it.

Do not create a replacement endpoint unless an existing supported UI/workflow demonstrably requires raw chunk browsing.

Any future browser-accessible replacement must be authenticated under /api/admin/\*\*.

6. Close /ingest

Remove unauthenticated:

POST /ingest

unless inspection proves an active supported integration still requires equivalent raw-text ingestion.

Prefer modern Knowledge Source/ingestion APIs.

If equivalent functionality remains required for administrators:

- expose it through an authenticated existing admin namespace
- reuse existing ingestion application services
- remove public /ingest

Do not add another static API key solely to preserve this path.

7. Preserve /ingest/upload security

POST /ingest/upload currently has explicit X-API-Key protection.

It is not equivalent to the unsecured /ingest route.

Codex must verify whether this endpoint is still supported.

If retained:

- preserve explicit credential validation
- ensure missing/invalid credentials are rejected before file persistence or ingestion submission where practical
- preserve idempotency behaviour
- document why this integration remains

If obsolete and unused:

- it may be removed

Do not accidentally make it public while refactoring ingest.py.

8. Use the existing administrator auth system

Any new browser-accessible replacement required by RAG UI must use existing administrator authentication.

Reuse:

- administrator session cookies
- require_authenticated_administrator
- require_administrator_role
- existing admin error contracts/client handling

Do not introduce:

- X-Admin-Key
- another JWT implementation
- another cookie/session format
- browser-stored secrets
- frontend-only authorization

9. Preserve RAG UI behaviour

This PR must leave apps/rag-ui functional.

At minimum preserve:

- sending a RAG chat request
- displaying the resulting reply
- displaying associated source/evaluation data currently relied upon by the UI
- loading audit records
- existing loading/error behaviour
- authentication failure handling consistent with authenticated administrative APIs

Do not remove a RAG UI feature because its old backend endpoint was insecure.

10. Preserve public Assistant chat

Do not add administrator authentication to:

POST /public/assistants/{assistant_slug}/chat

Preserve:

- anonymous access
- public-chat throttling
- concurrency controls
- Origin restrictions
- request-size enforcement
- timeout handling
- SSE contract
- maintenance behaviour
- safe error mapping

11. Clean route registration

Update:

apps/backend/assistant/api/routes.py

Remove obsolete router imports and registrations.

Delete dead API modules if they no longer contain supported routes.

Do not leave unreachable compatibility controllers.

12. Clean maintenance middleware

Remove:

\_LEGACY_PUBLIC_ASSISTANT_PATHS = frozenset({"/assistant/chat", "/rag-chat"})

after those legacy public routes have been retired.

Maintenance mode must continue covering:

/public/assistants/{assistant_slug}/chat

Authenticated admin RAG endpoints must not be treated as anonymous public traffic.

13. Clean widget legacy client code

Verify whether:

packages/assistant-widget/src/api/assistant.ts

is obsolete.

If it exists only for /assistant/chat:

- remove it
- remove obsolete tests
- remove schema/type dependencies that are no longer needed
- ensure no public package export exposes it

The supported widget must continue using:

packages/assistant-widget/src/publicChatClient.ts

14. Update OpenAPI and documentation

Removed routes must disappear from OpenAPI.

Document the final security model:

/public/** explicitly anonymous where designed
/api/admin/** authenticated/authorized
legacy routes removed

Do not describe removed routes as supported compatibility endpoints.

15. Rate limiting is not authorization

Rate limiting may remain as defence-in-depth.

It must never be the only protection for:

- ingestion
- audit retrieval
- raw chunks
- internal RAG chat
- legacy Assistant chat

⸻

Acceptance criteria

- Task is implemented on pr1a-legacy-public-api-security-hardening.
- Governing spec is .codex/tasks/1a-legacy-public-api-security-hardening.md.
- apps/rag-ui remains functional.
- RAG UI no longer calls unauthenticated /rag-chat.
- RAG UI RAG chat uses an explicitly authenticated administrative backend endpoint.
- RAG UI no longer calls /audit-logs.
- RAG UI audit browsing uses /api/admin/operations/audit or an extension of that canonical administrative contract.
- No RAG UI feature is removed merely because its original endpoint was insecure.
- POST /assistant/chat is removed.
- POST /rag-chat is removed after RAG UI migration.
- GET /audit-logs is removed after RAG UI migration.
- GET /chunks is removed from the public API.
- POST /ingest is removed from the public API.
- Removed routes are absent from OpenAPI.
- Any new RAG UI backend replacement uses existing administrator session authentication.
- Any new RAG UI backend replacement enforces server-side authorization.
- Unauthorized requests do not invoke retrieval, LLM/provider calls, audit reads or ingestion work.
- Caller-provided user_role cannot be used to elevate privileges.
- /ingest/upload does not become less secure.
- If /ingest/upload remains, missing and invalid credentials remain rejected.
- POST /public/assistants/{assistant_slug}/chat remains anonymous.
- Existing public-chat abuse and maintenance protections remain passing.
- Public Assistant widget chat continues using /public/assistants/{assistant_slug}/chat.
- The widget does not ship a supported /assistant/chat client.
- Maintenance middleware no longer treats /assistant/chat or /rag-chat as public paths.
- No new authentication library or parallel credential system is introduced.
- No database migration is introduced.
- Existing Assistant, Knowledge Source, Operations and administrator-auth functionality remains passing.
- Documentation reflects the final route boundaries.

Tests to add or update

Backend security regression

Add:

apps/backend/tests/test_legacy_api_security.py

Verify removed routes are not mounted:

POST /assistant/chat
POST /rag-chat
GET /audit-logs
GET /chunks
POST /ingest

Assert both HTTP behaviour and OpenAPI absence where appropriate.

Authenticated RAG endpoint

Add focused tests for the RAG UI replacement endpoint.

Cover:

- unauthenticated request
- invalid session
- authenticated non-authorized administrator if roles differ
- authorized administrator
- malformed request
- retrieval/provider failure mapping
- denied requests do not invoke RAG/provider work
- response contains the fields needed by apps/rag-ui

Use existing RAG application services rather than reproducing them in tests/controllers.

Administrative audit regression

Update/run:

apps/backend/tests/test_operations_administration_api.py

Cover the audit response fields consumed by RAG UI.

Public Assistant regression

Run:

apps/backend/tests/test_public_chat.py
apps/backend/tests/test_public_chat_protection.py

Ensure the public Assistant API remains intentionally anonymous.

Ingestion regression

Run/update:

apps/backend/tests/test_ingest_upload.py
apps/backend/tests/test_ingestion_api.py
apps/backend/tests/test_ingestion_jobs_api.py

If /ingest/upload remains, test:

- missing API key
- invalid API key
- valid API key
- rejected request creates no ingestion job

RAG UI tests

Update tests around:

apps/rag-ui/src/services/getRagChat.ts
apps/rag-ui/src/services/getAuditLogs.ts

Verify:

- correct authenticated admin paths
- credentials/session are included according to existing client conventions
- response adaptation preserves the service’s existing consumer contract
- auth failures surface correctly
- server failures surface correctly

Run relevant rendered RAG UI tests to prove chat and audit functionality still work.

Widget regression

If legacy widget API code changes, run/update:

packages/assistant-widget/src/publicChatClient.test.ts
packages/assistant-widget/src/AssistantWidget.public.test.tsx
packages/assistant-widget/src/api/assistant.test.ts

Delete obsolete tests only when the corresponding obsolete production client is removed.

Do not weaken assertions.

Verification commands

# Confirm endpoint/client references after migration.

rg -n '(/assistant/chat|/rag-chat|/audit-logs|/chunks|/ingest)' \
 apps packages README.md docs

# Backend focused security tests.

cd apps/backend
pytest tests/test_legacy_api_security.py -q

# New authenticated RAG endpoint test file; use the actual final filename.

pytest tests/test\_*rag*admin\*.py -q
pytest \
 tests/test_operations_administration_api.py \
 tests/test_admin_authentication_api.py \
 -q
pytest \
 tests/test_public_chat.py \
 tests/test_public_chat_protection.py \
 -q
pytest \
 tests/test_ingest_upload.py \
 tests/test_ingestion_api.py \
 tests/test_ingestion_jobs_api.py \
 -q
cd ../..

# Broader backend suite.

npm run test:api

# RAG UI must remain healthy.

npm run lint --workspace @ai-discovery-assistant/rag-ui
npm run build --workspace @ai-discovery-assistant/rag-ui
npm run test:storybook

# Widget checks when affected.

npm run lint --workspace @redmoor/assistant-widget
npm test --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget

# Broader affected workspace tests.

npm test

Before completion, verify the final route matrix explicitly:

Endpoint Final boundary
POST /assistant/chat REMOVED
POST /rag-chat REMOVED
GET /audit-logs REMOVED
GET /chunks REMOVED
POST /ingest REMOVED
POST /ingest/upload RETAINED + EXPLICIT AUTH or REMOVED
POST /api/admin/.../rag-chat ADMIN AUTHENTICATED
GET /api/admin/operations/audit ADMIN AUTHENTICATED
POST /public/assistants/{assistant_slug}/chat PUBLIC

The exact authenticated RAG-chat route name must follow the repository’s existing administrative route conventions after inspection.

Do not mark this task complete if apps/rag-ui loses either its RAG chat or audit browsing functionality.
