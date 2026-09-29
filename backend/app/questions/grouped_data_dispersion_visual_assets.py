from __future__ import annotations

import hashlib
import json
import math
import struct
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.questions.grouped_data_dispersion_academic_review import (
    DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
    EXPECTED_REVIEW_AGGREGATE_SHA256,
    GroupedDataDispersionAcademicReviewValidator,
)
from app.questions.grouped_data_dispersion_materialization import (
    DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH,
)


DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH = (
    DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH.parents[1]
    / "visual_assets"
    / "v0_1"
)
EXPECTED_VISUAL_AGGREGATE_SHA256 = (
    "72eb48af3ad973391e766ec92c3d969dbb5d8677e912ad5bc45392b66d09b438"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "37a4031fe1b7ef4b3e93fa9b88f7fd5cf156ffb3cafba8a819b9830d0b83c413"
)
EXPECTED_NOT_REQUIRED_ID = "M12_DISP_CAND_0034"
EXPECTED_CONTINUATION_PAGES = {
    "M12_DISP_CAND_0003": 80,
    "M12_DISP_CAND_0024": 625,
}
EXPECTED_COUNTS = {
    "academic_verified_units": 38,
    "visual_decisions": 38,
    "visual_required_units": 37,
    "ready_source_crops": 37,
    "not_required_from_academic_review": 1,
    "png_files": 37,
    "unresolved_visual_units": 0,
    "question_continuation_assets": 2,
    "rights_review_required_units": 38,
    "promotion_eligible_units": 0,
    "production_release_eligible": 0,
}
READY_SOURCE_CROP = "READY_SOURCE_CROP"
NOT_REQUIRED_FROM_ACADEMIC_REVIEW = "NOT_REQUIRED_FROM_ACADEMIC_REVIEW"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REQUIRED_FILES = (
    "README.md",
    "visual_review_decisions.json",
    "visual_asset_manifest.json",
    "visual_asset_stats.json",
    "visual_asset_contract.json",
)


@dataclass(frozen=True, slots=True, order=True)
class GroupedDataDispersionVisualAssetIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class GroupedDataDispersionVisualAssetReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    unresolved_candidate_ids: tuple[str, ...]
    not_required_candidate_ids: tuple[str, ...]
    question_continuation_candidate_ids: tuple[str, ...]
    aggregate_semantic_and_assets_sha256: str | None
    production_release_eligible: int
    database_import_allowed: bool
    canonical_snapshot_allowed: bool
    errors: tuple[GroupedDataDispersionVisualAssetIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "unresolved_candidate_ids": list(self.unresolved_candidate_ids),
            "not_required_candidate_ids": list(self.not_required_candidate_ids),
            "question_continuation_candidate_ids": list(
                self.question_continuation_candidate_ids
            ),
            "aggregate_semantic_and_assets_sha256": (
                self.aggregate_semantic_and_assets_sha256
            ),
            "production_release_eligible": self.production_release_eligible,
            "database_import_allowed": self.database_import_allowed,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class GroupedDataDispersionVisualAssetValidator:
    """Validate read-only DATA-MATH12-022 visual/source assets."""

    def validate(
        self,
        visual_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH,
        *,
        review_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
        materialization_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_MATERIALIZATION_PATH,
    ) -> GroupedDataDispersionVisualAssetReport:
        path = visual_path.resolve()
        review_path = review_path.resolve()
        materialization_path = materialization_path.resolve()
        initial: list[GroupedDataDispersionVisualAssetIssue] = []

        self._check_required_files(path, initial)
        decisions = self._load_list(path / "visual_review_decisions.json", initial)
        manifest = self._load_object(path / "visual_asset_manifest.json", initial)
        stats = self._load_object(path / "visual_asset_stats.json", initial)
        contract = self._load_object(path / "visual_asset_contract.json", initial)
        reviews = self._load_list(review_path / "standalone_reviews.json", initial)
        evidence = self._load_list(review_path / "source_evidence.json", initial)
        source_hashes = self._load_object(
            materialization_path / "source_hash_verification.json", initial
        )

        raw_assets = manifest.get("assets")
        assets = (
            raw_assets
            if isinstance(raw_assets, list)
            and all(isinstance(row, dict) for row in raw_assets)
            else []
        )
        verified_reviews = {
            str(row["candidate_id"]): row
            for row in reviews
            if row.get("review_status") == "VERIFIED"
            and isinstance(row.get("candidate_id"), str)
        }
        evidence_by_candidate = {
            str(row["candidate_id"]): row
            for row in evidence
            if row.get("question_unit_type") == "STANDALONE"
            and isinstance(row.get("candidate_id"), str)
        }

        checks_to_errors: dict[
            str, list[GroupedDataDispersionVisualAssetIssue]
        ] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "academic_review_binding": self._validate_academic_review_binding(
                review_path,
                materialization_path,
                manifest,
                contract,
                verified_reviews,
            ),
            "decision_registry": self._validate_decisions(
                decisions, verified_reviews, assets
            ),
            "manifest_contract": self._validate_manifest_contract(
                manifest, stats, contract
            ),
            "asset_registry": self._validate_asset_registry(
                path, assets, decisions, contract
            ),
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "png_integrity": self._validate_png_integrity(path, assets, contract),
            "source_lineage": self._validate_source_lineage(
                manifest,
                assets,
                verified_reviews,
                evidence_by_candidate,
                source_hashes,
            ),
            "source_page_roles": self._validate_source_page_roles(assets),
            "component_crop_policy": self._validate_component_crop_policy(
                manifest, assets
            ),
            "release_boundary": self._validate_release_boundary(
                decisions, assets, manifest, stats, contract
            ),
        }
        for issue in initial:
            if issue.check != "required_files":
                checks_to_errors.setdefault(issue.check, []).append(issue)

        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[GroupedDataDispersionVisualAssetIssue] = []
        expected_aggregate = contract.get("aggregate_semantic_and_assets_sha256")
        if aggregate != EXPECTED_VISUAL_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "visual_asset_contract.json",
                    f"Expected {EXPECTED_VISUAL_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if expected_aggregate != EXPECTED_VISUAL_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "visual_asset_contract.json",
                    "The contract does not bind the locked DATA-MATH12-022 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        errors = tuple(
            sorted(issue for issues in checks_to_errors.values() for issue in issues)
        )
        decision_statuses = Counter(
            row.get("visual_review_status") for row in decisions
        )
        unresolved = tuple(
            sorted(
                str(row.get("candidate_id"))
                for row in decisions
                if row.get("visual_review_status")
                not in {READY_SOURCE_CROP, NOT_REQUIRED_FROM_ACADEMIC_REVIEW}
            )
        )
        counts = {
            "academic_verified_units": len(verified_reviews),
            "visual_decisions": len(decisions),
            "visual_required_units": sum(
                row.get("academic_visual_required") is True for row in decisions
            ),
            "ready_source_crops": decision_statuses[READY_SOURCE_CROP],
            "not_required_from_academic_review": decision_statuses[
                NOT_REQUIRED_FROM_ACADEMIC_REVIEW
            ],
            "png_files": len(list((path / "assets").rglob("*.png")))
            if (path / "assets").is_dir()
            else 0,
            "unresolved_visual_units": len(unresolved),
            "question_continuation_assets": sum(
                row.get("source_page_role") == "QUESTION_CONTINUATION"
                for row in assets
            ),
            "rights_review_required_units": sum(
                row.get("rights_status") == "REVIEW_REQUIRED" for row in decisions
            ),
            "promotion_eligible_units": sum(
                row.get("promotion_eligible") is True for row in decisions
            ),
            "production_release_eligible": self._int_value(
                stats.get("production_release_eligible"), default=-1
            ),
        }
        if counts != EXPECTED_COUNTS:
            errors = tuple(
                sorted(
                    (
                        *errors,
                        self._issue(
                            "exact_counts",
                            "COUNT_MISMATCH",
                            "visual_asset_stats.json",
                            f"Expected {EXPECTED_COUNTS!r}, got {counts!r}.",
                        ),
                    )
                )
            )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }
        checks["exact_counts"] = counts == EXPECTED_COUNTS
        return GroupedDataDispersionVisualAssetReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            unresolved_candidate_ids=unresolved,
            not_required_candidate_ids=tuple(
                sorted(
                    str(row.get("candidate_id"))
                    for row in decisions
                    if row.get("visual_review_status")
                    == NOT_REQUIRED_FROM_ACADEMIC_REVIEW
                )
            ),
            question_continuation_candidate_ids=tuple(
                sorted(
                    str(row.get("candidate_id"))
                    for row in assets
                    if row.get("source_page_role") == "QUESTION_CONTINUATION"
                )
            ),
            aggregate_semantic_and_assets_sha256=aggregate,
            production_release_eligible=self._int_value(
                stats.get("production_release_eligible"), default=-1
            ),
            database_import_allowed=stats.get("database_import_allowed") is True,
            canonical_snapshot_allowed=(
                stats.get("canonical_snapshot_allowed") is True
            ),
            errors=errors,
        )

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        contract_path = path / "visual_asset_contract.json"
        if contract_path.is_file():
            actual_contract_hash = self._semantic_hash(contract_path)
            if actual_contract_hash != EXPECTED_CONTRACT_SEMANTIC_SHA256:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "CONTRACT_HASH_MISMATCH",
                        contract_path.name,
                        "The curated visual contract changed semantically.",
                    )
                )
        expected_hashes = contract.get("semantic_sha256")
        order = contract.get("semantic_files_order")
        if not isinstance(expected_hashes, dict) or not isinstance(order, list):
            return [
                *issues,
                self._issue(
                    "curated_hash_contract",
                    "INVALID_SEMANTIC_HASH_CONTRACT",
                    contract_path.name,
                    "semantic_sha256 and semantic_files_order are required.",
                ),
            ]
        if set(order) != set(expected_hashes):
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "SEMANTIC_FILE_SET_MISMATCH",
                    contract_path.name,
                    "Semantic file order and hash keys differ.",
                )
            )
        for name, expected in expected_hashes.items():
            file_path = path / str(name)
            actual = self._semantic_hash(file_path) if file_path.is_file() else None
            if actual != expected:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "SEMANTIC_HASH_MISMATCH",
                        str(name),
                        f"Expected {expected!r}, got {actual!r}.",
                    )
                )
        return issues

    def _validate_academic_review_binding(
        self,
        review_path: Path,
        materialization_path: Path,
        manifest: dict[str, Any],
        contract: dict[str, Any],
        verified_reviews: dict[str, dict[str, Any]],
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        review_report = GroupedDataDispersionAcademicReviewValidator().validate(
            review_path,
            materialization_path=materialization_path,
        )
        if not review_report.is_valid:
            issues.append(
                self._issue(
                    "academic_review_binding",
                    "ACADEMIC_REVIEW_INVALID",
                    str(review_path),
                    "DATA-MATH12-021 validation did not pass.",
                )
            )
        if review_report.review_aggregate_semantic_sha256 != EXPECTED_REVIEW_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "academic_review_binding",
                    "ACADEMIC_AGGREGATE_MISMATCH",
                    str(review_path),
                    "The visual set is not bound to the locked DATA-MATH12-021 aggregate.",
                )
            )
        for location, value in (
            ("visual_asset_manifest.json", manifest),
            ("visual_asset_contract.json", contract),
        ):
            if value.get("input_review_dataset") != "DATA-MATH12-021" or value.get(
                "input_review_aggregate_sha256"
            ) != EXPECTED_REVIEW_AGGREGATE_SHA256:
                issues.append(
                    self._issue(
                        "academic_review_binding",
                        "INPUT_REVIEW_BINDING_MISMATCH",
                        location,
                        "Input dataset or academic-review aggregate does not match.",
                    )
                )
        if len(verified_reviews) != 38:
            issues.append(
                self._issue(
                    "academic_review_binding",
                    "VERIFIED_REVIEW_COUNT_MISMATCH",
                    "standalone_reviews.json",
                    f"Expected 38 VERIFIED standalone reviews, got {len(verified_reviews)}.",
                )
            )
        return issues

    def _validate_decisions(
        self,
        decisions: list[dict[str, Any]],
        verified_reviews: dict[str, dict[str, Any]],
        assets: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        ids = [row.get("candidate_id") for row in decisions]
        if len(ids) != len(set(ids)):
            issues.append(
                self._issue(
                    "decision_registry",
                    "DUPLICATE_CANDIDATE_DECISION",
                    "visual_review_decisions.json",
                    "Each candidate must have exactly one visual decision.",
                )
            )
        if set(ids) != set(verified_reviews):
            issues.append(
                self._issue(
                    "decision_registry",
                    "DECISION_SET_MISMATCH",
                    "visual_review_decisions.json",
                    "Visual decisions must exactly cover VERIFIED standalone reviews.",
                )
            )
        assets_by_id = {
            row.get("asset_id"): row for row in assets if row.get("asset_id") is not None
        }
        for index, row in enumerate(decisions):
            candidate_id = row.get("candidate_id")
            review = verified_reviews.get(str(candidate_id))
            location = f"visual_review_decisions.json[{index}]"
            expected_required = review.get("visual_asset_required") if review else None
            if row.get("academic_review_status") != "VERIFIED" or row.get(
                "academic_visual_required"
            ) is not expected_required:
                issues.append(
                    self._issue(
                        "decision_registry",
                        "ACADEMIC_DECISION_MISMATCH",
                        location,
                        "Decision must preserve the academic review status and visual flag.",
                    )
                )
            status = row.get("visual_review_status")
            asset_id = row.get("visual_asset_id")
            if expected_required is True:
                asset = assets_by_id.get(asset_id)
                valid = (
                    status == READY_SOURCE_CROP
                    and row.get("visual_required_for_canonical_snapshot") is True
                    and asset is not None
                    and asset.get("candidate_id") == candidate_id
                )
            else:
                valid = (
                    candidate_id == EXPECTED_NOT_REQUIRED_ID
                    and status == NOT_REQUIRED_FROM_ACADEMIC_REVIEW
                    and asset_id is None
                    and row.get("visual_required_for_canonical_snapshot") is False
                )
            if not valid:
                issues.append(
                    self._issue(
                        "decision_registry",
                        "INVALID_VISUAL_DECISION",
                        location,
                        "Visual decision is inconsistent with academic review or asset registry.",
                    )
                )
        return issues

    def _validate_manifest_contract(
        self,
        manifest: dict[str, Any],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        if (
            manifest.get("dataset_code") != "DATA-MATH12-022"
            or manifest.get("subject_code") != "MATH_G12"
            or manifest.get("chapter_code") != "GROUPED_DATA_DISPERSION"
            or manifest.get("render_dpi") != 200
        ):
            issues.append(
                self._issue(
                    "manifest_contract",
                    "INVALID_MANIFEST_IDENTITY",
                    "visual_asset_manifest.json",
                    "Dataset identity, subject, chapter, and render DPI are locked.",
                )
            )
        required = contract.get("required_invariants")
        if not isinstance(required, dict):
            required = {}
        for key, expected in required.items():
            if stats.get(key) != expected:
                issues.append(
                    self._issue(
                        "manifest_contract",
                        "STATS_CONTRACT_MISMATCH",
                        f"visual_asset_stats.json:{key}",
                        f"Expected {expected!r}, got {stats.get(key)!r}.",
                    )
                )
        if contract.get("not_required_candidate_ids") != [EXPECTED_NOT_REQUIRED_ID]:
            issues.append(
                self._issue(
                    "manifest_contract",
                    "NOT_REQUIRED_ID_MISMATCH",
                    "visual_asset_contract.json",
                    "The sole nonvisual academic unit must remain candidate 0034.",
                )
            )
        if contract.get("question_continuation_asset_pages") != EXPECTED_CONTINUATION_PAGES:
            issues.append(
                self._issue(
                    "manifest_contract",
                    "CONTINUATION_CONTRACT_MISMATCH",
                    "visual_asset_contract.json",
                    "The two reviewed continuation pages are locked.",
                )
            )
        return issues

    def _validate_asset_registry(
        self,
        path: Path,
        assets: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        candidate_ids = [row.get("candidate_id") for row in assets]
        asset_ids = [row.get("asset_id") for row in assets]
        if len(candidate_ids) != len(set(candidate_ids)) or len(asset_ids) != len(
            set(asset_ids)
        ):
            issues.append(
                self._issue(
                    "asset_registry",
                    "DUPLICATE_ASSET_KEY",
                    "visual_asset_manifest.json",
                    "Candidate and asset IDs must be unique.",
                )
            )
        ready_ids = {
            row.get("candidate_id")
            for row in decisions
            if row.get("visual_review_status") == READY_SOURCE_CROP
        }
        if set(candidate_ids) != ready_ids:
            issues.append(
                self._issue(
                    "asset_registry",
                    "ASSET_CANDIDATE_SET_MISMATCH",
                    "visual_asset_manifest.json",
                    "Manifest assets must exactly cover READY decisions.",
                )
            )
        declared_files: set[str] = set()
        for index, row in enumerate(assets):
            location = f"visual_asset_manifest.json:assets[{index}]"
            name = row.get("file_name")
            if not isinstance(name, str) or not self._safe_relative_path(path, name):
                issues.append(
                    self._issue(
                        "asset_registry",
                        "UNSAFE_ASSET_PATH",
                        location,
                        "Asset file_name must be relative and remain under the asset root.",
                    )
                )
            else:
                declared_files.add(name)
        actual_files = {
            file.relative_to(path).as_posix()
            for file in (path / "assets").rglob("*.png")
            if file.is_file()
        } if (path / "assets").is_dir() else set()
        contract_files = set(contract.get("asset_file_hashes", {}))
        if actual_files != declared_files or actual_files != contract_files:
            issues.append(
                self._issue(
                    "asset_registry",
                    "PNG_FILE_SET_MISMATCH",
                    "assets/",
                    "Declared, contracted, and actual PNG files must match exactly.",
                )
            )
        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        pdf_files = [
            file.relative_to(path).as_posix()
            for file in path.rglob("*")
            if file.is_file() and file.suffix.casefold() == ".pdf"
        ]
        if not pdf_files:
            return []
        return [
            self._issue(
                "no_pdf_binaries",
                "SOURCE_PDF_BINARY_PRESENT",
                pdf_files[0],
                "Source PDF binaries are forbidden in the visual asset registry.",
            )
        ]

    def _validate_png_integrity(
        self,
        path: Path,
        assets: list[dict[str, Any]],
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        contract_hashes = contract.get("asset_file_hashes")
        if not isinstance(contract_hashes, dict):
            contract_hashes = {}
        for index, row in enumerate(assets):
            location = f"visual_asset_manifest.json:assets[{index}]"
            name = row.get("file_name")
            if not isinstance(name, str) or not self._safe_relative_path(path, name):
                continue
            asset_path = path / PurePosixPath(name)
            if not asset_path.is_file():
                issues.append(
                    self._issue(
                        "png_integrity",
                        "ASSET_FILE_MISSING",
                        name,
                        "Declared PNG file does not exist.",
                    )
                )
                continue
            data = asset_path.read_bytes()
            actual_sha = hashlib.sha256(data).hexdigest()
            if (
                row.get("mime_type") != "image/png"
                or actual_sha != row.get("sha256")
                or actual_sha != contract_hashes.get(name)
            ):
                issues.append(
                    self._issue(
                        "png_integrity",
                        "PNG_HASH_OR_MIME_MISMATCH",
                        location,
                        "PNG MIME or SHA-256 does not match manifest and contract.",
                    )
                )
            try:
                dimensions = self._png_dimensions(data)
            except ValueError as exc:
                issues.append(
                    self._issue(
                        "png_integrity",
                        "INVALID_PNG",
                        name,
                        str(exc),
                    )
                )
                continue
            if dimensions != (row.get("width_px"), row.get("height_px")):
                issues.append(
                    self._issue(
                        "png_integrity",
                        "PNG_DIMENSION_MISMATCH",
                        location,
                        f"Expected manifest dimensions, got {dimensions!r}.",
                    )
                )
        return issues

    def _validate_source_lineage(
        self,
        manifest: dict[str, Any],
        assets: list[dict[str, Any]],
        reviews: dict[str, dict[str, Any]],
        evidence: dict[str, dict[str, Any]],
        source_hashes: dict[str, Any],
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        source_rows = source_hashes.get("sources")
        hash_by_key = {
            row.get("source_key"): row
            for row in source_rows
            if isinstance(row, dict)
        } if isinstance(source_rows, list) else {}
        manifest_sources = manifest.get("source_pdfs")
        if not isinstance(manifest_sources, dict):
            manifest_sources = {}
        used_source_keys = {row.get("source_key") for row in assets}
        if set(manifest_sources) != used_source_keys:
            issues.append(
                self._issue(
                    "source_lineage",
                    "SOURCE_REGISTRY_SET_MISMATCH",
                    "visual_asset_manifest.json:source_pdfs",
                    "Source registry must exactly describe the sources used by assets.",
                )
            )
        for source_key, row in manifest_sources.items():
            verified = hash_by_key.get(source_key)
            if not verified or any(
                (
                    row.get("source_key") != source_key,
                    row.get("source_file_id") != verified.get("drive_file_id"),
                    row.get("source_pdf_sha256") != verified.get("actual_sha256"),
                    verified.get("status") != "MATCH",
                )
            ):
                issues.append(
                    self._issue(
                        "source_lineage",
                        "SOURCE_PDF_LINEAGE_MISMATCH",
                        f"visual_asset_manifest.json:source_pdfs:{source_key}",
                        "Source PDF identity or verified hash does not match DATA-MATH12-020.",
                    )
                )
        for index, asset in enumerate(assets):
            candidate_id = str(asset.get("candidate_id"))
            review = reviews.get(candidate_id)
            source_evidence = evidence.get(candidate_id)
            source = manifest_sources.get(asset.get("source_key"))
            fields_match = review is not None and source_evidence is not None and source is not None
            if fields_match:
                fields_match = all(
                    (
                        asset.get("source_code") == review.get("source_code") == source_evidence.get("source_code") == source.get("source_code"),
                        asset.get("source_key") == review.get("source_key") == source_evidence.get("source_key") == source.get("source_key"),
                        asset.get("source_file_id") == review.get("source_file_id") == source_evidence.get("source_file_id") == source.get("source_file_id"),
                        asset.get("source_pdf_sha256") == review.get("source_sha256") == source_evidence.get("source_sha256") == source.get("source_pdf_sha256"),
                        asset.get("question_anchor_page") == review.get("candidate_source_page") == source_evidence.get("candidate_source_page"),
                        asset.get("canonical_question_pages") == source_evidence.get("question_pages"),
                        asset.get("solution_pages") == source_evidence.get("solution_pages"),
                    )
                )
            if not fields_match:
                issues.append(
                    self._issue(
                        "source_lineage",
                        "ASSET_SOURCE_LINEAGE_MISMATCH",
                        f"visual_asset_manifest.json:assets[{index}]",
                        "Asset source identity/pages do not match review evidence.",
                    )
                )
        return issues

    def _validate_source_page_roles(
        self, assets: list[dict[str, Any]]
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        continuations: dict[str, int] = {}
        for index, row in enumerate(assets):
            candidate_id = str(row.get("candidate_id"))
            role = row.get("source_page_role")
            anchor = row.get("question_anchor_page")
            source_page = row.get("asset_source_page")
            if role == "QUESTION_CONTINUATION":
                continuations[candidate_id] = self._int_value(source_page, default=-1)
                valid = (
                    candidate_id in EXPECTED_CONTINUATION_PAGES
                    and source_page == EXPECTED_CONTINUATION_PAGES[candidate_id]
                    and source_page != anchor
                )
            else:
                valid = role == "QUESTION_PAGE" and source_page == anchor
            if not valid:
                issues.append(
                    self._issue(
                        "source_page_roles",
                        "INVALID_SOURCE_PAGE_ROLE",
                        f"visual_asset_manifest.json:assets[{index}]",
                        "Asset source page and role do not follow the reviewed page contract.",
                    )
                )
        if continuations != EXPECTED_CONTINUATION_PAGES:
            issues.append(
                self._issue(
                    "source_page_roles",
                    "CONTINUATION_SET_MISMATCH",
                    "visual_asset_manifest.json",
                    "Exactly candidates 0003 and 0024 must use continuation pages.",
                )
            )
        return issues

    def _validate_component_crop_policy(
        self, manifest: dict[str, Any], assets: list[dict[str, Any]]
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        policy = manifest.get("asset_policy")
        expected_policy = {
            "crop_scope": "DISTINCT_SOURCE_DATA_COMPONENT_ONLY",
            "no_full_question_crop_for_production": True,
            "fabrication_allowed": False,
            "redraw_allowed": False,
            "synthetic_asset_allowed": False,
            "rights_status": "REVIEW_REQUIRED",
        }
        if not isinstance(policy, dict) or any(
            policy.get(key) != value for key, value in expected_policy.items()
        ):
            issues.append(
                self._issue(
                    "component_crop_policy",
                    "INVALID_ASSET_POLICY",
                    "visual_asset_manifest.json:asset_policy",
                    "Component-only source-crop policy and safety boundaries are required.",
                )
            )
        for index, row in enumerate(assets):
            crop = row.get("crop_box_pdf_points")
            valid_crop = (
                isinstance(crop, list)
                and len(crop) == 4
                and all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    for value in crop
                )
                and crop[0] >= 0
                and crop[1] >= 0
                and crop[2] > crop[0]
                and crop[3] > crop[1]
            )
            component_types = row.get("component_types")
            valid = all(
                (
                    row.get("asset_kind")
                    in {"SOURCE_DATA_TABLE_CROP", "SOURCE_DATA_CHART_CROP"},
                    row.get("asset_status") == READY_SOURCE_CROP,
                    valid_crop,
                    isinstance(component_types, list) and bool(component_types),
                    row.get("component_count") == len(component_types or []),
                    row.get("extraction_method")
                    == "SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI",
                    row.get("answer_leakage_check")
                    == "PASS_DISTINCT_COMPONENT_ONLY",
                )
            )
            if not valid:
                issues.append(
                    self._issue(
                        "component_crop_policy",
                        "INVALID_COMPONENT_CROP",
                        f"visual_asset_manifest.json:assets[{index}]",
                        "Only reviewed data-component crops are permitted.",
                    )
                )
        return issues

    def _validate_release_boundary(
        self,
        decisions: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        manifest: dict[str, Any],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionVisualAssetIssue]:
        issues: list[GroupedDataDispersionVisualAssetIssue] = []
        invalid_decision = any(
            row.get("rights_status") != "REVIEW_REQUIRED"
            or row.get("promotion_ready") is not False
            for row in decisions
        )
        invalid_asset = any(
            row.get("rights_status") != "REVIEW_REQUIRED"
            or row.get("promotion_eligible") is not False
            for row in assets
        )
        if invalid_decision or invalid_asset:
            issues.append(
                self._issue(
                    "release_boundary",
                    "RELEASE_BOUNDARY_VIOLATION",
                    "visual assets",
                    "Every decision/asset must require rights review and remain non-promotable.",
                )
            )
        if manifest.get("asset_policy", {}).get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "release_boundary",
                    "RIGHTS_POLICY_MISMATCH",
                    "visual_asset_manifest.json",
                    "Global rights status must remain REVIEW_REQUIRED.",
                )
            )
        locked = {
            "promotion_eligible_units": 0,
            "production_release_eligible": 0,
            "database_import_allowed": False,
            "canonical_snapshot_allowed": False,
        }
        required = contract.get("required_invariants")
        if not isinstance(required, dict):
            required = {}
        if any(stats.get(key) != value for key, value in locked.items()) or any(
            required.get(key) != value for key, value in locked.items()
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "GLOBAL_RELEASE_FLAG_MISMATCH",
                    "visual_asset_stats.json",
                    "Promotion, production release, DB import, and snapshots must remain blocked.",
                )
            )
        return issues

    def _aggregate_hash(self, path: Path, contract: dict[str, Any]) -> str | None:
        order = contract.get("semantic_files_order")
        hashes = contract.get("asset_file_hashes")
        if not isinstance(order, list) or not isinstance(hashes, dict):
            return None
        digest = hashlib.sha256()
        try:
            for name in order:
                name = str(name)
                data = json.loads((path / name).read_text(encoding="utf-8"))
                canonical = json.dumps(
                    data,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                digest.update(name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(canonical)
                digest.update(b"\0")
            for name in sorted(str(key) for key in hashes):
                if not self._safe_relative_path(path, name):
                    return None
                actual_hash = hashlib.sha256(
                    (path / PurePosixPath(name)).read_bytes()
                ).hexdigest()
                digest.update(name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(actual_hash.encode("ascii"))
                digest.update(b"\0")
        except (OSError, json.JSONDecodeError, TypeError, UnicodeError):
            return None
        return digest.hexdigest()

    @staticmethod
    def _semantic_hash(path: Path) -> str | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        canonical = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _png_dimensions(data: bytes) -> tuple[int, int]:
        if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
            raise ValueError("File is not a PNG with a valid IHDR header.")
        return struct.unpack(">II", data[16:24])

    @staticmethod
    def _safe_relative_path(root: Path, value: str) -> bool:
        posix = PurePosixPath(value)
        windows = PureWindowsPath(value)
        if (
            not value
            or "\\" in value
            or posix.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or ".." in posix.parts
        ):
            return False
        try:
            (root / posix).resolve().relative_to(root)
        except (OSError, ValueError):
            return False
        return True

    @staticmethod
    def _load_list(
        path: Path, issues: list[GroupedDataDispersionVisualAssetIssue]
    ) -> list[dict[str, Any]]:
        value = GroupedDataDispersionVisualAssetValidator._load_json(path, issues)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
        issues.append(
            GroupedDataDispersionVisualAssetValidator._issue(
                "json_schema", "EXPECTED_LIST", path.name, "Expected a JSON object list."
            )
        )
        return []

    @staticmethod
    def _load_object(
        path: Path, issues: list[GroupedDataDispersionVisualAssetIssue]
    ) -> dict[str, Any]:
        value = GroupedDataDispersionVisualAssetValidator._load_json(path, issues)
        if isinstance(value, dict):
            return value
        issues.append(
            GroupedDataDispersionVisualAssetValidator._issue(
                "json_schema", "EXPECTED_OBJECT", path.name, "Expected a JSON object."
            )
        )
        return {}

    @staticmethod
    def _load_json(
        path: Path, issues: list[GroupedDataDispersionVisualAssetIssue]
    ) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            issues.append(
                GroupedDataDispersionVisualAssetValidator._issue(
                    "json_schema", "JSON_LOAD_FAILED", path.name, str(exc)
                )
            )
            return None

    @staticmethod
    def _check_required_files(
        path: Path, issues: list[GroupedDataDispersionVisualAssetIssue]
    ) -> None:
        for name in REQUIRED_FILES:
            if not (path / name).is_file():
                issues.append(
                    GroupedDataDispersionVisualAssetValidator._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        name,
                        "Required curated file is missing.",
                    )
                )
        if not (path / "assets").is_dir():
            issues.append(
                GroupedDataDispersionVisualAssetValidator._issue(
                    "required_files",
                    "MISSING_ASSET_DIRECTORY",
                    "assets/",
                    "Curated asset directory is missing.",
                )
            )

    @staticmethod
    def _int_value(value: Any, *, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    @staticmethod
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> GroupedDataDispersionVisualAssetIssue:
        return GroupedDataDispersionVisualAssetIssue(
            check=check, code=code, location=location, message=message
        )
