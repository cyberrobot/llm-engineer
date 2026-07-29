"""Adapter from the production chat response contract to pure answer evaluation."""

from collections.abc import Sequence

from assistant.domain import Citation
from assistant.evaluation.answer_evaluator import evaluate_answer
from assistant.evaluation.models import (
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    EvaluationCase,
    RetrievedItem,
)
from assistant.schemas import ChatResponse


def evaluate_chat_response(
    *,
    case: EvaluationCase,
    response: ChatResponse,
    retrieved_items: Sequence[RetrievedItem] | None = None,
    options: AnswerEvaluationOptions | None = None,
) -> AnswerEvaluationResult:
    """Evaluate a chat response whose source IDs are canonical document IDs."""

    citations = [
        Citation(document_id=source.id, title=source.title, chunk_id="")
        for source in response.sources
    ]
    return evaluate_answer(
        case=case,
        answer=response.message,
        citations=citations,
        retrieved_items=retrieved_items,
        options=options,
    )
