import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

import assistant.evaluation.reporting as reporting
from assistant.evaluation import (
    AnswerEvaluationResult,
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationReportExistsError,
    EvaluationReportJsonError,
    EvaluationReportPathError,
    EvaluationReportReadError,
    EvaluationReportValidationError,
    EvaluationReportWriteError,
    EvaluationRun,
    EvaluationRunStatus,
    EvaluationSummary,
    RetrievalEvaluationResult,
    RetrievedItem,
    UnsupportedEvaluationReportSchemaError,
    build_evaluation_report_path,
    load_evaluation_report,
    save_evaluation_report,
    save_evaluation_report_to_directory,
)


def _run(
    *,
    status: EvaluationRunStatus = EvaluationRunStatus.COMPLETED,
    dataset_name: str = "Support Knowledge/Baseline",
    dataset_version: str = "2026.07",
) -> EvaluationRun:
    started_at = datetime(2026, 7, 30, 8, 59, 12, tzinfo=timezone.utc)
    result = EvaluationCaseResult(
        case_id="unicode-case",
        question="How do I reset José's password?",
        status=EvaluationCaseStatus.PASSED,
        started_at=started_at,
        completed_at=started_at,
        duration_ms=0.0,
        retrieval=RetrievalEvaluationResult(
            retrieved_items=[
                RetrievedItem(
                    id="chunk-1",
                    rank=1,
                    document_id="account-guide",
                    metadata={"language": "日本語"},
                )
            ],
            hit=True,
            failure_reasons=["first-diagnostic", "second-diagnostic"],
        ),
        answer=AnswerEvaluationResult(
            answer="Use the reset link.",
            passed=True,
            matched_expected_fragments=["reset link"],
        ),
        metadata={"priority": 1},
    )
    return EvaluationRun(
        id="run-20260730-001",
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        status=status,
        results=[result],
        started_at=started_at,
        completed_at=started_at,
        summary=EvaluationSummary(
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            error_cases=0,
            skipped_cases=0,
            answer_pass_rate=1.0,
        ),
        configuration={"include_retrieved_content": False},
        metadata={"team": "quality"},
    )


def test_completed_report_round_trip_preserves_complete_run_and_format(tmp_path):
    run = _run()
    before = deepcopy(run)
    path = tmp_path / "nested" / "report.data"

    saved = save_evaluation_report(run, path)
    content = path.read_text(encoding="utf-8")
    payload = json.loads(content)

    assert saved == path
    assert content.endswith("\n")
    assert '\n  "id"' in content
    assert payload["schema_version"] == "1.0"
    assert payload["status"] == "completed"
    assert payload["started_at"] == "2026-07-30T08:59:12Z"
    assert (
        payload["results"][0]["retrieval"]["retrieved_items"][0]["document_id"] == "account-guide"
    )
    assert payload["results"][0]["answer"]["answer"] == "Use the reset link."
    assert payload["summary"]["total_cases"] == 1
    assert payload["configuration"] == {"include_retrieved_content": False}
    assert payload["metadata"] == {"team": "quality"}
    assert load_evaluation_report(path) == run
    assert run == before


def test_failed_terminal_report_and_compact_output_round_trip(tmp_path):
    run = _run(status=EvaluationRunStatus.FAILED)
    path = tmp_path / "failed.json"

    save_evaluation_report(run, path, pretty=False)

    assert "\n" not in path.read_text(encoding="utf-8").rstrip("\n")
    assert load_evaluation_report(path) == run


@pytest.mark.parametrize("status", [EvaluationRunStatus.PENDING, EvaluationRunStatus.RUNNING])
def test_transient_run_is_rejected_without_creating_destination(tmp_path, status):
    path = tmp_path / "report.json"

    with pytest.raises(EvaluationReportValidationError, match="terminal"):
        save_evaluation_report(_run(status=status), path)

    assert not path.exists()


def test_default_path_is_safe_deterministic_and_inside_requested_directory(tmp_path):
    run = _run(dataset_name="../../ Support : Knowledge !!!", dataset_version=" 2026/07 ")

    first = build_evaluation_report_path(run, output_dir=tmp_path)
    second = build_evaluation_report_path(run, output_dir=tmp_path)

    assert first == second
    assert first.parent == tmp_path
    assert first.name == "support-knowledge-2026-07-20260730T085912Z-run-20260730-001.json"


def test_empty_filename_components_use_fallback_and_directory_is_created_only_on_save(tmp_path):
    output_dir = tmp_path / "nested" / "reports"
    run = _run(dataset_name="...", dataset_version="///")

    path = build_evaluation_report_path(run, output_dir=output_dir)

    assert path.name.startswith("evaluation-evaluation-")
    assert not output_dir.exists()
    assert save_evaluation_report_to_directory(run, output_dir=output_dir) == path
    assert path.is_file()


def test_existing_report_is_unchanged_by_default_and_replaced_with_overwrite(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("original", encoding="utf-8")

    with pytest.raises(EvaluationReportExistsError, match="already exists"):
        save_evaluation_report(_run(), path)
    assert path.read_text(encoding="utf-8") == "original"

    save_evaluation_report(_run(status=EvaluationRunStatus.FAILED), path, overwrite=True)
    assert load_evaluation_report(path).status is EvaluationRunStatus.FAILED
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_commit_failure_leaves_no_destination_or_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "report.json"

    def fail_commit(_source, _destination):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(reporting.os, "link", fail_commit)

    with pytest.raises(EvaluationReportWriteError, match="simulated filesystem failure"):
        save_evaluation_report(_run(), path)

    assert not path.exists()
    assert list(tmp_path.iterdir()) == []


def test_serialization_failure_occurs_before_parent_directory_creation(tmp_path):
    path = tmp_path / "not-created" / "report.json"
    invalid_run = _run().model_copy(update={"metadata": {"invalid": object()}})

    with pytest.raises(EvaluationReportValidationError, match="serialized"):
        save_evaluation_report(invalid_run, path)

    assert not path.parent.exists()


def test_directory_target_and_parent_file_conflict_are_rejected(tmp_path):
    with pytest.raises(EvaluationReportPathError, match="directory"):
        save_evaluation_report(_run(), tmp_path)

    parent = tmp_path / "parent"
    parent.write_text("not a directory", encoding="utf-8")
    with pytest.raises(EvaluationReportPathError, match="parent"):
        save_evaluation_report(_run(), parent / "report.json")


@pytest.mark.parametrize(
    ("content", "error_type", "message"),
    [
        ("", EvaluationReportJsonError, "line 1, column 1"),
        ("[]", EvaluationReportJsonError, "root must be an object"),
        ('{"id": "run"}', EvaluationReportValidationError, "schema_version"),
        (
            '{"schema_version":"2.0"}',
            UnsupportedEvaluationReportSchemaError,
            "supported versions: 1.0",
        ),
        (
            '{"schema_version":"1.0","id":"run"}',
            EvaluationReportValidationError,
            "dataset_name",
        ),
    ],
)
def test_loader_rejects_invalid_report_contract(tmp_path, content, error_type, message):
    path = tmp_path / "report.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(error_type, match=message):
        load_evaluation_report(path)


def test_loader_retains_structured_validation_paths(tmp_path):
    path = tmp_path / "report.json"
    payload = _run().model_dump(mode="json")
    del payload["results"][0]["case_id"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationReportValidationError) as raised:
        load_evaluation_report(path)

    assert raised.value.errors[0]["loc"] == ("results", 0, "case_id")


def test_loader_rejects_missing_directory_and_invalid_utf8(tmp_path):
    with pytest.raises(EvaluationReportReadError, match="not found"):
        load_evaluation_report(tmp_path / "missing.json")
    with pytest.raises(EvaluationReportReadError, match="regular file"):
        load_evaluation_report(tmp_path)

    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"\xff")
    with pytest.raises(EvaluationReportReadError, match="UTF-8"):
        load_evaluation_report(invalid)


def test_repeated_serialization_is_identical_and_preserves_order(tmp_path):
    run = _run()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    save_evaluation_report(run, first)
    save_evaluation_report(run, second)

    assert first.read_bytes() == second.read_bytes()
    restored = load_evaluation_report(first)
    assert restored.results[0].retrieval is not None
    assert restored.results[0].retrieval.failure_reasons == [
        "first-diagnostic",
        "second-diagnostic",
    ]
