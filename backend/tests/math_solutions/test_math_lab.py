from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.math_canvas.schemas import GraphSpec

EXAMPLES = [
    {"version": 1, "kind": "PIECEWISE", "dimension": "2D", "branches": [{"expression": "-x", "condition": "x<0"}, {"expression": "x^2+a", "condition": "x>=0"}]},
    {"version": 1, "kind": "PARAMETRIC", "dimension": "3D", "coordinates": ["2*cos(t)", "2*sin(t)", "a*t/4"], "interval": [-12, 12], "progress": .5},
    {"version": 1, "kind": "VECTOR", "dimension": "3D", "origin": ["0", "0", "0"], "u": ["a", "1", "2"], "v": ["1", "2", "0"], "operation": "PROJECTION"},
    {"version": 1, "kind": "CALCULUS", "dimension": "2D", "expression": "a*x^2-1", "point": 1, "bounds": [-1, 1], "rectangles": 12, "showDerivative": True},
]


@pytest.mark.parametrize("document", EXAMPLES)
def test_lab_spec_roundtrip_preserves_each_representation(document):
    spec = GraphSpec(expression="y=0", settings={"lab": document, "view_mode": document["dimension"], "parameters": {"a": 2}})
    assert spec.settings.lab.model_dump(mode="json") == document
    assert GraphSpec.model_validate(spec.model_dump()).settings.lab.kind == document["kind"]


@pytest.mark.parametrize("expression", ["__import__('os')", "x.real", "[x]", "x//2", "y+1", "z", "1e309"])
def test_lab_scalars_reject_executable_or_wrong_coordinate_source(expression):
    document = {**EXAMPLES[3], "expression": expression}
    with pytest.raises(ValidationError):
        GraphSpec(expression="y=0", settings={"lab": document, "view_mode": "2D", "parameters": {}})


def test_parameter_coordinate_and_representation_constraints():
    document = deepcopy(EXAMPLES[1])
    document["coordinates"] = ["a+b+c+d+f+g+t", "sin(t)", "t"]
    spec = GraphSpec(expression="y=0", settings={"lab": document, "view_mode": "3D", "parameters": {name: 1 for name in "abcdfg"}})
    assert spec.settings.lab.parameter_names() == set("abcdfg")
    for patch in [{"view_mode": "2D"}, {"scale": 2}, {"parameters": {}}, {"slice_y": 1}]:
        with pytest.raises(ValidationError): GraphSpec(expression="y=0", settings={**spec.settings.model_dump(), **patch})
    for patch in [{"coordinates": ["t", "t"]}, {"interval": [1, 0]}, {"interval": [-101, 1]}, {"progress": 2}]:
        with pytest.raises(ValidationError): GraphSpec(expression="y=0", settings={"lab": {**document, **patch}, "view_mode": "3D", "parameters": {name: 1 for name in "abcdfg"}})


def test_piecewise_and_vector_boundaries_are_checked_independently_of_frontend():
    for branches in [[{"expression": "x", "condition": "y<1"}], [{"expression": "x", "condition": "x=__import__(x)"}], EXAMPLES[0]["branches"] * 4]:
        with pytest.raises(ValidationError): GraphSpec(expression="y=0", settings={"lab": {**EXAMPLES[0], "branches": branches}, "view_mode": "2D", "parameters": {}})
    for patch in [{"origin": ["0", "0"]}, {"u": ["x", "1", "2"]}, {"operation": "EXECUTE"}]:
        with pytest.raises(ValidationError): GraphSpec(expression="y=0", settings={"lab": {**EXAMPLES[2], **patch}, "view_mode": "3D", "parameters": {"a": 1}})
    for patch in [{"rectangles": 121}, {"rectangles": 5.5}, {"bounds": [-11, 1]}, {"point": float("nan")}, {"showDerivative": "false"}]:
        with pytest.raises(ValidationError): GraphSpec(expression="y=0", settings={"lab": {**EXAMPLES[3], **patch}, "view_mode": "2D", "parameters": {"a": 1}})
