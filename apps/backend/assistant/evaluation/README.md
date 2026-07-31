# Evaluation domain models

This package defines the stable, serializable records used by the evaluation framework, loads
repository-managed evaluation datasets from JSON, calculates deterministic retrieval and
answer-quality metrics, orchestrates complete evaluation runs, and can persist terminal runs as
versioned JSON reports. Report persistence is opt-in; the package provides no evaluation API
endpoint or database persistence.

The models have three boundaries:

- `EvaluationCase` and `EvaluationDataset` describe expected evaluation inputs.
- `RetrievedItem`, `RetrievalEvaluationResult`, `AnswerEvaluationResult`, and
  `EvaluationCaseResult` record output for an individual case.
- `EvaluationSummary` and `EvaluationRun` describe aggregate and run-level output.

Construct models directly from Python values:

```python
from assistant.evaluation import EvaluationCase, EvaluationDataset

dataset = EvaluationDataset(
    name="discovery-regression",
    version="2026.07",
    cases=[EvaluationCase(id="case-1", question="What is a discovery workshop?")],
)
```

Python construction defaults `schema_version` to `"1.0"` for backward compatibility. In persisted
JSON files the field is required explicitly:

- `schema_version` describes the structure of the complete JSON document. This loader supports
  schema version `1.0` only and does not migrate other versions.
- `version` identifies the content revision of a particular dataset, such as `"2026.07"`.

The JSON root must be one object matching `EvaluationDataset`; domain validation remains owned by
the Pydantic model. Load a dataset with:

```python
from pathlib import Path

from assistant.evaluation import load_evaluation_dataset

dataset = load_evaluation_dataset(Path("examples/evaluation/example-dataset.json"))
print(dataset.name)
print(len(dataset.cases))
```

`load_evaluation_dataset` accepts `str` and `Path`, reads the supplied file once as UTF-8, parses one
standard JSON document, and returns `EvaluationDataset`. `parse_evaluation_dataset_json` provides
the same parsing and validation boundary for JSON text. Files are intended to be practical
development and CI datasets rather than unbounded or streaming inputs.

Callers can handle `EvaluationDatasetError` or its public subclasses to distinguish missing files,
read and UTF-8 failures, malformed or non-object JSON, domain validation, and unsupported schema
versions. Validation errors retain Pydantic-style structured field details in `errors`, while
chained low-level exceptions remain available through `__cause__`.

The representative dataset at `examples/evaluation/example-dataset.json` contains source,
answer-inclusion, and answer-exclusion expectations.

Pydantic provides stable JSON serialization and reconstruction:

```python
payload = dataset.model_dump_json()
restored = EvaluationDataset.model_validate_json(payload)
assert restored == dataset
```

Evaluation datasets and reports currently default to schema version `1.0`. Construction and loading
are deterministic: the models and loader do not generate IDs, timestamps, metrics, cache files, or
other runtime values.

## Retrieval evaluation

`EvaluationCase.expected_source_ids` identifies knowledge documents. Retrieval evaluation therefore
uses `RetrievedItem.document_id` as the canonical source identity. Matching is exact and
case-sensitive; it does not compare content, resolve aliases, inspect labels, or perform database or
network lookups. A retrieved item without a `document_id` is rejected when a case has source
expectations.

Production retrieval can return several chunks from one document. Source-level precision and recall
count each retrieved document only once, in first-retrieved order. Repeated chunks still remain in
`retrieved_items`, count toward the average retrieved-item total, and occupy raw retrieval positions
for reciprocal rank. Duplicate document IDs are reported in
`duplicate_retrieved_source_ids` in first-duplicate order.

The per-case metrics are:

- Precision@K: unique expected documents retrieved divided by unique documents retrieved.
- Recall@K: unique expected documents retrieved divided by expected documents.
- Hit: whether at least one expected document was retrieved.
- Reciprocal rank: `1 / rank` for the first expected document in the raw ranked sequence, or `0.0`
  for a miss.

Supplying `k` evaluates only the first `k` ranked items; it must be a positive integer. The evaluator
sorts a copy by authoritative one-based rank, rejects duplicate or gapped ranks, and never mutates
caller-owned values. It stores the configured depth in `evaluated_at_k`; `None` means every supplied
item was evaluated. Metrics retain full Python floating-point precision.

Cases without expected source IDs are source-unevaluable: precision, recall, hit, and reciprocal rank
are `None`, while retrieved items remain available and `no_expected_sources` is recorded as a
diagnostic rather than a retrieval failure. When expectations exist but retrieval is empty, quality
metrics are zero and diagnostics include `no_retrieval_results` and
`no_expected_source_retrieved`.

Evaluate already-normalized items directly:

```python
from assistant.evaluation import EvaluationCase, RetrievedItem, evaluate_retrieval

case = EvaluationCase(
    id="reset-password",
    question="How do I reset my password?",
    expected_source_ids=["account-guide"],
)
result = evaluate_retrieval(
    case=case,
    retrieved_items=[
        RetrievedItem(
            id="chunk-1",
            document_id="account-guide",
            chunk_id="chunk-1",
            rank=1,
        )
    ],
    k=5,
)
print(result.recall_at_k)
```

`to_evaluation_retrieved_items` adapts the retrieval layer's `KnowledgeChunk` values without
executing a search. It preserves retrieval order, chunk and document identity, content, similarity
score, document metadata, and assigns ranks beginning at one. The production type has no distance,
so adapted distances remain unset.

`summarise_retrieval_results` reports supplied and source-evaluable case counts, mean precision,
mean recall, hit rate, mean reciprocal rank, and average raw retrieved-item count. Each quality mean
ignores `None` but includes zero; it is `None` when no case supplies that metric. The retrieved-item
average includes every supplied result and is `0.0` for an empty sequence.

## Answer evaluation

Answer evaluation is rule-based and independent from answer generation. It never calls an LLM,
retrieval service, database, embedding model, or external API. Callers supply completed answer text,
optional structured citations, and optional retrieval context.

By default, required and prohibited fragments are trimmed, consecutive whitespace is collapsed,
and comparison uses Unicode-aware case-insensitive substring matching. Punctuation and word order
are preserved; fragments are plain text rather than regular expressions. All required fragments
must be present, while any prohibited fragment fails the exclusion check. Options can enable
case-sensitive comparison, retain internal whitespace, or allow any required fragment to satisfy
the inclusion check.

Structured citations use `Citation.document_id`, matching retrieval evaluation's canonical
`RetrievedItem.document_id` identity. Raw citation count includes duplicates, while grounding and
expected-source diagnostics operate on unique document IDs in first-seen order. When a case has
expected sources, at least one citation is required by default. A citation is structurally valid
only when its document appeared in the supplied retrieval context; a retrieved but unexpected
document remains structurally valid. The evaluator does not require every expected document to be
cited.

Applicable checks are composed with logical AND: required fragments, prohibited fragments, the
citation requirement, and available citation grounding must all pass. A failed applicable check
fails the answer. If no checks apply, `passed` is `None` and `no_answer_expectations` is recorded.
Empty text is an ordinary result with an `empty_answer` diagnostic, not an exception.

`hallucination_detected` is deliberately narrow: it is `True` only when at least one structured
citation names a document absent from the supplied retrieval context, `False` when validation ran
and all citations were grounded, and `None` when validation was unavailable. It is not general
factuality or prose-level hallucination detection.

```python
from assistant.evaluation import EvaluationCase, evaluate_answer

case = EvaluationCase(
    id="password-reset",
    question="How do I reset my password?",
    expected_answer_contains=["reset link"],
    expected_answer_excludes=["send us your password"],
)
result = evaluate_answer(
    case=case,
    answer="Use the reset link sent to your registered email.",
)
print(result.passed)
print(result.missing_expected_fragments)
```

`evaluate_chat_response` is a small adapter for the production `ChatResponse` contract. Its
`SourceReference.id` values are already document IDs, so callers do not need to reconstruct domain
citations. It does not alter the response or its answer formatting.

`summarise_answer_results` reports supplied, evaluable, passed, failed, and unevaluable case counts;
pass rate across evaluable cases; average raw citation count across all supplied results; and the
result-level citation validity rate across results where grounding was evaluated. Empty aggregates
have an average citation count of `0.0`, with pass and citation-validity rates left as `None`.

## Evaluation runner

`EvaluationRunner` composes the production retrieval and answer-generation services with the pure
evaluators. The current application services are synchronous, so `run_case` and `run_dataset` are
synchronous. Dataset cases execute sequentially and retain their input order. The runner neither
loads a dataset file nor writes files or database records.

For each case, the runner retrieves the production `KnowledgeChunk` context, adapts it with
`to_evaluation_retrieved_items`, evaluates retrieval, asks `ChatService.generate` to generate from
that same context, and adapts/evaluates the resulting `ChatResponse`. This avoids a second retrieval
and keeps prompt construction in `ChatService`. `retrieval_k` limits metric evaluation only because
the production `RetrievalService.retrieve` contract does not accept a per-call limit; it does not
change the service's configured retrieval behavior or the context supplied to generation.

The active `RetrievalService` contract accepts only the question. The runner therefore introduces
no role override or access bypass: callers inject the same configured service used by the
application, and any repository-level visibility rules remain that service's responsibility. No
credentials, service instances, prompts, or environment values are copied into run configuration.

Cases are `passed` when every applicable retrieval and answer check passes, `failed` when execution
completes but a deterministic check fails, `error` when a service, adapter, or evaluator raises, and
`skipped` when neither stage has an evaluable expectation. Complete-source recall is required by
default; `require_all_expected_sources=False` accepts any retrieval hit. Answer pass semantics come
directly from `AnswerEvaluationResult.passed`.

Errors are isolated by default and later cases continue. Error results retain completed retrieval
evaluation when answer generation fails, but expose only the exception type rather than potentially
sensitive exception text. With `continue_on_error=False`, the first errored case stops execution and
the returned partial run is `failed`. Otherwise, a fully processed run is `completed` even when it
contains failed, errored, or skipped cases.

The run summary combines the existing retrieval and answer aggregation functions with status counts
and the mean of all available case durations, including zero durations. Configuration snapshots are
JSON-safe and contain retrieval depth, continuation, content-retention, complete-recall, and answer
evaluation settings. Retrieved content is omitted from results by default; IDs, ranks, scores, and
safe metadata remain available. Clock and ID generation are injectable for deterministic tests.

```python
from assistant.evaluation import EvaluationRunOptions, EvaluationRunner, load_evaluation_dataset

dataset = load_evaluation_dataset("examples/evaluation/example-dataset.json")
runner = EvaluationRunner(
    retrieval_service=retrieval_service,
    answer_service=chat_service,
)
run = runner.run_dataset(
    dataset,
    options=EvaluationRunOptions(retrieval_k=5),
)
print(run.status)
print(run.summary)
```

## Command-line interface

Run a repository-managed JSON dataset from `apps/backend` with the production retrieval and answer
services:

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --retrieval-k 5
```

The command uses the application's existing environment configuration and service factories.
`OPENAI_API_KEY` is required by the configured provider; database and provider settings retain their
existing meanings. When `DATABASE_URL` is set, retrieval uses the production pgvector repository;
otherwise it uses the application's in-memory seed store. The CLI does not initialize or migrate a
database.

The runner contract introduced in PR 8E has no caller-supplied role or access-context option, so the
CLI deliberately has no `--user-role` argument. It uses the same configured `RetrievalService` and
does not add an access override or imply elevated access.

The main options are:

- `--dataset PATH` selects exactly one relative or absolute JSON dataset path.
- `--retrieval-k INTEGER` evaluates retrieval metrics at a depth of at least one. Omitting it keeps
  the runner default. It does not change production retrieval depth or answer context.
- `--stop-on-error` stops after the first case execution error. The default continues through later
  cases.
- `--allow-partial-source-recall` allows a retrieval hit without requiring every expected source.
- `--include-retrieved-content` includes full retrieved chunk content in the result. Content is
  excluded by default, but the full production context is always supplied to answer generation.
- `--case-sensitive`, `--no-normalise-whitespace`, `--allow-missing-citations`, and
  `--skip-citation-validation` expose the corresponding deterministic answer-evaluation controls.
- `--json` writes only the complete serialized `EvaluationRun` to standard output. `--pretty` adds
  indentation and is rejected unless `--json` is also present.
- `--report PATH` writes the complete run to exactly that path and creates missing parent
  directories. The filename and extension are not changed.
- `--report-dir PATH` creates the directory and missing parents, then uses a deterministic generated
  filename.
- `--overwrite-report` explicitly permits replacement and is rejected unless a report destination
  is also supplied. `--report` and `--report-dir` are mutually exclusive.

By default, standard output contains a concise run summary, aggregate retrieval/answer metrics,
timing, and safe diagnostics for failed or errored cases. It does not include prompts, generated
answers, retrieved chunk content, stack traces, or secrets. Loading, configuration, bootstrap, and
run-level errors go to standard error. Provider resources are closed after both successful and
failed runs.

JSON output can be piped to another process without human-readable text mixed into it:

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --json
```

Stop on the first execution error with:

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --stop-on-error
```

Exit codes are stable:

| Code | Meaning |
| ---: | --- |
| 0 | The run completed and every evaluated case passed. |
| 1 | A deterministic evaluation failed, or every case was skipped. |
| 2 | Command usage or argument validation failed. |
| 3 | Dataset loading, JSON parsing, schema, or field validation failed. |
| 4 | The run completed with one or more case execution errors. |
| 5 | Service bootstrap or run-level execution failed. |
| 6 | A run was returned, but explicitly requested report persistence failed. |
| 7 | The baseline could not be loaded or the runs were incompatible. |
| 8 | A configured baseline regression gate failed. |

Case execution errors take precedence over deterministic failures. Some skipped cases do not fail a
run when all evaluated cases pass. A report error takes precedence over the evaluation outcome
because an explicitly requested artifact was not produced. When baseline comparison is requested,
the full precedence is usage (2), dataset (3), unusable run (5), report persistence (6), comparison
error (7), regression (8), case execution error (4), deterministic failure (1), then success (0).

Without a report flag, the CLI keeps each run in memory and creates no files or report directory.
It performs no baseline comparison and intentionally does not modify the dataset or application
configuration. The production services used by this runner are stateless for these operations and
do not invoke the legacy RAG audit-log path; future changes to those service contracts may
introduce inherited side effects that should be documented here.

## Evaluation report persistence

Each report is one complete UTF-8 JSON serialization of `EvaluationRun`, including the run ID,
dataset identity, status and timestamps, configuration, metadata, ordered case results, retrieval
and answer results, structured diagnostics, safe errors, and aggregate summary. Human-diffable
two-space indentation and a final newline are the defaults. Persistence does not recalculate
metrics, reorder results, fetch omitted retrieved content, generate a new ID or timestamp, execute
services, or mutate the run.

`EvaluationRun.schema_version` is the report schema version and currently supports only `"1.0"`.
It is distinct from `EvaluationDataset.schema_version`, which versions the dataset file structure,
and `EvaluationRun.dataset_version`, which records the dataset content revision. Persisted reports
must explicitly contain `schema_version`; loading rejects missing and unknown versions without
migration. Pydantic validates the complete model and structured field errors are retained.

Only terminal `completed` and `failed` runs can be saved or loaded as reports. Failed partial runs
remain valuable records and are supported; transient `pending` and `running` values are rejected.
The report is written to a temporary file in the destination directory, flushed and fsynced, then
committed atomically within normal local-filesystem constraints. With overwrite disabled, an atomic
same-filesystem hard link provides no-clobber behavior even if another writer creates the
destination concurrently. With overwrite enabled, `os.replace` atomically replaces the destination.
Temporary files are removed after success and expected failures. Filesystems must support normal
same-directory atomic replacement and hard links; no cross-filesystem move or file lock is used.

Save to an explicit path (missing parents are created):

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --report evaluation-reports/latest.json
```

Generate a filename inside an explicitly requested directory:

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --report-dir evaluation-reports
```

The generated format is
`{dataset-name}-{dataset-version}-{started-at-utc}-{run-id}.json`. Components are lowercase,
bounded, and sanitized to letters, digits, hyphens, underscores, and dots; unsafe sequences become
hyphens. For example:
`support-knowledge-baseline-2026.07-20260730T085912Z-run-20260730-001.json`.

Existing destinations are protected by default. Replace one explicitly with:

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --report evaluation-reports/latest.json \
  --overwrite-report
```

Human output prints `Report saved to: ...` only after the write succeeds. In `--json` mode, standard
output remains only the serialized run and the confirmation is written to standard error.

Load a report without executing evaluation logic:

```python
from assistant.evaluation import load_evaluation_report

run = load_evaluation_report("evaluation-reports/latest.json")
print(run.summary)
```

Reports can contain questions, generated answers, source identifiers, retrieved metadata, safe
errors, and—when `include_retrieved_content` was enabled—retrieved content. They must be handled
according to the application's data-classification requirements. Persistence never adds
environment variables, tokens, service objects, database URLs, HTTP headers, cookies, or raw stack
traces.

## Baseline comparison and regression gates

`compare_evaluation_runs` compares two terminal `EvaluationRun` objects without executing services,
recalculating metrics, modifying either run, or writing files. `compare_evaluation_report_files` is
a thin convenience wrapper that loads both inputs through `load_evaluation_report`. A baseline is
always read-only: comparison never rewrites, upgrades, publishes, or promotes it, and this work does
not add CI workflow wiring or automatic baseline management.

The fixed quality-metric set is Precision@K, Recall@K, retrieval hit rate, mean reciprocal rank,
and answer pass rate. All are explicitly higher-is-better. Stored comparison values retain their
full float precision. A signed delta is `current - baseline`; an absolute drop is
`max(baseline - current, 0)`. Aggregate decreases are reported without failing by default. An
absolute threshold fails only when the drop is strictly greater than the configured allowance, so
a drop exactly equal to the threshold passes; a central `1e-12` epsilon prevents binary float noise
at that boundary. Programmatic relative thresholds use decimal ratios
and calculate `(baseline - current) / abs(baseline)` only for a decrease. A zero baseline has a
relative drop of `0.0`; when both absolute and relative thresholds are configured, exceeding either
one fails the metric gate. The CLI intentionally exposes the smaller absolute-threshold surface;
relative thresholds remain available through `EvaluationRegressionPolicy`.

Missing values stay missing rather than becoming zero. A baseline `None` and current value is a
newly evaluable metric. A baseline value and current `None` is a became-unevaluable condition and
fails only when that metric has a configured threshold. Two `None` values are not comparable.

Compatibility requires equal report schema versions, dataset names, and retrieval depths by
default, as well as terminal run statuses, summaries, and unique case IDs. Dataset-version drift is
allowed with a warning because added and removed cases often represent an intentional dataset
revision; `--require-same-dataset-version` makes it an error. `--allow-different-retrieval-k`
permits depth drift with a warning. Failed terminal runs remain comparable with warnings. Changes
to complete-source recall or answer-evaluation semantics are also surfaced as warnings. Run IDs and
timestamps need not match.

Cases use `EvaluationCaseResult.case_id`, preserve current-run order for shared and added cases, and
append removed cases in baseline order. Every pass/fail/error/skip transition is represented
explicitly. Passed-to-failed and skipped-to-failed cases are newly failed; any shared non-error to
error transition is newly errored. Failed/error/skipped to passed cases are recovered. Error to
failed is marked as a partial improvement but is not recovered. Added failing and errored cases
fail the default comparison gate because the current suite is unhealthy; added passing or skipped
cases and all removed cases are reported without failing by default. `--fail-on-added-cases` and
`--fail-on-removed-cases` make coverage drift strict. `--allow-new-failures` and
`--allow-new-errors` disable the corresponding shared-case gate.

Run a basic comparison:

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --baseline evaluation-baselines/main.json
```

Configure maximum absolute metric drops as decimal ratios (for example, `0.02` is two percentage
points for a ratio metric):

```bash
python -m assistant.evaluation \
  --dataset examples/evaluation/example-dataset.json \
  --baseline evaluation-baselines/main.json \
  --max-recall-drop 0.02 \
  --max-mrr-drop 0.01 \
  --max-answer-pass-rate-drop 0.03 \
  --fail-on-removed-cases
```

Human output adds one comparison section after the current run summary. With both `--json` and
`--baseline`, standard output remains one valid document with `run` and `comparison` keys. Without
`--baseline`, the established JSON contract remains the serialized `EvaluationRun` directly.
Saving with `--report` or `--report-dir` persists only the current run; comparison output is not
saved and the baseline is not touched.

Programmatic absolute and relative thresholds can be combined:

```python
from assistant.evaluation import (
    EvaluationRegressionPolicy,
    MetricRegressionThreshold,
    compare_evaluation_runs,
    load_evaluation_report,
)

baseline = load_evaluation_report("evaluation-baselines/main.json")
current = load_evaluation_report("evaluation-reports/current.json")
policy = EvaluationRegressionPolicy(
    metric_thresholds={
        "retrieval_recall_at_k": MetricRegressionThreshold(
            maximum_absolute_drop=0.02,
            maximum_relative_drop=0.05,
        ),
        "answer_pass_rate": MetricRegressionThreshold(maximum_absolute_drop=0.03),
    }
)
comparison = compare_evaluation_runs(
    baseline=baseline,
    current=current,
    policy=policy,
)
print(comparison.regressed)
print(comparison.newly_failed_case_ids)
```

Comparison detects dataset-version and case-set drift but cannot detect changed expectations under
an unchanged case ID because persisted case results do not currently contain a case fingerprint.
Trend history, statistical significance, baseline uploads/downloads, remote storage, dashboards,
and automatic threshold tuning remain outside this package boundary.
