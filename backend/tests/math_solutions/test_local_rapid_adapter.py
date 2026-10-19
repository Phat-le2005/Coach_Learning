"""CPU-focused, no-download OCR provider contract tests."""
from uuid import uuid4
import pytest

from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.dependencies import get_ocr_adapter
from app.math_ocr.local_rapid_adapter import LocalRapidOCRAdapter


def sample(tool="PEN"):
    return InkStroke(
        id=uuid4(), tool=tool, color="#000000", width=2,
        points=[InkPoint(x=0.1, y=0.1), InkPoint(x=0.2, y=0.15)],
    )


def test_cpu_provider_selected_without_api_key(monkeypatch):
    settings = Settings(
        _env_file=None, database_name="edums_test", database_user="tester",
        math_ocr_provider="local_rapid",
    )
    monkeypatch.setattr("app.math_ocr.dependencies.get_settings", lambda: settings)
    assert isinstance(get_ocr_adapter(), LocalRapidOCRAdapter)


def test_rapid_adapter_returns_model_text_not_problem_hint(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"real-render")
    captured = []
    def predictor(image_bytes):
        captured.append(image_bytes)
        return r"x^{17}+3", 0.23
    result = LocalRapidOCRAdapter(predictor).recognize(
        [sample()], hint_topic="CALCULUS_DERIVATIVE"
    )
    assert result.latex == r"x^{17}+3"
    assert result.confidence == 0.0
    assert result.explanation_text is None
    assert captured == [b"real-render"]


def test_rapid_adapter_fails_when_result_missing(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"image")
    with pytest.raises(ApplicationError) as exc:
        LocalRapidOCRAdapter(lambda raw: ("", 0.0)).recognize([sample()])
    assert exc.value.code == "OCR_NOT_RECOGNIZED"


def test_rapid_adapter_rejects_malformed_output(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"image")
    with pytest.raises(ApplicationError) as exc:
        LocalRapidOCRAdapter(lambda raw: r"x^2").recognize([sample()])
    assert exc.value.code == "OCR_NOT_RECOGNIZED"


def test_rapid_adapter_is_nonblocking_when_cpu_busy(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"image")
    assert module._CPU_INFERENCE_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(ApplicationError) as exc:
            LocalRapidOCRAdapter(lambda raw: ("x", 0.1)).recognize([sample()])
        assert exc.value.code == "OCR_LOCAL_BUSY"
    finally:
        module._CPU_INFERENCE_LOCK.release()


def test_rapid_adapter_hides_internal_errors(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"image")
    def fail(raw):
        raise RuntimeError("private token or model path")
    with pytest.raises(ApplicationError) as exc:
        LocalRapidOCRAdapter(fail).recognize([sample()])
    assert exc.value.code == "OCR_LOCAL_MODEL_UNAVAILABLE"
    assert "private token" not in exc.value.message
