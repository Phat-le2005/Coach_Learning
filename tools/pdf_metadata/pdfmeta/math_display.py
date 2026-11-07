"""Presentation-only math recovery. Never infer symbols, values or missing terms.

Tokenize once on export so the browser and quality gate see the same boundaries.
The original transcription remains available separately from display markup.
"""
import re
import unicodedata
from pathlib import Path

from .storage import file_hash


VERSION = 'math-display/v1'
CODE_SHA256 = file_hash(Path(__file__))
COMMAND = re.compile(r'\\(?:frac|dfrac|tfrac|overline|bar|sqrt|int|sum|begin|mid|cup|cap)\b')
WORD = re.compile(r'[^\W\d_]+', re.UNICODE)
TEXT_COMMAND = re.compile(r'\\(?:text|textrm|textit|textbf|mathrm|operatorname)\s*\{')
EMPTY_FRACTION = re.compile(r'\\(?:[dt]?frac)\s*\{(?:\s|\\text\{\})*\}|'
                            r'\\(?:[dt]?frac)\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\s*\{(?:\s|\\text\{\})*\}')
SPLIT_LINE = re.compile(r'^\s*[A-Za-z]\([^\n)]+\)(?:\s+\d+(?:[,.]\d+)?){2,}\s*$')


def escaped(value, index):
    count = 0
    while index > 0 and value[index-1] == '\\':
        count += 1
        index -= 1
    return bool(count % 2)


def balanced_braces(value):
    depth = 0
    for i, char in enumerate(value):
        if char in '{}' and not escaped(value, i):
            depth += 1 if char == '{' else -1
            if depth < 0:return False
    return depth == 0


def math_evidence(value):
    return bool(COMMAND.search(value) or re.search(r'[=∩∪]|\bP\s*\(|\\\{.*;|\b[A-Za-z][_^]', value))


def text_in_math(value):
    """Wrap literal accented words; leave macros and existing text groups intact."""
    result = []
    i = 0
    while i < len(value):
        group = TEXT_COMMAND.match(value, i)
        if group:
            end, depth = group.end(), 1
            while end < len(value) and depth:
                if not escaped(value, end):
                    if value[end] == '{':depth += 1
                    elif value[end] == '}':depth -= 1
                end += 1
            result.append(value[i:end]);i = end;continue
        if value[i] == '\\':
            command = re.match(r'\\(?:[A-Za-z]+|.)', value[i:])
            if command:
                result.append(command[0]);i += len(command[0]);continue
        word = WORD.match(value, i)
        if word:
            text = word[0]
            # Accented prose is text. Long lowercase words in event tuples,
            # such as "xanh", are labels; single mathematical variables stay math.
            accented = any(ord(c) > 127 and unicodedata.name(c, '').startswith('LATIN ') for c in text)
            tuple_label = (len(text) >= 3 and text.islower() and text not in {'sin','cos','tan','cot','log','lim','max','min','exp'}
                           and ';' in value and '(' in value)
            result.append(r'\text{' + text + '}' if accented or tuple_label else text)
            i = word.end();continue
        result.append(value[i]);i += 1
    return ''.join(result)


def bare_equation(line):
    """Only recover an explicit equation line, with an optional prose prefix."""
    if '$' in line or '`' in line or '![' in line or not math_evidence(line):return None
    match = re.match(r'^(.*?)([⇒⇔→]?\s*(?:[A-Za-z]\s*\(|[-+]?\d|\\(?:frac|dfrac|sqrt|int|sum)\b|[A-Za-z]\s*[=^_]).*)$', line)
    if not match:return None
    prefix, formula = match.groups()
    leading = len(formula)-len(formula.lstrip())
    prefix += formula[:leading]
    formula = formula[leading:]
    # Do not swallow prose after a bare formula into math mode.
    if any(ord(c) > 127 and c.isalpha() for c in formula):return None
    if '=' not in formula and not COMMAND.search(formula):return None
    if not balanced_braces(formula):return None
    suffix = ''
    punct = re.search(r'\s*[.,;]\s*$', formula)
    if punct:
        formula, suffix = formula[:punct.start()], punct[0]
    return prefix + '$' + formula + '$' + suffix


def prepare(markdown):
    tokens, repairs, issues = [], [], []
    def text(value):
        if not value:return
        if tokens and tokens[-1]['kind'] == 'text':tokens[-1]['text'] += value
        else:tokens.append({'kind':'text','text':value})
    def math(latex, display, raw, repair=None):
        normalized = text_in_math(latex)
        if normalized != latex:repairs.append('LITERAL_TEXT_IN_MATH_WRAPPED')
        if repair:repairs.append(repair)
        errors = []
        if EMPTY_FRACTION.search(normalized):errors.append('EMPTY_FRACTION_ARGUMENT')
        if not balanced_braces(normalized):errors.append('UNBALANCED_MATH_BRACES')
        issues.extend(errors)
        tokens.append({'kind':'math','latex':normalized,'display':display,'raw':raw,'issues':errors})
    # Inline expressions are line-scoped. A malformed delimiter cannot consume
    # the prose or subsequent equations on another line.
    lines = markdown.splitlines(keepends=True)
    code_fence = None
    in_display = None
    display_lines = []
    for original in lines:
        fence = re.match(r'^\s*(`{3,}|~{3,})', original)
        if fence:
            if code_fence is None:code_fence = fence[1][0]
            elif fence[1][0] == code_fence:code_fence = None
            text(original);continue
        if code_fence:
            text(original);continue
        if in_display:
            end = original.find(in_display)
            if end < 0:
                display_lines.append(original);continue
            display_lines.append(original[:end])
            latex = ''.join(display_lines)
            math(latex, True, '$$'+latex+'$$')
            original = original[end+len(in_display):]
            in_display, display_lines = None, []
        if SPLIT_LINE.fullmatch(original.strip()):issues.append('POSSIBLE_SPLIT_FORMULA')
        line = bare_equation(original.rstrip('\r\n'))
        if line is not None:
            line += original[len(original.rstrip('\r\n')):]
            repairs.append('EXPLICIT_EQUATION_DELIMITED')
        else:line = original
        cursor = 0
        while cursor < len(line):
            if line[cursor] == '`':
                ticks = re.match(r'`+', line[cursor:])[0]
                end = line.find(ticks, cursor+len(ticks))
                if end >= 0:
                    text(line[cursor:end+len(ticks)]);cursor = end+len(ticks);continue
            image = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line[cursor:])
            if image:
                tokens.append({'kind':'image','alt':image[1],'path':image[2]})
                cursor += image.end();continue
            delim = None
            if line.startswith(r'\(', cursor):delim, closing = r'\(', r'\)'
            elif line.startswith(r'\[', cursor):delim, closing = r'\[', r'\]'
            elif line[cursor] == '$' and not escaped(line, cursor):
                delim = '$$' if line.startswith('$$', cursor) else '$'
                closing = delim
            if not delim:
                text(line[cursor]);cursor += 1;continue
            start = cursor+len(delim)
            end = line.find(closing, start)
            while end >= 0 and closing.startswith('$') and escaped(line, end):
                end = line.find(closing, end+len(closing))
            repair = None
            if end < 0 and delim in {'$$', r'\['}:
                in_display, display_lines = closing, [line[start:]]
                break
            if end < 0 and delim == '$':
                # A model may escape the closing delimiter as a literal dollar.
                wrong = re.search(r'\\\$([.,;:]?\s*)$', line[start:])
                if wrong and math_evidence(line[start:start+wrong.start()]):
                    end = start+wrong.start()
                    closing = r'\$'
                    repair = 'ESCAPED_CLOSING_MATH_DELIMITER_FIXED'
                else:
                    tail = line[start:].rstrip('\r\n')
                    if math_evidence(tail) and balanced_braces(tail):
                        math(tail, False, '$'+tail, 'MISSING_CLOSING_MATH_DELIMITER_ADDED')
                        text(line[start+len(tail):]);break
                    if re.match(r'\d', tail) and not math_evidence(tail):
                        text(line[cursor:]);break
            if end < 0:
                issues.append('UNBALANCED_MATH_DELIMITERS')
                text(line[cursor:]);break
            latex = line[start:end]
            if (delim == '$' and re.match(r'\d', latex) and not math_evidence(latex)
                    and re.search(r'\s[^\W\d_]{2,}', latex) and re.match(r'\d', line[end+1:])):
                text(line[cursor:]);break
            math(latex, delim in {'$$', r'\['}, line[cursor:end+len(closing)], repair)
            cursor = end+len(closing)
    if in_display:
        text(('$$' if in_display == '$$' else r'\[')+''.join(display_lines))
        issues.append('UNBALANCED_MATH_DELIMITERS')
    normalized = ''.join(t['text'] if t['kind']=='text' else
                         '!['+t['alt']+']('+t['path']+')' if t['kind']=='image' else
                         ('$$' if t['display'] else '$')+t['latex']+('$$' if t['display'] else '$') for t in tokens)
    return {'markdown':normalized,'tokens':tokens,'repairs':list(dict.fromkeys(repairs)),
            'issues':list(dict.fromkeys(issues))}
