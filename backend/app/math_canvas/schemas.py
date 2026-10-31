import ast
import math
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.math_canvas.scene_schema import GraphSceneDocument
from app.math_canvas.lab_schema import LabDocument

FUNCTIONS = {"sin", "cos", "tan", "sqrt", "abs", "exp", "log", "ln"}


def classify_expression(expression: str) -> tuple[str, set[str]]:
    """Validate a bounded mathematical AST without executing it (including SymPy parsers)."""
    if len(expression) > 500 or not re.fullmatch(r"[a-z0-9.+*/^()=\-]+", expression):
        raise ValueError("Use a normalized mathematical expression.")
    if expression.count("=") != 1:
        raise ValueError("Exactly one equation is required.")
    lhs, rhs = expression.split("=")
    implicit = lhs not in {"y", "z"}
    try:
        tree = ast.parse((f"({lhs})-({rhs})" if implicit else rhs).replace("^", "**"), mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Invalid mathematical expression.") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 250:
        raise ValueError("Expression is too complex.")
    symbols: set[str] = set()
    call_names = {id(node.func) for node in nodes if isinstance(node, ast.Call)}
    for node in nodes:
        if isinstance(node, ast.Constant):
            if type(node.value) not in {int, float} or abs(node.value) > 1e6 or not math.isfinite(node.value):
                raise ValueError("Invalid numeric constant.")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or len(node.args) != 1 or node.keywords:
                raise ValueError("Unsupported function.")
        elif isinstance(node, ast.Name):
            if node.id in FUNCTIONS and id(node) not in call_names:
                raise ValueError("Functions require parentheses.")
            if node.id in FUNCTIONS or node.id in {"pi", "e"}:
                continue
            if not re.fullmatch(r"[a-z]", node.id) or (node.id == "z" and not implicit):
                raise ValueError("Unsupported mathematical symbol.")
            symbols.add(node.id)
        elif not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.UAdd, ast.USub, ast.Load)):
            raise ValueError("Unsupported mathematical syntax.")
    if not implicit and lhs == "y" and "y" in symbols:
        raise ValueError("y=f(x) cannot depend on y.")
    if implicit and not symbols.intersection({"x", "y", "z"}):
        raise ValueError("An implicit equation must contain a coordinate.")
    parameters = symbols - {"x", "y", "z"}
    if len(parameters) > 6:
        raise ValueError("At most six parameters are supported.")
    return ("3D" if ("z" in symbols if implicit else lhs == "z") else "2D", parameters)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, from_attributes=True)


class GraphSettings(StrictModel):
    parameters: dict[str, float] = Field(default_factory=dict, max_length=6)
    scale: float = Field(default=1, ge=-5, le=5)
    offset: float = Field(default=0, ge=-5, le=5)
    shift_x: float = Field(default=0, ge=-5, le=5)
    shift_y: float = Field(default=0, ge=-5, le=5)
    domain: float = Field(default=3, ge=1, le=10)
    view_mode: Literal["AUTO", "2D", "3D", "EXTRUDED"] = "AUTO"
    slice_y: float = Field(default=0, ge=-5, le=5)
    scene: GraphSceneDocument | None = None
    lab: LabDocument | None = None

    @field_validator("parameters")
    @classmethod
    def bound_parameters(cls, values):
        if any(not re.fullmatch(r"[a-df-w]", key) or not math.isfinite(value) or abs(value) > 5 for key, value in values.items()):
            raise ValueError("Invalid graph parameter.")
        return values


class GraphSpec(StrictModel):
    expression: str = Field(min_length=1, max_length=500)
    settings: GraphSettings

    @model_validator(mode="after")
    def valid_expression(self):
        if self.settings.lab is not None:
            if self.settings.scene is not None or self.expression != "y=0":
                raise ValueError("Explorations use y=0 and cannot also contain a planar scene.")
            parameters = self.settings.lab.parameter_names()
            if len(parameters) > 6 or set(self.settings.parameters) != parameters:
                raise ValueError("Exploration parameters must match the mathematical document.")
            if self.settings.view_mode != self.settings.lab.dimension or self.settings.scale != 1 or any((self.settings.offset, self.settings.shift_x, self.settings.shift_y, self.settings.slice_y)):
                raise ValueError("Exploration view settings must match its dimension without legacy transforms.")
            return self
        if self.settings.scene is not None:
            if self.expression != "y=0":
                raise ValueError("Version 2 scenes use the compatibility expression y=0.")
            if set(self.settings.parameters) != self.settings.scene.parameter_names():
                raise ValueError("Shared parameters must match all scene expressions.")
            if self.settings.view_mode not in {"AUTO", "2D"} or self.settings.scale != 1 or any((self.settings.offset, self.settings.shift_x, self.settings.shift_y, self.settings.slice_y)):
                raise ValueError("Planar scenes use their own expressions without legacy view transforms.")
            return self
        dimension, parameters = classify_expression(self.expression)
        if set(self.settings.parameters) != parameters:
            raise ValueError("Parameter values must match the mathematical expression.")
        if self.settings.view_mode == "EXTRUDED" and (dimension != "2D" or not self.expression.startswith("y=")):
            raise ValueError("Only a one-variable curve can be extended along a free axis.")
        if not self.expression.startswith(("y=", "z=")) and any(
            (self.settings.scale != 1, self.settings.offset != 0, self.settings.shift_x != 0, self.settings.shift_y != 0)
        ):
            raise ValueError("Implicit equations use formula parameters, without outer function transforms.")
        return self


class GraphCamera(StrictModel):
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    zoom: float = Field(default=1, ge=0.05, le=30)

    @model_validator(mode="after")
    def valid_camera(self):
        if any(abs(value) > 1000 for value in (*self.position, *self.target)):
            raise ValueError("Camera is outside the view bounds.")
        if sum((a - b) ** 2 for a, b in zip(self.position, self.target)) < 0.01:
            raise ValueError("Camera position and target must differ.")
        return self


class SnapshotCreate(GraphSpec):
    client_action_id: UUID
    page_index: int = Field(ge=0, le=29)
    stroke_ids: list[UUID] = Field(default_factory=list, max_length=400)
    source_latex: str = Field(default="", max_length=500)
    camera: GraphCamera
    note: str = Field(default="", max_length=1000)
    explanation_id: UUID | None = None

    @field_validator("stroke_ids")
    @classmethod
    def unique_ids(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Duplicate stroke IDs.")
        return values


class ExplanationRead(StrictModel):
    id: UUID
    text: str
    provider: str
    model: str


class SnapshotRead(GraphSpec):
    id: UUID
    attempt_id: UUID
    student_id: UUID
    student_name: str
    dimension: Literal["2D", "3D"]
    page_index: int
    source_latex: str
    source_strokes: list[dict]
    source_ink_revision: int
    camera: GraphCamera
    note: str
    explanation: ExplanationRead | None
    created_at: datetime
