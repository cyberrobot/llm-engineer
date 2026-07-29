"""Stable public exports for deterministic evaluation models and metrics."""

from assistant.evaluation.answer_adapter import evaluate_chat_response
from assistant.evaluation.answer_evaluator import (
    AnswerEvaluationError,
    evaluate_answer,
    summarise_answer_results,
)
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
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    AnswerEvaluationSummary,
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
    "AnswerEvaluationError",
    "AnswerEvaluationOptions",
    "AnswerEvaluationResult",
    "AnswerEvaluationSummary",
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
    "evaluate_answer",
    "evaluate_chat_response",
    "evaluate_retrieval",
    "summarise_retrieval_results",
    "summarise_answer_results",
    "to_evaluation_retrieved_items",
]
