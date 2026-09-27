from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    EffectiveQuestionGroupReviewMaterializer,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
)


DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT = (
    DEFAULT_QUESTION_GROUP_STAGING_PATH.parents[1] / "visual_assets" / "v0_1"
)
READY_SOURCE_CROP = "READY_SOURCE_CROP"
BLOCKED_SOURCE_VISUAL_MISSING = "BLOCKED_SOURCE_VISUAL_MISSING"
KNOWN_ASSET_STATUSES = {READY_SOURCE_CROP, BLOCKED_SOURCE_VISUAL_MISSING}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True, order=True)
class QuestionGroupVisualAssetIssue:
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class QuestionGroupVisualAssetReport:
    dataset_path: str
    status: str
    counts: dict[str, int]
    required_group_ids: tuple[str, ...]
    unresolved_group_ids: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    errors: tuple[QuestionGroupVisualAssetIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "counts": self.counts,
            "required_group_ids": list(self.required_group_ids),
            "unresolved_group_ids": list(self.unresolved_group_ids),
            "errors": [asdict(error) for error in self.errors],
        }


class QuestionGroupVisualAssetValidator:
    """Validate the read-only visual registry against reviewed QuestionGroups."""

    def validate(
        self,
        asset_root: Path = DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT,
        group_staging_path: Path = DEFAULT_QUESTION_GROUP_STAGING_PATH,
        review_root: Path = DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    ) -> QuestionGroupVisualAssetReport:
        asset_root = asset_root.resolve()
        group_staging_path = group_staging_path.resolve()
        review_root = review_root.resolve()
        errors: list[QuestionGroupVisualAssetIssue] = []

        manifest = self._load_object(
            asset_root / "visual_asset_manifest.json", errors
        )
        stats = self._load_object(asset_root / "visual_asset_stats.json", errors)
        rows_value = manifest.get("assets")
        if not isinstance(rows_value, list) or not all(
            isinstance(row, dict) for row in rows_value
        ):
            self._add(
                errors,
                "MANIFEST_ASSETS_INVALID",
                "visual_asset_manifest.json.assets",
                "Manifest assets must be an array of objects.",
            )
            rows: list[dict[str, Any]] = []
        else:
            rows = rows_value

        structural_groups = self._load_list(
            group_staging_path / "question_group_candidates.json", errors
        )
        materialization = EffectiveQuestionGroupReviewMaterializer().materialize(
            structural_groups, review_root
        )
        for issue in materialization.issues:
            self._add(
                errors,
                "REVIEW_MATERIALIZATION_INVALID",
                issue.location,
                issue.message,
            )
        for batch in materialization.review_batches:
            for issue in batch.errors:
                self._add(
                    errors,
                    "REVIEW_MATERIALIZATION_INVALID",
                    f"{Path(batch.path).name}/{issue.location}",
                    issue.message,
                )

        effective_by_id = {
            str(group["group_candidate_id"]): group
            for group in materialization.effective_groups
            if isinstance(group.get("group_candidate_id"), str)
        }
        required_group_ids = {
            group_id
            for group_id, group in effective_by_id.items()
            if group.get("academic_review_status") == "VERIFIED"
            and isinstance(group.get("academic_review_record"), dict)
            and group["academic_review_record"].get("visual_asset_required") is True
        }

        group_ids = self._unique_values(rows, "group_candidate_id", errors)
        self._unique_values(rows, "asset_id", errors)
        if group_ids != required_group_ids:
            for group_id in sorted(required_group_ids - group_ids):
                self._add(
                    errors,
                    "REQUIRED_GROUP_MISSING",
                    group_id,
                    "A VERIFIED visual-required group is missing from the manifest.",
                )
            for group_id in sorted(group_ids - required_group_ids):
                self._add(
                    errors,
                    "UNEXPECTED_MANIFEST_GROUP",
                    group_id,
                    "Manifest group is not a VERIFIED visual-required group.",
                )

        source_lineages = self._load_source_lineages(review_root, errors)
        for index, row in enumerate(rows):
            location = f"visual_asset_manifest.json.assets[{index}]"
            group_id = row.get("group_candidate_id")
            group = effective_by_id.get(str(group_id))
            status = row.get("asset_status")

            if group is None:
                self._add(
                    errors,
                    "UNKNOWN_GROUP",
                    location,
                    "Manifest group does not exist in effective QuestionGroup review.",
                )
            elif status == READY_SOURCE_CROP and group_id not in required_group_ids:
                self._add(
                    errors,
                    "READY_NON_VISUAL_GROUP",
                    location,
                    "READY assets are allowed only for VERIFIED visual-required groups.",
                )
            else:
                self._validate_provenance(
                    row, group, source_lineages, location, errors
                )

            if status not in KNOWN_ASSET_STATUSES:
                self._add(
                    errors,
                    "UNKNOWN_ASSET_STATUS",
                    location,
                    f"Unknown asset_status {status!r}.",
                )
            elif status == READY_SOURCE_CROP:
                self._validate_ready(row, asset_root, location, errors)
            else:
                self._validate_blocked(row, location, errors)

            if row.get("rights_status") != "REVIEW_REQUIRED":
                self._add(
                    errors,
                    "RIGHTS_STATUS_INVALID",
                    location,
                    "Every visual asset row must remain REVIEW_REQUIRED.",
                )
            if row.get("promotion_eligible") is not False:
                self._add(
                    errors,
                    "PROMOTION_BOUNDARY_INVALID",
                    location,
                    "Visual asset rows must have promotion_eligible=false.",
                )
            if self._contains_embedded_image(row):
                self._add(
                    errors,
                    "EMBEDDED_IMAGE_DATA_FORBIDDEN",
                    location,
                    "Image bytes or data URLs must not be embedded in manifest JSON.",
                )

        ready_count = sum(row.get("asset_status") == READY_SOURCE_CROP for row in rows)
        blocked_count = sum(
            row.get("asset_status") == BLOCKED_SOURCE_VISUAL_MISSING for row in rows
        )
        rights_count = sum(
            row.get("rights_status") == "REVIEW_REQUIRED" for row in rows
        )
        promotion_count = sum(
            row.get("promotion_eligible") is True for row in rows
        )
        unresolved_ids = tuple(
            sorted(
                str(row["group_candidate_id"])
                for row in rows
                if row.get("asset_status") == BLOCKED_SOURCE_VISUAL_MISSING
                and isinstance(row.get("group_candidate_id"), str)
            )
        )
        counts = {
            "visual_required_groups": len(required_group_ids),
            "manifest_records": len(rows),
            "ready_source_crops": ready_count,
            "blocked_source_visual_missing": blocked_count,
            "rights_review_required": rights_count,
            "promotion_eligible": promotion_count,
        }
        for field, actual in counts.items():
            if stats.get(field) != actual:
                self._add(
                    errors,
                    "STATS_COUNT_MISMATCH",
                    f"visual_asset_stats.json.{field}",
                    f"Expected {actual}; found {stats.get(field)!r}.",
                )
        if stats.get("unresolved_group_ids") != list(unresolved_ids):
            self._add(
                errors,
                "STATS_UNRESOLVED_IDS_MISMATCH",
                "visual_asset_stats.json.unresolved_group_ids",
                f"Expected {list(unresolved_ids)!r}.",
            )

        final_errors = tuple(sorted(set(errors)))
        return QuestionGroupVisualAssetReport(
            dataset_path=asset_root.as_posix(),
            status="PASS" if not final_errors else "FAIL",
            counts=counts,
            required_group_ids=tuple(sorted(required_group_ids)),
            unresolved_group_ids=unresolved_ids,
            records=tuple(rows),
            errors=final_errors,
        )

    def _validate_provenance(
        self,
        row: dict[str, Any],
        group: dict[str, Any],
        source_lineages: dict[str, set[tuple[str, str]]],
        location: str,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> None:
        evidence = group.get("source_evidence")
        if not isinstance(evidence, dict):
            self._add(
                errors,
                "SOURCE_EVIDENCE_MISSING",
                location,
                "Effective review group has no source evidence.",
            )
            return
        expected_fields = {
            "source_code": evidence.get("source_code"),
            "effective_subsource_code": evidence.get("effective_subsource_code"),
            "canonical_question_pages": evidence.get("canonical_question_pages"),
            "solution_pages": evidence.get("solution_pages"),
        }
        for field, expected in expected_fields.items():
            if row.get(field) != expected:
                self._add(
                    errors,
                    "PROVENANCE_MISMATCH",
                    f"{location}.{field}",
                    f"Expected {expected!r}; found {row.get(field)!r}.",
                )
        if group.get("source_page") != evidence.get("candidate_extraction_page"):
            self._add(
                errors,
                "STRUCTURAL_SOURCE_PAGE_MISMATCH",
                location,
                "Structural source page must match review evidence extraction page.",
            )
        source_code = row.get("source_code")
        lineage = (
            str(row.get("source_pdf_sha256")),
            str(row.get("source_file")),
        )
        if not isinstance(source_code, str) or lineage not in source_lineages.get(
            source_code, set()
        ):
            self._add(
                errors,
                "SOURCE_LINEAGE_MISMATCH",
                location,
                "Source PDF hash/file does not match group-review source metadata.",
            )

    def _validate_ready(
        self,
        row: dict[str, Any],
        asset_root: Path,
        location: str,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> None:
        if row.get("blocker_reason") not in {None, ""}:
            self._add(
                errors,
                "READY_BLOCKER_INVALID",
                location,
                "READY rows must not contain a blocker reason.",
            )
        file_name = row.get("file_name")
        asset_path = self._safe_asset_path(file_name, asset_root)
        if asset_path is None:
            self._add(
                errors,
                "ASSET_PATH_INVALID",
                f"{location}.file_name",
                "READY file_name must be a safe relative path under the asset root.",
            )
            return
        if not asset_path.is_file():
            self._add(
                errors,
                "ASSET_FILE_MISSING",
                str(file_name),
                "READY asset file does not exist.",
            )
            return
        if row.get("mime_type") != "image/png":
            self._add(
                errors,
                "ASSET_MIME_INVALID",
                location,
                "READY assets must use image/png.",
            )
        data = asset_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row.get("sha256"):
            self._add(
                errors,
                "ASSET_SHA256_MISMATCH",
                str(file_name),
                "Asset SHA-256 does not match the manifest.",
            )
        dimensions = self._png_dimensions(data)
        if dimensions is None:
            self._add(
                errors,
                "ASSET_PNG_INVALID",
                str(file_name),
                "Asset is not a valid PNG with an IHDR header.",
            )
        elif dimensions != (row.get("width_px"), row.get("height_px")):
            self._add(
                errors,
                "ASSET_DIMENSIONS_MISMATCH",
                str(file_name),
                f"PNG dimensions are {dimensions}; manifest differs.",
            )
        pages = row.get("canonical_question_pages")
        source_page = row.get("asset_source_page")
        if (
            not isinstance(source_page, int)
            or isinstance(source_page, bool)
            or not isinstance(pages, list)
            or source_page not in pages
        ):
            self._add(
                errors,
                "ASSET_SOURCE_PAGE_INVALID",
                location,
                "READY asset_source_page must be a canonical question page.",
            )

    def _validate_blocked(
        self,
        row: dict[str, Any],
        location: str,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> None:
        for field in ("file_name", "sha256", "mime_type", "width_px", "height_px"):
            if row.get(field) is not None:
                self._add(
                    errors,
                    "BLOCKED_ASSET_FIELD_PRESENT",
                    f"{location}.{field}",
                    "BLOCKED rows must not describe an asset file.",
                )
        reason = row.get("blocker_reason")
        if not isinstance(reason, str) or not reason.strip():
            self._add(
                errors,
                "BLOCKER_REASON_MISSING",
                location,
                "BLOCKED rows require a non-empty blocker reason.",
            )

    @classmethod
    def _load_source_lineages(
        cls,
        review_root: Path,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> dict[str, set[tuple[str, str]]]:
        result: dict[str, set[tuple[str, str]]] = {}
        for batch_path in sorted(review_root.glob("batch_*")):
            if not batch_path.is_dir():
                continue
            metadata = cls._load_object(
                batch_path / "source_metadata.json", errors
            )
            source_code = metadata.get("source_code")
            source_hash = metadata.get("source_pdf_sha256")
            source_file = metadata.get("file_name")
            if all(isinstance(value, str) and value for value in (
                source_code, source_hash, source_file
            )):
                result.setdefault(source_code, set()).add((source_hash, source_file))
        return result

    @classmethod
    def _unique_values(
        cls,
        rows: list[dict[str, Any]],
        field: str,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> set[str]:
        values: set[str] = set()
        for index, row in enumerate(rows):
            value = row.get(field)
            location = f"visual_asset_manifest.json.assets[{index}].{field}"
            if not isinstance(value, str) or not value:
                cls._add(errors, "MANIFEST_IDENTIFIER_INVALID", location,
                         f"{field} must be a non-empty string.")
            elif value in values:
                cls._add(errors, "MANIFEST_IDENTIFIER_DUPLICATE", location,
                         f"Duplicate {field}: {value}.")
            else:
                values.add(value)
        return values

    @staticmethod
    def _safe_asset_path(file_name: Any, asset_root: Path) -> Path | None:
        if not isinstance(file_name, str) or not file_name or "\\" in file_name:
            return None
        relative = PurePosixPath(file_name)
        if (
            relative.is_absolute()
            or PureWindowsPath(file_name).is_absolute()
            or ".." in relative.parts
            or "." in relative.parts
        ):
            return None
        resolved = (asset_root / Path(*relative.parts)).resolve()
        if resolved != asset_root and asset_root not in resolved.parents:
            return None
        return resolved

    @staticmethod
    def _png_dimensions(data: bytes) -> tuple[int, int] | None:
        if (
            len(data) < 24
            or data[:8] != PNG_SIGNATURE
            or data[12:16] != b"IHDR"
        ):
            return None
        return struct.unpack(">II", data[16:24])

    @staticmethod
    def _contains_embedded_image(value: Any) -> bool:
        if isinstance(value, str):
            return value.lower().startswith("data:image/")
        if isinstance(value, dict):
            return any(
                QuestionGroupVisualAssetValidator._contains_embedded_image(item)
                for item in value.values()
            )
        if isinstance(value, list):
            return any(
                QuestionGroupVisualAssetValidator._contains_embedded_image(item)
                for item in value
            )
        return False

    @classmethod
    def _load_object(
        cls,
        path: Path,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> dict[str, Any]:
        value = cls._load_json(path, errors)
        if isinstance(value, dict):
            return value
        if value is not None:
            cls._add(errors, "JSON_SHAPE_INVALID", path.name,
                     "Expected a JSON object.")
        return {}

    @classmethod
    def _load_list(
        cls,
        path: Path,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> list[dict[str, Any]]:
        value = cls._load_json(path, errors)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
        if value is not None:
            cls._add(errors, "JSON_SHAPE_INVALID", path.name,
                     "Expected an array of objects.")
        return []

    @classmethod
    def _load_json(
        cls,
        path: Path,
        errors: list[QuestionGroupVisualAssetIssue],
    ) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            cls._add(errors, "REQUIRED_FILE_MISSING", path.name,
                     "Required registry file is missing.")
        except (OSError, json.JSONDecodeError) as error:
            cls._add(errors, "JSON_INVALID", path.name, f"Cannot read JSON: {error}.")
        return None

    @staticmethod
    def _add(
        errors: list[QuestionGroupVisualAssetIssue],
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(QuestionGroupVisualAssetIssue(code, location, message))
