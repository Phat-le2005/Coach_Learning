from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    EffectiveQuestionGroupReviewMaterializer,
)
from app.questions.question_group_review_validator import (
    QuestionGroupReviewValidator,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_staging_validator import (
    QuestionGroupStagingValidator,
)


BATCH_PATH = DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_004"
EXPECTED_SOURCE_PDF_SHA256 = (
    "15579d487c6ad6cdd6386c96ac829c48710c3ca66104acfbd0fc9e9183b586b4"
)
EXPECTED_PATTERNS = {
    "M12_DERIV_GROUP_0116": ("TRUE", "TRUE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0120": ("TRUE", "TRUE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0124": ("TRUE", "TRUE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0126": ("TRUE", "FALSE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0131": ("FALSE", "TRUE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0134": ("FALSE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0136": ("TRUE", "TRUE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0141": ("FALSE", "TRUE", "FALSE", "TRUE"),
}
EXPECTED_HOLD_ID = "M12_DERIV_GROUP_0138"
EXPECTED_DUPLICATES = {
    "M12_DERIV_GROUP_0118": "M12_DERIV_GROUP_0116",
    "M12_DERIV_GROUP_0122": "M12_DERIV_GROUP_0120",
    "M12_DERIV_GROUP_0127": "M12_DERIV_GROUP_0126",
}
EXPECTED_OUT_OF_SCOPE = {"M12_DERIV_GROUP_0139"}
EXPECTED_TARGET_IDS = (
    set(EXPECTED_PATTERNS)
    | {EXPECTED_HOLD_ID}
    | set(EXPECTED_DUPLICATES)
    | EXPECTED_OUT_OF_SCOPE
)


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _review_ids(batch_path: Path) -> set[str]:
    return {
        str(record["group_candidate_id"])
        for name in ("verified_groups.json", "hold_groups.json", "rejected_groups.json")
        for record in _load(batch_path / name)
    }


def _effective_by_id() -> dict[str, dict[str, object]]:
    groups = _load(
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    )
    assert isinstance(groups, list)
    materialization = EffectiveQuestionGroupReviewMaterializer().materialize(groups)
    assert materialization.is_valid
    return {
        str(group["group_candidate_id"]): group
        for group in materialization.effective_groups
    }


def test_batch_004_has_exact_ids_counts_metadata_and_no_prior_overlap() -> None:
    report = QuestionGroupReviewValidator().validate()
    batch_report = report.review_batches[3]
    stats = _load(BATCH_PATH / "review_stats.json")
    metadata = _load(BATCH_PATH / "source_metadata.json")
    assert isinstance(stats, dict) and isinstance(metadata, dict)

    assert report.is_valid
    assert batch_report["batch_code"] == "DATA-MATH12-008_BATCH_004"
    assert batch_report["counts"] == {
        "reviewed": 13,
        "verified": 8,
        "hold": 1,
        "rejected": 4,
    }
    assert set(batch_report["reviewed_group_ids"]) == EXPECTED_TARGET_IDS
    prior_ids = set().union(
        *(
            _review_ids(DEFAULT_QUESTION_GROUP_REVIEW_ROOT / f"batch_{index:03d}")
            for index in range(1, 4)
        )
    )
    assert prior_ids.isdisjoint(_review_ids(BATCH_PATH))
    assert stats["rejected_duplicate"] == 3
    assert stats["rejected_out_of_scope"] == 1
    assert stats["verified_child_statements"] == 32
    assert stats["assigned_child_answers"] == 32
    assert stats["visual_asset_required"] == 0
    assert stats["promotion_ready"] == 0
    assert stats["source_pdf_sha256"] == EXPECTED_SOURCE_PDF_SHA256
    assert metadata["source_pdf_sha256"] == EXPECTED_SOURCE_PDF_SHA256


def test_batch_004_verified_patterns_are_exact_and_non_promotable() -> None:
    effective = _effective_by_id()
    observed: dict[str, tuple[str, ...]] = {}

    for group_id in EXPECTED_PATTERNS:
        group = effective[group_id]
        record = group["academic_review_record"]
        items = record["items"]
        observed[group_id] = tuple(str(item["correct_answer"]) for item in items)
        assert [item["label"] for item in items] == ["a", "b", "c", "d"]
        assert [item["order_index"] for item in items] == [0, 1, 2, 3]
        assert record["answer_verification"] == (
            "SOURCE_BACKED_AND_REVIEW_CONSISTENT"
        )
        assert record["taxonomy_basis"] == "COACH_LEARNING_DERIVED"
        assert record["visual_asset_required"] is False
        assert group["promotion_ready"] is False

    assert observed == EXPECTED_PATTERNS


def test_batch_004_hold_preserves_conflict_metadata_without_trusted_answers() -> None:
    group = _effective_by_id()[EXPECTED_HOLD_ID]
    record = group["academic_review_record"]
    evidence = group["source_evidence"]

    assert record["review_status"] == "HOLD_SOURCE_ANSWER_CONFLICT"
    assert record["source_claimed_answer_pattern"] == [
        "FALSE",
        "FALSE",
        "TRUE",
        "FALSE",
    ]
    assert record["source_claimed_answer_pattern"] == evidence[
        "source_claimed_answer_pattern"
    ]
    assert record["conflicting_item_label"] == "c"
    assert record["conflicting_item_labels"] == ["c", "d"]
    assert record["independent_check"]["implied_answer_by_review"] == {
        "c": "FALSE",
        "d": "TRUE",
    }
    assert record["trusted_correct_answer"] is None
    assert group["promotion_ready"] is False


def test_batch_004_rejections_are_exact_and_excluded_from_usable_view() -> None:
    report = QuestionGroupReviewValidator().validate()
    effective = {
        str(group["group_candidate_id"]): group
        for group in report.materialization.effective_groups
    }
    usable_ids = {
        str(group["group_candidate_id"])
        for group in report.materialization.effective_usable_groups
    }

    for group_id, target in EXPECTED_DUPLICATES.items():
        record = effective[group_id]["academic_review_record"]
        assert record["review_status"] == "REJECTED_DUPLICATE_GROUP"
        assert record["duplicate_of_group_candidate_id"] == target
        assert target in effective
        assert not str(effective[target]["academic_review_status"]).startswith(
            "REJECTED_"
        )
        assert group_id not in usable_ids
    for group_id in EXPECTED_OUT_OF_SCOPE:
        assert effective[group_id]["academic_review_status"] == (
            "REJECTED_OUT_OF_SCOPE"
        )
        assert group_id not in usable_ids


def test_four_batch_materialization_is_deterministic_and_cumulative() -> None:
    groups = _load(
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    )
    assert isinstance(groups, list)
    materializer = EffectiveQuestionGroupReviewMaterializer()
    first = materializer.materialize(groups)
    second = materializer.materialize(groups)

    assert first.is_valid and second.is_valid
    assert first.effective_groups == second.effective_groups
    assert [batch.batch_code for batch in first.review_batches] == [
        "DATA-MATH12-007_BATCH_001",
        "DATA-MATH12-008_BATCH_002",
        "DATA-MATH12-008_BATCH_003",
        "DATA-MATH12-008_BATCH_004",
    ]
    report = QuestionGroupReviewValidator().validate()
    assert report.counts == {
        "structural_groups": 67,
        "structural_holds": 1,
        "review_batches": 4,
        "target_groups": 50,
        "reviewed_groups": 50,
        "verified": 27,
        "hold": 9,
        "rejected": 14,
        "rejected_duplicate": 7,
        "rejected_out_of_scope": 7,
        "verified_child_statements": 108,
        "assigned_child_answers": 108,
        "visual_asset_required": 6,
        "promotion_ready": 0,
        "effective_usable_groups": 53,
    }


def test_batch_004_keeps_raw_and_data_006_staging_immutable() -> None:
    raw_path = DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "candidate_questions.json"
    group_path = DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    raw_before = raw_path.read_bytes()
    groups_before = group_path.read_bytes()

    structural_report = QuestionGroupStagingValidator().validate()
    review_report = QuestionGroupReviewValidator().validate()

    assert hashlib.sha256(raw_before).hexdigest() == EXPECTED_RAW_CANDIDATE_SHA256
    assert raw_path.read_bytes() == raw_before
    assert group_path.read_bytes() == groups_before
    assert structural_report.status == "PASS"
    assert structural_report.counts == {
        "groups": 67,
        "structural_holds": 1,
        "child_statements": 268,
        "assigned_child_answers": 0,
    }
    assert review_report.counts["promotion_ready"] == 0
