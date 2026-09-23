from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.questions.review_overlay import QuestionReviewOverlayResolver
from app.questions.staging_validator import (
    DEFAULT_QUESTION_STAGING_PATH,
    QuestionStagingPromotionError,
    QuestionStagingValidator,
    assert_candidate_promotable,
)


DERIVATIVE_DATA_ROOT = DEFAULT_QUESTION_STAGING_PATH.parent
DEFAULT_REVIEW_BATCH = DERIVATIVE_DATA_ROOT / "review" / "batch_001"


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _raw_candidates(staging_path: Path = DEFAULT_QUESTION_STAGING_PATH) -> list[dict[str, object]]:
    value = _read_json(staging_path / "candidate_questions.json")
    assert isinstance(value, list)
    return value


def _copy_derivative_data(tmp_path: Path) -> tuple[Path, Path]:
    target = tmp_path / "derivative_applications_v0_1"
    shutil.copytree(DERIVATIVE_DATA_ROOT, target)
    return target / "staging", target / "review" / "batch_001"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_batch_001_resolves_and_has_exact_review_counts() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), DEFAULT_REVIEW_BATCH
    )

    assert result.report.status == "PASS"
    assert result.report.errors == ()
    assert result.report.counts == {
        "verified": 12,
        "hold": 2,
        "rejected": 2,
        "reviewed": 16,
    }
    assert len(result.report.reviewed_candidate_ids) == 16


def test_review_batch_candidate_ids_must_resolve(tmp_path: Path) -> None:
    staging_path, batch_path = _copy_derivative_data(tmp_path)
    holds = _read_json(batch_path / "hold_candidates.json")
    assert isinstance(holds, list) and isinstance(holds[0], dict)
    holds[0]["candidate_id"] = "M12_DERIV_CAND_UNKNOWN"
    _write_json(batch_path / "hold_candidates.json", holds)

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "CANDIDATE_NOT_FOUND" in {error.code for error in result.report.errors}


def test_verified_candidates_have_content_answer_and_taxonomy_review() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), DEFAULT_REVIEW_BATCH
    )

    verified = _read_json(DEFAULT_REVIEW_BATCH / "verified_candidates.json")
    assert isinstance(verified, list)
    for record in verified:
        assert isinstance(record, dict)
        assert record["review_status"] == "VERIFIED"
        assert record["reviewed_content"]
        assert record["verified_correct_answer"]
        assert record["answer_verification"]
        assert record["content_review"] == "CONFIRMED_AGAINST_SOURCE_PAGE"
        assert record["taxonomy_review"] == "CONFIRMED"
        assert record["concepts"]
        assert record["learning_outcomes"]
        assert record["promotion_ready"] is False
        assert "EXPLICIT_PROMOTION_REQUIRED" in _promotion_blockers(result, record["candidate_id"])


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("reviewed_content", "", "MISSING_VERIFIED_REVIEW_FIELD"),
        ("answer_verification", "PENDING", "ANSWER_REVIEW_NOT_CONFIRMED"),
        ("taxonomy_review", "PENDING", "TAXONOMY_REVIEW_NOT_CONFIRMED"),
    ],
)
def test_incomplete_verified_review_is_rejected(
    tmp_path: Path,
    field: str,
    value: str,
    error_code: str,
) -> None:
    staging_path, batch_path = _copy_derivative_data(tmp_path)
    verified = _read_json(batch_path / "verified_candidates.json")
    assert isinstance(verified, list) and isinstance(verified[0], dict)
    verified[0][field] = value
    _write_json(batch_path / "verified_candidates.json", verified)

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert error_code in {error.code for error in result.report.errors}


def _promotion_blockers(result, candidate_id: str) -> tuple[str, ...]:
    with pytest.raises(QuestionStagingPromotionError) as error:
        assert_candidate_promotable(result.candidate(candidate_id))
    return error.value.blockers


def test_hold_and_rejected_candidates_cannot_promote() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), DEFAULT_REVIEW_BATCH
    )

    assert result.candidate("M12_DERIV_CAND_0063")["status"] == "REVIEW_REQUIRED"
    assert result.candidate("M12_DERIV_CAND_0121")["status"] == "REVIEW_REQUIRED"
    assert _promotion_blockers(result, "M12_DERIV_CAND_0063") == ("STATUS_HOLD",)
    assert _promotion_blockers(result, "M12_DERIV_CAND_0121") == ("STATUS_HOLD",)

    assert result.candidate("M12_DERIV_CAND_0152")["status"] == "REJECTED"
    assert result.candidate("M12_DERIV_CAND_0172")["status"] == "REJECTED"
    assert _promotion_blockers(result, "M12_DERIV_CAND_0152") == ("STATUS_REJECTED",)
    assert _promotion_blockers(result, "M12_DERIV_CAND_0172") == ("STATUS_REJECTED",)


def test_patch_does_not_touch_unspecified_candidates() -> None:
    raw = _raw_candidates()
    result = QuestionReviewOverlayResolver().resolve(raw, DEFAULT_REVIEW_BATCH)
    reviewed_ids = set(result.report.reviewed_candidate_ids)
    raw_by_id = {str(item["candidate_id"]): item for item in raw}

    for candidate in result.candidates:
        candidate_id = str(candidate["candidate_id"])
        if candidate_id not in reviewed_ids:
            assert candidate == raw_by_id[candidate_id]


def test_review_overlay_preserves_raw_staging_file_and_provenance() -> None:
    staging_file = DEFAULT_QUESTION_STAGING_PATH / "candidate_questions.json"
    before_hash = hashlib.sha256(staging_file.read_bytes()).hexdigest()
    raw = _raw_candidates()
    raw_before = copy.deepcopy(raw)

    result = QuestionReviewOverlayResolver().resolve(raw, DEFAULT_REVIEW_BATCH)

    assert raw == raw_before
    assert hashlib.sha256(staging_file.read_bytes()).hexdigest() == before_hash
    raw_by_id = {str(item["candidate_id"]): item for item in raw}
    for candidate_id in result.report.reviewed_candidate_ids:
        view = result.candidate(candidate_id)
        original = raw_by_id[candidate_id]
        for field in (
            "source_code",
            "subsource_code",
            "source_page",
            "question_number",
            "fingerprint",
            "raw_question_text",
            "question_type_detected",
        ):
            assert view[field] == original[field]


def test_candidate_0038_is_multiple_choice_in_reviewed_view() -> None:
    raw = _raw_candidates()
    raw_0038 = next(item for item in raw if item["candidate_id"] == "M12_DERIV_CAND_0038")
    result = QuestionReviewOverlayResolver().resolve(raw, DEFAULT_REVIEW_BATCH)
    reviewed = result.candidate("M12_DERIV_CAND_0038")

    assert raw_0038["question_type_detected"] == "SHORT_ANSWER"
    assert reviewed["question_type_detected"] == "SHORT_ANSWER"
    assert reviewed["reviewed_question_type"] == "MULTIPLE_CHOICE"
    assert len(reviewed["reviewed_options"]) == 4


def test_required_quality_flags_are_preserved() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), DEFAULT_REVIEW_BATCH
    )

    assert result.candidate("M12_DERIV_CAND_0121")["review_record"]["review_status"] == (
        "HOLD_SOURCE_ANSWER_CONFLICT"
    )
    assert result.candidate("M12_DERIV_CAND_0063")["review_record"]["review_status"] == (
        "HOLD_EXPERT_REVIEW"
    )
    for candidate_id in ("M12_DERIV_CAND_0152", "M12_DERIV_CAND_0172"):
        assert result.candidate(candidate_id)["review_record"]["review_status"] == (
            "REJECTED_OUT_OF_SCOPE"
        )


def test_true_false_group_candidates_remain_unchanged() -> None:
    raw = _raw_candidates()
    result = QuestionReviewOverlayResolver().resolve(raw, DEFAULT_REVIEW_BATCH)
    raw_groups = {
        str(item["candidate_id"]): item
        for item in raw
        if item["question_type_detected"] == "TRUE_FALSE_GROUP"
    }

    assert raw_groups
    for candidate_id, original in raw_groups.items():
        assert result.candidate(candidate_id) == original


def test_question_staging_command_validation_includes_review_batch() -> None:
    report = QuestionStagingValidator().validate()

    assert report.status == "PASS"
    assert report.checks["review_overlays"] is True
    assert len(report.review_batches) == 1
    assert report.review_batches[0].batch_code == "DATA-MATH12-005_BATCH_001"
    assert report.review_batches[0].counts == {
        "verified": 12,
        "hold": 2,
        "rejected": 2,
        "reviewed": 16,
    }
