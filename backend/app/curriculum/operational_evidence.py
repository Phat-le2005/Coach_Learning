from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.curriculum.production_gate import (
    DEFAULT_PRODUCTION_GATE_PATH,
    EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256,
    ProductionGateValidator,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPERATIONAL_EVIDENCE_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "operational_evidence_v0_1"
)

EXPECTED_OPERATIONAL_EVIDENCE_AGGREGATE_SHA256 = (
    "f1722f394dd943f5ed437e29a2e05f67c85886e6d446fe260df963b864524c6a"
)
EXPECTED_BASE_REPO_COMMIT = "30bb2625128fa38a71fbbc8481e8589672027632"

SEMANTIC_FILES_ORDER = (
    "ci_evidence.json",
    "gate_refresh.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "ci_evidence.json": (
        "436b31208750fc6d7061c0947c80042188433c6fbdc842faea64c5a0795a50da"
    ),
    "gate_refresh.json": (
        "0d3bde9a97a92670f6d9a2c265a73258ff524e0b6885f21f0b2702c25e6ba314"
    ),
}

EXPECTED_CI_FACTS = {
    "run_id": 36817312571,
    "job_id": 110225088413,
    "conclusion": "success",
    "python_version": "3.12",
    "passed": 749,
    "failed": 0,
    "skipped": 1,
}

EXPECTED_REFRESHED_GATES = {
    "official_core_scope": "PASS_20_OF_20",
    "canonical_snapshot_candidate": "PASS_READY_FOR_EXPLICIT_REVIEW",
    "ci_regression": "PASS_749_TESTS",
    "vector_zero_evidence": "PASS_ZERO",
    "derivative_zero_evidence": "FAIL_ONE_REMAINING_PARAMETER_MONOTONICITY",
    "diagnostic_problem_type_density": "FAIL_MORE_REAL_QUESTIONS_REQUIRED",
    "source_diversity": "FAIL_PROBABILITY_STATS_AND_OTHER_THIN_SETS",
    "rights_review": "FAIL_PENDING_REVIEW",
    "canonical_activation": "BLOCKED",
    "postgres_import": "BLOCKED",
    "production_release": "BLOCKED",
}


@dataclass(frozen=True, slots=True, order=True)
class OperationalEvidenceIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class OperationalEvidenceReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    gates: dict[str, str]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    ci_evidence_state: str
    workflow_run_id: int | None
    historical_data042_immutable: bool
    rights_status: str
    production_ready: bool
    canonical_activation_blocked: bool
    postgres_import_blocked: bool
    production_release_blocked: bool
    errors: tuple[OperationalEvidenceIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "gates": self.gates,
            "base_repo_commit": self.base_repo_commit,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "ci_evidence_state": self.ci_evidence_state,
            "workflow_run_id": self.workflow_run_id,
            "historical_data042_immutable": self.historical_data042_immutable,
            "rights_status": self.rights_status,
            "production_ready": self.production_ready,
            "canonical_activation_blocked": self.canonical_activation_blocked,
            "postgres_import_blocked": self.postgres_import_blocked,
            "production_release_blocked": self.production_release_blocked,
            "errors": [asdict(issue) for issue in self.errors],
        }


class OperationalEvidenceValidator:
    """Validator for DATA-MATH12-044 operational CI evidence refresh."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_OPERATIONAL_EVIDENCE_PATH,
        *,
        data042_path: Path = DEFAULT_PRODUCTION_GATE_PATH,
    ) -> OperationalEvidenceReport:
        path = dataset_path.resolve()
        initial: list[OperationalEvidenceIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        ci_ev = self._load_object(path / "ci_evidence.json", initial)
        gate_refresh = self._load_object(path / "gate_refresh.json", initial)

        checks_to_errors: dict[str, list[OperationalEvidenceIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract, ci_ev),
            "historical_data042_immutability": self._validate_historical_data042(data042_path),
            "ci_evidence_integrity": self._validate_ci_evidence(ci_ev),
            "gate_refresh_integrity": self._validate_gate_refresh(gate_refresh),
            "critical_boundaries": self._validate_critical_boundaries(contract, ci_ev, gate_refresh),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[OperationalEvidenceIssue] = []
        if aggregate != EXPECTED_OPERATIONAL_EVIDENCE_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_OPERATIONAL_EVIDENCE_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_OPERATIONAL_EVIDENCE_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-044 aggregate.",
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

        wf = ci_ev.get("workflow", {})
        gates = gate_refresh.get("gates_after_043_and_green_ci", {})
        historical_ok = checks.get("historical_data042_immutability", False)

        is_activation_blocked = gates.get("canonical_activation") == "BLOCKED"
        is_import_blocked = gates.get("postgres_import") == "BLOCKED"
        is_release_blocked = gates.get("production_release") == "BLOCKED"

        return OperationalEvidenceReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            gates=gates,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            ci_evidence_state=ci_ev.get("ci_evidence_current_state", "UNKNOWN"),
            workflow_run_id=wf.get("run_id"),
            historical_data042_immutable=historical_ok,
            rights_status=ci_ev.get("rights_review_state", "UNKNOWN"),
            production_ready=False,
            canonical_activation_blocked=is_activation_blocked,
            postgres_import_blocked=is_import_blocked,
            production_release_blocked=is_release_blocked,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[OperationalEvidenceIssue]
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
    ) -> list[OperationalEvidenceIssue]:
        issues: list[OperationalEvidenceIssue] = []
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
    ) -> list[OperationalEvidenceIssue]:
        issues: list[OperationalEvidenceIssue] = []
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

    def _validate_base_repo_commit(
        self, contract: dict[str, Any], ci_ev: dict[str, Any]
    ) -> list[OperationalEvidenceIssue]:
        issues: list[OperationalEvidenceIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )
        if ci_ev.get("github_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "GITHUB_COMMIT_MISMATCH",
                    "ci_evidence.json",
                    f"Expected github_commit {EXPECTED_BASE_REPO_COMMIT}, got {ci_ev.get('github_commit')!r}.",
                )
            )
        return issues

    def _validate_historical_data042(
        self, data042_path: Path
    ) -> list[OperationalEvidenceIssue]:
        issues: list[OperationalEvidenceIssue] = []
        if not data042_path.is_dir():
            issues.append(
                self._issue(
                    "historical_data042_immutability",
                    "DATA042_DIR_MISSING",
                    str(data042_path),
                    "DATA-MATH12-042 directory is missing.",
                )
            )
            return issues

        rep = ProductionGateValidator().validate(dataset_path=data042_path)
        if not rep.is_valid:
            issues.append(
                self._issue(
                    "historical_data042_immutability",
                    "DATA042_NOT_VALID",
                    "production_gate_v0_1",
                    f"Historical DATA-042 dataset was mutated or invalid: {rep.errors}",
                )
            )
        if rep.aggregate_semantic_sha256 != EXPECTED_PRODUCTION_GATE_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "historical_data042_immutability",
                    "DATA042_AGGREGATE_MUTATED",
                    "production_gate_v0_1",
                    "Historical DATA-042 aggregate was mutated.",
                )
            )
        if rep.gates.get("ci_evidence") != "FAIL_NO_WORKFLOW_RUNS":
            issues.append(
                self._issue(
                    "historical_data042_immutability",
                    "DATA042_CI_EVIDENCE_MUTATED",
                    "production_gate_v0_1",
                    "Historical DATA-042 must retain ci_evidence == FAIL_NO_WORKFLOW_RUNS.",
                )
            )
        return issues

    def _validate_ci_evidence(
        self, ci_ev: dict[str, Any]
    ) -> list[OperationalEvidenceIssue]:
        issues: list[OperationalEvidenceIssue] = []
        wf = ci_ev.get("workflow", {})

        if wf.get("run_id") != EXPECTED_CI_FACTS["run_id"]:
            issues.append(
                self._issue(
                    "ci_evidence_integrity",
                    "RUN_ID_MISMATCH",
                    "ci_evidence.json",
                    f"Expected run_id {EXPECTED_CI_FACTS['run_id']}, got {wf.get('run_id')}.",
                )
            )
        if wf.get("job_id") != EXPECTED_CI_FACTS["job_id"]:
            issues.append(
                self._issue(
                    "ci_evidence_integrity",
                    "JOB_ID_MISMATCH",
                    "ci_evidence.json",
                    f"Expected job_id {EXPECTED_CI_FACTS['job_id']}, got {wf.get('job_id')}.",
                )
            )
        if wf.get("conclusion") != EXPECTED_CI_FACTS["conclusion"]:
            issues.append(
                self._issue(
                    "ci_evidence_integrity",
                    "CONCLUSION_MISMATCH",
                    "ci_evidence.json",
                    "Workflow conclusion must be success.",
                )
            )
        if wf.get("python_version") != EXPECTED_CI_FACTS["python_version"]:
            issues.append(
                self._issue(
                    "ci_evidence_integrity",
                    "PYTHON_VERSION_MISMATCH",
                    "ci_evidence.json",
                    "python_version must be 3.12.",
                )
            )

        res = wf.get("test_result", {})
        if res.get("passed") != EXPECTED_CI_FACTS["passed"] or res.get("failed") != EXPECTED_CI_FACTS["failed"]:
            issues.append(
                self._issue(
                    "ci_evidence_integrity",
                    "TEST_COUNTS_MISMATCH",
                    "ci_evidence.json",
                    f"Expected 749 passed and 0 failed, got passed={res.get('passed')}, failed={res.get('failed')}.",
                )
            )

        if ci_ev.get("ci_evidence_current_state") != "PASS_GREEN_RUN_CAPTURED":
            issues.append(
                self._issue(
                    "ci_evidence_integrity",
                    "CI_STATE_MISMATCH",
                    "ci_evidence.json",
                    "ci_evidence_current_state must be PASS_GREEN_RUN_CAPTURED.",
                )
            )

        return issues

    def _validate_gate_refresh(
        self, gate_refresh: dict[str, Any]
    ) -> list[OperationalEvidenceIssue]:
        issues: list[OperationalEvidenceIssue] = []
        gates = gate_refresh.get("gates_after_043_and_green_ci", {})

        for gname, expected in EXPECTED_REFRESHED_GATES.items():
            actual = gates.get(gname)
            if actual != expected:
                issues.append(
                    self._issue(
                        "gate_refresh_integrity",
                        f"{gname.upper()}_GATE_MISMATCH",
                        f"gate_refresh.json[{gname}]",
                        f"Expected {gname} to be {expected}, got {actual}.",
                    )
                )

        return issues

    def _validate_critical_boundaries(
        self,
        contract: dict[str, Any],
        ci_ev: dict[str, Any],
        gate_refresh: dict[str, Any],
    ) -> list[OperationalEvidenceIssue]:
        issues: list[OperationalEvidenceIssue] = []
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

        if ci_ev.get("rights_review_state") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "RIGHTS_NOT_REVIEW_REQUIRED",
                    "ci_evidence.json",
                    "rights_review_state must be REVIEW_REQUIRED.",
                )
            )
        if ci_ev.get("canonical_activation_state") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "ACTIVATION_NOT_BLOCKED",
                    "ci_evidence.json",
                    "canonical_activation_state must be BLOCKED.",
                )
            )
        if ci_ev.get("database_import_state") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DB_IMPORT_NOT_BLOCKED",
                    "ci_evidence.json",
                    "database_import_state must be BLOCKED.",
                )
            )
        if ci_ev.get("production_release_state") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "RELEASE_NOT_BLOCKED",
                    "ci_evidence.json",
                    "production_release_state must be BLOCKED.",
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
        self, path: Path, issues: list[OperationalEvidenceIssue]
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
    ) -> OperationalEvidenceIssue:
        return OperationalEvidenceIssue(
            check=check, code=code, location=location, message=message
        )
