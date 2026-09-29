from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.curriculum.grade12_scope import (
    EXPECTED_GRADE12_CHAPTER_ORDER,
    Grade12ScopeValidator,
)
from app.questions.grouped_data_dispersion_source_staging import (
    DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH,
    EXPECTED_EXCLUSION_EXAMPLES,
    EXPECTED_INCLUDE_EXAMPLES,
    EXPECTED_SCAN_COUNTS,
    GroupedDataDispersionQuestionSourceValidator,
)
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.questions.vector_academic_review import VectorAcademicReviewValidator
from app.questions.vector_materialization import VectorQuestionMaterializationValidator
from app.questions.vector_source_staging import (
    EXPECTED_ANSWER_AUTHORITY,
    EXPECTED_PRIMARY_SOURCES,
)
from app.questions.vector_visual_promotion import VectorVisualPromotionValidator
from app.validate_grouped_data_dispersion_question_sources import main


def _load(name: str, root: Path = DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH):
    return json.loads((root / name).read_text(encoding="utf-8"))


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "source_staging"
    shutil.copytree(DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH, target)
    return target


def test_source_staging_preserves_exact_sources_rights_and_scan_counts() -> None:
    report = GroupedDataDispersionQuestionSourceValidator().validate()
    manifest = _load("source_manifest.json")

    assert report.is_valid, report.as_dict()
    assert all(report.checks.values())
    assert report.counts == {
        "primary_sources": 3,
        "answer_authorities": 1,
        "seed_sources": 3,
        "confirmed_include_examples": 5,
        "confirmed_exclusion_examples": 3,
    }
    assert {
        row["source_key"]: (row["drive_file_id"], row["sha256"])
        for row in manifest["primary_sources"]
    } == EXPECTED_PRIMARY_SOURCES
    authority = manifest["answer_authority"][0]
    assert (authority["drive_file_id"], authority["sha256"]) == (
        EXPECTED_ANSWER_AUTHORITY
    )
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.scan_counts == {
        source: {
            "raw_question_windows_with_dispersion_keywords": raw,
            "heuristic_unique_windows": unique,
        }
        for source, (raw, unique) in EXPECTED_SCAN_COUNTS.items()
    }


def test_scan_contract_preserves_scope_examples_and_atomic_groups() -> None:
    contract = _load("question_scan_contract.json")
    seed = _load("source_scan_seed.json")

    includes = tuple(
        (
            row["source_key"],
            row["source_page"],
            row["question_number"],
            row["suggested_problem_type"],
        )
        for row in seed["confirmed_include_examples"]
    )
    exclusions = tuple(
        (row["source_key"], row["source_page"], row["question_number"])
        for row in seed["confirmed_exclusion_examples"]
    )

    assert includes == EXPECTED_INCLUDE_EXAMPLES
    assert exclusions == EXPECTED_EXCLUSION_EXAMPLES
    assert contract["initial_status"] == "STRUCTURAL_CANDIDATE"
    assert contract["mixed_group_policy"] == {
        "rule": "Never split TRUE_FALSE_FOUR shared context during structural staging.",
        "action": (
            "Keep full group; mark mixed_scope=true when only some children assess "
            "Grade-12 dispersion."
        ),
    }
    assert "grouped-data mean only" in contract["exclude_primary_intents"]
    assert "grouped-data median only" in contract["exclude_primary_intents"]
    assert "grouped-data mode only" in contract["exclude_primary_intents"]


def test_source_staging_has_no_pdf_and_cannot_import_or_promote() -> None:
    report = GroupedDataDispersionQuestionSourceValidator().validate()

    assert not list(DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH.rglob("*.pdf"))
    assert report.production_eligible is False
    assert report.database_import_allowed is False
    assert _load("source_manifest.json")["status"] == "SOURCE_LOCK_CANDIDATE"
    assert _load("source_scan_seed.json")["status"] == "HEURISTIC_TRIAGE"


def test_validator_rejects_rights_hash_and_pdf_changes(tmp_path: Path) -> None:
    path = _copy(tmp_path)
    manifest = _load("source_manifest.json", path)
    manifest["rights_status"] = "CLEARED"
    manifest["primary_sources"][0]["sha256"] = "0" * 64
    (path / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    (path / "source.pdf").write_bytes(b"not a source pdf")

    report = GroupedDataDispersionQuestionSourceValidator().validate(path)

    assert report.status == "FAIL"
    assert report.checks["source_identity"] is False
    assert report.checks["rights_boundary"] is False
    assert report.checks["no_pdf_binaries"] is False


def test_scope_vector_and_derivative_regressions_remain_green() -> None:
    scope = Grade12ScopeValidator().validate()
    vector_materialization = VectorQuestionMaterializationValidator().validate()
    vector_review = VectorAcademicReviewValidator().validate()
    vector_promotion = VectorVisualPromotionValidator().validate()
    derivative_review = QuestionGroupReviewValidator().validate()
    derivative_visual = QuestionGroupVisualAssetValidator().validate()
    derivative_promotion = QuestionGroupPromotionValidator().validate()

    assert scope.is_valid
    assert scope.in_scope_chapters == EXPECTED_GRADE12_CHAPTER_ORDER
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


def test_source_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out
    assert first == second
