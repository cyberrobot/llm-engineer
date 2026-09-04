# PR 4 — Extract a runnable `apps/rag-backend`

## Repository state

Expected branch:

`4-extract-runnable-rag-backend`

Base branch:

`main`

Worktree:

Fresh worktree based on current `origin/main`.

Dependencies:

- PR 1B / frozen legacy RAG contract must be present.
- PR 2 / secured RAG UI boundary must be present and must not be weakened.
- PR 3 / explicit RAG data contracts must be present.
- The existing `apps/backend` implementation of:
  - `POST /rag-chat`
  - `GET /audit-logs`
  
  must remain runnable for the duration of this PR.
- `apps/rag-ui` must continue using the existing production/backend route. Do not switch it to `apps/rag-backend` in this PR.
- No production ingress, Railway routing, reverse-proxy routing, DNS, public endpoint, or frontend API base URL may be changed to direct traffic to the new service.
- The frozen legacy RAG contract represents the authoritative HTTP compatibility target for both implementations.
- The current protected RAG boundary must remain protected. Do not make the new service anonymous merely because it is not receiving production traffic yet.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/TEMPLATE.md`
- `.codex/tasks/1b-freeze-legacy-rag-contract.md`
- `.codex/tasks/2-secure-rag-ui-boundary.md`
- `.codex/tasks/3-introduce-explicit-rag-data-contracts.md`
- `apps/backend/docs/legacy-rag-contract.md`
- `apps/backend/docs/rag-persistence-contract.md`
- `apps/backend/main.py`
- `apps/backend/README.md`

### Primary change area

New service:

- `apps/rag-backend/`
- `apps/rag-backend/main.py`
- `apps/rag-backend/api/`
- `apps/rag-backend/application/`
- `apps/rag-backend/application/ports/`
- `apps/rag-backend/infrastructure/`
- `apps/rag-backend/prompts/`
- `apps/rag-backend/tests/`
- `apps/rag-backend/.env.example`
- `apps/rag-backend/README.md`

Existing backend areas used as behavioural references:

- `apps/backend/assistant/api/rag.py`
- `apps/backend/assistant/api/audit.py`
- `apps/backend/assistant/api/rag_ui_middleware.py`
- `apps/backend/assistant/api/dependencies.py`
- `apps/backend/assistant/application/rag_chat.py`
- `apps/backend/assistant/application/rag_search.py`
- `apps/backend/assistant/application/retrieval.py`
- `apps/backend/assistant/application/ports/rag_knowledge_repository.py`
- `apps/backend/assistant/infrastructure/repositories/rag_knowledge.py`
- `apps/backend/assistant/infrastructure/generate_queries.py`
- `apps/backend/assistant/infrastructure/rerank.py`
- `apps/backend/assistant/infrastructure/llm.py`
- existing RAG audit persistence
- existing RAG evaluation implementation
- existing RAG cache implementation
- `apps/backend/prompts/`
- `apps/backend/tests/test_legacy_rag_contract.py`

Shared operational behaviour to reproduce independently:

- health probes
- request correlation
- safe exception mapping
- CORS
- rate limiting
- authentication/authorization required by the secured RAG UI boundary
- request-size limits
- request/provider timeouts

### Canonical implementation examples

Use the existing backend as the behavioural reference, not as a runtime Python dependency.

In particular inspect and preserve the semantics of:

- `assistant.application.rag_chat`
- `assistant.application.rag_search`
- `assistant.application.retrieval`
- `assistant.application.ports.rag_knowledge_repository.RagKnowledgeRepository`
- `assistant.infrastructure.repositories.rag_knowledge.PostgresRagKnowledgeRepository`
- `assistant.infrastructure.generate_queries`
- `assistant.infrastructure.rerank`
- `assistant.infrastructure.llm`
- current audit persistence
- current Redis-backed RAG cache
- current evaluation/debug implementation
- the existing health probe implementation
- the existing correlation middleware
- the existing safe exception handlers
- the existing administrator-session protection used by the RAG UI
- the current frozen legacy RAG HTTP tests

Follow the repository's normal API → application → port → infrastructure dependency direction.

Do not introduce a new framework or persistence abstraction where the existing RAG architecture can be reproduced cleanly inside the new service.

Temporary duplication between the two applications is acceptable during service extraction when it is necessary to keep both implementations independently runnable.

Do not solve temporary duplication by making `apps/rag-backend` import implementation modules from `apps/backend`.

### Relevant symbols

Existing RAG orchestration:

- `assistant.application.rag_chat.rag_chat`
- `assistant.application.rag_chat.empty_response`
- `assistant.application.rag_chat.build_audit_event`
- `assistant.application.rag_search.rag_search`
- `assistant.application.retrieval.search_chunks`
- `assistant.application.retrieval.multi_query_search`
- `assistant.application.retrieval.deduplicate`

Retrieval contract:

- `assistant.application.ports.rag_knowledge_repository.RagKnowledgeRepository`
- `assistant.application.ports.rag_knowledge_repository.RagKnowledgeChunk`
- `assistant.infrastructure.repositories.rag_knowledge.PostgresRagKnowledgeRepository`

Provider-backed legacy components:

- `assistant.infrastructure.generate_queries.generate_queries`
- `assistant.infrastructure.rerank.rerank_chunks`
- `assistant.infrastructure.llm.ask_rag`

Prompt files:

- `query_generation.md`
- `rerank_chunks.md`
- `answer_system.md`

HTTP contract:

- `assistant.api.rag.RagChatRequest`
- `assistant.api.rag.RagChatResponse`
- `assistant.api.rag.rag_chat_endpoint`
- current `/audit-logs` endpoint
- current RAG message/request-size limits
- current bounded audit-log limit

Operational behaviour:

- current request-correlation middleware
- current safe exception handlers
- current SlowAPI limiter
- current RAG UI authentication/authorization boundary
- current CORS trusted-origin policy
- `GET /health/live`
- `GET /health/ready`

Frozen compatibility suite:

- `apps/backend/tests/test_legacy_rag_contract.py`

### Expected change surface

Expected changes include:

- creation of a fully runnable `apps/rag-backend` Python application;
- independent application startup and dependency wiring;
- independent configuration;
- RAG-only HTTP routes;
- RAG-only health/readiness checks;
- RAG orchestration implementation;
- multi-query generation;
- hybrid retrieval using the PR 3 persistence contract;
- reranking;
- answer generation;
- evaluation/debug output;
- RAG audit persistence;
- RAG response caching;
- the three RAG prompt files;
- request correlation;
- safe HTTP errors;
- explicit trusted-origin CORS configuration;
- authentication/authorization equivalent to the secured RAG boundary;
- request and message size limits;
- rate limiting;
- whole-request timeout protection;
- provider-call timeouts;
- resource lifecycle/cleanup;
- service-local tests;
- shared or parameterized contract fixtures capable of exercising both applications;
- documentation for running both applications simultaneously.

Small changes to the existing backend contract tests are allowed where necessary to make the same fixtures executable against two FastAPI applications.

Those changes must not weaken or redefine the frozen contract.

### Excluded areas

Do not:

- remove `/rag-chat` from `apps/backend`;
- remove `/audit-logs` from `apps/backend`;
- route production traffic to `apps/rag-backend`;
- update `apps/rag-ui` to use the new service;
- change the RAG UI API base URL;
- change public Assistant widget routing;
- change `POST /public/assistants/{assistant_slug}/chat`;
- migrate ingestion into `apps/rag-backend`;
- migrate Assistant administration into `apps/rag-backend`;
- migrate public Assistant chat into `apps/rag-backend`;
- migrate maintenance administration into the service;
- import Python implementation modules from `apps/backend` into `apps/rag-backend`;
- manipulate `sys.path` or `PYTHONPATH` to make cross-application implementation imports possible;
- rely on the backend process for Redis, OpenAI, database, configuration, middleware, or lifecycle objects;
- redesign the hybrid retrieval algorithm;
- change vector/keyword weighting;
- change maximum-distance semantics;
- change result limits;
- change prompt semantics;
- improve or rewrite the legacy fallback answer;
- reshape RAG responses;
- reshape audit-log responses;
- weaken authentication or server-derived role enforcement;
- restore client-controlled authorization through `user_role`;
- remove `Cache-Control: no-store` from audit/debug responses;
- expose raw exceptions;
- expose provider responses, SQL, credentials, prompts, or document contents in errors;
- expand the RAG service into a generic replacement backend;
- delete the original RAG implementation yet;
- introduce production routing or a cutover flag in this PR.

### Unknowns Codex must verify

Before implementation, verify:

1. The exact current files implementing:
   - multi-query generation;
   - retrieval;
   - reranking;
   - answer generation;
   - evaluation;
   - audit persistence;
   - caching.

2. The exact current three RAG prompt paths and ensure the extracted service loads identical content.

3. The exact RAG Redis key format, TTL, serialization and cache-hit behaviour that are observable through the contract or application tests.

4. Which current OpenAI calls are used for:
   - embeddings;
   - query generation;
   - reranking;
   - answer generation;
   - evaluation, if provider-backed.

5. Which provider operations currently have timeouts and which rely only on SDK defaults.

6. The current administrator-session mechanism protecting `/rag-chat` and `/audit-logs`, including:
   - cookie name;
   - session lookup;
   - expiry;
   - CSRF/origin handling where applicable;
   - how the effective RAG role is derived server-side.

7. Whether the intended split-service deployment can validate the same administrator session directly or is expected to sit behind an identity-aware/private proxy.

8. If the existing administrator-session implementation cannot be reproduced in the new service without inappropriate coupling, stop and report the architecture conflict. Do not make the endpoints anonymous.

9. Whether PR 3 has provided a deployment-ready least-privilege RAG database credential and what configuration name should be used by the new service.

10. The exact database privileges required by:
    - hybrid retrieval;
    - RAG audit reads;
    - RAG audit writes.

    The knowledge repository may be read-only, but audit persistence requires its own explicit write capability.

11. Whether audit data lives in the same PostgreSQL database and whether a single least-privilege service credential can safely cover both knowledge reads and audit writes.

12. Existing health/readiness dependency semantics and which dependencies must determine `rag-backend` readiness:
    - PostgreSQL;
    - Redis when caching is enabled;
    - configuration validity;
    - provider configuration.

13. The exact current CORS policy needed by `apps/rag-ui`.

14. The exact request-size, message-size, audit-limit and rate-limit values currently frozen by tests.

15. How existing `X-Request-ID` normalization and response propagation work.

16. Whether the repo already contains an established mechanism for sharing test-only contract fixtures between sibling Python applications.

17. Whether each Python application currently has its own dependency manifest or whether backend dependencies are managed centrally.

18. How Docker/Railway/local commands identify the backend working directory and module entry point so that both applications can bind different ports simultaneously.

19. Whether any backend RAG implementation currently imports unrelated ingestion/admin modules indirectly. Do not reproduce those accidental dependencies in the new service.

20. All current RAG tests whose behaviour needs to be copied or parameterized rather than left testing only the original implementation.

If repository state materially contradicts these assumptions, report the mismatch rather than inventing a parallel architecture.

---

## Objective

Create a new independently runnable FastAPI service at:

`apps/rag-backend`

The service must reproduce the existing legacy RAG UI backend behaviour without changing production routing.

It must own the runtime implementation required for:

- `GET /health/live`
- `GET /health/ready`
- `POST /rag-chat`
- `GET /audit-logs`

The new service must contain or depend only on appropriate service-local or genuinely shared neutral code. It must not import Python implementation modules from `apps/backend`.

During this PR both implementations must remain runnable and the same frozen legacy RAG contract must pass against both.

This is a service-extraction PR, not a cutover PR.

At completion:

- `apps/backend` remains the production implementation;
- `apps/rag-backend` can run beside it on a separate port/process;
- the new service satisfies the same RAG HTTP fixtures;
- no production traffic is routed to the new service.

## Current architecture

The legacy RAG UI currently depends on two routes hosted inside the main backend:

- `POST /rag-chat`
- `GET /audit-logs`

Those routes are now security-hardened and protected by the administrator boundary.

RAG chat orchestration already has several separable pieces:

1. request validation and authorization;
2. multi-query generation;
3. embedding generation;
4. hybrid PostgreSQL retrieval;
5. deduplication;
6. reranking;
7. answer generation;
8. debug evaluation;
9. audit-event construction and persistence;
10. Redis-backed response caching.

PR 3 has already introduced a dedicated read-only RAG knowledge repository boundary and moved the hybrid retrieval SQL behind `RagKnowledgeRepository` / `PostgresRagKnowledgeRepository`.

This substantially reduces the persistence coupling that previously prevented RAG from becoming a separate service.

However, the RAG runtime still executes from inside `apps/backend` and uses backend-owned:

- application modules;
- provider adapters;
- Redis configuration;
- OpenAI configuration;
- prompt loading;
- audit persistence;
- middleware;
- dependency factories;
- application startup.

PR 4 creates a second independently runnable implementation while deliberately retaining the first implementation until a later routing/cutover PR.

## Required implementation

### 1. Create the new application skeleton

Add:

`apps/rag-backend`

with an independently executable FastAPI application.

The application must have its own:

- `main.py` or repository-standard equivalent;
- router composition;
- configuration;
- dependency composition;
- startup/lifespan handling;
- logging initialization;
- tests;
- dependency manifest/configuration where required by repository conventions;
- `.env.example`;
- README/run instructions.

It must be possible to start both:

- `apps/backend`
- `apps/rag-backend`

at the same time on different ports.

The RAG service must not depend on the main backend process being alive.

### 2. Expose only the required HTTP surface

The new service must expose:

- `GET /health/live`
- `GET /health/ready`
- `POST /rag-chat`
- `GET /audit-logs`

Do not automatically mount the main backend router.

The new service must not expose unrelated endpoints such as:

- ingestion;
- `/public/assistants/**`;
- Assistant administration;
- administrator management;
- maintenance administration;
- operations dashboards;
- knowledge-source management;
- public widget endpoints.

OpenAPI tests must confirm the intended minimal route surface.

### 3. Implement liveness and readiness

`GET /health/live` must answer based on process liveness only.

A failed external dependency must not cause liveness to fail.

`GET /health/ready` must verify the dependencies required for the RAG service to serve requests safely.

At minimum Codex must determine and test readiness semantics for:

- valid startup configuration;
- PostgreSQL connectivity;
- Redis connectivity when Redis-backed caching/rate limiting requires Redis.

Do not call OpenAI merely to perform routine readiness probes.

Use short bounded health-check timeouts.

Dependency failures must produce the established readiness failure response without leaking connection details.

### 4. Reproduce request correlation

Implement request correlation compatible with the current backend behaviour.

Preserve the existing `X-Request-ID` contract:

- accept a valid caller-supplied request UUID;
- replace malformed/missing IDs with a generated UUID;
- expose the effective ID through request context;
- return it on the response;
- make it available to structured logging.

Do not import the backend correlation middleware implementation.

### 5. Implement explicit CORS/origin policy

The RAG service must have its own explicit trusted-origin configuration.

Do not use:

- `allow_origins=["*"]` with credentials;
- wildcard production origins;
- backend configuration imports.

The configured origin policy must be compatible with the protected RAG UI.

Test:

- configured allowed origin;
- untrusted origin;
- preflight behaviour;
- credentialed requests where required;
- production startup/configuration validation.

### 6. Preserve the protected RAG boundary

Both RAG endpoints must retain the authorization guarantees established by PR 2.

At minimum:

- anonymous callers cannot access `/rag-chat`;
- anonymous callers cannot access `/audit-logs`;
- an authenticated caller cannot choose an arbitrary role and use it to retrieve another role's data;
- permitted roles are derived server-side;
- audit history remains administrator-protected;
- cross-role retrieval remains denied.

Do not trust the submitted `user_role` field as authorization input.

If the request field remains in the frozen transport contract for compatibility, treat it according to the currently frozen behaviour while deriving effective authorization server-side.

The new service does not need to expose administrator login or administrator-management routes merely to satisfy this requirement.

Use the narrowest service-owned session/policy implementation compatible with the existing protected boundary.

### 7. Preserve request and message bounds

Reproduce the current bounded RAG request behaviour.

Include:

- maximum request-body size;
- maximum message size;
- bounded audit-log `limit`;
- existing validation semantics required by the frozen contract.

Oversized requests must be rejected before expensive provider/database work.

Do not silently truncate user input.

### 8. Implement service-level rate limiting

Apply the existing frozen rate limits to:

- `POST /rag-chat`
- `GET /audit-logs`

Keep rate limiting isolated from the main backend process.

The RAG service must own its own limiter configuration/state.

If Redis is used for distributed rate-limit state, use the RAG service's Redis configuration rather than importing or implicitly sharing the main backend's configured client.

Tests must be deterministic and isolate rate-limit state between cases.

### 9. Add a whole-request timeout

Apply a bounded timeout to RAG requests so a stalled dependency cannot occupy a request indefinitely.

The timeout must cover the complete application request, including:

- query generation;
- embeddings;
- retrieval;
- reranking;
- answer generation;
- evaluation;
- cache operations;
- audit persistence where performed synchronously.

Return a stable non-sensitive timeout response.

Do not leave partially written audit/cache state where the current architecture expects atomic completion.

Cancellation must propagate to provider/database work where supported.

### 10. Add explicit provider timeouts

Every OpenAI/provider-backed call used by `rag-backend` must use an explicit bounded timeout.

This includes applicable calls for:

- query generation;
- embeddings;
- reranking;
- answer generation;
- evaluation.

Do not depend on an SDK's unbounded/default timeout.

Provider timeout configuration must belong to `apps/rag-backend`.

Test timeout mapping using provider test doubles, not live OpenAI calls.

### 11. Give the service independent OpenAI configuration

`apps/rag-backend` must own its AI/provider configuration.

It must not import:

`apps/backend/core/config.py`

or the backend's provider factory.

Codex must establish explicit service-owned settings for at least:

- provider;
- API key;
- chat/generation model;
- embedding model;
- provider request timeout;
- retry count where retained.

Use an explicit RAG-service configuration namespace if required to allow the two processes to be configured independently in the same deployment environment.

Document every environment variable.

Do not hard-code credentials.

### 12. Give the service independent Redis configuration

The RAG service must own its Redis configuration and client lifecycle.

It must be possible to configure:

- backend Redis;
- RAG backend Redis

independently.

Preserve existing RAG cache semantics, including where applicable:

- cache key generation;
- TTL;
- serialization;
- cache-hit metrics;
- disabled-cache behaviour;
- safe failure handling.

Prevent accidental key collisions between the two services if both point at the same physical Redis instance during migration.

Use either:

- an explicit service namespace; or
- a separately configured Redis database/URL;

according to the repository's established Redis patterns.

### 13. Use the explicit RAG persistence contract

The new service must implement/use the PR 3 RAG knowledge repository contract.

Reproduce the existing application-owned contract and PostgreSQL implementation within the new service, or move it to a genuinely neutral Python package only if the repository already has an established shared-Python-package mechanism.

The new service's production code must not import:

`apps/backend/assistant/...`

The hybrid query must preserve:

- Assistant isolation;
- document Assistant isolation;
- enabled retrieval-state filtering;
- role filtering in SQL;
- pgvector similarity;
- PostgreSQL full-text ranking;
- configured vector/keyword weighting;
- candidate bounds;
- result limits;
- ordering;
- application maximum-distance behaviour.

Do not redesign retrieval.

### 14. Reimplement multi-query generation

Move/reimplement the legacy RAG multi-query generation inside the service.

Preserve:

- number of generated variants;
- inclusion/exclusion of the original query;
- ordering;
- parsing behaviour;
- fallback behaviour;
- provider failure behaviour;
- cache behaviour if currently cached;
- prompt semantics.

Use the extracted `query_generation.md` prompt.

### 15. Reimplement retrieval orchestration

Implement the existing multi-query retrieval flow inside the service.

Preserve:

- embedding generation;
- repository invocation;
- per-query ordering;
- deduplication;
- maximum-distance filtering;
- result shape;
- downstream metadata required by reranking/evaluation/audit.

Do not import the backend retrieval implementation.

### 16. Reimplement reranking

Move/reimplement the legacy reranking behaviour.

Preserve:

- input ordering assumptions;
- top-K behaviour;
- response parsing;
- fallback/error handling;
- chunk metadata;
- final ordering.

Use the extracted `rerank_chunks.md` prompt.

Provider failures must map safely.

### 17. Reimplement answer generation

Move/reimplement the legacy RAG answer-generation behaviour.

Preserve the frozen output contract:

- `reply.answer`
- `reply.source_ids`
- `sources`
- ordering
- empty-context behaviour

Use the extracted `answer_system.md` prompt.

Do not alter the fallback answer or citation semantics in this PR.

### 18. Extract the three RAG prompts

The new service must own exact service-local copies of:

- `query_generation.md`
- `rerank_chunks.md`
- `answer_system.md`

Add parity tests that prevent accidental prompt-content drift during extraction.

Do not make the new service load prompts from `apps/backend/prompts`.

### 19. Reimplement debug evaluation

Move/reimplement the evaluation required by the legacy `/rag-chat` response and audit history.

Preserve the existing structure, including the fields frozen by the HTTP contract.

Do not turn evaluation into a new externally configurable feature.

Do not expose additional internal provider/prompt details.

### 20. Reimplement RAG audit persistence

Add a service-local RAG audit repository.

Preserve:

- persisted fields;
- serialization;
- newest-first ordering;
- default limit;
- maximum limit;
- complete legacy debug payload;
- evaluation data where currently preserved.

`GET /audit-logs` must return the same externally observable structure as the existing backend.

Audit/debug responses must retain:

`Cache-Control: no-store`

Use explicit least-privilege database permissions.

Do not give the RAG service broad ingestion/admin database writes merely because audit insertion requires write access.

### 21. Preserve safe errors

The RAG service must map unexpected failures to stable non-sensitive responses.

Never return:

- raw exception strings;
- stack traces;
- SQL;
- database URLs;
- Redis URLs;
- credentials;
- OpenAI payloads;
- provider error bodies;
- prompt content;
- document/chunk content not already intentionally part of a successful response.

Preserve useful internal logging using the request correlation ID.

Test provider, database, Redis and unexpected application failures using fictional secrets and assert they do not appear in HTTP responses.

### 22. Keep resource ownership service-local

The new service must create, reuse and close its own:

- database connection/pool resources;
- Redis client;
- OpenAI/provider client;
- other external-resource adapters.

Do not reach into backend dependency caches.

Use FastAPI lifespan or the repository's equivalent established lifecycle pattern.

Verify cleanup on normal shutdown and startup failure.

### 23. Keep `apps/backend` operational

Do not remove or disable the existing implementation.

At completion the following must still work from the original backend:

- `/rag-chat`
- `/audit-logs`
- existing authentication;
- existing RAG retrieval;
- existing cache;
- existing audit logging.

Do not change production route registration.

Changes to backend RAG code should be limited to:

- contract-test parameterization;
- clearly neutral extraction seams;
- fixes strictly required to keep the frozen contract executable against both apps.

Any backend production-code change must preserve its current behaviour.

### 24. Run one frozen contract against both applications

Refactor the existing contract-test structure so the same authoritative fixture/assertion set runs against:

1. `apps/backend`;
2. `apps/rag-backend`.

Do not create two independently maintained "equivalent" contract suites that can drift.

Use one shared contract definition with two application adapters/factories where practical.

The shared contract must continue to cover the current secured behaviour, including:

- authentication;
- server-derived role;
- request validation;
- successful RAG response;
- empty-context response;
- safe errors;
- audit-log shape;
- newest-first ordering;
- default and explicit bounded limits;
- `Cache-Control: no-store`;
- rate limits;
- request-size/message-size protection;
- route registration;
- OpenAPI compatibility where applicable.

If maintenance-mode behaviour is intentionally backend-only and the new RAG service does not own maintenance state, isolate that assertion as an explicit backend-composition test rather than silently changing the shared RAG HTTP contract.

Do not weaken an assertion simply because the new implementation fails it.

### 25. Add implementation-parity tests

Beyond the HTTP contract, add focused parity coverage for behaviour that could drift while HTTP fixtures still pass.

At minimum compare:

- multi-query generation parsing/order;
- retrieval filtering/order;
- deduplication;
- reranking;
- answer parsing;
- empty-context handling;
- audit-event construction;
- evaluation structure;
- Redis cache serialization/key behaviour;
- prompt contents.

Provider-backed tests must use deterministic external-boundary doubles.

Database retrieval tests must use real disposable PostgreSQL where the existing suite already does so.

### 26. Prove process independence

Add an automated or documented smoke test that starts both applications simultaneously on different ports.

Verify:

- both `/health/live` endpoints respond;
- both `/health/ready` endpoints behave according to configured dependencies;
- stopping one process does not stop the other;
- the new service does not require an import path into the backend application;
- the two processes can use independently supplied OpenAI and Redis settings.

Where practical, add a lightweight CI smoke test rather than relying solely on manual execution.

### 27. Prevent cross-application Python imports

Add an architecture test or equivalent static check proving production modules under:

`apps/rag-backend`

do not import implementation modules from:

`apps/backend`

Do not rely solely on code review.

Reject patterns such as:

- `from assistant...` resolving to `apps/backend`;
- `from core...` resolving to `apps/backend`;
- direct filesystem manipulation;
- `sys.path` injection;
- dynamic imports of backend modules.

If shared code is genuinely required, place it in an explicitly shared package/boundary consistent with repository architecture and test that dependency direction.

Do not create a shared production package merely to avoid temporary migration duplication unless there is a clear reusable abstraction.

### 28. Document local and deployment configuration

Add `apps/rag-backend/README.md` documenting:

- purpose of the service;
- that it is not production-routed yet;
- local startup command;
- default/local port;
- health probes;
- required PostgreSQL configuration;
- independent OpenAI configuration;
- independent Redis configuration;
- trusted-origin configuration;
- authentication/session assumptions;
- request/provider timeout settings;
- rate limits;
- request size limits;
- prompt location;
- how to run contract tests against both implementations.

Update the nearest root architecture/repository documentation to identify `apps/rag-backend` as a staged service extraction.

Do not describe the migration as complete until routing is changed in a later PR.

## Acceptance criteria

- [ ] `apps/rag-backend` exists as an independently runnable FastAPI application.
- [ ] The service can run at the same time as `apps/backend`.
- [ ] The service exposes `GET /health/live`.
- [ ] The service exposes `GET /health/ready`.
- [ ] The service exposes `POST /rag-chat`.
- [ ] The service exposes `GET /audit-logs`.
- [ ] The service does not unintentionally expose unrelated main-backend routes.
- [ ] `/rag-chat` remains authentication-protected.
- [ ] `/audit-logs` remains authentication-protected.
- [ ] Effective retrieval roles remain server-derived.
- [ ] Client-supplied role values cannot expand access.
- [ ] Cross-role knowledge retrieval remains impossible.
- [ ] Audit limits remain bounded.
- [ ] Audit/debug responses include `Cache-Control: no-store`.
- [ ] Request-size limits remain enforced.
- [ ] RAG message-size limits remain enforced.
- [ ] Existing RAG rate limits are enforced by the new service.
- [ ] Request correlation is implemented and the effective `X-Request-ID` is returned.
- [ ] CORS uses an explicit trusted-origin policy.
- [ ] Whole-request timeout protection exists.
- [ ] Every applicable provider call uses an explicit timeout.
- [ ] Unexpected errors return stable non-sensitive responses.
- [ ] `rag-backend` owns independent OpenAI configuration.
- [ ] `rag-backend` owns independent Redis configuration.
- [ ] Redis keys/state cannot accidentally collide with backend RAG state when both services share a physical Redis instance.
- [ ] The PR 3 RAG database contract is used for hybrid retrieval.
- [ ] Assistant isolation remains enforced in SQL.
- [ ] Role isolation remains enforced in SQL.
- [ ] Retrieval-state filtering remains enforced.
- [ ] Hybrid ranking semantics remain unchanged.
- [ ] Multi-query generation behaviour remains equivalent.
- [ ] Reranking behaviour remains equivalent.
- [ ] Answer generation behaviour remains equivalent.
- [ ] Debug evaluation behaviour remains equivalent.
- [ ] RAG audit persistence behaviour remains equivalent.
- [ ] `query_generation.md`, `rerank_chunks.md`, and `answer_system.md` are owned by the new service and remain content-equivalent.
- [ ] No production module under `apps/rag-backend` imports an implementation module from `apps/backend`.
- [ ] No `sys.path`/dynamic-import workaround is used to access backend implementation.
- [ ] The same frozen RAG contract fixtures execute against both FastAPI applications.
- [ ] Both implementations pass the frozen `/rag-chat` contract.
- [ ] Both implementations pass the frozen `/audit-logs` contract.
- [ ] Existing backend RAG behaviour remains unchanged.
- [ ] Existing `apps/rag-ui` source is unchanged.
- [ ] Production routing remains unchanged.
- [ ] No frontend API base URL is switched to the new service.
- [ ] No production ingress/DNS/Railway routing is added for `rag-backend`.
- [ ] Documentation explains how to run both services simultaneously.
- [ ] All focused RAG tests pass.
- [ ] All PostgreSQL RAG repository tests pass.
- [ ] Full backend tests pass.
- [ ] Full `rag-backend` tests pass.
- [ ] Ruff passes.
- [ ] Ruff formatting check passes.
- [ ] mypy passes for the affected Python applications.

## Tests to add or update

Add or update coverage for:

### Shared contract

- authoritative frozen RAG contract fixtures runnable against both applications;
- `/rag-chat` request/default/validation behaviour;
- complete successful response shape;
- stable source ordering;
- empty-context result;
- safe provider/database failure mapping;
- authentication;
- server-derived roles;
- rate limits;
- request/message bounds;
- `/audit-logs` complete response shape;
- newest-first ordering;
- default limit;
- explicit valid limit;
- maximum limit;
- malformed/out-of-range limits;
- `Cache-Control: no-store`.

### `apps/rag-backend`

Add focused tests for:

- application route surface;
- liveness;
- readiness with healthy database;
- readiness with unavailable database;
- Redis readiness when required;
- startup configuration validation;
- CORS allowed origin;
- CORS denied origin;
- correlation ID preservation;
- malformed correlation ID replacement;
- request timeout;
- provider timeout;
- safe timeout errors;
- Redis cache hit/miss;
- Redis/cache failure behaviour;
- independent Redis namespace/configuration;
- independent OpenAI configuration;
- provider lifecycle cleanup;
- database lifecycle cleanup;
- Redis lifecycle cleanup;
- prompt parity;
- multi-query generation;
- retrieval;
- deduplication;
- reranking;
- answer generation;
- evaluation;
- audit persistence;
- architecture test prohibiting imports from `apps/backend`.

### PostgreSQL integration

Use disposable PostgreSQL and real migrations/schema setup where established.

Cover:

- Assistant isolation;
- role isolation;
- retrieval-state isolation;
- hybrid vector/keyword ranking;
- result bounds;
- RAG audit writes;
- RAG audit newest-first reads;
- least-privilege service credentials where test infrastructure permits.

Do not use live OpenAI or production Redis/PostgreSQL.

## Verification commands

Codex must first verify the repository's active Python environment/tool invocation and then run the equivalent repository-standard commands below.

```bash
# Repository/diff sanity
git status -sb
git diff --check
git diff --name-only origin/main...HEAD

# Confirm the RAG UI and production routing were not changed.
git diff --exit-code origin/main...HEAD -- apps/rag-ui
git diff --exit-code origin/main...HEAD -- packages/assistant-widget

# Existing frozen contract against the main backend.
cd apps/backend
venv/bin/python -m pytest -q -o addopts= --strict-markers \
  tests/test_legacy_rag_contract.py

# Existing RAG application/retrieval/persistence coverage.
venv/bin/python -m pytest -q -o addopts= --strict-markers \
  tests/test_rag_chat.py \
  tests/test_rag_retrieval.py \
  tests/test_rag_knowledge_repository_postgres.py

cd ../..

# New service focused suite, using the repository-standard Python environment.
python -m pytest -q -o addopts= --strict-markers \
  apps/rag-backend/tests

# Shared frozen contract must explicitly execute against both app factories.
python -m pytest -q -o addopts= --strict-markers \
  <shared-contract-test-path>

# Run all backend tests.
cd apps/backend
venv/bin/python -m pytest -q -o addopts= --strict-markers tests
cd ../..

# Run all new RAG backend tests.
python -m pytest -q -o addopts= --strict-markers \
  apps/rag-backend/tests

# Lint and formatting.
ruff check apps/backend apps/rag-backend
ruff format --check apps/backend apps/rag-backend

# Type checking. Use the repository's configured mypy invocation if narrower targets are required.
mypy apps/rag-backend

# Architecture guard: this should be an automated test/check committed by the PR,
# not merely a manual grep.
python -m pytest -q -o addopts= --strict-markers \
  <rag-backend-import-boundary-test-path>

# Local smoke test:
# Start the existing backend on one port and rag-backend on another using their
# documented production-equivalent entry points, then verify:
#
# curl -fsS http://127.0.0.1:<backend-port>/health/live
# curl -fsS http://127.0.0.1:<rag-backend-port>/health/live
#
# Exercise /health/ready against both with configured disposable dependencies.
```

Before completing the PR, replace the `<...>` placeholders above with the actual committed test paths and use the repository's verified executable/environment commands.

Do not claim verification commands were run unless they were actually executed successfully.