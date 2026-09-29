from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.curriculum.grouped_data_dispersion_staging import (
    DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH,
    EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256,
    EXPECTED_GROUPED_DATA_DISPERSION_COUNTS,
    EXPECTED_PROBLEM_TYPE_CODES,
    GroupedDataDispersionStagingValidator,
)
from app.validate_grouped_data_dispersion_staging import main


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "grouped_data_dispersion_v0_1"
    shutil.copytree(DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH, target)
    return target


def _mutate(path: Path, name: str, mutation) -> None:
    file_path = path / name
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    mutation(payload)
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_grouped_data_dispersion_staging_has_exact_contract() -> None:
    report = GroupedDataDispersionStagingValidator().validate()

    assert report.is_valid, report.as_dict()
    assert all(report.checks.values())
    assert report.counts == EXPECTED_GROUPED_DATA_DISPERSION_COUNTS
    assert report.content_sha256 == EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256
    assert not (DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH / "manifest.json").exists()


def test_official_outcomes_and_derived_taxonomy_are_distinct() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH
    metadata = json.loads((root / "taxonomy_metadata.json").read_text("utf-8"))
    outcomes = json.loads(
        (root / "official_learning_outcomes.json").read_text("utf-8")
    )
    problem_types = json.loads((root / "problem_types.json").read_text("utf-8"))

    assert metadata["status"] == "REVIEW_CANDIDATE"
    assert metadata["subject_code"] == "MATH_G12"
    assert metadata["chapter_code"] == "GROUPED_DATA_DISPERSION"
    assert metadata["classification"]["official_learning_outcomes"] == (
        "OFFICIAL_NORMALIZED"
    )
    assert all(
        metadata["classification"][field].startswith("COACH_LEARNING_DERIVED")
        for field in (
            "topics",
            "problem_types",
            "concepts",
            "concept_relations",
            "weights",
            "difficulty",
        )
    )
    assert {row["provenance_type"] for row in outcomes} == {
        "OFFICIAL_NORMALIZED"
    }
    assert {row["code"] for row in problem_types} == EXPECTED_PROBLEM_TYPE_CODES


def test_grade11_boundary_keeps_only_dispersion_targets() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_STAGING_PATH
    metadata = json.loads((root / "taxonomy_metadata.json").read_text("utf-8"))
    concepts = json.loads((root / "concepts.json").read_text("utf-8"))
    problem_types = json.loads((root / "problem_types.json").read_text("utf-8"))

    assert "range, interquartile range, variance, standard deviation" in metadata[
        "scope_boundary"
    ]
    assert {"GROUPED_QUARTILE_INTERPOLATION", "GROUPED_MEAN_FOR_DISPERSION"} <= {
        row["code"] for row in concepts
    }
    assert all(
        forbidden not in row["code"]
        for row in problem_types
        for forbidden in ("MEAN_ONLY", "MEDIAN", "MODE", "QUARTILE_ONLY")
    )


@pytest.mark.parametrize(
    ("file_name", "mutation", "check", "code"),
    [
        (
            "concepts.json",
            lambda rows: rows.append(dict(rows[0])),
            "unique_codes",
            "DUPLICATE_CODE",
        ),
        (
            "topics.json",
            lambda rows: rows[0].update(chapter_code="UNKNOWN"),
            "references_resolve",
            "REFERENCE_NOT_FOUND",
        ),
        (
            "problem_types.json",
            lambda rows: rows[0].update(default_difficulty=1.01),
            "difficulty_range",
            "INVALID_DIFFICULTY",
        ),
        (
            "concepts.json",
            lambda rows: rows[0].update(grade_level=11),
            "grade_level",
            "INVALID_GRADE_LEVEL",
        ),
        (
            "problem_type_concepts.json",
            lambda rows: rows[0].update(is_primary=False),
            "primary_concept",
            "PRIMARY_CONCEPT_COUNT",
        ),
        (
            "problem_type_concepts.json",
            lambda rows: rows[0].update(weight=0.5),
            "concept_weight_totals",
            "WEIGHT_TOTAL",
        ),
        (
            "problem_type_learning_outcomes.json",
            lambda rows: rows[0].update(weight=0.9),
            "learning_outcome_weight_totals",
            "WEIGHT_TOTAL",
        ),
    ],
)
def test_validator_rejects_invalid_taxonomy(
    tmp_path: Path,
    file_name: str,
    mutation,
    check: str,
    code: str,
) -> None:
    path = _copy(tmp_path)
    _mutate(path, file_name, mutation)

    report = GroupedDataDispersionStagingValidator().validate(path)

    assert report.status == "FAIL"
    assert report.checks[check] is False
    assert code in {error.code for error in report.errors}
    assert report.checks["deterministic_content_hash"] is False


def test_validator_rejects_prerequisite_cycle(tmp_path: Path) -> None:
    path = _copy(tmp_path)

    def add_reverse_edge(rows: list[dict]) -> None:
        edge = rows[0]
        rows.append(
            {
                "source_code": edge["target_code"],
                "target_code": edge["source_code"],
                "relation_type": "PREREQUISITE",
            }
        )

    _mutate(path, "concept_relations.json", add_reverse_edge)
    report = GroupedDataDispersionStagingValidator().validate(path)

    assert report.checks["prerequisite_graph_acyclic"] is False
    assert "PREREQUISITE_CYCLE" in {error.code for error in report.errors}


def test_validator_rejects_manifest_and_identity_change(tmp_path: Path) -> None:
    path = _copy(tmp_path)
    (path / "manifest.json").write_text("{}", encoding="utf-8")
    _mutate(path, "taxonomy_metadata.json", lambda row: row.update(status="VERIFIED"))

    report = GroupedDataDispersionStagingValidator().validate(path)

    assert report.checks["manifest_absent"] is False
    assert report.checks["subject_chapter_status"] is False
    assert "STAGING_MANIFEST_FORBIDDEN" in {error.code for error in report.errors}


def test_content_hash_and_cli_are_deterministic(tmp_path: Path, capsys) -> None:
    validator = GroupedDataDispersionStagingValidator()
    first = validator.validate()
    second = validator.validate()
    assert first.content_sha256 == second.content_sha256 == (
        EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256
    )

    reformatted = _copy(tmp_path)
    topics = json.loads((reformatted / "topics.json").read_text("utf-8"))
    (reformatted / "topics.json").write_text(
        json.dumps(topics, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    assert validator.validate(reformatted).content_sha256 == (
        EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256
    )

    assert main([]) == 0
    first_output = capsys.readouterr().out
    assert main([]) == 0
    second_output = capsys.readouterr().out
    assert first_output == second_output
