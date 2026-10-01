from __future__ import annotations

import copy
import hashlib
import json
import shutil
import struct
from pathlib import Path
from typing import Any

import pytest

from app.curriculum.canonical_snapshot_candidate import (
    CanonicalSnapshotCandidateValidator,
)
from app.curriculum.diagnostic_graph import DiagnosticGraphValidator
from app.curriculum.operational_evidence import (
    DEFAULT_OPERATIONAL_EVIDENCE_PATH,
    EXPECTED_CI_FACTS,
    EXPECTED_OPERATIONAL_EVIDENCE_AGGREGATE_SHA256,
    EXPECTED_REFRESHED_GATES,
    OperationalEvidenceValidator,
)
from app.curriculum.production_gate import (
    DEFAULT_PRODUCTION_GATE_PATH,
    ProductionGateValidator,
)
from app.questions.depth_correction_overlay import (
    DepthCorrectionOverlayValidator,
)
from app.questions.depth_queue import (
    DEFAULT_DEPTH_QUEUE_PATH,
    EXPECTED_DEPTH_QUEUE_AGGREGATE_SHA256,
    EXPECTED_DERIVATIVE_ZERO,
    EXPECTED_QUEUE_STATUS,
    EXPECTED_VECTOR_ZERO,
    DepthQueueValidator,
)
from app.questions.local_depth_supplement import (
    DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH,
    EXPECTED_CROP_BOX,
    EXPECTED_DERIVATIVE_REMAINING_ZERO,
    EXPECTED_LOCAL_DEPTH_SUPPLEMENT_AGGREGATE_SHA256,
    EXPECTED_PNG_ASSET_SHA256,
    EXPECTED_PNG_HEIGHT,
    EXPECTED_PNG_WIDTH,
    EXPECTED_RENDERED_PAGE_DIMENSIONS,
    EXPECTED_SOURCES,
    EXPECTED_VECTOR_REMAINING_ZERO,
    LocalDepthSupplementOverlay,
    LocalDepthSupplementValidator,
)
from app.questions.quality_audit import QualityAuditValidator
from app.validate_full_session_038_042 import validate_full_session_038_042
from app.validate_full_session_043_045 import (
    main as session_main_043_045,
    validate_full_session_043_045,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, val: Any) -> None:
    path.write_text(json.dumps(val, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


# ======================================================================
# 1. DATA-MATH12-043 Local Depth Supplement Tests
# ======================================================================

def test_local_depth_supplement_validator_reports_pass() -> None:
    report = LocalDepthSupplementValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_LOCAL_DEPTH_SUPPLEMENT_AGGREGATE_SHA256
    assert report.derivative_remaining_zero == EXPECTED_DERIVATIVE_REMAINING_ZERO
    assert report.vector_remaining_zero == EXPECTED_VECTOR_REMAINING_ZERO
    assert report.probability_practice_units_after == 22
    assert report.probability_source_families_after == 4
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False


def test_local_depth_supplement_overlay_and_exact_units() -> None:
    units = LocalDepthSupplementOverlay.get_supplemental_units()
    assert len(units) == 4

    u_map = {u["unit_id"]: u for u in units}

    # 1. Derivative Parameter Extrema Count
    u1 = u_map["M12_D043_DERIV_PARAM_EXTREMA_001"]
    assert u1["problem_type_code"] == "PARAMETER_EXTREMA_COUNT"
    assert u1["correct_answer"] == "2"
    assert u1["source_code"] == "SRC_TRIAL_2026_01"
    assert u1["question_page_1_based"] == 5
    assert u1["solution_page_1_based"] == 20
    assert u1["visual_required"] is False

    # 2. Derivative Real World Monotonicity Interpretation Group
    u2 = u_map["M12_D043_DERIV_REALWORLD_MONO_GROUP_001"]
    assert u2["problem_type_code"] == "REAL_WORLD_MONOTONICITY_INTERPRETATION"
    assert u2["source_code"] == "SRC_TRIAL_2026_04"
    assert u2["atomic_group_policy"] is True
    tf_pattern = [c["correct_answer"] for c in u2["source_children"]]
    assert tf_pattern == [True, False, True, False]
    assert u2["source_children"][2]["target_problem_type_evidence"] == "REAL_WORLD_MONOTONICITY_INTERPRETATION"

    # 3. Vector Coordinate Linear Operations
    u3 = u_map["M12_D043_VECTOR_LINEAROPS_001"]
    assert u3["problem_type_code"] == "VECTOR_COORDINATE_LINEAR_OPERATIONS_3D"
    assert u3["correct_answer"] == "D"
    assert u3["correct_answer_value"] == "√74"
    assert u3["source_code"] == "SRC_TRIAL_2026_14"
    assert u3["question_page_1_based"] == 2
    assert u3["solution_page_1_based"] == 8

    # 4. Probability Tree Practice Question
    u4 = u_map["M12_D043_PROB_TREE_001"]
    assert u4["problem_type_code"] == "TREE_OR_TOTAL_PROBABILITY"
    assert u4["correct_answer"] == "0.76"
    assert u4["source_code"] == "SRC_TRIAL_2026_13"
    assert u4["question_page_1_based"] == 5
    assert u4["solution_pages_1_based"] == [18, 19]
    assert "CONDITIONAL_PROBABILITY_DIRECT" in u4["secondary_problem_type_evidence"]
    assert "TOTAL_PROBABILITY" in u4["secondary_problem_type_evidence"]


def test_png_asset_bytes_sha_and_dimensions() -> None:
    png_path = DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "assets" / "M12_PROB_TREE_TRIAL_2026_13.png"
    assert png_path.is_file()
    data = png_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXPECTED_PNG_ASSET_SHA256
    w, h = struct.unpack(">II", data[16:24])
    assert w == EXPECTED_PNG_WIDTH
    assert h == EXPECTED_PNG_HEIGHT


def test_local_depth_supplement_mutations(tmp_path: Path) -> None:
    d_copy = tmp_path / "local_depth"
    shutil.copytree(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH, d_copy)
    validator = LocalDepthSupplementValidator()

    # Mutation 1: Mutate parameter extrema answer 2 -> 3
    u_file = d_copy / "verified_units.json"
    u_data = _load_json(u_file)
    u_data["units"][0]["correct_answer"] = "3"
    _write_json(u_file, u_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "UNIT_1_ANSWER_MISMATCH" in _codes(rep)
    _write_json(u_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "verified_units.json"))

    # Mutation 2: Mutate T/F pattern [T, F, T, F] -> [T, T, T, F]
    u_data = _load_json(u_file)
    u_data["units"][1]["source_children"][1]["correct_answer"] = True
    _write_json(u_file, u_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "UNIT_2_TF_PATTERN_MISMATCH" in _codes(rep)
    _write_json(u_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "verified_units.json"))

    # Mutation 3: Mutate vector answer D -> C
    u_data = _load_json(u_file)
    u_data["units"][2]["correct_answer"] = "C"
    _write_json(u_file, u_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "UNIT_3_ANSWER_MISMATCH" in _codes(rep)
    _write_json(u_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "verified_units.json"))

    # Mutation 4: Mutate vector answer value √74 -> 74
    u_data = _load_json(u_file)
    u_data["units"][2]["correct_answer_value"] = "74"
    _write_json(u_file, u_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "UNIT_3_ANSWER_VALUE_MISMATCH" in _codes(rep)
    _write_json(u_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "verified_units.json"))

    # Mutation 5: Mutate probability answer 0.76 -> 0.75
    u_data = _load_json(u_file)
    u_data["units"][3]["correct_answer"] = "0.75"
    _write_json(u_file, u_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "UNIT_4_ANSWER_MISMATCH" in _codes(rep)
    _write_json(u_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "verified_units.json"))

    # Mutation 6: Mutate source pages
    u_data = _load_json(u_file)
    u_data["units"][0]["question_page_1_based"] = 6
    _write_json(u_file, u_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "UNIT_1_PAGES_MISMATCH" in _codes(rep)
    _write_json(u_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "verified_units.json"))

    # Mutation 7: Mutate source PDF SHA
    s_file = d_copy / "source_registry.json"
    s_data = _load_json(s_file)
    s_data["sources"][0]["sha256"] = "deadbeef" * 8
    _write_json(s_file, s_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "SOURCE_SHA_MISMATCH" in _codes(rep)
    _write_json(s_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "source_registry.json"))

    # Mutation 8: Mutate synthetic_question_generation = true
    s_data = _load_json(s_file)
    s_data["policy"]["synthetic_question_generation"] = True
    _write_json(s_file, s_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "SYNTHETIC_GENERATION_NOT_BLOCKED" in _codes(rep)
    _write_json(s_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "source_registry.json"))

    # Mutation 9: PNG byte tamper
    png_file = d_copy / "assets" / "M12_PROB_TREE_TRIAL_2026_13.png"
    png_bytes = png_file.read_bytes()
    png_file.write_bytes(png_bytes + b"\x00")
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "PNG_BYTES_SHA_MISMATCH" in _codes(rep)
    png_file.write_bytes(png_bytes)

    # Mutation 10: Vector remaining zero set nonempty
    cov_file = d_copy / "coverage_after_043.json"
    cov_data = _load_json(cov_file)
    cov_data["effects"]["vector_legacy_remaining_zero_evidence"] = ["SOME_VECTOR_PT"]
    _write_json(cov_file, cov_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "VECTOR_REMAINING_ZERO_MISMATCH" in _codes(rep)
    _write_json(cov_file, _load_json(DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH / "coverage_after_043.json"))

    # Mutation 11: Derivative remaining zero set not exactly [PARAMETER_MONOTONICITY]
    cov_data = _load_json(cov_file)
    cov_data["effects"]["derivative_remaining_zero_evidence"] = []
    _write_json(cov_file, cov_data)
    rep = validator.validate(dataset_path=d_copy)
    assert not rep.is_valid
    assert "DERIVATIVE_REMAINING_ZERO_MISMATCH" in _codes(rep)


# ======================================================================
# 2. DATA-MATH12-044 Operational Evidence Tests
# ======================================================================

def test_operational_evidence_validator_reports_pass() -> None:
    report = OperationalEvidenceValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_OPERATIONAL_EVIDENCE_AGGREGATE_SHA256
    assert report.ci_evidence_state == "PASS_GREEN_RUN_CAPTURED"
    assert report.workflow_run_id == EXPECTED_CI_FACTS["run_id"]
    assert report.historical_data042_immutable is True
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.production_ready is False
    assert report.canonical_activation_blocked is True
    assert report.postgres_import_blocked is True
    assert report.production_release_blocked is True
    assert report.gates == EXPECTED_REFRESHED_GATES


def test_historical_data042_immutability_enforced(tmp_path: Path) -> None:
    # Verify that tampering historical DATA-042 causes DATA-044 validator to fail
    d042_copy = tmp_path / "prod_gate"
    shutil.copytree(DEFAULT_PRODUCTION_GATE_PATH, d042_copy)

    # Mutate historical DATA-042
    p_file = d042_copy / "production_gate.json"
    p_data = _load_json(p_file)
    p_data["gates"]["ci_evidence"] = "PASS_GREEN"
    _write_json(p_file, p_data)

    rep = OperationalEvidenceValidator().validate(data042_path=d042_copy)
    assert not rep.is_valid
    assert "DATA042_CI_EVIDENCE_MUTATED" in _codes(rep)


def test_operational_evidence_mutations(tmp_path: Path) -> None:
    op_copy = tmp_path / "op_ev"
    shutil.copytree(DEFAULT_OPERATIONAL_EVIDENCE_PATH, op_copy)
    validator = OperationalEvidenceValidator()

    # Mutation 1: Mutate CI conclusion to failure
    ci_file = op_copy / "ci_evidence.json"
    ci_data = _load_json(ci_file)
    ci_data["workflow"]["conclusion"] = "failure"
    _write_json(ci_file, ci_data)
    rep = validator.validate(dataset_path=op_copy)
    assert not rep.is_valid
    assert "CONCLUSION_MISMATCH" in _codes(rep)
    _write_json(ci_file, _load_json(DEFAULT_OPERATIONAL_EVIDENCE_PATH / "ci_evidence.json"))

    # Mutation 2: Mutate test result passed count
    ci_data = _load_json(ci_file)
    ci_data["workflow"]["test_result"]["passed"] = 700
    _write_json(ci_file, ci_data)
    rep = validator.validate(dataset_path=op_copy)
    assert not rep.is_valid
    assert "TEST_COUNTS_MISMATCH" in _codes(rep)
    _write_json(ci_file, _load_json(DEFAULT_OPERATIONAL_EVIDENCE_PATH / "ci_evidence.json"))

    # Mutation 3: Mutate rights_review_state to APPROVED
    ci_data = _load_json(ci_file)
    ci_data["rights_review_state"] = "APPROVED"
    _write_json(ci_file, ci_data)
    rep = validator.validate(dataset_path=op_copy)
    assert not rep.is_valid
    assert "RIGHTS_NOT_REVIEW_REQUIRED" in _codes(rep)
    _write_json(ci_file, _load_json(DEFAULT_OPERATIONAL_EVIDENCE_PATH / "ci_evidence.json"))

    # Mutation 4: Mutate database_import_state to ALLOWED
    ci_data = _load_json(ci_file)
    ci_data["database_import_state"] = "ALLOWED"
    _write_json(ci_file, ci_data)
    rep = validator.validate(dataset_path=op_copy)
    assert not rep.is_valid
    assert "DB_IMPORT_NOT_BLOCKED" in _codes(rep)


# ======================================================================
# 3. DATA-MATH12-045 Depth Queue Tests
# ======================================================================

def test_depth_queue_validator_reports_pass() -> None:
    report = DepthQueueValidator().validate()
    assert report.is_valid, [e.message for e in report.errors]
    assert report.status == "PASS"
    assert report.aggregate_semantic_sha256 == EXPECTED_DEPTH_QUEUE_AGGREGATE_SHA256
    assert report.derivative_zero_evidence == EXPECTED_DERIVATIVE_ZERO
    assert report.vector_zero_evidence == EXPECTED_VECTOR_ZERO
    assert report.queue_items_count == 3
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.canonical_write_allowed is False
    assert report.database_import_allowed is False
    assert report.production_release_allowed is False


def test_depth_queue_unpinned_leads_and_targets() -> None:
    q_data = _load_json(DEFAULT_DEPTH_QUEUE_PATH / "remaining_ingestion_queue.json")
    for item in q_data["priority_ingestion"]:
        assert item["status"] == EXPECTED_QUEUE_STATUS
        assert item["promotion_allowed"] is False
        assert "source_pdf_sha256" not in item


def test_depth_queue_mutations(tmp_path: Path) -> None:
    q_copy = tmp_path / "queue"
    shutil.copytree(DEFAULT_DEPTH_QUEUE_PATH, q_copy)
    validator = DepthQueueValidator()

    # Mutation 1: External lead promoted to VERIFIED
    q_file = q_copy / "remaining_ingestion_queue.json"
    q_data = _load_json(q_file)
    q_data["priority_ingestion"][0]["status"] = "VERIFIED"
    _write_json(q_file, q_data)
    rep = validator.validate(dataset_path=q_copy)
    assert not rep.is_valid
    assert "INVALID_QUEUE_STATUS" in _codes(rep)
    _write_json(q_file, _load_json(DEFAULT_DEPTH_QUEUE_PATH / "remaining_ingestion_queue.json"))

    # Mutation 2: Premature SHA pinning
    q_data = _load_json(q_file)
    q_data["priority_ingestion"][0]["source_pdf_sha256"] = "cafebabe" * 8
    _write_json(q_file, q_data)
    rep = validator.validate(dataset_path=q_copy)
    assert not rep.is_valid
    assert "PREMATURE_SHA_PINNING" in _codes(rep)
    _write_json(q_file, _load_json(DEFAULT_DEPTH_QUEUE_PATH / "remaining_ingestion_queue.json"))

    # Mutation 3: Synthetic gap fill enabled
    q_data = _load_json(q_file)
    q_data["policy"]["synthetic_gap_fill"] = True
    _write_json(q_file, q_data)
    rep = validator.validate(dataset_path=q_copy)
    assert not rep.is_valid
    assert "SYNTHETIC_GAP_FILL_NOT_FALSE" in _codes(rep)
    _write_json(q_file, _load_json(DEFAULT_DEPTH_QUEUE_PATH / "remaining_ingestion_queue.json"))

    # Mutation 4: Unhashed external source counted as verified
    q_data = _load_json(q_file)
    q_data["policy"]["unhashed_external_source_counts_as_verified"] = True
    _write_json(q_file, q_data)
    rep = validator.validate(dataset_path=q_copy)
    assert not rep.is_valid
    assert "UNHASHED_COUNTED_AS_VERIFIED" in _codes(rep)


# ======================================================================
# 4. Joint Consistency & Regression: DATA-038..042 + DATA-043..045
# ======================================================================

def test_joint_consistency_data038_through_data045() -> None:
    # DATA-038
    assert CanonicalSnapshotCandidateValidator().validate().is_valid
    # DATA-039
    assert DepthCorrectionOverlayValidator().validate().is_valid
    # DATA-040
    assert DiagnosticGraphValidator().validate().is_valid
    # DATA-041
    assert QualityAuditValidator().validate().is_valid
    # DATA-042
    assert ProductionGateValidator().validate().is_valid
    # DATA-043
    assert LocalDepthSupplementValidator().validate().is_valid
    # DATA-044
    assert OperationalEvidenceValidator().validate().is_valid
    # DATA-045
    assert DepthQueueValidator().validate().is_valid

    # Full session 038-042 runner
    res_038 = validate_full_session_038_042()
    assert res_038["status"] == "PASS"

    # Full session 043-045 runner
    res_043 = validate_full_session_043_045()
    assert res_043["status"] == "PASS"
    assert res_043["summary"]["official_core_requirements"] == "20/20"
    assert res_043["summary"]["new_source_backed_units"] == 4
    assert res_043["summary"]["derivative_zero_evidence_after"] == ["PARAMETER_MONOTONICITY"]
    assert res_043["summary"]["vector_zero_evidence_after"] == []
    assert res_043["summary"]["probability_practice_units_after"] == 22
    assert res_043["summary"]["ci_evidence_state"] == "PASS_GREEN_RUN_CAPTURED"
    assert res_043["summary"]["production_ready"] is False

    exit_code = session_main_043_045(["--json"])
    assert exit_code == 0
