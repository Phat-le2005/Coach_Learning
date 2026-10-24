"""AI suggestions must be tied to an answer and every confirmed step."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.mock_provider import MockAIProvider
from app.core.exceptions import ApplicationError
from app.math_solutions.answer_grounded_ai import (
    AIGradeOutput, AnswerGroundedAIService,
)
from app.math_solutions.answer_reference import AnswerReference


class FakeSession:
    def __init__(self, attempt):
        self.attempt = attempt
        self.steps = [
            SimpleNamespace(id=uuid4(), step_index=1, step_type="DERIVATIVE_CALCULATION"),
            SimpleNamespace(id=uuid4(), step_index=2, step_type="CONCLUSION"),
        ]
        self.revisions = [
            SimpleNamespace(content_latex="y'=3x^2", explanation_text=None),
            SimpleNamespace(content_latex="increasing on (0,2)", explanation_text=None),
        ]
        self.calls = 0

    def get(self, model, key):
        return self.attempt if key == self.attempt.id else None

    def scalar(self, statement):
        self.calls += 1
        return None if self.calls == 1 else self.revisions[self.calls - 2]

    def scalars(self, statement):
        return self.steps


class FakeGateway:
    def __init__(self, response, *, mock=False):
        self.provider = MockAIProvider() if mock else object()
        self.response = response
        self.calls = 0
        self.messages = None

    async def generate_structured(self, **kwargs):
        self.calls += 1
        self.messages = kwargs["messages"]
        return SimpleNamespace(data=AIGradeOutput.model_validate(self.response))


def fixture_case(monkeypatch, response=None, *, mock=False):
    attempt = SimpleNamespace(
        id=uuid4(), student_id=uuid4(), status="SUBMITTED",
        source_kind="CANONICAL", context_type="SELF_PRACTICE",
    )
    reference = AnswerReference(
        source_kind="CANONICAL", source_id=uuid4(),
        problem_content="Find the derivative and intervals for y=x^3",
        correct_answer="y'=3x^2; increasing on (0,2)",
        explanation="The derivative is nonnegative.", content_sha256="a" * 64,
    )
    monkeypatch.setattr(
        "app.math_solutions.answer_grounded_ai.resolve_answer_reference",
        lambda session, row: reference,
    )
    default_response = {"steps": [
        {"step_index": 1, "verdict": "VALID", "score": 1.0, "confidence": 0.94,
         "student_quote": "3x^2", "answer_quote": "3x^2", "feedback": "Derivative matches."},
        {"step_index": 2, "verdict": "VALID", "score": 1.0, "confidence": 0.91,
         "student_quote": "(0,2)", "answer_quote": "(0,2)", "feedback": "Interval matches."},
    ]}
    session = FakeSession(attempt)
    gateway = FakeGateway(response or default_response, mock=mock)
    return attempt, session, gateway


def test_real_gateway_returns_grounded_step_review_without_final_db_grade(monkeypatch):
    attempt, session, gateway = fixture_case(monkeypatch)
    review = asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert [step.step_index for step in review.step_grades] == [1, 2]
    assert review.answer_sha256 == "a" * 64
    assert review.needs_teacher_review is False
    assert gateway.calls == 1
    assert "y'=3x^2; increasing on (0,2)" in gateway.messages[1].content
    assert attempt.status == "SUBMITTED"


def test_mock_provider_cannot_issue_ai_grades(monkeypatch):
    attempt, session, gateway = fixture_case(monkeypatch, mock=True)
    with pytest.raises(ApplicationError) as error:
        asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert error.value.code == "REAL_AI_PROVIDER_REQUIRED"
    assert gateway.calls == 0


def test_missing_answer_stops_before_model_call(monkeypatch):
    attempt, session, gateway = fixture_case(monkeypatch)
    def missing(session, row):
        raise ApplicationError(409, "GRADING_ANSWER_REQUIRED", "No answer")
    monkeypatch.setattr("app.math_solutions.answer_grounded_ai.resolve_answer_reference", missing)
    with pytest.raises(ApplicationError) as error:
        asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert error.value.code == "GRADING_ANSWER_REQUIRED"
    assert gateway.calls == 0


@pytest.mark.parametrize("broken,code", [
    ({"steps": [
        {"step_index": 1, "verdict": "VALID", "score": 1, "confidence": 0.95,
         "student_quote": "3x^2", "answer_quote": "3x^2", "feedback": "Good"},
        {"step_index": 1, "verdict": "VALID", "score": 1, "confidence": 0.95,
         "student_quote": "3x^2", "answer_quote": "3x^2", "feedback": "Good"},
    ]}, "AI_STEP_COVERAGE_INVALID"),
    ({"steps": [
        {"step_index": 1, "verdict": "VALID", "score": 1, "confidence": 0.95,
         "student_quote": "3x^2", "answer_quote": "invented", "feedback": "Good"},
        {"step_index": 2, "verdict": "VALID", "score": 1, "confidence": 0.95,
         "student_quote": "(0,2)", "answer_quote": "(0,2)", "feedback": "Good"},
    ]}, "AI_EVIDENCE_INVALID"),
])
def test_invalid_ai_coverage_or_evidence_cannot_be_used(monkeypatch, broken, code):
    attempt, session, gateway = fixture_case(monkeypatch, broken)
    with pytest.raises(ApplicationError) as error:
        asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert error.value.code == code


def test_uncertain_step_requires_teacher_review(monkeypatch):
    response = {"steps": [
        {"step_index": 1, "verdict": "VALID", "score": 1, "confidence": 0.7,
         "student_quote": "3x^2", "answer_quote": "3x^2", "feedback": "Uncertain"},
        {"step_index": 2, "verdict": "NEEDS_REVIEW", "score": None, "confidence": 0.5,
         "student_quote": "(0,2)", "answer_quote": "(0,2)", "feedback": "Review interval"},
    ]}
    attempt, session, gateway = fixture_case(monkeypatch, response)
    review = asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert review.needs_teacher_review is True