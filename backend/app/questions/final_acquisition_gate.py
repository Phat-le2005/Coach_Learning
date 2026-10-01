from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINAL_ACQUISITION_GATE_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "final_acquisition_gate_v0_1"
)

EXPECTED_FINAL_ACQUISITION_GATE_AGGREGATE_SHA256 = (
    "e8f614c8d4eda47acb0f68f42b926ac7d0c15682d07fa88ea98625263c1f9a67"
)
EXPECTED_BASE_REPO_COMMIT = "446abb9c2fde1fd9b065e0d8b42240c7e738da1f"

SEMANTIC_FILES_ORDER = (
    "acquisition_gate.json",
    "remaining_queue.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES_ORDER,
    "data_contract.json",
    "README.md",
)

EXPECTED_SEMANTIC_HASHES = {
    "acquisition_gate.json": (
        "b63fc2a083dd22d5a60fd8d147ecf338933541ea9f3938376ca191b48b875977"
    ),
    "remaining_queue.json": (
        "a8642d7dbe52482c8b8ad26ec11be566f9ed62cb5c74babbfe7cc9c92469b483"
    ),
}


@dataclass(frozen=True, order=True)
class FinalAcquisitionGateIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True)
class FinalAcquisitionGateReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str
    aggregate_semantic_sha256: str
    data_acquisition_mode: str
    broad_expansion_blocked: bool
    remaining_queue_items: list[str]
    rights_status: str
    canonical_activation_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[FinalAcquisitionGateIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS" and len(self.errors) == 0

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["is_valid"] = self.is_valid
        return result


class FinalAcquisitionGateValidator:
    """Validates DATA-MATH12-049 targeted acquisition freeze and gate."""

    def validate(
        self,
        dataset_path: Path | str | None = None,
    ) -> FinalAcquisitionGateReport:
        path = (
            Path(dataset_path)
            if dataset_path is not None
            else DEFAULT_FINAL_ACQUISITION_GATE_PATH
        )

        initial: list[FinalAcquisitionGateIssue] = []
        self._check_required_files(path, initial)

        contract = self._load_object(path / "data_contract.json", initial)
        gate_data = self._load_object(path / "acquisition_gate.json", initial)
        queue_data = self._load_object(path / "remaining_queue.json", initial)

        checks_to_errors: dict[str, list[FinalAcquisitionGateIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "acquisition_gate_integrity": self._validate_acquisition_gate(
                gate_data
            ),
            "remaining_queue_integrity": self._validate_remaining_queue(
                queue_data
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                contract, gate_data
            ),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[FinalAcquisitionGateIssue] = []
        if aggregate != EXPECTED_FINAL_ACQUISITION_GATE_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_FINAL_ACQUISITION_GATE_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_FINAL_ACQUISITION_GATE_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-049 aggregate.",
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

        queue_items = [
            item.get("target", "") for item in queue_data.get("items", [])
        ]

        counts = {
            "allowed_new_data_count": len(gate_data.get("allowed_new_data", [])),
            "blocked_policies_count": len(gate_data.get("blocked", [])),
            "remaining_queue_items_count": len(queue_items),
        }

        return FinalAcquisitionGateReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit", ""),
            aggregate_semantic_sha256=aggregate,
            data_acquisition_mode=str(
                gate_data.get("data_acquisition_mode", "")
            ),
            broad_expansion_blocked=not bool(
                gate_data.get("broad_web_scraping_or_new_chapter_expansion", True)
            ),
            remaining_queue_items=queue_items,
            rights_status=contract.get("rights_status", "UNKNOWN"),
            canonical_activation_allowed=bool(
                gate_data.get("canonical_activation_allowed", True)
            ),
            database_import_allowed=bool(
                gate_data.get("database_import_allowed", True)
            ),
            production_release_allowed=bool(
                gate_data.get("production_release_allowed", True)
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[FinalAcquisitionGateIssue]
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
    ) -> list[FinalAcquisitionGateIssue]:
        issues: list[FinalAcquisitionGateIssue] = []
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
    ) -> list[FinalAcquisitionGateIssue]:
        issues: list[FinalAcquisitionGateIssue] = []
        if contract.get("dataset_code") != "DATA-MATH12-049":
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "DATASET_CODE_MISMATCH",
                    "data_contract.json",
                    f"Expected dataset_code DATA-MATH12-049, got {contract.get('dataset_code')!r}.",
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
    ) -> list[FinalAcquisitionGateIssue]:
        issues: list[FinalAcquisitionGateIssue] = []
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

    def _validate_acquisition_gate(
        self, data: dict[str, Any]
    ) -> list[FinalAcquisitionGateIssue]:
        issues: list[FinalAcquisitionGateIssue] = []
        if data.get("data_acquisition_mode") != "TARGETED_ONLY":
            issues.append(
                self._issue(
                    "acquisition_gate_integrity",
                    "MODE_MISMATCH",
                    "acquisition_gate.json",
                    "data_acquisition_mode must be TARGETED_ONLY.",
                )
            )
        if data.get("broad_web_scraping_or_new_chapter_expansion") is not False:
            issues.append(
                self._issue(
                    "acquisition_gate_integrity",
                    "BROAD_EXPANSION_NOT_FALSE",
                    "acquisition_gate.json",
                    "broad_web_scraping_or_new_chapter_expansion must be false.",
                )
            )

        blocked = data.get("blocked", [])
        expected_blocked_items = [
            "synthetic gap fill",
            "unhashed external source promoted as practice-ready",
            "duplicate questions counted as depth",
            "adding Grade 11 exponential-logarithm into Grade 12 core",
            "new curriculum chapter expansion",
            "database import before activation/review",
        ]
        for b in expected_blocked_items:
            if b not in blocked:
                issues.append(
                    self._issue(
                        "acquisition_gate_integrity",
                        "BLOCKED_POLICY_MISSING",
                        "acquisition_gate.json",
                        f"Blocked policies must include '{b}'.",
                    )
                )

        return issues

    def _validate_remaining_queue(
        self, data: dict[str, Any]
    ) -> list[FinalAcquisitionGateIssue]:
        issues: list[FinalAcquisitionGateIssue] = []
        items = data.get("items", [])
        if len(items) != 4:
            issues.append(
                self._issue(
                    "remaining_queue_integrity",
                    "ITEMS_COUNT_MISMATCH",
                    "remaining_queue.json",
                    f"Expected exactly 4 remaining queue items, got {len(items)}.",
                )
            )
            return issues

        targets = {item.get("target"): item for item in items}
        for expected_target in (
            "PARAMETER_MONOTONICITY",
            "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
            "PARAMETER_FROM_GROUPED_VARIANCE_SD",
            "PROBABILITY_DIVERSITY",
        ):
            if expected_target not in targets:
                issues.append(
                    self._issue(
                        "remaining_queue_integrity",
                        "TARGET_MISSING",
                        "remaining_queue.json",
                        f"Missing queue target {expected_target}.",
                    )
                )

        # Check statuses
        if (
            targets.get("PARAMETER_MONOTONICITY", {}).get("status")
            != "WEB_REVIEWED_BINARY_PIN_REQUIRED"
        ):
            issues.append(
                self._issue(
                    "remaining_queue_integrity",
                    "STATUS_MISMATCH",
                    "PARAMETER_MONOTONICITY",
                    "status must be WEB_REVIEWED_BINARY_PIN_REQUIRED.",
                )
            )
        if (
            targets.get("MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS", {}).get("status")
            != "WEB_REVIEWED_BINARY_PIN_REQUIRED"
        ):
            issues.append(
                self._issue(
                    "remaining_queue_integrity",
                    "STATUS_MISMATCH",
                    "MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS",
                    "status must be WEB_REVIEWED_BINARY_PIN_REQUIRED.",
                )
            )
        if (
            targets.get("PARAMETER_FROM_GROUPED_VARIANCE_SD", {}).get("status")
            != "REAL_SOURCE_STILL_REQUIRED"
        ):
            issues.append(
                self._issue(
                    "remaining_queue_integrity",
                    "STATUS_MISMATCH",
                    "PARAMETER_FROM_GROUPED_VARIANCE_SD",
                    "status must be REAL_SOURCE_STILL_REQUIRED.",
                )
            )
        if (
            targets.get("PROBABILITY_DIVERSITY", {}).get("status")
            != "ONE_MORE_NON_DOMINANT_PINNED_UNIT_REQUIRED_TO_PASS_70_PERCENT_GATE"
        ):
            issues.append(
                self._issue(
                    "remaining_queue_integrity",
                    "STATUS_MISMATCH",
                    "PROBABILITY_DIVERSITY",
                    "status must be ONE_MORE_NON_DOMINANT_PINNED_UNIT_REQUIRED_TO_PASS_70_PERCENT_GATE.",
                )
            )

        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], gate_data: dict[str, Any]
    ) -> list[FinalAcquisitionGateIssue]:
        issues: list[FinalAcquisitionGateIssue] = []
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
        if gate_data.get("canonical_activation_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_ACTIVATION_NOT_BLOCKED",
                    "acquisition_gate.json",
                    "canonical_activation_allowed must be false.",
                )
            )
        if gate_data.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_GATE_NOT_BLOCKED",
                    "acquisition_gate.json",
                    "database_import_allowed must be false.",
                )
            )
        if gate_data.get("production_release_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "PRODUCTION_RELEASE_GATE_NOT_BLOCKED",
                    "acquisition_gate.json",
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
        if gate_data.get("rights_status") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "GATE_RIGHTS_STATUS_NOT_REVIEW_REQUIRED",
                    "acquisition_gate.json",
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
        self, path: Path, issues: list[FinalAcquisitionGateIssue]
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
    ) -> FinalAcquisitionGateIssue:
        return FinalAcquisitionGateIssue(
            check=check, code=code, location=location, message=message
        )
