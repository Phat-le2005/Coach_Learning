from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.curriculum.vector_staging import (
    DEFAULT_VECTOR_STAGING_PATH,
    EXPECTED_VECTOR_CONTENT_SHA256,
    EXPECTED_VECTOR_COUNTS,
    VectorCurriculumStagingValidator,
)
from app.validate_vector_staging import main


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "vector_coordinates_v0_1"
    shutil.copytree(DEFAULT_VECTOR_STAGING_PATH, target)
    return target


def _mutate(path: Path, name: str, mutate) -> None:
    file_path = path / name
    value = json.loads(file_path.read_text(encoding="utf-8"))
    mutate(value)
    file_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_vector_staging_passes_exact_contract() -> None:
    report = VectorCurriculumStagingValidator().validate()

    assert report.is_valid, report.as_dict()
    assert all(report.checks.values())
    assert report.counts == EXPECTED_VECTOR_COUNTS
    assert report.content_sha256 == EXPECTED_VECTOR_CONTENT_SHA256
    assert not (DEFAULT_VECTOR_STAGING_PATH / "manifest.json").exists()


def test_vector_staging_provenance_is_not_moet_taxonomy() -> None:
    metadata = json.loads(
        (DEFAULT_VECTOR_STAGING_PATH / "taxonomy_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    official = json.loads(
        (DEFAULT_VECTOR_STAGING_PATH / "official_learning_outcomes.json").read_text(
            encoding="utf-8"
        )
    )

    assert metadata["status"] == "REVIEW_CANDIDATE"
    assert metadata["classification"]["official_learning_outcomes"] == (
        "OFFICIAL_NORMALIZED"
    )
    assert all(
        metadata["classification"][field].startswith("COACH_LEARNING_DERIVED")
        for field in (
            "topics", "problem_types", "concepts", "concept_relations",
            "weights", "difficulty",
        )
    )
    assert {row["provenance_type"] for row in official} == {"OFFICIAL_NORMALIZED"}


@pytest.mark.parametrize(
    ("name", "mutation", "check", "code"),
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
            lambda rows: rows[0].update(default_difficulty=1.1),
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
            lambda rows: rows[0].update(weight=0.4),
            "concept_weight_totals",
            "WEIGHT_TOTAL",
        ),
        (
            "problem_type_concepts.json",
            lambda rows: rows[0].update(is_primary=False),
            "primary_concept",
            "PRIMARY_CONCEPT_COUNT",
        ),
        (
            "problem_type_learning_outcomes.json",
            lambda rows: rows[0].update(weight=0.9),
            "learning_outcome_weight_totals",
            "WEIGHT_TOTAL",
        ),
    ],
)
def test_vector_validator_rejects_invalid_taxonomy(
    tmp_path: Path,
    name: str,
    mutation,
    check: str,
    code: str,
) -> None:
    path = _copy(tmp_path)
    _mutate(path, name, mutation)

    report = VectorCurriculumStagingValidator().validate(path)

    assert report.status == "FAIL"
    assert report.checks[check] is False
    assert code in {error.code for error in report.errors}
    assert report.checks["deterministic_content_hash"] is False


def test_vector_validator_rejects_manifest(tmp_path: Path) -> None:
    path = _copy(tmp_path)
    (path / "manifest.json").write_text("{}", encoding="utf-8")
    report = VectorCurriculumStagingValidator().validate(path)
    assert report.checks["manifest_absent"] is False
    assert "STAGING_MANIFEST_FORBIDDEN" in {error.code for error in report.errors}


def test_vector_content_hash_and_cli_are_deterministic(
    tmp_path: Path, capsys
) -> None:
    first = VectorCurriculumStagingValidator().validate()
    second = VectorCurriculumStagingValidator().validate()
    assert first.content_sha256 == second.content_sha256 == EXPECTED_VECTOR_CONTENT_SHA256

    reformatted = _copy(tmp_path)
    topics = json.loads((reformatted / "topics.json").read_text(encoding="utf-8"))
    (reformatted / "topics.json").write_text(
        json.dumps(topics, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    assert VectorCurriculumStagingValidator().validate(
        reformatted
    ).content_sha256 == EXPECTED_VECTOR_CONTENT_SHA256

    assert main([]) == 0
    first_output = capsys.readouterr().out
    assert main([]) == 0
    second_output = capsys.readouterr().out
    assert first_output == second_output
