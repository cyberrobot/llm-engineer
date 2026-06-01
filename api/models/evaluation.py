from pydantic import BaseModel


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
