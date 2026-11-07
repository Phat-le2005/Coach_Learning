import copy

import pytest

from app.math_solutions.validator import DeterministicMathValidator, MathValidity


TARGET = r"Ví dụ 8. Tìm khoảng đơn điệu của $f(x)=2x^3-9x^2-24x+1$."


def ui_table():
    return {
        "version": 1,
        "points": [
            {"x": r"-\infty", "derivative": "", "y": r"-\infty"},
            {"x": "-1", "derivative": "0", "y": "14"},
            {"x": "4", "derivative": "0", "y": "-111"},
            {"x": r"+\infty", "derivative": "", "y": r"+\infty"},
        ],
        "intervals": [{"sign": "+", "trend": "UP"}, {"sign": "-", "trend": "DOWN"}, {"sign": "+", "trend": "UP"}],
    }


def test_actual_workspace_table_is_checked_against_source_function():
    validator = DeterministicMathValidator(TARGET)
    assert validator.validate_step("VARIATION_TABLE", None, artifact_payload=ui_table()).validity == MathValidity.VALID
    for group, index, field, value in [
        ("points", 1, "x", "-2"),
        ("points", 2, "y", "111"),
        ("points", 3, "y", r"-\infty"),
        ("points", 1, "derivative", "undefined"),
        ("intervals", 1, "sign", "+"),
        ("intervals", 0, "trend", "DOWN"),
    ]:
        broken = copy.deepcopy(ui_table())
        broken[group][index][field] = value
        assert validator.validate_step("VARIATION_TABLE", None, artifact_payload=broken).validity == MathValidity.INVALID


@pytest.mark.parametrize("change", [None, {}, {"version": 1, "points": [], "intervals": []}])
def test_incomplete_table_never_receives_a_grade(change):
    result = DeterministicMathValidator(TARGET).validate_step("VARIATION_TABLE", None, artifact_payload=change)
    assert result.validity == MathValidity.NEEDS_REVIEW
    assert result.score is None


@pytest.mark.parametrize("text", [
    r"Đồng biến trên $(-\infty;-1)$ và $(4;+\infty)$; nghịch biến trên $(-1;4)$.",
    "Hàm số nghịch biến trên (-1;4), và đồng biến trên (-∞;-1) và (4;+∞).",
    r"increasing on (-\infty;-1) \cup (4;+\infty); decreasing on (-1;4)",
])
def test_complete_interval_claims_include_outer_intervals_and_both_directions(text):
    result = DeterministicMathValidator(TARGET, require_complete_conclusion=True).validate_step("CONCLUSION", text)
    assert result.validity == MathValidity.VALID


def test_partial_conclusion_cannot_complete_reviewed_full_interval_rubric():
    assert DeterministicMathValidator(TARGET).validate_step("CONCLUSION", "nghịch biến trên (-1;4)").validity == MathValidity.VALID
    result = DeterministicMathValidator(TARGET, require_complete_conclusion=True).validate_step("CONCLUSION", "nghịch biến trên (-1;4)")
    assert result.validity == MathValidity.NEEDS_REVIEW


def test_wrong_claim_is_not_hidden_by_another_correct_claim():
    validator = DeterministicMathValidator(TARGET)
    result = validator.validate_step("CONCLUSION", "đồng biến trên (-∞;-1) và (-1;4)")
    assert result.validity == MathValidity.INVALID
    for text in ["không nghịch biến trên (-1;4)", "đồng biến trên (-1;3)", "nghịch biến trên (-1;4), thêm điều kiện x=100"]:
        assert validator.validate_step("CONCLUSION", text).validity == MathValidity.NEEDS_REVIEW


def test_explanation_channel_and_negative_leading_cubic():
    validator = DeterministicMathValidator("f(x)=-x^3+3x^2+9x+4", require_complete_conclusion=True)
    result = validator.validate_step("CONCLUSION", None, explanation_text="nghịch biến trên (-∞;-1) và (3;+∞); đồng biến trên (-1;3)")
    assert result.validity == MathValidity.VALID
    table = ui_table()
    assert validator.validate_step("VARIATION_TABLE", None, artifact_payload=table).validity == MathValidity.INVALID


@pytest.mark.parametrize("target,task,answer", [
    (r"y=-\frac{1}{3}x^3+2x^2+5x-44", "inner_sum", "a+b=4"),
    ("y=-x^3+3x^2+9x+4", "inner_width", "b-a=4"),
])
def test_source_numeric_tasks_check_requested_quantity(target, task, answer):
    validator = DeterministicMathValidator(target, require_complete_conclusion=True, conclusion_task=task)
    assert validator.validate_step("CONCLUSION", answer).validity == MathValidity.VALID
    assert validator.validate_step("CONCLUSION", "5").validity == MathValidity.INVALID
    assert validator.validate_step("CONCLUSION", "4 hoặc 5").validity == MathValidity.NEEDS_REVIEW


def test_curated_parser_does_not_discard_extra_equations_or_non_root_numbers():
    validator = DeterministicMathValidator(TARGET, require_complete_conclusion=True)
    assert validator.validate_step("DERIVATIVE_CALCULATION", "y'=6x^2-18x-24; y'=0").validity == MathValidity.UNDETERMINED
    assert validator.validate_step("DERIVATIVE_CALCULATION", "6.0x^2-18x-24").validity == MathValidity.VALID
    assert validator.validate_step("ROOT_FINDING", "Các số -1 và 4 chưa phải nghiệm").validity == MathValidity.NEEDS_REVIEW
    assert validator.validate_step("ROOT_FINDING", r"y'=0 \Leftrightarrow x=-1 \lor x=4").validity == MathValidity.VALID
    assert validator.validate_step("ROOT_FINDING", "x=-1, x=4, x=10").validity == MathValidity.INVALID
