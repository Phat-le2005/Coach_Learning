from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "oxyz_v0_1"
    / "academic_review"
    / "v0_1"
)
EXPECTED_AGGREGATE_SEMANTIC_SHA256 = (
    "a62426fd798e4b20b5b130bc72903304f3f88f0d26840bed661d2eed9b1521ce"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "a8e2c94f516f85a618a17ea41d35d2af1a646ff57aa8fb5a288b1fcce086e1df"
)
EXPECTED_GAP = "PLANE_SPHERE_RELATION"
EXPECTED_OFFICIAL_COVERAGE = (
    "vectơ và tọa độ trong không gian",
    "phương trình mặt phẳng",
    "phương trình đường thẳng trong không gian",
    "góc và khoảng cách bằng phương pháp tọa độ",
    "phương trình mặt cầu",
    "vận dụng vào thực tiễn",
)
SEMANTIC_FILES = (
    "source_registry.json",
    "taxonomy_candidate.json",
    "verified_questions.json",
    "hold_candidates.json",
    "source_evidence.json",
    "duplicate_clusters.json",
    "coverage.json",
    "review_stats.json",
    "extraction_limitations.json",
)
REQUIRED_FILES = (*SEMANTIC_FILES, "data_contract.json", "README.md")
EXPECTED_SEMANTIC_HASHES = {
    "source_registry.json": (
        "1ef16ebf875b3ff3e53be50471a4fb02549719fa62cd715795d84c97cd538554"
    ),
    "taxonomy_candidate.json": (
        "5ac488ed0159b95c00e79c19a97a43773aad7592c3a2caf0acc318672445fa70"
    ),
    "verified_questions.json": (
        "1915b1d64c48132f44252ea2254fffda5fbc0269b0b35954692905dfb09a05a1"
    ),
    "hold_candidates.json": (
        "7f1720e419e34a79c76e1cf0cf83c85809f0f887d64575b6368d5b6061981799"
    ),
    "source_evidence.json": (
        "238edc504d0734b670ba9c0888815d0e608fb8b5cd65f9821ae167bdff72f4c4"
    ),
    "duplicate_clusters.json": (
        "d165897dd6b79326a7decd732d27d29d920ba2ca2298873817cc39a382f1891d"
    ),
    "coverage.json": (
        "f297fadd01f39d11311eed94b95d3a0f59a6b3849767bf187b5afec3026d2dce"
    ),
    "review_stats.json": (
        "61fa75609844995f2c06cb080f470784d5ffbdd026444982b8d26913f5d53216"
    ),
    "extraction_limitations.json": (
        "231a0d2f60a3d5695501a10e59b954bd04a819636636e24047d3c32985590334"
    ),
}
EXPECTED_PROBLEM_TYPE_COUNTS = {
    "PLANE_EQUATION_NORMAL_VECTOR": 40,
    "POINT_PLANE_OR_PLANE_DISTANCE": 2,
    "PLANE_RELATION": 7,
    "LINE_EQUATION_DIRECTION_VECTOR": 33,
    "LINE_PLANE_INTERSECTION": 1,
    "LINE_RELATION": 2,
    "LINE_DISTANCE_IN_OXYZ": 1,
    "ANGLE_IN_OXYZ": 18,
    "SPHERE_EQUATION_CENTER_RADIUS": 7,
    "PLANE_SPHERE_RELATION": 0,
    "COORDINATE_DISTANCE_PROJECTION": 5,
    "COORDINATE_GEOMETRY_APPLICATION": 16,
}
EXPECTED_VERIFIED_TYPE_COUNTS = {
    "MULTIPLE_CHOICE": 94,
    "SHORT_ANSWER": 34,
    "TRUE_FALSE_GROUP": 4,
}
EXPECTED_HOLD_TYPE_COUNTS = {
    "UNKNOWN": 80,
    "TRUE_FALSE_GROUP": 61,
    "MULTIPLE_CHOICE": 36,
    "SHORT_ANSWER": 15,
}
EXPECTED_COUNTS = {
    "sources_scanned": 12,
    "candidate_occurrences_detected": 475,
    "unique_candidates_after_exact_dedupe": 324,
    "verified_candidates": 132,
    "hold_candidates": 192,
    "duplicate_clusters": 102,
    "visual_asset_required_verified": 6,
    "problem_types_total": 12,
    "problem_types_covered": 11,
    "production_release_eligible": 0,
}


@dataclass(frozen=True, slots=True, order=True)
class OxyzAcademicReviewIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class OxyzAcademicReviewReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    verified_question_type_counts: dict[str, int]
    hold_question_type_counts: dict[str, int]
    problem_type_coverage: dict[str, int]
    problem_type_gaps: tuple[str, ...]
    aggregate_semantic_sha256: str | None
    rights_status: str | None
    production_release_eligible: int
    database_import_allowed: bool
    canonical_snapshot_allowed: bool
    errors: tuple[OxyzAcademicReviewIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "verified_question_type_counts": self.verified_question_type_counts,
            "hold_question_type_counts": self.hold_question_type_counts,
            "problem_type_coverage": self.problem_type_coverage,
            "problem_type_gaps": list(self.problem_type_gaps),
            "aggregate_semantic_sha256": self.aggregate_semantic_sha256,
            "rights_status": self.rights_status,
            "production_release_eligible": self.production_release_eligible,
            "database_import_allowed": self.database_import_allowed,
            "canonical_snapshot_allowed": self.canonical_snapshot_allowed,
            "errors": [asdict(error) for error in self.errors],
        }


class OxyzAcademicReviewValidator:
    """Validate curated DATA-MATH12-024 without rewriting academic data."""

    def validate(
        self,
        path: Path = DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH,
    ) -> OxyzAcademicReviewReport:
        dataset_path = path.resolve()
        initial: list[OxyzAcademicReviewIssue] = []
        self._check_required_files(dataset_path, initial)
        sources = self._load_list(dataset_path / "source_registry.json", initial)
        taxonomy = self._load_object(
            dataset_path / "taxonomy_candidate.json", initial
        )
        verified = self._load_list(
            dataset_path / "verified_questions.json", initial
        )
        holds = self._load_list(dataset_path / "hold_candidates.json", initial)
        evidence = self._load_list(dataset_path / "source_evidence.json", initial)
        duplicates = self._load_list(
            dataset_path / "duplicate_clusters.json", initial
        )
        coverage = self._load_list(dataset_path / "coverage.json", initial)
        stats = self._load_object(dataset_path / "review_stats.json", initial)
        limitations = self._load_object(
            dataset_path / "extraction_limitations.json", initial
        )
        contract = self._load_object(dataset_path / "data_contract.json", initial)

        source_by_code = self._index(sources, "source_code")
        evidence_by_candidate = self._index(evidence, "candidate_id")
        verified_by_id = self._index(verified, "candidate_id")

        check_errors: dict[str, list[OxyzAcademicReviewIssue]] = {
            "required_files": [
                issue for issue in initial if issue.check == "required_files"
            ],
            "no_pdf_binaries": self._validate_no_pdf_binaries(dataset_path),
            "semantic_hash_contract": self._validate_semantic_hash_contract(
                dataset_path, contract
            ),
            "source_registry": self._validate_sources(sources),
            "official_scope_and_taxonomy": self._validate_taxonomy(taxonomy),
            "candidate_partition": self._validate_candidate_partition(
                verified, holds
            ),
            "verified_questions": self._validate_verified(
                verified,
                source_by_code,
                evidence_by_candidate,
                taxonomy,
            ),
            "hold_boundary": self._validate_holds(
                holds, source_by_code, taxonomy
            ),
            "source_evidence": self._validate_evidence(
                evidence, verified_by_id, source_by_code
            ),
            "duplicate_clusters": self._validate_duplicates(
                duplicates, verified_by_id
            ),
            "coverage_and_gap": self._validate_coverage(
                coverage, verified, taxonomy
            ),
            "review_stats": self._validate_stats(stats),
            "extraction_policy": self._validate_limitations(limitations),
            "release_boundary": self._validate_release_boundary(
                verified, holds, sources, stats, contract
            ),
        }
        for issue in initial:
            if issue.check != "required_files":
                check_errors.setdefault(issue.check, []).append(issue)

        verified_types = self._string_counter(verified, "question_type")
        hold_types = self._string_counter(holds, "question_type")
        problem_type_counts = self._string_counter(verified, "problem_type_code")
        coverage_counts = {
            code: problem_type_counts.get(code, 0)
            for code in EXPECTED_PROBLEM_TYPE_COUNTS
        }
        gaps = tuple(
            code for code, count in coverage_counts.items() if count == 0
        )
        occurrences_detected = sum(
            self._int(row.get("duplicate_occurrence_count"), default=1)
            for row in [*verified, *holds]
        )
        counts = {
            "sources_scanned": len(sources),
            "candidate_occurrences_detected": occurrences_detected,
            "unique_candidates_after_exact_dedupe": len(verified) + len(holds),
            "verified_candidates": len(verified),
            "hold_candidates": len(holds),
            "duplicate_clusters": len(duplicates),
            "visual_asset_required_verified": sum(
                row.get("visual_asset_required") is True for row in verified
            ),
            "problem_types_total": len(self._dict_list(taxonomy, "problem_types")),
            "problem_types_covered": sum(count > 0 for count in coverage_counts.values()),
            "production_release_eligible": self._int(
                stats.get("production_release_eligible"), default=-1
            ),
        }
        if counts != EXPECTED_COUNTS:
            check_errors["exact_counts"] = [
                self._issue(
                    "exact_counts",
                    "COUNT_MISMATCH",
                    "review_stats.json",
                    f"Expected {EXPECTED_COUNTS!r}, got {counts!r}.",
                )
            ]
        else:
            check_errors["exact_counts"] = []

        all_errors = tuple(
            sorted({issue for issues in check_errors.values() for issue in issues})
        )
        semantic_ok = not check_errors["semantic_hash_contract"]
        aggregate = EXPECTED_AGGREGATE_SEMANTIC_SHA256 if semantic_ok else None
        return OxyzAcademicReviewReport(
            dataset_path=str(dataset_path),
            status="PASS" if not all_errors else "FAIL",
            checks={name: not errors for name, errors in check_errors.items()},
            counts=counts,
            verified_question_type_counts=verified_types,
            hold_question_type_counts=hold_types,
            problem_type_coverage=coverage_counts,
            problem_type_gaps=gaps,
            aggregate_semantic_sha256=aggregate,
            rights_status=(
                stats.get("rights_status")
                if isinstance(stats.get("rights_status"), str)
                else None
            ),
            production_release_eligible=self._int(
                stats.get("production_release_eligible"), default=-1
            ),
            database_import_allowed=stats.get("database_import_allowed") is True,
            canonical_snapshot_allowed=(
                stats.get("canonical_snapshot_allowed") is True
            ),
            errors=all_errors,
        )

    def _validate_semantic_hash_contract(
        self, path: Path, contract: dict[str, Any]
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        contract_path = path / "data_contract.json"
        if self.semantic_sha256(contract) != EXPECTED_CONTRACT_SEMANTIC_SHA256:
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "DATA_CONTRACT_HASH_MISMATCH",
                    contract_path.name,
                    "The curated DATA-MATH12-024 contract changed semantically.",
                )
            )
        if contract.get("semantic_files_order") != list(SEMANTIC_FILES):
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "SEMANTIC_FILE_ORDER_MISMATCH",
                    contract_path.name,
                    "Semantic file order differs from the curated contract.",
                )
            )
        if contract.get("semantic_sha256") != EXPECTED_SEMANTIC_HASHES:
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "SEMANTIC_HASH_MAP_MISMATCH",
                    contract_path.name,
                    "Semantic hash map differs from the locked review input.",
                )
            )
        if (
            contract.get("aggregate_semantic_sha256")
            != EXPECTED_AGGREGATE_SEMANTIC_SHA256
        ):
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "AGGREGATE_HASH_MISMATCH",
                    contract_path.name,
                    "Locked aggregate semantic SHA-256 does not match.",
                )
            )
        for name, expected in EXPECTED_SEMANTIC_HASHES.items():
            file_path = path / name
            actual = self._semantic_file_sha256(file_path)
            if actual != expected:
                issues.append(
                    self._issue(
                        "semantic_hash_contract",
                        "SEMANTIC_FILE_HASH_MISMATCH",
                        name,
                        f"Expected {expected}, got {actual!r}.",
                    )
                )
        return issues

    def _validate_sources(
        self, sources: list[dict[str, Any]]
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        for field in ("source_code", "source_file_id", "source_pdf_sha256"):
            values = [row.get(field) for row in sources]
            if any(not isinstance(value, str) or not value for value in values) or len(
                values
            ) != len(set(values)):
                issues.append(
                    self._issue(
                        "source_registry",
                        "INVALID_OR_DUPLICATE_SOURCE_IDENTITY",
                        f"source_registry.json:{field}",
                        f"Every source must have a unique non-empty {field}.",
                    )
                )
        for index, row in enumerate(sources):
            valid_hash = self._is_sha256(row.get("source_pdf_sha256"))
            numeric_fields = ("page_count", "file_size_bytes")
            valid_numbers = all(
                self._int(row.get(field), default=-1) >= 0 for field in numeric_fields
            )
            if not all(
                (
                    valid_hash,
                    valid_numbers,
                    isinstance(row.get("source_type"), str) and bool(row.get("source_type")),
                    row.get("rights_status") == "REVIEW_REQUIRED",
                )
            ):
                issues.append(
                    self._issue(
                        "source_registry",
                        "INVALID_SOURCE_RECORD",
                        f"source_registry.json[{index}]",
                        "Source hash, scan status, counts, or rights boundary is invalid.",
                    )
                )
        if len(sources) != 12:
            issues.append(
                self._issue(
                    "source_registry",
                    "SOURCE_COUNT_MISMATCH",
                    "source_registry.json",
                    f"Expected 12 sources, got {len(sources)}.",
                )
            )
        return issues

    def _validate_taxonomy(
        self, taxonomy: dict[str, Any]
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        binding = taxonomy.get("official_scope_binding")
        policy = taxonomy.get("classification_policy")
        if not isinstance(binding, dict) or not all(
            (
                taxonomy.get("dataset_code") == "DATA-MATH12-024",
                taxonomy.get("subject_code") == "MATH_G12",
                taxonomy.get("chapter_code") == "OXYZ_CHAPTER",
                taxonomy.get("topic_code") == "OXYZ_TOPIC",
                binding.get("official_scope_code") == "M12_CORE_GEOMETRY_COORDINATE_3D",
                binding.get("official_content_title") == "Phương pháp tọa độ trong không gian",
                binding.get("provenance_type") == "OFFICIAL_SCOPE_BINDING",
                binding.get("normalized_coverage") == list(EXPECTED_OFFICIAL_COVERAGE),
            )
        ):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "INVALID_OFFICIAL_SCOPE_BINDING",
                    "taxonomy_candidate.json:official_scope_binding",
                    "Official scope binding code, title, or normalized coverage changed.",
                )
            )
        if not isinstance(policy, dict) or not all(
            (
                policy.get("problem_types_concepts_and_weights_are")
                == "COACH_LEARNING_DERIVED",
                policy.get("synthetic_question_fill_allowed") is False,
            )
        ):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "INVALID_TAXONOMY_POLICY",
                    "taxonomy_candidate.json:classification_policy",
                    "Policy must keep taxonomy Coach Learning derived with no synthetic fill.",
                )
            )
        problem_types = self._dict_list(taxonomy, "problem_types")
        concepts = self._dict_list(taxonomy, "concepts")
        outcomes = self._dict_list(taxonomy, "learning_outcomes")
        pt_codes = {row.get("code") for row in problem_types}
        concept_codes = {row.get("code") for row in concepts}
        outcome_codes = {row.get("code") for row in outcomes}
        if (
            len(problem_types) != 12
            or len(pt_codes) != 12
            or any(
                row.get("provenance_type") != "COACH_LEARNING_DERIVED"
                for row in problem_types
            )
            or pt_codes != set(EXPECTED_PROBLEM_TYPE_COUNTS)
        ):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "PROBLEM_TYPE_SET_MISMATCH",
                    "taxonomy_candidate.json",
                    "Taxonomy codes must be unique and contain exactly 12 ProblemTypes.",
                )
            )
        if any(
            row.get("provenance_type") != "COACH_LEARNING_DERIVED"
            for row in concepts
        ):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "CONCEPT_PROVENANCE_MISMATCH",
                    "taxonomy_candidate.json:concepts",
                    "Concepts must remain Coach Learning derived.",
                )
            )
        mappings = taxonomy.get("mappings")
        pt_outcomes = taxonomy.get("problem_type_learning_outcome")
        if not isinstance(mappings, dict) or set(mappings) != pt_codes:
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "PROBLEM_TYPE_MAPPING_SET_MISMATCH",
                    "taxonomy_candidate.json:mappings",
                    "Every ProblemType must have exactly one mapping list.",
                )
            )
            mappings = {}
        if not isinstance(pt_outcomes, dict) or set(pt_outcomes) != pt_codes:
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "LEARNING_OUTCOME_MAPPING_SET_MISMATCH",
                    "taxonomy_candidate.json:problem_type_learning_outcome",
                    "Every ProblemType must map to one LearningOutcome.",
                )
            )
            pt_outcomes = {}
        for code, rows in mappings.items():
            valid_rows = isinstance(rows, list) and all(
                isinstance(row, dict) for row in rows
            )
            if valid_rows:
                weights = [row.get("weight") for row in rows]
                valid_rows = all(
                    self._positive_number(weight) for weight in weights
                ) and math.isclose(sum(float(weight) for weight in weights), 1.0, abs_tol=1e-3)
                valid_rows = valid_rows and sum(
                    row.get("is_primary") is True for row in rows
                ) == 1
                valid_rows = valid_rows and all(
                    row.get("concept_code") in concept_codes for row in rows
                )
            if not valid_rows:
                issues.append(
                    self._issue(
                        "official_scope_and_taxonomy",
                        "INVALID_CONCEPT_MAPPING",
                        f"taxonomy_candidate.json:mappings:{code}",
                        "Concept mappings must resolve, sum to 1, and have one primary.",
                    )
                )
        if any(value not in outcome_codes for value in pt_outcomes.values()):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "UNKNOWN_LEARNING_OUTCOME_MAPPING",
                    "taxonomy_candidate.json:problem_type_learning_outcome",
                    "ProblemType LearningOutcome mappings must resolve.",
                )
            )
        return issues

    def _validate_candidate_partition(
        self,
        verified: list[dict[str, Any]],
        holds: list[dict[str, Any]],
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        verified_ids = [row.get("candidate_id") for row in verified]
        hold_ids = [row.get("candidate_id") for row in holds]
        if (
            len(verified_ids) != len(set(verified_ids))
            or len(hold_ids) != len(set(hold_ids))
            or any(not isinstance(value, str) or not value for value in [*verified_ids, *hold_ids])
        ):
            issues.append(
                self._issue(
                    "candidate_partition",
                    "INVALID_OR_DUPLICATE_CANDIDATE_ID",
                    "verified_questions.json/hold_candidates.json",
                    "Candidate IDs must be unique and non-empty in each partition.",
                )
            )
        if not set(verified_ids).isdisjoint(set(hold_ids)):
            issues.append(
                self._issue(
                    "candidate_partition",
                    "PARTITION_OVERLAP",
                    "verified_questions.json/hold_candidates.json",
                    "A candidate ID cannot belong to both VERIFIED and HOLD partitions.",
                )
            )
        if len(verified) != 132 or len(holds) != 192 or len(verified) + len(holds) != 324:
            issues.append(
                self._issue(
                    "candidate_partition",
                    "CANDIDATE_PARTITION_MISMATCH",
                    "verified_questions.json/hold_candidates.json",
                    "Expected exactly 132 VERIFIED and 192 HOLD candidates.",
                )
            )
        return issues

    def _validate_verified(
        self,
        rows: list[dict[str, Any]],
        sources: dict[str, dict[str, Any]],
        evidence: dict[str, dict[str, Any]],
        taxonomy: dict[str, Any],
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        mappings = taxonomy.get("mappings", {})
        learning_outcomes = taxonomy.get("problem_type_learning_outcome", {})
        for index, row in enumerate(rows):
            candidate_id = row.get("candidate_id")
            location = (
                f"verified_questions.json[{index}]:{candidate_id}"
                if isinstance(candidate_id, str)
                else f"verified_questions.json[{index}]"
            )
            answer = row.get("correct_answer")
            qtype = row.get("question_type")
            if qtype == "TRUE_FALSE_GROUP":
                answer_valid = (
                    isinstance(answer, list)
                    and len(answer) == 4
                    and all(isinstance(item, bool) for item in answer)
                )
            else:
                answer_valid = isinstance(answer, str) and bool(answer.strip())
            source = sources.get(str(row.get("source_code")))
            source_valid = (
                source is not None
                and row.get("source_file_id") == source.get("source_file_id")
                and row.get("source_pdf_sha256") == source.get("source_pdf_sha256")
            )
            evidence_row = evidence.get(str(candidate_id))
            problem_type = str(row.get("problem_type_code"))
            expected_outcomes = (
                [
                    {
                        "learning_outcome_code": learning_outcomes[problem_type],
                        "weight": 1.0,
                    }
                ]
                if problem_type in learning_outcomes
                else None
            )
            page_lineage_valid = (
                self._int(row.get("question_start_page"), default=-1) > 0
                and self._int(row.get("solution_answer_page"), default=-1) > 0
            )
            occurrence_lineage_valid = self._occurrence_lineage_valid(
                row.get("duplicate_occurrences"), sources
            )
            evidence_valid = evidence_row is not None and all(
                (
                    evidence_row.get("source_code") == row.get("source_code"),
                    evidence_row.get("source_file_id") == row.get("source_file_id"),
                    evidence_row.get("source_pdf_sha256") == row.get("source_pdf_sha256"),
                    evidence_row.get("question_page") == row.get("question_start_page"),
                    evidence_row.get("solution_answer_page") == row.get("solution_answer_page"),
                    evidence_row.get("source_claimed_answer") == answer,
                )
            )
            structural_valid = all(
                (
                    row.get("subject_code") == "MATH_G12",
                    row.get("chapter_code") == "OXYZ_CHAPTER",
                    row.get("topic_code") == "OXYZ_TOPIC",
                    row.get("official_scope_code") == "M12_CORE_GEOMETRY_COORDINATE_3D",
                    row.get("review_status") == "VERIFIED_SOURCE_ANSWER",
                    row.get("answer_verification") == "SOURCE_SOLUTION_EXPLICIT",
                    self._raw_text_hash_valid(row),
                    answer_valid,
                    source_valid,
                    evidence_valid,
                    page_lineage_valid,
                    occurrence_lineage_valid,
                    row.get("concepts") == mappings.get(problem_type),
                    row.get("learning_outcomes") == expected_outcomes,
                    row.get("rights_status") == "REVIEW_REQUIRED",
                    row.get("promotion_ready") is False,
                    row.get("database_import_allowed") is False,
                    row.get("canonical_snapshot_allowed") is False,
                    self._int(row.get("duplicate_occurrence_count"), default=-1)
                    == len(row.get("duplicate_occurrences", []))
                    if isinstance(row.get("duplicate_occurrences"), list)
                    else False,
                )
            )
            if not structural_valid:
                issues.append(
                    self._issue(
                        "verified_questions",
                        "INVALID_VERIFIED_RECORD",
                        location,
                        "Verified answer, taxonomy, lineage, or release boundary changed.",
                    )
                )
        if sum(row.get("visual_asset_required") is True for row in rows) != 6:
            issues.append(
                self._issue(
                    "verified_questions",
                    "VISUAL_REQUIRED_COUNT_MISMATCH",
                    "verified_questions.json",
                    "Exactly 6 VERIFIED questions must require later visual review.",
                )
            )
        return issues

    def _validate_holds(
        self,
        rows: list[dict[str, Any]],
        sources: dict[str, dict[str, Any]],
        taxonomy: dict[str, Any],
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        pt_codes = {
            row.get("code") for row in self._dict_list(taxonomy, "problem_types")
        }
        for index, row in enumerate(rows):
            candidate_id = row.get("candidate_id")
            location = (
                f"hold_candidates.json[{index}]:{candidate_id}"
                if isinstance(candidate_id, str)
                else f"hold_candidates.json[{index}]"
            )
            source = sources.get(str(row.get("source_code")))
            source_valid = (
                source is not None
                and row.get("source_file_id") == source.get("source_file_id")
                and row.get("source_pdf_sha256") == source.get("source_pdf_sha256")
            )
            occurrence_lineage_valid = self._occurrence_lineage_valid(
                row.get("duplicate_occurrences"), sources
            )
            valid = all(
                (
                    row.get("subject_code") == "MATH_G12",
                    row.get("chapter_code") == "OXYZ_CHAPTER",
                    row.get("topic_code") == "OXYZ_TOPIC",
                    row.get("official_scope_code") == "M12_CORE_GEOMETRY_COORDINATE_3D",
                    row.get("review_status") == "HOLD_SOURCE_ANSWER_UNPARSED_OR_CONFLICT",
                    "correct_answer" not in row,
                    isinstance(row.get("detected_answers"), list),
                    self._raw_text_hash_valid(row),
                    row.get("problem_type_code") in pt_codes,
                    source_valid,
                    self._int(row.get("question_start_page"), default=-1) > 0,
                    occurrence_lineage_valid,
                    row.get("rights_status") == "REVIEW_REQUIRED",
                    row.get("promotion_ready") is False,
                    row.get("database_import_allowed") is False,
                    row.get("canonical_snapshot_allowed") is False,
                    self._int(row.get("duplicate_occurrence_count"), default=-1)
                    == len(row.get("duplicate_occurrences", []))
                    if isinstance(row.get("duplicate_occurrences"), list)
                    else False,
                )
            )
            if not valid:
                issues.append(
                    self._issue(
                        "hold_boundary",
                        "INVALID_HOLD_RECORD",
                        location,
                        "Hold candidate must remain un-answered and blocked from import.",
                    )
                )
        return issues

    def _validate_evidence(
        self,
        rows: list[dict[str, Any]],
        verified: dict[str, dict[str, Any]],
        sources: dict[str, dict[str, Any]],
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        if len(rows) != 132:
            issues.append(
                self._issue(
                    "source_evidence",
                    "EVIDENCE_COUNT_MISMATCH",
                    "source_evidence.json",
                    f"Expected 132 evidence records, got {len(rows)}.",
                )
            )
        for index, row in enumerate(rows):
            candidate_id = row.get("candidate_id")
            candidate = verified.get(str(candidate_id))
            source = sources.get(str(row.get("source_code")))
            valid = (
                candidate is not None
                and source is not None
                and row.get("evidence_type") == "SOURCE_QUESTION_AND_EXPLICIT_SOLUTION_ANSWER"
                and row.get("review_consistency") == "CONFIRMED"
                and row.get("source_claimed_answer") == candidate.get("correct_answer")
                and row.get("source_file_id") == source.get("source_file_id")
                and row.get("source_pdf_sha256") == source.get("source_pdf_sha256")
                and row.get("question_page") == candidate.get("question_start_page")
                and row.get("solution_answer_page") == candidate.get("solution_answer_page")
            )
            if not valid:
                issues.append(
                    self._issue(
                        "source_evidence",
                        "INVALID_SOURCE_EVIDENCE",
                        f"source_evidence.json[{index}]",
                        "Source evidence must resolve to verified candidate and source registry.",
                    )
                )
        return issues

    def _validate_duplicates(
        self,
        clusters: list[dict[str, Any]],
        verified: dict[str, dict[str, Any]],
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        if len(clusters) != 102:
            issues.append(
                self._issue(
                    "duplicate_clusters",
                    "DUPLICATE_CLUSTER_COUNT_MISMATCH",
                    "duplicate_clusters.json",
                    f"Expected 102 duplicate clusters, got {len(clusters)}.",
                )
            )
        cluster_ids = [row.get("cluster_id") for row in clusters]
        if len(cluster_ids) != len(set(cluster_ids)):
            issues.append(
                self._issue(
                    "duplicate_clusters",
                    "DUPLICATE_CLUSTER_ID_MISMATCH",
                    "duplicate_clusters.json",
                    "Cluster IDs must be unique.",
                )
            )
        for index, row in enumerate(clusters):
            canonical = verified.get(str(row.get("canonical_candidate_id")))
            valid = (
                canonical is not None
                and row.get("dedupe_basis") == "EXACT_NORMALIZED_QUESTION_TEXT"
                and row.get("answer_consistency") == "CONSISTENT"
                and self._int(row.get("occurrence_count"), default=-1)
                == self._int(canonical.get("duplicate_occurrence_count"), default=-2)
                and self._int(row.get("occurrence_count"), default=-1) > 1
            )
            if not valid:
                issues.append(
                    self._issue(
                        "duplicate_clusters",
                        "INVALID_DUPLICATE_CLUSTER",
                        f"duplicate_clusters.json[{index}]",
                        "Duplicate cluster must link to verified canonical record.",
                    )
                )
        return issues

    def _validate_coverage(
        self,
        coverage: list[dict[str, Any]],
        verified: list[dict[str, Any]],
        taxonomy: dict[str, Any],
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        actual_counts = self._string_counter(verified, "problem_type_code")
        coverage_map = {row.get("problem_type_code"): row for row in coverage}
        pt_codes = {
            row.get("code") for row in self._dict_list(taxonomy, "problem_types")
        }
        if set(coverage_map) != pt_codes:
            issues.append(
                self._issue(
                    "coverage_and_gap",
                    "COVERAGE_SET_MISMATCH",
                    "coverage.json",
                    "Coverage problem types must match taxonomy candidates.",
                )
            )
        for code, expected_count in EXPECTED_PROBLEM_TYPE_COUNTS.items():
            row = coverage_map.get(code)
            actual = actual_counts.get(code, 0)
            if not row or actual != expected_count:
                issues.append(
                    self._issue(
                        "coverage_and_gap",
                        "COVERAGE_REPORT_MISMATCH",
                        f"coverage.json:{code}",
                        f"ProblemType {code} count mismatch: expected {expected_count}, got {actual}.",
                    )
                )
                continue
            expected_status = "GAP" if expected_count == 0 else "COVERED"
            if (
                row.get("verified_candidates") != actual
                or row.get("status") != expected_status
            ):
                issues.append(
                    self._issue(
                        "coverage_and_gap",
                        "COVERAGE_REPORT_MISMATCH",
                        f"coverage.json:{code}",
                        f"Coverage record mismatch for {code}.",
                    )
                )
        return issues

    def _validate_stats(
        self, stats: dict[str, Any]
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        if (
            stats.get("dataset_code") != "DATA-MATH12-024"
            or stats.get("official_scope_code") != "M12_CORE_GEOMETRY_COORDINATE_3D"
            or stats.get("problem_type_gaps") != [EXPECTED_GAP]
            or stats.get("verified_candidates") != 132
            or stats.get("hold_candidates") != 192
            or stats.get("duplicate_clusters") != 102
            or stats.get("sources_scanned") != 12
            or stats.get("candidate_occurrences_detected") != 475
            or stats.get("unique_candidates_after_exact_dedupe") != 324
            or stats.get("visual_asset_required_verified") != 6
            or stats.get("problem_types_total") != 12
            or stats.get("problem_types_covered") != 11
        ):
            issues.append(
                self._issue(
                    "review_stats",
                    "REVIEW_STATS_MISMATCH",
                    "review_stats.json",
                    "Review statistics summary does not match locked DATA-MATH12-024 state.",
                )
            )
        return issues

    def _validate_limitations(
        self, limitations: dict[str, Any]
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        if (
            limitations.get("dataset_code") != "DATA-MATH12-024"
            or limitations.get("policy") != "TEXT_LAYER_ONLY_NO_OCR_IN_THIS_BATCH"
            or not isinstance(limitations.get("notes"), list)
            or not limitations.get("hold_policy")
        ):
            issues.append(
                self._issue(
                    "extraction_policy",
                    "EXTRACTION_LIMITATIONS_MISMATCH",
                    "extraction_limitations.json",
                    "Extraction limitations policy does not match locked DATA-MATH12-024 contract.",
                )
            )
        return issues

    def _validate_release_boundary(
        self,
        verified: list[dict[str, Any]],
        holds: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[OxyzAcademicReviewIssue]:
        issues: list[OxyzAcademicReviewIssue] = []
        all_records = [*verified, *holds]
        if any(row.get("rights_status") != "REVIEW_REQUIRED" for row in all_records):
            issues.append(
                self._issue(
                    "release_boundary",
                    "RIGHTS_BOUNDARY_VIOLATION",
                    "verified_questions.json/hold_candidates.json",
                    "All candidate records must have rights_status=REVIEW_REQUIRED.",
                )
            )
        if any(row.get("rights_status") != "REVIEW_REQUIRED" for row in sources):
            issues.append(
                self._issue(
                    "release_boundary",
                    "SOURCE_RIGHTS_BOUNDARY_VIOLATION",
                    "source_registry.json",
                    "All sources must have rights_status=REVIEW_REQUIRED.",
                )
            )
        if any(
            row.get("promotion_ready") is not False
            or row.get("database_import_allowed") is not False
            or row.get("canonical_snapshot_allowed") is not False
            for row in all_records
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "RELEASE_BOUNDARY_VIOLATION",
                    "verified_questions.json/hold_candidates.json",
                    "No candidate may have promotion, DB import, or snapshot enabled.",
                )
            )
        if (
            stats.get("production_release_eligible") != 0
            or stats.get("promotion_ready") != 0
            or stats.get("database_import_allowed") is not False
            or stats.get("canonical_snapshot_allowed") is not False
            or stats.get("rights_status") != "REVIEW_REQUIRED"
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "RELEASE_STATS_BOUNDARY_VIOLATION",
                    "review_stats.json",
                    "Review stats must show zero release-eligible candidates and blocked flags.",
                )
            )
        policy = contract.get("policy", {})
        if (
            policy.get("no_synthetic_gap_fill") is not True
            or policy.get("source_answer_required_for_verified") is not True
            or policy.get("hold_is_not_importable") is not True
            or policy.get("rights_review_required") is not True
            or policy.get("codex_must_not_rewrite_curated_data") is not True
        ):
            issues.append(
                self._issue(
                    "release_boundary",
                    "CONTRACT_POLICY_VIOLATION",
                    "data_contract.json:policy",
                    "Data contract policies must remain intact.",
                )
            )
        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[OxyzAcademicReviewIssue]:
        pdfs = sorted(str(p.relative_to(path)) for p in path.rglob("*.pdf"))
        if not pdfs:
            return []
        return [
            self._issue(
                "no_pdf_binaries",
                "SOURCE_PDF_BINARY_PRESENT",
                pdfs[0],
                "Source PDF binaries are forbidden in DATA-MATH12-024.",
            )
        ]

    @staticmethod
    def semantic_sha256(value: Any) -> str:
        canonical = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def _semantic_file_sha256(cls, path: Path) -> str | None:
        try:
            return cls.semantic_sha256(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _raw_text_hash_valid(row: dict[str, Any]) -> bool:
        text = row.get("raw_question_text")
        expected = row.get("raw_question_text_sha256")
        return (
            isinstance(text, str)
            and isinstance(expected, str)
            and hashlib.sha256(text.encode("utf-8")).hexdigest() == expected
        )

    @classmethod
    def _occurrence_lineage_valid(
        cls,
        occurrences: Any,
        sources: dict[str, dict[str, Any]],
    ) -> bool:
        if not isinstance(occurrences, list) or not occurrences:
            return False
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                return False
            source = sources.get(str(occurrence.get("source_code")))
            page = occurrence.get("question_page")
            if source is None or not all(
                (
                    occurrence.get("source_file_id") == source.get("source_file_id"),
                    occurrence.get("source_pdf_sha256")
                    == source.get("source_pdf_sha256"),
                    cls._int(page, default=-1) > 0,
                )
            ):
                return False
        return True

    @staticmethod
    def _check_required_files(
        path: Path, issues: list[OxyzAcademicReviewIssue]
    ) -> None:
        for name in REQUIRED_FILES:
            if not (path / name).is_file():
                issues.append(
                    OxyzAcademicReviewIssue(
                        check="required_files",
                        code="MISSING_REQUIRED_FILE",
                        location=name,
                        message=f"Required file {name} is missing from DATA-MATH12-024.",
                    )
                )

    @classmethod
    def _load_list(
        cls, path: Path, issues: list[OxyzAcademicReviewIssue]
    ) -> list[dict[str, Any]]:
        data = cls._load_json(path, issues)
        if isinstance(data, list) and all(isinstance(row, dict) for row in data):
            return data
        issues.append(
            cls._issue(
                "required_files",
                "INVALID_JSON_STRUCTURE",
                path.name,
                "Expected a JSON list of objects.",
            )
        )
        return []

    @classmethod
    def _load_object(
        cls, path: Path, issues: list[OxyzAcademicReviewIssue]
    ) -> dict[str, Any]:
        data = cls._load_json(path, issues)
        if isinstance(data, dict):
            return data
        issues.append(
            cls._issue(
                "required_files",
                "INVALID_JSON_STRUCTURE",
                path.name,
                "Expected a JSON object.",
            )
        )
        return {}

    @classmethod
    def _load_json(
        cls, path: Path, issues: list[OxyzAcademicReviewIssue]
    ) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            issues.append(
                cls._issue(
                    "required_files",
                    "MALFORMED_JSON_FILE",
                    path.name,
                    f"Failed to read/decode JSON: {error}",
                )
            )
            return None

    @staticmethod
    def _index(
        rows: list[dict[str, Any]], field: str
    ) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row.get(field)
            if isinstance(key, str) and key and key not in indexed:
                indexed[key] = row
        return indexed

    @staticmethod
    def _string_counter(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
        return dict(
            Counter(
                str(row.get(field)) for row in rows if isinstance(row.get(field), str)
            )
        )

    @staticmethod
    def _dict_list(data: dict[str, Any], field: str) -> list[dict[str, Any]]:
        value = data.get(field)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
        return []

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _positive_number(value: Any) -> bool:
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _is_sha256(value: Any) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value)

    @staticmethod
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> OxyzAcademicReviewIssue:
        return OxyzAcademicReviewIssue(
            check=check, code=code, location=location, message=message
        )
