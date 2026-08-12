"""Administrator orchestration over the existing evaluation subsystem."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from assistant.evaluation import (
    EvaluationComparisonResult,
    EvaluationDataset,
    EvaluationRegressionPolicy,
    EvaluationRun,
    EvaluationRunner,
    EvaluationRunOptions,
    compare_evaluation_runs,
)


@dataclass(frozen=True, slots=True)
class EvaluationDatasetResource:
    """A server-controlled dataset identity and its validated domain value."""

    identifier: str
    dataset: EvaluationDataset


@dataclass(frozen=True, slots=True)
class EvaluationExecutionResult:
    run: EvaluationRun
    report_persisted: bool


class EvaluationResourceRepository(Protocol):
    """Server-managed dataset and report storage used by administration."""

    def list_datasets(self) -> Sequence[EvaluationDatasetResource]: ...

    def get_dataset(self, identifier: str) -> EvaluationDatasetResource: ...

    def save_report(self, run: EvaluationRun) -> None: ...

    def list_reports(self) -> Sequence[EvaluationRun]: ...

    def get_report(self, run_id: str) -> EvaluationRun: ...


class EvaluationAdministrationService:
    """Coordinate safe resource selection and canonical evaluation operations."""

    def __init__(
        self,
        resources: EvaluationResourceRepository,
        *,
        runner_factory: Callable[[], EvaluationRunner],
    ) -> None:
        self._resources = resources
        self._runner_factory = runner_factory

    def list_datasets(self) -> Sequence[EvaluationDatasetResource]:
        return self._resources.list_datasets()

    def get_dataset(self, identifier: str) -> EvaluationDatasetResource:
        return self._resources.get_dataset(identifier)

    def execute(
        self,
        *,
        dataset_id: str,
        options: EvaluationRunOptions | None = None,
        persist_report: bool = False,
    ) -> EvaluationExecutionResult:
        dataset = self._resources.get_dataset(dataset_id).dataset
        runner = self._runner_factory()
        run = runner.run_dataset(dataset, options=options)
        if persist_report:
            self._resources.save_report(run)
        return EvaluationExecutionResult(run=run, report_persisted=persist_report)

    def list_reports(self, *, limit: int, offset: int) -> tuple[Sequence[EvaluationRun], int]:
        reports = self._resources.list_reports()
        return reports[offset : offset + limit], len(reports)

    def get_report(self, run_id: str) -> EvaluationRun:
        return self._resources.get_report(run_id)

    def compare(
        self,
        *,
        candidate_run_id: str,
        baseline_run_id: str,
        policy: EvaluationRegressionPolicy | None = None,
    ) -> EvaluationComparisonResult:
        candidate = self._resources.get_report(candidate_run_id)
        baseline = self._resources.get_report(baseline_run_id)
        return compare_evaluation_runs(
            baseline=baseline,
            current=candidate,
            policy=policy,
        )
