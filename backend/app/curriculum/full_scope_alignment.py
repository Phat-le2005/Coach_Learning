from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FULL_SCOPE_ALIGNMENT_PATH = (
    BACKEND_ROOT
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "full_scope_alignment_v0_1"
)

EXPECTED_ALIGNMENT_AGGREGATE_SHA256 = (
    "2f4c17a62008895e4d003e22f872f5710dd265d13fe6ee38c2120040bcc4fdde"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "59c922c947c31027bcfa101a2eba8c57e0b198582435d50773cec69e250903d5"
)
EXPECTED_BASE_REPO_COMMIT = "de2f935bc88308aaffcb6eef43d4ee9cfd4c67bb"
EXPECTED_INPUT_AUDIT_AGGREGATE_SHA256 = (
    "ea64fd6dd257d80f4d19477a7708f21229643d87ad7793b22504bb680c7a22e5"
)
EXPECTED_PREVIEW_FINGERPRINT = (
    "af15be17e213b90eb70106225b43c8ca352acb6d22ed0cd9115129d0ef475d19"
)

EXPECTED_CHAPTER_CODES = (
    "DERIVATIVE_APPLICATIONS",
    "INTEGRALS",
    "OXYZ_CHAPTER",
    "GROUPED_DATA_STATISTICS",
    "PROBABILITY_CHAPTER",
)

EXPECTED_OFFICIAL_CORE_SCOPES = (
    "M12_CORE_CALCULUS_DERIVATIVE_APPLICATIONS",
    "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
    "M12_CORE_GEOMETRY_COORDINATE_3D",
    "M12_CORE_STATISTICS_GROUPED_DATA",
    "M12_CORE_PROBABILITY_CONDITIONAL",
)

SEMANTIC_FILES_ORDER = (
    "candidate_manifest.json",
    "chapters.json",
    "topics.json",
    "problem_type_alignment.json",
    "official_scope_bindings.json",
    "learning_outcome_requirement_bindings.json",
    "component_bindings.json",
    "cross_scope_relations.json",
    "legacy_quarantine.json",
    "coverage_gate.json",
    "activation_policy.json",
    "materialization_plan.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES_ORDER, "data_contract.json", "README.md")

EXPECTED_SEMANTIC_HASHES = {
    "candidate_manifest.json": (
        "ff05f3abbbe46fdded8763e89300339ba987fa46e84da5e3cd31a2f82c58d95b"
    ),
    "chapters.json": (
        "c5534f182827afcdb82164776926f8074b3668578508cb272a523db8edee102c"
    ),
    "topics.json": (
        "e0e2e2465921b6650a3c0cec7d3e78e5f92710d498a84539845acdeb974f1e28"
    ),
    "problem_type_alignment.json": (
        "7223c58d813e7f00121c69a3b9f27d9893e1cf532e2732af1a3e39a8069dea28"
    ),
    "official_scope_bindings.json": (
        "31120a4943170fd6d3d017f005467d43428e69d541e734e957ae30af0b23e5e8"
    ),
    "learning_outcome_requirement_bindings.json": (
        "f8e913fd9af910011f345c5fcaf0e795487435332a239efb4041da293dbf782d"
    ),
    "component_bindings.json": (
        "8d4ff8879c81f4e4a1c7f613af60c1608b9c95e3c5c9e46fac455e6ddaf206f4"
    ),
    "cross_scope_relations.json": (
        "accf6657097c2649e7a6dc814bd88a6529421b77434b3d9d466d54bdafce8a42"
    ),
    "legacy_quarantine.json": (
        "7e1ae5211104d431cc15ce5e81ffcf817d33331f2edf27223b49ac0ccd5e365e"
    ),
    "coverage_gate.json": (
        "75748191f4dad914f9e6175e9fa010f3d6410fec8e6218b07aacb7a9c03466b9"
    ),
    "activation_policy.json": (
        "24368fb400976dfe1e71c0720b5cc82639e96012f0465d1cef9fae37e6605993"
    ),
    "materialization_plan.json": (
        "4338494938efe83f57b5c1a02374ec89ed5c804d6f7eb0fde1214c845d673715"
    ),
}

EXPECTED_INVARIANTS = {
    "chapters": 5,
    "topics": 24,
    "problem_types": 75,
    "official_core_scopes": 5,
    "official_normalized_requirements": 20,
    "learning_outcome_requirement_bindings": 34,
    "cross_scope_relations": 11,
    "legacy_quarantine_entries": 3,
    "activation_allowed": False,
    "database_import_allowed": False,
    "canonical_write_allowed": False,
}

OFFICIAL_NORMALIZED_REQUIREMENTS = (
    "tính đơn điệu và cực trị",
    "giá trị lớn nhất và giá trị nhỏ nhất",
    "tiệm cận và khảo sát đồ thị",
    "ứng dụng đạo hàm và khảo sát hàm số vào thực tiễn",
    "khái niệm và tính chất nguyên hàm",
    "nguyên hàm của một số hàm số sơ cấp",
    "tích phân và tính chất",
    "diện tích, thể tích và bài toán thực tiễn",
    "vectơ và tọa độ trong không gian",
    "phương trình mặt phẳng",
    "phương trình đường thẳng trong không gian",
    "góc và khoảng cách bằng phương pháp tọa độ",
    "phương trình mặt cầu",
    "vận dụng vào thực tiễn",
    "các số đo mức độ phân tán của mẫu số liệu ghép nhóm",
    "ý nghĩa và diễn giải các số đặc trưng trong thực tiễn",
    "xác suất có điều kiện",
    "xác suất toàn phần",
    "công thức Bayes",
    "sơ đồ hình cây và ứng dụng thực tiễn",
)


@dataclass(frozen=True, slots=True, order=True)
class FullScopeAlignmentIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class FullScopeAlignmentPreview:
    candidate_code: str
    dataset_code: str
    subject_code: str
    chapters: tuple[dict[str, Any], ...]
    topics: tuple[dict[str, Any], ...]
    problem_types: tuple[dict[str, Any], ...]
    concepts: tuple[dict[str, Any], ...]
    learning_outcomes: tuple[dict[str, Any], ...]
    concept_relations: tuple[dict[str, Any], ...]
    problem_type_concepts: tuple[dict[str, Any], ...]
    problem_type_learning_outcomes: tuple[dict[str, Any], ...]
    cross_scope_relations: tuple[dict[str, Any], ...]
    official_scope_bindings: tuple[dict[str, Any], ...]
    learning_outcome_requirement_bindings: dict[str, str]
    schema_enrichment_required: bool
    enrichment_blockers: tuple[dict[str, Any], ...]
    fingerprint: str

    @property
    def counts(self) -> dict[str, int]:
        return {
            "chapters": len(self.chapters),
            "topics": len(self.topics),
            "problem_types": len(self.problem_types),
            "concepts": len(self.concepts),
            "learning_outcomes": len(self.learning_outcomes),
            "concept_relations": len(self.concept_relations),
            "problem_type_concepts": len(self.problem_type_concepts),
            "problem_type_learning_outcomes": len(
                self.problem_type_learning_outcomes
            ),
            "cross_scope_relations": len(self.cross_scope_relations),
            "official_scope_bindings": len(self.official_scope_bindings),
            "learning_outcome_requirement_bindings": len(
                self.learning_outcome_requirement_bindings
            ),
            "enrichment_blockers": len(self.enrichment_blockers),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_code": self.candidate_code,
            "dataset_code": self.dataset_code,
            "subject_code": self.subject_code,
            "counts": self.counts,
            "schema_enrichment_required": self.schema_enrichment_required,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class FullScopeAlignmentReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    base_repo_commit: str | None
    input_audit_aggregate_sha256: str | None
    aggregate_semantic_sha256: str | None
    activation_allowed: bool
    database_import_allowed: bool
    canonical_write_allowed: bool
    curriculum_import_service_allowed: bool
    schema_enrichment_required: bool
    enrichment_blockers_count: int
    preview_fingerprint: str | None
    errors: tuple[FullScopeAlignmentIssue, ...]
    preview: FullScopeAlignmentPreview | None

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
            "input_audit_aggregate_sha256": self.input_audit_aggregate_sha256,
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "activation_allowed": self.activation_allowed,
            "database_import_allowed": self.database_import_allowed,
            "canonical_write_allowed": self.canonical_write_allowed,
            "curriculum_import_service_allowed": (
                self.curriculum_import_service_allowed
            ),
            "schema_enrichment_required": self.schema_enrichment_required,
            "enrichment_blockers_count": self.enrichment_blockers_count,
            "preview_fingerprint": self.preview_fingerprint,
            "errors": [asdict(issue) for issue in self.errors],
        }


class FullScopeAlignmentPreviewComposer:
    """Read-only in-memory composer for curriculum graph alignment preview."""

    @classmethod
    def compose(
        cls,
        alignment_path: Path,
        repo_root: Path,
    ) -> tuple[FullScopeAlignmentPreview | None, list[FullScopeAlignmentIssue]]:
        issues: list[FullScopeAlignmentIssue] = []

        def _load_json(file_path: Path) -> Any:
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                issues.append(
                    FullScopeAlignmentIssue(
                        check="preview_composition",
                        code="JSON_LOAD_ERROR",
                        location=file_path.name,
                        message=f"Failed to read {file_path.name}: {e}",
                    )
                )
                return None

        manifest = _load_json(alignment_path / "candidate_manifest.json") or {}
        chapters_data = _load_json(alignment_path / "chapters.json") or []
        topics_data = _load_json(alignment_path / "topics.json") or []
        pt_align_data = (
            _load_json(alignment_path / "problem_type_alignment.json") or []
        )
        cb_data = (
            _load_json(alignment_path / "component_bindings.json") or {}
        ).get("components", {})
        cross_rel_data = (
            _load_json(alignment_path / "cross_scope_relations.json") or []
        )
        lo_req_data = (
            _load_json(
                alignment_path / "learning_outcome_requirement_bindings.json"
            )
            or {}
        )
        scope_bindings_data = (
            _load_json(alignment_path / "official_scope_bindings.json") or []
        )

        pt_align_map: dict[str, dict[str, Any]] = {
            row["problem_type_code"]: row
            for row in pt_align_data
            if isinstance(row, dict) and "problem_type_code" in row
        }

        # 1. Problem types composition with topic_code remapping
        composed_pts: list[dict[str, Any]] = []
        enrichment_blockers: list[dict[str, Any]] = []
        seen_pt_codes: dict[str, dict[str, Any]] = {}

        for comp_name, comp_info in cb_data.items():
            if "files" in comp_info and "problem_types.json" in comp_info["files"]:
                base = repo_root / comp_info["base_path"]
                src_pts = _load_json(base / "problem_types.json") or []
                for pt in src_pts:
                    code = pt.get("code")
                    if code in pt_align_map:
                        align_entry = pt_align_map[code]
                        row = copy.deepcopy(pt)
                        row["topic_code"] = align_entry.get("target_topic_code")
                        if code in seen_pt_codes:
                            if seen_pt_codes[code] != row:
                                issues.append(
                                    FullScopeAlignmentIssue(
                                        check="payload_conflict_prevention",
                                        code="CONFLICTING_CODE_PAYLOAD",
                                        location=f"problem_types[{code}]",
                                        message=f"Problem type code {code!r} has conflicting payloads across components.",
                                    )
                                )
                        else:
                            seen_pt_codes[code] = row
                            composed_pts.append(row)
            elif "path" in comp_info:
                tax_file = repo_root / comp_info["path"]
                src_data = _load_json(tax_file) or {}
                for pt in src_data.get("problem_types", []):
                    code = pt.get("code")
                    if code in pt_align_map:
                        align_entry = pt_align_map[code]
                        row = copy.deepcopy(pt)
                        row["topic_code"] = align_entry.get("target_topic_code")
                        if code in seen_pt_codes:
                            if seen_pt_codes[code] != row:
                                issues.append(
                                    FullScopeAlignmentIssue(
                                        check="payload_conflict_prevention",
                                        code="CONFLICTING_CODE_PAYLOAD",
                                        location=f"problem_types[{code}]",
                                        message=f"Problem type code {code!r} has conflicting payloads across components.",
                                    )
                                )
                        else:
                            seen_pt_codes[code] = row
                            composed_pts.append(row)

                        missing: list[str] = []
                        for f in ["name", "order_index"]:
                            if f not in pt or pt[f] is None:
                                missing.append(f)
                        if missing:
                            enrichment_blockers.append(
                                {
                                    "entity_type": "problem_type",
                                    "code": code,
                                    "source_component": comp_name,
                                    "missing_fields": missing,
                                    "status": "ENRICHMENT_REQUIRED",
                                }
                            )

        # 2. Concepts composition and conflict detection
        concepts_by_code: dict[str, dict[str, Any]] = {}
        for comp_name, comp_info in cb_data.items():
            if "files" in comp_info and "concepts.json" in comp_info["files"]:
                base = repo_root / comp_info["base_path"]
                for r in _load_json(base / "concepts.json") or []:
                    code = r.get("code")
                    if code in concepts_by_code:
                        if concepts_by_code[code] != r:
                            issues.append(
                                FullScopeAlignmentIssue(
                                    check="payload_conflict_prevention",
                                    code="CONFLICTING_CODE_PAYLOAD",
                                    location=f"concepts[{code}]",
                                    message=f"Concept code {code!r} has conflicting payloads across components.",
                                )
                            )
                    else:
                        concepts_by_code[code] = copy.deepcopy(r)
            elif "path" in comp_info:
                tax_file = repo_root / comp_info["path"]
                src_data = _load_json(tax_file) or {}
                for r in src_data.get("concepts", []):
                    code = r.get("code")
                    if code in concepts_by_code:
                        if concepts_by_code[code] != r:
                            issues.append(
                                FullScopeAlignmentIssue(
                                    check="payload_conflict_prevention",
                                    code="CONFLICTING_CODE_PAYLOAD",
                                    location=f"concepts[{code}]",
                                    message=f"Concept code {code!r} has conflicting payloads across components.",
                                )
                            )
                    else:
                        concepts_by_code[code] = copy.deepcopy(r)
                        if "name" not in r or r["name"] is None:
                            enrichment_blockers.append(
                                {
                                    "entity_type": "concept",
                                    "code": code,
                                    "source_component": comp_name,
                                    "missing_fields": ["name"],
                                    "status": "ENRICHMENT_REQUIRED",
                                }
                            )

        # 3. Learning outcomes composition and conflict detection
        los_by_code: dict[str, dict[str, Any]] = {}
        for comp_name, comp_info in cb_data.items():
            if (
                "files" in comp_info
                and "learning_outcomes.json" in comp_info["files"]
            ):
                base = repo_root / comp_info["base_path"]
                for r in _load_json(base / "learning_outcomes.json") or []:
                    code = r.get("code")
                    if code in los_by_code:
                        if los_by_code[code] != r:
                            issues.append(
                                FullScopeAlignmentIssue(
                                    check="payload_conflict_prevention",
                                    code="CONFLICTING_CODE_PAYLOAD",
                                    location=f"learning_outcomes[{code}]",
                                    message=f"Learning outcome code {code!r} has conflicting payloads across components.",
                                )
                            )
                    else:
                        los_by_code[code] = copy.deepcopy(r)
            elif "path" in comp_info:
                tax_file = repo_root / comp_info["path"]
                src_data = _load_json(tax_file) or {}
                for r in src_data.get("learning_outcomes", []):
                    code = r.get("code")
                    if code in los_by_code:
                        if los_by_code[code] != r:
                            issues.append(
                                FullScopeAlignmentIssue(
                                    check="payload_conflict_prevention",
                                    code="CONFLICTING_CODE_PAYLOAD",
                                    location=f"learning_outcomes[{code}]",
                                    message=f"Learning outcome code {code!r} has conflicting payloads across components.",
                                )
                            )
                    else:
                        los_by_code[code] = copy.deepcopy(r)
                        if "description" not in r or r["description"] is None:
                            enrichment_blockers.append(
                                {
                                    "entity_type": "learning_outcome",
                                    "code": code,
                                    "source_component": comp_name,
                                    "missing_fields": ["description"],
                                    "status": "ENRICHMENT_REQUIRED",
                                }
                            )

        # 4. Concept relations composition
        c_rels: list[dict[str, Any]] = []
        for comp_name, comp_info in cb_data.items():
            if (
                "files" in comp_info
                and "concept_relations.json" in comp_info["files"]
            ):
                base = repo_root / comp_info["base_path"]
                for r in _load_json(base / "concept_relations.json") or []:
                    c_rels.append(copy.deepcopy(r))
        for r in cross_rel_data:
            c_rels.append(copy.deepcopy(r))

        # 5. Problem type concepts
        pt_concepts: list[dict[str, Any]] = []
        for comp_name, comp_info in cb_data.items():
            if (
                "files" in comp_info
                and "problem_type_concepts.json" in comp_info["files"]
            ):
                base = repo_root / comp_info["base_path"]
                for r in _load_json(base / "problem_type_concepts.json") or []:
                    pt_concepts.append(copy.deepcopy(r))
            elif "path" in comp_info:
                tax_file = repo_root / comp_info["path"]
                src_data = _load_json(tax_file) or {}
                for pt_code, mappings in src_data.get("mappings", {}).items():
                    if isinstance(mappings, list):
                        for m in mappings:
                            if isinstance(m, dict):
                                pt_concepts.append(
                                    {
                                        "problem_type_code": pt_code,
                                        "concept_code": m.get("concept_code"),
                                        "weight": m.get("weight", 1.0),
                                        "is_primary": m.get("is_primary", True),
                                    }
                                )

        # 6. Problem type learning outcomes
        pt_los: list[dict[str, Any]] = []
        for comp_name, comp_info in cb_data.items():
            if (
                "files" in comp_info
                and "problem_type_learning_outcomes.json" in comp_info["files"]
            ):
                base = repo_root / comp_info["base_path"]
                for r in (
                    _load_json(base / "problem_type_learning_outcomes.json")
                    or []
                ):
                    pt_los.append(copy.deepcopy(r))
            elif "path" in comp_info:
                tax_file = repo_root / comp_info["path"]
                src_data = _load_json(tax_file) or {}
                for pt_code, lo_val in src_data.get(
                    "problem_type_learning_outcome", {}
                ).items():
                    if isinstance(lo_val, str):
                        pt_los.append(
                            {
                                "problem_type_code": pt_code,
                                "learning_outcome_code": lo_val,
                                "weight": 1.0,
                            }
                        )
                    elif isinstance(lo_val, list):
                        for l_code in lo_val:
                            pt_los.append(
                                {
                                    "problem_type_code": pt_code,
                                    "learning_outcome_code": l_code,
                                    "weight": 1.0,
                                }
                            )

        # Build preview dict deterministically
        preview_dict = {
            "candidate_code": manifest.get("candidate_code", ""),
            "dataset_code": manifest.get("dataset_code", ""),
            "subject_code": manifest.get("subject_code", ""),
            "chapters": sorted(
                chapters_data,
                key=lambda x: (x.get("order_index", 0), x.get("code", "")),
            ),
            "topics": sorted(
                topics_data,
                key=lambda x: (
                    x.get("chapter_code", ""),
                    x.get("order_index", 0),
                    x.get("code", ""),
                ),
            ),
            "problem_types": sorted(
                composed_pts,
                key=lambda x: (x.get("topic_code", ""), x.get("code", "")),
            ),
            "concepts": sorted(
                concepts_by_code.values(), key=lambda x: x.get("code", "")
            ),
            "learning_outcomes": sorted(
                los_by_code.values(), key=lambda x: x.get("code", "")
            ),
            "concept_relations": sorted(
                c_rels,
                key=lambda x: (
                    x.get("source_code", ""),
                    x.get("target_code", ""),
                    x.get("relation_type", ""),
                ),
            ),
            "problem_type_concepts": sorted(
                pt_concepts,
                key=lambda x: (
                    x.get("problem_type_code", ""),
                    x.get("concept_code", ""),
                ),
            ),
            "problem_type_learning_outcomes": sorted(
                pt_los,
                key=lambda x: (
                    x.get("problem_type_code", ""),
                    x.get("learning_outcome_code", ""),
                ),
            ),
            "cross_scope_relations": sorted(
                cross_rel_data,
                key=lambda x: (
                    x.get("source_code", ""),
                    x.get("target_code", ""),
                ),
            ),
            "official_scope_bindings": sorted(
                scope_bindings_data,
                key=lambda x: x.get("official_scope_code", ""),
            ),
            "learning_outcome_requirement_bindings": dict(
                sorted(lo_req_data.items())
            ),
            "schema_enrichment_blockers": sorted(
                enrichment_blockers,
                key=lambda x: (x.get("entity_type", ""), x.get("code", "")),
            ),
        }

        canon = json.dumps(
            preview_dict, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        fingerprint = hashlib.sha256(canon).hexdigest()

        preview = FullScopeAlignmentPreview(
            candidate_code=preview_dict["candidate_code"],
            dataset_code=preview_dict["dataset_code"],
            subject_code=preview_dict["subject_code"],
            chapters=tuple(preview_dict["chapters"]),
            topics=tuple(preview_dict["topics"]),
            problem_types=tuple(preview_dict["problem_types"]),
            concepts=tuple(preview_dict["concepts"]),
            learning_outcomes=tuple(preview_dict["learning_outcomes"]),
            concept_relations=tuple(preview_dict["concept_relations"]),
            problem_type_concepts=tuple(preview_dict["problem_type_concepts"]),
            problem_type_learning_outcomes=tuple(
                preview_dict["problem_type_learning_outcomes"]
            ),
            cross_scope_relations=tuple(preview_dict["cross_scope_relations"]),
            official_scope_bindings=tuple(
                preview_dict["official_scope_bindings"]
            ),
            learning_outcome_requirement_bindings=preview_dict[
                "learning_outcome_requirement_bindings"
            ],
            schema_enrichment_required=len(enrichment_blockers) > 0,
            enrichment_blockers=tuple(preview_dict["schema_enrichment_blockers"]),
            fingerprint=fingerprint,
        )

        return preview, issues


class FullScopeAlignmentValidator:
    """Validate DATA-MATH12-033 GDPT 2018 Grade 12 Math full-scope graph alignment candidate."""

    def validate(
        self,
        alignment_path: Path = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
        *,
        repo_root: Path = REPO_ROOT,
    ) -> FullScopeAlignmentReport:
        path = alignment_path.resolve()
        repo_root = repo_root.resolve()
        initial: list[FullScopeAlignmentIssue] = []

        self._check_required_files(path, initial)
        contract = self._load_object(path / "data_contract.json", initial)
        manifest = self._load_object(path / "candidate_manifest.json", initial)
        chapters = self._load_list(path / "chapters.json", initial)
        topics = self._load_list(path / "topics.json", initial)
        pt_align = self._load_list(
            path / "problem_type_alignment.json", initial
        )
        scope_bindings = self._load_list(
            path / "official_scope_bindings.json", initial
        )
        lo_bindings = self._load_object(
            path / "learning_outcome_requirement_bindings.json", initial
        )
        comp_bindings = self._load_object(
            path / "component_bindings.json", initial
        )
        cross_rel = self._load_list(
            path / "cross_scope_relations.json", initial
        )
        quarantine = self._load_object(path / "legacy_quarantine.json", initial)
        coverage_gate = self._load_object(path / "coverage_gate.json", initial)
        activation_policy = self._load_object(
            path / "activation_policy.json", initial
        )
        materialization_plan = self._load_object(
            path / "materialization_plan.json", initial
        )

        # Build in-memory preview
        preview, preview_issues = FullScopeAlignmentPreviewComposer.compose(
            path, repo_root
        )
        initial.extend(preview_issues)

        checks_to_errors: dict[str, list[FullScopeAlignmentIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(path),
            "curated_hash_contract": self._validate_curated_hash_contract(
                path, contract
            ),
            "audit_aggregate_binding": self._validate_audit_aggregate_binding(
                contract, manifest
            ),
            "component_git_blob_bindings": (
                self._validate_component_git_blobs(comp_bindings, repo_root)
            ),
            "candidate_chapter_structure": (
                self._validate_candidate_chapter_structure(chapters)
            ),
            "candidate_topic_structure": (
                self._validate_candidate_topic_structure(topics, chapters)
            ),
            "problem_type_alignment_rules": (
                self._validate_problem_type_alignment_rules(
                    pt_align, topics, comp_bindings, repo_root
                )
            ),
            "official_scope_bindings_coverage": (
                self._validate_official_scope_bindings(scope_bindings)
            ),
            "learning_outcome_requirement_bindings": (
                self._validate_learning_outcome_bindings(
                    lo_bindings, scope_bindings, preview
                )
            ),
            "cross_scope_relations_validity": (
                self._validate_cross_scope_relations(cross_rel, preview)
            ),
            "payload_conflict_prevention": [
                issue
                for issue in initial
                if issue.check == "payload_conflict_prevention"
            ],
            "classification_policy_guard": (
                self._validate_classification_policy(manifest)
            ),
            "legacy_quarantine_policy": (
                self._validate_legacy_quarantine(quarantine)
            ),
            "critical_boundaries": self._validate_critical_boundaries(
                activation_policy, manifest, contract
            ),
        }

        # Check aggregate hash
        aggregate = self._aggregate_hash(path, contract)
        aggregate_errors: list[FullScopeAlignmentIssue] = []
        if aggregate != EXPECTED_ALIGNMENT_AGGREGATE_SHA256:
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected {EXPECTED_ALIGNMENT_AGGREGATE_SHA256}, got {aggregate!r}.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_ALIGNMENT_AGGREGATE_SHA256
        ):
            aggregate_errors.append(
                self._issue(
                    "aggregate_hash",
                    "CONTRACT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    "The contract does not bind the locked DATA-MATH12-033 aggregate.",
                )
            )
        checks_to_errors["aggregate_hash"] = aggregate_errors

        # Check exact invariants
        invariants_errors: list[FullScopeAlignmentIssue] = []
        actual_invariants = {
            "chapters": len(chapters),
            "topics": len(topics),
            "problem_types": len(pt_align),
            "official_core_scopes": len(scope_bindings),
            "official_normalized_requirements": sum(
                len(r.get("normalized_requirements", []))
                for r in scope_bindings
            ),
            "learning_outcome_requirement_bindings": len(lo_bindings),
            "cross_scope_relations": len(cross_rel),
            "legacy_quarantine_entries": len(quarantine.get("entries", [])),
            "activation_allowed": activation_policy.get(
                "activation_allowed", True
            ),
            "database_import_allowed": activation_policy.get(
                "database_import_allowed", True
            ),
            "canonical_write_allowed": activation_policy.get(
                "canonical_write_allowed", True
            ),
        }
        if actual_invariants != EXPECTED_INVARIANTS:
            invariants_errors.append(
                self._issue(
                    "exact_invariants",
                    "INVARIANT_COUNT_MISMATCH",
                    "data_contract.json",
                    f"Expected invariants {EXPECTED_INVARIANTS!r}, got {actual_invariants!r}.",
                )
            )
        checks_to_errors["exact_invariants"] = invariants_errors

        # Schema enrichment reporting check
        enrichment_errors: list[FullScopeAlignmentIssue] = []
        if preview and not preview.schema_enrichment_required:
            enrichment_errors.append(
                self._issue(
                    "schema_enrichment_reporting",
                    "SCHEMA_ENRICHMENT_NOT_FLAGGED",
                    "materialization_plan.json",
                    "Schema enrichment must be flagged as required for candidate.",
                )
            )
        checks_to_errors["schema_enrichment_reporting"] = enrichment_errors

        errors = tuple(
            sorted(
                issue for issues in checks_to_errors.values() for issue in issues
            )
        )
        checks = {
            name: not issues for name, issues in checks_to_errors.items()
        }

        counts = {
            "chapters": len(chapters),
            "topics": len(topics),
            "problem_types": len(pt_align),
            "concepts": len(preview.concepts) if preview else 0,
            "learning_outcomes": len(preview.learning_outcomes)
            if preview
            else 0,
            "concept_relations": len(preview.concept_relations)
            if preview
            else 0,
            "official_core_scopes": len(scope_bindings),
            "official_normalized_requirements": actual_invariants[
                "official_normalized_requirements"
            ],
            "cross_scope_relations": len(cross_rel),
            "enrichment_blockers": len(preview.enrichment_blockers)
            if preview
            else 0,
        }

        return FullScopeAlignmentReport(
            dataset_path=str(path),
            status="PASS" if not errors else "FAIL",
            checks=checks,
            counts=counts,
            base_repo_commit=contract.get("base_repo_commit"),
            input_audit_aggregate_sha256=contract.get(
                "input_audit_aggregate_sha256"
            ),
            aggregate_semantic_sha256=aggregate,
            activation_allowed=activation_policy.get(
                "activation_allowed", False
            )
            is True,
            database_import_allowed=activation_policy.get(
                "database_import_allowed", False
            )
            is True,
            canonical_write_allowed=activation_policy.get(
                "canonical_write_allowed", False
            )
            is True,
            curriculum_import_service_allowed=activation_policy.get(
                "curriculum_import_service_allowed", False
            )
            is True,
            schema_enrichment_required=(
                preview.schema_enrichment_required if preview else True
            ),
            enrichment_blockers_count=(
                len(preview.enrichment_blockers) if preview else 0
            ),
            preview_fingerprint=preview.fingerprint if preview else None,
            errors=errors,
            preview=preview,
        )

    # ------------------------------------------------------------------
    # Check Implementations
    # ------------------------------------------------------------------

    def _check_required_files(
        self, path: Path, issues: list[FullScopeAlignmentIssue]
    ) -> None:
        for file_name in REQUIRED_FILES:
            target = path / file_name
            if not target.is_file():
                issues.append(
                    self._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        file_name,
                        f"Missing required file {file_name}.",
                    )
                )

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        pdf_files = list(path.rglob("*.pdf"))
        if pdf_files:
            issues.append(
                self._issue(
                    "no_pdf_binaries",
                    "PDF_BINARY_PRESENT",
                    pdf_files[0].name,
                    f"Found {len(pdf_files)} PDF binaries in alignment directory.",
                )
            )
        return issues

    def _validate_curated_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
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
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "INVALID_SEMANTIC_HASH_CONTRACT",
                    "data_contract.json",
                    "semantic_sha256 and semantic_files_order are required.",
                )
            )
            return issues

        if (
            set(order) != set(expected_hashes)
            or tuple(order) != SEMANTIC_FILES_ORDER
        ):
            issues.append(
                self._issue(
                    "curated_hash_contract",
                    "SEMANTIC_FILE_SET_MISMATCH",
                    "data_contract.json",
                    "Semantic file order does not match expected candidate files.",
                )
            )

        for name, expected in expected_hashes.items():
            file_path = path / str(name)
            actual = (
                self._semantic_hash(file_path) if file_path.is_file() else None
            )
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

    def _validate_audit_aggregate_binding(
        self, contract: dict[str, Any], manifest: dict[str, Any]
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        contract_audit = contract.get("input_audit_aggregate_sha256")
        manifest_audit = manifest.get("input_audit_aggregate_sha256")
        manifest_dataset = manifest.get("input_audit_dataset")

        if contract_audit != EXPECTED_INPUT_AUDIT_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "audit_aggregate_binding",
                    "CONTRACT_AUDIT_AGGREGATE_MISMATCH",
                    "data_contract.json",
                    f"Expected input_audit_aggregate_sha256 {EXPECTED_INPUT_AUDIT_AGGREGATE_SHA256!r}, got {contract_audit!r}.",
                )
            )
        if manifest_audit != EXPECTED_INPUT_AUDIT_AGGREGATE_SHA256:
            issues.append(
                self._issue(
                    "audit_aggregate_binding",
                    "MANIFEST_AUDIT_AGGREGATE_MISMATCH",
                    "candidate_manifest.json",
                    f"Expected input_audit_aggregate_sha256 {EXPECTED_INPUT_AUDIT_AGGREGATE_SHA256!r}, got {manifest_audit!r}.",
                )
            )
        if manifest_dataset != "DATA-MATH12-032":
            issues.append(
                self._issue(
                    "audit_aggregate_binding",
                    "MANIFEST_AUDIT_DATASET_MISMATCH",
                    "candidate_manifest.json",
                    f"Expected input_audit_dataset 'DATA-MATH12-032', got {manifest_dataset!r}.",
                )
            )

        contract_commit = contract.get("base_repo_commit")
        manifest_commit = manifest.get("base_repo_commit")
        if contract_commit != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "audit_aggregate_binding",
                    "BASE_REPO_COMMIT_MISMATCH",
                    "data_contract.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT!r}, got {contract_commit!r}.",
                )
            )
        if manifest_commit != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "audit_aggregate_binding",
                    "MANIFEST_BASE_COMMIT_MISMATCH",
                    "candidate_manifest.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT!r}, got {manifest_commit!r}.",
                )
            )

        return issues

    def _validate_component_git_blobs(
        self, comp_bindings: dict[str, Any], repo_root: Path
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        base_commit = comp_bindings.get("base_repo_commit")
        if base_commit != EXPECTED_BASE_REPO_COMMIT:
            issues.append(
                self._issue(
                    "component_git_blob_bindings",
                    "COMPONENT_BASE_COMMIT_MISMATCH",
                    "component_bindings.json",
                    f"Expected base_repo_commit {EXPECTED_BASE_REPO_COMMIT!r}, got {base_commit!r}.",
                )
            )

        components = comp_bindings.get("components", {})
        if not isinstance(components, dict):
            issues.append(
                self._issue(
                    "component_git_blob_bindings",
                    "COMPONENTS_STRUCTURE_INVALID",
                    "component_bindings.json",
                    "components must be a dict.",
                )
            )
            return issues

        for comp_name, comp_info in components.items():
            if "files" in comp_info:
                base_dir = repo_root / comp_info.get("base_path", "")
                for fname, expected_hash in comp_info.get("files", {}).items():
                    target = base_dir / fname
                    if not target.is_file():
                        issues.append(
                            self._issue(
                                "component_git_blob_bindings",
                                "COMPONENT_FILE_MISSING",
                                f"{comp_name}/{fname}",
                                f"Component file {target} does not exist.",
                            )
                        )
                    else:
                        actual = self._git_blob_sha1(target)
                        if actual != expected_hash:
                            issues.append(
                                self._issue(
                                    "component_git_blob_bindings",
                                    "COMPONENT_GIT_BLOB_MISMATCH",
                                    f"{comp_name}/{fname}",
                                    f"Expected Git blob SHA-1 {expected_hash!r}, got {actual!r}.",
                                )
                            )
            elif "path" in comp_info:
                target = repo_root / comp_info.get("path", "")
                expected_hash = comp_info.get("git_blob_sha1")
                if not target.is_file():
                    issues.append(
                        self._issue(
                            "component_git_blob_bindings",
                            "COMPONENT_FILE_MISSING",
                            comp_name,
                            f"Component file {target} does not exist.",
                        )
                    )
                else:
                    actual = self._git_blob_sha1(target)
                    if actual != expected_hash:
                        issues.append(
                            self._issue(
                                "component_git_blob_bindings",
                                "COMPONENT_GIT_BLOB_MISMATCH",
                                comp_name,
                                f"Expected Git blob SHA-1 {expected_hash!r}, got {actual!r}.",
                            )
                        )

        return issues

    def _validate_candidate_chapter_structure(
        self, chapters: list[dict[str, Any]]
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        if len(chapters) != 5:
            issues.append(
                self._issue(
                    "candidate_chapter_structure",
                    "CHAPTER_COUNT_MISMATCH",
                    "chapters.json",
                    f"Expected exactly 5 candidate chapters, got {len(chapters)}.",
                )
            )

        codes = tuple(r.get("code") for r in chapters if isinstance(r, dict))
        for expected in EXPECTED_CHAPTER_CODES:
            if expected not in codes:
                issues.append(
                    self._issue(
                        "candidate_chapter_structure",
                        "MISSING_REQUIRED_CHAPTER",
                        f"chapters.json[{expected}]",
                        f"Required chapter {expected!r} missing from candidate chapters.",
                    )
                )

        for code in codes:
            if code not in EXPECTED_CHAPTER_CODES:
                if code == "VECTORS_GEOMETRY":
                    issues.append(
                        self._issue(
                            "candidate_chapter_structure",
                            "VECTORS_GEOMETRY_AS_CANDIDATE_CHAPTER",
                            "chapters.json",
                            "VECTORS_GEOMETRY must not be a separate candidate chapter.",
                        )
                    )
                elif code == "EXPONENTIAL_LOGARITHM":
                    issues.append(
                        self._issue(
                            "candidate_chapter_structure",
                            "EXPONENTIAL_LOGARITHM_IN_CORE_CHAPTERS",
                            "chapters.json",
                            "EXPONENTIAL_LOGARITHM must not be in candidate core chapters.",
                        )
                    )
                else:
                    issues.append(
                        self._issue(
                            "candidate_chapter_structure",
                            "UNEXPECTED_CANDIDATE_CHAPTER",
                            f"chapters.json[{code}]",
                            f"Unexpected chapter {code!r} found in candidate chapters.",
                        )
                    )

        return issues

    def _validate_candidate_topic_structure(
        self, topics: list[dict[str, Any]], chapters: list[dict[str, Any]]
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        if len(topics) != 24:
            issues.append(
                self._issue(
                    "candidate_topic_structure",
                    "TOPIC_COUNT_MISMATCH",
                    "topics.json",
                    f"Expected exactly 24 topics, got {len(topics)}.",
                )
            )

        valid_chapter_codes = {
            r.get("code") for r in chapters if isinstance(r, dict)
        }
        for idx, t in enumerate(topics):
            if not isinstance(t, dict):
                continue
            code = t.get("code", f"index_{idx}")
            ch_code = t.get("chapter_code")
            if ch_code not in valid_chapter_codes:
                issues.append(
                    self._issue(
                        "candidate_topic_structure",
                        "UNDECLARED_TOPIC_CHAPTER",
                        f"topics.json[{code}]",
                        f"Topic {code!r} references undeclared chapter {ch_code!r}.",
                    )
                )

            src_comp = t.get("source_component")
            if src_comp == "VECTOR_STAGING" and ch_code != "OXYZ_CHAPTER":
                issues.append(
                    self._issue(
                        "candidate_topic_structure",
                        "VECTOR_TOPIC_NOT_UNDER_OXYZ",
                        f"topics.json[{code}]",
                        f"Vector topic {code!r} must be under OXYZ_CHAPTER, got {ch_code!r}.",
                    )
                )
            elif (
                src_comp == "GROUPED_DISPERSION_STAGING"
                and ch_code != "GROUPED_DATA_STATISTICS"
            ):
                issues.append(
                    self._issue(
                        "candidate_topic_structure",
                        "GROUPED_TOPIC_NOT_UNDER_STATISTICS",
                        f"topics.json[{code}]",
                        f"Grouped statistics topic {code!r} must be under GROUPED_DATA_STATISTICS, got {ch_code!r}.",
                    )
                )

        return issues

    def _validate_problem_type_alignment_rules(
        self,
        pt_align: list[dict[str, Any]],
        topics: list[dict[str, Any]],
        comp_bindings: dict[str, Any],
        repo_root: Path,
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        if len(pt_align) != 75:
            issues.append(
                self._issue(
                    "problem_type_alignment_rules",
                    "PROBLEM_TYPE_ALIGNMENT_COUNT_MISMATCH",
                    "problem_type_alignment.json",
                    f"Expected exactly 75 problem type alignments, got {len(pt_align)}.",
                )
            )

        declared_topic_codes = {
            t.get("code"): t.get("chapter_code")
            for t in topics
            if isinstance(t, dict)
        }

        # Load available problem types per source component
        component_pts: dict[str, set[str]] = {}
        for comp_name, comp_info in comp_bindings.get("components", {}).items():
            if (
                "files" in comp_info
                and "problem_types.json" in comp_info["files"]
            ):
                base = repo_root / comp_info["base_path"]
                pt_file = base / "problem_types.json"
                if pt_file.is_file():
                    try:
                        data = json.loads(pt_file.read_text(encoding="utf-8"))
                        component_pts[comp_name] = {
                            row.get("code")
                            for row in data
                            if isinstance(row, dict)
                        }
                    except (OSError, json.JSONDecodeError):
                        component_pts[comp_name] = set()
            elif "path" in comp_info:
                tax_file = repo_root / comp_info["path"]
                if tax_file.is_file():
                    try:
                        data = json.loads(tax_file.read_text(encoding="utf-8"))
                        component_pts[comp_name] = {
                            row.get("code")
                            for row in data.get("problem_types", [])
                            if isinstance(row, dict)
                        }
                    except (OSError, json.JSONDecodeError):
                        component_pts[comp_name] = set()

        seen_codes: dict[str, dict[str, Any]] = {}
        for pt in pt_align:
            if not isinstance(pt, dict):
                continue
            code = pt.get("problem_type_code")
            target_topic = pt.get("target_topic_code")
            source = pt.get("record_source")

            if code in seen_codes:
                issues.append(
                    self._issue(
                        "problem_type_alignment_rules",
                        "DUPLICATE_PROBLEM_TYPE_ALIGNMENT",
                        f"problem_type_alignment.json[{code}]",
                        f"Duplicate problem type code {code!r} in alignment list.",
                    )
                )
                if seen_codes[code] != pt:
                    issues.append(
                        self._issue(
                            "payload_conflict_prevention",
                            "CONFLICTING_CODE_PAYLOAD",
                            f"problem_type_alignment.json[{code}]",
                            f"Duplicate problem type code {code!r} has conflicting payloads.",
                        )
                    )
            else:
                seen_codes[code] = pt

            if target_topic not in declared_topic_codes:
                issues.append(
                    self._issue(
                        "problem_type_alignment_rules",
                        "UNDECLARED_TARGET_TOPIC",
                        f"problem_type_alignment.json[{code}]",
                        f"Problem type {code!r} references undeclared target topic {target_topic!r}.",
                    )
                )

            if source not in component_pts:
                issues.append(
                    self._issue(
                        "problem_type_alignment_rules",
                        "UNKNOWN_RECORD_SOURCE",
                        f"problem_type_alignment.json[{code}]",
                        f"Problem type {code!r} references unknown source {source!r}.",
                    )
                )
            elif code not in component_pts[source]:
                issues.append(
                    self._issue(
                        "problem_type_alignment_rules",
                        "PROBLEM_TYPE_NOT_FOUND_IN_SOURCE",
                        f"problem_type_alignment.json[{code}]",
                        f"Problem type {code!r} not found in component {source!r}.",
                    )
                )

            # Check vector remapping
            if source == "VECTOR_STAGING":
                ch = declared_topic_codes.get(target_topic)
                if ch != "OXYZ_CHAPTER":
                    issues.append(
                        self._issue(
                            "problem_type_alignment_rules",
                            "VECTOR_PT_NOT_UNDER_OXYZ",
                            f"problem_type_alignment.json[{code}]",
                            f"Vector problem type {code!r} target topic {target_topic!r} must belong to OXYZ_CHAPTER, got {ch!r}.",
                        )
                    )
            elif source == "GROUPED_DISPERSION_STAGING":
                ch = declared_topic_codes.get(target_topic)
                if ch != "GROUPED_DATA_STATISTICS":
                    issues.append(
                        self._issue(
                            "problem_type_alignment_rules",
                            "GROUPED_PT_NOT_UNDER_STATISTICS",
                            f"problem_type_alignment.json[{code}]",
                            f"Grouped problem type {code!r} target topic {target_topic!r} must belong to GROUPED_DATA_STATISTICS, got {ch!r}.",
                        )
                    )

        return issues

    def _validate_official_scope_bindings(
        self, scope_bindings: list[dict[str, Any]]
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        if len(scope_bindings) != 5:
            issues.append(
                self._issue(
                    "official_scope_bindings_coverage",
                    "SCOPE_BINDINGS_COUNT_MISMATCH",
                    "official_scope_bindings.json",
                    f"Expected 5 official scope bindings, got {len(scope_bindings)}.",
                )
            )

        core_codes = tuple(
            r.get("official_scope_code")
            for r in scope_bindings
            if isinstance(r, dict)
        )
        if core_codes != EXPECTED_OFFICIAL_CORE_SCOPES:
            issues.append(
                self._issue(
                    "official_scope_bindings_coverage",
                    "SCOPE_BINDINGS_CODES_MISMATCH",
                    "official_scope_bindings.json",
                    f"Expected scope bindings {EXPECTED_OFFICIAL_CORE_SCOPES!r}, got {core_codes!r}.",
                )
            )

        all_reqs: list[str] = []
        for row in scope_bindings:
            if isinstance(row, dict):
                reqs = row.get("normalized_requirements", [])
                all_reqs.extend(reqs)

        if len(all_reqs) != 20:
            issues.append(
                self._issue(
                    "official_scope_bindings_coverage",
                    "REQUIREMENT_COUNT_MISMATCH",
                    "official_scope_bindings.json",
                    f"Expected 20 normalized requirements total across scopes, got {len(all_reqs)}.",
                )
            )

        if len(set(all_reqs)) != len(all_reqs):
            issues.append(
                self._issue(
                    "official_scope_bindings_coverage",
                    "DUPLICATE_NORMALIZED_REQUIREMENT",
                    "official_scope_bindings.json",
                    "Duplicate normalized requirement found across official scope coverage lists.",
                )
            )

        for req in all_reqs:
            if req not in OFFICIAL_NORMALIZED_REQUIREMENTS:
                issues.append(
                    self._issue(
                        "official_scope_bindings_coverage",
                        "OFFICIAL_REQUIREMENT_MISMATCH",
                        f"official_scope_bindings.json[{req}]",
                        f"Requirement {req!r} does not match any official GDPT 2018 normalized requirement.",
                    )
                )

        return issues

    def _validate_learning_outcome_bindings(
        self,
        lo_bindings: dict[str, Any],
        scope_bindings: list[dict[str, Any]],
        preview: FullScopeAlignmentPreview | None,
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        if len(lo_bindings) != 34:
            issues.append(
                self._issue(
                    "learning_outcome_requirement_bindings",
                    "LO_BINDINGS_COUNT_MISMATCH",
                    "learning_outcome_requirement_bindings.json",
                    f"Expected 34 LO requirement bindings, got {len(lo_bindings)}.",
                )
            )

        official_reqs = {
            req
            for row in scope_bindings
            if isinstance(row, dict)
            for req in row.get("normalized_requirements", [])
        }

        composed_lo_codes = (
            {lo["code"] for lo in preview.learning_outcomes} if preview else set()
        )

        for lo_code, bound_req in lo_bindings.items():
            if bound_req not in official_reqs:
                issues.append(
                    self._issue(
                        "learning_outcome_requirement_bindings",
                        "LO_BOUND_TO_INVALID_REQUIREMENT",
                        f"learning_outcome_requirement_bindings.json[{lo_code}]",
                        f"LO {lo_code!r} bound to invalid requirement {bound_req!r}.",
                    )
                )
            if preview and lo_code not in composed_lo_codes:
                issues.append(
                    self._issue(
                        "learning_outcome_requirement_bindings",
                        "LO_BINDING_UNKNOWN_CODE",
                        f"learning_outcome_requirement_bindings.json[{lo_code}]",
                        f"Bound LO code {lo_code!r} not found in composed learning outcomes.",
                    )
                )

        return issues

    def _validate_cross_scope_relations(
        self,
        cross_rel: list[dict[str, Any]],
        preview: FullScopeAlignmentPreview | None,
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        if len(cross_rel) != 11:
            issues.append(
                self._issue(
                    "cross_scope_relations_validity",
                    "CROSS_SCOPE_RELATIONS_COUNT_MISMATCH",
                    "cross_scope_relations.json",
                    f"Expected 11 cross-scope relations, got {len(cross_rel)}.",
                )
            )

        all_concept_codes = (
            {c["code"] for c in preview.concepts} if preview else set()
        )

        for rel in cross_rel:
            if not isinstance(rel, dict):
                continue
            src = rel.get("source_code")
            tgt = rel.get("target_code")
            if preview:
                if src not in all_concept_codes:
                    issues.append(
                        self._issue(
                            "cross_scope_relations_validity",
                            "CROSS_SCOPE_RELATION_UNKNOWN_CONCEPT",
                            f"cross_scope_relations.json[{src}]",
                            f"Cross-scope relation source concept {src!r} does not exist after composition.",
                        )
                    )
                if tgt not in all_concept_codes:
                    issues.append(
                        self._issue(
                            "cross_scope_relations_validity",
                            "CROSS_SCOPE_RELATION_UNKNOWN_CONCEPT",
                            f"cross_scope_relations.json[{tgt}]",
                            f"Cross-scope relation target concept {tgt!r} does not exist after composition.",
                        )
                    )

        return issues

    def _validate_classification_policy(
        self, manifest: dict[str, Any]
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        policy = manifest.get("classification_policy", {})
        if not isinstance(policy, dict):
            issues.append(
                self._issue(
                    "classification_policy_guard",
                    "CLASSIFICATION_POLICY_MISSING",
                    "candidate_manifest.json",
                    "classification_policy must be present.",
                )
            )
            return issues

        derived_scope = policy.get(
            "chapters_topics_problem_types_concepts_relations"
        )
        if derived_scope != "COACH_LEARNING_DERIVED":
            issues.append(
                self._issue(
                    "classification_policy_guard",
                    "RAW_DERIVED_RELABELED_AS_OFFICIAL",
                    "candidate_manifest.json",
                    f"chapters_topics_problem_types_concepts_relations must be COACH_LEARNING_DERIVED, got {derived_scope!r}.",
                )
            )

        return issues

    def _validate_legacy_quarantine(
        self, quarantine: dict[str, Any]
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []
        if quarantine.get("policy") != "NON_DESTRUCTIVE":
            issues.append(
                self._issue(
                    "legacy_quarantine_policy",
                    "QUARANTINE_POLICY_NOT_NON_DESTRUCTIVE",
                    "legacy_quarantine.json",
                    "Legacy quarantine policy must be NON_DESTRUCTIVE.",
                )
            )

        entries = quarantine.get("entries", [])
        if len(entries) != 3:
            issues.append(
                self._issue(
                    "legacy_quarantine_policy",
                    "QUARANTINE_ENTRIES_COUNT_MISMATCH",
                    "legacy_quarantine.json",
                    f"Expected 3 quarantine entries, got {len(entries)}.",
                )
            )

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            code = entry.get("code")
            if entry.get("destructive_delete_allowed") is not False:
                issues.append(
                    self._issue(
                        "legacy_quarantine_policy",
                        "DESTRUCTIVE_DELETE_ALLOWED_VIOLATION",
                        f"legacy_quarantine.json[{code}]",
                        f"destructive_delete_allowed for {code!r} must be false.",
                    )
                )

        return issues

    def _validate_critical_boundaries(
        self,
        activation_policy: dict[str, Any],
        manifest: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[FullScopeAlignmentIssue]:
        issues: list[FullScopeAlignmentIssue] = []

        if activation_policy.get("activation_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "ACTIVATION_NOT_BLOCKED",
                    "activation_policy.json",
                    "activation_allowed must be false.",
                )
            )
        if manifest.get("activation_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "ACTIVATION_NOT_BLOCKED",
                    "candidate_manifest.json",
                    "activation_allowed must be false.",
                )
            )

        if activation_policy.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "activation_policy.json",
                    "database_import_allowed must be false.",
                )
            )
        if manifest.get("database_import_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "DATABASE_IMPORT_NOT_BLOCKED",
                    "candidate_manifest.json",
                    "database_import_allowed must be false.",
                )
            )

        if activation_policy.get("canonical_write_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_WRITE_NOT_BLOCKED",
                    "activation_policy.json",
                    "canonical_write_allowed must be false.",
                )
            )
        if manifest.get("canonical_write_allowed") is not False:
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "CANONICAL_WRITE_NOT_BLOCKED",
                    "candidate_manifest.json",
                    "canonical_write_allowed must be false.",
                )
            )

        if (
            activation_policy.get("curriculum_import_service_allowed")
            is not False
        ):
            issues.append(
                self._issue(
                    "critical_boundaries",
                    "IMPORT_SERVICE_NOT_BLOCKED",
                    "activation_policy.json",
                    "curriculum_import_service_allowed must be false.",
                )
            )

        return issues

    # ------------------------------------------------------------------
    # Hash and file utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _semantic_hash(file_path: Path) -> str:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        canonical_bytes = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()

    @staticmethod
    def _git_blob_sha1(file_path: Path) -> str:
        content = file_path.read_bytes()
        header = f"blob {len(content)}\0".encode("ascii")
        return hashlib.sha1(header + content).hexdigest()

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
        self, path: Path, issues: list[FullScopeAlignmentIssue]
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
        self, path: Path, issues: list[FullScopeAlignmentIssue]
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
    ) -> FullScopeAlignmentIssue:
        return FullScopeAlignmentIssue(
            check=check, code=code, location=location, message=message
        )
