from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.models import (
    Chapter,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    ProblemTypeLearningOutcome,
    Topic,
)
from app.subjects.models import Subject


DEVELOPMENT_TREE_DATASET = "MATH_G12_GDPT2018_DEVELOPMENT_FULL_TREE_V0_1"
DEVELOPMENT_TREE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "fixtures"
    / "curriculum"
    / "math_g12_full_tree_v0_1"
)
DEVELOPMENT_TREE_EXPECTED_COUNTS = {
    "chapters": 6,
    "topics": 25,
    "problem_types": 75,
    "concepts": 89,
    "learning_outcomes": 34,
    "concept_relations": 93,
    "problem_type_concepts": 200,
    "problem_type_learning_outcomes": 82,
}


class DevelopmentTreeActivationReport(BaseModel):
    dataset_code: str
    content_hash: str
    active_chapters: int
    active_topics: int
    active_problem_types: int
    concepts: int
    learning_outcomes: int
    deactivated_legacy_problem_types: list[str]
    removed_stale_mappings: int


class DevelopmentTreeActivationService:
    """Install the complete Math 12 tree in development/test without publishing questions."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.importer = CurriculumImportService(
            session, data_root=DEVELOPMENT_TREE_ROOT.parent
        )

    def preview(self):
        preview = self.importer.preview(DEVELOPMENT_TREE_DATASET)
        for name, expected in DEVELOPMENT_TREE_EXPECTED_COUNTS.items():
            if preview.counts.get(name) != expected:
                raise ApplicationError(
                    422,
                    "DEVELOPMENT_TREE_COUNT_MISMATCH",
                    f"Expected {expected} {name}, found {preview.counts.get(name)}.",
                )
        return preview

    def activate(self, *, app_env: str) -> DevelopmentTreeActivationReport:
        if app_env == "production":
            raise ApplicationError(
                403,
                "DEVELOPMENT_TREE_PRODUCTION_FORBIDDEN",
                "The development curriculum projection cannot be imported in production.",
            )

        target_codes = self._target_problem_type_codes()
        self.preview()
        try:
            result = self.importer.import_dataset(
                DEVELOPMENT_TREE_DATASET, commit=False
            )
            subject = self.session.scalar(
                select(Subject).where(Subject.code == "MATH_G12")
            )
            if subject is None:
                raise ApplicationError(
                    500,
                    "DEVELOPMENT_TREE_SUBJECT_MISSING",
                    "MATH_G12 was not created by the curriculum import.",
                )

            problem_types = list(
                self.session.scalars(
                    select(ProblemType)
                    .join(Topic, Topic.id == ProblemType.topic_id)
                    .join(Chapter, Chapter.id == Topic.chapter_id)
                    .where(Chapter.subject_id == subject.id)
                )
            )
            deactivated: list[str] = []
            for problem_type in problem_types:
                should_be_active = problem_type.code in target_codes
                if problem_type.is_active and not should_be_active:
                    deactivated.append(problem_type.code)
                problem_type.is_active = should_be_active

            removed_stale_mappings = self._reconcile_mappings(subject.id)
            self.session.flush()
            report = self._report(
                result.content_hash,
                subject.id,
                deactivated,
                removed_stale_mappings,
            )
            self._validate_report(report)
            self.session.commit()
            return report
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _target_problem_type_codes() -> set[str]:
        path = DEVELOPMENT_TREE_ROOT / "problem_types.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        return {str(row["code"]).strip().upper() for row in rows}

    @staticmethod
    def _target_codes(file_name: str) -> set[str]:
        rows = json.loads(
            (DEVELOPMENT_TREE_ROOT / file_name).read_text(encoding="utf-8")
        )
        return {str(row["code"]).strip().upper() for row in rows}

    def _report(
        self,
        content_hash: str,
        subject_id,
        deactivated: list[str],
        removed_stale_mappings: int,
    ) -> DevelopmentTreeActivationReport:
        active_problem_types = list(
            self.session.scalars(
                select(ProblemType)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(
                    Chapter.subject_id == subject_id,
                    ProblemType.is_active.is_(True),
                )
            )
        )
        active_topic_ids = {row.topic_id for row in active_problem_types}
        active_topics = list(
            self.session.scalars(select(Topic).where(Topic.id.in_(active_topic_ids)))
        )
        active_chapter_ids = {row.chapter_id for row in active_topics}
        target_concepts = self._target_codes("concepts.json")
        concept_count = len(
            list(
                self.session.scalars(
                    select(Concept).where(
                        Concept.subject_id == subject_id,
                        Concept.code.in_(target_concepts),
                    )
                )
            )
        )
        target_outcomes = self._target_codes("learning_outcomes.json")
        outcome_count = len(
            list(
                self.session.scalars(
                    select(LearningOutcome).where(
                        LearningOutcome.subject_id == subject_id,
                        LearningOutcome.code.in_(target_outcomes),
                    )
                )
            )
        )
        return DevelopmentTreeActivationReport(
            dataset_code=DEVELOPMENT_TREE_DATASET,
            content_hash=content_hash,
            active_chapters=len(active_chapter_ids),
            active_topics=len(active_topic_ids),
            active_problem_types=len(active_problem_types),
            concepts=concept_count,
            learning_outcomes=outcome_count,
            deactivated_legacy_problem_types=sorted(deactivated),
            removed_stale_mappings=removed_stale_mappings,
        )

    def _reconcile_mappings(self, subject_id) -> int:
        problem_types = {
            row.code: row
            for row in self.session.scalars(
                select(ProblemType)
                .join(Topic, Topic.id == ProblemType.topic_id)
                .join(Chapter, Chapter.id == Topic.chapter_id)
                .where(Chapter.subject_id == subject_id)
            )
        }
        concepts = {
            row.code: row
            for row in self.session.scalars(
                select(Concept).where(Concept.subject_id == subject_id)
            )
        }
        outcomes = {
            row.code: row
            for row in self.session.scalars(
                select(LearningOutcome).where(LearningOutcome.subject_id == subject_id)
            )
        }

        ptc_rows = json.loads(
            (DEVELOPMENT_TREE_ROOT / "problem_type_concepts.json").read_text(
                encoding="utf-8"
            )
        )
        target_ptc = {
            (problem_types[row["problem_type_code"]].id, concepts[row["concept_code"]].id)
            for row in ptc_rows
        }
        target_problem_ids = {
            problem_types[code].id for code in self._target_problem_type_codes()
        }
        removed = 0
        for row in self.session.scalars(
            select(ProblemTypeConcept).where(
                ProblemTypeConcept.problem_type_id.in_(target_problem_ids)
            )
        ):
            if (row.problem_type_id, row.concept_id) not in target_ptc:
                self.session.delete(row)
                removed += 1

        ptlo_rows = json.loads(
            (DEVELOPMENT_TREE_ROOT / "problem_type_learning_outcomes.json").read_text(
                encoding="utf-8"
            )
        )
        target_ptlo = {
            (
                problem_types[row["problem_type_code"]].id,
                outcomes[row["learning_outcome_code"]].id,
            )
            for row in ptlo_rows
        }
        for row in self.session.scalars(
            select(ProblemTypeLearningOutcome).where(
                ProblemTypeLearningOutcome.problem_type_id.in_(target_problem_ids)
            )
        ):
            if (row.problem_type_id, row.learning_outcome_id) not in target_ptlo:
                self.session.delete(row)
                removed += 1

        relation_rows = json.loads(
            (DEVELOPMENT_TREE_ROOT / "concept_relations.json").read_text(
                encoding="utf-8"
            )
        )
        target_relations = set()
        for row in relation_rows:
            source_id = concepts[row["source_code"]].id
            target_id = concepts[row["target_code"]].id
            relation_type = RelationType(row["relation_type"])
            if relation_type == RelationType.RELATED_TO and source_id > target_id:
                source_id, target_id = target_id, source_id
            target_relations.add((source_id, target_id, relation_type))
        subject_concept_ids = {row.id for row in concepts.values()}
        for row in self.session.scalars(select(ConceptRelation)):
            if (
                row.source_concept_id in subject_concept_ids
                and row.target_concept_id in subject_concept_ids
                and (row.source_concept_id, row.target_concept_id, row.relation_type)
                not in target_relations
            ):
                self.session.delete(row)
                removed += 1
        return removed

    @staticmethod
    def _validate_report(report: DevelopmentTreeActivationReport) -> None:
        actual = {
            "chapters": report.active_chapters,
            "topics": report.active_topics,
            "problem_types": report.active_problem_types,
            "concepts": report.concepts,
            "learning_outcomes": report.learning_outcomes,
        }
        for name, count in actual.items():
            expected = DEVELOPMENT_TREE_EXPECTED_COUNTS[name]
            if count != expected:
                raise ApplicationError(
                    409,
                    "DEVELOPMENT_TREE_ACTIVATION_MISMATCH",
                    f"Expected {expected} active {name}, found {count}.",
                )
