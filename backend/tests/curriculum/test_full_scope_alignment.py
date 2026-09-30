from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import pytest

from app.curriculum.derivative_candidate import (
    DerivativeCurriculumCandidateValidator,
)
from app.curriculum.full_scope_alignment import (
    DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    EXPECTED_ALIGNMENT_AGGREGATE_SHA256,
    EXPECTED_BASE_REPO_COMMIT,
    EXPECTED_CHAPTER_CODES,
    EXPECTED_CONTRACT_SEMANTIC_SHA256,
    EXPECTED_INPUT_AUDIT_AGGREGATE_SHA256,
    EXPECTED_INVARIANTS,
    EXPECTED_OFFICIAL_CORE_SCOPES,
    EXPECTED_PREVIEW_FINGERPRINT,
    EXPECTED_SEMANTIC_HASHES,
    OFFICIAL_NORMALIZED_REQUIREMENTS,
    REPO_ROOT,
    FullScopeAlignmentPreviewComposer,
    FullScopeAlignmentValidator,
)
from app.curriculum.full_scope_audit import FullScopeAuditValidator
from app.curriculum.import_service import CurriculumImportService
from app.questions.conditional_probability_academic_review import (
    ConditionalProbabilityAcademicReviewValidator,
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
from app.validate_full_scope_alignment import main


def _load(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, value: Any) -> None:
    (root / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "full_scope_alignment_v0_1"
    shutil.copytree(DEFAULT_FULL_SCOPE_ALIGNMENT_PATH, destination)
    return destination


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_data_math12_033_state() -> None:
    report = FullScopeAlignmentValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_ALIGNMENT_AGGREGATE_SHA256
    assert report.preview_fingerprint == EXPECTED_PREVIEW_FINGERPRINT
    assert report.base_repo_commit == EXPECTED_BASE_REPO_COMMIT
    assert report.input_audit_aggregate_sha256 == EXPECTED_INPUT_AUDIT_AGGREGATE_SHA256
    assert report.counts == {
        "chapters": 5,
        "topics": 24,
        "problem_types": 75,
        "concepts": 89,
        "learning_outcomes": 34,
        "concept_relations": 93,
        "official_core_scopes": 5,
        "official_normalized_requirements": 20,
        "cross_scope_relations": 11,
        "enrichment_blockers": 41,
    }
    assert report.schema_enrichment_required is True
    assert report.enrichment_blockers_count == 41
    assert report.activation_allowed is False
    assert report.database_import_allowed is False
    assert report.canonical_write_allowed is False
    assert report.curriculum_import_service_allowed is False
    assert all(report.checks.values())
    assert len(report.errors) == 0


def test_preview_composition_is_deterministic_and_read_only() -> None:
    root = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH
    before = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    preview1, issues1 = FullScopeAlignmentPreviewComposer.compose(root, REPO_ROOT)
    preview2, issues2 = FullScopeAlignmentPreviewComposer.compose(root, REPO_ROOT)

    after = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    assert before == after
    assert issues1 == []
    assert issues2 == []
    assert preview1 is not None and preview2 is not None
    assert preview1.fingerprint == preview2.fingerprint
    assert preview1.fingerprint == EXPECTED_PREVIEW_FINGERPRINT
    assert preview1.counts == {
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
        "enrichment_blockers": 41,
    }
    assert preview1.schema_enrichment_required is True


def test_component_bindings_and_git_blob_hashes() -> None:
    root = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH
    contract = _load(root, "data_contract.json")
    cb = _load(root, "component_bindings.json")

    actual_contract_hash = FullScopeAlignmentValidator._semantic_hash(root / "data_contract.json")
    assert actual_contract_hash == EXPECTED_CONTRACT_SEMANTIC_SHA256
    assert contract["semantic_sha256"] == EXPECTED_SEMANTIC_HASHES
    assert cb["base_repo_commit"] == EXPECTED_BASE_REPO_COMMIT

    for comp_name, comp_info in cb["components"].items():
        if "files" in comp_info:
            base_dir = REPO_ROOT / comp_info["base_path"]
            for fname, exp_hash in comp_info["files"].items():
                fpath = base_dir / fname
                assert fpath.is_file(), f"{comp_name}/{fname} missing"
                actual = FullScopeAlignmentValidator._git_blob_sha1(fpath)
                assert actual == exp_hash, f"{comp_name}/{fname} hash mismatch"
        elif "path" in comp_info:
            fpath = REPO_ROOT / comp_info["path"]
            assert fpath.is_file(), f"{comp_name} missing"
            exp_hash = comp_info["git_blob_sha1"]
            actual = FullScopeAlignmentValidator._git_blob_sha1(fpath)
            assert actual == exp_hash, f"{comp_name} hash mismatch"


def test_candidate_chapters_and_topics_structure() -> None:
    root = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH
    chapters = _load(root, "chapters.json")
    topics = _load(root, "topics.json")

    assert len(chapters) == 5
    chapter_codes = tuple(c["code"] for c in chapters)
    assert chapter_codes == EXPECTED_CHAPTER_CODES
    assert "VECTORS_GEOMETRY" not in chapter_codes
    assert "EXPONENTIAL_LOGARITHM" not in chapter_codes

    assert len(topics) == 24
    chapter_set = set(chapter_codes)
    for t in topics:
        assert t["chapter_code"] in chapter_set
        if t.get("source_component") == "VECTOR_STAGING":
            assert t["chapter_code"] == "OXYZ_CHAPTER"
        elif t.get("source_component") == "GROUPED_DISPERSION_STAGING":
            assert t["chapter_code"] == "GROUPED_DATA_STATISTICS"


def test_problem_type_alignment_rules() -> None:
    root = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH
    pt_align = _load(root, "problem_type_alignment.json")
    topics = _load(root, "topics.json")
    topic_map = {t["code"]: t["chapter_code"] for t in topics}

    assert len(pt_align) == 75
    unique_codes = {pt["problem_type_code"] for pt in pt_align}
    assert len(unique_codes) == 75

    for pt in pt_align:
        target = pt["target_topic_code"]
        assert target in topic_map
        source = pt["record_source"]
        if source == "VECTOR_STAGING":
            assert topic_map[target] == "OXYZ_CHAPTER"
        elif source == "GROUPED_DISPERSION_STAGING":
            assert topic_map[target] == "GROUPED_DATA_STATISTICS"


def test_official_scope_and_learning_outcome_bindings() -> None:
    root = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH
    scope_bindings = _load(root, "official_scope_bindings.json")
    lo_bindings = _load(root, "learning_outcome_requirement_bindings.json")

    assert len(scope_bindings) == 5
    assert tuple(s["official_scope_code"] for s in scope_bindings) == EXPECTED_OFFICIAL_CORE_SCOPES

    all_reqs = [
        req
        for s in scope_bindings
        for req in s.get("normalized_requirements", [])
    ]
    assert len(all_reqs) == 20
    assert len(set(all_reqs)) == 20
    assert set(all_reqs) == set(OFFICIAL_NORMALIZED_REQUIREMENTS)

    assert len(lo_bindings) == 34
    for lo_code, req in lo_bindings.items():
        assert req in set(OFFICIAL_NORMALIZED_REQUIREMENTS)


def test_cross_scope_relations_and_quarantine_policy() -> None:
    root = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH
    cross_rel = _load(root, "cross_scope_relations.json")
    quarantine = _load(root, "legacy_quarantine.json")

    assert len(cross_rel) == 11
    assert quarantine["policy"] == "NON_DESTRUCTIVE"
    entries = quarantine["entries"]
    assert len(entries) == 3
    quarantine_codes = {e["code"] for e in entries}
    assert quarantine_codes == {"EXPONENTIAL_LOGARITHM", "VECTORS_GEOMETRY", "GROUPED_DATA_DISPERSION"}
    for e in entries:
        assert e["destructive_delete_allowed"] is False


def test_critical_boundaries() -> None:
    root = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH
    manifest = _load(root, "candidate_manifest.json")
    contract = _load(root, "data_contract.json")
    policy = _load(root, "activation_policy.json")

    assert manifest["activation_allowed"] is False
    assert manifest["database_import_allowed"] is False
    assert manifest["canonical_write_allowed"] is False

    assert contract["required_invariants"]["activation_allowed"] is False
    assert contract["required_invariants"]["database_import_allowed"] is False
    assert contract["required_invariants"]["canonical_write_allowed"] is False

    assert policy["activation_allowed"] is False
    assert policy["database_import_allowed"] is False
    assert policy["canonical_write_allowed"] is False
    assert policy["curriculum_import_service_allowed"] is False


def test_cli_returns_success_and_locked_aggregate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["aggregate_semantic_sha256"] == EXPECTED_ALIGNMENT_AGGREGATE_SHA256
    assert output["preview_fingerprint"] == EXPECTED_PREVIEW_FINGERPRINT


def test_curriculum_import_service_not_invoked_by_preview() -> None:
    with patch.object(CurriculumImportService, "__init__", side_effect=AssertionError("CurriculumImportService must not be called!")):
        report = FullScopeAlignmentValidator().validate()
        assert report.is_valid
        preview, issues = FullScopeAlignmentPreviewComposer.compose(
            DEFAULT_FULL_SCOPE_ALIGNMENT_PATH, REPO_ROOT
        )
        assert preview is not None
        assert issues == []


@pytest.mark.parametrize(
    ("file_name", "mutate", "expected_code"),
    [
        (
            "chapters.json",
            lambda v: v.append({"code": "EXTRA_CHAPTER", "name": "Extra", "order_index": 60}),
            "CHAPTER_COUNT_MISMATCH",
        ),
        (
            "chapters.json",
            lambda v: v.append({"code": "EXPONENTIAL_LOGARITHM", "name": "Exp", "order_index": 60}),
            "EXPONENTIAL_LOGARITHM_IN_CORE_CHAPTERS",
        ),
        (
            "chapters.json",
            lambda v: v.append({"code": "VECTORS_GEOMETRY", "name": "Vec", "order_index": 60}),
            "VECTORS_GEOMETRY_AS_CANDIDATE_CHAPTER",
        ),
        (
            "chapters.json",
            lambda v: [v.remove(c) for c in v if c["code"] == "GROUPED_DATA_STATISTICS"],
            "MISSING_REQUIRED_CHAPTER",
        ),
        (
            "component_bindings.json",
            lambda v: v["components"]["DERIVATIVE_STAGING"]["files"].__setitem__("chapters.json", "f" * 40),
            "COMPONENT_GIT_BLOB_MISMATCH",
        ),
        (
            "problem_type_alignment.json",
            lambda v: v[0].__setitem__("target_topic_code", "UNDECLARED_TOPIC"),
            "UNDECLARED_TARGET_TOPIC",
        ),
        (
            "problem_type_alignment.json",
            lambda v: v.append({**v[0], "target_topic_code": "EXTREMA_TOPIC"}),
            "CONFLICTING_CODE_PAYLOAD",
        ),
        (
            "official_scope_bindings.json",
            lambda v: v[0]["normalized_requirements"].__setitem__(0, "RENAMED_REQUIREMENT"),
            "OFFICIAL_REQUIREMENT_MISMATCH",
        ),
        (
            "candidate_manifest.json",
            lambda v: v["classification_policy"].__setitem__(
                "chapters_topics_problem_types_concepts_relations", "OFFICIAL"
            ),
            "RAW_DERIVED_RELABELED_AS_OFFICIAL",
        ),
        (
            "activation_policy.json",
            lambda v: v.__setitem__("activation_allowed", True),
            "ACTIVATION_NOT_BLOCKED",
        ),
        (
            "activation_policy.json",
            lambda v: v.__setitem__("database_import_allowed", True),
            "DATABASE_IMPORT_NOT_BLOCKED",
        ),
        (
            "activation_policy.json",
            lambda v: v.__setitem__("canonical_write_allowed", True),
            "CANONICAL_WRITE_NOT_BLOCKED",
        ),
        (
            "activation_policy.json",
            lambda v: v.__setitem__("curriculum_import_service_allowed", True),
            "IMPORT_SERVICE_NOT_BLOCKED",
        ),
        (
            "legacy_quarantine.json",
            lambda v: v["entries"][0].__setitem__("destructive_delete_allowed", True),
            "DESTRUCTIVE_DELETE_ALLOWED_VIOLATION",
        ),
        (
            "data_contract.json",
            lambda v: v.__setitem__("input_audit_aggregate_sha256", "f" * 64),
            "CONTRACT_AUDIT_AGGREGATE_MISMATCH",
        ),
        (
            "data_contract.json",
            lambda v: v.__setitem__("aggregate_semantic_sha256", "f" * 64),
            "CONTRACT_AGGREGATE_MISMATCH",
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

    report = FullScopeAlignmentValidator().validate(root)

    assert not report.is_valid
    assert expected_code in _codes(report), f"Expected code {expected_code!r} not in {_codes(report)}"


def test_regression_existing_validators_remain_healthy() -> None:
    validators: list[tuple[str, Any]] = [
        ("FullScopeAuditValidator", FullScopeAuditValidator()),
        ("DerivativeCurriculumCandidateValidator", DerivativeCurriculumCandidateValidator()),
        ("VectorAcademicReviewValidator", VectorAcademicReviewValidator()),
        ("GroupedDataDispersionAcademicReviewValidator", GroupedDataDispersionAcademicReviewValidator()),
        ("IntegralsAcademicReviewValidator", IntegralsAcademicReviewValidator()),
        ("OxyzAcademicReviewValidator", OxyzAcademicReviewValidator()),
        ("ConditionalProbabilityAcademicReviewValidator", ConditionalProbabilityAcademicReviewValidator()),
    ]

    for name, val in validators:
        report = val.validate()
        assert report.is_valid, f"{name} failed regression check: {getattr(report, 'errors', None)}"
