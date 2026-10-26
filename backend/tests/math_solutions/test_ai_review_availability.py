"""Trusted-answer readiness does not spend AI budget without a reviewed answer."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import ApplicationError
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


def sample_without_answer():
    question = Question(id=uuid4(), subject_id=uuid4(), content="Find monotonicity",
        question_type=QuestionType.OPEN_RESPONSE, status=QuestionStatus.APPROVED,
        correct_answer=None, explanation="An incomplete hint.")
    attempt = SimpleNamespace(id=uuid4(), status="SUBMITTED", source_kind="CANONICAL",
        context_type="SELF_PRACTICE", question_id=question.id)
    return FakeSession(attempt, question), attempt


def test_missing_approved_answer_is_reported_before_ai_call(monkeypatch):
    session, attempt = sample_without_answer()
    monkeypatch.setattr(router, "MathSolutionService", lambda _session: SimpleNamespace(get=lambda *_: None))
    student = SimpleNamespace(id=uuid4())
    availability = router.get_ai_review_availability(attempt.id, student, session)
    assert availability.available is False
    assert availability.reason_code == "GRADING_ANSWER_REQUIRED"
    limiter = SimpleNamespace(check_rate_limit=lambda *_args, **_kwargs: pytest.fail("No AI budget without answer"))
    with pytest.raises(ApplicationError) as error:
        asyncio.run(router.review_submitted_steps(attempt.id, student, session, None,
            SimpleNamespace(ai_rate_limit_per_minute=5, ai_daily_requests_limit_per_student=20), limiter))
    assert error.value.status_code == 409
    assert error.value.code == "GRADING_ANSWER_REQUIRED"


def test_readiness_allows_draft_when_reference_exists(monkeypatch):
    session, attempt = sample_without_answer()
    session.question.correct_answer = "Reviewed solution"
    attempt.status = "IN_PROGRESS"
    monkeypatch.setattr(router, "MathSolutionService", lambda _session: SimpleNamespace(get=lambda *_: None))
    assert router.get_ai_review_availability(attempt.id, SimpleNamespace(id=uuid4()), session).available


