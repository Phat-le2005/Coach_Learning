from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.curriculum.staging_validator import (
    DEFAULT_STAGING_PATH,
    CurriculumStagingValidator,
)
from app.validate_curriculum_staging import main


def _copy_staging(tmp_path: Path) -> Path:
    target = tmp_path / "derivative_applications_v0_1"
    shutil.copytree(DEFAULT_STAGING_PATH, target)
    return target


def _read(path: Path, name: str) -> list[dict[str, object]]:
    value = json.loads((path / name).read_text(encoding="utf-8"))
    assert isinstance(value, list)
    return value


def _write(path: Path, name: str, value: object) -> None:
    (path / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_approved_staging_dataset_passes_all_checks() -> None:
    report = CurriculumStagingValidator().validate()

    assert report.status == "PASS"
    assert all(report.checks.values())
    assert report.errors == ()
    assert report.counts == {
        "chapters": 1,
        "topics": 5,
        "problem_types": 24,
        "concepts": 31,
        "learning_outcomes": 10,
        "official_learning_outcomes": 10,
        "concept_relations": 37,
        "problem_type_concepts": 83,
        "problem_type_learning_outcomes": 31,
    }


def test_staging_command_is_deterministic(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out

    assert first == second
    assert json.loads(first)["status"] == "PASS"


@pytest.mark.parametrize(
    ("mutation", "failed_check", "error_code"),
    [
        ("duplicate_code", "unique_codes", "DUPLICATE_CODE"),
        ("missing_reference", "references_resolve", "REFERENCE_NOT_FOUND"),
        ("prerequisite_cycle", "prerequisite_graph_acyclic", "PREREQUISITE_CYCLE"),
        ("primary_concept", "problem_type_primary_concept", "PRIMARY_CONCEPT_COUNT"),
        ("concept_weights", "problem_type_concept_weights", "CONCEPT_WEIGHT_TOTAL"),
        (
            "outcome_coverage",
            "problem_type_learning_outcome_coverage",
            "MISSING_LEARNING_OUTCOME",
        ),
    ],
)
def test_staging_validator_rejects_each_required_invariant(
    tmp_path: Path,
    mutation: str,
    failed_check: str,
    error_code: str,
) -> None:
    path = _copy_staging(tmp_path)
    if mutation == "duplicate_code":
        rows = _read(path, "concepts.json")
        rows.append(dict(rows[0]))
        _write(path, "concepts.json", rows)
    elif mutation == "missing_reference":
        rows = _read(path, "topics.json")
        rows[0]["chapter_code"] = "UNKNOWN_CHAPTER"
        _write(path, "topics.json", rows)
    elif mutation == "prerequisite_cycle":
        rows = _read(path, "concept_relations.json")
        rows.append({
            "source_code": "FIRST_DERIVATIVE",
            "target_code": "FUNCTION_DOMAIN",
            "relation_type": "PREREQUISITE",
        })
        _write(path, "concept_relations.json", rows)
    elif mutation == "primary_concept":
        rows = _read(path, "problem_type_concepts.json")
        problem_type = rows[0]["problem_type_code"]
        for row in rows:
            if row["problem_type_code"] == problem_type:
                row["is_primary"] = False
        _write(path, "problem_type_concepts.json", rows)
    elif mutation == "concept_weights":
        rows = _read(path, "problem_type_concepts.json")
        rows[0]["weight"] = float(rows[0]["weight"]) + 0.01
        _write(path, "problem_type_concepts.json", rows)
    else:
        rows = _read(path, "problem_type_learning_outcomes.json")
        problem_type = rows[0]["problem_type_code"]
        rows = [row for row in rows if row["problem_type_code"] != problem_type]
        _write(path, "problem_type_learning_outcomes.json", rows)

    report = CurriculumStagingValidator().validate(path)

    assert report.status == "FAIL"
    assert report.checks[failed_check] is False
    assert error_code in {error.code for error in report.errors}


def test_staging_remains_review_candidate_and_canonical_is_unverified() -> None:
    metadata = json.loads(
        (DEFAULT_STAGING_PATH / "taxonomy_metadata.json").read_text(encoding="utf-8")
    )
    canonical_manifest = json.loads(
        (DEFAULT_STAGING_PATH.parents[1] / "manifest.json").read_text(encoding="utf-8")
    )

    assert metadata["status"] == "REVIEW_CANDIDATE"
    assert metadata["classification"]["official_learning_outcomes"] == "OFFICIAL_NORMALIZED"
    for field in ("topics", "problem_types", "concepts", "concept_relations"):
        assert metadata["classification"][field] == "COACH_LEARNING_DERIVED"
    assert canonical_manifest["verified_at"] is None
