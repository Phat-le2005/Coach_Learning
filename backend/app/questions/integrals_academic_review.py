from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "integrals_v0_1"
    / "academic_review"
    / "v0_1"
)
EXPECTED_AGGREGATE_SEMANTIC_SHA256 = (
    "f627df2011b5d577b689751a9364b93428317fe2b173dc2d541142c46f790dc4"
)
EXPECTED_CONTRACT_SEMANTIC_SHA256 = (
    "52cc52de3ddea7c9183493d764779c58f866464e4e39caaa89435964429f10b2"
)
EXPECTED_GAP = "CALCULATE_DEFINITE_INTEGRAL"
EXPECTED_OFFICIAL_COVERAGE = (
    "khái niệm và tính chất nguyên hàm",
    "nguyên hàm của một số hàm số sơ cấp",
    "tích phân và tính chất",
    "diện tích, thể tích và bài toán thực tiễn",
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
        "8d9dd21c6937161ca7ff263a2d3240adb585ec377112f23794d1353693c6f213"
    ),
    "taxonomy_candidate.json": (
        "a75c901d90bc8ccf13efc1783a42b319ab9024f3819b0d085b45100ead089ccb"
    ),
    "verified_questions.json": (
        "c519c7ba97b1299b3cedb2203c7f1c2767a6e02a5a94276f85be0233e08b764c"
    ),
    "hold_candidates.json": (
        "f79420a7bf20c566430204c47e4cef440c75eec1922c9fa3ade997e93ee035da"
    ),
    "source_evidence.json": (
        "6612459ebbed280d5554ad7fa0a490c666ba755568bacd159a24958bb6c70a64"
    ),
    "duplicate_clusters.json": (
        "41dbcb1fe9c11a0b125c092a91d9d7242876f27f9981e9f0b6255e15c4253330"
    ),
    "coverage.json": (
        "edd489d693826ae7aeab5072e4d738047d31d8f72a5fcba6998a9b229a60ad5c"
    ),
    "review_stats.json": (
        "a51fa6e4c42a416c679e9d7f56e93cdc6cb9d405d1fdd9515d914428dafcea3d"
    ),
    "extraction_limitations.json": (
        "e2157db40dc301d97f1e7f575ab193a7abde83b41f0d2108152f261f2a36477f"
    ),
}
EXPECTED_PROBLEM_TYPE_COUNTS = {
    "CALCULATE_ANTIDERIVATIVE": 24,
    "ANTIDERIVATIVE_WITH_CONDITION": 3,
    "INTEGRAL_PROPERTIES": 11,
    "CALCULATE_DEFINITE_INTEGRAL": 0,
    "AREA_BY_INTEGRAL": 25,
    "VOLUME_BY_INTEGRAL": 11,
    "VOLUME_BY_CROSS_SECTION": 1,
    "PRACTICAL_ACCUMULATION": 2,
}
EXPECTED_VERIFIED_TYPE_COUNTS = {
    "MULTIPLE_CHOICE": 74,
    "TRUE_FALSE_GROUP": 2,
    "SHORT_ANSWER": 1,
}
EXPECTED_HOLD_TYPE_COUNTS = {
    "MULTIPLE_CHOICE": 31,
    "SHORT_ANSWER": 32,
    "TRUE_FALSE_GROUP": 4,
}
EXPECTED_COUNTS = {
    "sources_scanned": 22,
    "candidate_occurrences_detected": 210,
    "unique_candidates_after_exact_dedupe": 144,
    "verified_candidates": 77,
    "hold_candidates": 67,
    "duplicate_clusters": 52,
    "visual_asset_required_verified": 28,
    "problem_types_total": 8,
    "problem_types_covered": 7,
    "production_release_eligible": 0,
}


@dataclass(frozen=True, slots=True, order=True)
class IntegralsAcademicReviewIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class IntegralsAcademicReviewReport:
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
    errors: tuple[IntegralsAcademicReviewIssue, ...]

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


class IntegralsAcademicReviewValidator:
    """Validate curated DATA-MATH12-023 without rewriting academic data."""

    def validate(
        self,
        path: Path = DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    ) -> IntegralsAcademicReviewReport:
        dataset_path = path.resolve()
        initial: list[IntegralsAcademicReviewIssue] = []
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

        check_errors: dict[str, list[IntegralsAcademicReviewIssue]] = {
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
        counts = {
            "sources_scanned": len(sources),
            "candidate_occurrences_detected": sum(
                self._int(row.get("integral_candidate_occurrences_detected"))
                for row in sources
            ),
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
        return IntegralsAcademicReviewReport(
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
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        contract_path = path / "data_contract.json"
        if self.semantic_sha256(contract) != EXPECTED_CONTRACT_SEMANTIC_SHA256:
            issues.append(
                self._issue(
                    "semantic_hash_contract",
                    "DATA_CONTRACT_HASH_MISMATCH",
                    contract_path.name,
                    "The curated DATA-MATH12-023 contract changed semantically.",
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
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
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
            numeric_fields = (
                "page_count",
                "file_size_bytes",
                "integral_candidate_occurrences_detected",
                "verified_occurrence_contributions",
                "primary_verified_candidates",
                "hold_occurrence_contributions",
            )
            valid_numbers = all(self._int(row.get(field), default=-1) >= 0 for field in numeric_fields)
            if not all(
                (
                    valid_hash,
                    valid_numbers,
                    row.get("scope_scan_status") == "SCANNED",
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
        totals = {
            "occurrences": sum(
                self._int(row.get("integral_candidate_occurrences_detected"))
                for row in sources
            ),
            "verified_occurrences": sum(
                self._int(row.get("verified_occurrence_contributions"))
                for row in sources
            ),
            "primary_verified": sum(
                self._int(row.get("primary_verified_candidates")) for row in sources
            ),
            "hold_occurrences": sum(
                self._int(row.get("hold_occurrence_contributions"))
                for row in sources
            ),
        }
        if totals != {
            "occurrences": 210,
            "verified_occurrences": 133,
            "primary_verified": 77,
            "hold_occurrences": 77,
        }:
            issues.append(
                self._issue(
                    "source_registry",
                    "SOURCE_TOTAL_MISMATCH",
                    "source_registry.json",
                    f"Unexpected source totals: {totals!r}.",
                )
            )
        return issues

    def _validate_taxonomy(
        self, taxonomy: dict[str, Any]
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        binding = taxonomy.get("official_scope_binding")
        policy = taxonomy.get("classification_policy")
        if not isinstance(binding, dict) or not all(
            (
                taxonomy.get("dataset_code") == "DATA-MATH12-023",
                taxonomy.get("subject_code") == "MATH_G12",
                taxonomy.get("chapter_code") == "INTEGRALS",
                taxonomy.get("topic_code") == "INTEGRAL_TOPIC",
                binding.get("official_scope_code")
                == "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
                binding.get("official_content_title") == "Nguyên hàm. Tích phân",
                tuple(binding.get("normalized_coverage", ()))
                == EXPECTED_OFFICIAL_COVERAGE,
                binding.get("provenance_type") == "OFFICIAL_SCOPE_BINDING",
            )
        ):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "OFFICIAL_SCOPE_BINDING_MISMATCH",
                    "taxonomy_candidate.json",
                    "Subject/chapter/topic or official normalized scope changed.",
                )
            )
        if not isinstance(policy, dict) or not all(
            (
                policy.get("problem_types_concepts_and_weights_are")
                == "COACH_LEARNING_DERIVED",
                policy.get("official_scope_is_not_rewritten") is True,
                policy.get("synthetic_question_fill_allowed") is False,
            )
        ):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "DERIVED_TAXONOMY_POLICY_MISMATCH",
                    "taxonomy_candidate.json:classification_policy",
                    "Derived taxonomy provenance and no-synthetic-fill policy are locked.",
                )
            )
        problem_types = self._dict_list(taxonomy, "problem_types")
        concepts = self._dict_list(taxonomy, "concepts")
        outcomes = self._dict_list(taxonomy, "learning_outcomes")
        pt_codes = self._unique_codes(problem_types)
        concept_codes = self._unique_codes(concepts)
        outcome_codes = self._unique_codes(outcomes)
        if (
            len(pt_codes) != len(problem_types)
            or len(concept_codes) != len(concepts)
            or len(outcome_codes) != len(outcomes)
            or len(pt_codes) != 8
            or len(concept_codes) != 8
            or len(outcome_codes) != 6
        ):
            issues.append(
                self._issue(
                    "official_scope_and_taxonomy",
                    "INVALID_TAXONOMY_CODES",
                    "taxonomy_candidate.json",
                    "Taxonomy codes must be unique and contain exactly eight ProblemTypes.",
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
                ) and math.isclose(sum(float(weight) for weight in weights), 1.0)
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
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        verified_ids = [row.get("candidate_id") for row in verified]
        hold_ids = [row.get("hold_id") for row in holds]
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
        if len(verified) != 77 or len(holds) != 67 or len(verified) + len(holds) != 144:
            issues.append(
                self._issue(
                    "candidate_partition",
                    "CANDIDATE_PARTITION_MISMATCH",
                    "verified_questions.json/hold_candidates.json",
                    "Expected exactly 77 VERIFIED and 67 HOLD candidates.",
                )
            )
        if self._string_counter(verified, "question_type") != EXPECTED_VERIFIED_TYPE_COUNTS:
            issues.append(
                self._issue(
                    "candidate_partition",
                    "VERIFIED_TYPE_COUNT_MISMATCH",
                    "verified_questions.json",
                    "Verified question-type counts changed.",
                )
            )
        if self._string_counter(holds, "question_type") != EXPECTED_HOLD_TYPE_COUNTS:
            issues.append(
                self._issue(
                    "candidate_partition",
                    "HOLD_TYPE_COUNT_MISMATCH",
                    "hold_candidates.json",
                    "HOLD question-type counts changed.",
                )
            )
        return issues

    def _validate_verified(
        self,
        rows: list[dict[str, Any]],
        sources: dict[str, dict[str, Any]],
        evidence: dict[str, dict[str, Any]],
        taxonomy: dict[str, Any],
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        mappings = taxonomy.get("mappings") if isinstance(taxonomy.get("mappings"), dict) else {}
        pt_outcomes = taxonomy.get("problem_type_learning_outcome")
        if not isinstance(pt_outcomes, dict):
            pt_outcomes = {}
        for index, row in enumerate(rows):
            location = f"verified_questions.json[{index}]"
            candidate_id = row.get("candidate_id")
            source = sources.get(str(row.get("source_code")))
            evidence_row = evidence.get(str(candidate_id))
            question_type = row.get("question_type")
            answer = row.get("correct_answer")
            answer_valid = (
                question_type == "MULTIPLE_CHOICE" and answer in {"A", "B", "C", "D"}
            ) or (
                question_type == "SHORT_ANSWER"
                and isinstance(answer, str)
                and bool(answer.strip())
            ) or (
                question_type == "TRUE_FALSE_GROUP"
                and isinstance(answer, list)
                and len(answer) == 4
                and all(isinstance(value, bool) for value in answer)
            )
            problem_type = row.get("problem_type_code")
            expected_lo = pt_outcomes.get(problem_type)
            expected_outcomes = (
                [{"learning_outcome_code": expected_lo, "weight": 1.0}]
                if expected_lo is not None
                else None
            )
            source_valid = source is not None and all(
                (
                    row.get("source_file_id") == source.get("source_file_id"),
                    row.get("source_pdf_sha256") == source.get("source_pdf_sha256"),
                )
            )
            question_pages = row.get("question_pages")
            page_lineage_valid = (
                isinstance(question_pages, list)
                and bool(question_pages)
                and all(self._int(page, default=-1) > 0 for page in question_pages)
                and row.get("question_start_page") in question_pages
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
                    evidence_row.get("question_pages") == row.get("question_pages"),
                    evidence_row.get("solution_answer_page") == row.get("solution_answer_page"),
                    evidence_row.get("source_claimed_answer") == answer,
                )
            )
            structural_valid = all(
                (
                    row.get("subject_code") == "MATH_G12",
                    row.get("chapter_code") == "INTEGRALS",
                    row.get("topic_code") == "INTEGRAL_TOPIC",
                    row.get("official_scope_code")
                    == "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
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
        if sum(row.get("visual_asset_required") is True for row in rows) != 28:
            issues.append(
                self._issue(
                    "verified_questions",
                    "VISUAL_REQUIRED_COUNT_MISMATCH",
                    "verified_questions.json",
                    "Exactly 28 VERIFIED questions must require later visual review.",
                )
            )
        return issues

    def _validate_holds(
        self,
        rows: list[dict[str, Any]],
        sources: dict[str, dict[str, Any]],
        taxonomy: dict[str, Any],
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        problem_types = self._unique_codes(self._dict_list(taxonomy, "problem_types"))
        for index, row in enumerate(rows):
            occurrences = row.get("occurrences")
            occurrence_valid = isinstance(occurrences, list) and bool(occurrences)
            if occurrence_valid:
                for occurrence in occurrences:
                    source = sources.get(str(occurrence.get("source_code")))
                    occurrence_valid = occurrence_valid and source is not None and all(
                        (
                            occurrence.get("source_file_id") == source.get("source_file_id"),
                            occurrence.get("source_pdf_sha256") == source.get("source_pdf_sha256"),
                            isinstance(occurrence.get("question_pages"), list),
                            bool(occurrence.get("question_pages")),
                            occurrence.get("question_start_page")
                            in occurrence.get("question_pages", []),
                        )
                    )
            valid = all(
                (
                    row.get("subject_code") == "MATH_G12",
                    row.get("chapter_code") == "INTEGRALS",
                    row.get("topic_code") == "INTEGRAL_TOPIC",
                    row.get("official_scope_code")
                    == "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
                    row.get("review_status") == "HOLD_SOURCE_ANSWER_UNPARSED",
                    "correct_answer" not in row,
                    row.get("detected_answers") == [],
                    row.get("detected_problem_type_code") in problem_types,
                    self._raw_text_hash_valid(row),
                    occurrence_valid,
                    row.get("promotion_ready") is False,
                    row.get("database_import_allowed") is False,
                    row.get("canonical_snapshot_allowed") is False,
                )
            )
            if not valid:
                issues.append(
                    self._issue(
                        "hold_boundary",
                        "INVALID_HOLD_RECORD",
                        f"hold_candidates.json[{index}]",
                        "HOLD must remain answerless, source-linked, and non-importable.",
                    )
                )
        return issues

    def _validate_evidence(
        self,
        rows: list[dict[str, Any]],
        verified: dict[str, dict[str, Any]],
        sources: dict[str, dict[str, Any]],
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        ids = [row.get("candidate_id") for row in rows]
        evidence_ids = [row.get("evidence_id") for row in rows]
        if (
            len(ids) != len(set(ids))
            or len(evidence_ids) != len(set(evidence_ids))
            or set(ids) != set(verified)
        ):
            issues.append(
                self._issue(
                    "source_evidence",
                    "EVIDENCE_PARTITION_MISMATCH",
                    "source_evidence.json",
                    "Every VERIFIED candidate must have exactly one evidence record.",
                )
            )
        for index, row in enumerate(rows):
            question = verified.get(str(row.get("candidate_id")))
            source = sources.get(str(row.get("source_code")))
            valid = question is not None and source is not None and all(
                (
                    row.get("source_file_id") == source.get("source_file_id"),
                    row.get("source_pdf_sha256") == source.get("source_pdf_sha256"),
                    row.get("question_pages") == question.get("question_pages"),
                    row.get("solution_answer_page") == question.get("solution_answer_page"),
                    row.get("source_claimed_answer") == question.get("correct_answer"),
                    row.get("evidence_type")
                    == "SOURCE_QUESTION_AND_EXPLICIT_SOLUTION_ANSWER",
                    row.get("review_consistency") == "CONFIRMED",
                    row.get("all_occurrences") == question.get("duplicate_occurrences"),
                )
            )
            if not valid:
                issues.append(
                    self._issue(
                        "source_evidence",
                        "INVALID_SOURCE_EVIDENCE",
                        f"source_evidence.json[{index}]",
                        "Evidence answer/pages or source lineage differs from VERIFIED data.",
                    )
                )
        return issues

    def _validate_duplicates(
        self,
        rows: list[dict[str, Any]],
        verified: dict[str, dict[str, Any]],
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        cluster_ids = [row.get("cluster_id") for row in rows]
        canonical_ids = [row.get("canonical_candidate_id") for row in rows]
        expected_canonical = {
            candidate_id
            for candidate_id, row in verified.items()
            if self._int(row.get("duplicate_occurrence_count")) > 1
        }
        if (
            len(cluster_ids) != len(set(cluster_ids))
            or len(canonical_ids) != len(set(canonical_ids))
            or set(canonical_ids) != expected_canonical
        ):
            issues.append(
                self._issue(
                    "duplicate_clusters",
                    "DUPLICATE_CLUSTER_PARTITION_MISMATCH",
                    "duplicate_clusters.json",
                    "Duplicate clusters must exactly cover retained duplicate candidates.",
                )
            )
        for index, row in enumerate(rows):
            question = verified.get(str(row.get("canonical_candidate_id")))
            occurrence_count = self._int(row.get("occurrence_count"), default=-1)
            expected_sources = (
                sorted(
                    {
                        occurrence.get("source_code")
                        for occurrence in question.get("duplicate_occurrences", [])
                    }
                )
                if question is not None
                else []
            )
            valid = question is not None and all(
                (
                    row.get("dedupe_basis") == "EXACT_NORMALIZED_QUESTION_TEXT",
                    row.get("answer_consistency") == "CONSISTENT",
                    occurrence_count == question.get("duplicate_occurrence_count"),
                    sorted(row.get("source_codes", [])) == expected_sources,
                )
            )
            if not valid:
                issues.append(
                    self._issue(
                        "duplicate_clusters",
                        "INVALID_DUPLICATE_CLUSTER",
                        f"duplicate_clusters.json[{index}]",
                        "Duplicate target, occurrences, source set, or exact policy changed.",
                    )
                )
        return issues

    def _validate_coverage(
        self,
        coverage: list[dict[str, Any]],
        verified: list[dict[str, Any]],
        taxonomy: dict[str, Any],
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        pt_order = [
            row.get("code") for row in self._dict_list(taxonomy, "problem_types")
        ]
        actual_counts = self._string_counter(verified, "problem_type_code")
        expected_rows = [
            {
                "problem_type_code": code,
                "verified_candidates": EXPECTED_PROBLEM_TYPE_COUNTS[code],
                "status": (
                    "GAP" if EXPECTED_PROBLEM_TYPE_COUNTS[code] == 0 else "COVERED"
                ),
            }
            for code in pt_order
            if code in EXPECTED_PROBLEM_TYPE_COUNTS
        ]
        if coverage != expected_rows:
            issues.append(
                self._issue(
                    "coverage_and_gap",
                    "COVERAGE_REPORT_MISMATCH",
                    "coverage.json",
                    "Coverage report/order or the locked direct-integral gap changed.",
                )
            )
        derived = {
            code: actual_counts.get(code, 0) for code in EXPECTED_PROBLEM_TYPE_COUNTS
        }
        if derived != EXPECTED_PROBLEM_TYPE_COUNTS:
            issues.append(
                self._issue(
                    "coverage_and_gap",
                    "DERIVED_COVERAGE_MISMATCH",
                    "verified_questions.json",
                    f"Expected {EXPECTED_PROBLEM_TYPE_COUNTS!r}, got {derived!r}.",
                )
            )
        if [code for code, count in derived.items() if count == 0] != [EXPECTED_GAP]:
            issues.append(
                self._issue(
                    "coverage_and_gap",
                    "LOCKED_GAP_MISMATCH",
                    "coverage.json",
                    "CALCULATE_DEFINITE_INTEGRAL must remain the sole real gap.",
                )
            )
        return issues

    def _validate_stats(
        self, stats: dict[str, Any]
    ) -> list[IntegralsAcademicReviewIssue]:
        expected = {
            "dataset_code": "DATA-MATH12-023",
            "subject_code": "MATH_G12",
            "chapter_code": "INTEGRALS",
            "official_scope_code": "M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL",
            "sources_scanned": 22,
            "candidate_occurrences_detected": 210,
            "unique_candidates_after_exact_dedupe": 144,
            "verified_candidates": 77,
            "hold_candidates": 67,
            "duplicate_clusters": 52,
            "verified_question_type_counts": EXPECTED_VERIFIED_TYPE_COUNTS,
            "hold_question_type_counts": EXPECTED_HOLD_TYPE_COUNTS,
            "verified_problem_type_counts": {
                code: count
                for code, count in EXPECTED_PROBLEM_TYPE_COUNTS.items()
                if count > 0
            },
            "visual_asset_required_verified": 28,
            "problem_types_total": 8,
            "problem_types_covered": 7,
            "problem_type_gaps": [EXPECTED_GAP],
            "rights_status": "REVIEW_REQUIRED",
            "production_release_eligible": 0,
            "promotion_ready": 0,
            "database_import_allowed": False,
            "canonical_snapshot_allowed": False,
        }
        mismatches = [
            key for key, value in expected.items() if stats.get(key) != value
        ]
        if not mismatches:
            return []
        return [
            self._issue(
                "review_stats",
                "REVIEW_STATS_MISMATCH",
                "review_stats.json",
                f"Locked review stats changed: {mismatches!r}.",
            )
        ]

    def _validate_limitations(
        self, limitations: dict[str, Any]
    ) -> list[IntegralsAcademicReviewIssue]:
        notes = limitations.get("notes")
        valid = (
            limitations.get("policy") == "NO_OCR_IN_THIS_BATCH"
            and isinstance(notes, list)
            and any("no answer was inferred" in str(note) for note in notes)
            and any("not produced" in str(note) for note in notes)
        )
        if valid:
            return []
        return [
            self._issue(
                "extraction_policy",
                "EXTRACTION_POLICY_MISMATCH",
                "extraction_limitations.json",
                "No-OCR, no-answer-inference, and deferred-visual policy changed.",
            )
        ]

    def _validate_release_boundary(
        self,
        verified: list[dict[str, Any]],
        holds: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        stats: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[IntegralsAcademicReviewIssue]:
        issues: list[IntegralsAcademicReviewIssue] = []
        rows_safe = all(
            row.get("promotion_ready") is False
            and row.get("database_import_allowed") is False
            and row.get("canonical_snapshot_allowed") is False
            for row in [*verified, *holds]
        )
        rights_safe = all(
            row.get("rights_status") == "REVIEW_REQUIRED"
            for row in [*verified, *sources]
        )
        stats_safe = all(
            (
                stats.get("rights_status") == "REVIEW_REQUIRED",
                stats.get("production_release_eligible") == 0,
                stats.get("promotion_ready") == 0,
                stats.get("database_import_allowed") is False,
                stats.get("canonical_snapshot_allowed") is False,
            )
        )
        policy = contract.get("policy")
        invariants = contract.get("required_invariants")
        contract_safe = isinstance(policy, dict) and isinstance(invariants, dict) and all(
            (
                policy.get("no_synthetic_gap_fill") is True,
                policy.get("source_answer_required_for_verified") is True,
                policy.get("hold_is_not_importable") is True,
                policy.get("rights_review_required") is True,
                invariants.get("production_release_eligible") == 0,
                invariants.get("database_import_allowed") is False,
                invariants.get("canonical_snapshot_allowed") is False,
                contract.get("locked_problem_type_gaps") == [EXPECTED_GAP],
            )
        )
        if not (rows_safe and rights_safe and stats_safe and contract_safe):
            issues.append(
                self._issue(
                    "release_boundary",
                    "RELEASE_BOUNDARY_VIOLATION",
                    "DATA-MATH12-023",
                    "Rights, HOLD, promotion, DB import, snapshot, or gap-fill boundary changed.",
                )
            )
        return issues

    def _validate_no_pdf_binaries(
        self, path: Path
    ) -> list[IntegralsAcademicReviewIssue]:
        pdfs = [
            file.relative_to(path).as_posix()
            for file in path.rglob("*")
            if file.is_file() and file.suffix.casefold() == ".pdf"
        ]
        if not pdfs:
            return []
        return [
            self._issue(
                "no_pdf_binaries",
                "SOURCE_PDF_BINARY_PRESENT",
                pdfs[0],
                "Source PDF binaries are forbidden in DATA-MATH12-023.",
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
            pages = occurrence.get("question_pages")
            if source is None or not all(
                (
                    occurrence.get("source_file_id") == source.get("source_file_id"),
                    occurrence.get("source_pdf_sha256")
                    == source.get("source_pdf_sha256"),
                    isinstance(pages, list),
                    bool(pages),
                    occurrence.get("question_start_page") in (pages or []),
                    all(cls._int(page, default=-1) > 0 for page in (pages or [])),
                )
            ):
                return False
        return True

    @staticmethod
    def _is_sha256(value: Any) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
        )

    @staticmethod
    def _positive_number(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) > 0
        )

    @staticmethod
    def _int(value: Any, *, default: int = 0) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    @staticmethod
    def _index(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
        return {
            str(row[field]): row
            for row in rows
            if isinstance(row.get(field), str) and row.get(field)
        }

    @staticmethod
    def _dict_list(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
        rows = value.get(key)
        return (
            rows
            if isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
            else []
        )

    @staticmethod
    def _unique_codes(rows: list[dict[str, Any]]) -> set[str]:
        return {
            str(row["code"])
            for row in rows
            if isinstance(row.get("code"), str) and row.get("code")
        }

    @staticmethod
    def _string_counter(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
        return dict(
            Counter(
                str(row[field])
                for row in rows
                if isinstance(row.get(field), str) and row.get(field)
            )
        )

    @staticmethod
    def _load_list(
        path: Path, issues: list[IntegralsAcademicReviewIssue]
    ) -> list[dict[str, Any]]:
        value = IntegralsAcademicReviewValidator._load_json(path, issues)
        if isinstance(value, list) and all(isinstance(row, dict) for row in value):
            return value
        issues.append(
            IntegralsAcademicReviewValidator._issue(
                "json_schema", "EXPECTED_LIST", path.name, "Expected a JSON object list."
            )
        )
        return []

    @staticmethod
    def _load_object(
        path: Path, issues: list[IntegralsAcademicReviewIssue]
    ) -> dict[str, Any]:
        value = IntegralsAcademicReviewValidator._load_json(path, issues)
        if isinstance(value, dict):
            return value
        issues.append(
            IntegralsAcademicReviewValidator._issue(
                "json_schema", "EXPECTED_OBJECT", path.name, "Expected a JSON object."
            )
        )
        return {}

    @staticmethod
    def _load_json(path: Path, issues: list[IntegralsAcademicReviewIssue]) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            issues.append(
                IntegralsAcademicReviewValidator._issue(
                    "json_schema", "JSON_LOAD_FAILED", path.name, str(exc)
                )
            )
            return None

    @staticmethod
    def _check_required_files(
        path: Path, issues: list[IntegralsAcademicReviewIssue]
    ) -> None:
        for name in REQUIRED_FILES:
            if not (path / name).is_file():
                issues.append(
                    IntegralsAcademicReviewValidator._issue(
                        "required_files",
                        "MISSING_REQUIRED_FILE",
                        name,
                        "Required curated DATA-MATH12-023 file is missing.",
                    )
                )

    @staticmethod
    def _issue(
        check: str, code: str, location: str, message: str
    ) -> IntegralsAcademicReviewIssue:
        return IntegralsAcademicReviewIssue(check, code, location, message)
