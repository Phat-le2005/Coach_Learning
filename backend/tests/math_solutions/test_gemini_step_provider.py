"""Real Gemini adapter: HTTP is mocked, never a canned grade in production."""

import asyncio
import json

import httpx
import pytest

from app.ai.dependencies import create_ai_provider
from app.ai.exceptions import AIConfigurationError, AIOutputValidationError
from app.ai.gemini_provider import GeminiProvider
from app.ai.types import AIMessage
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.math_solutions.answer_grounded_ai import AIGradeOutput


@pytest.fixture
def settings_kwargs():
    return {"database_name": "test", "database_user": "test", "_env_file": None}


def test_real_provider_requires_explicit_key(settings_kwargs):
    with pytest.raises(AIConfigurationError):
        create_ai_provider(Settings(**settings_kwargs, ai_provider="gemini", ai_api_key=""))
    assert isinstance(create_ai_provider(Settings(**settings_kwargs, ai_provider="gemini", ai_api_key="secret")), GeminiProvider)
    with pytest.raises(AIConfigurationError):
        create_ai_provider(Settings(**settings_kwargs, ai_provider="unknown"))


def test_structured_request_uses_key_header_and_validates_answer():
    seen = {}

    def handle(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps({"steps": [
            {"step_index": 1, "verdict": "VALID", "score": 1.0, "confidence": 0.9,
             "student_quote": "x", "answer_quote": "x", "feedback": "Matches."}
        ]})}]}}]})

    provider = GeminiProvider("server-secret", transport=httpx.MockTransport(handle))
    output = asyncio.run(provider.generate_structured(
        [AIMessage(role="system", content="Evaluate against answer"), AIMessage(role="user", content="Student step x")],
        AIGradeOutput, "gemini-3.6-flash", temperature=0.0,
    ))
    assert output.steps[0].verdict == "VALID"
    assert seen["url"].endswith("/gemini-3.6-flash:generateContent")
    assert seen["key"] == "server-secret"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert "server-secret" not in json.dumps(seen["body"])


@pytest.mark.parametrize("status, code", [(429, "AI_RATE_LIMIT_EXCEEDED"), (403, "AI_CONFIGURATION_ERROR"), (404, "AI_CONFIGURATION_ERROR"), (503, "AI_SERVICE_UNAVAILABLE")])
def test_provider_failure_cannot_create_grade(status, code):
    provider = GeminiProvider("secret", transport=httpx.MockTransport(lambda request: httpx.Response(status)))
    with pytest.raises(ApplicationError) as error:
        asyncio.run(provider.generate_structured(
            [AIMessage(role="user", content="Work")], AIGradeOutput, "gemini-3.6-flash"
        ))
    assert error.value.code == code


def test_malformed_provider_json_is_rejected():
    provider = GeminiProvider("secret", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
    ))
    with pytest.raises(AIOutputValidationError):
        asyncio.run(provider.generate_structured(
            [AIMessage(role="user", content="Work")], AIGradeOutput, "gemini-3.6-flash"
        ))