"""A student-entered variation table is structured evidence, never an inferred answer."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.math_solutions.schemas import StepMutationRequest, VariationTablePayload


def table():
    return {"version": 1,
        "points": [
            {"x": "-infinity", "derivative": "", "y": ""},
            {"x": "a", "derivative": "0", "y": "A"},
            {"x": "b", "derivative": "0", "y": "B"},
            {"x": "+infinity", "derivative": "", "y": ""},
        ],
        "intervals": [
            {"sign": "+", "trend": "UP"},
            {"sign": "-", "trend": "DOWN"},
            {"sign": "+", "trend": "UP"},
        ]}


def mutation(payload=None):
    return {"expected_attempt_revision": 3, "client_action_id": str(uuid4()),
        "step_type": "VARIATION_TABLE", "content_latex": None,
        "explanation_text": None,
        "artifact": {"artifact_type": "VARIATION_TABLE", "payload": payload or table()}}


def test_structured_table_is_accepted_without_ocr_or_grade():
    value = StepMutationRequest.model_validate(mutation())
    assert value.artifact.payload == table()
    assert value.content_latex is None
    assert value.explanation_text is None
    assert value.to_draft().artifact.payload["intervals"][1]["trend"] == "DOWN"


@pytest.mark.parametrize("change", [
    lambda item: item["intervals"].pop(),
    lambda item: item["intervals"][0].update({"trend": "DOWN"}),
    lambda item: item["points"][1].update({"x": "-infinity"}),
    lambda item: item["points"][2].update({"x": ""}),
    lambda item: item["intervals"][1].update({"sign": ""}),
])
def test_incomplete_or_conflicting_table_is_rejected(change):
    payload = table()
    change(payload)
    with pytest.raises(ValidationError):
        VariationTablePayload.model_validate(payload)


def test_variation_artifact_cannot_be_disguised_as_other_step():
    request = mutation()
    request["step_type"] = "EXPLANATION"
    with pytest.raises(ValidationError):
        StepMutationRequest.model_validate(request)
