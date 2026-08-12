# PR 11I Review 1 — Evaluation Admin API Verification Hardening

## Governing specification

This review is governed by `.codex/tasks/11i-evaluation-admin-api-exposure.md`.

## Review outcome

PR #76 implements the requested administrator evaluation namespace and its principal security,
resource-selection, execution, report, comparison, response-filtering, configuration, and
documentation behavior. GitHub Actions is green and the existing focused tests cover primary happy
paths, authorization, path traversal, safe response mapping, pagination, and no-clobber persistence.

The PR is not yet approvable because the governing specification explicitly requires behavioral
evidence for several failure and terminal-result paths that the current HTTP suite does not cover.
Missing evidence is treated as unverified rather than inferred from implementation.

The report catalog also loads every complete `EvaluationRun`, including stored results and any
retrieved content, before applying pagination. This violates the governing requirement that report
discovery expose summary metadata without loading unnecessary retrieved content.

## Required changes

Add focused externally observable administrator API tests for:

1. A terminal run containing deterministic failed, errored, and skipped cases, proving that the API
   preserves existing status semantics and safe error categories without exposing raw exception
   details.
2. Evaluation service bootstrap failure, proving a stable `evaluation_bootstrap_failed` response
   that does not expose configuration or credentials and creates no report.
3. Evaluation run failure outside the existing per-case error isolation, proving a stable
   `evaluation_run_failed` response that retains the exception cause internally, emits only a safe
   structured error category, exposes no provider detail, and creates no report.
4. Report persistence failure, proving a stable `evaluation_report_persistence_failed` response and
   no false persistence-success result.
5. Unsupported persisted report schema, proving a stable `unsupported_report_schema` response for
   report detail and comparison inputs.
6. A compatible regression comparison, proving existing comparison semantics are exposed without
   recalculation and report files remain unchanged.
7. Evaluation-specific production composition and resource lifetime, proving separate executions
   receive separate runner state while reusing the application-managed provider, and that the
   existing application lifespan closes that provider after both successful and failed evaluation
   requests.
8. Report discovery through a canonical lightweight report-metadata loader that validates the
   report envelope and summary while streaming past case results without retaining answer or
   retrieved content. Full canonical report loading must remain authoritative for detail and
   comparison. Listing order and pagination contracts must remain unchanged.

Use realistic fakes only at provider/resource boundaries. Do not call a live AI provider. Do not
duplicate evaluator calculations in the HTTP tests.

## Scope constraints

- Preserve every public evaluation dataset, report, CLI, metric, and comparison contract.
- Do not add database persistence, background execution, queues, scheduling, concurrency, or new
  metrics.
- Do not broaden API response sensitivity.
- Do not add production code unless a failing behavioral test demonstrates a defect.
- Keep the original configuration and documentation contract unchanged unless behavior changes.

## Verification

Run:

```sh
cd apps/backend
venv/bin/python -m pytest -q -o addopts= --strict-markers tests/test_evaluation_admin_api.py
venv/bin/python -m pytest -q -o addopts= --strict-markers tests/evaluation \
  tests/test_admin_authentication_api.py tests/test_assistant_admin_api.py \
  tests/test_operations_administration_api.py tests/test_production_hardening.py
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/python -m mypy .
```

Then run the repository-defined backend suite against an isolated PostgreSQL database:

```sh
npm run test:api
```

## Acceptance criteria

- Every required failure and terminal-result path above has precise HTTP-level assertions.
- Safe error codes and messages are asserted; sensitive exception contents are absent.
- A failed top-level run is logged, returns `evaluation_run_failed`, and cannot create a report.
- Failed persistence cannot be reported as successful.
- Unsupported report schemas are rejected safely wherever reports are consumed.
- Regression comparison results come from the existing comparison subsystem and do not mutate files.
- Evaluation execution uses request-local runners and application-managed provider resources.
- Provider cleanup is verified after successful and failed evaluation requests.
- Report listing does not materialize case results, generated answers, or retrieved content.
- Existing evaluation, authentication, assistant administration, operations administration, CLI,
  report, and comparison tests remain green.
- Ruff, formatting, mypy, and the full backend suite pass.
