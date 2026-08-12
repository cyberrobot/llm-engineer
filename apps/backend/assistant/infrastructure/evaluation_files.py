"""Filesystem catalog for server-managed evaluation datasets and reports."""

import re
from pathlib import Path
from stat import S_ISREG

from assistant.application.evaluation_admin import EvaluationDatasetResource
from assistant.evaluation import (
    EvaluationReportExistsError,
    EvaluationReportMetadata,
    EvaluationRun,
    load_evaluation_dataset,
    load_evaluation_report,
    load_evaluation_report_metadata,
    save_evaluation_report_to_directory,
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class InvalidEvaluationResourceIdentifier(ValueError):
    """Raised before a caller-controlled identifier reaches filesystem resolution."""


class EvaluationDatasetResourceNotFound(LookupError):
    """Raised when no server-managed dataset has the requested identifier."""


class EvaluationReportResourceNotFound(LookupError):
    """Raised when no server-managed report has the requested run identifier."""


class EvaluationResourceDirectoryError(OSError):
    """Raised when a configured evaluation resource directory cannot be inspected."""


class EvaluationResourceCatalogError(ValueError):
    """Raised when server-managed resources have ambiguous or unsafe identities."""


class FileSystemEvaluationResources:
    """Discover direct JSON children without accepting client filesystem paths."""

    def __init__(self, *, dataset_directory: Path, report_directory: Path) -> None:
        self._dataset_directory = dataset_directory
        self._report_directory = report_directory

    def list_datasets(self) -> list[EvaluationDatasetResource]:
        resources: list[EvaluationDatasetResource] = []
        for path in self._json_files(self._dataset_directory):
            identifier = path.stem
            if not _is_safe_identifier(identifier):
                raise EvaluationResourceCatalogError(
                    "A repository-managed evaluation dataset has an unsafe identifier"
                )
            resources.append(
                EvaluationDatasetResource(
                    identifier=identifier,
                    dataset=load_evaluation_dataset(path),
                )
            )
        return sorted(resources, key=lambda resource: resource.identifier)

    def get_dataset(self, identifier: str) -> EvaluationDatasetResource:
        _validate_identifier(identifier)
        for resource in self.list_datasets():
            if resource.identifier == identifier:
                return resource
        raise EvaluationDatasetResourceNotFound(identifier)

    def save_report(self, run: EvaluationRun) -> None:
        if any(existing.id == run.id for existing in self.list_reports()):
            raise EvaluationReportExistsError(
                "An evaluation report with this run identifier already exists"
            )
        save_evaluation_report_to_directory(
            run,
            output_dir=self._report_directory,
            overwrite=False,
        )

    def list_reports(self) -> list[EvaluationReportMetadata]:
        reports: list[EvaluationReportMetadata] = []
        seen_ids: set[str] = set()
        for path in self._json_files(self._report_directory):
            metadata = load_evaluation_report_metadata(path)
            if not _is_safe_identifier(metadata.id):
                raise EvaluationResourceCatalogError(
                    "A repository-managed evaluation report has an unsafe run identifier"
                )
            if metadata.id in seen_ids:
                raise EvaluationResourceCatalogError(
                    "Repository-managed evaluation reports contain a duplicate run identifier"
                )
            seen_ids.add(metadata.id)
            reports.append(metadata)
        return sorted(reports, key=_report_order, reverse=True)

    def get_report(self, run_id: str) -> EvaluationRun:
        _validate_identifier(run_id)
        for path in self._json_files(self._report_directory):
            metadata = load_evaluation_report_metadata(path)
            if metadata.id == run_id:
                return load_evaluation_report(path)
        raise EvaluationReportResourceNotFound(run_id)

    @staticmethod
    def _json_files(directory: Path) -> list[Path]:
        try:
            if not directory.exists():
                return []
            if not directory.is_dir():
                raise EvaluationResourceDirectoryError(
                    "Configured evaluation resource location is not a directory"
                )
            paths = []
            for path in directory.iterdir():
                if path.suffix != ".json" or path.is_symlink():
                    continue
                if S_ISREG(path.stat().st_mode):
                    paths.append(path)
            return sorted(paths, key=lambda path: path.name)
        except EvaluationResourceDirectoryError:
            raise
        except OSError as exc:
            raise EvaluationResourceDirectoryError(
                "Configured evaluation resource directory could not be read"
            ) from exc


def _validate_identifier(identifier: str) -> None:
    if not _is_safe_identifier(identifier):
        raise InvalidEvaluationResourceIdentifier(identifier)


def _is_safe_identifier(identifier: str) -> bool:
    return bool(_SAFE_IDENTIFIER.fullmatch(identifier)) and ".." not in identifier


def _report_order(report: EvaluationReportMetadata) -> tuple[object, ...]:
    completed = report.completed_at or report.started_at
    return (
        completed is not None,
        completed.isoformat() if completed is not None else "",
        report.started_at.isoformat() if report.started_at is not None else "",
        report.id,
    )
