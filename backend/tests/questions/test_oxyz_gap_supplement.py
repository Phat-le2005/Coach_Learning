from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from app.questions.oxyz_academic_review import (
    DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_BASE_AGGREGATE_SHA256,
)
from app.questions.oxyz_gap_supplement import (
    DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    EXPECTED_COUNTS,
    EXPECTED_RESOLVED_GAP,
    EXPECTED_SEMANTIC_HASHES,
    OxyzGapSupplementValidator,
)
from app.validate_oxyz_gap_supplement import main


def _load(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, value: Any) -> None:
    (root / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "gap_supplement" / "v0_1"
    shutil.copytree(DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH, destination)
    return destination


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_data_math12_029_state() -> None:
    report = OxyzGapSupplementValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == EXPECTED_COUNTS
    assert report.resolved_gap == EXPECTED_RESOLVED_GAP
    assert report.remaining_base_gaps == ()
    assert report.effective_plane_sphere_coverage == 1
    assert report.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False
    assert all(report.checks.values())


def test_overlay_binds_to_data_math12_024_and_leaves_it_unchanged() -> None:
    root = DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH
    contract = _load(root, "data_contract.json")
    resolution = _load(root, "gap_resolution.json")

    assert contract["base_dataset"] == "DATA-MATH12-024"
    assert resolution["base_dataset"] == "DATA-MATH12-024"
    assert contract["policy"]["overlay_only_do_not_rewrite_base_data"] is True
    assert not list(root.rglob("*.pdf"))

    base_contract = _load(DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH, "data_contract.json")
    assert base_contract["aggregate_semantic_sha256"] == EXPECTED_BASE_AGGREGATE_SHA256


def test_plane_sphere_relation_gap_is_closed_by_overlay() -> None:
    root = DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH
    questions = _load(root, "verified_gap_questions.json")
    resolution = _load(root, "gap_resolution.json")

    assert len(questions) == 1
    q = questions[0]
    assert q["target_gap"] == EXPECTED_RESOLVED_GAP
    assert q["problem_type_code"] == EXPECTED_RESOLVED_GAP
    assert q["source_parent_candidate_id"] == "M12_OXYZ_CAND_0037"
    assert q["correct_answer"] == [True, False, True, False]
    assert q["question_start_page"] == 25
    assert q["solution_answer_page"] == 35
    assert q["visual_asset_required"] is False
    assert resolution["resolved_gap"] == EXPECTED_RESOLVED_GAP
    assert resolution["verified_gap_candidates"] == 1
    assert resolution["resolution_status"] == "SOURCE_BACKED_EVIDENCE_FOUND"
    assert resolution["remaining_data_math12_024_gap_after_overlay"] == []


def test_source_evidence_matches_verified_candidate() -> None:
    root = DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH
    evidence = _load(root, "source_evidence.json")
    questions = _load(root, "verified_gap_questions.json")

    assert len(evidence) == 1
    ev = evidence[0]
    q = questions[0]
    assert ev["overlay_candidate_id"] == q["overlay_candidate_id"]
    assert ev["source_parent_candidate_id"] == q["source_parent_candidate_id"]
    assert ev["question_page"] == q["question_start_page"]
    assert ev["solution_answer_page"] == q["solution_answer_page"]
    assert ev["source_claimed_answer"] == q["correct_answer"]
    assert ev["source_solution_key_text"] == "a) ĐÚNG; b) SAI; c) ĐÚNG; d) SAI"
    assert ev["review_consistency"] == "CONFIRMED"


def test_rights_and_release_boundaries_remain_blocked() -> None:
    root = DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH
    questions = _load(root, "verified_gap_questions.json")
    resolution = _load(root, "gap_resolution.json")
    contract = _load(root, "data_contract.json")

    assert all(row["rights_status"] == "REVIEW_REQUIRED" for row in questions)
    assert all(row["promotion_ready"] is False for row in questions)
    assert all(row["database_import_allowed"] is False for row in questions)
    assert all(row["canonical_snapshot_allowed"] is False for row in questions)
    assert resolution["rights_status"] == "REVIEW_REQUIRED"
    assert resolution["production_release_eligible"] == 0
    assert resolution["database_import_allowed"] is False
    assert resolution["canonical_snapshot_allowed"] is False
    assert contract["required_invariants"]["production_release_eligible"] == 0
    assert contract["required_invariants"]["database_import_allowed"] is False
    assert contract["required_invariants"]["canonical_snapshot_allowed"] is False


def test_validation_is_read_only_and_deterministic() -> None:
    root = DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH
    before = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    first = OxyzGapSupplementValidator().validate()
    second = OxyzGapSupplementValidator().validate()
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
    assert output["aggregate_semantic_sha256"] == (
        EXPECTED_AGGREGATE_SEMANTIC_SHA256
    )


@pytest.mark.parametrize(
    ("file_name", "mutate", "expected_code"),
    [
        (
            "verified_gap_questions.json",
            lambda value: value[0].__setitem__("correct_answer", [False, False, False, False]),
            "ANSWER_MISMATCH",
        ),
        (
            "verified_gap_questions.json",
            lambda value: value[0].__setitem__("target_gap", "WRONG_GAP"),
            "TARGET_GAP_MISMATCH",
        ),
        (
            "verified_gap_questions.json",
            lambda value: value[0].__setitem__("promotion_ready", True),
            "PROMOTION_NOT_BLOCKED",
        ),
        (
            "source_evidence.json",
            lambda value: value[0].__setitem__("review_consistency", "UNCONFIRMED"),
            "CONSISTENCY_NOT_CONFIRMED",
        ),
        (
            "gap_resolution.json",
            lambda value: value.__setitem__("production_release_eligible", 1),
            "PRODUCTION_RELEASE_COUNT_NONZERO",
        ),
        (
            "data_contract.json",
            lambda value: value.__setitem__("aggregate_semantic_sha256", "f" * 64),
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

    report = OxyzGapSupplementValidator().validate(root)

    assert not report.is_valid
    assert expected_code in _codes(report)
