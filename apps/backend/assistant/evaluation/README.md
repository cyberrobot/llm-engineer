# Evaluation domain models

This package defines the stable, serializable records used by the evaluation framework. It contains
only domain data and validation; dataset loading, retrieval, answer generation, metric calculation,
execution, and report persistence belong to later layers.

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

Pydantic provides stable JSON serialization and reconstruction:

```python
payload = dataset.model_dump_json()
restored = EvaluationDataset.model_validate_json(payload)
assert restored == dataset
```

Evaluation reports currently default to schema version `1.0`. Construction is deterministic: the
models do not generate IDs, timestamps, metrics, or other runtime values.
