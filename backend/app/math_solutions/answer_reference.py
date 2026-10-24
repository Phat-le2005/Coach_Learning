"""Resolve a trusted answer for one submitted math-solution attempt.

The assigned material snapshot, rather than the editable source document, is the
reference for classroom PDF work. No answer is inferred from the student's work.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.assignments.models import Assignment, AssignmentMaterialItem, AssignmentStudentQuestion, StudentAssignmentMaterialItem
from app.core.exceptions import ApplicationError
from app.math_solutions.models import SolutionAttempt
from app.questions.models import Question, QuestionStatus, QuestionType
from app.teacher_materials.models import MaterialEvaluationMode


@dataclass(frozen=True, slots=True)
class AnswerReference:
    source_kind: str
    source_id: UUID
    problem_content: str
    correct_answer: str
    explanation: str | None
    content_sha256: str


def resolve_answer_reference(session: Session, attempt: SolutionAttempt, *, require_submitted: bool = True) -> AnswerReference:
    """Bind grading to an approved question or immutable assigned snapshot."""
    if require_submitted and attempt.status != "SUBMITTED":
        raise ApplicationError(409, "SOLUTION_NOT_SUBMITTED", "Submit the solution before grading.")

    if attempt.source_kind == "CANONICAL":
        question = session.get(Question, attempt.question_id) if attempt.question_id else None
        if question is None or question.status != QuestionStatus.APPROVED or question.question_type != QuestionType.OPEN_RESPONSE:
            raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "An approved open-response question is required.")
        if attempt.context_type == "CLASSROOM_ASSIGNMENT":
            assignment = session.get(Assignment, attempt.assignment_id) if attempt.assignment_id else None
            item = session.get(AssignmentStudentQuestion, attempt.assignment_student_question_id) if attempt.assignment_student_question_id else None
            if (
                assignment is None or question.subject_id != assignment.subject_id
                or item is None or item.question_id != question.id
                or item.student_assignment_id != attempt.student_assignment_id
            ):
                raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "Question does not match its assigned item.")
        source_id = question.id
        content = question.content
        answer = question.correct_answer
        explanation = question.explanation
    elif attempt.source_kind == "TEACHER_MATERIAL":
        snapshot = session.get(AssignmentMaterialItem, attempt.assignment_material_item_id) if attempt.assignment_material_item_id else None
        student_item = session.get(StudentAssignmentMaterialItem, attempt.student_assignment_material_item_id) if attempt.student_assignment_material_item_id else None
        if (
            snapshot is None or snapshot.snapshotted_at is None
            or snapshot.assignment_id != attempt.assignment_id
            or snapshot.question_type != QuestionType.OPEN_RESPONSE
            or snapshot.evaluation_mode != MaterialEvaluationMode.OPEN_RESPONSE
            or student_item is None
            or student_item.student_assignment_id != attempt.student_assignment_id
            or student_item.assignment_material_item_id != snapshot.id
        ):
            raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "A reviewed assigned material snapshot is required.")
        source_id = snapshot.id
        content = snapshot.content
        answer = snapshot.correct_answer
        explanation = snapshot.explanation
    else:
        raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "Unsupported solution source.")

    if not isinstance(content, str) or not content.strip():
        raise ApplicationError(409, "GRADING_SOURCE_UNAVAILABLE", "The problem text is unavailable.")
    if not isinstance(answer, str) or not answer.strip():
        raise ApplicationError(409, "GRADING_ANSWER_REQUIRED", "A reviewed answer is required before AI step grading.")
    explanation = explanation.strip() if isinstance(explanation, str) and explanation.strip() else None
    content = content.strip()
    answer = answer.strip()
    fingerprint = sha256(json.dumps(
        {"source_kind": attempt.source_kind, "source_id": str(source_id),
         "problem_content": content, "correct_answer": answer, "explanation": explanation},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return AnswerReference(attempt.source_kind, source_id, content, answer, explanation, fingerprint)