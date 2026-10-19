"""Offline contract tests for the REAL Mathpix strokes transport (no paid API calls)."""
import json
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.adapter import MockMathOCRAdapter
from app.math_ocr.dependencies import get_ocr_adapter
from app.math_ocr.mathpix_adapter import MathpixStrokesAdapter
from app.math_solutions.schemas import StepKind


def _ink(tool: str = "PEN") -> InkStroke:
    return InkStroke(
        id=uuid4(),
        tool=tool,
        color="#142130",
        width=2,
        points=[InkPoint(x=0.1, y=0.2), InkPoint(x=0.3, y=0.4)],
    )


def test_stroke_payload_matches_mathpix_contract_and_privacy_opt_out():
    data = json.loads(MathpixStrokesAdapter._body([_ink(), _ink("HIGHLIGHTER")]))
    assert data["strokes"]["strokes"] == {
        "x": [[79.4, 238.2]],
        "y": [[224.6, 449.2]],
    }
    assert data["metadata"]["improve_mathpix"] is False


def test_real_adapter_parses_latex_from_provider_not_topic_template():
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url == "https://api.mathpix.com/v3/strokes"
        assert request.headers["app_id"] == "test-app"
        assert request.headers["app_key"] == "test-key"
        data = json.loads(request.content)
        assert data["strokes"]["strokes"]["x"]
        assert data["metadata"]["improve_mathpix"] is False
        return httpx.Response(
            200,
            json={"latex_styled": r"x^{7}+9", "confidence": 0.81},
        )

    adapter = MathpixStrokesAdapter(
        app_id="test-app",
        app_key="test-key",
        transport=httpx.MockTransport(respond),
    )
    result = adapter.recognize([_ink()], hint_topic="CALCULUS_DERIVATIVE")
    assert result.latex == r"x^{7}+9"
    assert result.confidence == 0.81
    assert result.suggested_step_type == StepKind.DERIVATIVE_CALCULATION
    assert result.explanation_text is None
    assert result.detected_symbols == []
    assert len(calls) == 1


def test_text_math_delimiters_without_styled_latex():
    adapter = MathpixStrokesAdapter(
        app_id="id", app_key="key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"text": r"\( z^{2}-1 \)"}
            )
        ),
    )
    result = adapter.recognize([_ink()])
    assert result.latex == r"z^{2}-1"
    assert result.confidence == 0  # Missing confidence never fabricated.


@pytest.mark.parametrize(
    "status,payload,code",
    [
        (401, {}, "OCR_PROVIDER_AUTH_FAILED"),
        (429, {}, "OCR_PROVIDER_BUSY"),
        (500, {}, "OCR_PROVIDER_ERROR"),
        (200, {}, "OCR_NOT_RECOGNIZED"),
        (200, {"error": "invalid-strokes"}, "OCR_NOT_RECOGNIZED"),
    ],
)
def test_fail_closed_when_provider_rejects_or_cannot_recognize(status, payload, code):
    adapter = MathpixStrokesAdapter(
        app_id="id", app_key="key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=payload)
        ),
    )
    with pytest.raises(ApplicationError) as exc:
        adapter.recognize([_ink()])
    assert exc.value.code == code


def test_timeout_is_a_controlled_provider_error():
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout", request=request)

    adapter = MathpixStrokesAdapter(
        app_id="id", app_key="key",
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(ApplicationError) as exc:
        adapter.recognize([_ink()])
    assert exc.value.status_code == 504
    assert exc.value.code == "OCR_PROVIDER_TIMEOUT"


def test_oversized_provider_response_is_rejected():
    adapter = MathpixStrokesAdapter(
        app_id="id", app_key="key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=b"x" * (65 * 1024)
            )
        ),
    )
    with pytest.raises(ApplicationError) as exc:
        adapter.recognize([_ink()])
    assert exc.value.code == "OCR_INVALID_RESPONSE"


def test_highlighters_alone_are_not_recognized():
    with pytest.raises(ApplicationError) as exc:
        MathpixStrokesAdapter._body([_ink("HIGHLIGHTER")])
    assert exc.value.code == "NO_PEN_STROKES_FOR_OCR"


def test_no_mathpix_credentials_fail_closed(monkeypatch):
    monkeypatch.setenv("MATH_OCR_PROVIDER", "mathpix")
    get_settings.cache_clear()
    with pytest.raises(ApplicationError) as exc:
        get_ocr_adapter()
    assert exc.value.code == "OCR_NOT_CONFIGURED"
    get_settings.cache_clear()


def test_default_test_provider_keeps_legacy_mock_tests_working(monkeypatch):
    monkeypatch.setenv("MATH_OCR_PROVIDER", "disabled")
    get_settings.cache_clear()
    assert isinstance(get_ocr_adapter(), MockMathOCRAdapter)
    get_settings.cache_clear()


def test_production_never_serves_mock(monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_name="db",
        database_user="user",
        jwt_secret_key="z" * 64,
        math_ocr_provider="mock",
    )
    monkeypatch.setattr("app.math_ocr.dependencies.get_settings", lambda: settings)
    with pytest.raises(ApplicationError) as exc:
        get_ocr_adapter()
    assert exc.value.code == "OCR_NOT_CONFIGURED"
