from __future__ import annotations

import copy
import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from app.questions.question_group_promotion import (
    DEFAULT_QUESTION_GROUP_PROMOTION_ROOT,
    QuestionGroupPromotionReport,
    QuestionGroupPromotionValidator,
)
from app.questions.question_group_review_validator import (
    QuestionGroupReviewValidator,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    EXPECTED_RAW_CANDIDATE_SHA256,
)
from app.questions.question_group_visual_assets import (
    READY_SOURCE_CROP,
    QuestionGroupVisualAssetValidator,
)


EXPECTED_HOLD_IDS = {
    "M12_DERIV_GROUP_0047",
    "M12_DERIV_GROUP_0062",
    "M12_DERIV_GROUP_0072",
    "M12_DERIV_GROUP_0076",
    "M12_DERIV_GROUP_0084",
    "M12_DERIV_GROUP_0104",
    "M12_DERIV_GROUP_0108",
    "M12_DERIV_GROUP_0111",
    "M12_DERIV_GROUP_0138",
    "M12_DERIV_GROUP_0159",
}
EXPECTED_REJECTED_IDS = {
    "M12_DERIV_GROUP_0021",
    "M12_DERIV_GROUP_0026",
    "M12_DERIV_GROUP_0044",
    "M12_DERIV_GROUP_0053",
    "M12_DERIV_GROUP_0055",
    "M12_DERIV_GROUP_0068",
    "M12_DERIV_GROUP_0073",
    "M12_DERIV_GROUP_0082",
    "M12_DERIV_GROUP_0105",
    "M12_DERIV_GROUP_0114",
    "M12_DERIV_GROUP_0118",
    "M12_DERIV_GROUP_0122",
    "M12_DERIV_GROUP_0127",
    "M12_DERIV_GROUP_0139",
    "M12_DERIV_GROUP_0144",
    "M12_DERIV_GROUP_0145",
    "M12_DERIV_GROUP_0155",
    "M12_DERIV_GROUP_0175",
}
EXPECTED_VISUAL_READY_IDS = {
    "M12_DERIV_GROUP_0024",
    "M12_DERIV_GROUP_0070",
    "M12_DERIV_GROUP_0087",
    "M12_DERIV_GROUP_0089",
    "M12_DERIV_GROUP_0113",
    "M12_DERIV_GROUP_0154",
    "M12_DERIV_GROUP_0163",
    "M12_DERIV_GROUP_0170",
}
EXPECTED_PROMOTION_COUNTS = {
    "structural_groups": 67,
    "reviewed_groups": 67,
    "academic_verified_groups": 39,
    "academic_hold_groups": 10,
    "academic_rejected_groups": 18,
    "verified_children": 156,
    "visual_required_verified_groups": 9,
    "visual_ready_groups": 8,
    "visual_missing_groups": 1,
    "visual_not_required_groups": 30,
    "canonical_snapshot_ready_groups": 38,
    "canonical_snapshot_ready_children": 152,
    "canonical_snapshot_blocked_groups": 1,
    "rights_review_required_groups": 39,
    "taxonomy_staging_only_groups": 39,
    "production_release_eligible_groups": 0,
    "database_import_ready_groups": 0,
}
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


def _copy_promotion(tmp_path: Path) -> Path:
    target = tmp_path / "promotion"
    shutil.copytree(DEFAULT_QUESTION_GROUP_PROMOTION_ROOT, target)
    return target


def _mutate_manifest(
    root: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    path = root / "promotion_manifest.json"
    manifest = _load(path)
    assert isinstance(manifest, dict)
    mutate(manifest)
    _write(path, manifest)


def _effective_groups() -> dict[str, dict[str, object]]:
    report = QuestionGroupReviewValidator().validate()
    assert report.is_valid
    return {
        str(group["group_candidate_id"]): group
        for group in report.materialization.effective_groups
    }


@pytest.fixture(scope="module")
def promotion_report() -> QuestionGroupPromotionReport:
    report = QuestionGroupPromotionValidator().validate()
    assert report.is_valid
    return report


def test_exact_verified_snapshot_and_child_counts(
    promotion_report: QuestionGroupPromotionReport,
) -> None:
    manifest = _load(DEFAULT_QUESTION_GROUP_PROMOTION_ROOT / "promotion_manifest.json")
    assert isinstance(manifest, dict)
    records = manifest["records"]
    assert isinstance(records, list)

    assert len(records) == 39
    assert len(promotion_report.snapshot) == 38
    assert sum(len(group["children"]) for group in promotion_report.snapshot) == 152
    assert promotion_report.counts == EXPECTED_PROMOTION_COUNTS


def test_all_hold_rejected_and_missing_visual_groups_are_excluded(
    promotion_report: QuestionGroupPromotionReport,
) -> None:
    snapshot_ids = {
        str(group["external_group_key"]) for group in promotion_report.snapshot
    }

    assert set(promotion_report.excluded_hold_ids) == EXPECTED_HOLD_IDS
    assert set(promotion_report.excluded_rejected_ids) == EXPECTED_REJECTED_IDS
    assert promotion_report.excluded_visual_ids == ("M12_DERIV_GROUP_0012",)
    assert not snapshot_ids & EXPECTED_HOLD_IDS
    assert not snapshot_ids & EXPECTED_REJECTED_IDS
    assert "M12_DERIV_GROUP_0012" not in snapshot_ids


def test_ready_visual_groups_preserve_exact_asset_ids(
    promotion_report: QuestionGroupPromotionReport,
) -> None:
    visual_report = QuestionGroupVisualAssetValidator().validate()
    assert visual_report.is_valid
    expected = {
        str(record["group_candidate_id"]): record["asset_id"]
        for record in visual_report.records
        if record["asset_status"] == READY_SOURCE_CROP
    }
    actual = {
        str(group["external_group_key"]): group["visual_asset_id"]
        for group in promotion_report.snapshot
        if group["visual_asset_id"] is not None
    }

    assert set(expected) == EXPECTED_VISUAL_READY_IDS
    assert actual == expected


def test_nonvisual_snapshot_groups_do_not_require_assets(
    promotion_report: QuestionGroupPromotionReport,
) -> None:
    nonvisual = [
        group
        for group in promotion_report.snapshot
        if group["external_group_key"] not in EXPECTED_VISUAL_READY_IDS
    ]

    assert len(nonvisual) == 30
    assert all(group["visual_asset_id"] is None for group in nonvisual)


def test_snapshot_children_preserve_reviewed_answers_and_taxonomy(
    promotion_report: QuestionGroupPromotionReport,
) -> None:
    effective = _effective_groups()
    for group in promotion_report.snapshot:
        group_id = str(group["external_group_key"])
        academic = effective[group_id]["academic_review_record"]
        reviewed_items = academic["items"]
        children = group["children"]

        assert [child["label"] for child in children] == list("abcd")
        assert [child["order_index"] for child in children] == list(range(4))
        assert len(children) == 4
        for child, reviewed in zip(children, reviewed_items):
            label = child["label"]
            assert child["external_question_key"] == f"{group_id}:{label}"
            assert child["question_type"] == "TRUE_FALSE"
            assert child["content"] == reviewed["reviewed_content"]
            assert child["correct_answer"] in {"TRUE", "FALSE"}
            assert child["correct_answer"] == reviewed["correct_answer"]
            assert child["problem_types"] == reviewed["problem_types"]
            assert child["concepts"] == reviewed["concepts"]
            assert child["learning_outcomes"] == reviewed["learning_outcomes"]
            assert child["taxonomy_basis"] == reviewed["taxonomy_basis"]


def test_snapshot_preserves_source_evidence_and_review_lineage(
    promotion_report: QuestionGroupPromotionReport,
) -> None:
    effective = _effective_groups()
    for group in promotion_report.snapshot:
        group_id = str(group["external_group_key"])
        source_group = effective[group_id]
        evidence = source_group["source_evidence"]
        academic = source_group["academic_review_record"]

        assert group["content"] == academic["reviewed_group_context"]
        assert group["review_lineage"]["academic_review_record"] == academic
        assert group["review_lineage"]["source_evidence"] == evidence
        assert group["source"]["source_candidate_id"] == source_group[
            "source_candidate_id"
        ]
        assert group["source"]["source_fingerprint"] == source_group[
            "source_fingerprint"
        ]
        assert group["source"]["source_evidence_id"] == academic[
            "source_evidence_id"
        ]
        assert group["source"]["candidate_extraction_page"] == evidence[
            "candidate_extraction_page"
        ]


def test_snapshot_has_no_production_or_database_identity_fields(
    promotion_report: QuestionGroupPromotionReport,
) -> None:
    serialized = json.dumps(promotion_report.snapshot, ensure_ascii=False)

    assert all(
        group["production_release_eligible"] is False
        for group in promotion_report.snapshot
    )
    assert '"id"' not in serialized
    assert '"difficulty"' not in serialized
    assert '"exam_weight"' not in serialized
    assert '"cognitive_level"' not in serialized
    assert '"explanation"' not in serialized


def test_legacy_academic_and_visual_validators_remain_unchanged() -> None:
    review_report = QuestionGroupReviewValidator().validate()
    visual_report = QuestionGroupVisualAssetValidator().validate()

    assert review_report.is_valid
    assert review_report.counts == EXPECTED_REVIEW_COUNTS
    assert visual_report.is_valid
    assert visual_report.counts == {
        "visual_required_groups": 9,
        "manifest_records": 9,
        "ready_source_crops": 8,
        "blocked_source_visual_missing": 1,
        "rights_review_required": 9,
        "promotion_eligible": 0,
    }


def test_raw_candidate_sha_remains_immutable() -> None:
    raw_path = DEFAULT_QUESTION_GROUP_STAGING_PATH.parent / "candidate_questions.json"

    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == (
        EXPECTED_RAW_CANDIDATE_SHA256
    )


def test_materialization_is_deterministic() -> None:
    first = QuestionGroupPromotionValidator().validate()
    second = QuestionGroupPromotionValidator().validate()

    assert first.is_valid and second.is_valid
    assert first.snapshot == second.snapshot
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.counts == second.counts


@pytest.mark.parametrize(
    "forbidden_group_id",
    ["M12_DERIV_GROUP_0062", "M12_DERIV_GROUP_0021"],
)
def test_manifest_cannot_include_hold_or_rejected_group(
    tmp_path: Path,
    forbidden_group_id: str,
) -> None:
    root = _copy_promotion(tmp_path)

    def add_forbidden(manifest: dict[str, object]) -> None:
        records = manifest["records"]
        assert isinstance(records, list)
        extra = copy.deepcopy(records[0])
        extra["group_candidate_id"] = forbidden_group_id
        records.append(extra)

    _mutate_manifest(root, add_forbidden)
    report = QuestionGroupPromotionValidator().validate(promotion_root=root)

    assert not report.is_valid
    assert "NON_VERIFIED_GROUP_INCLUDED" in {error.code for error in report.errors}


def test_manifest_cannot_include_missing_visual_group_in_snapshot(
    tmp_path: Path,
) -> None:
    root = _copy_promotion(tmp_path)

    def force_ready(manifest: dict[str, object]) -> None:
        records = manifest["records"]
        assert isinstance(records, list)
        record = next(
            row
            for row in records
            if row["group_candidate_id"] == "M12_DERIV_GROUP_0012"
        )
        record["canonical_snapshot_ready"] = True
        record["canonical_snapshot_blockers"] = []

    _mutate_manifest(root, force_ready)
    report = QuestionGroupPromotionValidator().validate(promotion_root=root)

    assert not report.is_valid
    assert "SNAPSHOT_GATE_MISMATCH" in {error.code for error in report.errors}
    assert "M12_DERIV_GROUP_0012" not in {
        group["external_group_key"] for group in report.snapshot
    }


def test_manifest_cannot_mark_production_release_eligible(
    tmp_path: Path,
) -> None:
    root = _copy_promotion(tmp_path)

    def force_eligible(manifest: dict[str, object]) -> None:
        records = manifest["records"]
        assert isinstance(records, list)
        records[0]["production_release_eligible"] = True

    _mutate_manifest(root, force_eligible)
    report = QuestionGroupPromotionValidator().validate(promotion_root=root)

    assert not report.is_valid
    assert report.counts["production_release_eligible_groups"] == 1
    assert "PRODUCTION_ELIGIBILITY_FORBIDDEN" in {
        error.code for error in report.errors
    }


@pytest.mark.parametrize("field", ["difficulty", "exam_weight"])
def test_synthetic_scoring_metadata_is_rejected(
    tmp_path: Path,
    field: str,
) -> None:
    root = _copy_promotion(tmp_path)

    def add_scoring_value(manifest: dict[str, object]) -> None:
        records = manifest["records"]
        assert isinstance(records, list)
        records[0][field] = 0.5

    _mutate_manifest(root, add_scoring_value)
    report = QuestionGroupPromotionValidator().validate(promotion_root=root)

    assert not report.is_valid
    matching = [
        error
        for error in report.errors
        if error.code == "FORBIDDEN_INFERENCE_FIELD"
    ]
    assert matching
    assert any(error.location.endswith(f".{field}") for error in matching)


def test_database_import_ready_flag_is_rejected(tmp_path: Path) -> None:
    root = _copy_promotion(tmp_path)

    def force_db_ready(manifest: dict[str, object]) -> None:
        records = manifest["records"]
        assert isinstance(records, list)
        records[0]["database_import_ready"] = True

    _mutate_manifest(root, force_db_ready)
    report = QuestionGroupPromotionValidator().validate(promotion_root=root)

    assert not report.is_valid
    assert report.counts["database_import_ready_groups"] == 1
    assert "DATABASE_IMPORT_FORBIDDEN" in {error.code for error in report.errors}
