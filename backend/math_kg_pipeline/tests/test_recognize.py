from src.recognize import (
    split_solution_steps, infer_operation, detect_math_regions,
    extract_math_elements,
)

def test_split_solution_steps_returns_candidates():
    steps = split_solution_steps("Ta có x + 1 = 3\nSuy ra x = 2\nVậy nghiệm là x = 2")
    assert len(steps) >= 2
    assert all(step["verification_status"] == "needs_review" for step in steps)

def test_infer_operation():
    assert infer_operation("Tính đạo hàm f'(x)") == "differentiate"
    assert infer_operation("x + 1 = 3") == "algebraic_transformation"

def test_detect_formula_region():
    regions = detect_math_regions({"page": 1, "text": "Ta có x + 2 = 5"})
    assert regions[0]["kind"] == "formula_candidate"


def test_extract_math_elements_returns_structured_formula():
    elements = extract_math_elements("Ta có x + 1 = 2")
    assert elements[0]["type"] == "formula"
    assert elements[0]["latex"] == "Ta có x + 1 = 2"
