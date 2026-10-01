from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIAGNOSTIC_GRAPH_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "diagnostic_graph_v0_1"
)
DEFAULT_SNAPSHOT_DIR = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "promotion"
    / "full_scope_v1_2_0_candidate"
    / "generated_snapshot"
)

EXPECTED_DIAGNOSTIC_GRAPH_AGGREGATE_SHA256 = (
    "1695f2c1740747e52a976dd48acefa87a8ff70fbbf207e68d7c858ab1adc8058"
)
EXPECTED_BASE_REPO_COMMIT = "aed14bf213ac9db65e820984f5a6c46ebabbe304"
EXPECTED_BASE_CURRICULUM_FINGERPRINT = (
    "2cad0c70f89d4d95ba3db2aaac194f0ddd9ad834e1b9014a6bbbe49bc1d7ec93"
)

EXPECTED_COUNTS = {
    "misconceptions": 26,
    "problem_type_misconceptions": 39,
    "misconception_remediation_concepts": 64,
}

SEMANTIC_FILES_ORDER = (
    "diagnostic_manifest.json",
    "misconceptions.json",
    "problem_type_misconceptions.json",
    "misconception_remediation_concepts.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "diagnostic_manifest.json": (
        "4a1bee1c1f3a8d36095f797d981103f2df4daf6b39fdd83ff5f6227b7e6990c4"
    ),
    "misconceptions.json": (
        "2caf27066801b75fda2cd0d735ead3a47b154539c4768f3bdfbd9be91c462575"
    ),
    "problem_type_misconceptions.json": (
        "0697310c9396ca08be738c47e608ad1e54d4d6dfb6490835d3323c702c8d30aa"
    ),
    "misconception_remediation_concepts.json": (
        "b1b050f6ae9f716b81d9f8cb385fb477ff0743e587692d0f4dcedf45fbba160a"
    ),
}


class MisconceptionNode(BaseModel):
    code: str
    chapter_code: str
    name: str
    description: str
    remediation_concepts: list[str] = Field(default_factory=list)


class ProblemTypeMisconceptionLink(BaseModel):
    problem_type_code: str
    misconception_code: str
    relation_type: str = "MAY_INDICATE"
    weight: float = 1.0


class MisconceptionRemediationConceptLink(BaseModel):
    misconception_code: str
    concept_code: str
    relation_type: str = "REMEDIATE_WITH"
    priority: int = 1


@dataclass(frozen=True, slots=True, order=True)
class DiagnosticGraphIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class DiagnosticGraphReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    base_curriculum_fingerprint: str | None
    automatic_student_diagnosis_allowed: bool
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[DiagnosticGraphIssue, ...]

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
            "base_curriculum_fingerprint": self.base_curriculum_fingerprint,
            "automatic_student_diagnosis_allowed": self.automatic_student_diagnosis_allowed,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_allowed": self.production_release_allowed,
            "errors": [asdict(issue) for issue in self.errors],
        }


class DiagnosticGraphValidator:
    """Validator for DATA-MATH12-040 diagnostic misconception graph."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_DIAGNOSTIC_GRAPH_PATH,
        *,
        snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    ) -> DiagnosticGraphReport:
        path = dataset_path.resolve()
        initial: list[DiagnosticGraphIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        manifest = self._load_object(path / "diagnostic_manifest.json", initial)

        misconceptions = self._load_list(path / "misconceptions.json", initial)
        pt_links = self._load_list(path / "problem_type_misconceptions.json", initial)
        remediation_links = self._load_list(
            path / "misconception_remediation_concepts.json", initial
        )

        checks_to_errors: dict[str, list[DiagnosticGraphIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract),
            "manifest_invariants": self._validate_manifest(manifest),
            "misconceptions_schema": self._validate_misconceptions(misconceptions),
            "pt_links_schema": self._validate_pt_links(pt_links),
            "remediation_links_schema": self._validate_remediation_links(remediation_links),
            "referential_integrity": self._validate_referential_integrity(
                misconceptions, pt_links, remediation_links, snapshot_dir
            ),
            "inference_policy_guard": self._validate_inference_policy(manifest),
            "critical_boundaries": self._validate_critical_boundaries(contract, manifest),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[DiagnosticGraphIssue] = []
        if aggregate != EXPECTED_DIAGNOSTIC_GRAPH_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_DIAGNOSTIC_GRAPH_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_DIAGNOSTIC_GRAPH_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-040 aggregate.",
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

        counts = {
            "misconceptions": len(misconceptions),
            "problem_type_misconceptions": len(pt_links),
            "misconception_remediation_concepts": len(remediation_links),
        }

        inf_policy = manifest.get("inference_policy", {})
        auto_diag = bool(inf_policy.get("automatic_student_diagnosis_allowed", True))

        return DiagnosticGraphReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            base_curriculum_fingerprint=manifest.get("base_curriculum_fingerprint"),
            automatic_student_diagnosis_allowed=auto_diag,
            canonical_write_allowed=bool(contract.get("canonical_write_allowed", True)),
            database_import_allowed=bool(contract.get("database_import_allowed", True)),
            production_release_allowed=bool(contract.get("production_release_allowed", True)),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[DiagnosticGraphIssue]
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
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
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
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
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
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
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

    def _validate_manifest(
        self, manifest: dict[str, Any]
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
        if manifest.get("base_curriculum_fingerprint") != EXPECTED_BASE_CURRICULUM_FINGERPRINT:
            issues.append(
                self._issue(
                    "manifest_invariants",
                    "FINGERPRINT_MISMATCH",
                    "diagnostic_manifest.json",
                    f"Expected fingerprint {EXPECTED_BASE_CURRICULUM_FINGERPRINT}, got {manifest.get('base_curriculum_fingerprint')!r}.",
                )
            )
        if manifest.get("misconception_nodes") != EXPECTED_COUNTS["misconceptions"]:
            issues.append(
                self._issue(
                    "manifest_invariants",
                    "MISCONCEPTION_COUNT_MISMATCH",
                    "diagnostic_manifest.json",
                    f"Expected {EXPECTED_COUNTS['misconceptions']} misconception nodes, got {manifest.get('misconception_nodes')}.",
                )
            )
        if manifest.get("problem_type_misconception_links") != EXPECTED_COUNTS["problem_type_misconceptions"]:
            issues.append(
                self._issue(
                    "manifest_invariants",
                    "PT_LINKS_COUNT_MISMATCH",
                    "diagnostic_manifest.json",
                    f"Expected {EXPECTED_COUNTS['problem_type_misconceptions']} PT links, got {manifest.get('problem_type_misconception_links')}.",
                )
            )
        return issues

    def _validate_misconceptions(
        self, misconceptions: list[Any]
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
        if len(misconceptions) != EXPECTED_COUNTS["misconceptions"]:
            issues.append(
                self._issue(
                    "misconceptions_schema",
                    "COUNT_MISMATCH",
                    "misconceptions.json",
                    f"Expected {EXPECTED_COUNTS['misconceptions']} misconceptions, got {len(misconceptions)}.",
                )
            )
        codes = set()
        for i, item in enumerate(misconceptions):
            if not isinstance(item, dict):
                issues.append(
                    self._issue(
                        "misconceptions_schema",
                        "INVALID_RECORD_FORMAT",
                        f"misconceptions.json[{i}]",
                        "Record must be a JSON object.",
                    )
                )
                continue
            code = item.get("code")
            if not code or code in codes:
                issues.append(
                    self._issue(
                        "misconceptions_schema",
                        "DUPLICATE_OR_EMPTY_CODE",
                        f"misconceptions.json[{i}]",
                        f"Duplicate or empty code: {code}.",
                    )
                )
            codes.add(code)
            try:
                MisconceptionNode.model_validate(item)
            except Exception as e:
                issues.append(
                    self._issue(
                        "misconceptions_schema",
                        "SCHEMA_VALIDATION_ERROR",
                        f"misconceptions.json[{i}]",
                        f"Validation error: {e}",
                    )
                )
        return issues

    def _validate_pt_links(
        self, pt_links: list[Any]
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
        if len(pt_links) != EXPECTED_COUNTS["problem_type_misconceptions"]:
            issues.append(
                self._issue(
                    "pt_links_schema",
                    "COUNT_MISMATCH",
                    "problem_type_misconceptions.json",
                    f"Expected {EXPECTED_COUNTS['problem_type_misconceptions']} links, got {len(pt_links)}.",
                )
            )
        for i, item in enumerate(pt_links):
            if not isinstance(item, dict):
                issues.append(
                    self._issue(
                        "pt_links_schema",
                        "INVALID_RECORD_FORMAT",
                        f"problem_type_misconceptions.json[{i}]",
                        "Record must be a JSON object.",
                    )
                )
                continue
            try:
                ProblemTypeMisconceptionLink.model_validate(item)
            except Exception as e:
                issues.append(
                    self._issue(
                        "pt_links_schema",
                        "SCHEMA_VALIDATION_ERROR",
                        f"problem_type_misconceptions.json[{i}]",
                        f"Validation error: {e}",
                    )
                )
        return issues

    def _validate_remediation_links(
        self, remediation_links: list[Any]
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
        if len(remediation_links) != EXPECTED_COUNTS["misconception_remediation_concepts"]:
            issues.append(
                self._issue(
                    "remediation_links_schema",
                    "COUNT_MISMATCH",
                    "misconception_remediation_concepts.json",
                    f"Expected {EXPECTED_COUNTS['misconception_remediation_concepts']} links, got {len(remediation_links)}.",
                )
            )
        for i, item in enumerate(remediation_links):
            if not isinstance(item, dict):
                issues.append(
                    self._issue(
                        "remediation_links_schema",
                        "INVALID_RECORD_FORMAT",
                        f"misconception_remediation_concepts.json[{i}]",
                        "Record must be a JSON object.",
                    )
                )
                continue
            try:
                MisconceptionRemediationConceptLink.model_validate(item)
            except Exception as e:
                issues.append(
                    self._issue(
                        "remediation_links_schema",
                        "SCHEMA_VALIDATION_ERROR",
                        f"misconception_remediation_concepts.json[{i}]",
                        f"Validation error: {e}",
                    )
                )
        return issues

    def _validate_referential_integrity(
        self,
        misconceptions: list[Any],
        pt_links: list[Any],
        remediation_links: list[Any],
        snapshot_dir: Path,
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
        misconception_codes = {
            m.get("code") for m in misconceptions if isinstance(m, dict) and m.get("code")
        }

        # Check candidate snapshot files
        pt_file = snapshot_dir / "problem_types.json"
        concepts_file = snapshot_dir / "concepts.json"
        chapters_file = snapshot_dir / "chapters.json"

        if not pt_file.is_file() or not concepts_file.is_file() or not chapters_file.is_file():
            issues.append(
                self._issue(
                    "referential_integrity",
                    "SNAPSHOT_FILES_MISSING",
                    "generated_snapshot",
                    "Generated snapshot files are missing for referential integrity check.",
                )
            )
            return issues

        try:
            pt_codes = {
                p.get("code") for p in json.loads(pt_file.read_text(encoding="utf-8")) if isinstance(p, dict)
            }
            concept_codes = {
                c.get("code") for c in json.loads(concepts_file.read_text(encoding="utf-8")) if isinstance(c, dict)
            }
            chapter_codes = {
                ch.get("code") for ch in json.loads(chapters_file.read_text(encoding="utf-8")) if isinstance(ch, dict)
            }
        except Exception as e:
            issues.append(
                self._issue(
                    "referential_integrity",
                    "SNAPSHOT_READ_ERROR",
                    "generated_snapshot",
                    f"Error reading snapshot files: {e}",
                )
            )
            return issues

        # 1. Chapters in misconceptions
        for m in misconceptions:
            if isinstance(m, dict):
                ch = m.get("chapter_code")
                if ch not in chapter_codes:
                    issues.append(
                        self._issue(
                            "referential_integrity",
                            "INVALID_CHAPTER_CODE",
                            f"misconceptions[{m.get('code')}]",
                            f"Chapter code {ch} does not exist in candidate chapters.",
                        )
                    )
                for rc in m.get("remediation_concepts", []):
                    if rc not in concept_codes:
                        issues.append(
                            self._issue(
                                "referential_integrity",
                                "INVALID_REMEDIATION_CONCEPT",
                                f"misconceptions[{m.get('code')}]",
                                f"Concept {rc} does not exist in candidate concepts.",
                            )
                        )

        # 2. PT links
        for link in pt_links:
            if isinstance(link, dict):
                pt = link.get("problem_type_code")
                mis = link.get("misconception_code")
                if pt not in pt_codes:
                    issues.append(
                        self._issue(
                            "referential_integrity",
                            "INVALID_PROBLEM_TYPE",
                            f"problem_type_misconceptions[{pt}]",
                            f"Problem type {pt} does not exist in candidate problem types.",
                        )
                    )
                if mis not in misconception_codes:
                    issues.append(
                        self._issue(
                            "referential_integrity",
                            "INVALID_MISCONCEPTION",
                            f"problem_type_misconceptions[{mis}]",
                            f"Misconception {mis} does not exist in misconceptions.json.",
                        )
                    )

        # 3. Remediation links
        for link in remediation_links:
            if isinstance(link, dict):
                mis = link.get("misconception_code")
                cc = link.get("concept_code")
                if mis not in misconception_codes:
                    issues.append(
                        self._issue(
                            "referential_integrity",
                            "INVALID_MISCONCEPTION",
                            f"misconception_remediation_concepts[{mis}]",
                            f"Misconception {mis} does not exist in misconceptions.json.",
                        )
                    )
                if cc not in concept_codes:
                    issues.append(
                        self._issue(
                            "referential_integrity",
                            "INVALID_CONCEPT",
                            f"misconception_remediation_concepts[{cc}]",
                            f"Concept {cc} does not exist in candidate concepts.",
                        )
                    )

        return issues

    def _validate_inference_policy(
        self, manifest: dict[str, Any]
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
        policy = manifest.get("inference_policy", {})
        if policy.get("automatic_student_diagnosis_allowed") is not False:
            issues.append(
                self._issue(
                    "inference_policy_guard",
                    "AUTO_DIAGNOSIS_NOT_BLOCKED",
                    "diagnostic_manifest.json",
                    "CRITICAL GUARDRAIL: automatic_student_diagnosis_allowed must be false.",
                )
            )
        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[DiagnosticGraphIssue]:
        issues: list[DiagnosticGraphIssue] = []
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
        if manifest.get("canonical_write_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "MANIFEST_CANONICAL_WRITE_NOT_BLOCKED",
                    "diagnostic_manifest.json",
                    "canonical_write_allowed must be false in diagnostic_manifest.json.",
                )
            )
        if manifest.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "MANIFEST_DB_IMPORT_NOT_BLOCKED",
                    "diagnostic_manifest.json",
                    "database_import_allowed must be false in diagnostic_manifest.json.",
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
        self, path: Path, issues: list[DiagnosticGraphIssue]
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

    def _load_list(
        self, path: Path, issues: list[DiagnosticGraphIssue]
    ) -> list[Any]:
        if not path.is_file():
            return []
        try:
            val = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(val, list):
                return val
            issues.append(
                self._issue(
                    "required_files",
                    "INVALID_JSON_STRUCTURE",
                    path.name,
                    f"Expected JSON list in {path.name}.",
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

    @staticmethod
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> DiagnosticGraphIssue:
        return DiagnosticGraphIssue(
            check=check, code=code, location=location, message=message
        )
