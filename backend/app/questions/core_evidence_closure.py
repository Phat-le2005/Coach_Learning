from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORE_EVIDENCE_CLOSURE_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "core_evidence_closure_v0_1"
)

EXPECTED_CORE_EVIDENCE_CLOSURE_AGGREGATE_SHA256 = (
    "0a068fec0bb04f2f3ef86b806a9f14c4eef41366b8d43c4201cb8b45939b1c9a"
)
EXPECTED_BASE_REPO_COMMIT = "453e3817c3d77098ad5d3171ed9b466391ac223b"
EXPECTED_BASE_AUDIT_AGGREGATE_SHA256 = (
    "ea64fd6dd257d80f4d19477a7708f21229643d87ad7793b22504bb680c7a22e5"
)
EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256 = (
    "2f4c17a62008895e4d003e22f872f5710dd265d13fe6ee38c2120040bcc4fdde"
)

EXPECTED_TREE_ASSET_SHA256 = (
    "755211c4d89f251f82c04961a058942b85825d2270c3b8ad4d010d596114b040"
)
EXPECTED_TREE_ASSET_WIDTH = 460
EXPECTED_TREE_ASSET_HEIGHT = 380

SEMANTIC_FILES_ORDER = (
    "evidence_manifest.json",
    "grouped_statistics_interpretation_evidence.json",
    "probability_tree_evidence.json",
    "derived_gap_reclassification.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES_ORDER,
    "data_contract.json",
    "README.md",
    "assets/M12_PROB_TREE_OFFICIAL_2025_C3.png",
)

EXPECTED_SEMANTIC_HASHES = {
    "evidence_manifest.json": (
        "99bcd70ab44df689085415a7f04c67da896e21372280617735ac69db859e4246"
    ),
    "grouped_statistics_interpretation_evidence.json": (
        "ddda2e1c2d8243580a67e4d110009036ec7328b65d7581fdf07dc4e6fa8881a9"
    ),
    "probability_tree_evidence.json": (
        "01de9a566132e1b7055af01f8e60ad3758bbb3f930811c6ed6fbb8f7b44e2d10"
    ),
    "derived_gap_reclassification.json": (
        "b192f40354771688006c71566bb6d5b8441facef3782d9c6cc236f6306f5684c"
    ),
}

EXPECTED_INVARIANTS = {
    "source_backed_evidence_units_added": 2,
    "synthetic_questions_added": 0,
    "official_requirements_before_total": 20,
    "official_requirements_before_covered": 18,
    "official_requirements_before_partial": 2,
    "official_requirements_after_total": 20,
    "official_requirements_after_covered": 20,
    "official_requirements_after_partial": 0,
    "rights_status": "REVIEW_REQUIRED",
    "production_release_eligible": 0,
    "database_import_allowed": False,
    "canonical_write_allowed": False,
    "production_release_allowed": False,
}


@dataclass(frozen=True, slots=True, order=True)
class CoreEvidenceClosureIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class CoreEvidenceClosureReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str | None
    base_audit_aggregate_sha256: str | None
    base_alignment_aggregate_sha256: str | None
    aggregate_semantic_sha256: str | None
    tree_asset_sha256: str | None
    tree_asset_dimensions: tuple[int, int] | None
    official_requirements_covered_after: int
    official_requirements_partial_after: int
    rights_status: str | None
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_eligible: int
    errors: tuple[CoreEvidenceClosureIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "base_repo_commit": self.base_repo_commit,
            "base_audit_aggregate_sha256": self.base_audit_aggregate_sha256,
            "base_alignment_aggregate_sha256": self.base_alignment_aggregate_sha256,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "tree_asset_sha256": self.tree_asset_sha256,
            "tree_asset_dimensions": self.tree_asset_dimensions,
            "official_requirements_covered_after": self.official_requirements_covered_after,
            "official_requirements_partial_after": self.official_requirements_partial_after,
            "rights_status": self.rights_status,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_eligible": self.production_release_eligible,
            "errors": [asdict(issue) for issue in self.errors],
        }


class CoreEvidenceClosureValidator:
    """Validate DATA-MATH12-035 GDPT 2018 Grade 12 Math core evidence closure candidate."""

    def validate(
        self,
        evidence_path: Path = DEFAULT_CORE_EVIDENCE_CLOSURE_PATH,
    ) -> CoreEvidenceClosureReport:
        path = evidence_path.resolve()
        initial: list[CoreEvidenceClosureIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        manifest = self._load_object(path / "evidence_manifest.json", initial)
        stats = self._load_object(
            path / "grouped_statistics_interpretation_evidence.json", initial
        )
        prob = self._load_object(
            path / "probability_tree_evidence.json", initial
        )
        gap = self._load_object(
            path / "derived_gap_reclassification.json", initial
        )

        tree_asset_file = path / "assets" / "M12_PROB_TREE_OFFICIAL_2025_C3.png"
        actual_tree_sha256: str | None = None
        actual_dimensions: tuple[int, int] | None = None
        if tree_asset_file.is_file():
            raw_bytes = tree_asset_file.read_bytes()
            actual_tree_sha256 = hashlib.sha256(raw_bytes).hexdigest()
            actual_dimensions = self._read_png_dimensions(raw_bytes)

        checks_to_errors: dict[str, list[CoreEvidenceClosureIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_bindings": self._validate_base_bindings(
                contract, manifest
            ),
            "tree_asset_integrity": self._validate_tree_asset(
                tree_asset_file, actual_tree_sha256, actual_dimensions, prob
            ),
            "grouped_statistics_evidence": self._validate_grouped_statistics(
                stats
            ),
            "probability_tree_evidence": self._validate_probability_tree(
                prob
            ),
            "gap_reclassification": self._validate_gap_reclassification(
                gap
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                contract, manifest
            ),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[CoreEvidenceClosureIssue] = []
        if aggregate != EXPECTED_CORE_EVIDENCE_CLOSURE_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_CORE_EVIDENCE_CLOSURE_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_CORE_EVIDENCE_CLOSURE_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-035 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        # Check exact invariants
        invariants_errors: list[CoreEvidenceClosureIssue] = []
        req_before = manifest.get("official_requirements_before", {})
        req_after = manifest.get("official_requirements_after_overlay", {})
        actual_invariants = {
            "source_backed_evidence_units_added": manifest.get(
                "source_backed_evidence_units_added"
            ),
            "synthetic_questions_added": manifest.get(
                "synthetic_questions_added"
            ),
            "official_requirements_before_total": req_before.get("total"),
            "official_requirements_before_covered": req_before.get("covered"),
            "official_requirements_before_partial": req_before.get("partial"),
            "official_requirements_after_total": req_after.get("total"),
            "official_requirements_after_covered": req_after.get("covered"),
            "official_requirements_after_partial": req_after.get("partial"),
            "rights_status": manifest.get("rights_status"),
            "production_release_eligible": manifest.get(
                "production_release_eligible"
            ),
            "database_import_allowed": contract.get("database_import_allowed"),
            "canonical_write_allowed": contract.get("canonical_write_allowed"),
            "production_release_allowed": contract.get(
                "production_release_allowed"
            ),
        }
        if actual_invariants != EXPECTED_INVARIANTS:
            invariants_errors.append(
                self._issue(
                    "exact_invariants",
                    "INVARIANT_COUNT_MISMATCH",
                    "evidence_manifest.json",
                    f"Invariants mismatch: expected {EXPECTED_INVARIANTS}, got {actual_invariants}.",
                )
            )
        checks_to_errors["exact_invariants"] = invariants_errors

        errors = tuple(
            sorted(
                issue for issues in checks_to_errors.values() for issue in issues
            )
        )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }

        counts = {
            "source_backed_evidence_units_added": manifest.get(
                "source_backed_evidence_units_added", 0
            ),
            "synthetic_questions_added": manifest.get(
                "synthetic_questions_added", 0
            ),
            "official_requirements_covered": req_after.get("covered", 0),
            "official_requirements_partial": req_after.get("partial", 0),
            "official_requirements_total": req_after.get("total", 0),
        }

        return CoreEvidenceClosureReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            base_audit_aggregate_sha256=manifest.get(
                "base_audit_aggregate_sha256"
            ),
            base_alignment_aggregate_sha256=manifest.get(
                "base_alignment_aggregate_sha256"
            ),
            aggregate_semantic_sha256=aggregate,
            tree_asset_sha256=actual_tree_sha256,
            tree_asset_dimensions=actual_dimensions,
            official_requirements_covered_after=req_after.get("covered", 0),
            official_requirements_partial_after=req_after.get("partial", 0),
            rights_status=manifest.get("rights_status"),
            canonical_write_allowed=bool(
                contract.get("canonical_write_allowed", True)
            ),
            database_import_allowed=bool(
                contract.get("database_import_allowed", True)
            ),
            production_release_eligible=int(
                manifest.get("production_release_eligible", 1)
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[CoreEvidenceClosureIssue]
    ) -> None:
        for file_name in REQUIRED_FILES:
            target = path / file_name
            if not target.is_file():
                issues.append(
                    self._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        file_name,
                        f"Missing required file: {file_name}.",
                    )
                )

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
        for file in path.rglob("*"):
            if file.is_file() and file.suffix.lower() == ".pdf":
                issues.append(
                    self._issue(
                        "no_pdf_binaries",
                        "PDF_BINARY_IN_DATASET",
                        file.name,
                        f"PDF binaries are prohibited in dataset: {file.name}.",
                    )
                )
        return issues

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
        hashes = contract.get("semantic_sha256", {})
        if not isinstance(hashes, dict):
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "MALFORMED_HASH_TABLE",
                    "data_contract.json",
                    "semantic_sha256 must be a dict.",
                )
            )
            return issues

        for file_name, expected_hash in EXPECTED_SEMANTIC_HASHES.items():
            declared = hashes.get(file_name)
            if declared != expected_hash:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "CONTRACT_HASH_MISMATCH",
                        f"data_contract.json[{file_name}]",
                        f"Contract hash mismatch for {file_name}: expected {expected_hash}, got {declared}.",
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

    def _validate_base_bindings(
        self, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_bindings",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )
        if manifest.get("base_audit_aggregate_sha256") != EXPECTED_BASE_AUDIT_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "base_bindings",
                    "BASE_AUDIT_AGGREGATE_MISMATCH",
                    "evidence_manifest.json",
                    f"Expected base_audit_aggregate_sha256 {EXPECTED_BASE_AUDIT_AGGREGATE_SHA256}, got {manifest.get('base_audit_aggregate_sha256')!r}.",
                )
            )
        if manifest.get("base_alignment_aggregate_sha256") != EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "base_bindings",
                    "BASE_ALIGNMENT_AGGREGATE_MISMATCH",
                    "evidence_manifest.json",
                    f"Expected base_alignment_aggregate_sha256 {EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256}, got {manifest.get('base_alignment_aggregate_sha256')!r}.",
                )
            )
        return issues

    def _validate_tree_asset(
        self,
        asset_file: Path,
        actual_sha256: str | None,
        dimensions: tuple[int, int] | None,
        prob: dict[str, Any],
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
        if not asset_file.is_file():
            issues.append(
                self._issue(
                    "tree_asset_integrity",
                    "MISSING_TREE_ASSET_PNG",
                    asset_file.name,
                    f"Tree asset file missing: {asset_file.name}.",
                )
            )
            return issues

        if actual_sha256 != EXPECTED_TREE_ASSET_SHA256:
            issues.append(
                self._issue(
                    "tree_asset_integrity",
                    "TREE_ASSET_SHA256_MISMATCH",
                    asset_file.name,
                    f"Tree asset sha256 expected {EXPECTED_TREE_ASSET_SHA256}, got {actual_sha256}.",
                )
            )

        declared_tree = prob.get("tree_asset", {})
        if declared_tree.get("sha256") != EXPECTED_TREE_ASSET_SHA256:
            issues.append(
                self._issue(
                    "tree_asset_integrity",
                    "DECLARED_TREE_SHA256_MISMATCH",
                    "probability_tree_evidence.json[tree_asset]",
                    f"Declared sha256 expected {EXPECTED_TREE_ASSET_SHA256}, got {declared_tree.get('sha256')}.",
                )
            )

        if dimensions != (EXPECTED_TREE_ASSET_WIDTH, EXPECTED_TREE_ASSET_HEIGHT):
            issues.append(
                self._issue(
                    "tree_asset_integrity",
                    "TREE_ASSET_DIMENSIONS_MISMATCH",
                    asset_file.name,
                    f"Tree asset dimensions expected {EXPECTED_TREE_ASSET_WIDTH}x{EXPECTED_TREE_ASSET_HEIGHT}, got {dimensions}.",
                )
            )

        if (
            declared_tree.get("width") != EXPECTED_TREE_ASSET_WIDTH
            or declared_tree.get("height") != EXPECTED_TREE_ASSET_HEIGHT
        ):
            issues.append(
                self._issue(
                    "tree_asset_integrity",
                    "DECLARED_TREE_DIMENSIONS_MISMATCH",
                    "probability_tree_evidence.json[tree_asset]",
                    f"Declared dimensions expected {EXPECTED_TREE_ASSET_WIDTH}x{EXPECTED_TREE_ASSET_HEIGHT}, got {declared_tree.get('width')}x{declared_tree.get('height')}.",
                )
            )

        return issues

    def _validate_grouped_statistics(
        self, stats: dict[str, Any]
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
        if stats.get("evidence_id") != "M12_STATS_INTERPRETATION_EVID_001":
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "INVALID_EVIDENCE_ID",
                    "grouped_statistics_interpretation_evidence.json",
                    f"Expected evidence_id M12_STATS_INTERPRETATION_EVID_001, got {stats.get('evidence_id')!r}.",
                )
            )
        if stats.get("evidence_status") != "SOURCE_BACKED_VERIFIED_CHILD_EVIDENCE":
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "INVALID_EVIDENCE_STATUS",
                    "grouped_statistics_interpretation_evidence.json",
                    f"Expected SOURCE_BACKED_VERIFIED_CHILD_EVIDENCE, got {stats.get('evidence_status')!r}.",
                )
            )
        if stats.get("official_scope_code") != "M12_CORE_STATISTICS_GROUPED_DATA":
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "INVALID_SCOPE_CODE",
                    "grouped_statistics_interpretation_evidence.json",
                    f"Expected M12_CORE_STATISTICS_GROUPED_DATA, got {stats.get('official_scope_code')!r}.",
                )
            )
        if stats.get("official_requirement") != "ý nghĩa và diễn giải các số đặc trưng trong thực tiễn":
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "INVALID_REQUIREMENT",
                    "grouped_statistics_interpretation_evidence.json",
                    f"Requirement mismatch: {stats.get('official_requirement')!r}.",
                )
            )
        src = stats.get("source", {})
        if src.get("source_type") != "REAL_GRADE12_PDF_WEB_SOURCE":
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "INVALID_SOURCE_TYPE",
                    "grouped_statistics_interpretation_evidence.json[source]",
                    f"Expected REAL_GRADE12_PDF_WEB_SOURCE, got {src.get('source_type')!r}.",
                )
            )
        sem = stats.get("source_semantics", {})
        if sem.get("source_answer") is not False:
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "INVALID_SOURCE_ANSWER",
                    "grouped_statistics_interpretation_evidence.json[source_semantics]",
                    f"Expected source_answer False, got {sem.get('source_answer')!r}.",
                )
            )
        sd = sem.get("source_computed_standard_deviation", {})
        if sd.get("Dung") != 0.26 or sd.get("Huy") != 0.24:
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "INVALID_SD_VALUES",
                    "grouped_statistics_interpretation_evidence.json[source_semantics]",
                    f"Expected SD Dung=0.26, Huy=0.24, got {sd}.",
                )
            )
        if stats.get("canonical_candidate_created") is not False:
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "CANONICAL_CANDIDATE_CREATED_VIOLATION",
                    "grouped_statistics_interpretation_evidence.json",
                    "canonical_candidate_created must be false.",
                )
            )
        if stats.get("synthetic_content_created") is not False:
            issues.append(
                self._issue(
                    "grouped_statistics_evidence",
                    "SYNTHETIC_CONTENT_CREATED_VIOLATION",
                    "grouped_statistics_interpretation_evidence.json",
                    "synthetic_content_created must be false.",
                )
            )
        return issues

    def _validate_probability_tree(
        self, prob: dict[str, Any]
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
        if prob.get("evidence_id") != "M12_PROB_TREE_EVID_001":
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_EVIDENCE_ID",
                    "probability_tree_evidence.json",
                    f"Expected evidence_id M12_PROB_TREE_EVID_001, got {prob.get('evidence_id')!r}.",
                )
            )
        if prob.get("evidence_status") != "SOURCE_BACKED_VERIFIED_TREE_EVIDENCE":
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_EVIDENCE_STATUS",
                    "probability_tree_evidence.json",
                    f"Expected SOURCE_BACKED_VERIFIED_TREE_EVIDENCE, got {prob.get('evidence_status')!r}.",
                )
            )
        if prob.get("official_scope_code") != "M12_CORE_PROBABILITY_CONDITIONAL":
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_SCOPE_CODE",
                    "probability_tree_evidence.json",
                    f"Expected M12_CORE_PROBABILITY_CONDITIONAL, got {prob.get('official_scope_code')!r}.",
                )
            )
        if prob.get("official_requirement") != "sơ đồ hình cây và ứng dụng thực tiễn":
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_REQUIREMENT",
                    "probability_tree_evidence.json",
                    f"Requirement mismatch: {prob.get('official_requirement')!r}.",
                )
            )
        src = prob.get("source", {})
        if src.get("source_code") != "SRC_OFFICIAL_EXAM_2025_SOLUTION":
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_SOURCE_CODE",
                    "probability_tree_evidence.json[source]",
                    f"Expected SRC_OFFICIAL_EXAM_2025_SOLUTION, got {src.get('source_code')!r}.",
                )
            )
        if src.get("source_pdf_sha256") != "90d5cb68a6f91418287c6643548f4f40ea9bb1598705a177b41bce07b09df11f":
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_SOURCE_PDF_SHA256",
                    "probability_tree_evidence.json[source]",
                    f"Expected 90d5cb68..., got {src.get('source_pdf_sha256')!r}.",
                )
            )
        if src.get("question_page_1_based") != 53 or src.get("solution_visual_page_1_based") != 54:
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_PAGE_LINEAGE",
                    "probability_tree_evidence.json[source]",
                    f"Expected pages 53/54, got {src.get('question_page_1_based')}/{src.get('solution_visual_page_1_based')}.",
                )
            )
        if src.get("source_answer_pattern") != [True, False, True, True]:
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "INVALID_SOURCE_ANSWER_PATTERN",
                    "probability_tree_evidence.json[source]",
                    f"Expected [True, False, True, True], got {src.get('source_answer_pattern')!r}.",
                )
            )
        if prob.get("canonical_candidate_created") is not False:
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "CANONICAL_CANDIDATE_CREATED_VIOLATION",
                    "probability_tree_evidence.json",
                    "canonical_candidate_created must be false.",
                )
            )
        if prob.get("synthetic_content_created") is not False:
            issues.append(
                self._issue(
                    "probability_tree_evidence",
                    "SYNTHETIC_CONTENT_CREATED_VIOLATION",
                    "probability_tree_evidence.json",
                    "synthetic_content_created must be false.",
                )
            )
        return issues

    def _validate_gap_reclassification(
        self, gap: dict[str, Any]
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
        g_data = gap.get("grouped_data_dispersion", {})
        expected_remaining = [
            "PARAMETER_FROM_GROUPED_VARIANCE_SD",
            "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
        ]
        if g_data.get("remaining_derived_enhancement_gaps") != expected_remaining:
            issues.append(
                self._issue(
                    "gap_reclassification",
                    "REMAINING_GAPS_MISMATCH",
                    "derived_gap_reclassification.json",
                    f"Expected remaining gaps {expected_remaining}, got {g_data.get('remaining_derived_enhancement_gaps')}.",
                )
            )
        if (
            g_data.get("remaining_gap_policy")
            != "COACH_DERIVED_COVERAGE_ENHANCEMENT_NONBLOCKING_FOR_OFFICIAL_CORE_COMPLETENESS"
        ):
            issues.append(
                self._issue(
                    "gap_reclassification",
                    "INVALID_GAP_POLICY",
                    "derived_gap_reclassification.json",
                    "Remaining gap policy must be non-blocking coverage enhancement.",
                )
            )
        if (
            g_data.get("official_interpretation_requirement_status_after_overlay")
            != "COVERED_BY_SOURCE_BACKED_EVIDENCE"
        ):
            issues.append(
                self._issue(
                    "gap_reclassification",
                    "REQUIREMENT_STATUS_NOT_COVERED",
                    "derived_gap_reclassification.json",
                    "official_interpretation_requirement_status_after_overlay must be COVERED_BY_SOURCE_BACKED_EVIDENCE.",
                )
            )
        cp = gap.get("conditional_probability", {})
        if (
            cp.get("probability_tree_requirement_status_after_overlay")
            != "COVERED_BY_SOURCE_BACKED_TREE_EVIDENCE"
        ):
            issues.append(
                self._issue(
                    "gap_reclassification",
                    "PROBABILITY_TREE_STATUS_NOT_COVERED",
                    "derived_gap_reclassification.json",
                    "probability_tree_requirement_status_after_overlay must be COVERED_BY_SOURCE_BACKED_TREE_EVIDENCE.",
                )
            )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[CoreEvidenceClosureIssue]:
        issues: list[CoreEvidenceClosureIssue] = []
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
        if manifest.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "evidence_manifest.json",
                    "database_import_allowed must be false.",
                )
            )
        if manifest.get("production_release_eligible") != 0:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "PRODUCTION_RELEASE_ELIGIBLE_VIOLATION",
                    "evidence_manifest.json",
                    "production_release_eligible must be 0.",
                )
            )
        if manifest.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "RIGHTS_NOT_REVIEW_REQUIRED",
                    "evidence_manifest.json",
                    f"rights_status must be REVIEW_REQUIRED, got {manifest.get('rights_status')!r}.",
                )
            )
        return issues

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _read_png_dimensions(raw_bytes: bytes) -> tuple[int, int] | None:
        if len(raw_bytes) >= 24 and raw_bytes[:8] == b"\x89PNG\r\n\x1a\n" and raw_bytes[12:16] == b"IHDR":
            width, height = struct.unpack(">II", raw_bytes[16:24])
            return width, height
        return None

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
        self, path: Path, issues: list[CoreEvidenceClosureIssue]
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
    ) -> CoreEvidenceClosureIssue:
        return CoreEvidenceClosureIssue(
            check=check, code=code, location=location, message=message
        )
