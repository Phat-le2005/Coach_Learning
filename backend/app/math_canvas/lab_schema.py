"""Versioned exploration documents; validate scalar ASTs without executing source."""
import ast
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.math_canvas.scene_schema import GraphSceneDocument


class LabModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Literal[1] = 1


def scalar_symbols(source: str, coordinate: str | None = None) -> set[str]:
    if len(source) > 500 or not re.fullmatch(r"[a-z0-9.+*/^()\-]+", source):
        raise ValueError("Use canonical scalar expressions.")
    # Reuse the independently validated planar grammar. The prefix supplies a
    # coordinate; any forbidden coordinate in the body is checked separately.
    validated_source = re.sub(r"\bt\b", "x", source) if coordinate == "t" else source
    GraphSceneDocument(version=2, dimension="2D", combine="OVERLAY", rows=[
        {"id": "scalar", "expression": f"y={validated_source}", "visible": True, "color": "#167a60"}])
    tree = ast.parse(source.replace("^", "**"), mode="eval")
    symbols = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and len(node.id) == 1 and node.id != "e"}
    if (symbols & {"x", "y", "z"}) - ({coordinate} if coordinate else set()):
        raise ValueError("The scalar uses an unsupported coordinate.")
    return symbols - ({coordinate} if coordinate else set())


class Branch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=500)
    condition: str = Field(min_length=1, max_length=500)


class PiecewiseLab(LabModel):
    kind: Literal["PIECEWISE"]
    dimension: Literal["2D"]
    branches: list[Branch] = Field(min_length=1, max_length=6)

    def parameter_names(self) -> set[str]:
        result: set[str] = set()
        for branch in self.branches:
            result |= scalar_symbols(branch.expression, "x")
            if "x" not in branch.condition or re.search(r"[yz]", branch.condition):
                raise ValueError("A branch condition must be an interval in x.")
            condition = GraphSceneDocument(version=2, dimension="2D", combine="AND", rows=[
                {"id": "condition", "expression": branch.condition, "color": "#167a60"}])
            result |= condition.parameter_names()
        return result


class ParametricLab(LabModel):
    kind: Literal["PARAMETRIC"]
    dimension: Literal["2D", "3D"]
    coordinates: list[str] = Field(min_length=2, max_length=3)
    interval: tuple[float, float]
    progress: float = Field(ge=0, le=1)

    def parameter_names(self) -> set[str]:
        if len(self.coordinates) != (3 if self.dimension == "3D" else 2) or any(abs(value) > 100 for value in self.interval) or self.interval[1] - self.interval[0] < 1e-6:
            raise ValueError("Invalid parametric coordinates or interval.")
        return set().union(*(scalar_symbols(value, "t") for value in self.coordinates))


class VectorLab(LabModel):
    kind: Literal["VECTOR"]
    dimension: Literal["2D", "3D"]
    origin: list[str] = Field(min_length=2, max_length=3)
    u: list[str] = Field(min_length=2, max_length=3)
    v: list[str] = Field(min_length=2, max_length=3)
    operation: Literal["SUM", "DIFFERENCE", "PROJECTION"]

    def parameter_names(self) -> set[str]:
        count = 3 if self.dimension == "3D" else 2
        if any(len(vector) != count for vector in (self.origin, self.u, self.v)):
            raise ValueError("Vector components must match the dimension.")
        return set().union(*(scalar_symbols(value) for vector in (self.origin, self.u, self.v) for value in vector))


class CalculusLab(LabModel):
    kind: Literal["CALCULUS"]
    dimension: Literal["2D"]
    expression: str = Field(min_length=1, max_length=500)
    point: float = Field(ge=-10, le=10)
    bounds: tuple[float, float]
    rectangles: int = Field(ge=4, le=120, strict=True)
    showDerivative: bool = Field(strict=True)

    def parameter_names(self) -> set[str]:
        if any(abs(value) > 10 for value in self.bounds):
            raise ValueError("Integration bounds must be between -10 and 10.")
        return scalar_symbols(self.expression, "x")


LabDocument = Annotated[PiecewiseLab | ParametricLab | VectorLab | CalculusLab, Field(discriminator="kind")]
