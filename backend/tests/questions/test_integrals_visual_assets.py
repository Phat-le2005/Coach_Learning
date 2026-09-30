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
    IntegralsAcademicReviewValidator,
)
from app.questions.integrals_visual_assets import (
    DEFAULT_INTEGRALS_VISUAL_ASSET_PATH,
    EXPECTED_COUNTS,
    EXPECTED_VISUAL_AGGREGATE_SHA256,
    IntegralsVisualAssetValidator,
)
from app.validate_integrals_visual_assets import main


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _copy_visual_dataset(tmp_path: Path) -> Path:
    target = tmp_path / "visual_assets" / "v0_1"
    shutil.copytree(DEFAULT_INTEGRALS_VISUAL_ASSET_PATH, target)
    return target


def _codes(report: Any) -> set[str]:
    return {issue.code for issue in report.errors}


def test_validator_reports_exact_locked_data_math12_027_state() -> None:
    report = IntegralsVisualAssetValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == EXPECTED_COUNTS
    assert report.aggregate_semantic_and_assets_sha256 == (
        EXPECTED_VISUAL_AGGREGATE_SHA256
    )
    assert report.unresolved_candidate_ids == ()
    assert len(report.ready_candidate_ids) == 8
    assert len(report.not_required_after_review_candidate_ids) == 20
    assert len(report.not_required_from_academic_candidate_ids) == 49
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False
    assert all(report.checks.values())


def test_visual_decisions_cover_verified_academic_units_exactly() -> None:
    root = DEFAULT_INTEGRALS_VISUAL_ASSET_PATH
    decisions = _load(root / "visual_review_decisions.json")
    manifest = _load(root / "visual_asset_manifest.json")
    statuses = {row["candidate_id"]: row for row in decisions}

    assert len(statuses) == 77
    assert sum(
        row["visual_review_status"] == "READY_SOURCE_CROP"
        for row in decisions
    ) == 8
    assert sum(
        row["visual_review_status"] == "NOT_REQUIRED_AFTER_VISUAL_REVIEW"
        for row in decisions
    ) == 20
    assert sum(
        row["visual_review_status"] == "NOT_REQUIRED_FROM_ACADEMIC_REVIEW"
        for row in decisions
    ) == 49
    assert len(manifest["assets"]) == 8


def test_all_png_hashes_dimensions_and_policy_pass() -> None:
    root = DEFAULT_INTEGRALS_VISUAL_ASSET_PATH
    manifest = _load(root / "visual_asset_manifest.json")
    contract = _load(root / "visual_asset_contract.json")
    assets = manifest["assets"]

    assert len(list((root / "assets").glob("*.png"))) == 8
    assert len({row["asset_id"] for row in assets}) == 8
    assert len({row["candidate_id"] for row in assets}) == 8
    for row in assets:
        data = (root / row["file_name"]).read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        assert actual_hash == row["sha256"]
        assert actual_hash == contract["asset_file_hashes"][row["file_name"]]
        assert IntegralsVisualAssetValidator._png_dimensions(data) == (
            row["width_px"],
            row["height_px"],
        )
        assert row["asset_kind"] == "SOURCE_VISUAL_COMPONENT_CROP"
        assert row["answer_leakage_check"] == "PASS_DISTINCT_COMPONENT_ONLY"
        assert row["extraction_method"] == (
            "SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI"
        )
        assert row["component_count"] == 1
        assert len(row["source_component_boxes_pdf_points"]) == 1
    assert manifest["asset_policy"]["crop_scope"] == (
        "DISTINCT_SOURCE_VISUAL_COMPONENT_ONLY"
    )
    assert manifest["asset_policy"]["no_full_question_crop_for_production"] is True


def test_rights_and_release_boundaries_remain_blocked() -> None:
    root = DEFAULT_INTEGRALS_VISUAL_ASSET_PATH
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
    root = DEFAULT_INTEGRALS_VISUAL_ASSET_PATH
    before = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    first = IntegralsVisualAssetValidator().validate()
    second = IntegralsVisualAssetValidator().validate()
    after = {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in root.rglob("*")
        if file.is_file()
    }

    assert first.as_dict() == second.as_dict()
    assert before == after


def test_data_math12_023_binding_remains_valid() -> None:
    report = IntegralsAcademicReviewValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.aggregate_semantic_sha256 == EXPECTED_BASE_AGGREGATE_SHA256
    assert report.counts["verified_candidates"] == 77
    assert report.production_release_eligible == 0
    assert report.database_import_allowed is False
    assert report.canonical_snapshot_allowed is False


def test_cli_returns_success_and_locked_aggregate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["aggregate_semantic_and_assets_sha256"] == (
        EXPECTED_VISUAL_AGGREGATE_SHA256
    )


def test_png_byte_mutation_is_rejected(tmp_path: Path) -> None:
    root = _copy_visual_dataset(tmp_path)
    png = next((root / "assets").glob("*.png"))
    png.write_bytes(png.read_bytes() + b"corrupted")

    report = IntegralsVisualAssetValidator().validate(root)

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
                "source_component_boxes_pdf_points", [[0, 0, 0, 0]]
            ),
            "INVALID_COMPONENT_CROP",
        ),
        (
            "visual_asset_manifest.json",
            lambda value: value["assets"][0].__setitem__(
                "answer_leakage_check", "FAIL_LEAK"
            ),
            "ANSWER_LEAKAGE_CHECK_FAILED",
        ),
        (
            "visual_review_decisions.json",
            lambda value: value[0].__setitem__("promotion_ready", True),
            "UNAUTHORIZED_PROMOTION",
        ),
        (
            "visual_asset_stats.json",
            lambda value: value.__setitem__("production_release_eligible", 1),
            "PRODUCTION_RELEASE_COUNT_NONZERO",
        ),
        (
            "visual_asset_contract.json",
            lambda value: value.__setitem__(
                "aggregate_semantic_and_assets_sha256", "f" * 64
            ),
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
    root = _copy_visual_dataset(tmp_path)
    payload = _load(root / file_name)
    mutate(payload)
    _write(root / file_name, payload)

    report = IntegralsVisualAssetValidator().validate(root)

    assert not report.is_valid
    assert expected_code in _codes(report)
