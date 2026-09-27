from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.concepts.models import RelationType
from app.curriculum.import_schemas import (
    ChapterRecord,
    ConceptRecord,
    ConceptRelationRecord,
    LearningOutcomeRecord,
    ProblemTypeConceptRecord,
    ProblemTypeOutcomeRecord,
    ProblemTypeRecord,
    SubjectRecord,
    TopicRecord,
)


DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "curriculum"
DEFAULT_CANONICAL_CURRICULUM_PATH = (
    DATA_ROOT / "math" / "grade12" / "gdpt2018"
)
DEFAULT_DERIVATIVE_STAGING_PATH = (
    DEFAULT_CANONICAL_CURRICULUM_PATH
    / "staging"
    / "derivative_applications_v0_1"
)
DEFAULT_PRODUCTION_BRIDGE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "questions"
    / "math"
    / "grade12"
    / "derivative_applications_v0_1"
    / "production_bridge"
    / "v0_1"
)
EXPECTED_CANDIDATE_COUNTS = {
    "subjects": 1,
    "chapters": 6,
    "topics": 10,
    "problem_types": 30,
    "concepts": 41,
    "learning_outcomes": 18,
    "concept_relations": 48,
    "problem_type_concepts": 100,
    "problem_type_learning_outcomes": 40,
}

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class DerivativeCurriculumCandidate:
    metadata: dict[str, Any]
    subject: SubjectRecord
    chapters: tuple[ChapterRecord, ...]
    topics: tuple[TopicRecord, ...]
    problem_types: tuple[ProblemTypeRecord, ...]
    concepts: tuple[ConceptRecord, ...]
    learning_outcomes: tuple[LearningOutcomeRecord, ...]
    concept_relations: tuple[ConceptRelationRecord, ...]
    problem_type_concepts: tuple[ProblemTypeConceptRecord, ...]
    problem_type_learning_outcomes: tuple[ProblemTypeOutcomeRecord, ...]
    content_hash: str

    @property
    def counts(self) -> dict[str, int]:
        return {
            "subjects": 1,
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
        }

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "metadata": copy.deepcopy(self.metadata),
            "subject": self.subject.model_dump(mode="json"),
            "chapters": [item.model_dump(mode="json") for item in self.chapters],
            "topics": [item.model_dump(mode="json") for item in self.topics],
            "problem_types": [
                item.model_dump(mode="json") for item in self.problem_types
            ],
            "concepts": [item.model_dump(mode="json") for item in self.concepts],
            "learning_outcomes": [
                item.model_dump(mode="json") for item in self.learning_outcomes
            ],
            "concept_relations": [
                item.model_dump(mode="json") for item in self.concept_relations
            ],
            "problem_type_concepts": [
                item.model_dump(mode="json")
                for item in self.problem_type_concepts
            ],
            "problem_type_learning_outcomes": [
                item.model_dump(mode="json")
                for item in self.problem_type_learning_outcomes
            ],
        }


@dataclass(frozen=True, slots=True, order=True)
class DerivativeCurriculumCandidateIssue:
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class DerivativeCurriculumCandidateReport:
    status: str
    dataset_path: str
    counts: dict[str, int]
    content_hash: str
    candidate: DerivativeCurriculumCandidate | None
    errors: tuple[DerivativeCurriculumCandidateIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        candidate_metadata = self.candidate.metadata if self.candidate else {}
        return {
            "status": self.status,
            "dataset_path": self.dataset_path,
            "counts": self.counts,
            "content_hash": self.content_hash,
            "candidate_metadata": candidate_metadata,
            "errors": [asdict(error) for error in self.errors],
        }


class DerivativeCurriculumCandidateBuilder:
    """Merge canonical Grade 12 data with derivative staging in memory only."""

    def build(
        self,
        canonical_path: Path = DEFAULT_CANONICAL_CURRICULUM_PATH,
        staging_path: Path = DEFAULT_DERIVATIVE_STAGING_PATH,
        bridge_root: Path = DEFAULT_PRODUCTION_BRIDGE_ROOT,
    ) -> DerivativeCurriculumCandidate:
        canonical_path = canonical_path.resolve()
        staging_path = staging_path.resolve()
        bridge_root = bridge_root.resolve()
        policy = self._load_object(bridge_root / "curriculum_candidate_policy.json")
        manifest = self._load_object(canonical_path / "manifest.json")
        subject = SubjectRecord.model_validate(
            self._load_object(canonical_path / "subject.json")
        )

        chapters = tuple(
            self._load_list(ChapterRecord, canonical_path / "chapters.json")
        )
        topics = tuple(
            self._merge_by_code(
                self._load_list(TopicRecord, canonical_path / "topics.json"),
                self._load_list(TopicRecord, staging_path / "topics.json"),
            )
        )
        problem_types = self._merge_by_code(
            self._load_list(
                ProblemTypeRecord, canonical_path / "problem_types.json"
            ),
            self._load_list(ProblemTypeRecord, staging_path / "problem_types.json"),
        )
        problem_types = [
            item.model_copy(update={"is_active": False})
            if item.code == "COMPLETE_FUNCTION_ANALYSIS"
            else item
            for item in problem_types
        ]
        concepts = tuple(
            self._merge_by_code(
                self._load_list(ConceptRecord, canonical_path / "concepts.json"),
                self._load_list(ConceptRecord, staging_path / "concepts.json"),
            )
        )
        outcomes = tuple(
            self._merge_by_code(
                self._load_list(
                    LearningOutcomeRecord,
                    canonical_path / "learning_outcomes.json",
                ),
                self._load_list(
                    LearningOutcomeRecord,
                    staging_path / "learning_outcomes.json",
                ),
            )
        )
        relations = tuple(
            self._merge_by_key(
                self._load_list(
                    ConceptRelationRecord,
                    canonical_path / "concept_relations.json",
                ),
                self._load_list(
                    ConceptRelationRecord,
                    staging_path / "concept_relations.json",
                ),
                lambda item: (
                    item.source_code,
                    item.target_code,
                    item.relation_type.value,
                ),
            )
        )
        problem_concepts = tuple(
            self._merge_by_key(
                self._load_list(
                    ProblemTypeConceptRecord,
                    canonical_path / "problem_type_concepts.json",
                ),
                self._load_list(
                    ProblemTypeConceptRecord,
                    staging_path / "problem_type_concepts.json",
                ),
                lambda item: (item.problem_type_code, item.concept_code),
            )
        )
        problem_outcomes = tuple(
            self._merge_by_key(
                self._load_list(
                    ProblemTypeOutcomeRecord,
                    canonical_path / "problem_type_learning_outcomes.json",
                ),
                self._load_list(
                    ProblemTypeOutcomeRecord,
                    staging_path / "problem_type_learning_outcomes.json",
                ),
                lambda item: (
                    item.problem_type_code,
                    item.learning_outcome_code,
                ),
            )
        )
        metadata = {
            "dataset_code": policy.get("candidate_code"),
            "canonical_dataset_code": manifest.get("dataset_code"),
            "dataset_version": policy.get("candidate_dataset_version"),
            "curriculum_code": manifest.get("curriculum_code"),
            "curriculum_version_code": manifest.get("curriculum_version_code"),
            "subject_code": subject.code,
            "grade_level": subject.grade_level,
            "verified_at": policy.get("verified_at"),
            "status": policy.get("status"),
            "importable": False,
        }
        payload = {
            "metadata": metadata,
            "subject": subject.model_dump(mode="json"),
            "chapters": [item.model_dump(mode="json") for item in chapters],
            "topics": [item.model_dump(mode="json") for item in topics],
            "problem_types": [
                item.model_dump(mode="json") for item in problem_types
            ],
            "concepts": [item.model_dump(mode="json") for item in concepts],
            "learning_outcomes": [
                item.model_dump(mode="json") for item in outcomes
            ],
            "concept_relations": [
                item.model_dump(mode="json") for item in relations
            ],
            "problem_type_concepts": [
                item.model_dump(mode="json") for item in problem_concepts
            ],
            "problem_type_learning_outcomes": [
                item.model_dump(mode="json") for item in problem_outcomes
            ],
        }
        content_hash = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return DerivativeCurriculumCandidate(
            metadata=metadata,
            subject=subject,
            chapters=chapters,
            topics=topics,
            problem_types=tuple(problem_types),
            concepts=concepts,
            learning_outcomes=outcomes,
            concept_relations=relations,
            problem_type_concepts=problem_concepts,
            problem_type_learning_outcomes=problem_outcomes,
            content_hash=content_hash,
        )

    @staticmethod
    def _merge_by_code(canonical: list[T], staging: list[T]) -> list[T]:
        return DerivativeCurriculumCandidateBuilder._merge_by_key(
            canonical, staging, lambda item: (str(getattr(item, "code")),)
        )

    @staticmethod
    def _merge_by_key(
        canonical: list[T],
        staging: list[T],
        key: Any,
    ) -> list[T]:
        records = {key(item): item for item in canonical}
        records.update({key(item): item for item in staging})
        return [records[item_key] for item_key in sorted(records)]

    @staticmethod
    def _load_object(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Cannot load {path}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"Expected object in {path}")
        return value

    @staticmethod
    def _load_list(model: type[T], path: Path) -> list[T]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return TypeAdapter(list[model]).validate_python(value)  # type: ignore[valid-type]
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise ValueError(f"Cannot load {path}: {error}") from error


class DerivativeCurriculumCandidateValidator:
    def validate(
        self,
        canonical_path: Path = DEFAULT_CANONICAL_CURRICULUM_PATH,
        staging_path: Path = DEFAULT_DERIVATIVE_STAGING_PATH,
        bridge_root: Path = DEFAULT_PRODUCTION_BRIDGE_ROOT,
    ) -> DerivativeCurriculumCandidateReport:
        canonical_path = canonical_path.resolve()
        errors: list[DerivativeCurriculumCandidateIssue] = []
        try:
            candidate = DerivativeCurriculumCandidateBuilder().build(
                canonical_path, staging_path, bridge_root
            )
        except ValueError as error:
            self._add(errors, "CANDIDATE_BUILD_FAILED", canonical_path.as_posix(), str(error))
            return DerivativeCurriculumCandidateReport(
                status="FAIL",
                dataset_path=canonical_path.as_posix(),
                counts={},
                content_hash="",
                candidate=None,
                errors=tuple(errors),
            )

        if candidate.counts != EXPECTED_CANDIDATE_COUNTS:
            self._add(
                errors,
                "CANDIDATE_COUNTS_MISMATCH",
                "candidate",
                f"Expected {EXPECTED_CANDIDATE_COUNTS}; found {candidate.counts}.",
            )
        expected_metadata = {
            "canonical_dataset_code": "MATH_G12_GDPT2018_CORE",
            "dataset_version": "1.2.0",
            "subject_code": "MATH_G12",
            "verified_at": None,
            "importable": False,
        }
        for field, expected in expected_metadata.items():
            if candidate.metadata.get(field) != expected:
                self._add(errors, "CANDIDATE_METADATA_MISMATCH", field,
                          f"Expected {expected!r}; found {candidate.metadata.get(field)!r}.")
        if candidate.subject.code != "MATH_G12":
            self._add(errors, "SUBJECT_IDENTITY_INVALID", "subject.code",
                      "Canonical candidate subject must be MATH_G12.")
        if any(item.code == "MATH12" for item in [candidate.subject]):
            self._add(errors, "LEGACY_SUBJECT_IDENTITY_FORBIDDEN", "subject.code",
                      "MATH12 must not become a canonical Subject identity.")

        self._validate_uniqueness(candidate, errors)
        self._validate_references(candidate, errors)
        self._validate_graph(candidate, errors)
        compatibility = next(
            (
                item
                for item in candidate.problem_types
                if item.code == "COMPLETE_FUNCTION_ANALYSIS"
            ),
            None,
        )
        if compatibility is None or compatibility.is_active:
            self._add(
                errors,
                "LEGACY_COMPATIBILITY_RECORD_INVALID",
                "problem_types.COMPLETE_FUNCTION_ANALYSIS",
                "Legacy compatibility ProblemType must remain present and inactive.",
            )
        self._validate_manifest_discovery(canonical_path, errors)

        final_errors = tuple(sorted(set(errors)))
        return DerivativeCurriculumCandidateReport(
            status="PASS" if not final_errors else "FAIL",
            dataset_path=canonical_path.as_posix(),
            counts=candidate.counts,
            content_hash=candidate.content_hash,
            candidate=candidate,
            errors=final_errors,
        )

    def _validate_uniqueness(
        self,
        candidate: DerivativeCurriculumCandidate,
        errors: list[DerivativeCurriculumCandidateIssue],
    ) -> None:
        for label, rows in (
            ("chapters", candidate.chapters),
            ("topics", candidate.topics),
            ("problem_types", candidate.problem_types),
            ("concepts", candidate.concepts),
            ("learning_outcomes", candidate.learning_outcomes),
        ):
            codes = [item.code for item in rows]
            if len(codes) != len(set(codes)):
                self._add(errors, "DUPLICATE_CODE", label,
                          f"Duplicate code in {label}.")
        for label, rows, key in (
            (
                "concept_relations",
                candidate.concept_relations,
                lambda item: (
                    item.source_code,
                    item.target_code,
                    item.relation_type.value,
                ),
            ),
            (
                "problem_type_concepts",
                candidate.problem_type_concepts,
                lambda item: (item.problem_type_code, item.concept_code),
            ),
            (
                "problem_type_learning_outcomes",
                candidate.problem_type_learning_outcomes,
                lambda item: (
                    item.problem_type_code,
                    item.learning_outcome_code,
                ),
            ),
        ):
            keys = [key(item) for item in rows]
            if len(keys) != len(set(keys)):
                self._add(errors, "DUPLICATE_MAPPING", label,
                          f"Duplicate key in {label}.")

    def _validate_references(
        self,
        candidate: DerivativeCurriculumCandidate,
        errors: list[DerivativeCurriculumCandidateIssue],
    ) -> None:
        chapters = {item.code for item in candidate.chapters}
        topics = {item.code for item in candidate.topics}
        problems = {item.code for item in candidate.problem_types}
        concepts = {item.code for item in candidate.concepts}
        outcomes = {item.code for item in candidate.learning_outcomes}
        checks = (
            ("topic.chapter_code", {item.chapter_code for item in candidate.topics}, chapters),
            ("problem_type.topic_code", {item.topic_code for item in candidate.problem_types}, topics),
            (
                "concept_relation",
                {item.source_code for item in candidate.concept_relations}
                | {item.target_code for item in candidate.concept_relations},
                concepts,
            ),
            (
                "problem_type_concept.problem_type",
                {item.problem_type_code for item in candidate.problem_type_concepts},
                problems,
            ),
            (
                "problem_type_concept.concept",
                {item.concept_code for item in candidate.problem_type_concepts},
                concepts,
            ),
            (
                "problem_type_outcome.problem_type",
                {
                    item.problem_type_code
                    for item in candidate.problem_type_learning_outcomes
                },
                problems,
            ),
            (
                "problem_type_outcome.outcome",
                {
                    item.learning_outcome_code
                    for item in candidate.problem_type_learning_outcomes
                },
                outcomes,
            ),
        )
        for location, references, available in checks:
            missing = sorted(references - available)
            if missing:
                self._add(errors, "REFERENCE_NOT_FOUND", location,
                          f"Missing references: {', '.join(missing)}.")

    def _validate_graph(
        self,
        candidate: DerivativeCurriculumCandidate,
        errors: list[DerivativeCurriculumCandidateIssue],
    ) -> None:
        codes = {item.code for item in candidate.concepts}
        outgoing = {code: [] for code in codes}
        for relation in candidate.concept_relations:
            if relation.relation_type == RelationType.PREREQUISITE:
                outgoing[relation.source_code].append(relation.target_code)
        state = {code: 0 for code in codes}

        def visit(code: str) -> bool:
            if state[code] == 1:
                return False
            if state[code] == 2:
                return True
            state[code] = 1
            if not all(visit(target) for target in outgoing[code]):
                return False
            state[code] = 2
            return True

        if not all(visit(code) for code in sorted(codes)):
            self._add(errors, "PREREQUISITE_GRAPH_CYCLE", "concept_relations",
                      "Candidate prerequisite graph must be acyclic.")

    def _validate_manifest_discovery(
        self,
        canonical_path: Path,
        errors: list[DerivativeCurriculumCandidateIssue],
    ) -> None:
        curriculum_root = canonical_path.parents[2]
        matching: list[Path] = []
        for path in curriculum_root.rglob("manifest.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(value, dict)
                and value.get("dataset_code") == "MATH_G12_GDPT2018_CORE"
            ):
                matching.append(path.resolve())
        expected = (canonical_path / "manifest.json").resolve()
        if matching != [expected]:
            self._add(
                errors,
                "CANONICAL_MANIFEST_DISCOVERY_AMBIGUOUS",
                curriculum_root.as_posix(),
                "Exactly one import-discoverable canonical manifest is allowed.",
            )

    @staticmethod
    def _add(
        errors: list[DerivativeCurriculumCandidateIssue],
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(DerivativeCurriculumCandidateIssue(code, location, message))
