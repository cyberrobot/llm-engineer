"""Command-line presentation and production bootstrap for evaluation runs."""

import argparse
import sys
from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TextIO

from assistant.api.dependencies import (
    get_ai_provider,
    get_chat_service,
    get_knowledge_repository,
    get_retrieval_service,
    get_vector_store,
)
from assistant.evaluation.dataset_loader import (
    EvaluationDatasetError,
    EvaluationDatasetValidationError,
    load_evaluation_dataset,
)
from assistant.evaluation.models import (
    AnswerEvaluationOptions,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
)
from assistant.evaluation.reporting import (
    EvaluationReportError,
    save_evaluation_report,
    save_evaluation_report_to_directory,
)
from assistant.evaluation.runner import EvaluationRunner, EvaluationRunOptions
from infrastructure.ai.exceptions import AIConfigurationError


class EvaluationCliExitCode(IntEnum):
    """Stable process outcomes for the evaluation command."""

    SUCCESS = 0
    EVALUATION_FAILED = 1
    USAGE_ERROR = 2
    DATASET_ERROR = 3
    CASE_EXECUTION_ERROR = 4
    RUN_ERROR = 5
    REPORT_ERROR = 6


@dataclass(frozen=True, slots=True)
class CliArguments:
    dataset: str
    retrieval_k: int | None
    stop_on_error: bool
    allow_partial_source_recall: bool
    include_retrieved_content: bool
    case_sensitive: bool
    no_normalise_whitespace: bool
    allow_missing_citations: bool
    skip_citation_validation: bool
    json: bool
    pretty: bool
    report: str | None
    report_dir: str | None
    overwrite_report: bool


DatasetLoader = Callable[[str | Path], EvaluationDataset]
RunnerContextFactory = Callable[[], AbstractContextManager[EvaluationRunner]]


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer greater than or equal to 1") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than or equal to 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m assistant.evaluation",
        description=(
            "Run a validated evaluation dataset against the configured retrieval "
            "and answer services."
        ),
        epilog=(
            "Exit codes: 0 all evaluated cases passed; 1 evaluation failures or all skipped; "
            "2 invalid usage; 3 dataset error; 4 case execution error; 5 run failure; "
            "6 requested report persistence failed."
        ),
    )
    parser.add_argument(
        "--dataset",
        required=True,
        metavar="PATH",
        help="Path to one JSON evaluation dataset (relative or absolute).",
    )
    parser.add_argument(
        "--retrieval-k",
        type=_positive_integer,
        metavar="INTEGER",
        help="Evaluate retrieval metrics at this depth (minimum 1).",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop after the first case execution error; the default continues.",
    )
    parser.add_argument(
        "--allow-partial-source-recall",
        action="store_true",
        help="Allow a retrieval hit to pass without retrieving every expected source.",
    )
    parser.add_argument(
        "--include-retrieved-content",
        action="store_true",
        help="Include retrieved chunk content in the in-memory result and JSON output.",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Match expected and excluded answer fragments case-sensitively.",
    )
    parser.add_argument(
        "--no-normalise-whitespace",
        action="store_true",
        help="Disable whitespace normalization during answer-fragment matching.",
    )
    parser.add_argument(
        "--allow-missing-citations",
        action="store_true",
        help="Do not require citations merely because expected sources are declared.",
    )
    parser.add_argument(
        "--skip-citation-validation",
        action="store_true",
        help="Do not validate answer citations against retrieved sources.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write only the complete serialized evaluation run to standard output.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Indent JSON output; valid only together with --json.",
    )
    report_destination = parser.add_mutually_exclusive_group()
    report_destination.add_argument(
        "--report",
        metavar="PATH",
        help="Save the complete run to exactly this report path.",
    )
    report_destination.add_argument(
        "--report-dir",
        metavar="PATH",
        help="Create this directory and save a report with a generated filename.",
    )
    parser.add_argument(
        "--overwrite-report",
        action="store_true",
        help="Replace an existing requested report; requires --report or --report-dir.",
    )
    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> CliArguments:
    """Parse command arguments without constructing application services."""

    parser = _parser()
    namespace = parser.parse_args(argv)
    if namespace.pretty and not namespace.json:
        parser.error("--pretty requires --json")
    if namespace.overwrite_report and not (namespace.report or namespace.report_dir):
        parser.error("--overwrite-report requires --report or --report-dir")
    return CliArguments(**vars(namespace))


def build_run_options(arguments: CliArguments) -> EvaluationRunOptions:
    """Map the explicit CLI surface onto the stable runner options."""

    return EvaluationRunOptions(
        retrieval_k=arguments.retrieval_k,
        continue_on_error=not arguments.stop_on_error,
        include_retrieved_content=arguments.include_retrieved_content,
        require_all_expected_sources=not arguments.allow_partial_source_recall,
        answer_options=AnswerEvaluationOptions(
            case_sensitive=arguments.case_sensitive,
            normalise_whitespace=not arguments.no_normalise_whitespace,
            require_citations_when_sources_expected=not arguments.allow_missing_citations,
            validate_citations_against_retrieval=not arguments.skip_citation_validation,
        ),
    )


@contextmanager
def build_evaluation_runner() -> Generator[EvaluationRunner, None, None]:
    """Compose and clean up the same production services used by the API."""

    provider = None
    try:
        provider = get_ai_provider()
        vector_store = get_vector_store()
        repository = get_knowledge_repository(vector_store)
        retrieval_service = get_retrieval_service(provider, repository)
        answer_service = get_chat_service(provider, retrieval_service)
        yield EvaluationRunner(
            retrieval_service=retrieval_service,
            answer_service=answer_service,
        )
    finally:
        if provider is not None:
            close = getattr(provider, "close", None)
            if close is not None:
                close()
        get_ai_provider.cache_clear()
        get_vector_store.cache_clear()


def execute_cli(
    arguments: CliArguments,
    *,
    load_dataset: DatasetLoader = load_evaluation_dataset,
    runner_context_factory: RunnerContextFactory = build_evaluation_runner,
) -> EvaluationRun:
    """Load one dataset and execute it through a lifecycle-managed runner."""

    dataset = load_dataset(arguments.dataset)
    options = build_run_options(arguments)
    with runner_context_factory() as runner:
        return runner.run_dataset(dataset, options=options)


def _format_ratio(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _format_mrr(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _format_duration(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value >= 1_000:
        return f"{value / 1_000:.2f} s"
    return f"{value:.0f} ms"


def render_evaluation_summary(run: EvaluationRun) -> str:
    """Render metrics already present on a completed run without recalculating them."""

    summary = run.summary
    if summary is None:
        raise ValueError("Evaluation run does not contain a summary")
    return "\n".join(
        [
            "Evaluation completed",
            f"Run ID: {run.id}",
            f"Dataset: {run.dataset_name}",
            f"Dataset version: {run.dataset_version}",
            f"Status: {run.status.value}",
            "Cases",
            f"  Total:   {summary.total_cases}",
            f"  Passed:  {summary.passed_cases}",
            f"  Failed:  {summary.failed_cases}",
            f"  Errors:  {summary.error_cases}",
            f"  Skipped: {summary.skipped_cases}",
            "Retrieval",
            f"  Hit rate: {_format_ratio(summary.retrieval_hit_rate)}",
            f"  Recall@K: {_format_ratio(summary.retrieval_recall_at_k)}",
            f"  MRR:      {_format_mrr(summary.mean_reciprocal_rank)}",
            "Answers",
            f"  Pass rate: {_format_ratio(summary.answer_pass_rate)}",
            "Timing",
            f"  Average case duration: {_format_duration(summary.average_duration_ms)}",
        ]
    )


def render_case_failures(run: EvaluationRun) -> str:
    """Render concise diagnostics for non-passing cases in run order."""

    non_passing = [
        result
        for result in run.results
        if result.status in {EvaluationCaseStatus.FAILED, EvaluationCaseStatus.ERROR}
    ]
    if not non_passing:
        return ""

    lines = ["Non-passing cases"]
    for result in non_passing:
        lines.append(f"- {result.case_id} [{result.status.value}]")
        if result.retrieval is not None:
            lines.extend(f"  Retrieval: {reason}" for reason in result.retrieval.failure_reasons)
        if result.answer is not None:
            lines.extend(f"  Answer: {reason}" for reason in result.answer.failure_reasons)
        if result.error is not None:
            lines.append(f"  Error: {result.error}")
    return "\n".join(lines)


def exit_code_for_run(run: EvaluationRun) -> EvaluationCliExitCode:
    """Select a deterministic exit code from a usable completed run."""

    summary = run.summary
    if summary is None or run.status in {EvaluationRunStatus.PENDING, EvaluationRunStatus.RUNNING}:
        return EvaluationCliExitCode.RUN_ERROR
    if summary.error_cases:
        return EvaluationCliExitCode.CASE_EXECUTION_ERROR
    if summary.failed_cases:
        return EvaluationCliExitCode.EVALUATION_FAILED
    if summary.total_cases > 0 and summary.skipped_cases == summary.total_cases:
        return EvaluationCliExitCode.EVALUATION_FAILED
    return EvaluationCliExitCode.SUCCESS


def _render_dataset_error(error: EvaluationDatasetError) -> str:
    if isinstance(error, EvaluationDatasetValidationError):
        lines = ["Invalid evaluation dataset:"]
        for detail in error.errors:
            location = detail.get("loc")
            if isinstance(location, (tuple, list)):
                field = ".".join(str(part) for part in location) or "<root>"
            else:
                field = str(location)
            lines.append(f"- {field}: {detail.get('msg', 'Invalid value')}")
        return "\n".join(lines)
    return f"Unable to load evaluation dataset:\n{error}"


def run_cli(
    arguments: CliArguments,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    load_dataset: DatasetLoader = load_evaluation_dataset,
    runner_context_factory: RunnerContextFactory = build_evaluation_runner,
) -> int:
    """Execute parsed arguments, separate result/error streams, and return an exit code."""

    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    try:
        run = execute_cli(
            arguments,
            load_dataset=load_dataset,
            runner_context_factory=runner_context_factory,
        )
    except EvaluationDatasetError as exc:
        print(_render_dataset_error(exc), file=error_stream)
        return EvaluationCliExitCode.DATASET_ERROR
    except AIConfigurationError as exc:
        print(f"Unable to configure evaluation services: {exc}", file=error_stream)
        return EvaluationCliExitCode.RUN_ERROR
    except Exception as exc:
        print(
            f"Unable to execute evaluation run ({type(exc).__name__}).",
            file=error_stream,
        )
        return EvaluationCliExitCode.RUN_ERROR

    exit_code = exit_code_for_run(run)
    if exit_code is EvaluationCliExitCode.RUN_ERROR:
        print("Evaluation runner did not return a usable completed run.", file=error_stream)
        return exit_code

    if arguments.json:
        print(run.model_dump_json(indent=2 if arguments.pretty else None), file=output_stream)
    else:
        rendered = render_evaluation_summary(run)
        failures = render_case_failures(run)
        print(f"{rendered}\n\n{failures}" if failures else rendered, file=output_stream)

    if arguments.report is not None or arguments.report_dir is not None:
        try:
            if arguments.report is not None:
                report_path = save_evaluation_report(
                    run,
                    arguments.report,
                    overwrite=arguments.overwrite_report,
                )
            else:
                report_path = save_evaluation_report_to_directory(
                    run,
                    output_dir=arguments.report_dir or "",
                    overwrite=arguments.overwrite_report,
                )
        except EvaluationReportError as exc:
            print(f"Unable to save evaluation report: {exc}", file=error_stream)
            return EvaluationCliExitCode.REPORT_ERROR
        confirmation_stream = error_stream if arguments.json else output_stream
        print(f"Report saved to: {report_path}", file=confirmation_stream)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Public module entry point returning the stable evaluation CLI exit code."""

    try:
        arguments = parse_arguments(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EvaluationCliExitCode.USAGE_ERROR
    return run_cli(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
