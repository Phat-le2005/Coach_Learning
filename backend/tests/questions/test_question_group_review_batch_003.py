from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

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


BATCH_PATH = DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_003"
EXPECTED_PATTERNS = {
    "M12_DERIV_GROUP_0089": ("FALSE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0091": ("TRUE", "FALSE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0094": ("TRUE", "FALSE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0096": ("TRUE", "FALSE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0099": ("TRUE", "FALSE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0101": ("TRUE", "TRUE", "FALSE", "FALSE"),
    "M12_DERIV_GROUP_0113": ("FALSE", "FALSE", "TRUE", "TRUE"),
}
EXPECTED_CONFLICT_LABELS = {
    "M12_DERIV_GROUP_0104": ("d",),
    "M12_DERIV_GROUP_0108": ("a", "b", "c"),
    "M12_DERIV_GROUP_0111": ("c", "d"),
}
EXPECTED_DUPLICATES = {
    "M12_DERIV_GROUP_0114": "M12_DERIV_GROUP_0113",
}
EXPECTED_OUT_OF_SCOPE = {"M12_DERIV_GROUP_0105"}
EXPECTED_VISUAL_GROUPS = {
    "M12_DERIV_GROUP_0089",
    "M12_DERIV_GROUP_0113",
}
EXPECTED_TARGET_IDS = (
    set(EXPECTED_PATTERNS)
    | set(EXPECTED_CONFLICT_LABELS)
    | set(EXPECTED_DUPLICATES)
    | EXPECTED_OUT_OF_SCOPE
)


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def test_batch_003_has_exact_ids_counts_and_no_prior_overlap() -> None:
    report = QuestionGroupReviewValidator().validate()
    batch_report = report.review_batches[2]

    assert report.is_valid
    assert batch_report["batch_code"] == "DATA-MATH12-008_BATCH_003"
    assert batch_report["counts"] == {
        "reviewed": 12,
        "verified": 7,
        "hold": 3,
        "rejected": 2,
    }
    assert set(batch_report["reviewed_group_ids"]) == EXPECTED_TARGET_IDS
    prior_ids = _review_ids(DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_001")
    prior_ids |= _review_ids(DEFAULT_QUESTION_GROUP_REVIEW_ROOT / "batch_002")
    assert prior_ids.isdisjoint(_review_ids(BATCH_PATH))


def test_batch_003_verified_patterns_visual_flags_and_promotion_boundary() -> None:
    effective = _effective_by_id()
    patterns: dict[str, tuple[str, ...]] = {}
    visual_groups: set[str] = set()

    for group_id in EXPECTED_PATTERNS:
        group = effective[group_id]
        record = group["academic_review_record"]
        patterns[group_id] = tuple(
            str(item["correct_answer"]) for item in record["items"]
        )
        assert [item["label"] for item in record["items"]] == ["a", "b", "c", "d"]
        assert [item["order_index"] for item in record["items"]] == [0, 1, 2, 3]
        assert record["answer_verification"] == (
            "SOURCE_BACKED_AND_REVIEW_CONSISTENT"
        )
        assert record["taxonomy_basis"] == "COACH_LEARNING_DERIVED"
        assert group["promotion_ready"] is False
        if record["visual_asset_required"] is True:
            visual_groups.add(group_id)

    assert patterns == EXPECTED_PATTERNS
    assert visual_groups == EXPECTED_VISUAL_GROUPS


def test_batch_003_conflict_holds_preserve_metadata_without_trusted_answers() -> None:
    effective = _effective_by_id()

    for group_id, labels in EXPECTED_CONFLICT_LABELS.items():
        group = effective[group_id]
        record = group["academic_review_record"]
        evidence = group["source_evidence"]
        implied = record["independent_check"]["implied_answer_by_review"]

        assert record["review_status"] == "HOLD_SOURCE_ANSWER_CONFLICT"
        assert tuple(record["conflicting_item_labels"]) == labels
        assert record["conflicting_item_label"] in labels
        assert set(implied) == set(labels)
        assert set(implied.values()) <= {"TRUE", "FALSE"}
        assert record["trusted_correct_answer"] is None
        assert record["source_claimed_answer_pattern"] == evidence[
            "source_claimed_answer_pattern"
        ]
        assert group["promotion_ready"] is False


def test_batch_003_rejections_are_exact_and_excluded_from_usable_view() -> None:
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
        assert group_id not in usable_ids
    for group_id in EXPECTED_OUT_OF_SCOPE:
        assert effective[group_id]["academic_review_status"] == (
            "REJECTED_OUT_OF_SCOPE"
        )
        assert group_id not in usable_ids


def test_three_batch_materialization_is_deterministic_and_cumulative() -> None:
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
    ]
    report = QuestionGroupReviewValidator().validate()
    assert report.counts == {
        "structural_groups": 67,
        "structural_holds": 1,
        "review_batches": 3,
        "target_groups": 37,
        "reviewed_groups": 37,
        "verified": 19,
        "hold": 8,
        "rejected": 10,
        "rejected_duplicate": 4,
        "rejected_out_of_scope": 6,
        "verified_child_statements": 76,
        "assigned_child_answers": 76,
        "visual_asset_required": 6,
        "promotion_ready": 0,
        "effective_usable_groups": 57,
    }


def test_batch_003_keeps_raw_and_data_006_invariants() -> None:
    raw_path = DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "candidate_questions.json"
    raw_before = raw_path.read_bytes()
    structural_before = (
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    ).read_bytes()

    report = QuestionGroupStagingValidator().validate()
    QuestionGroupReviewValidator().validate()

    assert hashlib.sha256(raw_before).hexdigest() == EXPECTED_RAW_CANDIDATE_SHA256
    assert raw_path.read_bytes() == raw_before
    assert (
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    ).read_bytes() == structural_before
    assert report.status == "PASS"
    assert report.counts == {
        "groups": 67,
        "structural_holds": 1,
        "child_statements": 268,
        "assigned_child_answers": 0,
    }


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ({"conflicting_item_labels": []}, "CONFLICTING_ITEM_LABELS_INVALID"),
        ({"conflicting_item_labels": ["a", "a"]}, "CONFLICTING_ITEM_LABELS_INVALID"),
        (
            {"conflicting_item_label": "d", "conflicting_item_labels": ["a"]},
            "CONFLICTING_ITEM_LABEL_INCONSISTENT",
        ),
    ],
)
def test_conflicting_item_labels_shape_is_validated(
    tmp_path: Path,
    mutation: dict[str, object],
    error_code: str,
) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    path = review_root / "batch_003" / "hold_groups.json"
    holds = _load(path)
    assert isinstance(holds, list)
    holds[0].update(mutation)
    _write(path, holds)

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert error_code in {error.code for error in report.errors}


def test_implied_answers_are_review_metadata_and_must_match_conflict_labels(
    tmp_path: Path,
) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    path = review_root / "batch_003" / "hold_groups.json"
    holds = _load(path)
    assert isinstance(holds, list)
    holds[1]["independent_check"]["implied_answer_by_review"].pop("b")
    _write(path, holds)

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert "INDEPENDENT_CONFLICT_ANSWERS_INVALID" in {
        error.code for error in report.errors
    }
