from __future__ import annotations

import hashlib
import json
import struct
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.questions.vector_academic_review import (
    DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH,
    EXPECTED_REVIEW_AGGREGATE_SHA256,
    VectorAcademicReviewValidator,
)
from app.questions.vector_materialization import (
    DEFAULT_VECTOR_MATERIALIZATION_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_MATERIALIZATION_AGGREGATE_SHA256,
    VectorQuestionMaterializationValidator,
)


DEFAULT_VECTOR_DATA_ROOT = DEFAULT_VECTOR_MATERIALIZATION_PATH.parents[1]
DEFAULT_VECTOR_VISUAL_ASSET_ROOT = DEFAULT_VECTOR_DATA_ROOT / "visual_assets" / "v0_1"
DEFAULT_VECTOR_PROMOTION_ROOT = DEFAULT_VECTOR_DATA_ROOT / "promotion" / "v0_1"
EXPECTED_BASE_COMMIT = "10e56b62584216617c79bac97638701a4a5c1ae1"
EXPECTED_AGGREGATE_SHA256 = (
    "7e8b2cc2405d7fabfcbd14bb04e3f0ddda2a8aa192996424418f37be4e24a000"
)
EXPECTED_DOWNGRADE_IDS = (
    "M12_VECTOR_CAND_0011",
    "M12_VECTOR_CAND_0015",
    "M12_VECTOR_CAND_0018",
    "M12_VECTOR_CAND_0022",
    "M12_VECTOR_CAND_0031",
    "M12_VECTOR_CAND_0052",
    "M12_VECTOR_CAND_0057",
    "M12_VECTOR_CAND_0064",
    "M12_VECTOR_CAND_0066",
    "M12_VECTOR_CAND_0068",
)
EXPECTED_BLOCKERS = (
    "RIGHTS_REVIEW_REQUIRED",
    "VECTOR_TAXONOMY_NOT_CANONICALLY_ACTIVATED",
    "VECTOR_TRUSTED_IMPORT_BRIDGE_NOT_IMPLEMENTED",
    "SCORING_METADATA_POLICY_NOT_REVIEWED",
)
EXPECTED_PROMOTION_COUNTS: dict[str, Any] = {
    "dataset_code": "DATA-MATH12-018",
    "promotion_set_code": "MATH12_VECTOR_PROMOTION_PREFLIGHT_V0_1",
    "base_commit": EXPECTED_BASE_COMMIT,
    "input_review_aggregate_sha256": EXPECTED_REVIEW_AGGREGATE_SHA256,
    "academic_reviewed_candidates": 68,
    "academic_verified_units": 48,
    "academic_hold_units": 4,
    "academic_rejected_units": 16,
    "canonical_snapshot_ready_units": 48,
    "canonical_snapshot_ready_standalone": 47,
    "canonical_snapshot_ready_groups": 1,
    "canonical_snapshot_ready_group_children": 4,
    "visual_ready_source_crops": 32,
    "visual_reclassified_not_required": 10,
    "visual_academic_not_required": 6,
    "visual_unresolved": 0,
    "rights_review_required_units": 48,
    "taxonomy_staging_only_units": 48,
    "production_release_eligible_units": 0,
    "database_import_ready_units": 0,
}
EXPECTED_REPORT_COUNTS: dict[str, int] = {
    "academic_verified_units": 48,
    "academic_visual_required": 42,
    "ready_source_crops": 32,
    "not_required_after_visual_review": 10,
    "not_required_from_academic_review": 6,
    "visual_unresolved": 0,
    "rights_review_required_units": 48,
    "canonical_snapshot_ready_units": 48,
    "canonical_standalone_questions": 47,
    "canonical_question_groups": 1,
    "canonical_group_children": 4,
    "production_release_eligible_units": 0,
    "database_import_ready_units": 0,
}
SEMANTIC_FILES = (
    "visual_assets/visual_asset_manifest.json",
    "visual_assets/visual_review_decisions.json",
    "visual_assets/visual_asset_stats.json",
    "promotion/canonical_standalone_questions.json",
    "promotion/canonical_question_groups.json",
    "promotion/promotion_policy.json",
    "promotion/promotion_stats.json",
)
READY_SOURCE_CROP = "READY_SOURCE_CROP"
NOT_REQUIRED_AFTER_VISUAL_REVIEW = "NOT_REQUIRED_AFTER_VISUAL_REVIEW"
NOT_REQUIRED_FROM_ACADEMIC_REVIEW = "NOT_REQUIRED_FROM_ACADEMIC_REVIEW"
KNOWN_VISUAL_STATUSES = {
    READY_SOURCE_CROP,
    NOT_REQUIRED_AFTER_VISUAL_REVIEW,
    NOT_REQUIRED_FROM_ACADEMIC_REVIEW,
}
FORBIDDEN_SCORING_FIELDS = {
    "difficulty",
    "exam_weight",
    "cognitive_level",
    "explanation",
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True, order=True)
class VectorVisualPromotionIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class VectorVisualPromotionReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    visual_downgrade_ids: tuple[str, ...]
    aggregate_semantic_and_assets_sha256: str | None
    errors: tuple[VectorVisualPromotionIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "visual_downgrade_ids": list(self.visual_downgrade_ids),
            "aggregate_semantic_and_assets_sha256": (
                self.aggregate_semantic_and_assets_sha256
            ),
            "errors": [asdict(error) for error in self.errors],
        }


class VectorVisualPromotionValidator:
    """Validate DATA-MATH12-018 without importing or approving questions."""

    def validate(
        self,
        visual_root: Path = DEFAULT_VECTOR_VISUAL_ASSET_ROOT,
        promotion_root: Path = DEFAULT_VECTOR_PROMOTION_ROOT,
        review_root: Path = DEFAULT_VECTOR_ACADEMIC_REVIEW_PATH,
        materialization_root: Path = DEFAULT_VECTOR_MATERIALIZATION_PATH,
    ) -> VectorVisualPromotionReport:
        visual_root = visual_root.resolve()
        promotion_root = promotion_root.resolve()
        review_root = review_root.resolve()
        materialization_root = materialization_root.resolve()
        initial: list[VectorVisualPromotionIssue] = []

        asset_manifest = self._load_object(
            visual_root / "visual_asset_manifest.json", initial
        )
        decisions = self._load_list(
            visual_root / "visual_review_decisions.json", initial
        )
        visual_stats = self._load_object(
            visual_root / "visual_asset_stats.json", initial
        )
        standalone_snapshot = self._load_list(
            promotion_root / "canonical_standalone_questions.json", initial
        )
        group_snapshot = self._load_list(
            promotion_root / "canonical_question_groups.json", initial
        )
        policy = self._load_object(promotion_root / "promotion_policy.json", initial)
        promotion_stats = self._load_object(
            promotion_root / "promotion_stats.json", initial
        )
        promotion_manifest = self._load_object(
            promotion_root / "promotion_manifest.json", initial
        )
        standalone_reviews = self._load_list(
            review_root / "standalone_reviews.json", initial
        )
        group_reviews = self._load_list(review_root / "group_reviews.json", initial)
        evidence = self._load_list(review_root / "source_evidence.json", initial)
        patches = self._load_list(
            review_root / "content_and_scope_patches.json", initial
        )
        effective_candidates = self._load_list(
            materialization_root / "effective_candidates.json", initial
        )
        source_hashes = self._load_object(
            materialization_root / "source_hash_verification.json", initial
        )

        verified_standalone = {
            str(row["candidate_id"]): row
            for row in standalone_reviews
            if row.get("review_status") == "VERIFIED"
            and isinstance(row.get("candidate_id"), str)
        }
        verified_groups = {
            str(row["group_candidate_id"]): row
            for row in group_reviews
            if row.get("review_status") == "VERIFIED"
            and isinstance(row.get("group_candidate_id"), str)
        }
        verified_candidate_ids = set(verified_standalone) | {
            str(row["source_candidate_id"])
            for row in verified_groups.values()
            if isinstance(row.get("source_candidate_id"), str)
        }
        evidence_by_id = {
            str(row["evidence_id"]): row
            for row in evidence
            if isinstance(row.get("evidence_id"), str)
        }
        effective_by_id = {
            str(row["candidate_id"]): row
            for row in effective_candidates
            if isinstance(row.get("candidate_id"), str)
        }
        patch_by_id = {
            str(row["candidate_id"]): row
            for row in patches
            if isinstance(row.get("candidate_id"), str)
        }
        assets_value = asset_manifest.get("assets")
        assets = (
            assets_value
            if isinstance(assets_value, list)
            and all(isinstance(row, dict) for row in assets_value)
            else []
        )

        check_errors: dict[str, list[VectorVisualPromotionIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "input_identity": self._validate_input_identity(
                promotion_manifest,
                asset_manifest,
                review_root,
                materialization_root,
                verified_standalone,
                verified_groups,
            ),
            "visual_decisions": self._validate_decisions(
                decisions,
                verified_candidate_ids,
                verified_standalone,
                verified_groups,
            ),
            "visual_assets": self._validate_assets(
                assets,
                decisions,
                visual_root,
                evidence_by_id,
                verified_standalone,
                verified_groups,
                source_hashes,
            ),
            "visual_stats": self._validate_visual_stats(
                visual_stats, decisions, assets
            ),
            "snapshot_set": self._validate_snapshot_set(
                standalone_snapshot,
                group_snapshot,
                set(verified_standalone),
                set(verified_groups),
            ),
            "standalone_snapshot": self._validate_standalone_snapshot(
                standalone_snapshot,
                verified_standalone,
                evidence_by_id,
                effective_by_id,
                patch_by_id,
                decisions,
            ),
            "group_snapshot": self._validate_group_snapshot(
                group_snapshot, verified_groups, evidence_by_id, decisions
            ),
            "promotion_boundary": self._validate_promotion_boundary(
                policy,
                promotion_stats,
                promotion_manifest,
                standalone_snapshot,
                group_snapshot,
            ),
            "no_pdf_binaries": self._validate_no_pdf_binaries(
                visual_root, promotion_root
            ),
            "semantic_hashes": self._validate_semantic_hashes(
                visual_root, promotion_root, promotion_manifest
            ),
            "asset_file_integrity": self._validate_asset_file_hashes(
                visual_root, promotion_manifest
            ),
            "aggregate_integrity": self._validate_aggregate(
                visual_root, promotion_root, promotion_manifest
            ),
        }
        all_errors = tuple(
            sorted(
                {
                    issue
                    for issues in check_errors.values()
                    for issue in issues
                }
            )
        )
        checks = {
            name: not issues for name, issues in sorted(check_errors.items())
        }
        counts = self._build_counts(
            standalone_reviews,
            group_reviews,
            decisions,
            assets,
            standalone_snapshot,
            group_snapshot,
        )
        if counts != EXPECTED_REPORT_COUNTS:
            issue = VectorVisualPromotionIssue(
                "exact_counts",
                "EXACT_COUNTS_MISMATCH",
                "DATA-MATH12-018",
                f"Expected {EXPECTED_REPORT_COUNTS!r}; found {counts!r}.",
            )
            all_errors = tuple(sorted({*all_errors, issue}))
            checks["exact_counts"] = False
        else:
            checks["exact_counts"] = True
        try:
            aggregate = self.aggregate_semantic_and_assets_sha256(
                visual_root, promotion_root, promotion_manifest
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            aggregate = None
        downgrades = tuple(
            sorted(
                str(row["candidate_id"])
                for row in decisions
                if row.get("visual_review_status")
                == NOT_REQUIRED_AFTER_VISUAL_REVIEW
                and isinstance(row.get("candidate_id"), str)
            )
        )
        return VectorVisualPromotionReport(
            dataset_path=DEFAULT_VECTOR_DATA_ROOT.resolve().as_posix(),
            status="PASS" if not all_errors else "FAIL",
            checks=checks,
            counts=counts,
            visual_downgrade_ids=downgrades,
            aggregate_semantic_and_assets_sha256=aggregate,
            errors=all_errors,
        )

    @staticmethod
    def semantic_sha256(value: Any) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def aggregate_semantic_and_assets_sha256(
        cls,
        visual_root: Path,
        promotion_root: Path,
        manifest: dict[str, Any] | None = None,
    ) -> str:
        manifest = manifest or json.loads(
            (promotion_root / "promotion_manifest.json").read_text(encoding="utf-8")
        )
        order = manifest.get("semantic_files_order")
        asset_hashes = manifest.get("asset_file_hashes")
        if not isinstance(order, list) or not all(isinstance(name, str) for name in order):
            raise ValueError("semantic_files_order must be a list of strings")
        if not isinstance(asset_hashes, dict):
            raise ValueError("asset_file_hashes must be an object")
        digest = hashlib.sha256()
        for name in order:
            value = json.loads(
                cls._logical_path(name, visual_root, promotion_root).read_text(
                    encoding="utf-8"
                )
            )
            canonical = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(canonical)
            digest.update(b"\0")
        for name in sorted(asset_hashes):
            path = cls._logical_path(name, visual_root, promotion_root)
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(actual_hash.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    @classmethod
    def _validate_input_identity(
        cls,
        manifest: dict[str, Any],
        asset_manifest: dict[str, Any],
        review_root: Path,
        materialization_root: Path,
        verified_standalone: dict[str, dict[str, Any]],
        verified_groups: dict[str, dict[str, Any]],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        review_report = VectorAcademicReviewValidator().validate(
            review_root, materialization_path=materialization_root
        )
        materialization_report = VectorQuestionMaterializationValidator().validate(
            materialization_root
        )
        valid = (
            review_report.is_valid
            and review_report.review_aggregate_semantic_sha256
            == EXPECTED_REVIEW_AGGREGATE_SHA256
            and materialization_report.is_valid
            and materialization_report.aggregate_semantic_sha256
            == EXPECTED_MATERIALIZATION_AGGREGATE_SHA256
            and manifest.get("base_commit") == EXPECTED_BASE_COMMIT
            and manifest.get("input_review_aggregate_sha256")
            == EXPECTED_REVIEW_AGGREGATE_SHA256
            and manifest.get("input_materialization_aggregate_sha256")
            == EXPECTED_MATERIALIZATION_AGGREGATE_SHA256
            and asset_manifest.get("base_commit") == EXPECTED_BASE_COMMIT
            and asset_manifest.get("input_review_aggregate_sha256")
            == EXPECTED_REVIEW_AGGREGATE_SHA256
            and len(verified_standalone) == 47
            and set(verified_groups) == {"M12_VECTOR_GROUP_0040"}
        )
        if not valid:
            cls._add(
                errors,
                "input_identity",
                "INPUT_IDENTITY_MISMATCH",
                "DATA-MATH12-016/017",
                "Promotion input hashes, base context, or VERIFIED set drifted.",
            )
        return errors

    @classmethod
    def _validate_decisions(
        cls,
        decisions: list[dict[str, Any]],
        verified_ids: set[str],
        standalone: dict[str, dict[str, Any]],
        groups: dict[str, dict[str, Any]],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        by_id = cls._unique_map(
            decisions, "candidate_id", "visual_decisions", errors
        )
        if set(by_id) != verified_ids:
            cls._add(
                errors,
                "visual_decisions",
                "VISUAL_DECISION_SET_MISMATCH",
                "visual_review_decisions.json",
                "Every VERIFIED source candidate must have exactly one decision.",
            )
        group_by_source = {
            str(row["source_candidate_id"]): row for row in groups.values()
        }
        for candidate_id, row in by_id.items():
            review = standalone.get(candidate_id) or group_by_source.get(candidate_id, {})
            status = row.get("visual_review_status")
            academic_required = review.get("visual_asset_required")
            valid = (
                status in KNOWN_VISUAL_STATUSES
                and row.get("academic_visual_required") == academic_required
                and isinstance(row.get("reason"), str)
                and bool(row.get("reason", "").strip())
            )
            if status == READY_SOURCE_CROP:
                valid = valid and academic_required is True and isinstance(
                    row.get("visual_asset_id"), str
                ) and row.get("visual_required_for_canonical_snapshot") is True
            elif status == NOT_REQUIRED_AFTER_VISUAL_REVIEW:
                valid = valid and academic_required is True and row.get(
                    "visual_asset_id"
                ) is None and row.get("visual_required_for_canonical_snapshot") is False
            elif status == NOT_REQUIRED_FROM_ACADEMIC_REVIEW:
                valid = valid and academic_required is False and row.get(
                    "visual_asset_id"
                ) is None and row.get("visual_required_for_canonical_snapshot") is False
            if not valid:
                cls._add(
                    errors,
                    "visual_decisions",
                    "VISUAL_DECISION_INVALID",
                    candidate_id,
                    "Visual decision conflicts with the academic review or status schema.",
                )
        downgrade_ids = tuple(
            sorted(
                candidate_id
                for candidate_id, row in by_id.items()
                if row.get("visual_review_status")
                == NOT_REQUIRED_AFTER_VISUAL_REVIEW
            )
        )
        if downgrade_ids != EXPECTED_DOWNGRADE_IDS:
            cls._add(
                errors,
                "visual_decisions",
                "VISUAL_DOWNGRADE_SET_MISMATCH",
                "visual_review_decisions.json",
                "The ten reviewed visual downgrades are locked.",
            )
        return errors

    @classmethod
    def _validate_assets(
        cls,
        assets: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        visual_root: Path,
        evidence_by_id: dict[str, dict[str, Any]],
        standalone: dict[str, dict[str, Any]],
        groups: dict[str, dict[str, Any]],
        source_hashes: dict[str, Any],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        by_asset_id = cls._unique_map(assets, "asset_id", "visual_assets", errors)
        by_candidate = cls._unique_map(assets, "candidate_id", "visual_assets", errors)
        ready_decisions = {
            str(row["candidate_id"]): row
            for row in decisions
            if row.get("visual_review_status") == READY_SOURCE_CROP
            and isinstance(row.get("candidate_id"), str)
        }
        if set(by_candidate) != set(ready_decisions) or len(by_asset_id) != 32:
            cls._add(
                errors,
                "visual_assets",
                "VISUAL_ASSET_SET_MISMATCH",
                "visual_asset_manifest.json",
                "READY decisions and the 32 asset records must match exactly.",
            )
        sources = source_hashes.get("sources")
        sources = sources if isinstance(sources, dict) else {}
        group_by_source = {
            str(row["source_candidate_id"]): row for row in groups.values()
        }
        declared_paths: set[Path] = set()
        for candidate_id, row in by_candidate.items():
            location = f"visual_asset_manifest.json:{candidate_id}"
            review = standalone.get(candidate_id) or group_by_source.get(candidate_id, {})
            evidence = evidence_by_id.get(str(review.get("source_evidence_id")), {})
            expected_group_id = (
                review.get("group_candidate_id")
                if candidate_id in group_by_source
                else None
            )
            source = sources.get(str(row.get("source_code")), {})
            crop_box = row.get("crop_box_pdf_points")
            crop_valid = (
                isinstance(crop_box, list)
                and len(crop_box) == 4
                and all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and value > 0
                    for value in crop_box
                )
                and crop_box[2] > crop_box[0]
                and crop_box[3] > crop_box[1]
            )
            expected_fields = {
                "group_candidate_id": expected_group_id,
                "asset_kind": "SOURCE_GEOMETRY_OR_FIGURE_CROP",
                "asset_status": READY_SOURCE_CROP,
                "mime_type": "image/png",
                "source_code": evidence.get("source_code"),
                "source_file_id": evidence.get("source_file_id"),
                "source_pdf_sha256": evidence.get("source_sha256"),
                "canonical_question_pages": evidence.get("question_pages"),
                "solution_pages": evidence.get("solution_pages"),
                "extraction_method": (
                    "SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI"
                ),
                "rights_status": "REVIEW_REQUIRED",
                "promotion_eligible": False,
            }
            valid = (
                ready_decisions.get(candidate_id, {}).get("visual_asset_id")
                == row.get("asset_id")
                and all(row.get(field) == value for field, value in expected_fields.items())
                and source.get("sha256") == row.get("source_pdf_sha256")
                and source.get("drive_file_id") == row.get("source_file_id")
                and isinstance(row.get("asset_source_page"), int)
                and not isinstance(row.get("asset_source_page"), bool)
                and row.get("asset_source_page") > 0
                and row.get("asset_source_page") in row.get(
                    "canonical_question_pages", []
                )
                and crop_valid
            )
            if not valid:
                cls._add(
                    errors,
                    "visual_assets",
                    "VISUAL_ASSET_METADATA_INVALID",
                    location,
                    "Asset safety, source lineage, pages, crop, or rights metadata drifted.",
                )
            asset_path = cls._safe_asset_path(row.get("file_name"), visual_root)
            if asset_path is None:
                cls._add(
                    errors,
                    "visual_assets",
                    "VISUAL_ASSET_PATH_INVALID",
                    location,
                    "Asset path must be relative and stay under the visual root.",
                )
                continue
            declared_paths.add(asset_path)
            try:
                data = asset_path.read_bytes()
            except OSError as error:
                cls._add(
                    errors,
                    "visual_assets",
                    "VISUAL_ASSET_FILE_MISSING",
                    asset_path.as_posix(),
                    str(error),
                )
                continue
            if hashlib.sha256(data).hexdigest() != row.get("sha256"):
                cls._add(
                    errors,
                    "visual_assets",
                    "VISUAL_ASSET_SHA256_MISMATCH",
                    asset_path.as_posix(),
                    "Actual PNG hash differs from the visual manifest.",
                )
            if cls._png_dimensions(data) != (
                row.get("width_px"),
                row.get("height_px"),
            ):
                cls._add(
                    errors,
                    "visual_assets",
                    "VISUAL_ASSET_DIMENSIONS_MISMATCH",
                    asset_path.as_posix(),
                    "Actual PNG dimensions differ from the visual manifest.",
                )
        actual_paths = set((visual_root / "assets").glob("*.png"))
        if actual_paths != declared_paths:
            cls._add(
                errors,
                "visual_assets",
                "VISUAL_ASSET_FILE_SET_MISMATCH",
                (visual_root / "assets").as_posix(),
                "The assets directory must contain exactly the 32 declared PNG files.",
            )
        return errors

    @classmethod
    def _validate_visual_stats(
        cls,
        stats: dict[str, Any],
        decisions: list[dict[str, Any]],
        assets: list[dict[str, Any]],
    ) -> list[VectorVisualPromotionIssue]:
        statuses = Counter(row.get("visual_review_status") for row in decisions)
        expected = {
            "academic_verified_units": 48,
            "academic_visual_required": 42,
            "ready_source_crops": 32,
            "reclassified_not_required_after_visual_review": 10,
            "academic_not_required": 6,
            "unresolved_visual_units": 0,
            "rights_review_required_units": 48,
            "promotion_eligible_units": 0,
        }
        valid = (
            len(assets) == 32
            and statuses
            == {
                READY_SOURCE_CROP: 32,
                NOT_REQUIRED_AFTER_VISUAL_REVIEW: 10,
                NOT_REQUIRED_FROM_ACADEMIC_REVIEW: 6,
            }
            and all(stats.get(field) == value for field, value in expected.items())
            and stats.get("reclassified_not_required_candidate_ids")
            == list(EXPECTED_DOWNGRADE_IDS)
        )
        if valid:
            return []
        return [
            VectorVisualPromotionIssue(
                "visual_stats",
                "VISUAL_STATS_MISMATCH",
                "visual_asset_stats.json",
                "Visual stats or locked downgrade IDs do not match actual decisions.",
            )
        ]

    @classmethod
    def _validate_snapshot_set(
        cls,
        standalone_snapshot: list[dict[str, Any]],
        group_snapshot: list[dict[str, Any]],
        verified_standalone_ids: set[str],
        verified_group_ids: set[str],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        standalone_ids = {
            str(row["source_candidate_id"])
            for row in standalone_snapshot
            if isinstance(row.get("source_candidate_id"), str)
        }
        group_ids = {
            str(row["group_candidate_id"])
            for row in group_snapshot
            if isinstance(row.get("group_candidate_id"), str)
        }
        if (
            len(standalone_snapshot) != 47
            or len(standalone_ids) != 47
            or standalone_ids != verified_standalone_ids
            or len(group_snapshot) != 1
            or len(group_ids) != 1
            or group_ids != verified_group_ids
        ):
            cls._add(
                errors,
                "snapshot_set",
                "CANONICAL_SNAPSHOT_SET_MISMATCH",
                "promotion/v0_1",
                "Snapshot must contain exactly the 47 VERIFIED standalone rows and group 0040.",
            )
        return errors

    @classmethod
    def _validate_standalone_snapshot(
        cls,
        snapshot: list[dict[str, Any]],
        reviews: dict[str, dict[str, Any]],
        evidence_by_id: dict[str, dict[str, Any]],
        effective_by_id: dict[str, dict[str, Any]],
        patch_by_id: dict[str, dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        decisions_by_id = {
            str(row["candidate_id"]): row
            for row in decisions
            if isinstance(row.get("candidate_id"), str)
        }
        for row in snapshot:
            candidate_id = str(row.get("source_candidate_id"))
            review = reviews.get(candidate_id, {})
            evidence = evidence_by_id.get(str(review.get("source_evidence_id")), {})
            decision = decisions_by_id.get(candidate_id, {})
            effective = effective_by_id.get(candidate_id, {})
            expected_taxonomy = cls._snapshot_taxonomy(review.get("taxonomy"))
            expected_lineage = {
                "source_code": review.get("source_code"),
                "source_file_id": review.get("source_file_id"),
                "source_sha256": review.get("source_sha256"),
                "candidate_source_page": review.get("candidate_source_page"),
                "source_evidence_id": review.get("source_evidence_id"),
            }
            if candidate_id in {"M12_VECTOR_CAND_0018", "M12_VECTOR_CAND_0044"}:
                expected_content = patch_by_id.get(candidate_id, {}).get(
                    "reviewed_content"
                )
                expected_basis = "ACADEMIC_REVIEW_PATCH"
            else:
                expected_content = effective.get("raw_question_text")
                expected_basis = "DATA_016_SOURCE_TEXT"
            expected_visual = {
                "status": decision.get("visual_review_status"),
                "asset_id": decision.get("visual_asset_id"),
            }
            valid = (
                review.get("review_status") == "VERIFIED"
                and row.get("snapshot_key") == candidate_id
                and row.get("subject_code") == "MATH_G12"
                and row.get("chapter_code") == "VECTORS_GEOMETRY"
                and row.get("question_type") == review.get("question_type")
                and row.get("content") == expected_content
                and row.get("content_basis") == expected_basis
                and row.get("correct_answer") == review.get("correct_answer")
                == evidence.get("source_claimed_answer")
                and row.get("taxonomy") == expected_taxonomy
                and row.get("source_lineage") == expected_lineage
                and row.get("visual") == expected_visual
                and row.get("canonical_snapshot_ready") is True
                and row.get("production_release_eligible") is False
                and row.get("production_blockers") == list(EXPECTED_BLOCKERS)
                and not cls._contains_forbidden_field(row)
            )
            if not valid:
                cls._add(
                    errors,
                    "standalone_snapshot",
                    "STANDALONE_SNAPSHOT_MISMATCH",
                    candidate_id,
                    "Standalone snapshot differs from review, evidence, content, visual, or blockers.",
                )
        return errors

    @classmethod
    def _validate_group_snapshot(
        cls,
        snapshot: list[dict[str, Any]],
        reviews: dict[str, dict[str, Any]],
        evidence_by_id: dict[str, dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        group = snapshot[0] if len(snapshot) == 1 else {}
        group_id = "M12_VECTOR_GROUP_0040"
        review = reviews.get(group_id, {})
        evidence = evidence_by_id.get(str(review.get("source_evidence_id")), {})
        decision = next(
            (
                row
                for row in decisions
                if row.get("candidate_id") == review.get("source_candidate_id")
            ),
            {},
        )
        expected_lineage = {
            "source_code": review.get("source_code"),
            "source_file_id": review.get("source_file_id"),
            "source_sha256": review.get("source_sha256"),
            "candidate_source_page": review.get("candidate_source_page"),
            "source_evidence_id": review.get("source_evidence_id"),
        }
        expected_visual = {
            "status": decision.get("visual_review_status"),
            "asset_id": decision.get("visual_asset_id"),
        }
        items = group.get("items")
        reviewed_items = review.get("items")
        valid = (
            group.get("snapshot_key") == group_id
            and group.get("group_candidate_id") == group_id
            and group.get("source_candidate_id") == "M12_VECTOR_CAND_0040"
            and group.get("subject_code") == "MATH_G12"
            and group.get("chapter_code") == "VECTORS_GEOMETRY"
            and group.get("group_type") == "TRUE_FALSE_FOUR"
            and group.get("scoring_policy") == "MOET_2025_TRUE_FALSE"
            and group.get("group_context") == review.get("reviewed_group_context")
            and group.get("source_lineage") == expected_lineage
            and group.get("visual") == expected_visual
            and group.get("canonical_snapshot_ready") is True
            and group.get("production_release_eligible") is False
            and group.get("production_blockers") == list(EXPECTED_BLOCKERS)
            and isinstance(items, list)
            and isinstance(reviewed_items, list)
            and len(items) == len(reviewed_items) == 4
            and evidence.get("source_claimed_answer_pattern")
            == ["TRUE", "TRUE", "TRUE", "FALSE"]
            and not cls._contains_forbidden_field(group)
        )
        if valid:
            for index, (item, reviewed) in enumerate(zip(items, reviewed_items)):
                expected_label = "abcd"[index]
                valid = valid and (
                    item.get("child_key") == f"{group_id}:{expected_label}"
                    and item.get("label") == expected_label
                    and item.get("order_index") == index
                    and item.get("question_type") == "TRUE_FALSE"
                    and item.get("content") == reviewed.get("reviewed_content")
                    and item.get("correct_answer") == reviewed.get("correct_answer")
                    and item.get("taxonomy")
                    == cls._snapshot_taxonomy(reviewed.get("taxonomy"))
                )
        if not valid:
            cls._add(
                errors,
                "group_snapshot",
                "GROUP_0040_SNAPSHOT_MISMATCH",
                group_id,
                "Group 0040 content, answers, taxonomy, visual, order, or scoring drifted.",
            )
        return errors

    @classmethod
    def _validate_promotion_boundary(
        cls,
        policy: dict[str, Any],
        stats: dict[str, Any],
        manifest: dict[str, Any],
        standalone: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> list[VectorVisualPromotionIssue]:
        rows = [*standalone, *groups]
        gate = policy.get("production_release_gate")
        valid = (
            stats == EXPECTED_PROMOTION_COUNTS
            and manifest.get("counts") == EXPECTED_PROMOTION_COUNTS
            and manifest.get("canonical_snapshot_created") is True
            and manifest.get("database_import_allowed") is False
            and manifest.get("production_release_eligible_units") == 0
            and isinstance(gate, dict)
            and gate.get("current_result") == "0 units eligible"
            and all(row.get("canonical_snapshot_ready") is True for row in rows)
            and all(row.get("production_release_eligible") is False for row in rows)
            and all(row.get("database_import_ready") is not True for row in rows)
            and all(row.get("production_blockers") == list(EXPECTED_BLOCKERS) for row in rows)
            and not any(cls._contains_forbidden_field(row) for row in rows)
        )
        if valid:
            return []
        return [
            VectorVisualPromotionIssue(
                "promotion_boundary",
                "PROMOTION_BOUNDARY_VIOLATION",
                "promotion/v0_1",
                "Internal snapshot must remain blocked from release and database import.",
            )
        ]

    @classmethod
    def _validate_no_pdf_binaries(
        cls, visual_root: Path, promotion_root: Path
    ) -> list[VectorVisualPromotionIssue]:
        pdfs = [
            path
            for root in (visual_root, promotion_root)
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"
        ]
        if not pdfs:
            return []
        return [
            VectorVisualPromotionIssue(
                "no_pdf_binaries",
                "SOURCE_PDF_FORBIDDEN",
                pdfs[0].as_posix(),
                "Source PDF binaries must not be stored in visual/promotion data.",
            )
        ]

    @classmethod
    def _validate_semantic_hashes(
        cls,
        visual_root: Path,
        promotion_root: Path,
        manifest: dict[str, Any],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        order = manifest.get("semantic_files_order")
        declared = manifest.get("semantic_file_hashes")
        if order != list(SEMANTIC_FILES) or not isinstance(declared, dict):
            cls._add(
                errors,
                "semantic_hashes",
                "SEMANTIC_FILE_CONTRACT_INVALID",
                "promotion_manifest.json",
                "Semantic file order or hash map is invalid.",
            )
            return errors
        for name in SEMANTIC_FILES:
            try:
                value = json.loads(
                    cls._logical_path(name, visual_root, promotion_root).read_text(
                        encoding="utf-8"
                    )
                )
                actual = cls.semantic_sha256(value)
            except (OSError, json.JSONDecodeError) as error:
                cls._add(
                    errors,
                    "semantic_hashes",
                    "SEMANTIC_FILE_UNREADABLE",
                    name,
                    str(error),
                )
                continue
            if declared.get(name) != actual:
                cls._add(
                    errors,
                    "semantic_hashes",
                    "SEMANTIC_FILE_SHA256_MISMATCH",
                    name,
                    "Canonical JSON SHA-256 differs from the promotion manifest.",
                )
        return errors

    @classmethod
    def _validate_asset_file_hashes(
        cls,
        visual_root: Path,
        manifest: dict[str, Any],
    ) -> list[VectorVisualPromotionIssue]:
        errors: list[VectorVisualPromotionIssue] = []
        declared = manifest.get("asset_file_hashes")
        if (
            not isinstance(declared, dict)
            or len(declared) != 32
            or not all(
                isinstance(name, str)
                and name.startswith("visual_assets/assets/")
                and name.endswith(".png")
                for name in declared
            )
        ):
            cls._add(
                errors,
                "asset_file_integrity",
                "ASSET_HASH_CONTRACT_INVALID",
                "promotion_manifest.json.asset_file_hashes",
                "Expected exactly 32 declared PNG hashes.",
            )
            return errors
        for name, expected in declared.items():
            try:
                path = cls._logical_path(str(name), visual_root, visual_root)
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, ValueError) as error:
                cls._add(
                    errors,
                    "asset_file_integrity",
                    "ASSET_FILE_UNREADABLE",
                    str(name),
                    str(error),
                )
                continue
            if actual != expected:
                cls._add(
                    errors,
                    "asset_file_integrity",
                    "ASSET_FILE_SHA256_MISMATCH",
                    str(name),
                    "Actual PNG bytes differ from the locked promotion manifest.",
                )
        return errors

    @classmethod
    def _validate_aggregate(
        cls,
        visual_root: Path,
        promotion_root: Path,
        manifest: dict[str, Any],
    ) -> list[VectorVisualPromotionIssue]:
        try:
            actual = cls.aggregate_semantic_and_assets_sha256(
                visual_root, promotion_root, manifest
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            return [
                VectorVisualPromotionIssue(
                    "aggregate_integrity",
                    "PROMOTION_AGGREGATE_INPUT_INVALID",
                    "promotion_manifest.json",
                    str(error),
                )
            ]
        if (
            actual == EXPECTED_AGGREGATE_SHA256
            and manifest.get("aggregate_semantic_and_assets_sha256") == actual
        ):
            return []
        return [
            VectorVisualPromotionIssue(
                "aggregate_integrity",
                "PROMOTION_AGGREGATE_SHA256_MISMATCH",
                "promotion_manifest.json.aggregate_semantic_and_assets_sha256",
                f"Expected {EXPECTED_AGGREGATE_SHA256}; recomputed {actual}.",
            )
        ]

    @staticmethod
    def _build_counts(
        standalone_reviews: list[dict[str, Any]],
        group_reviews: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        standalone_snapshot: list[dict[str, Any]],
        group_snapshot: list[dict[str, Any]],
    ) -> dict[str, int]:
        verified_reviews = [
            row
            for row in [*standalone_reviews, *group_reviews]
            if row.get("review_status") == "VERIFIED"
        ]
        statuses = Counter(row.get("visual_review_status") for row in decisions)
        snapshot_rows = [*standalone_snapshot, *group_snapshot]
        return {
            "academic_verified_units": len(verified_reviews),
            "academic_visual_required": sum(
                row.get("visual_asset_required") is True for row in verified_reviews
            ),
            "ready_source_crops": len(assets),
            "not_required_after_visual_review": statuses[
                NOT_REQUIRED_AFTER_VISUAL_REVIEW
            ],
            "not_required_from_academic_review": statuses[
                NOT_REQUIRED_FROM_ACADEMIC_REVIEW
            ],
            "visual_unresolved": sum(
                row.get("visual_review_status") not in KNOWN_VISUAL_STATUSES
                for row in decisions
            ),
            "rights_review_required_units": sum(
                "RIGHTS_REVIEW_REQUIRED" in row.get("production_blockers", [])
                for row in snapshot_rows
            ),
            "canonical_snapshot_ready_units": len(snapshot_rows),
            "canonical_standalone_questions": len(standalone_snapshot),
            "canonical_question_groups": len(group_snapshot),
            "canonical_group_children": sum(
                len(row.get("items", [])) for row in group_snapshot
            ),
            "production_release_eligible_units": sum(
                row.get("production_release_eligible") is True
                for row in snapshot_rows
            ),
            "database_import_ready_units": sum(
                row.get("database_import_ready") is True for row in snapshot_rows
            ),
        }

    @staticmethod
    def _snapshot_taxonomy(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {
            "problem_types": value.get("problem_types"),
            "concepts": value.get("concepts"),
            "learning_outcomes": value.get("learning_outcomes"),
            "taxonomy_basis": value.get("basis"),
        }

    @classmethod
    def _unique_map(
        cls,
        rows: list[dict[str, Any]],
        field: str,
        check: str,
        errors: list[VectorVisualPromotionIssue],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            value = row.get(field)
            if not isinstance(value, str) or not value or value in result:
                cls._add(
                    errors,
                    check,
                    "IDENTIFIER_INVALID_OR_DUPLICATE",
                    f"{field}[{index}]",
                    f"{field} must be unique and non-empty.",
                )
            else:
                result[value] = row
        return result

    @staticmethod
    def _safe_asset_path(value: Any, root: Path) -> Path | None:
        if not isinstance(value, str) or not value or "\\" in value:
            return None
        relative = PurePosixPath(value)
        if (
            relative.is_absolute()
            or PureWindowsPath(value).is_absolute()
            or ".." in relative.parts
            or "." in relative.parts
        ):
            return None
        resolved = (root / Path(*relative.parts)).resolve()
        if resolved != root and root not in resolved.parents:
            return None
        return resolved

    @staticmethod
    def _logical_path(
        name: str, visual_root: Path, promotion_root: Path
    ) -> Path:
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or PureWindowsPath(name).is_absolute()
            or ".." in relative.parts
            or len(relative.parts) < 2
        ):
            raise ValueError(f"Unsafe logical path: {name!r}")
        prefix, *parts = relative.parts
        if prefix == "visual_assets":
            return visual_root.joinpath(*parts)
        if prefix == "promotion":
            return promotion_root.joinpath(*parts)
        raise ValueError(f"Unknown logical path prefix: {prefix!r}")

    @staticmethod
    def _png_dimensions(data: bytes) -> tuple[int, int] | None:
        if (
            len(data) < 24
            or data[:8] != PNG_SIGNATURE
            or data[12:16] != b"IHDR"
        ):
            return None
        return struct.unpack(">II", data[16:24])

    @classmethod
    def _contains_forbidden_field(cls, value: Any) -> bool:
        if isinstance(value, dict):
            return bool(FORBIDDEN_SCORING_FIELDS & set(value)) or any(
                cls._contains_forbidden_field(item) for item in value.values()
            )
        if isinstance(value, list):
            return any(cls._contains_forbidden_field(item) for item in value)
        return False

    @classmethod
    def _load_object(
        cls, path: Path, errors: list[VectorVisualPromotionIssue]
    ) -> dict[str, Any]:
        value = cls._load_json(path, errors)
        if isinstance(value, dict):
            return value
        if value is not None:
            cls._add(
                errors,
                "required_files",
                "JSON_SHAPE_INVALID",
                path.as_posix(),
                "Expected a JSON object.",
            )
        return {}

    @classmethod
    def _load_list(
        cls, path: Path, errors: list[VectorVisualPromotionIssue]
    ) -> list[dict[str, Any]]:
        value = cls._load_json(path, errors)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
        if value is not None:
            cls._add(
                errors,
                "required_files",
                "JSON_SHAPE_INVALID",
                path.as_posix(),
                "Expected an array of objects.",
            )
        return []

    @classmethod
    def _load_json(
        cls, path: Path, errors: list[VectorVisualPromotionIssue]
    ) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            cls._add(
                errors,
                "required_files",
                "REQUIRED_FILE_MISSING",
                path.as_posix(),
                "Required DATA-MATH12-018 file is missing.",
            )
        except (OSError, json.JSONDecodeError) as error:
            cls._add(
                errors,
                "required_files",
                "JSON_INVALID",
                path.as_posix(),
                str(error),
            )
        return None

    @staticmethod
    def _add(
        errors: list[VectorVisualPromotionIssue],
        check: str,
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(VectorVisualPromotionIssue(check, code, location, message))
