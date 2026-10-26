"""Require an ungraded submitted Assignment item before step-score publication."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import (
    AssignmentStudentQuestion,
    StudentAssignment,
    StudentAssignmentMaterialItem,
    StudentAssignmentStatus,
)
from app.core.exceptions import ApplicationError
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.math_solutions.models import SolutionAttempt
from app.practice.models import EvaluationStatus


def require_pending_assignment_item(session: Session, attempt: SolutionAttempt) -> None:
    assigned = session.get(StudentAssignment, attempt.student_assignment_id)
    if (
        assigned is None
        or assigned.id != attempt.student_assignment_id
        or assigned.assignment_id != attempt.assignment_id
        or assigned.student_id != attempt.student_id
        or assigned.status != StudentAssignmentStatus.SUBMITTED
    ):
        raise ApplicationError(
            409, "GRADING_ASSIGNMENT_NOT_SUBMITTED",
            "The assigned work must be submitted before step grading.",
        )

    if attempt.source_kind == "CANONICAL":
        item = session.get(AssignmentStudentQuestion, attempt.assignment_student_question_id)
        valid = (
            item is not None
            and item.student_assignment_id == assigned.id
            and item.question_id == attempt.question_id
            and item.answered_at is not None
            and item.score is None
            and item.is_correct is None
        )
        source_kind = LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION
    elif attempt.source_kind == "TEACHER_MATERIAL":
        item = session.get(StudentAssignmentMaterialItem, attempt.student_assignment_material_item_id)
        valid = (
            item is not None
            and item.student_assignment_id == assigned.id
            and item.assignment_material_item_id == attempt.assignment_material_item_id
            and item.answered_at is not None
            and item.score is None
            and item.is_correct is None
            and item.evaluation_status in {
                EvaluationStatus.NEEDS_EVALUATION,
                EvaluationStatus.NEEDS_TEACHER_REVIEW,
            }
        )
        source_kind = LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM
    else:
        valid = False
        source_kind = None

    if not valid:
        raise ApplicationError(
            409, "GRADING_ASSIGNMENT_ITEM_NOT_PENDING",
            "This assignment item is not waiting for a step score.",
        )

    previous_evidence = session.scalar(
        select(LearningEvidenceEvent.id).where(
            LearningEvidenceEvent.source_kind == source_kind,
            LearningEvidenceEvent.source_entity_id == item.id,
        )
    )
    if previous_evidence is not None:
        raise ApplicationError(
            409, "GRADING_ASSIGNMENT_ITEM_ALREADY_SCORED",
            "This assignment item already has grading evidence.",
        )