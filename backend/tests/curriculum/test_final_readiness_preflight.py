from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from app.curriculum.derivative_candidate import (
    DerivativeCurriculumCandidateValidator,
)
from app.curriculum.final_readiness import (
    DEFAULT_FINAL_READINESS_PATH,
    EXPECTED_FINAL_READINESS_AGGREGATE_SHA256,
    EXPECTED_INPUT_OVERLAYS,
    FinalPreflightComposer,
    FinalReadinessValidator,
)
from app.curriculum.full_scope_alignment import (
    DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    EXPECTED_ALIGNMENT_AGGREGATE_SHA256,
    EXPECTED_ENRICHED_PREVIEW_FINGERPRINT,
    REPO_ROOT,
    FullScopeAlignmentValidator,
)
from app.curriculum.full_scope_audit import FullScopeAuditValidator
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.schema_enrichment import (
    DEFAULT_SCHEMA_ENRICHMENT_PATH,
    EXPECTED_BASE_REPO_COMMIT,
    EXPECTED_ENRICHMENT_AGGREGATE_SHA256,
    SchemaEnrichmentValidator,
)
from app.questions.conditional_probability_academic_review import (
    ConditionalProbabilityAcademicReviewValidator,
)
from app.questions.core_evidence_closure import (
    DEFAULT_CORE_EVIDENCE_CLOSURE_PATH,
    EXPECTED_CORE_EVIDENCE_CLOSURE_AGGREGATE_SHA256,
    EXPECTED_TREE_ASSET_HEIGHT,
    EXPECTED_TREE_ASSET_SHA256,
    EXPECTED_TREE_ASSET_WIDTH,
    CoreEvidenceClosureValidator,
)
from app.questions.derivative_release_exclusion import (
    DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH,
    EXPECTED_RELEASE_EXCLUSION_AGGREGATE_SHA256,
    DerivativeReleaseExclusionValidator,
)
from app.questions.grouped_data_dispersion_academic_review import (
    GroupedDataDispersionAcademicReviewValidator,
)
from app.questions.integrals_academic_review import (
    IntegralsAcademicReviewValidator,
)
from app.questions.oxyz_academic_review import (
    OxyzAcademicReviewValidator,
)
from app.questions.vector_academic_review import (
    VectorAcademicReviewValidator,
)
from app.validate_final_readiness import main, validate_all_final_readiness


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, val: Any) -> None:
    path.write_text(json.dumps(val, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


# ----------------------------------------------------------------------
# 1. DATA-MATH12-034 Schema Enrichment Tests
# ----------------------------------------------------------------------

def test_schema_enrichment_validator_reports_exact_data_state() -> None:
    report = SchemaEnrichmentValidator().validate()

    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_ENRICHMENT_AGGREGATE_SHA256
    assert report.base_repo_commit == EXPECTED_BASE_REPO_COMMIT
    assert report.enriched_preview_fingerprint == EXPECTED_ENRICHED_PREVIEW_FINGERPRINT
    assert report.blockers_before == 41
    assert report.blockers_after == 0
    assert report.counts == {
        "problem_types_enrichment": 16,
        "concepts_enrichment": 16,
        "learning_outcomes_enrichment": 15,
        "total_enrichment_records": 47,
    }
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False
    assert report.activation_allowed is False
    assert report.production_release_allowed is False
    assert all(report.checks.values())
    assert len(report.errors) == 0


# ----------------------------------------------------------------------
# 2. DATA-MATH12-035 Core Evidence Closure Tests
# ----------------------------------------------------------------------

def test_core_evidence_closure_validator_reports_exact_data_state() -> None:
    report = CoreEvidenceClosureValidator().validate()

    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_CORE_EVIDENCE_CLOSURE_AGGREGATE_SHA256
    assert report.base_repo_commit == EXPECTED_BASE_REPO_COMMIT
    assert report.tree_asset_sha256 == EXPECTED_TREE_ASSET_SHA256
    assert report.tree_asset_dimensions == (EXPECTED_TREE_ASSET_WIDTH, EXPECTED_TREE_ASSET_HEIGHT)
    assert report.official_requirements_covered_after == 20
    assert report.official_requirements_partial_after == 0
    assert report.counts == {
        "source_backed_evidence_units_added": 2,
        "synthetic_questions_added": 0,
        "official_requirements_covered": 20,
        "official_requirements_partial": 0,
        "official_requirements_total": 20,
    }
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_write_allowed is False
    assert all(report.checks.values())
    assert len(report.errors) == 0


def test_core_evidence_closure_specific_semantics() -> None:
    path = DEFAULT_CORE_EVIDENCE_CLOSURE_PATH
    stats = _load_json(path / "grouped_statistics_interpretation_evidence.json")
    prob = _load_json(path / "probability_tree_evidence.json")
    gaps = _load_json(path / "derived_gap_reclassification.json")

    # Grouped stats assertions
    assert stats["source"]["source_type"] == "REAL_GRADE12_PDF_WEB_SOURCE"
    assert stats["source_semantics"]["statement_claim"] == "Dũng is more consistent than Huy."
    assert stats["source_semantics"]["source_answer"] is False
    assert stats["source_semantics"]["source_computed_standard_deviation"]["Dung"] == 0.26
    assert stats["source_semantics"]["source_computed_standard_deviation"]["Huy"] == 0.24

    # Probability tree assertions
    assert prob["source"]["source_code"] == "SRC_OFFICIAL_EXAM_2025_SOLUTION"
    assert prob["source"]["source_pdf_sha256"] == "90d5cb68a6f91418287c6643548f4f40ea9bb1598705a177b41bce07b09df11f"
    assert prob["source"]["question_page_1_based"] == 53
    assert prob["source"]["solution_visual_page_1_based"] == 54
    assert prob["source"]["source_answer_pattern"] == [True, False, True, True]

    # Reclassification non-blocking gap assertions
    expected_gaps = [
        "PARAMETER_FROM_GROUPED_VARIANCE_SD",
        "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
    ]
    assert gaps["grouped_data_dispersion"]["remaining_derived_enhancement_gaps"] == expected_gaps


# ----------------------------------------------------------------------
# 3. DATA-MATH12-036 Derivative Release Exclusion Tests
# ----------------------------------------------------------------------

def test_derivative_release_exclusion_validator_reports_exact_data_state() -> None:
    report = DerivativeReleaseExclusionValidator().validate()

    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_RELEASE_EXCLUSION_AGGREGATE_SHA256
    assert report.base_repo_commit == EXPECTED_BASE_REPO_COMMIT
    assert report.group_candidate_id == "M12_DERIV_GROUP_0012"
    assert report.academic_review_status == "VERIFIED_RETAINED"
    assert report.decision == "EXCLUDE_FROM_CANONICAL_PROMOTION_SET"
    assert report.verified_groups_total == 39
    assert report.groups_in_candidate_promotion_set == 38
    assert report.children_in_candidate_promotion_set == 152
    assert report.excluded_visual_groups == ("M12_DERIV_GROUP_0012",)
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_write_allowed is False
    assert all(report.checks.values())
    assert len(report.errors) == 0


# ----------------------------------------------------------------------
# 4. DATA-MATH12-037 Final Readiness Tests
# ----------------------------------------------------------------------

def test_final_readiness_validator_reports_exact_data_state() -> None:
    report = FinalReadinessValidator().validate()

    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_FINAL_READINESS_AGGREGATE_SHA256
    assert report.base_repo_commit == EXPECTED_BASE_REPO_COMMIT
    assert report.academic_data_blockers == 0
    assert report.canonical_snapshot_candidate_allowed is True
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False
    assert len(report.remaining_external_blockers) == 3
    assert "RIGHTS_REVIEW_REQUIRED" in report.remaining_external_blockers
    assert all(report.checks.values())
    assert len(report.errors) == 0


# ----------------------------------------------------------------------
# 5. Preflight Composer Tests
# ----------------------------------------------------------------------

def test_preflight_composer_runs_read_only_and_validates_all_import_schemas() -> None:
    preflight = FinalPreflightComposer.run_preflight()

    assert preflight.is_valid, [e.message for e in preflight.errors]
    assert preflight.status == "PASS"
    assert preflight.mode == "DRY_RUN_ONLY"
    assert preflight.fingerprint == EXPECTED_ENRICHED_PREVIEW_FINGERPRINT
    assert preflight.database_writes_attempted == 0
    assert preflight.canonical_files_written == 0
    assert preflight.rights_status == "REVIEW_REQUIRED"
    assert preflight.academic_data_blockers == 0

    # Curriculum graph counts
    assert preflight.curriculum_counts == {
        "chapters": 5,
        "topics": 24,
        "problem_types": 75,
        "concepts": 89,
        "learning_outcomes": 34,
        "concept_relations": 93,
        "problem_type_concepts": 200,
        "problem_type_learning_outcomes": 82,
        "cross_scope_relations": 11,
        "official_scope_bindings": 5,
        "learning_outcome_requirement_bindings": 34,
        "enrichment_blockers": 0,
    }

    # Question promotion counts
    assert preflight.question_promotion_counts == {
        "derivative_candidate_promotion_groups": 38,
        "derivative_candidate_promotion_children": 152,
        "derivative_candidate_excluded_groups": 1,
        "core_evidence_units_added": 2,
        "hold_or_rejected_questions_included": 0,
    }

    # All 8 schema checks passed
    assert all(preflight.schema_validations_passed.values())
    assert set(preflight.schema_validations_passed.keys()) == {
        "ChapterRecord",
        "TopicRecord",
        "ProblemTypeRecord",
        "ConceptRecord",
        "LearningOutcomeRecord",
        "ConceptRelationRecord",
        "ProblemTypeConceptRecord",
        "ProblemTypeOutcomeRecord",
    }

    # All foreign key integrity checks passed
    assert all(preflight.integrity_checks.values())


def test_curriculum_import_service_is_never_invoked() -> None:
    with patch.object(CurriculumImportService, "__init__", side_effect=AssertionError("CRITICAL: CurriculumImportService MUST NOT BE CALLED")):
        # 1. Run all validators
        val_034 = SchemaEnrichmentValidator().validate()
        val_035 = CoreEvidenceClosureValidator().validate()
        val_036 = DerivativeReleaseExclusionValidator().validate()
        val_037 = FinalReadinessValidator().validate()

        assert val_034.is_valid
        assert val_035.is_valid
        assert val_036.is_valid
        assert val_037.is_valid

        # 2. Run preflight
        preflight = FinalPreflightComposer.run_preflight()
        assert preflight.is_valid

        # 3. Run full CLI validation
        results = validate_all_final_readiness()
        assert results["status"] == "PASS"


# ----------------------------------------------------------------------
# 6. CLI Entrypoint Tests
# ----------------------------------------------------------------------

def test_cli_returns_success_and_valid_report(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    assert exit_code == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "PASS"
    assert payload["summary"]["academic_or_data_blockers_remaining"] == 0
    assert payload["summary"]["database_import_allowed"] is False
    assert payload["summary"]["canonical_write_allowed"] is False
    assert payload["summary"]["production_release_allowed"] is False
    assert payload["summary"]["rights_status"] == "REVIEW_REQUIRED"
    assert payload["summary"]["enriched_fingerprint"] == EXPECTED_ENRICHED_PREVIEW_FINGERPRINT


# ----------------------------------------------------------------------
# 7. Mutation Rejection Tests
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "dataset_type,file_name,mutate,expected_code",
    [
        # DATA-034 mutations
        (
            "034",
            "data_contract.json",
            lambda v: v.__setitem__("aggregate_semantic_sha256", "0" * 64),
            "CONTRACT_AGGREGATE_MISMATCH",
        ),
        (
            "034",
            "data_contract.json",
            lambda v: v.__setitem__("base_repo_commit", "deadbeef" * 5),
            "BASE_REPO_COMMIT_MISMATCH",
        ),
        (
            "034",
            "data_contract.json",
            lambda v: v.__setitem__("canonical_write_allowed", True),
            "CANONICAL_WRITE_NOT_BLOCKED",
        ),
        (
            "034",
            "data_contract.json",
            lambda v: v.__setitem__("database_import_allowed", True),
            "DATABASE_IMPORT_NOT_BLOCKED",
        ),
        (
            "034",
            "enrichment_manifest.json",
            lambda v: v.__setitem__("activation_allowed", True),
            "ACTIVATION_NOT_BLOCKED",
        ),
        (
            "034",
            "problem_types_enrichment.json",
            lambda v: v.pop(0),
            "PROBLEM_TYPE_ENRICHMENT_COUNT_MISMATCH",
        ),
        # DATA-035 mutations
        (
            "035",
            "data_contract.json",
            lambda v: v.__setitem__("aggregate_semantic_sha256", "0" * 64),
            "CONTRACT_AGGREGATE_MISMATCH",
        ),
        (
            "035",
            "data_contract.json",
            lambda v: v.__setitem__("database_import_allowed", True),
            "DATABASE_IMPORT_NOT_BLOCKED",
        ),
        (
            "035",
            "evidence_manifest.json",
            lambda v: v.__setitem__("rights_status", "APPROVED"),
            "RIGHTS_NOT_REVIEW_REQUIRED",
        ),
        (
            "035",
            "evidence_manifest.json",
            lambda v: v.__setitem__("production_release_eligible", 1),
            "PRODUCTION_RELEASE_ELIGIBLE_VIOLATION",
        ),
        (
            "035",
            "grouped_statistics_interpretation_evidence.json",
            lambda v: v["source_semantics"].__setitem__("source_answer", True),
            "INVALID_SOURCE_ANSWER",
        ),
        (
            "035",
            "grouped_statistics_interpretation_evidence.json",
            lambda v: v["source_semantics"]["source_computed_standard_deviation"].__setitem__("Dung", 0.99),
            "INVALID_SD_VALUES",
        ),
        (
            "035",
            "probability_tree_evidence.json",
            lambda v: v["source"].__setitem__("source_answer_pattern", [False, False, False, False]),
            "INVALID_SOURCE_ANSWER_PATTERN",
        ),
        (
            "035",
            "probability_tree_evidence.json",
            lambda v: v["tree_asset"].__setitem__("width", 999),
            "DECLARED_TREE_DIMENSIONS_MISMATCH",
        ),
        # DATA-036 mutations
        (
            "036",
            "data_contract.json",
            lambda v: v.__setitem__("aggregate_semantic_sha256", "0" * 64),
            "CONTRACT_AGGREGATE_MISMATCH",
        ),
        (
            "036",
            "release_exclusion.json",
            lambda v: v.__setitem__("decision", "PROMOTE_ANYWAY"),
            "INVALID_DECISION",
        ),
        (
            "036",
            "release_exclusion.json",
            lambda v: v["promotion_effect"].__setitem__("groups_in_candidate_promotion_set", 39),
            "PROMOTION_GROUPS_MISMATCH",
        ),
        (
            "036",
            "release_exclusion.json",
            lambda v: v.__setitem__("database_import_allowed", True),
            "DATABASE_IMPORT_NOT_BLOCKED",
        ),
        # DATA-037 mutations
        (
            "037",
            "data_contract.json",
            lambda v: v.__setitem__("aggregate_semantic_sha256", "0" * 64),
            "CONTRACT_AGGREGATE_MISMATCH",
        ),
        (
            "037",
            "final_readiness.json",
            lambda v: v.__setitem__("academic_data_blockers", 5),
            "ACADEMIC_DATA_BLOCKERS_NOT_ZERO",
        ),
        (
            "037",
            "postgres_import_preflight_contract.json",
            lambda v: v.__setitem__("mode", "LIVE_EXECUTION"),
            "INVALID_PREFLIGHT_MODE",
        ),
        (
            "037",
            "issue_register.json",
            lambda v: v.__setitem__("academic_or_data_blockers_remaining", 2),
            "ACADEMIC_BLOCKERS_REMAINING",
        ),
    ],
)
def test_mutations_are_rejected(
    tmp_path: Path,
    dataset_type: str,
    file_name: str,
    mutate: Callable[[Any], None],
    expected_code: str,
) -> None:
    if dataset_type == "034":
        src = DEFAULT_SCHEMA_ENRICHMENT_PATH
        dst = tmp_path / "034"
        shutil.copytree(src, dst)
        payload = _load_json(dst / file_name)
        mutate(payload)
        _write_json(dst / file_name, payload)
        report = SchemaEnrichmentValidator().validate(enrichment_path=dst)
        assert not report.is_valid
        assert expected_code in _codes(report), f"Expected {expected_code} in {_codes(report)}"

    elif dataset_type == "035":
        src = DEFAULT_CORE_EVIDENCE_CLOSURE_PATH
        dst = tmp_path / "035"
        shutil.copytree(src, dst)
        payload = _load_json(dst / file_name)
        mutate(payload)
        _write_json(dst / file_name, payload)
        report = CoreEvidenceClosureValidator().validate(evidence_path=dst)
        assert not report.is_valid
        assert expected_code in _codes(report), f"Expected {expected_code} in {_codes(report)}"

    elif dataset_type == "036":
        src = DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH
        dst = tmp_path / "036"
        shutil.copytree(src, dst)
        payload = _load_json(dst / file_name)
        mutate(payload)
        _write_json(dst / file_name, payload)
        report = DerivativeReleaseExclusionValidator().validate(exclusion_path=dst)
        assert not report.is_valid
        assert expected_code in _codes(report), f"Expected {expected_code} in {_codes(report)}"

    elif dataset_type == "037":
        src = DEFAULT_FINAL_READINESS_PATH
        dst = tmp_path / "037"
        shutil.copytree(src, dst)
        payload = _load_json(dst / file_name)
        mutate(payload)
        _write_json(dst / file_name, payload)
        report = FinalReadinessValidator().validate(readiness_path=dst)
        assert not report.is_valid
        assert expected_code in _codes(report), f"Expected {expected_code} in {_codes(report)}"


# ----------------------------------------------------------------------
# 8. Full Repository Regression Test
# ----------------------------------------------------------------------

def test_full_repository_regression_all_validators_healthy() -> None:
    validators: list[tuple[str, Any]] = [
        ("FullScopeAuditValidator (DATA-032)", FullScopeAuditValidator()),
        ("FullScopeAlignmentValidator (DATA-033)", FullScopeAlignmentValidator()),
        ("SchemaEnrichmentValidator (DATA-034)", SchemaEnrichmentValidator()),
        ("CoreEvidenceClosureValidator (DATA-035)", CoreEvidenceClosureValidator()),
        ("DerivativeReleaseExclusionValidator (DATA-036)", DerivativeReleaseExclusionValidator()),
        ("FinalReadinessValidator (DATA-037)", FinalReadinessValidator()),
        ("DerivativeCurriculumCandidateValidator", DerivativeCurriculumCandidateValidator()),
        ("VectorAcademicReviewValidator", VectorAcademicReviewValidator()),
        ("GroupedDataDispersionAcademicReviewValidator", GroupedDataDispersionAcademicReviewValidator()),
        ("IntegralsAcademicReviewValidator", IntegralsAcademicReviewValidator()),
        ("OxyzAcademicReviewValidator", OxyzAcademicReviewValidator()),
        ("ConditionalProbabilityAcademicReviewValidator", ConditionalProbabilityAcademicReviewValidator()),
    ]

    for name, val in validators:
        report = val.validate()
        assert report.is_valid, f"{name} failed regression: {getattr(report, 'errors', None)}"
