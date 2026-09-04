# Backend Testing

Test observable outcomes through endpoints, public services, persisted state, files, and side effects. Use real validation, middleware, repositories, queries, constraints, transactions, and migrations where practical. Mock only true external boundaries; tests must not contact live providers, production databases, or uncontrolled networks.

Use disposable databases, temporary directories, deterministic fixtures, clocks, and IDs. Tests must clean up records, files, timers, and mocks and remain independent of execution order and uncontrolled time.

For relevant contracts, cover malformed and boundary input; authentication, authorization, ownership, roles, and tenant isolation; duplicate submissions, retries, idempotency, races, stale writes, and database enforcement; provider, database, network, timeout, cancellation, partial-completion, rollback, and cleanup failures; and persistence reload, unintended-record absence, transitions, ordering, compatibility, and resource cleanup.

Security-sensitive work must directly verify server-side validation and authorization, safe errors, audit outcomes where applicable, path traversal, upload size/signature validation, and storage/database reconciliation. A successful status alone is insufficient.
