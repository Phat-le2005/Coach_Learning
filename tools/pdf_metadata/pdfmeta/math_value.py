"""Typed table endpoints: exact source expression, symbols, and optional approximation."""
from __future__ import annotations

import math
import re
import sympy as sp

from .safe_math import UnsupportedMath,parse_expression


VERSION='math-value/v1'


def expression(text):
    text=text.strip().strip('$').replace('−','-')
    if len(text)>256:
        raise UnsupportedMath('MATH_VALUE_LENGTH_LIMIT')
    if text in {'+inf','inf',r'+\infty',r'\infty','+∞','∞'}:
        return sp.oo
    if text in {'-inf',r'-\infty','-∞'}:
        return -sp.oo
    text=re.sub(r'\\operatorname\{(ln|log)\}',r'\\\1',text)
    text=re.sub(r'\\(ln|log)\s*(?:\{(\d+)\}|(\d+))',
                lambda m:m[1]+'('+(m[2] or m[3])+')',text)
    text=text.replace('log','ln')
    value=parse_expression(text).expression
    if sp.count_ops(value)>20 or len(value.free_symbols)>3 or value.has(sp.zoo,sp.nan):
        raise UnsupportedMath('MATH_VALUE_COMPLEXITY_OR_DOMAIN')
    if not value.free_symbols and (value.is_real is not True or value.is_finite is not True):
        raise UnsupportedMath('MATH_VALUE_NOT_FINITE_REAL')
    if any(len(str(n))>48 for n in value.atoms(sp.Number)):
        raise UnsupportedMath('MATH_VALUE_NUMBER_LIMIT')
    return value


def record(text):
    value=expression(text)
    symbols=sorted(str(s) for s in value.free_symbols)
    canonical='+inf' if value==sp.oo else '-inf' if value==-sp.oo else sp.sstr(value)
    approximate=None
    if not symbols and value not in {sp.oo,-sp.oo}:
        approximate=float(value.evalf(15))
        if not math.isfinite(approximate):
            approximate=None
    return {'schema_version':VERSION,'source_expression':text,'canonical_expression':canonical,
        'kind':'INFINITY' if value in {sp.oo,-sp.oo} else 'SYMBOLIC_EXPRESSION' if symbols else 'NUMBER' if value.is_Rational else 'CONSTANT_EXPRESSION',
        'symbols':symbols,'approximate_value':approximate,
        'status':'PARSED_CANDIDATE_NOT_SOURCE_VERIFIED'}


def compare(left,right):
    a,b=expression(left),expression(right)
    if a==b:
        return 'EQ'
    if a==sp.oo or b==-sp.oo:
        return 'GT'
    if a==-sp.oo or b==sp.oo:
        return 'LT'
    difference=sp.simplify(a-b)
    return 'LT' if difference.is_negative is True else 'GT' if difference.is_positive is True else 'EQ' if difference.is_zero is True else 'UNKNOWN'
