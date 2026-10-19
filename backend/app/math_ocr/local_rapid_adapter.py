"""CPU-first formula OCR with ONNXRuntime (no PyTorch, CUDA or paid API).

RapidLaTeXOCR uses pix2tex-family weights converted to ONNX. Model files must
be provisioned *before* serving requests; no checkpoint download is performed
by an EduMS request. Inference is restricted to one call per worker to avoid
CPU and memory spikes on low-spec demo machines.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from app.core.config import BACKEND_DIR, get_settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkStroke
from app.math_ocr.adapter import MathOCRAdapter
from app.math_ocr.local_render import render_formula_png
from app.math_ocr.local_preprocess import alternative_formula_pngs
from app.math_ocr.schemas import OCRRecognizeResponse
from app.math_solutions.schemas import StepKind

_CPU_INFERENCE_LOCK = Lock()
_CPU_MODEL_LOCK = Lock()
logger = logging.getLogger(__name__)
_REQUIRED_WEIGHTS = (
    "encoder.onnx", "decoder.onnx", "image_resizer.onnx", "tokenizer.json",
)
_MIN_MODEL_BYTES = {
    "encoder.onnx": 1_000_000,
    "decoder.onnx": 1_000_000,
    "image_resizer.onnx": 1_000_000,
    "tokenizer.json": 1_000,
}


def inspect_cpu_model_files(model_dir: Path | None = None) -> tuple[Path, dict[str, int]]:
    """Check the four preinstalled files without importing or starting the model."""
    spec = find_spec("rapid_latex_ocr")
    if spec is None or spec.origin is None:
        raise ApplicationError(
            503, "OCR_LOCAL_DEPENDENCY_MISSING",
            "Install optional RapidLaTeXOCR CPU dependencies to enable local OCR.",
        )
    if model_dir is None:
        model_dir = get_settings().math_ocr_model_dir
    if model_dir is None:
        models = Path(spec.origin).resolve().parent / "models"
    else:
        models = model_dir if model_dir.is_absolute() else BACKEND_DIR / model_dir
    models = models.resolve()
    sizes = {
        name: (models / name).stat().st_size if (models / name).is_file() else 0
        for name in _REQUIRED_WEIGHTS
    }
    if any(sizes[name] < _MIN_MODEL_BYTES[name] for name in _REQUIRED_WEIGHTS):
        raise ApplicationError(
            503, "OCR_LOCAL_MODEL_UNAVAILABLE",
            "Local OCR model files are missing or incomplete. See OCR CPU setup guide.",
        )
    return models, sizes


@lru_cache(maxsize=1)
def _get_cpu_model(model_dir: str) -> Any:
    """Load ONNX sessions from checked paths; never invoke upstream auto-download."""
    models, _ = inspect_cpu_model_files(Path(model_dir))
    try:
        from rapid_latex_ocr import LaTeXOCR
        return LaTeXOCR(
            image_resizer_path=models / "image_resizer.onnx",
            encoder_path=models / "encoder.onnx",
            decoder_path=models / "decoder.onnx",
            tokenizer_json=models / "tokenizer.json",
        )
    except ImportError as exc:
        raise ApplicationError(
            503, "OCR_LOCAL_DEPENDENCY_MISSING",
            "Optional OCR CPU dependencies are incomplete.",
        ) from exc
    except Exception as exc:
        raise ApplicationError(
            503, "OCR_LOCAL_MODEL_UNAVAILABLE",
            "The local OCR model could not be loaded.",
        ) from exc


def load_cpu_model(model_dir: Path | None = None) -> Any:
    """Explicit prewarm entry point shared by the API and benchmark CLI."""
    models, _ = inspect_cpu_model_files(model_dir)
    return _get_cpu_model(str(models))


def _predict_png(png: bytes) -> tuple[str, float]:
    with _CPU_MODEL_LOCK:
        model = load_cpu_model()
    return model(png)


def _usable_latex(result: object) -> str | None:
    if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], str):
        return None
    latex = result[0].strip()
    if (latex.startswith(r"\(") and latex.endswith(r"\)")) or (
        latex.startswith(r"\[") and latex.endswith(r"\]")
    ):
        latex = latex[2:-2].strip()
    return latex if latex and len(latex) <= 8000 else None


class LocalRapidOCRAdapter(MathOCRAdapter):
    """Run one short mathematical expression through the local ONNX model."""

    def __init__(self, predictor: Callable[[bytes], object] | None = None) -> None:
        self._predictor = predictor or _predict_png

    def recognize(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        return self._recognize(strokes, include_alternatives=False)

    def recognize_with_alternatives(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        return self._recognize(strokes, include_alternatives=True)

    def _recognize(
        self,
        strokes: list[InkStroke],
        *,
        include_alternatives: bool,
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

            latex = _usable_latex(result)
            if latex is None:
                raise ApplicationError(
                    422, "OCR_NOT_RECOGNIZED", "No usable mathematical expression was recognized.",
                )
            alternatives: list[str] = []
            if include_alternatives:
                try:
                    for variant_png in alternative_formula_pngs(image_bytes):
                        candidate = _usable_latex(self._predictor(variant_png))
                        if candidate and candidate != latex and candidate not in alternatives:
                            alternatives.append(candidate)
                except Exception:
                    # A failed optional retry must not discard the usable first suggestion.
                    logger.warning("Optional local OCR retry failed")
            return OCRRecognizeResponse(
                latex=latex,
                confidence=0.0,  # Provider doesn't expose calibrated confidence.
                suggested_step_type=StepKind.EXPLANATION,
                explanation_text=None,
                detected_symbols=[],
                alternative_latex=alternatives,
            )
        finally:
            _CPU_INFERENCE_LOCK.release()
