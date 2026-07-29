from enum import Enum
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
NonNegativeFloat = Annotated[float, Field(strict=True, ge=0)]
UnitRatio = Annotated[float, Field(strict=True, ge=0, le=1)]


class _EvaluationModel(BaseModel):
    """Shared serialization and input-boundary rules for evaluation records."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def _deduplicate(values: list[str]) -> list[str]:
    """Return values in first-seen order after field-level string normalization."""

    return list(dict.fromkeys(values))


def _ensure_unique(values: list[str], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


class EvaluationCaseStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class EvaluationRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationCase(_EvaluationModel):
    """One deterministic input to a future evaluation runner."""

    id: NonEmptyString
    question: NonEmptyString
    description: NonEmptyString | None = None
    expected_source_ids: list[NonEmptyString] = Field(default_factory=list)
    expected_answer_contains: list[NonEmptyString] = Field(default_factory=list)
    expected_answer_excludes: list[NonEmptyString] = Field(default_factory=list)
    tags: list[NonEmptyString] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    _deduplicate_lists = field_validator(
        "expected_source_ids",
        "expected_answer_contains",
        "expected_answer_excludes",
        "tags",
    )(_deduplicate)


class EvaluationDataset(_EvaluationModel):
    """A named, versioned collection of evaluation inputs."""

    name: NonEmptyString
    version: NonEmptyString
    cases: list[EvaluationCase] = Field(min_length=1)
    description: NonEmptyString | None = None
    created_at: AwareDatetime | None = None
    tags: list[NonEmptyString] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    _deduplicate_tags = field_validator("tags")(_deduplicate)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> Self:
        _ensure_unique([case.id for case in self.cases], label="Evaluation case IDs")
        return self


class RetrievedItem(_EvaluationModel):
    """A retrieval result captured without depending on persistence entities."""

    id: NonEmptyString
    rank: PositiveInt
    document_id: NonEmptyString | None = None
    chunk_id: NonEmptyString | None = None
    content: str | None = None
    score: float | None = Field(default=None, allow_inf_nan=False, strict=True)
    distance: float | None = Field(default=None, allow_inf_nan=False, strict=True)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RetrievalEvaluationResult(_EvaluationModel):
    """Recorded retrieval output and optional, externally calculated metrics."""

    retrieved_items: list[RetrievedItem]
    precision_at_k: UnitRatio | None = None
    recall_at_k: UnitRatio | None = None
    reciprocal_rank: UnitRatio | None = None
    hit: StrictBool | None = None
    expected_source_ids: list[NonEmptyString] = Field(default_factory=list)
    matched_source_ids: list[NonEmptyString] = Field(default_factory=list)
    failure_reasons: list[NonEmptyString] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    _deduplicate_lists = field_validator(
        "expected_source_ids", "matched_source_ids", "failure_reasons"
    )(_deduplicate)

    @model_validator(mode="after")
    def validate_rank_sequence(self) -> Self:
        ranks = [item.rank for item in self.retrieved_items]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError(
                "Retrieved item ranks must be unique and form an ascending sequence from 1"
            )
        return self


class AnswerEvaluationResult(_EvaluationModel):
    """Recorded answer output and optional, externally assigned evaluation values."""

    answer: str
    passed: StrictBool | None = None
    matched_expected_fragments: list[NonEmptyString] = Field(default_factory=list)
    missing_expected_fragments: list[NonEmptyString] = Field(default_factory=list)
    matched_excluded_fragments: list[NonEmptyString] = Field(default_factory=list)
    citation_count: NonNegativeInt | None = None
    citations_valid: StrictBool | None = None
    hallucination_detected: StrictBool | None = None
    failure_reasons: list[NonEmptyString] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    _deduplicate_lists = field_validator(
        "matched_expected_fragments",
        "missing_expected_fragments",
        "matched_excluded_fragments",
        "failure_reasons",
    )(_deduplicate)


class EvaluationCaseResult(_EvaluationModel):
    """Complete recorded output for one evaluation case."""

    case_id: NonEmptyString
    question: NonEmptyString
    retrieval: RetrievalEvaluationResult | None = None
    answer: AnswerEvaluationResult | None = None
    status: EvaluationCaseStatus = EvaluationCaseStatus.PENDING
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    duration_ms: NonNegativeFloat | None = None
    error: NonEmptyString | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at must not precede started_at")
        if self.status is EvaluationCaseStatus.ERROR and self.error is None:
            raise ValueError("error must be present when status is error")
        return self


class EvaluationSummary(_EvaluationModel):
    """Externally calculated aggregate values for an evaluation run."""

    total_cases: NonNegativeInt
    passed_cases: NonNegativeInt
    failed_cases: NonNegativeInt
    error_cases: NonNegativeInt
    skipped_cases: NonNegativeInt
    retrieval_precision_at_k: UnitRatio | None = None
    retrieval_recall_at_k: UnitRatio | None = None
    retrieval_hit_rate: UnitRatio | None = None
    mean_reciprocal_rank: UnitRatio | None = None
    answer_pass_rate: UnitRatio | None = None
    average_duration_ms: NonNegativeFloat | None = None

    @model_validator(mode="after")
    def validate_terminal_counts(self) -> Self:
        terminal_cases = (
            self.passed_cases + self.failed_cases + self.error_cases + self.skipped_cases
        )
        if terminal_cases > self.total_cases:
            raise ValueError("Terminal case counts must not exceed total_cases")
        return self


class EvaluationRun(_EvaluationModel):
    """A complete or in-progress evaluation run record."""

    id: NonEmptyString
    dataset_name: NonEmptyString
    dataset_version: NonEmptyString
    status: EvaluationRunStatus
    results: list[EvaluationCaseResult]
    schema_version: NonEmptyString = "1.0"
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    summary: EvaluationSummary | None = None
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        _ensure_unique(
            [result.case_id for result in self.results], label="Evaluation result case IDs"
        )
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at must not precede started_at")
        return self
