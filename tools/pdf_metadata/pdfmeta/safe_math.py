"""Bounded arithmetic/LaTeX parser and narrow symbolic checks. No eval/sympify strings."""
from __future__ import annotations

from dataclasses import dataclass
import re

import sympy as sp


class UnsupportedMath(ValueError):
    pass


@dataclass
class Parsed:
    expression: object
    denominators: list


def _argument(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        raise UnsupportedMath("MISSING_LATEX_ARGUMENT")
    if text[start] != "{":
        return text[start], start + 1
    depth = 1
    for end in range(start + 1, len(text)):
        depth += (text[end] == "{") - (text[end] == "}")
        if depth == 0:
            return text[start + 1:end], end + 1
    raise UnsupportedMath("UNBALANCED_LATEX")


def latex_plain(text, depth=0):
    if depth > 20 or len(text) > 2000:
        raise UnsupportedMath("EXPRESSION_TOO_LARGE")
    text = text.replace("{,}", ".").replace("−", "-").replace("–", "-")
    text = text.replace("\\left", "").replace("\\right", "").replace("\\,", " ").replace("\\!", "")
    out, i = [], 0
    while i < len(text):
        if text[i] != "\\":
            out.append(text[i])
            i += 1
            continue
        match = re.match(r"\\([A-Za-z]+)", text[i:])
        if not match:
            raise UnsupportedMath("UNKNOWN_LATEX_ESCAPE")
        command = match[1]
        i += len(match[0])
        if command in {"frac", "dfrac", "tfrac"}:
            numerator, i = _argument(text, i)
            denominator, i = _argument(text, i)
            out.append("((" + latex_plain(numerator, depth + 1) + ")/(" + latex_plain(denominator, depth + 1) + "))")
        elif command == "sqrt":
            arg, i = _argument(text, i)
            out.append("sqrt(" + latex_plain(arg, depth + 1) + ")")
        elif command in {"sin", "cos", "tan", "exp", "log", "ln"}:
            out.append(command)
        elif command in {"cdot", "times"}:
            out.append("*")
        elif command == "div":
            out.append("/")
        elif command == "pi":
            out.append("π")
        elif command == "nu":
            out.append("ν")
        else:
            raise UnsupportedMath("UNSUPPORTED_LATEX_COMMAND")
    return "".join(out).replace("{", "(").replace("}", ")")


TOKEN = re.compile(r"\s*(?:(\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)|(sqrt|sin|cos|tan|exp|log|ln)|([A-Za-zνπ])|(\*\*|[()+*/^\-]))")
FUNCTIONS = {"sqrt": sp.sqrt, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
             "exp": sp.exp, "log": sp.log, "ln": sp.log}


class ArithmeticParser:
    def __init__(self, text):
        text = latex_plain(text.strip().strip("$"))
        if re.search(r'(?<![A-Za-z])[A-Za-z]\s*\(\s*[A-Za-z]\s*\)',text):
            # An unknown f(x) is not the product f*x. This grammar has no
            # declarations for user-defined functions, so keep it unresolved.
            raise UnsupportedMath('UNDECLARED_FUNCTION_OR_AMBIGUOUS_PRODUCT')
        if re.search(r"[A-Za-zν]\d", text):
            raise UnsupportedMath("AMBIGUOUS_LOST_SUPERSCRIPT")
        self.tokens, cursor = [], 0
        while cursor < len(text):
            if not text[cursor:].strip():
                break
            match = TOKEN.match(text, cursor)
            if not match:
                raise UnsupportedMath("UNSUPPORTED_EXPRESSION_TOKEN")
            self.tokens.append(next(value for value in match.groups() if value is not None))
            cursor = match.end()
        if not self.tokens or len(self.tokens) > 400:
            raise UnsupportedMath("EXPRESSION_TOKEN_LIMIT")
        self.i, self.depth, self.denominators = 0, 0, []

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self):
        token = self.peek()
        if token is None:
            raise UnsupportedMath("UNEXPECTED_END")
        self.i += 1
        return token

    def expression(self):
        value = self.term()
        while self.peek() in {"+", "-"}:
            operation = self.take()
            other = self.term()
            value = value + other if operation == "+" else value - other
        return value

    def term(self):
        value = self.factor()
        while self.peek() is not None and self.peek() not in {"+", "-", ")"}:
            operation = self.peek()
            if operation in {"*", "/"}:
                self.take()
                other = self.factor()
                if operation == "/":
                    if other == 0:
                        raise UnsupportedMath("ZERO_DENOMINATOR")
                    self.denominators.append(other)
                    value /= other
                else:
                    value *= other
            else:
                value *= self.factor()
        return value

    def factor(self):
        self.depth += 1
        if self.depth > 40:
            raise UnsupportedMath("EXPRESSION_DEPTH_LIMIT")
        try:
            if self.peek() in {"+", "-"}:
                sign = self.take()
                value = self.factor()
                return -value if sign == "-" else value
            value = self.atom()
            if self.peek() in {"^", "**"}:
                self.take()
                exponent = self.factor()
                if not exponent.is_Rational or abs(exponent) > 12 or exponent.q > 2:
                    raise UnsupportedMath("UNSUPPORTED_EXPONENT")
                if exponent < 0:
                    self.denominators.append(value)
                value **= exponent
            return value
        finally:
            self.depth -= 1

    def atom(self):
        token = self.take()
        if token == "(":
            value = self.expression()
            if self.take() != ")":
                raise UnsupportedMath("UNBALANCED_PARENTHESES")
            return value
        if re.fullmatch(r"\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?", token):
            if len(token) > 24:
                raise UnsupportedMath("NUMBER_TOO_LONG")
            exponent = re.search(r"[eE]([+-]?\d+)$", token)
            if exponent and abs(int(exponent[1])) > 12:
                raise UnsupportedMath("SCIENTIFIC_EXPONENT_LIMIT")
            value = sp.Rational(token.replace(",", "."))
            if abs(value) > 10**9:
                raise UnsupportedMath("NUMBER_TOO_LARGE")
            return value
        if token in FUNCTIONS:
            if self.take() != "(":
                raise UnsupportedMath("FUNCTION_PARENTHESES_REQUIRED")
            arg = self.expression()
            if self.take() != ")":
                raise UnsupportedMath("UNBALANCED_FUNCTION")
            return FUNCTIONS[token](arg)
        if re.fullmatch(r"[A-Za-zν]", token):
            return sp.Symbol(token)
        if token == "π":
            return sp.pi
        raise UnsupportedMath("UNEXPECTED_EXPRESSION_TOKEN")

    def parse(self):
        value = self.expression()
        if self.i != len(self.tokens) or sp.count_ops(value) > 300 or len(value.free_symbols) > 6:
            raise UnsupportedMath("EXPRESSION_COMPLEXITY_LIMIT")
        return Parsed(value, self.denominators)


def parse_expression(text):
    return ArithmeticParser(text).parse()


def assignment(latex):
    original = latex.strip().strip("$").replace("\\left", "").replace("\\right", "")
    conditions = ""
    atom = r"[-+]?(?:\d+(?:[.,]\d+)?|[A-Za-zν])"
    relation = r"(?:[<>≤≥]|\\(?:leq?|geq?))"
    domain = re.compile(rf"\s*{atom}(?:\s*{relation}\s*{atom}){{1,2}}\s*[.]?\s*")
    depth = 0
    for index, char in enumerate(original):
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
        elif char in ",;" and depth == 0 and domain.fullmatch(original[index+1:]):
            conditions, original = original[index+1:].strip(), original[:index]
            break
    main = re.split(r"\\(?:Leftrightarrow|Rightarrow|quad|qquad|text|mathrm)\b|[;；]", original, maxsplit=1)[0]
    main = main.replace("\\left", "").replace("\\right", "")
    suffix = re.search(r"(?:,\s*)?(?:\(\s*)?[A-Za-zν]\s*(?:[<>≤≥]|\\geq|\\leq)[^=]*$", main)
    conditions = suffix[0] if suffix else conditions
    if suffix:
        main = main[:suffix.start()].rstrip(" ,")
    for token in (r"^{\prime}", r"^{'}", r"^\prime", r"\prime", "′", "’"):
        main = main.replace(token, "'")
    pieces = main.split("=")
    if len(pieces) < 2:
        raise UnsupportedMath("NOT_AN_ASSIGNMENT")
    lhs = re.fullmatch(r"\s*([A-Za-z])\s*('{0,2})\s*(?:\(\s*([A-Za-zν])\s*\))?\s*", pieces[0])
    if not lhs:
        raise UnsupportedMath("UNSUPPORTED_ASSIGNMENT_LEFT_SIDE")
    if any(re.search(r"[<>≤≥]", p) for p in pieces[1:]):
        raise UnsupportedMath("RELATION_INSIDE_EXPRESSION")
    parsed = [parse_expression(p.strip().rstrip(" .")) for p in pieces[1:]]
    return {"label": lhs[1], "derivative_order": len(lhs[2]), "variable": lhs[3],
            "expression": parsed[-1].expression, "denominators": [d for p in parsed for d in p.denominators],
            "conditions_raw": conditions,
            "chain_consistent": all(sp.cancel(p.expression - parsed[-1].expression) == 0 for p in parsed)}


def equivalent(a, b):
    if a["label"] != b["label"] or a["derivative_order"] != b["derivative_order"] or a["variable"] != b["variable"]:
        return False
    return sp.cancel(a["expression"] - b["expression"]) == 0


def derivative_check(base, derivative):
    if (base["label"] != derivative["label"] or base["derivative_order"] != 0
            or derivative["derivative_order"] not in {1, 2}
            or (base["variable"] and derivative["variable"] and base["variable"] != derivative["variable"])):
        return {"status": "NOT_ASSESSED", "reason": "FUNCTION_OR_VARIABLE_MISMATCH"}
    variable = derivative["variable"] or base["variable"]
    if variable is None:
        symbols = base["expression"].free_symbols
        if len(symbols) != 1:
            return {"status": "NOT_ASSESSED", "reason": "VARIABLE_NOT_UNAMBIGUOUS"}
        variable = str(next(iter(symbols)))
    var = sp.Symbol(variable)
    for expression in (base["expression"], derivative["expression"]):
        if not expression.is_rational_function(var):
            return {"status": "NOT_ASSESSED", "reason": "ONLY_RATIONAL_FUNCTIONS_SUPPORTED"}
        numerator, denominator = sp.fraction(sp.cancel(expression))
        if max(sp.degree(numerator, var), sp.degree(denominator, var)) > 8:
            return {"status": "NOT_ASSESSED", "reason": "POLYNOMIAL_DEGREE_LIMIT"}
    expected = sp.diff(base["expression"], var, derivative["derivative_order"])
    difference = sp.cancel(expected - derivative["expression"])
    return {"status": "PASS" if difference == 0 else "FAIL", "kind": "DERIVATIVE_IDENTITY",
            "variable": variable, "order": derivative["derivative_order"], "expected": sp.sstr(expected),
            "candidate": sp.sstr(derivative["expression"]), "difference": sp.sstr(difference),
            "scope": "IDENTITY_ONLY_NOT_DOMAIN_SIGN_OR_ANSWER_APPROVAL",
            "source_denominators": sorted({sp.sstr(d) for d in base["denominators"] + derivative["denominators"]})}
