PR 11I — Evaluation Admin API Exposure

Repository state

Expected branch:

feature/11i-evaluation-admin-api-exposure

Base branch:

Latest main.

Worktree:

Backend worktree.

Dependencies:

* Existing Evaluation Framework
* Existing Evaluation Runner
* Existing evaluation dataset loading
* Existing evaluation report persistence
* Existing evaluation baseline/comparison functionality
* PR 11E — Administrator Authentication API
* PR 11F — Administrator Assistant Management API
* PR 11G — Assistant Behaviour, Publishing and Preview
* PR 11H — Admin Operations API Expansion for Dashboard

The repository already contains a mature evaluation subsystem under:

apps/backend/assistant/evaluation/

It already owns:

* evaluation datasets
* retrieval evaluation
* answer evaluation
* evaluation runs
* aggregate summaries
* report serialization
* report loading
* baseline comparison/regression logic
* CLI execution
* evaluation-specific validation and error contracts

Do not recreate this functionality inside the API layer.

The existing evaluation package currently provides no HTTP API and no database persistence.

⸻

Read first

* AGENTS.md
* apps/backend/AGENTS.md
* docs/architecture/repository-map.md
* docs/architecture/dependency-rules.md
* apps/backend/assistant/evaluation/README.md
* apps/backend/assistant/evaluation/models.py
* apps/backend/assistant/evaluation/runner.py
* apps/backend/assistant/evaluation/dataset_loader.py
* apps/backend/assistant/evaluation/reporting.py
* apps/backend/assistant/evaluation/comparison.py
* apps/backend/assistant/evaluation/cli.py
* apps/backend/assistant/evaluation/__init__.py
* apps/backend/assistant/api/assistant_admin.py
* apps/backend/assistant/api/dependencies.py
* apps/backend/admin_auth/
* existing admin router registration
* existing admin error-response conventions
* existing evaluation tests

Inspect the current repository before implementation.

Do not assume symbols or file names beyond the existing public evaluation contracts.

⸻

Primary change area

Administrator-facing Evaluation API.

This PR exposes the existing evaluation framework through authenticated backend HTTP endpoints suitable for a later Admin UI.

The API is an adapter over the existing evaluation subsystem.

It must not become a second evaluation implementation.

⸻

Canonical implementation examples

Reuse existing implementations for:

* EvaluationRunner
* EvaluationRun
* EvaluationRunOptions
* EvaluationDataset
* evaluation dataset loading and validation
* evaluation report serialization/loading
* evaluation comparison
* baseline regression evaluation
* production retrieval service
* production answer/chat service
* assistant dependency factories
* administrator authentication
* trusted-admin-origin protection
* Pydantic request/response models
* existing structured API error conventions

The CLI is useful as a behavioural reference for translating administrator requests into existing evaluation functionality.

Do not invoke the CLI from the API.

Call the underlying application/evaluation services directly.

⸻

Relevant symbols

Codex must identify the current implementation before changing it.

Expected concepts include:

* EvaluationRunner
* EvaluationRun
* EvaluationRunOptions
* EvaluationDataset
* EvaluationSummary
* EvaluationCaseResult
* load_evaluation_dataset
* evaluation report load/save functions
* evaluation comparison models/functions
* baseline regression configuration/results
* retrieval service factory
* chat/answer service factory
* require_administrator_role
* require_trusted_admin_origin
* administrator router registration

Prefer existing public evaluation exports where suitable.

Do not duplicate evaluator calculations inside schemas, routers, or services.

⸻

Expected change surface

Expected changes should remain primarily inside:

* apps/backend/assistant/api/
* apps/backend/assistant/schemas/
* apps/backend/assistant/application/ where an HTTP-facing orchestration service is warranted
* apps/backend/assistant/api/dependencies.py
* backend router registration
* apps/backend/tests/
* evaluation/admin API documentation

Small changes to:

apps/backend/assistant/evaluation/

are acceptable only where an existing reusable operation needs a clean application-facing boundary.

Database migrations are not expected.

Do not introduce database persistence for evaluation runs in this PR.

⸻

Excluded areas

Do not implement:

* Admin frontend
* charts
* evaluation dataset editing
* evaluation dataset upload
* arbitrary filesystem browsing
* arbitrary report paths supplied by clients
* arbitrary dataset paths supplied by clients
* database persistence for evaluation runs
* evaluation scheduling
* background workers
* queues
* concurrent evaluation execution
* new evaluation metrics
* LLM-as-a-judge evaluation
* prompt experimentation
* A/B testing
* automatic publishing
* automatic rollback
* CI evaluation workflows
* public evaluation endpoints
* changes to production retrieval semantics
* changes to production answer generation
* unrelated refactoring

⸻

Unknowns Codex must verify

Before implementation verify:

* exact dataset repository/location conventions
* exact report persistence location and filename conventions
* whether report discovery/listing already exists
* exact evaluation comparison API
* exact baseline regression options
* whether evaluation reports currently include generated answer text
* whether retrieved content can be excluded through existing run options
* current administrator API error contract
* current router registration pattern
* current retrieval/chat dependency factories
* whether provider resources require explicit cleanup
* whether evaluation execution is safe to perform synchronously inside the existing FastAPI request lifecycle
* whether a server-managed evaluation/report directory configuration already exists

If repository state differs materially from this specification, preserve the intent using the smallest compatible implementation.

Do not invent parallel functionality merely to match names in this document.

⸻

Objective

Expose the existing evaluation framework through a secure administrator HTTP API so a later Admin Evaluation UI can:

* discover available evaluation datasets
* inspect dataset metadata
* execute an evaluation
* inspect the resulting run and metrics
* discover persisted evaluation reports
* inspect a persisted report
* compare an evaluation run/report against a baseline where the existing comparison framework supports it

All evaluation calculations must remain owned by the existing evaluation subsystem.

The API layer is responsible only for:

* authentication and authorization
* safe resource selection
* request validation
* orchestration
* response mapping
* HTTP error mapping

⸻

Current architecture

The existing evaluation subsystem already supports approximately:

Evaluation Dataset
        │
        ▼
EvaluationRunner
        │
        ├── Production RetrievalService
        │
        └── Production ChatService
        │
        ▼
EvaluationRun
        │
        ├── Case Results
        ├── Retrieval Metrics
        ├── Answer Metrics
        └── Evaluation Summary
        │
        ▼
Optional JSON Report
        │
        ▼
Baseline Comparison

The existing CLI currently provides the operational entry point.

Target architecture:

Admin Evaluation UI
        │
        ▼
/admin/evaluation/*
        │
        ▼
Evaluation Admin API
        │
        ▼
Evaluation Application Boundary
        │
        ├── Dataset Loader
        ├── EvaluationRunner
        ├── Report Loader/Writer
        └── Comparison
        │
        ▼
Existing Evaluation Domain

The HTTP boundary must not contain evaluation calculations.

⸻

Required implementation

Administrator Evaluation API

Add an administrator-only API namespace:

/admin/evaluation

Follow the existing backend API registration conventions.

Every route requires administrator authentication.

Every endpoint that causes evaluation execution or writes a report must additionally use the existing trusted-admin-origin protection used by other administrator mutation/action endpoints.

Do not expose any evaluation endpoint publicly.

⸻

Evaluation dataset discovery

Add:

GET /admin/evaluation/datasets

Return the repository-managed evaluation datasets that administrators are allowed to execute.

Expose safe metadata such as:

* identifier
* name
* version
* schema version
* case count

Where available without reimplementing dataset logic, useful metadata may also include:

* number of source-evaluable cases
* number of answer-evaluable cases

Do not return filesystem paths.

Ordering must be deterministic.

⸻

Evaluation dataset detail

Add:

GET /admin/evaluation/datasets/{dataset_id}

Return dataset metadata and case definitions needed by the Admin UI.

Dataset identity must be server-controlled.

The API must not accept an arbitrary filesystem path.

Safe case information may include:

* case id
* question
* expected source IDs
* expected answer fragments
* prohibited answer fragments

Do not expose credentials, provider configuration, prompts, retrieved production content, or unrelated runtime configuration.

If the existing dataset model contains fields that should not be exposed administratively, map to an explicit response schema rather than serializing the model indiscriminately.

Unknown datasets return a structured 404.

Malformed or unsupported repository-managed datasets must return a safe structured error rather than a stack trace.

⸻

Run an evaluation

Add:

POST /admin/evaluation/runs

The request must identify a server-known dataset by identifier.

Do not accept arbitrary dataset paths.

Support the safe subset of existing EvaluationRunOptions useful to the Admin UI.

At minimum evaluate whether the existing framework can safely expose:

* retrieval K
* continue/stop on case error
* require complete expected-source recall
* answer comparison options
* citation requirements

Defaults must match the existing evaluation runner rather than establishing a second set of defaults.

Do not expose:

* credentials
* provider API keys
* environment overrides
* arbitrary prompts
* arbitrary service configuration
* arbitrary filesystem destinations

Execution must use the same production retrieval and answer-service composition already used by the evaluation runner/CLI.

Do not reconstruct retrieval or generation logic in the API.

⸻

Evaluation run response

Return the authoritative EvaluationRun result mapped through an explicit API response model.

The response must make the following usable by the Admin UI:

* run ID
* dataset name
* dataset version
* run status
* started timestamp
* completed timestamp
* duration where represented
* configuration snapshot
* aggregate summary
* case status counts
* retrieval metrics
* answer metrics
* case results
* safe diagnostics
* safe execution error type/category

Preserve the evaluation subsystem’s existing status semantics.

Do not reinterpret:

* passed
* failed
* error
* skipped
* completed

inside the API layer.

⸻

Sensitive evaluation content

Retrieved chunk content must remain excluded by default.

The API must not expose:

* credentials
* provider request/response payloads
* stack traces
* database connection information
* environment variables
* internal prompts unless already explicitly part of an approved administrator contract

Review whether generated answers are currently present in EvaluationRun.

If generated answer text is exposed by the evaluation model, Codex must determine whether it is necessary for the administrator evaluation workflow.

Prefer the minimum useful exposure.

Do not accidentally broaden existing evaluation-report sensitivity merely because the domain model is serializable.

⸻

Report persistence

Reuse the existing evaluation report persistence implementation.

The API may support requesting persistence of a successful or terminal evaluation run using a simple server-controlled option such as:

{
  "persist_report": true
}

The client must not supply:

* absolute paths
* relative filesystem paths
* filenames containing traversal components
* arbitrary report directories

The server chooses the report destination using the existing configured/report convention.

If the repository has no safe server-controlled report directory convention, introduce the smallest configuration needed rather than exposing paths through the HTTP contract.

Do not silently overwrite an existing report.

⸻

Evaluation report discovery

Where report persistence is already suitable for discovery, add:

GET /admin/evaluation/runs

or the smallest equivalent resource naming consistent with the existing API.

Return persisted evaluation reports in deterministic newest-first ordering where reliable timestamps exist.

Support bounded pagination using established project conventions.

Expose summary metadata without loading unnecessary retrieved content.

Expected metadata includes:

* run ID
* dataset name
* dataset version
* status
* started/completed timestamps
* summary metrics
* report schema version

Do not return filesystem paths.

If the existing report layer has no safe discovery abstraction, add a small report repository/index abstraction over the existing server-managed report directory rather than placing directory traversal inside the router.

Do not introduce database persistence merely to implement listing.

⸻

Evaluation report detail

Add:

GET /admin/evaluation/runs/{run_id}

for persisted reports where supported.

Resolve the run through server-controlled report discovery.

Do not turn run_id into a caller-controlled path.

Return 404 for an unknown run.

Reject malformed or unsupported report schema versions through safe structured API errors.

Use the existing report loader and validation.

⸻

Baseline comparison

Expose existing comparison/regression functionality where it is already supported by the evaluation framework.

Preferred endpoint:

POST /admin/evaluation/comparisons

Request:

* candidate run ID
* baseline run ID
* supported existing comparison/regression options where appropriate

Both IDs must resolve to server-managed evaluation reports.

Do not accept report paths.

Return the existing comparison result mapped into a stable API schema.

Expose useful information such as:

* compatibility
* aggregate deltas
* regression status
* regression reasons
* affected cases where represented by the existing comparison model

Do not implement new comparison algorithms in this PR.

If the current comparison subsystem supports a materially different contract, adapt the endpoint to it rather than creating duplicate semantics.

⸻

Error mapping

Map known evaluation failures into stable administrator API errors.

Distinguish at least:

* dataset not found
* malformed dataset
* unsupported dataset schema
* invalid evaluation options
* evaluation bootstrap failure
* evaluation run failure
* report persistence failure
* report not found
* malformed report
* unsupported report schema
* incompatible comparison
* authorization failure

Do not expose raw exception text when it may contain sensitive configuration or provider details.

Preserve exception causes internally for diagnostics/logging where existing conventions support this.

Unexpected programming errors must remain observable server errors rather than being converted into fake evaluation results.

⸻

Provider and resource cleanup

Reuse existing production service lifecycle behaviour.

If the CLI currently performs explicit provider/client cleanup, ensure HTTP execution does not leak equivalent resources.

Do not create unmanaged provider clients per case.

Prefer existing application dependency factories and managed service lifetimes.

⸻

Execution model

Keep evaluation execution synchronous in this PR unless the existing framework already provides an asynchronous execution abstraction.

Do not introduce:

* queues
* workers
* polling
* background jobs
* job persistence

merely because evaluation may become expensive.

If synchronous request execution has an established backend timeout limitation, document it as a known constraint.

A later PR may introduce asynchronous evaluation execution if operational need justifies it.

⸻

Concurrency

Do not add custom concurrency.

The existing EvaluationRunner executes dataset cases sequentially; preserve that behaviour.

Concurrent administrator HTTP requests are separate evaluation runs and must not share mutable run state.

Report filenames/run IDs must retain their existing collision protections.

⸻

Authorization

All evaluation APIs must require:

require_administrator_role

Any endpoint that:

* starts evaluation execution
* persists a report
* otherwise causes server-side action

must also require:

require_trusted_admin_origin

or the repository’s current equivalent.

Read endpoints must follow the established administrator read-security policy.

Authentication alone must not be replaced with frontend-only protection.

⸻

API compatibility

This PR is additive.

Do not change:

* public assistant APIs
* existing admin assistant APIs
* operations APIs
* evaluation CLI arguments
* evaluation report schema
* evaluation dataset schema
* existing evaluation metric semantics
* existing evaluation defaults

The CLI must continue working.

Existing evaluation report files must remain loadable.

⸻

Logging and observability

Use existing structured logging.

Evaluation API logs may include safe values such as:

* run ID
* dataset identifier
* evaluation status
* case count
* duration
* report persistence outcome

Do not log:

* prompts
* generated answers
* retrieved chunk content
* provider payloads
* API keys
* tokens
* database URLs
* full dataset contents

Avoid per-case success logging unless the existing evaluation subsystem already requires it.

⸻

Documentation

Update relevant backend documentation describing:

* evaluation administrator API
* authentication requirements
* dataset discovery
* evaluation execution
* run/result semantics
* report persistence
* report discovery
* comparison behaviour
* default sensitive-content handling
* synchronous execution limitation
* safe error behaviour

Do not describe asynchronous execution or database-backed history as implemented.

⸻

Idempotency

Read endpoints are side-effect free.

Repeated:

GET /admin/evaluation/datasets
GET /admin/evaluation/datasets/{dataset_id}
GET /admin/evaluation/runs
GET /admin/evaluation/runs/{run_id}

must not modify evaluation state.

Starting an evaluation is intentionally a new execution:

POST /admin/evaluation/runs

Repeated independent POST requests may produce distinct evaluation run IDs because each represents a new execution.

However:

* one request must create at most one evaluation run
* one request must persist at most one report when persistence is requested
* report persistence must never silently overwrite another report
* retries caused internally by the HTTP/application layer must not cause duplicate report writes

Comparison requests are read-only and must not mutate either report.

⸻

Acceptance criteria

* A numbered administrator Evaluation API is added without creating a second evaluation implementation.
* Every evaluation endpoint requires administrator authentication.
* Evaluation execution requires trusted administrator origin protection.
* Available repository-managed datasets can be listed.
* Dataset listing has deterministic ordering.
* Dataset metadata exposes name, version, schema version and case count.
* A repository-managed dataset can be inspected by safe server-controlled identifier.
* Arbitrary dataset filesystem paths cannot be supplied through the API.
* Unknown datasets return a structured 404.
* Malformed datasets return safe structured errors.
* Unsupported dataset schema versions return safe structured errors.
* An administrator can execute an existing evaluation dataset through the API.
* Evaluation execution uses the existing EvaluationRunner.
* Evaluation execution uses the existing production retrieval and answer-service composition.
* Existing EvaluationRunOptions defaults remain authoritative.
* Invalid evaluation options are rejected before execution.
* The run response exposes aggregate retrieval metrics.
* The run response exposes aggregate answer metrics.
* The run response exposes case statuses and safe diagnostics.
* Existing evaluation status semantics are preserved.
* Retrieved chunk content is excluded by default.
* Secrets, provider payloads and stack traces are never exposed.
* Evaluation results may be persisted through the existing report implementation using only a server-controlled destination.
* Clients cannot choose arbitrary report filesystem paths.
* Existing reports are never silently overwritten.
* Persisted reports can be discovered if the existing report architecture supports safe discovery.
* Persisted run listing is bounded/paginated.
* Persisted run ordering is deterministic.
* A persisted evaluation run can be retrieved by safe run identifier.
* run_id cannot be used for path traversal.
* Unsupported report schema versions are rejected safely.
* Existing baseline/comparison functionality is exposed without reimplementing comparison rules.
* Comparison operates only on server-managed reports.
* Comparison requests have no side effects.
* Provider/client resources are cleaned up correctly.
* Concurrent HTTP evaluations do not share mutable run state.
* Existing evaluation CLI behaviour remains unchanged.
* Existing evaluation dataset/report schemas remain unchanged.
* Existing public and administrator APIs remain compatible.
* No database migration is introduced.
* No background evaluation infrastructure is introduced.
* No new evaluation metrics are introduced.
* No regression is introduced.

⸻

Tests to add or update

Add focused backend tests covering the administrator HTTP boundary and existing evaluation integration.

Expected locations:

* apps/backend/tests/
* existing evaluation test modules where reusable evaluation behaviour requires additional coverage

Cover:

Authorization

* unauthenticated dataset listing is rejected
* non-administrator access is rejected
* administrator reads succeed
* evaluation execution requires trusted administrator origin
* denied execution causes no evaluation/report side effect

Dataset listing

* available datasets are returned
* deterministic ordering
* correct metadata
* empty configured dataset directory
* malformed dataset handling
* unsupported schema handling
* filesystem paths are not exposed

Dataset detail

* known dataset
* unknown dataset
* case metadata mapping
* malformed identifier
* path traversal attempts
* no arbitrary path access

Evaluation execution

* successful run
* runner defaults
* supported options
* invalid retrieval K
* contradictory/unsupported options
* deterministic evaluation failure
* case execution error
* skipped cases
* bootstrap/provider failure
* safe error mapping
* no duplicated retrieval/generation implementation
* retrieved content excluded by default

Use realistic fake external/provider boundaries where necessary.

Do not call live OpenAI services.

Report persistence

* persistence disabled
* persistence enabled
* server-controlled destination
* unique report creation
* existing file collision
* persistence failure
* no arbitrary path accepted
* no path traversal

Report listing/detail

Where implemented:

* empty report directory
* persisted runs
* deterministic ordering
* pagination boundaries
* unknown run
* malformed report
* unsupported schema
* path traversal
* response does not expose report filesystem paths

Comparison

Where exposed:

* compatible candidate and baseline
* regression
* improvement/no regression
* incompatible runs
* missing baseline
* missing candidate
* malformed report
* unsupported schema
* comparison has no persistence side effects

Resource behaviour

* service/provider resources are cleaned up after success
* resources are cleaned up after evaluation failure
* separate HTTP requests do not share run state

Regression coverage

Verify existing:

* evaluation unit tests
* CLI behaviour
* report loading
* report persistence
* comparison logic
* admin authentication
* assistant APIs

remain unaffected.

Test externally observable behaviour through the API where practical.

Do not duplicate evaluator unit tests in the HTTP test suite.

⸻

Verification commands

Run the smallest relevant tests first, then the broader backend suite.

cd apps/backend
python -m pytest tests -k "evaluation and admin"
python -m pytest
ruff check .
ruff format --check .
python -m mypy .

Then from the repository root:

npm run test:api

Also run the existing evaluation CLI tests and any dedicated evaluation test modules discovered during implementation.

If repository-defined commands differ from these examples, use the current repository commands.

Report any command that could not be executed and the remaining risk.
