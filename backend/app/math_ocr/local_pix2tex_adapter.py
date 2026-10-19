"""Offline formula OCR, using the open-source pix2tex model on our own host.

pix2tex/Pillow/PyTorch are optional; the main backend and CI can run without
a GPU or downloading model weights. This adapter never contacts a paid API.
"""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from threading import Lock
from typing import Callable

from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkStroke
from app.math_ocr.adapter import MathOCRAdapter
from app.math_ocr.local_render import render_formula_png
from app.math_ocr.schemas import OCRRecognizeResponse
from app.math_solutions.schemas import StepKind

_PREDICTION_LOCK = Lock()


@lru_cache(maxsize=1)
def _get_model():
    try:
        from pix2tex.cli import LatexOCR
    except ImportError as exc:
        raise ApplicationError(
            503, "OCR_LOCAL_DEPENDENCY_MISSING",
            "Install the optional local OCR model dependencies first.",
        ) from exc
    try:
        return LatexOCR()
    except Exception as exc:
        # Never expose model file paths or runtime environment data.
        raise ApplicationError(
            503, "OCR_LOCAL_MODEL_UNAVAILABLE",
            "The local OCR model could not be loaded.",
        ) from exc


def _predict(image) -> str:
    model = _get_model()
    # A single model instance may be shared by concurrent FastAPI requests.
    with _PREDICTION_LOCK:
        return model(image)


class LocalPix2TexAdapter(MathOCRAdapter):
    """Recognize *drawn content* locally. No math hints create answer text."""

    def __init__(self, predictor: Callable | None = None) -> None:
        self._predictor = predictor or _predict

    def recognize(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        image_bytes = render_formula_png(strokes)
        try:
            from PIL import Image
        except ImportError as exc:
            raise ApplicationError(
                503, "OCR_LOCAL_DEPENDENCY_MISSING",
                "Install the optional local OCR image dependencies.",
            ) from exc
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image.load()
                predicted = self._predictor(image.convert("RGB"))
        except ApplicationError:
            raise
        except Exception as exc:
            raise ApplicationError(
                503, "OCR_LOCAL_MODEL_UNAVAILABLE",
                "Local OCR could not process this expression.",
            ) from exc

        if not isinstance(predicted, str):
            raise ApplicationError(
                422, "OCR_NOT_RECOGNIZED", "No mathematical expression was recognized."
            )
        latex = predicted.strip()
        if not latex or len(latex) > 8000:
            raise ApplicationError(
                422, "OCR_NOT_RECOGNIZED", "No usable mathematical expression was recognized."
            )
        if (latex.startswith(r"\(") and latex.endswith(r"\)")) or (
            latex.startswith(r"\[") and latex.endswith(r"\]")
        ):
            latex = latex[2:-2].strip()
        if not latex:
            raise ApplicationError(
                422, "OCR_NOT_RECOGNIZED", "No usable mathematical expression was recognized."
            )
        # pix2tex does not provide calibrated confidence through this API.
        # Zero means UNKNOWN, not an accuracy estimate.
        return OCRRecognizeResponse(
            latex=latex,
            confidence=0.0,
            suggested_step_type=StepKind.EXPLANATION,
            explanation_text=None,
            detected_symbols=[],
        )
