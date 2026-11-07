"""Bounded equality checking against reviewed, content-bound numeric criteria.

This verifies the stated quantities and arithmetic, not a free-form proof or
natural-language event definition. Unknown statements require review.
"""
from __future__ import annotations

import re
import ast
import math
import sympy

from app.math_solutions.cubic_monotonicity import math_text


NUMERIC_PROFILE = "numeric-reference-v1"
NUMERIC_KINDS = {"ASSUMPTION", "CUSTOM", "EXPLANATION", "CONCLUSION"}
CONCEPT_CODES = {"CONDITIONAL_PROBABILITY", "TOTAL_PROBABILITY", "BAYES_FORMULA", "PROBABILITY_TREE",
                 "PROBABILITY_DATA", "PROBABILITY_ARITHMETIC"}
_LABEL = r"P\([~A-Z]+(?:\|[~A-Z]+)?\)"
STATS_CONCEPTS = {"GROUPED_DATA_FREQUENCY", "GROUPED_DATA_CLASS_BOUNDARY", "GROUPED_DATA_REPRESENTATIVE_VALUE",
                  "GROUPED_MEAN_FOR_DISPERSION", "GROUPED_QUARTILE_INTERPOLATION", "GROUPED_RANGE", "GROUPED_IQR",
                  "GROUPED_VARIANCE", "GROUPED_STANDARD_DEVIATION"}
INTEGRAL_CONCEPTS = {"DEFINITE_INTEGRAL", "ANTIDERIVATIVE", "INTEGRAL_PROPERTIES", "AREA_BY_INTEGRAL", "VOLUME_BY_INTEGRAL", "VOLUME_BY_CROSS_SECTION"}
EXTREMA_CONCEPTS = {"SIGN_ANALYSIS", "DERIVATIVE_RULES", "LOCAL_EXTREMUM", "EXTREMUM_CRITERION"}
_SCALAR_LABEL = (r"(?:N|R|Q1|Q3|IQR|XBAR|VAR|SD|S1|S2|RORIG|A|B)(?:A|B)?"
                 r"|(?:I|FA|FB|J|K|A|B)[1-6]?|RESULT|X[12]|Y[12]|XMAX|YMAX|XMIN|YMIN")


def normalize(text: str) -> str:
    text = re.sub(r"\\(?:mathrm|operatorname)\{([A-Za-z0-9_]+)\}", r"\1", text)
    text = re.sub(r"\\(?:overline|bar)\s*\{x\}", "XBAR", text)
    text = re.sub(r"Q_\{?([13])\}?", r"Q\1", text)
    text = re.sub(r"\bs_\{?([AB])\}?\^\{?2\}?", r"VAR\1", text)
    text = re.sub(r"\bs\^\{?2\}?", "VAR", text)
    text = re.sub(r"\bs\b", "SD", text)
    text = re.sub(r"([A-Z0-9])_\{?([AB])\}?", r"\1\2", text)
    text = re.sub(r"\\(?:overline|bar)\s*\{([A-Z])\}", r"~\1", text)
    text = re.sub(r"\\(?:overline|bar)\s*([A-Z])", r"~\1", text)
    text = text.replace(r"\cap", "").replace(r"\mid", "|")
    text = re.sub(r"\\(?:left|right|displaystyle)\b", "", text)
    text = text.replace(r"\cdot", "*").replace(r"\times", "*").replace("×", "*")
    text = text.replace(r"\(", "").replace(r"\)", "").replace("$", "")
    text = text.replace(r"\,", "").replace("−", "-")
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    text = re.sub(r"P\(([^()]*)\)", lambda m: "P(" + re.sub(r"\s+", "", m[1]) + ")", text)
    # P(BA) and P(AB) describe the same intersection. Conditions stay ordered.
    text = re.sub(_LABEL, lambda m: "P(" + "|".join("".join(sorted(re.findall(r"~?[A-Z]", s))) for s in m[0][2:-1].split("|")) + ")", text)
    return text.strip()


def numeric_expression(text: str, values: dict[str, sympy.Expr] | None = None) -> sympy.Expr:
    text = normalize(text)
    for _ in range(8):
        updated = re.sub(r"\\(?:dfrac|tfrac|frac)\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", text)
        updated = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", updated)
        if updated == text:
            break
        text = updated
    if values:
        token_pattern = r"(?<![A-Za-z0-9_])(?:" + "|".join(re.escape(label) for label in sorted(values, key=len, reverse=True)) + r")(?![A-Za-z0-9_])"
        text = re.sub(token_pattern, lambda match: f"({values[match[0]]})", text)
    text = re.sub(r"([0-9]+(?:\.[0-9]+)?)\\?%", r"(\1/100)", text)
    for _ in range(8):
        updated = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", text)
        if updated == text:
            break
        text = updated
    text = text.replace("^", "**")
    text = re.sub(r"(?<=\d)\s*(?=sqrt\()", "*", text)
    if len(text) > 1024:
        raise ValueError("Numeric expression is too long")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError) as error:
        raise ValueError("Unsupported numeric syntax") from error
    if sum(1 for _ in ast.walk(tree)) > 160:
        raise ValueError("Numeric expression is too complex")
    def build(node):
        if isinstance(node, ast.Expression):
            return build(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if not math.isfinite(node.value) or abs(node.value) > 1e12:
                raise ValueError("Numeric constant outside bounded range")
            return sympy.Rational(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = build(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1 and not node.keywords:
            value = build(node.args[0])
            if value.is_nonnegative is not True:
                raise ValueError("Square root requires a nonnegative value")
            return sympy.sqrt(value)
        if isinstance(node, ast.BinOp):
            left, right = build(node.left), build(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div) and right != 0: return left / right
            if isinstance(node.op, ast.Pow) and right.is_integer and abs(right) <= 12:
                if left == 0 and right < 0: raise ValueError("Zero denominator")
                return left ** right
        raise ValueError("Unsupported numeric operation")
    result = build(tree)
    if result.free_symbols or result.is_real is not True or result.is_finite is not True:
        raise ValueError("A finite numeric expression is required")
    return result


class NumericReferenceValidator:
    def __init__(self, profile: dict):
        self.criteria = profile["criteria"]
        task = profile.get("task", "probability")
        self.task = task
        allowed_concepts = {"probability": CONCEPT_CODES, "grouped_statistics": STATS_CONCEPTS,
                            "definite_integral": INTEGRAL_CONCEPTS, "polynomial_extrema": EXTREMA_CONCEPTS}.get(task, set())
        label_pattern = _LABEL if task == "probability" else _SCALAR_LABEL
        self.values = {}
        kinds = set()
        for criterion in self.criteria:
            kind = criterion["step_type"]
            if kind not in NUMERIC_KINDS or kind in kinds:
                raise ValueError("Numeric criteria require unique supported step kinds")
            kinds.add(kind)
            if not criterion.get("concept_codes") or not set(criterion["concept_codes"]) <= allowed_concepts:
                raise ValueError("Numeric criterion concepts must match the reviewed task")
            checks = criterion.get("checks")
            if not isinstance(checks, list) or not checks:
                raise ValueError("Numeric criteria require reviewed numeric checks")
            for check in checks:
                if check.get("concept_code") and check["concept_code"] not in criterion["concept_codes"]:
                    raise ValueError("A numeric part must use one of its criterion concepts")
                label = normalize(check["label"])
                if not re.fullmatch(label_pattern, label) or label in self.values:
                    raise ValueError("Each reviewed numeric quantity must have one criterion")
                value = numeric_expression(check["expected"])
                if task == "probability" and not 0 <= value <= 1:
                    raise ValueError("A probability reference must lie in [0,1]")
                if "rounded" in check:
                    rounded = numeric_expression(check["rounded"])
                    digits = check.get("decimal_places")
                    if type(digits) is not int or not 0 <= digits <= 6:
                        raise ValueError("Explicit rounding precision is required")
                    from decimal import Decimal, ROUND_HALF_UP, localcontext
                    with localcontext() as context:
                        context.prec = 40
                        exact = Decimal(str(sympy.N(value, 35)))
                        expected_round = exact.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
                    if numeric_expression(str(expected_round)) != rounded:
                        raise ValueError("The rounded reference is mathematically incorrect")
                self.values[label] = value
        if "CONCLUSION" not in kinds or len(kinds) < 2:
            raise ValueError("Numeric grading requires intermediate evidence and a conclusion")

    def validate_step(self, step_type: str, content_latex: str | None, explanation_text: str | None = None,
                      artifact_payload: dict | None = None):
        from app.math_solutions.validator import ValidationResult, MathValidity
        criterion = next((c for c in self.criteria if c["step_type"] == step_type), None)
        review = ValidationResult(MathValidity.NEEDS_REVIEW, None, 0.0, False,
                                  error_description="Bước này cần đối chiếu các đại lượng trong tiêu chí chấm.")
        if criterion is None or artifact_payload:
            return review
        text = normalize(content_latex or explanation_text or "")
        if not text or len(text) > 3000:
            return review
        expected = {normalize(check["label"]): check for check in criterion["checks"]}
        # A single requested quantity also accepts its numeric expression alone.
        if "=" not in text and len(expected) == 1:
            text = next(iter(expected)) + "=" + text
        chunks = [chunk.strip().rstrip(".") for chunk in re.split(r"[;\n]+", text) if chunk.strip()]
        seen = set()
        invalid = False
        claims = []
        try:
            for chunk in chunks:
                parts = [part.strip() for part in chunk.split("=")]
                label = normalize(parts[0])
                if len(parts) < 2 or label not in expected or label in seen:
                    return review
                seen.add(label)
                target = self.values[label]
                allowed = [target]
                check = expected[label]
                if "rounded" in check:
                    allowed.append(numeric_expression(check["rounded"]))
                claim_valid = True
                for expression in parts[1:]:
                    if re.search(r"(?<![A-Za-z0-9_])" + re.escape(label) + r"(?![A-Za-z0-9_])", normalize(expression)):
                        return review
                    value = numeric_expression(expression, self.values)
                    if not any(sympy.simplify(value - answer) == 0 for answer in allowed):
                        invalid = True
                        claim_valid = False
                claims.append({"label": label, "score": 1.0 if claim_valid else 0.0,
                               "concept_codes": [check["concept_code"]] if check.get("concept_code") else criterion["concept_codes"]})
            if seen != set(expected):
                return review
        except (ValueError, TypeError, OverflowError, ZeroDivisionError):
            return review
        if content_latex and explanation_text and re.search(r"[=<>\\]|P\(", explanation_text):
            explanation = self.validate_step(step_type, None, explanation_text)
            if invalid or explanation.validity != MathValidity.VALID:
                return review
        return ValidationResult(MathValidity.INVALID if invalid else MathValidity.VALID,
                                sum(claim["score"] for claim in claims) / len(expected), 1.0, invalid,
                                "NUMERIC_REFERENCE_MISMATCH" if invalid else None,
                                "Giá trị hoặc phép tính chưa khớp đại lượng được hỏi." if invalid else None,
                                content_latex, {"numeric_checks": claims})
