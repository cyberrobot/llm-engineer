# PR 11H — Admin Operations API Expansion for Dashboard

## Repository state

Expected branch:

`feature/11h-admin-operations-dashboard-api`

Base branch:

Latest `main`.

Worktree:

Backend worktree.

Dependencies:

- PR 10A — Operations Domain and Administration API Foundation
- PR 10B — Health, Readiness, Diagnostics, Runtime Configuration and Metrics
- PR 10C — Remaining Operations and Administration Capabilities
- PR 11B — Knowledge Source Management
- PR 11B1 — Knowledge Source Hardening
- PR 11F — Administrator Assistant Management API
- PR 11G — Assistant Behaviour, Publishing and Preview
- Existing ingestion observability and background-worker infrastructure

The current repository already contains the operations administration API, including:

- cache administration
- maintenance mode
- audit browsing
- operational job browsing
- operations summary
- health integration

Do not recreate these capabilities.

---

## Read first

- `AGENTS.md`
- `apps/backend/AGENTS.md`
- `docs/architecture/repository-map.md`
- `docs/architecture/dependency-rules.md`
- `apps/backend/operations/api/administration_router.py`
- `apps/backend/operations/api/models.py`
- `apps/backend/operations/application/administration.py`
- `apps/backend/operations/domain/administration.py`
- `apps/backend/operations/infrastructure/`
- `apps/backend/assistant/api/ingestion_status.py`
- `apps/backend/assistant/application/ingestion_observability.py`
- existing assistant administration repositories/services
- existing knowledge-source repositories/services
- existing ingestion-job repositories

Inspect the current repository before implementation.

Do not assume class names, repository methods or response models match this specification.

---

## Primary change area

Backend Operations/Admin read APIs.

This PR extends the existing Operations API to expose the additional operational data required by the administrator dashboard.

It must **not** introduce a second dashboard-specific backend subsystem.

---

## Canonical implementation

Reuse existing implementations for:

- OperationsSummaryService
- operations summary endpoint
- operational jobs endpoint
- ingestion observability
- assistant administration queries
- knowledge source queries
- dependency injection
- administrator authorization
- Pydantic response models
- repository abstractions

Prefer extending existing models over introducing parallel models.

---

## Relevant symbols

Codex must identify the current implementation before making changes.

Expected concepts include:

- OperationsSummaryService
- OperationsSummaryResponse
- JobOperationsService
- OperationalJobResponse
- ingestion operational status repository/service
- assistant administration service
- assistant repository
- knowledge source repository
- operations dependency registration

Do not duplicate abstractions.

---

## Expected change surface

Expected changes should remain inside:

- `apps/backend/operations/application`
- `apps/backend/operations/domain`
- `apps/backend/operations/api`
- `apps/backend/operations/infrastructure`
- operations dependency registration
- backend tests
- operations documentation

Small additions to assistant or knowledge query services are acceptable where efficient aggregate queries do not already exist.

Database migrations are **not expected**.

---

## Excluded

Do not implement:

- dashboard frontend
- charts
- widgets
- assistant management
- knowledge management
- ingestion execution
- retry logic
- authentication
- publishing
- evaluation
- new metrics
- new maintenance functionality
- new cache functionality
- analytics
- unrelated refactoring

---

## Unknowns Codex must verify

Before implementation verify:

- current OperationsSummaryService implementation
- current summary response model
- assistant publication model
- knowledge-source lifecycle model
- ingestion operational-status abstraction
- whether efficient aggregate repository queries already exist
- whether operational jobs already expose assistant/source identifiers
- existing dependency-unavailable behaviour
- existing generated timestamp conventions

If repository state differs materially, implement the smallest equivalent solution rather than recreating previous work.

---

# Objective

Expand the existing administrator Operations API so the Admin Dashboard can render its operational overview using a single authenticated API.

The dashboard should not call:

- internal ingestion endpoints
- Prometheus
- Redis
- database queries
- multiple unrelated administration endpoints

The Operations bounded context should compose the existing application services into one operational summary.

---

# Current architecture

The Operations API already exposes:

- health
- maintenance
- cache summary
- operational jobs
- audit summary

The ingestion subsystem already exposes authoritative operational state including:

- queued jobs
- running jobs
- recoverable jobs
- oldest queued age
- observed workers

Assistant management and Knowledge Source management already expose their own repositories and services.

This PR composes those existing read models.

Target architecture:

```
Admin Dashboard

        │

        ▼

GET /api/admin/operations/summary

        │

        ▼

OperationsSummaryService

 ├── Health

 ├── Maintenance

 ├── Cache

 ├── Audit

 ├── Operational Jobs

 ├── Ingestion Observability

 ├── Assistant Summary

 └── Knowledge Summary
```

---

# Required implementation

## Expand Operations Summary

Extend the existing endpoint:

```
GET /api/admin/operations/summary
```

Do not introduce a dashboard-specific endpoint.

Existing fields must remain.

Add dashboard aggregates for:

### Assistants

- total
- published

using the authoritative assistant status model.

### Knowledge Sources

- total
- enabled
- failed (only if an authoritative failure state already exists)

### Ingestion

Expose:

- queued
- running
- recoverable
- failed
- oldest queued age
- workers observed

Reuse the existing ingestion operational-status implementation.

Do not duplicate queue calculations.

### Existing sections

Retain:

- health
- maintenance
- cache
- jobs
- audit

---

## Response metadata

Expose a server-generated timestamp indicating when the summary was produced.

Use the existing Operations response conventions.

---

## Operational Jobs

Extend the existing operational jobs response where useful for the dashboard.

Where available expose safe operational context such as:

- assistant id
- source id
- job type

Do not expose secrets or implementation details.

Preserve:

- pagination
- filtering
- status values

---

## Efficient aggregation

The summary endpoint must use efficient aggregate queries.

Avoid:

- loading all assistants
- loading all sources
- loading all jobs

Use repository-level count queries where appropriate.

---

## Dependency behaviour

Reuse existing dependency-unavailable behaviour.

Do not silently convert failures into zero values.

---

## Authorization

Continue using the existing Operations administrator authorization.

Do not expose dashboard data through:

- public APIs
- internal ingestion APIs
- unauthenticated endpoints

---

## API compatibility

Existing consumers must continue working.

This PR should only add fields.

Do not rename existing fields.

Do not change existing endpoint routes.

---

## Documentation

Update backend operations documentation describing:

- expanded summary contract
- assistant summary
- knowledge summary
- ingestion operational summary
- worker observation semantics

---

# Idempotency

This PR introduces read-only API enhancements.

Repeated requests must:

- have no side effects
- not mutate state
- not create audit records beyond existing read behaviour
- return consistent aggregates for the current repository state

---

# Acceptance criteria

- [ ] Existing Operations Summary endpoint remains unchanged apart from additive fields.
- [ ] Existing clients remain compatible.
- [ ] Summary exposes generated timestamp.
- [ ] Summary exposes assistant totals.
- [ ] Summary exposes published assistant count.
- [ ] Summary exposes knowledge-source totals.
- [ ] Summary exposes enabled knowledge-source count.
- [ ] Summary exposes authoritative failed knowledge-source count where available.
- [ ] Summary exposes queued ingestion jobs.
- [ ] Summary exposes running ingestion jobs.
- [ ] Summary exposes recoverable ingestion jobs.
- [ ] Summary exposes failed ingestion jobs.
- [ ] Summary exposes oldest queued age.
- [ ] Summary exposes workers observed.
- [ ] Existing cache summary remains.
- [ ] Existing audit summary remains.
- [ ] Existing maintenance summary remains.
- [ ] Existing health summary remains.
- [ ] Existing operational job filtering continues working.
- [ ] Operational job responses expose additional safe dashboard context where available.
- [ ] Summary aggregation uses efficient repository queries.
- [ ] No internal ingestion endpoint is required by the frontend.
- [ ] No public endpoint exposes operational information.
- [ ] No duplicate dashboard backend is introduced.
- [ ] No regressions are introduced.

---

# Tests

Add or update tests covering:

- operations summary
- generated timestamp
- assistant aggregates
- knowledge aggregates
- ingestion aggregates
- queue age
- workers observed
- failed jobs
- zero-state behaviour
- dependency unavailable
- authorization
- operational jobs filtering
- pagination
- regression coverage

Use real application services where practical.

Mock only external dependencies.

---

# Verification

Run the smallest relevant verification first.

```bash
npm run test:api

cd apps/backend

python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```

Run any repository-specific integration tests affected by the changes.

Report any verification that could not be executed.
