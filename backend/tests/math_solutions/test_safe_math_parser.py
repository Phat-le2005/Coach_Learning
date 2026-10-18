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
        target_function_latex=r"\frac{1}{3}x^3 - x^2 - 3x + 1"
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


def test_sign_table_is_verified_against_problem_not_fixed_example():
    # y' = x^2 - 4 has turning points at -2, 2.
    validator = DeterministicMathValidator(target_function_latex="x^3/3 - 4x")

    correct = validator.validate_step(
        step_type="SIGN_TABLE",
        content_latex=None,
        artifact_payload={"critical_points": [-2, 2], "signs": ["+", "-", "+"]},
    )
    inverted = validator.validate_step(
        step_type="SIGN_TABLE",
        content_latex=None,
        artifact_payload={"critical_points": [-2, 2], "signs": ["-", "+", "-"]},
    )
    sample_roots_for_wrong_problem = validator.validate_step(
        step_type="SIGN_TABLE",
        content_latex=None,
        artifact_payload={"critical_points": [-1, 3], "signs": ["+", "-", "+"]},
    )

    assert correct.validity == MathValidity.VALID
    assert inverted.validity == MathValidity.INVALID
    assert inverted.error_code == "SIGN_TABLE_QUADRATIC_RULE_INVERTED"
    assert sample_roots_for_wrong_problem.validity == MathValidity.NEEDS_REVIEW


def test_sign_table_respects_negative_leading_coefficient():
    validator = DeterministicMathValidator(target_function_latex="-x^3/3 + 4x")

    correct = validator.validate_step(
        step_type="SIGN_TABLE",
        content_latex=None,
        artifact_payload={"critical_points": [-2, 2], "signs": ["-", "+", "-"]},
    )
    inverted = validator.validate_step(
        step_type="SIGN_TABLE",
        content_latex=None,
        artifact_payload={"critical_points": [-2, 2], "signs": ["+", "-", "+"]},
    )
    assert correct.validity == MathValidity.VALID
    assert inverted.validity == MathValidity.INVALID


@pytest.mark.parametrize(
    "target,payload",
    [
        (None, {"critical_points": [-1, 3], "signs": ["+", "-", "+"]}),
        ("x^2", {"critical_points": [0, 1], "signs": ["+", "-", "+"]}),
        ("x^3/3 - 4x", {"critical_points": [2, -2], "signs": ["+", "-", "+"]}),
        ("x^3/3 - 4x", {"critical_points": ["-2", 2], "signs": ["+", "-", "+"]}),
        ("x^3/3 - 4x", {"critical_points": [-2, float("nan")], "signs": ["+", "-", "+"]}),
        ("x^3/3 - 4x", {"critical_points": [-2, 2], "signs": ["+", "-"]}),
        ("x^3/3 - 4x", {"critical_points": [-2, 2], "signs": ["+", "0", "+"]}),
    ],
)
def test_sign_table_abstains_without_supported_target_and_artifact(target, payload):
    result = DeterministicMathValidator(target_function_latex=target).validate_step(
        step_type="SIGN_TABLE", content_latex=None, artifact_payload=payload
    )
    assert result.validity == MathValidity.NEEDS_REVIEW
    assert result.score is None
    assert not result.error_detected


def test_conclusion_is_checked_against_actual_problem_roots_and_direction():
    positive = DeterministicMathValidator(target_function_latex="x^3/3 - 4x")
    negative = DeterministicMathValidator(target_function_latex="-x^3/3 + 4x")

    assert positive.validate_step(
        step_type="CONCLUSION", content_latex="Hàm số nghịch biến trên (-2, 2)"
    ).validity == MathValidity.VALID
    assert positive.validate_step(
        step_type="CONCLUSION", content_latex="Hàm số đồng biến trên (-2, 2)"
    ).validity == MathValidity.INVALID
    assert negative.validate_step(
        step_type="CONCLUSION", content_latex="Hàm số đồng biến trên (-2, 2)"
    ).validity == MathValidity.VALID
    assert negative.validate_step(
        step_type="CONCLUSION", content_latex="Hàm số nghịch biến trên (-2, 2)"
    ).validity == MathValidity.INVALID


def test_conclusion_does_not_grade_unrelated_or_unsupported_claims():
    validator = DeterministicMathValidator(target_function_latex="x^3/3 - 4x")
    for content in (
        "Hàm số nghịch biến trên (-1, 3)",
        "Hàm số đồng biến trên (-2, 2) và nghịch biến trên (3, 4)",
        "Hàm số không đồng biến trên (-2, 2)",
        "Hàm số đồng biến và nghịch biến trên (-2, 2)",
    ):
        result = validator.validate_step(step_type="CONCLUSION", content_latex=content)
        assert result.validity == MathValidity.NEEDS_REVIEW
        assert result.score is None
