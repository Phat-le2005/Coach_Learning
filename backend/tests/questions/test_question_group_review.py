from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.questions.models import QuestionGroup, QuestionGroupItem
from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    EffectiveQuestionGroupReviewMaterializer,
)
from app.questions.question_group_review_validator import (
    EXPECTED_ANSWER_PATTERNS,
    EXPECTED_DUPLICATES,
    EXPECTED_OUT_OF_SCOPE,
    EXPECTED_TARGET_IDS,
    EXPECTED_VISUAL_GROUPS,
    QuestionGroupReviewValidator,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_staging_validator import (
    QuestionGroupStagingValidator,
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


def test_group_review_batch_001_passes_with_exact_acceptance_counts() -> None:
    report = QuestionGroupReviewValidator().validate()

    assert report.status == "PASS"
    assert all(report.checks.values())
    assert report.errors == ()
    assert report.counts == {
        "structural_groups": 67,
        "structural_holds": 1,
        "review_batches": 1,
        "target_groups": 13,
        "reviewed_groups": 13,
        "verified": 8,
        "hold": 0,
        "rejected": 5,
        "rejected_duplicate": 3,
        "rejected_out_of_scope": 2,
        "verified_child_statements": 32,
        "assigned_child_answers": 32,
        "visual_asset_required": 2,
        "promotion_ready": 0,
        "effective_usable_groups": 62,
    }
    assert set(report.review_batches[0]["reviewed_group_ids"]) == EXPECTED_TARGET_IDS


def test_verified_answer_patterns_visual_flags_and_promotion_boundary() -> None:
    effective = _effective_by_id()
    observed_patterns: dict[str, tuple[str, ...]] = {}
    visual_ids: set[str] = set()

    for group_id in EXPECTED_ANSWER_PATTERNS:
        group = effective[group_id]
        record = group["academic_review_record"]
        assert isinstance(record, dict)
        items = record["items"]
        assert isinstance(items, list)
        observed_patterns[group_id] = tuple(
            str(item["correct_answer"]) for item in items
        )
        assert [item["label"] for item in items] == ["a", "b", "c", "d"]
        assert [item["order_index"] for item in items] == [0, 1, 2, 3]
        assert record["answer_verification"] == "SOURCE_BACKED"
        assert record["taxonomy_basis"] == "COACH_LEARNING_DERIVED"
        assert group["promotion_ready"] is False
        if record["visual_asset_required"] is True:
            visual_ids.add(group_id)

    assert observed_patterns == EXPECTED_ANSWER_PATTERNS
    assert visual_ids == EXPECTED_VISUAL_GROUPS


def test_rejection_mappings_and_effective_usable_view() -> None:
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
        assert target not in EXPECTED_DUPLICATES
        assert group_id not in usable_ids
    for group_id in EXPECTED_OUT_OF_SCOPE:
        assert effective[group_id]["academic_review_status"] == "REJECTED_OUT_OF_SCOPE"
        assert group_id not in usable_ids


def test_group_0031_preserves_raw_and_effective_provenance() -> None:
    group = _effective_by_id()["M12_DERIV_GROUP_0031"]
    record = group["academic_review_record"]

    assert group["raw_subsource_code"] == "HA_TINH_2025"
    assert group["effective_subsource_code"] == "HUNG_YEN_2025"
    assert group["provenance_correction_code"] == (
        "PROV_CORR_HUNG_YEN_2025_PAGE_BOUNDARY"
    )
    assert record["raw_subsource_code"] == "HA_TINH_2025"
    assert record["effective_subsource_code"] == "HUNG_YEN_2025"
    assert record["provenance_correction_code"] == (
        "PROV_CORR_HUNG_YEN_2025_PAGE_BOUNDARY"
    )


def test_reviewed_taxonomy_references_and_concept_weights_are_valid() -> None:
    effective = _effective_by_id()

    for group_id in EXPECTED_ANSWER_PATTERNS:
        record = effective[group_id]["academic_review_record"]
        for item in record["items"]:
            assert item["problem_types"]
            assert item["concepts"]
            assert item["learning_outcomes"]
            assert sum(
                mapping.get("is_primary") is True
                for mapping in item["problem_types"]
            ) <= 1
            weights = [mapping["weight"] for mapping in item["concepts"]]
            assert all(weight > 0 for weight in weights)
            assert sum(weights) <= 1.0 + 1e-9


def test_overlay_only_adds_review_fields_and_never_mutates_data_006() -> None:
    group_path = (
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    )
    raw_path = DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "candidate_questions.json"
    groups_before = group_path.read_bytes()
    raw_before = raw_path.read_bytes()
    groups = _load(group_path)
    assert isinstance(groups, list)

    materialization = EffectiveQuestionGroupReviewMaterializer().materialize(groups)

    assert materialization.is_valid
    assert group_path.read_bytes() == groups_before
    assert raw_path.read_bytes() == raw_before
    assert hashlib.sha256(raw_before).hexdigest() == EXPECTED_RAW_CANDIDATE_SHA256
    assert all(
        item["correct_answer"] is None
        for group in materialization.structural_groups
        for item in group["items"]
    )
    assert sum(
        item["correct_answer"] is not None
        for group in materialization.structural_groups
        for item in group["items"]
    ) == 0


def test_existing_question_group_staging_invariants_still_pass() -> None:
    report = QuestionGroupStagingValidator().validate()

    assert report.status == "PASS"
    assert report.counts == {
        "groups": 67,
        "structural_holds": 1,
        "child_statements": 268,
        "assigned_child_answers": 0,
    }


def test_validator_and_overlay_do_not_insert_database_rows(
    db_session: Session,
) -> None:
    before = (
        db_session.scalar(select(func.count(QuestionGroup.id))),
        db_session.scalar(select(func.count(QuestionGroupItem.id))),
    )

    report = QuestionGroupReviewValidator().validate()

    after = (
        db_session.scalar(select(func.count(QuestionGroup.id))),
        db_session.scalar(select(func.count(QuestionGroupItem.id))),
    )
    assert report.is_valid
    assert after == before


def test_unknown_child_taxonomy_code_fails_validation(tmp_path: Path) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    verified_path = review_root / "batch_001" / "verified_groups.json"
    verified = _load(verified_path)
    assert isinstance(verified, list)
    verified[0]["items"][0]["concepts"][0]["code"] = "UNKNOWN_CONCEPT"
    _write(verified_path, verified)

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert "UNKNOWN_CONCEPT" in {error.code for error in report.errors}


def test_overlapping_group_ids_across_batches_are_rejected(tmp_path: Path) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    shutil.copytree(review_root / "batch_001", review_root / "batch_002")

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert "GROUP_REVIEW_BATCH_OVERLAP" in {
        error.code for error in report.errors
    }


def test_patch_cannot_carry_answers_or_change_structural_fields(
    tmp_path: Path,
) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    patch_path = review_root / "batch_001" / "group_patch.json"
    patches = _load(patch_path)
    assert isinstance(patches, list)
    patches[0]["set"]["reviewed_items"][0]["correct_answer"] = "TRUE"
    _write(patch_path, patches)

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert "PATCH_ITEM_FIELDS_INVALID" in {
        error.code for error in report.errors
    }


def test_overlay_does_not_modify_input_objects() -> None:
    groups = _load(
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    )
    assert isinstance(groups, list)
    before = copy.deepcopy(groups)

    EffectiveQuestionGroupReviewMaterializer().materialize(groups)

    assert groups == before
