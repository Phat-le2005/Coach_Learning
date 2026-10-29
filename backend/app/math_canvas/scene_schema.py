"""Versioned planar graph documents, validated without evaluating submitted code."""
import ast
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FUNCTIONS = {"sin", "cos", "tan", "sqrt", "abs", "exp", "log", "ln"}


class SceneRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=36, pattern=r"^[a-zA-Z0-9-]+$")
    expression: str = Field(min_length=1, max_length=500)
    visible: bool = Field(default=True, strict=True)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class GraphSceneDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[2]
    dimension: Literal["2D"]
    combine: Literal["OVERLAY", "AND", "OR"]
    rows: list[SceneRow] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def valid_document(self):
        self.parameter_names()
        return self

    def parameter_names(self) -> set[str]:
        if len({row.id for row in self.rows}) != len(self.rows):
            raise ValueError("Graph row identifiers must be unique.")
        definitions: dict[str, ast.expr] = {}
        parsed: list[tuple[bool, list[ast.expr]]] = []

        def scalar(source: str) -> ast.expr:
            try:
                node = ast.parse(source.replace("^", "**"), mode="eval").body
            except (SyntaxError, RecursionError) as exc:
                raise ValueError("Invalid scalar expression.") from exc
            if len(list(ast.walk(node))) > 250:
                raise ValueError("Scalar expression is too complex.")
            return node

        for row in self.rows:
            source = row.expression
            if not re.fullmatch(r"[a-z0-9.+*/^()=<>\-]+", source):
                raise ValueError("Use canonical mathematical expressions.")
            definition = re.fullmatch(r"([a-df-w])\(x\)=([^=<>]+)", source)
            if definition:
                name = definition[1]
                if name in definitions:
                    raise ValueError("A function is defined more than once.")
                body = scalar(definition[2]); definitions[name] = body; parsed.append((True, [body]))
            else:
                parts = re.split(r"(<=|>=|=|<|>)", source)
                if len(parts) < 3 or len(parts) > 7 or any(not part for part in parts):
                    raise ValueError("A valid relation or chained interval is required.")
                if len(parts) > 3 and "=" in parts[1::2]:
                    raise ValueError("Separate equations into individual rows.")
                parsed.append((False, [scalar(part) for part in parts[::2]]))

        def analyze(node: ast.expr, stack: tuple[str, ...] = (), argument: tuple[set[str], int] | None = None, depth=0) -> tuple[set[str], int]:
            if depth > 40:
                raise ValueError("Mathematical nesting is too deep.")
            if isinstance(node, ast.Constant):
                if type(node.value) not in {int, float} or not math.isfinite(node.value) or abs(node.value) > 1e6:
                    raise ValueError("Invalid numeric constant.")
                return set(), 1
            if isinstance(node, ast.Name):
                name = node.id
                if name in {"pi", "e"}:
                    return set(), 1
                if name == "x" and argument is not None:
                    return argument
                if not re.fullmatch(r"[a-z]", name) or name == "z" or name in FUNCTIONS or name in definitions:
                    raise ValueError("Invalid coordinate, parameter, or function reference.")
                return {name}, 1
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or len(node.args) != 1 or node.keywords:
                    raise ValueError("Functions require exactly one argument.")
                inner = analyze(node.args[0], stack, argument, depth+1); name = node.func.id
                if name in FUNCTIONS:
                    result = inner[0], inner[1]+1
                elif name in definitions:
                    if name in stack:
                        raise ValueError("Cyclic function definitions are not supported.")
                    body = analyze(definitions[name], (*stack, name), inner, depth+1)
                    result = inner[0] | body[0], inner[1]+body[1]+1
                else:
                    raise ValueError("A referenced function is not defined.")
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                child = analyze(node.operand, stack, argument, depth+1); result = child[0], child[1]+1
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
                left = analyze(node.left, stack, argument, depth+1); right = analyze(node.right, stack, argument, depth+1)
                result = left[0] | right[0], left[1]+right[1]+1
            else:
                raise ValueError("Unsupported mathematical syntax.")
            if result[1] > 600:
                raise ValueError("Expanded functions are too complex.")
            return result

        parameters: set[str] = set()
        for is_definition, nodes in parsed:
            symbols: set[str] = set()
            for node in nodes:
                names, _ = analyze(node); symbols |= names
            if is_definition:
                if "y" in symbols:
                    raise ValueError("A function of x cannot depend on y.")
            elif not symbols.intersection({"x", "y"}):
                raise ValueError("A relation must contain a coordinate.")
            parameters |= symbols - {"x", "y"}
        if len(parameters) > 6:
            raise ValueError("At most six shared parameters are supported.")
        return parameters
