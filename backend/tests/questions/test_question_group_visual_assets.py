from __future__ import annotations

import copy
import hashlib
import json
import shutil
import struct
from collections.abc import Callable
from pathlib import Path

import pytest

from app.questions.question_group_review_overlay import (
    EffectiveQuestionGroupReviewMaterializer,
)
from app.questions.question_group_review_validator import (
    QuestionGroupReviewValidator,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_visual_assets import (
    BLOCKED_SOURCE_VISUAL_MISSING,
    DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT,
    READY_SOURCE_CROP,
    QuestionGroupVisualAssetValidator,
)


EXPECTED_REQUIRED_IDS = {
    "M12_DERIV_GROUP_0012",
    "M12_DERIV_GROUP_0024",
    "M12_DERIV_GROUP_0070",
    "M12_DERIV_GROUP_0087",
    "M12_DERIV_GROUP_0089",
    "M12_DERIV_GROUP_0113",
    "M12_DERIV_GROUP_0154",
    "M12_DERIV_GROUP_0163",
    "M12_DERIV_GROUP_0170",
}
EXPECTED_BLOCKED_ID = "M12_DERIV_GROUP_0012"
EXPECTED_REVIEW_COUNTS = {
    "structural_groups": 67,
    "structural_holds": 1,
    "review_batches": 6,
    "target_groups": 67,
    "reviewed_groups": 67,
    "verified": 39,
    "hold": 10,
    "rejected": 18,
    "rejected_duplicate": 9,
    "rejected_out_of_scope": 9,
    "verified_child_statements": 156,
    "assigned_child_answers": 156,
    "visual_asset_required": 9,
    "promotion_ready": 0,
    "effective_usable_groups": 49,
}


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_registry(tmp_path: Path) -> Path:
    target = tmp_path / "visual_assets"
    shutil.copytree(DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT, target)
    return target


def _manifest_rows(root: Path) -> list[dict[str, object]]:
    manifest = _load(root / "visual_asset_manifest.json")
    assert isinstance(manifest, dict)
    rows = manifest["assets"]
    assert isinstance(rows, list)
    return rows


def _mutate_manifest(
    root: Path,
    mutate: Callable[[list[dict[str, object]]], None],
) -> None:
    manifest = _load(root / "visual_asset_manifest.json")
    assert isinstance(manifest, dict)
    rows = manifest["assets"]
    assert isinstance(rows, list)
    mutate(rows)
    _write(root / "visual_asset_manifest.json", manifest)


def _effective_groups() -> dict[str, dict[str, object]]:
    groups = _load(
        DEFAULT_QUESTION_GROUP_STAGING_PATH / "question_group_candidates.json"
    )
    assert isinstance(groups, list)
    result = EffectiveQuestionGroupReviewMaterializer().materialize(groups)
    assert result.is_valid
    return {
        str(group["group_candidate_id"]): group
        for group in result.effective_groups
    }


def test_visual_registry_has_exact_required_ready_blocked_and_rights_counts() -> None:
    report = QuestionGroupVisualAssetValidator().validate()

    assert report.is_valid
    assert report.errors == ()
    assert set(report.required_group_ids) == EXPECTED_REQUIRED_IDS
    assert report.unresolved_group_ids == (EXPECTED_BLOCKED_ID,)
    assert report.counts == {
        "visual_required_groups": 9,
        "manifest_records": 9,
        "ready_source_crops": 8,
        "blocked_source_visual_missing": 1,
        "rights_review_required": 9,
        "promotion_eligible": 0,
    }
    assert all(row["rights_status"] == "REVIEW_REQUIRED" for row in report.records)
    assert all(row["promotion_eligible"] is False for row in report.records)


def test_all_ready_png_hashes_dimensions_and_paths_match_manifest() -> None:
    rows = _manifest_rows(DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT)
    ready = [row for row in rows if row["asset_status"] == READY_SOURCE_CROP]

    assert len(ready) == 8
    for row in ready:
        file_name = row["file_name"]
        assert isinstance(file_name, str)
        path = DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT / file_name
        data = path.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert data[12:16] == b"IHDR"
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert struct.unpack(">II", data[16:24]) == (
            row["width_px"],
            row["height_px"],
        )
        assert row["mime_type"] == "image/png"


def test_blocked_hue_group_has_no_asset_and_keeps_reason() -> None:
    rows = _manifest_rows(DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT)
    blocked = [
        row for row in rows if row["asset_status"] == BLOCKED_SOURCE_VISUAL_MISSING
    ]

    assert [row["group_candidate_id"] for row in blocked] == [EXPECTED_BLOCKED_ID]
    row = blocked[0]
    for field in ("file_name", "sha256", "mime_type", "width_px", "height_px"):
        assert row[field] is None
    assert isinstance(row["blocker_reason"], str) and row["blocker_reason"].strip()


def test_group_0163_uses_canonical_asset_page_and_preserves_structural_page() -> None:
    rows = {
        str(row["group_candidate_id"]): row
        for row in _manifest_rows(DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT)
    }
    group = _effective_groups()["M12_DERIV_GROUP_0163"]
    evidence = group["source_evidence"]
    row = rows["M12_DERIV_GROUP_0163"]

    assert row["asset_source_page"] == 701
    assert row["canonical_question_pages"] == [700, 701]
    assert group["source_page"] == 708
    assert evidence["candidate_extraction_page"] == 708
    assert evidence["solution_pages"] == [708, 709]


def test_raw_and_academic_review_invariants_remain_unchanged() -> None:
    raw_path = DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "candidate_questions.json"
    raw_before = raw_path.read_bytes()
    review_report = QuestionGroupReviewValidator().validate()

    assert hashlib.sha256(raw_before).hexdigest() == EXPECTED_RAW_CANDIDATE_SHA256
    assert raw_path.read_bytes() == raw_before
    assert review_report.is_valid
    assert review_report.counts == EXPECTED_REVIEW_COUNTS


def test_asset_sha_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)
    _mutate_manifest(root, lambda rows: rows[1].update({"sha256": "0" * 64}))

    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "ASSET_SHA256_MISMATCH" in {error.code for error in report.errors}


def test_missing_ready_asset_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)
    row = next(
        row for row in _manifest_rows(root) if row["asset_status"] == READY_SOURCE_CROP
    )
    (root / str(row["file_name"])).unlink()

    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "ASSET_FILE_MISSING" in {error.code for error in report.errors}


def test_duplicate_manifest_group_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)

    def duplicate(rows: list[dict[str, object]]) -> None:
        record = copy.deepcopy(rows[0])
        record["asset_id"] = "UNIQUE_TEST_ASSET_ID"
        rows.append(record)

    _mutate_manifest(root, duplicate)
    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "MANIFEST_IDENTIFIER_DUPLICATE" in {
        error.code for error in report.errors
    }


def test_duplicate_asset_id_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)
    _mutate_manifest(
        root, lambda rows: rows[1].update({"asset_id": rows[0]["asset_id"]})
    )

    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "MANIFEST_IDENTIFIER_DUPLICATE" in {
        error.code for error in report.errors
    }


def test_asset_path_traversal_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)
    _mutate_manifest(root, lambda rows: rows[1].update({"file_name": "../x.png"}))

    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "ASSET_PATH_INVALID" in {error.code for error in report.errors}


def test_asset_dimension_mismatch_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)
    _mutate_manifest(
        root, lambda rows: rows[1].update({"width_px": rows[1]["width_px"] + 1})
    )

    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "ASSET_DIMENSIONS_MISMATCH" in {
        error.code for error in report.errors
    }


@pytest.mark.parametrize(
    ("row_index", "updates", "error_code"),
    [
        (1, {"blocker_reason": "Not valid for READY"}, "READY_BLOCKER_INVALID"),
        (
            0,
            {"file_name": "assets/fabricated.png"},
            "BLOCKED_ASSET_FIELD_PRESENT",
        ),
        (0, {"blocker_reason": ""}, "BLOCKER_REASON_MISSING"),
    ],
)
def test_invalid_ready_and_blocked_field_combinations_are_rejected(
    tmp_path: Path,
    row_index: int,
    updates: dict[str, object],
    error_code: str,
) -> None:
    root = _copy_registry(tmp_path)
    _mutate_manifest(root, lambda rows: rows[row_index].update(updates))

    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert error_code in {error.code for error in report.errors}


def test_unknown_status_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)
    _mutate_manifest(root, lambda rows: rows[0].update({"asset_status": "UNKNOWN"}))

    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "UNKNOWN_ASSET_STATUS" in {error.code for error in report.errors}


def test_ready_asset_for_non_visual_group_is_rejected(tmp_path: Path) -> None:
    root = _copy_registry(tmp_path)

    def replace_group(rows: list[dict[str, object]]) -> None:
        rows[1]["group_candidate_id"] = "M12_DERIV_GROUP_0001"

    _mutate_manifest(root, replace_group)
    report = QuestionGroupVisualAssetValidator().validate(asset_root=root)

    assert not report.is_valid
    assert "READY_NON_VISUAL_GROUP" in {error.code for error in report.errors}
