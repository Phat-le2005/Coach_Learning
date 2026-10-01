from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "academic_evidence_web_review_v0_1"
)

EXPECTED_ACADEMIC_WEB_EVIDENCE_AGGREGATE_SHA256 = (
    "285d79ba1156fe17bb1b18ebc657a9ae362f5a48ee493e134dbd30fdd0e264d1"
)
EXPECTED_BASE_REPO_COMMIT = "446abb9c2fde1fd9b065e0d8b42240c7e738da1f"

SEMANTIC_FILES_ORDER = (
    "parameter_monotonicity_evidence.json",
    "multi_measure_statistics_evidence.json",
    "academic_effect.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES_ORDER,
    "data_contract.json",
    "README.md",
)

EXPECTED_SEMANTIC_HASHES = {
    "parameter_monotonicity_evidence.json": (
        "569fcfbc7aa3c1c96b51e71c57197c285f54bf7119d317cf8789c91e4b9761b6"
    ),
    "multi_measure_statistics_evidence.json": (
        "0d24fc516520e436bd76aa2a6111727f4f9482a945b7ad28250585f18a6d2681"
    ),
    "academic_effect.json": (
        "00c9b82303af22d5dd133a63d30c1bb54ecf4425b1226c0e49da390e77ce0434"
    ),
}


@dataclass(frozen=True, order=True)
class AcademicWebEvidenceIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True)
class AcademicWebEvidenceReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str
    aggregate_semantic_sha256: str
    derivative_zero_academic: list[str]
    derivative_zero_pinned: list[str]
    stats_zero_academic: list[str]
    rights_status: str
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[AcademicWebEvidenceIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS" and len(self.errors) == 0

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["is_valid"] = self.is_valid
        return result


class AcademicWebEvidenceValidator:
    """Validates DATA-MATH12-046 web-reviewed academic existence evidence."""

    def validate(
        self,
        dataset_path: Path | str | None = None,
    ) -> AcademicWebEvidenceReport:
        path = (
            Path(dataset_path)
            if dataset_path is not None
            else DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH
        )

        initial: list[AcademicWebEvidenceIssue] = []
        self._check_required_files(path, initial)

        contract = self._load_object(path / "data_contract.json", initial)
        param_mono = self._load_object(
            path / "parameter_monotonicity_evidence.json", initial
        )
        multi_stats = self._load_object(
            path / "multi_measure_statistics_evidence.json", initial
        )
        effect_data = self._load_object(path / "academic_effect.json", initial)

        checks_to_errors: dict[str, list[AcademicWebEvidenceIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "parameter_monotonicity_integrity": (
                self._validate_parameter_monotonicity(param_mono)
            ),
            "multi_measure_statistics_integrity": (
                self._validate_multi_measure_statistics(multi_stats)
            ),
            "academic_effect_integrity": self._validate_academic_effect(
                effect_data
            ),
            "critical_boundaries": self._validate_critical_boundaries(contract),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[AcademicWebEvidenceIssue] = []
        if aggregate != EXPECTED_ACADEMIC_WEB_EVIDENCE_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_ACADEMIC_WEB_EVIDENCE_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_ACADEMIC_WEB_EVIDENCE_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-046 aggregate.",
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

        effects = effect_data.get("effects", {})
        deriv_acad = list(
            effects.get("derivative_zero_academic_evidence_after", [])
        )
        deriv_pin = list(
            effects.get("derivative_zero_pinned_practice_after", [])
        )
        stats_acad = list(
            effects.get("statistics_derived_zero_academic_evidence_after", [])
        )

        counts = {
            "evidence_records_count": 2,
            "derivative_zero_academic_count": len(deriv_acad),
            "derivative_zero_pinned_count": len(deriv_pin),
            "statistics_zero_academic_count": len(stats_acad),
        }

        return AcademicWebEvidenceReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit", ""),
            aggregate_semantic_sha256=aggregate,
            derivative_zero_academic=deriv_acad,
            derivative_zero_pinned=deriv_pin,
            stats_zero_academic=stats_acad,
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
        self, path: Path, issues: list[AcademicWebEvidenceIssue]
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
    ) -> list[AcademicWebEvidenceIssue]:
        issues: list[AcademicWebEvidenceIssue] = []
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
    ) -> list[AcademicWebEvidenceIssue]:
        issues: list[AcademicWebEvidenceIssue] = []
        if contract.get("dataset_code") != "DATA-MATH12-046":
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "DATASET_CODE_MISMATCH",
                    "data_contract.json",
                    f"Expected dataset_code DATA-MATH12-046, got {contract.get('dataset_code')!r}.",
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
    ) -> list[AcademicWebEvidenceIssue]:
        issues: list[AcademicWebEvidenceIssue] = []
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

    def _validate_parameter_monotonicity(
        self, data: dict[str, Any]
    ) -> list[AcademicWebEvidenceIssue]:
        issues: list[AcademicWebEvidenceIssue] = []
        if data.get("evidence_id") != "M12_D046_PARAMETER_MONOTONICITY_WEB_001":
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "EVIDENCE_ID_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    "evidence_id must be M12_D046_PARAMETER_MONOTONICITY_WEB_001.",
                )
            )
        if data.get("problem_type_code") != "PARAMETER_MONOTONICITY":
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "PROBLEM_TYPE_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    "problem_type_code must be PARAMETER_MONOTONICITY.",
                )
            )
        if data.get("scope") != "DERIVATIVE_APPLICATIONS":
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "SCOPE_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    "scope must be DERIVATIVE_APPLICATIONS.",
                )
            )
        if data.get("status") != "SOURCE_BACKED_WEB_PDF_REVIEWED_BINARY_UNPINNED":
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "STATUS_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    "status must be SOURCE_BACKED_WEB_PDF_REVIEWED_BINARY_UNPINNED.",
                )
            )

        src = data.get("source", {})
        expected_url = "https://file.montoan.com.vn/file-pdf/bai-giang-tinh-don-dieu-cua-ham-so.pdf"
        if src.get("url") != expected_url:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "SOURCE_URL_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    f"source url must be {expected_url}.",
                )
            )
        if src.get("question_pdf_page_1_based") != 31:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "QUESTION_PAGE_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    "question_pdf_page_1_based must be 31.",
                )
            )
        if src.get("answer_key_pdf_page_1_based") != 60:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "ANSWER_PAGE_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    "answer_key_pdf_page_1_based must be 60.",
                )
            )
        if src.get("binary_sha256") is not None:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "BINARY_SHA_NOT_NULL",
                    "parameter_monotonicity_evidence.json",
                    "binary_sha256 must remain null until explicitly pinned.",
                )
            )
        if src.get("binary_pin_required") is not True:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "BINARY_PIN_REQUIRED_NOT_TRUE",
                    "parameter_monotonicity_evidence.json",
                    "binary_pin_required must be true.",
                )
            )

        facts = data.get("source_supported_facts", {})
        expected_options = {"A": 6, "B": 4, "C": 7, "D": 5}
        if facts.get("options") != expected_options:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "OPTIONS_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    f"options must be {expected_options}, got {facts.get('options')}.",
                )
            )
        if facts.get("answer_key") != "C" or facts.get("answer_value") != 7:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "ANSWER_MISMATCH",
                    "parameter_monotonicity_evidence.json",
                    "answer_key must be 'C' and answer_value must be 7.",
                )
            )

        # Enforce practice-ready and promotion flags are False
        if data.get("practice_ready") is not False:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "PRACTICE_READY_NOT_FALSE",
                    "parameter_monotonicity_evidence.json",
                    "practice_ready must be false for unpinned web evidence.",
                )
            )
        if data.get("promotion_allowed") is not False:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "PROMOTION_ALLOWED_NOT_FALSE",
                    "parameter_monotonicity_evidence.json",
                    "promotion_allowed must be false for unpinned web evidence.",
                )
            )
        if data.get("canonical_candidate_created") is not False:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "CANONICAL_CANDIDATE_CREATED_NOT_FALSE",
                    "parameter_monotonicity_evidence.json",
                    "canonical_candidate_created must be false.",
                )
            )
        if data.get("synthetic_content_created") is not False:
            issues.append(
                self._issue(
                    "parameter_monotonicity_integrity",
                    "SYNTHETIC_CONTENT_NOT_FALSE",
                    "parameter_monotonicity_evidence.json",
                    "synthetic_content_created must be false.",
                )
            )

        return issues

    def _validate_multi_measure_statistics(
        self, data: dict[str, Any]
    ) -> list[AcademicWebEvidenceIssue]:
        issues: list[AcademicWebEvidenceIssue] = []
        if data.get("evidence_id") != "M12_D046_MULTI_MEASURE_STATS_WEB_001":
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "EVIDENCE_ID_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "evidence_id must be M12_D046_MULTI_MEASURE_STATS_WEB_001.",
                )
            )
        if (
            data.get("problem_type_code")
            != "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS"
        ):
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "PROBLEM_TYPE_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "problem_type_code must be MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS.",
                )
            )
        if data.get("scope") != "GROUPED_DATA_STATISTICS":
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "SCOPE_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "scope must be GROUPED_DATA_STATISTICS.",
                )
            )
        if data.get("status") != "SOURCE_BACKED_WEB_PDF_REVIEWED_BINARY_UNPINNED":
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "STATUS_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "status must be SOURCE_BACKED_WEB_PDF_REVIEWED_BINARY_UNPINNED.",
                )
            )

        src = data.get("source", {})
        expected_url = "https://file.toan12.edu.vn/file-pdf/de-kiem-tra-theo-bai-hoc-cac-so-dac-trung-do-muc-do-phan-tan-mau-so-lieu-ghep-nhom.pdf"
        if src.get("url") != expected_url:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "SOURCE_URL_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    f"source url must be {expected_url}.",
                )
            )
        if src.get("question_pdf_pages_1_based") != [54, 55]:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "QUESTION_PAGES_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "question_pdf_pages_1_based must be [54, 55].",
                )
            )
        if src.get("solution_pdf_pages_1_based") != [55, 56]:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "SOLUTION_PAGES_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "solution_pdf_pages_1_based must be [55, 56].",
                )
            )
        if src.get("binary_sha256") is not None:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "BINARY_SHA_NOT_NULL",
                    "multi_measure_statistics_evidence.json",
                    "binary_sha256 must remain null until explicitly pinned.",
                )
            )

        facts = data.get("source_supported_facts", {})
        if facts.get("school_X_frequencies") != [8, 10, 13, 10, 9]:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "SCHOOL_X_FREQS_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "school_X_frequencies must be [8, 10, 13, 10, 9].",
                )
            )
        if facts.get("school_Y_frequencies") != [4, 12, 17, 14, 3]:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "SCHOOL_Y_FREQS_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "school_Y_frequencies must be [4, 12, 17, 14, 3].",
                )
            )
        if facts.get("statement_answer_pattern") != [True, False, False, True]:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "ANSWER_PATTERN_MISMATCH",
                    "multi_measure_statistics_evidence.json",
                    "statement_answer_pattern must be [True, False, False, True].",
                )
            )

        # Enforce practice-ready and promotion flags are False
        if data.get("practice_ready") is not False:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "PRACTICE_READY_NOT_FALSE",
                    "multi_measure_statistics_evidence.json",
                    "practice_ready must be false for unpinned web evidence.",
                )
            )
        if data.get("promotion_allowed") is not False:
            issues.append(
                self._issue(
                    "multi_measure_statistics_integrity",
                    "PROMOTION_ALLOWED_NOT_FALSE",
                    "multi_measure_statistics_evidence.json",
                    "promotion_allowed must be false for unpinned web evidence.",
                )
            )

        return issues

    def _validate_academic_effect(
        self, data: dict[str, Any]
    ) -> list[AcademicWebEvidenceIssue]:
        issues: list[AcademicWebEvidenceIssue] = []
        effects = data.get("effects", {})
        if (
            effects.get("derivative_zero_academic_evidence_before")
            != ["PARAMETER_MONOTONICITY"]
        ):
            issues.append(
                self._issue(
                    "academic_effect_integrity",
                    "DERIVATIVE_ZERO_BEFORE_MISMATCH",
                    "academic_effect.json",
                    "derivative_zero_academic_evidence_before must be ['PARAMETER_MONOTONICITY'].",
                )
            )
        if effects.get("derivative_zero_academic_evidence_after") != []:
            issues.append(
                self._issue(
                    "academic_effect_integrity",
                    "DERIVATIVE_ZERO_AFTER_NOT_EMPTY",
                    "academic_effect.json",
                    "derivative_zero_academic_evidence_after must be empty [].",
                )
            )
        if (
            effects.get("derivative_zero_pinned_practice_after")
            != ["PARAMETER_MONOTONICITY"]
        ):
            issues.append(
                self._issue(
                    "academic_effect_integrity",
                    "DERIVATIVE_PINNED_AFTER_MISMATCH",
                    "academic_effect.json",
                    "derivative_zero_pinned_practice_after must remain ['PARAMETER_MONOTONICITY'].",
                )
            )
        if (
            effects.get("statistics_derived_zero_academic_evidence_after")
            != ["PARAMETER_FROM_GROUPED_VARIANCE_SD"]
        ):
            issues.append(
                self._issue(
                    "academic_effect_integrity",
                    "STATS_ZERO_AFTER_MISMATCH",
                    "academic_effect.json",
                    "statistics_derived_zero_academic_evidence_after must be ['PARAMETER_FROM_GROUPED_VARIANCE_SD'].",
                )
            )

        rule = data.get("rule", "")
        if "UNPINNED_WEB_EVIDENCE_MAY_CLOSE_ACADEMIC_EXISTENCE_GAP" not in rule:
            issues.append(
                self._issue(
                    "academic_effect_integrity",
                    "RULE_MISMATCH",
                    "academic_effect.json",
                    "rule must declare UNPINNED_WEB_EVIDENCE_MAY_CLOSE_ACADEMIC_EXISTENCE_GAP_BUT_MUST_NOT_COUNT_AS_PINNED_PRACTICE_OR_PROMOTION.",
                )
            )

        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any]
    ) -> list[AcademicWebEvidenceIssue]:
        issues: list[AcademicWebEvidenceIssue] = []
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
        self, path: Path, issues: list[AcademicWebEvidenceIssue]
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
    ) -> AcademicWebEvidenceIssue:
        return AcademicWebEvidenceIssue(
            check=check, code=code, location=location, message=message
        )
