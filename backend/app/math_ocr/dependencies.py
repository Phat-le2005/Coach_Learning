"""OCR provider selection for the current FastAPI application."""

from fastapi import Request
from app.core.config import Settings, get_settings
from app.core.exceptions import ApplicationError
from app.math_ocr.adapter import MathOCRAdapter, MockMathOCRAdapter
from app.math_ocr.mathpix_adapter import MathpixStrokesAdapter
from app.math_ocr.local_pix2tex_adapter import LocalPix2TexAdapter
from app.math_ocr.local_rapid_adapter import LocalRapidOCRAdapter


def get_ocr_adapter(settings: Settings | None = None) -> MathOCRAdapter:
    settings = settings or get_settings()
    provider = settings.math_ocr_provider

    if provider == "local_rapid":
        return LocalRapidOCRAdapter()

    if provider == "local_pix2tex":
        return LocalPix2TexAdapter()

    if provider == "mathpix":
        app_id = settings.mathpix_app_id.strip()
        app_key = settings.mathpix_app_key.get_secret_value()
        if not app_id or not app_key:
            raise ApplicationError(
                503, "OCR_NOT_CONFIGURED", "Math recognition provider is not configured."
            )
        return MathpixStrokesAdapter(
            app_id=app_id,
            app_key=app_key,
            timeout_seconds=settings.math_ocr_timeout_seconds,
        )

    if provider == "mock" or (provider == "disabled" and settings.app_env == "test"):
        if settings.app_env == "production":
            raise ApplicationError(
                503, "OCR_NOT_CONFIGURED", "Mock OCR is unavailable in production."
            )
        return MockMathOCRAdapter()

    raise ApplicationError(
        503, "OCR_NOT_CONFIGURED", "Math recognition is not configured."
    )


def get_request_ocr_adapter(request: Request) -> MathOCRAdapter:
    """Use the mounted v2 app configuration, including in isolated tests."""
    return get_ocr_adapter(request.app.state.settings)
