from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from app.curriculum.derivative_candidate import (
    DerivativeCurriculumCandidateValidator as DerivativeActivationGateValidator,
)
from app.curriculum.full_scope_audit import (
    AUDITED_REPO_HEAD_COMMIT,
    CURRICULUM_ROOT,
    DEFAULT_FULL_SCOPE_AUDIT_PATH,
    EXPECTED_AUDIT_AGGREGATE_SHA256,
    EXPECTED_CONTRACT_SEMANTIC_SHA256,
    EXPECTED_CORE_SCOPES,
    EXPECTED_CROSS_CUTTING,
    EXPECTED_GROUPED_DERIVED_GAPS,
    EXPECTED_GROUPED_INTERPRETATION_MAPPING,
    EXPECTED_INVARIANTS,
    EXPECTED_OPTIONAL_TOPICS,
    EXPECTED_SEMANTIC_HASHES,
    OFFICIAL_SCOPE_GIT_BLOB_SHA1,
    FullScopeAuditValidator,
)
from app.questions.conditional_probability_academic_review import (
    ConditionalProbabilityAcademicReviewValidator,
)
from app.questions.conditional_probability_gap_evidence import (
    ConditionalProbabilityGapEvidenceValidator,
)
from app.questions.grouped_data_dispersion_academic_review import (
    GroupedDataDispersionAcademicReviewValidator,
)
from app.questions.grouped_data_dispersion_gap_rescan import (
    GroupedDataDispersionGapRescanValidator,
)
from app.questions.grouped_data_dispersion_visual_assets import (
    GroupedDataDispersionVisualAssetValidator,
)
from app.questions.integrals_academic_review import (
    IntegralsAcademicReviewValidator,
)
from app.questions.integrals_gap_supplement import (
    IntegralsGapSupplementValidator,
)
from app.questions.integrals_visual_assets import (
    IntegralsVisualAssetValidator,
)
from app.questions.oxyz_academic_review import (
    OxyzAcademicReviewValidator,
)
from app.questions.oxyz_gap_supplement import (
    OxyzGapSupplementValidator,
)
from app.questions.oxyz_visual_assets import (
    OxyzVisualAssetValidator,
)
from app.questions.vector_academic_review import (
    VectorAcademicReviewValidator,
)
from app.validate_full_scope_audit import main


def _load(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, value: Any) -> None:
    (root / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "audit" / "v0_1"
    shutil.copytree(DEFAULT_FULL_SCOPE_AUDIT_PATH, destination)
    return destination


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_data_math12_032_state() -> None:
    report = FullScopeAuditValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_AUDIT_AGGREGATE_SHA256
    assert report.repo_head_commit == AUDITED_REPO_HEAD_COMMIT
    assert report.official_core_scopes_total == 5
    assert report.fully_evidenced_core_scopes == (
        "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
        "M12_CORE_CALCULUS_DERIVATIVE_APPLICATIONS",
        "M12_CORE_GEOMETRY_COORDINATE_3D",
    )
    assert report.partially_evidenced_core_scopes == (
        "M12_CORE_PROBABILITY_CONDITIONAL",
        "M12_CORE_STATISTICS_GROUPED_DATA",
    )
    assert report.missing_core_scopes == ()
    assert report.normalized_requirements_total == 20
    assert report.normalized_requirements_covered == 18
    assert report.normalized_requirements_partial == 2
    assert report.cross_cutting_materialized == 0
    assert report.optional_topics_materialized == 0
    assert report.production_release_ready is False
    assert report.activation_allowed is False
    assert report.counts == EXPECTED_INVARIANTS
    assert all(report.checks.values())
    assert len(report.errors) == 0


def test_repo_head_and_git_blob_bindings() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    contract = _load(root, "data_contract.json")
    snapshot = _load(root, "official_scope_snapshot.json")
    drift = _load(root, "curriculum_taxonomy_drift.json")

    assert contract["repo_head_commit"] == AUDITED_REPO_HEAD_COMMIT
    assert snapshot["repo_head_commit"] == AUDITED_REPO_HEAD_COMMIT
    actual_contract_hash = FullScopeAuditValidator._semantic_hash(
        root / "data_contract.json"
    )
    assert actual_contract_hash == EXPECTED_CONTRACT_SEMANTIC_SHA256
    assert contract["semantic_sha256"] == EXPECTED_SEMANTIC_HASHES
    assert drift["activation_allowed"] is False

    official_scope_file = CURRICULUM_ROOT / "official_scope.json"
    assert official_scope_file.is_file()
    actual_blob = FullScopeAuditValidator._git_blob_sha1(official_scope_file)
    assert actual_blob == OFFICIAL_SCOPE_GIT_BLOB_SHA1

    for field, file_name in [
        ("manifest_git_blob_sha1", "manifest.json"),
        ("chapters_git_blob_sha1", "chapters.json"),
        ("topics_git_blob_sha1", "topics.json"),
        ("problem_types_git_blob_sha1", "problem_types.json"),
        ("concepts_git_blob_sha1", "concepts.json"),
        ("learning_outcomes_git_blob_sha1", "learning_outcomes.json"),
    ]:
        target = CURRICULUM_ROOT / file_name
        assert target.is_file()
        expected = drift["repo_bindings"][field]
        actual = FullScopeAuditValidator._git_blob_sha1(target)
        assert actual == expected, f"{file_name}: expected {expected}, got {actual}"


def test_official_scope_snapshot_structure() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    snapshot = _load(root, "official_scope_snapshot.json")

    core = snapshot["core_program"]
    assert len(core) == 5
    assert tuple(row["official_scope_code"] for row in core) == EXPECTED_CORE_SCOPES

    expected_req_counts = {
        "M12_CORE_CALCULUS_DERIVATIVE_APPLICATIONS": 4,
        "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL": 4,
        "M12_CORE_GEOMETRY_COORDINATE_3D": 6,
        "M12_CORE_STATISTICS_GROUPED_DATA": 2,
        "M12_CORE_PROBABILITY_CONDITIONAL": 4,
    }
    for row in core:
        code = row["official_scope_code"]
        reqs = row["normalized_coverage"]
        assert len(reqs) == expected_req_counts[code], f"Scope {code} req count mismatch"

    total_requirements = sum(len(row["normalized_coverage"]) for row in core)
    assert total_requirements == 20

    cross = snapshot["cross_cutting"]
    assert len(cross) == 2
    assert tuple(row["official_scope_code"] for row in cross) == EXPECTED_CROSS_CUTTING

    opt = snapshot["optional_study_topics"]
    assert len(opt) == 3
    assert tuple(row["official_scope_code"] for row in opt) == EXPECTED_OPTIONAL_TOPICS


def test_core_coverage_audit_state() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    core_coverage = _load(root, "core_coverage_audit.json")
    stats = _load(root, "audit_stats.json")

    assert len(core_coverage) == 5
    by_code = {row["official_scope_code"]: row for row in core_coverage}

    fully_evidenced = [
        code for code, row in by_code.items()
        if row["status"] == "FULLY_EVIDENCED_NOT_RELEASE_READY"
    ]
    partially_evidenced = [
        code for code, row in by_code.items()
        if row["status"] in {
            "PARTIAL_EVIDENCE_CORE_GAP_REMAINS",
            "PARTIAL_EVIDENCE_TREE_REPRESENTATION_NOT_MATERIALIZED",
        }
    ]
    missing = [
        code for code, row in by_code.items()
        if row["status"] == "MISSING_ENTIRELY"
    ]

    assert len(fully_evidenced) == 3
    assert len(partially_evidenced) == 2
    assert len(missing) == 0

    covered_reqs = []
    partial_reqs = []
    for row in core_coverage:
        for desc, st in row["normalized_coverage_status"].items():
            if st in {"COVERED", "COVERED_BY_SOURCE_BACKED_CHILD_EVIDENCE"}:
                covered_reqs.append(desc)
            elif str(st).startswith("PARTIAL"):
                partial_reqs.append(desc)

    assert len(covered_reqs) == 18
    assert len(partial_reqs) == 2
    assert set(partial_reqs) == {
        "ý nghĩa và diễn giải các số đặc trưng trong thực tiễn",
        "sơ đồ hình cây và ứng dụng thực tiễn",
    }

    assert stats["official_core_scopes"] == 5
    assert stats["official_core_scopes_fully_evidenced"] == 3
    assert stats["official_core_scopes_partially_evidenced"] == 2
    assert stats["official_core_scopes_missing_entirely"] == 0
    assert stats["official_normalized_requirements_total"] == 20
    assert stats["official_normalized_requirements_covered"] == 18
    assert stats["official_normalized_requirements_partial"] == 2


def test_grouped_statistics_derived_gaps_and_interpretation_mapping() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    core_coverage = _load(root, "core_coverage_audit.json")
    by_code = {row["official_scope_code"]: row for row in core_coverage}
    stat_scope = by_code["M12_CORE_STATISTICS_GROUPED_DATA"]

    assert tuple(stat_scope["question_data"]["remaining_derived_gaps"]) == EXPECTED_GROUPED_DERIVED_GAPS
    assert (
        tuple(stat_scope["official_gap_mapping"])
        == EXPECTED_GROUPED_INTERPRETATION_MAPPING
    )
    assert (
        stat_scope["normalized_coverage_status"][
            "ý nghĩa và diễn giải các số đặc trưng trong thực tiễn"
        ]
        == "PARTIAL"
    )


def test_probability_tree_source_leads_remain_raw_not_verified() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    leads_doc = _load(root, "probability_tree_source_leads.json")

    assert leads_doc["status"] == "SOURCE_LEADS_NOT_CURATED_DATA"
    leads = leads_doc["leads"]
    assert len(leads) == 4

    for lead in leads:
        assert lead.get("review_status") != "VERIFIED"
        assert lead.get("verified") is not True


def test_vector_legacy_non_double_counting() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    core_coverage = _load(root, "core_coverage_audit.json")
    lineage = _load(root, "dataset_lineage.json")
    drift = _load(root, "curriculum_taxonomy_drift.json")
    contract = _load(root, "data_contract.json")

    by_code = {row["official_scope_code"]: row for row in core_coverage}
    oxyz_scope = by_code["M12_CORE_GEOMETRY_COORDINATE_3D"]
    legacy_overlap = oxyz_scope.get("legacy_overlap", {})

    assert (
        legacy_overlap.get("decision")
        == "SUPPLEMENTARY_LEGACY_SUBSET_OF_OXYZ_DO_NOT_COUNT_AS_SEPARATE_OFFICIAL_CHAPTER"
    )
    assert (
        oxyz_scope["question_data"]["legacy_vector_verified_units_not_double_counted"]
        == 48
    )

    assert (
        lineage["double_counting_policy"]["vector_coordinates_v0_1"]
        == "DO_NOT_DOUBLE_COUNT_AGAINST_OXYZ_CORE_COVERAGE"
    )
    assert (
        contract["policy"]["legacy_vector_data_must_not_be_double_counted"] is True
    )
    finding_decisions = [f.get("decision") for f in drift.get("findings", [])]
    assert any("TREAT_AS_LEGACY_OR_SUBSCOPE_OF_M12_CORE_GEOMETRY_COORDINATE_3D" in d for d in finding_decisions)


def test_curriculum_alignment_candidate_boundary() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    candidate = _load(root, "curriculum_alignment_candidate.json")
    drift = _load(root, "curriculum_taxonomy_drift.json")
    contract = _load(root, "data_contract.json")

    assert candidate["status"] == "PROPOSAL_NOT_CANONICAL"
    assert candidate["activation_allowed"] is False
    assert (
        candidate["problem_types_concepts_learning_outcomes_policy"]
        == "COACH_LEARNING_DERIVED_ONLY"
    )
    assert len(candidate["chapter_scope_mapping"]) == 5
    assert len(candidate["legacy_or_quarantine"]) == 2

    assert drift["activation_allowed"] is False
    assert contract["policy"]["audit_must_not_activate_curriculum"] is True
    assert contract["policy"]["audit_must_not_enable_database_import"] is True


def test_release_readiness_blockers() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    readiness = _load(root, "release_readiness.json")
    stats = _load(root, "audit_stats.json")
    contract = _load(root, "data_contract.json")

    assert readiness["production_release_ready"] is False
    assert (
        readiness["database_import_recommendation"]
        == "DO_NOT_IMPORT_NEW_GRADE12_CANONICAL_GRAPH_YET"
    )
    assert (
        readiness["canonical_snapshot_recommendation"]
        == "KEEP_EXISTING_PREFLIGHT_SNAPSHOTS_STAGING_ONLY_UNTIL_ALIGNMENT_AUDIT_IS_RESOLVED"
    )
    assert stats["production_release_ready_core_scopes"] == 0
    assert stats["production_readiness_status"] == "BLOCKED"
    assert len(readiness["blocking_reasons"]) > 0

    assert contract["required_invariants"]["production_release_ready_core_scopes"] == 0
    assert not list(root.rglob("*.pdf"))


def test_validation_is_read_only_and_deterministic() -> None:
    root = DEFAULT_FULL_SCOPE_AUDIT_PATH
    before = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    first = FullScopeAuditValidator().validate()
    second = FullScopeAuditValidator().validate()
    after = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    assert first.as_dict() == second.as_dict()
    assert before == after


def test_cli_returns_success_and_locked_aggregate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["aggregate_semantic_sha256"] == EXPECTED_AUDIT_AGGREGATE_SHA256


@pytest.mark.parametrize(
    ("file_name", "mutate", "expected_code"),
    [
        (
            "probability_tree_source_leads.json",
            lambda value: value["leads"][0].__setitem__("review_status", "VERIFIED"),
            "RAW_LEAD_MARKED_VERIFIED",
        ),
        (
            "probability_tree_source_leads.json",
            lambda value: value.__setitem__("status", "VERIFIED"),
            "TREE_LEADS_STATUS_MISMATCH",
        ),
        (
            "cross_cutting_optional_audit.json",
            lambda value: value["cross_cutting"][0].__setitem__("status", "MATERIALIZED"),
            "CROSS_CUTTING_INVALID_STATUS",
        ),
        (
            "audit_stats.json",
            lambda value: value.__setitem__("cross_cutting_items_materialized", 1),
            "CROSS_CUTTING_MATERIALIZED_NONZERO",
        ),
        (
            "cross_cutting_optional_audit.json",
            lambda value: value["optional_study_topics"][0].__setitem__("status", "MATERIALIZED"),
            "OPTIONAL_TOPIC_INVALID_STATUS",
        ),
        (
            "audit_stats.json",
            lambda value: value.__setitem__(
                "optional_special_topics_materialized_as_dedicated_datasets", 1
            ),
            "OPTIONAL_TOPICS_MATERIALIZED_NONZERO",
        ),
        (
            "curriculum_alignment_candidate.json",
            lambda value: value.__setitem__("activation_allowed", True),
            "CANDIDATE_ACTIVATION_ALLOWED_VIOLATION",
        ),
        (
            "curriculum_alignment_candidate.json",
            lambda value: value.__setitem__("status", "CANONICAL"),
            "CANDIDATE_STATUS_NOT_PROPOSAL",
        ),
        (
            "release_readiness.json",
            lambda value: value.__setitem__("production_release_ready", True),
            "PRODUCTION_RELEASE_READY_VIOLATION",
        ),
        (
            "release_readiness.json",
            lambda value: value.__setitem__(
                "database_import_recommendation", "IMPORT_NOW"
            ),
            "DB_IMPORT_RECOMMENDATION_MISMATCH",
        ),
        (
            "data_contract.json",
            lambda value: value.__setitem__("aggregate_semantic_sha256", "f" * 64),
            "CONTRACT_AGGREGATE_MISMATCH",
        ),
        (
            "official_scope_snapshot.json",
            lambda value: value.__setitem__("repo_head_commit", "f" * 40),
            "SNAPSHOT_REPO_HEAD_MISMATCH",
        ),
        (
            "core_coverage_audit.json",
            lambda value: value[3]["question_data"].__setitem__(
                "remaining_derived_gaps", []
            ),
            "GROUPED_REMAINING_GAPS_MISMATCH",
        ),
        (
            "dataset_lineage.json",
            lambda value: value["double_counting_policy"].__setitem__(
                "vector_coordinates_v0_1", "COUNT_SEPARATELY"
            ),
            "DOUBLE_COUNTING_POLICY_MISMATCH",
        ),
        (
            "data_contract.json",
            lambda value: value["policy"].__setitem__(
                "legacy_vector_data_must_not_be_double_counted", False
            ),
            "CONTRACT_VECTOR_POLICY_MISMATCH",
        ),
        (
            "core_coverage_audit.json",
            lambda value: value[2]["question_data"].__setitem__(
                "legacy_vector_verified_units_not_double_counted", 0
            ),
            "LEGACY_VECTOR_COUNT_MISMATCH",
        ),
    ],
)
def test_mutations_are_rejected(
    tmp_path: Path,
    file_name: str,
    mutate: Callable[[Any], None],
    expected_code: str,
) -> None:
    root = _copy_dataset(tmp_path)
    payload = _load(root, file_name)
    mutate(payload)
    _write(root, file_name, payload)

    report = FullScopeAuditValidator().validate(root)

    assert not report.is_valid
    assert expected_code in _codes(report), f"Expected code {expected_code!r} not in {_codes(report)}"


def test_regression_existing_validators_remain_healthy() -> None:
    validators: list[tuple[str, Any]] = [
        ("DerivativeActivationGateValidator", DerivativeActivationGateValidator()),
        ("VectorAcademicReviewValidator", VectorAcademicReviewValidator()),
        ("GroupedDataDispersionAcademicReviewValidator", GroupedDataDispersionAcademicReviewValidator()),
        ("GroupedDataDispersionVisualAssetValidator", GroupedDataDispersionVisualAssetValidator()),
        ("GroupedDataDispersionGapRescanValidator", GroupedDataDispersionGapRescanValidator()),
        ("IntegralsAcademicReviewValidator", IntegralsAcademicReviewValidator()),
        ("IntegralsGapSupplementValidator", IntegralsGapSupplementValidator()),
        ("IntegralsVisualAssetValidator", IntegralsVisualAssetValidator()),
        ("OxyzAcademicReviewValidator", OxyzAcademicReviewValidator()),
        ("OxyzGapSupplementValidator", OxyzGapSupplementValidator()),
        ("OxyzVisualAssetValidator", OxyzVisualAssetValidator()),
        ("ConditionalProbabilityAcademicReviewValidator", ConditionalProbabilityAcademicReviewValidator()),
        ("ConditionalProbabilityGapEvidenceValidator", ConditionalProbabilityGapEvidenceValidator()),
    ]

    for name, val in validators:
        report = val.validate()
        assert report.is_valid, f"{name} failed regression check: {getattr(report, 'errors', None)}"
