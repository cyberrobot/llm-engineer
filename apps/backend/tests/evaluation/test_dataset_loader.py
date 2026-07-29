import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from assistant.evaluation import (
    EvaluationDataset,
    EvaluationDatasetFileNotFoundError,
    EvaluationDatasetJsonError,
    EvaluationDatasetReadError,
    EvaluationDatasetValidationError,
    UnsupportedEvaluationDatasetSchemaError,
    load_evaluation_dataset,
    parse_evaluation_dataset_json,
)

EXAMPLE_DATASET_PATH = (
    Path(__file__).parents[2] / "examples" / "evaluation" / "example-dataset.json"
)


def dataset_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "name": "support-knowledge-baseline",
        "version": "2026.07",
        "cases": [{"id": "password-reset", "question": "How do I reset my password?"}],
    }
    payload.update(overrides)
    return payload


def write_dataset(path: Path, payload: object) -> str:
    content = json.dumps(payload, ensure_ascii=False)
    path.write_text(content, encoding="utf-8")
    return content


def error_locations(exc: EvaluationDatasetValidationError) -> set[tuple[object, ...]]:
    locations: set[tuple[object, ...]] = set()
    for error in exc.errors:
        location = error["loc"]
        assert isinstance(location, (tuple, list))
        locations.add(tuple(location))
    return locations


def test_parse_evaluation_dataset_json_returns_validated_dataset():
    dataset = parse_evaluation_dataset_json(json.dumps(dataset_payload()))

    assert isinstance(dataset, EvaluationDataset)
    assert dataset.name == "support-knowledge-baseline"
    assert dataset.schema_version == "1.0"
    assert dataset.version == "2026.07"
    assert dataset.cases[0].id == "password-reset"


def test_load_evaluation_dataset_accepts_path_and_string_inputs(tmp_path: Path):
    dataset_path = tmp_path / "dataset.data"
    write_dataset(dataset_path, dataset_payload())

    from_path = load_evaluation_dataset(dataset_path)
    from_string = load_evaluation_dataset(str(dataset_path))

    assert from_path == from_string
    assert from_path.name == "support-knowledge-baseline"


def test_load_evaluation_dataset_accepts_minimal_valid_dataset(tmp_path: Path):
    dataset_path = tmp_path / "minimal.json"
    write_dataset(dataset_path, dataset_payload())

    dataset = load_evaluation_dataset(dataset_path)

    assert dataset.description is None
    assert dataset.tags == []
    assert dataset.metadata == {}
    assert dataset.cases[0].expected_source_ids == []


def test_load_evaluation_dataset_accepts_fully_populated_unicode_and_metadata(tmp_path: Path):
    dataset_path = tmp_path / "unicode.json"
    write_dataset(
        dataset_path,
        dataset_payload(
            description="Régression de recherche",
            created_at="2026-07-29T09:00:00+00:00",
            tags=["baseline", "international"],
            metadata={"release": {"regions": ["München", "東京"], "enabled": True}},
            cases=[
                {
                    "id": "unicode-case",
                    "question": "Où trouver le guide de sécurité ?",
                    "description": "Vérifie la récupération multilingue",
                    "expected_source_ids": ["security-guide"],
                    "expected_answer_contains": ["sécurité"],
                    "expected_answer_excludes": ["mot de passe partagé"],
                    "tags": ["sécurité"],
                    "metadata": {"priority": 1, "nested": [None, False, {"locale": "fr-FR"}]},
                }
            ],
        ),
    )

    dataset = load_evaluation_dataset(dataset_path)

    assert dataset.description == "Régression de recherche"
    assert dataset.metadata["release"] == {
        "regions": ["München", "東京"],
        "enabled": True,
    }
    assert dataset.cases[0].question == "Où trouver le guide de sécurité ?"


def test_load_evaluation_dataset_supports_relative_paths_without_changing_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dataset_path = tmp_path / "relative.json"
    write_dataset(dataset_path, dataset_payload())
    monkeypatch.chdir(tmp_path)
    cwd_before = Path.cwd()

    dataset = load_evaluation_dataset(Path("relative.json"))

    assert dataset.name == "support-knowledge-baseline"
    assert Path.cwd() == cwd_before


def test_committed_example_dataset_loads_with_representative_expectations():
    dataset = load_evaluation_dataset(EXAMPLE_DATASET_PATH)

    assert dataset.schema_version == "1.0"
    assert len(dataset.cases) == 3
    assert any(case.expected_source_ids for case in dataset.cases)
    assert any(case.expected_answer_contains for case in dataset.cases)
    assert any(
        case.expected_answer_contains and case.expected_answer_excludes for case in dataset.cases
    )


def test_repeated_loads_are_equivalent_and_do_not_modify_file_or_models(tmp_path: Path):
    dataset_path = tmp_path / "stable.json"
    original_content = write_dataset(dataset_path, dataset_payload())

    first = load_evaluation_dataset(dataset_path)
    second = load_evaluation_dataset(dataset_path)
    first.tags.append("local-change")

    assert second.tags == []
    assert dataset_path.read_text(encoding="utf-8") == original_content
    assert load_evaluation_dataset(dataset_path) == second


def test_missing_file_raises_path_aware_error_and_preserves_cause(tmp_path: Path):
    dataset_path = tmp_path / "missing.json"

    with pytest.raises(EvaluationDatasetFileNotFoundError) as captured:
        load_evaluation_dataset(dataset_path)

    assert str(dataset_path) in str(captured.value)
    assert isinstance(captured.value.__cause__, FileNotFoundError)


def test_directory_path_raises_read_error(tmp_path: Path):
    with pytest.raises(EvaluationDatasetReadError) as captured:
        load_evaluation_dataset(tmp_path)

    assert str(tmp_path) in str(captured.value)
    assert "regular file" in str(captured.value)


def test_unreadable_file_raises_read_error_and_preserves_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dataset_path = tmp_path / "unreadable.json"
    write_dataset(dataset_path, dataset_payload())
    original_read_text = Path.read_text

    def deny_read(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
        if path == dataset_path:
            raise PermissionError("permission denied")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", deny_read)

    with pytest.raises(EvaluationDatasetReadError) as captured:
        load_evaluation_dataset(dataset_path)

    assert str(dataset_path) in str(captured.value)
    assert isinstance(captured.value.__cause__, PermissionError)


def test_invalid_utf8_raises_read_error_and_preserves_decode_cause(tmp_path: Path):
    dataset_path = tmp_path / "invalid-encoding.json"
    dataset_path.write_bytes(b'\xff{"schema_version": "1.0"}')

    with pytest.raises(EvaluationDatasetReadError) as captured:
        load_evaluation_dataset(dataset_path)

    assert str(dataset_path) in str(captured.value)
    assert "UTF-8" in str(captured.value)
    assert isinstance(captured.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize("content", ["", "  \n\t"])
def test_empty_or_whitespace_content_raises_json_error(content: str):
    with pytest.raises(EvaluationDatasetJsonError) as captured:
        parse_evaluation_dataset_json(content)

    assert isinstance(captured.value.__cause__, json.JSONDecodeError)


@pytest.mark.parametrize(
    "content",
    [
        '{"schema_version": "1.0",',
        '{"schema_version": "1.0",}',
        '{"schema_version": "1.0"} {"schema_version": "1.0"}',
    ],
)
def test_malformed_json_reports_line_and_column_and_preserves_cause(content: str):
    with pytest.raises(EvaluationDatasetJsonError) as captured:
        parse_evaluation_dataset_json(content)

    error = captured.value
    assert "line" in str(error)
    assert "column" in str(error)
    assert isinstance(error.__cause__, json.JSONDecodeError)


def test_file_json_error_includes_source_path(tmp_path: Path):
    dataset_path = tmp_path / "malformed.json"
    dataset_path.write_text("{", encoding="utf-8")

    with pytest.raises(EvaluationDatasetJsonError) as captured:
        load_evaluation_dataset(dataset_path)

    assert str(dataset_path) in str(captured.value)


@pytest.mark.parametrize("root", [[], "dataset", 7, None])
def test_non_object_json_roots_are_rejected(root: object):
    with pytest.raises(EvaluationDatasetJsonError) as captured:
        parse_evaluation_dataset_json(json.dumps(root))

    assert "root must be an object" in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize("schema_version", ["0.9", "2.0"])
def test_unsupported_schema_versions_are_rejected(schema_version: str):
    content = json.dumps(dataset_payload(schema_version=schema_version))

    with pytest.raises(UnsupportedEvaluationDatasetSchemaError) as captured:
        parse_evaluation_dataset_json(content)

    assert schema_version in str(captured.value)
    assert "1.0" in str(captured.value)


def test_missing_schema_version_is_rejected_for_external_json():
    payload = dataset_payload()
    del payload["schema_version"]

    with pytest.raises(EvaluationDatasetValidationError) as captured:
        parse_evaluation_dataset_json(json.dumps(payload))

    assert ("schema_version",) in error_locations(captured.value)
    assert "explicitly declare" in str(captured.value)


def test_empty_schema_version_is_rejected_by_domain_validation():
    with pytest.raises(EvaluationDatasetValidationError) as captured:
        parse_evaluation_dataset_json(json.dumps(dataset_payload(schema_version=" ")))

    assert ("schema_version",) in error_locations(captured.value)


def test_dataset_version_is_not_used_as_schema_version():
    payload = dataset_payload(version="1.0")
    del payload["schema_version"]

    with pytest.raises(EvaluationDatasetValidationError) as captured:
        parse_evaluation_dataset_json(json.dumps(payload))

    assert ("schema_version",) in error_locations(captured.value)


@pytest.mark.parametrize(
    ("overrides", "location"),
    [
        ({"name": " "}, ("name",)),
        ({"version": ""}, ("version",)),
        ({"cases": []}, ("cases",)),
        (
            {"cases": [{"id": "case-1", "question": "Question", "unexpected": True}]},
            ("cases", 0, "unexpected"),
        ),
        ({"cases": [{"id": " ", "question": "Question"}]}, ("cases", 0, "id")),
        ({"cases": [{"id": "case-1", "question": " "}]}, ("cases", 0, "question")),
        ({"created_at": "not-a-timestamp"}, ("created_at",)),
        ({"unexpected": True}, ("unexpected",)),
    ],
)
def test_domain_validation_errors_retain_structured_field_locations(
    overrides: dict[str, object], location: tuple[object, ...]
):
    with pytest.raises(EvaluationDatasetValidationError) as captured:
        parse_evaluation_dataset_json(json.dumps(dataset_payload(**overrides)))

    assert location in error_locations(captured.value)
    assert isinstance(captured.value.__cause__, ValidationError)


def test_nested_domain_validation_error_has_actionable_case_location():
    payload = dataset_payload(
        cases=[
            {"id": "case-1", "question": "Question"},
            {"id": "case-2", "question": ""},
        ]
    )

    with pytest.raises(EvaluationDatasetValidationError) as captured:
        parse_evaluation_dataset_json(json.dumps(payload))

    assert ("cases", 1, "question") in error_locations(captured.value)
    assert "cases.1.question" in str(captured.value)


def test_duplicate_case_ids_remain_a_domain_validation_error():
    duplicate_cases = [
        {"id": "duplicate", "question": "First"},
        {"id": "duplicate", "question": "Second"},
    ]

    with pytest.raises(EvaluationDatasetValidationError) as captured:
        parse_evaluation_dataset_json(json.dumps(dataset_payload(cases=duplicate_cases)))

    assert "unique" in str(captured.value).lower()
    assert isinstance(captured.value.__cause__, ValidationError)
