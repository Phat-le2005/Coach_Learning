import pytest
from sympy import symbols

from app.math_solutions.validator import (
    DeterministicMathValidator,
    MathValidity,
    _safe_parse_expression,
)


def test_safe_parser_supports_polynomial_and_implicit_multiplication():
    x = symbols("x")
    assert _safe_parse_expression("x^2 - 2x - 3", x) == x**2 - 2*x - 3
    assert _safe_parse_expression("(1/3)x^3 - x^2 - 3x + 1", x) == x**3/3 - x**2 - 3*x + 1


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo unsafe')",
        "x.__class__",
        "open('/tmp/unsafe', 'w')",
        "[x for x in (1, 2)]",
        "y + 1",
        "x**999",
        "x**(1/2)",
        "1/0",
    ],
)
def test_safe_parser_rejects_unsupported_or_unsafe_syntax(expression):
    with pytest.raises(ValueError):
        _safe_parse_expression(expression, symbols("x"))


def test_safe_parser_rejects_oversized_expressions():
    with pytest.raises(ValueError):
        _safe_parse_expression("x+" + "1+" * 300 + "x", symbols("x"))


def test_validator_still_handles_correct_and_incorrect_derivatives():
    validator = DeterministicMathValidator(
        target_function_latex=r"\\frac{1}{3}x^3 - x^2 - 3x + 1"
    )

    correct = validator.validate_step(
        step_type="DERIVATIVE_CALCULATION",
        content_latex="y' = x^2 - 2x - 3",
    )
    incorrect = validator.validate_step(
        step_type="DERIVATIVE_CALCULATION",
        content_latex="y' = x^2 + 2x - 3",
    )

    assert correct.validity == MathValidity.VALID
    assert incorrect.validity == MathValidity.INVALID
