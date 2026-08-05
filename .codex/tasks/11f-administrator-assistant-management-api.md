PR 11F — Administrator Assistant Management API

Repository state

Expected branch:

feature/11f-administrator-assistant-management-api

Base branch:

main

Worktree:

Use the backend worktree. Confirm that the worktree is clean and checked out to the expected branch before making changes.

Dependencies:

- PR 11A — Assistant Domain and Knowledge Scoping
- PR 11E — Administrator Authentication API
- PR 11B — Redmoor Knowledge Source Management
- PR 11B.1 — Knowledge Source Management Hardening

All dependencies are expected to be present on main.

Do not implement this work on top of an unmerged feature branch.

Read first

- AGENTS.md
- apps/backend/AGENTS.md
- docs/architecture/repository-map.md
- docs/architecture/dependency-rules.md
- apps/backend/README.md
- Existing administrator authentication API implementation
- Existing assistant domain and repository implementation
- Existing knowledge-source administration API implementation
- Existing public assistant chat API implementation
- Existing database migration conventions
- Existing API error, pagination, logging and metrics conventions

Primary change area

- apps/backend/assistant/domain/
- apps/backend/assistant/application/
- apps/backend/assistant/api/
- apps/backend/assistant/schemas/
- apps/backend/assistant/infrastructure/repositories/
- apps/backend/assistant/infrastructure/database/ or the repository’s canonical migration location
- apps/backend/tests/
- Backend API and operational documentation

Canonical implementation examples

Use existing implementations rather than creating parallel conventions.

Inspect and follow:

- apps/backend/assistant/domain/assistant.py
- apps/backend/assistant/domain/assistant_repository.py
- apps/backend/assistant/infrastructure/repositories/assistant.py
- apps/backend/assistant/api/knowledge_sources.py
- Administrator authentication dependencies and route protection
- Existing list/detail API schemas
- Existing PostgreSQL repository implementations
- Existing API exception mapping
- Existing structured logging and Prometheus metrics
- Existing migration and PostgreSQL integration tests

The knowledge-source administration implementation should be treated as the primary example for:

- authenticated administrator routes;
- dependency injection;
- application service boundaries;
- request and response schemas;
- API error mapping;
- pagination;
- structured lifecycle logging;
- metrics;
- PostgreSQL integration tests.

Do not copy known weaknesses or introduce assistant-specific behaviour into the knowledge-source service.

Relevant symbols

Existing symbols include, but are not limited to:

- Assistant
- AssistantStatus
- AssistantVisibility
- AssistantRepository
- AssistantNotFound
- REDMOOR_ASSISTANT_ID
- REDMOOR_ASSISTANT_SLUG
- administrator authentication dependencies;
- knowledge-source repository and service abstractions;
- public chat assistant resolution.

Codex must inspect the repository and identify the exact current names and locations before changing them.

Expected change surface

Expected work includes:

- extending the assistant domain where necessary;
- extending the assistant repository contract;
- extending the PostgreSQL assistant repository;
- adding an assistant administration application service;
- adding administrator request and response schemas;
- adding protected administrator assistant endpoints;
- adding database constraints or migrations only where required;
- registering routes and OpenAPI documentation;
- adding structured logging and metrics;
- adding unit, API, repository and PostgreSQL integration tests;
- updating backend API documentation.

Changes to existing public chat and knowledge-source behaviour should be limited to compatibility adaptations required by the extended repository contract.

Excluded areas

Do not modify:

- apps/admin frontend functionality;
- the public assistant widget;
- widget package exports;
- npm release automation;
- ingestion architecture;
- chunking or embedding behaviour;
- evaluation framework behaviour;
- administrator account management;
- user profile management;
- multi-tenant organisations;
- role-based permissions beyond the existing administrator authentication model;
- white-label branding;
- assistant analytics;
- assistant system prompts or model configuration;
- file or PDF ingestion;
- scheduled ingestion;
- multi-page crawling;
- bulk assistant import;
- permanent hard deletion of assistant-owned knowledge.

Do not add a new framework, ORM, validation library or service abstraction where the repository already has a suitable established approach.

Unknowns Codex must verify

Before implementation, verify:

1. The exact assistant table schema and migration history.
2. Whether assistant slugs currently have a database uniqueness constraint.
3. Whether assistant names are currently required to be unique.
4. How repository pagination is implemented elsewhere.
5. How administrator session authentication is applied to protected routes.
6. How API conflict, validation and not-found errors are represented.
7. How knowledge sources are counted or queried by assistant.
8. Whether documents can exist for an assistant without a knowledge source.
9. Whether public chat already rejects inactive or private assistants.
10. Whether timestamps are generated by the application or database.
11. Whether existing update operations use row locking, version fields or timestamp-based concurrency controls.
12. Whether the seeded Redmoor assistant is created by migration, bootstrap code or application startup.
13. Whether deleting assistant rows would cascade into documents, chunks, jobs or knowledge sources.
14. Whether the current metrics registry provides suitable reusable helpers.

Resolve these questions from the repository. Do not guess.

⸻

Objective

Add an authenticated administrator API for managing assistant records.

Administrators must be able to:

- list assistants;
- retrieve an assistant;
- create an assistant;
- update an assistant’s mutable properties;
- activate or deactivate an assistant;
- change an assistant’s visibility;
- safely request deletion of an unused assistant.

The implementation must preserve assistant isolation and must not allow an assistant operation to alter another assistant’s knowledge, documents, ingestion jobs or public-chat behaviour.

The API will become the backend contract for the administrator application introduced in PR 13A.

⸻

Current architecture

The repository already contains an Assistant domain entity with:

- UUID identifier;
- route-safe slug;
- display name;
- active or inactive status;
- public or private visibility;
- timezone-aware creation and update timestamps.

The repository also contains a seeded Redmoor assistant and assistant-scoped relationships for documents, chunks, retrieval and knowledge sources.

The public chat API resolves an assistant and uses assistant-scoped retrieval.

The knowledge-source administrator API manages knowledge under a specific assistant.

The current assistant repository contract appears limited to lookup by ID and slug. This PR must extend that capability without bypassing the existing domain and repository boundaries.

Administrator authentication already exists and uses HTTP-only cookie sessions. All routes introduced by this PR must use the existing administrator authentication mechanism.

⸻

Required implementation

1. Assistant domain behaviour

Preserve the existing Assistant entity and enum values unless repository evidence requires a compatible extension.

Define explicit domain behaviour for assistant mutations rather than allowing arbitrary field replacement.

At minimum, support:

- renaming an assistant;
- activating an assistant;
- deactivating an assistant;
- changing visibility;
- updating the modification timestamp.

The assistant slug is immutable after creation.

This avoids breaking:

- public embed configuration;
- bookmarked API URLs;
- external integrations;
- deployment environment variables;
- future analytics keys.

Do not support slug changes in this PR.

Validate assistant names using explicit bounded rules:

- trim leading and trailing whitespace;
- reject blank names;
- impose a reasonable maximum length consistent with repository conventions;
- reject control characters;
- preserve ordinary punctuation and Unicode names.

Continue using the existing lowercase route-safe slug format.

A slug must:

- contain lowercase ASCII letters, numbers and single hyphens;
- not begin or end with a hyphen;
- not contain consecutive hyphens;
- have a bounded length;
- be unique across assistants.

Do not automatically derive a different slug after a conflict. Return a deterministic conflict response.

Assistant names do not need to be unique unless existing repository rules already require uniqueness.

2. Repository contract

Extend AssistantRepository with the minimum operations required by the application service.

Expected capabilities:

- create an assistant;
- list assistants with bounded pagination;
- count assistants for pagination metadata if required by repository conventions;
- retrieve by ID;
- retrieve by slug;
- update an assistant;
- determine whether an assistant owns dependent records;
- safely delete an assistant when permitted.

Repository methods must use typed domain values rather than unstructured dictionaries.

Add explicit repository exceptions for:

- assistant not found;
- duplicate assistant slug;
- concurrent update conflict, if applicable;
- assistant deletion blocked by dependencies.

Map database constraint failures to domain or application exceptions. Do not expose driver exceptions through the API.

Use direct SQL lookups for uniqueness and dependency checks. Do not scan paginated lists in application code.

3. Concurrency and lost-update protection

Assistant updates must not silently overwrite a concurrent administrator update.

Use the repository’s established concurrency pattern where one exists.

If none exists, implement an explicit compare-and-set update using the current updated_at value or another minimal version token.

The update request must carry the concurrency token returned by the detail endpoint.

A stale update must return a deterministic conflict response and must not modify the assistant.

Do not hold a database transaction open across HTTP or external calls.

4. Application service

Introduce a dedicated assistant administration application service.

The API layer must not contain business rules or direct SQL.

Expected service operations:

- list_assistants
- get_assistant
- create_assistant
- update_assistant
- delete_assistant

Separate commands and results where that matches existing project conventions.

The service must:

- validate commands;
- create server-owned identifiers and timestamps;
- enforce immutable slug behaviour;
- handle idempotency where specified;
- invoke repository operations;
- map repository exceptions to application errors;
- emit lifecycle metrics and structured logs only after authoritative outcomes.

5. Administrator API routes

Add a protected assistant administration router under the existing administrator API namespace.

Expected routes:

List assistants

GET /admin/assistants

Support bounded pagination using the repository’s established query parameter and response conventions.

Default ordering:

1. creation timestamp ascending or descending according to existing list conventions;
2. assistant ID as a stable tie-breaker.

The ordering must be deterministic.

Optional filters may include:

- status;
- visibility.

Do not add free-text search unless it already exists as a standard repository pattern.

The response should include:

- assistant summaries;
- pagination metadata;
- status;
- visibility;
- created and updated timestamps.

Get assistant

GET /admin/assistants/{assistant_id}

Return:

- ID;
- slug;
- name;
- status;
- visibility;
- created timestamp;
- updated timestamp;
- concurrency token;
- a small dependency summary needed by the admin interface.

The dependency summary should be calculated efficiently and may include:

- knowledge-source count;
- whether deletion is currently allowed.

Do not include document content, chunks, embeddings or administrator-sensitive internals.

Create assistant

POST /admin/assistants

Accept:

- slug;
- name;
- status;
- visibility.

Use safe defaults where fields are omitted:

- status: inactive;
- visibility: private.

This ensures a newly created assistant does not become publicly usable accidentally.

Return 201 Created.

The response should include the canonical assistant representation and a Location header if consistent with repository conventions.

Duplicate slug creation must return 409 Conflict.

Malformed or invalid input must return the repository’s standard validation response.

Update assistant

PATCH /admin/assistants/{assistant_id}

Mutable fields:

- name;
- status;
- visibility.

Do not accept:

- ID;
- slug;
- creation timestamp;
- update timestamp except as a concurrency token.

Use partial-update semantics.

Reject an empty patch rather than treating it as a successful mutation.

Return the updated canonical assistant representation.

A stale concurrency token must return 409 Conflict.

Delete assistant

DELETE /admin/assistants/{assistant_id}

Deletion must be deliberately restrictive.

Deletion is allowed only when the assistant has no dependent:

- knowledge sources;
- documents;
- chunks;
- ingestion jobs;
- other persisted assistant-owned records discovered during repository inspection.

The dependency check and deletion must occur transactionally so that a dependent record cannot be inserted between the check and delete.

The seeded Redmoor assistant must not be deletable.

Attempting to delete the Redmoor assistant must return a deterministic conflict response.

Attempting to delete an assistant with dependencies must return 409 Conflict with a safe machine-readable error code.

Do not cascade-delete assistant knowledge.

Return 204 No Content after successful deletion.

Deletion of a missing assistant should follow existing API conventions. Prefer 404 Not Found unless the project consistently implements idempotent delete semantics.

6. Public behaviour compatibility

Verify that public chat resolves only assistants that are both:

- active;
- public.

If this is already correctly enforced, preserve the implementation and add regression coverage.

If it is not enforced, add the smallest compatible correction required so:

- inactive assistants cannot be used through public chat;
- private assistants cannot be used through public chat;
- responses do not disclose whether a non-public assistant exists.

Use the public API’s existing safe not-found or unavailable response.

Do not alter authenticated internal RAG endpoints unless necessary.

7. Knowledge-source compatibility

Knowledge-source endpoints must continue to:

- require an existing assistant;
- remain scoped to the requested assistant;
- prevent cross-assistant access;
- operate for inactive or private assistants when used by an authenticated administrator.

Deactivating or making an assistant private must not disable, delete or rewrite its knowledge sources.

Assistant status and visibility control public availability, not knowledge persistence.

8. Idempotency

Support creation idempotency if the existing administrator write APIs already provide an idempotency-key convention.

When an idempotency key is supplied:

- the key must be scoped to the authenticated administrative operation;
- replaying the same key with the same canonical payload must return the original result;
- replaying the key with a different payload must return a conflict;
- concurrent requests with the same key must create at most one assistant;
- an idempotency key must not bypass slug uniqueness.

If no established administrator idempotency mechanism exists, do not invent a broad generic framework in this PR. Rely on the unique slug constraint and deterministic conflict handling, and document the decision.

Update operations must be safe to retry when the requested state is already applied and the supplied concurrency token remains valid according to the chosen concurrency model.

9. Authentication and security

Every new route must require the existing authenticated administrator session.

Do not add API-key authentication to these routes.

Use the existing CSRF or same-site cookie protections. If write-route CSRF protection is not currently present, identify and report the gap, but do not create a competing authentication framework inside this PR.

Never log:

- session cookies;
- authentication tokens;
- request headers;
- complete request bodies;
- document content;
- assistant knowledge content.

Validate UUID path parameters through the established schema mechanism.

Use safe generic messages for public-facing errors and stable machine-readable error codes for the admin client.

10. Database changes

Add a migration only if required.

Potential required changes include:

- enforcing unique assistant slug at database level;
- adding a concurrency/version column if timestamp comparison is not suitable;
- adding an index supporting deterministic assistant listing.

Migrations must be:

- reversible where practical;
- safe for existing data;
- idempotent according to repository migration conventions;
- covered by migration tests;
- compatible with the seeded Redmoor assistant.

Do not rebuild or replace the assistant table unnecessarily.

11. Logging and metrics

Emit structured logs for:

- assistant created;
- assistant updated;
- assistant activated;
- assistant deactivated;
- assistant visibility changed;
- assistant deletion blocked;
- assistant deleted;
- duplicate slug conflict;
- concurrent update conflict.

Include only low-risk identifiers and metadata:

- assistant ID;
- slug where allowed by logging policy;
- resulting status;
- resulting visibility;
- administrator ID if the existing auth model exposes a safe identifier;
- request or correlation ID.

Do not log assistant names unless existing policy explicitly permits it.

Add low-cardinality metrics for:

- create outcomes;
- update outcomes;
- delete outcomes;
- conflicts;
- list and detail failures where useful.

Do not use assistant IDs or slugs as metric labels.

Telemetry failure must not change an API result.

12. API documentation

Register the routes in OpenAPI.

Document:

- authentication requirements;
- request and response schemas;
- default inactive/private creation behaviour;
- immutable slug behaviour;
- concurrency token requirements;
- duplicate slug conflict;
- deletion restrictions;
- public availability semantics.

Update the backend README or canonical API documentation.

⸻

Acceptance criteria

- An authenticated administrator can list assistants using bounded deterministic pagination.
- An authenticated administrator can retrieve an assistant by UUID.
- An authenticated administrator can create an assistant.
- New assistants default to inactive and private.
- Assistant slugs are validated and unique at the database level.
- Duplicate slug creation returns a deterministic 409 Conflict.
- Assistant names are validated and normalized without unnecessarily restricting Unicode.
- An authenticated administrator can update name, status and visibility.
- Assistant IDs and slugs cannot be changed.
- Empty patch requests are rejected.
- Concurrent administrator updates cannot silently overwrite one another.
- Stale update requests return a deterministic conflict.
- Inactive assistants are unavailable through public chat.
- Private assistants are unavailable through public chat.
- Public responses do not reveal the existence of private assistants.
- Administrator knowledge-source management remains available for inactive and private assistants.
- Status or visibility changes do not delete or rewrite assistant knowledge.
- The Redmoor assistant cannot be deleted.
- Assistants with dependent records cannot be deleted.
- Dependency checking and deletion are transaction-safe.
- Deletion never cascades into knowledge sources, documents, chunks or ingestion jobs.
- An unused non-Redmoor assistant can be deleted successfully.
- All routes reject unauthenticated requests using the existing authentication contract.
- Repository/database exceptions do not leak through the API.
- Structured logs contain no credentials, cookies, knowledge content or request bodies.
- Metrics use bounded labels.
- OpenAPI documents all routes and expected errors.
- Existing public chat, knowledge-source, ingestion and retrieval tests continue to pass.
- No frontend application behaviour is added in this PR.

⸻

Tests to add or update

Add tests in the repository’s canonical locations.

Domain tests

Cover:

- valid assistant creation;
- invalid slug formats;
- blank name rejection;
- maximum lengths;
- timezone-aware timestamps;
- rename behaviour;
- activation and deactivation;
- visibility changes;
- immutable identity and slug;
- updated timestamp behaviour.

Application service tests

Cover:

- list and detail delegation;
- default inactive/private creation;
- explicit status and visibility creation;
- duplicate slug mapping;
- partial updates;
- empty patch rejection;
- stale concurrency token;
- missing assistant;
- Redmoor deletion prohibition;
- dependency-blocked deletion;
- successful deletion;
- logging and metric outcomes;
- telemetry failure isolation.

Repository tests

Use real PostgreSQL integration tests for:

- assistant insertion;
- unique slug enforcement;
- deterministic pagination;
- status filter;
- visibility filter;
- lookup by ID and slug;
- compare-and-set update success;
- stale compare-and-set update failure;
- dependency summary;
- transactional deletion;
- concurrent dependency insertion versus deletion;
- exception mapping;
- Redmoor record compatibility.

Do not substitute mocks for database constraint and concurrency behaviour.

API tests

Cover:

- unauthenticated rejection for every route;
- list response and pagination;
- detail response;
- unknown UUID;
- invalid UUID;
- create success;
- defaults;
- invalid request validation;
- duplicate slug conflict;
- patch success;
- patching each mutable property;
- immutable-field rejection;
- empty patch;
- stale update;
- delete success;
- Redmoor deletion rejection;
- dependent-assistant deletion rejection;
- safe error bodies;
- OpenAPI registration.

Public API regression tests

Cover:

- active/public assistant accepted;
- inactive/public assistant unavailable;
- active/private assistant unavailable;
- inactive/private assistant unavailable;
- missing and private assistants produce equivalently safe public responses.

Knowledge-source regression tests

Cover:

- administrators can manage sources for inactive assistants;
- administrators can manage sources for private assistants;
- cross-assistant access remains prohibited;
- changing assistant status or visibility does not modify source retrieval state.

Migration tests

Where a migration is added, cover:

- upgrade from the current schema;
- existing Redmoor assistant preservation;
- constraint creation;
- downgrade where supported;
- repeated migration handling according to repository conventions;
- PostgreSQL error classes used for idempotent migration handling.

⸻

Verification commands

Codex must inspect the repository’s current scripts and use the canonical commands. At minimum, run the backend equivalents of:

cd apps/backend

# Static analysis

../../venv/bin/ruff check .
../../venv/bin/ruff format --check .
../../venv/bin/mypy .

# Targeted tests

../../venv/bin/python -m pytest \
 tests/test_assistant_domain.py \
 tests/test_assistant_repository.py \
 tests/test_assistant_admin_service.py \
 tests/test_assistant_admin_api.py \
 -q

# Relevant regression tests

../../venv/bin/python -m pytest \
 tests/test_public_chat_api.py \
 tests/test_knowledge_sources_api.py \
 tests/test_knowledge_source_service.py \
 -q

# Full backend suite against the repository's supported PostgreSQL test database

DATABASE_URL="<isolated-test-database-url>" \
 ../../venv/bin/python -m pytest -q

Use the actual test filenames present after implementation.

Run migration tests against an isolated PostgreSQL database.

Do not report database integration tests as passing if they were skipped because PostgreSQL was unavailable.

Also run:

git diff --check

Report:

- exact commands run;
- pass/fail counts;
- skipped tests and why;
- any validation that could not be completed;
- any repository behaviour discovered that changed the implementation from this specification.

Do not commit, push or create a pull request as part of this task.
