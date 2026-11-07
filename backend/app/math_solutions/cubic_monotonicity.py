"""Bounded checking of cubic monotonicity, including the workspace table format.

This module never evaluates Python or accepts a general symbolic student grammar.
Unknown claims remain reviewable rather than being silently discarded.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import sympy


_NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\d+/\d+)"
_BOUND = rf"(?:{_NUMBER}|[+-]?inf)"
_INTERVAL = re.compile(rf"\(\s*({_BOUND})\s*[,;]\s*({_BOUND})\s*\)")
_DIRECTION = re.compile(r"đồng biến|nghịch biến|increasing|decreasing|\btăng\b|\bgiảm\b", re.I)


def number(value: str) -> float:
    value = value.strip().replace("−", "-")
    if value in {"inf", "+inf"}:
        return math.inf
    if value == "-inf":
        return -math.inf
    if not re.fullmatch(_NUMBER, value):
        raise ValueError("Unsupported numeric boundary")
    if "/" in value:
        a, b = value.split("/")
        if int(b) == 0:
            raise ValueError("Zero denominator")
        return int(a) / int(b)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite number")
    return result


def math_text(text: str) -> str:
    text = text.lower().replace("−", "-").replace("∞", "inf")
    text = re.sub(r"\\(?:left|right|displaystyle|quad|qquad)\b", "", text)
    text = text.replace(r"\infty", "inf").replace(r"\infinity", "inf")
    text = re.sub(r"\\(?:dfrac|tfrac|frac)\{([+-]?\d+)\}\{(\d+)\}", r"\1/\2", text)
    text = text.replace(r"\(", "").replace(r"\)", "").replace("$", "")
    return text.strip()


def same(a: float, b: float) -> bool:
    return a == b if math.isinf(a) or math.isinf(b) else math.isclose(a, b, abs_tol=1e-8, rel_tol=1e-8)


@dataclass(frozen=True)
class CubicModel:
    expression: sympy.Expr
    variable: sympy.Symbol
    roots: tuple[float, float]
    signs: tuple[str, str, str]

    @classmethod
    def from_expression(cls, expression: sympy.Expr | None, variable: sympy.Symbol) -> "CubicModel | None":
        if expression is None or expression.free_symbols - {variable}:
            return None
        try:
            polynomial = sympy.Poly(expression, variable)
            if polynomial.degree() != 3:
                return None
            derivative = polynomial.diff()
            roots = sympy.solve(derivative.as_expr(), variable)
            if len(roots) != 2 or any(r.is_real is not True for r in roots):
                return None
            points = sorted(float(r) for r in roots)
            if not all(math.isfinite(r) for r in points) or same(*points):
                return None
            leading = derivative.LC()
            signs = ("+", "-", "+") if leading.is_positive else ("-", "+", "-") if leading.is_negative else None
            return cls(expression, variable, tuple(points), signs) if signs else None
        except (ValueError, TypeError, sympy.PolynomialError):
            return None

    @property
    def boundaries(self) -> tuple[float, float, float, float]:
        return (-math.inf, *self.roots, math.inf)

    def check_table(self, payload: dict) -> tuple[str, str | None]:
        points, intervals = payload.get("points"), payload.get("intervals")
        if payload.get("version") != 1 or not isinstance(points, list) or not isinstance(intervals, list):
            return "NEEDS_REVIEW", None
        if len(points) != 4 or len(intervals) != 3:
            return "NEEDS_REVIEW", None
        try:
            xs = [number(math_text(p["x"])) for p in points]
            if not all(same(a, b) for a, b in zip(xs, self.boundaries)):
                return "INVALID", "VARIATION_TABLE_BOUNDARY_ERROR"
            for i, interval in enumerate(intervals):
                sign, trend = interval.get("sign"), interval.get("trend")
                if sign not in ("+", "-") or trend not in ("UP", "DOWN"):
                    return "NEEDS_REVIEW", None
                if sign != self.signs[i] or trend != ("UP" if self.signs[i] == "+" else "DOWN"):
                    return "INVALID", "VARIATION_TABLE_SIGN_ERROR"
            for i, point in enumerate(points):
                derivative = point.get("derivative", "")
                if derivative == "?":
                    return "NEEDS_REVIEW", None
                if derivative not in ("", "0") or (i in (0, 3) and derivative == "0"):
                    return "INVALID", "VARIATION_TABLE_DERIVATIVE_ERROR"
                if i in (1, 2) and derivative != "0":
                    return "NEEDS_REVIEW", None
                if point.get("y", "").strip():
                    actual = number(math_text(point["y"]))
                    expected = (
                        math.copysign(math.inf, xs[i] * (1 if self.signs[0] == "+" else -1))
                        if i in (0, 3) else float(self.expression.subs(self.variable, xs[i]))
                    )
                    if not same(actual, expected):
                        return "INVALID", "VARIATION_TABLE_VALUE_ERROR"
            return "VALID", None
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return "NEEDS_REVIEW", None

    def check_roots(self, text: str) -> tuple[str, str | None]:
        text = math_text(text)
        if len(text) > 3000:
            return "NEEDS_REVIEW", None
        text = re.sub(r"^(?:y'|f'\(x\))\s*=\s*0\s*(?:\\leftrightarrow|\\iff|<=>)", "", text)
        text = re.sub(r"\\(?:begin|end)\{array\}(?:\{[lcr]+\})?", "", text)
        pattern = rf"x(?:_(?:[12]|\{{[12]\}}))?\s*=\s*({_NUMBER})"
        matches = list(re.finditer(pattern, text))
        if not matches:
            return "NEEDS_REVIEW", None
        residue = re.sub(pattern, "", text)
        residue = re.sub(r"\\(?:lor|vee|text)\b|\b(?:or|hoặc|và|and)\b|[\s,;{}\[\]\\.]", "", residue)
        if residue:
            return "NEEDS_REVIEW", None
        try:
            values = sorted({number(match[1]) for match in matches})
            if len(values) == 2 and all(same(a, b) for a, b in zip(values, self.roots)):
                return "VALID", None
            return "INVALID", "ROOT_FINDING_ERROR"
        except (ValueError, OverflowError):
            return "NEEDS_REVIEW", None

    def check_conclusion(self, text: str, *, complete: bool = False) -> tuple[str, str | None]:
        text = math_text(text)
        if len(text) > 3000 or re.search(r"không|\bnot\b|khẳng định sai|khong", text):
            return "NEEDS_REVIEW", None
        directions = list(_DIRECTION.finditer(text))
        if not directions:
            return "NEEDS_REVIEW", None
        if text[:directions[0].start()].strip(" ,.;:\n") not in {"", "vậy hàm số", "hàm số", "vậy", "the function", "function"}:
            return "NEEDS_REVIEW", None
        claims: set[tuple[float, float, str]] = set()
        for index, direction in enumerate(directions):
            end = directions[index + 1].start() if index + 1 < len(directions) else len(text)
            clause = text[direction.end():end]
            intervals = list(_INTERVAL.finditer(clause))
            if not intervals:
                return "NEEDS_REVIEW", None
            residue = _INTERVAL.sub(" ", clause)
            residue = re.sub(r"\\(?:cup|text|mathrm)\b|[{}]", " ", residue)
            residue = re.sub(r"\b(?:trên|các|khoảng|và|hàm|số|vậy|on|the|intervals?|and)\b|[\s,.;:∪]", "", residue)
            if residue:
                return "NEEDS_REVIEW", None
            sign = "+" if direction[0] in {"đồng biến", "increasing", "tăng"} else "-"
            for interval in intervals:
                try:
                    left, right = number(interval[1]), number(interval[2])
                except ValueError:
                    return "NEEDS_REVIEW", None
                position = next((i for i in range(3) if same(left, self.boundaries[i]) and same(right, self.boundaries[i + 1])), None)
                if position is None:
                    return "NEEDS_REVIEW", None
                if sign != self.signs[position]:
                    return "INVALID", "SIGN_TABLE_CONSEQUENCE_ERROR"
                claims.add((self.boundaries[position], self.boundaries[position + 1], sign))
        if complete and len(claims) != 3:
            return "NEEDS_REVIEW", None
        return "VALID", None

    def check_numeric_conclusion(self, content: str, explanation: str, task: str) -> tuple[str, str | None]:
        # These source questions ask for the endpoints of the increasing inner interval.
        if self.signs[1] != "+" or task not in {"inner_sum", "inner_width"}:
            return "NEEDS_REVIEW", None
        text = math_text(content)
        label = r"a\s*\+\s*b" if task == "inner_sum" else r"b\s*-\s*a"
        match = re.fullmatch(rf"(?:{label}\s*=\s*)?({_NUMBER})[.]?", text)
        if not match or explanation.strip():
            return "NEEDS_REVIEW", None
        try:
            expected = sum(self.roots) if task == "inner_sum" else self.roots[1] - self.roots[0]
            return ("VALID", None) if same(number(match[1]), expected) else ("INVALID", "CONCLUSION_VALUE_ERROR")
        except (ValueError, OverflowError):
            return "NEEDS_REVIEW", None
