"""Real online handwriting recognition using Mathpix's vector stroke API.

The request contains *only* normalized PEN coordinates and the explicit privacy
opt-out. Credentials never leave the backend. Recognition is always advisory.
"""
from __future__ import annotations

import json
import math
from typing import Any

import httpx

from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkStroke
from app.math_ocr.adapter import MathOCRAdapter
from app.math_ocr.schemas import OCRRecognizeResponse
from app.math_solutions.schemas import StepKind


MATHPIX_STROKES_URL = "https://api.mathpix.com/v3/strokes"
MAX_PROVIDER_REQUEST_BYTES = 450 * 1024  # Below Mathpix's 512 KiB limit
MAX_PROVIDER_RESPONSE_BYTES = 64 * 1024
A4_WIDTH = 794
A4_HEIGHT = 1123


class MathpixStrokesAdapter(MathOCRAdapter):
    """Math OCR for existing EduMS vector ink, without image rendering."""

    def __init__(
        self,
        *,
        app_id: str,
        app_key: str,
        timeout_seconds: float = 12.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not app_id or not app_key:
            raise ValueError("Mathpix credentials are required")
        self._app_id = app_id
        self._app_key = app_key
        self._timeout = timeout_seconds
        self._transport = transport

    @staticmethod
    def _body(strokes: list[InkStroke]) -> bytes:
        xs: list[list[float]] = []
        ys: list[list[float]] = []
        point_count = 0
        # Highlighters are visual annotations, not mathematical handwriting.
        for stroke in strokes:
            if stroke.tool != "PEN":
                continue
            point_count += len(stroke.points)
            if point_count > 15000 or len(xs) >= 400:
                raise ApplicationError(422, "OCR_TOO_MANY_POINTS", "Ink selection is too large to recognize.")
            xs.append([round(p.x * A4_WIDTH, 2) for p in stroke.points])
            ys.append([round(p.y * A4_HEIGHT, 2) for p in stroke.points])
        if not xs:
            raise ApplicationError(422, "NO_PEN_STROKES_FOR_OCR", "Select handwritten pen strokes to recognize.")
        body = json.dumps(
            {"strokes": {"strokes": {"x": xs, "y": ys}},
             "metadata": {"improve_mathpix": False}},
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(body) > MAX_PROVIDER_REQUEST_BYTES:
            raise ApplicationError(413, "OCR_STROKES_TOO_LARGE", "Too much ink for one recognition request.")
        return body

    @staticmethod
    def _parse(payload: Any, hint_topic: str | None) -> OCRRecognizeResponse:
        if not isinstance(payload, dict):
            raise ApplicationError(502, "OCR_INVALID_RESPONSE", "OCR provider returned invalid data.")
        if payload.get("error") or payload.get("error_info"):
            raise ApplicationError(422, "OCR_NOT_RECOGNIZED", "The handwriting could not be recognized. Try a smaller selection.")
        raw = payload.get("latex_styled") or payload.get("text")
        if not isinstance(raw, str):
            raise ApplicationError(422, "OCR_NOT_RECOGNIZED", "No mathematical expression was recognized.")
        latex = raw.strip()
        if (latex.startswith(r"\(") and latex.endswith(r"\)")) or (
            latex.startswith(r"\[") and latex.endswith(r"\]")
        ):
            latex = latex[2:-2].strip()
        if not latex or len(latex) > 8000:
            raise ApplicationError(422, "OCR_NOT_RECOGNIZED", "No usable mathematical expression was recognized.")
        estimate = payload.get("confidence")
        confidence = (
            float(estimate)
            if type(estimate) in (float, int) and math.isfinite(float(estimate)) and 0 <= estimate <= 1
            else 0.0
        )
        step_kind = (
            StepKind.DERIVATIVE_CALCULATION
            if hint_topic == "CALCULUS_DERIVATIVE"
            else StepKind.EXPLANATION
        )
        # No fabricated explanations or symbol lists; these are not model outputs.
        return OCRRecognizeResponse(
            latex=latex,
            confidence=confidence,
            suggested_step_type=step_kind,
            explanation_text=None,
            detected_symbols=[],
        )

    def recognize(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        body = self._body(strokes)
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout, connect=min(5.0, self._timeout)),
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                with client.stream(
                    "POST",
                    MATHPIX_STROKES_URL,
                    content=body,
                    headers={
                        "app_id": self._app_id,
                        "app_key": self._app_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                ) as response:
                    if response.status_code in (401, 403):
                        raise ApplicationError(503, "OCR_PROVIDER_AUTH_FAILED", "Math recognition is temporarily unavailable.")
                    if response.status_code == 429:
                        raise ApplicationError(503, "OCR_PROVIDER_BUSY", "Math recognition is busy. Please retry later.")
                    if response.status_code != 200:
                        raise ApplicationError(502, "OCR_PROVIDER_ERROR", "Math recognition provider failed.")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        if len(raw) + len(chunk) > MAX_PROVIDER_RESPONSE_BYTES:
                            raise ApplicationError(502, "OCR_INVALID_RESPONSE", "OCR provider response is too large.")
                        raw.extend(chunk)
            data = json.loads(raw)
        except httpx.TimeoutException as exc:
            raise ApplicationError(504, "OCR_PROVIDER_TIMEOUT", "Math recognition timed out.") from exc
        except httpx.RequestError as exc:
            raise ApplicationError(503, "OCR_PROVIDER_UNAVAILABLE", "Math recognition is currently unavailable.") from exc
        except (ValueError, UnicodeError) as exc:
            raise ApplicationError(502, "OCR_INVALID_RESPONSE", "OCR provider returned invalid data.") from exc
        return self._parse(data, hint_topic)
