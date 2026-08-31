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

- Existing supported anonymous Assistant boundary:
  - POST /public/assistants/{assistant_slug}/chat
- Existing public-chat abuse protection, request limits, origin handling and maintenance-mode integration
- Existing apps/rag-ui backend contracts:
  - POST /rag-chat
  - GET /audit-logs
- Existing X-API-Key protection for POST /ingest/upload

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

Backend API exposure and route cleanup:

- apps/backend/assistant/api/routes.py
- apps/backend/assistant/api/ingest.py
- apps/backend/assistant/api/chat.py
- apps/backend/operations/infrastructure/maintenance.py

Contract-preservation files that must remain unchanged from main:

- apps/backend/assistant/api/rag.py
- apps/backend/assistant/api/audit.py
- apps/rag-ui/**

Potential widget cleanup:

- packages/assistant-widget/src/api/
- packages/assistant-widget/src/publicChatClient.ts
- relevant tests and generated API types

Supported anonymous chat:

- apps/backend/assistant/api/public_chat.py
- apps/backend/assistant/application/public_chat.py
- apps/backend/assistant/application/public_chat_protection.py
- packages/assistant-widget/src/publicChatClient.ts

Relevant endpoints

Routes owned by PR 1A:

- POST /assistant/chat
- GET /chunks
- POST /ingest
- POST /ingest/upload

Temporary legacy exceptions not owned by PR 1A:

- POST /rag-chat
- GET /audit-logs

Supported anonymous endpoint:

- POST /public/assistants/{assistant_slug}/chat

Known consumers:

- apps/rag-ui/src/services/getAuditLogs.ts -> GET /audit-logs
- apps/rag-ui/src/services/getRagChat.ts -> POST /rag-chat
- packages/assistant-widget/src/api/assistant.ts -> POST /assistant/chat

Expected change surface

Expected:

- remove POST /assistant/chat
- remove GET /chunks
- remove raw-text POST /ingest
- preserve POST /ingest/upload and its existing credential boundary
- preserve POST /rag-chat exactly as it exists on main
- preserve GET /audit-logs exactly as it exists on main
- preserve apps/rag-ui without any source, URL, authentication, or test changes
- clean route registration only for endpoints removed by this PR
- clean maintenance middleware only for endpoints removed by this PR
- add focused backend regression/security tests
- remove obsolete widget /assistant/chat client code where it is not part of the supported package surface
- update OpenAPI and documentation for the routes actually removed

No database migration, new administrator endpoint, new authentication mechanism, or RAG UI change is required.

Excluded areas

Do not:

- change any file under apps/rag-ui
- add authentication or session handling to RAG UI
- migrate any RAG UI endpoint
- remove or modify POST /rag-chat
- remove or modify GET /audit-logs
- create a replacement /admin/** RAG-chat endpoint
- create a replacement /admin/** RAG audit endpoint
- add an auth wrapper, compatibility alias, new rate limit, or new API contract for /rag-chat or /audit-logs
- partially secure or migrate the retained RAG UI routes
- redesign retrieval, ranking, embeddings, prompts, or RAG response data
- redesign ingestion orchestration
- redesign public Assistant chat
- replace or extend the administrator authentication system
- introduce another API-key, JWT, cookie, or session system
- introduce database migrations
- alter Assistant or Knowledge Source persistence models
- retire apps/rag-ui in this PR

Unknowns Codex must verify

Before changing production code, verify:

1. packages/assistant-widget/src/api/assistant.ts is not reachable from the supported package surface and exists only for /assistant/chat before removing it.
2. /ingest and /chunks have no active supported consumers.
3. /ingest/upload remains a supported integration and retains its existing X-API-Key boundary.
4. The /rag-chat and /audit-logs implementations, registrations, OpenAPI operations, middleware behaviour, and RAG UI consumers match origin/main before and after the change.
5. apps/rag-ui has no diff against origin/main.

⸻

Objective

Remove only the unused legacy public endpoints that PR 1A can safely retire without changing a backend contract currently used by apps/rag-ui. The RAG UI routes and behaviour must remain exactly as they were before PR #86.

The supported anonymous Assistant-widget boundary remains:

POST /public/assistants/{assistant_slug}/chat

PR 1A removes:

- POST /assistant/chat
- GET /chunks
- POST /ingest

PR 1A preserves:

- POST /rag-chat exactly as it exists on main
- GET /audit-logs exactly as it exists on main
- POST /ingest/upload with its existing explicit X-API-Key protection

PR 1A must not add administrator authentication to RAG UI, migrate RAG UI to /admin/**, or create any replacement RAG administrator contract.

⸻

Temporary RAG UI legacy exception

POST /rag-chat and GET /audit-logs are explicit temporary exceptions to the security-hardening objective because they are active backend dependencies of apps/rag-ui.

This exception is intentionally narrow:

- Both routes remain legacy technical debt.
- Both routes remain candidates for removal.
- Their removal or partial hardening is out of scope for PR 1A.
- A separate future PR will remove apps/rag-ui and then remove these backend endpoints together. If a migration is chosen instead of retirement, that migration must be deliberate and complete within that separate PR.
- PR 1A must keep their routes, request and response contracts, rate limits, maintenance behaviour, and observable errors unchanged from main.
- PR 1A must not add another rate limit, authentication wrapper, compatibility alias, administrator replacement, response adapter, or new API contract for either route.
- Retaining these routes in PR 1A is not an endorsement of them as a supported long-term public API.

The two routes must be removed only in the same deliberate change that retires or migrates their RAG UI consumers.

⸻

Current architecture

Supported anonymous Assistant API

POST /public/assistants/{assistant_slug}/chat is the deliberate anonymous Assistant boundary for the published widget.

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

It must remain anonymous and unchanged.

RAG UI

apps/rag-ui currently calls:

apps/rag-ui/src/services/getAuditLogs.ts
-> GET /audit-logs

apps/rag-ui/src/services/getRagChat.ts
-> POST /rag-chat

PR 1A must not change those files, URLs, request options, response handling, or authentication behaviour.

Legacy API surface

The Assistant router on main mounts:

- POST /ingest — rate limited, unauthenticated
- GET /chunks — unauthenticated
- GET /audit-logs — rate limited, unauthenticated, temporarily retained for RAG UI
- POST /rag-chat — rate limited, unauthenticated, temporarily retained for RAG UI
- POST /assistant/chat — unauthenticated
- POST /ingest/upload — separate X-API-Key authentication

Maintenance middleware recognises /assistant/chat and /rag-chat as legacy public Assistant paths on main. After PR 1A, /assistant/chat may be removed from that classification because its route is removed. /rag-chat must retain its main-branch maintenance behaviour while it remains a live RAG UI route.

⸻

Required implementation

1. Final endpoint disposition

The final matrix is mandatory:

| Endpoint | PR 1A disposition |
| --- | --- |
| POST /assistant/chat | REMOVE |
| GET /chunks | REMOVE |
| POST /ingest | REMOVE |
| POST /rag-chat | KEEP AS-IS TEMPORARILY |
| GET /audit-logs | KEEP AS-IS TEMPORARILY |
| POST /ingest/upload | KEEP EXISTING AUTHENTICATED BEHAVIOUR |
| POST /public/assistants/{assistant_slug}/chat | KEEP SUPPORTED ANONYMOUS BEHAVIOUR |

There is no administrator replacement endpoint in PR 1A.

2. Remove /assistant/chat

Remove POST /assistant/chat. It must not remain as an alternative anonymous chat endpoint and must not redirect or alias to another route.

Remove obsolete:

- backend route registration
- controller code if unused
- OpenAPI operation
- package client references
- generated type references
- tests asserting availability
- documentation
- maintenance middleware special casing for /assistant/chat

The supported public widget contract remains POST /public/assistants/{assistant_slug}/chat.

3. Preserve /rag-chat unchanged

POST /rag-chat is out of scope for removal, migration, or hardening in PR 1A.

Do not:

- edit apps/backend/assistant/api/rag.py
- change its route registration
- change its request or response schema
- change its rate limit or maintenance-mode treatment
- add authentication or authorization
- create an /admin/** replacement
- change apps/rag-ui/src/services/getRagChat.ts or its callers
- add RAG UI tests for a replacement transport

4. Preserve /audit-logs unchanged

GET /audit-logs is out of scope for removal, migration, or hardening in PR 1A.

Do not:

- edit apps/backend/assistant/api/audit.py
- change its route registration
- change its request or response behaviour
- change its existing rate limit
- add authentication or authorization
- create an /admin/** replacement or Operations audit extension
- change apps/rag-ui/src/services/getAuditLogs.ts or its callers
- add RAG UI tests for a replacement transport

5. Remove /chunks

Remove unauthenticated GET /chunks. Raw retrieval chunks are not a public API.

Preserve underlying application functionality if backend internals use it. Do not create a replacement endpoint in PR 1A.

6. Remove raw-text /ingest

Remove unauthenticated POST /ingest. Prefer the existing modern Knowledge Source and ingestion APIs for supported workflows.

Do not add another static API key or administrator replacement solely to preserve this path.

7. Preserve /ingest/upload security

POST /ingest/upload is distinct from raw-text POST /ingest and remains supported with its existing X-API-Key protection.

Preserve:

- explicit credential validation
- rejection of missing and invalid credentials before file persistence or ingestion submission where practical
- valid-key behaviour
- idempotency behaviour
- existing request and response contract

Do not make this route public while removing POST /ingest from the same module.

8. Preserve public Assistant chat

Do not add administrator authentication to POST /public/assistants/{assistant_slug}/chat.

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

9. Clean route registration narrowly

Update apps/backend/assistant/api/routes.py only as needed to remove routes owned by PR 1A.

Keep the rag and audit routers mounted. Do not delete or replace their controller modules.

Delete dead API modules only when every route in the module is removed by this PR.

10. Clean maintenance middleware narrowly

Remove /assistant/chat from legacy public-path classification after its route is retired.

Keep /rag-chat classified and handled exactly as it is on main while the temporary RAG UI exception remains live.

Maintenance mode must continue covering:

- /public/assistants/{assistant_slug}/chat
- /rag-chat

11. Clean widget legacy client code

Verify whether packages/assistant-widget/src/api/assistant.ts exists only for /assistant/chat and is not exposed from the supported package surface.

If obsolete:

- remove it
- remove its obsolete tests
- remove schema/type dependencies used only by it
- ensure no public package export exposes it

The supported widget must continue using packages/assistant-widget/src/publicChatClient.ts and POST /public/assistants/{assistant_slug}/chat.

12. Update OpenAPI and documentation

The removed /assistant/chat, /chunks, and raw-text /ingest operations must disappear from OpenAPI.

/rag-chat and /audit-logs must remain in OpenAPI unchanged from main.

Documentation must distinguish:

- POST /public/assistants/{assistant_slug}/chat as the supported anonymous Assistant-widget boundary
- POST /ingest/upload as an explicitly credentialed integration
- /assistant/chat, /chunks, and raw-text /ingest as removed
- /rag-chat and /audit-logs as temporary legacy exceptions pending a separate RAG UI retirement or migration PR

Do not describe /rag-chat or /audit-logs as newly secured, migrated, or long-term supported contracts.

13. Rate limiting is not authorization

Do not treat the existing rate limits on /rag-chat or /audit-logs as a security remediation delivered by PR 1A. Their unchanged retention is a documented scope exception, not a claim that they are adequately authorized.

Do not add another rate limit or other partial mitigation to either retained route in this PR.

⸻

Acceptance criteria

- Task is implemented on 1a-legacy-public-api-security-hardening.
- Governing spec is .codex/tasks/1a-legacy-public-api-security-hardening.md.
- POST /assistant/chat is removed and absent from OpenAPI.
- GET /chunks is removed and absent from OpenAPI.
- Raw-text POST /ingest is removed and absent from OpenAPI.
- POST /ingest/upload retains its existing explicit credential protection and contract.
- Missing and invalid /ingest/upload credentials are rejected before persistence or ingestion work.
- POST /public/assistants/{assistant_slug}/chat remains the supported anonymous Assistant-widget boundary.
- Existing public-chat abuse and maintenance protections remain passing.
- The public Assistant widget continues using /public/assistants/{assistant_slug}/chat.
- The widget does not ship a supported /assistant/chat client.
- POST /rag-chat remains unchanged from origin/main, including registration, behaviour, rate limiting, OpenAPI, and maintenance treatment.
- GET /audit-logs remains unchanged from origin/main, including registration, behaviour, rate limiting, and OpenAPI.
- apps/rag-ui is unchanged from origin/main and continues to use /rag-chat and /audit-logs.
- No RAG UI authentication or session behaviour is introduced.
- No /admin/** replacement endpoint is introduced for RAG UI chat or RAG audit history.
- No new authentication library or parallel credential system is introduced.
- No database migration is introduced.
- Existing Assistant, Knowledge Source, ingestion, public-chat, and widget functionality remains passing.
- Documentation records /rag-chat and /audit-logs as temporary legacy exceptions pending a separate RAG UI retirement or migration PR.

⸻

Tests to add or update

Backend route security regression

Add or update apps/backend/tests/test_legacy_api_security.py to prove:

- POST /assistant/chat returns 404 and is absent from OpenAPI.
- GET /chunks returns 404 and is absent from OpenAPI.
- POST /ingest returns 404 and is absent from OpenAPI.
- POST /rag-chat retains its pre-PR HTTP behaviour and remains present in OpenAPI.
- GET /audit-logs retains its pre-PR HTTP behaviour and remains present in OpenAPI.
- POST /ingest/upload remains present in OpenAPI and retains its pre-PR authenticated behaviour.

The /rag-chat and /audit-logs assertions are contract-preservation regressions, not tests for a replacement endpoint.

RAG and audit regression

Run the existing focused tests for RAG application behaviour and audit retrieval. Add only the smallest backend route-level assertions needed to prove the main-branch contracts remain mounted and unchanged.

Do not add:

- authenticated RAG administrator endpoint tests
- administrator RAG audit endpoint tests
- RAG UI authentication tests
- RAG UI service tests for new URLs or credentials

Public Assistant regression

Run:

- apps/backend/tests/test_public_chat.py
- apps/backend/tests/test_public_chat_protection.py
- packages/assistant-widget/src/publicChatClient.test.ts
- packages/assistant-widget/src/AssistantWidget.public.test.tsx

Ensure the public Assistant API remains intentionally anonymous and the widget continues to use it.

Ingestion regression

Run/update:

- apps/backend/tests/test_ingest_upload.py
- apps/backend/tests/test_ingestion_api.py
- apps/backend/tests/test_ingestion_jobs_api.py

For /ingest/upload, prove:

- missing API key is rejected
- invalid API key is rejected
- valid API key retains pre-PR behaviour
- a rejected request creates no upload file or ingestion job
- idempotency behaviour is unchanged

Widget regression

If obsolete widget /assistant/chat code is removed, run/update:

- packages/assistant-widget/src/publicChatClient.test.ts
- packages/assistant-widget/src/AssistantWidget.public.test.tsx
- package build and consumer verification

Delete obsolete tests only when their corresponding obsolete production client is removed. Do not weaken assertions.

⸻

Verification commands

# Confirm the three removed endpoints have no live controller/client references and retained routes remain.

rg -n '(/assistant/chat|/rag-chat|/audit-logs|/chunks|/ingest)' \
  apps packages README.md docs

# Prove PR 1A does not alter RAG UI or its backend contracts.

git diff origin/main...HEAD -- apps/rag-ui
git diff origin/main...HEAD -- \
  apps/backend/assistant/api/rag.py \
  apps/backend/assistant/api/audit.py

Both diffs must be empty. The governing specification may document this deferred work, but no production, UI, or test file in those paths may change.

# Backend focused route and security tests.

cd apps/backend
pytest tests/test_legacy_api_security.py -q
pytest \
  tests/test_rag_chat.py \
  tests/test_audit.py \
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

# Widget checks when affected.

npm run lint --workspace @redmoor/assistant-widget
npm test --workspace @redmoor/assistant-widget
npm run pack:verify --workspace @redmoor/assistant-widget

# No RAG UI build, lint, service-test, authentication, or migration work is introduced by PR 1A.
# Its unchanged state is established by the empty origin/main diff above.

# Broader affected workspace tests.

npm test

Before completion, report the final route matrix explicitly:

| Endpoint | Final boundary |
| --- | --- |
| POST /assistant/chat | REMOVED |
| GET /chunks | REMOVED |
| POST /ingest | REMOVED |
| POST /rag-chat | TEMPORARILY RETAINED UNCHANGED FOR RAG UI |
| GET /audit-logs | TEMPORARILY RETAINED UNCHANGED FOR RAG UI |
| POST /ingest/upload | RETAINED WITH EXISTING X-API-KEY AUTHENTICATION |
| POST /public/assistants/{assistant_slug}/chat | SUPPORTED ANONYMOUS ASSISTANT-WIDGET BOUNDARY |

Do not mark this task complete if apps/rag-ui, apps/backend/assistant/api/rag.py, or apps/backend/assistant/api/audit.py differs from origin/main, or if any RAG UI replacement administrator endpoint has been introduced.
