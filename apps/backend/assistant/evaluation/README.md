# Evaluation domain models

This package defines the stable, serializable records used by the evaluation framework, loads
repository-managed evaluation datasets from JSON, and calculates deterministic retrieval and
answer-quality metrics from results supplied by a caller. It does not execute retrieval, generate
answers, orchestrate evaluation runs, or persist reports.

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

dataset = load_evaluation_dataset(
    Path("examples/evaluation/example-dataset.json")
)
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
