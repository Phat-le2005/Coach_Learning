"""Resolve every learning-evidence source into one diagnostic context."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.assignments.models import (
    AssignmentMaterialItem,
    AssignmentStudentQuestion,
    StudentAssignmentMaterialItem,
)
from app.core.exceptions import ApplicationError
from app.concepts.models import Concept
from app.curriculum.models import Chapter, ProblemType, Topic
from app.learning_evidence.models import (
    LearningEvidenceEvent,
    LearningEvidenceSourceKind,
)
from app.practice.models import QuestionAttempt
from app.questions.models import Question


@dataclass(frozen=True, slots=True)
class DiagnosticEvidenceContext:
    evidence_event: LearningEvidenceEvent
    student_id: UUID
    subject_id: UUID
    concept_weights: dict[UUID, float]
    problem_type_weights: dict[UUID, float]
    primary_problem_type_id: UUID | None
    student_response: str | None
    content: str
    expected_answer: str | None
    explanation: str | None
    difficulty: float | None
    source_kind: LearningEvidenceSourceKind
    source_entity_id: UUID
    canonical_question: Question | None = None
    assignment_material_snapshot_id: UUID | None = None


class LearningEvidenceContextResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(self, event_id: UUID) -> DiagnosticEvidenceContext:
        event = self.session.scalar(
            select(LearningEvidenceEvent)
            .options(
                selectinload(LearningEvidenceEvent.concepts),
                selectinload(LearningEvidenceEvent.problem_types),
            )
            .where(LearningEvidenceEvent.id == event_id)
        )
        if event is None:
            raise ApplicationError(
                404, "LEARNING_EVIDENCE_NOT_FOUND", "Learning evidence was not found."
            )
        primary = [link.problem_type_id for link in event.problem_types if link.is_primary]
        if len(primary) > 1:
            raise ApplicationError(
                409,
                "EVIDENCE_MULTIPLE_PRIMARY_PROBLEM_TYPES",
                "Learning evidence contains multiple primary ProblemTypes.",
            )
        fallback = sorted(
            event.problem_types,
            key=lambda link: (-link.weight, str(link.problem_type_id)),
        )
        primary_id = primary[0] if primary else (
            fallback[0].problem_type_id if fallback else None
        )
        self._validate_mapping_subject(event)
        base = {
            "evidence_event": event,
            "student_id": event.student_id,
            "subject_id": event.subject_id,
            "concept_weights": {
                link.concept_id: link.weight for link in event.concepts
            },
            "problem_type_weights": {
                link.problem_type_id: link.weight for link in event.problem_types
            },
            "primary_problem_type_id": primary_id,
            "difficulty": event.difficulty,
            "source_kind": event.source_kind,
            "source_entity_id": event.source_entity_id,
        }
        if event.source_kind == LearningEvidenceSourceKind.PRACTICE_QUESTION:
            attempt = self.session.get(QuestionAttempt, event.source_entity_id)
            if attempt is None:
                raise self._source_missing()
            question = self.session.get(Question, attempt.question_id)
            if (
                question is None
                or attempt.student_id != event.student_id
                or question.subject_id != event.subject_id
            ):
                raise self._source_missing()
            return DiagnosticEvidenceContext(
                **base,
                student_response=attempt.student_answer,
                content=question.content,
                expected_answer=question.correct_answer,
                explanation=question.explanation,
                canonical_question=question,
            )
        if event.source_kind == LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION:
            item = self.session.get(AssignmentStudentQuestion, event.source_entity_id)
            if item is None:
                raise self._source_missing()
            question = self.session.get(Question, item.question_id)
            if (
                question is None
                or item.student_assignment.student_id != event.student_id
                or item.student_assignment.assignment.subject_id != event.subject_id
                or question.subject_id != event.subject_id
            ):
                raise self._source_missing()
            return DiagnosticEvidenceContext(
                **base,
                student_response=item.student_answer,
                content=question.content,
                expected_answer=question.correct_answer,
                explanation=question.explanation,
                canonical_question=question,
            )
        if event.source_kind == LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM:
            item = self.session.scalar(
                select(StudentAssignmentMaterialItem)
                .options(
                    selectinload(
                        StudentAssignmentMaterialItem.assignment_material_item
                    )
                )
                .where(StudentAssignmentMaterialItem.id == event.source_entity_id)
            )
            if (
                item is None
                or item.assignment_material_item is None
                or item.student_assignment.student_id != event.student_id
                or item.student_assignment.assignment.subject_id != event.subject_id
            ):
                raise self._source_missing()
            snapshot: AssignmentMaterialItem = item.assignment_material_item
            return DiagnosticEvidenceContext(
                **base,
                student_response=item.student_answer,
                content=snapshot.content or "",
                expected_answer=snapshot.correct_answer,
                explanation=snapshot.explanation,
                assignment_material_snapshot_id=snapshot.id,
            )
        raise ApplicationError(
            422, "UNSUPPORTED_EVIDENCE_SOURCE", "Unsupported learning evidence source."
        )

    @staticmethod
    def _source_missing() -> ApplicationError:
        return ApplicationError(
            409,
            "EVIDENCE_SOURCE_CONTEXT_MISSING",
            "The immutable source context for this evidence is unavailable.",
        )

    def _validate_mapping_subject(self, event: LearningEvidenceEvent) -> None:
        concept_ids = {link.concept_id for link in event.concepts}
        if concept_ids:
            resolved = set(
                self.session.scalars(
                    select(Concept.id).where(
                        Concept.id.in_(concept_ids),
                        Concept.subject_id == event.subject_id,
                    )
                )
            )
            if resolved != concept_ids:
                raise self._mapping_mismatch()
        problem_type_ids = {link.problem_type_id for link in event.problem_types}
        if problem_type_ids:
            resolved = set(
                self.session.scalars(
                    select(ProblemType.id)
                    .join(Topic, Topic.id == ProblemType.topic_id)
                    .join(Chapter, Chapter.id == Topic.chapter_id)
                    .where(
                        ProblemType.id.in_(problem_type_ids),
                        Chapter.subject_id == event.subject_id,
                    )
                )
            )
            if resolved != problem_type_ids:
                raise self._mapping_mismatch()

    @staticmethod
    def _mapping_mismatch() -> ApplicationError:
        return ApplicationError(
            409,
            "EVIDENCE_MAPPING_SUBJECT_MISMATCH",
            "Learning evidence taxonomy is outside the event subject.",
        )
