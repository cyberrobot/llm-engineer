from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Assistant service health status."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = Field(description="Current Assistant service status", examples=["ok"])
