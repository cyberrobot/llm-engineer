"""Stable public exports for evaluation models, loading, and retrieval metrics."""

from assistant.evaluation.dataset_loader import (
    EvaluationDatasetError,
    EvaluationDatasetFileNotFoundError,
    EvaluationDatasetJsonError,
    EvaluationDatasetReadError,
    EvaluationDatasetValidationError,
    UnsupportedEvaluationDatasetSchemaError,
    load_evaluation_dataset,
    parse_evaluation_dataset_json,
)
from assistant.evaluation.models import (
    AnswerEvaluationResult,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationSummary,
    RetrievalEvaluationResult,
    RetrievalEvaluationSummary,
    RetrievedItem,
)
from assistant.evaluation.retrieval_adapter import to_evaluation_retrieved_items
from assistant.evaluation.retrieval_evaluator import (
    RetrievalEvaluationError,
    evaluate_retrieval,
    summarise_retrieval_results,
)

__all__ = [
    "AnswerEvaluationResult",
    "EvaluationCase",
    "EvaluationCaseResult",
    "EvaluationCaseStatus",
    "EvaluationDataset",
    "EvaluationDatasetError",
    "EvaluationDatasetFileNotFoundError",
    "EvaluationDatasetJsonError",
    "EvaluationDatasetReadError",
    "EvaluationDatasetValidationError",
    "EvaluationRun",
    "EvaluationRunStatus",
    "EvaluationSummary",
    "RetrievalEvaluationResult",
    "RetrievalEvaluationError",
    "RetrievalEvaluationSummary",
    "RetrievedItem",
    "UnsupportedEvaluationDatasetSchemaError",
    "load_evaluation_dataset",
    "parse_evaluation_dataset_json",
    "evaluate_retrieval",
    "summarise_retrieval_results",
    "to_evaluation_retrieved_items",
]
