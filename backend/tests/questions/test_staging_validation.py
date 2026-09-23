from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.questions.import_service import QuestionImportService
from app.questions.models import QuestionImportBatch
from app.questions.staging_validator import (
    DEFAULT_CURRICULUM_STAGING_PATH,
    DEFAULT_QUESTION_STAGING_PATH,
    QuestionStagingPromotionError,
    QuestionStagingValidator,
    assert_candidate_promotable,
)
from app.users.models import Role, User


EXPECTED_GAPS = {
    "PARAMETER_MONOTONICITY",
    "PARAMETER_EXTREMA_COUNT",
    "GLOBAL_EXTREMA_SIMPLE_DOMAIN",
    "COMPLETE_FUNCTION_ANALYSIS_LINEAR_FRACTION",
    "COMPLETE_FUNCTION_ANALYSIS_QUADRATIC_OVER_LINEAR",
    "REAL_WORLD_MONOTONICITY_INTERPRETATION",
}


def _copy_staging(tmp_path: Path) -> Path:
    target = tmp_path / "question_staging"
    shutil.copytree(DEFAULT_QUESTION_STAGING_PATH, target)
    return target


def _read_candidates(path: Path = DEFAULT_QUESTION_STAGING_PATH) -> list[dict[str, object]]:
    value = json.loads((path / "candidate_questions.json").read_text(encoding="utf-8"))
    assert isinstance(value, list)
    return value


def _write_candidates(path: Path, candidates: list[dict[str, object]]) -> None:
    (path / "candidate_questions.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_valid_question_staging_dataset() -> None:
    report = QuestionStagingValidator().validate()

    assert report.status == "PASS"
    assert all(report.checks.values())
    assert report.errors == ()
    assert report.counts == {
        "candidates": 175,
        "problem_types": 24,
        "concepts": 31,
        "learning_outcomes": 10,
        "sources": 4,
        "subsources": 54,
        "duplicate_fingerprint_groups": 0,
        "review_batches": 1,
    }
    assert report.promotion == {
        "eligible": 0,
        "blocked": 175,
        "blocker_counts": {
            "STATUS_NOT_VERIFIED": 175,
            "TRUE_FALSE_GROUP_UNSUPPORTED": 77,
        },
    }


@pytest.mark.parametrize(
    ("mapping", "field", "unknown", "failed_check"),
    [
        (None, "problem_type_code", "UNKNOWN_PROBLEM_TYPE", "problem_type_references"),
        ("concepts", "concept_code", "UNKNOWN_CONCEPT", "concept_references"),
        (
            "learning_outcomes",
            "learning_outcome_code",
            "UNKNOWN_LEARNING_OUTCOME",
            "learning_outcome_references",
        ),
    ],
)
def test_unknown_taxonomy_reference_is_rejected(
    tmp_path: Path,
    mapping: str | None,
    field: str,
    unknown: str,
    failed_check: str,
) -> None:
    path = _copy_staging(tmp_path)
    candidates = _read_candidates(path)
    if mapping is None:
        candidates[0][field] = unknown
    else:
        nested = candidates[0][mapping]
        assert isinstance(nested, list) and isinstance(nested[0], dict)
        nested[0][field] = unknown
    _write_candidates(path, candidates)

    report = QuestionStagingValidator().validate(path, DEFAULT_CURRICULUM_STAGING_PATH)

    assert report.status == "FAIL"
    assert report.checks[failed_check] is False
    assert "REFERENCE_NOT_FOUND" in {error.code for error in report.errors}


def test_unknown_source_is_rejected(tmp_path: Path) -> None:
    path = _copy_staging(tmp_path)
    candidates = _read_candidates(path)
    candidates[0]["source_code"] = "UNKNOWN_SOURCE"
    _write_candidates(path, candidates)

    report = QuestionStagingValidator().validate(path)

    assert report.checks["source_references"] is False


def test_unknown_subsource_is_rejected(tmp_path: Path) -> None:
    path = _copy_staging(tmp_path)
    candidates = _read_candidates(path)
    candidates[0]["subsource_code"] = "UNKNOWN_SUBSOURCE"
    _write_candidates(path, candidates)

    report = QuestionStagingValidator().validate(path)

    assert report.checks["subsource_references"] is False


def test_duplicate_fingerprint_is_reported(tmp_path: Path) -> None:
    path = _copy_staging(tmp_path)
    candidates = _read_candidates(path)
    candidates[1]["fingerprint"] = candidates[0]["fingerprint"]
    _write_candidates(path, candidates)

    report = QuestionStagingValidator().validate(path)

    assert report.status == "PASS"
    assert report.counts["duplicate_fingerprint_groups"] == 1
    assert report.duplicate_fingerprints[0].fingerprint == candidates[0]["fingerprint"]
    assert report.duplicate_fingerprints[0].candidate_ids == tuple(sorted((
        str(candidates[0]["candidate_id"]), str(candidates[1]["candidate_id"])
    )))


def test_review_required_candidate_cannot_promote() -> None:
    candidate = next(
        item
        for item in _read_candidates()
        if item["question_type_detected"] == "MULTIPLE_CHOICE"
    )

    with pytest.raises(QuestionStagingPromotionError) as error:
        assert_candidate_promotable(candidate)

    assert error.value.blockers == ("STATUS_NOT_VERIFIED",)


def test_true_false_group_cannot_promote_even_if_verified() -> None:
    candidate = dict(next(
        item
        for item in _read_candidates()
        if item["question_type_detected"] == "TRUE_FALSE_GROUP"
    ))
    candidate["status"] = "VERIFIED"

    with pytest.raises(QuestionStagingPromotionError) as error:
        assert_candidate_promotable(candidate)

    assert error.value.blockers == ("TRUE_FALSE_GROUP_UNSUPPORTED",)


def test_coverage_reports_all_problem_types_and_six_current_gaps() -> None:
    report = QuestionStagingValidator().validate()

    assert len(report.coverage) == 24
    assert {item.problem_type_code for item in report.coverage} == {
        row["code"]
        for row in json.loads(
            (DEFAULT_CURRICULUM_STAGING_PATH / "problem_types.json").read_text(
                encoding="utf-8"
            )
        )
    }
    assert set(report.coverage_gaps) == EXPECTED_GAPS
    assert all(
        item.question_type_counts.keys()
        >= {"MULTIPLE_CHOICE", "TRUE_FALSE_GROUP", "SHORT_ANSWER"}
        for item in report.coverage
    )


def test_production_import_rejects_review_candidate_before_creating_batch(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
) -> None:
    actor = question_user_factory(Role.TEACHER, "staging-guard@example.com")
    candidate = next(
        item
        for item in _read_candidates()
        if item["question_type_detected"] == "MULTIPLE_CHOICE"
    )

    with pytest.raises(ApplicationError) as error:
        QuestionImportService(db_session).preview(
            actor,
            file_name="candidate_questions.json",
            content=json.dumps([candidate], ensure_ascii=False).encode("utf-8"),
        )

    assert error.value.code == "STAGING_CANDIDATE_NOT_VERIFIED"
    assert db_session.scalar(select(func.count()).select_from(QuestionImportBatch)) == 0


def test_production_import_rejects_true_false_group_before_creating_batch(
    db_session: Session,
    question_user_factory: Callable[[Role, str], User],
) -> None:
    actor = question_user_factory(Role.TEACHER, "staging-group-guard@example.com")
    candidate = dict(next(
        item
        for item in _read_candidates()
        if item["question_type_detected"] == "TRUE_FALSE_GROUP"
    ))
    candidate["status"] = "VERIFIED"

    with pytest.raises(ApplicationError) as error:
        QuestionImportService(db_session).preview(
            actor,
            file_name="candidate_questions.json",
            content=json.dumps([candidate], ensure_ascii=False).encode("utf-8"),
        )

    assert error.value.code == "STAGING_QUESTION_GROUP_UNSUPPORTED"
    assert db_session.scalar(select(func.count()).select_from(QuestionImportBatch)) == 0
