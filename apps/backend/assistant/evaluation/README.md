# Evaluation domain models

This package defines the stable, serializable records used by the evaluation framework and the
boundary that loads repository-managed evaluation datasets from JSON. It does not perform retrieval,
answer generation, metric calculation, evaluation execution, or report persistence.

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
