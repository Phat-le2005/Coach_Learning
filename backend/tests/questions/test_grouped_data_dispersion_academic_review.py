from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from app.curriculum.grouped_data_dispersion_staging import (
    GroupedDataDispersionStagingValidator,
)
from app.questions.grouped_data_dispersion_academic_review import (
    CURATED_SEMANTIC_FILES,
    DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
    EXPECTED_CANONICAL_ID,
    EXPECTED_CURATED_SEMANTIC_HASHES,
    EXPECTED_DUPLICATE_ID,
    EXPECTED_GROUP_ANSWER_KEYS,
    EXPECTED_PROBLEM_TYPE_GAPS,
    EXPECTED_REVIEW_AGGREGATE_SHA256,
    EXPECTED_REVIEW_STATS,
    GroupedDataDispersionAcademicReviewValidator,
)
from app.questions.grouped_data_dispersion_materialization import (
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    GroupedDataDispersionMaterializationValidator,
)
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.questions.vector_academic_review import VectorAcademicReviewValidator
from app.questions.vector_materialization import VectorQuestionMaterializationValidator
from app.questions.vector_visual_promotion import VectorVisualPromotionValidator
from app.validate_grouped_data_dispersion_academic_review import main


def _load(name: str, root: Path = DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH):
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, value) -> None:
    (root / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_review(tmp_path: Path) -> Path:
    target = tmp_path / "academic_review" / "v0_1"
    shutil.copytree(DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH, target)
    return target


def test_curated_academic_review_passes_exact_contract() -> None:
    report = GroupedDataDispersionAcademicReviewValidator().validate()

    assert report.is_valid, report.as_dict()
    assert all(report.checks.values())
    assert report.counts == {
        "input_candidate_count": 41,
        "standalone_reviews": 39,
        "group_reviews": 2,
        "verified_standalone": 38,
        "rejected_duplicate": 1,
        "hold_mixed_scope_groups": 2,
        "true_false_child_answers_verified": 8,
        "production_release_eligible": 0,
    }
    assert report.review_aggregate_semantic_sha256 == (
        EXPECTED_REVIEW_AGGREGATE_SHA256
    )
    assert report.problem_type_gaps == EXPECTED_PROBLEM_TYPE_GAPS
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False


def test_curated_semantic_files_are_locked_and_validator_is_read_only() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH
    validator = GroupedDataDispersionAcademicReviewValidator()
    names = (*CURATED_SEMANTIC_FILES, "README.md")
    before = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in names
    }

    report = validator.validate()

    after = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in names
    }
    assert report.is_valid
    assert before == after
    assert {
        name: validator.semantic_sha256(_load(name))
        for name in CURATED_SEMANTIC_FILES
    } == EXPECTED_CURATED_SEMANTIC_HASHES


def test_data020_identity_and_hash_contract_are_preserved() -> None:
    review_manifest = _load("review_manifest.json")
    materialization = GroupedDataDispersionMaterializationValidator().validate()

    assert materialization.is_valid, materialization.as_dict()
    assert materialization.aggregate_semantic_sha256 == (
        EXPECTED_AGGREGATE_SEMANTIC_SHA256
    )
    assert review_manifest["input_candidate_semantic_sha256"] == (
        "bb88a02a3c982b55a11e250af05432ba999f455f1af54cfb347c5dd277f4c619"
    )
    assert review_manifest["input_materialization_aggregate_sha256"] == (
        EXPECTED_AGGREGATE_SEMANTIC_SHA256
    )


def test_verified_standalones_have_source_backed_answers_and_evidence() -> None:
    reviews = _load("standalone_reviews.json")
    evidence_by_id = {
        row["candidate_id"]: row for row in _load("source_evidence.json")
    }
    verified = [row for row in reviews if row["review_status"] == "VERIFIED"]

    assert len(verified) == 38
    assert all(row["correct_answer"] in {"A", "B", "C", "D"} for row in verified)
    assert all(
        row["answer_verification"] == "SOURCE_BACKED_AND_REVIEW_CONSISTENT"
        for row in verified
    )
    assert all(
        evidence_by_id[row["candidate_id"]]["source_claimed_answer"]
        == row["correct_answer"]
        for row in verified
    )
    assert all(
        evidence_by_id[row["candidate_id"]]["review_consistency"] == "CONFIRMED"
        for row in verified
    )


def test_duplicate_resolution_is_exact_and_canonical_answer_is_b() -> None:
    reviews = {row["candidate_id"]: row for row in _load("standalone_reviews.json")}
    clusters = _load("duplicate_clusters.json")

    assert clusters == [
        {
            "cluster_id": "DISP_DUP_0001",
            "canonical_candidate_id": EXPECTED_CANONICAL_ID,
            "duplicate_candidate_ids": [EXPECTED_DUPLICATE_ID],
            "reason": "EXACT_NORMALIZED_QUESTION_TEXT_MATCH",
            "academic_resolution": "KEEP_0015_REJECT_0014",
            "canonical_answer": "B",
            "canonical_answer_basis": (
                "SOURCE_SOLUTION_OCCURRENCE_ON_CANONICAL_CANDIDATE"
            ),
        }
    ]
    assert reviews[EXPECTED_DUPLICATE_ID]["review_status"] == "REJECTED_DUPLICATE"
    assert reviews[EXPECTED_DUPLICATE_ID]["duplicate_of"] == EXPECTED_CANONICAL_ID
    assert reviews[EXPECTED_DUPLICATE_ID]["correct_answer"] is None
    assert reviews[EXPECTED_CANONICAL_ID]["review_status"] == "VERIFIED"
    assert reviews[EXPECTED_CANONICAL_ID]["correct_answer"] == "B"


def test_mixed_scope_group_keys_are_verified_but_groups_remain_hold() -> None:
    groups = {row["group_candidate_id"]: row for row in _load("group_reviews.json")}

    assert set(groups) == set(EXPECTED_GROUP_ANSWER_KEYS)
    for group_id, expected_key in EXPECTED_GROUP_ANSWER_KEYS.items():
        group = groups[group_id]
        assert group["review_status"] == "HOLD_MIXED_SCOPE"
        assert group["mixed_scope"] is True
        assert group["promotion_ready"] is False
        assert tuple(item["correct_answer"] for item in group["items"]) == expected_key
        assert all(
            item["answer_status"] == "SOURCE_BACKED_VERIFIED"
            for item in group["items"]
        )
        assert Counter(item["taxonomy_status"] for item in group["items"]) == {
            "IN_SCOPE": 1,
            "OUT_OF_SCOPE_FOR_DISPERSION_DATASET": 3,
        }
        assert (
            "MIXED_SCOPE_GROUP_NOT_CANONICAL_FOR_DISPERSION_ONLY_DATASET"
            in group["promotion_blockers"]
        )


def test_source_evidence_is_one_to_one_for_all_reviewed_units() -> None:
    standalone = _load("standalone_reviews.json")
    groups = _load("group_reviews.json")
    evidence = _load("source_evidence.json")
    ids = [row["candidate_id"] for row in evidence]

    assert len(evidence) == len(ids) == len(set(ids)) == 41
    assert set(ids) == {row["candidate_id"] for row in standalone} | {
        row["group_candidate_id"] for row in groups
    }
    assert Counter(row["question_unit_type"] for row in evidence) == {
        "STANDALONE": 39,
        "TRUE_FALSE_GROUP": 2,
    }


def test_taxonomy_and_curated_coverage_gaps_are_preserved() -> None:
    reviews = _load("standalone_reviews.json")
    coverage = _load("coverage_after_review.json")
    stats = _load("review_stats.json")
    report = GroupedDataDispersionAcademicReviewValidator().validate()

    assert report.checks["taxonomy"] is True
    assert all(row["taxonomy"]["basis"] == "DATA_MATH12_019_TAXONOMY" for row in reviews)
    assert all(row["taxonomy"]["status"] == "CONFIRMED" for row in reviews)
    assert tuple(
        row["problem_type_code"] for row in coverage if row["status"] == "GAP"
    ) == EXPECTED_PROBLEM_TYPE_GAPS
    assert tuple(stats["problem_type_gaps"]) == EXPECTED_PROBLEM_TYPE_GAPS
    assert stats == EXPECTED_REVIEW_STATS


def test_rights_visual_import_and_snapshot_blockers_remain() -> None:
    standalone = _load("standalone_reviews.json")
    groups = _load("group_reviews.json")
    manifest = _load("review_manifest.json")
    stats = _load("review_stats.json")

    assert stats["rights_status"] == "REVIEW_REQUIRED"
    assert manifest["production_release_eligible"] == 0
    assert manifest["database_import_allowed"] is False
    assert manifest["canonical_snapshot_allowed"] is False
    assert all(row["promotion_ready"] is False for row in standalone)
    assert all(row["promotion_ready"] is False for row in groups)
    assert all(
        "RIGHTS_REVIEW_REQUIRED" in row["promotion_blockers"]
        for row in standalone
        if row["review_status"] == "VERIFIED"
    )


def test_validator_rejects_any_curated_answer_change(tmp_path: Path) -> None:
    root = _copy_review(tmp_path)
    reviews = _load("standalone_reviews.json", root)
    reviews[0]["correct_answer"] = "A" if reviews[0]["correct_answer"] != "A" else "B"
    _write(root, "standalone_reviews.json", reviews)

    report = GroupedDataDispersionAcademicReviewValidator().validate(root)

    assert report.status == "FAIL"
    assert report.checks["curated_semantic_hashes"] is False
    assert report.checks["source_evidence"] is False
    assert "CURATED_SEMANTIC_SHA256_MISMATCH" in {
        issue.code for issue in report.errors
    }


def test_validator_rejects_group_promotion_or_answer_change(tmp_path: Path) -> None:
    root = _copy_review(tmp_path)
    groups = _load("group_reviews.json", root)
    groups[0]["review_status"] = "VERIFIED"
    groups[0]["promotion_ready"] = True
    groups[0]["items"][0]["correct_answer"] = False
    _write(root, "group_reviews.json", groups)

    report = GroupedDataDispersionAcademicReviewValidator().validate(root)

    assert report.status == "FAIL"
    assert report.checks["group_reviews"] is False
    assert report.checks["promotion_boundary"] is False
    assert report.checks["source_evidence"] is False


def test_validator_rejects_changed_real_gap_set(tmp_path: Path) -> None:
    root = _copy_review(tmp_path)
    coverage = _load("coverage_after_review.json", root)
    gap = next(row for row in coverage if row["status"] == "GAP")
    gap["status"] = "COVERED"
    gap["verified_standalone_candidates"] = 1
    _write(root, "coverage_after_review.json", coverage)

    report = GroupedDataDispersionAcademicReviewValidator().validate(root)

    assert report.status == "FAIL"
    assert report.checks["coverage"] is False
    assert report.checks["curated_semantic_hashes"] is False


def test_previous_math12_pipelines_do_not_regress() -> None:
    data019 = GroupedDataDispersionStagingValidator().validate()
    data020 = GroupedDataDispersionMaterializationValidator().validate()
    vector_materialization = VectorQuestionMaterializationValidator().validate()
    vector_review = VectorAcademicReviewValidator().validate()
    vector_promotion = VectorVisualPromotionValidator().validate()
    derivative_review = QuestionGroupReviewValidator().validate()
    derivative_visual = QuestionGroupVisualAssetValidator().validate()
    derivative_promotion = QuestionGroupPromotionValidator().validate()

    assert data019.is_valid
    assert data020.is_valid
    assert data020.counts["materialized_unique_candidates"] == 41
    assert vector_materialization.is_valid
    assert vector_materialization.counts["raw"]["materialized_unique_candidates"] == 72
    assert vector_materialization.counts["effective"]["candidates"] == 68
    assert vector_review.is_valid
    assert vector_review.counts["reviewed_candidates"] == 68
    assert vector_review.counts["review_status_counts"]["VERIFIED"] == 48
    assert vector_promotion.is_valid
    assert vector_promotion.counts["canonical_snapshot_ready_units"] == 48
    assert vector_promotion.counts["ready_source_crops"] == 32
    assert vector_promotion.counts["production_release_eligible_units"] == 0
    assert derivative_review.is_valid
    assert derivative_review.counts["reviewed_groups"] == 67
    assert derivative_review.counts["verified"] == 39
    assert derivative_visual.is_valid
    assert derivative_visual.counts["ready_source_crops"] == 8
    assert derivative_visual.counts["blocked_source_visual_missing"] == 1
    assert derivative_promotion.is_valid
    assert derivative_promotion.counts["canonical_snapshot_ready_groups"] == 38
    assert derivative_promotion.counts["canonical_snapshot_ready_children"] == 152
    assert derivative_promotion.counts["production_release_eligible_groups"] == 0


def test_academic_review_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out
    assert first == second
