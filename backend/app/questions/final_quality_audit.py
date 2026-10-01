from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINAL_QUALITY_AUDIT_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "final_quality_audit_v0_1"
)

EXPECTED_FINAL_QUALITY_AUDIT_AGGREGATE_SHA256 = (
    "ce982cd5ffc6ae30dd3098bfd59c36752e84894d4c27b6412184f0d92c1610cc"
)
EXPECTED_BASE_REPO_COMMIT = "446abb9c2fde1fd9b065e0d8b42240c7e738da1f"

SEMANTIC_FILES_ORDER = (
    "quality_status.json",
    "priority_plan.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES_ORDER,
    "data_contract.json",
    "README.md",
)

EXPECTED_SEMANTIC_HASHES = {
    "quality_status.json": (
        "392487cb6d7d4db794ee887269dd919e60f149eddb93f79e3ce062e52ac86f98"
    ),
    "priority_plan.json": (
        "12d105ad3de92d9741a687bb27d23ee77999b80885a3c19279112c3df9bc30f2"
    ),
}


@dataclass(frozen=True, order=True)
class FinalQualityAuditIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True)
class FinalQualityAuditReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str
    aggregate_semantic_sha256: str
    official_scope_status: str
    diagnostic_density_status: str
    stats_diversity_status: str
    prob_diversity_status: str
    overall_status: str
    rights_status: str
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[FinalQualityAuditIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS" and len(self.errors) == 0

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["is_valid"] = self.is_valid
        return result


class FinalQualityAuditValidator:
    """Validates DATA-MATH12-048 final quality re-audit."""

    def validate(
        self,
        dataset_path: Path | str | None = None,
    ) -> FinalQualityAuditReport:
        path = (
            Path(dataset_path)
            if dataset_path is not None
            else DEFAULT_FINAL_QUALITY_AUDIT_PATH
        )

        initial: list[FinalQualityAuditIssue] = []
        self._check_required_files(path, initial)

        contract = self._load_object(path / "data_contract.json", initial)
        status_data = self._load_object(path / "quality_status.json", initial)
        plan_data = self._load_object(path / "priority_plan.json", initial)

        checks_to_errors: dict[str, list[FinalQualityAuditIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "quality_status_integrity": self._validate_quality_status(status_data),
            "priority_plan_integrity": self._validate_priority_plan(plan_data),
            "critical_boundaries": self._validate_critical_boundaries(contract),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[FinalQualityAuditIssue] = []
        if aggregate != EXPECTED_FINAL_QUALITY_AUDIT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_FINAL_QUALITY_AUDIT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_FINAL_QUALITY_AUDIT_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-048 aggregate.",
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

        off_scope = status_data.get("official_scope", {})
        diag_dens = status_data.get("diagnostic_density", {})
        src_div = status_data.get("source_diversity", {})
        stats_div = src_div.get("GROUPED_DATA_STATISTICS", {})
        prob_div = src_div.get("PROBABILITY_CHAPTER", {})

        counts = {
            "requirements_total": off_scope.get("requirements_total", 0),
            "source_evidenced": off_scope.get("source_evidenced", 0),
            "priority_thin_types_count": len(diag_dens.get("priority_thin_types", [])),
            "next_real_data_actions_count": len(plan_data.get("next_real_data_actions", [])),
        }

        return FinalQualityAuditReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit", ""),
            aggregate_semantic_sha256=aggregate,
            official_scope_status=str(off_scope.get("status", "")),
            diagnostic_density_status=str(diag_dens.get("status", "")),
            stats_diversity_status=str(stats_div.get("status", "")),
            prob_diversity_status=str(prob_div.get("status", "")),
            overall_status=str(status_data.get("overall", "")),
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
        self, path: Path, issues: list[FinalQualityAuditIssue]
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
    ) -> list[FinalQualityAuditIssue]:
        issues: list[FinalQualityAuditIssue] = []
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
    ) -> list[FinalQualityAuditIssue]:
        issues: list[FinalQualityAuditIssue] = []
        if contract.get("dataset_code") != "DATA-MATH12-048":
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "DATASET_CODE_MISMATCH",
                    "data_contract.json",
                    f"Expected dataset_code DATA-MATH12-048, got {contract.get('dataset_code')!r}.",
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
    ) -> list[FinalQualityAuditIssue]:
        issues: list[FinalQualityAuditIssue] = []
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

    def _validate_quality_status(
        self, data: dict[str, Any]
    ) -> list[FinalQualityAuditIssue]:
        issues: list[FinalQualityAuditIssue] = []
        # 1. Official scope coverage: must be PASS 20/20
        off = data.get("official_scope", {})
        if off.get("requirements_total") != 20 or off.get("source_evidenced") != 20:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "OFFICIAL_SCOPE_COUNT_MISMATCH",
                    "quality_status.json",
                    "official_scope must be 20/20 requirements.",
                )
            )
        if off.get("status") != "PASS":
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "OFFICIAL_SCOPE_NOT_PASS",
                    "quality_status.json",
                    "official_scope status must be PASS.",
                )
            )

        # 2. Academic existence: zero counts separated from pinned practice
        acad = data.get("academic_existence", {})
        if acad.get("derivative_zero_problem_types") != []:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "DERIVATIVE_ACADEMIC_ZERO_NOT_EMPTY",
                    "quality_status.json",
                    "derivative_zero_problem_types academic existence must be empty [].",
                )
            )
        if acad.get("vector_legacy_zero_problem_types") != []:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "VECTOR_ACADEMIC_ZERO_NOT_EMPTY",
                    "quality_status.json",
                    "vector_legacy_zero_problem_types academic existence must be empty [].",
                )
            )
        if acad.get("statistics_derived_zero_problem_types") != ["PARAMETER_FROM_GROUPED_VARIANCE_SD"]:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "STATS_ACADEMIC_ZERO_MISMATCH",
                    "quality_status.json",
                    "statistics_derived_zero_problem_types academic existence must be ['PARAMETER_FROM_GROUPED_VARIANCE_SD'].",
                )
            )

        # 3. Pinned practice readiness: PARAMETER_MONOTONICITY must remain in zero/not-ready
        pinned = data.get("pinned_practice_zero_or_not_practice_ready", {})
        if pinned.get("DERIVATIVE_APPLICATIONS") != ["PARAMETER_MONOTONICITY"]:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "DERIVATIVE_PINNED_ZERO_MISMATCH",
                    "quality_status.json",
                    "DERIVATIVE_APPLICATIONS pinned practice must contain ['PARAMETER_MONOTONICITY'].",
                )
            )
        if pinned.get("VECTOR_LEGACY_SUBSCOPE") != []:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "VECTOR_PINNED_ZERO_NOT_EMPTY",
                    "quality_status.json",
                    "VECTOR_LEGACY_SUBSCOPE pinned practice must be empty [].",
                )
            )
        stats_pinned = pinned.get("GROUPED_DATA_STATISTICS", [])
        if "PARAMETER_FROM_GROUPED_VARIANCE_SD" not in stats_pinned or "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS" not in stats_pinned:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "STATS_PINNED_ZERO_MISMATCH",
                    "quality_status.json",
                    "GROUPED_DATA_STATISTICS pinned practice must contain PARAMETER_FROM_GROUPED_VARIANCE_SD and MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS.",
                )
            )

        # 4. Source diversity
        div = data.get("source_diversity", {})
        stats_div = div.get("GROUPED_DATA_STATISTICS", {})
        if stats_div.get("status") != "PASS":
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "STATS_DIVERSITY_NOT_PASS",
                    "quality_status.json",
                    "statistics source diversity status must be PASS.",
                )
            )
        prob_div = div.get("PROBABILITY_CHAPTER", {})
        if prob_div.get("status") != "FAIL_SLIGHTLY_ABOVE_0_70":
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "PROB_DIVERSITY_NOT_FAIL",
                    "quality_status.json",
                    "probability source diversity status must be FAIL_SLIGHTLY_ABOVE_0_70.",
                )
            )

        # 5. Diagnostic density: must be FAIL (not a Ministry requirement, self-imposed QA target)
        dens = data.get("diagnostic_density", {})
        if dens.get("status") != "FAIL":
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "DIAGNOSTIC_DENSITY_NOT_FAIL",
                    "quality_status.json",
                    "diagnostic_density status must be FAIL.",
                )
            )
        if dens.get("target_per_problem_type") != 5:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "DENSITY_TARGET_MISMATCH",
                    "quality_status.json",
                    "diagnostic_density target_per_problem_type must be 5.",
                )
            )
        if len(dens.get("priority_thin_types", [])) != 19:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "THIN_TYPES_COUNT_MISMATCH",
                    "quality_status.json",
                    f"Expected 19 priority thin types, got {len(dens.get('priority_thin_types', []))}.",
                )
            )

        # Overall
        expected_overall = "BREADTH_COMPLETE_DEPTH_NOT_YET_AT_SELF_IMPOSED_PRODUCTION_QA_TARGET"
        if data.get("overall") != expected_overall:
            issues.append(
                self._issue(
                    "quality_status_integrity",
                    "OVERALL_STATUS_MISMATCH",
                    "quality_status.json",
                    f"overall status must be {expected_overall}.",
                )
            )

        return issues

    def _validate_priority_plan(
        self, data: dict[str, Any]
    ) -> list[FinalQualityAuditIssue]:
        issues: list[FinalQualityAuditIssue] = []
        if data.get("new_chapter_ingestion") != "DO_NOT_DO":
            issues.append(
                self._issue(
                    "priority_plan_integrity",
                    "NEW_CHAPTER_INGESTION_NOT_BLOCKED",
                    "priority_plan.json",
                    "new_chapter_ingestion must be DO_NOT_DO.",
                )
            )
        actions = data.get("next_real_data_actions", [])
        if len(actions) != 4:
            issues.append(
                self._issue(
                    "priority_plan_integrity",
                    "ACTIONS_COUNT_MISMATCH",
                    "priority_plan.json",
                    f"Expected 4 next_real_data_actions, got {len(actions)}.",
                )
            )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any]
    ) -> list[FinalQualityAuditIssue]:
        issues: list[FinalQualityAuditIssue] = []
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
        self, path: Path, issues: list[FinalQualityAuditIssue]
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
    ) -> FinalQualityAuditIssue:
        return FinalQualityAuditIssue(
            check=check, code=code, location=location, message=message
        )
