from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.grouped_data_dispersion_academic_review import (
    DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
    EXPECTED_REVIEW_AGGREGATE_SHA256 as EXPECTED_BASE_AGGREGATE_SHA256,
    GroupedDataDispersionAcademicReviewValidator,
)


DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH = (
    DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH.parents[1]
    / "gap_scan"
    / "v0_2"
)
EXPECTED_AGGREGATE_SEMANTIC_SHA256 = (
    "cae9d0c8a8970bbb19f43ab3de33927e348498f406f37a8938038692a9be8435"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "776790ed25e4a50c506f0f580e54dda46780b11aab9233744e05ca51d2a6c2e6"
)
EXPECTED_REMAINING_GAPS = (
    "IDENTIFY_MORE_STABLE_GROUPED_DATA",
    "INTERPRET_GROUPED_DISPERSION_MEASURE",
    "CONCLUDE_FROM_GROUPED_DISPERSION",
    "PARAMETER_FROM_GROUPED_VARIANCE_SD",
    "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
)
SEMANTIC_FILES = (
    "local_source_scan_registry.json",
    "external_gap_leads.json",
    "gap_scan_result.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES, "data_contract.json", "README.md")
EXPECTED_SEMANTIC_HASHES = {
    "local_source_scan_registry.json": (
        "875cf919c7be9799228a68d154d2e09e4780efda63866007d4254a056e2fa36f"
    ),
    "external_gap_leads.json": (
        "4b630cdc192a8c5d50ed9de803a71b4180c7ed622ecc81fad4b12b62bd639d71"
    ),
    "gap_scan_result.json": (
        "df689659b1b4a0fd0f8b40b9fe7004827402306323e7760eb20951a714b0a17c"
    ),
}
EXPECTED_COUNTS = {
    "local_real_pdf_sources_scanned": 22,
    "new_local_source_backed_verified_candidates_found": 0,
    "remaining_gap_count": 5,
    "external_gap_leads_count": 4,
}


@dataclass(frozen=True, slots=True, order=True)
class GroupedDataDispersionGapRescanIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class GroupedDataDispersionGapRescanReport:
    dataset_path: str
    base_dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    remaining_gaps: tuple[str, ...]
    aggregate_semantic_sha256: str | None
    rights_status: str | None
    database_import_allowed: bool
    canonical_snapshot_allowed: bool
    errors: tuple[GroupedDataDispersionGapRescanIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "base_dataset_path": self.base_dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "remaining_gaps": list(self.remaining_gaps),
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "rights_status": self.rights_status,
            "database_import_allowed": self.database_import_allowed,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class GroupedDataDispersionGapRescanValidator:
    """Validate DATA-MATH12-031 grouped-data dispersion gap rescan v0_2."""

    def validate(
        self,
        scan_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH,
        *,
        base_review_path: Path = DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
    ) -> GroupedDataDispersionGapRescanReport:
        path = scan_path.resolve()
        base_path = base_review_path.resolve()
        initial: list[GroupedDataDispersionGapRescanIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        source_registry = self._load_list(
            path / "local_source_scan_registry.json", initial
        )
        leads = self._load_list(path / "external_gap_leads.json", initial)
        result = self._load_object(path / "gap_scan_result.json", initial)

        checks_to_errors: dict[
            str, list[GroupedDataDispersionGapRescanIssue]
        ] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_academic_review_binding": self._validate_base_review_binding(
                base_path, result
            ),
            "local_source_scan_registry": self._validate_source_registry(
                source_registry
            ),
            "external_leads_contract": self._validate_external_leads(leads),
            "gap_scan_result_contract": self._validate_scan_result(
                result, source_registry, leads, contract
            ),
            "release_boundary": self._validate_release_boundary(
                contract, result, leads
            ),
        }
        for issue in initial:
            if issue.check != "required_files":
                checks_to_errors.setdefault(issue.check, []).append(issue)

        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[GroupedDataDispersionGapRescanIssue] = []
        expected_aggregate = contract.get("aggregate_semantic_sha256")
        if aggregate != EXPECTED_AGGREGATE_SEMANTIC_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_AGGREGATE_SEMANTIC_SHA256}, got {aggregate!r}.",
                )
            )
        if expected_aggregate != EXPECTED_AGGREGATE_SEMANTIC_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-031 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        errors = tuple(
            sorted(issue for issues in checks_to_errors.values() for issue in issues)
        )
        remaining = tuple(
            str(x)
            for x in result.get("remaining_gaps", [])
            if isinstance(x, str)
        )
        counts = {
            "local_real_pdf_sources_scanned": len(source_registry),
            "new_local_source_backed_verified_candidates_found": self._int_value(
                result.get("new_local_source_backed_verified_candidates_found"),
                default=-1,
            ),
            "remaining_gap_count": len(remaining),
            "external_gap_leads_count": len(leads),
        }
        if counts != EXPECTED_COUNTS:
            errors = tuple(
                sorted(
                    (
                        *errors,
                        self._issue(
                            "exact_counts",
                            "COUNT_MISMATCH",
                            "gap_scan_result.json",
                            f"Expected {EXPECTED_COUNTS!r}, got {counts!r}.",
                        ),
                    )
                )
            )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }
        checks["exact_counts"] = counts == EXPECTED_COUNTS

        return GroupedDataDispersionGapRescanReport(
            dataset_path=str(path),
            base_dataset_path=str(base_path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            remaining_gaps=remaining,
            aggregate_semantic_sha256=aggregate,
            rights_status=result.get("rights_status"),
            database_import_allowed=result.get("database_import_allowed") is True,
            canonical_snapshot_allowed=(
                result.get("canonical_snapshot_allowed") is True
            ),
            errors=errors,
        )

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[GroupedDataDispersionGapRescanIssue]:
        issues: list[GroupedDataDispersionGapRescanIssue] = []
        contract_path = path / "data_contract.json"
        if contract_path.is_file():
            actual_contract_hash = self._semantic_hash(contract_path)
            if actual_contract_hash != EXPECTED_CONTRACT_SEMANTIC_SHA256:
                issues.append(
                    self._issue(
                        "curated_hash_contract",
                        "CONTRACT_HASH_MISMATCH",
                        contract_path.name,
                        "The curated data_contract changed semantically.",
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
        if set(order) != set(expected_hashes) or tuple(order) != SEMANTIC_FILES:
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "SEMANTIC_FILE_SET_MISMATCH",
                    contract_path.name,
                    "Semantic file order does not match expected scan files.",
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

    def _validate_base_review_binding(
        self,
        base_path: Path,
        result: dict[str, Any],
    ) -> list[GroupedDataDispersionGapRescanIssue]:
        issues: list[GroupedDataDispersionGapRescanIssue] = []
        base_report = GroupedDataDispersionAcademicReviewValidator().validate(
            base_path
        )
        if not base_report.is_valid:
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "BASE_REVIEW_INVALID",
                    str(base_path),
                    "DATA-MATH12-021 validation did not pass.",
                )
            )
        if (
            base_report.review_aggregate_semantic_sha256
            != EXPECTED_BASE_AGGREGATE_SHA256
        ):
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "BASE_AGGREGATE_MISMATCH",
                    str(base_path),
                    "DATA-MATH12-021 aggregate hash does not match locked state.",
                )
            )
        if result.get("base_dataset") != "DATA-MATH12-021":
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "RESOLUTION_BASE_DATASET_MISMATCH",
                    "gap_scan_result.json",
                    "base_dataset in result must be DATA-MATH12-021.",
                )
            )
        if (
            result.get("base_review_aggregate_sha256")
            != EXPECTED_BASE_AGGREGATE_SHA256
        ):
            issues.append(
                self._issue(
                    "base_academic_review_binding",
                    "RESOLUTION_BASE_AGGREGATE_MISMATCH",
                    "gap_scan_result.json",
                    "Resolution base aggregate sha256 mismatch.",
                )
            )
        return issues

    def _validate_source_registry(
        self,
        sources: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionGapRescanIssue]:
        issues: list[GroupedDataDispersionGapRescanIssue] = []
        if len(sources) != 22:
            issues.append(
                self._issue(
                    "local_source_scan_registry",
                    "SOURCE_COUNT_MISMATCH",
                    "local_source_scan_registry.json",
                    f"Expected 22 rescanned local sources, got {len(sources)}.",
                )
            )
        seen_codes: set[str] = set()
        for idx, src in enumerate(sources):
            loc = f"local_source_scan_registry.json[{idx}]"
            code = src.get("source_code")
            if not code or code in seen_codes:
                issues.append(
                    self._issue(
                        "local_source_scan_registry",
                        "DUPLICATE_SOURCE_CODE",
                        loc,
                        f"Duplicate or empty source_code: {code!r}.",
                    )
                )
            seen_codes.add(str(code))
            if (
                src.get("scan_status")
                != "TARGETED_TEXT_LAYER_RESCAN_COMPLETED"
            ):
                issues.append(
                    self._issue(
                        "local_source_scan_registry",
                        "SCAN_STATUS_INCOMPLETE",
                        loc,
                        f"Expected scan_status TARGETED_TEXT_LAYER_RESCAN_COMPLETED, got {src.get('scan_status')!r}.",
                    )
                )
            if not isinstance(src.get("page_count"), int) or src.get("page_count", 0) <= 0:
                issues.append(
                    self._issue(
                        "local_source_scan_registry",
                        "INVALID_PAGE_COUNT",
                        loc,
                        f"Invalid page_count: {src.get('page_count')!r}.",
                    )
                )
            sha = src.get("source_pdf_sha256")
            if not isinstance(sha, str) or len(sha) != 64:
                issues.append(
                    self._issue(
                        "local_source_scan_registry",
                        "INVALID_PDF_SHA256",
                        loc,
                        f"Invalid source_pdf_sha256: {sha!r}.",
                    )
                )
        return issues

    def _validate_external_leads(
        self,
        leads: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionGapRescanIssue]:
        issues: list[GroupedDataDispersionGapRescanIssue] = []
        if len(leads) != 4:
            issues.append(
                self._issue(
                    "external_leads_contract",
                    "LEADS_COUNT_MISMATCH",
                    "external_gap_leads.json",
                    f"Expected 4 external gap leads, got {len(leads)}.",
                )
            )
        for idx, lead in enumerate(leads):
            loc = f"external_gap_leads.json[{idx}]"
            status = lead.get("status")
            if not isinstance(status, str) or not status.startswith("DISCOVERY_ONLY"):
                issues.append(
                    self._issue(
                        "external_leads_contract",
                        "LEAD_NOT_DISCOVERY_ONLY",
                        loc,
                        f"External lead status must start with DISCOVERY_ONLY, got {status!r}.",
                    )
                )
            relevance = lead.get("potential_gap_relevance")
            if not isinstance(relevance, list) or not relevance:
                issues.append(
                    self._issue(
                        "external_leads_contract",
                        "MISSING_GAP_RELEVANCE",
                        loc,
                        "potential_gap_relevance must be a non-empty list.",
                    )
                )
            else:
                for r in relevance:
                    if r not in EXPECTED_REMAINING_GAPS:
                        issues.append(
                            self._issue(
                                "external_leads_contract",
                                "UNKNOWN_GAP_RELEVANCE",
                                loc,
                                f"Unknown gap relevance {r!r}.",
                            )
                        )
        return issues

    def _validate_scan_result(
        self,
        result: dict[str, Any],
        sources: list[dict[str, Any]],
        leads: list[dict[str, Any]],
        contract: dict[str, Any],
    ) -> list[GroupedDataDispersionGapRescanIssue]:
        issues: list[GroupedDataDispersionGapRescanIssue] = []
        if result.get("dataset_code") != "DATA-MATH12-031":
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "DATASET_CODE_MISMATCH",
                    "gap_scan_result.json",
                    "dataset_code must be DATA-MATH12-031.",
                )
            )
        scope = result.get("scan_scope", {})
        if scope.get("local_real_pdf_sources_scanned") != len(sources):
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "SOURCES_SCANNED_MISMATCH",
                    "gap_scan_result.json",
                    "local_real_pdf_sources_scanned must match source registry length.",
                )
            )
        if scope.get("targeted_external_source_leads_recorded") != len(leads):
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "LEADS_COUNT_MISMATCH",
                    "gap_scan_result.json",
                    "targeted_external_source_leads_recorded must match leads length.",
                )
            )
        if scope.get("ocr_used") is not False:
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "OCR_USED_VIOLATION",
                    "gap_scan_result.json",
                    "ocr_used must be false.",
                )
            )
        if scope.get("synthetic_question_generation_used") is not False:
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "SYNTHETIC_GENERATION_VIOLATION",
                    "gap_scan_result.json",
                    "synthetic_question_generation_used must be false.",
                )
            )

        if tuple(result.get("original_gaps", [])) != EXPECTED_REMAINING_GAPS:
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "ORIGINAL_GAPS_MISMATCH",
                    "gap_scan_result.json",
                    f"original_gaps must match locked {EXPECTED_REMAINING_GAPS!r}.",
                )
            )
        if result.get("new_local_source_backed_verified_candidates_found") != 0:
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "NEW_CANDIDATES_NOT_ZERO",
                    "gap_scan_result.json",
                    "new_local_source_backed_verified_candidates_found must be 0.",
                )
            )
        if result.get("resolved_gaps") != []:
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "RESOLVED_GAPS_NONEMPTY",
                    "gap_scan_result.json",
                    "resolved_gaps must be empty in gap scan v0_2.",
                )
            )
        if tuple(result.get("remaining_gaps", [])) != EXPECTED_REMAINING_GAPS:
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "REMAINING_GAPS_MISMATCH",
                    "gap_scan_result.json",
                    f"remaining_gaps must match locked {EXPECTED_REMAINING_GAPS!r}.",
                )
            )
        if (
            result.get("decision")
            != "KEEP_REAL_GAPS_UNTIL_RAW_EXTERNAL_SOURCE_IS_INGESTED_AND_ANSWER_VERIFIED"
        ):
            issues.append(
                self._issue(
                    "gap_scan_result_contract",
                    "DECISION_MISMATCH",
                    "gap_scan_result.json",
                    "Unexpected decision string.",
                )
            )
        return issues

    def _validate_release_boundary(
        self,
        contract: dict[str, Any],
        result: dict[str, Any],
        leads: list[dict[str, Any]],
    ) -> list[GroupedDataDispersionGapRescanIssue]:
        issues: list[GroupedDataDispersionGapRescanIssue] = []
        if result.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "release_boundary",
                    "RIGHTS_NOT_REVIEW_REQUIRED",
                    "gap_scan_result.json",
                    "rights_status must be REVIEW_REQUIRED.",
                )
            )
        if result.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "release_boundary",
                    "DB_IMPORT_NOT_BLOCKED",
                    "gap_scan_result.json",
                    "database_import_allowed must be False.",
                )
            )
        if result.get("canonical_snapshot_allowed") is not False:
            issues.append(
                self._issue(
                    "release_boundary",
                    "CANONICAL_SNAPSHOT_NOT_BLOCKED",
                    "gap_scan_result.json",
                    "canonical_snapshot_allowed must be False.",
                )
            )

        policy = contract.get("policy", {})
        if policy.get("external_lead_is_not_verified_data") is not True:
            issues.append(
                self._issue(
                    "release_boundary",
                    "EXTERNAL_LEAD_POLICY_VIOLATION",
                    "data_contract.json",
                    "external_lead_is_not_verified_data must be true.",
                )
            )
        if policy.get("raw_source_required_before_verification") is not True:
            issues.append(
                self._issue(
                    "release_boundary",
                    "RAW_SOURCE_POLICY_VIOLATION",
                    "data_contract.json",
                    "raw_source_required_before_verification must be true.",
                )
            )
        if policy.get("no_synthetic_gap_fill") is not True:
            issues.append(
                self._issue(
                    "release_boundary",
                    "SYNTHETIC_GAP_FILL_POLICY_VIOLATION",
                    "data_contract.json",
                    "no_synthetic_gap_fill must be true.",
                )
            )
        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[GroupedDataDispersionGapRescanIssue]:
        issues: list[GroupedDataDispersionGapRescanIssue] = []
        pdf_files = list(path.rglob("*.pdf"))
        if pdf_files:
            issues.append(
                self._issue(
                    "no_pdf_binaries",
                    "PDF_BINARY_PRESENT",
                    str(pdf_files[0]),
                    "Raw PDF binaries must not be present in gap scan directory.",
                )
            )
        return issues

    def _aggregate_hash(
        self, path: Path, contract: dict[str, Any]
    ) -> str | None:
        order = contract.get("semantic_files_order")
        if not isinstance(order, list):
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

    def _check_required_files(
        self, path: Path, issues: list[GroupedDataDispersionGapRescanIssue]
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
        self, path: Path, issues: list[GroupedDataDispersionGapRescanIssue]
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
        self, path: Path, issues: list[GroupedDataDispersionGapRescanIssue]
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
    ) -> GroupedDataDispersionGapRescanIssue:
        return GroupedDataDispersionGapRescanIssue(
            check=check, code=code, location=location, message=message
        )
