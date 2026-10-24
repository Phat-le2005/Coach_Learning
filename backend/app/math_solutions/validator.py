import ast
from dataclasses import dataclass
from enum import StrEnum
import math
import re
from typing import Any

import sympy
from sympy import Eq, Integer, Rational, simplify, solve, symbols


_MAX_EXPRESSION_LENGTH = 512
_MAX_AST_NODES = 128
_MAX_EXPONENT = 12
_MAX_ABSOLUTE_CONSTANT = 1_000_000


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
    """Normalize the supported subset of LaTeX into a mathematical expression."""
    match = re.search(r"(?:y'|f'\(x\)|y|f\(x\))\s*=\s*([^$.;\n\r]+)", latex_str)
    if match:
        s = match.group(1)
    else:
        s = re.sub(r"^(?:y'|f'\(x\)|y|f\(x\))\s*=\s*", "", latex_str.strip())
    s = s.replace("$", "")
    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"((\1)/(\2))", s)
    s = s.replace("^", "**")
    s = s.replace("\\left", "").replace("\\right", "").replace("\\,", " ")
    s = s.replace("{", "(").replace("}", ")")
    return s.strip()


def _safe_parse_expression(expression: str, variable: sympy.Symbol) -> sympy.Expr:
    """Parse a deliberately small polynomial grammar without evaluating Python code.

    SymPy's parse_expr uses eval internally and must not receive untrusted student input.
    This parser accepts numeric constants, x, parentheses, unary signs, and + - * / **.
    Implicit multiplication such as 2x and (1/3)x is normalized before Python AST parsing.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("A non-empty mathematical expression is required.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError("Mathematical expression is too long.")

    normalized = expression.strip().replace("^", "**")
    normalized = re.sub(r"(?<=\d)\s*(?=[x(])", "*", normalized)
    normalized = re.sub(r"(?<=x)\s*(?=\()", "*", normalized)
    normalized = re.sub(r"(?<=\))\s*(?=[x\d(])", "*", normalized)

    try:
        tree = ast.parse(normalized, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ValueError("Unsupported mathematical syntax.") from exc

    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise ValueError("Mathematical expression is too complex.")

    def build(node: ast.AST) -> sympy.Expr:
        if isinstance(node, ast.Expression):
            return build(node.body)

        if isinstance(node, ast.Constant):
            value = node.value
            if type(value) is int:
                if abs(value) > _MAX_ABSOLUTE_CONSTANT:
                    raise ValueError("Numeric constant is out of range.")
                return Integer(value)
            if type(value) is float:
                if not math.isfinite(value) or abs(value) > _MAX_ABSOLUTE_CONSTANT:
                    raise ValueError("Numeric constant is out of range.")
                return Rational(str(value))
            raise ValueError("Only real numeric constants are supported.")

        if isinstance(node, ast.Name):
            if node.id != "x":
                raise ValueError("Only the variable x is supported.")
            return variable

        if isinstance(node, ast.UnaryOp):
            operand = build(node.operand)
            if isinstance(node.op, ast.UAdd):
                return operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError("Unsupported unary operator.")

        if isinstance(node, ast.BinOp):
            left = build(node.left)
            right = build(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValueError("Division by zero is not supported.")
                return left / right
            if isinstance(node.op, ast.Pow):
                if not right.is_Integer or abs(int(right)) > _MAX_EXPONENT:
                    raise ValueError("Only bounded integer exponents are supported.")
                return left**right
            raise ValueError("Unsupported binary operator.")

        # Calls, attributes, subscripts, comprehensions, and every other Python AST
        # construct are intentionally rejected.
        raise ValueError("Unsupported mathematical syntax.")

    return build(tree)


def extract_numbers_from_roots(text: str) -> set[float]:
    r"""Extract root values from expressions like x = -1 \lor x = 3, x_1 = -1, x_2 = 3."""
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
                self._target_expr = _safe_parse_expression(cleaned, self.x)
                self._target_derivative = sympy.diff(self._target_expr, self.x)
                raw_roots = solve(Eq(self._target_derivative, 0), self.x)
                self._target_roots = {float(r) for r in raw_roots if r.is_real}
            except Exception:
                self._target_expr = None
                self._target_derivative = None
                self._target_roots = None

    @property
    def supports_polynomial_target(self) -> bool:
        """Automatic grading is currently verified only for one-variable polynomials."""
        return self._target_expr is not None and bool(self._target_expr.is_polynomial(self.x))

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
            normalized = re.sub(r"\s+", "", content_latex or "")
            if self.supports_polynomial_target and normalized in {
                r"D=\mathbb{R}", "D=R",
            }:
                return ValidationResult(
                    validity=MathValidity.VALID,
                    score=1.0,
                    confidence=1.0,
                    error_detected=False,
                )
            return ValidationResult(
                validity=MathValidity.NEEDS_REVIEW,
                score=None,
                confidence=0.0,
                error_detected=False,
                error_description="The stated domain needs review.",
            )
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
            student_d = _safe_parse_expression(cleaned, self.x)
            is_zero = simplify(student_d - self._target_derivative) == 0

            if is_zero:
                return ValidationResult(
                    validity=MathValidity.VALID,
                    score=1.0,
                    confidence=1.0,
                    error_detected=False,
                )
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
        """Verify quadratic derivative signs only when the exercise is known.

        Unsupported functions, missing target expressions and malformed student
        artifacts must never be graded against a fixed sample sign table.
        """
        needs_review = ValidationResult(
            validity=MathValidity.NEEDS_REVIEW,
            score=None,
            confidence=0.0,
            error_detected=False,
            error_description="Chưa đủ dữ liệu để tự động kiểm chứng bảng xét dấu.",
        )
        if not isinstance(artifact_payload, dict) or self._target_derivative is None:
            return needs_review

        critical_points = artifact_payload.get("critical_points")
        signs = artifact_payload.get("signs")
        if not isinstance(critical_points, list) or not isinstance(signs, list):
            return needs_review
        if len(critical_points) != 2 or len(signs) != 3:
            return needs_review
        if any(type(p) not in (int, float) or not math.isfinite(p) for p in critical_points):
            return needs_review
        if any(sign not in ("+", "-") for sign in signs):
            return needs_review

        try:
            # This evaluator currently supports only quadratic derivatives with
            # two distinct real roots. All other cases require human review.
            polynomial = sympy.Poly(self._target_derivative, self.x)
            if polynomial.degree() != 2 or self._target_roots is None:
                return needs_review
            roots = sorted(self._target_roots)
            points = [float(p) for p in critical_points]
            if len(roots) != 2 or not roots[0] < roots[1] or not points[0] < points[1]:
                return needs_review
            if any(not math.isclose(point, root, rel_tol=1e-9, abs_tol=1e-9)
                   for point, root in zip(points, roots)):
                return needs_review

            leading = polynomial.LC()
            if leading.is_positive:
                expected_signs = ["+", "-", "+"]
            elif leading.is_negative:
                expected_signs = ["-", "+", "-"]
            else:
                return needs_review
        except (ValueError, TypeError, sympy.PolynomialError):
            return needs_review

        if signs == expected_signs:
            return ValidationResult(
                validity=MathValidity.VALID,
                score=1.0,
                confidence=1.0,
                error_detected=False,
            )

        if signs == ["-" if sign == "+" else "+" for sign in expected_signs]:
            return ValidationResult(
                validity=MathValidity.INVALID,
                score=0.0,
                confidence=0.99,
                error_detected=True,
                error_code="SIGN_TABLE_QUADRATIC_RULE_INVERTED",
                error_description="Đã đảo ngược dấu của đạo hàm trên tất cả các khoảng.",
                evidence_quote=str(artifact_payload),
            )

        return ValidationResult(
            validity=MathValidity.INVALID,
            score=0.0,
            confidence=0.98,
            error_detected=True,
            error_code="SIGN_TABLE_SIGN_ERROR",
            error_description="Dấu đạo hàm không khớp với hàm số của đề bài.",
            evidence_quote=str(artifact_payload),
        )

    def _validate_conclusion(
        self, content_latex: str | None, explanation_text: str | None = None
    ) -> ValidationResult:
        """Conservatively verify a single inner-interval monotonicity claim."""
        needs_review = ValidationResult(
            validity=MathValidity.NEEDS_REVIEW,
            score=None,
            confidence=0.0,
            error_detected=False,
            error_description="Kết luận ngoài phạm vi tự động kiểm chứng.",
        )
        if self._target_derivative is None or self._target_roots is None:
            return needs_review

        try:
            poly = sympy.Poly(self._target_derivative, self.x)
            roots = sorted(self._target_roots)
            if poly.degree() != 2 or len(roots) != 2 or not roots[0] < roots[1]:
                return needs_review
            lead = poly.LC()
            if lead.is_positive:
                expected_increasing = False
            elif lead.is_negative:
                expected_increasing = True
            else:
                return needs_review
        except (ValueError, TypeError, sympy.PolynomialError):
            return needs_review

        # Only grade a single, explicit claim about the interval between roots.
        text = (content_latex or "") + " " + (explanation_text or "")
        intervals = re.findall(
            r"\(\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*\)",
            text,
        )
        if not intervals:
            return needs_review
        unique_intervals = set(intervals)
        if len(unique_intervals) != 1:
            return needs_review
        left, right = map(float, intervals[0])
        if not (math.isclose(left, roots[0], abs_tol=1e-9, rel_tol=1e-9)
                and math.isclose(right, roots[1], abs_tol=1e-9, rel_tol=1e-9)):
            return needs_review

        lower = (content_latex or "").lower()
        increasing = any(term in lower for term in ("đồng biến", "tăng", "increasing"))
        decreasing = any(term in lower for term in ("nghịch biến", "giảm", "decreasing"))
        if increasing == decreasing or "không " in lower:
            return needs_review
        if increasing == expected_increasing:
            return ValidationResult(
                validity=MathValidity.VALID,
                score=1.0,
                confidence=0.98,
                error_detected=False,
            )
        return ValidationResult(
            validity=MathValidity.INVALID,
            score=0.0,
            confidence=0.95,
            error_detected=True,
            error_code="SIGN_TABLE_CONSEQUENCE_ERROR",
            error_description="Kết luận chiều biến thiên không phù hợp với dấu đạo hàm.",
            evidence_quote=text,
        )
