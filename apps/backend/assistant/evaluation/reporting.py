"""Persist complete terminal evaluation runs as versioned JSON reports."""

import json
import os
import re
import tempfile
from datetime import timezone
from pathlib import Path
from stat import S_ISREG

from pydantic import ValidationError

from assistant.evaluation.models import EvaluationRun, EvaluationRunStatus

_SUPPORTED_SCHEMA_VERSIONS = ("1.0",)
_TERMINAL_STATUSES = frozenset({EvaluationRunStatus.COMPLETED, EvaluationRunStatus.FAILED})
_UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^a-z0-9._-]+")
_REPEATED_FILENAME_SEPARATORS = re.compile(r"[-_.]{2,}")
_MAX_FILENAME_COMPONENT_LENGTH = 80


class EvaluationReportError(Exception):
    """Base exception for evaluation report persistence."""


class EvaluationReportPathError(EvaluationReportError):
    """Raised when a report path cannot identify a regular file."""


class EvaluationReportExistsError(EvaluationReportError):
    """Raised when overwrite protection prevents replacing a report."""


class EvaluationReportWriteError(EvaluationReportError):
    """Raised when a complete report cannot be written atomically."""


class EvaluationReportReadError(EvaluationReportError):
    """Raised when a report is not a readable UTF-8 regular file."""


class EvaluationReportJsonError(EvaluationReportError):
    """Raised when report content is not one valid JSON object."""


class EvaluationReportValidationError(EvaluationReportError):
    """Raised when JSON content does not satisfy the report contract."""

    def __init__(self, message: str, *, errors: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.errors = errors


class UnsupportedEvaluationReportSchemaError(EvaluationReportError):
    """Raised when a report declares a schema version this loader cannot read."""


def save_evaluation_report(
    run: EvaluationRun,
    path: str | Path,
    *,
    overwrite: bool = False,
    pretty: bool = True,
) -> Path:
    """Serialize and atomically save one complete terminal evaluation run."""

    _validate_terminal_run(run)
    content = _serialize_report(run, pretty=pretty)
    report_path = Path(path)
    _prepare_report_parent(report_path)
    _write_report_atomically(content, report_path, overwrite=overwrite)
    return report_path


def load_evaluation_report(path: str | Path) -> EvaluationRun:
    """Read and validate one versioned UTF-8 JSON evaluation report."""

    report_path = Path(path)
    content = _read_report_file(report_path)
    return _parse_report_json(content, source=str(report_path))


def build_evaluation_report_path(
    run: EvaluationRun,
    *,
    output_dir: str | Path,
) -> Path:
    """Build a deterministic safe filename without touching the output directory."""

    dataset_name = _sanitize_filename_component(run.dataset_name)
    dataset_version = _sanitize_filename_component(run.dataset_version)
    run_id = _sanitize_filename_component(run.id)
    if run.started_at is None:
        raise EvaluationReportPathError(
            "Cannot build an evaluation report filename without run.started_at"
        )
    timestamp = run.started_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(output_dir) / (f"{dataset_name}-{dataset_version}-{timestamp}-{run_id}.json")


def save_evaluation_report_to_directory(
    run: EvaluationRun,
    *,
    output_dir: str | Path,
    overwrite: bool = False,
    pretty: bool = True,
) -> Path:
    """Generate a deterministic path and save one report to that directory."""

    path = build_evaluation_report_path(run, output_dir=output_dir)
    return save_evaluation_report(run, path, overwrite=overwrite, pretty=pretty)


def _validate_terminal_run(run: EvaluationRun) -> None:
    if run.status not in _TERMINAL_STATUSES:
        details: list[dict[str, object]] = [
            {
                "type": "value_error",
                "loc": ("status",),
                "msg": "Evaluation reports require a terminal completed or failed run",
            }
        ]
        raise EvaluationReportValidationError(_validation_message(details), errors=details)


def _serialize_report(run: EvaluationRun, *, pretty: bool) -> str:
    try:
        content = run.model_dump_json(indent=2 if pretty else None)
    except Exception as exc:
        details: list[dict[str, object]] = [
            {
                "type": "serialization_error",
                "loc": (),
                "msg": f"Evaluation run could not be serialized ({type(exc).__name__})",
            }
        ]
        raise EvaluationReportValidationError(_validation_message(details), errors=details) from exc
    return f"{content}\n"


def _prepare_report_parent(path: Path) -> None:
    if path.exists() and path.is_dir():
        raise EvaluationReportPathError(
            f"Evaluation report path '{path}' is a directory, not a file"
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EvaluationReportPathError(
            f"Could not create evaluation report parent directory '{path.parent}': {exc}"
        ) from exc
    if not path.parent.is_dir():
        raise EvaluationReportPathError(
            f"Evaluation report parent path '{path.parent}' is not a directory"
        )


def _write_report_atomically(content: str, path: Path, *, overwrite: bool) -> None:
    if not overwrite and (path.exists() or path.is_symlink()):
        raise EvaluationReportExistsError(f"Evaluation report already exists: '{path}'")

    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
            descriptor = None
            file.write(content)
            file.flush()
            os.fsync(file.fileno())

        if overwrite:
            os.replace(temporary_path, path)
            temporary_path = None
        else:
            try:
                os.link(temporary_path, path)
            except FileExistsError as exc:
                raise EvaluationReportExistsError(
                    f"Evaluation report already exists: '{path}'"
                ) from exc
    except EvaluationReportExistsError:
        raise
    except OSError as exc:
        raise EvaluationReportWriteError(
            f"Could not write evaluation report '{path}': {exc}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _read_report_file(path: Path) -> str:
    try:
        if not S_ISREG(path.stat().st_mode):
            raise EvaluationReportReadError(
                f"Evaluation report path '{path}' is not a regular file"
            )
        return path.read_text(encoding="utf-8")
    except EvaluationReportReadError:
        raise
    except FileNotFoundError as exc:
        raise EvaluationReportReadError(f"Evaluation report file not found: '{path}'") from exc
    except UnicodeDecodeError as exc:
        raise EvaluationReportReadError(
            f"Evaluation report file '{path}' is not valid UTF-8"
        ) from exc
    except OSError as exc:
        raise EvaluationReportReadError(
            f"Could not read evaluation report file '{path}': {exc}"
        ) from exc


def _parse_report_json(content: str, *, source: str) -> EvaluationRun:
    source_description = f" in '{source}'"
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise EvaluationReportJsonError(
            f"Invalid evaluation report JSON{source_description} at "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise EvaluationReportJsonError(
            f"Invalid evaluation report JSON{source_description}: JSON root must be an object"
        )

    if "schema_version" not in data:
        details: list[dict[str, object]] = [
            {
                "type": "missing",
                "loc": ("schema_version",),
                "msg": "Persisted evaluation reports must explicitly declare schema_version",
            }
        ]
        raise EvaluationReportValidationError(
            _validation_message(details, source=source), errors=details
        )

    schema_version = data["schema_version"]
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(_SUPPORTED_SCHEMA_VERSIONS)
        raise UnsupportedEvaluationReportSchemaError(
            f"Unsupported evaluation report schema version '{schema_version}'"
            f"{source_description}; supported versions: {supported}"
        )

    try:
        run = EvaluationRun.model_validate(data)
    except ValidationError as exc:
        details = [
            dict(error)
            for error in exc.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
        ]
        raise EvaluationReportValidationError(
            _validation_message(details, source=source), errors=details
        ) from exc
    _validate_terminal_run(run)
    return run


def _sanitize_filename_component(value: str) -> str:
    sanitized = _UNSAFE_FILENAME_CHARACTERS.sub("-", value.strip().lower())
    sanitized = _REPEATED_FILENAME_SEPARATORS.sub("-", sanitized).strip("-_.")
    return sanitized[:_MAX_FILENAME_COMPONENT_LENGTH].rstrip("-_.") or "evaluation"


def _validation_message(
    errors: list[dict[str, object]],
    *,
    source: str | None = None,
) -> str:
    source_description = f" in '{source}'" if source is not None else ""
    rendered = "; ".join(
        f"{_format_location(error.get('loc'))}: {error.get('msg', 'Invalid value')}"
        for error in errors
    )
    return f"Invalid evaluation report{source_description}: {rendered}"


def _format_location(location: object) -> str:
    if isinstance(location, (tuple, list)):
        return ".".join(str(part) for part in location) or "<root>"
    return str(location)
