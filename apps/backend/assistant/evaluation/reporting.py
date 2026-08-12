"""Persist complete terminal evaluation runs as versioned JSON reports."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import TextIOBase
from pathlib import Path
from stat import S_ISREG

from pydantic import ValidationError

from assistant.evaluation.models import EvaluationRun, EvaluationRunStatus, EvaluationSummary

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


@dataclass(frozen=True, slots=True)
class EvaluationReportMetadata:
    """Validated report-listing fields without materialized case results or content."""

    id: str
    dataset_name: str
    dataset_version: str
    status: EvaluationRunStatus
    schema_version: str
    started_at: datetime | None
    completed_at: datetime | None
    summary: EvaluationSummary | None


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


def load_evaluation_report_metadata(path: str | Path) -> EvaluationReportMetadata:
    """Stream and validate report-listing fields without retaining complete case results."""

    report_path = Path(path)
    try:
        if not S_ISREG(report_path.stat().st_mode):
            raise EvaluationReportReadError(
                f"Evaluation report path '{report_path}' is not a regular file"
            )
        with report_path.open("r", encoding="utf-8") as report_file:
            data, fields = _JsonEnvelopeReader(report_file).read_object(
                capture={
                    "id",
                    "dataset_name",
                    "dataset_version",
                    "status",
                    "schema_version",
                    "started_at",
                    "completed_at",
                    "summary",
                }
            )
    except EvaluationReportReadError:
        raise
    except FileNotFoundError as exc:
        raise EvaluationReportReadError(
            f"Evaluation report file not found: '{report_path}'"
        ) from exc
    except UnicodeDecodeError as exc:
        raise EvaluationReportReadError(
            f"Evaluation report file '{report_path}' is not valid UTF-8"
        ) from exc
    except OSError as exc:
        raise EvaluationReportReadError(
            f"Could not read evaluation report file '{report_path}': {exc}"
        ) from exc
    except _JsonEnvelopeError as exc:
        raise EvaluationReportJsonError(
            f"Invalid evaluation report JSON in '{report_path}' at "
            f"line {exc.line}, column {exc.column}: {exc}"
        ) from exc

    if "schema_version" not in fields:
        details: list[dict[str, object]] = [
            {
                "type": "missing",
                "loc": ("schema_version",),
                "msg": "Persisted evaluation reports must explicitly declare schema_version",
            }
        ]
        raise EvaluationReportValidationError(
            _validation_message(details, source=str(report_path)), errors=details
        )
    schema_version = data.get("schema_version")
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(_SUPPORTED_SCHEMA_VERSIONS)
        raise UnsupportedEvaluationReportSchemaError(
            f"Unsupported evaluation report schema version '{schema_version}' "
            f"in '{report_path}'; supported versions: {supported}"
        )

    candidate = dict(data)
    if "results" in fields:
        candidate["results"] = []
    try:
        run = EvaluationRun.model_validate(candidate)
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
            _validation_message(details, source=str(report_path)), errors=details
        ) from exc
    _validate_terminal_run(run)
    return EvaluationReportMetadata(
        id=run.id,
        dataset_name=run.dataset_name,
        dataset_version=run.dataset_version,
        status=run.status,
        schema_version=run.schema_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary=run.summary,
    )


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


class _JsonEnvelopeError(ValueError):
    def __init__(self, message: str, *, line: int, column: int) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


class _JsonEnvelopeReader:
    """Validate one JSON object while retaining only selected top-level values."""

    _CHUNK_SIZE = 8192

    def __init__(self, source: TextIOBase) -> None:
        self._source = source
        self._buffer = ""
        self._position = 0
        self._eof = False
        self._line = 1
        self._column = 1
        self._capture: list[str] | None = None

    def read_object(self, *, capture: set[str]) -> tuple[dict[str, object], set[str]]:
        values: dict[str, object] = {}
        fields: set[str] = set()
        self._skip_whitespace()
        self._expect("{")
        self._skip_whitespace()
        if self._peek() == "}":
            self._take()
        else:
            while True:
                key = self._read_captured_string()
                fields.add(key)
                self._skip_whitespace()
                self._expect(":")
                self._skip_whitespace()
                if key == "results" and self._peek() != "[":
                    self._fail("results must be a JSON array")
                if key in capture:
                    values[key] = self._read_captured_value()
                else:
                    self._skip_value()
                self._skip_whitespace()
                separator = self._take()
                if separator == "}":
                    break
                if separator != ",":
                    self._fail("expected ',' or '}'")
                self._skip_whitespace()
        self._skip_whitespace()
        if self._peek():
            self._fail("unexpected content after the JSON object")
        return values, fields

    def _read_captured_string(self) -> str:
        captured = self._capture_with(self._skip_string)
        value = json.loads(captured)
        if not isinstance(value, str):
            self._fail("object keys must be strings")
        return value

    def _read_captured_value(self) -> object:
        return json.loads(self._capture_with(self._skip_value))

    def _capture_with(self, operation) -> str:
        if self._capture is not None:
            self._fail("nested JSON capture is not supported")
        captured: list[str] = []
        self._capture = captured
        try:
            operation()
        finally:
            self._capture = None
        return "".join(captured)

    def _skip_value(self) -> None:
        self._skip_whitespace()
        character = self._peek()
        if character == '"':
            self._skip_string()
        elif character == "{":
            self._skip_object()
        elif character == "[":
            self._skip_array()
        elif character:
            self._skip_primitive()
        else:
            self._fail("expected a JSON value")

    def _skip_object(self) -> None:
        self._expect("{")
        self._skip_whitespace()
        if self._peek() == "}":
            self._take()
            return
        while True:
            self._skip_string()
            self._skip_whitespace()
            self._expect(":")
            self._skip_value()
            self._skip_whitespace()
            separator = self._take()
            if separator == "}":
                return
            if separator != ",":
                self._fail("expected ',' or '}'")
            self._skip_whitespace()

    def _skip_array(self) -> None:
        self._expect("[")
        self._skip_whitespace()
        if self._peek() == "]":
            self._take()
            return
        while True:
            self._skip_value()
            self._skip_whitespace()
            separator = self._take()
            if separator == "]":
                return
            if separator != ",":
                self._fail("expected ',' or ']'")
            self._skip_whitespace()

    def _skip_string(self) -> None:
        self._expect('"')
        while True:
            character = self._take()
            if not character:
                self._fail("unterminated JSON string")
            if character == '"':
                return
            if ord(character) < 0x20:
                self._fail("unescaped control character in JSON string")
            if character != "\\":
                continue
            escape = self._take()
            if escape in {'"', "\\", "/", "b", "f", "n", "r", "t"}:
                continue
            if escape != "u":
                self._fail("invalid JSON string escape")
            for _ in range(4):
                hexadecimal = self._take()
                if hexadecimal not in "0123456789abcdefABCDEF":
                    self._fail("invalid Unicode escape in JSON string")

    def _skip_primitive(self) -> None:
        captured: list[str] = []
        while True:
            character = self._peek()
            if not character or character.isspace() or character in ",]}":
                break
            captured.append(self._take())
        token = "".join(captured)
        try:
            json.loads(token)
        except json.JSONDecodeError:
            self._fail("invalid JSON value")

    def _skip_whitespace(self) -> None:
        while self._peek() in {" ", "\t", "\r", "\n"}:
            self._take()

    def _expect(self, expected: str) -> None:
        if self._take() != expected:
            self._fail(f"expected '{expected}'")

    def _peek(self) -> str:
        if self._position >= len(self._buffer) and not self._eof:
            self._buffer = self._source.read(self._CHUNK_SIZE)
            self._position = 0
            self._eof = not self._buffer
        return self._buffer[self._position] if self._position < len(self._buffer) else ""

    def _take(self) -> str:
        character = self._peek()
        if not character:
            return ""
        self._position += 1
        if self._capture is not None:
            self._capture.append(character)
        if character == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return character

    def _fail(self, message: str) -> None:
        raise _JsonEnvelopeError(message, line=self._line, column=self._column)
