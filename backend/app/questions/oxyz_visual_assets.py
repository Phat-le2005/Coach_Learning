from __future__ import annotations

import hashlib
import json
import struct
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.questions.oxyz_academic_review import (
    DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH,
    EXPECTED_AGGREGATE_SEMANTIC_SHA256 as EXPECTED_BASE_REVIEW_AGGREGATE_SHA256,
    OxyzAcademicReviewValidator,
)


DEFAULT_OXYZ_VISUAL_ASSET_PATH = (
    DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH.parents[1]
    / "visual_assets"
    / "v0_1"
)
EXPECTED_VISUAL_AGGREGATE_SHA256 = (
    "e86db0b1c288e47fa278b9b1b22f8294785157664f984490112bacf9d584aa5b"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "0c0e5f790f0c0cdf35bc6e1dfd4aa7cab75d745b8376ceafe183a7568b8e1e40"
)
EXPECTED_COUNTS = {
    "academic_verified_units": 132,
    "academic_visual_required_units": 6,
    "visual_decisions": 132,
    "ready_source_crops": 5,
    "not_required_after_visual_review": 1,
    "not_required_from_academic_review": 126,
    "png_files": 5,
    "unresolved_visual_units": 0,
    "rights_review_required_units": 132,
    "promotion_eligible_units": 0,
    "production_release_eligible": 0,
}
READY_SOURCE_CROP = "READY_SOURCE_CROP"
NOT_REQUIRED_AFTER_VISUAL_REVIEW = "NOT_REQUIRED_AFTER_VISUAL_REVIEW"
NOT_REQUIRED_FROM_ACADEMIC_REVIEW = "NOT_REQUIRED_FROM_ACADEMIC_REVIEW"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REQUIRED_FILES = (
    "README.md",
    "visual_review_decisions.json",
    "visual_asset_manifest.json",
    "visual_asset_stats.json",
    "visual_asset_contract.json",
)
VALID_EXTRACTION_METHODS = {
    "SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI",
    "SOURCE_VISUAL_COMPONENTS_REGION_CROP_VERTICAL_STITCH_200_DPI",
}


@dataclass(frozen=True, slots=True, order=True)
class OxyzVisualAssetIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class OxyzVisualAssetReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    unresolved_candidate_ids: tuple[str, ...]
    ready_candidate_ids: tuple[str, ...]
    not_required_after_review_candidate_ids: tuple[str, ...]
    not_required_from_academic_candidate_ids: tuple[str, ...]
    aggregate_semantic_and_assets_sha256: str | None
    production_release_eligible: int
    database_import_allowed: bool
    canonical_snapshot_allowed: bool
    errors: tuple[OxyzVisualAssetIssue, ...]

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
            "ready_candidate_ids": list(self.ready_candidate_ids),
            "not_required_after_review_candidate_ids": list(
                self.not_required_after_review_candidate_ids
            ),
            "not_required_from_academic_candidate_ids": list(
                self.not_required_from_academic_candidate_ids
            ),
            "aggregate_semantic_and_assets_sha256": (
                self.aggregate_semantic_and_assets_sha256
            ),
            "production_release_eligible": self.production_release_eligible,
            "database_import_allowed": self.database_import_allowed,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class OxyzVisualAssetValidator:
    """Validate read-only DATA-MATH12-028 visual/source assets."""

    def validate(
        self,
        visual_path: Path = DEFAULT_OXYZ_VISUAL_ASSET_PATH,
        *,
        review_path: Path = DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH,
    ) -> OxyzVisualAssetReport:
        path = visual_path.resolve()
        review_path = review_path.resolve()
        initial: list[OxyzVisualAssetIssue] = []

        self._check_required_files(path, initial)
        decisions = self._load_list(path / "visual_review_decisions.json", initial)
        manifest = self._load_object(path / "visual_asset_manifest.json", initial)
        stats = self._load_object(path / "visual_asset_stats.json", initial)
        contract = self._load_object(path / "visual_asset_contract.json", initial)

        review_questions = self._load_list(
            review_path / "verified_questions.json", initial
        )
        source_evidence = self._load_list(
            review_path / "source_evidence.json", initial
        )

        raw_assets = manifest.get("assets")
        assets = (
            raw_assets
            if isinstance(raw_assets, list)
            and all(isinstance(row, dict) for row in raw_assets)
            else []
        )
        verified_candidates = {
            str(row["candidate_id"]): row
            for row in review_questions
            if isinstance(row.get("candidate_id"), str)
        }
        evidence_by_candidate = {
            str(row["candidate_id"]): row
            for row in source_evidence
            if isinstance(row.get("candidate_id"), str)
        }

        checks_to_errors: dict[str, list[OxyzVisualAssetIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "academic_review_binding": self._validate_academic_review_binding(
                review_path,
                manifest,
                contract,
                verified_candidates,
            ),
            "decision_registry": self._validate_decisions(
                decisions, verified_candidates, assets
            ),
            "manifest_contract": self._validate_manifest_contract(
                manifest, stats, contract
            ),
            "asset_registry": self._validate_asset_registry(
                path, assets, decisions, contract
            ),
            "png_integrity": self._validate_png_integrity(path, assets, contract),
            "source_lineage": self._validate_source_lineage(
                manifest,
                assets,
                verified_candidates,
                evidence_by_candidate,
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
        aggregate_errors: list[OxyzVisualAssetIssue] = []
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
                    "The contract does not bind the locked DATA-MATH12-028 aggregate.",
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
                not in {
                    READY_SOURCE_CROP,
                    NOT_REQUIRED_AFTER_VISUAL_REVIEW,
                    NOT_REQUIRED_FROM_ACADEMIC_REVIEW,
                }
            )
        )
        ready_ids = tuple(
            sorted(
                str(row.get("candidate_id"))
                for row in decisions
                if row.get("visual_review_status") == READY_SOURCE_CROP
            )
        )
        not_required_after_ids = tuple(
            sorted(
                str(row.get("candidate_id"))
                for row in decisions
                if row.get("visual_review_status") == NOT_REQUIRED_AFTER_VISUAL_REVIEW
            )
        )
        not_required_from_academic_ids = tuple(
            sorted(
                str(row.get("candidate_id"))
                for row in decisions
                if row.get("visual_review_status") == NOT_REQUIRED_FROM_ACADEMIC_REVIEW
            )
        )
        counts = {
            "academic_verified_units": len(verified_candidates),
            "academic_visual_required_units": sum(
                row.get("academic_visual_required") is True for row in decisions
            ),
            "visual_decisions": len(decisions),
            "ready_source_crops": decision_statuses[READY_SOURCE_CROP],
            "not_required_after_visual_review": decision_statuses[
                NOT_REQUIRED_AFTER_VISUAL_REVIEW
            ],
            "not_required_from_academic_review": decision_statuses[
                NOT_REQUIRED_FROM_ACADEMIC_REVIEW
            ],
            "png_files": len(list((path / "assets").rglob("*.png")))
            if (path / "assets").is_dir()
            else 0,
            "unresolved_visual_units": len(unresolved),
            "rights_review_required_units": sum(
                row.get("rights_status") == "REVIEW_REQUIRED" for row in decisions
            ),
            "promotion_eligible_units": sum(
                row.get("promotion_ready") is True for row in decisions
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
        return OxyzVisualAssetReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            unresolved_candidate_ids=unresolved,
            ready_candidate_ids=ready_ids,
            not_required_after_review_candidate_ids=not_required_after_ids,
            not_required_from_academic_candidate_ids=not_required_from_academic_ids,
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
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
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
        manifest: dict[str, Any],
        contract: dict[str, Any],
        verified_candidates: dict[str, dict[str, Any]],
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        review_report = OxyzAcademicReviewValidator().validate(review_path)
        if not review_report.is_valid:
            issues.append(
                self._issue(
                    "academic_review_binding",
                    "ACADEMIC_REVIEW_INVALID",
                    str(review_path),
                    "DATA-MATH12-024 validation did not pass.",
                )
            )
        if (
            review_report.aggregate_semantic_sha256
            != EXPECTED_BASE_REVIEW_AGGREGATE_SHA256
        ):
            issues.append(
                self._issue(
                    "academic_review_binding",
                    "ACADEMIC_AGGREGATE_MISMATCH",
                    str(review_path),
                    "The visual set is not bound to the locked DATA-MATH12-024 aggregate.",
                )
            )
        for location, value in (
            ("visual_asset_manifest.json", manifest),
            ("visual_asset_contract.json", contract),
        ):
            if value.get("input_review_dataset") != "DATA-MATH12-024" or value.get(
                "input_review_aggregate_sha256"
            ) != EXPECTED_BASE_REVIEW_AGGREGATE_SHA256:
                issues.append(
                    self._issue(
                        "academic_review_binding",
                        "INPUT_REVIEW_BINDING_MISMATCH",
                        location,
                        "Input dataset or academic-review aggregate does not match.",
                    )
                )
        if len(verified_candidates) != 132:
            issues.append(
                self._issue(
                    "academic_review_binding",
                    "VERIFIED_REVIEW_COUNT_MISMATCH",
                    "verified_questions.json",
                    f"Expected 132 VERIFIED questions, got {len(verified_candidates)}.",
                )
            )
        return issues

    def _validate_decisions(
        self,
        decisions: list[dict[str, Any]],
        verified_candidates: dict[str, dict[str, Any]],
        assets: list[dict[str, Any]],
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        decision_by_id = {row.get("candidate_id"): row for row in decisions}
        asset_by_candidate = {row.get("candidate_id"): row for row in assets}

        if len(decisions) != len(verified_candidates):
            issues.append(
                self._issue(
                    "decision_registry",
                    "DECISION_COUNT_MISMATCH",
                    "visual_review_decisions.json",
                    f"Expected {len(verified_candidates)} decisions, got {len(decisions)}.",
                )
            )
        missing_candidates = set(verified_candidates) - set(decision_by_id)
        if missing_candidates:
            issues.append(
                self._issue(
                    "decision_registry",
                    "MISSING_DECISION_CANDIDATES",
                    "visual_review_decisions.json",
                    f"Missing decisions for verified candidates: {sorted(missing_candidates)!r}.",
                )
            )

        for index, row in enumerate(decisions):
            cid = row.get("candidate_id")
            location = f"visual_review_decisions.json[{index}]"
            if cid not in verified_candidates:
                issues.append(
                    self._issue(
                        "decision_registry",
                        "UNKNOWN_CANDIDATE_DECISION",
                        location,
                        f"Candidate {cid!r} is not a verified DATA-MATH12-024 question.",
                    )
                )
                continue

            status = row.get("visual_review_status")
            asset_id = row.get("visual_asset_id")
            academic_req = row.get("academic_visual_required")
            verified_data = verified_candidates[str(cid)]
            expected_acad_req = verified_data.get("visual_asset_required") is True

            if academic_req != expected_acad_req:
                issues.append(
                    self._issue(
                        "decision_registry",
                        "ACADEMIC_VISUAL_FLAG_MISMATCH",
                        location,
                        f"Candidate {cid}: expected academic_visual_required={expected_acad_req}, got {academic_req}.",
                    )
                )

            if status == READY_SOURCE_CROP:
                if not asset_id:
                    issues.append(
                        self._issue(
                            "decision_registry",
                            "MISSING_VISUAL_ASSET_ID",
                            location,
                            f"Candidate {cid} is READY_SOURCE_CROP but has no visual_asset_id.",
                        )
                    )
                elif cid not in asset_by_candidate:
                    issues.append(
                        self._issue(
                            "decision_registry",
                            "ASSET_NOT_IN_MANIFEST",
                            location,
                            f"Candidate {cid} has asset_id {asset_id} which is not in manifest.",
                        )
                    )
                if academic_req is not True:
                    issues.append(
                        self._issue(
                            "decision_registry",
                            "UNEXPECTED_READY_STATUS",
                            location,
                            f"Candidate {cid} is READY_SOURCE_CROP but academic_visual_required is false.",
                        )
                    )
            elif status == NOT_REQUIRED_AFTER_VISUAL_REVIEW:
                if asset_id is not None:
                    issues.append(
                        self._issue(
                            "decision_registry",
                            "UNEXPECTED_VISUAL_ASSET_ID",
                            location,
                            f"Candidate {cid} is not-required but has asset_id {asset_id}.",
                        )
                    )
                if academic_req is not True:
                    issues.append(
                        self._issue(
                            "decision_registry",
                            "INVALID_NOT_REQUIRED_AFTER_REVIEW",
                            location,
                            f"Candidate {cid} is NOT_REQUIRED_AFTER_VISUAL_REVIEW but academic review did not flag it as visual required.",
                        )
                    )
            elif status == NOT_REQUIRED_FROM_ACADEMIC_REVIEW:
                if asset_id is not None:
                    issues.append(
                        self._issue(
                            "decision_registry",
                            "UNEXPECTED_VISUAL_ASSET_ID",
                            location,
                            f"Candidate {cid} is not-required but has asset_id {asset_id}.",
                        )
                    )
                if academic_req is not False:
                    issues.append(
                        self._issue(
                            "decision_registry",
                            "INVALID_NOT_REQUIRED_FROM_ACADEMIC",
                            location,
                            f"Candidate {cid} is NOT_REQUIRED_FROM_ACADEMIC_REVIEW but academic review flagged it as visual required.",
                        )
                    )
            else:
                issues.append(
                    self._issue(
                        "decision_registry",
                        "UNKNOWN_VISUAL_REVIEW_STATUS",
                        location,
                        f"Unknown visual review status {status!r}.",
                    )
                )

            if row.get("rights_status") != "REVIEW_REQUIRED":
                issues.append(
                    self._issue(
                        "decision_registry",
                        "INVALID_RIGHTS_STATUS",
                        location,
                        f"Rights status must be REVIEW_REQUIRED, got {row.get('rights_status')!r}.",
                    )
                )
            if row.get("promotion_ready") is not False:
                issues.append(
                    self._issue(
                        "decision_registry",
                        "UNAUTHORIZED_PROMOTION",
                        location,
                        "promotion_ready must be False.",
                    )
                )
            if (
                row.get("database_import_allowed") is not False
                or row.get("canonical_snapshot_allowed") is not False
            ):
                issues.append(
                    self._issue(
                        "decision_registry",
                        "UNAUTHORIZED_RELEASE",
                        location,
                        "database_import_allowed and canonical_snapshot_allowed must be False.",
                    )
                )

        return issues

    def _validate_manifest_contract(
        self,
        manifest: dict[str, Any],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        if manifest.get("dataset_code") != "DATA-MATH12-028":
            issues.append(
                self._issue(
                    "manifest_contract",
                    "DATASET_CODE_MISMATCH",
                    "visual_asset_manifest.json",
                    "dataset_code must be DATA-MATH12-028.",
                )
            )
        policy = manifest.get("asset_policy")
        if not isinstance(policy, dict):
            issues.append(
                self._issue(
                    "manifest_contract",
                    "MISSING_ASSET_POLICY",
                    "visual_asset_manifest.json",
                    "asset_policy object is missing.",
                )
            )
        else:
            if (
                policy.get("crop_scope")
                != "DISTINCT_SOURCE_VISUAL_COMPONENT_ONLY"
            ):
                issues.append(
                    self._issue(
                        "manifest_contract",
                        "INVALID_CROP_SCOPE",
                        "visual_asset_manifest.json",
                        "crop_scope must be DISTINCT_SOURCE_VISUAL_COMPONENT_ONLY.",
                    )
                )
            if policy.get("no_full_question_crop_for_production") is not True:
                issues.append(
                    self._issue(
                        "manifest_contract",
                        "FULL_QUESTION_CROP_POLICY_VIOLATION",
                        "visual_asset_manifest.json",
                        "no_full_question_crop_for_production must be true.",
                    )
                )
            if policy.get("no_redraw_or_synthetic_visual") is not True:
                issues.append(
                    self._issue(
                        "manifest_contract",
                        "SYNTHETIC_VISUAL_POLICY_VIOLATION",
                        "visual_asset_manifest.json",
                        "no_redraw_or_synthetic_visual must be true.",
                    )
                )
            if policy.get("render_dpi") != 200:
                issues.append(
                    self._issue(
                        "manifest_contract",
                        "RENDER_DPI_MISMATCH",
                        "visual_asset_manifest.json",
                        "render_dpi must be 200.",
                    )
                )

        if stats.get("dataset_code") != "DATA-MATH12-028":
            issues.append(
                self._issue(
                    "manifest_contract",
                    "STATS_DATASET_CODE_MISMATCH",
                    "visual_asset_stats.json",
                    "dataset_code must be DATA-MATH12-028.",
                )
            )
        if contract.get("dataset_code") != "DATA-MATH12-028":
            issues.append(
                self._issue(
                    "manifest_contract",
                    "CONTRACT_DATASET_CODE_MISMATCH",
                    "visual_asset_contract.json",
                    "dataset_code must be DATA-MATH12-028.",
                )
            )
        if contract.get("contract_code") != "DATA_MATH12_028_VISUAL_CONTRACT_V0_1":
            issues.append(
                self._issue(
                    "manifest_contract",
                    "CONTRACT_CODE_MISMATCH",
                    "visual_asset_contract.json",
                    "contract_code must be DATA_MATH12_028_VISUAL_CONTRACT_V0_1.",
                )
            )
        return issues

    def _validate_asset_registry(
        self,
        path: Path,
        assets: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        contract: dict[str, Any],
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        ready_decisions = {
            row["candidate_id"]: row
            for row in decisions
            if row.get("visual_review_status") == READY_SOURCE_CROP
        }
        contract_hashes = contract.get("asset_file_hashes", {})

        if len(assets) != len(ready_decisions):
            issues.append(
                self._issue(
                    "asset_registry",
                    "ASSET_COUNT_MISMATCH",
                    "visual_asset_manifest.json",
                    f"Expected {len(ready_decisions)} assets, got {len(assets)}.",
                )
            )

        asset_ids: set[str] = set()
        candidate_ids: set[str] = set()

        for idx, asset in enumerate(assets):
            aid = asset.get("asset_id")
            cid = asset.get("candidate_id")
            loc = f"visual_asset_manifest.json.assets[{idx}]"

            if aid in asset_ids:
                issues.append(
                    self._issue(
                        "asset_registry",
                        "DUPLICATE_ASSET_ID",
                        loc,
                        f"Duplicate asset_id {aid!r}.",
                    )
                )
            asset_ids.add(str(aid))

            if cid in candidate_ids:
                issues.append(
                    self._issue(
                        "asset_registry",
                        "DUPLICATE_CANDIDATE_ASSET",
                        loc,
                        f"Multiple assets for candidate_id {cid!r}.",
                    )
                )
            candidate_ids.add(str(cid))

            if cid not in ready_decisions:
                issues.append(
                    self._issue(
                        "asset_registry",
                        "ASSET_CANDIDATE_NOT_READY",
                        loc,
                        f"Candidate {cid!r} is not READY_SOURCE_CROP in decisions.",
                    )
                )
            else:
                expected_aid = ready_decisions[str(cid)].get("visual_asset_id")
                if aid != expected_aid:
                    issues.append(
                        self._issue(
                            "asset_registry",
                            "ASSET_ID_DECISION_MISMATCH",
                            loc,
                            f"Decision visual_asset_id is {expected_aid!r}, but manifest has {aid!r}.",
                        )
                    )

            file_name = asset.get("file_name")
            if not isinstance(file_name, str) or not self._safe_relative_path(path, file_name):
                issues.append(
                    self._issue(
                        "asset_registry",
                        "INVALID_ASSET_FILE_PATH",
                        loc,
                        f"Invalid file_name {file_name!r}.",
                    )
                )
            elif file_name not in contract_hashes:
                issues.append(
                    self._issue(
                        "asset_registry",
                        "ASSET_FILE_NOT_IN_CONTRACT",
                        loc,
                        f"File {file_name!r} not listed in contract asset_file_hashes.",
                    )
                )

        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        pdf_files = list(path.rglob("*.pdf"))
        if pdf_files:
            issues.append(
                self._issue(
                    "no_pdf_binaries",
                    "PDF_BINARY_PRESENT",
                    str(pdf_files[0]),
                    "Raw PDF binaries must not be present in visual directory.",
                )
            )
        return issues

    def _validate_png_integrity(
        self,
        path: Path,
        assets: list[dict[str, Any]],
        contract: dict[str, Any],
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        contract_hashes = contract.get("asset_file_hashes", {})

        for idx, asset in enumerate(assets):
            file_name = asset.get("file_name")
            loc = f"visual_asset_manifest.json.assets[{idx}]"
            if not isinstance(file_name, str):
                continue
            file_path = path / PurePosixPath(file_name)
            if not file_path.is_file():
                issues.append(
                    self._issue(
                        "png_integrity",
                        "PNG_FILE_NOT_FOUND",
                        loc,
                        f"File not found: {file_name}.",
                    )
                )
                continue

            data = file_path.read_bytes()
            actual_hash = hashlib.sha256(data).hexdigest()
            expected_hash = asset.get("sha256")
            expected_contract_hash = contract_hashes.get(file_name)

            if actual_hash != expected_hash or actual_hash != expected_contract_hash:
                issues.append(
                    self._issue(
                        "png_integrity",
                        "PNG_HASH_OR_MIME_MISMATCH",
                        loc,
                        f"Hash mismatch for {file_name}: actual={actual_hash}, manifest={expected_hash}, contract={expected_contract_hash}.",
                    )
                )

            try:
                width, height = self._png_dimensions(data)
                if width != asset.get("width_px") or height != asset.get("height_px"):
                    issues.append(
                        self._issue(
                            "png_integrity",
                            "PNG_DIMENSIONS_MISMATCH",
                            loc,
                            f"Dimensions mismatch for {file_name}: actual=({width}, {height}), manifest=({asset.get('width_px')}, {asset.get('height_px')}).",
                        )
                    )
            except ValueError as e:
                issues.append(
                    self._issue(
                        "png_integrity",
                        "PNG_HEADER_INVALID",
                        loc,
                        f"Invalid PNG header: {e}",
                    )
                )

        return issues

    def _validate_source_lineage(
        self,
        manifest: dict[str, Any],
        assets: list[dict[str, Any]],
        verified_candidates: dict[str, dict[str, Any]],
        evidence_by_candidate: dict[str, dict[str, Any]],
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        for idx, asset in enumerate(assets):
            cid = asset.get("candidate_id")
            loc = f"visual_asset_manifest.json.assets[{idx}]"
            if cid not in verified_candidates:
                continue
            question = verified_candidates[str(cid)]
            evidence = evidence_by_candidate.get(str(cid), {})

            expected_source_code = question.get("source_code")
            expected_file_id = question.get("source_file_id")
            expected_pdf_sha256 = question.get("source_pdf_sha256")
            expected_page = question.get("question_start_page") or evidence.get("question_page")

            if asset.get("source_code") != expected_source_code:
                issues.append(
                    self._issue(
                        "source_lineage",
                        "SOURCE_CODE_MISMATCH",
                        loc,
                        f"Expected source_code {expected_source_code!r}, got {asset.get('source_code')!r}.",
                    )
                )
            if asset.get("source_file_id") != expected_file_id:
                issues.append(
                    self._issue(
                        "source_lineage",
                        "SOURCE_FILE_ID_MISMATCH",
                        loc,
                        f"Expected source_file_id {expected_file_id!r}, got {asset.get('source_file_id')!r}.",
                    )
                )
            if asset.get("source_pdf_sha256") != expected_pdf_sha256:
                issues.append(
                    self._issue(
                        "source_lineage",
                        "SOURCE_PDF_SHA256_MISMATCH",
                        loc,
                        f"Expected source_pdf_sha256 {expected_pdf_sha256!r}, got {asset.get('source_pdf_sha256')!r}.",
                    )
                )
            if asset.get("question_anchor_page") != expected_page:
                issues.append(
                    self._issue(
                        "source_lineage",
                        "ANCHOR_PAGE_MISMATCH",
                        loc,
                        f"Expected question_anchor_page {expected_page}, got {asset.get('question_anchor_page')}.",
                    )
                )

        return issues

    def _validate_source_page_roles(
        self, assets: list[dict[str, Any]]
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        for idx, asset in enumerate(assets):
            loc = f"visual_asset_manifest.json.assets[{idx}]"
            role = asset.get("source_page_role")
            if role != "QUESTION_PAGE":
                issues.append(
                    self._issue(
                        "source_page_roles",
                        "INVALID_PAGE_ROLE",
                        loc,
                        f"Unexpected source_page_role {role!r}; expected QUESTION_PAGE.",
                    )
                )
            if asset.get("asset_source_page") != asset.get("question_anchor_page"):
                issues.append(
                    self._issue(
                        "source_page_roles",
                        "PAGE_ROLE_MISMATCH",
                        loc,
                        "asset_source_page must match question_anchor_page for QUESTION_PAGE role.",
                    )
                )
        return issues

    def _validate_component_crop_policy(
        self,
        manifest: dict[str, Any],
        assets: list[dict[str, Any]],
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        for idx, asset in enumerate(assets):
            loc = f"visual_asset_manifest.json.assets[{idx}]"
            boxes = asset.get("source_component_boxes_pdf_points")
            count = asset.get("component_count")
            if not isinstance(boxes, list) or len(boxes) == 0:
                issues.append(
                    self._issue(
                        "component_crop_policy",
                        "INVALID_COMPONENT_CROP",
                        loc,
                        "source_component_boxes_pdf_points must be a non-empty list.",
                    )
                )
            else:
                if len(boxes) != count:
                    issues.append(
                        self._issue(
                            "component_crop_policy",
                            "COMPONENT_COUNT_MISMATCH",
                            loc,
                            f"component_count {count} does not match boxes length {len(boxes)}.",
                        )
                    )
                for b_idx, box in enumerate(boxes):
                    if not (
                        isinstance(box, list)
                        and len(box) == 4
                        and all(isinstance(v, (int, float)) for v in box)
                    ):
                        issues.append(
                            self._issue(
                                "component_crop_policy",
                                "INVALID_COMPONENT_CROP",
                                f"{loc}.boxes[{b_idx}]",
                                f"Box must have 4 numeric coordinates, got {box!r}.",
                            )
                        )
                    else:
                        x0, y0, x1, y1 = box
                        if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                            issues.append(
                                self._issue(
                                    "component_crop_policy",
                                    "INVALID_COMPONENT_CROP",
                                    f"{loc}.boxes[{b_idx}]",
                                    f"Invalid box coordinates: {box!r}.",
                                )
                            )

            if asset.get("answer_leakage_check") != "PASS_DISTINCT_COMPONENT_ONLY":
                issues.append(
                    self._issue(
                        "component_crop_policy",
                        "ANSWER_LEAKAGE_CHECK_FAILED",
                        loc,
                        "answer_leakage_check must be PASS_DISTINCT_COMPONENT_ONLY.",
                    )
                )

            method = asset.get("extraction_method")
            if method not in VALID_EXTRACTION_METHODS:
                issues.append(
                    self._issue(
                        "component_crop_policy",
                        "EXTRACTION_METHOD_MISMATCH",
                        loc,
                        f"Unexpected extraction_method {method!r}.",
                    )
                )
            elif count == 1 and method != "SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI":
                issues.append(
                    self._issue(
                        "component_crop_policy",
                        "EXTRACTION_METHOD_MISMATCH",
                        loc,
                        f"Single-component crop must use SOURCE_VISUAL_COMPONENT_REGION_CROP_RENDER_200_DPI, got {method!r}.",
                    )
                )
            elif count > 1 and method != "SOURCE_VISUAL_COMPONENTS_REGION_CROP_VERTICAL_STITCH_200_DPI":
                issues.append(
                    self._issue(
                        "component_crop_policy",
                        "EXTRACTION_METHOD_MISMATCH",
                        loc,
                        f"Multi-component crop must use SOURCE_VISUAL_COMPONENTS_REGION_CROP_VERTICAL_STITCH_200_DPI, got {method!r}.",
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
    ) -> list[OxyzVisualAssetIssue]:
        issues: list[OxyzVisualAssetIssue] = []
        for idx, row in enumerate(decisions):
            loc = f"visual_review_decisions.json[{idx}]"
            if row.get("rights_status") != "REVIEW_REQUIRED":
                issues.append(
                    self._issue(
                        "release_boundary",
                        "RIGHTS_NOT_REVIEW_REQUIRED",
                        loc,
                        "rights_status must be REVIEW_REQUIRED.",
                    )
                )
            if row.get("promotion_ready") is not False:
                issues.append(
                    self._issue(
                        "release_boundary",
                        "PROMOTION_NOT_BLOCKED",
                        loc,
                        "promotion_ready must be False.",
                    )
                )

        for idx, asset in enumerate(assets):
            loc = f"visual_asset_manifest.json.assets[{idx}]"
            if asset.get("rights_status") != "REVIEW_REQUIRED":
                issues.append(
                    self._issue(
                        "release_boundary",
                        "RIGHTS_NOT_REVIEW_REQUIRED",
                        loc,
                        "Asset rights_status must be REVIEW_REQUIRED.",
                    )
                )
            if asset.get("promotion_eligible") is not False:
                issues.append(
                    self._issue(
                        "release_boundary",
                        "PROMOTION_NOT_BLOCKED",
                        loc,
                        "Asset promotion_eligible must be False.",
                    )
                )

        if stats.get("promotion_eligible_units") != 0:
            issues.append(
                self._issue(
                    "release_boundary",
                    "PROMOTION_COUNT_NONZERO",
                    "visual_asset_stats.json",
                    "promotion_eligible_units must be 0.",
                )
            )
        if stats.get("production_release_eligible") != 0:
            issues.append(
                self._issue(
                    "release_boundary",
                    "PRODUCTION_RELEASE_COUNT_NONZERO",
                    "visual_asset_stats.json",
                    "production_release_eligible must be 0.",
                )
            )
        if stats.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "release_boundary",
                    "DB_IMPORT_NOT_BLOCKED",
                    "visual_asset_stats.json",
                    "database_import_allowed must be false.",
                )
            )
        if stats.get("canonical_snapshot_allowed") is not False:
            issues.append(
                self._issue(
                    "release_boundary",
                    "CANONICAL_SNAPSHOT_NOT_BLOCKED",
                    "visual_asset_stats.json",
                    "canonical_snapshot_allowed must be false.",
                )
            )

        return issues

    def _aggregate_hash(
        self, path: Path, contract: dict[str, Any]
    ) -> str | None:
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
        return hashlib.sha256(
            json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _png_dimensions(data: bytes) -> tuple[int, int]:
        if (
            len(data) < 24
            or data[:8] != PNG_SIGNATURE
            or data[12:16] != b"IHDR"
        ):
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
        return True

    def _check_required_files(
        self, path: Path, issues: list[OxyzVisualAssetIssue]
    ) -> None:
        for name in REQUIRED_FILES:
            if not (path / name).is_file():
                issues.append(
                    self._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        name,
                        f"Required file {name} is missing.",
                    )
                )

    def _load_list(
        self, path: Path, issues: list[OxyzVisualAssetIssue]
    ) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
                return payload
            issues.append(
                self._issue(
                    "required_files",
                    "INVALID_JSON_STRUCTURE",
                    path.name,
                    f"Expected list of objects in {path.name}.",
                )
            )
            return []
        except (OSError, json.JSONDecodeError) as e:
            issues.append(
                self._issue(
                    "required_files",
                    "JSON_LOAD_ERROR",
                    path.name,
                    f"Error reading {path.name}: {e}",
                )
            )
            return []

    def _load_object(
        self, path: Path, issues: list[OxyzVisualAssetIssue]
    ) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
            issues.append(
                self._issue(
                    "required_files",
                    "INVALID_JSON_STRUCTURE",
                    path.name,
                    f"Expected JSON object in {path.name}.",
                )
            )
            return {}
        except (OSError, json.JSONDecodeError) as e:
            issues.append(
                self._issue(
                    "required_files",
                    "JSON_LOAD_ERROR",
                    path.name,
                    f"Error reading {path.name}: {e}",
                )
            )
            return {}

    @staticmethod
    def _int_value(val: Any, default: int = -1) -> int:
        if isinstance(val, int) and not isinstance(val, bool):
            return val
        return default

    @staticmethod
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> OxyzVisualAssetIssue:
        return OxyzVisualAssetIssue(
            check=check, code=code, location=location, message=message
        )
