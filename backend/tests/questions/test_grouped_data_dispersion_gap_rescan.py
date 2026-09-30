from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from app.questions.grouped_data_dispersion_academic_review import (
    DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
    EXPECTED_REVIEW_AGGREGATE_SHA256 as EXPECTED_BASE_AGGREGATE_SHA256,
    GroupedDataDispersionAcademicReviewValidator,
)
from app.questions.grouped_data_dispersion_gap_rescan import (
    DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256,
    EXPECTED_COUNTS,
    EXPECTED_REMAINING_GAPS,
    EXPECTED_SEMANTIC_HASHES,
    GroupedDataDispersionGapRescanValidator,
)
from app.validate_grouped_data_dispersion_gap_rescan import main


def _load(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, value: Any) -> None:
    (root / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_dataset(tmp_path: Path) -> Path:
    destination = tmp_path / "gap_scan" / "v0_2"
    shutil.copytree(DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH, destination)
    return destination


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_data_math12_031_state() -> None:
    report = GroupedDataDispersionGapRescanValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == EXPECTED_COUNTS
    assert report.remaining_gaps == EXPECTED_REMAINING_GAPS
    assert report.aggregate_semantic_sha256 == EXPECTED_AGGREGATE_SEMANTIC_SHA256
    assert report.rights_status == "REVIEW_REQUIRED"
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False
    assert all(report.checks.values())


def test_base_dataset_data_math12_021_binding_remains_valid() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH
    contract = _load(root, "data_contract.json")
    result = _load(root, "gap_scan_result.json")

    assert result["base_dataset"] == "DATA-MATH12-021"
    assert result["base_review_aggregate_sha256"] == EXPECTED_BASE_AGGREGATE_SHA256
    assert not list(root.rglob("*.pdf"))

    base_report = GroupedDataDispersionAcademicReviewValidator().validate()
    assert base_report.is_valid, base_report.as_dict()
    assert base_report.review_aggregate_semantic_sha256 == EXPECTED_BASE_AGGREGATE_SHA256


def test_local_source_registry_and_remaining_gaps_preserved() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH
    sources = _load(root, "local_source_scan_registry.json")
    result = _load(root, "gap_scan_result.json")

    assert len(sources) == 22
    assert all(
        s["scan_status"] == "TARGETED_TEXT_LAYER_RESCAN_COMPLETED"
        for s in sources
    )
    assert result["new_local_source_backed_verified_candidates_found"] == 0
    assert result["resolved_gaps"] == []
    assert tuple(result["remaining_gaps"]) == EXPECTED_REMAINING_GAPS
    assert result["scan_scope"]["local_real_pdf_sources_scanned"] == 22
    assert result["scan_scope"]["ocr_used"] is False
    assert result["scan_scope"]["synthetic_question_generation_used"] is False


def test_external_leads_are_discovery_only_and_not_verified() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH
    leads = _load(root, "external_gap_leads.json")
    contract = _load(root, "data_contract.json")

    assert len(leads) == 4
    for lead in leads:
        assert lead["status"].startswith("DISCOVERY_ONLY")
        assert "lead_id" in lead
        assert "url" in lead
        assert len(lead["potential_gap_relevance"]) > 0
    assert contract["policy"]["external_lead_is_not_verified_data"] is True
    assert contract["policy"]["raw_source_required_before_verification"] is True
    assert contract["policy"]["no_synthetic_gap_fill"] is True


def test_rights_and_release_boundaries_remain_blocked() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH
    result = _load(root, "gap_scan_result.json")
    contract = _load(root, "data_contract.json")

    assert result["rights_status"] == "REVIEW_REQUIRED"
    assert result["database_import_allowed"] is False
    assert result["canonical_snapshot_allowed"] is False
    assert contract["required_invariants"]["database_import_allowed"] is False
    assert contract["required_invariants"]["canonical_snapshot_allowed"] is False


def test_validation_is_read_only_and_deterministic() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH
    before = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    first = GroupedDataDispersionGapRescanValidator().validate()
    second = GroupedDataDispersionGapRescanValidator().validate()
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
            "external_gap_leads.json",
            lambda value: value[0].__setitem__("status", "VERIFIED_EXTERNAL"),
            "LEAD_NOT_DISCOVERY_ONLY",
        ),
        (
            "local_source_scan_registry.json",
            lambda value: value[0].__setitem__("scan_status", "PENDING"),
            "SCAN_STATUS_INCOMPLETE",
        ),
        (
            "gap_scan_result.json",
            lambda value: value.__setitem__(
                "new_local_source_backed_verified_candidates_found", 1
            ),
            "NEW_CANDIDATES_NOT_ZERO",
        ),
        (
            "gap_scan_result.json",
            lambda value: value["scan_scope"].__setitem__("ocr_used", True),
            "OCR_USED_VIOLATION",
        ),
        (
            "gap_scan_result.json",
            lambda value: value.__setitem__("database_import_allowed", True),
            "DB_IMPORT_NOT_BLOCKED",
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

    report = GroupedDataDispersionGapRescanValidator().validate(root)

    assert not report.is_valid
    assert expected_code in _codes(report)
