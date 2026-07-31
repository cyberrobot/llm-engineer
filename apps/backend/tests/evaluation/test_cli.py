import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from io import StringIO

import pytest

from assistant.evaluation import (
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationSummary,
    RetrievalEvaluationResult,
)
from assistant.evaluation.cli import (
    EvaluationCliExitCode,
    build_run_options,
    exit_code_for_run,
    main,
    parse_arguments,
    render_case_failures,
    render_evaluation_summary,
    run_cli,
)
from assistant.evaluation.dataset_loader import (
    EvaluationDatasetFileNotFoundError,
    EvaluationDatasetValidationError,
)
from infrastructure.ai.exceptions import AIConfigurationError


def _summary(
    *,
    total: int = 3,
    passed: int = 3,
    failed: int = 0,
    errors: int = 0,
    skipped: int = 0,
) -> EvaluationSummary:
    return EvaluationSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        error_cases=errors,
        skipped_cases=skipped,
        retrieval_recall_at_k=0.7812,
        retrieval_hit_rate=0.833333,
        mean_reciprocal_rank=0.81234,
        answer_pass_rate=0.75,
        average_duration_ms=842.0,
    )


def _result(
    case_id: str,
    status: EvaluationCaseStatus,
    *,
    retrieval_reasons: list[str] | None = None,
    answer_reasons: list[str] | None = None,
    error: str | None = None,
) -> EvaluationCaseResult:
    retrieval = (
        RetrievalEvaluationResult(
            retrieved_items=[],
            failure_reasons=retrieval_reasons,
        )
        if retrieval_reasons is not None
        else None
    )
    answer = (
        AnswerEvaluationResult(answer="short answer", failure_reasons=answer_reasons)
        if answer_reasons is not None
        else None
    )
    return EvaluationCaseResult(
        case_id=case_id,
        question=f"Question for {case_id}?",
        status=status,
        retrieval=retrieval,
        answer=answer,
        error=error,
    )


def _run(
    *,
    summary: EvaluationSummary | None = None,
    results: list[EvaluationCaseResult] | None = None,
    status: EvaluationRunStatus = EvaluationRunStatus.COMPLETED,
) -> EvaluationRun:
    return EvaluationRun(
        id="run-123",
        dataset_name="support-baseline",
        dataset_version="2026.07",
        status=status,
        results=results or [],
        started_at=datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 30, 9, 1, tzinfo=timezone.utc),
        summary=summary or _summary(),
        configuration={"retrieval_k": None},
    )


def test_parser_requires_dataset_and_rejects_invalid_retrieval_depth(capsys):
    with pytest.raises(SystemExit) as missing:
        parse_arguments([])
    assert missing.value.code == EvaluationCliExitCode.USAGE_ERROR

    for invalid in ("0", "-1", "not-an-integer"):
        with pytest.raises(SystemExit) as rejected:
            parse_arguments(["--dataset", "suite.json", "--retrieval-k", invalid])
        assert rejected.value.code == EvaluationCliExitCode.USAGE_ERROR

    assert "--dataset" in capsys.readouterr().err


def test_parser_accepts_relative_path_and_maps_explicit_runner_options():
    arguments = parse_arguments(
        [
            "--dataset",
            "examples/evaluation/suite.json",
            "--retrieval-k",
            "5",
            "--stop-on-error",
            "--allow-partial-source-recall",
            "--include-retrieved-content",
            "--case-sensitive",
            "--no-normalise-whitespace",
            "--allow-missing-citations",
            "--skip-citation-validation",
            "--json",
            "--pretty",
        ]
    )

    assert arguments.dataset == "examples/evaluation/suite.json"
    assert arguments.json is True
    assert arguments.pretty is True
    assert build_run_options(arguments).model_dump() == {
        "retrieval_k": 5,
        "continue_on_error": False,
        "include_retrieved_content": True,
        "require_all_expected_sources": False,
        "answer_options": {
            "case_sensitive": True,
            "normalise_whitespace": False,
            "require_all_expected_fragments": True,
            "require_citations_when_sources_expected": False,
            "validate_citations_against_retrieval": False,
        },
        "metadata": {},
    }


def test_omitted_options_preserve_runner_and_answer_evaluator_defaults():
    options = build_run_options(parse_arguments(["--dataset", "/tmp/suite.json"]))

    assert options.retrieval_k is None
    assert options.continue_on_error is True
    assert options.include_retrieved_content is False
    assert options.require_all_expected_sources is True
    assert options.answer_options == AnswerEvaluationOptions()


def test_pretty_requires_json_and_help_succeeds(capsys):
    with pytest.raises(SystemExit) as incompatible:
        parse_arguments(["--dataset", "suite.json", "--pretty"])
    assert incompatible.value.code == EvaluationCliExitCode.USAGE_ERROR

    with pytest.raises(SystemExit) as help_result:
        parse_arguments(["--help"])
    assert help_result.value.code == EvaluationCliExitCode.SUCCESS
    assert "validated evaluation dataset" in capsys.readouterr().out


def test_report_arguments_are_explicit_and_validated(capsys):
    explicit = parse_arguments(
        ["--dataset", "suite.json", "--report", "reports/latest.data", "--overwrite-report"]
    )
    generated = parse_arguments(["--dataset", "suite.json", "--report-dir", "reports"])

    assert explicit.report == "reports/latest.data"
    assert explicit.report_dir is None
    assert explicit.overwrite_report is True
    assert generated.report is None
    assert generated.report_dir == "reports"

    with pytest.raises(SystemExit) as conflicting:
        parse_arguments(
            [
                "--dataset",
                "suite.json",
                "--report",
                "one.json",
                "--report-dir",
                "reports",
            ]
        )
    assert conflicting.value.code == EvaluationCliExitCode.USAGE_ERROR

    with pytest.raises(SystemExit) as meaningless:
        parse_arguments(["--dataset", "suite.json", "--overwrite-report"])
    assert meaningless.value.code == EvaluationCliExitCode.USAGE_ERROR
    assert "--overwrite-report requires" in capsys.readouterr().err


def test_human_renderer_includes_required_summary_and_formats_metrics():
    output = render_evaluation_summary(_run())

    assert "Evaluation completed" in output
    assert "Run ID: run-123" in output
    assert "Dataset: support-baseline" in output
    assert "Dataset version: 2026.07" in output
    assert "Status: completed" in output
    assert "Total:   3" in output
    assert "Passed:  3" in output
    assert "Hit rate: 83.33%" in output
    assert "Recall@K: 78.12%" in output
    assert "MRR:      0.812" in output
    assert "Pass rate: 75.00%" in output
    assert "Average case duration: 842 ms" in output


def test_human_renderer_preserves_none_and_zero_metrics_without_recalculation():
    summary = EvaluationSummary(
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        error_cases=0,
        skipped_cases=0,
        retrieval_recall_at_k=None,
        retrieval_hit_rate=0.0,
        mean_reciprocal_rank=None,
        answer_pass_rate=0.0,
        average_duration_ms=1_250.0,
    )

    output = render_evaluation_summary(_run(summary=summary))

    assert "Hit rate: 0.00%" in output
    assert "Recall@K: N/A" in output
    assert "MRR:      N/A" in output
    assert "Pass rate: 0.00%" in output
    assert "Average case duration: 1.25 s" in output


def test_case_failure_renderer_lists_safe_reasons_in_dataset_order():
    run = _run(
        summary=_summary(total=3, passed=0, failed=2, errors=1),
        results=[
            _result(
                "first",
                EvaluationCaseStatus.FAILED,
                retrieval_reasons=["missing_expected_source"],
                answer_reasons=["citation_not_in_retrieval", "missing_fragment"],
            ),
            _result(
                "second",
                EvaluationCaseStatus.ERROR,
                error="evaluation case failed (RuntimeError)",
            ),
            _result("third", EvaluationCaseStatus.FAILED, answer_reasons=[]),
        ],
    )

    output = render_case_failures(run)

    assert output.index("first") < output.index("second") < output.index("third")
    assert "Retrieval: missing_expected_source" in output
    assert "Answer: citation_not_in_retrieval" in output
    assert "Answer: missing_fragment" in output
    assert "Error: evaluation case failed (RuntimeError)" in output
    assert "Question for" not in output
    assert "short answer" not in output


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (_summary(), EvaluationCliExitCode.SUCCESS),
        (_summary(total=2, passed=1, failed=1), EvaluationCliExitCode.EVALUATION_FAILED),
        (
            _summary(total=3, passed=1, failed=1, errors=1),
            EvaluationCliExitCode.CASE_EXECUTION_ERROR,
        ),
        (_summary(total=2, passed=1, skipped=1), EvaluationCliExitCode.SUCCESS),
        (_summary(total=2, passed=0, skipped=2), EvaluationCliExitCode.EVALUATION_FAILED),
    ],
)
def test_exit_code_selection_obeys_completed_run_precedence(summary, expected):
    assert exit_code_for_run(_run(summary=summary)) is expected


def test_successful_human_orchestration_loads_before_bootstrap_and_cleans_up():
    events: list[object] = []
    dataset = EvaluationDataset(
        name="suite",
        version="v1",
        cases=[EvaluationCase(id="one", question="Question?")],
    )
    expected_run = _run()

    class Runner:
        def run_dataset(self, loaded_dataset, *, options):
            events.append(("run", loaded_dataset, options))
            return expected_run

    def loader(path):
        events.append(("load", path))
        return dataset

    @contextmanager
    def runner_context():
        events.append("open")
        try:
            yield Runner()
        finally:
            events.append("close")

    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "suite.json"]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=loader,
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.SUCCESS
    assert events[0] == ("load", "suite.json")
    assert events[1] == "open"
    assert events[-1] == "close"
    assert "Evaluation completed" in stdout.getvalue()
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (_summary(), EvaluationCliExitCode.SUCCESS),
        (_summary(total=1, passed=0, failed=1), EvaluationCliExitCode.EVALUATION_FAILED),
        (_summary(total=1, passed=0, errors=1), EvaluationCliExitCode.CASE_EXECUTION_ERROR),
    ],
)
def test_json_output_is_complete_valid_and_keeps_outcome_exit_code(summary, expected):
    expected_run = _run(summary=summary)

    class Runner:
        def run_dataset(self, _dataset, *, options):
            return expected_run

    @contextmanager
    def runner_context():
        yield Runner()

    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "suite.json", "--json"]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    payload = json.loads(stdout.getvalue())
    assert code == expected
    assert payload["id"] == "run-123"
    assert payload["status"] == "completed"
    assert payload["started_at"] == "2026-07-30T09:00:00Z"
    assert "Evaluation completed" not in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_pretty_json_changes_only_formatting():
    expected_run = _run()

    class Runner:
        def run_dataset(self, _dataset, *, options):
            return expected_run

    @contextmanager
    def runner_context():
        yield Runner()

    outputs = []
    for extra in ([], ["--pretty"]):
        stdout = StringIO()
        run_cli(
            parse_arguments(["--dataset", "suite.json", "--json", *extra]),
            stdout=stdout,
            stderr=StringIO(),
            load_dataset=lambda _path: object(),
            runner_context_factory=runner_context,
        )
        outputs.append(stdout.getvalue())

    assert json.loads(outputs[0]) == json.loads(outputs[1])
    assert '\n  "id"' in outputs[1]


@pytest.mark.parametrize(
    ("extra", "expected_name"),
    [
        (["--report", "latest.data"], "latest.data"),
        (["--report-dir", "reports"], None),
    ],
)
def test_cli_persists_report_after_run_and_preserves_outcome(
    tmp_path, monkeypatch, extra, expected_name
):
    monkeypatch.chdir(tmp_path)
    expected_run = _run(summary=_summary(total=1, passed=0, failed=1))

    class Runner:
        def run_dataset(self, _dataset, *, options):
            return expected_run

    @contextmanager
    def runner_context():
        yield Runner()

    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "suite.json", *extra]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    reports = list(tmp_path.rglob("*.json")) + list(tmp_path.rglob("*.data"))
    assert code == EvaluationCliExitCode.EVALUATION_FAILED
    assert len(reports) == 1
    if expected_name is not None:
        assert reports[0].name == expected_name
    assert json.loads(reports[0].read_text(encoding="utf-8"))["id"] == "run-123"
    assert f"Report saved to: {reports[0].relative_to(tmp_path)}" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_json_mode_report_confirmation_uses_stderr_without_corrupting_stdout(tmp_path):
    expected_run = _run()

    class Runner:
        def run_dataset(self, _dataset, *, options):
            return expected_run

    @contextmanager
    def runner_context():
        yield Runner()

    path = tmp_path / "run.json"
    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "suite.json", "--json", "--report", str(path)]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.SUCCESS
    assert json.loads(stdout.getvalue())["id"] == "run-123"
    assert stderr.getvalue() == f"Report saved to: {path}\n"


def test_failed_partial_run_with_case_error_is_persisted_and_keeps_case_error_exit_code(tmp_path):
    expected_run = _run(
        status=EvaluationRunStatus.FAILED,
        summary=_summary(total=2, passed=0, errors=1, skipped=1),
    )

    class Runner:
        def run_dataset(self, _dataset, *, options):
            return expected_run

    @contextmanager
    def runner_context():
        yield Runner()

    path = tmp_path / "partial.json"
    code = run_cli(
        parse_arguments(["--dataset", "suite.json", "--report", str(path)]),
        stdout=StringIO(),
        stderr=StringIO(),
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.CASE_EXECUTION_ERROR
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "failed"


def test_report_error_takes_precedence_and_does_not_claim_success(tmp_path):
    expected_run = _run(summary=_summary(total=1, passed=0, errors=1))
    path = tmp_path / "existing.json"
    path.write_text("keep", encoding="utf-8")

    class Runner:
        def run_dataset(self, _dataset, *, options):
            return expected_run

    @contextmanager
    def runner_context():
        yield Runner()

    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "suite.json", "--report", str(path)]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.REPORT_ERROR
    assert "Evaluation completed" in stdout.getvalue()
    assert "Unable to save evaluation report" in stderr.getvalue()
    assert "Report saved" not in stdout.getvalue() + stderr.getvalue()
    assert path.read_text(encoding="utf-8") == "keep"


def test_cli_without_report_flags_creates_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class Runner:
        def run_dataset(self, _dataset, *, options):
            return _run()

    @contextmanager
    def runner_context():
        yield Runner()

    code = run_cli(
        parse_arguments(["--dataset", "suite.json"]),
        stdout=StringIO(),
        stderr=StringIO(),
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.SUCCESS
    assert list(tmp_path.iterdir()) == []


def test_dataset_errors_use_stderr_do_not_bootstrap_and_return_three():
    opened = False

    @contextmanager
    def runner_context():
        nonlocal opened
        opened = True
        yield object()

    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "missing.json", "--json"]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: (_ for _ in ()).throw(
            EvaluationDatasetFileNotFoundError("file not found: missing.json")
        ),
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.DATASET_ERROR
    assert stdout.getvalue() == ""
    assert "missing.json" in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()
    assert opened is False


def test_structured_dataset_validation_paths_are_rendered_to_stderr():
    error = EvaluationDatasetValidationError(
        "invalid dataset",
        errors=[{"loc": ("cases", 2, "question"), "msg": "Value must not be empty"}],
    )
    stdout, stderr = StringIO(), StringIO()

    code = run_cli(
        parse_arguments(["--dataset", "invalid.json"]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: (_ for _ in ()).throw(error),
        runner_context_factory=lambda: pytest.fail("services must not be constructed"),
    )

    assert code == EvaluationCliExitCode.DATASET_ERROR
    assert stdout.getvalue() == ""
    assert "cases.2.question: Value must not be empty" in stderr.getvalue()


@pytest.mark.parametrize("failure_stage", ["bootstrap", "run"])
def test_run_level_failures_are_safe_use_stderr_and_close_resources(failure_stage):
    events = []

    class Runner:
        def run_dataset(self, _dataset, *, options):
            raise RuntimeError("token=top-secret")

    @contextmanager
    def runner_context():
        events.append("open")
        try:
            if failure_stage == "bootstrap":
                raise RuntimeError("token=top-secret")
            yield Runner()
        finally:
            events.append("close")

    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "suite.json", "--json"]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.RUN_ERROR
    assert stdout.getvalue() == ""
    assert "RuntimeError" in stderr.getvalue()
    assert "top-secret" not in stderr.getvalue()
    assert "Traceback" not in stderr.getvalue()
    assert events[-1] == "close"


def test_known_configuration_failure_is_actionable_without_exposing_values():
    @contextmanager
    def runner_context():
        raise AIConfigurationError("OPENAI_API_KEY is not configured.")
        yield  # pragma: no cover

    stdout, stderr = StringIO(), StringIO()
    code = run_cli(
        parse_arguments(["--dataset", "suite.json"]),
        stdout=stdout,
        stderr=stderr,
        load_dataset=lambda _path: object(),
        runner_context_factory=runner_context,
    )

    assert code == EvaluationCliExitCode.RUN_ERROR
    assert stdout.getvalue() == ""
    assert "OPENAI_API_KEY is not configured" in stderr.getvalue()


def test_main_returns_native_usage_code_instead_of_constructing_services(capsys):
    assert main([]) == EvaluationCliExitCode.USAGE_ERROR
    assert "--dataset" in capsys.readouterr().err


def test_package_module_help_resolves_without_bootstrapping_services():
    result = subprocess.run(
        [sys.executable, "-m", "assistant.evaluation", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == EvaluationCliExitCode.SUCCESS
    assert "validated evaluation dataset" in result.stdout
    assert result.stderr == ""
