from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DEFAULT_VECTOR_STAGING_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "curriculum"
    / "math"
    / "grade12"
    / "gdpt2018"
    / "staging"
    / "vector_coordinates_v0_1"
)

VECTOR_LIST_FILES = (
    "chapters",
    "topics",
    "problem_types",
    "concepts",
    "official_learning_outcomes",
    "learning_outcomes",
    "concept_relations",
    "problem_type_concepts",
    "problem_type_learning_outcomes",
)
VECTOR_HASH_FILES = (*VECTOR_LIST_FILES, "taxonomy_metadata")
EXPECTED_VECTOR_COUNTS = {
    "chapters": 1,
    "topics": 4,
    "problem_types": 15,
    "concepts": 19,
    "official_learning_outcomes": 5,
    "learning_outcomes": 5,
    "concept_relations": 24,
    "problem_type_concepts": 37,
    "problem_type_learning_outcomes": 15,
}
EXPECTED_VECTOR_CONTENT_SHA256 = (
    "cbd949468ad5e074213f62e135a746dbebcfcad24ea84cfc7bbf3992bef9c247"
)
EXPECTED_CLASSIFICATION = {
    "official_learning_outcomes": "OFFICIAL_NORMALIZED",
    "topics": "COACH_LEARNING_DERIVED",
    "problem_types": "COACH_LEARNING_DERIVED",
    "concepts": "COACH_LEARNING_DERIVED",
    "concept_relations": "COACH_LEARNING_DERIVED",
    "weights": "COACH_LEARNING_DERIVED_INITIAL_EXPERT_WEIGHTS",
    "difficulty": "COACH_LEARNING_DERIVED_INITIAL_EXPERT_DIFFICULTY",
}


@dataclass(frozen=True, slots=True, order=True)
class VectorStagingIssue:
    check: str
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class VectorStagingReport:
    dataset_path: str
    status: str
    checks: dict[str, bool]
    counts: dict[str, int]
    content_sha256: str
    errors: tuple[VectorStagingIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "content_sha256": self.content_sha256,
            "errors": [asdict(error) for error in self.errors],
        }


class VectorCurriculumStagingValidator:
    """Validate the vector-coordinate review candidate without importing it."""

    def validate(
        self, dataset_path: Path = DEFAULT_VECTOR_STAGING_PATH
    ) -> VectorStagingReport:
        path = dataset_path.resolve()
        initial: list[VectorStagingIssue] = []
        rows = {name: self._load_list(path, name, initial) for name in VECTOR_LIST_FILES}
        metadata = self._load_object(path, "taxonomy_metadata", initial)
        validation_report = self._load_object(path, "validation_report", initial)
        content_hash = self.content_hash(path, initial)
        counts = {name: len(rows[name]) for name in VECTOR_LIST_FILES}

        checks_to_errors = {
            "dataset_files": [error for error in initial if error.check == "dataset_files"],
            "manifest_absent": self._validate_manifest_absent(path),
            "exact_counts": self._validate_counts(counts, validation_report),
            "unique_codes": self._validate_unique_codes(rows),
            "references_resolve": self._validate_references(rows, metadata),
            "grade_level": self._validate_grade(rows, metadata),
            "difficulty_range": self._validate_difficulty(rows),
            "primary_concept": self._validate_primary_concepts(rows),
            "concept_weight_totals": self._validate_weight_totals(
                rows, "problem_type_concepts", "concept"
            ),
            "learning_outcome_weight_totals": self._validate_weight_totals(
                rows, "problem_type_learning_outcomes", "learning_outcome"
            ),
            "prerequisite_graph_acyclic": self._validate_graph(rows),
            "provenance_boundary": self._validate_provenance(metadata, rows),
            "oxyz_boundary": self._validate_oxyz_boundary(metadata),
            "deterministic_content_hash": self._validate_hash(content_hash),
        }
        errors = list(initial)
        for name, check_errors in checks_to_errors.items():
            if name != "dataset_files":
                errors.extend(check_errors)
        checks = {name: not check_errors for name, check_errors in checks_to_errors.items()}
        ordered_errors = tuple(sorted(set(errors)))
        return VectorStagingReport(
            dataset_path=path.as_posix(),
            status="PASS" if all(checks.values()) else "FAIL",
            checks=checks,
            counts=counts,
            content_sha256=content_hash,
            errors=ordered_errors,
        )

    @staticmethod
    def _load_json(
        path: Path, name: str, errors: list[VectorStagingIssue]
    ) -> Any | None:
        file_path = path / f"{name}.json"
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(VectorStagingIssue(
                "dataset_files", "INVALID_OR_MISSING_JSON", file_path.name, str(error)
            ))
            return None

    @classmethod
    def _load_list(
        cls, path: Path, name: str, errors: list[VectorStagingIssue]
    ) -> list[dict[str, Any]]:
        value = cls._load_json(path, name, errors)
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            if value is not None:
                errors.append(VectorStagingIssue(
                    "dataset_files", "INVALID_JSON_SHAPE", f"{name}.json",
                    "Expected an array of objects.",
                ))
            return []
        return value

    @classmethod
    def _load_object(
        cls, path: Path, name: str, errors: list[VectorStagingIssue]
    ) -> dict[str, Any]:
        value = cls._load_json(path, name, errors)
        if not isinstance(value, dict):
            if value is not None:
                errors.append(VectorStagingIssue(
                    "dataset_files", "INVALID_JSON_SHAPE", f"{name}.json",
                    "Expected a JSON object.",
                ))
            return {}
        return value

    @classmethod
    def content_hash(
        cls, path: Path, errors: list[VectorStagingIssue] | None = None
    ) -> str:
        issues = errors if errors is not None else []
        digest = hashlib.sha256()
        for name in sorted(VECTOR_HASH_FILES):
            value = cls._load_json(path, name, issues)
            if value is None:
                continue
            canonical = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            digest.update(f"{name}.json".encode("utf-8"))
            digest.update(b"\0")
            digest.update(canonical)
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _codes(rows: list[dict[str, Any]], field: str = "code") -> set[str]:
        return {
            value for row in rows
            if isinstance((value := row.get(field)), str) and value
        }

    @staticmethod
    def _validate_manifest_absent(path: Path) -> list[VectorStagingIssue]:
        return [] if not (path / "manifest.json").exists() else [VectorStagingIssue(
            "manifest_absent", "STAGING_MANIFEST_FORBIDDEN", "manifest.json",
            "Vector review staging must not contain a canonical manifest.",
        )]

    @staticmethod
    def _validate_counts(
        counts: dict[str, int], report: dict[str, Any]
    ) -> list[VectorStagingIssue]:
        errors: list[VectorStagingIssue] = []
        if counts != EXPECTED_VECTOR_COUNTS:
            errors.append(VectorStagingIssue(
                "exact_counts", "UNEXPECTED_DATASET_COUNTS", "dataset",
                f"Expected {EXPECTED_VECTOR_COUNTS}; found {counts}.",
            ))
        if report.get("counts") != EXPECTED_VECTOR_COUNTS or (
            report.get("promotion_ready") is not False
            or report.get("academic_review_complete") is not False
            or report.get("canonical_curriculum_modified") is not False
        ):
            errors.append(VectorStagingIssue(
                "exact_counts", "INVALID_SUPPLIED_VALIDATION_REPORT",
                "validation_report.json", "The supplied report must match staging boundaries.",
            ))
        return errors

    @classmethod
    def _validate_unique_codes(
        cls, rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        fields = {
            "chapters": "code", "topics": "code", "problem_types": "code",
            "concepts": "code", "learning_outcomes": "code",
            "official_learning_outcomes": "official_outcome_code",
        }
        errors: list[VectorStagingIssue] = []
        for name, field in fields.items():
            values = [row.get(field) for row in rows[name]]
            if any(not isinstance(value, str) or not value for value in values):
                errors.append(VectorStagingIssue(
                    "unique_codes", "MISSING_CODE", f"{name}.json", field
                ))
            duplicates = sorted({value for value in values if values.count(value) > 1})
            for value in duplicates:
                errors.append(VectorStagingIssue(
                    "unique_codes", "DUPLICATE_CODE", f"{name}.json", str(value)
                ))
        return errors

    @classmethod
    def _validate_references(
        cls, rows: dict[str, list[dict[str, Any]]], metadata: dict[str, Any]
    ) -> list[VectorStagingIssue]:
        available = {
            "chapter": cls._codes(rows["chapters"]),
            "topic": cls._codes(rows["topics"]),
            "problem_type": cls._codes(rows["problem_types"]),
            "concept": cls._codes(rows["concepts"]),
            "learning_outcome": cls._codes(rows["learning_outcomes"]),
        }
        specs = (
            ("topics", "chapter_code", "chapter"),
            ("problem_types", "topic_code", "topic"),
            ("concept_relations", "source_code", "concept"),
            ("concept_relations", "target_code", "concept"),
            ("problem_type_concepts", "problem_type_code", "problem_type"),
            ("problem_type_concepts", "concept_code", "concept"),
            ("problem_type_learning_outcomes", "problem_type_code", "problem_type"),
            ("problem_type_learning_outcomes", "learning_outcome_code", "learning_outcome"),
        )
        errors: list[VectorStagingIssue] = []
        for name, field, target in specs:
            for index, row in enumerate(rows[name]):
                if row.get(field) not in available[target]:
                    errors.append(VectorStagingIssue(
                        "references_resolve", "REFERENCE_NOT_FOUND",
                        f"{name}.json[{index}].{field}", repr(row.get(field)),
                    ))
        if metadata.get("chapter_code") not in available["chapter"]:
            errors.append(VectorStagingIssue(
                "references_resolve", "REFERENCE_NOT_FOUND",
                "taxonomy_metadata.json.chapter_code", repr(metadata.get("chapter_code")),
            ))
        return errors

    @staticmethod
    def _validate_grade(
        rows: dict[str, list[dict[str, Any]]], metadata: dict[str, Any]
    ) -> list[VectorStagingIssue]:
        errors = [
            VectorStagingIssue(
                "grade_level", "INVALID_GRADE_LEVEL", f"{name}.json[{index}]",
                f"Expected grade_level=12; found {row.get('grade_level')!r}.",
            )
            for name in ("concepts", "learning_outcomes")
            for index, row in enumerate(rows[name])
            if row.get("grade_level") != 12
        ]
        if metadata.get("subject_code") != "MATH_G12":
            errors.append(VectorStagingIssue(
                "grade_level", "INVALID_SUBJECT_CODE", "taxonomy_metadata.json",
                "Expected MATH_G12.",
            ))
        return errors

    @staticmethod
    def _validate_difficulty(
        rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        errors: list[VectorStagingIssue] = []
        for index, row in enumerate(rows["problem_types"]):
            value = row.get("default_difficulty")
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= value <= 1
            ):
                errors.append(VectorStagingIssue(
                    "difficulty_range", "INVALID_DIFFICULTY",
                    f"problem_types.json[{index}].default_difficulty", repr(value),
                ))
        return errors

    @classmethod
    def _validate_primary_concepts(
        cls, rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        counts = {code: 0 for code in cls._codes(rows["problem_types"])}
        for row in rows["problem_type_concepts"]:
            code = row.get("problem_type_code")
            if code in counts and row.get("is_primary") is True:
                counts[code] += 1
        return [
            VectorStagingIssue(
                "primary_concept", "PRIMARY_CONCEPT_COUNT", code,
                f"Expected exactly one; found {count}.",
            )
            for code, count in sorted(counts.items()) if count != 1
        ]

    @classmethod
    def _validate_weight_totals(
        cls,
        rows: dict[str, list[dict[str, Any]]],
        mapping_name: str,
        label: str,
    ) -> list[VectorStagingIssue]:
        totals = {code: Decimal("0") for code in cls._codes(rows["problem_types"])}
        errors: list[VectorStagingIssue] = []
        for index, row in enumerate(rows[mapping_name]):
            code = row.get("problem_type_code")
            if code not in totals:
                continue
            try:
                weight = Decimal(str(row.get("weight")))
            except (InvalidOperation, ValueError):
                weight = Decimal("-1")
            if not Decimal("0") < weight <= Decimal("1"):
                errors.append(VectorStagingIssue(
                    f"{label}_weight_totals", "INVALID_WEIGHT",
                    f"{mapping_name}.json[{index}].weight", repr(row.get("weight")),
                ))
            else:
                totals[code] += weight
        for code, total in sorted(totals.items()):
            if total != Decimal("1.0"):
                errors.append(VectorStagingIssue(
                    f"{label}_weight_totals", "WEIGHT_TOTAL", code,
                    f"Expected exactly 1.0; found {total}.",
                ))
        return errors

    @classmethod
    def _validate_graph(
        cls, rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        concepts = cls._codes(rows["concepts"])
        edges = {code: set() for code in concepts}
        for row in rows["concept_relations"]:
            if row.get("relation_type") not in {"PREREQUISITE", "RELATED_TO"}:
                return [VectorStagingIssue(
                    "prerequisite_graph_acyclic", "INVALID_RELATION_TYPE",
                    "concept_relations.json", repr(row.get("relation_type")),
                )]
            if row.get("relation_type") == "PREREQUISITE" and row.get("source_code") in edges:
                edges[row["source_code"]].add(row.get("target_code"))
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(code: str) -> bool:
            if code in visiting:
                return False
            if code in visited:
                return True
            visiting.add(code)
            if any(target in concepts and not visit(target) for target in sorted(edges[code])):
                return False
            visiting.remove(code)
            visited.add(code)
            return True

        return [] if all(visit(code) for code in sorted(concepts)) else [VectorStagingIssue(
            "prerequisite_graph_acyclic", "PREREQUISITE_CYCLE",
            "concept_relations.json", "Prerequisite relations contain a cycle.",
        )]

    @staticmethod
    def _validate_provenance(
        metadata: dict[str, Any], rows: dict[str, list[dict[str, Any]]]
    ) -> list[VectorStagingIssue]:
        errors: list[VectorStagingIssue] = []
        if (
            metadata.get("status") != "REVIEW_CANDIDATE"
            or metadata.get("classification") != EXPECTED_CLASSIFICATION
        ):
            errors.append(VectorStagingIssue(
                "provenance_boundary", "INVALID_TAXONOMY_PROVENANCE",
                "taxonomy_metadata.json", "Staging provenance classifications changed.",
            ))
        if any(
            row.get("provenance_type") != "OFFICIAL_NORMALIZED"
            for row in rows["official_learning_outcomes"]
        ):
            errors.append(VectorStagingIssue(
                "provenance_boundary", "INVALID_OFFICIAL_OUTCOME_PROVENANCE",
                "official_learning_outcomes.json", "All official outcomes must be normalized.",
            ))
        return errors

    @staticmethod
    def _validate_oxyz_boundary(metadata: dict[str, Any]) -> list[VectorStagingIssue]:
        expected = (
            "Vector operations and vector coordinates only. "
            "Plane/line/sphere equation tasks belong to OXYZ_CHAPTER."
        )
        return [] if metadata.get("scope_boundary") == expected else [VectorStagingIssue(
            "oxyz_boundary", "INVALID_OXYZ_BOUNDARY",
            "taxonomy_metadata.json.scope_boundary", repr(metadata.get("scope_boundary")),
        )]

    @staticmethod
    def _validate_hash(content_hash: str) -> list[VectorStagingIssue]:
        return [] if content_hash == EXPECTED_VECTOR_CONTENT_SHA256 else [VectorStagingIssue(
            "deterministic_content_hash", "CONTENT_HASH_MISMATCH", "dataset",
            f"Expected {EXPECTED_VECTOR_CONTENT_SHA256}; found {content_hash}.",
        )]
