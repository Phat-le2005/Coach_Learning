from abc import ABC, abstractmethod
from typing import Any
from app.math_ink.schemas import InkStroke
from app.math_ocr.schemas import OCRRecognizeResponse
from app.math_solutions.schemas import StepKind


class MathOCRAdapter(ABC):
    """Abstract adapter interface for Math Handwriting OCR recognition."""

    @abstractmethod
    def recognize(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        """Recognize vector ink strokes into LaTeX formula and explanation text."""
        pass

    def recognize_with_alternatives(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        """Optional, on-demand suggestions; providers without this feature keep one result."""
        return self.recognize(strokes, hint_topic=hint_topic)


class MockMathOCRAdapter(MathOCRAdapter):
    """Deterministic, high-accuracy mock adapter for testing, development and CI."""

    def recognize(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        stroke_count = len(strokes)
        total_points = sum(len(s.points) for s in strokes)

        # Topic-driven deterministic formulas for Grade 12 Math
        if hint_topic == "CALCULUS_INTEGRAL":
            return OCRRecognizeResponse(
                latex=r"\int (3x^2 - 2x + 1) \, dx = x^3 - x^2 + x + C",
                confidence=0.96,
                suggested_step_type=StepKind.EXPLANATION,
                explanation_text="Áp dụng công thức nguyên hàm cơ bản từng số hạng.",
                detected_symbols=[r"\int", "3x^2", "-2x", "+1", "dx", "x^3", "C"],
            )

        if hint_topic == "CALCULUS_DERIVATIVE":
            return OCRRecognizeResponse(
                latex=r"y' = 3x^2 - 6x = 3x(x - 2)",
                confidence=0.98,
                suggested_step_type=StepKind.DERIVATIVE_CALCULATION,
                explanation_text="Tính đạo hàm bậc nhất của hàm số và phân tích nhân tử.",
                detected_symbols=["y'", "3x^2", "-6x", "=", "3x(x-2)"],
            )

        if hint_topic == "SPATIAL_GEOMETRY":
            return OCRRecognizeResponse(
                latex=r"\vec{n}_{(P)} = [\vec{u}, \vec{v}] = (1; -2; 2)",
                confidence=0.94,
                suggested_step_type=StepKind.EXPLANATION,
                explanation_text="Tích có hướng của hai vectơ chỉ phương để tìm vectơ pháp tuyến.",
                detected_symbols=[r"\vec{n}", r"\vec{u}", r"\vec{v}", "(1;-2;2)"],
            )

        if hint_topic == "PROBABILITY":
            return OCRRecognizeResponse(
                latex=r"P(A|B) = \frac{P(A \cap B)}{P(B)} = \frac{0.3}{0.5} = 0.6",
                confidence=0.95,
                suggested_step_type=StepKind.EXPLANATION,
                explanation_text="Công thức xác suất có điều kiện.",
                detected_symbols=["P(A|B)", r"\frac{P(A \cap B)}{P(B)}", "0.6"],
            )

        # Dynamic heuristic based on stroke and point counts
        if stroke_count == 1:
            return OCRRecognizeResponse(
                latex=r"x = 2",
                confidence=0.92,
                suggested_step_type=StepKind.CONCLUSION,
                explanation_text="Nghiệm của phương trình.",
                detected_symbols=["x", "=", "2"],
            )

        if stroke_count <= 4:
            return OCRRecognizeResponse(
                latex=r"f'(x) = 0 \Leftrightarrow x = 0 \lor x = 2",
                confidence=0.95,
                suggested_step_type=StepKind.ROOT_FINDING,
                explanation_text="Giải phương trình f'(x) = 0 tìm điểm cực trị.",
                detected_symbols=["f'(x)", "=", "0", r"\Leftrightarrow", r"\lor"],
            )

        return OCRRecognizeResponse(
            latex=r"\int (2x + 1) \, dx = x^2 + x + C",
            confidence=0.97,
            suggested_step_type=StepKind.EXPLANATION,
            explanation_text="Tính nguyên hàm từng thành phần theo bảng công thức chuẩn.",
            detected_symbols=[r"\int", "2x+1", "dx", "x^2+x+C"],
        )
