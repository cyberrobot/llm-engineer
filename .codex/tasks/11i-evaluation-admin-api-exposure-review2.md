# PR 11I Review 2 — Evaluation Admin API Static Verification

## Governing specification

This review is governed by `.codex/tasks/11i-evaluation-admin-api-exposure.md`.

## Review outcome

PR #76 at head `78683e3` contains the behavioral corrections required by Review 1, is no longer a
draft, and has green GitHub checks. Focused behavioral tests and mypy pass locally. The PR is not yet
approvable because the repository-defined full Ruff check fails in the new evaluation run-failure
logging test.

## Required change

Update the assertions for structured `LogRecord` extras in
`apps/backend/tests/test_evaluation_admin_api.py` so they remain accepted by mypy without violating
Ruff `B009`. Preserve the assertions that the safe dataset identifier and exception category are
logged and that the sensitive exception message is absent.

No production behavior, public contract, dependency, configuration, or migration change is needed.

## Verification

Run from `apps/backend`:

```sh
../../venv/bin/python -m pytest -q -o addopts= --strict-markers \
  tests/evaluation/test_reporting.py tests/test_evaluation_admin_api.py
../../venv/bin/ruff check .
../../venv/bin/ruff format --check .
../../venv/bin/python -m mypy .
```

Confirm `git diff --check` passes.

## Acceptance criteria

- The run-failure logging test still asserts `dataset_id == "suite"`.
- The run-failure logging test still asserts `error_type == "RuntimeError"`.
- The sensitive exception message remains absent from captured logs and the HTTP response.
- Focused tests, Ruff, formatting, mypy, and `git diff --check` pass.

