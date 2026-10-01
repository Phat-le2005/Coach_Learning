from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUALITY_AUDIT_PATH = (
    BACKEND_ROOT
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "quality_audit_v0_1"
)

EXPECTED_QUALITY_AUDIT_AGGREGATE_SHA256 = (
    "3953cb4035ecd4080d2928b46c1108cff4290356d4017dd1c44f088865e17a71"
)
EXPECTED_BASE_REPO_COMMIT = "aed14bf213ac9db65e820984f5a6c46ebabbe304"

SEMANTIC_FILES_ORDER = (
    "problem_type_density_audit.json",
    "source_diversity_audit.json",
    "source_acquisition_queue.json",
    "quality_gate.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "problem_type_density_audit.json": (
        "bf39e218c883131628c015b7e68d85830f53b6d757a1420aa018b77dd2f62922"
    ),
    "source_diversity_audit.json": (
        "17781cad9fcbd9fcee0da7d5c00b0f11fb486f2dd0e82f49db6b14798f3e678b"
    ),
    "source_acquisition_queue.json": (
        "320f11e49502da9d2f8745f3a0af723d10b88d105e791e8a5e1bfe83adc30eda"
    ),
    "quality_gate.json": (
        "7be81cb3111db8fb096a532010bc72000468d5db53398f52c4507cb32d09f149"
    ),
}

EXPECTED_QUEUE_STATUS = "INGESTION_REQUIRED_BINARY_SHA256_UNPINNED"


@dataclass(frozen=True, slots=True, order=True)
class QualityAuditIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class QualityAuditReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, Any]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    official_scope_coverage_gate: str
    diagnostic_density_gate: str
    source_diversity_gate: str
    new_chapter_ingestion_recommended: bool
    queue_items_count: int
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[QualityAuditIssue, ...]

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
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "official_scope_coverage_gate": self.official_scope_coverage_gate,
            "diagnostic_density_gate": self.diagnostic_density_gate,
            "source_diversity_gate": self.source_diversity_gate,
            "new_chapter_ingestion_recommended": self.new_chapter_ingestion_recommended,
            "queue_items_count": self.queue_items_count,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_allowed": self.production_release_allowed,
            "errors": [asdict(issue) for issue in self.errors],
        }


class QualityAuditValidator:
    """Validator for DATA-MATH12-041 density and diversity quality audit."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_QUALITY_AUDIT_PATH,
    ) -> QualityAuditReport:
        path = dataset_path.resolve()
        initial: list[QualityAuditIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        density = self._load_object(path / "problem_type_density_audit.json", initial)
        diversity = self._load_object(path / "source_diversity_audit.json", initial)
        queue = self._load_object(path / "source_acquisition_queue.json", initial)
        qgate = self._load_object(path / "quality_gate.json", initial)

        checks_to_errors: dict[str, list[QualityAuditIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "density_audit": self._validate_density_audit(density),
            "diversity_audit": self._validate_diversity_audit(diversity),
            "acquisition_queue": self._validate_acquisition_queue(queue),
            "quality_gate_invariants": self._validate_quality_gate(qgate),
            "critical_boundaries": self._validate_critical_boundaries(contract),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[QualityAuditIssue] = []
        if aggregate != EXPECTED_QUALITY_AUDIT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_QUALITY_AUDIT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_QUALITY_AUDIT_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-041 aggregate.",
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

        queue_items = queue.get("queue", [])
        counts = {
            "queue_items": len(queue_items),
            "audited_scopes": len(diversity.get("audited_sets", [])),
        }

        return QualityAuditReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            official_scope_coverage_gate=qgate.get("official_scope_coverage_gate", "UNKNOWN"),
            diagnostic_density_gate=qgate.get("diagnostic_density_gate", "UNKNOWN"),
            source_diversity_gate=qgate.get("source_diversity_gate", "UNKNOWN"),
            new_chapter_ingestion_recommended=bool(
                qgate.get("new_chapter_ingestion_recommended", True)
            ),
            queue_items_count=len(queue_items),
            canonical_write_allowed=bool(contract.get("canonical_write_allowed", True)),
            database_import_allowed=bool(contract.get("database_import_allowed", True)),
            production_release_allowed=bool(contract.get("production_release_allowed", True)),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[QualityAuditIssue]
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
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
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
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
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
        self, contract: dict[str, Any]
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
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

    def _validate_density_audit(
        self, density: dict[str, Any]
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
        thresholds = density.get("qa_thresholds", {})
        if thresholds.get("DIAGNOSTIC_MINIMUM_TARGET") != 5:
            issues.append(
                self._issue(
                    "density_audit",
                    "THRESHOLD_MISMATCH",
                    "problem_type_density_audit.json",
                    "DIAGNOSTIC_MINIMUM_TARGET must be 5.",
                )
            )
        chapters = density.get("chapters", {})
        for ch in ("DERIVATIVE_APPLICATIONS", "INTEGRALS", "OXYZ_CHAPTER", "GROUPED_DATA_STATISTICS", "PROBABILITY_CHAPTER"):
            if ch not in chapters:
                issues.append(
                    self._issue(
                        "density_audit",
                        "MISSING_CHAPTER_DENSITY",
                        f"problem_type_density_audit.json[{ch}]",
                        f"Missing density data for chapter {ch}.",
                    )
                )
        return issues

    def _validate_diversity_audit(
        self, diversity: dict[str, Any]
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
        target = diversity.get("qa_target", {})
        if target.get("minimum_independent_source_families") != 3:
            issues.append(
                self._issue(
                    "diversity_audit",
                    "TARGET_FAMILIES_MISMATCH",
                    "source_diversity_audit.json",
                    "minimum_independent_source_families must be 3.",
                )
            )
        if target.get("maximum_single_source_share") != 0.7:
            issues.append(
                self._issue(
                    "diversity_audit",
                    "TARGET_SHARE_MISMATCH",
                    "source_diversity_audit.json",
                    "maximum_single_source_share must be 0.7.",
                )
            )
        audited_sets = diversity.get("audited_sets", [])
        if len(audited_sets) < 6:
            issues.append(
                self._issue(
                    "diversity_audit",
                    "AUDITED_SETS_COUNT_LOW",
                    "source_diversity_audit.json",
                    f"Expected at least 6 audited sets, got {len(audited_sets)}.",
                )
            )
        return issues

    def _validate_acquisition_queue(
        self, queue_data: dict[str, Any]
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
        items = queue_data.get("queue", [])
        if len(items) != 5:
            issues.append(
                self._issue(
                    "acquisition_queue",
                    "QUEUE_LENGTH_MISMATCH",
                    "source_acquisition_queue.json",
                    f"Expected 5 acquisition queue items, got {len(items)}.",
                )
            )
        for i, item in enumerate(items):
            status = item.get("status")
            if status != EXPECTED_QUEUE_STATUS:
                issues.append(
                    self._issue(
                        "acquisition_queue",
                        "INVALID_QUEUE_STATUS",
                        f"source_acquisition_queue.json[{i}]",
                        f"Queue item must have status {EXPECTED_QUEUE_STATUS}, got {status!r}.",
                    )
                )
            # Must not contain sha256 or be treated as verified evidence
            if "source_pdf_sha256" in item:
                issues.append(
                    self._issue(
                        "acquisition_queue",
                        "PREMATURE_SHA_PINNING",
                        f"source_acquisition_queue.json[{i}]",
                        "Unpinned leads must not have source_pdf_sha256 set.",
                    )
                )
        return issues

    def _validate_quality_gate(
        self, qgate: dict[str, Any]
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
        if qgate.get("official_scope_coverage_gate") != "PASS_20_OF_20":
            issues.append(
                self._issue(
                    "quality_gate_invariants",
                    "OFFICIAL_SCOPE_GATE_MISMATCH",
                    "quality_gate.json",
                    "official_scope_coverage_gate must be PASS_20_OF_20.",
                )
            )
        if qgate.get("diagnostic_density_gate") != "FAIL_MORE_REAL_QUESTIONS_REQUIRED":
            issues.append(
                self._issue(
                    "quality_gate_invariants",
                    "DIAGNOSTIC_DENSITY_GATE_MISMATCH",
                    "quality_gate.json",
                    "diagnostic_density_gate must be FAIL_MORE_REAL_QUESTIONS_REQUIRED.",
                )
            )
        if qgate.get("source_diversity_gate") != "FAIL_IN_PROBABILITY_STATS_VECTOR_AND_DERIVATIVE":
            issues.append(
                self._issue(
                    "quality_gate_invariants",
                    "SOURCE_DIVERSITY_GATE_MISMATCH",
                    "quality_gate.json",
                    "source_diversity_gate must be FAIL_IN_PROBABILITY_STATS_VECTOR_AND_DERIVATIVE.",
                )
            )
        if qgate.get("new_chapter_ingestion_recommended") is not False:
            issues.append(
                self._issue(
                    "quality_gate_invariants",
                    "NEW_CHAPTER_INGESTION_NOT_FALSE",
                    "quality_gate.json",
                    "new_chapter_ingestion_recommended must be false.",
                )
            )
        if qgate.get("next_data_priority") != "DEPTH_AND_DIVERSITY_ONLY":
            issues.append(
                self._issue(
                    "quality_gate_invariants",
                    "NEXT_DATA_PRIORITY_MISMATCH",
                    "quality_gate.json",
                    "next_data_priority must be DEPTH_AND_DIVERSITY_ONLY.",
                )
            )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any]
    ) -> list[QualityAuditIssue]:
        issues: list[QualityAuditIssue] = []
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
        self, path: Path, issues: list[QualityAuditIssue]
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
    ) -> QualityAuditIssue:
        return QualityAuditIssue(
            check=check, code=code, location=location, message=message
        )
