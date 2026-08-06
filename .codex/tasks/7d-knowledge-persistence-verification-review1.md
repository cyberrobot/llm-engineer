# Update PR #67 — Complete knowledge-persistence verification hardening

## Repository state

Expected branch: `feature/7d-persistence-verification-hardening`

Base branch: `main`

Pull request: PR #67 — **Harden knowledge persistence PostgreSQL verification**

Dependencies: `.codex/tasks/7d-knowledge-persistence-verification-hardening.md`

This task updates the existing branch and pull request.

Do not:

- Create another branch or pull request.
- Change production persistence behavior.
- Add migrations, dependencies, API behavior, or ingestion orchestration.
- Replace the existing real-PostgreSQL tests with mocks.
- Weaken, delete, skip, or xfail existing persistence tests.
- Use arbitrary sleeps to manufacture concurrency.

### Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `.codex/tasks/7d-knowledge-persistence-verification-hardening.md`
- `apps/backend/tests/test_knowledge_persistence_integration.py`
- `apps/backend/assistant/application/knowledge_persistence_service.py`
- `apps/backend/assistant/infrastructure/repositories/knowledge_persistence.py`
- `.github/workflows/test.yml`
- The current PR #67 description, checks, and review findings

### Primary change area

- `apps/backend/tests/test_knowledge_persistence_integration.py`
- PR #67 description after all verification has completed

### Expected change surface

- A deterministic test-only concurrency coordination helper
- The concurrent duplicate-persistence integration test
- Exact assertions in the healthy retry/pre-commit rollback test
- PR #67 verification text

### Excluded areas

- Application, domain, repository, vector-store, and database production modules
- Database migrations or schema changes
- CI service topology and required-database environment behavior already completed in PR #67
- Website loading, processing, workers, retries, endpoints, and administrator features
- Unrelated test refactoring

---

## Objective

Resolve the remaining PR #67 review findings so the pull request provides deterministic evidence that concurrent persistence is safe, proves that a healthy retry reports accurate counters, and records truthful verification results in the pull request description.

The intended production implementation is already complete. This task strengthens verification and reporting only.

## Current state

PR #67 already provides:

- Required PostgreSQL/pgvector execution in CI.
- Fail-fast behavior when required database infrastructure is unavailable.
- Real repository rollback tests for document creation, chunk insertion, obsolete-chunk deletion, metadata updates, and final transaction failure.
- Retrieval and access-role checks after rollback.
- Migration idempotency and schema-contract tests.
- Passing GitHub Actions.

Three gaps remain:

1. The concurrent test submits two thread-pool tasks without proving they overlap at the persistence boundary.
2. The successful retry is compared with its replay result but its individual counters are not asserted.
3. The PR description says tests were not run and omits the required exact PostgreSQL result and skipped-test count.

## Required implementation

### 1. Coordinate concurrent persistence deterministically

Update `test_concurrent_duplicate_writes_leave_one_document_and_one_chunk` or rename it to a clearer behavior-oriented name.

Both workers must be proven ready before either proceeds into the persistence race. Use deterministic test-only synchronization such as:

- `threading.Barrier`, with each worker waiting immediately before its first transaction or duplicate-detection read; or
- paired `threading.Event` objects that allow the test to observe both workers at the selected boundary before releasing them.

The chosen boundary must exercise the real application service and `PostgresKnowledgePersistenceRepository`. It must not bypass the advisory lock, row lookup, uniqueness constraints, transaction context, or application exception mapping.

Requirements:

- Coordinate each worker exactly once.
- Do not place a reusable barrier around every connection acquisition; later reads and retrieval assertions must proceed normally.
- Do not use `sleep()` as synchronization.
- Use a bounded barrier/event timeout so a regression fails rather than hanging indefinitely.
- Preserve deterministic cleanup on success or failure.
- Continue using the deterministic fake embedding provider; do not call a live provider.

The test must assert:

- Both workers reached the coordinated boundary.
- Exactly one result reports one created document and the other reports unchanged content, or one returns the documented application conflict if that is the established contract.
- No raw `UniqueViolation`, repository exception, or synchronization exception escapes.
- Exactly one document exists for the assistant/source pair.
- Exactly one expected chunk set exists with no duplicate vectors.
- The stored chunk is retrievable through the existing retrieval path.
- Access-role filtering remains correct.

Prefer returning the complete `KnowledgePersistenceResult` from each worker instead of reducing it to a locally invented action string. Assert its public counters directly.

### 2. Assert exact healthy-retry counters

Strengthen `test_pipeline_persistence_rolls_back_reindex_and_replays_one_committed_result`.

After the injected pre-commit failure and before or alongside replay verification, assert the exact public fields of the successful `committed` result:

- `documents_received`
- `documents_created`
- `documents_updated`
- `documents_unchanged`
- `chunks_received`
- `chunks_created`
- `chunks_updated`
- `chunks_unchanged`
- `chunks_removed`
- `embeddings_generated`

Assert timing fields only through their stable contract, such as non-negative values; do not require exact elapsed milliseconds.

The expected values must reflect the existing document-level replacement strategy:

- one existing document is updated rather than created;
- one prior chunk is removed;
- one replacement chunk and vector are created;
- no chunk is reported unchanged or updated in place;
- the prepared embedding count is reported accurately.

Retain the existing assertions proving:

- failed state rolled back;
- no persistence receipt survived the failed attempt;
- the healthy retry committed once;
- replay returned the stored result without rewriting;
- a competing stale command produced the application conflict;
- final database state contains exactly one current representation.

### 3. Correct the PR #67 verification report

After the final branch commit is pushed and CI has completed, update the existing PR #67 description.

Remove `Tests not run locally (not requested)`.

Report only checks actually observed passing, including:

- The exact required PostgreSQL/pgvector persistence result and skipped-test count.
- The final complete backend test result.
- Ruff lint result.
- Ruff formatting result.
- Mypy result.
- Application startup/import validation result.
- GitHub Actions conclusion.

If final reruns produce counts different from earlier evidence, use the newest observed results. Do not copy stale counts from this task.

Keep the PR draft unless the user separately requests ready-for-review status.

## Acceptance criteria

- [ ] The concurrency test uses a barrier or equivalent event coordination with a bounded timeout.
- [ ] Both workers are observed at the intended race boundary before release.
- [ ] Coordination occurs only once per worker and cannot block later connection acquisition.
- [ ] The concurrent scenario executes through `KnowledgePersistenceService` and the real PostgreSQL repository.
- [ ] The concurrent test asserts public persistence results rather than only a derived action string.
- [ ] The concurrent test proves one current document and one expected chunk set remain.
- [ ] The concurrent representation remains retrievable and correctly access-filtered.
- [ ] No sleep-based timing or live provider call is introduced.
- [ ] The healthy retry’s exact document, chunk, removal, and embedding counters are asserted.
- [ ] Timing counters are asserted only through stable non-negative invariants.
- [ ] Existing rollback, receipt, replay, conflict, and final-state assertions remain intact.
- [ ] Required PostgreSQL/pgvector tests complete with zero skips, xfails, or deselections.
- [ ] The complete backend suite passes.
- [ ] Ruff lint, Ruff formatting, mypy, and startup validation pass.
- [ ] GitHub Actions passes on the final pushed head.
- [ ] PR #67 reports the exact final checks and no longer claims tests were not run.
- [ ] No production source, schema, dependency, or public-interface change is introduced.

## Tests to update

Primary file:

- `apps/backend/tests/test_knowledge_persistence_integration.py`

Update these scenarios:

- `test_concurrent_duplicate_writes_leave_one_document_and_one_chunk`
- `test_pipeline_persistence_rolls_back_reindex_and_replays_one_committed_result`

Do not create parallel tests if strengthening the existing scenarios provides the required evidence.

## Verification commands

```bash
cd apps/backend

# Focused required PostgreSQL/pgvector verification; zero skips are permitted
KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED=true \
  venv/bin/python -m pytest -q -o "addopts=" --strict-markers \
  tests/test_knowledge_persistence_integration.py

# Complete backend behavior with required PostgreSQL suites
KNOWLEDGE_SOURCE_POSTGRES_REQUIRED=true \
KNOWLEDGE_PERSISTENCE_POSTGRES_REQUIRED=true \
  venv/bin/python -m pytest -q

# Static and startup verification
ruff check .
ruff format --check .
venv/bin/python -m mypy .
venv/bin/python -c "from main import app; assert app is not None"
```

After pushing, verify the final GitHub Actions run and update PR #67 with the exact observed results. Completion is not valid while the required persistence suite contains any skipped, xfailed, or deselected test.
