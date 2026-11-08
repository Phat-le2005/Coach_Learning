"""Tests for GeminiMathOCRAdapter adopting math-ocr-pipeline architecture."""

from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest

from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.gemini_adapter import GeminiMathOCRAdapter, GeminiOCRJsonOutput
from app.math_solutions.schemas import StepKind


def test_rasterize_and_compute_telemetry():
    adapter = GeminiMathOCRAdapter(api_key="test-key")

    stroke_1 = InkStroke(
        id=uuid4(),
        tool="PEN",
        color="#000000",
        width=3,
        points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.5, y=0.1)],  # Horizontal bar
    )
    stroke_2 = InkStroke(
        id=uuid4(),
        tool="PEN",
        color="#000000",
        width=2,
        points=[InkPoint(x=0.2, y=0.2)],  # Dot
    )
    stroke_highlighter = InkStroke(
        id=uuid4(),
        tool="HIGHLIGHTER",
        color="#ffff00",
        width=10,
        points=[InkPoint(x=0.3, y=0.3)],
    )

    image_bytes, mime_type, telemetry = adapter._rasterize_and_optimize(
        [stroke_1, stroke_2, stroke_highlighter]
    )

    assert len(image_bytes) > 0
    assert mime_type in ("image/webp", "image/png")
    assert telemetry["pen_strokes"] == 2
    assert telemetry["horizontal_bars"] >= 1
    assert telemetry["dots"] >= 1


def test_to_response_mapping():
    adapter = GeminiMathOCRAdapter(api_key="test-key")

    # Derivative calculation
    resp = adapter._to_response(
        {
            "latex": "y' = 3x^2 - 6x",
            "suggested_step_type": "DERIVATIVE_CALCULATION",
            "explanation_text": "Tính đạo hàm",
            "detected_symbols": ["y'", "3x^2", "-6x"],
            "confidence": 0.99,
        },
        strokes=[],
    )
    assert resp.latex == "y' = 3x^2 - 6x"
    assert resp.suggested_step_type == StepKind.DERIVATIVE_CALCULATION
    assert resp.confidence == 0.99
    assert resp.explanation_text == "Tính đạo hàm"
    assert "y'" in resp.detected_symbols

    # Fallback step kind heuristic
    resp2 = adapter._to_response(
        {
            "latex": "f'(x) = 0 \\Leftrightarrow x = 0 \\lor x = 2",
            "suggested_step_type": "UNKNOWN_KIND",
            "confidence": 0.95,
        },
        strokes=[],
    )
    assert resp2.suggested_step_type == StepKind.ROOT_FINDING


def test_gemini_recognize_with_mocked_client():
    adapter = GeminiMathOCRAdapter(api_key="test-fake-key", model_name="gemini-3.8-flash")

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"latex": "\\\\int x dx = \\\\frac{x^2}{2} + C", "suggested_step_type": "EXPLANATION", "confidence": 0.97, "detected_symbols": ["\\\\int", "x", "dx"]}'
    mock_client.models.generate_content.return_value = mock_resp

    stroke = InkStroke(
        id=uuid4(),
        tool="PEN",
        color="#000000",
        width=2,
        points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.2, y=0.2)],
    )

    with patch("app.math_ocr.gemini_adapter._get_genai_client", return_value=mock_client):
        result = adapter.recognize([stroke], hint_topic="CALCULUS_INTEGRAL")

    assert result.latex == "\\int x dx = \\frac{x^2}{2} + C"
    assert result.suggested_step_type == StepKind.EXPLANATION
    assert result.confidence == 0.97
    assert "\\int" in result.detected_symbols
    assert mock_client.models.generate_content.called
