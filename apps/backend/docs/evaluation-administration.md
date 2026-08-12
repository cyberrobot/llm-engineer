# Evaluation administration

The administrator evaluation API exposes the existing evaluation framework at
`/admin/evaluation`. It is an HTTP adapter over the canonical dataset loader,
`EvaluationRunner`, report serializer/loader, and comparison implementation; it does not calculate
metrics or implement separate evaluation semantics.

Every endpoint requires an authenticated administrator cookie session. `POST
/admin/evaluation/runs` additionally requires an `Origin` allowed by `ADMIN_TRUSTED_ORIGINS` because
it executes production retrieval and answer services and can write a report. Comparison is
read-only and does not modify either report.

## Server-managed resources

`EVALUATION_DATASET_DIR` identifies the directory containing administrator-executable JSON
datasets. It defaults to `examples/evaluation`, relative to the backend application directory.
Dataset identifiers are direct JSON filename stems, are validated before lookup, and never become
caller-supplied paths. Dataset responses contain explicit safe fields and do not expose paths,
arbitrary dataset metadata, prompts, provider configuration, or credentials.

`EVALUATION_REPORT_DIR` identifies the report directory and defaults to `evaluation-reports`, also
relative to the backend directory. Clients can request persistence with `persist_report: true` but
cannot choose a directory, path, or filename. The existing generated filename and atomic no-clobber
writer remain authoritative. Existing run identifiers are rejected instead of overwritten.

Both settings may be absolute paths. Relative configured paths remain relative to the backend
application directory, so process working-directory changes do not alter resource selection.

## Endpoints

- `GET /admin/evaluation/datasets` lists validated datasets in deterministic identifier order with
  identifier, name, version, schema version, and case count.
- `GET /admin/evaluation/datasets/{dataset_id}` returns safe dataset and case definitions.
- `POST /admin/evaluation/runs` executes one server-managed dataset synchronously and optionally
  persists its terminal report.
- `GET /admin/evaluation/runs?limit=50&offset=0` lists persisted reports newest first when report
  timestamps are present. Pagination is bounded to 100 items. Discovery streams and validates only
  the report envelope and summary, skipping case results so stored answers and retrieved content are
  not materialized for list responses.
- `GET /admin/evaluation/runs/{run_id}` loads a persisted report through the canonical report
  validator using its server-managed run identity.
- `POST /admin/evaluation/comparisons` compares a candidate and baseline report using the existing
  regression policy and comparison implementation. The request has no persistence side effects.

The execution request supports the existing retrieval depth, continue-on-error, complete expected
source recall, fragment comparison, and citation controls. Omitted fields use
`EvaluationRunOptions` and `AnswerEvaluationOptions` defaults directly. Retrieved-content inclusion
is intentionally not exposed.

## Result and content policy

Run responses preserve existing run and case statuses, timing, safe configuration, aggregate
retrieval and answer metrics, case counts, per-case metrics, citation diagnostics, and safe error
categories. Generated answer text, retrieved chunk content and metadata, arbitrary run metadata,
provider payloads, prompts, stack traces, environment values, credentials, and filesystem paths are
not returned. The same filtered response mapping is used for newly executed and persisted runs.

Persisted report files retain the existing complete report schema and may contain generated answers
and, for reports created outside this API, retrieved content. Protect the configured report
directory according to the application's data-classification requirements. API filtering does not
rewrite those files.

## Errors and operational constraints

Known dataset, report, option, persistence, and compatibility failures use structured administrator
errors with stable codes and safe messages. Examples include `evaluation_dataset_not_found`,
`malformed_evaluation_dataset`, `unsupported_dataset_schema`, `invalid_evaluation_options`,
`evaluation_bootstrap_failed`, `evaluation_run_failed`, `evaluation_report_not_found`,
`malformed_evaluation_report`, `unsupported_report_schema`,
`evaluation_report_persistence_failed`, and `incompatible_evaluation_comparison`. Internal paths and
underlying provider details are not included. Unexpected programming failures remain observable
server errors.

Execution is synchronous and sequential because those are the current `EvaluationRunner` and
production service contracts. The endpoint does not create queues, background work, polling state,
database history, or custom concurrency. Concurrent HTTP requests create independent runners while
reusing the application's managed provider resources; those resources are closed by the existing
application lifespan cleanup. Deployments must set an HTTP timeout long enough for their largest
approved dataset. A later change can add asynchronous execution if operational evidence requires it.
