from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from assistant.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    IngestionJobResponse,
    KnowledgeStatusResponse,
    SourceReference,
    StartIngestionRequest,
)

API_CONTRACT_VERSION = "1.0.0"

CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    IngestionJobResponse,
    KnowledgeStatusResponse,
    SourceReference,
    StartIngestionRequest,
)


def create_openapi_schema(app: FastAPI) -> Callable[[], dict[str, Any]]:
    """Create an OpenAPI generator that includes contracts without routes yet."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        _, contract_schema = models_json_schema(
            [(model, "validation") for model in CONTRACT_MODELS],
            ref_template="#/components/schemas/{model}",
        )
        schema.setdefault("components", {}).setdefault("schemas", {}).update(
            contract_schema.get("$defs", {})
        )
        app.openapi_schema = schema
        return schema

    return openapi
