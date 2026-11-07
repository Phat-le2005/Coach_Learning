import copy

import pytest

from app.math_solutions.numeric_reference import NumericReferenceValidator


def profile():
    return {"criteria": [
        {"id": "givens", "step_type": "ASSUMPTION", "concept_codes": ["PROBABILITY_DATA"],
         "checks": [{"label": "P(B)", "expected": "3/5"}]},
        {"id": "joint", "step_type": "CUSTOM", "concept_codes": ["PROBABILITY_ARITHMETIC"],
         "checks": [{"label": "P(AB)", "expected": "9/50"}]},
        {"id": "final", "step_type": "CONCLUSION", "concept_codes": ["CONDITIONAL_PROBABILITY"],
         "checks": [{"label": "P(A|B)", "expected": "3/10"}]},
    ]}


def test_reviewed_numeric_steps_verify_quantity_and_arithmetic():
    checker = NumericReferenceValidator(profile())
    assert checker.validate_step("ASSUMPTION", "P(B)=60%").validity.value == "VALID"
    assert checker.validate_step("CUSTOM", r"P(A\cap B)=\frac{18}{100}").validity.value == "VALID"
    assert checker.validate_step("CONCLUSION", r"P(A\mid B)=\frac{P(AB)}{P(B)}=0,3").validity.value == "VALID"
    assert checker.validate_step("CUSTOM", "P(AB)=0.2").validity.value == "INVALID"
    assert checker.validate_step("CONCLUSION", "0.3").validity.value == "VALID"


@pytest.mark.parametrize("text", ["P(B|A)=0.3", "P(A|B)=P(A|B)", "P(A|B)=0.3;P(H)=1",
                                  "P(A|B)=__import__('os')", "P(A|B)=0.3 hoặc 0.5"])
def test_ambiguous_unmatched_or_unsafe_claims_require_review(text):
    assert NumericReferenceValidator(profile()).validate_step("CONCLUSION", text).validity.value == "NEEDS_REVIEW"


def test_rounding_is_an_explicit_alternative_not_a_wide_tolerance():
    data = profile()
    data["criteria"][-1]["checks"][0].update(expected="24/31", rounded="0.77", decimal_places=2)
    checker = NumericReferenceValidator(data)
    assert checker.validate_step("CONCLUSION", "24/31").validity.value == "VALID"
    assert checker.validate_step("CONCLUSION", "0.77").validity.value == "VALID"
    assert checker.validate_step("CONCLUSION", "0.78").validity.value == "INVALID"
    data["criteria"][-1]["checks"][0]["rounded"] = "0.78"
    with pytest.raises(ValueError, match="rounded reference"):
        NumericReferenceValidator(data)


def test_each_requested_quantity_receives_its_own_score():
    data = profile()
    data["criteria"][-1]["checks"].append({"label": "P(B|A)", "expected": "1/2"})
    result = NumericReferenceValidator(data).validate_step("CONCLUSION", "P(A|B)=.3; P(B|A)=.6")
    assert result.validity.value == "INVALID" and result.score == .5
    assert [(c["label"], c["score"]) for c in result.details["numeric_checks"]] == [("P(A|B)", 1.0), ("P(B|A)", 0.0)]


def test_grouped_scalar_sqrt_and_individual_skill_attribution():
    from app.learning_evidence.skill_outcomes import build_outcomes, KEY
    from app.math_solutions.rubric_evaluator import RubricCriterionMatch
    from uuid import uuid4
    profile = {"task": "grouped_statistics", "criteria": [
        {"id": "n", "step_type": "ASSUMPTION", "concept_codes": ["GROUPED_DATA_FREQUENCY"], "checks": [{"label": "N", "expected": "40"}]},
        {"id": "result", "step_type": "CONCLUSION", "concept_codes": ["GROUPED_VARIANCE", "GROUPED_STANDARD_DEVIATION"],
         "checks": [{"label": "VAR", "expected": "4", "concept_code": "GROUPED_VARIANCE"},
                    {"label": "SD", "expected": "sqrt(4)", "concept_code": "GROUPED_STANDARD_DEVIATION"}]},
    ]}
    result = NumericReferenceValidator(profile).validate_step("CONCLUSION", "VAR=4;SD=3")
    assert result.score == .5
    var, sd = uuid4(), uuid4()
    outcome = build_outcomes([profile["criteria"][1]], [RubricCriterionMatch("result", 1, .5, 2, result.details)],
                             {"GROUPED_VARIANCE": var, "GROUPED_STANDARD_DEVIATION": sd})
    assert outcome[KEY]["concepts"][str(var)]["score"] == 1
    assert outcome[KEY]["concepts"][str(sd)]["score"] == 0


def test_scalar_labels_match_whole_quantities_and_math_in_both_channels():
    data = {"task": "definite_integral", "criteria": [
        {"id": "parts", "step_type": "CUSTOM", "concept_codes": ["INTEGRAL_PROPERTIES"],
         "checks": [{"label": "I1", "expected": "1"}, {"label": "I2", "expected": "2"}]},
        {"id": "final", "step_type": "CONCLUSION", "concept_codes": ["DEFINITE_INTEGRAL"],
         "checks": [{"label": "I", "expected": "3"}]},
    ]}
    checker = NumericReferenceValidator(data)
    assert checker.validate_step("CONCLUSION", "I=I1+I2").validity.value == "VALID"
    assert checker.validate_step("CONCLUSION", "I=3", "I=999").validity.value == "NEEDS_REVIEW"
    assert checker.validate_step("CONCLUSION", "I=3", "I=I1+I2").validity.value == "VALID"
    assert checker.validate_step("CONCLUSION", "I=I").validity.value == "NEEDS_REVIEW"
    from app.math_solutions.numeric_reference import numeric_expression, normalize
    assert numeric_expression(r"\frac{2\sqrt{65}}{65}") == numeric_expression("sqrt(4/65)")
    assert normalize(r"s_A^2") == "VARA"
