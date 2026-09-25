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
    QuestionGroupReviewValidator,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_staging_validator import (
    QuestionGroupStagingValidator,
)


EXPECTED_ANSWER_PATTERNS = {
    "M12_DERIV_GROUP_0012": ("TRUE", "FALSE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0019": ("TRUE", "FALSE", "FALSE", "TRUE"),
    "M12_DERIV_GROUP_0024": ("FALSE", "TRUE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0031": ("FALSE", "TRUE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0035": ("TRUE", "FALSE", "TRUE", "FALSE"),
    "M12_DERIV_GROUP_0041": ("TRUE", "FALSE", "TRUE", "TRUE"),
    "M12_DERIV_GROUP_0052": ("TRUE", "FALSE", "TRUE", "TRUE"),
}
EXPECTED_HOLD_ID = "M12_DERIV_GROUP_0047"
EXPECTED_DUPLICATES = {
    "M12_DERIV_GROUP_0021": "M12_DERIV_GROUP_0019",
    "M12_DERIV_GROUP_0026": "M12_DERIV_GROUP_0024",
    "M12_DERIV_GROUP_0053": "M12_DERIV_GROUP_0052",
}
EXPECTED_OUT_OF_SCOPE = {
    "M12_DERIV_GROUP_0044",
    "M12_DERIV_GROUP_0055",
}
EXPECTED_VISUAL_GROUPS = {
    "M12_DERIV_GROUP_0012",
    "M12_DERIV_GROUP_0024",
}
EXPECTED_TARGET_IDS = (
    set(EXPECTED_ANSWER_PATTERNS)
    | {EXPECTED_HOLD_ID}
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


def _add_valid_synthetic_hold_batch(review_root: Path) -> str:
    groups = _load(
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    )
    assert isinstance(groups, list)
    structural = next(
        group
        for group in groups
        if group["group_candidate_id"] not in EXPECTED_TARGET_IDS
    )
    group_id = str(structural["group_candidate_id"])
    evidence_id = f"EVID_TEST_{group_id}"
    batch_path = review_root / "batch_002"
    batch_path.mkdir()
    (batch_path / "README.md").write_text(
        "# Synthetic validator fixture\n", encoding="utf-8"
    )
    source_file = "synthetic-reviewed-source.json"
    source_sha = "0" * 64
    _write(batch_path / "source_metadata.json", {
        "source_code": structural["source_code"],
        "file_name": source_file,
        "source_pdf_sha256": source_sha,
        "pdf_binary_in_bundle": False,
    })
    _write(batch_path / "source_evidence.json", [{
        "evidence_id": evidence_id,
        "group_candidate_id": group_id,
        "source_code": structural["source_code"],
        "effective_subsource_code": structural["effective_subsource_code"],
        "candidate_extraction_page": structural["source_page"],
        "question_number": structural["question_number"],
        "evidence_type": "SYNTHETIC_TEST_FIXTURE",
    }])
    _write(batch_path / "verified_groups.json", [])
    _write(batch_path / "hold_groups.json", [{
        "group_candidate_id": group_id,
        "source_candidate_id": structural["source_candidate_id"],
        "source_fingerprint": structural["source_fingerprint"],
        "source_code": structural["source_code"],
        "raw_subsource_code": structural["raw_subsource_code"],
        "effective_subsource_code": structural["effective_subsource_code"],
        "provenance_correction_code": structural["provenance_correction_code"],
        "candidate_extraction_page": structural["source_page"],
        "question_number": structural["question_number"],
        "review_status": "HOLD_VISUAL_SOURCE_REVIEW",
        "source_evidence_id": evidence_id,
        "reason": "Synthetic future-batch validation fixture.",
        "promotion_ready": False,
    }])
    _write(batch_path / "rejected_groups.json", [])
    _write(batch_path / "group_patch.json", [])
    _write(batch_path / "review_stats.json", {
        "dataset_code": "DATA-MATH12-008_TEST",
        "batch_code": "DATA-MATH12-008_TEST_BATCH_002",
        "source_code": structural["source_code"],
        "source_file": source_file,
        "source_pdf_sha256": source_sha,
        "raw_candidate_sha256": EXPECTED_RAW_CANDIDATE_SHA256,
        "target_groups": 1,
        "reviewed_groups": 1,
        "verified": 0,
        "hold": 1,
        "rejected": 0,
        "rejected_duplicate": 0,
        "rejected_out_of_scope": 0,
        "verified_child_statements": 0,
        "assigned_child_answers": 0,
        "visual_asset_required": 0,
        "source_evidence_backed_decisions": 1,
        "promotion_ready": 0,
        "production_imported": 0,
    })
    return group_id


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
        "verified": 7,
        "hold": 1,
        "rejected": 5,
        "rejected_duplicate": 3,
        "rejected_out_of_scope": 2,
        "verified_child_statements": 28,
        "assigned_child_answers": 28,
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


def test_group_0047_is_a_non_promotable_source_answer_conflict_hold() -> None:
    effective = _effective_by_id()
    group = effective[EXPECTED_HOLD_ID]
    record = group["academic_review_record"]
    evidence = group["source_evidence"]

    assert record["review_status"] == "HOLD_SOURCE_ANSWER_CONFLICT"
    assert record["source_claimed_answer_pattern"] == [
        "TRUE",
        "TRUE",
        "FALSE",
        "FALSE",
    ]
    assert evidence["answer_pattern"] == ["TRUE", "TRUE", "FALSE", "FALSE"]
    assert evidence["source_claimed_answer_pattern"] == [
        "TRUE",
        "TRUE",
        "FALSE",
        "FALSE",
    ]
    assert record["conflicting_item_label"] == "c"
    assert record["trusted_correct_answer"] is None
    assert record["conflict_explanation"]
    assert record["independent_check"]["provenance_type"] == (
        "INDEPENDENT_REVIEW_CHECK"
    )
    assert group["promotion_ready"] is False
    assert all(
        item.get("correct_answer") is None
        for item in record.get("items", [])
        if item.get("label") == "c"
    )


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


def test_generic_validator_accepts_a_valid_additional_batch_with_new_counts(
    tmp_path: Path,
) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    added_group_id = _add_valid_synthetic_hold_batch(review_root)

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "PASS"
    assert report.counts["review_batches"] == 2
    assert report.counts["reviewed_groups"] == 14
    assert report.counts["verified"] == 7
    assert report.counts["hold"] == 2
    assert report.counts["rejected"] == 5
    assert added_group_id in report.review_batches[1]["reviewed_group_ids"]
    assert report.review_batches[1]["counts"] == {
        "reviewed": 1,
        "verified": 0,
        "hold": 1,
        "rejected": 0,
    }


def test_overlapping_group_ids_across_batches_are_rejected(tmp_path: Path) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    shutil.copytree(review_root / "batch_001", review_root / "batch_002")

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert "GROUP_REVIEW_BATCH_OVERLAP" in {
        error.code for error in report.errors
    }


def test_invalid_hold_provenance_fails_validation(tmp_path: Path) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    hold_path = review_root / "batch_001" / "hold_groups.json"
    holds = _load(hold_path)
    assert isinstance(holds, list)
    holds[0]["raw_subsource_code"] = "WRONG_SUBSOURCE"
    _write(hold_path, holds)

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert "HOLD_PROVENANCE_MISMATCH" in {
        error.code for error in report.errors
    }


def test_source_answer_conflict_hold_rejects_trusted_final_answer(
    tmp_path: Path,
) -> None:
    review_root = tmp_path / "group_review"
    shutil.copytree(DEFAULT_QUESTION_GROUP_REVIEW_ROOT, review_root)
    hold_path = review_root / "batch_001" / "hold_groups.json"
    holds = _load(hold_path)
    assert isinstance(holds, list)
    holds[0]["trusted_correct_answer"] = "FALSE"
    _write(hold_path, holds)

    report = QuestionGroupReviewValidator().validate(review_root=review_root)

    assert report.status == "FAIL"
    assert "HOLD_CONFLICT_TRUSTED_ANSWER_ASSIGNED" in {
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
