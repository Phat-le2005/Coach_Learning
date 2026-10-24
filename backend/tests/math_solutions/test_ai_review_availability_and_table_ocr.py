"""Trusted-answer readiness and opt-in visual transcription boundaries."""

import asyncio
from base64 import b64encode
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.ai.gemini_provider import GeminiProvider
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


def png_bytes():
    out = BytesIO()
    Image.new("RGB", (48, 32), "white").save(out, format="PNG")
    return out.getvalue()


def test_table_png_rejects_invalid_and_accepts_real_image():
    image = png_bytes()
    assert router._decode_ink_png(b64encode(image).decode("ascii")) == image
    for invalid in ("not base64", b64encode(image[:-12]).decode("ascii"),
                    b64encode(b"not PNG" * 50).decode("ascii")):
        with pytest.raises(ApplicationError) as error:
            router._decode_ink_png(invalid)
        assert error.value.code == "INVALID_INK_IMAGE"


def test_gemini_image_is_inline_png_and_output_is_unverified():
    image = png_bytes()
    captured = {}

    def respond(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps({
            "recognized": True, "x_row": "-inf, ?, +inf", "derivative_row": "+, 0, -",
            "function_row": "up, down", "uncertainties": ["middle x value"],
        })}]}}]})

    provider = GeminiProvider("server-only-key", transport=httpx.MockTransport(respond))
    result = asyncio.run(provider.generate_image_structured("Transcribe only", image,
        router.VariationTableDraft, "gemini-3.6-flash"))
    assert result.recognized and result.uncertainties == ["middle x value"]
    parts = captured["payload"]["contents"][0]["parts"]
    assert parts[1]["inlineData"] == {"mimeType": "image/png", "data": b64encode(image).decode("ascii")}
    assert "server-only-key" not in json.dumps(captured["payload"])
