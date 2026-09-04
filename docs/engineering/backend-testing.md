# Backend Testing

Test observable outcomes through endpoints, public services, persisted state, files, and side effects.
Use real validation, middleware, routes, services, repositories, serializers, queries, constraints,
transactions, migrations, and state management where practical. Mock only true external boundaries,
such as third-party APIs, cloud storage, or unavailable operating-system integrations; tests must not
contact live providers, production databases, or uncontrolled networks.

Use disposable migrated databases for persistence tests, temporary directories, deterministic
fictional fixtures, fixed clocks and IDs. Tests must not depend on execution order, shared mutable
state, current production state, uncontrolled time, or unseeded randomness. Clean up files, records,
timers, and mocks.

## Coverage matrix

Cover the cases relevant to the changed contract:

- happy paths and precise user-visible or persisted outcomes;
- missing, empty, malformed, mistyped, unsupported, extra, contradictory, and out-of-range input;
- invalid or expired credentials; authentication, authorization, privilege escalation, ownership,
  role, organisation, and tenant isolation; deleted or unavailable resources; unguessable access
  boundaries; and confirmation that denied operations have no side effects;
- minimum, maximum, just-outside-boundary, null, empty, single-item, and large-collection cases;
- duplicate submissions, retries, idempotency, stale requests and writes, concurrent create/update/
  delete races, and database constraints and enforcement;
- domain, provider (including malformed responses), database, storage, network, timeout,
  retry-exhaustion, cancellation, partial-completion, rollback, and cleanup failures;
- persistence after reload, record counts, absence of unintended records, immutable and omitted
  fields, valid state transitions, incomplete-operation consistency, input immutability,
  deterministic ordering where contractual, backward compatibility, and resource cleanup.

Security-sensitive flows must directly test server-side validation and authorization, safe errors,
audit outcomes where applicable, path traversal, upload size and signature validation, and
storage/database reconciliation. A successful status alone is insufficient.
