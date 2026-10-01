from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.curriculum.full_scope_alignment import (
    DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    EXPECTED_ALIGNMENT_AGGREGATE_SHA256,
    EXPECTED_ENRICHED_PREVIEW_FINGERPRINT,
    REPO_ROOT,
    FullScopeAlignmentPreviewComposer,
)
from app.curriculum.import_schemas import (
    ConceptRecord,
    LearningOutcomeRecord,
    ProblemTypeRecord,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_ENRICHMENT_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "full_scope_enrichment_v0_1"
)

EXPECTED_ENRICHMENT_AGGREGATE_SHA256 = (
    "25d50a7f4fdb1473c72ff14fa0ee6f7ace5070d02dbe8c4dd304b5a5608d9182"
)
EXPECTED_BASE_REPO_COMMIT = "453e3817c3d77098ad5d3171ed9b466391ac223b"
EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256 = (
    "2f4c17a62008895e4d003e22f872f5710dd265d13fe6ee38c2120040bcc4fdde"
)

SEMANTIC_FILES_ORDER = (
    "enrichment_manifest.json",
    "problem_types_enrichment.json",
    "concepts_enrichment.json",
    "learning_outcomes_enrichment.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "enrichment_manifest.json": (
        "856a23ea93521679c2fa7aa4dfcbec1ae9334f4b330c630c3aea3bbe83c374b6"
    ),
    "problem_types_enrichment.json": (
        "e066a9b1432b269910c778992176e8317e2f997d7ed43c45fc629d8da634ff9c"
    ),
    "concepts_enrichment.json": (
        "cee5d0b380cc3eaa7776b2b42a6a30373ef8346e8291d86c11584298899fbe13"
    ),
    "learning_outcomes_enrichment.json": (
        "7c8193454960121314a309bcd501232b3f903a79816ca3ebda3a9d0d4b676155"
    ),
}

EXPECTED_INVARIANTS = {
    "problem_types_enrichment": 16,
    "concepts_enrichment": 16,
    "learning_outcomes_enrichment": 15,
    "total_enrichment_records": 47,
    "data033_blockers_before": 41,
    "data033_blockers_after_overlay": 0,
    "canonical_write_allowed": False,
    "database_import_allowed": False,
    "activation_allowed": False,
    "production_release_allowed": False,
}


@dataclass(frozen=True, slots=True, order=True)
class SchemaEnrichmentIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class SchemaEnrichmentReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str | None
    base_alignment_aggregate_sha256: str | None
    aggregate_semantic_sha256: str | None
    canonical_write_allowed: bool
    database_import_allowed: bool
    activation_allowed: bool
    production_release_allowed: bool
    blockers_before: int
    blockers_after: int
    enriched_preview_fingerprint: str | None
    errors: tuple[SchemaEnrichmentIssue, ...]

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
            "base_alignment_aggregate_sha256": self.base_alignment_aggregate_sha256,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "activation_allowed": self.activation_allowed,
            "production_release_allowed": self.production_release_allowed,
            "blockers_before": self.blockers_before,
            "blockers_after": self.blockers_after,
            "enriched_preview_fingerprint": self.enriched_preview_fingerprint,
            "errors": [asdict(issue) for issue in self.errors],
        }


class SchemaEnrichmentValidator:
    """Validate DATA-MATH12-034 GDPT 2018 Grade 12 Math full-scope schema enrichment candidate."""

    def validate(
        self,
        enrichment_path: Path = DEFAULT_SCHEMA_ENRICHMENT_PATH,
        *,
        alignment_path: Path = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
        repo_root: Path = REPO_ROOT,
    ) -> SchemaEnrichmentReport:
        path = enrichment_path.resolve()
        align_path = alignment_path.resolve()
        repo_root = repo_root.resolve()
        initial: list[SchemaEnrichmentIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        manifest = self._load_object(path / "enrichment_manifest.json", initial)
        pts = self._load_list(path / "problem_types_enrichment.json", initial)
        concepts = self._load_list(path / "concepts_enrichment.json", initial)
        los = self._load_list(path / "learning_outcomes_enrichment.json", initial)

        checks_to_errors: dict[str, list[SchemaEnrichmentIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_alignment_binding": self._validate_base_alignment_binding(
                contract, manifest
            ),
            "enrichment_counts": self._validate_enrichment_counts(
                manifest, pts, concepts, los
            ),
            "import_schema_validation": self._validate_import_schemas(
                pts, concepts, los
            ),
            "overlay_closure": self._validate_overlay_closure(
                path, align_path, repo_root
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                contract, manifest
            ),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[SchemaEnrichmentIssue] = []
        if aggregate != EXPECTED_ENRICHMENT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_ENRICHMENT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_ENRICHMENT_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-034 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        # Check exact invariants
        invariants_errors: list[SchemaEnrichmentIssue] = []
        actual_invariants = {
            "problem_types_enrichment": len(pts),
            "concepts_enrichment": len(concepts),
            "learning_outcomes_enrichment": len(los),
            "total_enrichment_records": len(pts) + len(concepts) + len(los),
            "data033_blockers_before": manifest.get("locked_counts", {}).get(
                "data033_blockers_before"
            ),
            "data033_blockers_after_overlay": manifest.get(
                "locked_counts", {}
            ).get("data033_blockers_after_overlay"),
            "canonical_write_allowed": contract.get("canonical_write_allowed"),
            "database_import_allowed": contract.get("database_import_allowed"),
            "activation_allowed": manifest.get("activation_allowed"),
            "production_release_allowed": contract.get(
                "production_release_allowed"
            ),
        }
        if actual_invariants != EXPECTED_INVARIANTS:
            invariants_errors.append(
                self._issue(
                    "exact_invariants",
                    "INVARIANT_COUNT_MISMATCH",
                    "data_contract.json",
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
            "problem_types_enrichment": len(pts),
            "concepts_enrichment": len(concepts),
            "learning_outcomes_enrichment": len(los),
            "total_enrichment_records": len(pts) + len(concepts) + len(los),
        }

        # Check preview fingerprint after overlay
        preview, _ = FullScopeAlignmentPreviewComposer.compose(
            align_path, repo_root, enrichment_path=path
        )
        fingerprint = preview.fingerprint if preview else None
        blockers_after = len(preview.enrichment_blockers) if preview else -1

        return SchemaEnrichmentReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            base_alignment_aggregate_sha256=manifest.get(
                "base_alignment_aggregate_sha256"
            ),
            aggregate_semantic_sha256=aggregate,
            canonical_write_allowed=bool(
                contract.get("canonical_write_allowed", True)
            ),
            database_import_allowed=bool(
                contract.get("database_import_allowed", True)
            ),
            activation_allowed=bool(
                manifest.get("activation_allowed", True)
            ),
            production_release_allowed=bool(
                contract.get("production_release_allowed", True)
            ),
            blockers_before=41,
            blockers_after=blockers_after,
            enriched_preview_fingerprint=fingerprint,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[SchemaEnrichmentIssue]
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
    ) -> list[SchemaEnrichmentIssue]:
        issues: list[SchemaEnrichmentIssue] = []
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
    ) -> list[SchemaEnrichmentIssue]:
        issues: list[SchemaEnrichmentIssue] = []
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

    def _validate_base_alignment_binding(
        self, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[SchemaEnrichmentIssue]:
        issues: list[SchemaEnrichmentIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_alignment_binding",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )
        if manifest.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_alignment_binding",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "enrichment_manifest.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {manifest.get('base_repo_commit')!r}.",
                )
            )
        if (
            manifest.get("base_alignment_aggregate_sha256")
            != EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256
        ):
            issues.append(
                self._issue(
                    "base_alignment_binding",
                    "BASE_ALIGNMENT_AGGREGATE_MISMATCH",
                    "enrichment_manifest.json",
                    f"Expected base_alignment_aggregate_sha256 {EXPECTED_BASE_ALIGNMENT_AGGREGATE_SHA256}, got {manifest.get('base_alignment_aggregate_sha256')!r}.",
                )
            )
        return issues

    def _validate_enrichment_counts(
        self,
        manifest: dict[str, Any],
        pts: list[dict[str, Any]],
        concepts: list[dict[str, Any]],
        los: list[dict[str, Any]],
    ) -> list[SchemaEnrichmentIssue]:
        issues: list[SchemaEnrichmentIssue] = []
        lc = manifest.get("locked_counts", {})
        if lc.get("problem_type_enrichment_records") != len(pts):
            issues.append(
                self._issue(
                    "enrichment_counts",
                    "PROBLEM_TYPE_ENRICHMENT_COUNT_MISMATCH",
                    "enrichment_manifest.json",
                    f"Manifest declared {lc.get('problem_type_enrichment_records')} problem types, found {len(pts)}.",
                )
            )
        if lc.get("concept_enrichment_records") != len(concepts):
            issues.append(
                self._issue(
                    "enrichment_counts",
                    "CONCEPT_ENRICHMENT_COUNT_MISMATCH",
                    "enrichment_manifest.json",
                    f"Manifest declared {lc.get('concept_enrichment_records')} concepts, found {len(concepts)}.",
                )
            )
        if lc.get("learning_outcome_enrichment_records") != len(los):
            issues.append(
                self._issue(
                    "enrichment_counts",
                    "LEARNING_OUTCOME_ENRICHMENT_COUNT_MISMATCH",
                    "enrichment_manifest.json",
                    f"Manifest declared {lc.get('learning_outcome_enrichment_records')} learning outcomes, found {len(los)}.",
                )
            )
        total = len(pts) + len(concepts) + len(los)
        if lc.get("total_enrichment_records") != total:
            issues.append(
                self._issue(
                    "enrichment_counts",
                    "TOTAL_ENRICHMENT_COUNT_MISMATCH",
                    "enrichment_manifest.json",
                    f"Manifest declared {lc.get('total_enrichment_records')} total, found {total}.",
                )
            )
        return issues

    def _validate_import_schemas(
        self,
        pts: list[dict[str, Any]],
        concepts: list[dict[str, Any]],
        los: list[dict[str, Any]],
    ) -> list[SchemaEnrichmentIssue]:
        issues: list[SchemaEnrichmentIssue] = []

        def _validate_record(cls: Any, record: dict[str, Any], loc: str) -> None:
            allowed = set(cls.model_fields.keys())
            filtered = {k: v for k, v in record.items() if k in allowed}
            try:
                cls.model_validate(filtered)
            except ValidationError as e:
                issues.append(
                    self._issue(
                        "import_schema_validation",
                        "PYDANTIC_VALIDATION_ERROR",
                        loc,
                        f"Schema validation error: {e}",
                    )
                )

        for i, pt in enumerate(pts):
            code = pt.get("code", f"index_{i}")
            _validate_record(
                ProblemTypeRecord, pt, f"problem_types_enrichment.json[{code}]"
            )

        for i, c in enumerate(concepts):
            code = c.get("code", f"index_{i}")
            _validate_record(
                ConceptRecord, c, f"concepts_enrichment.json[{code}]"
            )

        for i, lo in enumerate(los):
            code = lo.get("code", f"index_{i}")
            _validate_record(
                LearningOutcomeRecord,
                lo,
                f"learning_outcomes_enrichment.json[{code}]",
            )

        return issues

    def _validate_overlay_closure(
        self, path: Path, align_path: Path, repo_root: Path
    ) -> list[SchemaEnrichmentIssue]:
        issues: list[SchemaEnrichmentIssue] = []
        preview, p_issues = FullScopeAlignmentPreviewComposer.compose(
            align_path, repo_root, enrichment_path=path
        )
        for pi in p_issues:
            issues.append(
                self._issue(
                    "overlay_closure",
                    pi.code,
                    pi.location,
                    f"Preview issue during overlay: {pi.message}",
                )
            )
        if preview is None:
            issues.append(
                self._issue(
                    "overlay_closure",
                    "PREVIEW_COMPOSITION_FAILED",
                    "full_scope_enrichment_v0_1",
                    "Failed to compose preview with enrichment overlay.",
                )
            )
            return issues

        if len(preview.enrichment_blockers) != 0:
            issues.append(
                self._issue(
                    "overlay_closure",
                    "UNRESOLVED_ENRICHMENT_BLOCKERS",
                    "full_scope_enrichment_v0_1",
                    f"Expected 0 enrichment blockers after overlay, found {len(preview.enrichment_blockers)}.",
                )
            )

        if preview.schema_enrichment_required is not False:
            issues.append(
                self._issue(
                    "overlay_closure",
                    "ENRICHMENT_STILL_REQUIRED",
                    "full_scope_enrichment_v0_1",
                    "schema_enrichment_required must be False after overlay.",
                )
            )

        if preview.fingerprint != EXPECTED_ENRICHED_PREVIEW_FINGERPRINT:
            issues.append(
                self._issue(
                    "overlay_closure",
                    "ENRICHED_FINGERPRINT_MISMATCH",
                    "full_scope_enrichment_v0_1",
                    f"Expected enriched fingerprint {EXPECTED_ENRICHED_PREVIEW_FINGERPRINT}, got {preview.fingerprint}.",
                )
            )

        return issues

    def _validate_critical_boundaries(
        self, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[SchemaEnrichmentIssue]:
        issues: list[SchemaEnrichmentIssue] = []
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
        if manifest.get("activation_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "ACTIVATION_NOT_BLOCKED",
                    "enrichment_manifest.json",
                    "activation_allowed must be false.",
                )
            )
        if manifest.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "enrichment_manifest.json",
                    "database_import_allowed must be false.",
                )
            )
        if manifest.get("canonical_write_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_WRITE_NOT_BLOCKED",
                    "enrichment_manifest.json",
                    "canonical_write_allowed must be false.",
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
        self, path: Path, issues: list[SchemaEnrichmentIssue]
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
        self, path: Path, issues: list[SchemaEnrichmentIssue]
    ) -> list[dict[str, Any]]:
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
    ) -> SchemaEnrichmentIssue:
        return SchemaEnrichmentIssue(
            check=check, code=code, location=location, message=message
        )
