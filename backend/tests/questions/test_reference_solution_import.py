from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.questions.import_schemas import QuestionImportRecord


def _row():
    return {"subject_code": "MATH_G12", "content": "Explain why a function is increasing.",
            "question_type": "OPEN_RESPONSE", "source": "TEST_FIXTURE", "difficulty": 0.5,
            "exam_weight": 0.5, "concepts": [{"code": "TEST_CONCEPT", "weight": 1.0}]}


def test_import_accepts_reference_solution_without_a_short_answer():
    row = _row()
    row["reference_solution"] = "Its derivative is strictly positive on the given interval."
    parsed = QuestionImportRecord.model_validate(row)
    assert parsed.correct_answer is None
    assert parsed.explanation == row["reference_solution"]
    assert "reference_solution" not in parsed.model_dump()


def test_existing_explanation_field_still_imports_unchanged():
    row = _row()
    row["explanation"] = "Reviewed solution text."
    assert QuestionImportRecord.model_validate(row).explanation == row["explanation"]


@pytest.mark.parametrize("kind", ["MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER"])
def test_reference_solution_does_not_bypass_objective_answer_requirements(kind):
    row = _row()
    row.update(question_type=kind, reference_solution="Full source solution text.")
    if kind == "MULTIPLE_CHOICE":
        row["options"] = [{"label": label, "content": label, "order_index": i} for i, label in enumerate(["A", "B"])]
    with pytest.raises(ValidationError):
        QuestionImportRecord.model_validate(row)


def test_conflicting_solution_aliases_are_rejected():
    row = _row()
    row.update(explanation="First solution", reference_solution="Different solution")
    with pytest.raises(ValidationError):
        QuestionImportRecord.model_validate(row)
