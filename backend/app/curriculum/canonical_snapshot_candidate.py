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
    FullScopeAlignmentPreview,
    FullScopeAlignmentPreviewComposer,
)
from app.curriculum.import_schemas import (
    ChapterRecord,
    ConceptRecord,
    ConceptRelationRecord,
    DatasetManifest,
    LearningOutcomeRecord,
    ProblemTypeConceptRecord,
    ProblemTypeOutcomeRecord,
    ProblemTypeRecord,
    TopicRecord,
)
from app.curriculum.schema_enrichment import (
    DEFAULT_SCHEMA_ENRICHMENT_PATH,
    EXPECTED_ENRICHMENT_AGGREGATE_SHA256,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "promotion"
    / "full_scope_v1_2_0_candidate"
)
DEFAULT_SNAPSHOT_DIR = DEFAULT_CANDIDATE_PATH / "generated_snapshot"
ROOT_CANONICAL_PATH = BACKEND_ROOT / "data" / "curriculum" / "math" / "grade12" / "gdpt2018"

EXPECTED_SNAPSHOT_CANDIDATE_AGGREGATE_SHA256 = (
    "827777dcf365a562eb0a5dda1109859f56232d242373291a3f7c6eafb2d0f695"
)
EXPECTED_BASE_REPO_COMMIT = "aed14bf213ac9db65e820984f5a6c46ebabbe304"
EXPECTED_BOUND_COMPOSED_FINGERPRINT = (
    "2cad0c70f89d4d95ba3db2aaac194f0ddd9ad834e1b9014a6bbbe49bc1d7ec93"
)

EXPECTED_ACTIVE_CHAPTERS = (
    "DERIVATIVE_APPLICATIONS",
    "INTEGRALS",
    "OXYZ_CHAPTER",
    "GROUPED_DATA_STATISTICS",
    "PROBABILITY_CHAPTER",
)

EXPECTED_COUNTS = {
    "chapters": 5,
    "topics": 24,
    "problem_types": 75,
    "concepts": 89,
    "learning_outcomes": 34,
    "concept_relations": 93,
    "problem_type_concepts": 200,
    "problem_type_learning_outcomes": 82,
}

SEMANTIC_FILES_ORDER = (
    "snapshot_manifest.json",
    "canonical_diff.json",
    "snapshot_policy.json",
    "promotion_gate.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "snapshot_manifest.json": (
        "0088f7b2cf297a6713be453e0443cc8fe21ff93ff160c504963a27e8559f6039"
    ),
    "canonical_diff.json": (
        "f1fa20770e829832a7ecffcc73fd9f7f742401cd8311799a7096064c73f56b95"
    ),
    "snapshot_policy.json": (
        "a875f93e344711f8213202a718bf09260f82b0c73782c19e19d47f68724ce330"
    ),
    "promotion_gate.json": (
        "d30ed17aa3195b52929e2f602c7d7762881f0f262ed8dcf077820318b2a24ee9"
    ),
}

GENERATED_SNAPSHOT_FILES = (
    "manifest.json",
    "chapters.json",
    "topics.json",
    "problem_types.json",
    "concepts.json",
    "learning_outcomes.json",
    "concept_relations.json",
    "problem_type_concepts.json",
    "problem_type_learning_outcomes.json",
)


@dataclass(frozen=True, slots=True, order=True)
class CanonicalSnapshotCandidateIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class CanonicalSnapshotCandidateReport:
    candidate_path: str
    snapshot_dir: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str | None
    aggregate_semantic_sha256: str | None
    bound_composed_fingerprint: str | None
    candidate_manifest_version: str | None
    active_chapter_codes: tuple[str, ...]
    canonical_activation_allowed: bool
    canonical_write_allowed: bool
    database_import_allowed: bool
    production_release_allowed: bool
    errors: tuple[CanonicalSnapshotCandidateIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_path": self.candidate_path,
            "snapshot_dir": self.snapshot_dir,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "base_repo_commit": self.base_repo_commit,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "bound_composed_fingerprint": self.bound_composed_fingerprint,
            "candidate_manifest_version": self.candidate_manifest_version,
            "active_chapter_codes": list(self.active_chapter_codes),
            "canonical_activation_allowed": self.canonical_activation_allowed,
            "canonical_write_allowed": self.canonical_write_allowed,
            "database_import_allowed": self.database_import_allowed,
            "production_release_allowed": self.production_release_allowed,
            "errors": [asdict(issue) for issue in self.errors],
        }


class CanonicalSnapshotCandidateGenerator:
    """Deterministic generator for canonical v1.2.0 snapshot candidate files."""

    @classmethod
    def generate(
        cls,
        target_dir: Path = DEFAULT_SNAPSHOT_DIR,
        *,
        alignment_path: Path = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
        enrichment_path: Path = DEFAULT_SCHEMA_ENRICHMENT_PATH,
        repo_root: Path = REPO_ROOT,
        root_canonical_path: Path = ROOT_CANONICAL_PATH,
    ) -> dict[str, Any]:
        target = target_dir.resolve()
        root_canonical = root_canonical_path.resolve()

        # Guard: Never write directly to root canonical 1.1.0 directory!
        if target == root_canonical:
            raise RuntimeError(
                "CRITICAL BOUNDARY VIOLATION: Generator MUST NOT write to root canonical path."
            )

        preview, issues = FullScopeAlignmentPreviewComposer.compose(
            alignment_path, repo_root, enrichment_path=enrichment_path
        )
        if preview is None:
            raise RuntimeError(f"Preview composition failed: {issues}")

        if preview.fingerprint != EXPECTED_BOUND_COMPOSED_FINGERPRINT:
            raise RuntimeError(
                f"Composed fingerprint mismatch: expected {EXPECTED_BOUND_COMPOSED_FINGERPRINT}, got {preview.fingerprint}"
            )

        target.mkdir(parents=True, exist_ok=True)

        # 1. Manifest
        manifest_data = {
            "dataset_code": "MATH_G12_GDPT2018_CANONICAL_SNAPSHOT_CANDIDATE_1_2_0",
            "dataset_version": "1.2.0",
            "curriculum_code": "GDPT2018",
            "curriculum_name": "Chương trình giáo dục phổ thông 2018",
            "curriculum_description": "Versioned curriculum container for Grade 12 Mathematics.",
            "curriculum_version_code": "GDPT2018_2018",
            "curriculum_version": "2018",
            "subject_code": "MATH_G12",
            "grade_level": 12,
            "source_name": "Bộ Giáo dục và Đào tạo - Chương trình GDPT môn Toán 2018",
            "source_reference": "Thông tư 32/2018/TT-BGDĐT",
            "verified_at": None,
            "legacy_identity_compatible": True,
        }

        # Format helper
        def _dump_json(path: Path, obj: Any) -> None:
            text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
            path.write_text(text, encoding="utf-8")

        _dump_json(target / "manifest.json", manifest_data)
        _dump_json(target / "chapters.json", list(preview.chapters))
        _dump_json(target / "topics.json", list(preview.topics))
        _dump_json(target / "problem_types.json", list(preview.problem_types))
        _dump_json(target / "concepts.json", list(preview.concepts))
        _dump_json(target / "learning_outcomes.json", list(preview.learning_outcomes))
        _dump_json(target / "concept_relations.json", list(preview.concept_relations))
        _dump_json(target / "problem_type_concepts.json", list(preview.problem_type_concepts))
        _dump_json(target / "problem_type_learning_outcomes.json", list(preview.problem_type_learning_outcomes))

        return {
            "status": "GENERATED",
            "target_dir": str(target),
            "fingerprint": preview.fingerprint,
            "manifest_version": manifest_data["dataset_version"],
            "counts": preview.counts,
        }


class CanonicalSnapshotCandidateValidator:
    """Validator for DATA-MATH12-038 specification and generated v1.2.0 snapshot files."""

    def validate(
        self,
        candidate_path: Path = DEFAULT_CANDIDATE_PATH,
        *,
        snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
        root_canonical_path: Path = ROOT_CANONICAL_PATH,
        alignment_path: Path = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
        enrichment_path: Path = DEFAULT_SCHEMA_ENRICHMENT_PATH,
        repo_root: Path = REPO_ROOT,
    ) -> CanonicalSnapshotCandidateReport:
        path = candidate_path.resolve()
        snapshot_path = snapshot_dir.resolve()
        root_canonical = root_canonical_path.resolve()
        initial: list[CanonicalSnapshotCandidateIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        manifest = self._load_object(path / "snapshot_manifest.json", initial)
        policy = self._load_object(path / "snapshot_policy.json", initial)
        gate = self._load_object(path / "promotion_gate.json", initial)
        diff = self._load_object(path / "canonical_diff.json", initial)

        checks_to_errors: dict[str, list[CanonicalSnapshotCandidateIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "base_repo_commit": self._validate_base_repo_commit(contract, manifest),
            "snapshot_files_exist": self._validate_snapshot_files_exist(snapshot_path),
            "snapshot_import_schemas": self._validate_snapshot_import_schemas(snapshot_path),
            "snapshot_counts_and_fingerprint": self._validate_counts_and_fingerprint(
                snapshot_path, manifest, alignment_path, enrichment_path, repo_root
            ),
            "active_chapters_guard": self._validate_active_chapters(snapshot_path, manifest),
            "root_canonical_unmodified": self._validate_root_canonical_unmodified(root_canonical),
            "critical_boundaries": self._validate_critical_boundaries(contract, manifest, gate),
        }

        # Check aggregate semantic SHA-256
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[CanonicalSnapshotCandidateIssue] = []
        if aggregate != EXPECTED_SNAPSHOT_CANDIDATE_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_SNAPSHOT_CANDIDATE_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_SNAPSHOT_CANDIDATE_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-038 aggregate.",
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

        # Read snapshot manifest version and active chapters if available
        sn_manifest_file = snapshot_path / "manifest.json"
        sn_version: str | None = None
        if sn_manifest_file.is_file():
            try:
                sn_version = json.loads(sn_manifest_file.read_text(encoding="utf-8")).get("dataset_version")
            except Exception:
                pass

        sn_chapters_file = snapshot_path / "chapters.json"
        actual_active_chapters: list[str] = []
        if sn_chapters_file.is_file():
            try:
                actual_active_chapters = [
                    c.get("code")
                    for c in json.loads(sn_chapters_file.read_text(encoding="utf-8"))
                    if isinstance(c, dict)
                ]
            except Exception:
                pass

        counts = {
            "chapters": len(actual_active_chapters),
            "expected_chapters": 5,
            "expected_topics": 24,
            "expected_problem_types": 75,
        }

        return CanonicalSnapshotCandidateReport(
            candidate_path=str(path),
            snapshot_dir=str(snapshot_path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            aggregate_semantic_sha256=aggregate,
            bound_composed_fingerprint=manifest.get("bound_composed_fingerprint"),
            candidate_manifest_version=sn_version,
            active_chapter_codes=tuple(actual_active_chapters),
            canonical_activation_allowed=bool(
                manifest.get("canonical_activation_allowed", True)
            ),
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
        self, path: Path, issues: list[CanonicalSnapshotCandidateIssue]
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
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
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
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
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
        self, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
        if contract.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {contract.get('base_repo_commit')!r}.",
                )
            )
        if manifest.get("base_repo_commit") != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "base_repo_commit",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "snapshot_manifest.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT}, got {manifest.get('base_repo_commit')!r}.",
                )
            )
        return issues

    def _validate_snapshot_files_exist(
        self, snapshot_dir: Path
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
        if not snapshot_dir.is_dir():
            issues.append(
                self._issue(
                    "snapshot_files_exist",
                    "SNAPSHOT_DIRECTORY_MISSING",
                    "generated_snapshot",
                    "Snapshot directory generated_snapshot does not exist.",
                )
            )
            return issues

        for file_name in GENERATED_SNAPSHOT_FILES:
            target = snapshot_dir / file_name
            if not target.is_file():
                issues.append(
                    self._issue(
                        "snapshot_files_exist",
                        "MISSING_SNAPSHOT_FILE",
                        f"generated_snapshot/{file_name}",
                        f"Missing generated snapshot file: {file_name}.",
                    )
                )
        return issues

    def _validate_snapshot_import_schemas(
        self, snapshot_dir: Path
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
        if not snapshot_dir.is_dir():
            return issues

        def _validate_items(model_cls: Any, filename: str, is_list: bool = True) -> None:
            f = snapshot_dir / filename
            if not f.is_file():
                return
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                issues.append(
                    self._issue(
                        "snapshot_import_schemas",
                        "JSON_DECODE_ERROR",
                        filename,
                        f"Failed to decode {filename}: {e}",
                    )
                )
                return

            allowed = set(model_cls.model_fields.keys())
            if is_list:
                if not isinstance(data, list):
                    issues.append(
                        self._issue(
                            "snapshot_import_schemas",
                            "INVALID_LIST_FORMAT",
                            filename,
                            f"Expected list in {filename}.",
                        )
                    )
                    return
                for i, row in enumerate(data):
                    filtered = {k: v for k, v in row.items() if k in allowed}
                    try:
                        model_cls.model_validate(filtered)
                    except ValidationError as e:
                        issues.append(
                            self._issue(
                                "snapshot_import_schemas",
                                "SCHEMA_VALIDATION_ERROR",
                                f"{filename}[{i}]",
                                f"Validation error in {filename}: {e}",
                            )
                        )
            else:
                filtered = {k: v for k, v in data.items() if k in allowed}
                try:
                    model_cls.model_validate(filtered)
                except ValidationError as e:
                    issues.append(
                        self._issue(
                            "snapshot_import_schemas",
                            "SCHEMA_VALIDATION_ERROR",
                            filename,
                            f"Validation error in {filename}: {e}",
                        )
                    )

        _validate_items(DatasetManifest, "manifest.json", is_list=False)
        _validate_items(ChapterRecord, "chapters.json")
        _validate_items(TopicRecord, "topics.json")
        _validate_items(ProblemTypeRecord, "problem_types.json")
        _validate_items(ConceptRecord, "concepts.json")
        _validate_items(LearningOutcomeRecord, "learning_outcomes.json")
        _validate_items(ConceptRelationRecord, "concept_relations.json")
        _validate_items(ProblemTypeConceptRecord, "problem_type_concepts.json")
        _validate_items(ProblemTypeOutcomeRecord, "problem_type_learning_outcomes.json")

        return issues

    def _validate_counts_and_fingerprint(
        self,
        snapshot_dir: Path,
        manifest: dict[str, Any],
        alignment_path: Path,
        enrichment_path: Path,
        repo_root: Path,
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
        if not snapshot_dir.is_dir():
            return issues

        # Verify candidate manifest version
        manifest_file = snapshot_dir / "manifest.json"
        if manifest_file.is_file():
            try:
                m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                if m_data.get("dataset_version") != "1.2.0":
                    issues.append(
                        self._issue(
                            "snapshot_counts_and_fingerprint",
                            "MANIFEST_VERSION_MISMATCH",
                            "generated_snapshot/manifest.json",
                            f"Expected dataset_version 1.2.0, got {m_data.get('dataset_version')!r}.",
                        )
                    )
            except Exception:
                pass

        # Verify counts
        file_to_count_key = {
            "chapters.json": "chapters",
            "topics.json": "topics",
            "problem_types.json": "problem_types",
            "concepts.json": "concepts",
            "learning_outcomes.json": "learning_outcomes",
            "concept_relations.json": "concept_relations",
            "problem_type_concepts.json": "problem_type_concepts",
            "problem_type_learning_outcomes.json": "problem_type_learning_outcomes",
        }

        snapshot_lists: dict[str, list[Any]] = {}
        for fname, ckey in file_to_count_key.items():
            fpath = snapshot_dir / fname
            if not fpath.is_file():
                continue
            try:
                items = json.loads(fpath.read_text(encoding="utf-8"))
                snapshot_lists[ckey] = items
                expected_cnt = EXPECTED_COUNTS[ckey]
                if len(items) != expected_cnt:
                    issues.append(
                        self._issue(
                            "snapshot_counts_and_fingerprint",
                            f"{ckey.upper()}_COUNT_MISMATCH",
                            f"generated_snapshot/{fname}",
                            f"Expected {expected_cnt} items in {fname}, got {len(items)}.",
                        )
                    )
            except Exception:
                pass

        # Reconstruct candidate preview dictionary to verify fingerprint
        if len(snapshot_lists) == len(file_to_count_key):
            try:
                cb_path = alignment_path / "candidate_manifest.json"
                cross_path = alignment_path / "cross_scope_relations.json"
                scope_path = alignment_path / "official_scope_bindings.json"
                lo_req_path = alignment_path / "learning_outcome_requirement_bindings.json"

                c_manifest = json.loads(cb_path.read_text(encoding="utf-8")) if cb_path.is_file() else {}
                cross_rels = json.loads(cross_path.read_text(encoding="utf-8")) if cross_path.is_file() else []
                scope_binds = json.loads(scope_path.read_text(encoding="utf-8")) if scope_path.is_file() else []
                lo_binds = json.loads(lo_req_path.read_text(encoding="utf-8")) if lo_req_path.is_file() else {}

                preview_dict = {
                    "candidate_code": c_manifest.get("candidate_code", ""),
                    "dataset_code": c_manifest.get("dataset_code", ""),
                    "subject_code": c_manifest.get("subject_code", ""),
                    "chapters": sorted(
                        snapshot_lists["chapters"],
                        key=lambda x: (x.get("order_index", 0), x.get("code", "")),
                    ),
                    "topics": sorted(
                        snapshot_lists["topics"],
                        key=lambda x: (
                            x.get("chapter_code", ""),
                            x.get("order_index", 0),
                            x.get("code", ""),
                        ),
                    ),
                    "problem_types": sorted(
                        snapshot_lists["problem_types"],
                        key=lambda x: (x.get("topic_code", ""), x.get("code", "")),
                    ),
                    "concepts": sorted(
                        snapshot_lists["concepts"], key=lambda x: x.get("code", "")
                    ),
                    "learning_outcomes": sorted(
                        snapshot_lists["learning_outcomes"], key=lambda x: x.get("code", "")
                    ),
                    "concept_relations": sorted(
                        snapshot_lists["concept_relations"],
                        key=lambda x: (
                            x.get("source_code", ""),
                            x.get("target_code", ""),
                            x.get("relation_type", ""),
                        ),
                    ),
                    "problem_type_concepts": sorted(
                        snapshot_lists["problem_type_concepts"],
                        key=lambda x: (
                            x.get("problem_type_code", ""),
                            x.get("concept_code", ""),
                        ),
                    ),
                    "problem_type_learning_outcomes": sorted(
                        snapshot_lists["problem_type_learning_outcomes"],
                        key=lambda x: (
                            x.get("problem_type_code", ""),
                            x.get("learning_outcome_code", ""),
                        ),
                    ),
                    "cross_scope_relations": sorted(
                        cross_rels,
                        key=lambda x: (
                            x.get("source_code", ""),
                            x.get("target_code", ""),
                        ),
                    ),
                    "official_scope_bindings": sorted(
                        scope_binds,
                        key=lambda x: x.get("official_scope_code", ""),
                    ),
                    "learning_outcome_requirement_bindings": dict(
                        sorted(lo_binds.items())
                    ),
                    "schema_enrichment_blockers": [],
                }

                canon = json.dumps(
                    preview_dict,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                actual_fp = hashlib.sha256(canon).hexdigest()

                if actual_fp != EXPECTED_BOUND_COMPOSED_FINGERPRINT:
                    issues.append(
                        self._issue(
                            "snapshot_counts_and_fingerprint",
                            "FINGERPRINT_MISMATCH",
                            "generated_snapshot",
                            f"Expected fingerprint {EXPECTED_BOUND_COMPOSED_FINGERPRINT}, got {actual_fp}.",
                        )
                    )
            except Exception as e:
                issues.append(
                    self._issue(
                        "snapshot_counts_and_fingerprint",
                        "FINGERPRINT_COMPUTATION_ERROR",
                        "generated_snapshot",
                        f"Error checking fingerprint: {e}",
                    )
                )

        return issues

    def _validate_active_chapters(
        self, snapshot_dir: Path, manifest: dict[str, Any]
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
        chapters_file = snapshot_dir / "chapters.json"
        if not chapters_file.is_file():
            return issues

        try:
            chapters = json.loads(chapters_file.read_text(encoding="utf-8"))
            codes = [c.get("code") for c in chapters if isinstance(c, dict)]

            if tuple(codes) != EXPECTED_ACTIVE_CHAPTERS:
                issues.append(
                    self._issue(
                        "active_chapters_guard",
                        "ACTIVE_CHAPTERS_MISMATCH",
                        "generated_snapshot/chapters.json",
                        f"Expected active chapters {EXPECTED_ACTIVE_CHAPTERS}, got {tuple(codes)}.",
                    )
                )

            if "EXPONENTIAL_LOGARITHM" in codes:
                issues.append(
                    self._issue(
                        "active_chapters_guard",
                        "EXPONENTIAL_LOGARITHM_ACTIVE_VIOLATION",
                        "generated_snapshot/chapters.json",
                        "EXPONENTIAL_LOGARITHM must not be an active Grade 12 core chapter.",
                    )
                )

            if "VECTORS_GEOMETRY" in codes:
                issues.append(
                    self._issue(
                        "active_chapters_guard",
                        "VECTORS_GEOMETRY_ACTIVE_VIOLATION",
                        "generated_snapshot/chapters.json",
                        "VECTORS_GEOMETRY must not be a separate active core chapter.",
                    )
                )

            if "GROUPED_DATA_STATISTICS" not in codes:
                issues.append(
                    self._issue(
                        "active_chapters_guard",
                        "GROUPED_DATA_STATISTICS_MISSING",
                        "generated_snapshot/chapters.json",
                        "GROUPED_DATA_STATISTICS is required as an active core chapter.",
                    )
                )
        except Exception as e:
            issues.append(
                self._issue(
                    "active_chapters_guard",
                    "CHAPTERS_READ_ERROR",
                    "generated_snapshot/chapters.json",
                    f"Error reading chapters.json: {e}",
                )
            )

        return issues

    def _validate_root_canonical_unmodified(
        self, root_canonical: Path
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []
        root_manifest = root_canonical / "manifest.json"
        if root_manifest.is_file():
            try:
                m = json.loads(root_manifest.read_text(encoding="utf-8"))
                if m.get("dataset_version") != "1.1.0":
                    issues.append(
                        self._issue(
                            "root_canonical_unmodified",
                            "ROOT_CANONICAL_VERSION_MUTATED",
                            "backend/data/curriculum/math/grade12/gdpt2018/manifest.json",
                            f"Root canonical manifest version must remain 1.1.0, got {m.get('dataset_version')!r}.",
                        )
                    )
            except Exception as e:
                issues.append(
                    self._issue(
                        "root_canonical_unmodified",
                        "ROOT_CANONICAL_READ_ERROR",
                        "manifest.json",
                        f"Error reading root canonical manifest: {e}",
                    )
                )
        return issues

    def _validate_critical_boundaries(
        self,
        contract: dict[str, Any],
        manifest: dict[str, Any],
        gate: dict[str, Any],
    ) -> list[CanonicalSnapshotCandidateIssue]:
        issues: list[CanonicalSnapshotCandidateIssue] = []

        if manifest.get("canonical_activation_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_ACTIVATION_NOT_BLOCKED",
                    "snapshot_manifest.json",
                    "canonical_activation_allowed must be false.",
                )
            )
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
        cg = gate.get("canonical_activation_gate", {})
        if cg.get("canonical_activation") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "ACTIVATION_GATE_NOT_BLOCKED",
                    "promotion_gate.json",
                    "canonical_activation in promotion_gate must be BLOCKED.",
                )
            )
        if gate.get("database_import") != "BLOCKED":
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DB_IMPORT_GATE_NOT_BLOCKED",
                    "promotion_gate.json",
                    "database_import in promotion_gate must be BLOCKED.",
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
        self, path: Path, issues: list[CanonicalSnapshotCandidateIssue]
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
    ) -> CanonicalSnapshotCandidateIssue:
        return CanonicalSnapshotCandidateIssue(
            check=check, code=code, location=location, message=message
        )
