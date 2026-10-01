from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.curriculum.canonical_snapshot_candidate import (
    DEFAULT_CANDIDATE_PATH,
    DEFAULT_SNAPSHOT_DIR,
    EXPECTED_ACTIVE_CHAPTERS,
    EXPECTED_BOUND_COMPOSED_FINGERPRINT,
    EXPECTED_COUNTS as SNAPSHOT_EXPECTED_COUNTS,
    EXPECTED_SNAPSHOT_CANDIDATE_AGGREGATE_SHA256,
    GENERATED_SNAPSHOT_FILES,
    ROOT_CANONICAL_PATH,
    CanonicalSnapshotCandidateGenerator,
    CanonicalSnapshotCandidateValidator,
)
from app.curriculum.diagnostic_graph import (
    DEFAULT_DIAGNOSTIC_GRAPH_PATH,
    EXPECTED_COUNTS as DIAG_EXPECTED_COUNTS,
    EXPECTED_DIAGNOSTIC_GRAPH_AGGREGATE_SHA256,
    DiagnosticGraphValidator,
)
from app.curriculum.production_gate import (
    DEFAULT_PRODUCTION_GATE_PATH,
    EXPECTED_GATES,
    EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256,
    WORKFLOW_FILE_PATH,
    ProductionGateValidator,
)
from app.questions.depth_correction_overlay import (
    BASE_DERIVATIVE_GROUPS_PATH,
    BASE_OXYZ_DATA_PATH,
    BASE_PROBABILITY_DATA_PATH,
    DEFAULT_DEPTH_CORRECTION_PATH,
    EXPECTED_DEPTH_CORRECTION_AGGREGATE_SHA256,
    EXPECTED_DERIVATIVE_ZERO_EV,
    EXPECTED_PROBABILITY_PROMOTIONS,
    EXPECTED_VECTOR_ZERO_EV,
    DepthCorrectionOverlay,
    DepthCorrectionOverlayValidator,
)
from app.questions.quality_audit import (
    DEFAULT_QUALITY_AUDIT_PATH,
    EXPECTED_QUALITY_AUDIT_AGGREGATE_SHA256,
    EXPECTED_QUEUE_STATUS,
    QualityAuditValidator,
)
from app.validate_full_session_038_042 import (
    main as session_main,
    validate_full_session_038_042,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, val: Any) -> None:
    path.write_text(json.dumps(val, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


# ======================================================================
# 1. DATA-MATH12-038 Canonical Snapshot Candidate Tests
# ======================================================================

def test_snapshot_candidate_generator_and_validator() -> None:
    gen_result = CanonicalSnapshotCandidateGenerator.generate()
    assert gen_result["status"] == "GENERATED"
    assert gen_result["fingerprint"] == EXPECTED_BOUND_COMPOSED_FINGERPRINT
    assert gen_result["manifest_version"] == "1.2.0"

    report = CanonicalSnapshotCandidateValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_SNAPSHOT_CANDIDATE_AGGREGATE_SHA256
    assert report.bound_composed_fingerprint == EXPECTED_BOUND_COMPOSED_FINGERPRINT
    assert report.candidate_manifest_version == "1.2.0"
    assert report.active_chapter_codes == EXPECTED_ACTIVE_CHAPTERS
    assert report.canonical_activation_allowed is False
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False

    for fname in GENERATED_SNAPSHOT_FILES:
        target = DEFAULT_SNAPSHOT_DIR / fname
        assert target.is_file(), f"Missing snapshot file: {fname}"


def test_snapshot_candidate_counts() -> None:
    for entity_name, expected_count in SNAPSHOT_EXPECTED_COUNTS.items():
        fname = f"{entity_name}.json"
        fpath = DEFAULT_SNAPSHOT_DIR / fname
        data = _load_json(fpath)
        assert len(data) == expected_count, f"{entity_name} count mismatch"


def test_snapshot_candidate_active_chapters_guard() -> None:
    chapters = _load_json(DEFAULT_SNAPSHOT_DIR / "chapters.json")
    codes = [c["code"] for c in chapters]
    assert codes == list(EXPECTED_ACTIVE_CHAPTERS)
    assert "EXPONENTIAL_LOGARITHM" not in codes
    assert "VECTORS_GEOMETRY" not in codes


def test_root_canonical_1_1_0_isolation() -> None:
    root_manifest = _load_json(ROOT_CANONICAL_PATH / "manifest.json")
    assert root_manifest["dataset_version"] == "1.1.0"

    with pytest.raises(RuntimeError, match="CRITICAL BOUNDARY VIOLATION"):
        CanonicalSnapshotCandidateGenerator.generate(target_dir=ROOT_CANONICAL_PATH)


def test_snapshot_candidate_mutations(tmp_path: Path) -> None:
    cand_copy = tmp_path / "candidate"
    shutil.copytree(DEFAULT_CANDIDATE_PATH, cand_copy)
    sn_copy = cand_copy / "generated_snapshot"

    validator = CanonicalSnapshotCandidateValidator()

    # Mutation 1: Corrupted manifest version
    m_path = sn_copy / "manifest.json"
    m_data = _load_json(m_path)
    m_data["dataset_version"] = "2.0.0"
    _write_json(m_path, m_data)
    rep = validator.validate(cand_copy, snapshot_dir=sn_copy)
    assert not rep.is_valid
    assert "MANIFEST_VERSION_MISMATCH" in _codes(rep)
    _write_json(m_path, _load_json(DEFAULT_SNAPSHOT_DIR / "manifest.json"))

    # Mutation 2: Contract hash tamper
    contract_path = cand_copy / "data_contract.json"
    c_data = _load_json(contract_path)
    c_data["aggregate_semantic_sha256"] = "deadbeef" * 8
    _write_json(contract_path, c_data)
    rep2 = validator.validate(cand_copy, snapshot_dir=sn_copy)
    assert not rep2.is_valid
    assert "CONTRACT_AGGREGATE_MISMATCH" in _codes(rep2)


# ======================================================================
# 2. DATA-MATH12-039 Depth Correction Overlay Tests
# ======================================================================

def test_depth_correction_overlay_validator_reports_pass() -> None:
    report = DepthCorrectionOverlayValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_DEPTH_CORRECTION_AGGREGATE_SHA256
    assert report.probability_promotions_count == 4
    assert report.probability_verified_count_after == 21
    assert report.derivative_zero_evidence_count == 3
    assert report.vector_zero_evidence_count == 1
    assert report.canonical_snapshot_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False


def test_probability_overlay_application_and_answers() -> None:
    promotions = _load_json(DEFAULT_DEPTH_CORRECTION_PATH / "probability_hold_promotions.json")
    records = {r["candidate_id"]: r for r in promotions["records"]}

    for cid, expected_ans in EXPECTED_PROBABILITY_PROMOTIONS.items():
        assert cid in records
        rec = records[cid]
        assert rec["correct_answer"] == expected_ans
        assert rec["review_status_after_overlay"] == "VERIFIED_SOURCE_ANSWER"
        assert rec["rights_status"] == "REVIEW_REQUIRED"

    base_cands = [
        {"candidate_id": "M12_PROB_CAND_0058", "review_status": "HOLD_CANONICAL_SOURCE_ANSWER_REQUIRED"},
        {"candidate_id": "M12_PROB_CAND_0001", "review_status": "VERIFIED_SOURCE_ANSWER"},
    ]
    overlaid = DepthCorrectionOverlay.apply_probability_hold_promotions(base_cands)
    assert overlaid[0]["review_status"] == "VERIFIED_SOURCE_ANSWER"
    assert overlaid[0]["rights_status"] == "REVIEW_REQUIRED"
    assert overlaid[1]["review_status"] == "VERIFIED_SOURCE_ANSWER"


def test_derivative_and_vector_zero_evidence_invariants() -> None:
    deriv = _load_json(DEFAULT_DEPTH_CORRECTION_PATH / "derivative_coverage_correction.json")
    actual_deriv_zero = tuple(deriv["zero_evidence_problem_types_after_secondary_mapping"])
    assert actual_deriv_zero == EXPECTED_DERIVATIVE_ZERO_EV

    sec_groups = deriv["secondary_group_level_evidence"]
    assert len(sec_groups) == 1
    assert sec_groups[0]["problem_type_code"] == "COMPLETE_FUNCTION_ANALYSIS_CUBIC"
    assert sec_groups[0]["source_group_id"] == "M12_DERIV_GROUP_0136"

    vec = _load_json(DEFAULT_DEPTH_CORRECTION_PATH / "vector_secondary_evidence.json")
    actual_vec_zero = tuple(vec["remaining_zero_evidence_vector_problem_types_after_overlay"])
    assert actual_vec_zero == EXPECTED_VECTOR_ZERO_EV
    assert len(vec["records"]) == 3


def test_depth_correction_mutations(tmp_path: Path) -> None:
    d_copy = tmp_path / "depth"
    shutil.copytree(DEFAULT_DEPTH_CORRECTION_PATH, d_copy)
    validator = DepthCorrectionOverlayValidator()

    # Mutation 1: Corrupt promoted answer
    p_file = d_copy / "probability_hold_promotions.json"
    p_data = _load_json(p_file)
    p_data["records"][0]["correct_answer"] = [False, False, False, False]
    _write_json(p_file, p_data)

    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "ANSWER_MISMATCH" in _codes(rep)


# ======================================================================
# 3. DATA-MATH12-040 Diagnostic Misconception Graph Tests
# ======================================================================

def test_diagnostic_graph_validator_reports_pass() -> None:
    report = DiagnosticGraphValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_DIAGNOSTIC_GRAPH_AGGREGATE_SHA256
    assert report.counts == DIAG_EXPECTED_COUNTS
    assert report.automatic_student_diagnosis_allowed is False
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False


def test_diagnostic_graph_referential_integrity() -> None:
    misconceptions = _load_json(DEFAULT_DIAGNOSTIC_GRAPH_PATH / "misconceptions.json")
    pt_links = _load_json(DEFAULT_DIAGNOSTIC_GRAPH_PATH / "problem_type_misconceptions.json")
    remediations = _load_json(DEFAULT_DIAGNOSTIC_GRAPH_PATH / "misconception_remediation_concepts.json")

    snapshot_pts = {p["code"] for p in _load_json(DEFAULT_SNAPSHOT_DIR / "problem_types.json")}
    snapshot_concepts = {c["code"] for c in _load_json(DEFAULT_SNAPSHOT_DIR / "concepts.json")}
    mis_codes = {m["code"] for m in misconceptions}

    for link in pt_links:
        assert link["problem_type_code"] in snapshot_pts
        assert link["misconception_code"] in mis_codes

    for rem in remediations:
        assert rem["misconception_code"] in mis_codes
        assert rem["concept_code"] in snapshot_concepts


def test_diagnostic_graph_guardrail_mutation(tmp_path: Path) -> None:
    g_copy = tmp_path / "diag"
    shutil.copytree(DEFAULT_DIAGNOSTIC_GRAPH_PATH, g_copy)
    validator = DiagnosticGraphValidator()

    # Mutation: Tamper inference policy to true
    man_file = g_copy / "diagnostic_manifest.json"
    man_data = _load_json(man_file)
    man_data["inference_policy"]["automatic_student_diagnosis_allowed"] = True
    _write_json(man_file, man_data)

    rep = validator.validate(dataset_path=g_copy)
    assert not rep.is_valid
    assert "AUTO_DIAGNOSIS_NOT_BLOCKED" in _codes(rep)


# ======================================================================
# 4. DATA-MATH12-041 Quality Audit Tests
# ======================================================================

def test_quality_audit_validator_reports_pass() -> None:
    report = QualityAuditValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_QUALITY_AUDIT_AGGREGATE_SHA256
    assert report.official_scope_coverage_gate == "PASS_20_OF_20"
    assert report.diagnostic_density_gate == "FAIL_MORE_REAL_QUESTIONS_REQUIRED"
    assert report.source_diversity_gate == "FAIL_IN_PROBABILITY_STATS_VECTOR_AND_DERIVATIVE"
    assert report.new_chapter_ingestion_recommended is False
    assert report.queue_items_count == 5
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False


def test_acquisition_queue_unpinned_status() -> None:
    queue_data = _load_json(DEFAULT_QUALITY_AUDIT_PATH / "source_acquisition_queue.json")
    for item in queue_data["queue"]:
        assert item["status"] == EXPECTED_QUEUE_STATUS
        assert "source_pdf_sha256" not in item


def test_quality_audit_mutation(tmp_path: Path) -> None:
    qa_copy = tmp_path / "qa"
    shutil.copytree(DEFAULT_QUALITY_AUDIT_PATH, qa_copy)
    validator = QualityAuditValidator()

    # Mutation: Prematurely pin sha256 in queue lead
    q_file = qa_copy / "source_acquisition_queue.json"
    q_data = _load_json(q_file)
    q_data["queue"][0]["source_pdf_sha256"] = "abc123"
    _write_json(q_file, q_data)

    rep = validator.validate(dataset_path=qa_copy)
    assert not rep.is_valid
    assert "PREMATURE_SHA_PINNING" in _codes(rep)


# ======================================================================
# 5. DATA-MATH12-042 Production Gate & CI Tests
# ======================================================================

def test_production_gate_validator_reports_pass() -> None:
    report = ProductionGateValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256
    assert report.workflow_exists is True
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.rights_auto_approval_allowed is False
    assert report.production_ready is False
    assert report.canonical_activation_blocked is True
    assert report.postgres_import_blocked is True
    assert report.production_release_blocked is True

    assert report.gates == EXPECTED_GATES


def test_ci_workflow_content_and_safety() -> None:
    assert WORKFLOW_FILE_PATH.is_file()
    content = WORKFLOW_FILE_PATH.read_text(encoding="utf-8")
    assert "python-version" in content and "3.12" in content
    assert "pytest" in content
    # Confirm workflow does not set up Postgres services or credentials for read-only validation
    assert "POSTGRES_DB" not in content


def test_production_gate_mutations(tmp_path: Path) -> None:
    p_copy = tmp_path / "prod"
    shutil.copytree(DEFAULT_PRODUCTION_GATE_PATH, p_copy)
    validator = ProductionGateValidator()

    # Mutation: Tamper auto approval to True
    r_file = p_copy / "rights_review_queue.json"
    r_data = _load_json(r_file)
    r_data["rights_auto_approval_allowed"] = True
    _write_json(r_file, r_data)

    rep = validator.validate(dataset_path=p_copy)
    assert not rep.is_valid
    assert "AUTO_APPROVAL_NOT_FALSE" in _codes(rep)


# ======================================================================
# 6. Full Session Runner & Integration Tests
# ======================================================================

def test_validate_full_session_038_042_runner() -> None:
    res = validate_full_session_038_042()
    assert res["status"] == "PASS"
    assert res["batch_code"] == "MATH12_038_042_SESSION_FIX"
    assert res["summary"]["official_core_requirements"] == "20/20"
    assert res["summary"]["canonical_candidate_version"] == "1.2.0"
    assert res["summary"]["composed_fingerprint"] == EXPECTED_BOUND_COMPOSED_FINGERPRINT
    assert res["summary"]["probability_verified_after_overlay"] == 21
    assert res["summary"]["derivative_zero_evidence_after_secondary"] == 3
    assert res["summary"]["vector_zero_evidence_after_secondary"] == 1
    assert res["summary"]["misconception_nodes"] == 26
    assert res["summary"]["production_ready"] is False
    assert res["summary"]["canonical_activation_allowed"] is False
    assert res["summary"]["database_import_allowed"] is False

    exit_code = session_main(["--json"])
    assert exit_code == 0
