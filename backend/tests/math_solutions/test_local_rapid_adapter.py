"""CPU-focused, no-download OCR provider contract tests."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.dependencies import get_ocr_adapter, get_request_ocr_adapter
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
    assert result.alternative_latex == []


def test_alternatives_are_on_demand_and_never_replace_primary(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"original")
    monkeypatch.setattr(module, "alternative_formula_pngs", lambda raw: (b"half", b"large"))
    seen = []

    def predictor(raw):
        seen.append(raw)
        return {b"original": "x^{2}", b"half": "x^2", b"large": r"\chi^{2}"}[raw], 0.1

    adapter = LocalRapidOCRAdapter(predictor)
    default = adapter.recognize([sample()])
    assert default.latex == "x^{2}"
    assert default.alternative_latex == []
    assert seen == [b"original"]

    reviewed = adapter.recognize_with_alternatives([sample()])
    assert reviewed.latex == "x^{2}"
    assert reviewed.alternative_latex == ["x^2", r"\chi^{2}"]
    assert reviewed.confidence == 0.0
    assert seen == [b"original", b"original", b"half", b"large"]


def test_failed_alternate_keeps_first_suggestion(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"original")
    monkeypatch.setattr(module, "alternative_formula_pngs", lambda raw: (b"half", b"large"))

    def predictor(raw):
        if raw == b"large":
            raise RuntimeError("private model detail")
        return ("x^2" if raw == b"original" else "x^2"), 0.1

    result = LocalRapidOCRAdapter(predictor).recognize_with_alternatives([sample()])
    assert result.latex == "x^2"
    assert result.alternative_latex == []


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

def test_request_provider_uses_mounted_app_settings(monkeypatch):
    app_settings = Settings(
        _env_file=None, app_env="development", database_name="edums_test",
        database_user="tester", math_ocr_provider="local_rapid",
    )
    monkeypatch.setattr(
        "app.math_ocr.dependencies.get_settings",
        lambda: Settings(
            _env_file=None, app_env="development", database_name="edums_test",
            database_user="tester", math_ocr_provider="mock",
        ),
    )
    app = SimpleNamespace(state=SimpleNamespace(settings=app_settings))
    request = Request({"type": "http", "app": app})
    assert isinstance(get_request_ocr_adapter(request), LocalRapidOCRAdapter)

@pytest.mark.parametrize("model_latex", [
    r"\bigvee\bigcap = \land + \vdash",
    r"\widehat{\mathbf{v}}} = \mathcal{v}",
])
def test_rapid_adapter_abstains_on_hallucinated_or_malformed_latex(monkeypatch, model_latex):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"ink-image")
    with pytest.raises(ApplicationError) as exc:
        LocalRapidOCRAdapter(lambda raw: (model_latex, 0.8)).recognize([sample()])
    assert exc.value.code == "OCR_NOT_RECOGNIZED"


def test_rapid_adapter_abstains_on_renderable_operator_hallucination(monkeypatch):
    import app.math_ocr.local_rapid_adapter as module
    monkeypatch.setattr(module, "render_formula_png", lambda strokes: b"ink-image")
    hallucination = r"{\lor\lnot\ \ {\times}\ \ +\ A}"
    with pytest.raises(ApplicationError) as exc:
        LocalRapidOCRAdapter(lambda raw: (hallucination, 0.8)).recognize([sample()])
    assert exc.value.code == "OCR_NOT_RECOGNIZED"
