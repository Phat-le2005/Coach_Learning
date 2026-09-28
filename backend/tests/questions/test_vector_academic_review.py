from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from app.questions import vector_academic_review
from app.questions.group_import_service import TrustedQuestionGroupImportService
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.questions.vector_academic_review import (
    DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH,
    EXPECTED_DUPLICATE_CLUSTERS,
    EXPECTED_HOLD_GROUP_IDS,
    EXPECTED_PROBLEM_TYPE_GAPS,
    EXPECTED_RAW_CANDIDATE_SEMANTIC_SHA256,
    EXPECTED_REJECTED_GROUP_IDS,
    EXPECTED_REVIEW_AGGREGATE_SHA256,
    EXPECTED_REVIEW_STATS,
    EXPECTED_VERIFIED_GROUP_IDS,
    REVIEW_SEMANTIC_FILES,
    VectorAcademicReviewValidator,
)
from app.questions.vector_materialization import (
    DEFAULT_VECTOR_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    VectorQuestionMaterializationValidator,
)
from app.validate_vector_academic_review import main


def _load_list(
    name: str, root: Path = DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH
) -> list[dict]:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _load_object(
    name: str, root: Path = DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH
) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write_semantic_file_and_lock_aggregate(
    root: Path,
    name: str,
    payload: list[dict],
) -> str:
    (root / name).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    manifest = _load_object("review_manifest.json", root)
    manifest["semantic_file_hashes"][name] = (
        VectorAcademicReviewValidator.semantic_sha256(payload)
    )
    (root / "review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    aggregate = VectorAcademicReviewValidator.aggregate_semantic_sha256(root)
    manifest["review_aggregate_semantic_sha256"] = aggregate
    (root / "review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return aggregate


def test_exact_review_totals_and_statuses() -> None:
    report = VectorAcademicReviewValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == {
        "target_candidates": 68,
        "reviewed_candidates": 68,
        "standalone_reviews": 54,
        "group_reviews": 14,
        "review_status_counts": {
            "VERIFIED": 48,
            "REJECTED_DUPLICATE": 7,
            "REJECTED_OUT_OF_SCOPE_OXYZ": 9,
            "HOLD_MIXED_VECTOR_OXYZ": 4,
        },
        "true_false_child_answers_reviewed": 56,
        "taxonomy_corrections_standalone": 31,
        "verified_visual_required": 42,
        "production_release_eligible": 0,
    }
    assert _load_object("review_stats.json") == EXPECTED_REVIEW_STATS
    assert _load_object("review_manifest.json")["counts"] == EXPECTED_REVIEW_STATS


def test_review_ids_exactly_partition_data_016_effective_candidates() -> None:
    effective = json.loads(
        (DEFAULT_VECTOR_MATERIALIZATION_PATH / "effective_candidates.json").read_text(
            encoding="utf-8"
        )
    )
    standalone = _load_list("standalone_reviews.json")
    groups = _load_list("group_reviews.json")
    reviewed_ids = [row["candidate_id"] for row in standalone] + [
        row["source_candidate_id"] for row in groups
    ]

    assert len(reviewed_ids) == len(set(reviewed_ids)) == 68
    assert set(reviewed_ids) == {row["candidate_id"] for row in effective}


def test_standalone_answers_are_source_backed_and_non_promotable() -> None:
    standalone = _load_list("standalone_reviews.json")

    assert len(standalone) == 54
    assert all(row["correct_answer"] is not None for row in standalone)
    assert all(
        row["answer_verification"].startswith("SOURCE_BACKED")
        for row in standalone
    )
    assert all(row["promotion_ready"] is False for row in standalone)
    assert Counter(row["review_status"] for row in standalone) == {
        "VERIFIED": 47,
        "REJECTED_DUPLICATE": 7,
    }


def test_all_standalone_answers_are_bound_to_confirmed_source_evidence() -> None:
    standalone = _load_list("standalone_reviews.json")
    evidence_by_id = {
        row["evidence_id"]: row for row in _load_list("source_evidence.json")
    }

    assert len(standalone) == 54
    for review in standalone:
        evidence = evidence_by_id[review["source_evidence_id"]]
        assert evidence["question_unit_type"] == "STANDALONE"
        assert evidence["review_consistency"] == "CONFIRMED"
        assert review["correct_answer"] == evidence["source_claimed_answer"]


def test_all_group_answers_are_bound_to_confirmed_source_evidence() -> None:
    groups = _load_list("group_reviews.json")
    evidence_by_id = {
        row["evidence_id"]: row for row in _load_list("source_evidence.json")
    }

    assert len(groups) == 14
    assert sum(len(group["items"]) for group in groups) == 56
    for group in groups:
        evidence = evidence_by_id[group["source_evidence_id"]]
        assert evidence["question_unit_type"] == "TRUE_FALSE_FOUR"
        assert evidence["review_consistency"] == "CONFIRMED"
        assert [item["correct_answer"] for item in group["items"]] == (
            evidence["source_claimed_answer_pattern"]
        )


def test_exact_duplicate_clusters_and_verified_targets() -> None:
    standalone = _load_list("standalone_reviews.json")
    clusters = _load_list("duplicate_clusters.json")
    review_by_id = {row["candidate_id"]: row for row in standalone}
    actual_clusters = {
        row["canonical_candidate_id"]: tuple(row["duplicate_candidate_ids"])
        for row in clusters
    }
    expected_rejected = {
        duplicate: canonical
        for canonical, duplicates in EXPECTED_DUPLICATE_CLUSTERS.items()
        for duplicate in duplicates
    }

    assert actual_clusters == EXPECTED_DUPLICATE_CLUSTERS
    assert {
        row["candidate_id"]: row["duplicate_of"]
        for row in standalone
        if row["review_status"] == "REJECTED_DUPLICATE"
    } == expected_rejected
    assert all(
        review_by_id[canonical]["review_status"] == "VERIFIED"
        for canonical in EXPECTED_DUPLICATE_CLUSTERS
    )


def test_exact_31_standalone_taxonomy_corrections() -> None:
    standalone = _load_list("standalone_reviews.json")
    corrections = _load_list("taxonomy_corrections.json")
    corrected_ids = {
        row["candidate_id"]
        for row in standalone
        if row["structural_problem_type_code"]
        != row["reviewed_problem_type_code"]
    }

    assert len(corrections) == 31
    assert {row["candidate_id"] for row in corrections} == corrected_ids
    assert all(row["taxonomy"]["basis"] == "COACH_LEARNING_DERIVED" for row in standalone)


def test_content_patches_0018_and_0044_preserve_reviewed_decisions() -> None:
    patches = {
        row["candidate_id"]: row
        for row in _load_list("content_and_scope_patches.json")
    }
    reviews = {
        row["candidate_id"]: row for row in _load_list("standalone_reviews.json")
    }

    assert patches["M12_VECTOR_CAND_0018"]["source_question_pages"] == [42]
    assert "vector AB = vector CD" in patches["M12_VECTOR_CAND_0018"][
        "reviewed_content"
    ]
    assert "vector AB = vector DC" in patches["M12_VECTOR_CAND_0018"][
        "reviewed_content"
    ]
    assert reviews["M12_VECTOR_CAND_0018"]["correct_answer"] == "A"
    assert patches["M12_VECTOR_CAND_0044"]["source_question_pages"] == [397, 398]
    assert patches["M12_VECTOR_CAND_0044"]["source_solution_pages"] == [404]
    assert "A. 6. B. 5. C. 7. D. 3." in patches["M12_VECTOR_CAND_0044"][
        "reviewed_content"
    ]
    assert reviews["M12_VECTOR_CAND_0044"]["correct_answer"] == "A"


def test_group_0010_mixed_scope_is_corrected_only_in_review_overlay() -> None:
    groups = {
        row["source_candidate_id"]: row for row in _load_list("group_reviews.json")
    }
    patches = {
        row["candidate_id"]: row
        for row in _load_list("content_and_scope_patches.json")
    }
    structural = {
        row["source_candidate_id"]: row
        for row in json.loads(
            (
                DEFAULT_VECTOR_MATERIALIZATION_PATH
                / "question_group_candidates.json"
            ).read_text(encoding="utf-8")
        )
    }

    assert structural["M12_VECTOR_CAND_0010"]["mixed_scope"] is False
    assert groups["M12_VECTOR_CAND_0010"]["structural_mixed_scope"] is False
    assert groups["M12_VECTOR_CAND_0010"]["reviewed_mixed_scope"] is True
    assert patches["M12_VECTOR_CAND_0010"]["reviewed_mixed_scope"] is True


def test_all_groups_remain_atomic_with_exact_status_sets() -> None:
    groups = _load_list("group_reviews.json")
    by_status = {
        status: tuple(
            sorted(
                row["group_candidate_id"]
                for row in groups
                if row["review_status"] == status
            )
        )
        for status in {
            "VERIFIED",
            "HOLD_MIXED_VECTOR_OXYZ",
            "REJECTED_OUT_OF_SCOPE_OXYZ",
        }
    }

    assert len(groups) == 14
    assert sum(len(row["items"]) for row in groups) == 56
    assert by_status["VERIFIED"] == EXPECTED_VERIFIED_GROUP_IDS
    assert by_status["HOLD_MIXED_VECTOR_OXYZ"] == EXPECTED_HOLD_GROUP_IDS
    assert by_status["REJECTED_OUT_OF_SCOPE_OXYZ"] == EXPECTED_REJECTED_GROUP_IDS
    for group in groups:
        assert [item["label"] for item in group["items"]] == ["a", "b", "c", "d"]
        assert [item["order_index"] for item in group["items"]] == [0, 1, 2, 3]
        assert all(item["correct_answer"] in {"TRUE", "FALSE"} for item in group["items"])
        assert group["promotion_ready"] is False


def test_oxyz_children_carry_no_vector_taxonomy() -> None:
    items = [
        item
        for group in _load_list("group_reviews.json")
        for item in group["items"]
        if item["scope_classification"] == "OXYZ"
    ]

    assert len(items) == 46
    assert all(item["taxonomy_status"] == "DEFERRED_TO_OXYZ_CHAPTER" for item in items)
    assert all(item["taxonomy"]["problem_types"] == [] for item in items)
    assert all(item["taxonomy"]["concepts"] == [] for item in items)
    assert all(item["taxonomy"]["learning_outcomes"] == [] for item in items)


def test_verified_group_0040_pattern_taxonomy_evidence_and_blockers() -> None:
    group = next(
        row
        for row in _load_list("group_reviews.json")
        if row["group_candidate_id"] == "M12_VECTOR_GROUP_0040"
    )
    evidence = next(
        row
        for row in _load_list("source_evidence.json")
        if row.get("group_candidate_id") == "M12_VECTOR_GROUP_0040"
    )

    assert [item["correct_answer"] for item in group["items"]] == [
        "TRUE", "TRUE", "TRUE", "FALSE"
    ]
    assert [
        item["taxonomy"]["problem_types"][0]["code"] for item in group["items"]
    ] == [
        "VECTOR_COORDINATES_FROM_POINTS_3D",
        "VECTOR_LENGTH_DISTANCE_3D",
        "MIDPOINT_CENTROID_COORDINATES_3D",
        "VECTOR_ANGLE_3D",
    ]
    assert evidence["solution_pages"] == [368]
    assert group["visual_asset_required"] is True
    assert group["promotion_ready"] is False


def test_reviewed_coverage_is_11_of_15_with_exact_gaps() -> None:
    coverage = _load_list("coverage_after_review.json")
    gaps = tuple(
        row["problem_type_code"]
        for row in coverage
        if row["coverage_status"] == "GAP"
    )

    assert len(coverage) == 15
    assert sum(row["coverage_status"] == "HAS_VERIFIED_EVIDENCE" for row in coverage) == 11
    assert gaps == EXPECTED_PROBLEM_TYPE_GAPS


def test_verified_visual_count_and_release_boundaries() -> None:
    rows = [
        *_load_list("standalone_reviews.json"),
        *_load_list("group_reviews.json"),
    ]
    manifest = _load_object("review_manifest.json")

    assert sum(
        row["review_status"] == "VERIFIED" and row["visual_asset_required"]
        for row in rows
    ) == 42
    assert all(row["promotion_ready"] is False for row in rows)
    assert manifest["database_import_allowed"] is False
    assert manifest["production_release_eligible"] == 0
    assert manifest["db_migration_required"] is False
    assert not (DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH / "manifest.json").exists()


def test_review_hashes_and_direct_aggregate_are_deterministic() -> None:
    validator = VectorAcademicReviewValidator()
    manifest = _load_object("review_manifest.json")
    first = validator.aggregate_semantic_sha256(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH)
    second = validator.aggregate_semantic_sha256(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH)

    assert first == second == EXPECTED_REVIEW_AGGREGATE_SHA256
    assert manifest["review_aggregate_semantic_sha256"] == first
    assert manifest["semantic_files_order"] == list(REVIEW_SEMANTIC_FILES)
    assert {
        name: validator.semantic_sha256(
            json.loads(
                (DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH / name).read_text(
                    encoding="utf-8"
                )
            )
        )
        for name in REVIEW_SEMANTIC_FILES
    } == manifest["semantic_file_hashes"]


def test_mutated_review_with_updated_file_hash_still_fails_aggregate(
    tmp_path: Path,
) -> None:
    target = tmp_path / "review"
    shutil.copytree(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH, target)
    rows = _load_list("standalone_reviews.json", target)
    rows[0]["correct_answer"] = "MUTATED"
    (target / "standalone_reviews.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8"
    )
    manifest = _load_object("review_manifest.json", target)
    manifest["semantic_file_hashes"]["standalone_reviews.json"] = (
        VectorAcademicReviewValidator.semantic_sha256(rows)
    )
    (target / "review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    report = VectorAcademicReviewValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is False
    assert any(
        error.code == "REVIEW_AGGREGATE_SEMANTIC_SHA256_MISMATCH"
        for error in report.errors
    )


def test_standalone_answer_mismatch_fails_after_relocking_review_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "review"
    shutil.copytree(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH, target)
    rows = _load_list("standalone_reviews.json", target)
    rows[0]["correct_answer"] = (
        "A" if rows[0]["correct_answer"] != "A" else "B"
    )
    aggregate = _write_semantic_file_and_lock_aggregate(
        target, "standalone_reviews.json", rows
    )
    monkeypatch.setattr(
        vector_academic_review,
        "EXPECTED_REVIEW_AGGREGATE_SHA256",
        aggregate,
    )

    report = VectorAcademicReviewValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is True
    assert report.checks["source_evidence"] is False
    assert any(
        error.code == "STANDALONE_ANSWER_EVIDENCE_MISMATCH"
        for error in report.errors
    )


def test_group_answer_mismatch_fails_after_relocking_review_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "review"
    shutil.copytree(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH, target)
    groups = _load_list("group_reviews.json", target)
    group = next(
        row
        for row in groups
        if row["group_candidate_id"] == "M12_VECTOR_GROUP_0007"
    )
    first_answer = group["items"][0]["correct_answer"]
    group["items"][0]["correct_answer"] = (
        "FALSE" if first_answer == "TRUE" else "TRUE"
    )
    aggregate = _write_semantic_file_and_lock_aggregate(
        target, "group_reviews.json", groups
    )
    monkeypatch.setattr(
        vector_academic_review,
        "EXPECTED_REVIEW_AGGREGATE_SHA256",
        aggregate,
    )

    report = VectorAcademicReviewValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is True
    assert report.checks["source_evidence"] is False
    assert any(
        error.code == "GROUP_ANSWER_EVIDENCE_MISMATCH"
        for error in report.errors
    )


def test_unconfirmed_evidence_fails_after_relocking_review_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "review"
    shutil.copytree(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH, target)
    evidence = _load_list("source_evidence.json", target)
    evidence[0]["review_consistency"] = "NOT_CONFIRMED"
    aggregate = _write_semantic_file_and_lock_aggregate(
        target, "source_evidence.json", evidence
    )
    monkeypatch.setattr(
        vector_academic_review,
        "EXPECTED_REVIEW_AGGREGATE_SHA256",
        aggregate,
    )

    report = VectorAcademicReviewValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is True
    assert report.checks["source_evidence"] is False
    assert any(
        error.code == "SOURCE_EVIDENCE_REVIEW_NOT_CONFIRMED"
        for error in report.errors
    )


def test_invalid_group_evidence_shape_fails_after_relocking_review_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "review"
    shutil.copytree(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH, target)
    evidence = _load_list("source_evidence.json", target)
    group_evidence = next(
        row
        for row in evidence
        if row.get("group_candidate_id") == "M12_VECTOR_GROUP_0007"
    )
    group_evidence["source_claimed_answer_pattern"] = ["TRUE", "FALSE", "TRUE"]
    aggregate = _write_semantic_file_and_lock_aggregate(
        target, "source_evidence.json", evidence
    )
    monkeypatch.setattr(
        vector_academic_review,
        "EXPECTED_REVIEW_AGGREGATE_SHA256",
        aggregate,
    )

    report = VectorAcademicReviewValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is True
    assert report.checks["source_evidence"] is False
    assert any(
        error.code == "SOURCE_EVIDENCE_ANSWER_SHAPE_INVALID"
        for error in report.errors
    )


def test_data_016_and_derivative_regression_invariants() -> None:
    materialization = VectorQuestionMaterializationValidator().validate()
    review = QuestionGroupReviewValidator().validate()
    visual = QuestionGroupVisualAssetValidator().validate()
    promotion = QuestionGroupPromotionValidator().validate()
    preview = TrustedQuestionGroupImportService().preview()
    raw = json.loads(
        (DEFAULT_VECTOR_MATERIALIZATION_PATH / "candidate_questions.json").read_text(
            encoding="utf-8"
        )
    )

    assert materialization.is_valid, materialization.as_dict()
    assert materialization.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert materialization.counts["raw"]["materialized_unique_candidates"] == 72
    assert materialization.counts["effective"]["candidates"] == 68
    assert VectorQuestionMaterializationValidator.semantic_sha256(raw) == (
        EXPECTED_RAW_CANDIDATE_SEMANTIC_SHA256
    )
    assert review.is_valid and review.counts["reviewed_groups"] == 67
    assert review.counts["verified"] == 39
    assert visual.is_valid and visual.counts["ready_source_crops"] == 8
    assert visual.counts["blocked_source_visual_missing"] == 1
    assert promotion.is_valid
    assert promotion.counts["canonical_snapshot_ready_groups"] == 38
    assert promotion.counts["canonical_snapshot_ready_children"] == 152
    assert promotion.counts["production_release_eligible_groups"] == 0
    assert preview.counts["draft_groups"] == 38
    assert preview.counts["draft_children"] == 152
    assert preview.production_release_eligible == 0


def test_vector_academic_review_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out

    assert first == second
    assert '"status": "PASS"' in first
