from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "data_completion_snapshot_v0_1"
)

EXPECTED_DATA_COMPLETION_SNAPSHOT_AGGREGATE_SHA256 = (
    "4aef04ea5711d70a7e47d7511ed213929cacdfee546a54f874ad204e39793310"
)
EXPECTED_BASE_REPO_COMMIT = "446abb9c2fde1fd9b065e0d8b42240c7e738da1f"

SEMANTIC_FILES_ORDER = (
    "completion_snapshot.json",
    "definition_of_done.json",
)
REQUIRED_FILES = (
    *SEMANTIC_FILES_ORDER,
    "data_contract.json",
    "README.md",
)

EXPECTED_SEMANTIC_HASHES = {
    "completion_snapshot.json": (
        "1a5a8822cdcdab9053ad5244ad705bc3eaee07b6ef608d4e24956b38fb94550f"
    ),
    "definition_of_done.json": (
        "ea3a42db22fe66123dbbc102025673aebdab246eeac511866a7ea8794aa36f5e"
    ),
}


@dataclass(frozen=True, order=True)
class DataCompletionSnapshotIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True)
class DataCompletionSnapshotReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str
    aggregate_semantic_sha256: str
    completion_status: str
    official_core_requirements: str
    canonical_candidate_version: str
    root_canonical_activation: str
    minimum_demo_data_done: bool
    official_curriculum_data_done: bool
    adaptive_production_data_done: bool
    rights_status: str
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[DataCompletionSnapshotIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS" and len(self.errors) == 0

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["is_valid"] = self.is_valid
        return result


class DataCompletionSnapshotValidator:
    """Validates DATA-MATH12-050 data completion snapshot."""

    def validate(
        self,
        dataset_path: Path | str | None = None,
    ) -> DataCompletionSnapshotReport:
        path = (
            Path(dataset_path)
            if dataset_path is not None
            else DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH
        )

        initial: list[DataCompletionSnapshotIssue] = []
        self._check_required_files(path, initial)

        contract = self._load_object(path / "data_contract.json", initial)
        snapshot_data = self._load_object(
            path / "completion_snapshot.json", initial
        )
        dod_data = self._load_object(
            path / "definition_of_done.json", initial
        )

        checks_to_errors: dict[str, list[DataCompletionSnapshotIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "completion_snapshot_integrity": (
                self._validate_completion_snapshot(snapshot_data)
            ),
            "definition_of_done_integrity": (
                self._validate_definition_of_done(dod_data)
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                contract, snapshot_data
            ),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[DataCompletionSnapshotIssue] = []
        if aggregate != EXPECTED_DATA_COMPLETION_SNAPSHOT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_DATA_COMPLETION_SNAPSHOT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_DATA_COMPLETION_SNAPSHOT_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-050 aggregate.",
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

        curric = snapshot_data.get("curriculum", {})
        graph = curric.get("canonical_candidate_graph", {})
        gates = snapshot_data.get("production_gates", {})

        counts = {
            "graph_chapters": graph.get("chapters", 0),
            "graph_topics": graph.get("topics", 0),
            "graph_problem_types": graph.get("problem_types", 0),
            "graph_concepts": graph.get("concepts", 0),
            "graph_learning_outcomes": graph.get("learning_outcomes", 0),
            "remaining_dod_items_count": len(
                dod_data.get("remaining_to_adaptive_production_done", [])
            ),
        }

        return DataCompletionSnapshotReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit", ""),
            aggregate_semantic_sha256=aggregate,
            completion_status=str(snapshot_data.get("status", "")),
            official_core_requirements=str(
                curric.get("official_core_requirements", "")
            ),
            canonical_candidate_version=str(
                curric.get("canonical_candidate_version", "")
            ),
            root_canonical_activation=str(
                curric.get("root_canonical_activation", "")
            ),
            minimum_demo_data_done=bool(
                dod_data.get("minimum_demo_data_done", False)
            ),
            official_curriculum_data_done=bool(
                dod_data.get("official_curriculum_data_done", False)
            ),
            adaptive_production_data_done=bool(
                dod_data.get("adaptive_production_data_done", True)
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
        self, path: Path, issues: list[DataCompletionSnapshotIssue]
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
    ) -> list[DataCompletionSnapshotIssue]:
        issues: list[DataCompletionSnapshotIssue] = []
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
    ) -> list[DataCompletionSnapshotIssue]:
        issues: list[DataCompletionSnapshotIssue] = []
        if contract.get("dataset_code") != "DATA-MATH12-050":
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "DATASET_CODE_MISMATCH",
                    "data_contract.json",
                    f"Expected dataset_code DATA-MATH12-050, got {contract.get('dataset_code')!r}.",
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
    ) -> list[DataCompletionSnapshotIssue]:
        issues: list[DataCompletionSnapshotIssue] = []
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

    def _validate_completion_snapshot(
        self, data: dict[str, Any]
    ) -> list[DataCompletionSnapshotIssue]:
        issues: list[DataCompletionSnapshotIssue] = []
        expected_status = (
            "GRADE12_MATH_DATA_BREADTH_COMPLETE_DEPTH_HARDENING_REMAINS"
        )
        if data.get("status") != expected_status:
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "STATUS_MISMATCH",
                    "completion_snapshot.json",
                    f"status must be {expected_status}.",
                )
            )

        curric = data.get("curriculum", {})
        if curric.get("official_core_requirements") != "20/20":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "CORE_REQUIREMENTS_MISMATCH",
                    "completion_snapshot.json",
                    "official_core_requirements must be 20/20.",
                )
            )
        if curric.get("canonical_candidate_version") != "1.2.0":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "CANDIDATE_VERSION_MISMATCH",
                    "completion_snapshot.json",
                    "canonical_candidate_version must be 1.2.0.",
                )
            )
        graph = curric.get("canonical_candidate_graph", {})
        expected_graph = {
            "chapters": 5,
            "topics": 24,
            "problem_types": 75,
            "concepts": 89,
            "learning_outcomes": 34,
        }
        if graph != expected_graph:
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "GRAPH_COUNTS_MISMATCH",
                    "completion_snapshot.json",
                    f"canonical_candidate_graph must be {expected_graph}, got {graph}.",
                )
            )
        if curric.get("root_canonical_activation") != "NOT_YET_ACTIVATED":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "ACTIVATION_STATUS_MISMATCH",
                    "completion_snapshot.json",
                    "root_canonical_activation must be NOT_YET_ACTIVATED.",
                )
            )

        val = data.get("validation", {})
        if val.get("ci_status") != "GREEN":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "CI_STATUS_NOT_GREEN",
                    "completion_snapshot.json",
                    "ci_status must be GREEN.",
                )
            )

        gates = data.get("production_gates", {})
        if gates.get("official_scope") != "PASS":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "GATE_OFFICIAL_SCOPE_NOT_PASS",
                    "completion_snapshot.json",
                    "production_gates.official_scope must be PASS.",
                )
            )
        if gates.get("adaptive_density") != "FAIL":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "GATE_ADAPTIVE_DENSITY_NOT_FAIL",
                    "completion_snapshot.json",
                    "production_gates.adaptive_density must be FAIL.",
                )
            )
        if gates.get("canonical_activation") != "BLOCKED":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "GATE_CANONICAL_ACTIVATION_NOT_BLOCKED",
                    "completion_snapshot.json",
                    "production_gates.canonical_activation must be BLOCKED.",
                )
            )
        if gates.get("postgres_import") != "BLOCKED":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "GATE_POSTGRES_IMPORT_NOT_BLOCKED",
                    "completion_snapshot.json",
                    "production_gates.postgres_import must be BLOCKED.",
                )
            )
        if gates.get("production_release") != "BLOCKED":
            issues.append(
                self._issue(
                    "completion_snapshot_integrity",
                    "GATE_PRODUCTION_RELEASE_NOT_BLOCKED",
                    "completion_snapshot.json",
                    "production_gates.production_release must be BLOCKED.",
                )
            )

        return issues

    def _validate_definition_of_done(
        self, data: dict[str, Any]
    ) -> list[DataCompletionSnapshotIssue]:
        issues: list[DataCompletionSnapshotIssue] = []
        if data.get("minimum_demo_data_done") is not True:
            issues.append(
                self._issue(
                    "definition_of_done_integrity",
                    "DEMO_DATA_NOT_DONE",
                    "definition_of_done.json",
                    "minimum_demo_data_done must be true.",
                )
            )
        if data.get("official_curriculum_data_done") is not True:
            issues.append(
                self._issue(
                    "definition_of_done_integrity",
                    "CURRICULUM_DATA_NOT_DONE",
                    "definition_of_done.json",
                    "official_curriculum_data_done must be true.",
                )
            )
        # Crucial check: adaptive_production_data_done MUST be False!
        if data.get("adaptive_production_data_done") is not False:
            issues.append(
                self._issue(
                    "definition_of_done_integrity",
                    "ADAPTIVE_PRODUCTION_FALSELY_DONE",
                    "definition_of_done.json",
                    "adaptive_production_data_done must be false (depth hardening remains).",
                )
            )
        rem = data.get("remaining_to_adaptive_production_done", [])
        if len(rem) != 6:
            issues.append(
                self._issue(
                    "definition_of_done_integrity",
                    "REMAINING_ITEMS_COUNT_MISMATCH",
                    "definition_of_done.json",
                    f"Expected 6 remaining items to adaptive production done, got {len(rem)}.",
                )
            )

        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], snapshot_data: dict[str, Any]
    ) -> list[DataCompletionSnapshotIssue]:
        issues: list[DataCompletionSnapshotIssue] = []
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
        gates = snapshot_data.get("production_gates", {})
        if gates.get("rights") != "REVIEW_REQUIRED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "GATE_RIGHTS_NOT_REVIEW_REQUIRED",
                    "completion_snapshot.json",
                    "production_gates.rights must be REVIEW_REQUIRED.",
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
        self, path: Path, issues: list[DataCompletionSnapshotIssue]
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
    ) -> DataCompletionSnapshotIssue:
        return DataCompletionSnapshotIssue(
            check=check, code=code, location=location, message=message
        )
