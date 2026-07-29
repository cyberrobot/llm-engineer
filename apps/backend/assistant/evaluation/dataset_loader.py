"""Load evaluation dataset files into the domain model."""

import json
from pathlib import Path
from stat import S_ISREG

from pydantic import ValidationError

from assistant.evaluation.models import EvaluationDataset

_SUPPORTED_SCHEMA_VERSIONS = ("1.0",)


class EvaluationDatasetError(Exception):
    """Base error for evaluation dataset loading."""


class EvaluationDatasetFileNotFoundError(EvaluationDatasetError):
    """Raised when the requested dataset path does not exist."""


class EvaluationDatasetReadError(EvaluationDatasetError):
    """Raised when a dataset path is not a readable UTF-8 file."""


class EvaluationDatasetJsonError(EvaluationDatasetError):
    """Raised when dataset content is not one valid JSON object."""


class EvaluationDatasetValidationError(EvaluationDatasetError):
    """Raised when a JSON object does not satisfy the dataset domain model."""

    def __init__(self, message: str, *, errors: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.errors = errors


class UnsupportedEvaluationDatasetSchemaError(EvaluationDatasetError):
    """Raised when a dataset declares a schema version this loader cannot read."""


def load_evaluation_dataset(path: str | Path) -> EvaluationDataset:
    """Read one UTF-8 JSON file and return its validated evaluation dataset."""

    dataset_path = Path(path)
    content = _read_dataset_file(dataset_path)
    return _parse_evaluation_dataset_json(content, source=str(dataset_path))


def parse_evaluation_dataset_json(content: str) -> EvaluationDataset:
    """Parse JSON text and return its validated evaluation dataset."""

    return _parse_evaluation_dataset_json(content)


def _read_dataset_file(path: Path) -> str:
    try:
        if not S_ISREG(path.stat().st_mode):
            raise EvaluationDatasetReadError(
                f"Evaluation dataset path '{path}' is not a regular file"
            )
        return path.read_text(encoding="utf-8")
    except EvaluationDatasetReadError:
        raise
    except FileNotFoundError as exc:
        raise EvaluationDatasetFileNotFoundError(
            f"Evaluation dataset file not found: '{path}'"
        ) from exc
    except UnicodeDecodeError as exc:
        raise EvaluationDatasetReadError(
            f"Evaluation dataset file '{path}' is not valid UTF-8"
        ) from exc
    except OSError as exc:
        raise EvaluationDatasetReadError(
            f"Could not read evaluation dataset file '{path}': {exc}"
        ) from exc


def _parse_evaluation_dataset_json(content: str, *, source: str | None = None) -> EvaluationDataset:
    source_description = f" in '{source}'" if source is not None else ""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise EvaluationDatasetJsonError(
            f"Invalid evaluation dataset JSON{source_description} at "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise EvaluationDatasetJsonError(
            f"Invalid evaluation dataset JSON{source_description}: JSON root must be an object"
        )

    if "schema_version" not in data:
        details: list[dict[str, object]] = [
            {
                "type": "missing",
                "loc": ("schema_version",),
                "msg": "External dataset JSON must explicitly declare schema_version",
            }
        ]
        raise EvaluationDatasetValidationError(
            _validation_message(details, source=source), errors=details
        )

    try:
        dataset = EvaluationDataset.model_validate(data)
    except ValidationError as exc:
        details = [
            dict(error)
            for error in exc.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
        ]
        raise EvaluationDatasetValidationError(
            _validation_message(details, source=source), errors=details
        ) from exc

    if dataset.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(_SUPPORTED_SCHEMA_VERSIONS)
        raise UnsupportedEvaluationDatasetSchemaError(
            f"Unsupported evaluation dataset schema version '{dataset.schema_version}'"
            f"{source_description}; supported versions: {supported}"
        )

    return dataset


def _validation_message(errors: list[dict[str, object]], *, source: str | None) -> str:
    source_description = f" in '{source}'" if source is not None else ""
    rendered_errors = "; ".join(
        f"{_format_location(error.get('loc'))}: {error.get('msg', 'Invalid value')}"
        for error in errors
    )
    return f"Invalid evaluation dataset{source_description}: {rendered_errors}"


def _format_location(location: object) -> str:
    if isinstance(location, (tuple, list)):
        return ".".join(str(part) for part in location) or "<root>"
    return str(location)
