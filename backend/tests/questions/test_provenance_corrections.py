from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from app.questions.provenance_corrections import (
    PRESERVED_PROVENANCE_FIELDS,
    QuestionProvenanceCorrectionResolver,
)
from app.questions.review_overlay import QuestionReviewOverlayResolver
from app.questions.staging_validator import (
    DEFAULT_QUESTION_STAGING_PATH,
    QuestionStagingValidator,
    candidate_promotion_blockers,
)


DATA_ROOT = DEFAULT_QUESTION_STAGING_PATH.parent
CORRECTION_PATH = DEFAULT_QUESTION_STAGING_PATH / "provenance_corrections.json"
SUBSOURCE_PATH = DEFAULT_QUESTION_STAGING_PATH / "subsource_catalog.json"
SOURCE_PATH = DEFAULT_QUESTION_STAGING_PATH / "source_catalog.json"
EXTRACTION_STATS_PATH = DEFAULT_QUESTION_STAGING_PATH / "extraction_stats.json"
RAW_CANDIDATE_PATH = DEFAULT_QUESTION_STAGING_PATH / "candidate_questions.json"
RAW_CANDIDATE_SHA256 = (
    "b627a458e0b18c0a4e0733e18864e0bd83165f94894a7d690e4fc1313f3ed4d5"
)
CORRECTION_CODE = "PROV_CORR_HUNG_YEN_2025_PAGE_BOUNDARY"
CORRECTED_IDS = {
    "M12_DERIV_CAND_0027",
    "M12_DERIV_CAND_0028",
    "M12_DERIV_CAND_0029",
    "M12_DERIV_CAND_0030",
    "M12_DERIV_CAND_0031",
    "M12_DERIV_CAND_0032",
}
REVIEW_BATCHES = tuple(sorted((DATA_ROOT / "review").glob("batch_*")))


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _raw_candidates() -> list[dict[str, object]]:
    value = _read_json(RAW_CANDIDATE_PATH)
    assert isinstance(value, list)
    return value


def _subsources() -> list[dict[str, object]]:
    value = _read_json(SUBSOURCE_PATH)
    assert isinstance(value, list)
    return value


def _write_corrections(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "provenance_corrections.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _resolve(
    *,
    candidates: list[dict[str, object]] | None = None,
    correction_path: Path = CORRECTION_PATH,
    subsources: list[dict[str, object]] | None = None,
):
    return QuestionProvenanceCorrectionResolver().resolve(
        candidates if candidates is not None else _raw_candidates(),
        correction_path,
        subsources if subsources is not None else _subsources(),
    )


def test_catalog_boundary_and_counts_are_corrected_without_extraction_changes() -> None:
    subsources = _subsources()
    by_code = {str(row["subsource_code"]): row for row in subsources}
    source_catalog = _read_json(SOURCE_PATH)
    extraction_stats = _read_json(EXTRACTION_STATS_PATH)

    assert len(subsources) == 55
    assert (by_code["HA_TINH_2025"]["start_page"], by_code["HA_TINH_2025"]["end_page"]) == (37, 54)
    assert (
        by_code["HUNG_YEN_2025"]["start_page"],
        by_code["HUNG_YEN_2025"]["end_page"],
    ) == (55, 72)
    assert by_code["DA_NANG_2025"]["start_page"] == 73
    assert isinstance(source_catalog, dict)
    provincial = next(
        row
        for row in source_catalog["sources"]
        if row["source_code"] == "SRC_PROVINCIAL_TRIAL_2025_COLLECTION"
    )
    assert provincial["scope"] == "11 đề Sở GDĐT được phát hiện"
    assert isinstance(extraction_stats, dict)
    assert extraction_stats["source_counts"] == {
        "SRC_MOET_EXAM_2025_SOLUTION_COMPILATION": 9,
        "SRC_PROVINCIAL_TRIAL_2025_COLLECTION": 47,
        "SRC_TRUONG_NGOC_VY_40_2026": 119,
    }


def test_six_corrections_preserve_raw_file_and_expose_effective_provenance() -> None:
    before = RAW_CANDIDATE_PATH.read_bytes()
    raw = _raw_candidates()
    raw_by_id = {str(candidate["candidate_id"]): candidate for candidate in raw}

    result = _resolve(candidates=raw)

    after = RAW_CANDIDATE_PATH.read_bytes()
    assert before == after
    assert hashlib.sha256(before).hexdigest() == RAW_CANDIDATE_SHA256
    assert result.report.status == "PASS"
    assert result.report.total == 6
    assert result.report.applied == 6
    assert result.report.errors == 0
    assert set(result.report.corrected_candidate_ids) == CORRECTED_IDS
    for candidate_id in CORRECTED_IDS:
        raw_candidate = raw_by_id[candidate_id]
        effective = result.candidate(candidate_id)
        assert raw_candidate["subsource_code"] == "HA_TINH_2025"
        assert effective["subsource_code"] == "HA_TINH_2025"
        assert effective["corrected_subsource_code"] == "HUNG_YEN_2025"
        assert effective["provenance_correction_code"] == CORRECTION_CODE
        assert all(
            effective[field] == raw_candidate[field]
            for field in PRESERVED_PROVENANCE_FIELDS
        )


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("source_page", 54, "SOURCE_PAGE_MISMATCH"),
        ("original_subsource_code", "VINH_PHUC_2025", "ORIGINAL_SUBSOURCE_MISMATCH"),
        ("corrected_subsource_code", "UNKNOWN_SUBSOURCE", "CORRECTED_SUBSOURCE_NOT_FOUND"),
    ],
)
def test_invalid_correction_reference_fails(
    tmp_path: Path,
    field: str,
    value: object,
    expected_code: str,
) -> None:
    payload = _read_json(CORRECTION_PATH)
    assert isinstance(payload, dict)
    corrections = payload["candidate_corrections"]
    assert isinstance(corrections, list) and isinstance(corrections[0], dict)
    corrections[0][field] = value

    result = _resolve(correction_path=_write_corrections(tmp_path, payload))

    assert result.report.status == "FAIL"
    assert expected_code in {issue.code for issue in result.report.issues}


def test_correction_fails_when_candidate_page_is_outside_corrected_range(
    tmp_path: Path,
) -> None:
    candidates = copy.deepcopy(_raw_candidates())
    candidate = next(
        row for row in candidates if row["candidate_id"] == "M12_DERIV_CAND_0027"
    )
    candidate["source_page"] = 73
    payload = _read_json(CORRECTION_PATH)
    assert isinstance(payload, dict)
    correction = next(
        row
        for row in payload["candidate_corrections"]
        if row["candidate_id"] == "M12_DERIV_CAND_0027"
    )
    correction["source_page"] = 73

    result = _resolve(
        candidates=candidates,
        correction_path=_write_corrections(tmp_path, payload),
    )

    assert result.report.status == "FAIL"
    assert "CORRECTED_SUBSOURCE_PAGE_OUT_OF_RANGE" in {
        issue.code for issue in result.report.issues
    }


def test_correction_fails_when_page_still_belongs_to_original_subsource() -> None:
    subsources = copy.deepcopy(_subsources())
    ha_tinh = next(
        row for row in subsources if row["subsource_code"] == "HA_TINH_2025"
    )
    ha_tinh["end_page"] = 72

    result = _resolve(subsources=subsources)

    assert result.report.status == "FAIL"
    assert "ORIGINAL_SUBSOURCE_PAGE_STILL_IN_RANGE" in {
        issue.code for issue in result.report.issues
    }


def test_duplicate_candidate_correction_fails(tmp_path: Path) -> None:
    payload = _read_json(CORRECTION_PATH)
    assert isinstance(payload, dict)
    corrections = payload["candidate_corrections"]
    assert isinstance(corrections, list) and isinstance(corrections[0], dict)
    corrections.append(copy.deepcopy(corrections[0]))

    result = _resolve(correction_path=_write_corrections(tmp_path, payload))

    assert result.report.status == "FAIL"
    assert "DUPLICATE_CANDIDATE_CORRECTION" in {
        issue.code for issue in result.report.issues
    }


def test_unknown_correction_field_fails(tmp_path: Path) -> None:
    payload = _read_json(CORRECTION_PATH)
    assert isinstance(payload, dict)
    correction = payload["candidate_corrections"][0]
    correction["subsource_code"] = "HUNG_YEN_2025"

    result = _resolve(correction_path=_write_corrections(tmp_path, payload))

    assert result.report.status == "FAIL"
    assert "UNKNOWN_CORRECTION_FIELDS" in {
        issue.code for issue in result.report.issues
    }


def test_validator_reports_corrections_and_preserves_review_decisions() -> None:
    report = QuestionStagingValidator().validate()
    assert report.provenance_corrections.total == 6
    assert report.provenance_corrections.applied == 6
    assert report.provenance_corrections.errors == 0
    assert report.effective_reviewed.status_summary == {
        "total": 175,
        "verified": 28,
        "hold": 21,
        "rejected": 31,
        "untouched_review_required": 95,
    }

    current = list(_resolve().candidates)
    for batch_path in REVIEW_BATCHES:
        overlay = QuestionReviewOverlayResolver().resolve(current, batch_path)
        assert overlay.report.is_valid
        current = list(overlay.candidates)
    by_id = {str(candidate["candidate_id"]): candidate for candidate in current}

    candidate_0032 = by_id["M12_DERIV_CAND_0032"]
    assert candidate_0032["status"] == "VERIFIED"
    assert candidate_0032["verified_correct_answer"] == "95"
    assert candidate_0032["subsource_code"] == "HA_TINH_2025"
    assert candidate_0032["corrected_subsource_code"] == "HUNG_YEN_2025"
    assert candidate_0032["promotion_ready"] is False
    assert "EXPLICIT_PROMOTION_REQUIRED" in candidate_promotion_blockers(
        candidate_0032
    )
    assert by_id["M12_DERIV_CAND_0030"]["review_record"]["review_status"] == (
        "HOLD_VISUAL_SOURCE_REVIEW"
    )
    assert by_id["M12_DERIV_CAND_0027"]["review_record"]["review_status"] == (
        "REJECTED_DUPLICATE"
    )
    for candidate_id in {
        "M12_DERIV_CAND_0027",
        "M12_DERIV_CAND_0030",
        "M12_DERIV_CAND_0032",
    }:
        review_record = by_id[candidate_id]["review_record"]
        assert review_record["subsource_code"] == "HA_TINH_2025"
        assert review_record["corrected_subsource_code"] == "HUNG_YEN_2025"
        assert review_record["provenance_correction_code"] == CORRECTION_CODE
