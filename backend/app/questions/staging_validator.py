from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.questions.provenance_corrections import (
    ProvenanceCorrectionReport,
    QuestionProvenanceCorrectionResolver,
)
from app.questions.question_type_resolution import (
    SUPPORTED_STAGING_QUESTION_TYPES,
    effective_question_type,
    requires_question_group,
)
from app.questions.review_overlay import (
    QuestionReviewOverlayResolver,
    ReviewBatchReport,
)


BACKEND_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
DEFAULT_QUESTION_STAGING_PATH = (
    BACKEND_DATA_ROOT
    / "questions"
    / "math"
    / "grade12"
    / "derivative_applications_v0_1"
    / "staging"
)
DEFAULT_CURRICULUM_STAGING_PATH = (
    BACKEND_DATA_ROOT
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "derivative_applications_v0_1"
)

REQUIRED_STAGING_FILES = (
    "README.md",
    "candidate_questions.json",
    "coverage_report.json",
    "extraction_stats.json",
    "provenance_corrections.json",
    "review_queue.csv",
    "source_catalog.json",
    "subsource_catalog.json",
)
@dataclass(frozen=True, slots=True, order=True)
class QuestionStagingIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class FingerprintDuplicate:
    fingerprint: str
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProblemTypeCoverage:
    problem_type_code: str
    candidate_count: int
    question_type_counts: dict[str, int]
    coverage_status: str
    verified_count: int = 0
    hold_count: int = 0
    untouched_review_required_count: int = 0
    rejected_excluded_count: int = 0


@dataclass(frozen=True, slots=True)
class CandidateViewReport:
    status_summary: dict[str, int]
    coverage: tuple[ProblemTypeCoverage, ...]
    coverage_gaps: tuple[str, ...]
    promotion: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_summary": self.status_summary,
            "coverage": [asdict(item) for item in self.coverage],
            "coverage_gaps": list(self.coverage_gaps),
            "promotion": self.promotion,
        }


@dataclass(frozen=True, slots=True)
class QuestionStagingValidationReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    errors: tuple[QuestionStagingIssue, ...]
    duplicate_fingerprints: tuple[FingerprintDuplicate, ...]
    raw: CandidateViewReport
    effective_reviewed: CandidateViewReport
    provenance_corrections: ProvenanceCorrectionReport
    review_batches: tuple[ReviewBatchReport, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    @property
    def coverage(self) -> tuple[ProblemTypeCoverage, ...]:
        """Backward-compatible raw staging coverage for audit callers."""
        return self.raw.coverage

    @property
    def coverage_gaps(self) -> tuple[str, ...]:
        return self.raw.coverage_gaps

    @property
    def promotion(self) -> dict[str, Any]:
        return self.raw.promotion

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "errors": [asdict(error) for error in self.errors],
            "duplicate_fingerprints": [
                asdict(duplicate) for duplicate in self.duplicate_fingerprints
            ],
            "raw": self.raw.as_dict(),
            "effective_reviewed": self.effective_reviewed.as_dict(),
            "provenance_corrections": self.provenance_corrections.as_dict(),
            "review_batches": [batch.as_dict() for batch in self.review_batches],
        }


class QuestionStagingPromotionError(ValueError):
    def __init__(self, candidate_id: str, blockers: tuple[str, ...]) -> None:
        self.candidate_id = candidate_id
        self.blockers = blockers
        super().__init__(f"Candidate {candidate_id} cannot be promoted: {', '.join(blockers)}.")


def candidate_promotion_blockers(candidate: dict[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    review_record = candidate.get("review_record")
    review_status = (
        review_record.get("review_status")
        if isinstance(review_record, dict)
        else None
    )
    if candidate.get("status") == "REJECTED" or str(review_status).startswith("REJECTED"):
        blockers.append("STATUS_REJECTED")
    elif str(review_status).startswith("HOLD_"):
        blockers.append("STATUS_HOLD")
    elif candidate.get("status") != "VERIFIED":
        blockers.append("STATUS_NOT_VERIFIED")
    if requires_question_group(candidate):
        blockers.append("TRUE_FALSE_GROUP_UNSUPPORTED")
    if (
        candidate.get("status") == "VERIFIED"
        and candidate.get("review_batch")
        and candidate.get("promotion_ready") is not True
    ):
        blockers.append("EXPLICIT_PROMOTION_REQUIRED")
    visual_asset_required = (
        review_record.get("visual_asset_required") is True
        if isinstance(review_record, dict)
        else candidate.get("visual_asset_required") is True
    )
    if visual_asset_required:
        blockers.append("VISUAL_ASSET_REQUIRED")
    return tuple(blockers)


def assert_candidate_promotable(candidate: dict[str, Any]) -> None:
    blockers = candidate_promotion_blockers(candidate)
    if blockers:
        candidate_id = str(candidate.get("candidate_id") or "<unknown>")
        raise QuestionStagingPromotionError(candidate_id, blockers)


class QuestionStagingValidator:
    """Read-only validation and reporting for non-production question candidates."""

    def validate(
        self,
        dataset_path: Path = DEFAULT_QUESTION_STAGING_PATH,
        curriculum_path: Path = DEFAULT_CURRICULUM_STAGING_PATH,
        review_root: Path | None = None,
    ) -> QuestionStagingValidationReport:
        dataset_path = dataset_path.resolve()
        curriculum_path = curriculum_path.resolve()
        review_root = (
            review_root.resolve()
            if review_root is not None
            else dataset_path.parent / "review"
        )
        file_issues = self._validate_required_files(dataset_path)

        candidates_value = self._load_json(
            dataset_path / "candidate_questions.json", "dataset_files", file_issues
        )
        source_catalog_value = self._load_json(
            dataset_path / "source_catalog.json", "dataset_files", file_issues
        )
        subsources_value = self._load_json(
            dataset_path / "subsource_catalog.json", "dataset_files", file_issues
        )
        self._load_json(dataset_path / "coverage_report.json", "dataset_files", file_issues)
        self._load_json(dataset_path / "extraction_stats.json", "dataset_files", file_issues)

        candidates = self._object_list(
            candidates_value, "candidate_questions.json", file_issues
        )
        source_catalog = (
            source_catalog_value if isinstance(source_catalog_value, dict) else {}
        )
        sources = self._object_list(
            source_catalog.get("sources"), "source_catalog.json.sources", file_issues
        )
        subsources = self._object_list(
            subsources_value, "subsource_catalog.json", file_issues
        )

        problem_types = self._load_taxonomy_codes(
            curriculum_path / "problem_types.json", "code", file_issues
        )
        concepts = self._load_taxonomy_codes(
            curriculum_path / "concepts.json", "code", file_issues
        )
        learning_outcomes = self._load_taxonomy_codes(
            curriculum_path / "learning_outcomes.json", "code", file_issues
        )

        check_issues: dict[str, list[QuestionStagingIssue]] = {
            "dataset_files": file_issues,
            "unique_identifiers": self._validate_unique_identifiers(
                candidates, sources, subsources
            ),
            "problem_type_references": self._validate_problem_type_references(
                candidates, problem_types
            ),
            "concept_references": self._validate_nested_references(
                candidates, "concepts", "concept_code", concepts
            ),
            "learning_outcome_references": self._validate_nested_references(
                candidates,
                "learning_outcomes",
                "learning_outcome_code",
                learning_outcomes,
            ),
            "source_references": self._validate_source_references(
                candidates, sources, subsources
            ),
            "subsource_references": self._validate_subsource_references(
                candidates, subsources
            ),
            "fingerprints_available": self._validate_fingerprints(candidates),
            "provenance_corrections": [],
            "review_overlays": [],
            "review_batch_overlap": [],
        }
        provenance_result = QuestionProvenanceCorrectionResolver().resolve(
            candidates,
            dataset_path / "provenance_corrections.json",
            subsources,
        )
        for correction_issue in provenance_result.report.issues:
            check_issues["provenance_corrections"].append(QuestionStagingIssue(
                check="provenance_corrections",
                code=correction_issue.code,
                location=correction_issue.candidate_id,
                message=correction_issue.message,
            ))
        review_results = []
        effective_candidates = (
            list(provenance_result.candidates)
            if provenance_result.report.is_valid
            else candidates
        )
        reviewed_candidate_batches: dict[str, str] = {}
        batch_paths = (
            tuple(
                batch_path
                for batch_path in sorted(review_root.glob("batch_*"))
                if batch_path.is_dir()
            )
            if review_root.is_dir()
            else ()
        )
        for batch_path in batch_paths:
            result = QuestionReviewOverlayResolver().resolve(
                effective_candidates, batch_path
            )
            review_results.append(result)
            for review_error in result.report.errors:
                check_issues["review_overlays"].append(QuestionStagingIssue(
                    check="review_overlays",
                    code=review_error.code,
                    location=f"{batch_path.name}/{review_error.candidate_id}",
                    message=(
                        f"{review_error.message} "
                        f"[batch={batch_path.name}; path={result.report.path}; "
                        f"candidate_id={review_error.candidate_id}]"
                    ),
                ))
            overlapping_ids = sorted(
                set(result.report.reviewed_candidate_ids) & set(reviewed_candidate_batches)
            )
            for candidate_id in overlapping_ids:
                check_issues["review_batch_overlap"].append(QuestionStagingIssue(
                    check="review_batch_overlap",
                    code="CANDIDATE_REVIEW_BATCH_OVERLAP",
                    location=batch_path.name,
                    message=(
                        f"{candidate_id} was already reviewed by "
                        f"{reviewed_candidate_batches[candidate_id]}."
                    ),
                ))
            if result.report.is_valid and not overlapping_ids:
                effective_candidates = list(result.candidates)
                reviewed_candidate_batches.update({
                    candidate_id: result.report.batch_code
                    for candidate_id in result.report.reviewed_candidate_ids
                })
        checks = {name: not issues for name, issues in check_issues.items()}
        checks["review_overlays"] = (
            all(result.report.is_valid for result in review_results)
            and checks["review_overlays"]
            and checks["review_batch_overlap"]
        )
        issues = tuple(sorted({issue for values in check_issues.values() for issue in values}))

        duplicates = self._duplicate_fingerprints(candidates)
        raw_coverage = self._coverage(candidates, problem_types, effective=False)
        effective_coverage = self._coverage(
            effective_candidates, problem_types, effective=True
        )
        raw_view = CandidateViewReport(
            status_summary=self._reviewed_status_summary(candidates),
            coverage=raw_coverage,
            coverage_gaps=self._coverage_gaps(raw_coverage),
            promotion=self._promotion_summary(candidates),
        )
        effective_view = CandidateViewReport(
            status_summary=self._reviewed_status_summary(effective_candidates),
            coverage=effective_coverage,
            coverage_gaps=self._coverage_gaps(effective_coverage),
            promotion=self._promotion_summary(effective_candidates),
        )
        return QuestionStagingValidationReport(
            dataset_path=dataset_path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts={
                "candidates": len(candidates),
                "problem_types": len(problem_types),
                "concepts": len(concepts),
                "learning_outcomes": len(learning_outcomes),
                "sources": len(sources),
                "subsources": len(subsources),
                "duplicate_fingerprint_groups": len(duplicates),
                "review_batches": len(review_results),
            },
            errors=issues,
            duplicate_fingerprints=duplicates,
            raw=raw_view,
            effective_reviewed=effective_view,
            provenance_corrections=provenance_result.report,
            review_batches=tuple(result.report for result in review_results),
        )

    @staticmethod
    def _validate_required_files(path: Path) -> list[QuestionStagingIssue]:
        return [
            QuestionStagingIssue(
                check="dataset_files",
                code="MISSING_FILE",
                location=name,
                message="Required question staging file is missing.",
            )
            for name in REQUIRED_STAGING_FILES
            if not (path / name).is_file()
        ]

    @staticmethod
    def _load_json(
        path: Path,
        check: str,
        issues: list[QuestionStagingIssue],
    ) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            issues.append(QuestionStagingIssue(
                check=check,
                code="INVALID_JSON",
                location=path.name,
                message=f"Cannot load JSON: {error}.",
            ))
            return None

    @staticmethod
    def _object_list(
        value: Any,
        location: str,
        issues: list[QuestionStagingIssue],
    ) -> list[dict[str, Any]]:
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
        if value is not None:
            issues.append(QuestionStagingIssue(
                check="dataset_files",
                code="INVALID_JSON_SHAPE",
                location=location,
                message="Expected a JSON array of objects.",
            ))
        return []

    def _load_taxonomy_codes(
        self,
        path: Path,
        code_field: str,
        issues: list[QuestionStagingIssue],
    ) -> tuple[str, ...]:
        value = self._load_json(path, "dataset_files", issues)
        rows = self._object_list(value, path.name, issues)
        return tuple(
            str(row[code_field])
            for row in rows
            if isinstance(row.get(code_field), str) and row[code_field]
        )

    @staticmethod
    def _duplicates(rows: list[dict[str, Any]], field: str) -> set[str]:
        values = [row.get(field) for row in rows]
        counts = Counter(value for value in values if isinstance(value, str) and value)
        return {value for value, count in counts.items() if count > 1}

    def _validate_unique_identifiers(
        self,
        candidates: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        subsources: list[dict[str, Any]],
    ) -> list[QuestionStagingIssue]:
        issues: list[QuestionStagingIssue] = []
        specs = (
            (candidates, "candidate_id", "candidate_questions.json"),
            (sources, "source_code", "source_catalog.json"),
            (subsources, "subsource_code", "subsource_catalog.json"),
        )
        for rows, field, location in specs:
            for duplicate in sorted(self._duplicates(rows, field)):
                issues.append(QuestionStagingIssue(
                    check="unique_identifiers",
                    code="DUPLICATE_IDENTIFIER",
                    location=location,
                    message=f"Duplicate {field}: {duplicate}.",
                ))
            for index, row in enumerate(rows):
                if not isinstance(row.get(field), str) or not row[field]:
                    issues.append(QuestionStagingIssue(
                        check="unique_identifiers",
                        code="MISSING_IDENTIFIER",
                        location=f"{location}[{index}].{field}",
                        message=f"{field} must be a non-empty string.",
                    ))
        return issues

    @staticmethod
    def _reference_issue(
        check: str, location: str, field: str, value: Any
    ) -> QuestionStagingIssue:
        return QuestionStagingIssue(
            check=check,
            code="REFERENCE_NOT_FOUND",
            location=f"{location}.{field}",
            message=f"Reference does not resolve: {value!r}.",
        )

    def _validate_problem_type_references(
        self,
        candidates: list[dict[str, Any]],
        problem_types: tuple[str, ...],
    ) -> list[QuestionStagingIssue]:
        available = set(problem_types)
        issues: list[QuestionStagingIssue] = []
        for index, candidate in enumerate(candidates):
            location = f"candidate_questions.json[{index}]"
            value = candidate.get("problem_type_code")
            if value not in available:
                issues.append(self._reference_issue(
                    "problem_type_references", location, "problem_type_code", value
                ))
            for field in ("concepts", "learning_outcomes"):
                mappings = candidate.get(field)
                if not isinstance(mappings, list):
                    continue
                for mapping_index, mapping in enumerate(mappings):
                    if not isinstance(mapping, dict):
                        continue
                    mapped = mapping.get("problem_type_code")
                    if mapped not in available:
                        issues.append(self._reference_issue(
                            "problem_type_references",
                            f"{location}.{field}[{mapping_index}]",
                            "problem_type_code",
                            mapped,
                        ))
        return issues

    def _validate_nested_references(
        self,
        candidates: list[dict[str, Any]],
        list_field: str,
        code_field: str,
        available_codes: tuple[str, ...],
    ) -> list[QuestionStagingIssue]:
        available = set(available_codes)
        issues: list[QuestionStagingIssue] = []
        check = "concept_references" if list_field == "concepts" else "learning_outcome_references"
        for index, candidate in enumerate(candidates):
            mappings = candidate.get(list_field)
            if not isinstance(mappings, list):
                issues.append(QuestionStagingIssue(
                    check=check,
                    code="INVALID_MAPPING_SHAPE",
                    location=f"candidate_questions.json[{index}].{list_field}",
                    message="Expected a JSON array of mapping objects.",
                ))
                continue
            for mapping_index, mapping in enumerate(mappings):
                value = mapping.get(code_field) if isinstance(mapping, dict) else None
                if value not in available:
                    issues.append(self._reference_issue(
                        check,
                        f"candidate_questions.json[{index}].{list_field}[{mapping_index}]",
                        code_field,
                        value,
                    ))
        return issues

    def _validate_source_references(
        self,
        candidates: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        subsources: list[dict[str, Any]],
    ) -> list[QuestionStagingIssue]:
        available = {
            row["source_code"] for row in sources if isinstance(row.get("source_code"), str)
        }
        issues: list[QuestionStagingIssue] = []
        for index, candidate in enumerate(candidates):
            value = candidate.get("source_code")
            if value not in available:
                issues.append(self._reference_issue(
                    "source_references",
                    f"candidate_questions.json[{index}]",
                    "source_code",
                    value,
                ))
        for index, subsource in enumerate(subsources):
            value = subsource.get("source_code")
            if value not in available:
                issues.append(self._reference_issue(
                    "source_references",
                    f"subsource_catalog.json[{index}]",
                    "source_code",
                    value,
                ))
        return issues

    def _validate_subsource_references(
        self,
        candidates: list[dict[str, Any]],
        subsources: list[dict[str, Any]],
    ) -> list[QuestionStagingIssue]:
        catalog = {
            row["subsource_code"]: row.get("source_code")
            for row in subsources
            if isinstance(row.get("subsource_code"), str)
        }
        issues: list[QuestionStagingIssue] = []
        for index, candidate in enumerate(candidates):
            value = candidate.get("subsource_code")
            if value in (None, ""):
                continue
            location = f"candidate_questions.json[{index}]"
            if value not in catalog:
                issues.append(self._reference_issue(
                    "subsource_references", location, "subsource_code", value
                ))
            elif catalog[value] != candidate.get("source_code"):
                issues.append(QuestionStagingIssue(
                    check="subsource_references",
                    code="SUBSOURCE_SOURCE_MISMATCH",
                    location=f"{location}.subsource_code",
                    message="Subsource does not belong to the candidate source.",
                ))
        return issues

    @staticmethod
    def _validate_fingerprints(
        candidates: list[dict[str, Any]],
    ) -> list[QuestionStagingIssue]:
        return [
            QuestionStagingIssue(
                check="fingerprints_available",
                code="MISSING_FINGERPRINT",
                location=f"candidate_questions.json[{index}].fingerprint",
                message="Candidate fingerprint must be a non-empty string.",
            )
            for index, candidate in enumerate(candidates)
            if not isinstance(candidate.get("fingerprint"), str)
            or not candidate["fingerprint"]
        ]

    @staticmethod
    def _duplicate_fingerprints(
        candidates: list[dict[str, Any]],
    ) -> tuple[FingerprintDuplicate, ...]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for candidate in candidates:
            fingerprint = candidate.get("fingerprint")
            candidate_id = candidate.get("candidate_id")
            if isinstance(fingerprint, str) and isinstance(candidate_id, str):
                grouped[fingerprint].append(candidate_id)
        return tuple(
            FingerprintDuplicate(fingerprint, tuple(sorted(candidate_ids)))
            for fingerprint, candidate_ids in sorted(grouped.items())
            if len(candidate_ids) > 1
        )

    @staticmethod
    def _coverage(
        candidates: list[dict[str, Any]],
        problem_types: tuple[str, ...],
        *,
        effective: bool,
    ) -> tuple[ProblemTypeCoverage, ...]:
        by_problem_type: dict[str, Counter[str]] = defaultdict(Counter)
        statuses: dict[str, Counter[str]] = defaultdict(Counter)
        for candidate in candidates:
            problem_type = candidate.get("problem_type_code")
            review_status = QuestionStagingValidator._review_status(candidate)
            if effective and review_status == "REJECTED":
                if isinstance(problem_type, str):
                    statuses[problem_type]["REJECTED"] += 1
                continue
            question_type = (
                effective_question_type(candidate)
                if effective
                else candidate.get("question_type_detected")
            )
            if isinstance(problem_type, str) and isinstance(question_type, str):
                by_problem_type[problem_type][question_type] += 1
                statuses[problem_type][review_status] += 1
        result: list[ProblemTypeCoverage] = []
        for code in problem_types:
            type_counts = by_problem_type[code]
            known_and_observed_types = sorted(
                SUPPORTED_STAGING_QUESTION_TYPES | set(type_counts)
            )
            counts = {
                question_type: type_counts[question_type]
                for question_type in known_and_observed_types
            }
            total = sum(type_counts.values())
            result.append(ProblemTypeCoverage(
                problem_type_code=code,
                candidate_count=total,
                question_type_counts=counts,
                coverage_status="HAS_CANDIDATES" if total else "GAP",
                verified_count=statuses[code]["VERIFIED"],
                hold_count=statuses[code]["HOLD"],
                untouched_review_required_count=statuses[code][
                    "UNTOUCHED_REVIEW_REQUIRED"
                ],
                rejected_excluded_count=statuses[code]["REJECTED"],
            ))
        return tuple(result)

    @staticmethod
    def _review_status(candidate: dict[str, Any]) -> str:
        review_record = candidate.get("review_record")
        review_status = (
            review_record.get("review_status")
            if isinstance(review_record, dict)
            else None
        )
        if candidate.get("status") == "REJECTED" or str(review_status).startswith(
            "REJECTED"
        ):
            return "REJECTED"
        if str(review_status).startswith("HOLD_"):
            return "HOLD"
        if candidate.get("status") == "VERIFIED":
            return "VERIFIED"
        return "UNTOUCHED_REVIEW_REQUIRED"

    @classmethod
    def _reviewed_status_summary(
        cls, candidates: list[dict[str, Any]]
    ) -> dict[str, int]:
        counts = Counter(cls._review_status(candidate) for candidate in candidates)
        return {
            "total": len(candidates),
            "verified": counts["VERIFIED"],
            "hold": counts["HOLD"],
            "rejected": counts["REJECTED"],
            "untouched_review_required": counts["UNTOUCHED_REVIEW_REQUIRED"],
        }

    @staticmethod
    def _coverage_gaps(
        coverage: tuple[ProblemTypeCoverage, ...]
    ) -> tuple[str, ...]:
        return tuple(
            item.problem_type_code for item in coverage if item.candidate_count == 0
        )

    @staticmethod
    def _promotion_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        blocker_counts: Counter[str] = Counter()
        eligible = 0
        for candidate in candidates:
            blockers = candidate_promotion_blockers(candidate)
            if blockers:
                blocker_counts.update(blockers)
            else:
                eligible += 1
        return {
            "eligible": eligible,
            "blocked": len(candidates) - eligible,
            "blocker_counts": dict(sorted(blocker_counts.items())),
        }
