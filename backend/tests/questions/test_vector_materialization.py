from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from app.curriculum.grade12_scope import Grade12ScopeValidator
from app.curriculum.vector_staging import (
    EXPECTED_VECTOR_CONTENT_SHA256,
    EXPECTED_VECTOR_COUNTS,
    VectorCurriculumStagingValidator,
)
from app.questions.group_import_service import TrustedQuestionGroupImportService
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_staging import EXPECTED_RAW_CANDIDATE_SHA256
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.questions.vector_materialization import (
    DEFAULT_VECTOR_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    EXPECTED_BOUNDARY_HOLD_IDS,
    EXPECTED_COUNTS,
    EXPECTED_EFFECTIVE_REVIEW_COUNTS,
    EXPECTED_EXCLUDED_IDS,
    EXPECTED_SCOPE_DECISIONS,
    EXPECTED_SOURCE_LOCKS,
    SEMANTIC_FILES,
    VectorQuestionMaterializationValidator,
)
from app.questions.vector_source_staging import VectorQuestionSourceValidator
from app.validate_vector_materialization import main


RAW_CANDIDATE_SEMANTIC_SHA256 = (
    "1b364f145fcd6110ba99ee32dc91928a5d3909eac3347e315c40bd7e73fee1ab"
)


def _load_list(
    name: str, root: Path = DEFAULT_VECTOR_MATERIALIZATION_PATH
) -> list[dict]:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _load_object(
    name: str, root: Path = DEFAULT_VECTOR_MATERIALIZATION_PATH
) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _review_queue_ids(
    root: Path = DEFAULT_VECTOR_MATERIALIZATION_PATH,
) -> list[str]:
    with (root / "review_queue.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        return [row["candidate_id"] for row in csv.DictReader(handle)]


def test_manifest_semantic_hashes_and_direct_aggregate_are_deterministic() -> None:
    validator = VectorQuestionMaterializationValidator()
    first = validator.validate()
    second = validator.validate()
    manifest = _load_object("materialization_manifest.json")

    assert first.is_valid, first.as_dict()
    assert first.as_dict() == second.as_dict()
    assert validator.aggregate_semantic_sha256(
        DEFAULT_VECTOR_MATERIALIZATION_PATH
    ) == validator.aggregate_semantic_sha256(DEFAULT_VECTOR_MATERIALIZATION_PATH)
    assert first.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert manifest["aggregate_semantic_sha256"] == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert list(manifest["semantic_file_hashes"]) == list(SEMANTIC_FILES)
    assert {
        name: validator.semantic_sha256(
            json.loads(
                (DEFAULT_VECTOR_MATERIALIZATION_PATH / name).read_text(
                    encoding="utf-8"
                )
            )
        )
        for name in SEMANTIC_FILES
    } == manifest["semantic_file_hashes"]


def test_raw_and_effective_counts_remain_distinct() -> None:
    report = VectorQuestionMaterializationValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts["raw"] == {
        "raw_included_occurrences": 132,
        "materialized_unique_candidates": 72,
        "standalone_candidates": 58,
        "true_false_four_groups": 14,
        "structural_holds": 0,
        "question_type_counts": {
            "MULTIPLE_CHOICE": 54,
            "TRUE_FALSE_GROUP": 14,
            "SHORT_ANSWER": 4,
        },
        "visual_required_count": 53,
        "answer_detected_count": 47,
        "mixed_scope_group_count": 12,
        "problem_types_total": 15,
        "problem_types_with_candidates": 9,
        "production_release_eligible": 0,
    }
    assert report.counts["scope"] == {"excluded": 3, "boundary_holds": 1}
    assert report.counts["effective"] == EXPECTED_EFFECTIVE_REVIEW_COUNTS
    assert _load_object("extraction_stats.json") == EXPECTED_COUNTS
    assert _load_object("materialization_manifest.json")["counts"] == EXPECTED_COUNTS


def test_scope_overlay_has_exact_ids_decisions_and_safety_policy() -> None:
    overlay = _load_object("scope_review_overrides.json")
    decisions = overlay["decisions"]

    assert {
        row["candidate_id"]: row["decision"] for row in decisions
    } == EXPECTED_SCOPE_DECISIONS
    assert len({row["candidate_id"] for row in decisions}) == 4
    assert tuple(
        row["candidate_id"]
        for row in decisions
        if row["decision"].startswith("EXCLUDE_")
    ) == EXPECTED_EXCLUDED_IDS
    assert tuple(
        row["candidate_id"]
        for row in decisions
        if row["decision"].startswith("HOLD_")
    ) == EXPECTED_BOUNDARY_HOLD_IDS
    assert all(overlay["policy"].values())


def test_effective_files_are_exact_filtered_raw_projections() -> None:
    validator = VectorQuestionMaterializationValidator()
    raw = _load_list("candidate_questions.json")
    raw_standalone = _load_list("standalone_candidates.json")
    effective = _load_list("effective_candidates.json")
    effective_standalone = _load_list("effective_standalone_candidates.json")
    blocked = set(EXPECTED_SCOPE_DECISIONS)

    assert validator.semantic_sha256(raw) == RAW_CANDIDATE_SEMANTIC_SHA256
    assert len(raw) == 72
    assert effective == [row for row in raw if row["candidate_id"] not in blocked]
    assert effective_standalone == [
        row for row in raw_standalone if row["candidate_id"] not in blocked
    ]
    assert len(effective) == 68
    assert len(effective_standalone) == 54
    assert blocked.isdisjoint({row["candidate_id"] for row in effective})


def test_review_queue_contains_each_effective_id_once() -> None:
    effective_ids = [
        row["candidate_id"] for row in _load_list("effective_candidates.json")
    ]
    queue_ids = _review_queue_ids()

    assert len(queue_ids) == len(set(queue_ids)) == 68
    assert queue_ids == effective_ids
    assert set(EXPECTED_SCOPE_DECISIONS).isdisjoint(queue_ids)


def test_raw_candidate_ids_dedupe_and_provenance_remain_unchanged() -> None:
    candidates = _load_list("candidate_questions.json")
    ids = [row["candidate_id"] for row in candidates]
    hashes = [row["dedupe_hash"] for row in candidates]

    assert ids == [f"M12_VECTOR_CAND_{number:04d}" for number in range(1, 73)]
    assert len(hashes) == len(set(hashes)) == 72
    assert all(row["duplicate_occurrences"] for row in candidates)


def test_source_ids_hashes_pages_and_duplicate_occurrences_are_locked() -> None:
    candidates = _load_list("candidate_questions.json")
    verification = _load_object("source_hash_verification.json")["sources"]

    assert set(verification) == set(EXPECTED_SOURCE_LOCKS)
    for row in candidates:
        lock = EXPECTED_SOURCE_LOCKS[row["source_code"]]
        assert row["source_key"] == lock["source_key"]
        assert row["source_file_id"] == lock["file_id"]
        assert row["source_sha256"] == lock["sha256"]
        assert 1 <= row["source_page"] <= lock["page_count"]
        for occurrence in row["duplicate_occurrences"]:
            occurrence_lock = EXPECTED_SOURCE_LOCKS[occurrence["source_code"]]
            assert occurrence["source_file_id"] == occurrence_lock["file_id"]
            assert occurrence["source_sha256"] == occurrence_lock["sha256"]
            assert 1 <= occurrence["source_page"] <= occurrence_lock["page_count"]


def test_taxonomy_stays_provisional_and_matches_data_015() -> None:
    candidates = _load_list("candidate_questions.json")
    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    curriculum_root = (
        Path(__file__).resolve().parents[2]
        / "data/curriculum/math/grade12/gdpt2018/staging/vector_coordinates_v0_1"
    )
    concept_rows = json.loads(
        (curriculum_root / "problem_type_concepts.json").read_text(encoding="utf-8")
    )
    outcome_rows = json.loads(
        (curriculum_root / "problem_type_learning_outcomes.json").read_text(
            encoding="utf-8"
        )
    )

    for row in candidates:
        code = row["problem_type_code"]
        assert row["concepts"] == [
            item for item in concept_rows if item["problem_type_code"] == code
        ]
        assert row["learning_outcomes"] == [
            item for item in outcome_rows if item["problem_type_code"] == code
        ]
        assert row["classification_method"] == "RULE_BASED_INITIAL_FROM_SOURCE_TEXT"
    assert candidate_by_id["M12_VECTOR_CAND_0008"]["problem_type_code"] == (
        "VECTOR_RELATION_IDENTIFICATION_3D"
    )
    assert candidate_by_id["M12_VECTOR_CAND_0011"]["problem_type_code"] == (
        "VECTOR_RELATION_IDENTIFICATION_3D"
    )
    assert candidate_by_id["M12_VECTOR_CAND_0066"]["problem_type_code"] == (
        "VECTOR_GEOMETRIC_DECOMPOSITION_3D"
    )


def test_all_true_false_groups_remain_atomic_unanswered_and_effective() -> None:
    raw = _load_list("candidate_questions.json")
    effective = _load_list("effective_candidates.json")
    effective_standalone = _load_list("effective_standalone_candidates.json")
    groups = _load_list("question_group_candidates.json")
    effective_ids = {row["candidate_id"] for row in effective}
    standalone_ids = {row["candidate_id"] for row in effective_standalone}

    assert len(groups) == 14
    assert sum(group["mixed_scope"] for group in groups) == 12
    assert {group["source_candidate_id"] for group in groups} <= effective_ids
    assert {group["source_candidate_id"] for group in groups}.isdisjoint(
        standalone_ids
    )
    assert {group["source_candidate_id"] for group in groups} == {
        row["candidate_id"]
        for row in raw
        if row["question_type_detected"] == "TRUE_FALSE_GROUP"
    }
    for group in groups:
        assert group["group_type"] == "TRUE_FALSE_FOUR"
        assert group["group_context"].strip()
        assert [item["label"] for item in group["items"]] == ["a", "b", "c", "d"]
        assert [item["order_index"] for item in group["items"]] == [0, 1, 2, 3]
        assert all(item["correct_answer"] is None for item in group["items"])
        assert all(item["answer_status"] == "UNREVIEWED" for item in group["items"])
        assert all(
            item["taxonomy_status"] == "NOT_REVIEWED" for item in group["items"]
        )


def test_effective_review_boundaries_and_counts_are_locked() -> None:
    effective = _load_list("effective_candidates.json")
    stats = _load_object("effective_review_stats.json")

    assert stats["effective_review_counts"] == EXPECTED_EFFECTIVE_REVIEW_COUNTS
    assert all(row["status"] == "STRUCTURAL_CANDIDATE" for row in effective)
    assert all(row["academic_review_status"] == "NOT_REVIEWED" for row in effective)
    assert all(row["promotion_eligible"] is False for row in effective)
    assert all("correct_answer" not in row for row in effective)
    assert stats["database_import_allowed"] is False
    assert stats["canonical_snapshot_allowed"] is False


def test_exact_six_coverage_gaps_rights_and_no_source_pdf() -> None:
    report = VectorQuestionMaterializationValidator().validate()
    coverage = _load_list("coverage_report.json")
    # This dataset must not ship PDFs. A developer may keep an unrelated,
    # untracked OCR test PDF at the workspace root; that is outside this bundle.
    dataset_root = DEFAULT_VECTOR_MATERIALIZATION_PATH.parents[1]

    assert report.problem_type_gaps == tuple(EXPECTED_COUNTS["problem_type_gaps"])
    assert [
        row["problem_type_code"]
        for row in coverage
        if row["coverage_status"] == "GAP"
    ] == EXPECTED_COUNTS["problem_type_gaps"]
    assert not any(
        path.suffix.lower() == ".pdf"
        for path in dataset_root.rglob("*")
    )
    assert report.rights_status == "REVIEW_REQUIRED"


def test_mutated_file_with_updated_per_file_hash_still_fails_aggregate(
    tmp_path: Path,
) -> None:
    target = tmp_path / "materialized_v0_1"
    shutil.copytree(DEFAULT_VECTOR_MATERIALIZATION_PATH, target)
    candidates = _load_list("effective_candidates.json", target)
    candidates[0]["raw_question_text"] += " MUTATED"
    (target / "effective_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
    )
    manifest = _load_object("materialization_manifest.json", target)
    manifest["semantic_file_hashes"]["effective_candidates.json"] = (
        VectorQuestionMaterializationValidator.semantic_sha256(candidates)
    )
    (target / "materialization_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    report = VectorQuestionMaterializationValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is False
    assert any(
        error.code == "AGGREGATE_SEMANTIC_SHA256_MISMATCH"
        for error in report.errors
    )


def test_validator_rejects_taxonomy_mapping_mutation(tmp_path: Path) -> None:
    target = tmp_path / "materialized_v0_1"
    shutil.copytree(DEFAULT_VECTOR_MATERIALIZATION_PATH, target)
    candidates = _load_list("candidate_questions.json", target)
    candidates[0]["concepts"][0]["weight"] = 0.99
    (target / "candidate_questions.json").write_text(
        json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
    )

    report = VectorQuestionMaterializationValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["taxonomy_mappings"] is False
    assert report.checks["aggregate_integrity"] is False


def test_data_015_scope_taxonomy_and_source_regressions() -> None:
    scope = Grade12ScopeValidator().validate()
    taxonomy = VectorCurriculumStagingValidator().validate()
    sources = VectorQuestionSourceValidator().validate()

    assert scope.is_valid, scope.as_dict()
    assert taxonomy.is_valid, taxonomy.as_dict()
    assert taxonomy.counts == EXPECTED_VECTOR_COUNTS
    assert taxonomy.content_sha256 == EXPECTED_VECTOR_CONTENT_SHA256
    assert sources.is_valid, sources.as_dict()
    assert sources.rights_status == "REVIEW_REQUIRED"


def test_derivative_regression_invariants_and_draft_only_preview() -> None:
    review = QuestionGroupReviewValidator().validate()
    visual = QuestionGroupVisualAssetValidator().validate()
    promotion = QuestionGroupPromotionValidator().validate()
    preview = TrustedQuestionGroupImportService().preview()

    assert review.is_valid and review.counts["reviewed_groups"] == 67
    assert review.counts["target_groups"] == 67
    assert review.counts["verified"] == 39
    assert promotion.is_valid
    assert promotion.counts["canonical_snapshot_ready_groups"] == 38
    assert promotion.counts["canonical_snapshot_ready_children"] == 152
    assert promotion.counts["production_release_eligible_groups"] == 0
    assert visual.is_valid
    assert visual.counts["ready_source_crops"] == 8
    assert visual.counts["blocked_source_visual_missing"] == 1
    assert preview.raw_candidate_sha256 == EXPECTED_RAW_CANDIDATE_SHA256
    assert preview.counts["draft_groups"] == 38
    assert preview.counts["draft_children"] == 152
    assert preview.production_release_eligible == 0
    assert preview.database_import_ready is False
    assert {group.status for group in preview.groups} == {"DRAFT"}


def test_vector_materialization_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out

    assert first == second
    assert '"status": "PASS"' in first
