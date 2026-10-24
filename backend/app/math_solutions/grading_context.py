"""Fail-closed source and rubric selection for deterministic math-step grading.

Practice uses approved Question rows; classroom material uses the immutable
AssignmentMaterialItem captured when the teacher published the assignment.
Exam attempts have their own scoring lifecycle and are intentionally excluded.
"""
from dataclasses import dataclass
import math

from sqlalchemy.orm import Session

from app.assignments.models import AssignmentMaterialItem, StudentAssignmentMaterialItem
from app.core.exceptions import ApplicationError
from app.math_solutions.models import SolutionAttempt, SolutionRubric
from app.questions.models import Question, QuestionStatus, QuestionType
from app.teacher_materials.models import MaterialEvaluationMode


@dataclass(frozen=True, slots=True)
class GradingContext:
    problem_content: str
    rubric: SolutionRubric


_AUTO_STEP_TYPES = frozenset({
    "ASSUMPTION", "DERIVATIVE_CALCULATION", "ROOT_FINDING", "SIGN_TABLE", "CONCLUSION",
})


def resolve_grading_context(session: Session, attempt: SolutionAttempt) -> GradingContext:
    """Resolve only a submitted solution with a matching, pinned approved rubric."""
    if attempt.status != "SUBMITTED":
        raise ApplicationError(409, "SOLUTION_NOT_SUBMITTED", "Submit the solution before grading.")
    if attempt.rubric_id is None:
        raise ApplicationError(409, "GRADING_RUBRIC_REQUIRED", "An approved rubric must be attached to the attempt.")

    rubric = session.get(SolutionRubric, attempt.rubric_id)
    if rubric is None or rubric.status != "APPROVED":
        raise ApplicationError(409, "GRADING_RUBRIC_UNAVAILABLE", "The attached rubric is not approved.")

    if attempt.source_kind == "CANONICAL":
        question = session.get(Question, attempt.question_id) if attempt.question_id else None
        if (question is None or question.status != QuestionStatus.APPROVED
                or question.question_type != QuestionType.OPEN_RESPONSE
                or rubric.question_id != attempt.question_id
                or rubric.assignment_material_item_id is not None):
            raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "The rubric does not match an approved open-response question.")
        content = question.content
    elif attempt.source_kind == "TEACHER_MATERIAL":
        snapshot = (session.get(AssignmentMaterialItem, attempt.assignment_material_item_id)
                    if attempt.assignment_material_item_id else None)
        student_item = (session.get(StudentAssignmentMaterialItem, attempt.student_assignment_material_item_id)
                        if attempt.student_assignment_material_item_id else None)
        if (snapshot is None or snapshot.snapshotted_at is None
                or snapshot.assignment_id != attempt.assignment_id
                or student_item is None
                or student_item.assignment_material_item_id != snapshot.id
                or student_item.student_assignment_id != attempt.student_assignment_id
                or snapshot.question_type != QuestionType.OPEN_RESPONSE
                or snapshot.evaluation_mode != MaterialEvaluationMode.OPEN_RESPONSE
                or rubric.assignment_material_item_id != attempt.assignment_material_item_id
                or rubric.question_id is not None):
            raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "The rubric does not match a reviewed assignment snapshot.")
        content = snapshot.content
    else:
        raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "Unsupported solution source.")

    if not content:
        raise ApplicationError(409, "GRADING_SOURCE_UNAVAILABLE", "The submitted problem has no stable content.")
    _validate_rubric(rubric)
    return GradingContext(problem_content=content, rubric=rubric)


def _validate_rubric(rubric: SolutionRubric) -> None:
    """The current matcher handles one normalized criterion per supported step kind."""
    criteria = rubric.criteria
    if isinstance(criteria, dict):
        criteria = criteria.get("criteria")
    if (not isinstance(criteria, list) or not criteria
            or not math.isclose(rubric.max_score, 1.0)):
        raise ApplicationError(409, "GRADING_RUBRIC_UNSUPPORTED", "The rubric is not compatible with automatic step grading.")
    ids: set[str] = set()
    kinds: set[str] = set()
    total_weight = 0.0
    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise ApplicationError(409, "GRADING_RUBRIC_UNSUPPORTED", "Rubric criteria must be structured records.")
        identifier = criterion.get("id")
        kind = criterion.get("step_type")
        weight = criterion.get("weight")
        if (not isinstance(identifier, str) or not identifier.strip() or identifier in ids
                or kind not in _AUTO_STEP_TYPES or kind in kinds
                or type(weight) not in (int, float) or not math.isfinite(weight) or weight <= 0):
            raise ApplicationError(409, "GRADING_RUBRIC_UNSUPPORTED", "Rubric criteria must have unique supported steps and positive weights.")
        ids.add(identifier)
        kinds.add(kind)
        total_weight += weight
    if not math.isclose(total_weight, 1.0, rel_tol=0, abs_tol=1e-6):
        raise ApplicationError(409, "GRADING_RUBRIC_UNSUPPORTED", "Rubric weights must total 1.0.")
