"""Source, rubric, and final-score safety boundaries for step grading."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assignments.models import AssignmentMaterialItem, StudentAssignmentMaterialItem
from app.core.exceptions import ApplicationError
from app.math_solutions.grading_context import resolve_grading_context
from app.math_solutions.models import SolutionRubric
from app.questions.models import Question, QuestionStatus, QuestionType
from app.teacher_materials.models import MaterialEvaluationMode


class FakeSession:
    def __init__(self, *rows):
        self.rows = {(type(row), row.id): row for row in rows}

    def get(self, model, row_id):
        return self.rows.get((model, row_id))


def rubric_for(**target):
    return SolutionRubric(
        id=uuid4(),
        title="Reviewed derivative criterion",
        status="APPROVED",
        criteria=[{"id": "derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 1.0}],
        max_score=1.0,
        **target,
    )


def canonical_case():
    question = Question(
        id=uuid4(),
        content="Find the derivative of y = x^3",
        question_type=QuestionType.OPEN_RESPONSE,
        status=QuestionStatus.APPROVED,
    )
    rubric = rubric_for(question_id=question.id)
    attempt = SimpleNamespace(
        status="SUBMITTED", rubric_id=rubric.id, source_kind="CANONICAL",
        question_id=question.id,
    )
    return FakeSession(question, rubric), attempt, question, rubric


def material_case():
    assignment_id = uuid4()
    student_assignment_id = uuid4()
    snapshot = AssignmentMaterialItem(
        id=uuid4(),
        assignment_id=assignment_id,
        content="Find the derivative of y = x^3",
        question_type=QuestionType.OPEN_RESPONSE,
        evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
        snapshotted_at=datetime.now(timezone.utc),
    )
    student_item = StudentAssignmentMaterialItem(
        id=uuid4(),
        assignment_material_item_id=snapshot.id,
        student_assignment_id=student_assignment_id,
    )
    rubric = rubric_for(assignment_material_item_id=snapshot.id)
    attempt = SimpleNamespace(
        status="SUBMITTED", rubric_id=rubric.id, source_kind="TEACHER_MATERIAL",
        assignment_material_item_id=snapshot.id,
        student_assignment_material_item_id=student_item.id,
        assignment_id=assignment_id,
        student_assignment_id=student_assignment_id,
    )
    return FakeSession(snapshot, student_item, rubric), attempt, snapshot, student_item, rubric


def assert_blocked(session, attempt, code):
    with pytest.raises(ApplicationError) as exc:
        resolve_grading_context(session, attempt)
    assert exc.value.code == code


def test_canonical_uses_approved_question_and_pinned_rubric():
    session, attempt, question, rubric = canonical_case()
    context = resolve_grading_context(session, attempt)
    assert context.problem_content == question.content
    assert context.rubric.id == rubric.id


def test_teacher_material_uses_immutable_assignment_snapshot():
    session, attempt, snapshot, _, rubric = material_case()
    context = resolve_grading_context(session, attempt)
    assert context.problem_content == snapshot.content
    assert context.rubric.id == rubric.id


def test_unsubmitted_or_unpinned_solution_cannot_be_graded():
    session, attempt, _, _ = canonical_case()
    attempt.status = "IN_PROGRESS"
    assert_blocked(session, attempt, "SOLUTION_NOT_SUBMITTED")
    attempt.status = "SUBMITTED"
    attempt.rubric_id = None
    assert_blocked(session, attempt, "GRADING_RUBRIC_REQUIRED")


def test_canonical_rejects_draft_question_and_foreign_rubric():
    session, attempt, question, rubric = canonical_case()
    question.status = QuestionStatus.DRAFT
    assert_blocked(session, attempt, "GRADING_SOURCE_MISMATCH")
    question.status = QuestionStatus.APPROVED
    rubric.question_id = uuid4()
    assert_blocked(session, attempt, "GRADING_SOURCE_MISMATCH")


def test_teacher_material_rejects_wrong_assignment_or_student_item():
    session, attempt, _, student_item, _ = material_case()
    attempt.assignment_id = uuid4()
    assert_blocked(session, attempt, "GRADING_SOURCE_MISMATCH")
    session, attempt, _, student_item, _ = material_case()
    student_item.student_assignment_id = uuid4()
    assert_blocked(session, attempt, "GRADING_SOURCE_MISMATCH")


def test_teacher_review_mode_and_unapproved_rubric_block_automatic_score():
    session, attempt, snapshot, _, rubric = material_case()
    snapshot.evaluation_mode = MaterialEvaluationMode.TEACHER_REVIEW
    assert_blocked(session, attempt, "GRADING_SOURCE_MISMATCH")
    snapshot.evaluation_mode = MaterialEvaluationMode.OPEN_RESPONSE
    rubric.status = "DRAFT"
    assert_blocked(session, attempt, "GRADING_RUBRIC_UNAVAILABLE")


def test_assigned_solution_cannot_publish_before_assignment_submission():
    from unittest.mock import Mock, patch

    from app.math_solutions.evaluator_service import MathEvaluatorService

    session, attempt, _, _, _ = material_case()
    attempt.id = uuid4()
    attempt.context_type = "CLASSROOM_ASSIGNMENT"
    evaluator_session = Mock()
    evaluator_session.get.return_value = attempt
    evaluator_session.scalar.return_value = None
    with patch(
        "app.math_solutions.evaluator_service.resolve_grading_context",
        return_value=resolve_grading_context(session, attempt),
    ):
        with pytest.raises(ApplicationError) as exc:
            MathEvaluatorService(evaluator_session).evaluate_attempt(attempt.id)
    assert exc.value.code == "GRADING_ASSIGNMENT_NOT_SUBMITTED"
    evaluator_session.commit.assert_not_called()

def test_automatic_math_scope_requires_a_parsed_polynomial():
    from app.math_solutions.validator import DeterministicMathValidator, MathValidity

    polynomial = DeterministicMathValidator("y = x^3 - 2*x + 1")
    rational = DeterministicMathValidator("y = 1/(x-1)")
    missing = DeterministicMathValidator("No readable function")
    assert polynomial.supports_polynomial_target
    assert not rational.supports_polynomial_target
    assert not missing.supports_polynomial_target
    assert polynomial.validate_step("ASSUMPTION", r"D = \mathbb{R}").validity == MathValidity.VALID
    assert polynomial.validate_step("ASSUMPTION", r"D = (0,+\infty)").validity == MathValidity.NEEDS_REVIEW

@pytest.mark.parametrize("criteria", [
    [{"id": "derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 0.7}],
    [{"id": "derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 1.0},
     {"id": "repeat", "step_type": "DERIVATIVE_CALCULATION", "weight": 0.0}],
    [{"id": "custom", "step_type": "CUSTOM", "weight": 1.0}],
])
def test_unsupported_rubric_cannot_produce_final_score(criteria):
    session, attempt, _, rubric = canonical_case()
    rubric.criteria = criteria
    assert_blocked(session, attempt, "GRADING_RUBRIC_UNSUPPORTED")