# Backend Engineering Rules

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

## Backend Testing

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
