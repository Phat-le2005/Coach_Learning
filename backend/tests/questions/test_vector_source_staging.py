from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.questions.group_import_service import TrustedQuestionGroupImportService
from app.questions.question_group_promotion import QuestionGroupPromotionValidator
from app.questions.question_group_review_validator import QuestionGroupReviewValidator
from app.questions.question_group_staging import EXPECTED_RAW_CANDIDATE_SHA256
from app.questions.question_group_visual_assets import QuestionGroupVisualAssetValidator
from app.questions.vector_source_staging import (
    DEFAULT_VECTOR_SOURCE_STAGING_PATH,
    EXPECTED_ANSWER_AUTHORITY,
    EXPECTED_PRIMARY_SOURCES,
    EXPECTED_SECONDARY_SOURCE,
    VectorQuestionSourceValidator,
)
from app.validate_vector_question_sources import main


def _load_manifest(path: Path = DEFAULT_VECTOR_SOURCE_STAGING_PATH) -> dict:
    return json.loads((path / "source_manifest.json").read_text(encoding="utf-8"))


def test_vector_source_manifest_preserves_exact_ids_hashes_and_rights() -> None:
    report = VectorQuestionSourceValidator().validate()
    manifest = _load_manifest()

    assert report.is_valid, report.as_dict()
    assert report.counts == {
        "primary_sources": 3,
        "secondary_sources": 1,
        "answer_authorities": 1,
        "seed_sources": 3,
    }
    assert {
        row["source_key"]: (row["drive_file_id"], row["sha256"])
        for row in manifest["primary_sources"]
    } == EXPECTED_PRIMARY_SOURCES
    secondary = manifest["secondary_sources"][0]
    assert (secondary["source_key"], secondary["drive_file_id"]) == (
        EXPECTED_SECONDARY_SOURCE
    )
    authority = manifest["answer_authority"][0]
    assert (authority["drive_file_id"], authority["sha256"]) == (
        EXPECTED_ANSWER_AUTHORITY
    )
    assert report.rights_status == "REVIEW_REQUIRED"


def test_secondary_pptx_never_qualifies_as_sole_promotion_evidence() -> None:
    manifest = _load_manifest()
    validator = VectorQuestionSourceValidator()

    assert validator.has_primary_promotion_evidence(
        [EXPECTED_SECONDARY_SOURCE[0]], manifest
    ) is False
    assert validator.has_primary_promotion_evidence(
        [next(iter(EXPECTED_PRIMARY_SOURCES))], manifest
    ) is True
    assert validator.validate().secondary_only_promotion_evidence is False


def test_true_false_four_and_oxyz_boundaries_are_preserved() -> None:
    contract = json.loads(
        (DEFAULT_VECTOR_SOURCE_STAGING_PATH / "question_scan_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["initial_status"] == "STRUCTURAL_CANDIDATE"
    assert "TRUE_FALSE_FOUR" in contract["allowed_question_structures"]
    assert contract["mixed_group_policy"] == {
        "rule": "Never split a shared-context TRUE_FALSE_FOUR during structural staging.",
        "action": (
            "Keep full group, set mixed_scope=true, classify each child during "
            "academic review."
        ),
    }
    assert contract["exclude_primary_intents"] == [
        "plane equation or plane normal as the main task",
        "line equation or line direction representation as the main task",
        "sphere equation/center/radius/tangent plane as the main task",
        "coordinate geometry distance tasks whose primary object is plane/line/sphere",
        "Grade-11 exponential/logarithm questions",
    ]


def test_source_validator_rejects_secondary_promotion_flag(tmp_path: Path) -> None:
    target = tmp_path / "source"
    shutil.copytree(DEFAULT_VECTOR_SOURCE_STAGING_PATH, target)
    manifest = _load_manifest(target)
    manifest["secondary_sources"][0]["promotion_allowed"] = True
    (target / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    report = VectorQuestionSourceValidator().validate(target)

    assert report.status == "FAIL"
    assert report.checks["secondary_promotion_boundary"] is False


def test_vector_source_cli_is_deterministic(capsys) -> None:
    assert main([]) == 0
    first = capsys.readouterr().out
    assert main([]) == 0
    second = capsys.readouterr().out
    assert first == second


def test_derivative_review_visual_promotion_and_draft_boundaries_remain() -> None:
    review = QuestionGroupReviewValidator().validate()
    visual = QuestionGroupVisualAssetValidator().validate()
    promotion = QuestionGroupPromotionValidator().validate()
    preview = TrustedQuestionGroupImportService().preview()

    assert review.is_valid and review.counts["reviewed_groups"] == 67
    assert review.counts["target_groups"] == 67
    assert review.counts["verified"] == 39
    assert promotion.is_valid
    assert promotion.counts["canonical_snapshot_ready_groups"] == 38
    assert promotion.counts["canonical_snapshot_ready_children"] == 152
    assert promotion.counts["production_release_eligible_groups"] == 0
    assert visual.is_valid
    assert visual.counts["ready_source_crops"] == 8
    assert visual.counts["blocked_source_visual_missing"] == 1
    assert preview.raw_candidate_sha256 == EXPECTED_RAW_CANDIDATE_SHA256
    assert preview.counts["draft_groups"] == 38
    assert preview.counts["draft_children"] == 152
    assert preview.production_release_eligible == 0
    assert preview.database_import_ready is False
    assert {group.status for group in preview.groups} == {"DRAFT"}
