"""Hybrid routing spends AI budget only when verified grading cannot finish."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ai.exceptions import AIConfigurationError
from app.core.exceptions import ApplicationError
from app.math_solutions import ai_review_router as router
from app.math_solutions.answer_grounded_ai import AIStepGrade, AnswerGroundedReview
from app.math_solutions.answer_reference import AnswerReference
from app.math_solutions.models import SolutionAttempt


class FakeSession:
    def __init__(self, attempt):
        self.attempt = attempt

    def get(self, model, key):
        return self.attempt if model is SolutionAttempt and key == self.attempt.id else None

    def scalar(self, statement):
        return None


@pytest.fixture
def scenario(monkeypatch):
    attempt = SimpleNamespace(id=uuid4(), student_id=uuid4(), status="SUBMITTED", rubric_id=uuid4())
    session = FakeSession(attempt)
    student = SimpleNamespace(id=uuid4())
    reference = AnswerReference("CANONICAL", uuid4(), "Find y' for y=x^3", "y'=3x^2", None, "a" * 64)
    calls = {"limit": 0, "model": 0, "deterministic": 0}
    monkeypatch.setattr(router, "MathSolutionService", lambda _session: SimpleNamespace(get=lambda *_: None))
    monkeypatch.setattr(router, "resolve_answer_reference", lambda *_args, **_kwargs: reference)
    monkeypatch.setattr(router, "_save_cache_to_disk", lambda *_args: None)
    monkeypatch.setattr(router, "_REVIEW_CACHE", {})
    limiter = SimpleNamespace(check_rate_limit=lambda *_args, **_kwargs: calls.__setitem__("limit", calls["limit"] + 1))
    settings = SimpleNamespace(ai_rate_limit_per_minute=5, ai_daily_requests_limit_per_student=20)
    return attempt, session, student, reference, calls, limiter, settings


def _review(attempt_id, sha, *, unanswered=False):
    grade = AIStepGrade(
        step_index=1, verdict="NEEDS_REVIEW" if unanswered else "VALID",
        score=None if unanswered else 1.0, confidence=0.0 if unanswered else 0.9,
        student_quote="3x^2", answer_quote="y=x^3" if unanswered else "3x^2",
        feedback="Check the rule." if unanswered else "Matches the reference.",
    )
    return AnswerGroundedReview(attempt_id, sha, (grade,), unanswered)


def test_approved_rubric_and_verified_steps_finish_without_ai_or_rate_limit(monkeypatch, scenario):
    attempt, session, student, ref, calls, limiter, settings = scenario
    decision = SimpleNamespace(final_score=0.9)

    class Evaluator:
        def __init__(self, _session):
            pass

        def evaluate_attempt(self, _attempt_id):
            calls["deterministic"] += 1
            return decision

    monkeypatch.setattr(router, "MathEvaluatorService", Evaluator)
    monkeypatch.setattr(router, "_final_review", lambda *_args: router.AIReviewRead(
        attempt_id=attempt.id, step_grades=[router.StepSuggestionRead(
            step_index=1, verdict="VALID", score=1, confidence=1,
            feedback="Verified by SymPy.")], needs_teacher_review=False,
        is_final=True, review_source="DETERMINISTIC", final_score=0.9,
    ))
    result = asyncio.run(router.review_submitted_steps(attempt.id, student, session, None, settings, limiter))
    assert result.is_final and result.final_score == 0.9
    assert result.review_source == "DETERMINISTIC"
    assert calls == {"limit": 0, "model": 0, "deterministic": 1}


def test_uncertain_math_falls_back_to_one_answer_grounded_call_and_caches(monkeypatch, scenario):
    attempt, session, student, ref, calls, limiter, settings = scenario

    class Evaluator:
        def __init__(self, _session):
            pass

        def evaluate_attempt(self, _attempt_id):
            calls["deterministic"] += 1
            raise ApplicationError(409, "GRADING_REVIEW_REQUIRED", "Uncertain step")

    class AI:
        def __init__(self, _session, _gateway):
            pass

        async def review_attempt(self, attempt_id):
            calls["model"] += 1
            return _review(attempt_id, ref.content_sha256)

    monkeypatch.setattr(router, "MathEvaluatorService", Evaluator)
    monkeypatch.setattr(router, "AnswerGroundedAIService", AI)
    gateway = SimpleNamespace(provider=object())
    first = asyncio.run(router.review_submitted_steps(attempt.id, student, session, gateway, settings, limiter))
    second = asyncio.run(router.review_submitted_steps(attempt.id, student, session, gateway, settings, limiter))
    assert first == second
    assert not first.is_final and first.final_score is None
    assert first.review_source == "ANSWER_GROUNDED_AI"
    assert calls == {"limit": 1, "model": 1, "deterministic": 2}


def test_missing_answer_only_returns_unscored_preliminary_feedback(monkeypatch, scenario):
    attempt, session, student, ref, calls, limiter, settings = scenario
    empty = AnswerReference(ref.source_kind, ref.source_id, ref.problem_content, "", None, "b" * 64)
    monkeypatch.setattr(router, "resolve_answer_reference", lambda *_args, **_kwargs: empty)

    class NoAnswerAI:
        def __init__(self, _session, _gateway):
            pass

        async def review_attempt(self, attempt_id):
            calls["model"] += 1
            return _review(attempt_id, empty.content_sha256, unanswered=True)

    monkeypatch.setattr(router, "UnansweredAIService", NoAnswerAI)
    monkeypatch.setattr(router, "MathEvaluatorService", lambda *_args: pytest.fail("No official grading without answer"))
    result = asyncio.run(router.review_submitted_steps(attempt.id, student, session,
                                                       SimpleNamespace(provider=object()), settings, limiter))
    assert result.review_source == "UNANSWERED_AI"
    assert result.needs_teacher_review and not result.is_final
    assert result.final_score is None
    assert result.step_grades[0].verdict == "NEEDS_REVIEW" and result.step_grades[0].score is None
    assert calls == {"limit": 1, "model": 1, "deterministic": 0}


def test_response_schema_rejects_ai_final_grade_and_unanswered_step_score():
    with pytest.raises(ValidationError):
        router.AIReviewRead(attempt_id=uuid4(), step_grades=[], needs_teacher_review=False,
                            is_final=True, review_source="ANSWER_GROUNDED_AI", final_score=1)
    with pytest.raises(ValidationError):
        router.AIReviewRead(attempt_id=uuid4(), step_grades=[router.StepSuggestionRead(
            step_index=1, verdict="VALID", score=1, confidence=1, feedback="Looks right")],
            needs_teacher_review=True, review_source="UNANSWERED_AI")
    with pytest.raises(ValidationError):
        router.AIReviewRead(attempt_id=uuid4(), step_grades=[router.StepSuggestionRead(
            step_index=1, verdict="VALID", score=1, confidence=0.9, feedback="Tentative")],
            needs_teacher_review=False, review_source="ANSWER_GROUNDED_AI")


def test_mismatched_rubric_stops_before_ai_or_rate_limit(monkeypatch, scenario):
    attempt, session, student, _ref, calls, limiter, settings = scenario

    class Evaluator:
        def __init__(self, _session):
            pass

        def evaluate_attempt(self, _attempt_id):
            raise ApplicationError(409, "GRADING_SOURCE_MISMATCH", "Rubric belongs to another problem")

    monkeypatch.setattr(router, "MathEvaluatorService", Evaluator)
    with pytest.raises(ApplicationError) as error:
        asyncio.run(router.review_submitted_steps(attempt.id, student, session, object(), settings, limiter))
    assert error.value.code == "GRADING_SOURCE_MISMATCH"
    assert calls["limit"] == 0 and calls["model"] == 0


def test_final_response_uses_persisted_decision_and_step_evaluations():
    evaluation = SimpleNamespace(
        math_validity="VALID", score=1.0, confidence=1.0,
        error_description=None,
    )
    session = SimpleNamespace(execute=lambda _query: SimpleNamespace(all=lambda: [(1, evaluation)]))
    decision = SimpleNamespace(
        rubric_id=uuid4(), decision_source="AUTOMATED_CONSENSUS", final_score=0.7,
    )
    result = router._final_review(session, uuid4(), decision)
    assert result.is_final and result.review_source == "DETERMINISTIC"
    assert result.final_score == 0.7
    assert result.step_grades[0].score == 1.0


def test_missing_gemini_configuration_only_blocks_the_ai_fallback(monkeypatch, scenario):
    attempt, session, student, _ref, calls, limiter, settings = scenario
    attempt.rubric_id = None
    monkeypatch.setattr(router, "get_ai_gateway_singleton", lambda _settings: (_ for _ in ()).throw(
        AIConfigurationError("No key")))
    assert router.get_step_ai_gateway(settings) is None
    with pytest.raises(ApplicationError) as error:
        asyncio.run(router.review_submitted_steps(attempt.id, student, session, None, settings, limiter))
    assert error.value.code == "REAL_AI_PROVIDER_REQUIRED"
    assert calls["limit"] == 0



def test_solution_only_ai_is_grounded_but_does_not_write_mastery(monkeypatch, scenario):
    attempt, session, student, ref, calls, limiter, settings = scenario
    attempt.rubric_id = None
    solution_reference = AnswerReference(ref.source_kind, ref.source_id, ref.problem_content, "", "The derivative is 3x^2.", "c" * 64)
    monkeypatch.setattr(router, "resolve_answer_reference", lambda *_args, **_kwargs: solution_reference)
    class AI:
        def __init__(self, _session, _gateway):
            pass
        async def review_attempt(self, attempt_id):
            calls["model"] += 1
            return _review(attempt_id, solution_reference.content_sha256)
    monkeypatch.setattr(router, "AnswerGroundedAIService", AI)
    monkeypatch.setattr(router, "UnansweredAIService", lambda *_args: pytest.fail("A solution exists; unanswered routing is incorrect"))
    monkeypatch.setattr("app.math_solutions.mastery_backdrop.MasteryBackdropService", lambda *_args: pytest.fail("Solution-only AI must not create mastery evidence"))
    result = asyncio.run(router.review_submitted_steps(attempt.id, student, session, SimpleNamespace(provider=object()), settings, limiter))
    assert result.review_source == "ANSWER_GROUNDED_AI"
    assert result.is_final is False and result.final_score is None
    assert all(step.score is None for step in result.step_grades)
    assert calls["model"] == calls["limit"] == 1
