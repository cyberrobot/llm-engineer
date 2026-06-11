from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class Sentence:
    text: str
    index: int


class CitationVerification(BaseModel):
    sentence: str
    supported: bool
    source_ids: list[str]


class EvaluationMetrics(BaseModel):
    groundedness_score: float
    citation_accuracy: float
    unsupported_claims: int
    verified_sentences: int
    total_sentences: int
