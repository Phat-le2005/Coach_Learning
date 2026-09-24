from __future__ import annotations

import copy
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from app.questions.review_overlay import QuestionReviewOverlayResolver
from app.questions.question_type_resolution import effective_question_type
from app.questions.staging_validator import (
    DEFAULT_QUESTION_STAGING_PATH,
    QuestionStagingPromotionError,
    QuestionStagingValidator,
    assert_candidate_promotable,
    candidate_promotion_blockers,
)


DERIVATIVE_DATA_ROOT = DEFAULT_QUESTION_STAGING_PATH.parent
DEFAULT_REVIEW_BATCH = DERIVATIVE_DATA_ROOT / "review" / "batch_001"
SECOND_REVIEW_BATCH = DERIVATIVE_DATA_ROOT / "review" / "batch_002"
THIRD_REVIEW_BATCH = DERIVATIVE_DATA_ROOT / "review" / "batch_003"
FOURTH_REVIEW_BATCH = DERIVATIVE_DATA_ROOT / "review" / "batch_004"
FIFTH_REVIEW_BATCH = DERIVATIVE_DATA_ROOT / "review" / "batch_005"
REVIEW_BATCHES = (
    DEFAULT_REVIEW_BATCH,
    SECOND_REVIEW_BATCH,
    THIRD_REVIEW_BATCH,
    FOURTH_REVIEW_BATCH,
    FIFTH_REVIEW_BATCH,
)


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


def _effective_candidates() -> list[dict[str, object]]:
    current = _raw_candidates()
    for batch_path in REVIEW_BATCHES:
        result = QuestionReviewOverlayResolver().resolve(current, batch_path)
        assert result.report.is_valid
        current = list(result.candidates)
    return current


def _copied_batch_002(tmp_path: Path) -> tuple[Path, Path]:
    staging_path, _ = _copy_derivative_data(tmp_path)
    return staging_path, staging_path.parent / "review" / "batch_002"


def _set_duplicate_target(
    batch_path: Path,
    candidate_id: str,
    duplicate_of_candidate_id: str,
) -> None:
    rejected = _read_json(batch_path / "rejected_candidates.json")
    patches = _read_json(batch_path / "candidate_patch.json")
    assert isinstance(rejected, list)
    assert isinstance(patches, list)
    record = next(
        item
        for item in rejected
        if isinstance(item, dict) and item.get("candidate_id") == candidate_id
    )
    patch = next(
        item
        for item in patches
        if isinstance(item, dict) and item.get("candidate_id") == candidate_id
    )
    assert record["review_status"] == "REJECTED_DUPLICATE"
    assert isinstance(patch.get("set"), dict)
    record["duplicate_of_candidate_id"] = duplicate_of_candidate_id
    patch["set"]["duplicate_of_candidate_id"] = duplicate_of_candidate_id
    patch["set"]["rejection_reason"] = f"DUPLICATE_OF:{duplicate_of_candidate_id}"
    _write_json(batch_path / "rejected_candidates.json", rejected)
    _write_json(batch_path / "candidate_patch.json", patches)


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


def test_batch_002_resolves_and_has_exact_review_counts() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), SECOND_REVIEW_BATCH
    )

    assert result.report.status == "PASS"
    assert result.report.errors == ()
    assert result.report.counts == {
        "verified": 13,
        "hold": 8,
        "rejected": 18,
        "reviewed": 39,
    }
    assert len(result.report.reviewed_candidate_ids) == 39


def test_batch_003_resolves_and_has_exact_review_counts() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), THIRD_REVIEW_BATCH
    )

    assert result.report.status == "PASS"
    assert result.report.errors == ()
    assert result.report.counts == {
        "verified": 3,
        "hold": 11,
        "rejected": 11,
        "reviewed": 25,
    }
    assert len(result.report.reviewed_candidate_ids) == 25


def test_batch_004_resolves_and_has_exact_review_counts() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), FOURTH_REVIEW_BATCH
    )

    assert result.report.status == "PASS"
    assert result.report.errors == ()
    assert result.report.counts == {
        "verified": 0,
        "hold": 12,
        "rejected": 6,
        "reviewed": 18,
    }
    assert len(result.report.reviewed_candidate_ids) == 18


def test_batch_005_resolves_and_has_exact_review_counts() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), FIFTH_REVIEW_BATCH
    )

    assert result.report.status == "PASS"
    assert result.report.errors == ()
    assert result.report.counts == {
        "verified": 1,
        "hold": 7,
        "rejected": 6,
        "reviewed": 14,
    }
    assert len(result.report.reviewed_candidate_ids) == 14


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


def test_mixed_visual_and_text_only_verified_candidates_validate(
    tmp_path: Path,
) -> None:
    staging_path, batch_path = _copy_derivative_data(tmp_path)
    verified = _read_json(batch_path / "verified_candidates.json")
    patches = _read_json(batch_path / "candidate_patch.json")
    assert isinstance(verified, list) and len(verified) >= 2
    assert isinstance(patches, list)
    visual_record = verified[0]
    text_record = verified[1]
    assert isinstance(visual_record, dict) and isinstance(text_record, dict)
    visual_patch = next(
        item
        for item in patches
        if isinstance(item, dict)
        and item.get("candidate_id") == visual_record["candidate_id"]
    )
    text_patch = next(
        item
        for item in patches
        if isinstance(item, dict)
        and item.get("candidate_id") == text_record["candidate_id"]
    )
    assert isinstance(visual_patch.get("set"), dict)
    assert isinstance(text_patch.get("set"), dict)
    visual_record["visual_asset_required"] = True
    visual_record["visual_source_page"] = int(visual_record["source_page"])
    visual_patch["set"]["visual_asset_required"] = True
    visual_patch["set"]["visual_source_page"] = visual_record["visual_source_page"]
    text_record.pop("visual_asset_required", None)
    text_record.pop("visual_source_page", None)
    text_patch["set"].pop("visual_asset_required", None)
    text_patch["set"].pop("visual_source_page", None)
    _write_json(batch_path / "verified_candidates.json", verified)
    _write_json(batch_path / "candidate_patch.json", patches)

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "PASS"
    assert "VISUAL_ASSET_REQUIRED" in candidate_promotion_blockers(
        result.candidate(str(visual_record["candidate_id"]))
    )
    assert "VISUAL_ASSET_REQUIRED" not in candidate_promotion_blockers(
        result.candidate(str(text_record["candidate_id"]))
    )


@pytest.mark.parametrize("visual_source_page", [0, -1, True, "1", None])
def test_visual_verified_candidate_requires_positive_integer_source_page(
    tmp_path: Path,
    visual_source_page: object,
) -> None:
    staging_path, batch_path = _copy_derivative_data(tmp_path)
    verified = _read_json(batch_path / "verified_candidates.json")
    patches = _read_json(batch_path / "candidate_patch.json")
    assert isinstance(verified, list) and isinstance(verified[0], dict)
    assert isinstance(patches, list)
    record = verified[0]
    patch = next(
        item
        for item in patches
        if isinstance(item, dict) and item.get("candidate_id") == record["candidate_id"]
    )
    assert isinstance(patch.get("set"), dict)
    record["visual_asset_required"] = True
    record["visual_source_page"] = visual_source_page
    patch["set"]["visual_asset_required"] = True
    patch["set"]["visual_source_page"] = visual_source_page
    _write_json(batch_path / "verified_candidates.json", verified)
    _write_json(batch_path / "candidate_patch.json", patches)

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "VISUAL_SOURCE_PAGE_INVALID" in {
        error.code for error in result.report.errors
    }


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

    current = raw
    results = []
    for batch_path in REVIEW_BATCHES:
        result = QuestionReviewOverlayResolver().resolve(current, batch_path)
        assert result.report.is_valid
        results.append(result)
        current = list(result.candidates)

    assert raw == raw_before
    assert hashlib.sha256(staging_file.read_bytes()).hexdigest() == before_hash
    raw_by_id = {str(item["candidate_id"]): item for item in raw}
    effective_by_id = {str(item["candidate_id"]): item for item in current}
    reviewed_ids = {
        candidate_id
        for result in results
        for candidate_id in result.report.reviewed_candidate_ids
    }
    for candidate_id in reviewed_ids:
        view = effective_by_id[candidate_id]
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
    assert len(report.review_batches) == 5
    reports = {batch.batch_code: batch for batch in report.review_batches}
    assert reports["DATA-MATH12-005_BATCH_001"].counts == {
        "verified": 12,
        "hold": 2,
        "rejected": 2,
        "reviewed": 16,
    }
    assert reports["DATA-MATH12-005_BATCH_002"].counts == {
        "verified": 13,
        "hold": 8,
        "rejected": 18,
        "reviewed": 39,
    }
    assert reports["DATA-MATH12-005_BATCH_003"].counts == {
        "verified": 3,
        "hold": 11,
        "rejected": 11,
        "reviewed": 25,
    }
    assert reports["DATA-MATH12-005_BATCH_004"].counts == {
        "verified": 0,
        "hold": 12,
        "rejected": 6,
        "reviewed": 18,
    }
    assert reports["DATA-MATH12-005_BATCH_005"].counts == {
        "verified": 1,
        "hold": 7,
        "rejected": 6,
        "reviewed": 14,
    }


def test_validator_keeps_raw_and_effective_reviewed_counts_explicit() -> None:
    report = QuestionStagingValidator().validate()

    assert report.raw.status_summary == {
        "total": 175,
        "verified": 0,
        "hold": 0,
        "rejected": 0,
        "untouched_review_required": 175,
    }
    assert report.effective_reviewed.status_summary == {
        "total": 175,
        "verified": 29,
        "hold": 40,
        "rejected": 43,
        "untouched_review_required": 63,
    }
    assert 175 - report.effective_reviewed.status_summary[
        "untouched_review_required"
    ] == 112


def test_all_untouched_candidates_are_structural_true_false_groups_after_batch_005() -> None:
    untouched = [
        candidate
        for candidate in _effective_candidates()
        if QuestionStagingValidator._review_status(candidate)
        == "UNTOUCHED_REVIEW_REQUIRED"
    ]
    question_type_counts = Counter(
        str(candidate["question_type_detected"]) for candidate in untouched
    )

    assert len(untouched) == 63
    assert question_type_counts == {"TRUE_FALSE_GROUP": 63}
    assert question_type_counts["MULTIPLE_CHOICE"] == 0
    assert question_type_counts["SHORT_ANSWER"] == 0
    for candidate in untouched:
        raw_text = str(candidate["raw_question_text"])
        assert all(marker in raw_text for marker in ("a)", "b)", "c)", "d)"))


def test_effective_promotion_summary_blocks_all_verified_candidates() -> None:
    report = QuestionStagingValidator().validate()

    assert report.effective_reviewed.promotion["eligible"] == 0
    assert report.effective_reviewed.promotion["blocked"] == 175
    assert report.effective_reviewed.promotion["blocker_counts"][
        "EXPLICIT_PROMOTION_REQUIRED"
    ] == 29
    assert report.effective_reviewed.promotion["blocker_counts"]["STATUS_HOLD"] == 40
    assert report.effective_reviewed.promotion["blocker_counts"]["STATUS_REJECTED"] == 43
    assert report.effective_reviewed.promotion["blocker_counts"][
        "STATUS_NOT_VERIFIED"
    ] == 63
    assert report.effective_reviewed.promotion["blocker_counts"][
        "VISUAL_ASSET_REQUIRED"
    ] == 42
    assert report.effective_reviewed.promotion["blocker_counts"][
        "TRUE_FALSE_GROUP_UNSUPPORTED"
    ] == 74


def test_effective_coverage_excludes_rejected_and_reports_holds() -> None:
    report = QuestionStagingValidator().validate()

    assert sum(item.candidate_count for item in report.raw.coverage) == 175
    assert sum(
        item.candidate_count for item in report.effective_reviewed.coverage
    ) == 132
    assert sum(
        item.rejected_excluded_count for item in report.effective_reviewed.coverage
    ) == 43
    assert sum(item.hold_count for item in report.effective_reviewed.coverage) == 40
    assert all(item.rejected_excluded_count == 0 for item in report.raw.coverage)


def test_raw_coverage_remains_available_for_audit() -> None:
    report = QuestionStagingValidator().validate()

    assert report.coverage is report.raw.coverage
    assert report.coverage_gaps is report.raw.coverage_gaps
    assert len(report.raw.coverage) == 24
    assert report.raw.promotion["blocker_counts"]["STATUS_NOT_VERIFIED"] == 175
    assert sum(
        item.question_type_counts["TRUE_FALSE_GROUP"]
        for item in report.raw.coverage
    ) == 77
    assert sum(
        item.question_type_counts["MULTIPLE_CHOICE"]
        for item in report.effective_reviewed.coverage
    ) == 57
    assert sum(
        item.question_type_counts["TRUE_FALSE_GROUP"]
        for item in report.effective_reviewed.coverage
    ) == 63


def test_effective_view_uses_reviewed_type_for_candidate_0038() -> None:
    raw_candidates = _raw_candidates()
    candidate = next(
        item for item in raw_candidates if item["candidate_id"] == "M12_DERIV_CAND_0038"
    )
    current = raw_candidates
    for batch_path in REVIEW_BATCHES:
        result = QuestionReviewOverlayResolver().resolve(current, batch_path)
        assert result.report.is_valid
        current = list(result.candidates)
    effective = next(
        item for item in current if item["candidate_id"] == "M12_DERIV_CAND_0038"
    )

    assert candidate["question_type_detected"] == "SHORT_ANSWER"
    assert effective["question_type_detected"] == "SHORT_ANSWER"
    assert effective["reviewed_question_type"] == "MULTIPLE_CHOICE"


def test_all_effective_verified_candidates_require_explicit_promotion() -> None:
    current = _raw_candidates()
    for batch_path in REVIEW_BATCHES:
        result = QuestionReviewOverlayResolver().resolve(current, batch_path)
        assert result.report.is_valid
        current = list(result.candidates)

    verified = [candidate for candidate in current if candidate.get("status") == "VERIFIED"]

    assert len(verified) == 29
    assert all(
        "EXPLICIT_PROMOTION_REQUIRED" in candidate_promotion_blockers(candidate)
        for candidate in verified
    )


def test_batch_002_verified_candidates_require_visual_asset_and_promotion() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), SECOND_REVIEW_BATCH
    )
    records = _read_json(SECOND_REVIEW_BATCH / "verified_candidates.json")
    assert isinstance(records, list)

    assert len(records) == 13
    for record in records:
        assert isinstance(record, dict)
        candidate = result.candidate(str(record["candidate_id"]))
        assert record["visual_asset_required"] is True
        assert candidate["visual_asset_required"] is True
        assert set(candidate_promotion_blockers(candidate)) >= {
            "EXPLICIT_PROMOTION_REQUIRED",
            "VISUAL_ASSET_REQUIRED",
        }


def test_batch_002_duplicate_targets_resolve() -> None:
    candidates = {
        str(candidate["candidate_id"]): candidate for candidate in _raw_candidates()
    }
    records = _read_json(SECOND_REVIEW_BATCH / "rejected_candidates.json")
    assert isinstance(records, list)
    duplicates = [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("review_status") == "REJECTED_DUPLICATE"
    ]

    assert len(duplicates) == 12
    assert all(record["duplicate_of_candidate_id"] in candidates for record in duplicates)


def test_valid_duplicate_target_passes_review_validation() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), SECOND_REVIEW_BATCH
    )

    assert result.report.status == "PASS"
    assert not {
        error.code
        for error in result.report.errors
        if error.check == "duplicate_references"
    }


def test_unknown_duplicate_target_fails(tmp_path: Path) -> None:
    staging_path, batch_path = _copied_batch_002(tmp_path)
    _set_duplicate_target(
        batch_path,
        "M12_DERIV_CAND_0045",
        "M12_DERIV_CAND_UNKNOWN",
    )

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "DUPLICATE_TARGET_NOT_FOUND" in {
        error.code for error in result.report.errors
    }


def test_self_duplicate_target_fails(tmp_path: Path) -> None:
    staging_path, batch_path = _copied_batch_002(tmp_path)
    _set_duplicate_target(
        batch_path,
        "M12_DERIV_CAND_0045",
        "M12_DERIV_CAND_0045",
    )

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "DUPLICATE_TARGET_SELF" in {error.code for error in result.report.errors}


def test_duplicate_chain_fails(tmp_path: Path) -> None:
    staging_path, batch_path = _copied_batch_002(tmp_path)
    _set_duplicate_target(
        batch_path,
        "M12_DERIV_CAND_0045",
        "M12_DERIV_CAND_0046",
    )

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "DUPLICATE_CHAIN_NOT_ALLOWED" in {
        error.code for error in result.report.errors
    }


def test_duplicate_cycle_fails(tmp_path: Path) -> None:
    staging_path, batch_path = _copied_batch_002(tmp_path)
    _set_duplicate_target(
        batch_path,
        "M12_DERIV_CAND_0045",
        "M12_DERIV_CAND_0046",
    )
    _set_duplicate_target(
        batch_path,
        "M12_DERIV_CAND_0046",
        "M12_DERIV_CAND_0045",
    )

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "DUPLICATE_CYCLE" in {error.code for error in result.report.errors}


def test_duplicate_target_rejected_out_of_scope_fails(tmp_path: Path) -> None:
    staging_path, batch_path = _copied_batch_002(tmp_path)
    _set_duplicate_target(
        batch_path,
        "M12_DERIV_CAND_0045",
        "M12_DERIV_CAND_0048",
    )

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "DUPLICATE_TARGET_OUT_OF_SCOPE" in {
        error.code for error in result.report.errors
    }


def test_batch_002_question_group_holds_remain_blocked() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), SECOND_REVIEW_BATCH
    )
    candidate_ids = {
        "M12_DERIV_CAND_0012",
        "M12_DERIV_CAND_0019",
        "M12_DERIV_CAND_0035",
        "M12_DERIV_CAND_0047",
        "M12_DERIV_CAND_0052",
    }

    for candidate_id in candidate_ids:
        candidate = result.candidate(candidate_id)
        assert candidate["status"] == "REVIEW_REQUIRED"
        assert candidate["review_record"]["review_status"] == (
            "HOLD_QUESTION_TYPE_CORRECTION"
        )
        assert candidate["review_record"]["requires_question_group_model"] is True
        assert set(candidate_promotion_blockers(candidate)) >= {
            "STATUS_HOLD",
            "TRUE_FALSE_GROUP_UNSUPPORTED",
        }


def test_batch_002_primary_source_holds_remain_blocked() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), SECOND_REVIEW_BATCH
    )
    for candidate_id in (
        "M12_DERIV_CAND_0003",
        "M12_DERIV_CAND_0007",
        "M12_DERIV_CAND_0009",
    ):
        candidate = result.candidate(candidate_id)
        assert candidate["review_record"]["review_status"] == (
            "HOLD_PRIMARY_SOURCE_CROSSCHECK"
        )
        assert "STATUS_HOLD" in candidate_promotion_blockers(candidate)


def test_batch_003_verified_text_questions_require_explicit_promotion() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), THIRD_REVIEW_BATCH
    )
    expected_ids = {
        "M12_DERIV_CAND_0013",
        "M12_DERIV_CAND_0032",
        "M12_DERIV_CAND_0059",
    }
    records = _read_json(THIRD_REVIEW_BATCH / "verified_candidates.json")
    assert isinstance(records, list)

    assert {str(record["candidate_id"]) for record in records} == expected_ids
    for candidate_id in expected_ids:
        candidate = result.candidate(candidate_id)
        assert candidate["status"] == "VERIFIED"
        assert candidate["promotion_ready"] is False
        assert candidate_promotion_blockers(candidate) == (
            "EXPLICIT_PROMOTION_REQUIRED",
        )


def test_batch_003_visual_source_holds_remain_review_required() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), THIRD_REVIEW_BATCH
    )
    records = _read_json(THIRD_REVIEW_BATCH / "hold_candidates.json")
    assert isinstance(records, list)
    visual_holds = [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("review_status") == "HOLD_VISUAL_SOURCE_REVIEW"
    ]

    assert len(visual_holds) == 10
    for record in visual_holds:
        candidate = result.candidate(str(record["candidate_id"]))
        assert candidate["status"] == "REVIEW_REQUIRED"
        assert candidate["review_record"]["review_status"] == (
            "HOLD_VISUAL_SOURCE_REVIEW"
        )
        assert "STATUS_HOLD" in candidate_promotion_blockers(candidate)


def test_batch_003_misdetected_holds_preserve_raw_question_type() -> None:
    raw_by_id = {
        str(candidate["candidate_id"]): candidate for candidate in _raw_candidates()
    }
    result = QuestionReviewOverlayResolver().resolve(
        list(raw_by_id.values()), THIRD_REVIEW_BATCH
    )

    for candidate_id in ("M12_DERIV_CAND_0030", "M12_DERIV_CAND_0040"):
        candidate = result.candidate(candidate_id)
        assert raw_by_id[candidate_id]["question_type_detected"] == "SHORT_ANSWER"
        assert candidate["question_type_detected"] == "SHORT_ANSWER"
        assert "reviewed_question_type" not in candidate
        assert candidate["review_record"]["detected_question_type"] == (
            "SHORT_ANSWER"
        )
        assert candidate["review_record"]["suggested_question_type"] == (
            "MULTIPLE_CHOICE"
        )


def test_batch_003_corrupt_content_candidate_remains_hold() -> None:
    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(), THIRD_REVIEW_BATCH
    )
    candidate = result.candidate("M12_DERIV_CAND_0133")

    assert candidate["status"] == "REVIEW_REQUIRED"
    assert candidate["review_record"]["review_status"] == (
        "HOLD_CONTENT_EXTRACTION_CORRUPT"
    )
    assert "reviewed_content" not in candidate
    assert candidate_promotion_blockers(candidate) == ("STATUS_HOLD",)


def test_batch_003_duplicate_targets_are_direct_retained_candidates() -> None:
    current = _raw_candidates()
    for batch_path in REVIEW_BATCHES:
        result = QuestionReviewOverlayResolver().resolve(current, batch_path)
        assert result.report.is_valid
        current = list(result.candidates)
    effective_by_id = {
        str(candidate["candidate_id"]): candidate for candidate in current
    }
    records = _read_json(THIRD_REVIEW_BATCH / "rejected_candidates.json")
    assert isinstance(records, list)
    duplicate_records = [
        record
        for record in records
        if isinstance(record, dict)
        and record.get("review_status") == "REJECTED_DUPLICATE"
    ]
    duplicate_ids = {str(record["candidate_id"]) for record in duplicate_records}

    assert len(duplicate_records) == 11
    for record in duplicate_records:
        candidate_id = str(record["candidate_id"])
        target_id = str(record["duplicate_of_candidate_id"])
        assert target_id in effective_by_id
        assert target_id != candidate_id
        assert target_id not in duplicate_ids
        target = effective_by_id[target_id]
        assert target["status"] != "REJECTED"
        target_review = target.get("review_record")
        if isinstance(target_review, dict):
            assert not str(target_review.get("review_status", "")).startswith(
                "REJECTED"
            )


def test_batch_004_visual_holds_remain_review_required_and_blocked() -> None:
    effective_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in _effective_candidates()
    }
    records = _read_json(FOURTH_REVIEW_BATCH / "hold_candidates.json")
    assert isinstance(records, list)
    expected_ids = {
        "M12_DERIV_CAND_0060",
        "M12_DERIV_CAND_0069",
        "M12_DERIV_CAND_0078",
        "M12_DERIV_CAND_0103",
        "M12_DERIV_CAND_0107",
        "M12_DERIV_CAND_0110",
        "M12_DERIV_CAND_0112",
        "M12_DERIV_CAND_0135",
        "M12_DERIV_CAND_0137",
        "M12_DERIV_CAND_0149",
        "M12_DERIV_CAND_0158",
        "M12_DERIV_CAND_0169",
    }
    source_answers = {
        "M12_DERIV_CAND_0069": "D",
        "M12_DERIV_CAND_0112": "B",
        "M12_DERIV_CAND_0137": "A",
        "M12_DERIV_CAND_0169": "C",
    }

    assert {str(record["candidate_id"]) for record in records} == expected_ids
    for record in records:
        candidate_id = str(record["candidate_id"])
        candidate = effective_by_id[candidate_id]
        assert record["review_status"] == "HOLD_VISUAL_SOURCE_REVIEW"
        assert record["visual_asset_required"] is True
        assert candidate["status"] == "REVIEW_REQUIRED"
        assert candidate["review_record"]["visual_asset_required"] is True
        assert "verified_correct_answer" not in candidate
        assert "source_answer_detected" not in candidate
        assert set(candidate_promotion_blockers(candidate)) >= {
            "STATUS_HOLD",
            "VISUAL_ASSET_REQUIRED",
        }
        with pytest.raises(QuestionStagingPromotionError):
            assert_candidate_promotable(candidate)
    for candidate_id, answer in source_answers.items():
        assert effective_by_id[candidate_id]["review_record"][
            "source_answer_detected"
        ] == answer


def test_batch_004_duplicate_targets_are_direct_retained_candidates() -> None:
    effective_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in _effective_candidates()
    }
    records = _read_json(FOURTH_REVIEW_BATCH / "rejected_candidates.json")
    assert isinstance(records, list)
    expected_mappings = {
        "M12_DERIV_CAND_0015": "M12_DERIV_CAND_0011",
        "M12_DERIV_CAND_0081": "M12_DERIV_CAND_0078",
        "M12_DERIV_CAND_0106": "M12_DERIV_CAND_0103",
        "M12_DERIV_CAND_0109": "M12_DERIV_CAND_0107",
        "M12_DERIV_CAND_0119": "M12_DERIV_CAND_0121",
        "M12_DERIV_CAND_0130": "M12_DERIV_CAND_0132",
    }
    actual_mappings = {
        str(record["candidate_id"]): str(record["duplicate_of_candidate_id"])
        for record in records
    }
    duplicate_ids = set(actual_mappings)

    assert actual_mappings == expected_mappings
    for candidate_id, target_id in actual_mappings.items():
        assert candidate_id != target_id
        assert target_id not in duplicate_ids
        assert target_id in effective_by_id
        candidate = effective_by_id[candidate_id]
        target = effective_by_id[target_id]
        assert candidate["status"] == "REJECTED"
        assert candidate["duplicate_of_candidate_id"] == target_id
        assert target["status"] != "REJECTED"
        assert "duplicate_of_candidate_id" not in target
        target_review = target.get("review_record")
        if isinstance(target_review, dict):
            assert not str(target_review.get("review_status", "")).startswith(
                "REJECTED"
            )
    assert effective_by_id["M12_DERIV_CAND_0121"]["review_record"][
        "review_status"
    ] == "HOLD_SOURCE_ANSWER_CONFLICT"
    assert effective_by_id["M12_DERIV_CAND_0132"]["review_record"][
        "review_status"
    ] == "HOLD_VISUAL_SOURCE_REVIEW"


def test_batch_005_reclassifies_exactly_eight_raw_true_false_records() -> None:
    raw_by_id = {
        str(candidate["candidate_id"]): candidate for candidate in _raw_candidates()
    }
    effective_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in _effective_candidates()
    }
    reclassified_ids = {
        "M12_DERIV_CAND_0002",
        "M12_DERIV_CAND_0005",
        "M12_DERIV_CAND_0011",
        "M12_DERIV_CAND_0023",
        "M12_DERIV_CAND_0028",
        "M12_DERIV_CAND_0034",
        "M12_DERIV_CAND_0037",
        "M12_DERIV_CAND_0051",
    }

    for candidate_id in reclassified_ids:
        assert raw_by_id[candidate_id]["question_type_detected"] == (
            "TRUE_FALSE_GROUP"
        )
        assert effective_by_id[candidate_id]["question_type_detected"] == (
            "TRUE_FALSE_GROUP"
        )
        assert effective_question_type(effective_by_id[candidate_id]) == (
            "MULTIPLE_CHOICE"
        )

    candidate_0034 = effective_by_id["M12_DERIV_CAND_0034"]
    assert candidate_0034["status"] == "VERIFIED"
    assert candidate_0034["verified_correct_answer"] == "B"
    assert candidate_0034["promotion_ready"] is False
    assert candidate_promotion_blockers(candidate_0034) == (
        "EXPLICIT_PROMOTION_REQUIRED",
    )


def test_batch_005_visual_mcq_holds_remain_blocked_without_group_blocker() -> None:
    effective_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in _effective_candidates()
    }
    records = _read_json(FIFTH_REVIEW_BATCH / "hold_candidates.json")
    assert isinstance(records, list)
    expected_ids = {
        "M12_DERIV_CAND_0002",
        "M12_DERIV_CAND_0005",
        "M12_DERIV_CAND_0011",
        "M12_DERIV_CAND_0023",
        "M12_DERIV_CAND_0028",
        "M12_DERIV_CAND_0037",
        "M12_DERIV_CAND_0051",
    }

    assert {str(record["candidate_id"]) for record in records} == expected_ids
    for record in records:
        candidate = effective_by_id[str(record["candidate_id"])]
        assert record["classification_review"] == "CONFIRMED"
        assert record["reviewed_question_type"] == "MULTIPLE_CHOICE"
        assert record["visual_asset_required"] is True
        assert candidate["status"] == "REVIEW_REQUIRED"
        assert "reviewed_question_type" not in candidate
        assert "verified_correct_answer" not in candidate
        blockers = candidate_promotion_blockers(candidate)
        assert "STATUS_HOLD" in blockers
        assert "VISUAL_ASSET_REQUIRED" in blockers
        assert "TRUE_FALSE_GROUP_UNSUPPORTED" not in blockers
    for candidate_id in ("M12_DERIV_CAND_0002", "M12_DERIV_CAND_0005"):
        assert effective_by_id[candidate_id]["review_record"][
            "primary_source_crosscheck_required"
        ] is True


def test_batch_005_duplicate_targets_are_direct_retained_candidates() -> None:
    effective_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in _effective_candidates()
    }
    records = _read_json(FIFTH_REVIEW_BATCH / "rejected_candidates.json")
    assert isinstance(records, list)
    expected_mappings = {
        "M12_DERIV_CAND_0016": "M12_DERIV_CAND_0012",
        "M12_DERIV_CAND_0029": "M12_DERIV_CAND_0031",
        "M12_DERIV_CAND_0039": "M12_DERIV_CAND_0041",
        "M12_DERIV_CAND_0064": "M12_DERIV_CAND_0062",
        "M12_DERIV_CAND_0067": "M12_DERIV_CAND_0068",
        "M12_DERIV_CAND_0142": "M12_DERIV_CAND_0141",
    }
    actual_mappings = {
        str(record["candidate_id"]): str(record["duplicate_of_candidate_id"])
        for record in records
    }
    duplicate_ids = set(actual_mappings)

    assert actual_mappings == expected_mappings
    for candidate_id, target_id in actual_mappings.items():
        assert target_id in effective_by_id
        assert target_id != candidate_id
        assert target_id not in duplicate_ids
        candidate = effective_by_id[candidate_id]
        target = effective_by_id[target_id]
        assert candidate["status"] == "REJECTED"
        assert candidate["duplicate_of_candidate_id"] == target_id
        assert target["status"] != "REJECTED"
        assert "duplicate_of_candidate_id" not in target


@pytest.mark.parametrize("location", ["review_record", "candidate_patch"])
def test_invalid_reviewed_question_type_fails_review_validation(
    tmp_path: Path,
    location: str,
) -> None:
    staging_path, _ = _copy_derivative_data(tmp_path)
    batch_path = staging_path.parent / "review" / "batch_005"
    if location == "review_record":
        records = _read_json(batch_path / "hold_candidates.json")
        assert isinstance(records, list) and isinstance(records[0], dict)
        records[0]["reviewed_question_type"] = "INVALID_TYPE"
        _write_json(batch_path / "hold_candidates.json", records)
    else:
        patches = _read_json(batch_path / "candidate_patch.json")
        assert isinstance(patches, list) and isinstance(patches[0], dict)
        assert isinstance(patches[0].get("set"), dict)
        patches[0]["set"]["reviewed_question_type"] = "INVALID_TYPE"
        _write_json(batch_path / "candidate_patch.json", patches)

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "INVALID_REVIEWED_QUESTION_TYPE" in {
        issue.code for issue in result.report.errors
    }


def test_verified_review_and_patch_question_types_must_agree(tmp_path: Path) -> None:
    staging_path, _ = _copy_derivative_data(tmp_path)
    batch_path = staging_path.parent / "review" / "batch_005"
    patches = _read_json(batch_path / "candidate_patch.json")
    assert isinstance(patches, list) and isinstance(patches[0], dict)
    assert isinstance(patches[0].get("set"), dict)
    patches[0]["set"]["reviewed_question_type"] = "SHORT_ANSWER"
    _write_json(batch_path / "candidate_patch.json", patches)

    result = QuestionReviewOverlayResolver().resolve(
        _raw_candidates(staging_path), batch_path
    )

    assert result.report.status == "FAIL"
    assert "PATCH_REVIEW_MISMATCH" in {
        issue.code for issue in result.report.errors
    }


def test_review_batch_candidate_ids_do_not_overlap() -> None:
    raw = _raw_candidates()
    reviewed_ids: set[str] = set()
    for batch_path in REVIEW_BATCHES:
        result = QuestionReviewOverlayResolver().resolve(raw, batch_path)
        batch_ids = set(result.report.reviewed_candidate_ids)
        assert reviewed_ids.isdisjoint(batch_ids)
        reviewed_ids.update(batch_ids)

    assert len(reviewed_ids) == 112


def test_validator_rejects_candidate_reviewed_by_multiple_batches(
    tmp_path: Path,
) -> None:
    staging_path, _ = _copy_derivative_data(tmp_path)
    batch_path = staging_path.parent / "review" / "batch_002"
    holds = _read_json(batch_path / "hold_candidates.json")
    assert isinstance(holds, list) and isinstance(holds[0], dict)
    holds[0]["candidate_id"] = "M12_DERIV_CAND_0063"
    _write_json(batch_path / "hold_candidates.json", holds)

    report = QuestionStagingValidator().validate(
        staging_path,
        review_root=staging_path.parent / "review",
    )

    assert report.status == "FAIL"
    assert report.checks["review_batch_overlap"] is False
    assert "CANDIDATE_REVIEW_BATCH_OVERLAP" in {
        error.code for error in report.errors
    }


def test_review_overlay_failure_is_reported_at_top_level(tmp_path: Path) -> None:
    staging_path, batch_path = _copied_batch_002(tmp_path)
    holds = _read_json(batch_path / "hold_candidates.json")
    assert isinstance(holds, list) and isinstance(holds[0], dict)
    holds[0]["candidate_id"] = "M12_DERIV_CAND_UNKNOWN"
    _write_json(batch_path / "hold_candidates.json", holds)

    report = QuestionStagingValidator().validate(
        staging_path,
        review_root=staging_path.parent / "review",
    )

    assert report.status == "FAIL"
    assert report.checks["review_overlays"] is False
    top_level_errors = [
        error for error in report.errors if error.code == "CANDIDATE_NOT_FOUND"
    ]
    assert len(top_level_errors) == 1
    error = top_level_errors[0]
    assert error.location == "batch_002/M12_DERIV_CAND_UNKNOWN"
    assert batch_path.resolve().as_posix() in error.message
    assert "candidate_id=M12_DERIV_CAND_UNKNOWN" in error.message
    batch_report = next(
        batch
        for batch in report.review_batches
        if batch.batch_code == "DATA-MATH12-005_BATCH_002"
    )
    assert "CANDIDATE_NOT_FOUND" in {
        nested_error.code for nested_error in batch_report.errors
    }
