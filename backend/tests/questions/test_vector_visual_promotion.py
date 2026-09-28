from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from app.questions.group_import_service import TrustedQuestionGroupImportService
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.questions.vector_academic_review import (
    DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH,
    EXPECTED_REVIEW_AGGREGATE_SHA256,
    VectorAcademicReviewValidator,
)
from app.questions.vector_materialization import (
    DEFAULT_VECTOR_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_MATERIALIZATION_AGGREGATE,
    VectorQuestionMaterializationValidator,
)
from app.questions.vector_visual_promotion import (
    DEFAULT_VECTOR_PROMOTION_ROOT,
    DEFAULT_VECTOR_VISUAL_ASSET_ROOT,
    EXPECTED_AGGREGATE_SHA256,
    EXPECTED_BLOCKERS,
    EXPECTED_DOWNGRADE_IDS,
    EXPECTED_REPORT_COUNTS,
    VectorVisualPromotionValidator,
)
from app.validate_vector_visual_promotion import main


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _visual(name: str) -> Any:
    return _load(DEFAULT_VECTOR_VISUAL_ASSET_ROOT / name)


def _promotion(name: str) -> Any:
    return _load(DEFAULT_VECTOR_PROMOTION_ROOT / name)


def _review(name: str) -> Any:
    return _load(DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH / name)


def _copy_dataset(tmp_path: Path) -> tuple[Path, Path]:
    visual_root = tmp_path / "visual_assets" / "v0_1"
    promotion_root = tmp_path / "promotion" / "v0_1"
    shutil.copytree(DEFAULT_VECTOR_VISUAL_ASSET_ROOT, visual_root)
    shutil.copytree(DEFAULT_VECTOR_PROMOTION_ROOT, promotion_root)
    return visual_root, promotion_root


def test_validator_reports_exact_visual_and_snapshot_counts() -> None:
    report = VectorVisualPromotionValidator().validate()

    assert report.is_valid, report.as_dict()
    assert report.counts == EXPECTED_REPORT_COUNTS
    assert report.visual_downgrade_ids == EXPECTED_DOWNGRADE_IDS
    assert report.aggregate_semantic_and_assets_sha256 == EXPECTED_AGGREGATE_SHA256
    assert all(report.checks.values())


def test_visual_decisions_cover_exact_verified_candidate_ids() -> None:
    decisions = _visual("visual_review_decisions.json")
    standalone = _review("standalone_reviews.json")
    groups = _review("group_reviews.json")
    verified_ids = {
        row["candidate_id"]
        for row in standalone
        if row["review_status"] == "VERIFIED"
    } | {
        row["source_candidate_id"]
        for row in groups
        if row["review_status"] == "VERIFIED"
    }

    assert len(decisions) == len({row["candidate_id"] for row in decisions}) == 48
    assert {row["candidate_id"] for row in decisions} == verified_ids
    assert Counter(row["visual_review_status"] for row in decisions) == {
        "READY_SOURCE_CROP": 32,
        "NOT_REQUIRED_AFTER_VISUAL_REVIEW": 10,
        "NOT_REQUIRED_FROM_ACADEMIC_REVIEW": 6,
    }


def test_exact_ten_visual_review_downgrades_are_locked() -> None:
    decisions = _visual("visual_review_decisions.json")
    actual = tuple(
        sorted(
            row["candidate_id"]
            for row in decisions
            if row["visual_review_status"]
            == "NOT_REQUIRED_AFTER_VISUAL_REVIEW"
        )
    )

    assert actual == EXPECTED_DOWNGRADE_IDS
    assert all(
        row["academic_visual_required"] is True
        and row["visual_asset_id"] is None
        and row["visual_required_for_canonical_snapshot"] is False
        for row in decisions
        if row["candidate_id"] in actual
    )


def test_all_32_png_hashes_dimensions_crop_boxes_and_safety_fields() -> None:
    assets = _visual("visual_asset_manifest.json")["assets"]

    assert len(assets) == 32
    assert len({row["asset_id"] for row in assets}) == 32
    assert len({row["candidate_id"] for row in assets}) == 32
    for row in assets:
        path = DEFAULT_VECTOR_VISUAL_ASSET_ROOT / row["file_name"]
        data = path.read_bytes()
        crop = row["crop_box_pdf_points"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert VectorVisualPromotionValidator._png_dimensions(data) == (
            row["width_px"],
            row["height_px"],
        )
        assert len(crop) == 4 and all(value > 0 for value in crop)
        assert crop[2] > crop[0] and crop[3] > crop[1]
        assert row["asset_source_page"] > 0
        assert row["asset_source_page"] in row["canonical_question_pages"]
        assert row["asset_kind"] == "SOURCE_GEOMETRY_OR_FIGURE_CROP"
        assert row["asset_status"] == "READY_SOURCE_CROP"
        assert row["extraction_method"] == (
            "SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI"
        )
        assert row["rights_status"] == "REVIEW_REQUIRED"
        assert row["promotion_eligible"] is False


def test_visual_references_resolve_and_nonrequired_units_have_no_asset() -> None:
    assets = _visual("visual_asset_manifest.json")["assets"]
    decisions = _visual("visual_review_decisions.json")
    assets_by_id = {row["asset_id"]: row for row in assets}

    for decision in decisions:
        if decision["visual_review_status"] == "READY_SOURCE_CROP":
            asset = assets_by_id[decision["visual_asset_id"]]
            assert asset["candidate_id"] == decision["candidate_id"]
            assert decision["visual_required_for_canonical_snapshot"] is True
        else:
            assert decision["visual_asset_id"] is None
            assert decision["visual_required_for_canonical_snapshot"] is False


def test_snapshot_contains_only_exact_verified_units() -> None:
    standalone_snapshot = _promotion("canonical_standalone_questions.json")
    group_snapshot = _promotion("canonical_question_groups.json")
    standalone_reviews = _review("standalone_reviews.json")
    group_reviews = _review("group_reviews.json")

    assert len(standalone_snapshot) == 47
    assert len(group_snapshot) == 1
    assert {
        row["source_candidate_id"] for row in standalone_snapshot
    } == {
        row["candidate_id"]
        for row in standalone_reviews
        if row["review_status"] == "VERIFIED"
    }
    assert {row["group_candidate_id"] for row in group_snapshot} == {
        row["group_candidate_id"]
        for row in group_reviews
        if row["review_status"] == "VERIFIED"
    } == {"M12_VECTOR_GROUP_0040"}


def test_standalone_snapshot_answers_taxonomy_and_lineage_match_review() -> None:
    snapshot = _promotion("canonical_standalone_questions.json")
    reviews = {
        row["candidate_id"]: row
        for row in _review("standalone_reviews.json")
        if row["review_status"] == "VERIFIED"
    }

    for row in snapshot:
        review = reviews[row["source_candidate_id"]]
        taxonomy = review["taxonomy"]
        assert row["correct_answer"] == review["correct_answer"]
        assert row["taxonomy"] == {
            "problem_types": taxonomy["problem_types"],
            "concepts": taxonomy["concepts"],
            "learning_outcomes": taxonomy["learning_outcomes"],
            "taxonomy_basis": taxonomy["basis"],
        }
        assert row["source_lineage"] == {
            "source_code": review["source_code"],
            "source_file_id": review["source_file_id"],
            "source_sha256": review["source_sha256"],
            "candidate_source_page": review["candidate_source_page"],
            "source_evidence_id": review["source_evidence_id"],
        }


def test_content_patches_0018_and_0044_are_used_exactly() -> None:
    snapshot = {
        row["source_candidate_id"]: row
        for row in _promotion("canonical_standalone_questions.json")
    }
    patches = {
        row["candidate_id"]: row
        for row in _review("content_and_scope_patches.json")
    }

    for candidate_id in ("M12_VECTOR_CAND_0018", "M12_VECTOR_CAND_0044"):
        assert snapshot[candidate_id]["content"] == patches[candidate_id][
            "reviewed_content"
        ]
        assert snapshot[candidate_id]["content_basis"] == "ACADEMIC_REVIEW_PATCH"


def test_group_0040_remains_atomic_with_exact_scoring_answers_and_taxonomy() -> None:
    group = _promotion("canonical_question_groups.json")[0]
    reviews = {
        row["group_candidate_id"]: row for row in _review("group_reviews.json")
    }
    reviewed = reviews["M12_VECTOR_GROUP_0040"]

    assert group["group_candidate_id"] == "M12_VECTOR_GROUP_0040"
    assert group["group_type"] == "TRUE_FALSE_FOUR"
    assert group["scoring_policy"] == "MOET_2025_TRUE_FALSE"
    assert [item["label"] for item in group["items"]] == list("abcd")
    assert [item["order_index"] for item in group["items"]] == [0, 1, 2, 3]
    assert [item["correct_answer"] for item in group["items"]] == [
        "TRUE", "TRUE", "TRUE", "FALSE"
    ]
    assert [
        item["taxonomy"]["problem_types"][0]["code"] for item in group["items"]
    ] == [
        "VECTOR_COORDINATES_FROM_POINTS_3D",
        "VECTOR_LENGTH_DISTANCE_3D",
        "MIDPOINT_CENTROID_COORDINATES_3D",
        "VECTOR_ANGLE_3D",
    ]
    assert [item["correct_answer"] for item in group["items"]] == [
        item["correct_answer"] for item in reviewed["items"]
    ]
    assert group["visual"] == {
        "status": "READY_SOURCE_CROP",
        "asset_id": "M12_VECTOR_CAND_0040_VISUAL_V1",
    }


def test_all_snapshot_units_remain_rights_and_production_blocked() -> None:
    rows = [
        *_promotion("canonical_standalone_questions.json"),
        *_promotion("canonical_question_groups.json"),
    ]
    stats = _promotion("promotion_stats.json")
    manifest = _promotion("promotion_manifest.json")

    assert len(rows) == 48
    assert all(row["canonical_snapshot_ready"] is True for row in rows)
    assert all(row["production_release_eligible"] is False for row in rows)
    assert all(row["production_blockers"] == list(EXPECTED_BLOCKERS) for row in rows)
    assert stats["rights_review_required_units"] == 48
    assert stats["taxonomy_staging_only_units"] == 48
    assert stats["production_release_eligible_units"] == 0
    assert stats["database_import_ready_units"] == 0
    assert manifest["database_import_allowed"] is False


def test_no_forbidden_scoring_metadata_or_pdf_binary_exists() -> None:
    rows = [
        *_promotion("canonical_standalone_questions.json"),
        *_promotion("canonical_question_groups.json"),
    ]

    assert not any(
        VectorVisualPromotionValidator._contains_forbidden_field(row)
        for row in rows
    )
    assert not any(
        path.suffix.lower() == ".pdf"
        for root in (DEFAULT_VECTOR_VISUAL_ASSET_ROOT, DEFAULT_VECTOR_PROMOTION_ROOT)
        for path in root.rglob("*")
        if path.is_file()
    )


def test_semantic_and_asset_aggregate_is_deterministic() -> None:
    manifest = _promotion("promotion_manifest.json")
    first = VectorVisualPromotionValidator.aggregate_semantic_and_assets_sha256(
        DEFAULT_VECTOR_VISUAL_ASSET_ROOT,
        DEFAULT_VECTOR_PROMOTION_ROOT,
        manifest,
    )
    second = VectorVisualPromotionValidator.aggregate_semantic_and_assets_sha256(
        DEFAULT_VECTOR_VISUAL_ASSET_ROOT,
        DEFAULT_VECTOR_PROMOTION_ROOT,
        manifest,
    )

    assert first == second == EXPECTED_AGGREGATE_SHA256
    assert manifest["aggregate_semantic_and_assets_sha256"] == first


def test_json_mutation_with_updated_file_hash_still_fails_aggregate(
    tmp_path: Path,
) -> None:
    visual_root, promotion_root = _copy_dataset(tmp_path)
    stats_path = visual_root / "visual_asset_stats.json"
    stats = _load(stats_path)
    stats["academic_verified_units"] = 999
    stats_path.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    manifest_path = promotion_root / "promotion_manifest.json"
    manifest = _load(manifest_path)
    manifest["semantic_file_hashes"]["visual_assets/visual_asset_stats.json"] = (
        VectorVisualPromotionValidator.semantic_sha256(stats)
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    report = VectorVisualPromotionValidator().validate(visual_root, promotion_root)

    assert report.status == "FAIL"
    assert report.checks["semantic_hashes"] is True
    assert report.checks["aggregate_integrity"] is False
    assert any(
        issue.code == "PROMOTION_AGGREGATE_SHA256_MISMATCH"
        for issue in report.errors
    )


def test_png_byte_mutation_fails_asset_integrity(tmp_path: Path) -> None:
    visual_root, promotion_root = _copy_dataset(tmp_path)
    manifest = _load(promotion_root / "promotion_manifest.json")
    logical_name = sorted(manifest["asset_file_hashes"])[0]
    asset_path = visual_root.joinpath(*logical_name.split("/")[1:])
    asset_path.write_bytes(asset_path.read_bytes() + b"MUTATED")

    report = VectorVisualPromotionValidator().validate(visual_root, promotion_root)

    assert report.status == "FAIL"
    assert report.checks["asset_file_integrity"] is False
    assert report.checks["aggregate_integrity"] is False
    assert any(
        issue.code == "ASSET_FILE_SHA256_MISMATCH" for issue in report.errors
    )


def test_png_mutation_with_updated_manifests_still_fails_aggregate(
    tmp_path: Path,
) -> None:
    visual_root, promotion_root = _copy_dataset(tmp_path)
    promotion_manifest_path = promotion_root / "promotion_manifest.json"
    promotion_manifest = _load(promotion_manifest_path)
    logical_name = sorted(promotion_manifest["asset_file_hashes"])[0]
    asset_path = visual_root.joinpath(*logical_name.split("/")[1:])
    asset_path.write_bytes(asset_path.read_bytes() + b"MUTATED")
    actual_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()

    asset_manifest_path = visual_root / "visual_asset_manifest.json"
    asset_manifest = _load(asset_manifest_path)
    file_name = "/".join(logical_name.split("/")[1:])
    row = next(row for row in asset_manifest["assets"] if row["file_name"] == file_name)
    row["sha256"] = actual_hash
    asset_manifest_path.write_text(
        json.dumps(asset_manifest, ensure_ascii=False), encoding="utf-8"
    )
    promotion_manifest["asset_file_hashes"][logical_name] = actual_hash
    promotion_manifest["semantic_file_hashes"][
        "visual_assets/visual_asset_manifest.json"
    ] = VectorVisualPromotionValidator.semantic_sha256(asset_manifest)
    promotion_manifest_path.write_text(
        json.dumps(promotion_manifest, ensure_ascii=False), encoding="utf-8"
    )

    report = VectorVisualPromotionValidator().validate(visual_root, promotion_root)

    assert report.status == "FAIL"
    assert report.checks["visual_assets"] is True
    assert report.checks["semantic_hashes"] is True
    assert report.checks["asset_file_integrity"] is True
    assert report.checks["aggregate_integrity"] is False


def test_data_016_017_and_derivative_regressions_remain_green() -> None:
    materialization = VectorQuestionMaterializationValidator().validate()
    academic = VectorAcademicReviewValidator().validate()
    derivative_review = QuestionGroupReviewValidator().validate()
    derivative_visual = QuestionGroupVisualAssetValidator().validate()
    derivative_promotion = QuestionGroupPromotionValidator().validate()
    practice_preview = TrustedQuestionGroupImportService().preview()

    assert materialization.is_valid
    assert materialization.aggregate_semantic_sha256 == EXPECTED_MATERIALIZATION_AGGREGATE
    assert materialization.counts["raw"]["materialized_unique_candidates"] == 72
    assert materialization.counts["effective"]["candidates"] == 68
    assert academic.is_valid
    assert academic.review_aggregate_semantic_sha256 == EXPECTED_REVIEW_AGGREGATE_SHA256
    assert academic.counts["reviewed_candidates"] == 68
    assert academic.counts["review_status_counts"] == {
        "VERIFIED": 48,
        "REJECTED_DUPLICATE": 7,
        "REJECTED_OUT_OF_SCOPE_OXYZ": 9,
        "HOLD_MIXED_VECTOR_OXYZ": 4,
    }
    assert derivative_review.is_valid
    assert derivative_review.counts["reviewed_groups"] == 67
    assert derivative_review.counts["verified"] == 39
    assert derivative_visual.is_valid
    assert derivative_visual.counts["ready_source_crops"] == 8
    assert derivative_visual.counts["blocked_source_visual_missing"] == 1
    assert derivative_promotion.is_valid
    assert derivative_promotion.counts["canonical_snapshot_ready_groups"] == 38
    assert derivative_promotion.counts["canonical_snapshot_ready_children"] == 152
    assert derivative_promotion.counts["production_release_eligible_groups"] == 0
    assert practice_preview.counts["draft_groups"] == 38
    assert practice_preview.counts["draft_children"] == 152


def test_vector_visual_promotion_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out

    assert first == second
    assert '"status": "PASS"' in first
