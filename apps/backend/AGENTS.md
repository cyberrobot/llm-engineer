# Backend Engineering Rules

## Repository Navigation

Read the root `AGENTS.md` and start with the owning bounded context; load the architecture documents
only under its conditional-read policy. Inspect only the layers participating in the requested behaviour:

- `assistant/domain/` for assistant, document, ingestion, citation, and evaluation rules.
- `assistant/application/` and `assistant/application/ports/` for use-case orchestration and
  application-owned integration contracts.
- `assistant/api/` and `assistant/schemas/` for HTTP validation and transport mapping.
- `assistant/infrastructure/` for assistant repositories, ingestion adapters, and vector stores.
- `admin_auth/` or `operations/` for their respective bounded contexts.
- `core/`, `infrastructure/`, and `shared/` only for genuinely shared runtime concerns.
- `tests/` for the focused behavioural and persistence coverage matching the changed boundary.

Follow imports, dependency factories, repository contracts, migrations, and callers outward from
the primary change area. Do not enumerate all backend files or inspect every bounded context by
default. Read `main.py`, shared router registration, database bootstrap, migrations, or provider
factories only when the change affects those composition or public-contract boundaries.

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

Test observable behaviour through public boundaries. Cover the happy path and the boundary,
authorization, persistence, idempotency/concurrency, and failure cases relevant to the changed
contract. Use real application layers and disposable migrated databases when practical; mock only
true external boundaries. Use `docs/engineering/backend-testing.md` when the task is security-,
persistence-, ingestion-, concurrency-, provider-, or failure-mode-heavy.

## Verification

Run the narrowest affected tests first and the broader relevant suite before completion. For complete
backend verification when warranted, run from `apps/backend`:

```sh
python -m pytest
ruff check .
ruff format --check .
python -m mypy .
```

Report any command that cannot run rather than claiming success.
