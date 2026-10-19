"""Free local Math OCR regression tests (never download model weights in CI)."""
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkPoint, InkStroke
from app.math_ocr.dependencies import get_ocr_adapter
from app.math_ocr.local_pix2tex_adapter import LocalPix2TexAdapter


def _stroke(tool="PEN"):
    return InkStroke(
        id=uuid4(),
        tool=tool,
        color="#152031",
        width=2,
        points=[InkPoint(x=0.1, y=0.2), InkPoint(x=0.18, y=0.3)],
    )


def test_local_provider_selected_with_no_mathpix_credentials(monkeypatch):
    config = Settings(
        _env_file=None,
        app_env="development",
        database_name="test",
        database_user="test",
        math_ocr_provider="local_pix2tex",
    )
    monkeypatch.setattr("app.math_ocr.dependencies.get_settings", lambda: config)
    assert isinstance(get_ocr_adapter(), LocalPix2TexAdapter)


def test_local_provider_accepts_real_predicted_latex_but_not_topic_template():
    pytest.importorskip("PIL")
    observed = []

    def predict(image):
        observed.append((image.mode, image.size))
        return r"x^{11}+7"

    adapter = LocalPix2TexAdapter(predictor=predict)
    result = adapter.recognize([_stroke(), _stroke("HIGHLIGHTER")], hint_topic="CALCULUS_DERIVATIVE")
    assert result.latex == r"x^{11}+7"
    assert result.confidence == 0.0  # No invented calibrated confidence.
    assert result.explanation_text is None
    assert result.detected_symbols == []
    assert observed[0][0] == "RGB"
    assert observed[0][1][0] < 794
    assert observed[0][1][1] < 1123


def test_local_provider_rejects_empty_prediction():
    pytest.importorskip("PIL")
    adapter = LocalPix2TexAdapter(predictor=lambda image: "   ")
    with pytest.raises(ApplicationError) as exc:
        adapter.recognize([_stroke()])
    assert exc.value.code == "OCR_NOT_RECOGNIZED"


def test_local_provider_rejects_no_pen_strokes():
    adapter = LocalPix2TexAdapter(predictor=lambda image: r"x^2")
    with pytest.raises(ApplicationError) as exc:
        adapter.recognize([_stroke("HIGHLIGHTER")])
    assert exc.value.code in ("NO_PEN_STROKES_FOR_OCR", "OCR_LOCAL_DEPENDENCY_MISSING")


def test_local_model_failures_do_not_expose_sensitive_exception_messages():
    pytest.importorskip("PIL")

    def broken_predict(image):
        raise RuntimeError("secret-token-or-private-model-file-path")

    adapter = LocalPix2TexAdapter(predictor=broken_predict)
    with pytest.raises(ApplicationError) as exc:
        adapter.recognize([_stroke()])
    assert exc.value.code == "OCR_LOCAL_MODEL_UNAVAILABLE"
    assert "secret-token" not in exc.value.message
