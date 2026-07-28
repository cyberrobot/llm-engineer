from pydantic import BaseModel, ConfigDict, Field


class SourceReference(BaseModel):
    """A minimal reference to a source used in an assistant response."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for the source", examples=["source-123"])
    title: str = Field(description="Human-readable source title", examples=["Discovery report"])


class ErrorResponse(BaseModel):
    """Standard error returned by the API."""

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(description="Human-readable error detail", examples=["Invalid request"])
