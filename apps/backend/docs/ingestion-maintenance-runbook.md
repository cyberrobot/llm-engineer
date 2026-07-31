# Ingestion maintenance runbook

Ingestion maintenance is a separate CLI process. It never runs during API startup and every
command defaults to dry-run. Use `--execute` to approve mutations and `--json` for machine-readable
results.

## Data model and safety boundary

The current schema has one active `documents` row and one atomically replaced `chunks` set per
indexed document. Embeddings are the `chunks.embedding` vector column. There is no representation
version table, separate embedding table, soft-delete/archive convention, object-storage adapter,
outbox, legal-hold model, or persistent operational-audit model.

Consequently:

- active document rows, chunks, fingerprints, and file-ingestion request records are never removed;
- old persistence-result evidence is removed only in the same transaction as an eligible,
  unreferenced terminal job;
- representation cleanup commands return `not_applicable_current_schema` rather than guessing at
  versions that do not exist;
- orphan chunk cleanup is a legacy-integrity repair; foreign keys normally make its candidate count
  zero;
- structured operational logs are the audit record for maintenance runs.

## Retention configuration

| Environment variable | Default | Meaning |
| --- | ---: | --- |
| `INGESTION_COMPLETED_JOB_RETENTION_DAYS` | 90 | Completed job history |
| `INGESTION_FAILED_JOB_RETENTION_DAYS` | 180 | Failed job diagnostics |
| `INGESTION_CANCELLED_JOB_RETENTION_DAYS` | 90 | Cancelled job history |
| `INGESTION_STEP_HISTORY_RETENTION_DAYS` | 90 | Completed/failed step-attempt detail |
| `INGESTION_SUPERSEDED_REPRESENTATION_RETENTION_DAYS` | 30 | Reserved until versioned representations exist |
| `INGESTION_TEMPORARY_SOURCE_RETENTION_HOURS` | 24 | Unreferenced managed upload files |
| `INGESTION_MAINTENANCE_BATCH_SIZE` | 100 | Maximum candidates per transaction |
| `INGESTION_MAINTENANCE_MAX_BATCHES` | 20 | Maximum batches per category and run |
| `INGESTION_MAINTENANCE_LOCK_TIMEOUT_SECONDS` | 5 | Advisory-lock acquisition bound |
| `INGESTION_MAINTENANCE_STALE_JOB_GRACE_SECONDS` | 300 | Grace before missing-lease repair |
| `INGESTION_MAINTENANCE_EXECUTION_IDENTITY` | host name | Safe scheduler/operator identity in audit logs |

Negative retention and lock/grace values are rejected. Temporary-source retention, batch size, and
maximum batches must be positive. Retention boundaries are inclusive and calculated using
timezone-aware UTC timestamps.

## Commands

Run commands from `apps/backend` using the project Python environment:

```text
python -m assistant.maintenance.ingestion report --json
python -m assistant.maintenance.ingestion cleanup-jobs --dry-run
python -m assistant.maintenance.ingestion cleanup-step-history --dry-run
python -m assistant.maintenance.ingestion cleanup-superseded-representations --dry-run
python -m assistant.maintenance.ingestion cleanup-orphans --dry-run
python -m assistant.maintenance.ingestion cleanup-temp-sources --dry-run
python -m assistant.maintenance.ingestion reconcile-stale-jobs --dry-run
python -m assistant.maintenance.ingestion repair-committed-jobs --dry-run
python -m assistant.maintenance.ingestion run-all --dry-run
```

Replace `--dry-run` with `--execute` only after reviewing the report. Omitting both flags is a
dry-run. `report` is always non-destructive, even if `--execute` is supplied. Exit code `0` means
the command completed (including a safe lock-contention skip), `1` means a structured maintenance
error occurred, and `2` means configuration or process startup failed.

## Cleanup and reconciliation behavior

Terminal jobs are selected by status-specific completion cutoffs and stable `(completed_at, id)`
ordering. A job is skipped when it has worker ownership, a live lease, a running/interrupted step,
an active document/chunk reference, or a retained file-ingestion request. Candidate selection and
deletion share one transaction and row lock. Dependent step history cascades; an old, unreferenced
persistence result is deleted in the same transaction. Fingerprints and indexed data remain.

Step cleanup removes only completed/failed attempts belonging to terminal jobs. Running and
interrupted attempts remain as retry/recovery evidence. The job row retains retry count, final
failure fields, current/last completed step, and lifecycle timestamps.

Temporary cleanup scans only regular, non-symlink files matching the application-generated UUID
PDF namespace directly beneath `UPLOAD_DIR`. Files inside retention or referenced by `documents`
are preserved. The database reference is rechecked immediately before deletion. Missing files are
idempotent; storage errors retain the candidate for another run.

Stale reconciliation clears impossible ownership from queued/terminal jobs. A stale running job is
completed only when the exact persistence result, active document pointer, and complete job-owned
chunk set agree. Otherwise a valid checkpoint with an available website or managed upload source is
reset to queued while retry counts and checkpoints remain. Missing sources, invalid checkpoints,
and ambiguous committed results are reported for manual review and are not mutated.

## Locking, batching, and recovery

Each category uses a session-scoped PostgreSQL advisory lock derived from its category name. The
same destructive category cannot run twice concurrently; independent categories use independent
locks. Connection loss releases the lock. Each database batch is a short transaction using
`FOR UPDATE SKIP LOCKED`; there are no offsets and no transaction remains open during local-file
deletion, telemetry export, or between categories.

If a database batch fails, PostgreSQL rolls it back and the command reports a process error. Fix the
dependency, repeat the dry-run, then execute again. Successfully removed candidates are naturally
absent on retry. Manual-review findings contain only record type, safe identifier, reason code, and
recommended action.

## Scheduling

Create independent Railway cron services (or equivalent platform jobs) using explicit commands.
Do not schedule maintenance through API startup.

- every 15 minutes: `reconcile-stale-jobs --execute --json`
- hourly: `cleanup-temp-sources --execute --json`
- daily: `cleanup-step-history --execute --json`, then `cleanup-jobs --execute --json`
- daily: `cleanup-orphans --execute --json`
- weekly: `cleanup-superseded-representations --execute --json` (currently reports not applicable)

Use one scheduled process per command so a failure is isolated and visible. A lock-contention skip
is not a liveness failure. Alert on repeated `result="error"`, manual-review growth, or repeated
storage deletion failures.

## Operational procedures

### Safe production execution

1. Run `report --json`.
2. Run the target category in dry-run and review candidate and manual-review counts.
3. Run the category with `--execute`.
4. Verify `ingestion_maintenance_*` metrics and structured completion logs.
5. Repeat the dry-run; a converged category reports no eligible candidates.

### Queue appears stuck

1. Inspect queued/running/recoverable metrics and verify workers are healthy.
2. Run `reconcile-stale-jobs --dry-run --json`.
3. Review missing-source, checkpoint, and committed-result findings.
4. Execute reconciliation when the deterministic repairs are expected.
5. Confirm reset jobs are claimed and committed jobs are terminal.

### Upload storage is growing

1. Run `cleanup-temp-sources --dry-run --json`.
2. Confirm the count represents generated UUID PDFs outside retention, not canonical sources.
3. Execute bounded cleanup and verify storage-error counters/logs.
4. Repeat dry-run to confirm convergence.

### Multiple active representations reported

The current schema has no versioned representations. Treat such a report as evidence of a future
schema or an unsupported external writer. Stop destructive repair, inspect the canonical document
and completed ingestion jobs, and add a schema-aware repair before mutation.

### Maintenance fails

1. Inspect the structured error code and confirm the batch rolled back.
2. Confirm the category lock was released (a new dry-run should acquire it).
3. Correct configuration, database availability, or upload-directory permissions.
4. Repeat dry-run, then execute. Do not bypass a manual-review finding with direct deletion.

## Telemetry

Structured events include start, lock acquisition/contention, batch completion, manual-review,
storage error, completion, and process failure. Logs never include source bytes, document/chunk
content, embeddings, credentials, full URLs, or raw SQL.

Prometheus exports run, deleted, archived, repaired, skipped, error, manual-review, run-duration,
and batch-duration metrics. Labels are limited to maintenance category, result, and reason code;
record identifiers are never metric labels.
