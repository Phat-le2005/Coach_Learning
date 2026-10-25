"""Conservative guard for PDF text-layer failures in student-facing questions.

This is a presentation check, not academic review. It never repairs or rewrites
mathematics; a source reviewer must supply a faithful display version.
"""

from __future__ import annotations

import unicodedata

from app.questions.models import Question


def has_broken_math_extraction(text: str) -> bool:
    if any(unicodedata.category(char) == "Co" for char in text):
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 10:
        return False
    fragments = sum(len(line) <= 3 for line in lines)
    return fragments >= 6 and fragments * 2 >= len(lines)


def question_has_broken_math_extraction(question: Question) -> bool:
    return has_broken_math_extraction(question.content) or any(
        has_broken_math_extraction(option.content) for option in question.options
    )
