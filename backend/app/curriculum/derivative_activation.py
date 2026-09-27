from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.derivative_candidate import (
    DEFAULT_CANONICAL_CURRICULUM_PATH,
    DEFAULT_PRODUCTION_BRIDGE_ROOT,
    DerivativeCurriculumCandidate,
    DerivativeCurriculumCandidateValidator,
)
from app.curriculum.import_schemas import DatasetManifest
from app.curriculum.import_service import (
    CurriculumImportService,
    LoadedCurriculumDataset,
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


DATASET_CODE = "MATH_G12_GDPT2018_CORE"
DATASET_VERSION = "1.2.0"
CURRICULUM_CODE = "GDPT2018"
CURRICULUM_VERSION_CODE = "GDPT2018_2018"
SUBJECT_CODE = "MATH_G12"
DEFAULT_FINGERPRINT_CONTRACT_PATH = (
    DEFAULT_PRODUCTION_BRIDGE_ROOT / "taxonomy_fingerprint_contract.json"
)


@dataclass(frozen=True, slots=True, order=True)
class DerivativeTaxonomyActivationIssue:
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class DerivativeTaxonomyActivationReport:
    status: str
    candidate_fingerprint: str
    database_fingerprint: str
    expected_import_content_hash: str
    candidate_counts: dict[str, int]
    database_counts: dict[str, int]
    history_status: str
    errors: tuple[DerivativeTaxonomyActivationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "candidate_fingerprint": self.candidate_fingerprint,
            "database_fingerprint": self.database_fingerprint,
            "expected_import_content_hash": self.expected_import_content_hash,
            "candidate_counts": self.candidate_counts,
            "database_counts": self.database_counts,
            "history_status": self.history_status,
            "errors": [asdict(error) for error in self.errors],
        }


class DerivativeTaxonomyActivationValidator:
    """Prove that the full reviewed derivative taxonomy was imported canonically."""

    def __init__(
        self,
        session: Session,
        fingerprint_contract_path: Path = DEFAULT_FINGERPRINT_CONTRACT_PATH,
    ) -> None:
        self.session = session
        self.fingerprint_contract_path = fingerprint_contract_path

    @classmethod
    def build_import_dataset(
        cls,
        canonical_path: Path = DEFAULT_CANONICAL_CURRICULUM_PATH,
    ) -> LoadedCurriculumDataset:
        report = DerivativeCurriculumCandidateValidator().validate(
            canonical_path=canonical_path
        )
        if not report.is_valid or report.candidate is None:
            details = ", ".join(error.code for error in report.errors)
            raise ValueError(f"Derivative curriculum candidate is invalid: {details}")
        candidate = report.candidate
        base_manifest = json.loads(
            (canonical_path / "manifest.json").read_text(encoding="utf-8")
        )
        manifest = DatasetManifest.model_validate(
            {
                **base_manifest,
                "dataset_code": DATASET_CODE,
                "dataset_version": DATASET_VERSION,
                "curriculum_code": CURRICULUM_CODE,
                "curriculum_version_code": CURRICULUM_VERSION_CODE,
                "subject_code": SUBJECT_CODE,
                "verified_at": None,
                "legacy_identity_compatible": True,
            }
        )
        files = cls._candidate_files(candidate)
        return LoadedCurriculumDataset(
            path=canonical_path,
            manifest=manifest,
            subject=candidate.subject,
            chapters=list(candidate.chapters),
            topics=list(candidate.topics),
            problem_types=list(candidate.problem_types),
            concepts=list(candidate.concepts),
            learning_outcomes=list(candidate.learning_outcomes),
            concept_relations=list(candidate.concept_relations),
            problem_type_concepts=list(candidate.problem_type_concepts),
            problem_type_outcomes=list(candidate.problem_type_learning_outcomes),
            content_hash=CurriculumImportService._content_hash(manifest, files),
        )

    @classmethod
    def write_import_dataset(
        cls,
        data_root: Path,
        canonical_path: Path = DEFAULT_CANONICAL_CURRICULUM_PATH,
    ) -> LoadedCurriculumDataset:
        """Write the deterministic candidate to a caller-owned temporary import root."""
        dataset = cls.build_import_dataset(canonical_path)
        destination = data_root / "math_g12_derivative_candidate"
        destination.mkdir(parents=True, exist_ok=True)
        documents = {
            "manifest": dataset.manifest.model_dump(mode="json"),
            **cls._candidate_files_from_dataset(dataset),
        }
        for name, value in documents.items():
            (destination / f"{name}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return dataset

    def validate(self) -> DerivativeTaxonomyActivationReport:
        errors: list[DerivativeTaxonomyActivationIssue] = []
        try:
            dataset = self.build_import_dataset()
            contract = json.loads(
                self.fingerprint_contract_path.read_text(encoding="utf-8-sig")
            )
            if not isinstance(contract.get("payload"), dict):
                raise ValueError("Fingerprint contract payload must be an object.")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            issue = DerivativeTaxonomyActivationIssue(
                "CANDIDATE_INVALID", "candidate", str(error)
            )
            return DerivativeTaxonomyActivationReport(
                status="FAIL",
                candidate_fingerprint="",
                database_fingerprint="",
                expected_import_content_hash="",
                candidate_counts={},
                database_counts={},
                history_status="NOT_CHECKED",
                errors=(issue,),
            )

        candidate_payload = self._apply_contract(
            self._candidate_fingerprint_payload(dataset), contract
        )
        candidate_fingerprint = self._fingerprint(candidate_payload)
        identity = self._resolve_identity(errors)
        database_payload, database_counts, ids = self._database_payload(identity)
        database_payload = self._apply_contract(database_payload, contract)
        database_fingerprint = self._fingerprint(database_payload)

        if dataset.counts != database_counts:
            self._add(
                errors,
                "TAXONOMY_COUNTS_MISMATCH",
                "database",
                f"Expected {dataset.counts}; found {database_counts}.",
            )
        if candidate_fingerprint != database_fingerprint:
            self._add(
                errors,
                "TAXONOMY_FINGERPRINT_MISMATCH",
                "database",
                "Database semantic graph differs from the reviewed candidate.",
            )

        self._validate_stable_ids(dataset, identity, ids, errors)
        history_status = self._validate_history(dataset, identity, errors)
        ordered_errors = tuple(sorted(set(errors)))
        return DerivativeTaxonomyActivationReport(
            status="PASS" if not ordered_errors else "FAIL",
            candidate_fingerprint=candidate_fingerprint,
            database_fingerprint=database_fingerprint,
            expected_import_content_hash=dataset.content_hash,
            candidate_counts=dict(dataset.counts),
            database_counts=database_counts,
            history_status=history_status,
            errors=ordered_errors,
        )

    def _resolve_identity(
        self,
        errors: list[DerivativeTaxonomyActivationIssue],
    ) -> tuple[Curriculum, CurriculumVersion, Subject] | None:
        rows = self.session.execute(
            select(Curriculum, CurriculumVersion, Subject)
            .join(CurriculumVersion, CurriculumVersion.curriculum_id == Curriculum.id)
            .join(Subject, Subject.curriculum_version_id == CurriculumVersion.id)
            .where(
                Curriculum.code == CURRICULUM_CODE,
                CurriculumVersion.code == CURRICULUM_VERSION_CODE,
                CurriculumVersion.is_active.is_(True),
                Subject.code == SUBJECT_CODE,
            )
        ).all()
        if len(rows) != 1:
            self._add(
                errors,
                "DATASET_IDENTITY_NOT_ACTIVE",
                "dataset_identity",
                "Expected exactly one active GDPT2018/GDPT2018_2018/MATH_G12 identity.",
            )
            return None
        return rows[0]

    def _database_payload(
        self,
        identity: tuple[Curriculum, CurriculumVersion, Subject] | None,
    ) -> tuple[dict[str, Any], dict[str, int], dict[str, dict[str, UUID]]]:
        empty_counts = {
            "subjects": 0,
            "chapters": 0,
            "topics": 0,
            "problem_types": 0,
            "concepts": 0,
            "learning_outcomes": 0,
            "concept_relations": 0,
            "problem_type_concepts": 0,
            "problem_type_learning_outcomes": 0,
        }
        empty_ids: dict[str, dict[str, UUID]] = {
            name: {} for name in (
                "chapters", "topics", "problem_types", "concepts",
                "learning_outcomes", "concept_relations",
            )
        }
        if identity is None:
            payload = self._empty_payload()
            return payload, empty_counts, empty_ids
        _, _, subject = identity

        chapter_rows = list(self.session.scalars(
            select(Chapter).where(Chapter.subject_id == subject.id)
        ))
        chapter_codes = {row.id: row.code for row in chapter_rows}
        topic_rows = self.session.execute(
            select(Topic, Chapter.code)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.subject_id == subject.id)
        ).all()
        topic_codes = {row.id: row.code for row, _ in topic_rows}
        problem_rows = self.session.execute(
            select(ProblemType, Topic.code)
            .join(Topic, ProblemType.topic_id == Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.subject_id == subject.id)
        ).all()
        problem_codes = {row.id: row.code for row, _ in problem_rows}
        concept_rows = list(self.session.scalars(
            select(Concept).where(Concept.subject_id == subject.id)
        ))
        concept_codes = {row.id: row.code for row in concept_rows}
        outcome_rows = list(self.session.scalars(
            select(LearningOutcome).where(LearningOutcome.subject_id == subject.id)
        ))
        outcome_codes = {row.id: row.code for row in outcome_rows}

        source = aliased(Concept)
        target = aliased(Concept)
        relation_rows = self.session.execute(
            select(ConceptRelation, source.code, target.code)
            .join(source, ConceptRelation.source_concept_id == source.id)
            .join(target, ConceptRelation.target_concept_id == target.id)
            .where(source.subject_id == subject.id, target.subject_id == subject.id)
        ).all()
        problem_concept_rows = self.session.execute(
            select(ProblemTypeConcept, ProblemType.code, Concept.code)
            .join(ProblemType, ProblemTypeConcept.problem_type_id == ProblemType.id)
            .join(Topic, ProblemType.topic_id == Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .join(Concept, ProblemTypeConcept.concept_id == Concept.id)
            .where(Chapter.subject_id == subject.id, Concept.subject_id == subject.id)
        ).all()
        problem_outcome_rows = self.session.execute(
            select(ProblemTypeLearningOutcome, ProblemType.code, LearningOutcome.code)
            .join(ProblemType, ProblemTypeLearningOutcome.problem_type_id == ProblemType.id)
            .join(Topic, ProblemType.topic_id == Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .join(
                LearningOutcome,
                ProblemTypeLearningOutcome.learning_outcome_id == LearningOutcome.id,
            )
            .where(
                Chapter.subject_id == subject.id,
                LearningOutcome.subject_id == subject.id,
            )
        ).all()

        payload = {
            "dataset_identity": self._dataset_identity(),
            "subject": self._subject_payload(subject),
            "chapters": self._sort([
                self._fields(row, "code", "name", "description", "order_index")
                for row in chapter_rows
            ]),
            "topics": self._sort([
                {
                    "chapter_code": parent_code,
                    **self._fields(row, "code", "name", "description", "order_index"),
                }
                for row, parent_code in topic_rows
            ]),
            "problem_types": self._sort([
                {
                    "topic_code": parent_code,
                    **self._fields(
                        row, "code", "name", "description", "order_index",
                        "default_difficulty", "is_active",
                    ),
                }
                for row, parent_code in problem_rows
            ]),
            "concepts": self._sort([
                self._fields(
                    row, "code", "name", "description", "grade_level", "order_index"
                )
                for row in concept_rows
            ]),
            "learning_outcomes": self._sort([
                self._fields(
                    row, "code", "description", "grade_level", "order_index",
                    "source_reference",
                )
                for row in outcome_rows
            ]),
            "concept_relations": self._sort([
                {
                    "source_code": source_code,
                    "target_code": target_code,
                    "relation_type": relation.relation_type.value,
                }
                for relation, source_code, target_code in relation_rows
            ]),
            "problem_type_concepts": self._sort([
                {
                    "problem_type_code": problem_code,
                    "concept_code": concept_code,
                    "weight": link.weight,
                    "is_primary": link.is_primary,
                }
                for link, problem_code, concept_code in problem_concept_rows
            ]),
            "problem_type_learning_outcomes": self._sort([
                {
                    "problem_type_code": problem_code,
                    "learning_outcome_code": outcome_code,
                    "weight": link.weight,
                }
                for link, problem_code, outcome_code in problem_outcome_rows
            ]),
        }
        counts = {
            "subjects": 1,
            "chapters": len(chapter_rows),
            "topics": len(topic_rows),
            "problem_types": len(problem_rows),
            "concepts": len(concept_rows),
            "learning_outcomes": len(outcome_rows),
            "concept_relations": len(relation_rows),
            "problem_type_concepts": len(problem_concept_rows),
            "problem_type_learning_outcomes": len(problem_outcome_rows),
        }
        ids = {
            "chapters": {row.code: row.id for row in chapter_rows},
            "topics": {row.code: row.id for row, _ in topic_rows},
            "problem_types": {row.code: row.id for row, _ in problem_rows},
            "concepts": {row.code: row.id for row in concept_rows},
            "learning_outcomes": {row.code: row.id for row in outcome_rows},
            "concept_relations": {
                f"{source_code}>{target_code}:{relation.relation_type.value}": relation.id
                for relation, source_code, target_code in relation_rows
            },
        }
        # Keep the maps built above explicit: they document the candidate scope and make
        # accidental cross-subject joins visible during maintenance.
        assert set(chapter_codes.values()) == set(ids["chapters"])
        assert set(topic_codes.values()) == set(ids["topics"])
        assert set(problem_codes.values()) == set(ids["problem_types"])
        assert set(concept_codes.values()) == set(ids["concepts"])
        assert set(outcome_codes.values()) == set(ids["learning_outcomes"])
        return payload, counts, ids

    def _validate_stable_ids(
        self,
        dataset: LoadedCurriculumDataset,
        identity: tuple[Curriculum, CurriculumVersion, Subject] | None,
        ids: dict[str, dict[str, UUID]],
        errors: list[DerivativeTaxonomyActivationIssue],
    ) -> None:
        if identity is None:
            return
        curriculum, version, subject = identity
        importer = CurriculumImportService(self.session)
        expected_identity = {
            "curriculum": stable_id("curriculum", CURRICULUM_CODE),
            "curriculum_version": stable_id(
                "curriculum-version", f"{CURRICULUM_CODE}:{CURRICULUM_VERSION_CODE}"
            ),
            "subject": importer._entity_id(dataset, "subject", SUBJECT_CODE),
        }
        actual_identity = {
            "curriculum": curriculum.id,
            "curriculum_version": version.id,
            "subject": subject.id,
        }
        for name, expected in expected_identity.items():
            if actual_identity[name] != expected:
                self._add(
                    errors, "STABLE_ID_MISMATCH", name,
                    f"{name} does not use the canonical importer identity.",
                )

        specs: list[tuple[str, str, list[Any]]] = [
            ("chapters", "chapter", dataset.chapters),
            ("topics", "topic", dataset.topics),
            ("problem_types", "problem-type", dataset.problem_types),
            ("concepts", "concept", dataset.concepts),
            ("learning_outcomes", "learning-outcome", dataset.learning_outcomes),
        ]
        for collection, entity, records in specs:
            for record in records:
                key = f"{SUBJECT_CODE}:{record.code}"
                expected = importer._entity_id(dataset, entity, key)
                if ids[collection].get(record.code) != expected:
                    self._add(
                        errors, "STABLE_ID_MISMATCH", f"{collection}.{record.code}",
                        "Row does not use the canonical importer identity.",
                    )
        for relation in dataset.concept_relations:
            source_code, target_code = self._canonical_relation_codes(
                dataset, relation.source_code, relation.target_code, relation.relation_type
            )
            key = f"{source_code}>{target_code}:{relation.relation_type.value}"
            expected = importer._entity_id(dataset, "concept-relation", key)
            if ids["concept_relations"].get(key) != expected:
                self._add(
                    errors, "STABLE_ID_MISMATCH", f"concept_relations.{key}",
                    "Relation does not use the canonical importer identity.",
                )

    def _validate_history(
        self,
        dataset: LoadedCurriculumDataset,
        identity: tuple[Curriculum, CurriculumVersion, Subject] | None,
        errors: list[DerivativeTaxonomyActivationIssue],
    ) -> str:
        rows = list(self.session.scalars(
            select(CurriculumImportHistory).where(
                CurriculumImportHistory.dataset_code == DATASET_CODE
            )
        ))
        if not rows:
            self._add(
                errors, "IMPORT_HISTORY_MISSING", "curriculum_import_history",
                "Canonical candidate has no CurriculumImportHistory proof.",
            )
            return "MISSING"
        version_rows = [row for row in rows if row.dataset_version == DATASET_VERSION]
        if not version_rows:
            self._add(
                errors, "IMPORT_HISTORY_VERSION_MISMATCH", "curriculum_import_history",
                f"Expected dataset version {DATASET_VERSION}.",
            )
            return "VERSION_MISMATCH"
        hash_rows = [row for row in version_rows if row.content_hash == dataset.content_hash]
        if not hash_rows:
            self._add(
                errors, "IMPORT_HISTORY_HASH_MISMATCH", "curriculum_import_history",
                "Import history content hash differs from the candidate payload.",
            )
            return "HASH_MISMATCH"
        expected_version_id = identity[1].id if identity is not None else None
        exact = [
            row for row in hash_rows
            if expected_version_id is not None
            and row.curriculum_version_id == expected_version_id
        ]
        if len(exact) != 1:
            self._add(
                errors, "IMPORT_HISTORY_VERSION_ID_MISMATCH",
                "curriculum_import_history",
                "Import history does not reference the active curriculum version.",
            )
            return "VERSION_ID_MISMATCH"
        return "MATCHED"

    @classmethod
    def _candidate_fingerprint_payload(
        cls, dataset: LoadedCurriculumDataset
    ) -> dict[str, Any]:
        relation_rows = []
        for relation in dataset.concept_relations:
            source_code, target_code = cls._canonical_relation_codes(
                dataset, relation.source_code, relation.target_code, relation.relation_type
            )
            relation_rows.append({
                "source_code": source_code,
                "target_code": target_code,
                "relation_type": relation.relation_type.value,
            })
        return {
            "dataset_identity": cls._dataset_identity(),
            "subject": dataset.subject.model_dump(mode="json"),
            "chapters": cls._sort([
                item.model_dump(mode="json") for item in dataset.chapters
            ]),
            "topics": cls._sort([
                item.model_dump(mode="json") for item in dataset.topics
            ]),
            "problem_types": cls._sort([
                item.model_dump(mode="json") for item in dataset.problem_types
            ]),
            "concepts": cls._sort([
                item.model_dump(mode="json") for item in dataset.concepts
            ]),
            "learning_outcomes": cls._sort([
                item.model_dump(mode="json") for item in dataset.learning_outcomes
            ]),
            "concept_relations": cls._sort(relation_rows),
            "problem_type_concepts": cls._sort([
                item.model_dump(mode="json") for item in dataset.problem_type_concepts
            ]),
            "problem_type_learning_outcomes": cls._sort([
                item.model_dump(mode="json") for item in dataset.problem_type_outcomes
            ]),
        }

    @staticmethod
    def _canonical_relation_codes(
        dataset: LoadedCurriculumDataset,
        source_code: str,
        target_code: str,
        relation_type: RelationType,
    ) -> tuple[str, str]:
        if relation_type != RelationType.RELATED_TO:
            return source_code, target_code
        importer = CurriculumImportService.__new__(CurriculumImportService)
        source_id = CurriculumImportService._entity_id(
            importer, dataset, "concept", f"{SUBJECT_CODE}:{source_code}"
        )
        target_id = CurriculumImportService._entity_id(
            importer, dataset, "concept", f"{SUBJECT_CODE}:{target_code}"
        )
        return (
            (target_code, source_code)
            if source_id > target_id
            else (source_code, target_code)
        )

    @staticmethod
    def _candidate_files(candidate: DerivativeCurriculumCandidate) -> dict[str, object]:
        return {
            "subject": candidate.subject.model_dump(mode="json"),
            "chapters": [item.model_dump(mode="json") for item in candidate.chapters],
            "topics": [item.model_dump(mode="json") for item in candidate.topics],
            "problem_types": [
                item.model_dump(mode="json") for item in candidate.problem_types
            ],
            "concepts": [item.model_dump(mode="json") for item in candidate.concepts],
            "learning_outcomes": [
                item.model_dump(mode="json") for item in candidate.learning_outcomes
            ],
            "concept_relations": [
                item.model_dump(mode="json") for item in candidate.concept_relations
            ],
            "problem_type_concepts": [
                item.model_dump(mode="json") for item in candidate.problem_type_concepts
            ],
            "problem_type_learning_outcomes": [
                item.model_dump(mode="json")
                for item in candidate.problem_type_learning_outcomes
            ],
        }

    @staticmethod
    def _candidate_files_from_dataset(
        dataset: LoadedCurriculumDataset,
    ) -> dict[str, object]:
        return {
            "subject": dataset.subject.model_dump(mode="json"),
            "chapters": [item.model_dump(mode="json") for item in dataset.chapters],
            "topics": [item.model_dump(mode="json") for item in dataset.topics],
            "problem_types": [item.model_dump(mode="json") for item in dataset.problem_types],
            "concepts": [item.model_dump(mode="json") for item in dataset.concepts],
            "learning_outcomes": [item.model_dump(mode="json") for item in dataset.learning_outcomes],
            "concept_relations": [item.model_dump(mode="json") for item in dataset.concept_relations],
            "problem_type_concepts": [item.model_dump(mode="json") for item in dataset.problem_type_concepts],
            "problem_type_learning_outcomes": [item.model_dump(mode="json") for item in dataset.problem_type_outcomes],
        }

    @staticmethod
    def _dataset_identity() -> dict[str, str]:
        return {
            "dataset_code": DATASET_CODE,
            "dataset_version": DATASET_VERSION,
            "curriculum_code": CURRICULUM_CODE,
            "curriculum_version_code": CURRICULUM_VERSION_CODE,
            "subject_code": SUBJECT_CODE,
        }

    @staticmethod
    def _subject_payload(subject: Subject) -> dict[str, Any]:
        return DerivativeTaxonomyActivationValidator._fields(
            subject, "code", "name", "grade_level", "description", "order_index"
        )

    @classmethod
    def _empty_payload(cls) -> dict[str, Any]:
        return {
            "dataset_identity": cls._dataset_identity(),
            "subject": {},
            "chapters": [],
            "topics": [],
            "problem_types": [],
            "concepts": [],
            "learning_outcomes": [],
            "concept_relations": [],
            "problem_type_concepts": [],
            "problem_type_learning_outcomes": [],
        }

    @staticmethod
    def _fields(record: object, *names: str) -> dict[str, Any]:
        return {name: getattr(record, name) for name in names}

    @staticmethod
    def _sort(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda row: json.dumps(
                row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        value = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _apply_contract(
        cls,
        payload: dict[str, Any],
        contract: dict[str, Any],
    ) -> dict[str, Any]:
        projected: dict[str, Any] = {}
        for section, raw_fields in contract["payload"].items():
            if not isinstance(raw_fields, list) or not all(
                isinstance(field, str) for field in raw_fields
            ):
                raise ValueError(
                    f"Fingerprint contract fields for {section} must be strings."
                )
            fields = list(raw_fields)
            value = payload.get(section)
            if isinstance(value, list):
                projected[section] = cls._sort([
                    {field: row.get(field) for field in fields} for row in value
                ])
            elif isinstance(value, dict):
                projected[section] = {field: value.get(field) for field in fields}
            else:
                raise ValueError(
                    f"Fingerprint payload section {section} is missing or invalid."
                )
        return projected

    @staticmethod
    def _add(
        errors: list[DerivativeTaxonomyActivationIssue],
        code: str,
        location: str,
        message: str,
    ) -> None:
        errors.append(DerivativeTaxonomyActivationIssue(code, location, message))
