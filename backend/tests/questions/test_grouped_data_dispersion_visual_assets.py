from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.questions.grouped_data_dispersion_academic_review import (
    EXPECTED_REVIEW_AGGREGATE_SHA256,
    GroupedDataDispersionAcademicReviewValidator,
)
from app.questions.grouped_data_dispersion_visual_assets import (
    DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH,
    EXPECTED_CONTINUATION_PAGES,
    EXPECTED_COUNTS,
    EXPECTED_NOT_REQUIRED_ID,
    EXPECTED_VISUAL_AGGREGATE_SHA256,
    GroupedDataDispersionVisualAssetValidator,
)
from app.validate_grouped_data_dispersion_visual_assets import main


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_visual_dataset(tmp_path: Path) -> Path:
    target = tmp_path / "visual_assets" / "v0_1"
    shutil.copytree(DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH, target)
    return target


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_locked_data_math12_022_state() -> None:
    report = GroupedDataDispersionVisualAssetValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == EXPECTED_COUNTS
    assert report.aggregate_semantic_and_assets_sha256 == (
        EXPECTED_VISUAL_AGGREGATE_SHA256
    )
    assert report.unresolved_candidate_ids == ()
    assert report.not_required_candidate_ids == (EXPECTED_NOT_REQUIRED_ID,)
    assert report.question_continuation_candidate_ids == tuple(
        sorted(EXPECTED_CONTINUATION_PAGES)
    )
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False
    assert all(report.checks.values())


def test_visual_decisions_exactly_cover_verified_academic_units() -> None:
    decisions = _load(
        DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH
        / "visual_review_decisions.json"
    )
    manifest = _load(
        DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH
        / "visual_asset_manifest.json"
    )
    statuses = {row["candidate_id"]: row for row in decisions}

    assert len(statuses) == 38
    assert sum(
        row["visual_review_status"] == "READY_SOURCE_CROP"
        for row in decisions
    ) == 37
    assert len(manifest["assets"]) == 37
    assert statuses[EXPECTED_NOT_REQUIRED_ID]["visual_review_status"] == (
        "NOT_REQUIRED_FROM_ACADEMIC_REVIEW"
    )
    assert statuses[EXPECTED_NOT_REQUIRED_ID]["academic_visual_required"] is False
    assert statuses[EXPECTED_NOT_REQUIRED_ID]["visual_asset_id"] is None


def test_all_png_hashes_dimensions_and_component_only_policy_pass() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH
    manifest = _load(root / "visual_asset_manifest.json")
    contract = _load(root / "visual_asset_contract.json")
    assets = manifest["assets"]

    assert len(list((root / "assets").glob("*.png"))) == 37
    assert len({row["asset_id"] for row in assets}) == 37
    assert len({row["candidate_id"] for row in assets}) == 37
    for row in assets:
        data = (root / row["file_name"]).read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        assert actual_hash == row["sha256"]
        assert actual_hash == contract["asset_file_hashes"][row["file_name"]]
        assert GroupedDataDispersionVisualAssetValidator._png_dimensions(data) == (
            row["width_px"],
            row["height_px"],
        )
        assert row["asset_kind"] in {
            "SOURCE_DATA_TABLE_CROP",
            "SOURCE_DATA_CHART_CROP",
        }
        assert row["answer_leakage_check"] == "PASS_DISTINCT_COMPONENT_ONLY"
        assert row["extraction_method"] == (
            "SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI"
        )
    assert manifest["asset_policy"]["crop_scope"] == (
        "DISTINCT_SOURCE_DATA_COMPONENT_ONLY"
    )
    assert manifest["asset_policy"]["no_full_question_crop_for_production"] is True


def test_continuation_pages_and_anchor_pages_are_preserved_exactly() -> None:
    manifest = _load(
        DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH
        / "visual_asset_manifest.json"
    )
    assets = {row["candidate_id"]: row for row in manifest["assets"]}

    assert assets["M12_DISP_CAND_0003"]["question_anchor_page"] == 79
    assert assets["M12_DISP_CAND_0003"]["asset_source_page"] == 80
    assert assets["M12_DISP_CAND_0003"]["source_page_role"] == (
        "QUESTION_CONTINUATION"
    )
    assert assets["M12_DISP_CAND_0024"]["question_anchor_page"] == 624
    assert assets["M12_DISP_CAND_0024"]["asset_source_page"] == 625
    assert assets["M12_DISP_CAND_0024"]["source_page_role"] == (
        "QUESTION_CONTINUATION"
    )
    assert {
        row["candidate_id"]
        for row in manifest["assets"]
        if row["source_page_role"] == "QUESTION_CONTINUATION"
    } == set(EXPECTED_CONTINUATION_PAGES)


def test_rights_and_release_boundaries_remain_blocked() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH
    decisions = _load(root / "visual_review_decisions.json")
    manifest = _load(root / "visual_asset_manifest.json")
    stats = _load(root / "visual_asset_stats.json")

    assert all(row["rights_status"] == "REVIEW_REQUIRED" for row in decisions)
    assert all(row["promotion_ready"] is False for row in decisions)
    assert all(
        row["rights_status"] == "REVIEW_REQUIRED"
        and row["promotion_eligible"] is False
        for row in manifest["assets"]
    )
    assert stats["promotion_eligible_units"] == 0
    assert stats["production_release_eligible"] == 0
    assert stats["database_import_allowed"] is False
    assert stats["canonical_snapshot_allowed"] is False


def test_validation_is_read_only_and_deterministic() -> None:
    root = DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH
    before = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    first = GroupedDataDispersionVisualAssetValidator().validate()
    second = GroupedDataDispersionVisualAssetValidator().validate()
    after = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    assert first.as_dict() == second.as_dict()
    assert before == after


def test_data_math12_021_binding_and_regression_remain_valid() -> None:
    report = GroupedDataDispersionAcademicReviewValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.review_aggregate_semantic_sha256 == EXPECTED_REVIEW_AGGREGATE_SHA256
    assert report.counts["verified_standalone"] == 38
    assert report.counts["hold_mixed_scope_groups"] == 2
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False


def test_cli_returns_success_and_locked_aggregate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["aggregate_semantic_and_assets_sha256"] == (
        EXPECTED_VISUAL_AGGREGATE_SHA256
    )


def test_png_byte_mutation_is_rejected(tmp_path: Path) -> None:
    root = _copy_visual_dataset(tmp_path)
    png = next((root / "assets").glob("*.png"))
    png.write_bytes(png.read_bytes() + b"mutated")

    report = GroupedDataDispersionVisualAssetValidator().validate(root)

    assert not report.is_valid
    assert "PNG_HASH_OR_MIME_MISMATCH" in _codes(report)
    assert "AGGREGATE_MISMATCH" in _codes(report)


@pytest.mark.parametrize(
    ("file_name", "mutate", "expected_code"),
    [
        (
            "visual_asset_manifest.json",
            lambda value: value["assets"][0].__setitem__("sha256", "0" * 64),
            "PNG_HASH_OR_MIME_MISMATCH",
        ),
        (
            "visual_asset_manifest.json",
            lambda value: value["assets"][0].__setitem__(
                "crop_box_pdf_points", [0, 0, 0, 0]
            ),
            "INVALID_COMPONENT_CROP",
        ),
        (
            "visual_asset_manifest.json",
            lambda value: next(
                row
                for row in value["assets"]
                if row["candidate_id"] == "M12_DISP_CAND_0003"
            ).__setitem__("asset_source_page", 79),
            "INVALID_SOURCE_PAGE_ROLE",
        ),
        (
            "visual_review_decisions.json",
            lambda value: value[0].__setitem__("visual_review_status", "BLOCKED"),
            "INVALID_VISUAL_DECISION",
        ),
    ],
)
def test_curated_json_mutations_are_rejected(
    tmp_path: Path,
    file_name: str,
    mutate: Any,
    expected_code: str,
) -> None:
    root = _copy_visual_dataset(tmp_path)
    path = root / file_name
    value = _load(path)
    mutate(value)
    _write(path, value)

    report = GroupedDataDispersionVisualAssetValidator().validate(root)

    assert not report.is_valid
    assert "SEMANTIC_HASH_MISMATCH" in _codes(report)
    assert expected_code in _codes(report)


def test_missing_and_undeclared_pngs_are_rejected(tmp_path: Path) -> None:
    missing_root = _copy_visual_dataset(tmp_path / "missing")
    missing_png = next((missing_root / "assets").glob("*.png"))
    missing_png.unlink()
    missing_report = GroupedDataDispersionVisualAssetValidator().validate(
        missing_root
    )

    extra_root = _copy_visual_dataset(tmp_path / "extra")
    source = next((extra_root / "assets").glob("*.png"))
    shutil.copyfile(source, extra_root / "assets" / "undeclared.png")
    extra_report = GroupedDataDispersionVisualAssetValidator().validate(extra_root)

    assert not missing_report.is_valid
    assert "PNG_FILE_SET_MISMATCH" in _codes(missing_report)
    assert "ASSET_FILE_MISSING" in _codes(missing_report)
    assert not extra_report.is_valid
    assert "PNG_FILE_SET_MISMATCH" in _codes(extra_report)


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    root = _copy_visual_dataset(tmp_path)
    manifest_path = root / "visual_asset_manifest.json"
    manifest = _load(manifest_path)
    manifest["assets"][0]["file_name"] = "../outside.png"
    _write(manifest_path, manifest)

    report = GroupedDataDispersionVisualAssetValidator().validate(root)

    assert not report.is_valid
    assert "UNSAFE_ASSET_PATH" in _codes(report)


def test_source_pdf_binary_is_rejected(tmp_path: Path) -> None:
    root = _copy_visual_dataset(tmp_path)
    (root / "source.pdf").write_bytes(b"%PDF-forbidden")

    report = GroupedDataDispersionVisualAssetValidator().validate(root)

    assert not report.is_valid
    assert "SOURCE_PDF_BINARY_PRESENT" in _codes(report)
