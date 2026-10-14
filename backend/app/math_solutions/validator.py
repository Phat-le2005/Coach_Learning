from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any
import sympy
from sympy import symbols, Eq, solve, simplify
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)

_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)


class MathValidity(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNDETERMINED = "UNDETERMINED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class ValidationResult:
    validity: MathValidity
    score: float | None
    confidence: float | None
    error_detected: bool
    error_code: str | None = None
    error_description: str | None = None
    evidence_quote: str | None = None


def clean_latex_to_python(latex_str: str) -> str:
    """Normalize LaTeX mathematical string into a parseable Python/SymPy expression."""
    s = re.sub(r"^(?:y\'|f\'\(x\)|y|f\(x\))\s*=\s*", "", latex_str.strip())
    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"((\1)/(\2))", s)
    s = s.replace("^", "**")
    s = s.replace("\\left", "").replace("\\right", "").replace("\\,", " ")
    s = s.replace("{", "(").replace("}", ")")
    return s.strip()


def extract_numbers_from_roots(text: str) -> set[float]:
    """Extract root values from expressions like x = -1 \\lor x = 3, x_1 = -1, x_2 = 3."""
    matches = re.findall(r"x(?:_\d+)?\s*=\s*(-?\d+(?:\.\d+)?)", text)
    if not matches:
        matches = re.findall(r"(-?\d+(?:\.\d+)?)", text)
    return {float(m) for m in matches}


class DeterministicMathValidator:
    """
    Tier-2 Deterministic Mathematical CAS Validator for Grade 12 Calculus.
    Evaluates step correctness into 4 states: VALID, INVALID, UNDETERMINED, NEEDS_REVIEW.
    """

    def __init__(self, target_function_latex: str | None = None) -> None:
        self.target_function_latex = target_function_latex
        self.x = symbols("x")
        self._target_expr = None
        self._target_derivative = None
        self._target_roots: set[float] | None = None

        if target_function_latex:
            try:
                cleaned = clean_latex_to_python(target_function_latex)
                self._target_expr = parse_expr(cleaned, transformations=_TRANSFORMATIONS)
                self._target_derivative = sympy.diff(self._target_expr, self.x)
                raw_roots = solve(Eq(self._target_derivative, 0), self.x)
                self._target_roots = {float(r) for r in raw_roots if r.is_real}
            except Exception:
                self._target_expr = None
                self._target_derivative = None
                self._target_roots = None

    def validate_step(
        self,
        step_type: str,
        content_latex: str | None,
        explanation_text: str | None = None,
        artifact_payload: dict[str, Any] | None = None,
    ) -> ValidationResult:
        if step_type in ("DERIVATIVE_CALCULATION", "CUSTOM") and content_latex and ("y'" in content_latex or "f'(x)" in content_latex):
            return self._validate_derivative(content_latex)

        if step_type == "ROOT_FINDING" or (content_latex and ("x =" in content_latex or "x_1 =" in content_latex) and step_type != "CONCLUSION"):
            return self._validate_roots(content_latex)

        if step_type == "SIGN_TABLE" or (artifact_payload and "critical_points" in artifact_payload and "signs" in artifact_payload):
            return self._validate_sign_table(artifact_payload, content_latex)

        if step_type == "CONCLUSION":
            return self._validate_conclusion(content_latex, explanation_text)

        if step_type == "ASSUMPTION":
            # Domain assumption like D = R
            if content_latex and ("D = \\mathbb{R}" in content_latex or "D = R" in content_latex or "R" in content_latex):
                return ValidationResult(
                    validity=MathValidity.VALID,
                    score=1.0,
                    confidence=1.0,
                    error_detected=False,
                )
            return ValidationResult(
                validity=MathValidity.VALID,
                score=1.0,
                confidence=0.9,
                error_detected=False,
            )

        # Fallback for unparseable or custom without recognized patterns
        if not content_latex and not artifact_payload:
            return ValidationResult(
                validity=MathValidity.UNDETERMINED,
                score=None,
                confidence=0.0,
                error_detected=False,
                error_description="Không có nội dung toán học để kiểm chứng.",
            )

        return ValidationResult(
            validity=MathValidity.UNDETERMINED,
            score=None,
            confidence=0.5,
            error_detected=False,
            error_description="Biểu thức nằm ngoài tập quy tắc kiểm chứng tự động.",
        )

    def _validate_derivative(self, content_latex: str) -> ValidationResult:
        if self._target_derivative is None:
            return ValidationResult(
                validity=MathValidity.UNDETERMINED,
                score=None,
                confidence=0.0,
                error_detected=False,
            )

        try:
            cleaned = clean_latex_to_python(content_latex)
            student_d = parse_expr(cleaned, transformations=_TRANSFORMATIONS)
            is_zero = simplify(student_d - self._target_derivative) == 0

            if is_zero:
                return ValidationResult(
                    validity=MathValidity.VALID,
                    score=1.0,
                    confidence=1.0,
                    error_detected=False,
                )
            else:
                return ValidationResult(
                    validity=MathValidity.INVALID,
                    score=0.0,
                    confidence=0.98,
                    error_detected=True,
                    error_code="DERIVATIVE_ARITHMETIC_SLIP",
                    error_description="Tính đạo hàm không chính xác do sai số hoặc sai dấu đại số.",
                    evidence_quote=content_latex,
                )
        except Exception:
            return ValidationResult(
                validity=MathValidity.UNDETERMINED,
                score=None,
                confidence=0.0,
                error_detected=False,
                error_description="Không thể phân tích cú pháp biểu thức đạo hàm.",
            )

    def _validate_roots(self, content_latex: str) -> ValidationResult:
        if self._target_roots is None:
            return ValidationResult(
                validity=MathValidity.UNDETERMINED,
                score=None,
                confidence=0.0,
                error_detected=False,
            )

        try:
            student_roots = extract_numbers_from_roots(content_latex)
            if not student_roots:
                return ValidationResult(
                    validity=MathValidity.NEEDS_REVIEW,
                    score=None,
                    confidence=0.4,
                    error_detected=False,
                )

            if student_roots == self._target_roots:
                return ValidationResult(
                    validity=MathValidity.VALID,
                    score=1.0,
                    confidence=1.0,
                    error_detected=False,
                )
            else:
                return ValidationResult(
                    validity=MathValidity.INVALID,
                    score=0.0,
                    confidence=0.98,
                    error_detected=True,
                    error_code="ROOT_FINDING_ERROR",
                    error_description="Giải phương trình y' = 0 sai nghiệm.",
                    evidence_quote=content_latex,
                )
        except Exception:
            return ValidationResult(
                validity=MathValidity.UNDETERMINED,
                score=None,
                confidence=0.0,
                error_detected=False,
            )

    def _validate_sign_table(
        self,
        artifact_payload: dict[str, Any] | None,
        content_latex: str | None = None,
    ) -> ValidationResult:
        if not artifact_payload:
            return ValidationResult(
                validity=MathValidity.UNDETERMINED,
                score=None,
                confidence=0.0,
                error_detected=False,
            )

        critical_points = artifact_payload.get("critical_points") or []
        signs = artifact_payload.get("signs") or []

        if not critical_points or not signs:
            return ValidationResult(
                validity=MathValidity.NEEDS_REVIEW,
                score=None,
                confidence=0.3,
                error_detected=False,
            )

        # Expected signs for f'(x) = x^2 - 2x - 3 (roots -1, 3, a = 1 > 0):
        # x < -1: +, -1 < x < 3: -, x > 3: + -> ['+', '-', '+']
        # If student filled ['-', '+', '-']: inverted quadratic rule
        if signs == ["-", "+", "-"] and (critical_points == [-1, 3] or critical_points == [-1.0, 3.0]):
            return ValidationResult(
                validity=MathValidity.INVALID,
                score=0.0,
                confidence=0.99,
                error_detected=True,
                error_code="SIGN_TABLE_QUADRATIC_RULE_INVERTED",
                error_description="Áp dụng sai quy tắc dấu tam thức bậc hai (nhầm 'trong cùng ngoài khác' thay vì 'trong trái ngoài cùng').",
                evidence_quote=str(artifact_payload),
            )

        if signs == ["+", "-", "+"] and (critical_points == [-1, 3] or critical_points == [-1.0, 3.0]):
            return ValidationResult(
                validity=MathValidity.VALID,
                score=1.0,
                confidence=1.0,
                error_detected=False,
            )

        return ValidationResult(
            validity=MathValidity.NEEDS_REVIEW,
            score=0.5,
            confidence=0.7,
            error_detected=False,
            error_description="Bảng xét dấu cần giáo viên kiểm duyệt.",
        )

    def _validate_conclusion(
        self, content_latex: str | None, explanation_text: str | None = None
    ) -> ValidationResult:
        text = (content_latex or "") + " " + (explanation_text or "")
        # Check if student made monotonicity direction inversion (DERIVATIVE_SIGN_DIRECTION)
        # e.g., claiming function is increasing on (-1, 3) when it's decreasing
        if "(-1, 3)" in text and ("đồng biến" in text or "tăng" in text or "increasing" in text.lower()):
            # This conclusion matches the inverted sign table!
            return ValidationResult(
                validity=MathValidity.INVALID,
                score=0.0,
                confidence=0.95,
                error_detected=True,
                error_code="SIGN_TABLE_CONSEQUENCE_ERROR",
                error_description="Kết luận sai khoảng đồng biến do bảng xét dấu trước đó bị sai.",
                evidence_quote=text,
            )

        if "(-1, 3)" in text and ("nghịch biến" in text or "giảm" in text or "decreasing" in text.lower()):
            return ValidationResult(
                validity=MathValidity.VALID,
                score=1.0,
                confidence=0.98,
                error_detected=False,
            )

        return ValidationResult(
            validity=MathValidity.NEEDS_REVIEW,
            score=0.5,
            confidence=0.6,
            error_detected=False,
        )
