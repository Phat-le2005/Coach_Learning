from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "pinned_depth_supplement_v0_2"
)

EXPECTED_PINNED_DEPTH_SUPPLEMENT_AGGREGATE_SHA256 = (
    "682041d87f2a22f2ddbe11c80b67e91fc5a4e096586e0c8bf03622dd86d0a5ca"
)
EXPECTED_BASE_REPO_COMMIT = "446abb9c2fde1fd9b065e0d8b42240c7e738da1f"

SEMANTIC_FILES_ORDER = (
    "source_registry.json",
    "verified_units.json",
    "coverage_after_047.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES_ORDER,
    "data_contract.json",
    "README.md",
)

EXPECTED_SEMANTIC_HASHES = {
    "source_registry.json": (
        "f8fe7c77319161819f101db6a15d229e51a97fae690ca9485b867e68aa5e017b"
    ),
    "verified_units.json": (
        "196f698ed6b9de6b06ac291d70d599ed8a305294f3d2c13c204eeaa0d9501564"
    ),
    "coverage_after_047.json": (
        "f64b9d0b96119a977aec6ec7b90cca6a35f2666cefc1cfe37ea3340f0c494e89"
    ),
}

EXPECTED_SOURCES = {
    "SRC_TRIAL_2026_05": "c5156c422b7cc2e390369831e32bf02f43dfbfbc6d2a1438a92e3d74ae2614a4",
    "SRC_TRIAL_2026_10": "5029733489302ddaa04ae4595a9e622e86030a547bdc989d17a0dfb8d968d6fa",
    "SRC_TRIAL_2026_11": "769c6f69a4a6a643ae1bf144840a52e64bd00b5fcedef4565d805a84aeeea1b7",
    "SRC_TRIAL_2026_13": "6ab24e60dd44ed7bff543eb4c5b60a96e6650242c5709a1aca641b9ea59be396",
    "SRC_TRIAL_2026_14": "7330415051643b8ded8b26e29f1cb4cfe3dc85fc025e3ed8a5294205b60e9e8d",
    "SRC_PROVINCIAL_TRIAL_2025_COLLECTION": "d3f2158ee028431e01b2f30f7e446d66d75e364c27d49c53f3e09c193325b7e0",
}


@dataclass(frozen=True, order=True)
class PinnedDepthSupplementIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True)
class PinnedDepthSupplementReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str
    aggregate_semantic_sha256: str
    stats_practice_units_after: int
    stats_dominant_source_share: float
    stats_diversity_gate: str
    prob_practice_units_after: int
    prob_dominant_source_share: float
    prob_diversity_gate: str
    prob_units_needed_to_pass: int
    point_plane_evidence_count: int
    line_plane_evidence_count: int
    rights_status: str
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[PinnedDepthSupplementIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS" and len(self.errors) == 0

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["is_valid"] = self.is_valid
        return result


class PinnedDepthSupplementValidator:
    """Validates DATA-MATH12-047 11 pinned real-source practice/evidence units."""

    def validate(
        self,
        dataset_path: Path | str | None = None,
    ) -> PinnedDepthSupplementReport:
        path = (
            Path(dataset_path)
            if dataset_path is not None
            else DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH
        )

        initial: list[PinnedDepthSupplementIssue] = []
        self._check_required_files(path, initial)

        contract = self._load_object(path / "data_contract.json", initial)
        source_reg = self._load_object(path / "source_registry.json", initial)
        units_data = self._load_object(path / "verified_units.json", initial)
        cov_data = self._load_object(path / "coverage_after_047.json", initial)

        checks_to_errors: dict[str, list[PinnedDepthSupplementIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "source_registry_integrity": self._validate_source_registry(
                source_reg
            ),
            "verified_units_integrity": self._validate_verified_units(
                units_data
            ),
            "coverage_effects_integrity": self._validate_coverage_effects(
                cov_data
            ),
            "critical_boundaries": self._validate_critical_boundaries(contract),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[PinnedDepthSupplementIssue] = []
        if aggregate != EXPECTED_PINNED_DEPTH_SUPPLEMENT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_PINNED_DEPTH_SUPPLEMENT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_PINNED_DEPTH_SUPPLEMENT_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-047 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        errors = tuple(
            sorted(
                issue for issues in checks_to_errors.values() for issue in issues
            )
        )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }

        stats_cov = cov_data.get("statistics", {})
        oxyz_cov = cov_data.get("oxyz", {})
        prob_cov = cov_data.get("probability", {})
        units_list = units_data.get("units", [])

        counts = {
            "verified_units_count": len(units_list),
            "statistics_units_count": sum(
                1 for u in units_list if u.get("scope") == "GROUPED_DATA_STATISTICS"
            ),
            "oxyz_units_count": sum(
                1 for u in units_list if u.get("scope") == "OXYZ_CHAPTER"
            ),
            "probability_units_count": sum(
                1 for u in units_list if u.get("scope") == "PROBABILITY_CHAPTER"
            ),
        }

        return PinnedDepthSupplementReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit", ""),
            aggregate_semantic_sha256=aggregate,
            stats_practice_units_after=stats_cov.get("practice_units_after", 0),
            stats_dominant_source_share=float(
                stats_cov.get("dominant_source_share_after", 0.0)
            ),
            stats_diversity_gate=str(
                stats_cov.get("source_diversity_target_70pct", "")
            ),
            prob_practice_units_after=prob_cov.get("practice_units_after", 0),
            prob_dominant_source_share=float(
                prob_cov.get("dominant_source_share_after", 0.0)
            ),
            prob_diversity_gate=str(
                prob_cov.get("dominant_source_target_70pct", "")
            ),
            prob_units_needed_to_pass=int(
                prob_cov.get("additional_non_dominant_unit_needed_to_pass_70pct", 0)
            ),
            point_plane_evidence_count=int(
                oxyz_cov.get("point_plane_evidence_count_after", 0)
            ),
            line_plane_evidence_count=int(
                oxyz_cov.get("line_plane_intersection_evidence_count_after", 0)
            ),
            rights_status=contract.get("rights_status", "UNKNOWN"),
            canonical_write_allowed=bool(
                contract.get("canonical_write_allowed", True)
            ),
            database_import_allowed=bool(
                contract.get("database_import_allowed", True)
            ),
            production_release_allowed=bool(
                contract.get("production_release_allowed", True)
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[PinnedDepthSupplementIssue]
    ) -> None:
        for file_name in REQUIRED_FILES:
            target = path / file_name
            if not target.is_file():
                issues.append(
                    self._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        file_name,
                        f"Missing required file: {file_name}",
                    )
                )

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[PinnedDepthSupplementIssue]:
        issues: list[PinnedDepthSupplementIssue] = []
        if path.is_dir():
            for p in path.rglob("*.pdf"):
                issues.append(
                    self._issue(
                        "no_pdf_binaries",
                        "FORBIDDEN_PDF_BINARY",
                        p.name,
                        f"PDF binaries must not be committed: {p.name}",
                    )
                )
        return issues

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[PinnedDepthSupplementIssue]:
        issues: list[PinnedDepthSupplementIssue] = []
        if contract.get("dataset_code") != "DATA-MATH12-047":
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "DATASET_CODE_MISMATCH",
                    "data_contract.json",
                    f"Expected dataset_code DATA-MATH12-047, got {contract.get('dataset_code')!r}.",
                )
            )

        sem_hashes = contract.get("semantic_sha256", {})
        for file_name in SEMANTIC_FILES_ORDER:
            expected_hash = EXPECTED_SEMANTIC_HASHES.get(file_name)
            contract_hash = sem_hashes.get(file_name)
            if contract_hash != expected_hash:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "CONTRACT_FILE_HASH_MISMATCH",
                        file_name,
                        f"Contract hash mismatch for {file_name}: expected {expected_hash}, got {contract_hash}.",
                    )
                )
            file_path = path / file_name
            if file_path.is_file():
                actual_hash = self._semantic_hash(file_path)
                if actual_hash != expected_hash:
                    issues.append(
                        self._issue(
                            "curated_hash_contract",
                            "FILE_HASH_MISMATCH",
                            file_name,
                            f"File hash mismatch for {file_name}: expected {expected_hash}, got {actual_hash}.",
                        )
                    )
        return issues

    def _validate_base_repo_commit(
        self, contract: dict[str, Any]
    ) -> list[PinnedDepthSupplementIssue]:
        issues: list[PinnedDepthSupplementIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )
        return issues

    def _validate_source_registry(
        self, source_reg: dict[str, Any]
    ) -> list[PinnedDepthSupplementIssue]:
        issues: list[PinnedDepthSupplementIssue] = []
        sources = source_reg.get("sources", [])
        if len(sources) != 6:
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "SOURCES_COUNT_MISMATCH",
                    "source_registry.json",
                    f"Expected exactly 6 sources, got {len(sources)}.",
                )
            )

        for src in sources:
            code = src.get("source_code")
            expected_sha = EXPECTED_SOURCES.get(code)
            if expected_sha is None:
                issues.append(
                    self._issue(
                        "source_registry_integrity",
                        "UNKNOWN_SOURCE",
                        "source_registry.json",
                        f"Unexpected source code {code}.",
                    )
                )
            elif src.get("sha256") != expected_sha:
                issues.append(
                    self._issue(
                        "source_registry_integrity",
                        "SOURCE_SHA_MISMATCH",
                        str(code),
                        f"Source {code} expected sha256 {expected_sha}, got {src.get('sha256')}.",
                    )
                )

        policy = source_reg.get("policy", {})
        if policy.get("all_source_binaries_sha256_pinned") is not True:
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "BINARIES_NOT_PINNED",
                    "source_registry.json",
                    "all_source_binaries_sha256_pinned must be true.",
                )
            )
        if policy.get("synthetic_questions") is not False:
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "SYNTHETIC_NOT_BLOCKED",
                    "source_registry.json",
                    "synthetic_questions must be false.",
                )
            )
        if policy.get("real_sources_only") is not True:
            issues.append(
                self._issue(
                    "source_registry_integrity",
                    "REAL_SOURCES_ONLY_NOT_TRUE",
                    "source_registry.json",
                    "real_sources_only must be true.",
                )
            )
        return issues

    def _validate_verified_units(
        self, units_data: dict[str, Any]
    ) -> list[PinnedDepthSupplementIssue]:
        issues: list[PinnedDepthSupplementIssue] = []
        units = units_data.get("units", [])
        if len(units) != 11:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "UNITS_COUNT_MISMATCH",
                    "verified_units.json",
                    f"Expected exactly 11 verified units, got {len(units)}.",
                )
            )
            return issues

        unit_by_id = {u.get("unit_id"): u for u in units}

        # 1. Statistics units (6 units)
        # Unit 1: M12_D047_STATS_RANGE_TRIAL05_001
        u1 = unit_by_id.get("M12_D047_STATS_RANGE_TRIAL05_001")
        if not u1:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_STATS_RANGE_TRIAL05_001.",
                )
            )
        else:
            if u1.get("correct_answer") != "D" or u1.get("correct_answer_value") != 1.5:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_STATS_RANGE_TRIAL05_001",
                        "Answer must be D / 1.5.",
                    )
                )

        # Unit 2: M12_D047_STATS_IQR_GROUP_TRIAL05_001
        u2 = unit_by_id.get("M12_D047_STATS_IQR_GROUP_TRIAL05_001")
        if not u2:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_STATS_IQR_GROUP_TRIAL05_001.",
                )
            )
        else:
            if u2.get("answer_pattern") != [True, True, False, True]:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "PATTERN_MISMATCH",
                        "M12_D047_STATS_IQR_GROUP_TRIAL05_001",
                        "answer_pattern must be [True, True, False, True].",
                    )
                )
            if u2.get("atomic_group_policy") is not True:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ATOMIC_GROUP_SPLIT",
                        "M12_D047_STATS_IQR_GROUP_TRIAL05_001",
                        "atomic_group_policy must be true.",
                    )
                )

        # Unit 3: M12_D047_STATS_IQR_TRIAL10_001
        u3 = unit_by_id.get("M12_D047_STATS_IQR_TRIAL10_001")
        if not u3:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_STATS_IQR_TRIAL10_001.",
                )
            )
        else:
            if u3.get("correct_answer") != "B" or u3.get("correct_answer_value") != 25.01:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_STATS_IQR_TRIAL10_001",
                        "Answer must be B / 25.01.",
                    )
                )

        # Unit 4: M12_D047_STATS_RANGE_TRIAL14_001
        u4 = unit_by_id.get("M12_D047_STATS_RANGE_TRIAL14_001")
        if not u4:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_STATS_RANGE_TRIAL14_001.",
                )
            )
        else:
            if u4.get("correct_answer") != "A" or u4.get("correct_answer_value") != 10:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_STATS_RANGE_TRIAL14_001",
                        "Answer must be A / 10.",
                    )
                )

        # Unit 5: M12_D047_STATS_VAR_SD_GROUP_TRIAL14_001
        u5 = unit_by_id.get("M12_D047_STATS_VAR_SD_GROUP_TRIAL14_001")
        if not u5:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_STATS_VAR_SD_GROUP_TRIAL14_001.",
                )
            )
        else:
            if u5.get("answer_pattern") != [True, True, False, False]:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "PATTERN_MISMATCH",
                        "M12_D047_STATS_VAR_SD_GROUP_TRIAL14_001",
                        "answer_pattern must be [True, True, False, False].",
                    )
                )
            if u5.get("atomic_group_policy") is not True:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ATOMIC_GROUP_SPLIT",
                        "M12_D047_STATS_VAR_SD_GROUP_TRIAL14_001",
                        "atomic_group_policy must be true.",
                    )
                )
            sec = u5.get("secondary_problem_type_evidence", [])
            if "CALCULATE_GROUPED_STANDARD_DEVIATION" not in sec:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "SECONDARY_EVIDENCE_MISMATCH",
                        "M12_D047_STATS_VAR_SD_GROUP_TRIAL14_001",
                        "secondary evidence must contain CALCULATE_GROUPED_STANDARD_DEVIATION.",
                    )
                )

        # Unit 6: M12_D047_STATS_IQR_TRIAL14_002
        u6 = unit_by_id.get("M12_D047_STATS_IQR_TRIAL14_002")
        if not u6:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_STATS_IQR_TRIAL14_002.",
                )
            )
        else:
            if u6.get("correct_answer") != "4.8":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_STATS_IQR_TRIAL14_002",
                        "correct_answer must be '4.8'.",
                    )
                )

        # 2. Oxyz units (3 units: 2 standalone + 1 atomic group)
        # Unit 7: M12_D047_OXYZ_POINT_PLANE_TRIAL11_001
        u7 = unit_by_id.get("M12_D047_OXYZ_POINT_PLANE_TRIAL11_001")
        if not u7:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_OXYZ_POINT_PLANE_TRIAL11_001.",
                )
            )
        else:
            if u7.get("correct_answer") != "B" or u7.get("correct_answer_value") != 6:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_OXYZ_POINT_PLANE_TRIAL11_001",
                        "Answer must be B / 6.",
                    )
                )

        # Unit 8: M12_D047_OXYZ_LINE_PLANE_TRIAL05_001
        u8 = unit_by_id.get("M12_D047_OXYZ_LINE_PLANE_TRIAL05_001")
        if not u8:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_OXYZ_LINE_PLANE_TRIAL05_001.",
                )
            )
        else:
            if u8.get("correct_answer") != "A":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_OXYZ_LINE_PLANE_TRIAL05_001",
                        "correct_answer must be 'A'.",
                    )
                )

        # Unit 9: M12_D047_OXYZ_WALL_GROUP_TRIAL13_001
        u9 = unit_by_id.get("M12_D047_OXYZ_WALL_GROUP_TRIAL13_001")
        if not u9:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_OXYZ_WALL_GROUP_TRIAL13_001.",
                )
            )
        else:
            if u9.get("answer_pattern") != [True, False, True, False]:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "PATTERN_MISMATCH",
                        "M12_D047_OXYZ_WALL_GROUP_TRIAL13_001",
                        "answer_pattern must be [True, False, True, False].",
                    )
                )
            if u9.get("atomic_group_policy") is not True:
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ATOMIC_GROUP_SPLIT",
                        "M12_D047_OXYZ_WALL_GROUP_TRIAL13_001",
                        "atomic_group_policy must be true.",
                    )
                )
            child_ev = u9.get("child_problem_type_evidence", {})
            if (
                child_ev.get("a") != "POINT_PLANE_OR_PLANE_DISTANCE"
                or child_ev.get("c") != "LINE_PLANE_INTERSECTION"
            ):
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "CHILD_EVIDENCE_MISMATCH",
                        "M12_D047_OXYZ_WALL_GROUP_TRIAL13_001",
                        "Child evidence must map a -> POINT_PLANE and c -> LINE_PLANE_INTERSECTION.",
                    )
                )

        # 3. Probability units (2 units)
        # Unit 10: M12_D047_PROB_SEQUENTIAL_DRAW_001
        u10 = unit_by_id.get("M12_D047_PROB_SEQUENTIAL_DRAW_001")
        if not u10:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_PROB_SEQUENTIAL_DRAW_001.",
                )
            )
        else:
            if u10.get("correct_answer") != "0.24":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_PROB_SEQUENTIAL_DRAW_001",
                        "correct_answer must be '0.24'.",
                    )
                )
            if u10.get("problem_type_code") != "TREE_OR_TOTAL_PROBABILITY":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "PROBLEM_TYPE_MISMATCH",
                        "M12_D047_PROB_SEQUENTIAL_DRAW_001",
                        "problem_type_code must be TREE_OR_TOTAL_PROBABILITY.",
                    )
                )

        # Unit 11: M12_D047_PROB_BOX_CONDITIONAL_001
        u11 = unit_by_id.get("M12_D047_PROB_BOX_CONDITIONAL_001")
        if not u11:
            issues.append(
                self._issue(
                    "verified_units_integrity",
                    "MISSING_UNIT",
                    "verified_units.json",
                    "Missing M12_D047_PROB_BOX_CONDITIONAL_001.",
                )
            )
        else:
            if u11.get("correct_answer") != "0.45":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "ANSWER_MISMATCH",
                        "M12_D047_PROB_BOX_CONDITIONAL_001",
                        "correct_answer must be '0.45'.",
                    )
                )
            if u11.get("problem_type_code") != "TREE_OR_TOTAL_PROBABILITY":
                issues.append(
                    self._issue(
                        "verified_units_integrity",
                        "PROBLEM_TYPE_MISMATCH",
                        "M12_D047_PROB_BOX_CONDITIONAL_001",
                        "problem_type_code must be TREE_OR_TOTAL_PROBABILITY.",
                    )
                )
            sec = u11.get("secondary_problem_type_evidence", [])
            for pt in ("CONDITIONAL_PROBABILITY_DIRECT", "TOTAL_PROBABILITY", "BAYES_POSTERIOR"):
                if pt not in sec:
                    issues.append(
                        self._issue(
                            "verified_units_integrity",
                            "SECONDARY_EVIDENCE_MISMATCH",
                            "M12_D047_PROB_BOX_CONDITIONAL_001",
                            f"Missing secondary evidence {pt}.",
                        )
                    )

        return issues

    def _validate_coverage_effects(
        self, cov_data: dict[str, Any]
    ) -> list[PinnedDepthSupplementIssue]:
        issues: list[PinnedDepthSupplementIssue] = []
        if cov_data.get("new_pinned_units") != 11:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "NEW_UNITS_COUNT_MISMATCH",
                    "coverage_after_047.json",
                    "new_pinned_units must be 11.",
                )
            )

        # Statistics checks
        stats = cov_data.get("statistics", {})
        if stats.get("practice_units_after") != 44:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "STATS_PRACTICE_COUNT_MISMATCH",
                    "coverage_after_047.json",
                    f"statistics practice_units_after must be 44, got {stats.get('practice_units_after')}.",
                )
            )
        if stats.get("source_families_after") != 5:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "STATS_SOURCE_FAMILIES_MISMATCH",
                    "coverage_after_047.json",
                    "statistics source_families_after must be 5.",
                )
            )
        expected_dominant_share = 30 / 44
        actual_stats_share = float(stats.get("dominant_source_share_after", 0.0))
        if abs(actual_stats_share - expected_dominant_share) > 1e-6:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "STATS_DOMINANT_SHARE_MISMATCH",
                    "coverage_after_047.json",
                    f"statistics dominant_source_share_after must be 30/44 (~0.68181818), got {actual_stats_share}.",
                )
            )
        if stats.get("source_diversity_target_70pct") != "PASS":
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "STATS_DIVERSITY_GATE_MISMATCH",
                    "coverage_after_047.json",
                    "statistics source_diversity_target_70pct must be PASS.",
                )
            )

        # Oxyz checks
        oxyz = cov_data.get("oxyz", {})
        if oxyz.get("point_plane_evidence_count_after") != 4:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "POINT_PLANE_COUNT_MISMATCH",
                    "coverage_after_047.json",
                    "point_plane_evidence_count_after must be 4.",
                )
            )
        if oxyz.get("line_plane_intersection_evidence_count_after") != 3:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "LINE_PLANE_COUNT_MISMATCH",
                    "coverage_after_047.json",
                    "line_plane_intersection_evidence_count_after must be 3.",
                )
            )

        # Probability checks
        prob = cov_data.get("probability", {})
        if prob.get("practice_units_after") != 24:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROB_PRACTICE_COUNT_MISMATCH",
                    "coverage_after_047.json",
                    f"probability practice_units_after must be 24, got {prob.get('practice_units_after')}.",
                )
            )
        primary_dist = prob.get("primary_distribution_after", {})
        if primary_dist.get("TREE_OR_TOTAL_PROBABILITY") != 5:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROB_TREE_COUNT_MISMATCH",
                    "coverage_after_047.json",
                    "probability primary TREE_OR_TOTAL_PROBABILITY must be 5.",
                )
            )
        if prob.get("dominant_source_count") != 17:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROB_DOMINANT_COUNT_MISMATCH",
                    "coverage_after_047.json",
                    "probability dominant_source_count must be 17.",
                )
            )
        expected_prob_share = 17 / 24
        actual_prob_share = float(prob.get("dominant_source_share_after", 0.0))
        if abs(actual_prob_share - expected_prob_share) > 1e-6:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROB_DOMINANT_SHARE_MISMATCH",
                    "coverage_after_047.json",
                    f"probability dominant_source_share_after must be 17/24 (~0.70833333), got {actual_prob_share}.",
                )
            )
        # 70% diversity gate must still FAIL
        prob_gate = prob.get("dominant_source_target_70pct", "")
        if "FAIL" not in prob_gate:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROB_DIVERSITY_FALSE_PASS",
                    "coverage_after_047.json",
                    "probability dominant_source_target_70pct must FAIL because 70.83% > 70%.",
                )
            )
        if prob.get("additional_non_dominant_unit_needed_to_pass_70pct") != 1:
            issues.append(
                self._issue(
                    "coverage_effects_integrity",
                    "PROB_DELTA_MISMATCH",
                    "coverage_after_047.json",
                    "additional_non_dominant_unit_needed_to_pass_70pct must be 1.",
                )
            )

        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any]
    ) -> list[PinnedDepthSupplementIssue]:
        issues: list[PinnedDepthSupplementIssue] = []
        if contract.get("canonical_write_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_WRITE_NOT_BLOCKED",
                    "data_contract.json",
                    "canonical_write_allowed must be false.",
                )
            )
        if contract.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "data_contract.json",
                    "database_import_allowed must be false.",
                )
            )
        if contract.get("production_release_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "PRODUCTION_RELEASE_NOT_BLOCKED",
                    "data_contract.json",
                    "production_release_allowed must be false.",
                )
            )
        if contract.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "RIGHTS_STATUS_NOT_REVIEW_REQUIRED",
                    "data_contract.json",
                    "rights_status must be REVIEW_REQUIRED.",
                )
            )
        return issues

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _semantic_hash(file_path: Path) -> str:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        canonical_bytes = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()

    def _aggregate_hash(self, path: Path, contract: dict[str, Any]) -> str:
        order = contract.get("semantic_files_order", list(SEMANTIC_FILES_ORDER))
        digest = hashlib.sha256()
        for name in order:
            file_path = path / str(name)
            file_hash = (
                self._semantic_hash(file_path) if file_path.is_file() else ""
            )
            digest.update(str(name).encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_hash.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _load_object(
        self, path: Path, issues: list[PinnedDepthSupplementIssue]
    ) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            val = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(val, dict):
                return val
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
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> PinnedDepthSupplementIssue:
        return PinnedDepthSupplementIssue(
            check=check, code=code, location=location, message=message
        )
