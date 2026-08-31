PR 1B — Freeze the Legacy RAG Contract

Repository state

Expected branch:

1b-freeze-legacy-rag-contract

Base branch:

main

Worktree:

Create a fresh worktree/feature branch from the latest origin/main.

Task specification:

.codex/tasks/1b-freeze-legacy-rag-contract.md

Dependencies:

- PR 1A — Legacy Public API Security Hardening is merged.
- The temporary legacy RAG UI routes remain mounted exactly as retained by PR 1A:
  - POST /rag-chat
  - GET /audit-logs
- apps/rag-ui remains the active consumer of both routes.
- The supported public Assistant endpoint remains:
  - POST /public/assistants/{assistant_slug}/chat

Read first

- AGENTS.md
- apps/backend/AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- .codex/tasks/1a-legacy-public-api-security-hardening.md
- README.md
- apps/backend/README.md
- apps/backend/docs/operations-administration.md

Primary change area

Legacy RAG HTTP contract characterization:

- apps/backend/tests/test_legacy_rag_contract.py
- apps/backend/tests/test_legacy_api_security.py
- apps/backend/assistant/api/rag.py
- apps/backend/assistant/api/audit.py
- apps/backend/assistant/application/rag_chat.py
- apps/backend/assistant/infrastructure/audit.py
- apps/backend/operations/infrastructure/maintenance.py
- apps/backend/docs/legacy-rag-contract.md

Consumer contract references:

- apps/rag-ui/src/services/getRagChat.ts
- apps/rag-ui/src/services/getAuditLogs.ts
- apps/rag-ui/src/App.tsx
- apps/rag-ui/src/components/DisplayDebugHistory.tsx
- apps/rag-ui/src/components/DisplayDebug.tsx
- apps/rag-ui/src/components/DisplayAnswer.tsx
- apps/rag-ui/src/components/DisplaySources.tsx

Canonical implementation examples

- apps/backend/tests/test_legacy_api_security.py
- apps/backend/tests/test_operations_administration_api.py
- apps/backend/tests/test_rag_chat.py
- apps/backend/tests/test_audit.py
- apps/backend/tests/test_public_chat.py

Relevant symbols

- assistant.api.rag.RagChatRequest
- assistant.api.rag.RagChatResponse
- assistant.api.rag.rag_chat_endpoint
- assistant.api.audit.get_logs
- assistant.application.rag_chat.rag_chat
- assistant.application.rag_chat.empty_response
- assistant.application.rag_chat.build_audit_event
- assistant.infrastructure.audit.get_audit_logs
- operations.infrastructure.maintenance.MaintenanceModeMiddleware
- getRagChat
- getAuditLogs
- DebugInstance
- Answer
- EvaluationMetrics
- Metrics
- RetrievedChunk
- RerankedChunk

Expected change surface

Expected:

- add focused HTTP characterization tests for POST /rag-chat
- add focused HTTP characterization tests for GET /audit-logs
- freeze the request defaults, successful response fields, empty-result behaviour and validation errors that apps/rag-ui relies on
- freeze descending audit-log ordering and limit forwarding at the public HTTP boundary
- freeze the existing anonymous access, rate limits and maintenance-mode behaviour
- freeze OpenAPI route presence and the schemas already emitted by the current implementation
- document the temporary legacy contract and its known consumer
- keep implementation changes limited to test seams or contract declarations proven not to alter runtime behaviour
- remove duplicated shallow assertions from broader tests only when the new focused contract suite supersedes them without reducing coverage

No database migration, endpoint migration, authentication change, RAG UI feature change, retrieval change or response redesign is required.

Excluded areas

Do not:

- remove, rename, redirect or alias POST /rag-chat
- remove, rename, redirect or alias GET /audit-logs
- add authentication or authorization to either route
- add an /admin/** replacement for either route
- change route registration, URL paths, HTTP methods, status codes, headers, rate limits or maintenance treatment
- change request field names, defaults or currently accepted values
- change response field names, nesting, value types or ordering
- tighten validation, reject currently accepted extra fields or coerce values differently
- add pagination, filtering, cursors, envelopes or metadata to GET /audit-logs
- change the audit-log default limit or database query ordering
- expose additional audit data
- change apps/rag-ui source, requests, rendering, authentication or tests
- redesign retrieval, ranking, caching, evaluation, prompting, citations or audit persistence
- replace dictionary payloads with new domain or transport models unless equivalence is demonstrated for every frozen case and OpenAPI remains compatible
- modify POST /public/assistants/{assistant_slug}/chat
- introduce a database migration, configuration key, dependency or generated client
- describe these routes as supported long-term public APIs

Unknowns Codex must verify

Before changing production code, verify:

1. PR 1A is present on the selected base and the retired /assistant/chat, /chunks and raw-text /ingest routes remain absent.
2. apps/rag-ui is still the only active in-repository consumer of /rag-chat and /audit-logs.
3. The exact request and response fields read by the RAG UI, including nested evaluation, source, metric and debug-chunk fields.
4. The current Pydantic version's observable handling of omitted user_role, malformed bodies, extra fields and null values; characterize existing behaviour instead of assuming it.
5. The current default audit limit, explicit limit forwarding, descending ordering, empty-list result and invalid-limit behaviour.
6. The current anonymous access, SlowAPI limits and maintenance-mode behaviour for both endpoints. /rag-chat is maintenance-gated; /audit-logs is not currently classified as public Assistant traffic.
7. Whether a realistic HTTP test can exercise audit ordering and limit behaviour through a disposable database. Prefer that over mocking the controller-owned application call. If the repository's test infrastructure cannot support it, document the boundary and use the narrowest established substitute.
8. Whether adding explicit response models would reject, drop, coerce or reshape any currently returned value. Do not add them if runtime or OpenAPI equivalence cannot be proved.
9. The focused contract tests fail for realistic drift such as renamed fields, changed defaults, removed route registration, reversed audit ordering, lost maintenance gating or altered limits.
10. apps/rag-ui has no diff against origin/main after the work.

---

Objective

Turn the two temporary RAG UI dependencies retained by PR 1A into an explicit, executable legacy contract before any later retirement or migration work begins.

PR 1B must make accidental drift visible without changing behaviour. It records what the existing RAG UI sends, what it reads, and the operational behaviour surrounding both endpoints:

- POST /rag-chat
- GET /audit-logs

The freeze is temporary and consumer-specific. It protects the current apps/rag-ui integration while that application exists; it does not promote either route into the supported public Assistant API.

The supported anonymous Assistant boundary remains:

POST /public/assistants/{assistant_slug}/chat

---

Current architecture

RAG chat request

apps/rag-ui/src/services/getRagChat.ts sends:

- POST /rag-chat
- Content-Type: application/json
- Accept: application/json
- a JSON object containing:
  - message
  - user_role
- a 30-second browser-side abort signal

The backend currently validates the body with RagChatRequest. message is required and user_role defaults to "user" when omitted. The route is anonymous, rate-limited to 20 requests per minute and handled by maintenance middleware as legacy public Assistant traffic.

RAG chat response

apps/rag-ui reads these top-level fields:

- reply
- sources
- evaluation

The UI reads these nested values:

- reply.answer
- reply.source_ids
- sources[].id
- sources[].text
- evaluation.metrics.groundedness_score
- evaluation.metrics.verified_sentences
- evaluation.metrics.total_sentences
- evaluation.metrics.citation_count

When retrieval finds no context, the existing application returns a successful response with its current fallback answer, an empty source_ids list, an empty sources list and zero-valued evaluation metrics. This is observable legacy behaviour and must be characterized without rewriting retrieval.

Audit-log request

apps/rag-ui/src/services/getAuditLogs.ts sends:

- GET /audit-logs
- Content-Type: application/json
- no authentication credentials
- no limit query parameter
- a 30-second browser-side abort signal

The backend currently applies the configured AUDIT_LOG_LIMIT default, forwards the effective limit to persistence, rate-limits the route to 60 requests per minute and returns audit rows in descending id order. Unlike /rag-chat, /audit-logs is not currently maintenance-gated.

Audit-log response

The route returns a top-level JSON array. The RAG UI expects the newest item first and reads:

- id
- timestamp
- user_role
- question
- reply
- metrics
- queries
- retrieved_chunks
- reranked_chunks

The current persistence adapter also returns evaluation. The contract documentation and tests must record whether that field is required by the consumer or merely preserved legacy output; it must not be removed or reshaped in this PR.

Each debug item contains nested fields currently rendered by the UI:

- metrics.retrieval_time
- metrics.llm_time
- metrics.total_time
- metrics.cache_hit
- metrics.input_tokens
- metrics.output_tokens
- retrieved_chunks[].rank
- retrieved_chunks[].id
- retrieved_chunks[].doc_id
- retrieved_chunks[].distance
- retrieved_chunks[].hybrid_score
- retrieved_chunks[].text_snippet
- retrieved_chunks[].keyword_match
- reranked_chunks[] with the same chunk fields

The existing route has no explicit response model. Its serialized database values therefore form an implicit legacy contract. PR 1B freezes the behaviour actually exercised by the RAG UI; it must not infer stricter validation that the current route does not provide.

---

Required implementation

1. Establish a dedicated contract suite

Add apps/backend/tests/test_legacy_rag_contract.py, or an equivalently focused test module consistent with the backend suite.

Exercise both endpoints through FastAPI TestClient and the real router/middleware composition. Assert response status and complete semantic fields, not only route presence or a mocked call.

Use representative fictional payloads containing every field read by apps/rag-ui. Keep fixtures local and clear enough to act as executable contract examples.

Do not use broad snapshots. Assertions must identify which request, response or operational rule drifted.

2. Freeze POST /rag-chat request behaviour

Characterize at least:

- a valid request containing message and user_role
- omission of user_role and the current "user" default
- missing message
- malformed JSON
- the current handling of empty strings, nulls, wrong types and extra fields as verified against the selected base

Tests must prove the values reaching the existing application boundary and the externally visible validation responses. They must not change validation to match a preferred design.

3. Freeze POST /rag-chat successful responses

Characterize a successful response containing:

- reply.answer
- reply.source_ids with stable list ordering
- sources with id and text in stable list ordering
- evaluation and its current metrics

Use a response containing multiple source IDs and sources so the suite detects dropped fields and ordering drift.

Where the HTTP test replaces provider-backed RAG orchestration, replace only that external/application seam and return a realistic complete payload. Existing application tests remain responsible for retrieval, reranking, LLM, caching and evaluation logic.

4. Freeze POST /rag-chat empty-context behaviour

Exercise or faithfully expose the current no-context result through the HTTP boundary and assert:

- HTTP 200
- the current fallback answer text
- reply.source_ids is []
- sources is []
- evaluation is present with the current zero-result structure

Do not improve the copy or convert this case into an error in PR 1B.

5. Freeze POST /rag-chat failure mapping

Characterize the current visible response when existing RAG orchestration raises an exception, including status and JSON detail shape.

Use a fictional non-sensitive failure. Do not leak a real credential, connection string, provider payload, prompt or document content into the fixture or assertions.

This test records current behaviour only. Any separate effort to make legacy errors safer must have its own scope and migration decision.

6. Freeze GET /audit-logs response behaviour

Characterize:

- a successful top-level array response
- a representative complete audit item with every field read by apps/rag-ui
- multiple items returned newest first
- an empty database result returning [] with HTTP 200
- preservation of the current evaluation field

Prefer a realistic repository/database path when supported by existing fixtures. If the persistence boundary must be substituted, separately cover its ORDER BY id DESC and LIMIT semantics in its existing focused infrastructure tests.

7. Freeze GET /audit-logs limit behaviour

Characterize:

- omission of limit uses AUDIT_LOG_LIMIT
- an explicit valid limit is forwarded unchanged
- the current externally visible behaviour for zero, negative, repeated, malformed and excessively large limit values, as verified on the selected base

Do not add clamping or stricter validation in this PR.

8. Freeze anonymous access and rate limits

Prove that both routes retain their current anonymous behaviour: a request without administrator session, API key or other credential reaches the route subject to its normal validation and dependencies.

Prove the current limits through the closest stable behavioural boundary:

- POST /rag-chat — 20/minute
- GET /audit-logs — 60/minute

Keep rate-limit tests isolated from global limiter state and independent of execution order. Do not replace behavioural evidence with assertions against private decorator internals.

9. Freeze maintenance behaviour

Characterize the intentional asymmetry retained by PR 1A:

- /rag-chat is blocked with the existing 503 maintenance response while maintenance mode is enabled
- /audit-logs retains its current non-maintenance-gated behaviour
- maintenance-disabled requests proceed normally
- the existing correlation and CORS middleware behaviour remains observable where current broader tests already establish it

Do not add /audit-logs to maintenance classification and do not remove /rag-chat from it.

10. Freeze route registration and OpenAPI

Assert that:

- /rag-chat remains documented only with POST
- /audit-logs remains documented only with GET
- neither administrator replacement route exists
- the retired /assistant/chat, /chunks and raw-text /ingest routes remain absent
- the current request, response and validation schemas emitted by OpenAPI remain compatible with the selected base

Prefer semantic assertions for operation methods, required fields, defaults and response shape. Do not commit a whole-document OpenAPI snapshot.

11. Document the temporary contract

Add apps/backend/docs/legacy-rag-contract.md and link it from the nearest relevant backend/root documentation.

Document:

- the two route methods and paths
- that both routes are anonymous temporary exceptions for apps/rag-ui
- request fields and defaults
- successful and empty-result response examples
- audit item fields and newest-first ordering
- default and explicit limit behaviour
- current rate limits
- current maintenance behaviour
- validation and failure behaviour
- the supported public Assistant endpoint that new consumers must use
- the rule that retirement or migration must update the RAG UI and backend routes together

Do not call the freeze a long-term compatibility promise. State that no new consumer should integrate with these legacy endpoints.

12. Keep production behaviour unchanged

Production-code edits are not expected unless required to expose an existing contract safely to tests or to make the existing OpenAPI declaration accurately describe behaviour without changing it.

If production code is changed:

- prove before/after equivalence for every frozen case
- keep route registration, orchestration, persistence and middleware behaviour unchanged
- do not move business logic into API models or tests
- do not add compatibility adapters for behaviour that did not previously exist

13. Preserve the RAG UI exactly

Do not edit any file under apps/rag-ui.

At completion, verify that apps/rag-ui has no diff against origin/main. The purpose of PR 1B is to freeze the backend boundary consumed by that application, not to alter the consumer.

---

Acceptance criteria

- [ ] A focused backend contract suite covers POST /rag-chat and GET /audit-logs through their public HTTP boundaries.
- [ ] POST /rag-chat request field names, required fields, user_role default and verified validation behaviour are characterized.
- [ ] POST /rag-chat successful reply, source and evaluation fields consumed by apps/rag-ui are asserted semantically.
- [ ] POST /rag-chat no-context behaviour is frozen, including HTTP 200, fallback reply, empty sources and zero-result evaluation.
- [ ] POST /rag-chat current failure mapping is characterized with non-sensitive fixture data.
- [ ] GET /audit-logs returns a top-level array whose complete representative items preserve every field consumed by apps/rag-ui.
- [ ] GET /audit-logs empty-result and newest-first ordering behaviour are covered.
- [ ] The configured default audit limit, explicit limit forwarding and verified invalid-limit behaviour are covered.
- [ ] Anonymous access remains unchanged for both routes.
- [ ] The existing 20/minute /rag-chat and 60/minute /audit-logs rate limits are covered without order-dependent global state.
- [ ] /rag-chat remains maintenance-gated with the current 503 contract.
- [ ] /audit-logs remains outside maintenance gating.
- [ ] OpenAPI semantically preserves both legacy operations and their current request/default declarations without a brittle whole-document snapshot.
- [ ] No /admin/** replacement for either route is introduced.
- [ ] /assistant/chat, /chunks and raw-text /ingest remain absent.
- [ ] Documentation records the frozen temporary contract and warns new consumers not to adopt it.
- [ ] No files under apps/rag-ui differ from origin/main.
- [ ] No retrieval, ranking, caching, prompting, evaluation, audit persistence or public Assistant behaviour changes.
- [ ] No migration, new configuration, dependency or generated client is introduced.

Tests to add or update

- Add apps/backend/tests/test_legacy_rag_contract.py for focused HTTP characterization.
- Update apps/backend/tests/test_legacy_api_security.py only to remove assertions made redundant by the dedicated suite or to retain its route-removal security focus.
- Update apps/backend/tests/test_operations_administration_api.py only if maintenance assertions are moved without reducing its operations-level coverage.
- Update apps/backend/tests/test_audit.py only when realistic persistence coverage is needed for newest-first and limit semantics.
- Update apps/backend/tests/test_rag_chat.py only when the no-context or failure case cannot be exercised at the HTTP boundary without duplicating application logic.
- Do not add or update apps/rag-ui tests.

Important cases:

- valid /rag-chat body with explicit user_role
- omitted user_role default
- missing and malformed /rag-chat bodies
- verified boundary values and extra-field handling
- complete multi-source successful chat response
- empty-context successful response
- existing chat exception mapping
- complete multi-row audit response newest first
- empty audit response
- default, explicit and invalid audit limits
- anonymous access
- rate-limit exhaustion and isolation
- maintenance enabled and disabled
- semantic OpenAPI route and schema declarations
- continued absence of removed and invented routes

Verification commands

```bash
# Confirm the prerequisite and the focused diff.
git status -sb
git log -1 --oneline origin/main
git diff --check origin/main...HEAD
git diff --exit-code origin/main...HEAD -- apps/rag-ui

# Focused contract and directly affected backend suites.
venv/bin/python -m pytest -q -o "addopts=" --strict-markers \
  apps/backend/tests/test_legacy_rag_contract.py \
  apps/backend/tests/test_legacy_api_security.py \
  apps/backend/tests/test_operations_administration_api.py \
  apps/backend/tests/test_rag_chat.py \
  apps/backend/tests/test_audit.py

# Broader backend verification.
venv/bin/python -m pytest -q
venv/bin/ruff check apps/backend
venv/bin/ruff format --check apps/backend

# The consumer must remain buildable without source changes.
npm run lint --workspace @ai-discovery-assistant/rag-ui
npm run build --workspace @ai-discovery-assistant/rag-ui
```
