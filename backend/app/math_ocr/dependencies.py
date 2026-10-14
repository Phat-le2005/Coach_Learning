from functools import lru_cache
from app.math_ocr.adapter import MathOCRAdapter, MockMathOCRAdapter


@lru_cache
def get_ocr_adapter() -> MathOCRAdapter:
    """Return configured Math OCR adapter instance."""
    return MockMathOCRAdapter()
