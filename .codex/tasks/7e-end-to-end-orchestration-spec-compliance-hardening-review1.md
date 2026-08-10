# PR 7E Follow-up — Secure Reconciliation Logging and Reload Failure Coverage

**Branch:** `feature/7e-orchestration-spec-compliance`

## Objective

Complete the remaining work required for PR 7E.

This is a targeted follow-up only. Do **not** redesign the orchestration flow that has already been implemented.

The purpose of this change is to:

1. Eliminate sensitive repository/provider/database information from reconciliation logs.
2. Preserve the original exception as the application failure cause.
3. Add deterministic tests covering repository reload failures during reconciliation.

---

# Repository state

This work builds directly on the existing PR 7E implementation.

The current implementation already:

- separates pending and running persistence
- reconciles ambiguous writes using repository reloads
- preserves committed knowledge when completion persistence fails
- sanitises logged URLs
- includes workflow coverage for unchanged and changed ingestion

Do not redesign the orchestration.

Do not modify retry behaviour.

Do not change the ingestion API.

Do not introduce new dependencies.

---

# Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `apps/backend/README.md`
- `apps/backend/assistant/application/ingestion_service.py`
- `apps/backend/tests/test_ingestion_service.py`

---

# Required implementation

## 1. Prevent sensitive exception leakage

The reconciliation code currently emits `logger.exception(...)` for several repository reconciliation failures.

These include:

- failed job-state persistence
- repository reload failures
- initialization failures
- completion reconciliation failures

This currently records the original exception message and traceback.

Repository exceptions may legitimately contain:

- SQL
- connection information
- usernames
- passwords
- provider responses
- infrastructure details
- implementation details

These must never appear in operational logs.

The original exception must still remain available through Python exception chaining.

For example:

```python
raise IngestionFailedError("Knowledge ingestion failed.") from original_exception
```

Application behaviour must remain unchanged.

---

## 2. Replace reconciliation exception logging

Replace reconciliation `logger.exception(...)` usage with structured safe logging.

The log record should contain only operational metadata, for example:

- ingestion job id
- reconciliation stage
- failure category
- exception class name
- durations already collected

Do not log:

- exception messages
- tracebacks
- SQL
- provider errors
- connection strings
- credentials
- raw URLs
- document contents
- embeddings

The logs should remain useful for production diagnostics while avoiding leakage of internal implementation details.

---

## 3. Preserve exception chaining

Secondary reconciliation failures must never replace the original repository failure.

Example:

```
update()
    raises WriteFailure

reload()
    raises RepositoryError
```

The final exception chain must still be:

```
IngestionFailedError
    caused by
WriteFailure
```

The reload failure should only produce a safe structured log entry.

---

## 4. Extend the deterministic repository

Extend the existing `FaultInjectingJobRepository`.

Do not introduce another fake repository.

Add deterministic support for failing:

```
get()
```

before durable state can be reloaded.

Support scenarios such as:

- ambiguous create followed by reload failure
- ambiguous running update followed by reload failure
- ambiguous completion update followed by reload failure

No sleeps.

No races.

No timing-based tests.

---

# Required tests

## Ambiguous create + reload failure

Repository behaviour:

- create stores the row
- create raises
- reload raises

Verify:

- original create exception remains the cause
- safe application error returned
- loader never executes
- processing never executes
- persistence never executes
- sensitive repository exception text is absent from captured logs

---

## Ambiguous running update + reload failure

Repository behaviour:

- running update raises after persistence
- reload raises

Verify:

- original running update exception remains primary
- ingestion fails safely
- downstream pipeline does not execute
- logs contain only structured reconciliation information
- repository exception text does not appear

---

## Ambiguous completion update + reload failure

Repository behaviour:

- completion update raises
- reload raises

Verify:

- original completion update exception remains primary
- no second persistence occurs
- committed knowledge is not modified
- no successful completion is returned
- sensitive repository messages are absent from logs

---

## Failed-state persistence failure

Extend the existing failed-state persistence tests.

Inject repository exception messages containing sentinel strings such as:

```
SQL SECRET
PASSWORD SECRET
CONNECTION SECRET
```

Verify these strings never appear in:

- caplog.text
- structured logging fields

---

## Reload failure logging

Verify reload failures produce:

- safe structured log entries
- ingestion job id
- reconciliation stage
- exception class name

Verify they do **not** contain:

- traceback
- SQL
- repository message
- provider message

---

# Acceptance criteria

- [ ] Reconciliation logs never expose repository exception messages.
- [ ] Reconciliation logs never expose SQL.
- [ ] Reconciliation logs never expose credentials.
- [ ] Reconciliation logs never expose provider error messages.
- [ ] Structured reconciliation logs still include operational metadata.
- [ ] The original repository exception remains the primary exception cause.
- [ ] Secondary reload failures never replace the original exception.
- [ ] Secondary failed-state persistence failures never replace the original exception.
- [ ] Deterministic reload failure coverage exists for create, running update and completion update.
- [ ] All new tests verify that sentinel repository strings never appear in captured logs.
- [ ] Existing orchestration behaviour remains unchanged.
- [ ] Existing workflow tests continue to pass.
- [ ] PostgreSQL integration tests continue to pass.
- [ ] No API changes are introduced.
- [ ] No retry behaviour changes are introduced.
- [ ] No database schema changes are introduced.

---

# Idempotency

This PR must not alter ingestion idempotency.

The existing behaviour for:

- unchanged content
- changed content
- completion reconciliation

must remain unchanged.

This work is limited to secure reconciliation logging and deterministic failure coverage.

---

# Out of scope

Do not change:

- ingestion lifecycle
- retry policy
- persistence implementation
- retrieval
- chat
- embeddings
- workflow orchestration
- database schema
- API contracts
- metrics
- URL sanitisation behaviour
- documentation except where necessary to reflect the new logging behaviour.
