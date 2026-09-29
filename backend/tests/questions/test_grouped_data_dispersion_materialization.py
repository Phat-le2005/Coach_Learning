from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from app.curriculum.grouped_data_dispersion_staging import (
    EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256,
    GroupedDataDispersionStagingValidator,
)
from app.questions.grouped_data_dispersion_materialization import (
    DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    EXPECTED_COUNTS,
    EXPECTED_PROBLEM_TYPE_COVERAGE,
    EXPECTED_PROBLEM_TYPE_GAPS,
    EXPECTED_PROVENANCE_OCCURRENCE_COUNTS,
    EXPECTED_SELECTED_SOURCE_COUNTS,
    SEMANTIC_FILES,
    GroupedDataDispersionMaterializationValidator,
)
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.questions.vector_academic_review import VectorAcademicReviewValidator
from app.questions.vector_materialization import VectorQuestionMaterializationValidator
from app.questions.vector_visual_promotion import VectorVisualPromotionValidator
from app.validate_grouped_data_dispersion_materialization import main


def _load(name: str, root: Path = DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH):
    return json.loads((root / name).read_text(encoding="utf-8"))


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "materialized_v0_1"
    shutil.copytree(DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH, target)
    return target


def _write_json(root: Path, name: str, payload) -> None:
    (root / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_materialization_passes_exact_locked_contract() -> None:
    report = GroupedDataDispersionMaterializationValidator().validate()

    assert report.is_valid, report.as_dict()
    assert all(report.checks.values())
    assert report.counts == EXPECTED_COUNTS
    assert report.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert report.problem_type_coverage == EXPECTED_PROBLEM_TYPE_COVERAGE
    assert report.problem_type_gaps == EXPECTED_PROBLEM_TYPE_GAPS
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False


def test_candidate_source_and_provenance_counts_are_exact() -> None:
    candidates = _load("candidate_questions.json")

    assert Counter(row["source_key"] for row in candidates) == (
        EXPECTED_SELECTED_SOURCE_COUNTS
    )
    assert Counter(
        occurrence["source_key"]
        for row in candidates
        for occurrence in row["duplicate_occurrences"]
    ) == EXPECTED_PROVENANCE_OCCURRENCE_COUNTS
    assert sum(len(row["duplicate_occurrences"]) for row in candidates) == 80
    assert not any(
        row["source_key"] == "OFFICIAL_EXAM_SOLUTIONS_2025"
        for row in candidates
    )


def test_structural_answers_never_become_academic_authority() -> None:
    candidates = _load("candidate_questions.json")
    groups = _load("question_group_candidates.json")

    assert sum(row["answer_detected"] is not None for row in candidates) == 38
    assert {row["status"] for row in candidates} == {"STRUCTURAL_CANDIDATE"}
    assert {row["academic_review_status"] for row in candidates} == {
        "NOT_REVIEWED"
    }
    assert not any(row["promotion_eligible"] for row in candidates)
    assert all("correct_answer" not in row for row in candidates)
    assert all("verified_answer" not in row for row in candidates)
    assert {row["status"] for row in groups} == {"STRUCTURAL_CANDIDATE"}
    assert {row["academic_review_status"] for row in groups} == {"NOT_REVIEWED"}
    assert not any(row["promotion_eligible"] for row in groups)


def test_true_false_four_groups_remain_atomic_mixed_and_unreviewed() -> None:
    candidates = _load("candidate_questions.json")
    standalone_ids = {
        row["candidate_id"] for row in _load("standalone_candidates.json")
    }
    groups = _load("question_group_candidates.json")
    candidate_by_id = {row["candidate_id"]: row for row in candidates}

    assert len(groups) == 2
    for group in groups:
        source_id = group["source_candidate_id"]
        source = candidate_by_id[source_id]
        assert source_id not in standalone_ids
        assert source["requires_question_group_model"] is True
        assert source["question_type_detected"] == "TRUE_FALSE_GROUP"
        assert source["mixed_scope"] is True
        assert group["group_type"] == "TRUE_FALSE_FOUR"
        assert group["scoring_policy"] == "MOET_2025_TRUE_FALSE"
        assert group["mixed_scope"] is True
        assert group["items"] == source["tf_items"]
        assert [item["label"] for item in group["items"]] == ["a", "b", "c", "d"]
        assert [item["order_index"] for item in group["items"]] == [0, 1, 2, 3]
        assert all(item["correct_answer"] is None for item in group["items"])
        assert all(item["answer_status"] == "UNREVIEWED" for item in group["items"])
        assert all(
            item["taxonomy_status"] == "NOT_REVIEWED" for item in group["items"]
        )


def test_taxonomy_mappings_are_exact_data019_projections() -> None:
    report = GroupedDataDispersionMaterializationValidator().validate()
    candidates = _load("candidate_questions.json")

    assert report.checks["taxonomy_mappings"] is True
    assert Counter(row["problem_type_code"] for row in candidates) == (
        EXPECTED_PROBLEM_TYPE_COVERAGE
    )
    assert set(row["problem_type_code"] for row in candidates) == set(
        EXPECTED_PROBLEM_TYPE_COVERAGE
    )


def test_review_queue_contains_each_candidate_once_with_matching_fields() -> None:
    candidates = _load("candidate_questions.json")
    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    with (
        DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH / "review_queue.csv"
    ).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == len({row["candidate_id"] for row in rows}) == 41
    assert {row["candidate_id"] for row in rows} == set(candidate_by_id)
    for row in rows:
        candidate = candidate_by_id[row["candidate_id"]]
        assert row["source_key"] == candidate["source_key"]
        assert row["source_page"] == str(candidate["source_page"])
        assert row["question_number"] == candidate["question_number"]
        assert row["question_type"] == candidate["question_type_detected"]
        assert row["problem_type_code"] == candidate["problem_type_code"]
        assert row["review_status"] == "NOT_REVIEWED"


def test_semantic_aggregate_is_deterministic_and_validator_is_read_only() -> None:
    validator = GroupedDataDispersionMaterializationValidator()
    before = {
        name: hashlib.sha256(
            (DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH / name).read_bytes()
        ).hexdigest()
        for name in (*SEMANTIC_FILES, "review_queue.csv")
    }

    first = validator.validate()
    second = validator.validate()

    after = {
        name: hashlib.sha256(
            (DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH / name).read_bytes()
        ).hexdigest()
        for name in (*SEMANTIC_FILES, "review_queue.csv")
    }
    assert first.as_dict() == second.as_dict()
    assert first.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert before == after


def test_aggregate_fails_when_file_hash_is_updated_without_aggregate(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    candidates = _load("candidate_questions.json", root)
    candidates[0]["raw_question_text"] += " MUTATED"
    _write_json(root, "candidate_questions.json", candidates)

    manifest = _load("materialization_manifest.json", root)
    manifest["semantic_file_hashes"]["candidate_questions.json"] = (
        GroupedDataDispersionMaterializationValidator.semantic_sha256(candidates)
    )
    _write_json(root, "materialization_manifest.json", manifest)

    report = GroupedDataDispersionMaterializationValidator().validate(root)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is False
    assert "AGGREGATE_SEMANTIC_SHA256_MISMATCH" in {
        error.code for error in report.errors
    }


def test_validator_rejects_unknown_taxonomy_mapping(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    candidates = _load("candidate_questions.json", root)
    candidates[0]["problem_type_code"] = "UNKNOWN_PROBLEM_TYPE"
    _write_json(root, "candidate_questions.json", candidates)

    report = GroupedDataDispersionMaterializationValidator().validate(root)

    assert report.checks["taxonomy_mappings"] is False
    assert "UNKNOWN_PROBLEM_TYPE" in {error.code for error in report.errors}


def test_validator_rejects_trusted_tf_answer(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    groups = _load("question_group_candidates.json", root)
    groups[0]["items"][0]["correct_answer"] = True
    groups[0]["items"][0]["answer_status"] = "SOURCE_BACKED"
    _write_json(root, "question_group_candidates.json", groups)

    report = GroupedDataDispersionMaterializationValidator().validate(root)

    assert report.checks["question_groups"] is False
    assert "INVALID_UNREVIEWED_CHILD" in {error.code for error in report.errors}


def test_validator_rejects_split_group_projection(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    standalone = _load("standalone_candidates.json", root)
    candidates = _load("candidate_questions.json", root)
    standalone.append(
        next(row for row in candidates if row["requires_question_group_model"])
    )
    _write_json(root, "standalone_candidates.json", standalone)

    report = GroupedDataDispersionMaterializationValidator().validate(root)

    assert report.checks["question_groups"] is False
    assert report.checks["standalone_projection"] is False
    assert "GROUP_SOURCE_IN_STANDALONE" in {error.code for error in report.errors}


def test_validator_rejects_source_lock_and_rights_changes(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    verification = _load("source_hash_verification.json", root)
    verification["sources"][0]["actual_sha256"] = "0" * 64
    _write_json(root, "source_hash_verification.json", verification)
    policy = _load("materialization_policy.json", root)
    policy["rights_status"] = "CLEARED"
    _write_json(root, "materialization_policy.json", policy)

    report = GroupedDataDispersionMaterializationValidator().validate(root)

    assert report.checks["source_registry"] is False
    assert report.checks["visual_rights_boundary"] is False
    assert "SOURCE_LOCK_MISMATCH" in {error.code for error in report.errors}


def test_no_pdf_migration_import_snapshot_or_synthetic_gap_fill() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH
    manifest = _load("materialization_manifest.json")
    policy = _load("materialization_policy.json")

    assert not list(root.rglob("*.pdf"))
    assert manifest["db_migration_required"] is False
    assert manifest["database_import_allowed"] is False
    assert manifest["canonical_snapshot_allowed"] is False
    assert manifest["production_release_eligible"] == 0
    assert policy["no_synthetic_gap_fill"] is True
    assert policy["scope"]["exclude_standalone"] == [
        "grouped mean only",
        "median only",
        "mode only",
        "Q1/Q2/Q3 only",
        "median-group only",
        "probability-only",
    ]


def test_data019_vector_and_derivative_regressions_remain_green() -> None:
    curriculum = GroupedDataDispersionStagingValidator().validate()
    vector_materialization = VectorQuestionMaterializationValidator().validate()
    vector_review = VectorAcademicReviewValidator().validate()
    vector_promotion = VectorVisualPromotionValidator().validate()
    derivative_review = QuestionGroupReviewValidator().validate()
    derivative_visual = QuestionGroupVisualAssetValidator().validate()
    derivative_promotion = QuestionGroupPromotionValidator().validate()

    assert curriculum.is_valid
    assert curriculum.content_sha256 == EXPECTED_GROUPED_DATA_DISPERSION_CONTENT_SHA256
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


def test_materialization_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out
    assert first == second
