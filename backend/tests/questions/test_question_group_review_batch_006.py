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


BATCH_PATH = DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_006"
EXPECTED_PATTERNS = {
    "M12_DERIV_GROUP_0001": ("TRUE", "FALSE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0004": ("TRUE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0006": ("TRUE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0008": ("TRUE", "FALSE", "FALSE", "FALSE"),
}


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


def test_batch_006_has_exact_ids_counts_and_no_prior_overlap() -> None:
    report = QuestionGroupReviewValidator().validate()
    batch_report = report.review_batches[5]
    stats = _load(BATCH_PATH / "review_stats.json")
    assert isinstance(stats, dict)

    assert report.is_valid
    assert batch_report["batch_code"] == "DATA-MATH12-009_BATCH_006"
    assert batch_report["counts"] == {
        "reviewed": 4,
        "verified": 4,
        "hold": 0,
        "rejected": 0,
    }
    assert set(batch_report["reviewed_group_ids"]) == set(EXPECTED_PATTERNS)
    prior_ids = set().union(
        *(
            _review_ids(DEFAULT_QUESTION_GROUP_REVIEW_ROOT / f"batch_{index:03d}")
            for index in range(1, 6)
        )
    )
    assert prior_ids.isdisjoint(_review_ids(BATCH_PATH))
    assert stats["verified_child_statements"] == 16
    assert stats["assigned_child_answers"] == 16
    assert stats["visual_asset_required"] == 0
    assert stats["promotion_ready"] == 0


def test_batch_006_patterns_crosschecks_and_non_promotion_are_exact() -> None:
    effective = _effective_by_id()
    observed: dict[str, tuple[str, ...]] = {}

    for group_id, expected_pattern in EXPECTED_PATTERNS.items():
        group = effective[group_id]
        record = group["academic_review_record"]
        evidence = group["source_evidence"]
        items = record["items"]
        pattern = tuple(str(item["correct_answer"]) for item in items)
        observed[group_id] = pattern

        assert record["review_status"] == "VERIFIED"
        assert [item["label"] for item in items] == ["a", "b", "c", "d"]
        assert [item["order_index"] for item in items] == [0, 1, 2, 3]
        assert record["visual_asset_required"] is False
        assert group["promotion_ready"] is False
        assert tuple(evidence["source_claimed_answer_pattern"]) == expected_pattern
        crosscheck = evidence["primary_crosscheck"]
        assert tuple(crosscheck["official_answer_pattern"]) == expected_pattern
        assert crosscheck["official_answer_exam_code"]
        assert crosscheck["official_answer_row"]

    assert observed == EXPECTED_PATTERNS


def test_group_0008_keeps_null_structure_with_canonical_103_only_in_evidence() -> None:
    group = _effective_by_id()["M12_DERIV_GROUP_0008"]
    record = group["academic_review_record"]
    evidence = group["source_evidence"]

    assert group["raw_subsource_code"] is None
    assert group["effective_subsource_code"] is None
    assert group["source_page"] == 53
    assert record["raw_subsource_code"] is None
    assert record["effective_subsource_code"] is None
    assert record["candidate_extraction_page"] == 53
    assert evidence["effective_subsource_code"] is None
    assert evidence["candidate_extraction_page"] == 53
    assert evidence["canonical_subsource_code"] == "MOET_2025_103"
    assert evidence["canonical_question_pages"] == [14, 15]
    assert evidence["solution_pages"] == [53]
    assert evidence["primary_crosscheck"]["official_answer_exam_code"] == "0103"


def test_six_batch_materialization_is_deterministic_and_cumulative() -> None:
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


def test_batch_006_keeps_raw_and_data_006_staging_immutable() -> None:
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
