from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from app.curriculum.data_completion_snapshot import (
    DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH,
    EXPECTED_DATA_COMPLETION_SNAPSHOT_AGGREGATE_SHA256,
    DataCompletionSnapshotValidator,
)
from app.questions.academic_web_evidence import (
    DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH,
    EXPECTED_ACADEMIC_WEB_EVIDENCE_AGGREGATE_SHA256,
    AcademicWebEvidenceValidator,
)
from app.questions.final_acquisition_gate import (
    DEFAULT_FINAL_ACQUISITION_GATE_PATH,
    EXPECTED_FINAL_ACQUISITION_GATE_AGGREGATE_SHA256,
    FinalAcquisitionGateValidator,
)
from app.questions.final_quality_audit import (
    DEFAULT_FINAL_QUALITY_AUDIT_PATH,
    EXPECTED_FINAL_QUALITY_AUDIT_AGGREGATE_SHA256,
    FinalQualityAuditValidator,
)
from app.questions.pinned_depth_supplement import (
    DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH,
    EXPECTED_PINNED_DEPTH_SUPPLEMENT_AGGREGATE_SHA256,
    PinnedDepthSupplementValidator,
)
from app.validate_full_session_038_042 import validate_full_session_038_042
from app.validate_full_session_043_045 import validate_full_session_043_045
from app.validate_full_session_046_050 import validate_full_session_046_050


# ======================================================================
# DATA-046: Web-Reviewed Academic Evidence Tests
# ======================================================================

def test_data046_academic_web_evidence_clean_pass() -> None:
    validator = AcademicWebEvidenceValidator()
    report = validator.validate()
    assert report.is_valid, f"Expected PASS, got errors: {report.errors}"
    assert report.aggregate_semantic_sha256 == EXPECTED_ACADEMIC_WEB_EVIDENCE_AGGREGATE_SHA256
    assert report.counts["evidence_records_count"] == 2
    assert report.derivative_zero_academic == []
    assert report.derivative_zero_pinned == ["PARAMETER_MONOTONICITY"]
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False


def test_data046_negative_mutations(tmp_path: Path) -> None:
    temp_dir = tmp_path / "academic_evidence_web_review_v0_1"
    shutil.copytree(DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH, temp_dir)
    validator = AcademicWebEvidenceValidator()

    # 1. Mutate answer in parameter_monotonicity_evidence.json
    param_path = temp_dir / "parameter_monotonicity_evidence.json"
    data = json.loads(param_path.read_text(encoding="utf-8"))
    data["source_supported_facts"]["answer_key"] = "A"
    data["source_supported_facts"]["answer_value"] = 6
    param_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("ANSWER_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)

    # 2. Reset and set binary_sha256 to non-null
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH, temp_dir)
    data = json.loads(param_path.read_text(encoding="utf-8"))
    data["source"]["binary_sha256"] = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    param_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("BINARY_SHA_NOT_NULL", "FILE_HASH_MISMATCH") for e in report.errors)

    # 3. Reset and set practice_ready to True
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH, temp_dir)
    data = json.loads(param_path.read_text(encoding="utf-8"))
    data["practice_ready"] = True
    param_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("PRACTICE_READY_NOT_FALSE", "FILE_HASH_MISMATCH") for e in report.errors)

    # 4. Reset and mutate stats statement_answer_pattern from [True, False, False, True]
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH, temp_dir)
    stats_path = temp_dir / "multi_measure_statistics_evidence.json"
    data = json.loads(stats_path.read_text(encoding="utf-8"))
    data["source_supported_facts"]["statement_answer_pattern"] = [True, True, True, True]
    stats_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("ANSWER_PATTERN_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)

    # 5. Reset and set canonical_write_allowed to True
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH, temp_dir)
    contract_path = temp_dir / "data_contract.json"
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    data["canonical_write_allowed"] = True
    contract_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code == "CANONICAL_WRITE_NOT_BLOCKED" for e in report.errors)


# ======================================================================
# DATA-047: 11 Pinned Real-Source Units Tests
# ======================================================================

def test_data047_pinned_depth_supplement_clean_pass() -> None:
    validator = PinnedDepthSupplementValidator()
    report = validator.validate()
    assert report.is_valid, f"Expected PASS, got errors: {report.errors}"
    assert report.aggregate_semantic_sha256 == EXPECTED_PINNED_DEPTH_SUPPLEMENT_AGGREGATE_SHA256
    assert report.counts["verified_units_count"] == 11
    assert report.counts["statistics_units_count"] == 6
    assert report.counts["oxyz_units_count"] == 3
    assert report.counts["probability_units_count"] == 2
    # Statistics coverage effects
    assert report.stats_practice_units_after == 44
    assert abs(report.stats_dominant_source_share - 30 / 44) < 1e-6
    assert report.stats_diversity_gate == "PASS"
    # Probability coverage effects
    assert report.prob_practice_units_after == 24
    assert abs(report.prob_dominant_source_share - 17 / 24) < 1e-6
    assert "FAIL" in report.prob_diversity_gate
    assert report.prob_units_needed_to_pass == 1
    # Oxyz counts
    assert report.point_plane_evidence_count == 4
    assert report.line_plane_evidence_count == 3
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False


def test_data047_negative_mutations(tmp_path: Path) -> None:
    temp_dir = tmp_path / "pinned_depth_supplement_v0_2"
    shutil.copytree(DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH, temp_dir)
    validator = PinnedDepthSupplementValidator()

    # 1. Mutate source registry SHA-256
    reg_path = temp_dir / "source_registry.json"
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    data["sources"][0]["sha256"] = "1111111111111111111111111111111111111111111111111111111111111111"
    reg_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("SOURCE_SHA_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)

    # 2. Reset and mutate unit answer (M12_D047_STATS_RANGE_TRIAL05_001)
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH, temp_dir)
    units_path = temp_dir / "verified_units.json"
    data = json.loads(units_path.read_text(encoding="utf-8"))
    data["units"][0]["correct_answer"] = "A"
    data["units"][0]["correct_answer_value"] = 1.2
    units_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("ANSWER_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)

    # 3. Reset and split atomic group (set atomic_group_policy = False)
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH, temp_dir)
    data = json.loads(units_path.read_text(encoding="utf-8"))
    data["units"][1]["atomic_group_policy"] = False
    units_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("ATOMIC_GROUP_SPLIT", "FILE_HASH_MISMATCH") for e in report.errors)

    # 4. Reset and mutate stats dominant share in coverage_after_047.json
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH, temp_dir)
    cov_path = temp_dir / "coverage_after_047.json"
    data = json.loads(cov_path.read_text(encoding="utf-8"))
    data["statistics"]["dominant_source_share_after"] = 0.50
    cov_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("STATS_DOMINANT_SHARE_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)

    # 5. Reset and falsely set probability diversity gate to PASS
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH, temp_dir)
    data = json.loads(cov_path.read_text(encoding="utf-8"))
    data["probability"]["dominant_source_target_70pct"] = "PASS"
    cov_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("PROB_DIVERSITY_FALSE_PASS", "FILE_HASH_MISMATCH") for e in report.errors)

    # 6. Reset and auto-approve rights
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH, temp_dir)
    contract_path = temp_dir / "data_contract.json"
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    data["rights_status"] = "APPROVED"
    contract_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code == "RIGHTS_STATUS_NOT_REVIEW_REQUIRED" for e in report.errors)


# ======================================================================
# DATA-048: Final Quality Re-Audit Tests
# ======================================================================

def test_data048_final_quality_audit_clean_pass() -> None:
    validator = FinalQualityAuditValidator()
    report = validator.validate()
    assert report.is_valid, f"Expected PASS, got errors: {report.errors}"
    assert report.aggregate_semantic_sha256 == EXPECTED_FINAL_QUALITY_AUDIT_AGGREGATE_SHA256
    assert report.official_scope_status == "PASS"
    assert report.diagnostic_density_status == "FAIL"
    assert report.stats_diversity_status == "PASS"
    assert report.prob_diversity_status == "FAIL_SLIGHTLY_ABOVE_0_70"
    assert report.counts["requirements_total"] == 20
    assert report.counts["source_evidenced"] == 20
    assert report.counts["priority_thin_types_count"] == 19
    assert report.counts["next_real_data_actions_count"] == 4
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.canonical_write_allowed is False


def test_data048_negative_mutations(tmp_path: Path) -> None:
    temp_dir = tmp_path / "final_quality_audit_v0_1"
    shutil.copytree(DEFAULT_FINAL_QUALITY_AUDIT_PATH, temp_dir)
    validator = FinalQualityAuditValidator()

    # 1. Mutate official scope requirements total
    status_path = temp_dir / "quality_status.json"
    data = json.loads(status_path.read_text(encoding="utf-8"))
    data["official_scope"]["requirements_total"] = 18
    status_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("OFFICIAL_SCOPE_COUNT_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)

    # 2. Reset and falsely set diagnostic density status to PASS
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_FINAL_QUALITY_AUDIT_PATH, temp_dir)
    data = json.loads(status_path.read_text(encoding="utf-8"))
    data["diagnostic_density"]["status"] = "PASS"
    status_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("DIAGNOSTIC_DENSITY_NOT_FAIL", "FILE_HASH_MISMATCH") for e in report.errors)

    # 3. Reset and mutate priority plan new_chapter_ingestion
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_FINAL_QUALITY_AUDIT_PATH, temp_dir)
    plan_path = temp_dir / "priority_plan.json"
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    data["new_chapter_ingestion"] = "ALLOWED"
    plan_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("NEW_CHAPTER_INGESTION_NOT_BLOCKED", "FILE_HASH_MISMATCH") for e in report.errors)


# ======================================================================
# DATA-049: Final Acquisition Gate Tests
# ======================================================================

def test_data049_final_acquisition_gate_clean_pass() -> None:
    validator = FinalAcquisitionGateValidator()
    report = validator.validate()
    assert report.is_valid, f"Expected PASS, got errors: {report.errors}"
    assert report.aggregate_semantic_sha256 == EXPECTED_FINAL_ACQUISITION_GATE_AGGREGATE_SHA256
    assert report.data_acquisition_mode == "TARGETED_ONLY"
    assert report.broad_expansion_blocked is True
    assert len(report.remaining_queue_items) == 4
    assert "PARAMETER_MONOTONICITY" in report.remaining_queue_items
    assert "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS" in report.remaining_queue_items
    assert "PARAMETER_FROM_GROUPED_VARIANCE_SD" in report.remaining_queue_items
    assert "PROBABILITY_DIVERSITY" in report.remaining_queue_items
    assert report.canonical_activation_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False


def test_data049_negative_mutations(tmp_path: Path) -> None:
    temp_dir = tmp_path / "final_acquisition_gate_v0_1"
    shutil.copytree(DEFAULT_FINAL_ACQUISITION_GATE_PATH, temp_dir)
    validator = FinalAcquisitionGateValidator()

    # 1. Enable broad web scraping
    gate_path = temp_dir / "acquisition_gate.json"
    data = json.loads(gate_path.read_text(encoding="utf-8"))
    data["broad_web_scraping_or_new_chapter_expansion"] = True
    gate_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("BROAD_EXPANSION_NOT_FALSE", "FILE_HASH_MISMATCH") for e in report.errors)

    # 2. Reset and remove synthetic gap fill from blocked
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_FINAL_ACQUISITION_GATE_PATH, temp_dir)
    data = json.loads(gate_path.read_text(encoding="utf-8"))
    data["blocked"] = [b for b in data["blocked"] if b != "synthetic gap fill"]
    gate_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("BLOCKED_POLICY_MISSING", "FILE_HASH_MISMATCH") for e in report.errors)

    # 3. Reset and falsely promote unpinned remaining queue item
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_FINAL_ACQUISITION_GATE_PATH, temp_dir)
    queue_path = temp_dir / "remaining_queue.json"
    data = json.loads(queue_path.read_text(encoding="utf-8"))
    data["items"][0]["status"] = "PROMOTED_PRACTICE_READY"
    queue_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("STATUS_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)


# ======================================================================
# DATA-050: Completion Snapshot Tests
# ======================================================================

def test_data050_data_completion_snapshot_clean_pass() -> None:
    validator = DataCompletionSnapshotValidator()
    report = validator.validate()
    assert report.is_valid, f"Expected PASS, got errors: {report.errors}"
    assert report.aggregate_semantic_sha256 == EXPECTED_DATA_COMPLETION_SNAPSHOT_AGGREGATE_SHA256
    assert report.completion_status == "GRADE12_MATH_DATA_BREADTH_COMPLETE_DEPTH_HARDENING_REMAINS"
    assert report.official_core_requirements == "20/20"
    assert report.canonical_candidate_version == "1.2.0"
    assert report.root_canonical_activation == "NOT_YET_ACTIVATED"
    assert report.minimum_demo_data_done is True
    assert report.official_curriculum_data_done is True
    assert report.adaptive_production_data_done is False
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False


def test_data050_negative_mutations(tmp_path: Path) -> None:
    temp_dir = tmp_path / "data_completion_snapshot_v0_1"
    shutil.copytree(DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH, temp_dir)
    validator = DataCompletionSnapshotValidator()

    # 1. Falsely mark adaptive_production_data_done as True
    dod_path = temp_dir / "definition_of_done.json"
    data = json.loads(dod_path.read_text(encoding="utf-8"))
    data["adaptive_production_data_done"] = True
    dod_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("ADAPTIVE_PRODUCTION_FALSELY_DONE", "FILE_HASH_MISMATCH") for e in report.errors)

    # 2. Reset and set canonical_activation to PASS
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH, temp_dir)
    snap_path = temp_dir / "completion_snapshot.json"
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    data["production_gates"]["canonical_activation"] = "PASS"
    snap_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("GATE_CANONICAL_ACTIVATION_NOT_BLOCKED", "FILE_HASH_MISMATCH") for e in report.errors)

    # 3. Reset and mutate candidate graph chapters count
    shutil.rmtree(temp_dir)
    shutil.copytree(DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH, temp_dir)
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    data["curriculum"]["canonical_candidate_graph"]["chapters"] = 6
    snap_path.write_text(json.dumps(data), encoding="utf-8")
    report = validator.validate(temp_dir)
    assert not report.is_valid
    assert any(e.code in ("GRAPH_COUNTS_MISMATCH", "FILE_HASH_MISMATCH") for e in report.errors)


# ======================================================================
# Joint Consistency & Cross-Session Tests
# ======================================================================

def test_joint_full_session_046_050_runner() -> None:
    result = validate_full_session_046_050()
    assert result["status"] == "PASS"
    for dcode, dinfo in result["datasets"].items():
        assert dinfo["status"] == "PASS"
        assert len(dinfo["errors"]) == 0

    s = result["summary"]
    assert s["official_core_requirements"] == "20/20"
    assert s["new_pinned_units"] == 11
    assert s["derivative_academic_zero_after"] == 0
    assert s["derivative_pinned_practice_zero_after"] == ["PARAMETER_MONOTONICITY"]
    assert s["vector_zero_after"] == 0
    assert s["statistics_practice_units_after"] == 44
    assert s["statistics_source_diversity_gate"] == "PASS"
    assert s["probability_practice_units_after"] == 24
    assert "FAIL" in s["probability_diversity_gate"]
    assert s["probability_units_needed_to_pass_70pct"] == 1
    assert s["minimum_demo_data_done"] is True
    assert s["official_curriculum_data_done"] is True
    assert s["adaptive_production_complete"] is False
    assert s["rights_status"] == "REVIEW_REQUIRED"
    assert s["canonical_activation_allowed"] is False
    assert s["database_import_allowed"] is False
    assert s["production_release_allowed"] is False


def test_end_to_end_data038_through_data050_invariants() -> None:
    # 1. Session 038..042 must still PASS
    res_038_042 = validate_full_session_038_042()
    assert res_038_042["status"] == "PASS"

    # 2. Session 043..045 must still PASS
    res_043_045 = validate_full_session_043_045()
    assert res_043_045["status"] == "PASS"

    # 3. Session 046..050 must PASS
    res_046_050 = validate_full_session_046_050()
    assert res_046_050["status"] == "PASS"

    # 4. Check that root canonical 1.1.0 manifest was never modified
    backend_root = Path(__file__).resolve().parents[2]
    canonical_manifest_path = (
        backend_root
        / "data"
        / "curriculum"
        / "math"
        / "grade12"
        / "gdpt2018"
        / "manifest.json"
    )
    man = json.loads(canonical_manifest_path.read_text(encoding="utf-8"))
    assert man.get("dataset_version") == "1.1.0"
    assert man.get("dataset_code") == "MATH_G12_GDPT2018_CORE"
