"""The AI reference is an approved answer, never OCR or editable PDF text."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assignments.models import AssignmentMaterialItem, StudentAssignmentMaterialItem
from app.core.exceptions import ApplicationError
from app.math_solutions.answer_reference import resolve_answer_reference
from app.questions.models import Question, QuestionStatus, QuestionType
from app.teacher_materials.models import MaterialEvaluationMode


class FakeSession:
    def __init__(self, *rows):
        self.rows = {(type(row), row.id): row for row in rows}

    def get(self, model, key):
        return self.rows.get((model, key))


def canonical_case(answer="y' = 3x^2"):
    question = Question(
        id=uuid4(), subject_id=uuid4(), content="Find the derivative of y=x^3",
        question_type=QuestionType.OPEN_RESPONSE, status=QuestionStatus.APPROVED,
        correct_answer=answer, explanation="Differentiate term by term.",
    )
    attempt = SimpleNamespace(
        id=uuid4(), status="SUBMITTED", source_kind="CANONICAL",
        context_type="SELF_PRACTICE", question_id=question.id,
    )
    return FakeSession(question), attempt, question


def test_approved_canonical_answer_is_stable_and_missing_answer_blocks_ai():
    session, attempt, question = canonical_case()
    first = resolve_answer_reference(session, attempt)
    assert first.correct_answer == "y' = 3x^2"
    assert first.source_id == question.id
    assert first.content_sha256 == resolve_answer_reference(session, attempt).content_sha256
    question.correct_answer = None
    with pytest.raises(ApplicationError) as missing:
        resolve_answer_reference(session, attempt)
    assert missing.value.code == "GRADING_ANSWER_REQUIRED"
    question.correct_answer = "y' = 2x"
    assert resolve_answer_reference(session, attempt).content_sha256 != first.content_sha256


def test_draft_and_unsubmitted_canonical_questions_are_rejected():
    session, attempt, question = canonical_case()
    question.status = QuestionStatus.DRAFT
    with pytest.raises(ApplicationError) as draft:
        resolve_answer_reference(session, attempt)
    assert draft.value.code == "GRADING_SOURCE_MISMATCH"
    question.status = QuestionStatus.APPROVED
    attempt.status = "IN_PROGRESS"
    with pytest.raises(ApplicationError) as unsubmitted:
        resolve_answer_reference(session, attempt)
    assert unsubmitted.value.code == "SOLUTION_NOT_SUBMITTED"


def test_teacher_reference_uses_assigned_snapshot_not_editable_source():
    assignment_id = uuid4()
    student_assignment_id = uuid4()
    snapshot = AssignmentMaterialItem(
        id=uuid4(), assignment_id=assignment_id, teacher_material_item_id=uuid4(),
        content="Find the derivative of y=x^3", correct_answer="y' = 3x^2",
        explanation="Use the power rule.", question_type=QuestionType.OPEN_RESPONSE,
        evaluation_mode=MaterialEvaluationMode.OPEN_RESPONSE,
        snapshotted_at=datetime.now(timezone.utc), order_index=0,
    )
    item = StudentAssignmentMaterialItem(
        id=uuid4(), student_assignment_id=student_assignment_id,
        assignment_material_item_id=snapshot.id,
        teacher_material_item_id=snapshot.teacher_material_item_id,
        order_index=0,
    )
    attempt = SimpleNamespace(
        status="SUBMITTED", source_kind="TEACHER_MATERIAL",
        assignment_id=assignment_id, student_assignment_id=student_assignment_id,
        assignment_material_item_id=snapshot.id,
        student_assignment_material_item_id=item.id,
    )
    session = FakeSession(snapshot, item)
    reference = resolve_answer_reference(session, attempt)
    assert reference.correct_answer == "y' = 3x^2"
    assert reference.source_id == snapshot.id
    snapshot.correct_answer = None
    with pytest.raises(ApplicationError) as missing:
        resolve_answer_reference(session, attempt)
    assert missing.value.code == "GRADING_ANSWER_REQUIRED"
    snapshot.correct_answer = "y' = 3x^2"
    item.assignment_material_item_id = uuid4()
    with pytest.raises(ApplicationError) as mismatched:
        resolve_answer_reference(session, attempt)
    assert mismatched.value.code == "GRADING_SOURCE_MISMATCH"