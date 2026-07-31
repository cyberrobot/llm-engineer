from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, TypeAlias
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

OperationId: TypeAlias = UUID
OperationType: TypeAlias = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$",
    ),
]


class OperationStatus(str, Enum):
    accepted = "accepted"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    rejected = "rejected"


class OperationalAction(BaseModel):
    """Validated metadata for one privileged administrative operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: OperationId = Field(default_factory=uuid4)
    operation_type: OperationType
    requested_at: AwareDatetime
    requested_by: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]*$",
        ),
    ]
    status: OperationStatus = OperationStatus.accepted

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)
