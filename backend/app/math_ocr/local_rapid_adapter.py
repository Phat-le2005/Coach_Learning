"""CPU-first formula OCR with ONNXRuntime (no PyTorch, CUDA or paid API).

RapidLaTeXOCR uses pix2tex-family weights converted to ONNX. Model files must
be provisioned *before* serving requests; no checkpoint download is performed
by an EduMS request. Inference is restricted to one call per worker to avoid
CPU and memory spikes on low-spec demo machines.
"""
from __future__ import annotations

from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from threading import Lock
from typing import Callable

from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkStroke
from app.math_ocr.adapter import MathOCRAdapter
from app.math_ocr.local_render import render_formula_png
from app.math_ocr.schemas import OCRRecognizeResponse
from app.math_solutions.schemas import StepKind

_CPU_INFERENCE_LOCK = Lock()
_CPU_MODEL_LOCK = Lock()
_REQUIRED_WEIGHTS = (
    "encoder.onnx", "decoder.onnx", "image_resizer.onnx", "tokenizer.json",
)


@lru_cache(maxsize=1)
def _get_cpu_model():
    """Lazy load ONNX sessions only after explicit model preinstallation."""
    spec = find_spec("rapid_latex_ocr")
    if spec is None or spec.origin is None:
        raise ApplicationError(
            503, "OCR_LOCAL_DEPENDENCY_MISSING",
            "Install optional RapidLaTeXOCR CPU dependencies to enable local OCR.",
        )
    models = Path(spec.origin).resolve().parent / "models"
    if any(not (models / name).is_file() for name in _REQUIRED_WEIGHTS):
        raise ApplicationError(
            503, "OCR_LOCAL_MODEL_UNAVAILABLE",
            "Local OCR model weights are not provisioned. See OCR CPU setup guide.",
        )
    try:
        from rapid_latex_ocr import LaTeXOCR
        return LaTeXOCR()
    except Exception as exc:
        raise ApplicationError(
            503, "OCR_LOCAL_MODEL_UNAVAILABLE",
            "The local OCR model could not be loaded.",
        ) from exc


def _predict_png(png: bytes):
    with _CPU_MODEL_LOCK:
        model = _get_cpu_model()
    return model(png)


class LocalRapidOCRAdapter(MathOCRAdapter):
    """Run one short mathematical expression through the local ONNX model."""

    def __init__(self, predictor: Callable[[bytes], object] | None = None) -> None:
        self._predictor = predictor or _predict_png

    def recognize(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        # Do not infer text from topic/number of strokes. Render actual drawing.
        if not _CPU_INFERENCE_LOCK.acquire(blocking=False):
            raise ApplicationError(
                503, "OCR_LOCAL_BUSY",
                "Local OCR is processing another expression. Retry shortly.",
            )
        try:
            image_bytes = render_formula_png(strokes)
            try:
                result = self._predictor(image_bytes)
            except ApplicationError:
                raise
            except Exception as exc:
                raise ApplicationError(
                    503, "OCR_LOCAL_MODEL_UNAVAILABLE",
                    "Local OCR could not process this expression.",
                ) from exc

            # RapidLaTeXOCR officially returns (latex, elapsed_seconds).
            if not isinstance(result, tuple) or len(result) != 2:
                raise ApplicationError(
                    422, "OCR_NOT_RECOGNIZED", "No mathematical expression was recognized.",
                )
            latex, _elapsed = result
            if not isinstance(latex, str):
                raise ApplicationError(
                    422, "OCR_NOT_RECOGNIZED", "No mathematical expression was recognized.",
                )
            latex = latex.strip()
            if (latex.startswith(r"\(") and latex.endswith(r"\)")) or (
                latex.startswith(r"\[") and latex.endswith(r"\]")
            ):
                latex = latex[2:-2].strip()
            if not latex or len(latex) > 8000:
                raise ApplicationError(
                    422, "OCR_NOT_RECOGNIZED", "No usable mathematical expression was recognized.",
                )
            return OCRRecognizeResponse(
                latex=latex,
                confidence=0.0,  # Provider doesn't expose calibrated confidence.
                suggested_step_type=StepKind.EXPLANATION,
                explanation_text=None,
                detected_symbols=[],
            )
        finally:
            _CPU_INFERENCE_LOCK.release()
