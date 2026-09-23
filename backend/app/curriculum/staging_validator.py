from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "curriculum"
DEFAULT_STAGING_PATH = (
    DATA_ROOT
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "derivative_applications_v0_1"
)

_LIST_FILES = (
    "chapters",
    "topics",
    "problem_types",
    "concepts",
    "learning_outcomes",
    "official_learning_outcomes",
    "concept_relations",
    "problem_type_concepts",
    "problem_type_learning_outcomes",
)


@dataclass(frozen=True, slots=True, order=True)
class StagingValidationIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class StagingValidationReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    errors: tuple[StagingValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "errors": [asdict(error) for error in self.errors],
        }


class CurriculumStagingValidator:
    """Validate a review-candidate taxonomy without importing or mutating it."""

    def validate(self, dataset_path: Path = DEFAULT_STAGING_PATH) -> StagingValidationReport:
        path = dataset_path.resolve()
        issues: list[StagingValidationIssue] = []
        rows = {
            file_name: self._load_list(path, file_name, issues)
            for file_name in _LIST_FILES
        }
        metadata = self._load_object(path, "taxonomy_metadata", issues)

        check_issues: dict[str, list[StagingValidationIssue]] = {
            "dataset_files": [issue for issue in issues if issue.check == "dataset_files"],
            "unique_codes": self._validate_unique_codes(rows),
            "references_resolve": self._validate_references(rows, metadata),
            "prerequisite_graph_acyclic": self._validate_prerequisite_graph(rows),
            "problem_type_primary_concept": self._validate_primary_concepts(rows),
            "problem_type_concept_weights": self._validate_concept_weights(rows),
            "problem_type_learning_outcome_coverage": self._validate_outcome_coverage(rows),
            "review_provenance_boundary": self._validate_provenance_boundary(metadata),
        }
        for check_name in check_issues:
            if check_name != "dataset_files":
                issues.extend(check_issues[check_name])

        checks = {
            check_name: not check_issues[check_name]
            for check_name in check_issues
        }
        sorted_issues = tuple(sorted(set(issues)))
        return StagingValidationReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts={file_name: len(rows[file_name]) for file_name in _LIST_FILES},
            errors=sorted_issues,
        )

    @staticmethod
    def _load_list(
        path: Path,
        file_name: str,
        issues: list[StagingValidationIssue],
    ) -> list[dict[str, Any]]:
        value = CurriculumStagingValidator._load_json(path, file_name, issues)
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            issues.append(StagingValidationIssue(
                check="dataset_files",
                code="INVALID_JSON_SHAPE",
                location=f"{file_name}.json",
                message="Expected a JSON array of objects.",
            ))
            return []
        return value

    @staticmethod
    def _load_object(
        path: Path,
        file_name: str,
        issues: list[StagingValidationIssue],
    ) -> dict[str, Any]:
        value = CurriculumStagingValidator._load_json(path, file_name, issues)
        if value is None:
            return {}
        if not isinstance(value, dict):
            issues.append(StagingValidationIssue(
                check="dataset_files",
                code="INVALID_JSON_SHAPE",
                location=f"{file_name}.json",
                message="Expected a JSON object.",
            ))
            return {}
        return value

    @staticmethod
    def _load_json(
        path: Path,
        file_name: str,
        issues: list[StagingValidationIssue],
    ) -> Any | None:
        file_path = path / f"{file_name}.json"
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            issues.append(StagingValidationIssue(
                check="dataset_files",
                code="MISSING_FILE",
                location=file_path.name,
                message="Required staging file is missing.",
            ))
        except (OSError, json.JSONDecodeError) as error:
            issues.append(StagingValidationIssue(
                check="dataset_files",
                code="INVALID_JSON",
                location=file_path.name,
                message=f"Cannot load JSON: {error}.",
            ))
        return None

    @staticmethod
    def _validate_unique_codes(
        rows: dict[str, list[dict[str, Any]]],
    ) -> list[StagingValidationIssue]:
        issues: list[StagingValidationIssue] = []
        code_fields = {
            "chapters": "code",
            "topics": "code",
            "problem_types": "code",
            "concepts": "code",
            "learning_outcomes": "code",
            "official_learning_outcomes": "official_outcome_code",
        }
        for file_name, code_field in code_fields.items():
            seen: set[str] = set()
            duplicates: set[str] = set()
            for index, item in enumerate(rows[file_name]):
                code = item.get(code_field)
                if not isinstance(code, str) or not code.strip():
                    issues.append(StagingValidationIssue(
                        check="unique_codes",
                        code="MISSING_CODE",
                        location=f"{file_name}.json[{index}]",
                        message=f"Field {code_field} must be a non-empty string.",
                    ))
                    continue
                if code in seen:
                    duplicates.add(code)
                seen.add(code)
            for duplicate in sorted(duplicates):
                issues.append(StagingValidationIssue(
                    check="unique_codes",
                    code="DUPLICATE_CODE",
                    location=f"{file_name}.json",
                    message=f"Duplicate {code_field}: {duplicate}.",
                ))
        return issues

    @staticmethod
    def _codes(rows: list[dict[str, Any]], field: str = "code") -> set[str]:
        return {
            value
            for item in rows
            if isinstance((value := item.get(field)), str) and value
        }

    def _validate_references(
        self,
        rows: dict[str, list[dict[str, Any]]],
        metadata: dict[str, Any],
    ) -> list[StagingValidationIssue]:
        chapters = self._codes(rows["chapters"])
        topics = self._codes(rows["topics"])
        problem_types = self._codes(rows["problem_types"])
        concepts = self._codes(rows["concepts"])
        outcomes = self._codes(rows["learning_outcomes"])
        official_outcomes = self._codes(
            rows["official_learning_outcomes"], "official_outcome_code"
        )
        issues: list[StagingValidationIssue] = []

        reference_specs = (
            ("topics", "chapter_code", chapters),
            ("problem_types", "topic_code", topics),
            ("concept_relations", "source_code", concepts),
            ("concept_relations", "target_code", concepts),
            ("problem_type_concepts", "problem_type_code", problem_types),
            ("problem_type_concepts", "concept_code", concepts),
            (
                "problem_type_learning_outcomes",
                "problem_type_code",
                problem_types,
            ),
            (
                "problem_type_learning_outcomes",
                "learning_outcome_code",
                outcomes,
            ),
        )
        for file_name, field, available in reference_specs:
            for index, item in enumerate(rows[file_name]):
                value = item.get(field)
                if not isinstance(value, str) or value not in available:
                    issues.append(StagingValidationIssue(
                        check="references_resolve",
                        code="REFERENCE_NOT_FOUND",
                        location=f"{file_name}.json[{index}].{field}",
                        message=f"Reference does not resolve: {value!r}.",
                    ))

        chapter_code = metadata.get("chapter_code")
        if chapter_code not in chapters:
            issues.append(StagingValidationIssue(
                check="references_resolve",
                code="REFERENCE_NOT_FOUND",
                location="taxonomy_metadata.json.chapter_code",
                message=f"Reference does not resolve: {chapter_code!r}.",
            ))

        for code in sorted(official_outcomes - outcomes):
            issues.append(StagingValidationIssue(
                check="references_resolve",
                code="OFFICIAL_OUTCOME_NOT_MAPPED",
                location="official_learning_outcomes.json",
                message=f"Official outcome has no import-compatible outcome: {code}.",
            ))
        for code in sorted(outcomes - official_outcomes):
            issues.append(StagingValidationIssue(
                check="references_resolve",
                code="OUTCOME_PROVENANCE_NOT_FOUND",
                location="learning_outcomes.json",
                message=f"Learning outcome has no official provenance record: {code}.",
            ))
        return issues

    def _validate_prerequisite_graph(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> list[StagingValidationIssue]:
        concepts = self._codes(rows["concepts"])
        outgoing: dict[str, set[str]] = {code: set() for code in concepts}
        for relation in rows["concept_relations"]:
            source = relation.get("source_code")
            target = relation.get("target_code")
            if (
                relation.get("relation_type") == "PREREQUISITE"
                and source in concepts
                and target in concepts
            ):
                outgoing[source].add(target)

        state = {code: 0 for code in concepts}
        stack: list[str] = []

        def visit(code: str) -> list[str] | None:
            if state[code] == 1:
                start = stack.index(code)
                return [*stack[start:], code]
            if state[code] == 2:
                return None
            state[code] = 1
            stack.append(code)
            for target in sorted(outgoing[code]):
                if cycle := visit(target):
                    return cycle
            stack.pop()
            state[code] = 2
            return None

        for concept_code in sorted(concepts):
            if cycle := visit(concept_code):
                return [StagingValidationIssue(
                    check="prerequisite_graph_acyclic",
                    code="PREREQUISITE_CYCLE",
                    location="concept_relations.json",
                    message=f"Cycle detected: {' -> '.join(cycle)}.",
                )]
        return []

    def _validate_primary_concepts(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> list[StagingValidationIssue]:
        problem_types = self._codes(rows["problem_types"])
        primary_counts = {code: 0 for code in problem_types}
        for mapping in rows["problem_type_concepts"]:
            code = mapping.get("problem_type_code")
            if code in primary_counts and mapping.get("is_primary") is True:
                primary_counts[code] += 1
        return [
            StagingValidationIssue(
                check="problem_type_primary_concept",
                code="PRIMARY_CONCEPT_COUNT",
                location=f"problem_type:{code}",
                message=f"Expected exactly one primary concept; found {primary_counts[code]}.",
            )
            for code in sorted(problem_types)
            if primary_counts[code] != 1
        ]

    def _validate_concept_weights(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> list[StagingValidationIssue]:
        problem_types = self._codes(rows["problem_types"])
        totals = {code: Decimal("0") for code in problem_types}
        issues: list[StagingValidationIssue] = []
        for index, mapping in enumerate(rows["problem_type_concepts"]):
            code = mapping.get("problem_type_code")
            if code not in totals:
                continue
            try:
                weight = Decimal(str(mapping.get("weight")))
            except (InvalidOperation, ValueError):
                issues.append(StagingValidationIssue(
                    check="problem_type_concept_weights",
                    code="INVALID_WEIGHT",
                    location=f"problem_type_concepts.json[{index}].weight",
                    message=f"Weight is not numeric: {mapping.get('weight')!r}.",
                ))
                continue
            totals[code] += weight

        for code in sorted(problem_types):
            if totals[code] != Decimal("1.0"):
                issues.append(StagingValidationIssue(
                    check="problem_type_concept_weights",
                    code="CONCEPT_WEIGHT_TOTAL",
                    location=f"problem_type:{code}",
                    message=f"Concept weights must total exactly 1.0; found {totals[code]}.",
                ))
        return issues

    def _validate_outcome_coverage(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> list[StagingValidationIssue]:
        problem_types = self._codes(rows["problem_types"])
        covered = {
            mapping.get("problem_type_code")
            for mapping in rows["problem_type_learning_outcomes"]
        }
        return [
            StagingValidationIssue(
                check="problem_type_learning_outcome_coverage",
                code="MISSING_LEARNING_OUTCOME",
                location=f"problem_type:{code}",
                message="ProblemType must map to at least one LearningOutcome.",
            )
            for code in sorted(problem_types - covered)
        ]

    @staticmethod
    def _validate_provenance_boundary(
        metadata: dict[str, Any],
    ) -> list[StagingValidationIssue]:
        issues: list[StagingValidationIssue] = []
        if metadata.get("status") != "REVIEW_CANDIDATE":
            issues.append(StagingValidationIssue(
                check="review_provenance_boundary",
                code="INVALID_STAGING_STATUS",
                location="taxonomy_metadata.json.status",
                message="Staging taxonomy must remain REVIEW_CANDIDATE.",
            ))
        expected = {
            "official_learning_outcomes": "OFFICIAL_NORMALIZED",
            "topics": "COACH_LEARNING_DERIVED",
            "problem_types": "COACH_LEARNING_DERIVED",
            "concepts": "COACH_LEARNING_DERIVED",
            "concept_relations": "COACH_LEARNING_DERIVED",
            "weights": "COACH_LEARNING_DERIVED_INITIAL_EXPERT_WEIGHTS",
            "difficulty": "COACH_LEARNING_DERIVED_INITIAL_EXPERT_DIFFICULTY",
        }
        classification = metadata.get("classification")
        if not isinstance(classification, dict):
            classification = {}
        for field, expected_value in expected.items():
            if classification.get(field) != expected_value:
                issues.append(StagingValidationIssue(
                    check="review_provenance_boundary",
                    code="INVALID_PROVENANCE_CLASSIFICATION",
                    location=f"taxonomy_metadata.json.classification.{field}",
                    message=f"Expected classification {expected_value}.",
                ))
        return issues
