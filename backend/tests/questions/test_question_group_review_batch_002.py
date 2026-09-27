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


BATCH_PATH = DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_002"
EXPECTED_PATTERNS = {
    "M12_DERIV_GROUP_0058": ("TRUE", "FALSE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0066": ("FALSE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0070": ("FALSE", "TRUE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0079": ("TRUE", "FALSE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0087": ("TRUE", "FALSE", "FALSE", "TRUE"),
}
EXPECTED_CONFLICT_LABELS = {
    "M12_DERIV_GROUP_0062": "b",
    "M12_DERIV_GROUP_0072": "c",
    "M12_DERIV_GROUP_0076": "c",
    "M12_DERIV_GROUP_0084": "d",
}
EXPECTED_OUT_OF_SCOPE = {
    "M12_DERIV_GROUP_0068",
    "M12_DERIV_GROUP_0073",
    "M12_DERIV_GROUP_0082",
}
EXPECTED_VISUAL_GROUPS = {
    "M12_DERIV_GROUP_0070",
    "M12_DERIV_GROUP_0087",
}
EXPECTED_TARGET_IDS = (
    set(EXPECTED_PATTERNS)
    | set(EXPECTED_CONFLICT_LABELS)
    | EXPECTED_OUT_OF_SCOPE
)


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _review_ids(batch_path: Path) -> set[str]:
    return {
        str(record["group_candidate_id"])
        for name in ("verified_groups.json", "hold_groups.json", "rejected_groups.json")
        for record in _load(batch_path / name)
    }


def test_batch_002_has_exact_ids_counts_and_no_batch_001_overlap() -> None:
    report = QuestionGroupReviewValidator().validate()
    batch_report = report.review_batches[1]

    assert report.is_valid
    assert batch_report["batch_code"] == "DATA-MATH12-008_BATCH_002"
    assert batch_report["counts"] == {
        "reviewed": 12,
        "verified": 5,
        "hold": 4,
        "rejected": 3,
    }
    assert set(batch_report["reviewed_group_ids"]) == EXPECTED_TARGET_IDS
    assert _review_ids(DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_001").isdisjoint(
        _review_ids(BATCH_PATH)
    )


def test_batch_002_verified_patterns_and_visual_flags_are_exact() -> None:
    effective = _effective_by_id()
    patterns: dict[str, tuple[str, ...]] = {}
    visual_groups: set[str] = set()

    for group_id in EXPECTED_PATTERNS:
        record = effective[group_id]["academic_review_record"]
        patterns[group_id] = tuple(
            str(item["correct_answer"]) for item in record["items"]
        )
        assert record["answer_verification"] == (
            "SOURCE_BACKED_AND_REVIEW_CONSISTENT"
        )
        assert effective[group_id]["promotion_ready"] is False
        if record["visual_asset_required"] is True:
            visual_groups.add(group_id)

    assert patterns == EXPECTED_PATTERNS
    assert visual_groups == EXPECTED_VISUAL_GROUPS


def test_batch_002_conflict_holds_keep_claimed_pattern_without_trusted_answer() -> None:
    effective = _effective_by_id()

    for group_id, label in EXPECTED_CONFLICT_LABELS.items():
        group = effective[group_id]
        record = group["academic_review_record"]
        evidence = group["source_evidence"]
        assert record["review_status"] == "HOLD_SOURCE_ANSWER_CONFLICT"
        assert record["conflicting_item_label"] == label
        assert record["trusted_correct_answer"] is None
        assert record["source_claimed_answer_pattern"] == evidence[
            "source_claimed_answer_pattern"
        ]
        assert evidence["review_consistency"] == "SOURCE_ANSWER_CONFLICT"
        assert record["conflict_explanation"]
        assert record["independent_check"]["provenance_type"] == (
            "INDEPENDENT_REVIEW_CHECK"
        )
        assert group["promotion_ready"] is False


def test_batch_002_out_of_scope_groups_are_excluded_from_usable_view() -> None:
    report = QuestionGroupReviewValidator().validate()
    effective = {
        str(group["group_candidate_id"]): group
        for group in report.materialization.effective_groups
    }
    usable_ids = {
        str(group["group_candidate_id"])
        for group in report.materialization.effective_usable_groups
    }

    for group_id in EXPECTED_OUT_OF_SCOPE:
        assert effective[group_id]["academic_review_status"] == (
            "REJECTED_OUT_OF_SCOPE"
        )
        assert group_id not in usable_ids


def test_review_materialization_is_deterministic_and_lexical() -> None:
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
    assert not first.issues


def test_batch_002_keeps_raw_and_data_006_invariants() -> None:
    raw_path = DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "candidate_questions.json"
    raw_before = raw_path.read_bytes()

    report = QuestionGroupStagingValidator().validate()
    QuestionGroupReviewValidator().validate()

    assert hashlib.sha256(raw_before).hexdigest() == EXPECTED_RAW_CANDIDATE_SHA256
    assert raw_path.read_bytes() == raw_before
    assert report.status == "PASS"
    assert report.counts == {
        "groups": 67,
        "structural_holds": 1,
        "child_statements": 268,
        "assigned_child_answers": 0,
    }
