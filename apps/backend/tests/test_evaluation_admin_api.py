import asyncio
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from admin_auth.dependencies import require_administrator_role, require_trusted_admin_origin
from assistant.api.dependencies import get_evaluation_administration_service
from assistant.api.evaluation_admin import router
from assistant.api.routes import router as assistant_router
from assistant.application.evaluation_admin import EvaluationAdministrationService
from assistant.evaluation import (
    AnswerEvaluationOptions,
    AnswerEvaluationResult,
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationReportWriteError,
    EvaluationRun,
    EvaluationRunOptions,
    EvaluationRunStatus,
    EvaluationSummary,
    RetrievalEvaluationResult,
    RetrievedItem,
    save_evaluation_report_to_directory,
)
from assistant.infrastructure.evaluation_files import FileSystemEvaluationResources
from core.exceptions import register_exception_handlers
from infrastructure.ai.exceptions import AIConfigurationError

NOW = datetime(2026, 8, 12, 9, 30, tzinfo=timezone.utc)


def _dataset_payload(
    *,
    name: str = "Admin regression",
    version: str = "2026.08",
    schema_version: str = "1.0",
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "name": name,
        "version": version,
        "description": "Administrator evaluation suite",
        "cases": [
            {
                "id": "case-1",
                "question": "What is the approved process?",
                "expected_source_ids": ["policy-1"],
                "expected_answer_contains": ["approved"],
                "expected_answer_excludes": ["secret"],
                "metadata": {"internal_note": "must-not-be-exposed"},
            }
        ],
        "metadata": {"filesystem_hint": "/private/dataset.json"},
    }


def _write_dataset(directory: Path, identifier: str, **overrides: Any) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{identifier}.json"
    path.write_text(json.dumps(_dataset_payload(**overrides)), encoding="utf-8")
    return path


def _run(
    run_id: str,
    *,
    completed_at: datetime = NOW,
    status: EvaluationRunStatus = EvaluationRunStatus.COMPLETED,
) -> EvaluationRun:
    return EvaluationRun(
        id=run_id,
        dataset_name="Admin regression",
        dataset_version="2026.08",
        status=status,
        started_at=completed_at - timedelta(seconds=1),
        completed_at=completed_at,
        configuration={
            "retrieval_k": None,
            "continue_on_error": True,
            "include_retrieved_content": False,
            "require_all_expected_sources": True,
            "answer_evaluation": {
                "case_sensitive": False,
                "normalise_whitespace": True,
                "require_all_expected_fragments": True,
                "require_citations_when_sources_expected": True,
                "validate_citations_against_retrieval": True,
            },
        },
        results=[
            EvaluationCaseResult(
                case_id="case-1",
                question="What is the approved process?",
                status=EvaluationCaseStatus.PASSED,
                started_at=completed_at - timedelta(seconds=1),
                completed_at=completed_at,
                duration_ms=1000,
                retrieval=RetrievalEvaluationResult(
                    retrieved_items=[
                        RetrievedItem(
                            id="chunk-1",
                            document_id="policy-1",
                            chunk_id="chunk-1",
                            rank=1,
                            content="sensitive retrieved production content",
                            score=0.9,
                            metadata={"private": "value"},
                        )
                    ],
                    precision_at_k=1.0,
                    recall_at_k=1.0,
                    reciprocal_rank=1.0,
                    hit=True,
                    expected_source_ids=["policy-1"],
                    matched_source_ids=["policy-1"],
                ),
                answer=AnswerEvaluationResult(
                    answer="The generated approved answer is sensitive.",
                    passed=True,
                    matched_expected_fragments=["approved"],
                    citation_count=1,
                    citations_valid=True,
                    hallucination_detected=False,
                    cited_source_ids=["policy-1"],
                    valid_citation_source_ids=["policy-1"],
                ),
            )
        ],
        summary=EvaluationSummary(
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            error_cases=0,
            skipped_cases=0,
            retrieval_precision_at_k=1.0,
            retrieval_recall_at_k=1.0,
            retrieval_hit_rate=1.0,
            mean_reciprocal_rank=1.0,
            answer_pass_rate=1.0,
            average_duration_ms=1000,
        ),
        metadata={"provider_payload": "must-not-be-exposed"},
    )


class RecordingRunner:
    def __init__(self, run_id: str = "11111111-1111-4111-8111-111111111111") -> None:
        self.run_id = run_id
        self.options: list[EvaluationRunOptions] = []

    def run_dataset(self, dataset, *, options=None):
        self.options.append(options or EvaluationRunOptions())
        return _run(self.run_id)


class FixedRunRunner(RecordingRunner):
    def __init__(self, run: EvaluationRun) -> None:
        super().__init__(run.id)
        self.run = run

    def run_dataset(self, dataset, *, options=None):
        self.options.append(options or EvaluationRunOptions())
        return self.run


def _client(
    dataset_dir: Path,
    report_dir: Path,
    *,
    authenticated: bool = True,
    trusted: bool = True,
    runner_factory=None,
) -> tuple[TestClient, RecordingRunner | None]:
    resources = FileSystemEvaluationResources(
        dataset_directory=dataset_dir,
        report_directory=report_dir,
    )
    recording_runner = None
    if runner_factory is None:
        recording_runner = RecordingRunner()

        def runner_factory():
            return recording_runner

    service = EvaluationAdministrationService(resources, runner_factory=runner_factory)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_evaluation_administration_service] = lambda: service
    if authenticated:
        app.dependency_overrides[require_administrator_role] = lambda: object()
    if trusted:
        app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    return TestClient(app), recording_runner


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/admin/evaluation/datasets", None),
        ("get", "/admin/evaluation/datasets/suite", None),
        ("post", "/admin/evaluation/runs", {"dataset_id": "suite"}),
        ("get", "/admin/evaluation/runs", None),
        ("get", "/admin/evaluation/runs/run-1", None),
        (
            "post",
            "/admin/evaluation/comparisons",
            {"candidate_run_id": "run-1", "baseline_run_id": "run-2"},
        ),
    ],
)
def test_every_evaluation_route_requires_an_administrator(
    tmp_path: Path, method: str, path: str, payload: object
) -> None:
    client, _runner = _client(tmp_path / "datasets", tmp_path / "reports", authenticated=False)

    response = client.request(method, path, json=payload)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_execution_requires_trusted_origin_without_side_effects(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    report_dir = tmp_path / "reports"
    _write_dataset(dataset_dir, "suite")
    client, runner = _client(dataset_dir, report_dir, trusted=False)

    response = client.post(
        "/admin/evaluation/runs",
        json={"dataset_id": "suite", "persist_report": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"
    assert runner is not None and runner.options == []
    assert not report_dir.exists()


def test_non_administrator_access_is_forbidden(tmp_path: Path) -> None:
    client, _runner = _client(tmp_path / "datasets", tmp_path / "reports")
    app = cast(FastAPI, client.app)
    app.dependency_overrides[require_administrator_role] = lambda: (_ for _ in ()).throw(
        HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Not permitted."},
        )
    )

    response = client.get("/admin/evaluation/datasets")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden"


def test_dataset_listing_and_detail_are_deterministic_and_safe(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    _write_dataset(dataset_dir, "zeta", name="Zeta")
    _write_dataset(dataset_dir, "alpha", name="Alpha")
    client, _runner = _client(dataset_dir, tmp_path / "reports")

    listing = client.get("/admin/evaluation/datasets")
    detail = client.get("/admin/evaluation/datasets/alpha")

    assert listing.status_code == 200
    assert listing.json() == {
        "items": [
            {
                "id": "alpha",
                "name": "Alpha",
                "version": "2026.08",
                "schema_version": "1.0",
                "case_count": 1,
            },
            {
                "id": "zeta",
                "name": "Zeta",
                "version": "2026.08",
                "schema_version": "1.0",
                "case_count": 1,
            },
        ],
        "total": 2,
    }
    assert detail.status_code == 200
    assert detail.json()["cases"] == [
        {
            "id": "case-1",
            "question": "What is the approved process?",
            "expected_source_ids": ["policy-1"],
            "expected_answer_contains": ["approved"],
            "expected_answer_excludes": ["secret"],
        }
    ]
    serialized = json.dumps({"listing": listing.json(), "detail": detail.json()})
    assert str(dataset_dir) not in serialized
    assert "filesystem_hint" not in serialized
    assert "internal_note" not in serialized


def test_empty_unknown_and_unsafe_dataset_selection(tmp_path: Path) -> None:
    client, _runner = _client(tmp_path / "datasets", tmp_path / "reports")

    assert client.get("/admin/evaluation/datasets").json() == {"items": [], "total": 0}
    missing = client.get("/admin/evaluation/datasets/missing")
    traversal = client.get("/admin/evaluation/datasets/..%2Fsecret")

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "evaluation_dataset_not_found"
    assert traversal.status_code == 422
    assert traversal.json()["detail"]["code"] == "invalid_evaluation_identifier"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("{not-json", "malformed_evaluation_dataset"),
        (json.dumps(_dataset_payload(schema_version="99")), "unsupported_dataset_schema"),
    ],
)
def test_malformed_and_unsupported_datasets_have_safe_errors(
    tmp_path: Path, content: str, code: str
) -> None:
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    (dataset_dir / "broken.json").write_text(content, encoding="utf-8")
    client, _runner = _client(dataset_dir, tmp_path / "reports")

    response = client.get("/admin/evaluation/datasets")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code
    assert str(dataset_dir) not in response.text
    assert "not-json" not in response.text


def test_execution_uses_runner_defaults_and_filters_sensitive_result_content(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "datasets"
    _write_dataset(dataset_dir, "suite")
    client, runner = _client(dataset_dir, tmp_path / "reports")

    response = client.post("/admin/evaluation/runs", json={"dataset_id": "suite"})

    assert response.status_code == 200
    assert runner is not None and runner.options == [EvaluationRunOptions()]
    assert response.json()["report_persisted"] is False
    assert response.json()["run"]["status"] == "completed"
    serialized = response.text
    assert "sensitive retrieved production content" not in serialized
    assert "generated approved answer" not in serialized
    assert "provider_payload" not in serialized
    assert "private" not in serialized


def test_execution_preserves_failed_error_and_skipped_statuses_with_safe_diagnostics(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "datasets"
    _write_dataset(dataset_dir, "suite")
    results = [
        EvaluationCaseResult(
            case_id="failed",
            question="Failed question?",
            status=EvaluationCaseStatus.FAILED,
            answer=AnswerEvaluationResult(
                answer="sensitive failed answer",
                passed=False,
                missing_expected_fragments=["required"],
                failure_reasons=["missing_expected_fragments"],
            ),
        ),
        EvaluationCaseResult(
            case_id="error",
            question="Errored question?",
            status=EvaluationCaseStatus.ERROR,
            error="evaluation case failed (RuntimeError)",
        ),
        EvaluationCaseResult(
            case_id="skipped",
            question="Skipped question?",
            status=EvaluationCaseStatus.SKIPPED,
            metadata={"diagnostic_reasons": ["no_evaluable_expectations"]},
        ),
    ]
    run = _run("terminal-mix").model_copy(
        update={
            "results": results,
            "summary": EvaluationSummary(
                total_cases=3,
                passed_cases=0,
                failed_cases=1,
                error_cases=1,
                skipped_cases=1,
                average_duration_ms=None,
            ),
        }
    )
    client, _runner = _client(
        dataset_dir,
        tmp_path / "reports",
        runner_factory=lambda: FixedRunRunner(run),
    )

    response = client.post("/admin/evaluation/runs", json={"dataset_id": "suite"})

    assert response.status_code == 200
    payload = response.json()["run"]
    assert payload["status"] == "completed"
    assert payload["summary"] == {
        "total_cases": 3,
        "passed_cases": 0,
        "failed_cases": 1,
        "error_cases": 1,
        "skipped_cases": 1,
        "retrieval_precision_at_k": None,
        "retrieval_recall_at_k": None,
        "retrieval_hit_rate": None,
        "mean_reciprocal_rank": None,
        "answer_pass_rate": None,
        "average_duration_ms": None,
    }
    assert [item["status"] for item in payload["results"]] == ["failed", "error", "skipped"]
    assert payload["results"][1]["error"] == "evaluation case failed (RuntimeError)"
    assert payload["results"][2]["diagnostics"] == ["no_evaluable_expectations"]
    assert "sensitive failed answer" not in response.text


def test_evaluation_bootstrap_failure_is_safe_and_does_not_persist(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    report_dir = tmp_path / "reports"
    _write_dataset(dataset_dir, "suite")

    def fail_bootstrap():
        raise AIConfigurationError("OPENAI_API_KEY=secret-value")

    client, _runner = _client(dataset_dir, report_dir, runner_factory=fail_bootstrap)

    response = client.post(
        "/admin/evaluation/runs",
        json={"dataset_id": "suite", "persist_report": True},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "evaluation_bootstrap_failed",
        "message": "Evaluation services could not be configured.",
    }
    assert "secret-value" not in response.text
    assert not report_dir.exists()


def test_evaluation_run_failure_is_safe_and_does_not_persist(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    dataset_dir = tmp_path / "datasets"
    report_dir = tmp_path / "reports"
    _write_dataset(dataset_dir, "suite")

    class FailingRunner(RecordingRunner):
        def run_dataset(self, dataset, *, options=None):
            raise RuntimeError("provider response contained secret-value")

    client, _runner = _client(
        dataset_dir,
        report_dir,
        runner_factory=lambda: FailingRunner(),
    )

    response = client.post(
        "/admin/evaluation/runs",
        json={"dataset_id": "suite", "persist_report": True},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "evaluation_run_failed",
        "message": "The evaluation run failed.",
    }
    assert "secret-value" not in response.text
    assert not report_dir.exists()
    record = next(
        record
        for record in caplog.records
        if record.message == "administrator_evaluation_run_failed"
    )
    assert record.__dict__["dataset_id"] == "suite"
    assert record.__dict__["error_type"] == "RuntimeError"
    assert "secret-value" not in caplog.text


def test_execution_maps_supported_options_and_persists_once_server_side(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    report_dir = tmp_path / "reports"
    _write_dataset(dataset_dir, "suite")
    client, runner = _client(dataset_dir, report_dir)

    response = client.post(
        "/admin/evaluation/runs",
        json={
            "dataset_id": "suite",
            "persist_report": True,
            "options": {
                "retrieval_k": 4,
                "continue_on_error": False,
                "require_all_expected_sources": False,
                "answer_options": {
                    "case_sensitive": True,
                    "normalise_whitespace": False,
                    "require_all_expected_fragments": False,
                    "require_citations_when_sources_expected": False,
                    "validate_citations_against_retrieval": False,
                },
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["report_persisted"] is True
    assert runner is not None
    assert runner.options == [
        EvaluationRunOptions(
            retrieval_k=4,
            continue_on_error=False,
            require_all_expected_sources=False,
            answer_options=AnswerEvaluationOptions(
                case_sensitive=True,
                normalise_whitespace=False,
                require_all_expected_fragments=False,
                require_citations_when_sources_expected=False,
                validate_citations_against_retrieval=False,
            ),
        )
    ]
    assert len(list(report_dir.glob("*.json"))) == 1


def test_repeated_persistence_never_overwrites_or_duplicates_a_run_report(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    report_dir = tmp_path / "reports"
    _write_dataset(dataset_dir, "suite")
    client, _runner = _client(dataset_dir, report_dir)
    request = {"dataset_id": "suite", "persist_report": True}

    first = client.post("/admin/evaluation/runs", json=request)
    original = next(report_dir.glob("*.json")).read_bytes()
    second = client.post("/admin/evaluation/runs", json=request)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "evaluation_report_exists"
    reports = list(report_dir.glob("*.json"))
    assert len(reports) == 1
    assert reports[0].read_bytes() == original


def test_report_persistence_failure_is_safe_and_never_reports_success(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    report_dir = tmp_path / "reports"
    _write_dataset(dataset_dir, "suite")

    class FailingResources(FileSystemEvaluationResources):
        def save_report(self, run: EvaluationRun) -> None:
            raise EvaluationReportWriteError("failed path contains /private/secret")

    service = EvaluationAdministrationService(
        FailingResources(dataset_directory=dataset_dir, report_directory=report_dir),
        runner_factory=lambda: cast(Any, RecordingRunner()),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_evaluation_administration_service] = lambda: service
    app.dependency_overrides[require_administrator_role] = lambda: object()
    app.dependency_overrides[require_trusted_admin_origin] = lambda: None

    response = TestClient(app).post(
        "/admin/evaluation/runs",
        json={"dataset_id": "suite", "persist_report": True},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "evaluation_report_persistence_failed",
        "message": "The evaluation report could not be persisted.",
    }
    assert "private" not in response.text
    assert not report_dir.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"dataset_id": "suite", "options": {"retrieval_k": 0}},
        {"dataset_id": "suite", "options": {"include_retrieved_content": True}},
        {"dataset_id": "suite", "report_path": "../../secret.json"},
    ],
)
def test_invalid_or_unsafe_execution_options_are_rejected_before_running(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    dataset_dir = tmp_path / "datasets"
    _write_dataset(dataset_dir, "suite")
    client, runner = _client(dataset_dir, tmp_path / "reports")

    response = client.post("/admin/evaluation/runs", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_evaluation_options"
    assert runner is not None and runner.options == []


def test_report_listing_detail_and_pagination_are_newest_first_and_safe(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    save_evaluation_report_to_directory(_run("run-old", completed_at=NOW), output_dir=report_dir)
    save_evaluation_report_to_directory(
        _run("run-new", completed_at=NOW + timedelta(hours=1)), output_dir=report_dir
    )
    client, _runner = _client(tmp_path / "datasets", report_dir)

    listing = client.get("/admin/evaluation/runs?limit=1&offset=0")
    detail = client.get("/admin/evaluation/runs/run-new")

    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert listing.json()["limit"] == 1
    assert listing.json()["offset"] == 0
    assert [item["id"] for item in listing.json()["items"]] == ["run-new"]
    assert listing.json()["items"][0]["report_schema_version"] == "1.0"
    assert detail.status_code == 200
    assert detail.json()["id"] == "run-new"
    serialized = json.dumps({"listing": listing.json(), "detail": detail.json()})
    assert str(report_dir) not in serialized
    assert "sensitive retrieved production content" not in serialized
    assert "generated approved answer" not in serialized


def test_report_listing_uses_metadata_discovery_without_loading_complete_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import assistant.infrastructure.evaluation_files as evaluation_files

    report_dir = tmp_path / "reports"
    save_evaluation_report_to_directory(_run("run-1"), output_dir=report_dir)
    monkeypatch.setattr(
        evaluation_files,
        "load_evaluation_report",
        lambda _path: pytest.fail("listing must not load complete evaluation runs"),
    )
    client, _runner = _client(tmp_path / "datasets", report_dir)

    response = client.get("/admin/evaluation/runs")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["run-1"]


def test_report_selection_rejects_missing_traversal_and_malformed_reports(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    client, _runner = _client(tmp_path / "datasets", report_dir)

    missing = client.get("/admin/evaluation/runs/missing")
    traversal = client.get("/admin/evaluation/runs/..%2Fsecret")
    (report_dir / "broken.json").write_text("{bad", encoding="utf-8")
    malformed = client.get("/admin/evaluation/runs")

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "evaluation_report_not_found"
    assert traversal.status_code == 422
    assert traversal.json()["detail"]["code"] == "invalid_evaluation_identifier"
    assert malformed.status_code == 422
    assert malformed.json()["detail"]["code"] == "malformed_evaluation_report"
    assert str(report_dir) not in malformed.text


def test_unsupported_report_schema_is_safe_for_detail_and_comparison(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    payload = _run("unsupported").model_dump(mode="json")
    payload["schema_version"] = "99"
    (report_dir / "unsupported.json").write_text(json.dumps(payload), encoding="utf-8")
    client, _runner = _client(tmp_path / "datasets", report_dir)

    detail = client.get("/admin/evaluation/runs/unsupported")
    comparison = client.post(
        "/admin/evaluation/comparisons",
        json={"candidate_run_id": "unsupported", "baseline_run_id": "unsupported"},
    )

    for response in (detail, comparison):
        assert response.status_code == 422
        assert response.json()["detail"] == {
            "code": "unsupported_report_schema",
            "message": "The evaluation report schema is not supported.",
        }
        assert "99" not in response.text


def test_comparison_uses_persisted_reports_without_mutation(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    baseline = _run("baseline")
    candidate = _run("candidate")
    save_evaluation_report_to_directory(baseline, output_dir=report_dir)
    save_evaluation_report_to_directory(candidate, output_dir=report_dir)
    before = {path.name: path.read_bytes() for path in report_dir.iterdir()}
    client, _runner = _client(tmp_path / "datasets", report_dir)

    response = client.post(
        "/admin/evaluation/comparisons",
        json={"candidate_run_id": "candidate", "baseline_run_id": "baseline"},
    )

    assert response.status_code == 200
    assert response.json()["compatible"] is True
    assert response.json()["baseline_run_id"] == "baseline"
    assert response.json()["current_run_id"] == "candidate"
    assert response.json()["regressed"] is False
    assert {path.name: path.read_bytes() for path in report_dir.iterdir()} == before


def test_comparison_exposes_existing_regression_result_without_mutating_reports(
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    baseline = _run("baseline")
    failed_result = baseline.results[0].model_copy(update={"status": EvaluationCaseStatus.FAILED})
    candidate = _run("candidate").model_copy(
        update={
            "results": [failed_result],
            "summary": baseline.summary.model_copy(
                update={
                    "passed_cases": 0,
                    "failed_cases": 1,
                    "answer_pass_rate": 0.0,
                }
            )
            if baseline.summary is not None
            else None,
        }
    )
    save_evaluation_report_to_directory(baseline, output_dir=report_dir)
    save_evaluation_report_to_directory(candidate, output_dir=report_dir)
    before = {path.name: path.read_bytes() for path in report_dir.iterdir()}
    client, _runner = _client(tmp_path / "datasets", report_dir)

    response = client.post(
        "/admin/evaluation/comparisons",
        json={"candidate_run_id": "candidate", "baseline_run_id": "baseline"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["compatible"] is True
    assert payload["regressed"] is True
    assert payload["newly_failed_case_ids"] == ["case-1"]
    assert payload["regression_reasons"] == ["new_failed_case"]
    answer_metric = next(
        item for item in payload["metric_results"] if item["metric"] == "answer_pass_rate"
    )
    assert answer_metric["baseline_value"] == 1.0
    assert answer_metric["current_value"] == 0.0
    assert answer_metric["status"] == "regressed"
    assert {path.name: path.read_bytes() for path in report_dir.iterdir()} == before


def test_incompatible_comparison_and_missing_runs_have_stable_errors(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    save_evaluation_report_to_directory(_run("baseline"), output_dir=report_dir)
    incompatible = _run("candidate").model_copy(update={"dataset_name": "Different"})
    save_evaluation_report_to_directory(incompatible, output_dir=report_dir)
    client, _runner = _client(tmp_path / "datasets", report_dir)

    conflict = client.post(
        "/admin/evaluation/comparisons",
        json={"candidate_run_id": "candidate", "baseline_run_id": "baseline"},
    )
    missing = client.post(
        "/admin/evaluation/comparisons",
        json={"candidate_run_id": "missing", "baseline_run_id": "baseline"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "incompatible_evaluation_comparison"
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "evaluation_report_not_found"


def test_separate_requests_create_separate_runner_state(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    _write_dataset(dataset_dir, "suite")
    created: list[RecordingRunner] = []

    def factory() -> RecordingRunner:
        runner = RecordingRunner(f"run-{len(created) + 1}")
        created.append(runner)
        return runner

    client, _runner = _client(dataset_dir, tmp_path / "reports", runner_factory=factory)

    first = client.post("/admin/evaluation/runs", json={"dataset_id": "suite"})
    second = client.post("/admin/evaluation/runs", json={"dataset_id": "suite"})

    assert first.json()["run"]["id"] == "run-1"
    assert second.json()["run"]["id"] == "run-2"
    assert len(created) == 2
    assert all(len(runner.options) == 1 for runner in created)


@pytest.mark.parametrize("provider_fails", [False, True])
def test_production_composition_reuses_and_closes_managed_provider_after_evaluation_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_fails: bool,
) -> None:
    import main
    from assistant.api import dependencies
    from core.config import EvaluationAdminSettings

    dataset_dir = tmp_path / "datasets"
    _write_dataset(dataset_dir, "suite")
    created: list[object] = []

    class Provider:
        name = "fake"
        model = "fake-model"

        def __init__(self) -> None:
            self.closed = False
            self.embedding_calls = 0
            self.answer_calls = 0

        def generate_embedding(self, *, text: str) -> list[float]:
            self.embedding_calls += 1
            if provider_fails:
                raise RuntimeError("provider token=must-not-escape")
            return []

        def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
            self.answer_calls += 1
            return "approved"

        def close(self) -> None:
            self.closed = True

    @lru_cache
    def provider_factory():
        provider = Provider()
        created.append(provider)
        return provider

    monkeypatch.setattr(dependencies, "get_ai_provider", provider_factory)
    monkeypatch.setattr(main, "get_ai_provider", provider_factory)
    monkeypatch.setattr(dependencies, "get_vector_store", lambda: object())
    monkeypatch.setattr(dependencies, "get_knowledge_repository", lambda _store: SimpleNamespace())
    monkeypatch.setattr(
        dependencies,
        "get_evaluation_admin_settings",
        lambda: EvaluationAdminSettings(
            dataset_directory=dataset_dir,
            report_directory=tmp_path / "reports",
        ),
    )
    monkeypatch.setattr(main, "validate_startup_configuration", lambda: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    service = dependencies.get_evaluation_administration_service()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_evaluation_administration_service] = lambda: service
    app.dependency_overrides[require_administrator_role] = lambda: object()
    app.dependency_overrides[require_trusted_admin_origin] = lambda: None
    client = TestClient(app)

    async def execute_requests() -> tuple[dict[str, Any], dict[str, Any]]:
        async with main.lifespan(main.app):
            first = client.post("/admin/evaluation/runs", json={"dataset_id": "suite"})
            second = client.post("/admin/evaluation/runs", json={"dataset_id": "suite"})
            assert first.status_code == 200
            assert second.status_code == 200
            return first.json(), second.json()

    first, second = asyncio.run(execute_requests())

    assert first["run"]["id"] != second["run"]["id"]
    assert len(created) == 1
    provider = cast(Provider, created[0])
    assert provider.embedding_calls == 2
    assert provider.answer_calls == (0 if provider_fails else 2)
    assert provider.closed is True
    if provider_fails:
        assert first["run"]["results"][0]["status"] == "error"
        assert "must-not-escape" not in json.dumps(first)


def test_registered_openapi_exposes_only_the_authenticated_admin_namespace() -> None:
    app = FastAPI()
    app.include_router(assistant_router)

    schema = app.openapi()
    paths = schema["paths"]

    assert set(paths["/admin/evaluation/datasets"]) == {"get"}
    assert set(paths["/admin/evaluation/datasets/{dataset_id}"]) == {"get"}
    assert set(paths["/admin/evaluation/runs"]) == {"get", "post"}
    assert set(paths["/admin/evaluation/runs/{run_id}"]) == {"get"}
    assert set(paths["/admin/evaluation/comparisons"]) == {"post"}
    for path in (
        "/admin/evaluation/datasets",
        "/admin/evaluation/datasets/{dataset_id}",
        "/admin/evaluation/runs",
        "/admin/evaluation/runs/{run_id}",
        "/admin/evaluation/comparisons",
    ):
        assert all(operation["security"] for operation in paths[path].values())
    assert not any(path.startswith("/evaluation") for path in paths)
    execute_schema = schema["components"]["schemas"]["ExecuteEvaluationRequest"]
    assert set(execute_schema["properties"]) == {"dataset_id", "persist_report", "options"}
