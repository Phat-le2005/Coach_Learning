"""Readiness reports provisional feedback when an approved answer is absent."""

from types import SimpleNamespace
from uuid import uuid4

from app.math_solutions import ai_review_router as router
from app.math_solutions.models import SolutionAttempt
from app.questions.models import Question, QuestionStatus, QuestionType


class FakeSession:
    def __init__(self, attempt, question):
        self.attempt = attempt
        self.question = question

    def get(self, model, key):
        if model is SolutionAttempt and key == self.attempt.id:
            return self.attempt
        if model is Question and key == self.question.id:
            return self.question
        return None

    def scalar(self, statement):
        return None


def sample_without_answer():
    question = Question(id=uuid4(), subject_id=uuid4(), content="Find monotonicity",
        question_type=QuestionType.OPEN_RESPONSE, status=QuestionStatus.APPROVED,
        correct_answer=None, explanation=None)
    attempt = SimpleNamespace(id=uuid4(), status="SUBMITTED", source_kind="CANONICAL",
        context_type="SELF_PRACTICE", question_id=question.id)
    return FakeSession(attempt, question), attempt


def test_missing_approved_answer_allows_only_provisional_feedback(monkeypatch):
    session, attempt = sample_without_answer()
    monkeypatch.setattr(router, "MathSolutionService", lambda _session: SimpleNamespace(get=lambda *_: None))
    student = SimpleNamespace(id=uuid4())
    availability = router.get_ai_review_availability(attempt.id, student, session)
    assert availability.available is True
    assert availability.reason_code == "PROVISIONAL_WITHOUT_ANSWER"
    assert availability.cached_review is None


def test_readiness_allows_draft_when_reference_exists(monkeypatch):
    session, attempt = sample_without_answer()
    session.question.correct_answer = "Reviewed solution"
    attempt.status = "IN_PROGRESS"
    monkeypatch.setattr(router, "MathSolutionService", lambda _session: SimpleNamespace(get=lambda *_: None))
    assert router.get_ai_review_availability(attempt.id, SimpleNamespace(id=uuid4()), session).available




def test_assigned_solution_waits_for_whole_assignment_submission(monkeypatch):
    from app.core.exceptions import ApplicationError
    from app.math_solutions.answer_reference import AnswerReference

    session, attempt = sample_without_answer()
    attempt.context_type = "CLASSROOM_ASSIGNMENT"
    reference = AnswerReference("CANONICAL", session.question.id,
                                session.question.content, "Reviewed answer", None, "a" * 64)
    monkeypatch.setattr(router, "MathSolutionService", lambda _session: SimpleNamespace(get=lambda *_: None))
    monkeypatch.setattr(router, "resolve_answer_reference", lambda *_args, **_kwargs: reference)

    def pending(_session, _attempt):
        raise ApplicationError(409, "GRADING_ASSIGNMENT_NOT_SUBMITTED", "Submit the assignment first.")

    monkeypatch.setattr(router, "require_pending_assignment_item", pending)
    result = router.get_ai_review_availability(attempt.id, SimpleNamespace(id=uuid4()), session)
    assert result.available is False
    assert result.reason_code == "GRADING_ASSIGNMENT_NOT_SUBMITTED"

    monkeypatch.setattr(router, "require_pending_assignment_item", lambda *_args: None)
    allowed = router.get_ai_review_availability(attempt.id, SimpleNamespace(id=uuid4()), session)
    assert allowed.available is True


def test_solution_only_is_a_reference_not_unanswered_feedback(monkeypatch):
    session, attempt = sample_without_answer()
    session.question.explanation = "Compute the derivative, solve its roots, then determine monotonicity."
    monkeypatch.setattr(router, "MathSolutionService", lambda _session: SimpleNamespace(get=lambda *_: None))
    availability = router.get_ai_review_availability(attempt.id, SimpleNamespace(id=uuid4()), session)
    assert availability.available is True
    assert availability.reason_code is None
