# Global Engineering Rules

## Core Principles

- Inspect and understand the repository before changing it.
- Prefer the smallest complete, backward-compatible change that satisfies the requirement.
- Reuse proven libraries and existing project abstractions before creating new ones.
- Keep each change independently reviewable, testable, deliverable, and limited to its stated scope.
- Verify externally observable behaviour and business rules, not implementation details or coverage numbers.
- Never claim a command or scenario passed unless it was actually run successfully.

## Repository Inspection and Scope

Before implementation:

1. Inspect the relevant domain models, services, repositories, factories, utilities, configuration, dependencies, conventions, and tests.
2. Identify expected behaviour, invariants, failure modes, security boundaries, callers, stored data, and public contracts.
3. Confirm prerequisite branches or earlier pull requests are present. If repository state contradicts task assumptions, stop and report the mismatch instead of recreating missing work.
4. Follow existing structure and naming unless a documented reason justifies a change.

Assume each pull request begins on a fresh feature branch. Implement only its owned scope and make dependencies on earlier work explicit. Avoid unrelated refactoring, renaming, formatting, dependency upgrades, migrations, or architecture changes. In parallel worktrees, minimise overlap in shared bootstrap, exports, migrations, and dependency-injection files.

## Design and Reuse

### Reuse order

Prefer, in order:

1. The standard library.
2. Existing project libraries and utilities.
3. Existing services, repositories, factories, ports, adapters, serializers, validators, configuration, logging, clocks, ID generators, filesystem helpers, and dependency-injection wiring.
4. When the existing stack is unsuitable, either a small local implementation for simple, non-specialised behaviour or a mature, maintained, licence-compatible library for specialised capability.

Do not introduce parallel implementations or multiple libraries for the same capability. A new dependency must provide a clear benefit, avoid duplicating the existing stack, and be documented.

### Composition and boundaries

Compose or extend stable components before adding a framework, base class, service layer, or generic abstraction. Add an abstraction only for multiple concrete uses with a clear shared contract and a net reduction in complexity.

Keep responsibilities separated:

- Domain code owns business rules and must not depend on transport, CLI parsing, database sessions, application startup, dependency-injection containers, or provider clients.
- Orchestration coordinates components without reimplementing their rules.
- Persistence stores and retrieves data without making business decisions.
- Presentation formats outcomes without calculating them.
- Integration adapters contain provider-specific types and map them to application-owned models.
- Lower-level modules must not import higher-level entry points. Avoid circular imports and startup-dependent package exports.

Keep functions and classes focused. Extract shared code when it represents the same rule, not merely similar syntax. Prefer explicit code and business-oriented names over clever or speculative abstractions. Comments should explain constraints and non-obvious decisions, not restate code. Remove dead code, temporary debugging, commented-out implementations, and unused compatibility layers.

## Domain Models and Validation

- Model important business concepts explicitly and validate them so invalid states are difficult to construct.
- Use stable string values for persisted or externally exposed enums, safe factories for mutable defaults, and clear distinctions among identifiers, schema versions, content versions, statuses, and timestamps.
- Keep domain models serializable and free of clients, repositories, sessions, credentials, environment settings, containers, and other runtime services.
- Validate external input at the owning boundary. Reject malformed, unsupported, contradictory, ambiguous, extra, or out-of-range input clearly; do not silently coerce it or ignore unsupported fields.
- Preserve useful structured validation details. Keep each rule in one authoritative location unless separate layers enforce genuinely different invariants.
- Validate identifiers before database, filesystem, shell, or provider operations.

## Determinism, Idempotency, and Concurrency

Identical inputs should produce equivalent outputs unless nondeterminism is required. Preserve meaningful ordering and keep generated ordering, filenames, reason codes, and serialization stable. Inject clocks, IDs, randomness, and external services when tests need control. Avoid locale- or environment-dependent output, memory addresses, and unnecessary current timestamps. Do not mutate caller-owned models or collections unless the public API promises mutation.

Document idempotency for ingestion, orchestration, persistence, retries, recovery, and externally triggered work. Repeated operations with the same key or business identity must not duplicate effects. Reuse existing completed or active work where appropriate, and never create a new business identity merely because an operation is retried. Protect critical guarantees with transactions, constraints, or established locking rather than only in-memory checks. Keep read-only transformations free of persistence and unrelated side effects.

Default to sequential execution. Add concurrency only for a demonstrated need, bound it, preserve deterministic output order, protect shared state, and respect cancellation and cleanup. Do not introduce workers, queues, multiprocessing, or orchestration frameworks without an explicit requirement. Account for races and duplicate execution whenever concurrent workers can process the same entity.

## Persistence and Files

- Keep storage behind established repository or data-access boundaries.
- Use transactions for changes that must succeed or fail together; verify rollback and avoid holding transactions open across slow external calls.
- Enforce critical uniqueness and integrity at the database level, and avoid unsafe read-modify-write sequences.
- Make create, update, upsert, and no-op semantics explicit. Never silently delete or overwrite data.
- Add migrations only when required, run them in tests, and keep them compatible with concurrently deployed application versions where applicable.
- Use established model serialization, stable enum values, timezone-explicit timestamps, and UTF-8 text. Never serialize runtime services, credentials, or arbitrary object state.
- Protect existing files from accidental overwrite. Use atomic writes when partial files would be harmful, create temporary files in the destination directory when atomic rename is required, and clean up artifacts after success, failure, or cancellation.
- Keep filenames safe, deterministic, and free of secrets or sensitive content.

## External Services, Configuration, and Resources

- Access providers through existing adapters; do not call provider SDKs directly from controllers, CLI commands, or domain code.
- Apply project-standard timeouts and map provider responses into application-owned types.
- Reuse the central configuration system instead of scattering environment reads. Validate configuration at startup or the owning boundary, document new settings, and do not change existing meanings without a migration plan.
- Keep secrets out of source, fixtures, logs, reports, errors, and generated files. Do not add undocumented environment-controlled behaviour.
- Manage database pools, sessions, clients, files, streams, and connections with context managers or lifecycle hooks. Reuse managed resources instead of creating one per item, avoid unmanaged global mutable resources, and clean up on every exit path.
- Do not bypass production authorisation, filtering, validation, or safety rules for tests, evaluation, administration, recovery, or background work without an explicit privileged policy.

## Errors, Failure Isolation, and Retries

- Distinguish validation errors, domain failures, infrastructure failures, and programming defects. Use focused exception types when existing ones are insufficient.
- Fail early when work cannot continue safely. Preserve causes through exception chaining and include useful, non-sensitive context such as entity IDs, field paths, file paths, and operation names.
- Never expose secrets, tokens, raw provider payloads, stack traces, or sensitive data in user-facing errors.
- Do not catch `BaseException` or convert cancellation, keyboard interruption, or process termination into ordinary failures.
- Isolate failures at the smallest meaningful unit unless atomicity is required. Preserve structured item-level failures, distinguish them from operation-level failure, expose partial success, and make stop-on-error behaviour explicit. Never silently discard failed work.
- Reuse established retry libraries and policies. Retry only plausibly transient failures, with bounded attempts and backoff, after ensuring duplicate side effects are prevented. Never retry validation, authorisation, unsupported-operation, or deterministic domain failures. Preserve the original failure after exhaustion and avoid compounded retries across layers.

## Security and Observability

- Enforce authorisation at the established service or policy boundary, including ownership, role, and tenant rules; frontend visibility and authentication alone are insufficient.
- Use least privilege. Do not construct shell commands from untrusted input or use `eval`, `exec`, unsafe deserialization, or user-controlled dynamic imports.
- Use existing logging and observability systems. Record meaningful operation boundaries, safe identifiers, statuses, durations, correlations, and failure categories with structured fields.
- Do not log credentials, tokens, cookies, connection strings, prompts, full documents, provider payloads, or other sensitive content. Avoid duplicate stack traces and noisy per-item success logs.
- Logs and metrics describe behaviour; they must not be the only record of important business state or alter the operation.

## Public Contracts and Compatibility

Treat existing public behaviour as a contract, including APIs, exports, serialized data, persisted formats, schemas, configuration and environment keys, CLI arguments and exit codes, events, integrations, and user workflows.

- Prefer additive fields, compatible defaults, optional features, adapters, and deprecation periods. Omitted options must retain existing behaviour.
- Keep exports deliberate and minimal; do not expose private helpers.
- Before changing a contract, identify consumers and stored data, add contract coverage, define a migration path, and make transition state observable.
- If compatibility cannot be preserved, document the reason, affected consumers, migration and rollout steps, rollback strategy, and removal criteria before implementation.
- For substantial changes, establish a tested baseline, separate mechanical refactoring from behavioural changes, migrate incrementally, keep each step deployable and reversible, and remove legacy code only after consumers have moved.
- A rewrite requires explicit scope, approval, parity criteria, migration tests, rollout safeguards, and evidence that incremental change is riskier or costlier.

## Testing

### Test observable behaviour

Tests must fail for realistic defects and verify results through public interfaces: endpoints, exported functions, public service methods, rendered interactions, persisted state, files, and observable side effects. Refactoring internals without changing behaviour should not break tests.

Do not test private helpers, internal variables or structure, exact internal call order, or a mock call without verifying its outcome. Never write tests merely to increase coverage or endorse the current implementation.

### Development process

For every feature or bug fix, where practical:

1. Add or update behaviour-focused tests before production code.
2. Run the new test and confirm it fails for the expected reason.
3. Implement the smallest production change.
4. Run targeted tests, the broader affected suite, integration checks, type checking, formatting, and linting using repository commands.
5. Review whether the suite catches plausible mutations such as removed validation or ownership filters, reversed comparisons, skipped transactions, duplicate creation, omitted constraints, hard-coded results, ignored provider failure, unintended field resets, and invalid state transitions.

Every bug fix needs a clearly named regression test that reproduces the defect and fails before the fix, unless automated testing is genuinely impossible and the reason is documented. Never weaken expected behaviour or assertions to accommodate an implementation.

### Test doubles and infrastructure

Do not mock the unit under test or internal application layers when realistic integration is practical. Use real validation, middleware, routes, services, repositories, serializers, queries, constraints, transactions, migrations, and state management.

Mock only true external boundaries such as email, SMS, payments, malware scanning, cloud storage, third-party APIs, or unavailable operating-system integrations. Mocks must model realistic success and failure without reproducing implementation details. Unit and integration tests must not call live providers, production databases, or uncontrolled networks.

Use disposable databases and run real migrations for persistence tests. Use temporary directories, deterministic fixtures, fixed clocks and IDs, and realistic fictional data. Tests must be independent of execution order, shared mutable state, current production state, uncontrolled time, and unseeded randomness. Clean up files, records, timers, and mocks.

### Required coverage where applicable

Cover:

- Happy paths and precise user-visible or persisted outcomes.
- Missing, empty, malformed, mistyped, unsupported, extra, contradictory, and out-of-range input.
- Authentication, invalid or expired credentials, roles, ownership, tenant boundaries, deleted or unavailable resources, privilege escalation, and confirmation that denied actions have no side effects.
- Minimum, maximum, just-outside-boundary, null, empty, single-item, and large collection cases.
- Duplicate submissions, retries, stale requests, idempotency, concurrent creation or updates, deletion races, and database enforcement.
- Domain, database, storage, network, timeout, malformed-provider-response, partial-completion, retry-exhaustion, cancellation, rollback, and cleanup failures.
- Persistence after reload, record counts, absence of unintended records, immutable and omitted fields, valid state transitions, and incomplete-operation consistency.
- Input immutability, ordering, backward compatibility, and resource cleanup where contractual.

Security-sensitive flows must directly test server-side validation, ownership and organisation isolation, unguessable access boundaries, safe errors, audit events, path traversal, upload size and signature validation, and storage/database reconciliation where relevant. A successful status alone is insufficient.

### Assertions, UI, and end-to-end tests

Use precise assertions for status or result type, response fields, persisted values, ownership, counts, transitions, timestamps, immutable fields, events, side effects, and user-visible output. Avoid truthiness-only checks, “no exception” checks, mock-call-only checks, status-only checks, or broad snapshots. Snapshots may supplement but never replace semantic assertions. Avoid brittle complete exception-string or log assertions when structured data is available.

UI tests should query by accessible role, label, name, or visible text and simulate real keyboard and pointer interactions. Verify loading, empty, validation, error, disabled, retry, navigation, persistence, duplicate-click, accessibility, and submission states. Do not query implementation-specific structure or mock away the application layer.

Use a small number of end-to-end tests for critical journeys such as authentication, incident creation and editing, draft recovery, attachments, access controls, state transitions, deletion and recovery, exports, and failure recovery. Verify final user-visible and persisted outcomes.

Test names must state the scenario, action, and expected outcome. Factories should provide valid defaults with focused overrides; avoid large irrelevant fixtures or fixed IDs that can collide.

### Prohibited test practices

Never:

- Delete a test solely because a change breaks it.
- Skip or disable a failure without a documented valid reason, or commit focused tests such as `.only`.
- Loosen a meaningful assertion, replace it with a snapshot, hide failures, or mock away the behaviour under test.
- Change production code solely for test convenience when realistic setup is possible.
- Change expected behaviour merely to match the current implementation.

If a test appears wrong, confirm intended behaviour and explain the correction.

## Verification and Documentation

Run the repository-defined commands relevant to the change:

- Targeted and broader affected tests, plus integration or end-to-end suites where applicable.
- Type checking, linting, and formatting checks.
- Database migrations and persistence checks when storage changes.
- Manual verification of changed public entry points where practical.

If a command cannot run, report the exact command, reason, observed error, and remaining risk. Do not declare completion while relevant checks fail.

Update documentation for public APIs, configuration, operations, persisted formats, exit codes, side effects, failure and retry behaviour, idempotency, compatibility, recovery, and migration procedures. Keep examples accurate, never describe planned behaviour as implemented, and record justified deviations.

## Completion Report

For implementation work, report:

1. Branch and files changed.
2. Behaviour and tests added or updated, including the initial expected failure where practical.
3. Production changes and important design or reuse decisions.
4. Migrations, configuration, dependencies, and public-interface changes.
5. Commands actually run and their final results.
6. Known limitations, unverified behaviour, repository mismatches, deviations, and remaining risks.

Completion requires defined behaviour, meaningful regression coverage, passing relevant tests, type checks, and linting, verified security and persistence boundaries where applicable, and explicit disclosure of remaining limitations.

## GitHub Branches and Pull Requests

Create a new branch only after fetching the latest remote state. Base it on current `origin/main` with `git switch --no-track -c <branch> origin/main`; never use a stale local branch or configure a feature branch to track the default branch. On first push, use `git push --set-upstream origin <branch>` and verify it tracks the same-named remote branch.

Sandboxed `gh auth status` may not see host keychain credentials. Before requesting login, run `gh auth status` and `gh repo view --json nameWithOwner,defaultBranchRef` with the necessary host permission. Ask for `gh auth login` only if those checks fail outside the sandbox.

When commit, push, and pull-request creation are requested:

1. Inspect `git status -sb` and the diff.
2. Stage only in-scope files; leave unrelated work untouched unless the user confirms inclusion.
3. Commit with a concise description of the complete change.
4. Push the feature branch to the same-named remote branch with upstream tracking; never push it to the default branch.
5. Open a draft pull request against the repository default branch unless the user requests another base or ready-for-review status.
6. Use a Markdown body with real newlines describing the change, impact, and checks that actually passed.
7. Verify and report branch, commit, base, URL, draft status, and deliberately uncommitted files.
