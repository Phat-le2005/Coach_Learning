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


BATCH_PATH = DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_005"
EXPECTED_SOURCE_PDF_SHA256 = (
    "15579d487c6ad6cdd6386c96ac829c48710c3ca66104acfbd0fc9e9183b586b4"
)
EXPECTED_PATTERNS = {
    "M12_DERIV_GROUP_0143": ("FALSE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0147": ("TRUE", "TRUE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0150": ("TRUE", "FALSE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0154": ("FALSE", "TRUE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0163": ("TRUE", "TRUE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0165": ("FALSE", "TRUE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0170": ("TRUE", "TRUE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0174": ("FALSE", "FALSE", "TRUE", "TRUE"),
}
EXPECTED_VISUAL_GROUPS = {
    "M12_DERIV_GROUP_0154",
    "M12_DERIV_GROUP_0163",
    "M12_DERIV_GROUP_0170",
}
EXPECTED_HOLD_ID = "M12_DERIV_GROUP_0159"
EXPECTED_DUPLICATES = {
    "M12_DERIV_GROUP_0155": "M12_DERIV_GROUP_0154",
    "M12_DERIV_GROUP_0175": "M12_DERIV_GROUP_0174",
}
EXPECTED_OUT_OF_SCOPE = {
    "M12_DERIV_GROUP_0144",
    "M12_DERIV_GROUP_0145",
}
EXPECTED_TARGET_IDS = (
    set(EXPECTED_PATTERNS)
    | EXPECTED_VISUAL_GROUPS
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


def test_batch_005_has_exact_ids_counts_metadata_and_no_prior_overlap() -> None:
    report = QuestionGroupReviewValidator().validate()
    batch_report = report.review_batches[4]
    stats = _load(BATCH_PATH / "review_stats.json")
    metadata = _load(BATCH_PATH / "source_metadata.json")
    assert isinstance(stats, dict) and isinstance(metadata, dict)

    assert report.is_valid
    assert batch_report["batch_code"] == "DATA-MATH12-008_BATCH_005"
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
            for index in range(1, 5)
        )
    )
    assert prior_ids.isdisjoint(_review_ids(BATCH_PATH))
    assert stats["rejected_duplicate"] == 2
    assert stats["rejected_out_of_scope"] == 2
    assert stats["verified_child_statements"] == 32
    assert stats["assigned_child_answers"] == 32
    assert stats["visual_asset_required"] == 3
    assert stats["promotion_ready"] == 0
    assert stats["source_pdf_sha256"] == EXPECTED_SOURCE_PDF_SHA256
    assert metadata["source_pdf_sha256"] == EXPECTED_SOURCE_PDF_SHA256


def test_batch_005_verified_patterns_visual_flags_and_non_promotion_are_exact() -> None:
    effective = _effective_by_id()
    observed: dict[str, tuple[str, ...]] = {}
    visual_groups: set[str] = set()

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
        assert group["promotion_ready"] is False
        if record["visual_asset_required"] is True:
            visual_groups.add(group_id)

    assert observed == EXPECTED_PATTERNS
    assert visual_groups == EXPECTED_VISUAL_GROUPS


def test_batch_005_hold_keeps_conflict_item_without_trusted_answer() -> None:
    group = _effective_by_id()[EXPECTED_HOLD_ID]
    record = group["academic_review_record"]
    evidence = group["source_evidence"]

    assert record["review_status"] == "HOLD_SOURCE_ANSWER_CONFLICT"
    assert record["source_claimed_answer_pattern"] == [
        "TRUE",
        "FALSE",
        "FALSE",
        "TRUE",
    ]
    assert record["source_claimed_answer_pattern"] == evidence[
        "source_claimed_answer_pattern"
    ]
    assert record["conflicting_item_label"] == "a"
    assert record["conflicting_item_labels"] == ["a"]
    assert record["independent_check"]["implied_answer_by_review"] == {
        "a": "FALSE"
    }
    assert record["trusted_correct_answer"] is None
    assert all(
        item.get("correct_answer") is None
        for item in group["items"]
        if item["label"] == "a"
    )
    assert group["promotion_ready"] is False


def test_batch_005_rejections_are_exact_and_excluded_from_usable_view() -> None:
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
        record = effective[group_id]["academic_review_record"]
        assert record["review_status"] == "REJECTED_OUT_OF_SCOPE"
        assert record.get("duplicate_of_group_candidate_id") is None
        assert group_id not in usable_ids
    assert effective["M12_DERIV_GROUP_0145"]["academic_review_status"] == (
        "REJECTED_OUT_OF_SCOPE"
    )


def test_group_0163_preserves_structural_and_canonical_page_provenance() -> None:
    group = _effective_by_id()["M12_DERIV_GROUP_0163"]
    record = group["academic_review_record"]
    evidence = group["source_evidence"]

    assert group["source_page"] == 708
    assert record["candidate_extraction_page"] == 708
    assert evidence["candidate_extraction_page"] == 708
    assert evidence["canonical_question_pages"] == [700, 701]
    assert evidence["solution_pages"] == [708, 709]


def test_five_batch_materialization_is_deterministic_and_cumulative() -> None:
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
        "DATA-MATH12-008_BATCH_005",
        "DATA-MATH12-009_BATCH_006",
    ]
    report = QuestionGroupReviewValidator().validate()
    assert report.counts == {
        "structural_groups": 67,
        "structural_holds": 1,
        "review_batches": 6,
        "target_groups": 67,
        "reviewed_groups": 67,
        "verified": 39,
        "hold": 10,
        "rejected": 18,
        "rejected_duplicate": 9,
        "rejected_out_of_scope": 9,
        "verified_child_statements": 156,
        "assigned_child_answers": 156,
        "visual_asset_required": 9,
        "promotion_ready": 0,
        "effective_usable_groups": 49,
    }


def test_batch_005_keeps_raw_and_data_006_staging_immutable() -> None:
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
