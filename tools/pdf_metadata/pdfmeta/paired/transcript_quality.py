"""Fail-closed checks for image transcription; no model can grant approval."""
from collections import Counter
import re

from .math_recovery import latex_tokens


def notation(text):
    text=latex_tokens(text)
    text=re.sub(r'\\(?:bigl|bigr|Bigl|Bigr|big|Big)\b','',text)
    return text.replace(r'\dfrac',r'\frac').replace(r'\tfrac',r'\frac')


def check_source_tokens(source,latex):
    # Geometry gives a digit multiset without inventing a 2D reading order.
    # Agreement here is necessary, not sufficient (12 and 21 share digits).
    digits=lambda s:Counter(re.findall(r'[0-9]',s))
    issues=[]
    if digits(source)!=digits(latex):issues.append('SOURCE_DIGITS_CHANGED')
    signs=lambda s:Counter(c for c in s.replace('−','-').replace('–','-') if c in '=+')
    if signs(source)!=signs(latex):issues.append('SOURCE_EQUALITY_OR_PLUS_CHANGED')
    minus=lambda s:s.replace('−','-').replace('–','-').count('-')
    if minus(source)!=minus(latex):issues.append('SOURCE_MINUS_SIGNS_CHANGED')
    return issues


def display_decision(source,primary,secondary,syntax,signals):
    reasons=check_source_tokens(source,primary)
    if syntax['status']!='PASS':reasons.append('LATEX_SYNTAX_FAILURE')
    if notation(primary)!=notation(secondary):reasons.append('LOCAL_FORMULA_MODELS_DISAGREE')
    guards=[('absolute_bars',r'\||\\(?:[lr]?vert|abs)\b'),('overlines',r'\\(?:overline|bar)\b'),
            ('lower_glyphs',r'_'),('top_bars',r'\\(?:sqrt|frac|dfrac|tfrac|overline)\b')]
    for key,pattern in guards:
        if signals.get(key) and not re.search(pattern,primary):reasons.append('SOURCE_STRUCTURE_NOT_PRESERVED_'+key.upper())
    if re.search(r'\\begin\{(?:aligned|array|matrix|cases)',primary):reasons.append('COMPOUND_LAYOUT_REQUIRES_SOURCE_REVIEW')
    return {'display_latex':None if reasons else primary,'issues':reasons,
            'status':'SOURCE_REVIEW_REQUIRED' if reasons else 'TWO_LOCAL_MODELS_AGREE_DRAFT',
            'academic_review':'PENDING','publishable':False}
