from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.constants import LEGACY_CURRICULUM_VERSION_ID
from app.curriculum.import_schemas import (
    ChapterRecord,
    ConceptRecord,
    ConceptRelationRecord,
    CurriculumImportPreview,
    CurriculumImportResult,
    DatasetManifest,
    LearningOutcomeRecord,
    ProblemTypeConceptRecord,
    ProblemTypeOutcomeRecord,
    ProblemTypeRecord,
    SubjectRecord,
    TopicRecord,
)
from app.curriculum.models import (
    Chapter,
    Curriculum,
    CurriculumImportHistory,
    CurriculumVersion,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    ProblemTypeLearningOutcome,
    Topic,
)
from app.subjects.models import Subject
from data.seed.identifiers import stable_id

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "curriculum"


@dataclass(frozen=True, slots=True)
class LoadedCurriculumDataset:
    path: Path
    manifest: DatasetManifest
    subject: SubjectRecord
    chapters: list[ChapterRecord]
    topics: list[TopicRecord]
    problem_types: list[ProblemTypeRecord]
    concepts: list[ConceptRecord]
    learning_outcomes: list[LearningOutcomeRecord]
    concept_relations: list[ConceptRelationRecord]
    problem_type_concepts: list[ProblemTypeConceptRecord]
    problem_type_outcomes: list[ProblemTypeOutcomeRecord]
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
            "problem_type_learning_outcomes": len(self.problem_type_outcomes),
        }


class CurriculumImportService:
    """Validated, idempotent importer for versioned curriculum datasets."""

    def __init__(self, session: Session, data_root: Path = DATA_ROOT) -> None:
        self.session = session
        self.data_root = data_root

    def preview(self, dataset_code: str) -> CurriculumImportPreview:
        dataset = self._load(dataset_code)
        existing = self.session.scalar(self._history_statement(dataset)) is not None
        return CurriculumImportPreview(
            dataset_code=dataset.manifest.dataset_code,
            dataset_version=dataset.manifest.dataset_version,
            content_hash=dataset.content_hash,
            source_name=dataset.manifest.source_name,
            source_reference=dataset.manifest.source_reference,
            verified_at=dataset.manifest.verified_at,
            counts=dataset.counts,
            already_imported=existing,
        )

    def import_dataset(
        self, dataset_code: str, *, commit: bool = True
    ) -> CurriculumImportResult:
        dataset = self._load(dataset_code)
        self._lock()
        created: Counter[str] = Counter()
        updated: Counter[str] = Counter()
        unchanged: Counter[str] = Counter()
        try:
            prior_hashes = set(self.session.scalars(
                select(CurriculumImportHistory.content_hash).where(
                    CurriculumImportHistory.dataset_code
                    == dataset.manifest.dataset_code,
                    CurriculumImportHistory.dataset_version
                    == dataset.manifest.dataset_version,
                )
            ))
            if prior_hashes and dataset.content_hash not in prior_hashes:
                raise ApplicationError(
                    409,
                    "CURRICULUM_DATASET_VERSION_CONFLICT",
                    "Dataset content changed without a new dataset version.",
                )
            curriculum = self._upsert(
                Curriculum,
                stable_id("curriculum", dataset.manifest.curriculum_code),
                {
                    "code": dataset.manifest.curriculum_code,
                    "name": dataset.manifest.curriculum_name,
                    "description": dataset.manifest.curriculum_description,
                },
                "curricula",
                created,
                updated,
                unchanged,
            )
            version_id = stable_id(
                "curriculum-version",
                f"{dataset.manifest.curriculum_code}:{dataset.manifest.curriculum_version_code}",
            )
            version = self._upsert(
                CurriculumVersion,
                version_id,
                {
                    "curriculum_id": curriculum.id,
                    "code": dataset.manifest.curriculum_version_code,
                    "version": dataset.manifest.curriculum_version,
                    "source_reference": dataset.manifest.source_reference,
                    "verified_at": dataset.manifest.verified_at,
                    "is_active": True,
                },
                "curriculum_versions",
                created,
                updated,
                unchanged,
            )
            subject_id = self._entity_id(dataset, "subject", dataset.subject.code)
            subject = self.session.get(Subject, subject_id)
            if (
                subject is not None
                and subject.curriculum_version_id != version.id
                and not (
                    dataset.manifest.legacy_identity_compatible
                    and subject.curriculum_version_id == LEGACY_CURRICULUM_VERSION_ID
                )
            ):
                raise ApplicationError(
                    409,
                    "CURRICULUM_VERSION_CONFLICT",
                    "Stable subject identity belongs to another curriculum version.",
                )
            subject = self._upsert(
                Subject,
                subject_id,
                {
                    "curriculum_version_id": version.id,
                    "code": dataset.subject.code,
                    "name": dataset.subject.name,
                    "grade_level": dataset.subject.grade_level,
                    "description": dataset.subject.description,
                    "order_index": dataset.subject.order_index,
                },
                "subjects",
                created,
                updated,
                unchanged,
            )
            chapters = {
                item.code: self._upsert(
                    Chapter,
                    self._entity_id(dataset, "chapter", f"{subject.code}:{item.code}"),
                    {"subject_id": subject.id, **item.model_dump()},
                    "chapters", created, updated, unchanged,
                )
                for item in dataset.chapters
            }
            topics = {
                item.code: self._upsert(
                    Topic,
                    self._entity_id(dataset, "topic", f"{subject.code}:{item.code}"),
                    {
                        "chapter_id": chapters[item.chapter_code].id,
                        **item.model_dump(exclude={"chapter_code"}),
                    },
                    "topics", created, updated, unchanged,
                )
                for item in dataset.topics
            }
            problem_types = {
                item.code: self._upsert(
                    ProblemType,
                    self._entity_id(dataset, "problem-type", f"{subject.code}:{item.code}"),
                    {
                        "topic_id": topics[item.topic_code].id,
                        **item.model_dump(exclude={"topic_code"}),
                    },
                    "problem_types", created, updated, unchanged,
                )
                for item in dataset.problem_types
            }
            concepts = {
                item.code: self._upsert(
                    Concept,
                    self._entity_id(dataset, "concept", f"{subject.code}:{item.code}"),
                    {"subject_id": subject.id, **item.model_dump()},
                    "concepts", created, updated, unchanged,
                )
                for item in dataset.concepts
            }
            outcomes = {
                item.code: self._upsert(
                    LearningOutcome,
                    self._entity_id(
                        dataset, "learning-outcome", f"{subject.code}:{item.code}"
                    ),
                    {"subject_id": subject.id, **item.model_dump()},
                    "learning_outcomes", created, updated, unchanged,
                )
                for item in dataset.learning_outcomes
            }
            for item in dataset.concept_relations:
                source, target = concepts[item.source_code], concepts[item.target_code]
                if item.relation_type == RelationType.RELATED_TO and source.id > target.id:
                    source, target = target, source
                key = f"{source.code}>{target.code}:{item.relation_type.value}"
                self._upsert(
                    ConceptRelation,
                    self._entity_id(dataset, "concept-relation", key),
                    {
                        "source_concept_id": source.id,
                        "target_concept_id": target.id,
                        "relation_type": item.relation_type,
                    },
                    "concept_relations", created, updated, unchanged,
                )
            for item in dataset.problem_type_concepts:
                self._upsert_composite(
                    ProblemTypeConcept,
                    (problem_types[item.problem_type_code].id, concepts[item.concept_code].id),
                    {
                        "problem_type_id": problem_types[item.problem_type_code].id,
                        "concept_id": concepts[item.concept_code].id,
                        "weight": item.weight,
                        "is_primary": item.is_primary,
                    },
                    "problem_type_concepts", created, updated, unchanged,
                )
            for item in dataset.problem_type_outcomes:
                self._upsert_composite(
                    ProblemTypeLearningOutcome,
                    (
                        problem_types[item.problem_type_code].id,
                        outcomes[item.learning_outcome_code].id,
                    ),
                    {
                        "problem_type_id": problem_types[item.problem_type_code].id,
                        "learning_outcome_id": outcomes[item.learning_outcome_code].id,
                        "weight": item.weight,
                    },
                    "problem_type_learning_outcomes", created, updated, unchanged,
                )
            history = self.session.scalar(self._history_statement(dataset))
            if history is None:
                self.session.add(CurriculumImportHistory(
                    id=stable_id(
                        "curriculum-import",
                        f"{dataset.manifest.dataset_code}:{dataset.manifest.dataset_version}:{dataset.content_hash}",
                    ),
                    dataset_code=dataset.manifest.dataset_code,
                    dataset_version=dataset.manifest.dataset_version,
                    curriculum_version_id=version.id,
                    content_hash=dataset.content_hash,
                    manifest=dataset.manifest.model_dump(mode="json"),
                    counts=dataset.counts,
                ))
                created["curriculum_import_history"] += 1
            else:
                unchanged["curriculum_import_history"] += 1
            self.session.flush()
            if commit:
                self.session.commit()
        except Exception:
            if commit:
                self.session.rollback()
            raise
        logger.info(
            "Curriculum dataset processed (dataset=%s, version=%s)",
            dataset.manifest.dataset_code,
            dataset.manifest.dataset_version,
        )
        return CurriculumImportResult(
            **self.preview(dataset_code).model_dump(exclude={"already_imported"}),
            already_imported=True,
            created=dict(created),
            updated=dict(updated),
            unchanged=dict(unchanged),
        )

    def _load(self, dataset_code: str) -> LoadedCurriculumDataset:
        normalized = dataset_code.strip().upper()
        candidates: list[tuple[Path, DatasetManifest]] = []
        for path in self.data_root.rglob("manifest.json") if self.data_root.exists() else []:
            try:
                manifest = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError) as error:
                raise ApplicationError(
                    422, "CURRICULUM_DATASET_INVALID", f"Invalid manifest {path.name}: {error}."
                ) from error
            if manifest.dataset_code == normalized:
                candidates.append((path.parent, manifest))
        if not candidates:
            raise ApplicationError(
                404, "CURRICULUM_DATASET_NOT_FOUND", "Curriculum dataset was not found."
            )
        if len(candidates) > 1:
            raise ApplicationError(
                409, "CURRICULUM_DATASET_AMBIGUOUS", "Dataset code is not unique."
            )
        path, manifest = candidates[0]
        raw_files: dict[str, object] = {}
        for name in (
            "subject", "chapters", "topics", "problem_types", "concepts",
            "learning_outcomes", "concept_relations", "problem_type_concepts",
            "problem_type_learning_outcomes",
        ):
            file_path = path / f"{name}.json"
            try:
                raw_files[name] = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ApplicationError(
                    422,
                    "CURRICULUM_DATASET_INVALID",
                    f"Cannot load {file_path.name}: {error}.",
                ) from error
        try:
            dataset = LoadedCurriculumDataset(
                path=path,
                manifest=manifest,
                subject=SubjectRecord.model_validate(raw_files["subject"]),
                chapters=self._list(ChapterRecord, raw_files["chapters"]),
                topics=self._list(TopicRecord, raw_files["topics"]),
                problem_types=self._list(ProblemTypeRecord, raw_files["problem_types"]),
                concepts=self._list(ConceptRecord, raw_files["concepts"]),
                learning_outcomes=self._list(
                    LearningOutcomeRecord, raw_files["learning_outcomes"]
                ),
                concept_relations=self._list(
                    ConceptRelationRecord, raw_files["concept_relations"]
                ),
                problem_type_concepts=self._list(
                    ProblemTypeConceptRecord, raw_files["problem_type_concepts"]
                ),
                problem_type_outcomes=self._list(
                    ProblemTypeOutcomeRecord,
                    raw_files["problem_type_learning_outcomes"],
                ),
                content_hash=self._content_hash(manifest, raw_files),
            )
        except ValidationError as error:
            raise ApplicationError(
                422, "CURRICULUM_DATASET_INVALID", f"Dataset schema validation failed: {error}."
            ) from error
        self._validate(dataset)
        return dataset

    def _validate(self, dataset: LoadedCurriculumDataset) -> None:
        manifest = dataset.manifest
        if dataset.subject.code != manifest.subject_code or dataset.subject.grade_level != manifest.grade_level:
            raise ApplicationError(
                422,
                "CURRICULUM_DATASET_INVALID",
                "Manifest subject or grade does not match subject.json.",
            )
        self._unique(dataset.chapters, "chapter")
        self._unique(dataset.topics, "topic")
        self._unique(dataset.problem_types, "problem type")
        self._unique(dataset.concepts, "concept")
        self._unique(dataset.learning_outcomes, "learning outcome")
        chapter_codes = {item.code for item in dataset.chapters}
        topic_codes = {item.code for item in dataset.topics}
        problem_codes = {item.code for item in dataset.problem_types}
        concept_codes = {item.code for item in dataset.concepts}
        outcome_codes = {item.code for item in dataset.learning_outcomes}
        self._require_refs(
            {item.chapter_code for item in dataset.topics}, chapter_codes, "topic chapter"
        )
        self._require_refs(
            {item.topic_code for item in dataset.problem_types}, topic_codes, "problem type topic"
        )
        for relation in dataset.concept_relations:
            if relation.relation_type == RelationType.PART_OF:
                raise ApplicationError(
                    422,
                    "CURRICULUM_DATASET_INVALID",
                    "PART_OF cannot represent curriculum hierarchy.",
                )
            if relation.source_code == relation.target_code:
                raise ApplicationError(
                    422, "CURRICULUM_DATASET_INVALID", "Concept relation cannot be self-referential."
                )
        self._require_refs(
            {item.source_code for item in dataset.concept_relations}
            | {item.target_code for item in dataset.concept_relations},
            concept_codes,
            "concept relation",
        )
        self._require_refs(
            {item.problem_type_code for item in dataset.problem_type_concepts},
            problem_codes,
            "problem type concept",
        )
        self._require_refs(
            {item.concept_code for item in dataset.problem_type_concepts},
            concept_codes,
            "problem type concept",
        )
        self._require_refs(
            {item.problem_type_code for item in dataset.problem_type_outcomes},
            problem_codes,
            "problem type outcome",
        )
        self._require_refs(
            {item.learning_outcome_code for item in dataset.problem_type_outcomes},
            outcome_codes,
            "problem type outcome",
        )
        self._validate_graph(dataset.concept_relations, concept_codes)

    @staticmethod
    def _validate_graph(
        relations: list[ConceptRelationRecord], concept_codes: set[str]
    ) -> None:
        outgoing: dict[str, list[str]] = {code: [] for code in concept_codes}
        for relation in relations:
            if relation.relation_type == RelationType.PREREQUISITE:
                outgoing[relation.source_code].append(relation.target_code)
        state: dict[str, int] = {code: 0 for code in concept_codes}

        def visit(code: str) -> None:
            if state[code] == 1:
                raise ApplicationError(
                    422, "CURRICULUM_GRAPH_CYCLE", "Concept prerequisite graph contains a cycle."
                )
            if state[code] == 2:
                return
            state[code] = 1
            for target in outgoing[code]:
                visit(target)
            state[code] = 2

        for code in sorted(concept_codes):
            visit(code)

    def _upsert(
        self,
        model,
        entity_id: UUID,
        values: dict[str, object],
        entity: str,
        created: Counter[str],
        updated: Counter[str],
        unchanged: Counter[str],
    ):
        record = self.session.get(model, entity_id)
        if record is None:
            record = model(id=entity_id, **values)
            self.session.add(record)
            created[entity] += 1
        elif self._reconcile(record, values):
            updated[entity] += 1
        else:
            unchanged[entity] += 1
        self.session.flush()
        return record

    def _upsert_composite(
        self,
        model,
        key: tuple[UUID, UUID],
        values: dict[str, object],
        entity: str,
        created: Counter[str],
        updated: Counter[str],
        unchanged: Counter[str],
    ) -> None:
        record = self.session.get(model, key)
        if record is None:
            self.session.add(model(**values))
            created[entity] += 1
        elif self._reconcile(record, values):
            updated[entity] += 1
        else:
            unchanged[entity] += 1
        self.session.flush()

    @staticmethod
    def _reconcile(record: object, values: dict[str, object]) -> bool:
        changed = False
        for name, value in values.items():
            if getattr(record, name) != value:
                setattr(record, name, value)
                changed = True
        return changed

    def _entity_id(self, dataset: LoadedCurriculumDataset, entity: str, code: str) -> UUID:
        if dataset.manifest.legacy_identity_compatible and entity in {
            "subject", "concept", "concept-relation"
        }:
            return stable_id(entity, code)
        version = dataset.manifest.curriculum_version_code
        return stable_id(entity, f"{dataset.manifest.curriculum_code}:{version}:{code}")

    def _history_statement(self, dataset: LoadedCurriculumDataset):
        return select(CurriculumImportHistory.id).where(
            CurriculumImportHistory.dataset_code == dataset.manifest.dataset_code,
            CurriculumImportHistory.dataset_version == dataset.manifest.dataset_version,
            CurriculumImportHistory.content_hash == dataset.content_hash,
        )

    def _lock(self) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(
                select(func.pg_advisory_xact_lock(func.hashtext("edums:curriculum-import")))
            )

    @staticmethod
    def _list(model: type[T], value: object) -> list[T]:
        return TypeAdapter(list[model]).validate_python(value)  # type: ignore[valid-type]

    @staticmethod
    def _unique(records: list[ImportRecord], label: str) -> None:
        codes = [record.code for record in records]
        if len(codes) != len(set(codes)):
            raise ApplicationError(
                422, "CURRICULUM_DUPLICATE_CODE", f"Duplicate {label} code in dataset."
            )

    @staticmethod
    def _require_refs(references: set[str], available: set[str], label: str) -> None:
        missing = sorted(references - available)
        if missing:
            raise ApplicationError(
                422,
                "CURRICULUM_REFERENCE_NOT_FOUND",
                f"Missing {label} reference(s): {', '.join(missing)}.",
            )

    @staticmethod
    def _content_hash(manifest: DatasetManifest, files: dict[str, object]) -> str:
        payload = {"manifest": manifest.model_dump(mode="json"), **files}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
