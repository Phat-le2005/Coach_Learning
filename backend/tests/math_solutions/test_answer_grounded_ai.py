"""AI feedback must cover confirmed steps and never invent a final grade."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.mock_provider import MockAIProvider
from app.core.exceptions import ApplicationError
from app.math_solutions.answer_grounded_ai import (
    AIGradeOutput, AnswerGroundedAIService, UnansweredAIService,
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
        return SimpleNamespace(data=kwargs["schema"].model_validate(self.response))


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


def test_no_answer_feedback_is_always_unscored_and_requests_teacher_review(monkeypatch):
    attempt, session, gateway = fixture_case(monkeypatch)
    reference = AnswerReference("CANONICAL", uuid4(), "Find the derivative for y=x^3", "", None, "b" * 64)
    monkeypatch.setattr(
        "app.math_solutions.answer_grounded_ai.resolve_answer_reference",
        lambda _session, _attempt, **_kwargs: reference,
    )
    gateway.response = {"steps": [
        {"step_index": 1, "student_quote": "3x^2", "problem_quote": "derivative", "feedback": "Check the derivative rule."},
        {"step_index": 2, "student_quote": "(0,2)", "problem_quote": "y=x^3", "feedback": "Check the interval against the domain."},
    ]}
    review = asyncio.run(UnansweredAIService(session, gateway).review_attempt(attempt.id))
    assert gateway.calls == 1
    assert review.needs_teacher_review is True
    assert [step.verdict for step in review.step_grades] == ["NEEDS_REVIEW"] * 2
    assert all(step.score is None for step in review.step_grades)
    assert "correct_answer" not in gateway.messages[1].content
    assert attempt.status == "SUBMITTED"


def test_no_answer_feedback_rejects_fabricated_problem_quote(monkeypatch):
    attempt, session, gateway = fixture_case(monkeypatch)
    reference = AnswerReference("CANONICAL", uuid4(), "Find the derivative for y=x^3", "", None, "b" * 64)
    monkeypatch.setattr(
        "app.math_solutions.answer_grounded_ai.resolve_answer_reference",
        lambda _session, _attempt, **_kwargs: reference,
    )
    gateway.response = {"steps": [
        {"step_index": 1, "student_quote": "3x^2", "problem_quote": "unrelated theorem", "feedback": "Check the step."},
        {"step_index": 2, "student_quote": "(0,2)", "problem_quote": "y=x^3", "feedback": "Check the interval."},
    ]}
    with pytest.raises(ApplicationError) as error:
        asyncio.run(UnansweredAIService(session, gateway).review_attempt(attempt.id))
    assert error.value.code == "AI_EVIDENCE_INVALID"


@pytest.mark.parametrize("score", [0.0, None])
def test_ai_cannot_return_a_score_that_conflicts_with_its_verdict(score):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AIGradeOutput.model_validate({"steps": [{
            "step_index": 1, "verdict": "VALID", "score": score, "confidence": 1.0,
            "student_quote": "x", "answer_quote": "x", "feedback": "Conflicting score",
        }]})


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

def test_confirmed_variation_artifact_is_included_as_student_evidence(monkeypatch):
    response = {"steps": [
        {"step_index": 1, "verdict": "NEEDS_REVIEW", "score": None, "confidence": 0.4,
         "student_quote": "\"trend\":\"UP\"", "answer_quote": "3x^2", "feedback": "Review the table against the full answer."},
        {"step_index": 2, "verdict": "VALID", "score": 1.0, "confidence": 0.9,
         "student_quote": "(0,2)", "answer_quote": "(0,2)", "feedback": "Interval matches."},
    ]}
    attempt, session, gateway = fixture_case(monkeypatch, response)
    session.steps[0].step_type = "VARIATION_TABLE"
    session.revisions[0] = SimpleNamespace(content_latex=None, explanation_text=None,
        artifact_snapshot={"artifact_type": "VARIATION_TABLE", "payload": {
            "version": 1,
            "points": [{"x": "left", "derivative": "", "y": ""},
                       {"x": "right", "derivative": "", "y": ""}],
            "intervals": [{"sign": "+", "trend": "UP"}],
        }})
    review = asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert gateway.calls == 1
    assert "Student-entered variation table" in gateway.messages[1].content
    assert review.step_grades[0].verdict == "NEEDS_REVIEW"
    assert review.needs_teacher_review


def test_problem_content_restatement_is_valid_evidence(monkeypatch):
    response = {"steps": [
        {"step_index": 1, "verdict": "VALID", "score": 1.0, "confidence": 0.95,
         "student_quote": "y=x^3", "answer_quote": "y=x^3", "feedback": "Restates problem correctly."},
        {"step_index": 2, "verdict": "VALID", "score": 1.0, "confidence": 0.91,
         "student_quote": "(0,2)", "answer_quote": "(0,2)", "feedback": "Interval matches."},
    ]}
    attempt, session, gateway = fixture_case(monkeypatch, response)
    session.revisions[0] = SimpleNamespace(content_latex="y=x^3", explanation_text=None)
    review = asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert review.step_grades[0].verdict == "VALID"
    assert review.step_grades[0].score == 1.0


def test_quote_with_normalized_whitespace_and_delimiters_is_accepted(monkeypatch):
    response = {"steps": [
        {"step_index": 1, "verdict": "VALID", "score": 1.0, "confidence": 0.95,
         "student_quote": "3x^2", "answer_quote": "y'=3x^2", "feedback": "Matches derivative."},
        {"step_index": 2, "verdict": "VALID", "score": 1.0, "confidence": 0.91,
         "student_quote": "(0, 2)", "answer_quote": "(0,2)", "feedback": "Matches with spacing."},
    ]}
    attempt, session, gateway = fixture_case(monkeypatch, response)
    session.revisions[1] = SimpleNamespace(content_latex="increasing on (0, 2)", explanation_text=None)
    review = asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    assert review.step_grades[1].verdict == "VALID"



def test_solution_only_is_sent_as_primary_reference_in_one_model_call(monkeypatch):
    attempt, session, gateway = fixture_case(monkeypatch)
    solution = "The power rule gives y'=3x^2; the function is increasing on (0,2)."
    reference = AnswerReference("CANONICAL", uuid4(), "Find the derivative and intervals for y=x^3", "", solution, "c" * 64)
    monkeypatch.setattr("app.math_solutions.answer_grounded_ai.resolve_answer_reference", lambda *_args: reference)
    review = asyncio.run(AnswerGroundedAIService(session, gateway).review_attempt(attempt.id))
    import json
    payload = json.loads(gateway.messages[1].content)
    assert payload["correct_answer"] is None
    assert payload["reference_solution"] == solution
    assert payload["reference_basis"] == "REFERENCE_SOLUTION"
    assert gateway.calls == 1
    assert len(review.step_grades) == 2
    assert attempt.status == "SUBMITTED"


def test_unanswered_feedback_rejects_source_with_solution_only(monkeypatch):
    attempt, session, gateway = fixture_case(monkeypatch)
    reference = AnswerReference("CANONICAL", uuid4(), "Find derivative", "", "Power rule gives y'=3x^2", "c" * 64)
    monkeypatch.setattr("app.math_solutions.answer_grounded_ai.resolve_answer_reference", lambda *_args, **_kwargs: reference)
    with pytest.raises(ApplicationError) as error:
        asyncio.run(UnansweredAIService(session, gateway).review_attempt(attempt.id))
    assert error.value.code == "GRADING_ANSWER_AVAILABLE"
    assert gateway.calls == 0


def test_quote_evidence_matches_unicode_and_vietnamese_decimals():
    from app.math_solutions.answer_grounded_ai import _is_valid_evidence_quote
    source = "Theo yêu cầu làm tròn, $x\\approx6{,}67$ cm với $x\\le10$."
    # Model returns unicode approx and standard comma
    quote1 = "x≈6,67 cm"
    assert _is_valid_evidence_quote(quote1, source) is True
    # Model returns unicode inequality
    quote2 = "x≤10"
    assert _is_valid_evidence_quote(quote2, source) is True
