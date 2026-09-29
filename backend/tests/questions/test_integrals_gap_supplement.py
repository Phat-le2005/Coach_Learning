from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from app.questions.integrals_academic_review import (
    DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_BASE_AGGREGATE_SHA256,
)
from app.questions.integrals_gap_supplement import (
    DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    EXPECTED_COUNTS,
    EXPECTED_GROUPED_DISPERSION_GAPS,
    EXPECTED_RESOLVED_GAP,
    EXPECTED_SEMANTIC_HASHES,
    IntegralsGapSupplementValidator,
)
from app.validate_integrals_gap_supplement import main


def _load(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, value: Any) -> None:
    (root / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "gap_supplement" / "v0_1"
    shutil.copytree(DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH, destination)
    return destination


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_data_math12_026_state() -> None:
    report = IntegralsGapSupplementValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == EXPECTED_COUNTS
    assert report.resolved_gap == EXPECTED_RESOLVED_GAP
    assert report.remaining_base_gaps == ()
    assert report.effective_definite_integral_coverage == 2
    assert report.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False
    assert all(report.checks.values())


def test_overlay_binds_to_data_math12_023_and_leaves_it_unchanged() -> None:
    root = DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH
    contract = _load(root, "data_contract.json")
    resolution = _load(root, "gap_resolution.json")

    assert contract["base_dataset"] == "DATA-MATH12-023"
    assert resolution["base_dataset"] == "DATA-MATH12-023"
    assert contract["policy"]["overlay_only_do_not_rewrite_base_data"] is True
    assert not list(root.rglob("*.pdf"))

    # Verify base dataset files remain immutable
    base_contract = _load(DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH, "data_contract.json")
    assert base_contract["aggregate_semantic_sha256"] == EXPECTED_BASE_AGGREGATE_SHA256


def test_definite_integral_evidence_gap_is_closed_by_overlay() -> None:
    root = DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH
    questions = _load(root, "verified_gap_questions.json")
    resolution = _load(root, "gap_resolution.json")

    assert len(questions) == 2
    assert all(row["target_gap"] == EXPECTED_RESOLVED_GAP for row in questions)
    assert all(row["problem_type_code"] == EXPECTED_RESOLVED_GAP for row in questions)
    assert resolution["resolved_gap"] == EXPECTED_RESOLVED_GAP
    assert resolution["verified_gap_candidates"] == 2
    assert resolution["resolution_status"] == "SOURCE_BACKED_EVIDENCE_FOUND"
    assert resolution["remaining_data_math12_023_gap_after_overlay"] == []


def test_grouped_dispersion_remaining_gaps_are_preserved() -> None:
    root = DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH
    scan = _load(root, "remaining_gap_scan.json")

    assert scan["grouped_data_dispersion_original_gaps"] == list(
        EXPECTED_GROUPED_DISPERSION_GAPS
    )
    assert scan["new_source_backed_verified_candidates_found"] == 0
    assert scan["decision"] == "KEEP_EXISTING_GAPS_NO_SYNTHETIC_FILL"


def test_verified_gap_questions_and_evidence_are_exact() -> None:
    root = DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH
    questions = _load(root, "verified_gap_questions.json")
    evidence = {row["candidate_id"]: row for row in _load(root, "source_evidence.json")}

    assert len(questions) == 2
    assert len(evidence) == 2
    for row in questions:
        cid = row["candidate_id"]
        ev = evidence[cid]
        assert row["review_status"] == "VERIFIED_SOURCE_ANSWER"
        assert row["answer_verification"] == "SOURCE_SOLUTION_EXPLICIT"
        assert row["correct_answer"] == ev["source_claimed_answer"]
        assert row["question_start_page"] == ev["question_page"]
        assert row["solution_answer_page"] == ev["solution_answer_page"]
        assert row["source_code"] == ev["source_code"]
        assert row["source_file_id"] == ev["source_file_id"]
        assert row["source_pdf_sha256"] == ev["source_pdf_sha256"]
        assert row["rights_status"] == "REVIEW_REQUIRED"
        assert row["promotion_ready"] is False
        assert row["database_import_allowed"] is False
        assert row["canonical_snapshot_allowed"] is False


def test_semantic_hashes_and_locked_aggregate_are_exact() -> None:
    root = DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH
    contract = _load(root, "data_contract.json")

    assert contract["semantic_sha256"] == EXPECTED_SEMANTIC_HASHES
    assert contract["aggregate_semantic_sha256"] == (
        EXPECTED_AGGREGATE_SEMANTIC_SHA256
    )
    for name, expected in EXPECTED_SEMANTIC_HASHES.items():
        value = _load(root, name)
        assert IntegralsGapSupplementValidator.semantic_sha256(value) == expected


def test_validation_is_read_only_and_deterministic() -> None:
    root = DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH
    before = {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.iterdir()
        if file.is_file()
    }

    first = IntegralsGapSupplementValidator().validate()
    second = IntegralsGapSupplementValidator().validate()
    after = {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.iterdir()
        if file.is_file()
    }

    assert first.as_dict() == second.as_dict()
    assert before == after


def test_cli_reports_pass_and_locked_aggregate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["aggregate_semantic_sha256"] == EXPECTED_AGGREGATE_SEMANTIC_SHA256


Mutation = Callable[[Any], None]


@pytest.mark.parametrize(
    ("file_name", "mutate", "expected_code"),
    [
        (
            "verified_gap_questions.json",
            lambda rows: rows[0].__setitem__("correct_answer", "Z_WRONG"),
            "INVALID_GAP_QUESTION_RECORD",
        ),
        (
            "verified_gap_questions.json",
            lambda rows: rows[0].__setitem__("review_status", "HOLD"),
            "INVALID_GAP_QUESTION_RECORD",
        ),
        (
            "verified_gap_questions.json",
            lambda rows: rows[0].__setitem__("source_file_id", "changed-file-id"),
            "INVALID_GAP_QUESTION_RECORD",
        ),
        (
            "verified_gap_questions.json",
            lambda rows: rows[0].__setitem__("source_pdf_sha256", "0" * 64),
            "INVALID_GAP_QUESTION_RECORD",
        ),
        (
            "verified_gap_questions.json",
            lambda rows: rows[0].__setitem__("question_start_page", 999999),
            "INVALID_GAP_QUESTION_RECORD",
        ),
        (
            "source_evidence.json",
            lambda rows: rows[0].__setitem__("solution_answer_page", 999999),
            "INVALID_SOURCE_EVIDENCE",
        ),
        (
            "gap_resolution.json",
            lambda value: value.__setitem__(
                "resolved_gap", "CALCULATE_ANTIDERIVATIVE"
            ),
            "INVALID_GAP_RESOLUTION",
        ),
        (
            "gap_resolution.json",
            lambda value: value.__setitem__("database_import_allowed", True),
            "RELEASE_STATS_BOUNDARY_VIOLATION",
        ),
        (
            "remaining_gap_scan.json",
            lambda value: value.__setitem__(
                "new_source_backed_verified_candidates_found", 1
            ),
            "INVALID_REMAINING_GAP_SCAN",
        ),
        (
            "data_contract.json",
            lambda value: value["semantic_sha256"].__setitem__(
                "verified_gap_questions.json", "0" * 64
            ),
            "SEMANTIC_HASH_MAP_MISMATCH",
        ),
    ],
)
def test_curated_mutations_are_rejected(
    tmp_path: Path,
    file_name: str,
    mutate: Mutation,
    expected_code: str,
) -> None:
    root = _copy_dataset(tmp_path)
    value = _load(root, file_name)
    mutate(value)
    _write(root, file_name, value)

    report = IntegralsGapSupplementValidator().validate(root)

    assert not report.is_valid
    assert expected_code in _codes(report)
    assert (
        "SEMANTIC_FILE_HASH_MISMATCH" in _codes(report)
        or "DATA_CONTRACT_HASH_MISMATCH" in _codes(report)
    )


def test_source_pdf_binary_is_rejected(tmp_path: Path) -> None:
    root = _copy_dataset(tmp_path)
    (root / "source.pdf").write_bytes(b"%PDF-forbidden")

    report = IntegralsGapSupplementValidator().validate(root)

    assert not report.is_valid
    assert "SOURCE_PDF_BINARY_PRESENT" in _codes(report)
