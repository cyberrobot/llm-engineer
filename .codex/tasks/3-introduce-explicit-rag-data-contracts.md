# PR 3 — Introduce explicit RAG data contracts

## Repository state

Expected branch:

`3-introduce-explicit-rag-data-contracts`

Base branch:

`main`

Worktree:

Fresh worktree based on current `origin/main`.

Dependencies:

- PR 1 / legacy RAG contract work must already be present where applicable.
- PR 2 / secured RAG UI boundary must remain compatible.
- This PR must not migrate `/rag-chat` out of `apps/backend`.
- This PR must preserve the existing RAG retrieval behaviour and externally observable `/rag-chat` contract.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/TEMPLATE.md`

### Primary change area

- `apps/backend/assistant/application/`
- `apps/backend/assistant/application/ports/`
- `apps/backend/assistant/infrastructure/`
- `apps/backend/infrastructure/database/`
- `apps/backend/tests/`

### Canonical implementation examples

Inspect and reuse the repository’s existing application-port and repository patterns before introducing new abstractions.

In particular, follow existing patterns under:

- `apps/backend/assistant/application/ports/`
- `apps/backend/assistant/infrastructure/`
- existing PostgreSQL repository implementations
- existing disposable-PostgreSQL integration tests
- existing database migration and schema verification infrastructure

Do not introduce a parallel persistence framework or a second database access abstraction when an existing pattern can satisfy the requirement.

### Relevant symbols

Current retrieval path:

- `assistant.application.retrieval.search_chunks`
- `assistant.application.retrieval.multi_query_search`
- `assistant.infrastructure.storage.search_chunks_by_embedding`

Current mixed storage responsibilities include:

- `save_document_with_chunks`
- `create_uploaded_document`
- `create_ingestion_job`
- `search_chunks_by_embedding`
- `list_all_chunks`

RAG retrieval currently depends on the following database fields:

- `documents.id`
- `documents.assistant_id`
- `documents.retrieval_state`
- `chunks.id`
- `chunks.doc_id`
- `chunks.assistant_id`
- `chunks.access_roles`
- `chunks.embedding`
- `chunks.text`
- `chunks.text_search`

The current hybrid query:

- restricts chunks by `chunks.assistant_id`;
- independently restricts joined documents by `documents.assistant_id`;
- requires `documents.retrieval_state = 'enabled'`;
- requires the requested role to exist in `chunks.access_roles`;
- ranks vector candidates using pgvector distance;
- ranks keyword relevance using PostgreSQL full-text search;
- combines vector and keyword scores using the existing configured weights;
- applies the existing candidate and result limits.

### Expected change surface

Expected changes should remain narrowly focused on:

- a RAG read-only repository contract;
- its PostgreSQL implementation;
- retrieval dependency wiring;
- extraction of the hybrid query from the mixed storage module;
- database contract verification;
- least-privilege RAG database-role definition/documentation;
- PostgreSQL integration tests;
- updating existing tests that directly import the old mixed-storage retrieval function.

Small migration or database bootstrap changes are allowed only where required to define or verify the RAG read role.

### Excluded areas

Do not:

- move `/rag-chat` into a new application or service;
- change `/rag-chat` request or response behaviour;
- change embedding providers or embedding dimensions;
- redesign hybrid ranking;
- change vector/keyword weighting;
- change maximum-distance behaviour;
- change result limits unless required to preserve existing behaviour;
- alter ingestion orchestration;
- move ingestion repositories as part of this PR;
- redesign document lifecycle or `retrieval_state`;
- change Assistant publishing behaviour;
- change RAG UI behaviour;
- change the public Assistant widget;
- introduce write capabilities into the RAG repository;
- combine this work with a broader storage-module refactor;
- create speculative generic repository abstractions unrelated to RAG reads.

### Unknowns Codex must verify

Before implementation, verify:

1. The exact application-port naming conventions currently used under `assistant/application/ports/`.
2. How repository implementations are currently instantiated and injected into application services.
3. Whether `get_connection()` can already accept alternate PostgreSQL credentials or connection configuration suitable for a read-only RAG role.
4. How migrations/bootstrap SQL currently manages PostgreSQL roles and grants, if at all.
5. Whether database-role provisioning belongs in migrations, deployment/bootstrap SQL, or documented infrastructure configuration.
6. Whether `text_search` is generated, indexed, or maintained by migration/database trigger logic.
7. Existing indexes supporting:
   - `chunks.embedding`;
   - `chunks.text_search`;
   - `chunks.assistant_id`;
   - `documents.assistant_id`;
   - `documents.retrieval_state`.
8. Every current caller and test that imports `search_chunks_by_embedding`.
9. Whether any non-RAG code depends on the retrieval query remaining in `assistant/infrastructure/storage.py`.
10. The current `/rag-chat` composition path so that repository injection can be changed without altering HTTP behaviour.
11. Whether the production deployment mechanism permits a separate RAG database credential now, or whether this PR should define the role/grants and configuration contract without activating separate credentials by default.

If repository state contradicts these assumptions, stop and report the mismatch rather than introducing a competing architecture.

---

## Objective

Decouple RAG retrieval from the backend’s mixed persistence module by introducing an explicit, read-only RAG knowledge repository contract and a dedicated PostgreSQL implementation.

RAG application code must depend on a retrieval-specific repository interface rather than importing the mixed `assistant/infrastructure/storage.py` module.

The PostgreSQL schema required by RAG must become an explicit, independently testable contract, including assistant isolation, role isolation, retrieval-state filtering, vector search, and full-text search.

The change must preserve the existing `/rag-chat` behaviour while creating a persistence boundary that can later be separated from ingestion and administrative database privileges.

## Current architecture

RAG retrieval orchestration currently lives in:

`apps/backend/assistant/application/retrieval.py`

That application module directly imports:

`assistant.infrastructure.storage.search_chunks_by_embedding`

The same `assistant/infrastructure/storage.py` module also contains write-oriented ingestion persistence such as document creation, chunk persistence, and ingestion-job creation.

This creates two problems:

1. The RAG read path is coupled to a persistence module with unrelated write responsibilities.
2. The exact PostgreSQL schema and privileges required by RAG are implicit rather than defined as a standalone contract.

The existing hybrid query already enforces important retrieval constraints:

- chunk Assistant ownership;
- document Assistant ownership;
- enabled document retrieval state;
- role membership through `chunks.access_roles`;
- vector similarity ranking;
- PostgreSQL full-text ranking;
- configured hybrid scoring and limits.

Those semantics are part of the current behaviour and must be preserved.

The repository architecture requires application logic to depend on application-owned ports and persistence implementations to remain in infrastructure. RAG therefore needs a dedicated read-only persistence boundary rather than a direct application-to-mixed-storage import.

## Required implementation

### 1. Introduce a read-only RAG knowledge repository contract

Add an application-owned persistence interface for RAG retrieval under the established application-port location.

Use repository conventions already present in the codebase.

Conceptually, the contract must provide the retrieval operation currently supplied by `search_chunks_by_embedding`, accepting the information required to perform a bounded Assistant/role-scoped hybrid search.

The contract must be read-only.

It must not expose:

- document creation;
- chunk creation;
- ingestion-job creation;
- document mutation;
- retrieval-state mutation;
- Assistant administration;
- arbitrary SQL execution;
- transaction or connection objects.

Use an application-owned return type if an established pattern exists. Do not leak psycopg row objects, cursors, or PostgreSQL-specific types into application orchestration.

### 2. Add a dedicated PostgreSQL RAG repository

Add a PostgreSQL implementation of the RAG knowledge repository under the appropriate Assistant infrastructure persistence boundary.

Move the existing hybrid retrieval SQL from:

`assistant/infrastructure/storage.py`

into this dedicated implementation.

Preserve the current query semantics unless a change is strictly necessary to correct a proven defect.

The implementation must continue to enforce all of the following at the SQL boundary:

- `chunks.assistant_id = requested assistant`;
- `documents.assistant_id = requested assistant`;
- `documents.retrieval_state = 'enabled'`;
- `chunks.access_roles` contains the caller’s permitted role;
- vector distance is calculated using the existing pgvector operator;
- vector candidate bounding remains equivalent;
- keyword rank continues to use the existing PostgreSQL full-text search behaviour;
- existing configured vector and keyword weights remain authoritative;
- final result ordering remains by hybrid score;
- requested result limits remain bounded according to current application behaviour.

Do not move Assistant or role isolation out of SQL into post-processing.

### 3. Remove the RAG application dependency on the mixed storage module

Update RAG retrieval orchestration so that:

`assistant/application/retrieval.py`

no longer imports:

`assistant.infrastructure.storage`

for knowledge retrieval.

Application orchestration must receive or resolve the RAG repository using the repository’s established dependency-injection/factory pattern.

Do not create hidden module-level database dependencies as a substitute for the current import.

Existing RAG entry points, including `/rag-chat`, must use the new repository implementation while remaining inside `apps/backend`.

### 4. Remove the hybrid retrieval query from the mixed storage module

After all RAG callers use the new repository:

- remove `search_chunks_by_embedding` from the mixed `assistant/infrastructure/storage.py`, or leave only a temporary compatibility layer if an existing in-scope caller demonstrably requires one;
- no RAG application or test should depend on that compatibility layer;
- do not move unrelated ingestion/write functions in this PR.

The resulting mixed storage module may continue to serve existing ingestion responsibilities until later work addresses those separately.

### 5. Define the explicit RAG database contract

Document and verify that RAG requires, at minimum, the following schema contract:

#### `documents`

- `id`
- `assistant_id`
- `retrieval_state`

Required semantics:

- `assistant_id` identifies the owning Assistant.
- `retrieval_state` determines whether document chunks are eligible for retrieval.
- only documents belonging to the requested Assistant and in the enabled retrieval state are eligible.

#### `chunks`

- `id`
- `doc_id`
- `assistant_id`
- `access_roles`
- `embedding`
- `text`
- `text_search`

Required semantics:

- `doc_id` links the chunk to its document.
- `assistant_id` identifies the owning Assistant.
- `access_roles` supports server-side role filtering using the existing PostgreSQL representation/operator.
- `embedding` is compatible with the existing pgvector query and embedding dimension.
- `text_search` supports the existing English full-text ranking query.
- `text` remains the retrieved chunk content returned to application logic.

The contract must not rely on ingestion implementation functions to prove these fields exist or work.

### 6. Add independent schema-compatibility verification

Add PostgreSQL integration coverage that constructs or migrates a disposable database using the real migration path and verifies that the RAG repository operates against the required schema.

The test must prove RAG schema compatibility independently of ingestion orchestration.

Do not satisfy this requirement by calling `save_document_with_chunks()` or another ingestion helper to create all test fixtures.

Fixtures for the contract test should insert the minimum necessary database rows directly through test database setup or an appropriate low-level persistence fixture so that failure of the ingestion implementation does not invalidate the independence of the RAG contract test.

The test should fail clearly if any required RAG column, type, generated field, extension, index-dependent operator, or query assumption becomes incompatible.

### 7. Add Assistant-isolation PostgreSQL integration tests

Using the real PostgreSQL RAG repository, prove that retrieval cannot cross Assistant boundaries.

At minimum create:

- Assistant A with an enabled document and retrievable chunk;
- Assistant B with a separate enabled document and retrievable chunk;
- content that would otherwise be highly relevant to the same query.

Verify:

- querying as Assistant A returns only Assistant A chunks;
- querying as Assistant B returns only Assistant B chunks;
- a chunk whose `chunks.assistant_id` disagrees with the joined document Assistant is not returned;
- a document belonging to another Assistant cannot become visible merely because the chunk row contains the requested Assistant ID.

These must be real PostgreSQL persistence tests, not mocked repository tests.

### 8. Add role-isolation PostgreSQL integration tests

Using the real PostgreSQL RAG repository, create chunks with distinct `access_roles`.

Verify:

- a permitted role receives its eligible chunks;
- another role cannot retrieve those chunks;
- relevant content does not bypass role filtering because of high vector similarity;
- relevant content does not bypass role filtering because of high keyword rank;
- chunks with multiple roles are available only to roles explicitly represented in the stored role set;
- role filtering occurs in the database query rather than after unrestricted rows are returned.

Preserve the current role representation and PostgreSQL containment/operator behaviour unless an existing schema contract requires otherwise.

### 9. Cover retrieval-state isolation

Add PostgreSQL integration coverage proving:

- chunks belonging to `retrieval_state = 'enabled'` documents can be retrieved;
- chunks belonging to disabled, inactive, failed, or otherwise non-enabled states supported by the current schema are not retrieved;
- high semantic or keyword relevance cannot override the document retrieval-state restriction.

Do not duplicate document lifecycle rules in RAG application code.

### 10. Preserve hybrid retrieval behaviour

Add or update behavioural tests to establish parity for:

- vector candidate selection;
- keyword ranking;
- hybrid score ordering;
- configured weighting;
- result limit;
- maximum-distance handling performed by application orchestration;
- result mapping fields currently consumed by downstream RAG code.

The refactor must not intentionally alter ranking or result shape.

Where practical, establish the current behaviour with tests before moving the query.

### 11. Introduce a least-privilege PostgreSQL role design

Define a dedicated RAG database-role design with only the privileges required for retrieval.

The intended privilege surface is:

- `CONNECT` to the required database where explicit grant is needed;
- `USAGE` on the relevant schema where required;
- `SELECT` on:
  - `documents`;
  - `chunks`.

The RAG role must not receive:

- `INSERT`;
- `UPDATE`;
- `DELETE`;
- `TRUNCATE`;
- ingestion-job table writes;
- Assistant administration writes;
- audit-log writes;
- migration/schema ownership;
- `CREATE` on the application schema;
- superuser, database-owner, or broad inherited administrative privileges.

Use the repository’s existing database provisioning mechanism if one exists.

If PostgreSQL role creation is intentionally deployment-managed rather than migration-managed, add the declarative SQL/configuration/documentation in the established infrastructure location rather than forcing role ownership into application migrations.

Do not hard-code production passwords or credentials.

### 12. Add least-privilege integration verification

Where the test infrastructure permits PostgreSQL role creation, add integration tests that connect using the RAG read role and verify:

Allowed:

- `SELECT` from `documents`;
- `SELECT` from `chunks`;
- execution of the real RAG hybrid retrieval query.

Denied:

- inserting a document;
- updating a document;
- deleting a document;
- inserting a chunk;
- updating a chunk;
- deleting a chunk;
- writing ingestion-job or administrative tables.

If CI PostgreSQL permissions make role creation impossible, provide the strongest executable privilege test supported by the current infrastructure and document the remaining deployment-level verification requirement. Do not silently omit least-privilege verification.

### 13. Keep `/rag-chat` on the new repository

Existing `/rag-chat` execution must continue through `apps/backend`.

Update its dependency path so that the RAG application retrieval service ultimately uses the new read-only repository.

Do not:

- introduce a new HTTP service;
- change the route contract;
- require clients to know about the repository;
- expose database details through the API.

### 14. Preserve failure behaviour

Infrastructure failures from the new repository must flow through the existing application/API error handling.

Do not expose:

- SQL text;
- PostgreSQL connection strings;
- credentials;
- schema internals;
- raw database exception messages

to `/rag-chat` callers.

Do not add broad exception swallowing merely to preserve status codes.

### 15. Documentation

Update the nearest relevant backend architecture or operations documentation to describe:

- the read-only RAG knowledge repository boundary;
- the database fields forming the RAG persistence contract;
- the intended RAG database role;
- required grants;
- how deployments supply the RAG database credential if separate credentials are supported;
- the fact that ingestion retains write credentials;
- how to verify schema and privilege compatibility.

Do not document separate production credentials as active unless the implementation/deployment configuration actually uses them.

## Acceptance criteria

- [ ] A dedicated application-owned read-only RAG knowledge repository interface exists.
- [ ] The interface exposes retrieval capabilities only and no ingestion or administrative writes.
- [ ] A dedicated PostgreSQL implementation owns the RAG hybrid retrieval query.
- [ ] `assistant/application/retrieval.py` no longer imports `assistant.infrastructure.storage`.
- [ ] No RAG application code imports the mixed storage module to perform retrieval.
- [ ] The hybrid SQL query has been removed from the mixed storage module or is retained only behind a justified compatibility shim unused by RAG.
- [ ] Existing ingestion/write behaviour is not refactored beyond what is necessary to remove RAG retrieval from the mixed module.
- [ ] `/rag-chat` continues to run in `apps/backend`.
- [ ] `/rag-chat` uses the new RAG repository through the established application dependency boundary.
- [ ] `/rag-chat` externally observable behaviour remains unchanged.
- [ ] Retrieval continues to require matching `chunks.assistant_id`.
- [ ] Retrieval continues to require matching `documents.assistant_id`.
- [ ] Retrieval continues to require `documents.retrieval_state = 'enabled'`.
- [ ] Retrieval continues to apply role filtering through `chunks.access_roles` in PostgreSQL.
- [ ] Vector ranking remains equivalent to the pre-refactor implementation.
- [ ] Full-text ranking remains equivalent to the pre-refactor implementation.
- [ ] Hybrid weighting and ordering remain equivalent.
- [ ] Existing candidate and result bounds remain equivalent.
- [ ] Existing maximum-distance application behaviour remains equivalent.
- [ ] The RAG database contract explicitly covers `documents.assistant_id`.
- [ ] The RAG database contract explicitly covers `documents.retrieval_state`.
- [ ] The RAG database contract explicitly covers `chunks.assistant_id`.
- [ ] The RAG database contract explicitly covers `chunks.access_roles`.
- [ ] The RAG database contract explicitly covers `chunks.embedding`.
- [ ] The RAG database contract explicitly covers `chunks.text_search`.
- [ ] The repository contract tests also account for `documents.id`, `chunks.id`, `chunks.doc_id`, and `chunks.text` because the query depends on them.
- [ ] Schema compatibility is tested against real PostgreSQL after applying the real database migrations.
- [ ] Schema compatibility tests do not depend on ingestion application functions to establish the RAG contract.
- [ ] PostgreSQL integration tests prove Assistant A cannot retrieve Assistant B data.
- [ ] PostgreSQL integration tests cover inconsistent chunk/document Assistant ownership.
- [ ] PostgreSQL integration tests prove one role cannot retrieve chunks belonging exclusively to another role.
- [ ] PostgreSQL integration tests prove high vector similarity cannot bypass role isolation.
- [ ] PostgreSQL integration tests prove high keyword relevance cannot bypass role isolation.
- [ ] PostgreSQL integration tests prove non-enabled documents are excluded from retrieval.
- [ ] A least-privilege RAG PostgreSQL role design exists.
- [ ] The RAG database role has `SELECT` access to `documents` and `chunks`.
- [ ] The RAG database role does not have ingestion or administrative write access.
- [ ] No production database credential is committed to source.
- [ ] Least-privilege behaviour is integration-tested where supported by the repository’s PostgreSQL test environment.
- [ ] Raw PostgreSQL errors or credentials are not exposed to RAG clients.
- [ ] Existing RAG retrieval tests are updated to use the new repository boundary.
- [ ] Relevant backend documentation describes the RAG schema and privilege contract.
- [ ] No unrelated frontend, widget, ingestion, or Assistant administration behaviour changes.

## Tests to add or update

Add or update focused tests under `apps/backend/tests/`.

Expected coverage includes:

### Repository integration tests

Add a focused PostgreSQL integration test module for the RAG knowledge repository, following existing persistence-test naming conventions.

Cover:

- basic hybrid retrieval;
- result mapping;
- Assistant isolation;
- mismatched document/chunk Assistant ownership;
- role isolation;
- multiple permitted roles;
- role denied despite high vector similarity;
- role denied despite strong keyword match;
- enabled document retrieval;
- non-enabled document exclusion;
- result limit;
- deterministic hybrid ordering for controlled fixtures.

### Schema contract tests

Add a dedicated integration test proving the migrated PostgreSQL database satisfies the RAG contract independently of ingestion code.

The test should exercise the real repository after inserting minimal compatible rows without calling ingestion orchestration.

Verify availability and compatibility of:

- `documents.assistant_id`;
- `documents.retrieval_state`;
- `chunks.assistant_id`;
- `chunks.access_roles`;
- `chunks.embedding`;
- `chunks.text_search`;
- required relationship and content fields.

Where generated columns, triggers, extensions, or indexes are necessary for the real query, exercise them rather than merely checking `information_schema`.

### Least-privilege tests

Where supported:

- create/use the RAG read role;
- prove the real retrieval query succeeds;
- prove document writes fail;
- prove chunk writes fail;
- prove ingestion/admin writes fail.

Use exact privilege failures rather than truthiness or “no exception” assertions.

### Existing retrieval/application tests

Update tests that currently import:

`assistant.infrastructure.storage.search_chunks_by_embedding`

so they exercise either:

- the public RAG repository interface; or
- the application retrieval service with an injected test repository where a unit test is appropriate.

Do not mock the PostgreSQL repository in tests whose purpose is to verify Assistant, role, schema, vector, or full-text isolation.

### `/rag-chat` regression coverage

Retain or add behavioural coverage proving that the existing route still produces the same externally observable result for equivalent fixtures.

Do not couple the route test to concrete PostgreSQL implementation classes unless required by the established integration-test pattern.

## Verification commands

Run the narrowest affected tests first, then the broader backend suite.

```bash
# From repository root.

# Focused RAG repository / persistence integration tests.
cd apps/backend
pytest -q tests/<rag_repository_integration_test>.py
pytest -q tests/<rag_schema_contract_test>.py

# Existing persistence integration coverage affected by moving the query.
pytest -q tests/test_knowledge_persistence_integration.py

# Focused RAG/retrieval and rag-chat coverage.
pytest -q tests -k "rag or retrieval"

# Return to repository root.
cd ../..

# Repository-supported backend/API test suite.
npm run test:api
```

Also run the repository-defined backend formatting, linting, type-checking, and migration verification commands that apply to the final change.

If the repository provides a dedicated PostgreSQL migration or integration command after inspection, run it as part of final verification.

If least-privilege role tests require PostgreSQL capabilities unavailable in the standard CI database, record:

- the exact command attempted;
- the permission failure;
- the deployment-level verification still required.

Do not report the PR complete while any relevant executable verification is failing.
