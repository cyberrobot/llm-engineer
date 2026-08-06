# Chunk 7D follow-up — Knowledge persistence verification hardening

## Repository state

Expected branch: a fresh feature branch

Base branch: `origin/main`

Worktree: repository worktree for the new branch

Dependencies: Chunk 7C content processing and the existing Chunk 7D knowledge-persistence implementation on `main`

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- The authoritative Chunk 7D knowledge-persistence specification
- `apps/backend/README.md`, especially **Knowledge persistence**

### Primary change area

- `apps/backend/tests/test_knowledge_persistence_integration.py`
- Backend PostgreSQL/pgvector test fixtures and CI configuration, only where required to make the focused integration suite mandatory and deterministic

### Canonical implementation examples

- `apps/backend/assistant/application/knowledge_persistence_service.py`
- `apps/backend/assistant/domain/knowledge_persistence.py`
- `apps/backend/assistant/infrastructure/repositories/knowledge_persistence.py`
- `apps/backend/infrastructure/database/connection.py`
- `apps/backend/infrastructure/database/migrations/transactional_ingestion_persistence.py`
- Existing PostgreSQL-backed migration and repository tests under `apps/backend/tests/`

### Relevant symbols

- `KnowledgePersistenceService`
- `PostgresKnowledgePersistenceRepository`
- `PostgresKnowledgePersistenceTransaction`
- `replace_document`
- `update_document_metadata`
- `test_processed_knowledge_is_idempotent_retrievable_and_replaces_stale_chunks`
- `test_repository_rolls_back_document_when_chunk_insert_fails`
- `test_concurrent_duplicate_writes_leave_one_document_and_one_chunk`
- `test_pipeline_persistence_rolls_back_reindex_and_replays_one_committed_result`
- `test_transactional_persistence_migration_preserves_existing_index_and_is_reversible`

### Expected change surface

- Focused PostgreSQL integration tests and their reusable test-only failure-injection helpers
- Test database readiness/skip policy used by the focused suite
- GitHub Actions PostgreSQL/pgvector setup if the focused tests are not currently mandatory there
- Minimal test documentation when a new command or environment requirement is introduced

### Excluded areas

- Production persistence behavior, unless a new test demonstrates a real defect
- Website loading, extraction, cleaning, and chunking
- Ingestion orchestration, workers, retries, scheduling, and job lifecycle behavior
- API endpoints, administrator UI, retrieval ranking, and embedding algorithms
- Schema redesign, new vector stores, new ORMs, or new test frameworks
- Broad refactoring or changes made only to simplify test injection

### Unknowns Codex must verify

- Why the focused PostgreSQL tests skip locally and whether CI already treats that condition as a failure
- Whether the repository connection context commits on clean exit and rolls back every exception path
- The precise SQL boundaries needed to inject failures without changing production interfaces
- Whether a database trigger, test-only cursor proxy, or connection/cursor wrapper is the smallest reliable stage-specific failure mechanism
- Whether current migration tests run against a real pgvector-enabled PostgreSQL service in CI

---

## Objective

Close the remaining Chunk 7D verification gaps without changing its established document-level replacement strategy.

The completed work must provide executable, non-skipped PostgreSQL/pgvector evidence that:

1. Processed content persists through `KnowledgePersistenceService` and is retrievable through the existing vector retrieval path.
2. Identical input is idempotent and concurrent duplicate attempts cannot create duplicate knowledge.
3. Every important document-level write stage rolls back completely when it fails.
4. The relevant migration preserves existing data, constraints, indexes, vector dimensions, and reversibility.

The required integration suite must fail clearly when its database prerequisites are expected but unavailable. It must not silently convert missing CI infrastructure into a passing build.

## Current architecture

`KnowledgePersistenceService.prepare()` performs duplicate detection and embedding generation before the database write transaction. `persist_prepared()` opens one repository-owned transaction for all prepared documents. `PostgresKnowledgePersistenceTransaction.replace_document()` serializes writers for an assistant/source pair, updates or creates the document, removes obsolete chunks, and bulk-inserts the replacement chunks. `update_document_metadata()` updates document and chunk access roles without regenerating embeddings.

The existing integration suite already covers the successful retrieval path, unchanged-content idempotency, replacement of stale chunks, chunk-insert rollback, concurrent duplicates, a pre-commit failure, and migration reversibility. The remaining gap is direct rollback evidence for each significant write stage and guaranteed execution of the PostgreSQL suite in its required environment.

## Required implementation

### 1. Make database test prerequisites explicit

Inspect the existing `require_database()` behavior and CI workflow.

- Preserve developer-friendly skips only when PostgreSQL is genuinely optional for a local command.
- Add or reuse an explicit environment setting that makes PostgreSQL integration tests required in CI and in the documented verification command.
- When required mode is enabled, an unavailable database, missing pgvector extension, failed migration, or incompatible vector dimension must fail with a clear diagnostic instead of skipping.
- Do not embed credentials or introduce a second database configuration path.
- Reuse the existing `DATABASE_URL`, connection factory, migration bootstrap, and CI PostgreSQL service.
- Keep integration tests isolated with unique identifiers or schemas and deterministic cleanup.

### 2. Add stage-specific atomic rollback tests

Use the real `PostgresKnowledgePersistenceRepository` against migrated PostgreSQL. Inject a database failure at each stage below and verify the complete externally observable stored state after the transaction exits.

#### New document creation failure

- Fail during or immediately after the document insert and before any successful commit.
- Confirm no document, chunk, vector, or persistence receipt remains.

#### Chunk insertion failure

- Retain or strengthen the existing uniqueness-induced chunk insertion failure test.
- Confirm the newly inserted document is rolled back and no chunks remain.

#### Obsolete chunk removal failure

- Begin with an existing document and chunk set.
- Attempt a changed-content replacement.
- Inject failure at the obsolete-chunk deletion stage.
- Confirm the prior document hash, metadata, chunk texts, chunk hashes, vectors, and retrieval results remain unchanged.

#### Document metadata update failure

- Begin with unchanged content and existing roles/title.
- Attempt a metadata-only update.
- Inject failure after one metadata write but before transaction completion.
- Confirm both document and chunk roles/title retain their original committed values and retrieval authorization behavior is unchanged.

#### Commit or final-transaction failure

- Retain or strengthen the existing failure immediately before commit.
- Confirm document replacement, chunk changes, ingestion-job links, and persistence receipts all roll back together.
- Confirm a subsequent healthy retry succeeds exactly once.

Failure injection must be deterministic. Do not use timing races, arbitrary sleeps, production-only flags, or broad monkeypatches that bypass the real repository SQL. Prefer narrowly scoped test-only cursor/transaction wrappers or PostgreSQL mechanisms that fail the intended statement while leaving production code unchanged.

### 3. Prove retrieval state after rollback

For replacement and metadata rollback cases, query through the existing `PgVectorStore` or retrieval repository after the injected failure.

- Old chunks must remain retrievable after a failed replacement.
- Proposed replacement chunks must not be retrievable.
- Source URL and title must remain correct.
- Access-role filtering must reflect the last committed roles, not the attempted update.
- Use deterministic embeddings and do not call a live provider.

### 4. Preserve and verify concurrency guarantees

Keep the existing concurrent duplicate-write scenario and ensure it runs in required database mode.

- Coordinate simultaneous attempts deterministically without relying on sleeps.
- Assert exactly one document and one expected chunk set exist.
- Assert both attempts either resolve safely as created/unchanged or one raises the documented application conflict.
- Confirm no raw uniqueness error escapes the application boundary when exercising the application service.
- Confirm the stored representation remains retrievable.

### 5. Verify schema and migration compatibility

Run migrations against a fresh isolated schema and a schema containing representative existing retrieval data.

Verify:

- Upgrade succeeds and is idempotent.
- Downgrade succeeds where the migration convention requires it.
- Existing document and chunk records remain readable.
- pgvector is available.
- The vector column dimension matches `EMBEDDING_VECTOR_DIMENSIONS`.
- Assistant/source URL, document/sequence, and document/content-hash uniqueness constraints or indexes exist.
- Foreign-key behavior is explicit and preserves document/chunk integrity.
- No migration deletes existing knowledge data.

Do not add a migration merely to make the tests pass unless inspection demonstrates an actual schema defect.

### 6. Keep error boundaries and logs safe

If a new test exposes a production defect and a minimal production fix is required:

- Preserve application-level exception mapping.
- Ensure provider, psycopg, and raw SQL errors do not leak from `KnowledgePersistenceService`.
- Preserve the original exception as the cause.
- Do not log chunk text, vectors, provider payloads, credentials, or connection strings.
- Add a regression test that fails before the production fix.

## Acceptance criteria

- [ ] The focused PostgreSQL/pgvector persistence integration suite runs rather than skips in the required verification environment.
- [ ] Missing PostgreSQL or pgvector fails clearly when required mode is enabled.
- [ ] Local optional mode, if retained, reports an explicit skip reason.
- [ ] Processed content persisted through `KnowledgePersistenceService` is returned by the existing retrieval path with source metadata.
- [ ] Access-role filtering works for persisted content.
- [ ] Repeating identical content creates no documents, chunks, vectors, or embeddings.
- [ ] Concurrent duplicate attempts leave exactly one current document representation and no duplicate chunks.
- [ ] A document-creation-stage failure leaves no partial state.
- [ ] A chunk-insertion-stage failure leaves no partial state.
- [ ] An obsolete-chunk-removal-stage failure preserves the complete prior representation.
- [ ] A metadata-update-stage failure preserves document metadata, chunk roles, and retrieval authorization.
- [ ] A final transaction or commit-stage failure rolls back representation and persistence receipt changes.
- [ ] A healthy retry after a failed transaction succeeds once and produces accurate counters.
- [ ] Migration upgrade, idempotent re-upgrade, and required downgrade behavior pass against real PostgreSQL.
- [ ] Existing retrieval data remains readable across migration verification.
- [ ] Vector dimensions and required uniqueness/foreign-key constraints are asserted from the database catalog.
- [ ] No production behavior is changed unless a failing regression test proves a defect.
- [ ] No live website or embedding-provider request is made.
- [ ] Focused unit tests, integration tests, lint, formatting, type checking, and startup validation pass.

## Tests to add or update

Primary location:

- `apps/backend/tests/test_knowledge_persistence_integration.py`

Add or strengthen clearly named tests equivalent to:

- `test_required_database_mode_fails_when_postgres_is_unavailable`
- `test_document_creation_failure_rolls_back_all_knowledge`
- `test_chunk_insertion_failure_rolls_back_new_document`
- `test_obsolete_chunk_deletion_failure_preserves_previous_retrievable_representation`
- `test_metadata_update_failure_preserves_document_chunk_roles_and_authorization`
- `test_pre_commit_failure_rolls_back_replacement_and_receipt_then_retry_succeeds`
- `test_concurrent_service_persistence_creates_one_retrievable_representation`
- `test_persistence_migration_preserves_existing_retrieval_data_and_schema_contracts`

Reuse existing tests when they already prove the complete behavior; do not duplicate scenarios solely to match suggested names.

For every rollback test, assert exact document and chunk counts, document hash, title, roles, ordered chunk text and hashes, receipt count where applicable, and retrieval results. A broad “no exception” or status-only assertion is insufficient.

## Verification commands

Use the repository’s actual required-database environment variable after inspecting existing fixtures. The placeholder below must be replaced with that established setting rather than introducing a duplicate switch.

```bash
cd apps/backend

# Focused unit behavior
venv/bin/python -m pytest \
  tests/test_knowledge_persistence_service.py \
  tests/test_content_processing_config.py -q

# Required real PostgreSQL/pgvector verification; zero skips are permitted
REQUIRE_POSTGRES_TESTS=1 venv/bin/python -m pytest \
  tests/test_knowledge_persistence_integration.py -q

# Broader affected backend suite
venv/bin/python -m pytest -q

# Static validation
ruff check .
ruff format --check .
venv/bin/python -m mypy .

# Startup/import validation
venv/bin/python -c "from main import app; assert app is not None"
```

The completion report must include the exact PostgreSQL integration result and skipped-test count. Completion is not valid if any focused persistence integration test is skipped, xfailed, or deselected in required mode.
